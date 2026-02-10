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
from io import BytesIO

from .models import Aggregate
from .serializers import AggregateSerializer
from indicators.models import Indicator
from projects.models import Project


class AggregateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing aggregate data."""
    
    queryset = Aggregate.objects.all()
    serializer_class = AggregateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['indicator', 'project', 'organization', 'period_start', 'period_end']
    ordering_fields = ['period_start', 'period_end', 'created_at']
    ordering = ['-period_start']
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return Aggregate.objects.all()
        elif user.organization:
            return Aggregate.objects.filter(organization=user.organization)
        return Aggregate.objects.none()
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

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
                        'notes': item.get('notes'),
                    })
                    serializer.is_valid(raise_exception=True)
                    serializer.save(created_by=request.user)
                    created.append(serializer.data)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'created': len(created), 'results': created}, status=status.HTTP_201_CREATED)

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
            rows.append({
                'indicator': agg.indicator.name if agg.indicator_id else '',
                'indicator_code': agg.indicator.code if agg.indicator_id else '',
                'project': agg.project.name if agg.project_id else '',
                'organization': agg.organization.name if agg.organization_id else '',
                'period_start': agg.period_start.isoformat(),
                'period_end': agg.period_end.isoformat(),
                'value': agg.value,
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

