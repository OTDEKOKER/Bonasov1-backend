from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProfileViewSet, ProfileFieldViewSet

router = DefaultRouter()
router.register('fields', ProfileFieldViewSet, basename='profile-fields')
router.register('', ProfileViewSet, basename='profiles')

urlpatterns = [
    path('', include(router.urls)),
]
