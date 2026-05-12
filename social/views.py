from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from organizations.access import get_user_organization_ids, is_organization_admin, filter_queryset_by_org_ids

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
        if is_organization_admin(user):
            return SocialPost.objects.all()
        org_ids = get_user_organization_ids(user)
        if org_ids:
            return filter_queryset_by_org_ids(SocialPost.objects.all(), 'organization_id', org_ids)
        return SocialPost.objects.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

