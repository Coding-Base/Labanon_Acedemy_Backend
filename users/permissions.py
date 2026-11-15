from rest_framework import permissions
from .models import User


class IsMasterAdmin(permissions.BasePermission):
    """
    Allow access only to actual master admins (superuser or ADMIN role without a subadmin profile).
    Subadmins MUST NOT pass this check.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if hasattr(user, 'subadmin_profile') or user.role == User.SUBADMIN:
            return False
        return bool(user.role == User.ADMIN)


def check_subadmin_permission(user, permission_key):
    """
    Helper to check if a user is Master Admin or an active Subadmin with the specified permission.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if hasattr(user, 'subadmin_profile') or user.role == User.SUBADMIN:
        try:
            profile = user.subadmin_profile
            if not profile.is_active:
                return False
            return profile.has_permission(permission_key)
        except Exception:
            return False
    if user.role == User.ADMIN:
        return True
    return False


class HasSubAdminPermission(permissions.BasePermission):
    """
    Dynamic DRF permission class that checks for a specific subadmin permission key.
    Usage on ViewSet or APIView:
        required_permission = 'can_manage_courses'
    """

    def has_permission(self, request, view):
        required_perm = getattr(view, 'required_permission', None)
        if not required_perm:
            return False
        return check_subadmin_permission(request.user, required_perm)


class IsUnlocked(permissions.BasePermission):
    """Allow access only to users whose account is unlocked (or staff/admin).

    Safe methods are allowed. For non-safe methods, user must be unlocked or admin.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False
        # allow Django staff/superusers
        if user.is_staff or user.is_superuser:
            return True
        return getattr(user, 'is_unlocked', False)
