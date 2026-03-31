from rest_framework.permissions import BasePermission


def is_platform_admin(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.is_staff or getattr(user, "role", None) == "admin")
    )


class IsPlatformAdmin(BasePermission):
    message = "Admin privileges are required."

    def has_permission(self, request, view):
        return is_platform_admin(request.user)
