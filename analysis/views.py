from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from django.db import models
from django.db.models import Count, Sum, Avg
from django.utils.text import slugify
from datetime import date
from django.http import HttpResponse
import csv
import json
from io import BytesIO

from .models import Report, SavedQuery, ScheduledReport
from indicators.models import Indicator
from .serializers import ReportSerializer, SavedQuerySerializer, ScheduledReportSerializer
from aggregates.models import Aggregate


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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def indicator_trends(request, indicator_id: int):
    months = int(request.query_params.get('months', 12))
    months = max(1, min(months, 36))
    org_id = request.query_params.get('organization')
    project_id = request.query_params.get('project')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')

    user = request.user
    aggregates = Aggregate.objects.filter(indicator_id=indicator_id)
    if org_id:
        aggregates = aggregates.filter(organization_id=org_id)
    if project_id:
        aggregates = aggregates.filter(project_id=project_id)
    if date_from:
        aggregates = aggregates.filter(period_start__gte=date_from)
    if date_to:
        aggregates = aggregates.filter(period_end__lte=date_to)
    if user.role != 'admin':
        if user.organization:
            aggregates = aggregates.filter(organization=user.organization)
        else:
            aggregates = Aggregate.objects.none()

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
    project_id = request.query_params.get('project')
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')

    user = request.user
    aggregates = Aggregate.objects.filter(indicator_id__in=indicator_ids)
    if org_id:
        aggregates = aggregates.filter(organization_id=org_id)
    if project_id:
        aggregates = aggregates.filter(project_id=project_id)
    if date_from:
        aggregates = aggregates.filter(period_start__gte=date_from)
    if date_to:
        aggregates = aggregates.filter(period_end__lte=date_to)
    if user.role != 'admin':
        if user.organization:
            aggregates = aggregates.filter(organization=user.organization)
        else:
            aggregates = Aggregate.objects.none()

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
        if user.role == 'admin':
            return Report.objects.all()
        return Report.objects.filter(
            models.Q(organization=user.organization) |
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

        user = request.user
        if user.role != 'admin':
            if user.organization_id:
                aggregates = aggregates.filter(organization_id=user.organization_id)
            else:
                aggregates = Aggregate.objects.none()

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
        if user.role == 'admin':
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
        from indicators.models import Indicator
        
        user = request.user
        
        # Build base querysets based on user role
        if user.role == 'admin':
            respondents = Respondent.objects.all()
            interactions = Interaction.objects.all()
            projects = Project.objects.all()
        elif user.organization:
            respondents = Respondent.objects.filter(organization=user.organization)
            interactions = Interaction.objects.filter(respondent__organization=user.organization)
            projects = Project.objects.filter(organizations=user.organization)
        else:
            respondents = Respondent.objects.none()
            interactions = Interaction.objects.none()
            projects = Project.objects.none()
        
        return Response({
            'total_respondents': respondents.count(),
            'total_assessments': interactions.count(),
            'active_projects': projects.filter(status='active').count(),
            'total_indicators': Indicator.objects.filter(is_active=True).count(),
            'indicators_behind': 0,  # Calculate based on project targets
            'recent_activity': [],
        })
