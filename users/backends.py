import logging

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

logger = logging.getLogger(__name__)


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Authentication backend which allows users to authenticate using either their
    username or email address.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        # 'username' argument is the value from the login form (could be an email)
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)

        try:
            # Try to find user by Username OR Email
            user = User.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # Don't raise a 500 on duplicate records — log the issue and fail authentication
            # Returning None causes the authentication flow to return a 401/invalid credentials
            # instead of crashing the request. Admins should dedupe users in the database.
            try:
                duplicate_qs = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username))
                dup_ids = list(duplicate_qs.values_list('id', flat=True)[:10])
            except Exception:
                dup_ids = None
            logger.exception(
                "Multiple users matched login identifier '%s'. duplicate_ids=%s",
                username,
                dup_ids,
            )
            return None

        # Verify password and check if user is active
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None