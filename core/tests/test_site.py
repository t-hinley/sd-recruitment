import shutil
import tempfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import CandidateRegistration, ContactEnquiry, Job, VacancyEnquiry

MEDIA = tempfile.mkdtemp(prefix="sdr-test-media-")


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


def candidate_data(**extra):
    data = {
        "candidate-full_name": "Jane Citizen",
        "candidate-email": "jane@example.com",
        "candidate-phone": "0400 000 000",
        "candidate-location": "Perth WA",
        "candidate-position_sought": "Aged Care Worker",
        "candidate-industry": "healthcare",
        "candidate-experience": "Cert III in Individual Support",
        "candidate-support": ["jobs", "interview"],
        "candidate-consent": "on",
    }
    data.update(extra)
    return data


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ENQUIRY_NOTIFICATION_EMAILS=["team@example.com"],
    MEDIA_ROOT=MEDIA,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class SiteTests(TestCase):
    def test_pages_render_with_recommended_wording(self):
        for name, text in [
            ("core:home", "Connecting Talent with"),
            ("core:about", "Our recruitment approach"),
            ("core:employers", "Find the Right People for Your Business."),
            ("core:candidates", "Your Next Opportunity Starts Here."),
            ("core:contact", "Send us a message"),
            ("core:privacy", "Australian Privacy Principles"),
        ]:
            with self.subTest(name=name):
                r = self.client.get(reverse(name))
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, text)
                # Navigation from the recommendation: Home | About Us | Employers | Candidates | Contact Us
                for label in ("Home", "About Us", "Employers", "Candidates", "Contact Us"):
                    self.assertContains(r, f">{label}</a>")
                self.assertNotContains(r, "Jobseeker")  # 'Candidates', not 'Jobseekers'

    def test_home_has_both_pathways(self):
        r = self.client.get(reverse("core:home"))
        self.assertContains(r, "For Employers")
        self.assertContains(r, "Looking for the right people?")
        self.assertContains(r, "For Candidates")
        self.assertContains(r, "Looking for your next opportunity?")

    def test_employers_page_sections(self):
        r = self.client.get(reverse("core:employers"))
        for text in ("Save time", "Healthcare &amp; Aged Care", "Engineering, Construction &amp; Trades",
                     "Understand your vacancy", "Need help finding the right people?"):
            self.assertContains(r, text)
        self.assertGreaterEqual(r.content.decode().count('href="#vacancy"'), 1)

    def test_candidates_page_sections(self):
        r = self.client.get(reverse("core:candidates"))
        for text in ("Access to opportunities", "Resume Support", "Interview Preparation", "Career Counselling",
                     "Get resume support", "Prepare for an interview", "Explore career support",
                     "does not guarantee an interview", "No roles are advertised right now"):
            self.assertContains(r, text)

    def test_service_buttons_preselect_support(self):
        for service in ("resume", "interview", "career"):
            r = self.client.get(reverse("core:candidates") + f"?service={service}")
            self.assertContains(r, f'value="{service}"')
            self.assertRegex(r.content.decode(), rf'value="{service}"[^>]*checked')
        # No service: nothing pre-selected
        r = self.client.get(reverse("core:candidates"))
        self.assertNotRegex(r.content.decode(), r'name="candidate-support"[^>]*checked')

    def test_industry_link_preselects_vacancy_industry(self):
        r = self.client.get(reverse("core:employers") + "?industry=education")
        self.assertContains(r, '<option value="education" selected>')

    def test_jobs_listed_and_apply_preselects(self):
        job = Job.objects.create(title="Head Chef", industry="hospitality", location="Perth WA",
                                 summary="Lead a busy kitchen.")
        Job.objects.create(title="Hidden Role", industry="healthcare", location="Perth", summary="x",
                           is_published=False)
        r = self.client.get(reverse("core:candidates"))
        self.assertContains(r, "Head Chef")
        self.assertNotContains(r, "Hidden Role")
        self.assertNotContains(r, "No roles are advertised right now")
        r = self.client.get(reverse("core:candidates") + f"?job={job.pk}")
        self.assertContains(r, "Applying for <strong>Head Chef</strong>")
        self.client.post(reverse("core:candidates"), candidate_data(**{"candidate-job": job.pk}))
        self.assertEqual(CandidateRegistration.objects.get().job, job)

    def test_vacancy_saves_and_emails(self):
        r = self.client.post(reverse("core:employers"), {
            "vacancy-contact_name": "Sam Lee",
            "vacancy-company": "Cafe Co",
            "vacancy-email": "sam@cafe.com.au",
            "vacancy-phone": "0411 111 111",
            "vacancy-industry": "hospitality",
            "vacancy-position": "Restaurant Manager",
            "vacancy-positions_count": "1",
            "vacancy-employment_type": "full-time",
            "vacancy-location": "Fremantle WA",
            "vacancy-start_timeframe": "ASAP",
            "vacancy-details": "Busy venue.",
        })
        self.assertRedirects(r, reverse("core:employers") + "?sent=1#vacancy", fetch_redirect_response=False)
        v = VacancyEnquiry.objects.get()
        self.assertEqual(v.status, "new")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Restaurant Manager", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].reply_to, ["sam@cafe.com.au"])
        follow = self.client.get(reverse("core:employers") + "?sent=1")
        self.assertContains(follow, "Vacancy received")

    def test_candidate_registration_without_cv(self):
        r = self.client.post(reverse("core:candidates"), candidate_data())
        self.assertEqual(r.status_code, 302)
        c = CandidateRegistration.objects.get()
        self.assertEqual(c.support_list, ["Job opportunities", "Interview preparation"])
        self.assertFalse(c.resume)
        self.assertTrue(c.consent)
        self.assertIn("Support requested: Job opportunities, Interview preparation", mail.outbox[0].body)
        self.assertIn("not provided", mail.outbox[0].body)

    def test_candidate_registration_with_cv(self):
        cv = SimpleUploadedFile("Jane CV.pdf", b"%PDF-1.7 resume", content_type="application/pdf")
        r = self.client.post(reverse("core:candidates"), candidate_data(**{"candidate-resume": cv}))
        self.assertEqual(r.status_code, 302)
        c = CandidateRegistration.objects.get()
        self.assertEqual(c.resume_name, "Jane CV.pdf")
        self.assertTrue(c.resume.name.endswith(".pdf"))
        self.assertNotIn("Jane", c.resume.name)
        self.assertEqual(mail.outbox[0].attachments, [])  # CVs stay on the server, not in email

    def test_candidate_requires_consent_and_support(self):
        data = candidate_data()
        del data["candidate-consent"]
        del data["candidate-support"]
        r = self.client.post(reverse("core:candidates"), data)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Please tick this box so we can contact you.")
        self.assertContains(r, "Please choose at least one option.")
        self.assertFalse(CandidateRegistration.objects.exists())

    def test_cv_rejects_wrong_type_and_fake_documents(self):
        bad = SimpleUploadedFile("cv.exe", b"MZ...", content_type="application/octet-stream")
        r = self.client.post(reverse("core:candidates"), candidate_data(**{"candidate-resume": bad}))
        self.assertContains(r, "Please upload a PDF or Word document")
        fake = SimpleUploadedFile("cv.pdf", b"<html>not a pdf", content_type="application/pdf")
        r = self.client.post(reverse("core:candidates"), candidate_data(**{"candidate-resume": fake}))
        self.assertContains(r, "doesn&#x27;t look like a valid document")
        self.assertFalse(CandidateRegistration.objects.exists())

    @override_settings(RESUME_MAX_MB=1)
    def test_cv_size_limit(self):
        big = SimpleUploadedFile("cv.pdf", b"%PDF" + b"0" * (1024 * 1024 + 10), content_type="application/pdf")
        r = self.client.post(reverse("core:candidates"), candidate_data(**{"candidate-resume": big}))
        self.assertContains(r, "The file is too large")

    def test_contact_enquiry_saves(self):
        r = self.client.post(reverse("core:contact"), {
            "contact-name": "Alex", "contact-email": "alex@example.com", "contact-phone": "",
            "contact-enquirer_type": "employer", "contact-message": "Do you recruit in Bunbury?",
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ContactEnquiry.objects.get().enquirer_type, "employer")
        self.assertEqual(len(mail.outbox), 1)

    def test_honeypot_blocks_bots(self):
        r = self.client.post(reverse("core:contact"), {
            "contact-name": "Bot", "contact-email": "bot@example.com", "contact-enquirer_type": "other",
            "contact-message": "spam", "contact-website": "http://spam.example",
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ContactEnquiry.objects.exists())

    @override_settings(ENQUIRY_NOTIFICATION_EMAILS=[])
    def test_no_inbox_configured_still_saves(self):
        self.client.post(reverse("core:candidates"), candidate_data())
        self.assertTrue(CandidateRegistration.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_robots_and_sitemap(self):
        self.assertContains(self.client.get(reverse("robots_txt")), "Disallow: /admin/")
        r = self.client.get(reverse("sitemap"))
        self.assertContains(r, "/employers/")
        self.assertContains(r, "/candidates/")
