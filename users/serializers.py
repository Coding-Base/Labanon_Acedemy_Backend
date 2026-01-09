from rest_framework import serializers
from django.conf import settings
from .models import User
import uuid

# Safe import for Djoser to prevent Pylance/Runtime errors if not installed
try:
    from djoser.serializers import UserCreateSerializer as DjoserBaseUserCreateSerializer
except ImportError:
    # Fallback to standard ModelSerializer if djoser is missing
    from rest_framework.serializers import ModelSerializer as DjoserBaseUserCreateSerializer


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
        role = validated_data.get('role')
        admin_secret = validated_data.pop('admin_secret', '')
        
        # Prevent anonymous or non-admin users from registering as 'admin'
        if role == User.ADMIN:
            request = self.context.get('request')
            user_request = getattr(request, 'user', None)
            
            # allow if requester is already an authenticated admin
            is_admin_request = user_request and user_request.is_authenticated and getattr(user_request, 'role', None) == User.ADMIN
            
            # or allow if a server-side invite code is provided and matches
            invite_code = getattr(settings, 'ADMIN_INVITE_CODE', None)
            is_valid_invite = invite_code and admin_secret == invite_code

            if not (is_admin_request or is_valid_invite):
                raise serializers.ValidationError({'role': 'Cannot register as admin.'})

        # 1. Create the User
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        # 2. AUTOMATICALLY CREATE INSTITUTION & PORTFOLIO
        if role == User.INSTITUTION:
            try:
                # Local import to avoid circular dependency (User -> Course -> User)
                from courses.models import Institution, Portfolio
                
                # Get name from input or default to Username
                inst_name = validated_data.get('institution_name')
                if not inst_name:
                    inst_name = f"{user.username}'s Institution"
                
                # Create Institution Record
                institution = Institution.objects.create(
                    owner=user,
                    name=inst_name,
                    description=f"Welcome to {inst_name}. We provide top-tier educational services."
                )
                
                # Create Portfolio Record
                Portfolio.objects.create(
                    institution=institution,
                    title=inst_name,
                    public_token=str(uuid.uuid4()), # Generate unique public link
                    published=False # Default to draft
                )
                print(f"Auto-created Institution & Portfolio for {user.username}")
                
            except Exception as e:
                # Log error but allow user creation to succeed (prevents registration crash)
                print(f"CRITICAL ERROR: Failed to auto-create institution profile: {e}")

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
        admin_secret = attrs.get('admin_secret', '')
        
        if role == User.ADMIN:
            user_request = getattr(request, 'user', None)
            is_admin_request = user_request and user_request.is_authenticated and getattr(user_request, 'role', None) == User.ADMIN
            
            invite_code = getattr(settings, 'ADMIN_INVITE_CODE', None)
            is_valid_invite = invite_code and admin_secret == invite_code

            if not (is_admin_request or is_valid_invite):
                raise serializers.ValidationError({'role': 'Cannot register as admin.'})
        
        # Clean up admin_secret from attrs so it doesn't get passed to create()
        if 'admin_secret' in attrs:
            del attrs['admin_secret']
            
        return super().validate(attrs)

    def create(self, validated_data):
        # Allow Djoser to handle the standard user creation
        user = super().create(validated_data)
        
        # Add the same auto-creation logic here in case Djoser endpoint is used
        if user.role == User.INSTITUTION:
            try:
                from courses.models import Institution, Portfolio
                
                inst_name = validated_data.get('institution_name') or f"{user.username}'s Institution"
                
                institution = Institution.objects.create(
                    owner=user,
                    name=inst_name,
                    description=f"Welcome to {inst_name}."
                )
                
                Portfolio.objects.create(
                    institution=institution,
                    title=inst_name,
                    public_token=str(uuid.uuid4()),
                    published=False
                )
            except Exception as e:
                print(f"CRITICAL ERROR (Djoser): Failed to auto-create institution profile: {e}")
        
        return user