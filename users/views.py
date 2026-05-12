from rest_framework import viewsets, status, generics
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from organizations.access import get_user_organization_ids, is_organization_admin, filter_queryset_by_org_ids

from .models import UserActivity
from .serializers import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    PasswordChangeSerializer, AdminResetPasswordSerializer, UserActivitySerializer,
    CurrentUserDashboardPreferencesSerializer,
)

User = get_user_model()


# ---------------------------
# JWT Token Views
# ---------------------------
class CookieTokenObtainPairView(TokenObtainPairView):
    """Custom login view that logs user activity."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user = User.objects.filter(username=request.data.get('username')).first()
            if user:
                user.last_activity = timezone.now()
                user.save(update_fields=['last_activity'])
                UserActivity.objects.create(
                    user=user,
                    action='login',
                    ip_address=self.get_client_ip(request)
                )
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')


class CookieTokenRefreshView(TokenRefreshView):
    """Custom refresh token view."""
    pass


# ---------------------------
# Auth & User Endpoints
# ---------------------------
@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """Return or update currently logged-in user details."""
    if request.method == 'PATCH':
        serializer = CurrentUserDashboardPreferencesSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

    response_serializer = UserSerializer(request.user)
    return Response(response_serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Logout by blacklisting refresh token."""
    refresh_token = request.data.get('refresh')
    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    UserActivity.objects.create(
        user=request.user,
        action='logout',
        ip_address=request.META.get('REMOTE_ADDR')
    )
    return Response({'detail': 'Successfully logged out.'})


class TestConnectionView(APIView):
    """Test API - no authentication required."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'status': 'ok', 'message': 'BONASO API is running'})


class ApplyForNewUser(generics.CreateAPIView):
    """Create new user account."""
    serializer_class = UserCreateSerializer
    permission_classes = [AllowAny]


class AdminResetPasswordView(APIView):
    """Admin can reset a user's password."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = AdminResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = User.objects.get(id=serializer.validated_data['user_id'])
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            UserActivity.objects.create(
                user=request.user,
                action='update',
                model_name='User',
                object_id=user.id,
                description=f'Admin reset password for {user.username}'
            )
            return Response({'detail': 'Password reset successfully.'})
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)


# ---------------------------
# User Management ViewSet
# ---------------------------
class UserViewSet(viewsets.ModelViewSet):
    """CRUD for users."""
    queryset = User.objects.all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'organization', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'created_at', 'last_activity']
    ordering = ['-created_at']

    # For testing, allow unauthenticated; change to IsAuthenticated in production
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer

    def get_queryset(self):
        """Filter queryset based on user role."""
        queryset = User.objects.select_related('organization')
        user = self.request.user
        if is_organization_admin(user):
            return queryset
        if user.role == 'manager':
            org_ids = get_user_organization_ids(user)
            if org_ids:
                return filter_queryset_by_org_ids(queryset, 'organization_id', org_ids)
            return queryset.none()
        return queryset.filter(id=user.id)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a user."""
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response({'detail': 'User deactivated.'})

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a user."""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({'detail': 'User activated.'})

    @action(detail=True, methods=['get'])
    def activity(self, request, pk=None):
        """Return last 50 activities of a user."""
        user = self.get_object()
        activities = UserActivity.objects.filter(user=user).order_by('-timestamp')[:50]
        serializer = UserActivitySerializer(activities, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def permissions(self, request):
        """Return assignable permissions for admins."""
        user = request.user
        if not (user.is_superuser or user.is_staff or user.role == 'admin'):
            return Response({'detail': 'You do not have permission to view permissions.'}, status=status.HTTP_403_FORBIDDEN)

        permissions = Permission.objects.select_related('content_type').order_by(
            'content_type__app_label', 'codename'
        )
        payload = [
            {
                'id': str(permission.id),
                'app_label': permission.content_type.app_label,
                'codename': permission.codename,
                'name': permission.name,
            }
            for permission in permissions
        ]
        return Response(payload)


# ---------------------------
# User Activity ViewSet
# ---------------------------
class UserActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only view for user activities."""
    queryset = UserActivity.objects.select_related('user')
    serializer_class = UserActivitySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['user', 'action', 'model_name']
    ordering = ['-timestamp']

    def get_queryset(self):
        user = self.request.user
        queryset = UserActivity.objects.select_related('user')
        if is_organization_admin(user):
            return queryset
        if user.role == 'manager':
            org_ids = get_user_organization_ids(user)
            if org_ids:
                return filter_queryset_by_org_ids(queryset, 'user__organization_id', org_ids)
            return queryset.none()
        return queryset.filter(user=user)

