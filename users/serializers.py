from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import UserActivity

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""
    
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    full_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'organization', 'organization_name', 'phone', 'avatar',
            'is_active', 'last_activity', 'date_joined', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'date_joined', 'created_at', 'updated_at', 'last_activity']


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new users."""
    
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'organization', 'phone', 'password', 'password_confirm'
        ]
    
    def validate(self, attrs):
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({'password_confirm': "Passwords don't match."})
        role = attrs.get('role')
        organization = attrs.get('organization')
        if role in {'manager', 'officer', 'collector', 'client'} and not organization:
            raise serializers.ValidationError({'organization': 'Organization is required for this role.'})
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating users."""
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'role', 'organization', 
            'phone', 'avatar', 'is_active'
        ]

    def validate(self, attrs):
        role = attrs.get('role', getattr(self.instance, 'role', None))
        organization = attrs.get('organization', getattr(self.instance, 'organization', None))
        if role in {'manager', 'officer', 'collector', 'client'} and not organization:
            raise serializers.ValidationError({'organization': 'Organization is required for this role.'})
        return attrs


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
