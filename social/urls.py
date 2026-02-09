from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SocialPostViewSet

router = DefaultRouter()
router.register('posts', SocialPostViewSet, basename='social-posts')

urlpatterns = [
    path('', include(router.urls)),
]
