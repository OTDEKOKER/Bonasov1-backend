from django.contrib import admin
from .models import Report, SavedQuery

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'report_type', 'organization', 'is_public', 'last_generated']
    list_filter = ['report_type', 'is_public']
    search_fields = ['name', 'description']

@admin.register(SavedQuery)
class SavedQueryAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at']
    search_fields = ['name']
