from rest_framework import serializers
from .models import Upload, ImportJob


class UploadSerializer(serializers.ModelSerializer):
    """Serializer for Upload model."""
    
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Upload
        fields = [
            'id', 'name', 'file', 'file_url', 'file_type', 'file_size', 'mime_type',
            'description', 'organization', 'organization_name',
            'content_type', 'object_id',
            'created_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'file_size', 'file_type', 'created_at', 'created_by']
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None


class ImportJobSerializer(serializers.ModelSerializer):
    """Serializer for ImportJob model."""
    
    upload_name = serializers.CharField(source='upload.name', read_only=True)
    progress = serializers.SerializerMethodField()
    
    class Meta:
        model = ImportJob
        fields = [
            'id', 'upload', 'upload_name', 'status',
            'total_rows', 'processed_rows', 'successful_rows', 'failed_rows',
            'progress', 'errors', 'started_at', 'completed_at',
            'created_at', 'created_by'
        ]
        read_only_fields = ['id', 'created_at', 'created_by']
    
    def get_progress(self, obj):
        if obj.total_rows == 0:
            return 0
        return int((obj.processed_rows / obj.total_rows) * 100)


class MissingIndicatorAssignmentSerializer(serializers.Serializer):
    organization_id = serializers.IntegerField(required=False, allow_null=True)
    organization_name = serializers.CharField(required=False, allow_blank=True)
    q1_target = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)
    q2_target = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)
    q3_target = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)
    q4_target = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)


class MissingIndicatorCreateItemSerializer(serializers.Serializer):
    temp_key = serializers.CharField()
    name = serializers.CharField(max_length=255)
    code = serializers.CharField(max_length=50)
    type = serializers.CharField(max_length=20, default='number')
    category = serializers.CharField(max_length=30, required=False, allow_blank=True)
    unit = serializers.CharField(max_length=50, required=False, allow_blank=True)
    sub_labels = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    aggregate_disaggregation_config = serializers.JSONField(required=False)
    organizations = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )
    assignments = MissingIndicatorAssignmentSerializer(many=True, required=False)


class CreateMissingIndicatorsSerializer(serializers.Serializer):
    project_id = serializers.IntegerField(required=False)
    assign_to_project = serializers.BooleanField(required=False, default=True)
    create_targets = serializers.BooleanField(required=False, default=True)
    indicators = MissingIndicatorCreateItemSerializer(many=True)
