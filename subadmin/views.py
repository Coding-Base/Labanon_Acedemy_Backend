import logging

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
            
            # Get permissions from request (either legacy boolean fields or new JSON format)
            permissions_data = request.data.get('permissions', {})
            
            # If using legacy format, convert to new format
            if not permissions_data:
                subadmin_instance = SubAdmin(created_by=request.user, user=user)
                permissions_data = subadmin_instance.get_default_permissions()
                
                # Map legacy boolean fields to new format
                legacy_fields = {
                    'can_manage_users': 'can_manage_users',
                    'can_manage_institutions': 'can_manage_institutions',
                    'can_manage_courses': 'can_manage_courses',
                    'can_manage_cbt': 'can_manage_cbt',
                    'can_view_payments': 'can_view_payments',
                    'can_manage_blog': 'can_manage_blog',
                    'can_manage_subadmins': 'can_manage_subadmins',
                    'can_view_messages': 'can_view_messages',
                }
                
                for old_field, new_key in legacy_fields.items():
                    if old_field in request.data:
                        permissions_data[new_key] = request.data.get(old_field, False)
            
            # Create the SubAdmin Profile with JSON permissions
            subadmin = SubAdmin.objects.create(
                created_by=request.user,
                user=user,
                permissions=permissions_data,
                # Also set legacy fields for backward compatibility
                can_manage_users=permissions_data.get('can_manage_users', False),
                can_manage_institutions=permissions_data.get('can_manage_institutions', False),
                can_manage_courses=permissions_data.get('can_manage_courses', False),
                can_manage_cbt=permissions_data.get('can_manage_cbt', False),
                can_view_payments=permissions_data.get('can_view_payments', False),
                can_manage_blog=permissions_data.get('can_manage_blog', False),
                can_manage_subadmins=permissions_data.get('can_manage_subadmins', False),
                can_view_messages=permissions_data.get('can_view_messages', False),
            )
            serializer = self.get_serializer(subadmin)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def available_permissions(self, request):
        """Get list of all available permissions with their descriptions"""
        permissions_map = {
            'can_view_overview': {'label': 'Overview', 'category': 'Dashboard', 'icon': 'BarChart3'},
            'can_manage_users': {'label': 'Manage Users', 'category': 'User Management', 'icon': 'Users'},
            'can_manage_students': {'label': 'Manage Students', 'category': 'User Management', 'icon': 'GraduationCap'},
            'can_manage_tutors': {'label': 'Manage Tutors', 'category': 'User Management', 'icon': 'Briefcase'},
            'can_manage_institutions': {'label': 'Manage Institutions', 'category': 'Institution Management', 'icon': 'Building'},
            'can_manage_admins': {'label': 'Manage Admins', 'category': 'User Management', 'icon': 'Shield'},
            'can_manage_courses': {'label': 'Manage Courses', 'category': 'Course Management', 'icon': 'BookOpen'},
            'can_manage_materials': {'label': 'Manage Materials', 'category': 'Course Management', 'icon': 'File'},
            'can_manage_lessons': {'label': 'Manage Lessons', 'category': 'Course Management', 'icon': 'BookMarked'},
            'can_manage_cbt': {'label': 'Manage CBT/Exams', 'category': 'Exam Management', 'icon': 'FileText'},
            'can_manage_mock_exams': {'label': 'Manage Mock Exams', 'category': 'Exam Management', 'icon': 'Zap'},
            'can_manage_signature': {'label': 'Manage Signature', 'category': 'Institution Management', 'icon': 'Upload'},
            'can_view_analytics': {'label': 'View Analytics', 'category': 'Reporting', 'icon': 'BarChart3'},
            'can_view_payments': {'label': 'View Payments', 'category': 'Reporting', 'icon': 'BarChart3'},
            'can_manage_verification': {'label': 'Manage Verification', 'category': 'Institution Management', 'icon': 'CheckCircle'},
            'can_manage_legal_documents': {'label': 'Manage Legal Documents', 'category': 'Institution Management', 'icon': 'FileText'},
            'can_manage_blog': {'label': 'Manage Blog', 'category': 'Content Management', 'icon': 'BookOpen'},
            'can_manage_gospel': {'label': 'Manage Gospel', 'category': 'Content Management', 'icon': 'Mail'},
            'can_view_messages': {'label': 'View Messages', 'category': 'Communication', 'icon': 'Mail'},
            'can_manage_exams': {'label': 'Manage Exams & Subjects', 'category': 'Exam Management', 'icon': 'GraduationCap'},
            'can_manage_bulk_upload': {'label': 'Bulk Upload', 'category': 'Course Management', 'icon': 'Upload'},
            'can_manage_promos': {'label': 'Manage Promos', 'category': 'Marketing', 'icon': 'Shield'},
            'can_manage_trial': {'label': 'Manage Trial Period', 'category': 'User Management', 'icon': 'Clock'},
            'can_manage_subadmins': {'label': 'Manage Sub-Admins', 'category': 'Admin Management', 'icon': 'UserCog'},
            'can_manage_permissions': {'label': 'Manage Permissions', 'category': 'Admin Management', 'icon': 'Lock'},
        }
        return Response(permissions_map)

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
        # Disallow changes to linked User fields or privilege flags via this endpoint
        forbidden_user_fields = {'user', 'username', 'email', 'is_staff', 'is_superuser'}
        if any(field in request.data for field in forbidden_user_fields):
            return Response({'error': 'Modifying user or privilege fields is forbidden via this endpoint'}, status=status.HTTP_400_BAD_REQUEST)

        logger = logging.getLogger(__name__)
        changed_keys = list(request.data.keys())

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        logger.info('SubAdmin(id=%s,user_id=%s) updated by user_id=%s changed_fields=%s', instance.id, instance.user_id, request.user.id, changed_keys)

        return Response(serializer.data)