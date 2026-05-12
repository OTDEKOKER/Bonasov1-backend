from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from django.db import models, transaction
from django.db.models import Count, Sum, Avg
from django.utils.text import slugify
from datetime import date
from django.http import HttpResponse
import csv
import json
from io import BytesIO

from .models import Report, SavedQuery, ScheduledReport, CoordinatorTarget
from indicators.models import Indicator
from .serializers import ReportSerializer, SavedQuerySerializer, ScheduledReportSerializer, CoordinatorTargetSerializer
from aggregates.models import Aggregate
from organizations.access import get_user_organization_ids, is_organization_admin, filter_queryset_by_org_ids
from organizations.models import Organization


def _month_start(base: date, offset: int) -> date:
    year = base.year
    month = base.month - offset
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _month_range(start: date, end: date):
    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    months = []
    while current <= last:
        months.append(current)
        year = current.year + (current.month // 12)
        month = current.month % 12 + 1
        current = date(year, month, 1)
    return months


def _extract_total(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if value.get('total') is not None:
            return float(value.get('total') or 0)
        male = float(value.get('male') or 0)
        female = float(value.get('female') or 0)
        return male + female
    return 0.0


def _next_run_for_frequency(frequency: str):
    now = timezone.now()
    if frequency == 'daily':
        return now + timezone.timedelta(days=1)
    if frequency == 'weekly':
        return now + timezone.timedelta(days=7)
    if frequency == 'monthly':
        return now + timezone.timedelta(days=30)
    if frequency == 'quarterly':
        return now + timezone.timedelta(days=90)
    return now + timezone.timedelta(days=7)


def _safe_parse_date(value: str):
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def _safe_parse_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _organization_scope_with_descendants(org_id: int):
    organization = Organization.objects.filter(id=org_id).first()
    if not organization:
        return set()
    descendants = organization.get_descendants()
    return {organization.id, *[child.id for child in descendants]}


def _restrict_aggregates_to_user_scope(aggregates, user):
    if is_organization_admin(user):
        return aggregates
    org_ids = get_user_organization_ids(user)
    if org_ids:
        return filter_queryset_by_org_ids(aggregates, 'organization_id', org_ids)
    return Aggregate.objects.none()


def _approved_aggregates_only(aggregates, request):
    status_param = request.query_params.get('status')
    if status_param:
        statuses = [value.strip() for value in status_param.split(',') if value.strip()]
        if statuses:
            return aggregates.filter(status__in=statuses)
    return aggregates.filter(status='approved')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def indicator_trends(request, indicator_id: int):
    months = int(request.query_params.get('months', 12))
    months = max(1, min(months, 36))
    org_id = request.query_params.get('organization')
    coordinator_id = request.query_params.get('coordinator')
    project_id = request.query_params.get('project')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')

    user = request.user
    aggregates = Aggregate.objects.filter(indicator_id=indicator_id, status='approved')
    parsed_org_id = _safe_parse_int(org_id) if org_id not in (None, "") else None
    parsed_coordinator_id = _safe_parse_int(coordinator_id) if coordinator_id not in (None, "") else None
    if org_id not in (None, "") and parsed_org_id is None:
        return Response({'detail': 'organization must be a valid numeric id.'}, status=400)
    if coordinator_id not in (None, "") and parsed_coordinator_id is None:
        return Response({'detail': 'coordinator must be a valid numeric id.'}, status=400)

    requested_org_scope = None
    if parsed_coordinator_id is not None:
        requested_org_scope = _organization_scope_with_descendants(parsed_coordinator_id)
    if parsed_org_id is not None:
        organization_scope = _organization_scope_with_descendants(parsed_org_id)
        requested_org_scope = (
            organization_scope
            if requested_org_scope is None
            else requested_org_scope.intersection(organization_scope)
        )
    if requested_org_scope is not None:
        if len(requested_org_scope) == 0:
            return Response({
                'data': [],
                'trend': 'stable',
                'forecast': 0,
            })
        aggregates = aggregates.filter(organization_id__in=requested_org_scope)

    if project_id:
        aggregates = aggregates.filter(project_id=project_id)
    if date_from:
        aggregates = aggregates.filter(period_start__gte=date_from)
    if date_to:
        aggregates = aggregates.filter(period_end__lte=date_to)
    aggregates = _restrict_aggregates_to_user_scope(aggregates, user)

    if date_from and date_to:
        start = _safe_parse_date(date_from)
        end = _safe_parse_date(date_to)
        if not start or not end:
            return Response({'detail': 'Invalid date_from/date_to. Expected YYYY-MM-DD.'}, status=400)
        if start > end:
            return Response({'detail': 'date_from must be before date_to.'}, status=400)
        month_starts = _month_range(start, end)
    else:
        base = timezone.now().date().replace(day=1)
        month_starts = [_month_start(base, offset) for offset in reversed(range(months))]
    totals = {month_start: 0.0 for month_start in month_starts}
    earliest = month_starts[0]

    for agg in aggregates.filter(period_start__gte=earliest):
        month_start = agg.period_start.replace(day=1)
        if month_start in totals:
            totals[month_start] += _extract_total(agg.value)

    data = [
        {
            'month': month_start.strftime('%b %Y'),
            'value': totals[month_start],
            'target': 0,
        }
        for month_start in month_starts
    ]

    return Response({
        'data': data,
        'trend': 'stable',
        'forecast': data[-1]['value'] if data else 0,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def indicator_trends_bulk(request):
    ids_param = request.query_params.get('indicator_ids', '')
    indicator_ids = [int(value) for value in ids_param.split(',') if value.strip().isdigit()]
    if not indicator_ids:
        return Response({'series': []})

    months = int(request.query_params.get('months', 12))
    months = max(1, min(months, 36))
    org_id = request.query_params.get('organization')
    coordinator_id = request.query_params.get('coordinator')
    project_id = request.query_params.get('project')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')

    user = request.user
    aggregates = Aggregate.objects.filter(indicator_id__in=indicator_ids, status='approved')
    parsed_org_id = _safe_parse_int(org_id) if org_id not in (None, "") else None
    parsed_coordinator_id = _safe_parse_int(coordinator_id) if coordinator_id not in (None, "") else None
    if org_id not in (None, "") and parsed_org_id is None:
        return Response({'detail': 'organization must be a valid numeric id.'}, status=400)
    if coordinator_id not in (None, "") and parsed_coordinator_id is None:
        return Response({'detail': 'coordinator must be a valid numeric id.'}, status=400)

    requested_org_scope = None
    if parsed_coordinator_id is not None:
        requested_org_scope = _organization_scope_with_descendants(parsed_coordinator_id)
    if parsed_org_id is not None:
        organization_scope = _organization_scope_with_descendants(parsed_org_id)
        requested_org_scope = (
            organization_scope
            if requested_org_scope is None
            else requested_org_scope.intersection(organization_scope)
        )
    if requested_org_scope is not None:
        if len(requested_org_scope) == 0:
            return Response({'series': []})
        aggregates = aggregates.filter(organization_id__in=requested_org_scope)

    if project_id:
        aggregates = aggregates.filter(project_id=project_id)
    if date_from:
        aggregates = aggregates.filter(period_start__gte=date_from)
    if date_to:
        aggregates = aggregates.filter(period_end__lte=date_to)
    aggregates = _restrict_aggregates_to_user_scope(aggregates, user)

    if date_from and date_to:
        start = _safe_parse_date(date_from)
        end = _safe_parse_date(date_to)
        if not start or not end:
            return Response({'detail': 'Invalid date_from/date_to. Expected YYYY-MM-DD.'}, status=400)
        if start > end:
            return Response({'detail': 'date_from must be before date_to.'}, status=400)
        month_starts = _month_range(start, end)
    else:
        base = timezone.now().date().replace(day=1)
        month_starts = [_month_start(base, offset) for offset in reversed(range(months))]

    earliest = month_starts[0]
    totals_by_indicator = {
        indicator_id: {month_start: 0.0 for month_start in month_starts}
        for indicator_id in indicator_ids
    }

    for agg in aggregates.filter(period_start__gte=earliest):
        month_start = agg.period_start.replace(day=1)
        indicator_totals = totals_by_indicator.get(agg.indicator_id)
        if indicator_totals is not None and month_start in indicator_totals:
            indicator_totals[month_start] += _extract_total(agg.value)

    indicator_lookup = {
        indicator.id: indicator.name
        for indicator in Indicator.objects.filter(id__in=indicator_ids)
    }

    series = []
    for indicator_id in indicator_ids:
        totals = totals_by_indicator.get(indicator_id, {})
        data = [
            {
                'month': month_start.strftime('%b %Y'),
                'value': totals.get(month_start, 0.0),
                'target': 0,
            }
            for month_start in month_starts
        ]
        series.append({
            'indicator_id': indicator_id,
            'indicator_name': indicator_lookup.get(indicator_id, f'Indicator {indicator_id}'),
            'data': data,
        })

    return Response({
        'series': series,
    })




class CoordinatorTargetViewSet(viewsets.ModelViewSet):
    """Coordinator target CRUD API backed by the live coordinator target table."""

    queryset = CoordinatorTarget.objects.select_related('project', 'coordinator', 'indicator').all()
    serializer_class = CoordinatorTargetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['project__name', 'coordinator__name', 'indicator__name', 'notes']
    ordering_fields = ['year', 'quarter', 'target_value', 'updated_at', 'created_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        qs = self.queryset
        user = self.request.user
        if not (user.is_superuser or user.is_staff or getattr(user, 'role', None) == 'admin'):
            if getattr(user, 'organization', None):
                qs = qs.filter(
                    models.Q(coordinator=user.organization) |
                    models.Q(coordinator__parent=user.organization) |
                    models.Q(project__organizations=user.organization)
                ).distinct()
            else:
                return qs.none()

        params = self.request.query_params
        if params.get('project_id'):
            qs = qs.filter(project_id=params.get('project_id'))
        if params.get('coordinator_id'):
            qs = qs.filter(coordinator_id=params.get('coordinator_id'))
        if params.get('indicator_id'):
            qs = qs.filter(indicator_id=params.get('indicator_id'))
        if params.get('year'):
            qs = qs.filter(year=params.get('year'))
        if params.get('quarter'):
            qs = qs.filter(quarter=params.get('quarter'))
        if params.get('is_active') in {'true', 'false'}:
            qs = qs.filter(is_active=(params.get('is_active') == 'true'))
        return qs

    @action(detail=False, methods=['post'], url_path='bulk-assign')
    def bulk_assign(self, request):
        project_id = request.data.get('project_id')
        coordinator_ids = request.data.get('coordinator_ids') or []
        indicator_ids = request.data.get('indicator_ids') or []
        year = request.data.get('year')
        quarter = request.data.get('quarter')
        target_value = request.data.get('target_value', 0)
        notes = request.data.get('notes')
        is_active = request.data.get('is_active', True)

        if not project_id or not coordinator_ids or not indicator_ids or not year or not quarter:
            return Response({'detail': 'project_id, coordinator_ids, indicator_ids, year, and quarter are required.'}, status=400)
        if quarter not in {'Q1', 'Q2', 'Q3', 'Q4'}:
            return Response({'detail': 'quarter must be one of Q1, Q2, Q3, or Q4.'}, status=400)

        created = 0
        updated = 0
        skipped = 0
        with transaction.atomic():
            for coordinator_id in coordinator_ids:
                for indicator_id in indicator_ids:
                    target, target_created = CoordinatorTarget.objects.get_or_create(
                        project_id=project_id,
                        coordinator_id=coordinator_id,
                        indicator_id=indicator_id,
                        year=year,
                        quarter=quarter,
                        defaults={
                            'target_value': target_value,
                            'notes': notes,
                            'is_active': is_active,
                        },
                    )
                    if target_created:
                        created += 1
                        continue

                    dirty = []
                    if str(target.target_value) != str(target_value):
                        target.target_value = target_value
                        dirty.append('target_value')
                    next_notes = notes if notes not in ('', None) else None
                    if (target.notes if target.notes not in ('', None) else None) != next_notes:
                        target.notes = next_notes
                        dirty.append('notes')
                    if bool(target.is_active) != bool(is_active):
                        target.is_active = is_active
                        dirty.append('is_active')

                    if dirty:
                        target.save(update_fields=dirty + ['updated_at'])
                        updated += 1
                    else:
                        skipped += 1

        return Response({'created': created, 'updated': updated, 'skipped': skipped})

class ReportViewSet(viewsets.ModelViewSet):
    """ViewSet for managing reports."""
    
    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['report_type', 'organization', 'is_public']
    search_fields = ['name', 'description']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        if is_organization_admin(user):
            return Report.objects.all()
        org_ids = get_user_organization_ids(user)
        return Report.objects.filter(
            models.Q(organization_id__in=org_ids) |
            models.Q(is_public=True) |
            models.Q(created_by=user)
        )
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def generate(self, request, pk=None):
        """Generate/refresh report data."""
        report = self.get_object()

        params = report.parameters or {}
        project_id = params.get('project_id') or params.get('project')
        organization_id = params.get('organization_id') or params.get('organization')
        indicator_ids = params.get('indicator_ids') or params.get('indicators') or []
        date_from = params.get('date_from')
        date_to = params.get('date_to')

        aggregates = Aggregate.objects.all()
        if project_id:
            aggregates = aggregates.filter(project_id=project_id)
        if organization_id:
            aggregates = aggregates.filter(organization_id=organization_id)
        if indicator_ids:
            aggregates = aggregates.filter(indicator_id__in=indicator_ids)
        if date_from:
            aggregates = aggregates.filter(period_start__gte=date_from)
        if date_to:
            aggregates = aggregates.filter(period_end__lte=date_to)

        aggregates = _restrict_aggregates_to_user_scope(aggregates, request.user)
        aggregates = _approved_aggregates_only(aggregates, request)

        cached_rows = []
        if report.report_type == 'indicator':
            totals = {}
            for agg in aggregates.select_related('indicator'):
                row = totals.setdefault(
                    agg.indicator_id,
                    {
                        'indicator_id': agg.indicator_id,
                        'indicator_code': agg.indicator.code,
                        'indicator_name': agg.indicator.name,
                        'total_value': 0.0,
                        'entries': 0,
                    },
                )
                row['total_value'] += _extract_total(agg.value)
                row['entries'] += 1
            cached_rows = sorted(totals.values(), key=lambda item: item['total_value'], reverse=True)
        elif report.report_type == 'project':
            totals = {}
            for agg in aggregates.select_related('project'):
                row = totals.setdefault(
                    agg.project_id,
                    {
                        'project_id': agg.project_id,
                        'project_name': agg.project.name,
                        'total_value': 0.0,
                        'entries': 0,
                    },
                )
                row['total_value'] += _extract_total(agg.value)
                row['entries'] += 1
            cached_rows = sorted(totals.values(), key=lambda item: item['total_value'], reverse=True)
        else:
            # Default "custom" report is a raw aggregate export based on parameters.
            for agg in aggregates.select_related('indicator', 'project', 'organization'):
                cached_rows.append({
                    'indicator_id': agg.indicator_id,
                    'indicator_code': agg.indicator.code,
                    'indicator_name': agg.indicator.name,
                    'project_id': agg.project_id,
                    'project_name': agg.project.name,
                    'organization_id': agg.organization_id,
                    'organization_name': agg.organization.name,
                    'period_start': agg.period_start.isoformat(),
                    'period_end': agg.period_end.isoformat(),
                    'value': _extract_total(agg.value),
                })
            cached_rows = cached_rows

        report.cached_data = cached_rows
        report.last_generated = timezone.now()
        report.save(update_fields=['cached_data', 'last_generated', 'updated_at'])
        return Response(ReportSerializer(report).data)
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download report as CSV/XLSX."""
        report = self.get_object()

        export_format = (request.query_params.get('format') or (report.parameters or {}).get('format') or 'csv')
        export_format = str(export_format).lower()

        safe_name = slugify(report.name) or f'report-{report.id}'

        cached_data = report.cached_data if isinstance(report.cached_data, list) else []
        if not cached_data:
            cached_data = []

        if export_format in ('excel', 'xlsx'):
            try:
                from openpyxl import Workbook
            except ImportError:
                export_format = 'csv'
            else:
                workbook = Workbook()
                sheet = workbook.active
                sheet.title = 'Report'

                if cached_data:
                    headers = list(cached_data[0].keys())
                    sheet.append(headers)
                    for row in cached_data:
                        values = []
                        for key in headers:
                            value = row.get(key)
                            if isinstance(value, (dict, list)):
                                value = json.dumps(value)
                            values.append(value)
                        sheet.append(values)
                else:
                    sheet.append(['No data'])

                output = BytesIO()
                workbook.save(output)
                output.seek(0)
                response = HttpResponse(
                    output.getvalue(),
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )
                response['Content-Disposition'] = f'attachment; filename=\"{safe_name}.xlsx\"'
                return response

        # Default: CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename=\"{safe_name}.csv\"'

        writer = csv.writer(response)
        if cached_data:
            headers = list(cached_data[0].keys())
            writer.writerow(headers)
            for row in cached_data:
                writer.writerow([row.get(key) for key in headers])
        else:
            writer.writerow(['No data'])

        return response


class SavedQueryViewSet(viewsets.ModelViewSet):
    """ViewSet for saved queries."""
    
    queryset = SavedQuery.objects.all()
    serializer_class = SavedQuerySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return SavedQuery.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ScheduledReportViewSet(viewsets.ModelViewSet):
    """ViewSet for scheduled reports."""

    queryset = ScheduledReport.objects.all()
    serializer_class = ScheduledReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['frequency', 'is_active']
    search_fields = ['report_name', 'report_type']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if is_organization_admin(user):
            return ScheduledReport.objects.all()
        return ScheduledReport.objects.filter(created_by=user)

    def perform_create(self, serializer):
        data = serializer.validated_data
        next_run = data.get('next_run') or _next_run_for_frequency(data.get('frequency'))
        serializer.save(created_by=self.request.user, next_run=next_run)


class DashboardView(viewsets.ViewSet):
    """Dashboard analytics endpoints."""
    
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get dashboard overview stats."""
        from respondents.models import Respondent, Interaction
        from projects.models import Project

        user = request.user
        project_param = request.query_params.get('project')
        coordinator_param = request.query_params.get('coordinator')
        organization_param = request.query_params.get('organization')
        date_from_param = request.query_params.get('date_from')
        date_to_param = request.query_params.get('date_to')

        project_id = _safe_parse_int(project_param) if project_param not in (None, "") else None
        coordinator_id = _safe_parse_int(coordinator_param) if coordinator_param not in (None, "") else None
        organization_id = _safe_parse_int(organization_param) if organization_param not in (None, "") else None

        if project_param not in (None, "") and project_id is None:
            return Response(
                {'detail': 'project must be a valid numeric id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if coordinator_param not in (None, "") and coordinator_id is None:
            return Response(
                {'detail': 'coordinator must be a valid numeric id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if organization_param not in (None, "") and organization_id is None:
            return Response(
                {'detail': 'organization must be a valid numeric id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_from = _safe_parse_date(date_from_param) if date_from_param else None
        date_to = _safe_parse_date(date_to_param) if date_to_param else None
        if date_from_param and not date_from:
            return Response(
                {'detail': 'Invalid date_from. Expected YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if date_to_param and not date_to:
            return Response(
                {'detail': 'Invalid date_to. Expected YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if date_from and date_to and date_from > date_to:
            return Response(
                {'detail': 'date_from must be before date_to.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def _org_scope_with_descendants(org_id: int) -> set[int]:
            organization = Organization.objects.filter(id=org_id).first()
            if not organization:
                return set()
            descendants = organization.get_descendants()
            return {organization.id, *[child.id for child in descendants]}

        requested_org_ids = None
        if coordinator_id is not None:
            requested_org_ids = _org_scope_with_descendants(coordinator_id)
        if organization_id is not None:
            organization_scope = _org_scope_with_descendants(organization_id)
            requested_org_ids = (
                organization_scope
                if requested_org_ids is None
                else requested_org_ids.intersection(organization_scope)
            )

        if requested_org_ids is not None and len(requested_org_ids) == 0:
            return Response(
                {
                    'total_respondents': 0,
                    'total_assessments': 0,
                    'active_projects': 0,
                    'total_indicators': 0,
                    'indicators_behind': 0,
                    'recent_activity': [],
                }
            )

        user_scope_ids = None if is_organization_admin(user) else set(get_user_organization_ids(user) or [])
        effective_org_ids = requested_org_ids
        if user_scope_ids is not None:
            effective_org_ids = (
                user_scope_ids
                if effective_org_ids is None
                else effective_org_ids.intersection(user_scope_ids)
            )
            if len(effective_org_ids) == 0:
                return Response(
                    {
                        'total_respondents': 0,
                        'total_assessments': 0,
                        'active_projects': 0,
                        'total_indicators': 0,
                        'indicators_behind': 0,
                        'recent_activity': [],
                    }
                )

        # Build base querysets based on user role
        respondents = Respondent.objects.all()
        interactions = Interaction.objects.all()
        projects = Project.objects.all()

        if effective_org_ids is not None:
            respondents = respondents.filter(organization_id__in=effective_org_ids)
            interactions = interactions.filter(respondent__organization_id__in=effective_org_ids)
            projects = projects.filter(organizations__id__in=effective_org_ids).distinct()

        if project_id is not None:
            projects = projects.filter(id=project_id)
            interactions = interactions.filter(project_id=project_id)

        if date_from:
            interactions = interactions.filter(date__gte=date_from)
        if date_to:
            interactions = interactions.filter(date__lte=date_to)

        if project_id is not None or date_from or date_to:
            respondent_ids = interactions.values_list('respondent_id', flat=True).distinct()
            respondents = respondents.filter(id__in=respondent_ids)

        indicators = Indicator.objects.filter(is_active=True)
        if project_id is not None:
            indicators = indicators.filter(projects__id=project_id)
        if effective_org_ids is not None:
            indicators = indicators.filter(organizations__id__in=effective_org_ids)
        total_indicators = indicators.distinct().count()

        recent_activity = []
        for interaction in interactions.select_related('respondent').order_by('-date', '-created_at')[:10]:
            respondent_name = (
                interaction.respondent.full_name
                if getattr(interaction, 'respondent_id', None)
                else 'Respondent'
            )
            recent_activity.append({
                'type': 'interaction',
                'description': f'Interaction recorded for {respondent_name}',
                'timestamp': interaction.created_at.isoformat(),
            })
        
        return Response({
            'total_respondents': respondents.count(),
            'total_assessments': interactions.count(),
            'active_projects': projects.filter(status='active').count(),
            'total_indicators': total_indicators,
            'indicators_behind': 0,  # Calculate based on project targets
            'recent_activity': recent_activity,
        })

