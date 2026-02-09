from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Organization
from .serializers import (
    OrganizationSerializer, OrganizationTreeSerializer, OrganizationSimpleSerializer
)


class OrganizationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing organizations."""
    
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'parent', 'is_active']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'created_at', 'type']
    ordering = ['name']
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return Organization.objects.all()
        elif user.organization:
            # Return user's org and its descendants
            org = user.organization
            descendants = org.get_descendants()
            ancestors = org.get_ancestors()
            return Organization.objects.filter(
                id__in=[org.id]
                + [d.id for d in descendants]
                + [a.id for a in ancestors]
            )
        return Organization.objects.none()
    
    def perform_create(self, serializer):
        serializer.save()
    
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Get organization hierarchy tree."""
        root_orgs = Organization.objects.filter(parent__isnull=True, is_active=True)
        serializer = OrganizationTreeSerializer(root_orgs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def simple(self, request):
        """Get simple list for dropdowns."""
        orgs = self.get_queryset().filter(is_active=True)
        serializer = OrganizationSimpleSerializer(orgs, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def descendants(self, request, pk=None):
        """Get all descendant organizations."""
        org = self.get_object()
        descendants = org.get_descendants()
        serializer = OrganizationSimpleSerializer(descendants, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def users(self, request, pk=None):
        """Get users in this organization."""
        from users.serializers import UserSerializer
        org = self.get_object()
        users = org.users.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)
