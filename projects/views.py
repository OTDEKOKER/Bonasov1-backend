from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from django.db import models

from .models import Project, ProjectIndicator, Task, Deadline
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
        user = self.request.user
        if user.role == 'admin':
            return Project.objects.all()
        elif user.organization:
            return Project.objects.filter(
                models.Q(organizations=user.organization) |
                models.Q(created_by=user)
            ).distinct()
        return Project.objects.filter(created_by=user)
    
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
            ProjectIndicator.objects.get_or_create(
                project=project,
                indicator_id=ind_id
            )
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
        target_value = request.data.get('target_value', 0)
        baseline_value = request.data.get('baseline_value', 0)
        
        pi, _ = ProjectIndicator.objects.get_or_create(
            project=project,
            indicator_id=indicator_id
        )
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
        pi.target_value = target_value
        pi.baseline_value = baseline_value
        pi.save()
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
        user = self.request.user
        if user.role == 'admin':
            return Task.objects.all()
        elif user.organization:
            return Task.objects.filter(project__organizations=user.organization)
        return Task.objects.filter(assigned_to=user)
    
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
        user = self.request.user
        if user.role == 'admin':
            return Deadline.objects.all()
        elif user.organization:
            return Deadline.objects.filter(project__organizations=user.organization)
        return Deadline.objects.none()
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming deadlines."""
        days = int(request.query_params.get('days', 7))
        cutoff = timezone.now().date() + timezone.timedelta(days=days)
        deadlines = self.get_queryset().filter(
            status='pending',
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
