from django.contrib import admin
from .models import Respondent, Interaction, Response


class ResponseInline(admin.TabularInline):
    model = Response
    extra = 0


@admin.register(Respondent)
class RespondentAdmin(admin.ModelAdmin):
    list_display = ['unique_id', 'first_name', 'last_name', 'gender', 'organization', 'is_active']
    list_filter = ['gender', 'organization', 'is_active']
    search_fields = ['unique_id', 'first_name', 'last_name']


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ['respondent', 'assessment', 'date', 'created_by']
    list_filter = ['assessment', 'project']
    search_fields = ['respondent__unique_id']
    inlines = [ResponseInline]
