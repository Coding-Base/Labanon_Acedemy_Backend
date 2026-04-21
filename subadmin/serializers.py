from rest_framework import serializers
from .models import SubAdmin
from users.serializers import UserSerializer

class SubAdminSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = SubAdmin
        fields = [
            'id', 'user', 
            # New JSON permissions field
            'permissions',
            # Legacy boolean fields (kept for backward compatibility)
            'can_manage_users', 
            'can_manage_institutions', 
            'can_manage_courses', 
            'can_manage_cbt', 
            'can_view_payments', 
            'can_manage_blog', 
            'can_manage_subadmins', 
            'can_view_messages',
            'is_active', 'created_at'
        ]
        read_only_fields = ['created_at']
    
    def to_representation(self, instance):
        """Ensure permissions dict is always populated"""
        if not instance.permissions:
            instance.set_permissions_from_legacy()
            instance.save(update_fields=['permissions'])
        return super().to_representation(instance)
    
    def update(self, instance, validated_data):
        """Handle both legacy boolean fields and new JSON permissions"""
        # If updating via new permissions format, update the JSON field
        if 'permissions' in validated_data:
            instance.permissions = validated_data['permissions']
        
        # Also update legacy fields if provided
        for field in ['can_manage_users', 'can_manage_institutions', 'can_manage_courses', 
                      'can_manage_cbt', 'can_view_payments', 'can_manage_blog', 
                      'can_manage_subadmins', 'can_view_messages']:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        
        instance.save()
        return instance
