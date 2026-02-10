# respondents/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response as DRFResponse
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Count
from django.http import HttpResponse
import csv

from .models import Respondent, Interaction, Response
from .serializers import (
    RespondentSerializer,
    RespondentProfileSerializer,
    InteractionSerializer,
    InteractionCreateSerializer,
    ResponseSerializer
)


class RespondentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing respondents."""
    
    queryset = Respondent.objects.all()
    serializer_class = RespondentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['organization', 'gender', 'is_active']
    search_fields = ['unique_id', 'first_name', 'last_name', 'phone', 'email']
    ordering_fields = ['last_name', 'first_name', 'created_at', 'unique_id']
    ordering = ['last_name', 'first_name']
    
    def get_queryset(self):
        """Filter queryset by user role and organization."""
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return Respondent.objects.all()
        elif user.organization:
            return Respondent.objects.filter(organization=user.organization)
        return Respondent.objects.none()
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['get'])
    def profile(self, request, pk=None):
        """Get respondent profile with all interactions."""
        respondent = self.get_object()
        serializer = RespondentProfileSerializer(respondent)
        return DRFResponse(serializer.data)
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search respondents by unique ID."""
        query = request.query_params.get('q', '')
        respondents = self.get_queryset().filter(unique_id__icontains=query)[:10]
        return DRFResponse(RespondentSerializer(respondents, many=True).data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get respondent statistics."""
        qs = self.get_queryset()
        return DRFResponse({
            'total': qs.count(),
            'active': qs.filter(is_active=True).count(),
            'by_gender': list(qs.values('gender').annotate(count=Count('id'))),
            'by_organization': list(qs.values('organization__name').annotate(count=Count('id'))),
        })
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export respondents to CSV."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="respondents.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['ID', 'Unique ID', 'First Name', 'Last Name', 'Gender', 'Organization'])
        
        for r in self.get_queryset():
            writer.writerow([
                r.id, r.unique_id, r.first_name, r.last_name,
                r.gender, r.organization.name if r.organization else ''
            ])
        
        return response


class InteractionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing interactions."""
    
    queryset = Interaction.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['respondent', 'assessment', 'project']
    search_fields = ['respondent__unique_id', 'notes']
    ordering_fields = ['date', 'created_at']
    ordering = ['-date', '-created_at']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return InteractionCreateSerializer
        return InteractionSerializer
    
    def get_queryset(self):
        """Filter interactions by user role and organization."""
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return Interaction.objects.all()
        elif user.organization:
            return Interaction.objects.filter(respondent__organization=user.organization)
        return Interaction.objects.filter(created_by=user)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def add_response(self, request, pk=None):
        """Add a response to an interaction."""
        interaction = self.get_object()
        serializer = ResponseSerializer(data={
            'interaction': interaction.id,
            **request.data
        })
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return DRFResponse(serializer.data, status=status.HTTP_201_CREATED)


class ResponseViewSet(viewsets.ModelViewSet):
    """ViewSet for managing responses."""
    
    queryset = Response.objects.all()
    serializer_class = ResponseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['interaction', 'indicator']

