from django.contrib import admin
from .models import Profile, ProfileField


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['respondent', 'education_level', 'employment_status', 'created_at']
    search_fields = ['respondent__unique_id', 'respondent__first_name']


@admin.register(ProfileField)
class ProfileFieldAdmin(admin.ModelAdmin):
    list_display = ['name', 'field_type', 'is_required', 'order', 'organization']
    list_filter = ['field_type', 'is_required']
