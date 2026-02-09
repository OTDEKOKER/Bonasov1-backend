from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CookieTokenObtainPairView, CookieTokenRefreshView,
    current_user, logout_view, TestConnectionView,
    ApplyForNewUser, AdminResetPasswordView, UserViewSet
)

router = DefaultRouter()
router.register(r'', UserViewSet, basename='user')  # handles /api/users/

urlpatterns = [
    # JWT Auth
    path('request-token/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    
    # User info
    path('me/', current_user, name='current_user'),
    path('logout/', logout_view, name='logout'),
    
    # Test
    path('test-connection/', TestConnectionView.as_view(), name='test_connection'),
    
    # Create / admin
    path('create-user/', ApplyForNewUser.as_view(), name='create_user'),
    path('admin-reset-password/', AdminResetPasswordView.as_view(), name='admin_reset_password'),
    
    # Include ViewSet
    path('', include(router.urls)),
]
