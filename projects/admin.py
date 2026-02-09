from django.contrib import admin
from .models import Project, ProjectIndicator, Task, Deadline


class ProjectIndicatorInline(admin.TabularInline):
    model = ProjectIndicator
    extra = 1


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'status', 'start_date', 'end_date', 'created_at']
    list_filter = ['status', 'organizations']
    search_fields = ['name', 'code', 'description']
    inlines = [ProjectIndicatorInline]


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
