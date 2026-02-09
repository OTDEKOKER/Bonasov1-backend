from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IndicatorViewSet, AssessmentViewSet

router = DefaultRouter()
router.register('assessments', AssessmentViewSet, basename='assessments')
router.register('', IndicatorViewSet, basename='indicators')

urlpatterns = [
    path('', include(router.urls)),
]
