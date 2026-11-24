import shutil
import tempfile

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import CandidateRegistration
from core.tests.test_site import candidate_data

MEDIA = tempfile.mkdtemp(prefix="sdr-test-media-")
STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


@override_settings(STORAGES=STATIC, MEDIA_ROOT=MEDIA, ENQUIRY_NOTIFICATION_EMAILS=["team@example.com"],
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CareerServicesTests(TestCase):
    def test_page_shows_client_content_and_prices(self):
        r = self.client.get(reverse("core:career_services"))
        self.assertEqual(r.status_code, 200)
        for text in ("Create My Resume", "Student Resume", "$50", "For applicants aged 19 years and below.",
                     "Basic Resume", "$95", "Professional Resume", "$200", "Executive Resume", "$350",
                     "Selection Criteria Writing", "per criterion", "Ready to take the next step?", "Get Started",
                     "Interview Preparation", "45-minute one-on-one coaching session", "Book My Interview Session",
                     "Career Counselling", "First consultation", "Follow-up session", "$65",
                     "Book a Free Consultation", "include GST"):
            self.assertContains(r, text)
        self.assertNotContains(r, "<form")  # no separate form: buttons go to the candidate form

    def test_buttons_open_candidate_form_with_service(self):
        r = self.client.get(reverse("core:career_services"))
        reg = reverse("core:candidates")
        for href in (f"{reg}?service=resume#register", f"{reg}?service=interview#register",
                     f"{reg}?service=career#register", f"{reg}?package=executive#register",
                     f"{reg}?package=criteria#register"):
            self.assertContains(r, f'href="{href}"')

    def test_candidates_cards_link_to_services(self):
        r = self.client.get(reverse("core:candidates"))
        url = reverse("core:career_services")
        for frag, label, price in (("resume", "Create My Resume", "From $50"),
                                   ("interview", "Book My Interview Session", "$95 · 45-minute session"),
                                   ("counselling", "Book a Free Consultation", "First 15 minutes free")):
            self.assertContains(r, f'href="{url}#{frag}"')
            self.assertContains(r, label)
            self.assertContains(r, price)

    def test_package_link_preselects_resume_support_and_package(self):
        r = self.client.get(reverse("core:candidates") + "?package=executive")
        self.assertRegex(r.content.decode(), r'value="resume"[^>]*checked')
        self.assertContains(r, '<option value="executive" selected>')

    def test_resume_support_needs_package_and_criteria_count(self):
        url = reverse("core:candidates")
        r = self.client.post(url, candidate_data(**{"candidate-support": ["resume"]}))
        self.assertContains(r, "Please choose a resume package.")
        r = self.client.post(url, candidate_data(**{"candidate-support": ["resume"],
                                                    "candidate-resume_package": "criteria"}))
        self.assertContains(r, "Please tell us how many selection criteria you need.")
        self.assertFalse(CandidateRegistration.objects.exists())
        self.client.post(url, candidate_data(**{"candidate-support": ["resume", "interview"],
                                                "candidate-resume_package": "criteria",
                                                "candidate-criteria_count": "4",
                                                "candidate-preferred_times": "Weekday evenings"}))
        c = CandidateRegistration.objects.get()
        self.assertEqual(c.package_summary, "Selection Criteria Writing – $35 per criterion × 4")
        self.assertEqual(c.preferred_times, "Weekday evenings")
        body = mail.outbox[0].body
        self.assertIn("Resume package: Selection Criteria Writing – $35 per criterion × 4", body)
        self.assertIn("Preferred days and times: Weekday evenings", body)

    def test_extras_dropped_when_service_not_chosen(self):
        self.client.post(reverse("core:candidates"), candidate_data(**{
            "candidate-support": ["jobs"], "candidate-resume_package": "executive",
            "candidate-criteria_count": "3", "candidate-preferred_times": "Mondays"}))
        c = CandidateRegistration.objects.get()
        self.assertEqual((c.resume_package, c.criteria_count, c.preferred_times), ("", None, ""))

    def test_admin_and_report_show_service_details(self):
        self.client.post(reverse("core:candidates"), candidate_data(**{
            "candidate-support": ["resume"], "candidate-resume_package": "professional"}))
        c = CandidateRegistration.objects.get()
        admin = User.objects.create_superuser("boss", "boss@example.com", "a-strong-pass-123")
        self.client.force_login(admin)
        r = self.client.get(reverse("admin:core_candidateregistration_change", args=[c.pk]))
        self.assertContains(r, "Professional Resume – $200")
        csv = self.client.get(reverse("admin:reports"), {"report": "candidates"}).content.decode()
        self.assertIn("Resume package", csv)
        self.assertIn("Professional Resume – $200", csv)
