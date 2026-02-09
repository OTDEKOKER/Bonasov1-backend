from django.contrib import admin
from .models import Upload, ImportJob


@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    list_display = ['name', 'file_type', 'file_size', 'organization', 'created_at']
    list_filter = ['file_type', 'organization']
    search_fields = ['name', 'description']


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ['upload', 'status', 'total_rows', 'successful_rows', 'failed_rows', 'created_at']
    list_filter = ['status']
