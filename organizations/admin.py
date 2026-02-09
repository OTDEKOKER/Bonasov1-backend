from django.contrib import admin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'type', 'parent', 'is_active', 'created_at']
    list_filter = ['type', 'is_active']
    search_fields = ['name', 'code']
    ordering = ['name']
