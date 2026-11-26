from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import CandidateRegistration, ContactEnquiry, VacancyEnquiry
from core.tests.test_site import MEDIA, VACANCY, candidate_data

STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
CONTACT = {"contact-name": "Alex", "contact-email": "alex@example.com", "contact-message": "Hello"}


@override_settings(FORM_LIMIT_PER_HOUR=3, STORAGES=STATIC, MEDIA_ROOT=MEDIA,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FormLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def _flood(self, url, data, model):
        codes = [self.client.post(url, data).status_code for _ in range(5)]
        self.assertEqual(codes, [302, 302, 302, 429, 429])
        self.assertEqual(model.objects.count(), 3)

    def test_each_form_is_limited(self):
        self._flood(reverse("core:employers"), VACANCY, VacancyEnquiry)
        self._flood(reverse("core:candidates"), candidate_data(), CandidateRegistration)
        self._flood(reverse("core:contact"), CONTACT, ContactEnquiry)

    def test_limit_message_shown_and_other_connections_unaffected(self):
        for _ in range(3):
            self.client.post(reverse("core:contact"), CONTACT)
        r = self.client.post(reverse("core:contact"), CONTACT)
        self.assertContains(r, "several submissions from your connection", status_code=429)
        r = self.client.post(reverse("core:contact"), CONTACT, REMOTE_ADDR="10.9.9.9")
        self.assertEqual(r.status_code, 302)

    def test_invalid_submissions_dont_count(self):
        for _ in range(5):
            self.client.post(reverse("core:contact"), {"contact-name": ""})
        self.assertEqual(self.client.post(reverse("core:contact"), CONTACT).status_code, 302)


class LoginLoggingTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_superuser("boss", "boss@example.com", "a-strong-pass-123")

    def test_failed_sign_in_and_pause_are_logged(self):
        with self.assertLogs("core.security", level="WARNING") as logs:
            for _ in range(6):
                self.client.post(reverse("admin:login"), {"username": "boss", "password": "wrong"})
        text = "\n".join(logs.output)
        self.assertIn("Failed admin sign-in for username 'boss'", text)
        self.assertIn("Admin sign-in paused", text)

    def test_login_redirects_to_admin_not_missing_page(self):
        r = self.client.post(reverse("admin:login") + "?next=//evil.com",
                             {"username": "boss", "password": "a-strong-pass-123", "next": "//evil.com"})
        self.assertRedirects(r, reverse("admin:index"), fetch_redirect_response=False)


class SettingsSafetyTests(TestCase):
    def test_live_site_refuses_development_key(self):
        import os, subprocess, sys
        # Set explicitly, so a local .env (which only fills in missing values) can't change the result.
        env = {**os.environ, "DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "django-insecure-placeholder"}
        out = subprocess.run([sys.executable, "-c", "import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()"],
                             env=env, capture_output=True, text=True, cwd=os.getcwd())
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Set DJANGO_SECRET_KEY", out.stderr)
