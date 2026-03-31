from rest_framework import serializers
from .models import Aggregate, AggregateChangeLog, DerivationRule


class AggregateChangeLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    def get_changed_by_name(self, obj):
        return getattr(obj.changed_by, 'username', None)

    class Meta:
        model = AggregateChangeLog
        fields = ['id', 'action', 'comment', 'changes', 'created_at', 'changed_by', 'changed_by_name']
        read_only_fields = fields


class AggregateListSerializer(serializers.ModelSerializer):
    """Serializer for aggregate list responses."""

    indicator_name = serializers.SerializerMethodField()
    indicator_code = serializers.SerializerMethodField()
    project_name = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    def get_indicator_name(self, obj):
        return getattr(obj.indicator, 'name', None)

    def get_indicator_code(self, obj):
        return getattr(obj.indicator, 'code', None)

    def get_project_name(self, obj):
        return getattr(obj.project, 'name', None)

    def get_organization_name(self, obj):
        return getattr(obj.organization, 'name', None)

    def get_created_by_name(self, obj):
        return getattr(obj.created_by, 'username', None)

    def get_reviewed_by_name(self, obj):
        return getattr(obj.reviewed_by, 'username', None)

    class Meta:
        model = Aggregate
        fields = [
            'id', 'indicator', 'indicator_name', 'indicator_code',
            'project', 'project_name', 'organization', 'organization_name',
            'period_start', 'period_end', 'value', 'notes',
            'status', 'reviewed_at', 'reviewed_by', 'reviewed_by_name',
            'created_at', 'updated_at', 'created_by', 'created_by_name',
        ]
        read_only_fields = [
            'id', 'status', 'reviewed_at', 'reviewed_by',
            'created_at', 'updated_at', 'created_by'
        ]


class AggregateSerializer(AggregateListSerializer):
    """Detailed serializer for single aggregate responses."""

    history_entries = AggregateChangeLogSerializer(many=True, read_only=True)

    class Meta(AggregateListSerializer.Meta):
        fields = AggregateListSerializer.Meta.fields + ['history_entries']


class AggregateReviewSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)


class AggregateFlagSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(
        choices=[
            'duplicate',
            'incorrect_data',
            'suspicious',
            'incomplete',
            'other',
        ]
    )
    description = serializers.CharField(required=False, allow_blank=True)
    severity = serializers.ChoiceField(
        choices=['low', 'medium', 'high'],
        default='medium',
        required=False,
    )


class DerivationRuleSerializer(serializers.ModelSerializer):
    output_indicator_code = serializers.CharField(source='output_indicator.code', read_only=True)
    output_indicator_name = serializers.CharField(source='output_indicator.name', read_only=True)
    source_indicator_code = serializers.CharField(source='source_indicator.code', read_only=True)
    source_indicator_name = serializers.CharField(source='source_indicator.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = DerivationRule
        fields = [
            'id',
            'output_indicator',
            'output_indicator_code',
            'output_indicator_name',
            'source_indicator',
            'source_indicator_code',
            'source_indicator_name',
            'operator',
            'match_value',
            'count_distinct',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']


class GenerateFromInteractionsSerializer(serializers.Serializer):
    output_indicator = serializers.IntegerField()
    source_indicator = serializers.IntegerField()
    operator = serializers.ChoiceField(choices=['equals', 'not_equals', 'contains'], default='equals', required=False)
    match_value = serializers.JSONField(required=False, allow_null=True)
    count_distinct = serializers.ChoiceField(choices=['respondent', 'interaction'], default='respondent', required=False)

    project = serializers.IntegerField()
    organization = serializers.IntegerField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()

    save_rule = serializers.BooleanField(default=True, required=False)
    save_aggregate = serializers.BooleanField(default=True, required=False)
