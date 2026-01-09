from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from .models import SubAdmin
from .serializers import SubAdminSerializer
from users.permissions import IsMasterAdmin

User = get_user_model()

class SubAdminViewSet(viewsets.ModelViewSet):
    """Sub-admin management endpoints"""
    queryset = SubAdmin.objects.all()
    serializer_class = SubAdminSerializer
    permission_classes = [IsMasterAdmin]

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's sub-admin profile if they are a sub-admin"""
        try:
            subadmin = SubAdmin.objects.get(user=request.user)
            serializer = self.get_serializer(subadmin)
            return Response(serializer.data)
        except SubAdmin.DoesNotExist:
            return Response({'detail': 'User is not a sub-admin'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def create_subadmin(self, request):
        """Create a new sub-admin account"""
        username = request.data.get('username')
        password = request.data.get('password')
        email = request.data.get('email', '')
        
        if not username or not password:
            return Response({'error': 'username and password required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Create the User
            user = User.objects.create_user(username=username, password=password, email=email, is_staff=True)
            
            # Create the SubAdmin Profile with ALL permissions
            subadmin = SubAdmin.objects.create(
                created_by=request.user,
                user=user,
                can_manage_users=request.data.get('can_manage_users', False),
                can_manage_institutions=request.data.get('can_manage_institutions', False),
                can_manage_courses=request.data.get('can_manage_courses', False),
                can_manage_cbt=request.data.get('can_manage_cbt', False),
                can_view_payments=request.data.get('can_view_payments', False),
                can_manage_blog=request.data.get('can_manage_blog', False),
                can_manage_subadmins=request.data.get('can_manage_subadmins', False),
                can_view_messages=request.data.get('can_view_messages', False), # <--- Added
            )
            serializer = self.get_serializer(subadmin)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def list_subadmins(self, request):
        """Get all sub-admins created by this master admin"""
        subadmins = SubAdmin.objects.filter(created_by=request.user)
        serializer = self.get_serializer(subadmins, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['delete'])
    def delete_subadmin(self, request, pk=None):
        """Delete a sub-admin account"""
        subadmin = self.get_object()
        if subadmin.created_by != request.user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
        user = subadmin.user
        subadmin.delete()
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # Added Update method to fix permissions on existing accounts
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Prevent updating subadmins you didn't create
        if instance.created_by != request.user:
             return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)