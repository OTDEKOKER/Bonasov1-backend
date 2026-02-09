from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UploadViewSet, ImportJobViewSet

router = DefaultRouter()
router.register('imports', ImportJobViewSet, basename='import-jobs')
router.register('', UploadViewSet, basename='uploads')

urlpatterns = [
    path('', include(router.urls)),
]
