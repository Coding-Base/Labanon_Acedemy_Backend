from rest_framework import permissions
from .models import User


class IsMasterAdmin(permissions.BasePermission):
    """Allow access only to the master admin (role == ADMIN) or staff users."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.role == User.ADMIN))
from rest_framework import permissions


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
