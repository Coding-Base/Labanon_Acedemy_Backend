from django.db import models
from django.conf import settings

class SubAdmin(models.Model):
    """Sub-admin account with limited dashboard permissions"""
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_subadmins')
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subadmin_profile')
    
    # Permission flags for dashboard features
    can_manage_users = models.BooleanField(default=False)
    can_manage_institutions = models.BooleanField(default=False)
    can_manage_courses = models.BooleanField(default=False)
    can_manage_cbt = models.BooleanField(default=False)
    can_view_payments = models.BooleanField(default=False)
    can_manage_blog = models.BooleanField(default=False)
    can_manage_subadmins = models.BooleanField(default=False)
    
    # ADDED: This was missing but required by your Dashboard
    can_view_messages = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sub-Admin'
        verbose_name_plural = 'Sub-Admins'

    def __str__(self):
        return f"SubAdmin: {self.user.username}"