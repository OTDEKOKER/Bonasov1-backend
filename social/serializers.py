from rest_framework import serializers
from .models import SocialPost


class SocialPostSerializer(serializers.ModelSerializer):
    """Serializer for SocialPost model."""

    indicator_name = serializers.CharField(source='indicator.name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = SocialPost
        fields = [
            'id', 'title', 'description', 'post_date',
            'indicator', 'indicator_name',
            'organization', 'organization_name',
            'platform', 'url',
            'views', 'likes', 'comments', 'shares', 'interactions',
            'last_synced', 'created_at', 'updated_at',
            'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'interactions', 'created_at', 'updated_at', 'created_by']
