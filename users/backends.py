from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

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

        # Verify password and check if user is active
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None