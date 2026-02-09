from django.contrib import admin
from .models import Event, Participant


class ParticipantInline(admin.TabularInline):
    model = Participant
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'type', 'status', 'organization', 'start_date', 'actual_participants']
    list_filter = ['type', 'status', 'organization']
    search_fields = ['title', 'description']
    inlines = [ParticipantInline]
