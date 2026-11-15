from rest_framework import permissions

from users.models import User


class CanManageExamLibrary(permissions.BasePermission):
    """Allow master admins and sub-admins granted CBT/exam permissions."""

    message = 'You do not have permission to manage the exam library.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        # Check subadmin permissions strictly
        if hasattr(user, 'subadmin_profile') or user.role == User.SUBADMIN:
            try:
                profile = user.subadmin_profile
                if not profile.is_active:
                    return False
                configured = profile.permissions or {}
                return bool(
                    configured.get('can_manage_cbt')
                    or configured.get('can_manage_exams')
                    or configured.get('can_manage_exam_library')
                    or profile.can_manage_cbt
                )
            except Exception:
                return False

        # Master admin
        return bool(user.role == User.ADMIN)
