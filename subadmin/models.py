from django.db import models
from django.conf import settings
import json

class SubAdmin(models.Model):
    """Sub-admin account with limited dashboard permissions"""
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_subadmins')
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subadmin_profile')
    
    # NEW: JSON field for granular tab-based permissions (23+ tabs)
    permissions = models.JSONField(default=dict, blank=True)
    
    # DEPRECATED: Keep old boolean fields for backward compatibility during migration
    can_manage_users = models.BooleanField(default=False)
    can_manage_institutions = models.BooleanField(default=False)
    can_manage_courses = models.BooleanField(default=False)
    can_manage_cbt = models.BooleanField(default=False)
    can_view_payments = models.BooleanField(default=False)
    can_manage_blog = models.BooleanField(default=False)
    can_manage_subadmins = models.BooleanField(default=False)
    can_view_messages = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sub-Admin'
        verbose_name_plural = 'Sub-Admins'

    def __str__(self):
        return f"SubAdmin: {self.user.username}"
    
    def get_default_permissions(self):
        """Get all available permissions with default False values"""
        return {
            'can_view_overview': False,
            'can_manage_users': False,
            'can_manage_students': False,
            'can_manage_tutors': False,
            'can_manage_institutions': False,
            'can_manage_admins': False,
            'can_manage_courses': False,
            'can_manage_materials': False,
            'can_manage_lessons': False,
            'can_manage_cbt': False,
            'can_manage_mock_exams': False,
            'can_manage_signature': False,
            'can_view_analytics': False,
            'can_view_payments': False,
            'can_manage_verification': False,
            'can_manage_legal_documents': False,
            'can_manage_blog': False,
            'can_manage_gospel': False,
            'can_view_messages': False,
            'can_manage_exams': False,
            'can_manage_bulk_upload': False,
            'can_manage_promos': False,
            'can_manage_trial': False,
            'can_manage_subadmins': False,
            'can_manage_permissions': False,
        }
    
    def set_permissions_from_legacy(self):
        """Convert old boolean fields to new JSON format"""
        if not self.permissions:
            self.permissions = self.get_default_permissions()
            # Map old boolean fields to new permission keys
            if self.can_manage_users:
                self.permissions['can_manage_users'] = True
            if self.can_manage_institutions:
                self.permissions['can_manage_institutions'] = True
            if self.can_manage_courses:
                self.permissions['can_manage_courses'] = True
            if self.can_manage_cbt:
                self.permissions['can_manage_cbt'] = True
            if self.can_view_payments:
                self.permissions['can_view_payments'] = True
            if self.can_manage_blog:
                self.permissions['can_manage_blog'] = True
            if self.can_manage_subadmins:
                self.permissions['can_manage_subadmins'] = True
            if self.can_view_messages:
                self.permissions['can_view_messages'] = True
    
    def has_permission(self, permission_key):
        """Check if sub-admin has a specific permission"""
        if not self.permissions:
            self.set_permissions_from_legacy()
        return self.permissions.get(permission_key, False)