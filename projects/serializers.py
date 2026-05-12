from django.db import DatabaseError, connection
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
        annotated_count = getattr(obj, 'indicators_count', None)
        if annotated_count is not None:
            return annotated_count
        return obj.indicators.count()
    
    def get_tasks_count(self, obj):
        annotated_count = getattr(obj, 'tasks_count', None)
        if annotated_count is not None:
            return annotated_count
        return obj.tasks.count()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        completed = getattr(instance, 'completed_indicators_count', None)
        total = getattr(instance, 'total_project_indicators', None)
        if completed is not None and total is not None:
            data['progress_percentage'] = int((completed / total) * 100) if total else 0
        return data


class ProjectDetailSerializer(ProjectSerializer):
    """Detailed serializer including indicators."""
    
    project_indicators = serializers.SerializerMethodField()
    organization_targets = serializers.SerializerMethodField()
    
    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + ['project_indicators', 'organization_targets']
    
    def get_project_indicators(self, obj):
        project_indicators = getattr(obj, 'projectindicator_set', None)
        if project_indicators is None:
            project_indicators = ProjectIndicator.objects.filter(project=obj).select_related('indicator')
        return ProjectIndicatorSerializer(project_indicators, many=True).data

    def get_organization_targets(self, obj):
        query = """
            SELECT
                piot.id,
                pi.project_id,
                pi.indicator_id,
                COALESCE(ind.name, ''),
                COALESCE(ind.code, ''),
                piot.organization_id,
                COALESCE(org.name, ''),
                COALESCE(org.code, ''),
                piot.q1_target,
                piot.q2_target,
                piot.q3_target,
                piot.q4_target,
                piot.target_value,
                piot.current_value,
                piot.baseline_value
            FROM projects_projectindicatororganizationtarget piot
            INNER JOIN projects_projectindicator pi
                ON pi.id = piot.project_indicator_id
            LEFT JOIN indicators_indicator ind
                ON ind.id = pi.indicator_id
            LEFT JOIN organizations_organization org
                ON org.id = piot.organization_id
            WHERE pi.project_id = %s
            ORDER BY ind.name ASC, org.name ASC, piot.id ASC
        """

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, [obj.id])
                rows = cursor.fetchall()
        except DatabaseError:
            return []

        results = []
        for row in rows:
            (
                target_id,
                project_id,
                indicator_id,
                indicator_name,
                indicator_code,
                organization_id,
                organization_name,
                organization_code,
                q1_target,
                q2_target,
                q3_target,
                q4_target,
                target_value,
                current_value,
                baseline_value,
            ) = row

            progress = 0
            if target_value and float(target_value) > 0:
                progress = min(int((float(current_value or 0) / float(target_value)) * 100), 100)

            results.append(
                {
                    'id': str(target_id),
                    'project': str(project_id),
                    'project_name': obj.name,
                    'project_code': obj.code,
                    'indicator': str(indicator_id),
                    'indicator_name': indicator_name,
                    'indicator_code': indicator_code,
                    'organization': str(organization_id),
                    'organization_name': organization_name,
                    'organization_code': organization_code,
                    'q1_target': q1_target,
                    'q2_target': q2_target,
                    'q3_target': q3_target,
                    'q4_target': q4_target,
                    'target_value': target_value,
                    'current_value': current_value,
                    'baseline_value': baseline_value,
                    'progress': progress,
                }
            )

        return results


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
