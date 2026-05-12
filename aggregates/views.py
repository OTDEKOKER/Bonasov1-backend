from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
import django_filters
from rest_framework.filters import OrderingFilter
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.http import HttpResponse
import csv
import json
from io import BytesIO

from .models import Aggregate
from .pagination import AggregatePagination
from .serializers import AggregateSerializer
from indicators.models import Indicator
from flags.models import Flag
from projects.models import Project
from respondents.models import Response as InteractionResponse
from organizations.access import get_user_organization_ids, is_organization_admin, filter_queryset_by_org_ids
from organizations.models import Organization
from respondents.rollups import sync_project_indicator_total
from users.models import User
from messaging.notifications import (
    AggregateNotificationContext,
    notify_aggregate_status_to_submitter,
    notify_aggregate_submitted_for_review,
)


class AggregateFilterSet(django_filters.FilterSet):
    """Allow comma-separated status filters from the review queue UI."""

    status = django_filters.CharFilter(method="filter_status")
    organization = django_filters.CharFilter(method="filter_organization")
    coordinator = django_filters.CharFilter(method="filter_coordinator")
    include_org_descendants = django_filters.CharFilter(method="filter_include_org_descendants")
    date_from = django_filters.DateFilter(field_name="period_start", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="period_end", lookup_expr="lte")

    class Meta:
        model = Aggregate
        fields = {
            "indicator": ["exact"],
            "project": ["exact"],
            "period_start": ["exact"],
            "period_end": ["exact"],
        }

    def _to_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _org_scope_with_descendants(self, org_id: int):
        organization = Organization.objects.filter(id=org_id).first()
        if not organization:
            return []
        descendants = organization.get_descendants()
        return [organization.id] + [child.id for child in descendants]

    def _is_truthy(self, value):
        return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    def filter_status(self, queryset, name, value):
        statuses = [item.strip() for item in str(value).split(",") if item.strip()]
        if not statuses:
            return queryset
        return queryset.filter(status__in=statuses)

    def filter_organization(self, queryset, name, value):
        org_id = self._to_int(value)
        if org_id is None:
            return queryset.none()
        include_descendants = self._is_truthy(self.data.get("include_org_descendants"))
        if include_descendants:
            scoped_org_ids = self._org_scope_with_descendants(org_id)
            if not scoped_org_ids:
                return queryset.none()
            return queryset.filter(organization_id__in=scoped_org_ids)
        return queryset.filter(organization_id=org_id)

    def filter_coordinator(self, queryset, name, value):
        coordinator_id = self._to_int(value)
        if coordinator_id is None:
            return queryset.none()
        scoped_org_ids = self._org_scope_with_descendants(coordinator_id)
        if not scoped_org_ids:
            return queryset.none()
        return queryset.filter(organization_id__in=scoped_org_ids)

    def filter_include_org_descendants(self, queryset, name, value):
        return queryset


class AggregateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing aggregate data."""
    
    queryset = Aggregate.objects.all()
    serializer_class = AggregateSerializer
    pagination_class = AggregatePagination
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AggregateFilterSet
    ordering_fields = ['period_start', 'period_end', 'created_at']
    ordering = ['-period_start']

    def _notification_context(self, aggregate: Aggregate) -> AggregateNotificationContext:
        indicator_label = (
            (getattr(aggregate.indicator, 'code', None) or '').strip()
            or (getattr(aggregate.indicator, 'name', None) or '').strip()
            or f"Indicator {aggregate.indicator_id}"
        )
        organization_name = (
            (getattr(aggregate.organization, 'name', None) or '').strip()
            or f"Organization {aggregate.organization_id}"
        )
        return AggregateNotificationContext(
            aggregate_id=int(aggregate.id),
            organization_id=int(aggregate.organization_id),
            indicator_label=indicator_label,
            organization_name=organization_name,
            period_start=aggregate.period_start.isoformat() if aggregate.period_start else '',
            period_end=aggregate.period_end.isoformat() if aggregate.period_end else '',
        )

    def _notify_pending_submission(self, aggregate: Aggregate) -> None:
        notify_aggregate_submitted_for_review(
            context=self._notification_context(aggregate),
            actor=self.request.user,
        )

    def _notify_status_change(self, aggregate: Aggregate, status_value: str) -> None:
        notify_aggregate_status_to_submitter(
            context=self._notification_context(aggregate),
            actor=self.request.user,
            submitter=aggregate.created_by,
            status_value=status_value,
        )
    
    def get_queryset(self):
        queryset = Aggregate.objects.select_related(
            'indicator', 'project', 'organization', 'created_by', 'reviewed_by'
        )
        user = self.request.user
        if is_organization_admin(user):
            return queryset
        org_ids = get_user_organization_ids(user)
        if org_ids:
            return filter_queryset_by_org_ids(queryset, 'organization_id', org_ids)
        return Aggregate.objects.none()
    
    def _upsert_pending_aggregate(
        self,
        *,
        indicator,
        project,
        organization,
        period_start,
        period_end,
        value,
        notes,
    ):
        existing = Aggregate.objects.filter(
            indicator=indicator,
            project=project,
            organization=organization,
            period_start=period_start,
            period_end=period_end,
        ).first()
        previous_status = existing.status if existing else None
        aggregate, created = Aggregate.objects.update_or_create(
            indicator=indicator,
            project=project,
            organization=organization,
            period_start=period_start,
            period_end=period_end,
            defaults={
                'value': value,
                'notes': notes or "",
                'status': 'pending',
                'reviewed_at': None,
                'reviewed_by': None,
                'created_by': self.request.user,
            },
        )
        if previous_status == 'approved':
            sync_project_indicator_total(aggregate.project_id, aggregate.indicator_id)
        return aggregate, created

    def perform_create(self, serializer):
        validated = serializer.validated_data
        aggregate, _created = self._upsert_pending_aggregate(
            indicator=validated['indicator'],
            project=validated['project'],
            organization=validated['organization'],
            period_start=validated['period_start'],
            period_end=validated['period_end'],
            value=validated.get('value'),
            notes=validated.get('notes'),
        )
        serializer.instance = aggregate
        self._notify_pending_submission(aggregate)

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        aggregate = serializer.save(
            status='pending',
            reviewed_at=None,
            reviewed_by=None,
        )
        self._notify_pending_submission(aggregate)
        if previous_status == 'approved' or aggregate.status == 'approved':
            sync_project_indicator_total(aggregate.project_id, aggregate.indicator_id)

    def perform_destroy(self, instance):
        project_id = instance.project_id
        indicator_id = instance.indicator_id
        should_sync = instance.status == 'approved'
        super().perform_destroy(instance)
        if should_sync:
            sync_project_indicator_total(project_id, indicator_id)

    def _mark_review_state(self, aggregate, status_value):
        previous_status = aggregate.status
        aggregate.status = status_value
        if status_value == 'pending':
            aggregate.reviewed_at = None
            aggregate.reviewed_by = None
        else:
            aggregate.reviewed_at = timezone.now()
            aggregate.reviewed_by = self.request.user
        aggregate.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'updated_at'])
        self._notify_status_change(aggregate, status_value)
        if previous_status == 'approved' or status_value == 'approved':
            sync_project_indicator_total(aggregate.project_id, aggregate.indicator_id)
        return aggregate

    def _reporting_queryset(self):
        queryset = self.filter_queryset(self.get_queryset())
        status_filter = self.request.query_params.get('status')
        if status_filter:
            statuses = [value.strip() for value in status_filter.split(',') if value.strip()]
            if statuses:
                return queryset.filter(status__in=statuses)
        return queryset.filter(status='approved')

    def _extract_total(self, value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            if value.get('total') is not None:
                return float(value.get('total') or 0)
            male = float(value.get('male') or 0)
            female = float(value.get('female') or 0)
            return male + female
        return 0.0

    def _normalize_match_tokens(self, raw_value):
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        tokens = set()
        for value in values:
            if value is None:
                continue
            normalized = str(value).strip().lower()
            if normalized:
                tokens.add(normalized)
        return tokens

    def _response_matches(self, response_value, operator, match_tokens):
        if not match_tokens:
            return response_value not in (None, "", [], {})

        if isinstance(response_value, list):
            response_tokens = {
                str(item).strip().lower()
                for item in response_value
                if str(item).strip()
            }
            response_text = " ".join(sorted(response_tokens))
        elif isinstance(response_value, dict):
            response_tokens = {
                str(item).strip().lower()
                for item in response_value.values()
                if str(item).strip()
            }
            response_text = json.dumps(response_value, sort_keys=True).lower()
        else:
            normalized = str(response_value).strip().lower() if response_value is not None else ""
            response_tokens = {normalized} if normalized else set()
            response_text = normalized

        if operator == 'contains':
            return any(token in response_text for token in match_tokens)
        if operator == 'not_equals':
            return not any(token in response_tokens for token in match_tokens)
        return any(token in response_tokens for token in match_tokens)

    @action(detail=False, methods=['post'])
    def generate_from_interactions(self, request):
        """Compute an aggregate from respondent interactions and optionally save it."""
        output_indicator_id = request.data.get('output_indicator')
        source_indicator_id = request.data.get('source_indicator')
        project_id = request.data.get('project')
        organization_id = request.data.get('organization')
        period_start = request.data.get('period_start')
        period_end = request.data.get('period_end')
        operator = str(request.data.get('operator') or 'equals')
        match_value = request.data.get('match_value')
        count_distinct = str(request.data.get('count_distinct') or 'respondent')
        save_rule = bool(request.data.get('save_rule', False))
        save_aggregate = bool(request.data.get('save_aggregate', False))

        if not all([output_indicator_id, source_indicator_id, project_id, organization_id, period_start, period_end]):
            return Response(
                {'detail': 'output_indicator, source_indicator, project, organization, period_start, and period_end are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if operator not in {'equals', 'not_equals', 'contains'}:
            return Response(
                {'detail': 'operator must be equals, not_equals, or contains.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if count_distinct not in {'respondent', 'interaction'}:
            return Response(
                {'detail': 'count_distinct must be respondent or interaction.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            organization_id_int = int(organization_id)
        except (TypeError, ValueError):
            return Response({'detail': 'organization must be a valid id.'}, status=status.HTTP_400_BAD_REQUEST)

        allowed_org_ids = set(get_user_organization_ids(request.user) or [])
        if not is_organization_admin(request.user) and organization_id_int not in allowed_org_ids:
            return Response(
                {'detail': 'You do not have permission to generate aggregates for this organization.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            output_indicator = Indicator.objects.get(id=output_indicator_id)
        except Indicator.DoesNotExist:
            return Response({'detail': 'Output indicator not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not Indicator.objects.filter(id=source_indicator_id).exists():
            return Response({'detail': 'Source indicator not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not Project.objects.filter(id=project_id).exists():
            return Response({'detail': 'Project not found.'}, status=status.HTTP_404_NOT_FOUND)

        match_tokens = self._normalize_match_tokens(match_value)
        responses = InteractionResponse.objects.select_related(
            'interaction',
            'interaction__respondent',
        ).filter(
            indicator_id=source_indicator_id,
            interaction__project_id=project_id,
            interaction__respondent__organization_id=organization_id_int,
            interaction__date__gte=period_start,
            interaction__date__lte=period_end,
        )

        matched_responses = [
            response
            for response in responses
            if self._response_matches(response.value, operator, match_tokens)
        ]

        if count_distinct == 'interaction':
            computed = len({response.interaction_id for response in matched_responses})
        else:
            computed = len({response.interaction.respondent_id for response in matched_responses})

        aggregate_payload = None
        if save_aggregate:
            aggregate, _created = self._upsert_pending_aggregate(
                indicator=output_indicator,
                project=Project.objects.get(id=project_id),
                organization=Organization.objects.get(id=organization_id_int),
                period_start=period_start,
                period_end=period_end,
                value={'total': computed},
                notes=(
                    f"Auto-calculated from source indicator {source_indicator_id} "
                    f"using operator '{operator}' and distinct-by '{count_distinct}'."
                ),
            )
            self._notify_pending_submission(aggregate)
            aggregate_payload = AggregateSerializer(aggregate).data

        return Response(
            {
                'computed': computed,
                'rule': {
                    'output_indicator': int(output_indicator_id),
                    'output_indicator_code': output_indicator.code,
                    'source_indicator': int(source_indicator_id),
                    'operator': operator,
                    'match_value': match_value,
                    'count_distinct': count_distinct,
                    'project': int(project_id),
                    'organization': organization_id_int,
                    'period_start': period_start,
                    'period_end': period_end,
                    'save_rule_requested': save_rule,
                },
                'aggregate': aggregate_payload,
            }
        )
    
    @action(detail=False, methods=['get'])
    def by_indicator(self, request):
        """Get aggregates grouped by indicator."""
        indicator_id = request.query_params.get('indicator_id')
        if not indicator_id:
            return Response({'error': 'indicator_id required'}, status=400)
        
        aggregates = self._reporting_queryset().filter(indicator_id=indicator_id)
        return Response(AggregateSerializer(aggregates, many=True).data)

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Bulk create aggregates."""
        project_id = request.data.get('project')
        organization_id = request.data.get('organization')
        period_start = request.data.get('period_start')
        period_end = request.data.get('period_end')
        data = request.data.get('data', [])

        if not project_id or not organization_id or not period_start or not period_end:
            return Response(
                {'error': 'project, organization, period_start, period_end required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not isinstance(data, list) or not data:
            return Response({'error': 'data list required'}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        created_count = 0
        updated_count = 0
        try:
            with transaction.atomic():
                for item in data:
                    serializer = AggregateSerializer(data={
                        'indicator': item.get('indicator'),
                        'project': project_id,
                        'organization': organization_id,
                        'period_start': period_start,
                        'period_end': period_end,
                        'value': item.get('value'),
                        'notes': item.get('notes'),
                    })
                    serializer.is_valid(raise_exception=True)
                    validated = serializer.validated_data
                    aggregate, created = self._upsert_pending_aggregate(
                        indicator=validated['indicator'],
                        project=validated['project'],
                        organization=validated['organization'],
                        period_start=validated['period_start'],
                        period_end=validated['period_end'],
                        value=validated.get('value'),
                        notes=validated.get('notes'),
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                    self._notify_pending_submission(aggregate)
                    results.append(AggregateSerializer(aggregate).data)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'created': created_count,
                'updated': updated_count,
                'results': results,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['get'])
    def templates(self, request):
        """Return aggregate templates (indicator sets)."""
        project_id = request.query_params.get('project')
        organization_id = request.query_params.get('organization')
        indicators = Indicator.objects.filter(is_active=True)

        if project_id and Project.objects.filter(id=project_id).exists():
            indicators = indicators.filter(projects__id=project_id).distinct()
            template_name = f"Project {project_id} Indicators"
        elif organization_id:
            indicators = indicators.filter(organizations__id=organization_id).distinct()
            template_name = "Organization Indicators"
        else:
            template_name = "All Indicators"

        payload = [{
            'id': 1,
            'name': template_name,
            'indicators': [
                {
                    'id': indicator.id,
                    'name': indicator.name,
                    'code': indicator.code,
                    'type': indicator.type,
                    'disaggregation_fields': [],
                }
                for indicator in indicators
            ],
        }]
        return Response(payload)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get aggregate summary by indicator."""
        queryset = self._reporting_queryset()
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(period_start__gte=date_from)
        if date_to:
            queryset = queryset.filter(period_end__lte=date_to)
        totals = {}
        counts = {}
        for agg in queryset:
            totals[agg.indicator_id] = totals.get(agg.indicator_id, 0.0) + self._extract_total(agg.value)
            counts[agg.indicator_id] = counts.get(agg.indicator_id, 0) + 1

        indicators = Indicator.objects.filter(id__in=totals.keys())
        results = []
        for indicator in indicators:
            results.append({
                'indicator_id': indicator.id,
                'indicator_name': indicator.name,
                'total_value': totals.get(indicator.id, 0.0),
                'period_count': counts.get(indicator.id, 0),
                'trend': 'stable',
            })
        return Response(results)

    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export aggregates to CSV or Excel."""
        fmt = request.query_params.get('file_format', 'csv').lower()
        if fmt not in {'csv', 'excel'}:
            fmt = 'csv'
        queryset = self._reporting_queryset().select_related('indicator', 'project', 'organization')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(period_start__gte=date_from)
        if date_to:
            queryset = queryset.filter(period_end__lte=date_to)

        rows = []
        for agg in queryset:
            value = agg.value
            male = None
            female = None
            total = None
            if isinstance(value, dict):
                male = value.get('male')
                female = value.get('female')
                total = value.get('total')
            elif isinstance(value, (int, float)):
                total = value

            rows.append({
                'indicator_id': agg.indicator_id or '',
                'indicator_name': agg.indicator.name if agg.indicator_id else '',
                'indicator_code': agg.indicator.code if agg.indicator_id else '',
                'project_id': agg.project_id or '',
                'project_name': agg.project.name if agg.project_id else '',
                'organization_id': agg.organization_id or '',
                'organization_name': agg.organization.name if agg.organization_id else '',
                'period_start': agg.period_start.isoformat(),
                'period_end': agg.period_end.isoformat(),
                'male': male if male is not None else '',
                'female': female if female is not None else '',
                'total': total if total is not None else '',
                'value_json': json.dumps(value, ensure_ascii=False) if value is not None else '',
                'notes': agg.notes or '',
            })

        if fmt == 'excel':
            try:
                import openpyxl
            except Exception as exc:
                return Response({'error': f'Excel export not available: {exc}'}, status=500)

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'aggregates'
            if rows:
                ws.append(list(rows[0].keys()))
                for row in rows:
                    ws.append(list(row.values()))
            output = BytesIO()
            wb.save(output)
            output.seek(0)
            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = 'attachment; filename="aggregates.xlsx"'
            return response

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="aggregates.csv"'
        writer = csv.writer(response)
        if rows:
            writer.writerow(rows[0].keys())
            for row in rows:
                writer.writerow(row.values())
        return response

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Mark an aggregate as reviewed and send it back through the approval queue."""
        aggregate = self.get_object()
        return Response(AggregateSerializer(self._mark_review_state(aggregate, 'reviewed')).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve an aggregate so it appears in the main aggregate view."""
        aggregate = self.get_object()
        return Response(AggregateSerializer(self._mark_review_state(aggregate, 'approved')).data)

    @action(detail=False, methods=['post'])
    def bulk_approve(self, request):
        """Approve multiple queued aggregates at once."""
        if not is_organization_admin(request.user):
            return Response({'error': 'admin access required'}, status=status.HTTP_403_FORBIDDEN)

        raw_ids = request.data.get('ids', [])
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response({'error': 'ids list required'}, status=status.HTTP_400_BAD_REQUEST)

        aggregate_ids = []
        for value in raw_ids:
            try:
                aggregate_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        if not aggregate_ids:
            return Response({'error': 'ids list required'}, status=status.HTTP_400_BAD_REQUEST)

        approved_count = 0
        skipped = 0
        affected_pairs = set()
        reviewed_at = timezone.now()
        with transaction.atomic():
            aggregate_rows = list(
                self.get_queryset().filter(
                    id__in=aggregate_ids,
                    status__in=['pending', 'reviewed'],
                ).values(
                    'id',
                    'project_id',
                    'indicator_id',
                    'created_by_id',
                    'organization_id',
                    'organization__name',
                    'indicator__code',
                    'indicator__name',
                    'period_start',
                    'period_end',
                )
            )

            found_ids = {row['id'] for row in aggregate_rows}
            affected_pairs = {
                (row['project_id'], row['indicator_id'])
                for row in aggregate_rows
            }

            if found_ids:
                approved_count = Aggregate.objects.filter(id__in=found_ids).update(
                    status='approved',
                    reviewed_at=reviewed_at,
                    reviewed_by_id=request.user.id,
                    updated_at=reviewed_at,
                )

            skipped = len(set(aggregate_ids) - found_ids)

        for project_id, indicator_id in affected_pairs:
            sync_project_indicator_total(project_id, indicator_id)

        for row in aggregate_rows:
            submitter_id = row.get('created_by_id')
            if not submitter_id or submitter_id == request.user.id:
                continue
            submitter = User.objects.filter(id=submitter_id, is_active=True).first()
            if not submitter:
                continue
            indicator_label = (row.get('indicator__code') or row.get('indicator__name') or '').strip() or f"Indicator {row.get('indicator_id')}"
            organization_name = (row.get('organization__name') or '').strip() or f"Organization {row.get('organization_id')}"
            context = AggregateNotificationContext(
                aggregate_id=int(row['id']),
                organization_id=int(row['organization_id']),
                indicator_label=indicator_label,
                organization_name=organization_name,
                period_start=row['period_start'].isoformat() if row.get('period_start') else '',
                period_end=row['period_end'].isoformat() if row.get('period_end') else '',
            )
            notify_aggregate_status_to_submitter(
                context=context,
                actor=request.user,
                submitter=submitter,
                status_value='approved',
            )

        return Response(
            {
                'approved': approved_count,
                'skipped': skipped,
                'results': [],
            }
        )

    @action(detail=True, methods=['post'])
    def flag(self, request, pk=None):
        """Flag an aggregate for data quality review."""
        aggregate = self.get_object()
        reason = str(request.data.get('reason') or 'other')
        description = str(request.data.get('description') or '').strip()
        severity = str(request.data.get('severity') or 'medium')
        priority_map = {
            'low': 'low',
            'medium': 'medium',
            'high': 'high',
            'critical': 'critical',
        }
        flag = Flag.objects.create(
            flag_type='data_quality',
            status='open',
            priority=priority_map.get(severity, 'medium'),
            title=f"Aggregate review flag: {aggregate.indicator.code or aggregate.indicator.name}",
            description=description or f"Aggregate flagged during review ({reason}).",
            content_type='aggregate',
            object_id=aggregate.id,
            organization=aggregate.organization,
            created_by=request.user,
        )
        flagged_aggregate = self._mark_review_state(aggregate, 'flagged')
        response_data = AggregateSerializer(flagged_aggregate).data
        response_data['flag_id'] = flag.id
        return Response(response_data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject an aggregate so it does not appear in aggregate reporting."""
        aggregate = self.get_object()
        return Response(AggregateSerializer(self._mark_review_state(aggregate, 'rejected')).data)

