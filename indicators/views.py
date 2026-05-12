from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models
from django.db.models import Count, Prefetch

from .models import Indicator, IndicatorAlias, Assessment, AssessmentIndicator
from .serializers import (
    IndicatorSerializer, IndicatorListSerializer, IndicatorSimpleSerializer, IndicatorAliasSerializer,
    AssessmentSerializer, AssessmentListSerializer, AssessmentSimpleSerializer, AssessmentIndicatorSerializer
)


class IndicatorPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


class AssessmentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class IndicatorViewSet(viewsets.ModelViewSet):
    """ViewSet for managing indicators."""
    
    queryset = Indicator.objects.all()
    serializer_class = IndicatorSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = IndicatorPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'category', 'is_active', 'organizations']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'code', 'category', 'created_at']
    ordering = ['category', 'name']

    def get_serializer_class(self):
        if self.action == 'list':
            return IndicatorListSerializer
        if self.action == 'simple':
            return IndicatorSimpleSerializer
        return IndicatorSerializer
    
    def get_queryset(self):
        queryset = Indicator.objects.prefetch_related('organizations')
        if self.action != 'list':
            queryset = queryset.select_related('created_by').prefetch_related(
                Prefetch(
                    'aliases',
                    queryset=IndicatorAlias.objects.select_related('indicator', 'created_by'),
                ),
            ).annotate(
                organizations_count=Count('organizations', distinct=True)
            )
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return queryset
        elif user.organization:
            return queryset.filter(
                models.Q(organizations=user.organization) | models.Q(organizations__isnull=True)
            ).distinct()
        return queryset.filter(organizations__isnull=True)
    
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


class IndicatorAliasViewSet(viewsets.ModelViewSet):
    """ViewSet for managing indicator aliases."""

    queryset = IndicatorAlias.objects.all()
    serializer_class = IndicatorAliasSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['indicator', 'is_active']
    search_fields = ['name', 'normalized_name', 'indicator__name', 'indicator__code']
    ordering_fields = ['name', 'created_at', 'updated_at']
    ordering = ['name']

    def get_queryset(self):
        queryset = IndicatorAlias.objects.select_related(
            'indicator', 'created_by'
        )
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return queryset
        elif user.organization:
            return queryset.filter(
                models.Q(indicator__organizations=user.organization)
                | models.Q(indicator__organizations__isnull=True)
            ).distinct()
        return queryset.filter(indicator__organizations__isnull=True)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AssessmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing assessments."""
    
    queryset = Assessment.objects.all()
    serializer_class = AssessmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AssessmentPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'organizations']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'list':
            return AssessmentListSerializer
        if self.action == 'simple':
            return AssessmentSimpleSerializer
        return AssessmentSerializer
    
    def get_queryset(self):
        queryset = Assessment.objects.annotate(
            indicators_count=Count('indicators', distinct=True)
        )
        if self.action == 'list':
            queryset = queryset.prefetch_related('organizations', 'indicators')
        else:
            queryset = queryset.select_related('created_by').prefetch_related(
                'organizations',
                Prefetch(
                    'assessmentindicator_set',
                    queryset=AssessmentIndicator.objects.select_related(
                        'indicator', 'depends_on'
                    ).order_by('order'),
                ),
            )
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return queryset
        elif user.organization:
            return queryset.filter(
                models.Q(organizations=user.organization) | models.Q(organizations__isnull=True)
            ).distinct()
        return queryset.filter(organizations__isnull=True)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _coerce_bool(self, value, default=True):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {'false', '0', 'no', 'off', ''}
        return bool(value)

    def _coerce_int(self, value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _validate_question_payload(self, payload):
        response_type = payload.get('response_type')
        if response_type in (None, ''):
            response_type = ''
        elif response_type not in {choice[0] for choice in Indicator.TYPE_CHOICES}:
            return Response(
                {'detail': 'Invalid response_type supplied.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_options = payload.get('response_options')
        if response_options is not None and not isinstance(response_options, list):
            return Response(
                {'detail': 'response_options must be a list.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_sub_labels = payload.get('response_sub_labels')
        if response_sub_labels is not None and not isinstance(response_sub_labels, list):
            return Response(
                {'detail': 'response_sub_labels must be a list.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        aggregate_mode = payload.get('aggregate_mode')
        if aggregate_mode not in (None, '') and aggregate_mode not in {
            choice[0] for choice in AssessmentIndicator.AGGREGATE_MODE_CHOICES
        }:
            return Response(
                {'detail': 'Invalid aggregate_mode supplied.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        aggregate_match_values = payload.get('aggregate_match_values')
        if aggregate_match_values is not None and not isinstance(aggregate_match_values, list):
            return Response(
                {'detail': 'aggregate_match_values must be a list.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return None
    
    @action(detail=False, methods=['get'])
    def simple(self, request):
        """Get simple list for dropdowns."""
        assessments = self.get_queryset().filter(is_active=True)
        serializer = AssessmentSimpleSerializer(assessments, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def add_indicator(self, request, pk=None):
        """Create or update an assessment question linked to an indicator."""
        assessment = self.get_object()
        from respondents.rollups import sync_assessment_question_rollups

        question_id = request.data.get('question_id')
        indicator_id = request.data.get('indicator_id')
        order = self._coerce_int(request.data.get('order'), 0)
        is_required = self._coerce_bool(request.data.get('is_required'), True)

        validation_error = self._validate_question_payload(request.data)
        if validation_error is not None:
            return validation_error
        
        try:
            indicator = Indicator.objects.get(id=indicator_id)
            if question_id:
                ai = AssessmentIndicator.objects.filter(
                    assessment=assessment,
                    id=question_id,
                ).first()
                if ai is None:
                    return Response(
                        {'detail': 'Assessment question not found.'},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                duplicate = AssessmentIndicator.objects.filter(
                    assessment=assessment,
                    indicator=indicator,
                ).exclude(id=ai.id)
                if duplicate.exists():
                    return Response(
                        {'detail': 'That indicator is already linked to this assessment.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                ai.indicator = indicator
            else:
                ai, _ = AssessmentIndicator.objects.get_or_create(
                    assessment=assessment,
                    indicator=indicator,
                )

            ai.order = order
            ai.is_required = is_required

            if 'question_text' in request.data:
                ai.question_text = (request.data.get('question_text') or '').strip()
            if 'help_text' in request.data:
                ai.help_text = request.data.get('help_text') or ''
            if 'response_type' in request.data:
                ai.response_type = request.data.get('response_type') or ''
            if 'response_options' in request.data:
                ai.response_options = request.data.get('response_options') or []
            if 'response_sub_labels' in request.data:
                ai.response_sub_labels = request.data.get('response_sub_labels') or []
            if 'aggregate_mode' in request.data:
                ai.aggregate_mode = request.data.get('aggregate_mode') or 'none'
            if 'aggregate_match_values' in request.data:
                ai.aggregate_match_values = request.data.get('aggregate_match_values') or []

            ai.save()
            sync_assessment_question_rollups(ai.assessment_id, ai.indicator_id)
            return Response(AssessmentIndicatorSerializer(ai).data)
        except Indicator.DoesNotExist:
            return Response({'detail': 'Indicator not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'])
    def remove_indicator(self, request, pk=None):
        """Remove a question from an assessment."""
        assessment = self.get_object()
        from respondents.rollups import sync_assessment_question_rollups

        question_id = request.data.get('question_id')
        indicator_id = request.data.get('indicator_id')

        queryset = AssessmentIndicator.objects.filter(assessment=assessment)
        if question_id:
            queryset = queryset.filter(id=question_id)
        elif indicator_id:
            queryset = queryset.filter(indicator_id=indicator_id)
        else:
            return Response(
                {'detail': 'question_id or indicator_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        affected_pairs = list(queryset.values_list('assessment_id', 'indicator_id').distinct())
        queryset.delete()
        for affected_assessment_id, affected_indicator_id in affected_pairs:
            sync_assessment_question_rollups(affected_assessment_id, affected_indicator_id)

        return Response({'detail': 'Question removed from assessment.'})

