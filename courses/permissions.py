from rest_framework import permissions
from users.models import User


class IsCreatorOrTeacherOrAdmin(permissions.BasePermission):
    """Allow read-only to everyone; create/update/delete only to tutors, institutions, or admins.

    - SAFE_METHODS: allow any
    - POST (create): allowed for authenticated users with role in (tutor, institution, admin)
    - PUT/PATCH/DELETE: allowed only if user is the creator of the object or admin
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        # For create, require role
        if request.method == 'POST':
            user = request.user
            return (
                user and user.is_authenticated and
                user.role in (User.TUTOR, User.INSTITUTION, User.ADMIN)
            )
        # For other methods, allow; object-level check will handle ownership
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        # Admins can do anything
        if request.user.role == User.ADMIN:
            return True
        # Creator can modify
        try:
            creator = getattr(obj, 'creator', None)
            if creator and creator == request.user:
                return True
        except Exception:
            pass
        return False
