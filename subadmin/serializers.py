from rest_framework import serializers
from .models import SubAdmin
from users.serializers import UserSerializer


class SubAdminSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = SubAdmin
        fields = ['id', 'user', 'can_manage_users', 'can_manage_institutions', 'can_manage_courses', 
                  'can_manage_cbt', 'can_view_payments', 'can_manage_blog', 'can_manage_subadmins', 
                  'is_active', 'created_at']
        read_only_fields = ['created_at']
