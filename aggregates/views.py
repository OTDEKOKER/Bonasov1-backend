from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.http import HttpResponse
import csv
import json
from io import BytesIO

from .models import Aggregate, AggregateChangeLog, DerivationRule
from .serializers import (
    AggregateFlagSerializer,
    AggregateListSerializer,
    AggregateSerializer,
    AggregateReviewSerializer,
    DerivationRuleSerializer,
    GenerateFromInteractionsSerializer,
)
from core.permissions import is_platform_admin
from flags.models import Flag, FlagComment
from indicators.models import Indicator
from messaging.models import Notification
from projects.models import Project
from respondents.models import Response as InteractionResponse


class AggregateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing aggregate data."""
    
    queryset = Aggregate.objects.all()
    serializer_class = AggregateListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['indicator', 'project', 'organization', 'period_start', 'period_end', 'status', 'reviewed_by']
    ordering_fields = ['period_start', 'period_end', 'created_at', 'reviewed_at']
    ordering = ['-period_start']

    FLAG_REASON_LABELS = {
        'duplicate': 'Duplicate entry',
        'incorrect_data': 'Incorrect data',
        'suspicious': 'Suspicious values',
        'incomplete': 'Incomplete information',
        'other': 'Other issue',
    }

    FLAG_PRIORITY_MAP = {
        'low': 'low',
        'medium': 'medium',
        'high': 'high',
    }

    TRACKED_FIELD_LABELS = {
        'indicator': 'Indicator',
        'project': 'Project',
        'organization': 'Organization',
        'period_start': 'Period start',
        'period_end': 'Period end',
        'notes': 'Notes',
        'value': 'Captured values',
        'status': 'Status',
    }

    def _json_safe(self, value):
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        return value

    def _snapshot_aggregate(self, aggregate):
        return {
            'indicator': aggregate.indicator_id,
            'project': aggregate.project_id,
            'organization': aggregate.organization_id,
            'period_start': aggregate.period_start,
            'period_end': aggregate.period_end,
            'notes': aggregate.notes or '',
            'value': self._json_safe(aggregate.value),
            'status': aggregate.status,
        }

    def _build_change_set(self, before, after):
        changes = {}
        for field_name, label in self.TRACKED_FIELD_LABELS.items():
            before_value = self._json_safe(before.get(field_name))
            after_value = self._json_safe(after.get(field_name))
            if before_value != after_value:
                changes[field_name] = {
                    'label': label,
                    'from': before_value,
                    'to': after_value,
                }
        return changes

    def _record_history(self, aggregate, action, user=None, comment='', changes=None):
        AggregateChangeLog.objects.create(
            aggregate=aggregate,
            action=action,
            changed_by=user if getattr(user, 'is_authenticated', False) else None,
            comment=(comment or '').strip(),
            changes=changes or {},
        )

    def _notify_user(self, user, title, content, link=''):
        if not user:
            return
        Notification.objects.create(
            user=user,
            title=title,
            content=content,
            link=link or '',
        )

    def _get_active_flag(self, aggregate):
        return (
            Flag.objects.filter(content_type='aggregate', object_id=aggregate.id)
            .exclude(status__in=['resolved', 'dismissed'])
            .order_by('-created_at', '-id')
            .first()
        )

    def _set_active_flag_status(self, aggregate, status_value, resolution_notes=''):
        active_flag = self._get_active_flag(aggregate)
        if not active_flag:
            return None
        active_flag.status = status_value
        if status_value == 'resolved':
            active_flag.resolution_notes = resolution_notes or active_flag.resolution_notes
            active_flag.resolved_at = timezone.now()
            active_flag.resolved_by = self.request.user
            active_flag.save(
                update_fields=['status', 'resolution_notes', 'resolved_at', 'resolved_by', 'updated_at']
            )
        else:
            active_flag.resolution_notes = resolution_notes or active_flag.resolution_notes
            active_flag.resolved_at = None
            active_flag.resolved_by = None
            active_flag.save(
                update_fields=['status', 'resolution_notes', 'resolved_at', 'resolved_by', 'updated_at']
            )
        return active_flag

    def _ensure_flag_for_correction(self, aggregate, user, reason_label, description, severity):
        flag_title = f"Aggregate requires correction: {aggregate.indicator.code}"
        base_comment = f"Reason: {reason_label}."
        if description:
            base_comment = f"{base_comment} {description}"

        active_flag = self._get_active_flag(aggregate)
        if active_flag:
            active_flag.status = 'open'
            active_flag.priority = self.FLAG_PRIORITY_MAP.get(severity, 'medium')
            active_flag.title = flag_title
            active_flag.description = (
                f"Aggregate {aggregate.indicator.code} for {aggregate.organization.name} "
                f"({aggregate.period_start} to {aggregate.period_end}) requires correction."
            )
            active_flag.resolution_notes = ''
            active_flag.resolved_at = None
            active_flag.resolved_by = None
            active_flag.assigned_to = aggregate.created_by
            active_flag.save(
                update_fields=[
                    'status',
                    'priority',
                    'title',
                    'description',
                    'resolution_notes',
                    'resolved_at',
                    'resolved_by',
                    'assigned_to',
                    'updated_at',
                ]
            )
            FlagComment.objects.create(flag=active_flag, content=base_comment, created_by=user)
            return active_flag

        created_flag = Flag.objects.create(
            flag_type='data_quality',
            priority=self.FLAG_PRIORITY_MAP.get(severity, 'medium'),
            title=flag_title,
            description=(
                f"Aggregate {aggregate.indicator.code} for {aggregate.organization.name} "
                f"({aggregate.period_start} to {aggregate.period_end}) requires correction."
            ),
            content_type='aggregate',
            object_id=aggregate.id,
            organization_id=aggregate.organization_id,
            assigned_to=aggregate.created_by,
            created_by=user,
        )
        FlagComment.objects.create(flag=created_flag, content=base_comment, created_by=user)
        return created_flag

    def _get_manager_scope_ids(self, user):
        if not getattr(user, 'organization_id', None):
            return []
        organization = user.organization
        descendants = organization.get_descendants() if organization else []
        return [organization.id, *[item.id for item in descendants if item.id != organization.id]]

    def _can_write_organization(self, user, organization_id):
        if is_platform_admin(user):
            return True
        return bool(getattr(user, 'organization_id', None) and int(user.organization_id) == int(organization_id))

    def _can_review_aggregate(self, user, aggregate):
        if is_platform_admin(user):
            return True
        if getattr(user, 'role', None) != 'manager':
            return False
        return int(aggregate.organization_id) in self._get_manager_scope_ids(user)

    def _append_audit_note(self, aggregate, label, note):
        detail = (note or '').strip()
        entry = f"{label}: {detail}" if detail else label
        aggregate.notes = "\n".join(filter(None, [aggregate.notes.strip(), entry])).strip()
    
    def get_queryset(self):
        user = self.request.user
        base_queryset = Aggregate.objects.select_related(
            'indicator',
            'project',
            'organization',
            'created_by',
            'reviewed_by',
        )
        if self.action == 'retrieve':
            base_queryset = base_queryset.prefetch_related('history_entries__changed_by')
        if is_platform_admin(user):
            return base_queryset
        elif getattr(user, 'role', None) == 'manager' and user.organization:
            return base_queryset.filter(organization_id__in=self._get_manager_scope_ids(user))
        elif user.organization:
            return base_queryset.filter(organization=user.organization)
        return base_queryset.none()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AggregateSerializer
        return super().get_serializer_class()
    
    def perform_create(self, serializer):
        organization_id = serializer.validated_data.get('organization').id
        if not self._can_write_organization(self.request.user, organization_id):
            raise PermissionError('Not allowed for this organization.')
        aggregate = serializer.save(
            created_by=self.request.user,
            status=Aggregate.STATUS_PENDING,
            reviewed_at=None,
            reviewed_by=None,
        )
        self._record_history(
            aggregate,
            AggregateChangeLog.ACTION_SUBMITTED,
            user=self.request.user,
            comment='Aggregate submitted for coordinator review.',
            changes=self._build_change_set({}, self._snapshot_aggregate(aggregate)),
        )

    def perform_update(self, serializer):
        instance = self.get_object()
        next_organization = serializer.validated_data.get('organization', instance.organization)
        if not self._can_write_organization(self.request.user, next_organization.id):
            raise PermissionError('Not allowed for this organization.')
        before = self._snapshot_aggregate(instance)
        prior_status = instance.status
        prior_reviewer = instance.reviewed_by
        aggregate = serializer.save(
            status=Aggregate.STATUS_PENDING,
            reviewed_at=None,
            reviewed_by=None,
        )
        changes = self._build_change_set(before, self._snapshot_aggregate(aggregate))
        comment = 'Aggregate updated and resubmitted for coordinator review.'
        history_action = AggregateChangeLog.ACTION_CORRECTED if prior_status == Aggregate.STATUS_FLAGGED else AggregateChangeLog.ACTION_SUBMITTED
        self._record_history(
            aggregate,
            history_action,
            user=self.request.user,
            comment=comment,
            changes=changes,
        )
        if prior_status == Aggregate.STATUS_FLAGGED:
            active_flag = self._set_active_flag_status(
                aggregate,
                'in_progress',
                resolution_notes='Corrections submitted and awaiting coordinator review.',
            )
            coordinator = prior_reviewer or getattr(active_flag, 'created_by', None)
            if coordinator and coordinator != self.request.user:
                self._notify_user(
                    coordinator,
                    'Aggregate corrections submitted',
                    (
                        f"{aggregate.created_by.username if aggregate.created_by else 'A user'} "
                        f"updated {aggregate.indicator.code} for {aggregate.organization.name}. "
                        'Please review the corrections.'
                    ),
                    link=f"/aggregates?reviewAggregateId={aggregate.id}",
                )

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

    def partial_update(self, request, *args, **kwargs):
        try:
            return super().partial_update(request, *args, **kwargs)
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

    @action(detail=False, methods=['post'])
    def generate_from_interactions(self, request):
        """
        Derive an aggregate value from Interaction Responses and optionally save:
        - upsert DerivationRule (output_indicator -> source_indicator + condition)
        - upsert Aggregate (output_indicator + project + organization + period)
        """
        serializer = GenerateFromInteractionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        output_indicator_id = payload['output_indicator']
        source_indicator_id = payload['source_indicator']
        project_id = payload['project']
        organization_id = payload['organization']
        period_start = payload['period_start']
        period_end = payload['period_end']
        operator = payload.get('operator', 'equals')
        match_value = payload.get('match_value', None)
        count_distinct = payload.get('count_distinct', 'respondent')
        save_rule = payload.get('save_rule', True)
        save_aggregate = payload.get('save_aggregate', True)

        user = request.user
        if not self._can_write_organization(user, organization_id):
            return Response({'detail': 'Not allowed for this organization.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            output_indicator = Indicator.objects.get(id=output_indicator_id)
            source_indicator = Indicator.objects.get(id=source_indicator_id)
        except Indicator.DoesNotExist:
            return Response({'detail': 'Indicator not found.'}, status=status.HTTP_404_NOT_FOUND)

        rule = None
        if save_rule:
            rule, created = DerivationRule.objects.update_or_create(
                output_indicator=output_indicator,
                defaults={
                    'source_indicator': source_indicator,
                    'operator': operator,
                    'match_value': match_value,
                    'count_distinct': count_distinct,
                    'is_active': True,
                },
            )
            if created and user and user.is_authenticated:
                rule.created_by = user
                rule.save(update_fields=['created_by'])
        else:
            rule = DerivationRule(
                output_indicator=output_indicator,
                source_indicator=source_indicator,
                operator=operator,
                match_value=match_value,
                count_distinct=count_distinct,
                is_active=True,
            )

        response_qs = InteractionResponse.objects.filter(
            indicator_id=source_indicator.id,
            interaction__date__gte=period_start,
            interaction__date__lte=period_end,
            interaction__respondent__organization_id=organization_id,
        )
        if project_id:
            response_qs = response_qs.filter(interaction__project_id=project_id)

        if operator == 'equals':
            response_qs = response_qs.filter(value=match_value)
        elif operator == 'not_equals':
            response_qs = response_qs.exclude(value=match_value)
        elif operator == 'contains':
            response_qs = response_qs.filter(value__contains=match_value)

        if count_distinct == 'interaction':
            computed = response_qs.values('interaction_id').distinct().count()
        else:
            computed = response_qs.values('interaction__respondent_id').distinct().count()

        aggregate_data = None
        if save_aggregate:
            aggregate, created = Aggregate.objects.update_or_create(
                indicator_id=output_indicator.id,
                project_id=project_id,
                organization_id=organization_id,
                period_start=period_start,
                period_end=period_end,
                defaults={
                    'value': computed,
                    'notes': f"Auto-generated from interactions on {timezone.now().date().isoformat()}",
                    'status': Aggregate.STATUS_PENDING,
                    'reviewed_at': None,
                    'reviewed_by': None,
                },
            )
            if created and user and user.is_authenticated:
                aggregate.created_by = user
                aggregate.save(update_fields=['created_by'])
            self._record_history(
                aggregate,
                AggregateChangeLog.ACTION_SUBMITTED,
                user=user,
                comment='Aggregate generated from interactions and submitted for coordinator review.',
                changes=self._build_change_set({}, self._snapshot_aggregate(aggregate)) if created else {},
            )
            aggregate_data = AggregateListSerializer(aggregate).data

        return Response(
            {
                'computed': computed,
                'rule': DerivationRuleSerializer(rule).data if save_rule and rule else {
                    'output_indicator': output_indicator.id,
                    'source_indicator': source_indicator.id,
                    'operator': operator,
                    'match_value': match_value,
                    'count_distinct': count_distinct,
                },
                'aggregate': aggregate_data,
            }
        )

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
    
    @action(detail=False, methods=['get'])
    def by_indicator(self, request):
        """Get aggregates grouped by indicator."""
        indicator_id = request.query_params.get('indicator_id')
        if not indicator_id:
            return Response({'error': 'indicator_id required'}, status=400)
        
        aggregates = self.get_queryset().filter(indicator_id=indicator_id)
        return Response(AggregateListSerializer(aggregates, many=True).data)

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
        if not self._can_write_organization(request.user, organization_id):
            return Response({'detail': 'Not allowed for this organization.'}, status=status.HTTP_403_FORBIDDEN)

        created = []
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
                        'notes': item.get('notes') or '',
                    })
                    serializer.is_valid(raise_exception=True)
                    aggregate = serializer.save(
                        created_by=request.user,
                        status=Aggregate.STATUS_PENDING,
                        reviewed_at=None,
                        reviewed_by=None,
                    )
                    self._record_history(
                        aggregate,
                        AggregateChangeLog.ACTION_SUBMITTED,
                        user=request.user,
                        comment='Aggregate submitted for coordinator review.',
                        changes=self._build_change_set({}, self._snapshot_aggregate(aggregate)),
                    )
                    created.append(serializer.data)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'created': len(created), 'results': created}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        aggregate = self.get_object()
        if not self._can_review_aggregate(request.user, aggregate):
            return Response({'detail': 'You do not have permission to review this aggregate.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AggregateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get('notes', '').strip()

        if aggregate.status == Aggregate.STATUS_APPROVED:
            return Response({'detail': 'This aggregate has already been approved.'}, status=status.HTTP_400_BAD_REQUEST)

        previous_status = aggregate.status
        aggregate.status = Aggregate.STATUS_REVIEWED
        aggregate.reviewed_at = timezone.now()
        aggregate.reviewed_by = request.user
        self._append_audit_note(aggregate, 'Reviewed by coordinator', note)
        aggregate.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'notes', 'updated_at'])
        self._record_history(
            aggregate,
            AggregateChangeLog.ACTION_REVIEWED,
            user=request.user,
            comment=note or 'Aggregate reviewed by coordinator.',
            changes=self._build_change_set(
                {'status': previous_status},
                {'status': aggregate.status},
            ),
        )
        return Response(AggregateSerializer(aggregate).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        aggregate = self.get_object()
        if not self._can_review_aggregate(request.user, aggregate):
            return Response({'detail': 'You do not have permission to approve this aggregate.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AggregateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get('notes', '').strip()

        if aggregate.status != Aggregate.STATUS_REVIEWED:
            return Response(
                {'detail': 'This aggregate must be reviewed before it can be approved.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        aggregate.status = Aggregate.STATUS_APPROVED
        aggregate.reviewed_at = timezone.now()
        aggregate.reviewed_by = request.user
        self._append_audit_note(aggregate, 'Approved by coordinator', note)
        aggregate.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'notes', 'updated_at'])
        self._set_active_flag_status(
            aggregate,
            'resolved',
            resolution_notes='Aggregate approved after coordinator review.',
        )
        self._record_history(
            aggregate,
            AggregateChangeLog.ACTION_APPROVED,
            user=request.user,
            comment=note or 'Aggregate approved by coordinator.',
            changes=self._build_change_set(
                {'status': Aggregate.STATUS_REVIEWED},
                {'status': aggregate.status},
            ),
        )
        if aggregate.created_by and aggregate.created_by != request.user:
            self._notify_user(
                aggregate.created_by,
                'Aggregate approved',
                (
                    f"Your aggregate for {aggregate.indicator.code} "
                    f"({aggregate.period_start} to {aggregate.period_end}) was approved."
                ),
                link='/aggregates',
            )
        return Response(AggregateSerializer(aggregate).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def flag(self, request, pk=None):
        aggregate = self.get_object()
        if not self._can_review_aggregate(request.user, aggregate):
            return Response({'detail': 'You do not have permission to flag this aggregate.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AggregateFlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']
        description = serializer.validated_data.get('description', '').strip()
        severity = serializer.validated_data.get('severity', 'medium')

        reason_label = self.FLAG_REASON_LABELS.get(reason, 'Data quality issue')
        previous_status = aggregate.status
        created_flag = self._ensure_flag_for_correction(
            aggregate,
            request.user,
            reason_label,
            description,
            severity,
        )

        aggregate.status = Aggregate.STATUS_FLAGGED
        aggregate.reviewed_at = timezone.now()
        aggregate.reviewed_by = request.user
        flag_note = f"{reason_label} (Flag #{created_flag.id})"
        self._append_audit_note(aggregate, 'Flagged for correction', f"{flag_note}. {description}".strip('. '))
        aggregate.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'notes', 'updated_at'])
        self._record_history(
            aggregate,
            AggregateChangeLog.ACTION_FLAGGED,
            user=request.user,
            comment=f"{reason_label}. {description}".strip('. '),
            changes=self._build_change_set(
                {'status': previous_status},
                {'status': Aggregate.STATUS_FLAGGED},
            ),
        )
        if aggregate.created_by and aggregate.created_by != request.user:
            self._notify_user(
                aggregate.created_by,
                'Aggregate flagged for correction',
                (
                    f"Your aggregate for {aggregate.indicator.code} "
                    f"({aggregate.period_start} to {aggregate.period_end}) was flagged. "
                    f"{reason_label}{': ' + description if description else ''}"
                ),
                link=f"/aggregates?reviewAggregateId={aggregate.id}",
            )
        return Response(AggregateSerializer(aggregate).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self.flag(request, pk=pk)

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
        queryset = self.filter_queryset(self.get_queryset())
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
        fmt = request.query_params.get('format', 'csv')
        queryset = self.filter_queryset(self.get_queryset()).select_related('indicator', 'project', 'organization')
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
                'status': agg.status,
                'reviewed_at': agg.reviewed_at.isoformat() if agg.reviewed_at else '',
                'reviewed_by': agg.reviewed_by.username if agg.reviewed_by_id else '',
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


class DerivationRuleViewSet(viewsets.ModelViewSet):
    """CRUD for derivation rules (output indicator derived from interaction responses)."""

    queryset = DerivationRule.objects.all()
    serializer_class = DerivationRuleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['output_indicator', 'source_indicator', 'is_active']
    ordering_fields = ['updated_at', 'created_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        return DerivationRule.objects.all()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

