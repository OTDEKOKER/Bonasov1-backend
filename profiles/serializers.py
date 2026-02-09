from rest_framework import serializers
from .models import Profile, ProfileField


class ProfileSerializer(serializers.ModelSerializer):
    """Serializer for Profile model."""
    
    respondent_name = serializers.CharField(source='respondent.full_name', read_only=True)
    
    class Meta:
        model = Profile
        fields = [
            'id', 'respondent', 'respondent_name',
            'education_level', 'employment_status', 'income_level', 'household_size',
            'health_status', 'disabilities', 'custom_fields',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProfileFieldSerializer(serializers.ModelSerializer):
    """Serializer for ProfileField model."""
    
    class Meta:
        model = ProfileField
        fields = [
            'id', 'name', 'field_type', 'options', 'is_required',
            'order', 'organization', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
