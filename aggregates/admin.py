from django.contrib import admin
from .models import Aggregate, DerivationRule


@admin.register(Aggregate)
class AggregateAdmin(admin.ModelAdmin):
    list_display = ['indicator', 'project', 'organization', 'status', 'reviewed_by', 'period_start', 'period_end']
    list_filter = ['status', 'project', 'organization', 'indicator', 'reviewed_by']
    ordering = ['-period_start']


@admin.register(DerivationRule)
class DerivationRuleAdmin(admin.ModelAdmin):
    list_display = ['output_indicator', 'source_indicator', 'operator', 'count_distinct', 'is_active', 'updated_at']
    list_filter = ['operator', 'count_distinct', 'is_active']
    search_fields = ['output_indicator__name', 'output_indicator__code', 'source_indicator__name', 'source_indicator__code']
    ordering = ['-updated_at']
