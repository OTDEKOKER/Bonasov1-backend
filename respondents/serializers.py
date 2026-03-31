from rest_framework import serializers
from .models import Respondent, Interaction, Response


class ResponseSerializer(serializers.ModelSerializer):
    """Serializer for Response model."""
    
    indicator_name = serializers.CharField(source='indicator.name', read_only=True)
    indicator_code = serializers.CharField(source='indicator.code', read_only=True)
    indicator_type = serializers.CharField(source='indicator.type', read_only=True)
    
    class Meta:
        model = Response
        fields = [
            'id', 'interaction', 'indicator', 'indicator_name',
            'indicator_code', 'indicator_type', 'value', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ResponseCreateSerializer(serializers.ModelSerializer):
    """Minimal serializer for nested Response creation (InteractionCreateSerializer)."""

    class Meta:
        model = Response
        fields = ['indicator', 'value']


class InteractionSerializer(serializers.ModelSerializer):
    """Serializer for Interaction model."""
    
    respondent_name = serializers.CharField(source='respondent.full_name', read_only=True)
    assessment_name = serializers.CharField(source='assessment.name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    event_name = serializers.CharField(source='event.title', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    responses = ResponseSerializer(many=True, read_only=True)
    responses_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Interaction
        fields = [
            'id', 'respondent', 'respondent_name', 'assessment', 'assessment_name',
            'project', 'project_name', 'event', 'event_name', 'date', 'notes', 'responses', 'responses_count',
            'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_responses_count(self, obj):
        return obj.responses.count()


class InteractionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating interactions with responses."""
    
    responses = ResponseCreateSerializer(many=True, required=False)
    
    class Meta:
        model = Interaction
        fields = ['respondent', 'assessment', 'project', 'event', 'date', 'notes', 'responses']

    def validate(self, attrs):
        respondent = attrs.get('respondent') or getattr(self.instance, 'respondent', None)
        event = attrs.get('event') if 'event' in attrs else getattr(self.instance, 'event', None)
        if event and respondent:
            respondent_org_id = respondent.organization_id
            is_owner_org = event.organization_id == respondent_org_id
            is_participating_org = event.participating_organizations.filter(id=respondent_org_id).exists()
            if not (is_owner_org or is_participating_org):
                raise serializers.ValidationError({
                    'event': 'Selected event must belong to the respondent organization or include it as a participating organization.'
                })
        return attrs
    
    def create(self, validated_data):
        responses_data = validated_data.pop('responses', [])
        interaction = Interaction.objects.create(**validated_data)
        
        for response_data in responses_data:
            Response.objects.create(interaction=interaction, **response_data)
        
        return interaction


class RespondentSerializer(serializers.ModelSerializer):
    """Serializer for Respondent model."""
    
    full_name = serializers.CharField(read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    interactions_count = serializers.SerializerMethodField()
    last_interaction = serializers.SerializerMethodField()
    
    class Meta:
        model = Respondent
        fields = [
            'id', 'unique_id', 'first_name', 'last_name', 'full_name',
            'gender', 'date_of_birth', 'phone', 'email', 'address',
            'organization', 'organization_name', 'demographics', 'is_active',
            'interactions_count', 'last_interaction', 'created_at', 'updated_at',
            'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_interactions_count(self, obj):
        return obj.interactions.count()
    
    def get_last_interaction(self, obj):
        last = obj.interactions.first()
        return last.date.isoformat() if last else None


class RespondentProfileSerializer(RespondentSerializer):
    """Detailed serializer with interaction history."""
    
    interactions = InteractionSerializer(many=True, read_only=True)
    
    class Meta(RespondentSerializer.Meta):
        fields = RespondentSerializer.Meta.fields + ['interactions']
