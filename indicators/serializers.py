from rest_framework import serializers
from .models import Indicator, Assessment, AssessmentIndicator


class IndicatorSerializer(serializers.ModelSerializer):
    """Serializer for Indicator model."""
    
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    organizations_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Indicator
        fields = [
            'id', 'name', 'code', 'description', 'type', 'category', 'unit',
            'options', 'sub_labels', 'aggregation_method', 'is_active',
            'organizations', 'organizations_count', 'created_at', 'updated_at',
            'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_organizations_count(self, obj):
        return obj.organizations.count()


class IndicatorSimpleSerializer(serializers.ModelSerializer):
    """Simple serializer for dropdowns."""
    
    class Meta:
        model = Indicator
        fields = ['id', 'name', 'code', 'type', 'category']


class AssessmentIndicatorSerializer(serializers.ModelSerializer):
    """Serializer for AssessmentIndicator through model."""
    
    indicator_detail = IndicatorSimpleSerializer(source='indicator', read_only=True)
    
    class Meta:
        model = AssessmentIndicator
        fields = [
            'id', 'assessment', 'indicator', 'indicator_detail', 'order',
            'is_required', 'depends_on', 'condition_value'
        ]


class AssessmentSerializer(serializers.ModelSerializer):
    """Serializer for Assessment model."""
    
    indicators_detail = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    indicators_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Assessment
        fields = [
            'id', 'name', 'description', 'indicators', 'indicators_detail',
            'indicators_count', 'logic_rules', 'is_active', 'organizations',
            'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_indicators_detail(self, obj):
        assessment_indicators = AssessmentIndicator.objects.filter(assessment=obj).order_by('order')
        return AssessmentIndicatorSerializer(assessment_indicators, many=True).data
    
    def get_indicators_count(self, obj):
        return obj.indicators.count()


class AssessmentSimpleSerializer(serializers.ModelSerializer):
    """Simple serializer for dropdowns."""
    
    class Meta:
        model = Assessment
        fields = ['id', 'name', 'description']
