import shutil
import tempfile

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import ServiceRequest

MEDIA = tempfile.mkdtemp(prefix="sdr-test-media-")
STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


def data(**extra):
    d = {
        "service-service": "interview",
        "service-full_name": "Sam Citizen",
        "service-email": "sam@example.com",
        "service-phone": "0400 000 000",
        "service-role": "Registered Nurse",
        "service-preferred_times": "Weekday evenings",
        "service-details": "Interview next Friday",
        "service-consent": "on",
    }
    d.update(extra)
    return d


@override_settings(STORAGES=STATIC, MEDIA_ROOT=MEDIA, ENQUIRY_NOTIFICATION_EMAILS=["team@example.com"],
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CareerServicesPageTests(TestCase):
    def test_page_shows_client_content_and_prices(self):
        r = self.client.get(reverse("core:career_services"))
        self.assertEqual(r.status_code, 200)
        for text in ("Create My Resume", "Student Resume", "$50", "For applicants aged 19 years and below.",
                     "Basic Resume", "$95", "Professional Resume", "$200", "Executive Resume", "$350",
                     "Selection Criteria Writing", "per criterion", "Ready to take the next step?", "Get Started",
                     "Interview Preparation", "45-minute one-on-one coaching session", "Book My Interview Session",
                     "Career Counselling", "First consultation", "15 minutes", "Follow-up session", "30 minutes",
                     "$65", "Book a Free Consultation", "include GST"):
            self.assertContains(r, text)

    def test_candidates_cards_link_to_services(self):
        r = self.client.get(reverse("core:candidates"))
        url = reverse("core:career_services")
        for frag, label, price in (("resume", "Create My Resume", "From $50"),
                                   ("interview", "Book My Interview Session", "$95 · 45-minute session"),
                                   ("counselling", "Book a Free Consultation", "First 15 minutes free")):
            self.assertContains(r, f'href="{url}#{frag}"')
            self.assertContains(r, label)
            self.assertContains(r, price)
        self.assertContains(self.client.get(reverse("core:home")), f'href="{url}"')  # footer link

    def test_query_preselects_service_and_package(self):
        r = self.client.get(reverse("core:career_services") + "?service=resume&package=executive")
        self.assertRegex(r.content.decode(), r'value="resume"[^>]*checked')
        self.assertContains(r, '<option value="executive" selected>')
        r = self.client.get(reverse("core:career_services") + "?service=career")
        self.assertRegex(r.content.decode(), r'value="career"[^>]*checked')

    def test_interview_request_saves_and_emails(self):
        r = self.client.post(reverse("core:career_services"), data())
        self.assertRedirects(r, reverse("core:career_services") + "?sent=1#request", fetch_redirect_response=False)
        obj = ServiceRequest.objects.get()
        self.assertEqual((obj.service, obj.package, obj.preferred_times), ("interview", "", "Weekday evenings"))
        self.assertIn("New service request: Interview preparation – Sam Citizen", mail.outbox[0].subject)
        self.assertContains(self.client.get(reverse("core:career_services") + "?sent=1"), "Request received")

    def test_resume_needs_package_and_criteria_count(self):
        r = self.client.post(reverse("core:career_services"), data(**{"service-service": "resume"}))
        self.assertContains(r, "Please choose a resume package.")
        r = self.client.post(reverse("core:career_services"),
                             data(**{"service-service": "resume", "service-package": "criteria"}))
        self.assertContains(r, "Please tell us how many selection criteria you need.")
        self.assertFalse(ServiceRequest.objects.exists())
        cv = SimpleUploadedFile("old cv.pdf", b"%PDF-1.4 cv", content_type="application/pdf")
        self.client.post(reverse("core:career_services"), data(**{
            "service-service": "resume", "service-package": "criteria", "service-criteria_count": "4",
            "service-resume": cv}))
        obj = ServiceRequest.objects.get()
        self.assertEqual(obj.summary, "Resume writing · Selection Criteria Writing – $35 per criterion × 4")
        self.assertEqual(obj.preferred_times, "")  # not needed for resume writing
        self.assertEqual(obj.resume_name, "old cv.pdf")
        self.assertNotIn("old", obj.resume.name)

    def test_package_dropped_for_other_services(self):
        self.client.post(reverse("core:career_services"), data(**{
            "service-service": "career", "service-package": "executive", "service-criteria_count": "3"}))
        obj = ServiceRequest.objects.get()
        self.assertEqual((obj.package, obj.criteria_count), ("", None))

    def test_consent_required_and_bad_file_rejected(self):
        d = data()
        del d["service-consent"]
        self.assertContains(self.client.post(reverse("core:career_services"), d),
                            "Please tick this box so we can contact you.")
        bad = SimpleUploadedFile("cv.pdf", b"<html>", content_type="application/pdf")
        self.assertContains(self.client.post(reverse("core:career_services"), data(**{"service-resume": bad})),
                            "doesn&#x27;t look like a valid document")
        self.assertFalse(ServiceRequest.objects.exists())


@override_settings(STORAGES=STATIC, MEDIA_ROOT=MEDIA)
class ServiceRequestAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("boss", "boss@example.com", "a-strong-pass-123")
        self.staff = User.objects.create_user("helper", "h@example.com", "a-strong-pass-123", is_staff=True)
        self.staff.groups.add(Group.objects.get(name="Staff"))
        self.client.post(reverse("core:career_services"), data(**{
            "service-resume": SimpleUploadedFile("my cv.pdf", b"%PDF-1.4 x", content_type="application/pdf")}))
        self.obj = ServiceRequest.objects.get()

    def test_staff_can_view_and_download_but_not_add_or_delete(self):
        self.client.force_login(self.staff)
        change = self.client.get(reverse("admin:core_servicerequest_change", args=[self.obj.pk]))
        self.assertContains(change, "Interview preparation")
        dl = reverse("admin:service_resume_download", args=[self.obj.pk])
        self.assertContains(change, dl)
        r = self.client.get(dl)
        self.assertEqual(r.status_code, 200)
        self.assertIn('filename="Resume-Sam-Citizen.pdf"', r["Content-Disposition"])
        self.assertEqual(self.client.get(reverse("admin:core_servicerequest_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:core_servicerequest_delete", args=[self.obj.pk])).status_code, 403)

    def test_dashboard_and_reports(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, 'aria-label="New service requests: 1"')
        self.assertContains(r, "Service requests")  # sidebar
        csv = self.client.get(reverse("admin:reports"), {"report": "services"}).content.decode()
        self.assertIn("Sam Citizen", csv)
        self.assertIn("Weekday evenings", csv)
        pdf = self.client.get(reverse("admin:reports"), {"report": "services", "format": "pdf"})
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_deleting_removes_file(self):
        storage, name = self.obj.resume.storage, self.obj.resume.name
        ServiceRequest.objects.all().delete()
        self.assertFalse(storage.exists(name))
