from django.contrib import admin
from .models import Report, SavedQuery, ScheduledReport, CoordinatorTarget

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'report_type', 'organization', 'is_public', 'last_generated']
    list_filter = ['report_type', 'is_public']
    search_fields = ['name', 'description']

@admin.register(SavedQuery)
class SavedQueryAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at']
    search_fields = ['name']


@admin.register(ScheduledReport)
class ScheduledReportAdmin(admin.ModelAdmin):
    list_display = ['report_name', 'frequency', 'is_active', 'next_run', 'last_run']
    list_filter = ['frequency', 'is_active']
    search_fields = ['report_name', 'report_type']


@admin.register(CoordinatorTarget)
class CoordinatorTargetAdmin(admin.ModelAdmin):
    list_display = [
        'project',
        'coordinator',
        'indicator',
        'year',
        'quarter',
        'target_value',
        'is_active',
        'updated_at',
    ]
    list_filter = ['year', 'quarter', 'is_active', 'project', 'coordinator']
    search_fields = ['project__name', 'coordinator__name', 'indicator__name', 'indicator__code', 'notes']
