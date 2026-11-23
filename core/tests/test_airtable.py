import json
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from core import airtable
from core.models import AIRTABLE_FAILED, AIRTABLE_OFF, AIRTABLE_SENT, CandidateRegistration, ContactEnquiry, VacancyEnquiry
from core.tests.test_site import VACANCY, candidate_data

STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
ON = dict(AIRTABLE_TOKEN="patTEST", AIRTABLE_BASE_ID="appv3PA1WBgRGxeX5", AIRTABLE_TABLE="tblZaBP5px3dqWuaD",
          STORAGES=STATIC, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@override_settings(**ON)
class AirtableTests(TestCase):
    def setUp(self):
        self.calls = []

        def fake_urlopen(req, timeout=None, context=None):
            self.calls.append((req.get_method(), req.full_url, json.loads(req.data.decode()),
                               req.get_header("Authorization")))
            return FakeResponse({"records": [{"id": "recABC123"}]})

        patcher = mock.patch("urllib.request.urlopen", side_effect=fake_urlopen)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_vacancy_sent_with_employer_form_mapping(self):
        self.client.post(reverse("core:employers"), VACANCY)
        v = VacancyEnquiry.objects.get()
        self.assertEqual((v.airtable_status, v.airtable_id), (AIRTABLE_SENT, "recABC123"))
        method, url, body, auth = self.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.airtable.com/v0/appv3PA1WBgRGxeX5/tblZaBP5px3dqWuaD")
        self.assertEqual(auth, "Bearer patTEST")
        self.assertTrue(body["typecast"])
        f = body["records"][0]["fields"]
        self.assertEqual(f["flde6QS0zw4mK3vcV"], "Cafe Co")              # Organisation / Company Name
        self.assertEqual(f["fldZzLlrg8bgGdkpY"], "Hospitality")           # Industry / Sector
        self.assertEqual(f["fldg9tVfNK7REj52P"], "Sam Lee")               # "Contact Person"
        self.assertEqual(f["fldDXTuMrsq5riVPU"], "0411 111 111")          # Phone Number
        self.assertEqual(f["fldRtIJEPWV15RmSv"], "Restaurant Manager")    # Position Recruiting For
        self.assertEqual(f["fldlKUehNaiNjxa90"], ["Full Time", "Casual"])  # Employment Type
        self.assertEqual(f["fldg2R4etvUrg9WBQ"], "2-5")                   # Number of Staff Required
        self.assertEqual(f["fldaFBs37NRkuw38W"], "Fremantle WA")          # Work Location
        self.assertEqual(f["fld93WIxFp36uXcwo"], "Busy venue.")           # Additional Information
        self.assertIs(f["fldt1MwrPLURa3fJo"], True)                       # Consent to Contact

    def test_candidate_sent_with_talent_form_mapping(self):
        self.client.post(reverse("core:candidates"), candidate_data())
        c = CandidateRegistration.objects.get()
        self.assertEqual(c.airtable_status, AIRTABLE_SENT)
        f = self.calls[0][2]["records"][0]["fields"]
        self.assertEqual(f["fldNazuVVEevqlwIf"], "Jane Citizen")
        self.assertEqual(f["fldlOQ61PTPvjfZkt"], "Student Visa (Subclass 500)")
        self.assertEqual(f["fld8DCHC9mxzlYQyN"], "Aged Care & Disability")
        self.assertEqual(f["fld0UHh3D9L21yqPx"], "Support Worker")
        self.assertEqual(f["fldlKUehNaiNjxa90"], ["Casual", "Part - Time"])
        self.assertEqual(f["fld2MpuDbls6jFRt0"], "1–3 Years")
        self.assertEqual(f["fldj8QcpglaHe7K1e"], "Perth metro")

    def test_empty_optional_fields_are_left_out(self):
        data = dict(VACANCY)
        for k in ("vacancy-email", "vacancy-contact_name", "vacancy-details", "vacancy-location"):
            data[k] = ""
        data.pop("vacancy-employment_types")
        self.client.post(reverse("core:employers"), data)
        f = self.calls[0][2]["records"][0]["fields"]
        for fid in ("fldjEWSC9V0b31LEf", "fldg9tVfNK7REj52P", "fld93WIxFp36uXcwo", "fldlKUehNaiNjxa90"):
            self.assertNotIn(fid, f)

    def test_contact_messages_are_not_sent(self):
        self.client.post(reverse("core:contact"), {"contact-name": "A", "contact-email": "a@example.com",
                                                   "contact-enquirer_type": "other", "contact-message": "Hi"})
        self.assertTrue(ContactEnquiry.objects.exists())
        self.assertEqual(self.calls, [])

    def test_failure_is_recorded_and_retried_by_command(self):
        import urllib.error
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            r = self.client.post(reverse("core:candidates"), candidate_data())
        self.assertEqual(r.status_code, 302)  # the visitor still gets "Thank you"
        c = CandidateRegistration.objects.get()
        self.assertEqual(c.airtable_status, AIRTABLE_FAILED)
        self.assertIn("Could not reach Airtable", c.airtable_error)
        call_command("sync_airtable", stdout=mock.MagicMock())
        c.refresh_from_db()
        self.assertEqual((c.airtable_status, c.airtable_id), (AIRTABLE_SENT, "recABC123"))
        call_command("sync_airtable", stdout=mock.MagicMock())  # nothing left to send
        self.assertEqual(len(self.calls), 1)

    def test_sent_once_only(self):
        self.client.post(reverse("core:employers"), VACANCY)
        v = VacancyEnquiry.objects.get()
        self.assertTrue(airtable.push(v))
        self.assertEqual(len(self.calls), 1)


@override_settings(AIRTABLE_TOKEN="", STORAGES=STATIC)
class AirtableOffTests(TestCase):
    def test_switched_off_without_token(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            self.client.post(reverse("core:employers"), VACANCY)
        urlopen.assert_not_called()
        self.assertEqual(VacancyEnquiry.objects.get().airtable_status, AIRTABLE_OFF)
