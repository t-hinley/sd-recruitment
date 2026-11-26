"""Admin sign-in: username or email + password, then (when ADMIN_TWO_FACTOR is on) a 6-digit code from an
authenticator app. People who haven't set one up yet are shown a QR code to add it first.

After the password is accepted the person is NOT signed in yet: their id waits in the session for up to
10 minutes until a valid code is entered.
"""

import time

from django import forms
from django.contrib import messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from . import backup_codes, security, totp
from .models import AuthenticatorDevice

PENDING = "two_step_pending"
PENDING_SECONDS = 10 * 60
MAX_CODE_ATTEMPTS = 5
ISSUER = "SD Recruitment"


class AdminLoginForm(AdminAuthenticationForm):
    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_login": "Please enter a correct username or email address and password for a staff account. "
                         "Both fields may be case-sensitive.",
    }


class CodeForm(forms.Form):
    code = forms.CharField(max_length=12)


class TwoStepLoginView(LoginView):
    """Password accepted: hold the person in the session and ask for their code instead of signing in."""

    def form_valid(self, form):
        user = form.get_user()
        self.request.session.cycle_key()
        self.request.session[PENDING] = {
            "uid": user.pk, "backend": user.backend, "at": int(time.time()), "fails": 0,
            "next": self.get_redirect_url() or "",
        }
        has_app = AuthenticatorDevice.objects.filter(user=user, confirmed=True).exists()
        return redirect("admin:two_step" if has_app else "admin:two_step_setup")


def _pending(request):
    data = request.session.get(PENDING)
    if not data or time.time() - data.get("at", 0) > PENDING_SECONDS:
        request.session.pop(PENDING, None)
        return None, None
    user = get_user_model()._default_manager.filter(pk=data["uid"], is_active=True, is_staff=True).first()
    return (data, user) if user else (None, None)


def _safe_next(request, nxt):
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return ""


def _finish(request, user, data, show_codes=None):
    request.session.pop(PENDING, None)
    auth_login(request, user, backend=data["backend"])
    nxt = _safe_next(request, data.get("next") or "")
    if show_codes:
        request.session[backup_codes.SESSION_KEY] = {"codes": show_codes, "next": nxt}
        return redirect("admin:two_step_codes")
    return redirect(nxt or "admin:index")


def _wrong_code(request, user, data):
    data["fails"] = data.get("fails", 0) + 1
    request.session[PENDING] = data
    security.record_failure(request, user.get_username())
    if data["fails"] >= MAX_CODE_ATTEMPTS:
        request.session.pop(PENDING, None)
        messages.error(request, "Too many incorrect codes. Please sign in again.")
        return redirect("admin:login")
    return None


def _start_again(request):
    messages.error(request, "Your sign-in timed out. Please sign in again.")
    return redirect("admin:login")


def verify(request, site):
    data, user = _pending(request)
    if not user:
        return _start_again(request)
    device = AuthenticatorDevice.objects.filter(user=user, confirmed=True).first()
    if not device:
        return redirect("admin:two_step_setup")
    error = ""
    if request.method == "POST":
        form = CodeForm(request.POST)
        raw = request.POST.get("code", "")
        if form.is_valid() and backup_codes.looks_like_backup_code(raw):
            if backup_codes.use(device, raw):
                left = backup_codes.remaining(device)
                security.logger.warning("Backup code used to sign in by %s (%d left)", user.get_username(), left)
                messages.warning(request, f"You signed in with a backup code. {left} left. Lost your phone? Go to "
                                          f"Profile and choose 'Set up on a new phone'."
                                 + (" Your backup codes are running out: create new ones on your Profile."
                                    if left <= 3 else ""))
                return _finish(request, user, data)
        else:
            step = totp.match(device.secret, raw) if form.is_valid() else None
            if step is not None and step > device.last_used_step:
                AuthenticatorDevice.objects.filter(pk=device.pk).update(last_used_step=step)
                return _finish(request, user, data)
        response = _wrong_code(request, user, data)
        if response:
            return response
        error = ("That backup code didn't work. Each code works only once." if backup_mode(request) else
                 "That code didn't work. Check the time on your phone and enter the newest code.")
    return render(request, "admin/two_step_verify.html", {
        **site.each_context(request), "site_name": ISSUER, "error": error, "backup": backup_mode(request),
        "account": user.email or user.get_username()})


def backup_mode(request):
    return request.GET.get("backup") == "1" or request.POST.get("mode") == "backup"


def setup(request, site):
    data, user = _pending(request)
    if not user:
        return _start_again(request)
    device, _ = AuthenticatorDevice.objects.get_or_create(user=user, defaults={"secret": totp.new_secret()})
    if device.confirmed:
        return redirect("admin:two_step")
    account = user.email or user.get_username()
    error = ""
    if request.method == "POST":
        step = totp.match(device.secret, request.POST.get("code", ""))
        if step is not None:
            AuthenticatorDevice.objects.filter(pk=device.pk).update(
                confirmed=True, confirmed_at=timezone.now(), last_used_step=step)
            return _finish(request, user, data, show_codes=backup_codes.create(device))
        response = _wrong_code(request, user, data)
        if response:
            return response
        error = "That code didn't work. Make sure you scanned this QR code, then enter the newest code."
    uri = totp.provisioning_uri(device.secret, account, ISSUER)
    return render(request, "admin/two_step_setup.html", {
        **site.each_context(request), "site_name": ISSUER, "error": error, "account": account,
        "qr_svg": totp.qr_svg(uri), "secret": totp.grouped(device.secret)})


# ---- Backup codes and new phone (signed-in pages, wrapped in admin_view) ----------------------------------
def codes(request, site):
    """Shows newly created backup codes, once."""
    shown = request.session.pop(backup_codes.SESSION_KEY, None)
    if not shown:
        messages.info(request, "Backup codes are only shown once. You can create new ones here.")
        return redirect("admin:profile")
    return render(request, "admin/two_step_codes.html", {
        **site.each_context(request), "site_name": ISSUER, "codes": shown["codes"],
        "account": request.user.email or request.user.get_username(),
        "next": _safe_next(request, shown.get("next") or "")})


def new_codes(request, site):
    if request.method != "POST":
        return redirect("admin:profile")
    device = AuthenticatorDevice.objects.filter(user=request.user, confirmed=True).first()
    if not device:
        messages.error(request, "Set up your authenticator app first.")
        return redirect("admin:profile")
    request.session[backup_codes.SESSION_KEY] = {"codes": backup_codes.create(device), "next": ""}
    security.logger.warning("New backup codes created by %s", request.user.get_username())
    return redirect("admin:two_step_codes")


def new_phone(request, site):
    """Remove your own authenticator app (and its backup codes), sign out, and set up again at sign-in."""
    from django.contrib.auth import logout as auth_logout
    if request.method != "POST":
        return redirect("admin:profile")
    AuthenticatorDevice.objects.filter(user=request.user).delete()
    security.logger.warning("%s removed their authenticator app to set up a new phone", request.user.get_username())
    auth_logout(request)
    messages.success(request, "Your old phone has been removed. Sign in again to set up your new phone.")
    return redirect("admin:login")
