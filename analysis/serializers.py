from projects.models import Project
from organizations.models import Organization
from indicators.models import Indicator
from rest_framework import serializers
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
    project_id = serializers.PrimaryKeyRelatedField(source='project', queryset=Project.objects.all())
    coordinator_id = serializers.PrimaryKeyRelatedField(source='coordinator', queryset=Organization.objects.all())
    indicator_id = serializers.PrimaryKeyRelatedField(source='indicator', queryset=Indicator.objects.all())
    project_name = serializers.CharField(source='project.name', read_only=True)
    coordinator_name = serializers.CharField(source='coordinator.name', read_only=True)
    indicator_name = serializers.CharField(source='indicator.name', read_only=True)

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

    def validate(self, attrs):
        project = attrs.get('project', getattr(self.instance, 'project', None))
        coordinator = attrs.get('coordinator', getattr(self.instance, 'coordinator', None))
        indicator = attrs.get('indicator', getattr(self.instance, 'indicator', None))
        year = attrs.get('year', getattr(self.instance, 'year', None))
        quarter = attrs.get('quarter', getattr(self.instance, 'quarter', None))
        if project and coordinator and indicator and year and quarter:
            qs = CoordinatorTarget.objects.filter(
                project=project,
                coordinator=coordinator,
                indicator=indicator,
                year=year,
                quarter=quarter,
            )
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    'A coordinator target already exists for this project, coordinator, indicator, year, and quarter.'
                )
        return attrs

