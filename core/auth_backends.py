"""Sign in with a username or an email address."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


def find_user(identifier):
    """The user for a username or (if unique) an email address; None if there's no single match."""
    User = get_user_model()
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    try:
        return User._default_manager.get_by_natural_key(identifier)
    except User.DoesNotExist:
        pass
    if "@" in identifier:
        matches = list(User._default_manager.filter(email__iexact=identifier)[:2])
        if len(matches) == 1:  # an email shared by two accounts can't be used to sign in
            return matches[0]
    return None


class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or password is None:
            return None
        user = find_user(username)
        if user is None:
            User().set_password(password)  # same time spent as a real check, so it can't be used to find accounts
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
