from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from django.db.models import Count, Sum

from .models import Event, Participant, EventPhase
from .serializers import (
    EventSerializer,
    EventDetailSerializer,
    ParticipantSerializer,
    EventPhaseSerializer,
)


class EventViewSet(viewsets.ModelViewSet):
    """ViewSet for managing events/activities."""
    
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'status', 'project', 'organization']
    search_fields = ['title', 'description', 'location']
    ordering_fields = ['start_date', 'created_at', 'title']
    ordering = ['-start_date']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return EventDetailSerializer
        return EventSerializer
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return Event.objects.all()
        elif user.organization:
            return Event.objects.filter(organization=user.organization)
        return Event.objects.none()
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['get'])
    def checkin(self, request, pk=None):
        """Return the check-in token and URL for this event."""
        event = self.get_object()
        return Response({
            'event_id': event.id,
            'title': event.title,
            'checkin_token': str(event.checkin_token),
        })
    
    @action(detail=True, methods=['post'])
    def add_participant(self, request, pk=None):
        """Add participant to event."""
        event = self.get_object()
        serializer = ParticipantSerializer(data={
            'event': event.id,
            **request.data
        })
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Update actual participants count
        event.actual_participants = event.participants.filter(attended=True).count()
        event.save()
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark event as completed."""
        event = self.get_object()
        event.status = 'completed'
        event.actual_participants = event.participants.filter(attended=True).count()
        event.save()
        return Response(EventSerializer(event).data)

    @action(detail=False, methods=['get'])
    def types(self, request):
        """Return available event types."""
        return Response([
            {'value': value, 'label': label}
            for value, label in Event.TYPE_CHOICES
        ])

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Return event statistics."""
        queryset = self.get_queryset()
        total = queryset.count()
        completed = queryset.filter(status='completed').count()
        total_participants = queryset.aggregate(total=Sum('actual_participants')).get('total') or 0
        by_type = {
            item['type']: item['count']
            for item in queryset.values('type').annotate(count=Count('id'))
        }
        return Response({
            'total': total,
            'completed': completed,
            'total_participants': total_participants,
            'by_type': by_type,
        })

    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Return upcoming events."""
        days = int(request.query_params.get('days', 30))
        start = timezone.now().date()
        end = start + timezone.timedelta(days=days)
        queryset = self.get_queryset().filter(start_date__gte=start, start_date__lte=end)
        serializer = EventSerializer(queryset, many=True)
        return Response(serializer.data)


class ParticipantViewSet(viewsets.ModelViewSet):
    """ViewSet for managing participants."""
    
    queryset = Participant.objects.all()
    serializer_class = ParticipantSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['event', 'attended']

    @action(detail=True, methods=['post'])
    def mark_attendance(self, request, pk=None):
        """Mark attendance for a participant."""
        participant = self.get_object()
        attended = request.data.get('attended', True)
        participant.attended = bool(attended)
        participant.save()
        event = participant.event
        event.actual_participants = event.participants.filter(attended=True).count()
        event.save()
        return Response(ParticipantSerializer(participant).data)


class EventPhaseViewSet(viewsets.ModelViewSet):
    """ViewSet for managing event preparation phases/activities."""

    queryset = EventPhase.objects.all()
    serializer_class = EventPhaseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['event', 'status']
    ordering_fields = ['due_date', 'created_at', 'title']
    ordering = ['-created_at']


class EventCheckinViewSet(viewsets.ViewSet):
    """Public check-in endpoint (token-based)."""

    permission_classes = [AllowAny]

    def retrieve(self, request, pk=None):
        event = Event.objects.filter(checkin_token=pk).first()
        if not event:
            return Response({'detail': 'Invalid check-in token.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'event_id': event.id,
            'title': event.title,
        })

    def create(self, request, pk=None):
        event = Event.objects.filter(checkin_token=pk).first()
        if not event:
            return Response({'detail': 'Invalid check-in token.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ParticipantSerializer(data={
            'event': event.id,
            'name': request.data.get('name', ''),
            'email': request.data.get('email', ''),
            'contact': request.data.get('contact', ''),
            'organization_name': request.data.get('organization_name', ''),
            'attended': True,
        })
        serializer.is_valid(raise_exception=True)
        serializer.save()
        event.actual_participants = event.participants.filter(attended=True).count()
        event.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
