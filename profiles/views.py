from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.db import models

from core.permissions import is_platform_admin
from .models import Profile, ProfileField
from .serializers import ProfileSerializer, ProfileFieldSerializer


class ProfileViewSet(viewsets.ModelViewSet):
    """ViewSet for managing profiles."""
    
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['respondent']
    
    def get_queryset(self):
        user = self.request.user
        if is_platform_admin(user):
            return Profile.objects.all()
        elif user.organization:
            return Profile.objects.filter(respondent__organization=user.organization)
        return Profile.objects.none()

    def _validate_respondent_scope(self, respondent):
        user = self.request.user
        if is_platform_admin(user):
            return
        if not user.organization_id or respondent.organization_id != user.organization_id:
            raise PermissionDenied('You can only manage profiles for respondents in your organization.')

    def perform_create(self, serializer):
        self._validate_respondent_scope(serializer.validated_data['respondent'])
        serializer.save()

    def perform_update(self, serializer):
        self._validate_respondent_scope(serializer.validated_data.get('respondent', serializer.instance.respondent))
        serializer.save()


class ProfileFieldViewSet(viewsets.ModelViewSet):
    """ViewSet for managing custom profile fields."""
    
    queryset = ProfileField.objects.all()
    serializer_class = ProfileFieldSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['organization', 'field_type']
    
    def get_queryset(self):
        user = self.request.user
        if is_platform_admin(user):
            return ProfileField.objects.all()
        return ProfileField.objects.filter(
            models.Q(organization=user.organization) |
            models.Q(organization__isnull=True)
        )

    def perform_create(self, serializer):
        user = self.request.user
        organization = serializer.validated_data.get('organization')
        if is_platform_admin(user):
            serializer.save()
            return
        if organization and organization.id != user.organization_id:
            raise PermissionDenied('You can only create fields for your own organization.')
        serializer.save(organization=user.organization)

    def perform_update(self, serializer):
        user = self.request.user
        organization = serializer.validated_data.get('organization', serializer.instance.organization)
        if is_platform_admin(user):
            serializer.save()
            return
        if organization and organization.id != user.organization_id:
            raise PermissionDenied('You can only update fields for your own organization.')
        serializer.save(organization=user.organization)

