from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProjectViewSet, TaskViewSet, DeadlineViewSet

router = DefaultRouter()
router.register('projects', ProjectViewSet, basename='projects')
router.register('tasks', TaskViewSet, basename='tasks')
router.register('deadlines', DeadlineViewSet, basename='deadlines')

urlpatterns = [
    path('', include(router.urls)),
]
