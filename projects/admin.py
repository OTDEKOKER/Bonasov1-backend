from django.contrib import admin

from .models import Project, ProjectIndicator, ProjectIndicatorOrganizationTarget, Task, Deadline


class ProjectIndicatorInline(admin.TabularInline):
    model = ProjectIndicator
    extra = 0
    fields = ('indicator', 'q1_target', 'q2_target', 'q3_target', 'q4_target', 'target_value', 'baseline_value', 'current_value')
    readonly_fields = ('q1_target', 'q2_target', 'q3_target', 'q4_target', 'target_value', 'baseline_value', 'current_value')
    can_delete = False


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'status', 'start_date', 'end_date', 'created_at']
    list_filter = ['status', 'organizations']
    search_fields = ['name', 'code', 'description']
    inlines = [ProjectIndicatorInline]


@admin.register(ProjectIndicatorOrganizationTarget)
class ProjectIndicatorOrganizationTargetAdmin(admin.ModelAdmin):
    list_display = [
        'project_name', 'indicator_name', 'organization',
        'q1_target', 'q2_target', 'q3_target', 'q4_target', 'target_value'
    ]
    list_filter = ['organization', 'project_indicator__project']
    search_fields = ['project_indicator__project__name', 'project_indicator__indicator__name', 'organization__name']

    @staticmethod
    def project_name(obj):
        return obj.project_indicator.project.name

    @staticmethod
    def indicator_name(obj):
        return obj.project_indicator.indicator.name


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'status', 'priority', 'assigned_to', 'due_date']
    list_filter = ['status', 'priority', 'project']
    search_fields = ['name', 'description']


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'status', 'due_date']
    list_filter = ['status', 'project']
    search_fields = ['name', 'description']
