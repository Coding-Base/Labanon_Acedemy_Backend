from rest_framework import permissions

from users.models import User


class CanManageExamLibrary(permissions.BasePermission):
    """Allow master admins and sub-admins granted CBT/exam permissions."""

    message = 'You do not have permission to manage the exam library.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_staff or user.is_superuser or user.role == User.ADMIN:
            return True

        try:
            profile = user.subadmin_profile
        except Exception:
            return False

        if not profile.is_active:
            return False

        configured = profile.permissions or {}
        return bool(
            configured.get('can_manage_cbt')
            or configured.get('can_manage_exams')
            or profile.can_manage_cbt
        )
