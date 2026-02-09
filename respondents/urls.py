# respondents/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RespondentViewSet, InteractionViewSet, ResponseViewSet

# Create a DRF router
router = DefaultRouter()
router.register(r'respondents', RespondentViewSet, basename='respondent')
router.register(r'interactions', InteractionViewSet, basename='interaction')
router.register(r'responses', ResponseViewSet, basename='response')

# Include router URLs
urlpatterns = [
    path('', include(router.urls)),
]