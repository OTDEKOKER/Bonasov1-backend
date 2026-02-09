from django.contrib import admin
from .models import SocialPost


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'indicator', 'organization', 'platform', 'views', 'likes', 'comments', 'shares', 'created_at']
    list_filter = ['platform', 'indicator', 'organization']
    search_fields = ['title', 'url']
