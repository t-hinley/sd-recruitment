import shutil
import tempfile

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import CandidateRegistration, ContactEnquiry, VacancyEnquiry

STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MEDIA = tempfile.mkdtemp(prefix="sdr-test-media-")


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


def make_candidate(**kw):
    data = dict(full_name="Jane Citizen", email="j@example.com", phone="0412345670", location="Perth WA",
                position_sought="=HYPERLINK(\"x\")", industry="Hospitality & Tourism", experience="1–3 Years",
                support_jobs=True, support_resume=True, consent=True)
    data.update(kw)
    return CandidateRegistration.objects.create(**data)


@override_settings(STORAGES=STATIC, MEDIA_ROOT=MEDIA, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser("boss", "boss@example.com", "a-strong-pass-123")
        self.staff = User.objects.create_user("helper", "h@example.com", "a-strong-pass-123", is_staff=True)
        self.cand = make_candidate()
        VacancyEnquiry.objects.create(contact_name="Sam", company="Cafe Co", email="s@example.com", phone="0412345671",
                                      industry="Hospitality", position="Head Chef", employment_types=["Full Time"],
                                      location="Perth")
        ContactEnquiry.objects.create(name="Alex", email="a@example.com", message="Hello", enquirer_type="other")

    def test_login_page_is_styled(self):
        r = self.client.get(reverse("admin:login"))
        self.assertContains(r, "Admin Login")
        self.assertContains(r, "core/auth.css")
        self.assertContains(r, "SD Recruitment")

    def test_login_shows_toast_once(self):
        r = self.client.post(reverse("admin:login"), {"username": "boss", "password": "a-strong-pass-123",
                                                      "next": reverse("admin:index")}, follow=True)
        self.assertContains(r, 'class="toast"')
        self.assertNotContains(self.client.get(reverse("admin:index")), 'class="toast"')

    def test_dashboard_shows_numbers_and_sidebar(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, 'id="sdside"')
        self.assertContains(r, "Needs attention")
        self.assertContains(r, 'aria-label="New candidates: 1"')
        self.assertContains(r, 'aria-label="New vacancies: 1"')
        self.assertContains(r, 'aria-label="Candidates: 1"')
        self.assertNotContains(r, "Airtable send failures")  # only shown when something failed
        self.assertNotContains(r, "Current opportunities")  # jobs come from the careers page
        self.assertNotContains(r, "Live opportunities")
        self.assertContains(r, "Hospitality &amp; Tourism")
        self.assertContains(r, "Resume support")
        self.assertContains(r, reverse("admin:reports"))

    def test_staff_without_superuser_cannot_export(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:reports")).status_code, 403)

    def test_csv_exports_and_formula_protection(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:reports"), {"report": "candidates", "date_from": "", "date_to": ""})
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        body = r.content.decode("utf-8")
        self.assertIn("Jane Citizen", body)
        self.assertIn("Job opportunities, Resume support", body)
        self.assertIn("'=HYPERLINK", body)
        self.assertIn("Cafe Co", self.client.get(reverse("admin:reports"), {"report": "vacancies"}).content.decode())
        self.assertIn("Alex", self.client.get(reverse("admin:reports"), {"report": "contact"}).content.decode())

    def _pdf_text(self, content):
        """Text drawn in a PDF made by ReportLab (page streams are ASCII85 + zlib encoded)."""
        import base64
        import re
        import zlib
        out = []
        for m in re.finditer(rb"/Filter \[ /ASCII85Decode /FlateDecode \].*?stream\r?\n(.*?)endstream", content, re.S):
            data = m.group(1).strip()
            if data.endswith(b"~>"):
                data = data[:-2]
            out.append(zlib.decompress(base64.a85decode(data)).decode("latin-1"))
        return " ".join(re.findall(r"\((.*?)\) Tj", " ".join(out)))

    def test_pdf_exports(self):
        self.client.force_login(self.admin)
        for report, expected in (("candidates", "Jane Citizen"), ("vacancies", "Cafe Co"), ("contact", "Alex")):
            r = self.client.get(reverse("admin:reports"), {"report": report, "format": "pdf"})
            self.assertEqual(r["Content-Type"], "application/pdf", report)
            self.assertIn(f"sd-recruitment-{report}-", r["Content-Disposition"])
            self.assertTrue(r.content.startswith(b"%PDF"))
            text = self._pdf_text(r.content)
            self.assertIn(expected, text, report)
            self.assertIn("Confidential", text)

    def test_pdf_with_dates_and_no_records(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:reports"), {"report": "vacancies", "format": "pdf",
                                                       "date_from": "2001-01-01", "date_to": "2001-01-31"})
        text = self._pdf_text(r.content)
        self.assertIn("No records for this period.", text)
        self.assertIn("1 Jan 2001", text)

    def test_reports_in_sidebar_not_on_dashboard(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:index"))
        self.assertNotContains(r, "Export reports")
        self.assertContains(r, reverse("admin:reports"))  # the Reports link in the sidebar
        r = self.client.get(reverse("admin:reports"), {"format": "pdf"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'value="pdf" checked')
        self.assertNotContains(r, "This field is required")

    def test_profile_and_changelists(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("admin:profile")), "Administrator")
        for name in ("candidateregistration", "vacancyenquiry", "contactenquiry"):
            self.assertEqual(self.client.get(reverse(f"admin:core_{name}_changelist")).status_code, 200, name)
        self.assertEqual(self.client.get(reverse("admin:core_candidateregistration_change",
                                                 args=[self.cand.pk])).status_code, 200)

    def test_logout_returns_to_login(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("admin:logout"))
        self.assertRedirects(r, reverse("admin:login"))

    def test_session_ping_and_expire(self):
        self.assertEqual(self.client.post(reverse("session_ping")).status_code, 401)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse("session_ping")).status_code, 204)
        self.client.post(reverse("session_expire"))
        self.assertEqual(self.client.post(reverse("session_ping")).status_code, 401)

    def test_login_pauses_after_repeated_failures(self):
        for _ in range(5):
            self.client.post(reverse("admin:login"), {"username": "boss", "password": "wrong"})
        r = self.client.post(reverse("admin:login"), {"username": "boss", "password": "a-strong-pass-123"})
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "Too many failed sign-in attempts", status_code=429)

    @override_settings(BEHIND_PROXY=True)
    def test_behind_proxy_failures_are_counted_per_visitor(self):
        for _ in range(5):
            self.client.post(reverse("admin:login"), {"username": "boss", "password": "wrong"}, HTTP_X_REAL_IP="1.1.1.1")
        r = self.client.post(reverse("admin:login"), {"username": "boss", "password": "a-strong-pass-123"},
                             HTTP_X_REAL_IP="2.2.2.2")
        self.assertNotEqual(r.status_code, 429)

    def test_password_reset_page(self):
        r = self.client.get(reverse("admin_password_reset"))
        self.assertContains(r, "Reset your password")


@override_settings(STORAGES=STATIC, MEDIA_ROOT=MEDIA)
class FollowUpTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("boss", "boss@example.com", "a-strong-pass-123")
        self.staff = User.objects.create_user("helper", "h@example.com", "a-strong-pass-123", is_staff=True,
                                              first_name="Pema")
        self.staff.groups.add(Group.objects.get(name="Staff"))
        self.e = make_candidate(phone="0412 345 678", position_sought="Original position")
        self.url = reverse("admin:core_candidateregistration_change", args=[self.e.pk])

    def post_change(self, **extra):
        data = {"status": "active", "assigned_to": self.staff.pk, "notes": "Phone screen done",
                "full_name": "Hacked", "position_sought": "Changed", "email": "x@example.com"}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_staff_role_permissions(self):
        codes = set(Group.objects.get(name="Staff").permissions.values_list("codename", flat=True))
        self.assertIn("change_candidateregistration", codes)
        self.assertNotIn("delete_candidateregistration", codes)
        self.assertNotIn("add_vacancyenquiry", codes)

    def test_staff_updates_follow_up_but_not_submitted_details(self):
        self.client.force_login(self.staff)
        r = self.post_change()
        self.assertEqual(r.status_code, 302)
        self.e.refresh_from_db()
        self.assertEqual((self.e.status, self.e.assigned_to, self.e.notes), ("active", self.staff, "Phone screen done"))
        self.assertEqual((self.e.full_name, self.e.position_sought, self.e.email),
                         ("Jane Citizen", "Original position", "j@example.com"))

    def test_details_are_read_only_even_for_admins(self):
        self.client.force_login(self.admin)
        self.post_change()
        self.e.refresh_from_db()
        self.assertEqual(self.e.full_name, "Jane Citizen")
        r = self.client.get(self.url)
        self.assertNotContains(r, 'name="full_name"')
        self.assertContains(r, 'name="notes"')
        self.assertContains(r, 'href="tel:0412345678"')
        self.assertContains(r, "Not provided")

    def test_no_add_and_only_admins_delete(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:core_candidateregistration_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:core_candidateregistration_delete",
                                                 args=[self.e.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:auth_user_changelist")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:core_candidateregistration_delete",
                                                 args=[self.e.pk])).status_code, 200)

    def test_assign_to_me_action_and_dashboard_card(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("admin:core_candidateregistration_changelist"),
                         {"action": "assign_to_me", "_selected_action": [self.e.pk]})
        self.e.refresh_from_db()
        self.assertEqual(self.e.assigned_to, self.staff)
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, "1 open item assigned to you")
        self.assertContains(r, "1 candidate</a>")
        self.assertNotContains(r, "0 vacancies")


@override_settings(STORAGES=STATIC, MEDIA_ROOT=MEDIA)
class ResumeAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("boss", "boss@example.com", "a-strong-pass-123")
        self.staff = User.objects.create_user("helper", "h@example.com", "a-strong-pass-123", is_staff=True)
        self.staff.groups.add(Group.objects.get(name="Staff"))
        self.nobody = User.objects.create_user("visitor", "v@example.com", "a-strong-pass-123")
        self.cand = make_candidate(resume_name="my cv.pdf")
        self.cand.resume.save("my cv.pdf", ContentFile(b"%PDF-1.4 test"), save=True)
        self.url = reverse("admin:resume_download", args=[self.cand.pk])

    def test_resume_is_stored_under_random_name(self):
        self.assertNotIn("Jane", self.cand.resume.name)
        self.assertTrue(self.cand.resume.name.startswith("resumes/"))

    def test_anonymous_and_non_staff_cannot_download(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)  # sent to the admin login
        self.client.force_login(self.nobody)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_staff_can_download(self):
        self.client.force_login(self.staff)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertIn('attachment; filename="CV-Jane-Citizen.pdf"', r["Content-Disposition"])
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4 test")
        change = self.client.get(reverse("admin:core_candidateregistration_change", args=[self.cand.pk]))
        self.assertContains(change, self.url)

    def test_deleting_candidate_removes_file(self):
        storage, name = self.cand.resume.storage, self.cand.resume.name
        self.assertTrue(storage.exists(name))
        CandidateRegistration.objects.filter(pk=self.cand.pk).delete()  # bulk delete path
        self.assertFalse(storage.exists(name))


class RecordPageTests(TestCase):
    def test_record_page_layout(self):
        from django.contrib.auth.models import User
        from django.test import override_settings
        from core.models import ContactEnquiry
        boss = User.objects.create_superuser("recboss", "rb@example.com", "a-strong-pass-123")
        e = ContactEnquiry.objects.create(name="Sam Lee", email="sam@example.com", phone="0412 111 222", message="Hi")
        self.client.force_login(boss)
        with override_settings(STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}):
            url = reverse("admin:core_contactenquiry_change", args=[e.pk])
            r = self.client.get(url)
            self.assertContains(r, 'class="rec-head"')
            self.assertContains(r, 'href="mailto:sam@example.com"')
            self.assertContains(r, 'href="tel:0412111222"')
            r = self.client.post(url, {"status": "contacted", "assigned_to": boss.pk, "notes": "Called back",
                                       "_continue": "1"})
            self.assertRedirects(r, url)
        e.refresh_from_db()
        self.assertEqual((e.status, e.assigned_to, e.notes), ("contacted", boss, "Called back"))


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class FilterBarTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser("fbboss", "fb@example.com", "a-strong-pass-123")
        self.client.force_login(self.boss)
        base = dict(phone="0412 345 678", location="Perth", visa_type="Australian Citizen", consent=True,
                    preferred_location="Perth Metro", position_sought="Carer", experience="1–3 Years",
                    employment_types=["Full - Time"])
        CandidateRegistration.objects.create(full_name="Amy New", email="a@example.com", industry="Healthcare & Nursing",
                                             status="new", support_interview=True, **base)
        CandidateRegistration.objects.create(full_name="Bo Mine", email="b@example.com", industry="Hospitality & Tourism",
                                             status="contacted", assigned_to=self.boss, support_jobs=True, **base)
        self.url = reverse("admin:core_candidateregistration_changelist")

    def test_tabs_dropdowns_and_no_side_column(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'class="fb-tab is-on')
        self.assertContains(r, "Mine <b>1</b>", html=False)
        self.assertContains(r, "Unassigned <b>1</b>", html=False)
        self.assertContains(r, "+ More filters")
        self.assertNotContains(r, 'id="changelist-filter"')

    def test_filters_and_chips(self):
        r = self.client.get(self.url + "?service=interview")
        self.assertContains(r, "Amy New")
        self.assertNotContains(r, "Bo Mine")
        self.assertContains(r, "Service requested: Interview")
        r = self.client.get(self.url + "?assigned=me")  # the Mine tab: no duplicate chip
        self.assertContains(r, "Bo Mine")
        self.assertNotContains(r, "Amy New")
        self.assertNotContains(r, 'class="fb-chip"')
        r = self.client.get(self.url + "?q=Amy")
        self.assertContains(r, "Search: Amy")


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AutoAssignOnStatusTests(TestCase):
    def setUp(self):
        self.sam = User.objects.create_user("samx", "samx@example.com", "a-strong-pass-123", is_staff=True)
        self.sam.groups.add(Group.objects.get(name="Staff"))
        self.other = User.objects.create_user("otherx", "o@example.com", "a-strong-pass-123", is_staff=True)
        self.client.force_login(self.sam)

    def enquiry(self, **kw):
        return ContactEnquiry.objects.create(name="Ann", email="ann@example.com", message="Hi", **kw)

    def post_change(self, e, **data):
        url = reverse("admin:core_contactenquiry_change", args=[e.pk])
        return self.client.post(url, {"status": e.status, "assigned_to": e.assigned_to_id or "", "notes": e.notes,
                                      "_continue": "1", **data})

    def test_changing_status_assigns_unassigned_to_you(self):
        e = self.enquiry()
        self.post_change(e, status="contacted")
        e.refresh_from_db()
        self.assertEqual((e.status, e.assigned_to), ("contacted", self.sam))

    def test_owner_and_explicit_choice_are_kept(self):
        e = self.enquiry(assigned_to=self.other)
        self.post_change(e, status="contacted")
        e.refresh_from_db()
        self.assertEqual(e.assigned_to, self.other)          # someone else's stays theirs
        e2 = self.enquiry()
        self.post_change(e2, status="contacted", assigned_to=str(self.other.pk))
        e2.refresh_from_db()
        self.assertEqual(e2.assigned_to, self.other)         # picking a person wins
        e3 = self.enquiry()
        self.post_change(e3, notes="Just a note")            # no status change: no assignment
        e3.refresh_from_db()
        self.assertIsNone(e3.assigned_to)

    def test_list_dropdown_and_bulk_action(self):
        e = self.enquiry()
        url = reverse("admin:core_contactenquiry_changelist")
        self.client.post(url, {"form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1", "form-0-id": str(e.pk),
                               "form-0-status": "contacted", "_save": "Save"})
        e.refresh_from_db()
        self.assertEqual((e.status, e.assigned_to), ("contacted", self.sam))
        a, b = self.enquiry(), self.enquiry(assigned_to=self.other)
        self.client.post(url, {"action": "mark_closed", "_selected_action": [a.pk, b.pk]})
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((a.status, a.assigned_to), ("closed", self.sam))
        self.assertEqual((b.status, b.assigned_to), ("closed", self.other))
