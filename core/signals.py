from django.contrib import messages
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db.models.signals import post_delete
from django.dispatch import receiver

from . import security
from .models import CandidateRegistration


@receiver(post_delete, sender=CandidateRegistration)
def delete_resume_file(sender, instance, **kwargs):
    """Deleting a candidate (one at a time or in bulk) also removes their stored CV file."""
    if instance.resume:
        instance.resume.storage.delete(instance.resume.name)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    if request is not None:
        security.record_failure(request, str(credentials.get("username", "")))


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    # Shows the "Login successful!" pop-up once on the next admin page.
    if user.is_staff and request is not None and hasattr(request, "_messages"):
        messages.success(request, "Login successful!", extra_tags="toast")
