"""Sign-in protection (pause logins after repeated failures) and limits on public form submissions."""

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def client_ip(request):
    """The visitor's address. Behind Nginx (DJANGO_BEHIND_PROXY=True) Nginx passes it in X-Real-IP,
    which it always overwrites, so visitors cannot fake it."""
    if settings.BEHIND_PROXY:
        real = request.META.get("HTTP_X_REAL_IP", "").strip()
        if real:
            return real[:64]
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def _keys(request, username):
    ip = client_ip(request)
    username = (username or "")[:150].lower()
    return f"login-ip:{ip}", f"login-user:{ip}:{username}"


def record_failure(request, username):
    logger.warning("Failed admin sign-in for username %r from %s", (username or "")[:150], client_ip(request))
    for key in _keys(request, username):
        cache.add(key, 0, settings.LOGIN_FAIL_WINDOW)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, settings.LOGIN_FAIL_WINDOW)


def login_blocked(request):
    ip_key, user_key = _keys(request, request.POST.get("username", ""))
    return (cache.get(ip_key, 0) >= settings.LOGIN_FAIL_LIMIT_IP
            or cache.get(user_key, 0) >= settings.LOGIN_FAIL_LIMIT_USER)


# ---------------------------------------------------------------------------
# Public forms: stop one connection flooding the inbox, the database or the disk (CV uploads).
# ---------------------------------------------------------------------------
FORM_LIMIT_PER_HOUR = 10
FORM_LIMIT_MESSAGE = ("We've received several submissions from your connection in the last hour. "
                      "Please try again later, or contact us by phone or email.")


def _form_key(request, form_name):
    return f"form-submissions:{form_name}:{client_ip(request)}"


def submission_allowed(request, form_name):
    allowed = cache.get(_form_key(request, form_name), 0) < getattr(settings, "FORM_LIMIT_PER_HOUR", FORM_LIMIT_PER_HOUR)
    if not allowed:
        logger.warning("Form submission limit reached for %s from %s", form_name, client_ip(request))
    return allowed


def record_submission(request, form_name):
    key = _form_key(request, form_name)
    cache.add(key, 0, 3600)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, 3600)
