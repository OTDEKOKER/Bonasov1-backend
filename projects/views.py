from decimal import Decimal, InvalidOperation

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from django.db import models, connection
from django.db.models import Count, F, Q, Prefetch
from organizations.access import get_user_organization_ids, is_organization_admin, filter_queryset_by_org_ids
from organizations.models import Organization

from .models import Project, ProjectIndicator, Task, Deadline
from .project_indicator_links import ensure_project_indicator_link
from indicators.models import Indicator
from .serializers import (
    ProjectSerializer, ProjectDetailSerializer, ProjectIndicatorSerializer,
    TaskSerializer, DeadlineSerializer
)


class ProjectViewSet(viewsets.ModelViewSet):
    """ViewSet for managing projects."""
    
    queryset = Project.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'organizations']
    search_fields = ['name', 'code', 'description', 'funder']
    ordering_fields = ['name', 'start_date', 'end_date', 'created_at']
    ordering = ['-start_date']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProjectDetailSerializer
        return ProjectSerializer
    
    def get_queryset(self):
        queryset = Project.objects.select_related('created_by').prefetch_related(
            'organizations'
        ).annotate(
            indicators_count=Count('indicators', distinct=True),
            tasks_count=Count('tasks', distinct=True),
            completed_indicators_count=Count(
                'projectindicator',
                filter=Q(projectindicator__current_value__gte=F('projectindicator__target_value')),
                distinct=True,
            ),
            total_project_indicators=Count('projectindicator', distinct=True),
        )

        if self.action == 'retrieve':
            queryset = queryset.prefetch_related(
                Prefetch(
                    'projectindicator_set',
                    queryset=ProjectIndicator.objects.select_related('indicator'),
                )
            )

        user = self.request.user
        if is_organization_admin(user):
            return queryset
        org_ids = get_user_organization_ids(user)
        if org_ids:
            return queryset.filter(
                models.Q(organizations__id__in=org_ids) |
                models.Q(created_by=user)
            ).distinct()
        return queryset.filter(created_by=user)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get project statistics."""
        project = self.get_object()
        indicators = ProjectIndicator.objects.filter(project=project)
        
        return Response({
            'total_indicators': indicators.count(),
            'completed_targets': indicators.filter(current_value__gte=models.F('target_value')).count(),
            'pending_deadlines': project.deadlines.filter(status='pending').count(),
            'progress_percentage': project.progress_percentage,
        })
    
    @action(detail=True, methods=['post'])
    def assign_indicators(self, request, pk=None):
        """Assign indicators to project."""
        project = self.get_object()
        indicator_ids = request.data.get('indicator_ids', [])
        
        for ind_id in indicator_ids:
            ensure_project_indicator_link(project, ind_id)
            indicator = Indicator.objects.filter(id=ind_id).first()
            if indicator and not Task.objects.filter(
                project=project,
                name=indicator.name
            ).exists():
                Task.objects.create(
                    project=project,
                    name=indicator.name,
                    description=indicator.description,
                    status='pending',
                    priority='medium',
                    created_by=request.user,
                )
        return Response({'detail': 'Indicators assigned.'})
    
    @action(detail=True, methods=['post'])
    def set_target(self, request, pk=None):
        """Set target for indicator in project."""
        project = self.get_object()
        indicator_id = request.data.get('indicator_id')
        if not indicator_id:
            return Response({'detail': 'indicator_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        organization_id = request.data.get('organization_id')

        def to_decimal(value):
            if value in (None, ""):
                return Decimal("0")
            if isinstance(value, Decimal):
                return value
            try:
                return Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                return Decimal("0")

        q1_target = to_decimal(request.data.get('q1_target'))
        q2_target = to_decimal(request.data.get('q2_target'))
        q3_target = to_decimal(request.data.get('q3_target'))
        q4_target = to_decimal(request.data.get('q4_target'))
        baseline_value = to_decimal(request.data.get('baseline_value'))
        requested_target_value = request.data.get('target_value')
        target_value = (
            to_decimal(requested_target_value)
            if requested_target_value not in (None, "")
            else q1_target + q2_target + q3_target + q4_target
        )
        
        ensure_project_indicator_link(
            project,
            indicator_id,
            target_value=target_value,
            baseline_value=baseline_value,
            q1_target=q1_target,
            q2_target=q2_target,
            q3_target=q3_target,
            q4_target=q4_target,
        )
        pi = ProjectIndicator.objects.get(project=project, indicator_id=indicator_id)
        indicator = Indicator.objects.filter(id=indicator_id).first()
        if indicator and not Task.objects.filter(
            project=project,
            name=indicator.name
        ).exists():
            Task.objects.create(
                project=project,
                name=indicator.name,
                description=indicator.description,
                status='pending',
                priority='medium',
                    created_by=request.user,
                )

        # Modern payload path: save organization-scoped quarterly targets.
        if organization_id not in (None, ""):
            try:
                organization_id_value = int(organization_id)
            except (TypeError, ValueError):
                return Response({'detail': 'organization_id must be a valid integer.'}, status=status.HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO projects_projectindicatororganizationtarget (
                        q1_target,
                        q2_target,
                        q3_target,
                        q4_target,
                        target_value,
                        current_value,
                        baseline_value,
                        organization_id,
                        project_indicator_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (project_indicator_id, organization_id)
                    DO UPDATE SET
                        q1_target = EXCLUDED.q1_target,
                        q2_target = EXCLUDED.q2_target,
                        q3_target = EXCLUDED.q3_target,
                        q4_target = EXCLUDED.q4_target,
                        target_value = EXCLUDED.target_value,
                        baseline_value = EXCLUDED.baseline_value
                    """,
                    [
                        q1_target,
                        q2_target,
                        q3_target,
                        q4_target,
                        target_value,
                        Decimal("0"),
                        baseline_value,
                        organization_id_value,
                        pi.id,
                    ],
                )

                # Keep project-indicator rollup aligned with organization rows.
                cursor.execute(
                    """
                    SELECT
                        COALESCE(SUM(q1_target), 0),
                        COALESCE(SUM(q2_target), 0),
                        COALESCE(SUM(q3_target), 0),
                        COALESCE(SUM(q4_target), 0),
                        COALESCE(SUM(target_value), 0),
                        COALESCE(SUM(baseline_value), 0)
                    FROM projects_projectindicatororganizationtarget
                    WHERE project_indicator_id = %s
                    """,
                    [pi.id],
                )
                totals_row = cursor.fetchone() or (0, 0, 0, 0, 0, 0)
                cursor.execute(
                    """
                    UPDATE projects_projectindicator
                    SET
                        q1_target = %s,
                        q2_target = %s,
                        q3_target = %s,
                        q4_target = %s,
                        target_value = %s,
                        baseline_value = %s
                    WHERE id = %s
                    """,
                    [
                        totals_row[0],
                        totals_row[1],
                        totals_row[2],
                        totals_row[3],
                        totals_row[4],
                        totals_row[5],
                        pi.id,
                    ],
                )
        else:
            # Legacy payload path: save project-level aggregate target only.
            pi.target_value = target_value
            pi.baseline_value = baseline_value
            pi.save(update_fields=['target_value', 'baseline_value'])
        return Response({'detail': 'Target set.'})


class TaskViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tasks."""
    
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['project', 'status', 'priority', 'assigned_to']
    search_fields = ['name', 'description']
    ordering_fields = ['due_date', 'priority', 'created_at']
    ordering = ['due_date', '-priority']
    
    def get_queryset(self):
        queryset = Task.objects.select_related('project', 'assigned_to', 'created_by')
        user = self.request.user
        if is_organization_admin(user):
            return queryset
        org_ids = get_user_organization_ids(user)
        if org_ids:
            return filter_queryset_by_org_ids(queryset, 'project__organizations__id', org_ids).distinct()
        return queryset.filter(assigned_to=user)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark task as complete."""
        task = self.get_object()
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.save()
        return Response(TaskSerializer(task).data)


class DeadlineViewSet(viewsets.ModelViewSet):
    """ViewSet for managing deadlines."""
    
    queryset = Deadline.objects.all()
    serializer_class = DeadlineSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['project', 'status']
    search_fields = ['name', 'description']
    ordering_fields = ['due_date', 'created_at']
    ordering = ['due_date']
    
    def get_queryset(self):
        queryset = Deadline.objects.select_related(
            'project', 'submitted_by'
        ).prefetch_related('indicators')
        user = self.request.user
        if is_organization_admin(user):
            return queryset
        org_ids = get_user_organization_ids(user)
        if org_ids:
            queryset = filter_queryset_by_org_ids(queryset, 'project__organizations__id', org_ids).distinct()
        else:
            queryset = Deadline.objects.none()

        def _to_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def _org_scope_with_descendants(org_id: int) -> set[int]:
            organization = Organization.objects.filter(id=org_id).first()
            if not organization:
                return set()
            descendants = organization.get_descendants()
            return {organization.id, *[child.id for child in descendants]}

        coordinator_param = self.request.query_params.get('coordinator')
        organization_param = self.request.query_params.get('organization')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        coordinator_id = _to_int(coordinator_param) if coordinator_param not in (None, "") else None
        organization_id = _to_int(organization_param) if organization_param not in (None, "") else None

        scoped_org_ids = None
        if coordinator_id is not None:
            scoped_org_ids = _org_scope_with_descendants(coordinator_id)
        if organization_id is not None:
            organization_scope = _org_scope_with_descendants(organization_id)
            scoped_org_ids = (
                organization_scope
                if scoped_org_ids is None
                else scoped_org_ids.intersection(organization_scope)
            )
        if scoped_org_ids is not None:
            if len(scoped_org_ids) == 0:
                return queryset.none()
            queryset = queryset.filter(project__organizations__id__in=scoped_org_ids).distinct()

        if date_from:
            queryset = queryset.filter(due_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(due_date__lte=date_to)

        upcoming = str(self.request.query_params.get('upcoming', '')).lower()
        if upcoming in {'1', 'true', 'yes'}:
            try:
                days = int(self.request.query_params.get('days', 7))
            except (TypeError, ValueError):
                days = 7
            if days < 0:
                days = 7
            today = timezone.now().date()
            cutoff = today + timezone.timedelta(days=days)
            queryset = queryset.filter(
                status='pending',
                due_date__gte=today,
                due_date__lte=cutoff,
            )
        return queryset
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming deadlines."""
        try:
            days = int(request.query_params.get('days', 7))
        except (TypeError, ValueError):
            days = 7
        if days < 0:
            days = 7
        today = timezone.now().date()
        cutoff = timezone.now().date() + timezone.timedelta(days=days)
        deadlines = self.get_queryset().filter(
            status='pending',
            due_date__gte=today,
            due_date__lte=cutoff
        )
        return Response(DeadlineSerializer(deadlines, many=True).data)
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit deadline."""
        deadline = self.get_object()
        deadline.status = 'submitted'
        deadline.submitted_at = timezone.now()
        deadline.submitted_by = request.user
        deadline.save()
        return Response(DeadlineSerializer(deadline).data)

