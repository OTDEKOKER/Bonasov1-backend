from django.contrib import admin
from .models import Aggregate


@admin.register(Aggregate)
class AggregateAdmin(admin.ModelAdmin):
    list_display = ['indicator', 'project', 'organization', 'status', 'period_start', 'period_end']
    list_filter = ['status', 'project', 'organization', 'indicator']
    ordering = ['-period_start']
