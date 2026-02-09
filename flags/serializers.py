from rest_framework import serializers
from .models import Flag, FlagComment


class FlagCommentSerializer(serializers.ModelSerializer):
    """Serializer for FlagComment model."""
    
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = FlagComment
        fields = ['id', 'flag', 'content', 'created_at', 'created_by', 'created_by_name']
        read_only_fields = ['id', 'created_at', 'created_by']


class FlagSerializer(serializers.ModelSerializer):
    """Serializer for Flag model."""
    
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    resolved_by_name = serializers.CharField(source='resolved_by.username', read_only=True)
    comments = FlagCommentSerializer(many=True, read_only=True)
    comments_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Flag
        fields = [
            'id', 'flag_type', 'status', 'priority', 'title', 'description',
            'content_type', 'object_id', 'organization', 'organization_name',
            'assigned_to', 'assigned_to_name', 'resolution_notes',
            'resolved_at', 'resolved_by', 'resolved_by_name',
            'comments', 'comments_count',
            'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'resolved_at', 'resolved_by']
    
    def get_comments_count(self, obj):
        return obj.comments.count()
