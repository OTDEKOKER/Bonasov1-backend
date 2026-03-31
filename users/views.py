from django.contrib.auth import get_user_model
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.permissions import IsPlatformAdmin, is_platform_admin
from .models import UserActivity
from .serializers import (
    AdminResetPasswordSerializer,
    EmailOrUsernameTokenObtainPairSerializer,
    PasswordChangeSerializer,
    PermissionOptionSerializer,
    resolve_login_user,
    UserActivitySerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
    get_assignable_permissions_queryset,
)

User = get_user_model()


class CookieTokenObtainPairView(TokenObtainPairView):
    """Custom login view that logs user activity."""
    serializer_class = EmailOrUsernameTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user = resolve_login_user(request.data.get('username') or request.data.get('email'))
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """Return currently logged-in user details."""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


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
    throttle_classes = [AnonRateThrottle]


class AdminResetPasswordView(APIView):
    """Admin can reset a user's password."""
    permission_classes = [IsPlatformAdmin]

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


class UserViewSet(viewsets.ModelViewSet):
    """CRUD for users."""

    queryset = User.objects.all().prefetch_related('user_permissions__content_type')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'organization', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'created_at', 'last_activity']
    ordering = ['-created_at']
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'destroy', 'deactivate', 'activate', 'permissions']:
            return [IsPlatformAdmin()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        if self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer

    def get_queryset(self):
        """Filter queryset based on user role."""
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return User.objects.all().prefetch_related('user_permissions__content_type')
        if user.role == 'manager':
            return User.objects.filter(organization=user.organization).prefetch_related(
                'user_permissions__content_type'
            )
        return User.objects.filter(id=user.id).prefetch_related('user_permissions__content_type')

    @action(detail=False, methods=['get'])
    def permissions(self, request):
        """Return assignable user permissions for admin screens."""
        serializer = PermissionOptionSerializer(get_assignable_permissions_queryset(), many=True)
        return Response(serializer.data)

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


class UserActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only view for user activities."""

    queryset = UserActivity.objects.all()
    serializer_class = UserActivitySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['user', 'action', 'model_name']
    ordering = ['-timestamp']

    def get_queryset(self):
        user = self.request.user
        if is_platform_admin(user):
            return UserActivity.objects.all()
        if getattr(user, 'role', None) == 'manager' and user.organization_id:
            return UserActivity.objects.filter(user__organization_id=user.organization_id)
        return UserActivity.objects.filter(user=user)
