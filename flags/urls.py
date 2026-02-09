from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FlagViewSet, FlagCommentViewSet

router = DefaultRouter()
router.register('comments', FlagCommentViewSet, basename='flag-comments')
router.register('', FlagViewSet, basename='flags')

urlpatterns = [
    path('', include(router.urls)),
]
