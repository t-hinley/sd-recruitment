import json
import urllib.error
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core import careers_feed
from core.models import Job

STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
PAGE1 = {
    "next": "https://www.careers-page.com/api/v1.0/c/sd-recruitment/jobs/?page=2",
    "results": [
        {"hash": "V67YY948", "position_name": "CENTRE DIRECTOR", "location_display": "",
         "city": "Perth", "state": "WA", "country": "Australia", "is_pinned_in_career_page": False,
         "description": "<p>Minimum 2 years&#x27; experience as a <strong>Childcare Centre Director</strong></p>"
                        "<script>alert(1)</script>"},
        {"hash": "../../evil", "position_name": "Bad code", "description": ""},
    ],
}
PAGE2 = {
    "next": "https://evil.example/api/next",
    "results": [{"hash": "AB12CD34", "position_name": "Chef <b>de partie</b>", "location_display": "Fremantle, WA",
                 "is_pinned_in_career_page": True, "description": "x " * 300}],
}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@override_settings(MANATAL_CAREERS_ACCOUNT="sd-recruitment", STORAGES=STATIC)
class CareersFeedTests(TestCase):
    def setUp(self):
        cache.clear()
        self.urls = []

        def fake(req, timeout=None, context=None):
            self.urls.append(req.full_url)
            return FakeResponse(PAGE2 if "page=2" in req.full_url else PAGE1)

        p = mock.patch("urllib.request.urlopen", side_effect=fake)
        p.start()
        self.addCleanup(p.stop)

    def test_jobs_parsed_safely(self):
        jobs = careers_feed.jobs()
        self.assertEqual([j["title"] for j in jobs], ["Chef de partie", "CENTRE DIRECTOR"])  # pinned first
        chef, director = jobs
        self.assertEqual(director["url"], "https://www.careers-page.com/sd-recruitment/job/V67YY948")
        self.assertEqual(director["location"], "Perth, WA, Australia")
        self.assertEqual(director["summary"], "Minimum 2 years' experience as a Childcare Centre Director")
        self.assertTrue(chef["summary"].endswith("…"))
        self.assertLessEqual(len(chef["summary"]), 222)
        # the bad job code was skipped, and the off-site "next" link was not followed
        self.assertEqual(len(self.urls), 2)
        self.assertTrue(all(u.startswith("https://www.careers-page.com/api/v1.0/c/sd-recruitment/") for u in self.urls))

    def test_cached_between_visits(self):
        careers_feed.jobs()
        careers_feed.jobs()
        self.assertEqual(len(self.urls), 2)

    def test_candidates_page_lists_jobs_with_external_links(self):
        r = self.client.get(reverse("core:candidates"))
        self.assertContains(r, "CENTRE DIRECTOR")
        self.assertContains(r, 'href="https://www.careers-page.com/sd-recruitment/job/V67YY948" target="_blank" '
                               'rel="noopener noreferrer"')
        self.assertContains(r, "View &amp; Apply")
        self.assertContains(r, 'href="https://www.careers-page.com/sd-recruitment"')
        self.assertNotContains(r, "No roles are advertised right now")
        self.assertNotContains(r, "<script>alert")

    def test_last_good_list_used_when_site_down(self):
        careers_feed.jobs()
        cache.delete("manatal-jobs:sd-recruitment")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            self.assertEqual(len(careers_feed.jobs()), 2)


@override_settings(MANATAL_CAREERS_ACCOUNT="", STORAGES=STATIC)
class CareersFeedOffTests(TestCase):
    def test_off_shows_admin_jobs_or_empty_state(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            r = self.client.get(reverse("core:candidates"))
            urlopen.assert_not_called()
        self.assertContains(r, "No roles are advertised right now")
        Job.objects.create(title="Head Chef", industry="Hospitality & Tourism", location="Perth", summary="x")
        self.assertContains(self.client.get(reverse("core:candidates")), "Head Chef")

    @override_settings(MANATAL_CAREERS_ACCOUNT="bad/../name")
    def test_invalid_account_ignored(self):
        self.assertEqual(careers_feed.account(), "")
        self.assertEqual(careers_feed.jobs(), [])

    def test_site_down_with_no_history_shows_empty_state(self):
        cache.clear()
        with override_settings(MANATAL_CAREERS_ACCOUNT="sd-recruitment"), \
                mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            r = self.client.get(reverse("core:candidates"))
        self.assertContains(r, "No roles are advertised right now")
