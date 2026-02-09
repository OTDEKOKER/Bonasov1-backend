from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, UserActivityViewSet

router = DefaultRouter()
router.register('', UserViewSet, basename='users')
router.register('activities', UserActivityViewSet, basename='user-activities')

urlpatterns = [
    path('', include(router.urls)),
]
