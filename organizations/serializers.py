from rest_framework import serializers
from .models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer for Organization model."""
    
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    children_count = serializers.SerializerMethodField()
    users_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'code', 'type', 'parent', 'parent_name',
            'description', 'address', 'phone', 'email', 'is_active',
            'children_count', 'users_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        code = (validated_data.get('code') or '').strip().upper()
        name = (validated_data.get('name') or '').strip()

        if not code:
            base = ''.join(ch if ch.isalnum() else '_' for ch in name.upper())
            base = base.strip('_') or 'ORG'
            code = base
        else:
            base = code

        # Ensure code is unique; append suffix if needed.
        if Organization.objects.filter(code=code).exists():
            suffix = 1
            while Organization.objects.filter(code=f"{base}_{suffix}").exists():
                suffix += 1
            code = f"{base}_{suffix}"

        validated_data['code'] = code
        return super().create(validated_data)
    
    def get_children_count(self, obj):
        return obj.children.count()
    
    def get_users_count(self, obj):
        return obj.users.count()


class OrganizationTreeSerializer(serializers.ModelSerializer):
    """Serializer for organization hierarchy tree."""
    
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = Organization
        fields = ['id', 'name', 'code', 'type', 'children']
    
    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        return OrganizationTreeSerializer(children, many=True).data


class OrganizationSimpleSerializer(serializers.ModelSerializer):
    """Simple serializer for dropdowns."""
    
    class Meta:
        model = Organization
        fields = ['id', 'name', 'code', 'type']
