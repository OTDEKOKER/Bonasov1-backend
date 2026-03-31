from django.db import models
from rest_framework import serializers
from organizations.models import Organization
from indicators.models import Indicator
from projects.models import Project

from .models import Report, SavedQuery, ScheduledReport, CoordinatorTarget


class ReportSerializer(serializers.ModelSerializer):
    """Serializer for Report model."""
    
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Report
        fields = [
            'id', 'name', 'description', 'report_type', 'parameters',
            'cached_data', 'last_generated', 'organization', 'organization_name',
            'is_public', 'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'last_generated']


class SavedQuerySerializer(serializers.ModelSerializer):
    """Serializer for SavedQuery model."""
    
    class Meta:
        model = SavedQuery
        fields = ['id', 'name', 'description', 'query_params', 'user', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class ScheduledReportSerializer(serializers.ModelSerializer):
    """Serializer for ScheduledReport model."""

    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    next_run = serializers.DateTimeField(required=False)
    last_run = serializers.DateTimeField(required=False, allow_null=True)

    class Meta:
        model = ScheduledReport
        fields = [
            'id', 'report_name', 'report_type', 'parameters',
            'frequency', 'recipients', 'is_active', 'next_run', 'last_run',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class CoordinatorTargetSerializer(serializers.ModelSerializer):
    """Serializer for coordinator portfolio quarterly targets."""

    project_id = serializers.PrimaryKeyRelatedField(source='project', queryset=Project.objects.all())
    coordinator_id = serializers.PrimaryKeyRelatedField(source='coordinator', queryset=Organization.objects.all())
    indicator_id = serializers.PrimaryKeyRelatedField(source='indicator', queryset=Indicator.objects.all())

    project_name = serializers.CharField(source='project.name', read_only=True)
    coordinator_name = serializers.CharField(source='coordinator.name', read_only=True)
    indicator_name = serializers.CharField(source='indicator.name', read_only=True)

    target_value = serializers.DecimalField(max_digits=15, decimal_places=2, coerce_to_string=False)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = CoordinatorTarget
        fields = [
            'id',
            'project_id',
            'coordinator_id',
            'indicator_id',
            'year',
            'quarter',
            'target_value',
            'notes',
            'is_active',
            'created_at',
            'updated_at',
            'project_name',
            'coordinator_name',
            'indicator_name',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'project_name', 'coordinator_name', 'indicator_name']

    def validate_year(self, value):
        if value < 2000 or value > 2200:
            raise serializers.ValidationError('year must be between 2000 and 2200.')
        return value

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        project = attrs.get('project', getattr(instance, 'project', None))
        coordinator = attrs.get('coordinator', getattr(instance, 'coordinator', None))
        indicator = attrs.get('indicator', getattr(instance, 'indicator', None))
        year = attrs.get('year', getattr(instance, 'year', None))
        quarter = attrs.get('quarter', getattr(instance, 'quarter', None))

        if not all([project, coordinator, indicator, year, quarter]):
            return attrs

        duplicate_qs = CoordinatorTarget.objects.filter(
            project=project,
            coordinator=coordinator,
            indicator=indicator,
            year=year,
            quarter=quarter,
        )
        if instance is not None:
            duplicate_qs = duplicate_qs.exclude(pk=instance.pk)

        if duplicate_qs.exists():
            raise serializers.ValidationError(
                'A coordinator target already exists for this project, coordinator, indicator, year, and quarter.'
            )
        return attrs


class CoordinatorTargetBulkAssignSerializer(serializers.Serializer):
    """Serializer for bulk assignment requests."""

    project_id = serializers.PrimaryKeyRelatedField(source='project', queryset=Project.objects.all())
    coordinator_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all()),
        allow_empty=False,
    )
    indicator_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all()),
        allow_empty=False,
    )
    year = serializers.IntegerField(min_value=2000, max_value=2200)
    quarter = serializers.ChoiceField(choices=CoordinatorTarget.QUARTER_CHOICES)
    target_value = serializers.DecimalField(max_digits=15, decimal_places=2, coerce_to_string=False)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)


class DashboardPreferencesSerializer(serializers.Serializer):
    """Serializer for per-user dashboard card preferences."""

    selected_indicator_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )
    card_order = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
    )
    hidden_sections = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
    )
    layout = serializers.JSONField(required=False, default=dict)

    def _available_indicator_queryset(self):
        request = self.context.get('request')
        queryset = Indicator.objects.filter(is_active=True)

        user = getattr(request, 'user', None)
        if user and not (user.is_superuser or user.is_staff or user.role == 'admin'):
            if user.organization_id:
                queryset = queryset.filter(
                    models.Q(organizations__isnull=True) | models.Q(organizations=user.organization)
                ).distinct()
            else:
                queryset = Indicator.objects.filter(is_active=True, organizations__isnull=True).distinct()
        return queryset

    def validate_selected_indicator_ids(self, value):
        indicator_ids = list(dict.fromkeys(value))
        existing_ids = set(self._available_indicator_queryset().filter(id__in=indicator_ids).values_list('id', flat=True))
        missing_ids = [indicator_id for indicator_id in indicator_ids if indicator_id not in existing_ids]
        if missing_ids:
            raise serializers.ValidationError(
                f"Unknown, inactive, or inaccessible indicator ids: {', '.join(str(indicator_id) for indicator_id in missing_ids)}."
            )
        return indicator_ids

    def get_available_indicators(self):
        queryset = self._available_indicator_queryset()
        return [
            {
                'id': indicator.id,
                'code': indicator.code,
                'name': indicator.name,
                'category': indicator.category,
                'unit': indicator.unit,
            }
            for indicator in queryset.order_by('category', 'name')
        ]
