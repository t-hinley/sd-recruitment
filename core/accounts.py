"""Suspending and reactivating staff accounts (instead of deleting them), with a permanent history.

A suspended account cannot sign in (password, email or authenticator code), cannot reset its password,
and is signed out on its next click. Everything it did, and every enquiry assigned to it, stays on record.
"""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import AccountStatusChange


class StatusError(Exception):
    pass


def check(actor, user, suspend):
    """Raise StatusError when this change is not allowed."""
    if suspend and user.pk == actor.pk:
        raise StatusError("You can't suspend your own account.")
    if suspend and user.is_superuser and not actor.is_superuser:
        raise StatusError(f"Only an administrator can suspend {user.get_username()}.")
    if suspend and user.is_superuser:
        others = get_user_model().objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk)
        if not others.exists():
            raise StatusError(f"{user.get_username()} is the only active administrator, so can't be suspended.")


@transaction.atomic
def set_status(actor, user, suspend, reason):
    """Suspend (suspend=True) or reactivate a user and record who, when and why. Returns True if changed."""
    reason = (reason or "").strip()
    if not reason:
        raise StatusError("Please give a reason. It's kept in the account history.")
    if user.is_active == (not suspend):
        return False
    check(actor, user, suspend)
    user.is_active = not suspend
    user.save(update_fields=["is_active"])
    entry = AccountStatusChange.objects.create(
        user=user, action=AccountStatusChange.SUSPENDED if suspend else AccountStatusChange.REACTIVATED,
        reason=reason, changed_by=actor, username=user.get_username(), full_name=user.get_full_name(),
        email=user.email)
    LogEntry.objects.log_actions(
        user_id=actor.pk, queryset=[user], action_flag=CHANGE, single_object=True,
        change_message=f"{entry.get_action_display()} account. Reason: {reason}")
    return True
