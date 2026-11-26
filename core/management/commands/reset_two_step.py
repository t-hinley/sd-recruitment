"""Reset someone's two-step login (e.g. lost phone): they set up their authenticator app again at their
next sign-in.

    python manage.py reset_two_step USERNAME_OR_EMAIL
"""

from django.core.management.base import BaseCommand, CommandError

from core.auth_backends import find_user
from core.models import AuthenticatorDevice


class Command(BaseCommand):
    help = "Remove a user's authenticator app so they set it up again at their next sign-in."

    def add_arguments(self, parser):
        parser.add_argument("user", help="Username or email address")

    def handle(self, *args, **opts):
        user = find_user(opts["user"])
        if not user:
            raise CommandError(f"No single account matches {opts['user']!r}.")
        deleted, _ = AuthenticatorDevice.objects.filter(user=user).delete()
        if deleted:
            self.stdout.write(f"Two-step login reset for {user.get_username()}. They'll set it up again at their next sign-in.")
        else:
            self.stdout.write(f"{user.get_username()} had no authenticator app set up.")
