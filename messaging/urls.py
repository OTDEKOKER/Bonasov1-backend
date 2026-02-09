from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MessageViewSet, NotificationViewSet

router = DefaultRouter()
router.register('notifications', NotificationViewSet, basename='notifications')
router.register('', MessageViewSet, basename='messages')

urlpatterns = [
    path('', include(router.urls)),
]
