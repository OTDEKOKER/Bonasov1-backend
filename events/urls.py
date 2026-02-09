from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EventViewSet, ParticipantViewSet, EventPhaseViewSet, EventCheckinViewSet

router = DefaultRouter()
router.register('participants', ParticipantViewSet, basename='participants')
router.register('phases', EventPhaseViewSet, basename='phases')
router.register('', EventViewSet, basename='events')

urlpatterns = [
    path('checkin/<uuid:pk>/', EventCheckinViewSet.as_view({'get': 'retrieve', 'post': 'create'}), name='event-checkin'),
    path('', include(router.urls)),
]
