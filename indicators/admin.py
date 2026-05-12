from django.contrib import admin
from .models import Indicator, IndicatorAlias, Assessment, AssessmentIndicator


class AssessmentIndicatorInline(admin.TabularInline):
    model = AssessmentIndicator
    extra = 1
    fields = [
        'indicator', 'question_text', 'response_type', 'aggregate_mode',
        'order', 'is_required', 'depends_on', 'condition_value',
    ]


class IndicatorAliasInline(admin.TabularInline):
    model = IndicatorAlias
    extra = 1
    fields = ['name', 'is_active', 'notes']


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'type', 'category', 'is_active', 'created_at']
    list_filter = ['type', 'category', 'is_active']
    search_fields = ['name', 'code', 'description']
    ordering = ['category', 'name']
    inlines = [IndicatorAliasInline]


@admin.register(IndicatorAlias)
class IndicatorAliasAdmin(admin.ModelAdmin):
    list_display = ['name', 'indicator', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'normalized_name', 'indicator__name', 'indicator__code']
    autocomplete_fields = ['indicator', 'created_by']


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    inlines = [AssessmentIndicatorInline]
