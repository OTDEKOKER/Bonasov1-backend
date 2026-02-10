from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import SocialPost
from .serializers import SocialPostSerializer


class SocialPostViewSet(viewsets.ModelViewSet):
    """ViewSet for managing social media posts."""

    queryset = SocialPost.objects.all()
    serializer_class = SocialPostSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['indicator', 'organization', 'platform']
    search_fields = ['title', 'url']
    ordering_fields = ['created_at', 'updated_at', 'views', 'likes', 'comments', 'shares']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return SocialPost.objects.all()
        elif user.organization:
            return SocialPost.objects.filter(organization=user.organization)
        return SocialPost.objects.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

