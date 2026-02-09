from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ReportViewSet, SavedQueryViewSet, ScheduledReportViewSet, DashboardView, indicator_trends, indicator_trends_bulk

# Create a router and register our viewsets
router = DefaultRouter()
router.register('reports', ReportViewSet, basename='reports')
router.register('scheduled-reports', ScheduledReportViewSet, basename='scheduled-reports')
router.register('saved-queries', SavedQueryViewSet, basename='saved-queries')
router.register('dashboard', DashboardView, basename='dashboard')  # DashboardView as a ViewSet

# Include the router URLs in urlpatterns
urlpatterns = [
    path('', include(router.urls)),
    path('trends/<int:indicator_id>/', indicator_trends, name='indicator-trends'),
    path('trends/', indicator_trends_bulk, name='indicator-trends-bulk'),
]
