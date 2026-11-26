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

from . import security, totp
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


def _finish(request, user, data):
    request.session.pop(PENDING, None)
    auth_login(request, user, backend=data["backend"])
    nxt = data.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    return redirect("admin:index")


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
        step = totp.match(device.secret, request.POST.get("code", "")) if form.is_valid() else None
        if step is not None and step > device.last_used_step:
            AuthenticatorDevice.objects.filter(pk=device.pk).update(last_used_step=step)
            return _finish(request, user, data)
        response = _wrong_code(request, user, data)
        if response:
            return response
        error = "That code didn't work. Check the time on your phone and enter the newest code."
    return render(request, "admin/two_step_verify.html", {
        **site.each_context(request), "site_name": ISSUER, "error": error,
        "account": user.email or user.get_username()})


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
            messages.success(request, "Two-step login is set up.", extra_tags="toast")
            return _finish(request, user, data)
        response = _wrong_code(request, user, data)
        if response:
            return response
        error = "That code didn't work. Make sure you scanned this QR code, then enter the newest code."
    uri = totp.provisioning_uri(device.secret, account, ISSUER)
    return render(request, "admin/two_step_setup.html", {
        **site.each_context(request), "site_name": ISSUER, "error": error, "account": account,
        "qr_svg": totp.qr_svg(uri), "secret": totp.grouped(device.secret)})
