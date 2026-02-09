from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

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
        if user.role == 'admin':
            return Profile.objects.all()
        elif user.organization:
            return Profile.objects.filter(respondent__organization=user.organization)
        return Profile.objects.none()


class ProfileFieldViewSet(viewsets.ModelViewSet):
    """ViewSet for managing custom profile fields."""
    
    queryset = ProfileField.objects.all()
    serializer_class = ProfileFieldSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['organization', 'field_type']
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return ProfileField.objects.all()
        return ProfileField.objects.filter(
            models.Q(organization=user.organization) |
            models.Q(organization__isnull=True)
        )
