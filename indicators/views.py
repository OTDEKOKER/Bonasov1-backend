from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Indicator, Assessment, AssessmentIndicator
from .serializers import (
    IndicatorSerializer, IndicatorSimpleSerializer,
    AssessmentSerializer, AssessmentSimpleSerializer, AssessmentIndicatorSerializer
)


class IndicatorViewSet(viewsets.ModelViewSet):
    """ViewSet for managing indicators."""
    
    queryset = Indicator.objects.all()
    serializer_class = IndicatorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'category', 'is_active', 'organizations']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'code', 'category', 'created_at']
    ordering = ['category', 'name']
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return Indicator.objects.all()
        elif user.organization:
            return Indicator.objects.filter(
                models.Q(organizations=user.organization) | models.Q(organizations__isnull=True)
            ).distinct()
        return Indicator.objects.filter(organizations__isnull=True)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def simple(self, request):
        """Get simple list for dropdowns."""
        indicators = self.get_queryset().filter(is_active=True)
        serializer = IndicatorSimpleSerializer(indicators, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def types(self, request):
        """Get available indicator types."""
        return Response([
            {'value': choice[0], 'label': choice[1]}
            for choice in Indicator.TYPE_CHOICES
        ])
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Get available indicator categories."""
        return Response([
            {'value': choice[0], 'label': choice[1]}
            for choice in Indicator.CATEGORY_CHOICES
        ])


class AssessmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing assessments."""
    
    queryset = Assessment.objects.all()
    serializer_class = AssessmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'organizations']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return Assessment.objects.all()
        elif user.organization:
            return Assessment.objects.filter(
                models.Q(organizations=user.organization) | models.Q(organizations__isnull=True)
            ).distinct()
        return Assessment.objects.filter(organizations__isnull=True)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def simple(self, request):
        """Get simple list for dropdowns."""
        assessments = self.get_queryset().filter(is_active=True)
        serializer = AssessmentSimpleSerializer(assessments, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def add_indicator(self, request, pk=None):
        """Add indicator to assessment."""
        assessment = self.get_object()
        indicator_id = request.data.get('indicator_id')
        order = request.data.get('order', 0)
        is_required = request.data.get('is_required', True)
        
        try:
            indicator = Indicator.objects.get(id=indicator_id)
            ai, created = AssessmentIndicator.objects.get_or_create(
                assessment=assessment,
                indicator=indicator,
                defaults={'order': order, 'is_required': is_required}
            )
            if not created:
                ai.order = order
                ai.is_required = is_required
                ai.save()
            return Response({'detail': 'Indicator added to assessment.'})
        except Indicator.DoesNotExist:
            return Response({'detail': 'Indicator not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'])
    def remove_indicator(self, request, pk=None):
        """Remove indicator from assessment."""
        assessment = self.get_object()
        indicator_id = request.data.get('indicator_id')
        
        AssessmentIndicator.objects.filter(
            assessment=assessment,
            indicator_id=indicator_id
        ).delete()
        return Response({'detail': 'Indicator removed from assessment.'})

