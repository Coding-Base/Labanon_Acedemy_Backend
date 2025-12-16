from rest_framework import serializers
from django.conf import settings
from .models import User
from djoser.serializers import UserCreateSerializer as DjoserBaseUserCreateSerializer


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'institution_name', 'is_unlocked']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    admin_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role', 'institution_name', 'admin_secret']

    def create(self, validated_data):
        password = validated_data.pop('password')
        # Prevent anonymous or non-admin users from registering as 'admin'
        request = self.context.get('request')
        role = validated_data.get('role')
        admin_secret = validated_data.pop('admin_secret', '')
        if role == User.ADMIN:
            user_request = getattr(request, 'user', None)
            # allow if requester is already an authenticated admin
            if not (user_request and user_request.is_authenticated and getattr(user_request, 'role', None) == User.ADMIN):
                # or allow if a server-side invite code is provided and matches
                invite_code = getattr(settings, 'ADMIN_INVITE_CODE', None)
                if not invite_code or admin_secret != invite_code:
                    raise serializers.ValidationError({'role': 'Cannot register as admin.'})

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class DjoserUserCreateSerializer(DjoserBaseUserCreateSerializer):
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, default=User.STUDENT)
    institution_name = serializers.CharField(allow_blank=True, required=False)
    admin_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta(DjoserBaseUserCreateSerializer.Meta):
        model = User
        fields = ('id', 'username', 'email', 'password', 'role', 'institution_name', 'admin_secret')

    def validate(self, attrs):
        # Prevent registering as admin unless the requester is an authenticated admin
        request = self.context.get('request')
        role = attrs.get('role')
        admin_secret = attrs.pop('admin_secret', '')
        if role == User.ADMIN:
            user_request = getattr(request, 'user', None)
            if not (user_request and user_request.is_authenticated and getattr(user_request, 'role', None) == User.ADMIN):
                invite_code = getattr(settings, 'ADMIN_INVITE_CODE', None)
                if not invite_code or admin_secret != invite_code:
                    raise serializers.ValidationError({'role': 'Cannot register as admin.'})
        return super().validate(attrs)
