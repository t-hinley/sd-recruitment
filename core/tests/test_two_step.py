import re
import time
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from core import totp
from core.models import AuthenticatorDevice

STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
PW = "a-strong-pass-123"


class TotpTests(TestCase):
    def test_rfc6238_vectors_and_window(self):
        s = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.assertEqual(totp.code_at(s, 59 // 30), "287082")
        self.assertEqual(totp.match(s, "287 082", now=59), 1)
        self.assertEqual(totp.match(s, "287082", now=59 + 30), 1)  # one step late still OK
        self.assertIsNone(totp.match(s, "287082", now=59 + 90))   # too late
        self.assertIsNone(totp.match(s, "287082", last_used_step=1, now=59))  # no replay
        self.assertIsNone(totp.match(s, "abc"))


@override_settings(STORAGES=STATIC)
class EmailLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.boss = User.objects.create_superuser("boss", "Boss@Example.com", PW)

    def test_login_with_username_or_email(self):
        self.assertTrue(self.client.login(username="boss", password=PW))
        self.client.logout()
        r = self.client.post(reverse("admin:login"), {"username": "boss@example.com", "password": PW})
        self.assertRedirects(r, reverse("admin:index"), fetch_redirect_response=False)

    def test_wrong_password_and_shared_email(self):
        r = self.client.post(reverse("admin:login"), {"username": "boss@example.com", "password": "nope"})
        self.assertContains(r, "username or email address and password")
        User.objects.create_user("twin", "boss@example.com", PW, is_staff=True)
        self.assertFalse(self.client.login(username="boss@example.com", password=PW))  # ambiguous email
        self.assertTrue(self.client.login(username="twin", password=PW))

    def test_login_page_wording(self):
        r = self.client.get(reverse("admin:login"))
        self.assertContains(r, "Username or email")

    def test_lockout_counts_username_and_email_together(self):
        for i in range(5):
            ident = "boss" if i % 2 else "boss@example.com"
            self.client.post(reverse("admin:login"), {"username": ident, "password": "wrong"})
        r = self.client.post(reverse("admin:login"), {"username": "boss", "password": PW})
        self.assertEqual(r.status_code, 429)


@override_settings(STORAGES=STATIC, ADMIN_TWO_FACTOR=True)
class TwoStepTests(TestCase):
    def setUp(self):
        cache.clear()
        self.boss = User.objects.create_superuser("boss", "boss@example.com", PW)

    def _password(self, ident="boss", nxt=None):
        data = {"username": ident, "password": PW}
        url = reverse("admin:login")
        if nxt:
            data["next"] = nxt
            url += "?next=" + nxt
        return self.client.post(url, data)

    def _secret_from_setup(self):
        r = self.client.get(reverse("admin:two_step_setup"))
        self.assertContains(r, "<svg")
        return re.search(r"Key: <code>([A-Z2-7 ]+)</code>", r.content.decode()).group(1).replace(" ", "")

    def test_first_sign_in_sets_up_app(self):
        r = self._password("boss@example.com")
        self.assertRedirects(r, reverse("admin:two_step_setup"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)  # not signed in yet
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)
        secret = self._secret_from_setup()
        r = self.client.post(reverse("admin:two_step_setup"), {"code": "000000"})
        self.assertContains(r, "didn&#x27;t work")
        r = self.client.post(reverse("admin:two_step_setup"), {"code": totp.code_at(secret, int(time.time() // 30))})
        self.assertRedirects(r, reverse("admin:index"), fetch_redirect_response=False)
        self.assertTrue(AuthenticatorDevice.objects.get(user=self.boss).confirmed)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def _with_app(self):
        dev = AuthenticatorDevice.objects.create(user=self.boss, secret=totp.new_secret(), confirmed=True)
        return dev

    def test_every_sign_in_needs_code_and_codes_cant_be_reused(self):
        dev = self._with_app()
        r = self._password()
        self.assertRedirects(r, reverse("admin:two_step"), fetch_redirect_response=False)
        code = totp.code_at(dev.secret, int(time.time() // 30))
        r = self.client.post(reverse("admin:two_step"), {"code": code})
        self.assertRedirects(r, reverse("admin:index"), fetch_redirect_response=False)
        self.client.logout()
        self._password()
        r = self.client.post(reverse("admin:two_step"), {"code": code})  # same code again
        self.assertContains(r, "didn&#x27;t work")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_too_many_wrong_codes_back_to_login(self):
        self._with_app()
        self._password()
        for _ in range(4):
            self.assertEqual(self.client.post(reverse("admin:two_step"), {"code": "000000"}).status_code, 200)
        r = self.client.post(reverse("admin:two_step"), {"code": "000000"})
        self.assertRedirects(r, reverse("admin:login"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("admin:two_step")).status_code, 302)

    def test_code_step_times_out(self):
        dev = self._with_app()
        self._password()
        with mock.patch("core.two_step.time.time", return_value=time.time() + 11 * 60):
            r = self.client.post(reverse("admin:two_step"), {"code": totp.code_at(dev.secret, int(time.time() // 30))})
        self.assertRedirects(r, reverse("admin:login"), fetch_redirect_response=False)

    def test_code_pages_need_password_first(self):
        for name in ("admin:two_step", "admin:two_step_setup"):
            self.assertRedirects(self.client.get(reverse(name)), reverse("admin:login"), fetch_redirect_response=False)

    def test_next_is_kept_but_only_if_safe(self):
        dev = self._with_app()
        self._password(nxt="/admin/core/candidateregistration/")
        r = self.client.post(reverse("admin:two_step"), {"code": totp.code_at(dev.secret, int(time.time() // 30))})
        self.assertRedirects(r, "/admin/core/candidateregistration/", fetch_redirect_response=False)

    def test_reset_command_and_admin_page(self):
        self._with_app()
        out = StringIO()
        call_command("reset_two_step", "boss@example.com", stdout=out)
        self.assertIn("reset for boss", out.getvalue())
        self.assertFalse(AuthenticatorDevice.objects.exists())
        r = self._password()
        self.assertRedirects(r, reverse("admin:two_step_setup"), fetch_redirect_response=False)

    def test_staff_cant_see_authenticator_list(self):
        from django.contrib.auth.models import Group
        staff = User.objects.create_user("helper", "h@example.com", PW, is_staff=True)
        staff.groups.add(Group.objects.get(name="Staff"))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("admin:core_authenticatordevice_changelist")).status_code, 403)
        self.client.force_login(self.boss)
        self.assertEqual(self.client.get(reverse("admin:core_authenticatordevice_changelist")).status_code, 200)
