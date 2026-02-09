from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from .models import Upload, ImportJob
from .serializers import UploadSerializer, ImportJobSerializer


class UploadViewSet(viewsets.ModelViewSet):
    """ViewSet for managing uploads."""
    
    queryset = Upload.objects.all()
    serializer_class = UploadSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['file_type', 'organization', 'content_type']
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return Upload.objects.all()
        elif user.organization:
            return Upload.objects.filter(organization=user.organization)
        return Upload.objects.filter(created_by=user)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def start_import(self, request, pk=None):
        """Start an import job for the uploaded file."""
        upload = self.get_object()
        
        # Create import job
        job = ImportJob.objects.create(
            upload=upload,
            created_by=request.user
        )
        
        # In production, this would trigger a background task
        # For now, return the job status
        return Response(ImportJobSerializer(job).data, status=status.HTTP_201_CREATED)


class ImportJobViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing import jobs."""
    
    queryset = ImportJob.objects.all()
    serializer_class = ImportJobSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'upload']
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return ImportJob.objects.all()
        return ImportJob.objects.filter(created_by=user)
