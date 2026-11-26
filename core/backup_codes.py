"""Ten single-use backup codes per authenticator app, e.g. 'k7m2p-x9qrt'. Shown once when created; only an
HMAC of each code is stored, so a copy of the database doesn't reveal them."""

import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import BackupCode

COUNT = 10
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i: easy to read and type
SESSION_KEY = "backup_codes_to_show"


def normalise(raw):
    return "".join(ch for ch in (raw or "").lower() if ch.isalnum())


def looks_like_backup_code(raw):
    code = normalise(raw)
    return len(code) == 10 and not code.isdigit()


def _hash(code):
    return hmac.new(settings.SECRET_KEY.encode(), ("backup:" + normalise(code)).encode(), hashlib.sha256).hexdigest()


@transaction.atomic
def create(device):
    """Replace any existing codes with ten new ones and return them (the only time they're visible)."""
    device.backup_codes.all().delete()
    codes = []
    for _ in range(COUNT):
        raw = "".join(secrets.choice(ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    BackupCode.objects.bulk_create(BackupCode(device=device, code_hash=_hash(c)) for c in codes)
    return codes


def use(device, raw):
    """True if raw is one of the device's unused codes; the code is then used up."""
    if not looks_like_backup_code(raw):
        return False
    digest = _hash(raw)
    for bc in device.backup_codes.filter(used_at__isnull=True):
        if hmac.compare_digest(bc.code_hash, digest):
            # Conditional update, so the same code can't be used twice at the same moment.
            return BackupCode.objects.filter(pk=bc.pk, used_at__isnull=True).update(used_at=timezone.now()) == 1
    return False


def remaining(device):
    return device.backup_codes.filter(used_at__isnull=True).count() if device else 0
