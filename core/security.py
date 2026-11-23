"""Sign-in protection: pause logins after repeated failures from one address or username."""

from django.conf import settings
from django.core.cache import cache


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
