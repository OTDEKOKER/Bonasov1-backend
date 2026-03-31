from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.permissions import is_platform_admin
from .models import UserActivity

User = get_user_model()

EXCLUDED_ASSIGNABLE_PERMISSION_APP_LABELS = {
    'admin',
    'auth',
    'contenttypes',
    'sessions',
    'token_blacklist',
}


def build_permission_identifier(permission):
    return f'{permission.content_type.app_label}.{permission.codename}'


def get_assignable_permissions_queryset():
    return Permission.objects.select_related('content_type').exclude(
        content_type__app_label__in=EXCLUDED_ASSIGNABLE_PERMISSION_APP_LABELS
    ).order_by('content_type__app_label', 'codename', 'name')


def normalize_permission_identifiers(permission_ids):
    identifiers = []
    seen = set()

    for permission_id in permission_ids or []:
        normalized = str(permission_id or '').strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        identifiers.append(normalized)

    return identifiers


def resolve_login_user(identifier):
    normalized = str(identifier or '').strip()
    if not normalized:
        return None

    return User.objects.filter(
        Q(username__iexact=normalized) | Q(email__iexact=normalized)
    ).first()


def resolve_permission_identifiers(permission_ids):
    identifiers = normalize_permission_identifiers(permission_ids)
    if not identifiers:
        return [], []

    invalid_identifiers = []
    query = Q()
    for identifier in identifiers:
        app_label, separator, codename = identifier.partition('.')
        if not separator or not app_label or not codename:
            invalid_identifiers.append(identifier)
            continue
        query |= Q(content_type__app_label=app_label, codename=codename)

    if invalid_identifiers:
        raise serializers.ValidationError({
            'permissions': [
                f"Invalid permission id(s): {', '.join(invalid_identifiers)}."
            ]
        })

    permissions = list(get_assignable_permissions_queryset().filter(query))
    permissions_by_identifier = {
        build_permission_identifier(permission): permission for permission in permissions
    }
    missing_identifiers = [
        identifier for identifier in identifiers if identifier not in permissions_by_identifier
    ]
    if missing_identifiers:
        raise serializers.ValidationError({
            'permissions': [
                f"Unknown permission id(s): {', '.join(missing_identifiers)}."
            ]
        })

    ordered_permissions = [
        permissions_by_identifier[identifier] for identifier in identifiers
    ]
    return identifiers, ordered_permissions


class PermissionOptionSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    app_label = serializers.CharField(source='content_type.app_label', read_only=True)

    class Meta:
        model = Permission
        fields = ['id', 'app_label', 'codename', 'name']

    def get_id(self, obj):
        return build_permission_identifier(obj)


class EmailOrUsernameTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Allow SimpleJWT login via either username or email."""

    def validate(self, attrs):
        identifier = attrs.get(self.username_field) or attrs.get('email')
        user = resolve_login_user(identifier)
        if user is not None:
            attrs[self.username_field] = getattr(user, self.username_field)
        return super().validate(attrs)


class PermissionAssignmentMixin(serializers.Serializer):
    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )

    def validate_permissions(self, value):
        request = self.context.get('request')
        caller_is_admin = is_platform_admin(getattr(request, 'user', None))
        normalized_permissions = normalize_permission_identifiers(value)

        if not caller_is_admin:
            if normalized_permissions:
                raise serializers.ValidationError('Only admins can assign user permissions.')
            self._validated_permission_objects = []
            return []

        _, permission_objects = resolve_permission_identifiers(normalized_permissions)
        self._validated_permission_objects = permission_objects
        return normalized_permissions

    def get_validated_permission_objects(self):
        return list(getattr(self, '_validated_permission_objects', []))


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    organization_name = serializers.CharField(source='organization.name', read_only=True)
    full_name = serializers.CharField(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'organization', 'organization_name', 'phone', 'avatar',
            'is_active', 'last_activity', 'date_joined', 'created_at', 'updated_at',
            'permissions',
        ]
        read_only_fields = [
            'id', 'date_joined', 'created_at', 'updated_at', 'last_activity', 'permissions'
        ]

    def get_permissions(self, obj):
        return [
            build_permission_identifier(permission)
            for permission in obj.user_permissions.select_related('content_type').order_by(
                'content_type__app_label',
                'codename',
            )
        ]


class UserCreateSerializer(PermissionAssignmentMixin, serializers.ModelSerializer):
    """Serializer for creating new users."""

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'organization', 'phone', 'password', 'password_confirm',
            'permissions',
        ]

    def validate(self, attrs):
        request = self.context.get('request')
        caller_is_admin = is_platform_admin(getattr(request, 'user', None))

        if not caller_is_admin:
            requested_role = attrs.get('role') or 'client'
            if requested_role in {'admin', 'manager'}:
                raise serializers.ValidationError({
                    'role': 'Public registration cannot assign admin or manager roles.'
                })
            attrs['role'] = requested_role

        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({'password_confirm': "Passwords don't match."})
        role = attrs.get('role')
        organization = attrs.get('organization')
        if role in {'manager', 'officer', 'collector', 'client'} and not organization:
            raise serializers.ValidationError({'organization': 'Organization is required for this role.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        validated_data.pop('permissions', None)
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        permission_objects = self.get_validated_permission_objects()
        if permission_objects:
            user.user_permissions.set(permission_objects)

        return user


class UserUpdateSerializer(PermissionAssignmentMixin, serializers.ModelSerializer):
    """Serializer for updating users."""

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'role', 'organization',
            'phone', 'avatar', 'is_active', 'permissions'
        ]

    def validate_permissions(self, value):
        request = self.context.get('request')
        if request and not is_platform_admin(getattr(request, 'user', None)):
            raise serializers.ValidationError('Only admins can update this field.')
        return super().validate_permissions(value)

    def validate(self, attrs):
        request = self.context.get('request')
        if request and not is_platform_admin(getattr(request, 'user', None)):
            restricted = [
                field for field in ('role', 'organization', 'is_active', 'permissions')
                if field in self.initial_data
            ]
            if restricted:
                raise serializers.ValidationError({
                    field: 'Only admins can update this field.' for field in restricted
                })

        role = attrs.get('role', getattr(self.instance, 'role', None))
        organization = attrs.get('organization', getattr(self.instance, 'organization', None))
        if (
            ('role' in attrs or 'organization' in attrs)
            and role in {'manager', 'officer', 'collector', 'client'}
            and not organization
        ):
            raise serializers.ValidationError({'organization': 'Organization is required for this role.'})
        return attrs

    def update(self, instance, validated_data):
        permissions_were_supplied = 'permissions' in validated_data
        validated_data.pop('permissions', None)
        user = super().update(instance, validated_data)

        if permissions_were_supplied:
            user.user_permissions.set(self.get_validated_permission_objects())

        return user


class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for password change."""

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': "Passwords don't match."})
        return attrs


class AdminResetPasswordSerializer(serializers.Serializer):
    """Serializer for admin password reset."""

    user_id = serializers.IntegerField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])


class UserActivitySerializer(serializers.ModelSerializer):
    """Serializer for user activity logs."""

    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = UserActivity
        fields = ['id', 'user', 'user_name', 'action', 'model_name', 'object_id', 'description', 'ip_address', 'timestamp']
        read_only_fields = ['id', 'timestamp']
