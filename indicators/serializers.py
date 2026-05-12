from rest_framework import serializers
from .models import Indicator, IndicatorAlias, Assessment, AssessmentIndicator


class IndicatorAliasSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    indicator_name = serializers.CharField(source='indicator.name', read_only=True)
    indicator_code = serializers.CharField(source='indicator.code', read_only=True)

    class Meta:
        model = IndicatorAlias
        fields = [
            'id', 'indicator', 'indicator_name', 'indicator_code', 'name',
            'normalized_name', 'is_active', 'notes', 'created_at', 'updated_at',
            'created_by', 'created_by_name',
        ]
        read_only_fields = [
            'id', 'normalized_name', 'created_at', 'updated_at',
            'created_by', 'created_by_name', 'indicator_name', 'indicator_code',
        ]


class IndicatorSerializer(serializers.ModelSerializer):
    """Serializer for Indicator model."""
    
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    organizations_count = serializers.SerializerMethodField()
    aliases = IndicatorAliasSerializer(many=True, read_only=True)
    
    class Meta:
        model = Indicator
        fields = [
            'id', 'name', 'code', 'description', 'type', 'category', 'unit',
            'options', 'sub_labels', 'aggregation_method', 'is_active',
            'organizations', 'organizations_count', 'aliases',
            'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_organizations_count(self, obj):
        annotated_count = getattr(obj, 'organizations_count', None)
        if annotated_count is not None:
            return annotated_count
        return obj.organizations.count()


class IndicatorListSerializer(serializers.ModelSerializer):
    """Slim serializer for indicator list endpoints."""

    class Meta:
        model = Indicator
        fields = [
            'id', 'name', 'code', 'description', 'type', 'category', 'unit',
            'options', 'sub_labels', 'aggregation_method', 'is_active',
            'organizations', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class IndicatorSimpleSerializer(serializers.ModelSerializer):
    """Simple serializer for dropdowns."""
    
    class Meta:
        model = Indicator
        fields = ['id', 'name', 'code', 'type', 'category']


class AssessmentIndicatorSerializer(serializers.ModelSerializer):
    """Serializer for AssessmentIndicator through model."""
    
    indicator_detail = IndicatorSimpleSerializer(source='indicator', read_only=True)
    question_text_display = serializers.SerializerMethodField()
    response_type_display = serializers.SerializerMethodField()
    response_options_display = serializers.SerializerMethodField()
    response_sub_labels_display = serializers.SerializerMethodField()
    
    class Meta:
        model = AssessmentIndicator
        fields = [
            'id', 'assessment', 'indicator', 'indicator_detail',
            'question_text', 'question_text_display', 'help_text',
            'response_type', 'response_type_display',
            'response_options', 'response_options_display',
            'response_sub_labels', 'response_sub_labels_display',
            'aggregate_mode', 'aggregate_match_values',
            'order', 'is_required', 'depends_on', 'condition_value'
        ]

    def get_question_text_display(self, obj):
        return obj.question_text or obj.indicator.name

    def get_response_type_display(self, obj):
        return obj.response_type or obj.indicator.type

    def get_response_options_display(self, obj):
        return obj.response_options or obj.indicator.options

    def get_response_sub_labels_display(self, obj):
        return obj.response_sub_labels or obj.indicator.sub_labels


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
        assessment_indicators = getattr(obj, 'assessmentindicator_set', None)
        if assessment_indicators is None:
            assessment_indicators = AssessmentIndicator.objects.filter(
                assessment=obj
            ).select_related('indicator', 'depends_on').order_by('order')
        return AssessmentIndicatorSerializer(assessment_indicators, many=True).data
    
    def get_indicators_count(self, obj):
        annotated_count = getattr(obj, 'indicators_count', None)
        if annotated_count is not None:
            return annotated_count
        return obj.indicators.count()


class AssessmentListSerializer(serializers.ModelSerializer):
    """Slim serializer for assessment list endpoints."""

    indicators_count = serializers.SerializerMethodField()

    class Meta:
        model = Assessment
        fields = [
            'id', 'name', 'description', 'indicators',
            'indicators_count', 'logic_rules', 'is_active', 'organizations',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_indicators_count(self, obj):
        annotated_count = getattr(obj, 'indicators_count', None)
        if annotated_count is not None:
            return annotated_count
        return obj.indicators.count()


class AssessmentSimpleSerializer(serializers.ModelSerializer):
    """Simple serializer for dropdowns."""
    
    class Meta:
        model = Assessment
        fields = ['id', 'name', 'description']
