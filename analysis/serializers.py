from rest_framework import serializers
from .models import Report, SavedQuery, ScheduledReport


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
