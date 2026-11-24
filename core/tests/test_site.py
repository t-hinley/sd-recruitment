import shutil
import tempfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import CandidateRegistration, ContactEnquiry, VacancyEnquiry

MEDIA = tempfile.mkdtemp(prefix="sdr-test-media-")


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


VACANCY = {
    "vacancy-company": "Cafe Co",
    "vacancy-industry": "Hospitality",
    "vacancy-contact_name": "Sam Lee",
    "vacancy-phone": "0411 111 111",
    "vacancy-email": "sam@cafe.com.au",
    "vacancy-position": "Restaurant Manager",
    "vacancy-employment_types": ["Full Time", "Casual"],
    "vacancy-positions_count": "2-5",
    "vacancy-location": "Fremantle WA",
    "vacancy-details": "Busy venue.",
    "vacancy-consent": "on",
}


def candidate_data(**extra):
    data = {
        "candidate-full_name": "Jane Citizen",
        "candidate-email": "jane@example.com",
        "candidate-phone": "0400 000 000",
        "candidate-location": "Perth WA",
        "candidate-visa_type": "Student Visa (Subclass 500)",
        "candidate-preferred_location": "Perth metro",
        "candidate-industry": "Aged Care & Disability",
        "candidate-position_sought": "Support Worker",
        "candidate-employment_types": ["Casual", "Part - Time"],
        "candidate-experience": "1–3 Years",
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
            ("core:home", "Connecting Business."),
            ("core:about", "Our recruitment approach"),
            ("core:employers", "Find the Right People for Your Business."),
            ("core:candidates", "Your Next Opportunity Starts Here."),
            ("core:contact", "General enquiry"),
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

    def test_home_hero(self):
        r = self.client.get(reverse("core:home"))
        self.assertContains(r, 'Connecting Business. <span class="text-orange">Empowering Careers.</span>')
        self.assertContains(r, "images/hero.jpg")
        self.assertNotContains(r, "Looking for the right people?")  # pathway buttons removed from the hero
        # The Employers and Candidates cards further down still lead to both pages.
        self.assertContains(r, 'class="audience audience--employers"')
        self.assertContains(r, 'class="audience audience--candidates"')

    def test_employers_page_sections(self):
        r = self.client.get(reverse("core:employers"))
        for text in ("Save time", "Healthcare &amp; Support Services", "Engineering, Construction &amp; Trades",
                     "Understand your vacancy", "Need help finding the right people?"):
            self.assertContains(r, text)
        self.assertGreaterEqual(r.content.decode().count('href="#vacancy"'), 1)

    def test_candidates_page_sections(self):
        r = self.client.get(reverse("core:candidates"))
        for text in ("Access to opportunities", "Resume Support", "Interview Preparation", "Career Counselling",
                     "Create My Resume", "Book My Interview Session", "Book a Free Consultation",
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
        r = self.client.get(reverse("core:employers") + "?industry=construction")
        self.assertContains(r, '<option value="Construction &amp; Trades" selected>')

    def test_vacancy_saves_and_emails(self):
        r = self.client.post(reverse("core:employers"), VACANCY)
        self.assertRedirects(r, reverse("core:employers") + "?sent=1#vacancy", fetch_redirect_response=False)
        v = VacancyEnquiry.objects.get()
        self.assertEqual(v.status, "new")
        self.assertEqual(v.employment_types, ["Full Time", "Casual"])
        self.assertTrue(v.consent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Restaurant Manager", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].reply_to, ["sam@cafe.com.au"])
        follow = self.client.get(reverse("core:employers") + "?sent=1")
        self.assertContains(follow, "Vacancy received")

    def test_forms_use_airtable_fields_and_options(self):
        r = self.client.get(reverse("core:employers"))
        for text in ("Company name", "Industry / sector", "Contact person", "Mobile number",
                     "Position recruiting for", "Number of vacancies", "Work location",
                     "Additional requirements or comments", "Aged Care &amp; Disability", "More than 10",
                     "Temporary / Contract", "I agree to be contacted by SD Recruitment"):
            self.assertContains(r, text)
        r = self.client.get(reverse("core:candidates"))
        for text in ("Country / location", "Visa type", "Preferred job location", "Industry / job category",
                     "Position(s) interested in", "Relevant work experience", "Offshore Applicant / Unsure",
                     "Cleaning &amp; Maintenance", "More than 5 Years", "Working Holiday / Work and Holiday Visa"):
            self.assertContains(r, text)

    def test_vacancy_required_fields_match_airtable(self):
        r = self.client.post(reverse("core:employers"), {"vacancy-company": ""})
        form = r.context["form"]
        self.assertEqual(set(form.errors), {"company", "industry", "phone", "position"})

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

    def test_contact_details_shown(self):
        r = self.client.get(reverse("core:contact"))
        self.assertContains(r, 'href="tel:+61497389693"')
        self.assertContains(r, "0497 389 693")
        self.assertContains(r, 'href="mailto:admin@sd-recruitment.com"')
        home = self.client.get(reverse("core:home"))
        self.assertContains(home, "admin@sd-recruitment.com")  # footer
        self.assertContains(home, 'href="tel:+61497389693"')  # footer and contact prompt

    def test_phone_link_format(self):
        from core.content import _tel
        for given, expected in (("0497 389 693", "+61497389693"), ("+61 0497389693", "+61497389693"),
                                ("+61 497 389 693", "+61497389693"), ("(08) 9123 4567", "+61891234567")):
            self.assertEqual(_tel(given), expected)

    def test_contact_form_has_no_employer_candidate_choice(self):
        r = self.client.get(reverse("core:contact"))
        self.assertNotContains(r, "An employer")
        self.assertNotContains(r, "A candidate")
        self.assertNotContains(r, 'name="contact-enquirer_type"')

    def test_contact_page_shows_address_and_map(self):
        r = self.client.get(reverse("core:contact"))
        self.assertContains(r, "Suite 20, 25 Walters Drive, Osborne Park 6017, WA")
        self.assertContains(r, 'src="https://www.google.com/maps?q=Suite%2020%2C%2025%20Walters%20Drive%2C%20Osborne%20Park%206017%2C%20WA&amp;output=embed"')
        self.assertContains(self.client.get(reverse("core:home")), "Suite 20, 25 Walters Drive")  # footer

    def test_contact_enquiry_saves(self):
        r = self.client.post(reverse("core:contact"), {
            "contact-name": "Alex", "contact-email": "alex@example.com", "contact-phone": "",
            "contact-message": "Do you recruit in Bunbury?",
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(ContactEnquiry.objects.get().enquirer_type, "other")  # general enquiry
        self.assertEqual(len(mail.outbox), 1)

    def test_honeypot_blocks_bots(self):
        r = self.client.post(reverse("core:contact"), {
            "contact-name": "Bot", "contact-email": "bot@example.com",
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
