from rest_framework import serializers
from .models import Project, ProjectIndicator, Task, Deadline


class ProjectIndicatorSerializer(serializers.ModelSerializer):
    """Serializer for ProjectIndicator through model."""
    
    indicator_name = serializers.CharField(source='indicator.name', read_only=True)
    indicator_code = serializers.CharField(source='indicator.code', read_only=True)
    progress = serializers.SerializerMethodField()
    
    class Meta:
        model = ProjectIndicator
        fields = [
            'id', 'project', 'indicator', 'indicator_name', 'indicator_code',
            'target_value', 'current_value', 'baseline_value', 'progress'
        ]
    
    def get_progress(self, obj):
        if obj.target_value == 0:
            return 0
        return min(int((obj.current_value / obj.target_value) * 100), 100)


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Project model."""
    
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    indicators_count = serializers.SerializerMethodField()
    tasks_count = serializers.SerializerMethodField()
    progress_percentage = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Project
        fields = [
            'id', 'name', 'code', 'description', 'funder', 'status',
            'start_date', 'end_date', 'organizations', 'indicators_count',
            'tasks_count', 'progress_percentage', 'created_at', 'updated_at',
            'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_indicators_count(self, obj):
        return obj.indicators.count()
    
    def get_tasks_count(self, obj):
        return obj.tasks.count()


class ProjectDetailSerializer(ProjectSerializer):
    """Detailed serializer including indicators."""
    
    project_indicators = serializers.SerializerMethodField()
    
    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + ['project_indicators']
    
    def get_project_indicators(self, obj):
        project_indicators = ProjectIndicator.objects.filter(project=obj)
        return ProjectIndicatorSerializer(project_indicators, many=True).data


class TaskSerializer(serializers.ModelSerializer):
    """Serializer for Task model."""
    
    project_name = serializers.CharField(source='project.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Task
        fields = [
            'id', 'project', 'project_name', 'name', 'description', 'status',
            'priority', 'assigned_to', 'assigned_to_name', 'due_date',
            'completed_at', 'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'completed_at']


class DeadlineSerializer(serializers.ModelSerializer):
    """Serializer for Deadline model."""
    
    project_name = serializers.CharField(source='project.name', read_only=True)
    submitted_by_name = serializers.CharField(source='submitted_by.username', read_only=True)
    days_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = Deadline
        fields = [
            'id', 'project', 'project_name', 'name', 'description', 'due_date',
            'status', 'indicators', 'submitted_at', 'submitted_by',
            'submitted_by_name', 'days_remaining', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'submitted_at', 'submitted_by']
    
    def get_days_remaining(self, obj):
        from django.utils import timezone
        if obj.status in ['submitted', 'approved']:
            return None
        delta = obj.due_date - timezone.now().date()
        return delta.days
