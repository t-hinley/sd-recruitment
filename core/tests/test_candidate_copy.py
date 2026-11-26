from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import CandidateRegistration
from core.tests.test_site import MEDIA, candidate_data

STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", STORAGES=STATIC, MEDIA_ROOT=MEDIA,
                   ENQUIRY_NOTIFICATION_EMAILS=["team@example.com"], DEFAULT_FROM_EMAIL="SD Recruitment <web@example.com>")
class CandidateCopyTests(TestCase):
    def setUp(self):
        cache.clear()

    def _copy(self):
        copies = [m for m in mail.outbox if m.to == ["jane@example.com"]]
        self.assertEqual(len(copies), 1)
        return copies[0]

    def test_candidate_gets_copy_and_admin_still_notified(self):
        cv = SimpleUploadedFile("Jane CV.pdf", b"%PDF-1.4 x", content_type="application/pdf")
        r = self.client.post(reverse("core:candidates"),
                             candidate_data(**{"candidate-resume": cv, "candidate-support": ["jobs", "resume"],
                                               "candidate-resume_package": "basic"}))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(mail.outbox), 2)
        admin = [m for m in mail.outbox if m.to == ["team@example.com"]][0]
        self.assertIn("New candidate: Jane Citizen", admin.subject)
        copy = self._copy()
        self.assertEqual(copy.subject, "We've received your registration – SD Recruitment")
        self.assertEqual(copy.reply_to, ["admin@sd-recruitment.com"])
        self.assertEqual(copy.from_email, "SD Recruitment <web@example.com>")
        for text in ("Hi Jane,", "Full name: Jane Citizen", "Visa type: Student Visa (Subclass 500)",
                     "Industry / job category: Aged Care & Disability", "Employment type: Casual, Part - Time",
                     "What we can help with: Job opportunities, Resume support",
                     "Resume package: Basic Resume – $95", "Resume / CV: Jane CV.pdf",
                     "does not guarantee an interview"):
            self.assertIn(text, copy.body)
        self.assertEqual(copy.attachments, [])  # the CV itself is never emailed
        self.assertNotIn("just reply to this email", copy.body)
        self.assertNotIn("You received this email because", copy.body)
        self.assertTrue(copy.body.rstrip().endswith(
            "Kind regards,\nSD Recruitment\nSuite 20, 25 Walters Drive, Osborne Park 6017, WA"))
        self.assertNotIn("0497 389 693", copy.body)

    def test_copy_sent_even_without_admin_inbox(self):
        with self.settings(ENQUIRY_NOTIFICATION_EMAILS=[]):
            self.client.post(reverse("core:candidates"), candidate_data())
        self.assertEqual([m.to for m in mail.outbox], [["jane@example.com"]])

    @override_settings(CANDIDATE_CONFIRMATION_EMAILS=False)
    def test_can_be_switched_off(self):
        self.client.post(reverse("core:candidates"), candidate_data())
        self.assertEqual([m.to for m in mail.outbox], [["team@example.com"]])

    def test_limit_per_address_per_day(self):
        for _ in range(5):
            self.client.post(reverse("core:candidates"), candidate_data(), REMOTE_ADDR=f"10.0.0.{_}")
        self.assertEqual(CandidateRegistration.objects.count(), 5)  # all saved
        self.assertEqual(len([m for m in mail.outbox if m.to == ["jane@example.com"]]), 3)
        self.assertEqual(len([m for m in mail.outbox if m.to == ["team@example.com"]]), 5)  # admin always told

    def test_limit_per_connection_per_hour(self):
        for n in range(7):
            self.client.post(reverse("core:candidates"), candidate_data(**{"candidate-email": f"p{n}@example.com"}))
        self.assertEqual(len([m for m in mail.outbox if m.to != ["team@example.com"]]), 5)

    def test_success_message_mentions_copy(self):
        r = self.client.post(reverse("core:candidates"), candidate_data(), follow=True)
        self.assertContains(r, "emailed you a copy")
