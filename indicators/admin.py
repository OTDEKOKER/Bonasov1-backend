from django.contrib import admin
from .models import Indicator, Assessment, AssessmentIndicator


class AssessmentIndicatorInline(admin.TabularInline):
    model = AssessmentIndicator
    extra = 1


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'type', 'category', 'is_active', 'created_at']
    list_filter = ['type', 'category', 'is_active']
    search_fields = ['name', 'code', 'description']
    ordering = ['category', 'name']


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    inlines = [AssessmentIndicatorInline]
