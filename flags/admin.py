from django.contrib import admin
from .models import Flag, FlagComment


class FlagCommentInline(admin.TabularInline):
    model = FlagComment
    extra = 0


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = ['title', 'flag_type', 'status', 'priority', 'organization', 'created_at']
    list_filter = ['flag_type', 'status', 'priority', 'organization']
    search_fields = ['title', 'description']
    inlines = [FlagCommentInline]
