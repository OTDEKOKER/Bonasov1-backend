from rest_framework import serializers
from .models import Aggregate


class AggregateSerializer(serializers.ModelSerializer):
    """Serializer for Aggregate model."""
    
    indicator_name = serializers.CharField(source='indicator.name', read_only=True)
    indicator_code = serializers.CharField(source='indicator.code', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Aggregate
        fields = [
            'id', 'indicator', 'indicator_name', 'indicator_code',
            'project', 'project_name', 'organization', 'organization_name',
            'period_start', 'period_end', 'value', 'notes',
            'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
