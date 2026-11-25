import json
import urllib.error
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core import careers_feed

STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
PAGE = "https://sd-recruitment.careers-page.com"
DIRECTOR = "442cd1b3-c462-42a4-8cc5-7f04797527f5"
CHEF = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def card(job_id, title, city="", country=""):
    return (f'<article class="mb-3 job-card"><a href="/jobs/{job_id}" class="job-title-link d-inline-flex" '
            f'data-job-id="{job_id}" data-job-title="{title}" data-job-city="{city}" data-job-country="{country}">'
            f'<h6>{title}</h6></a><a class="btn btn-primary" href="jobs/{job_id}/apply">Apply</a></article>')


HTML_PAGE1 = ("<html><body>" + card(DIRECTOR, "CENTRE DIRECTOR") + card(CHEF, "Chef &lt;de partie&gt;", "Fremantle", "Australia")
              + card("../../evil", "Bad id") + "</body></html>")
FEED = {"next": "https://evil.example/next", "results": [
    {"hash": "V67YY948", "position_name": "CENTRE DIRECTOR", "location_display": "Perth, WA",
     "is_pinned_in_career_page": False,
     "description": "<p>Minimum 2 years&#x27; experience as a <strong>Childcare Centre Director</strong></p>"
                    "<script>alert(1)</script>"},
    {"hash": "AB12", "position_name": "Chef <de partie>", "is_pinned_in_career_page": True,
     "description": "x " * 300},
]}


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@override_settings(MANATAL_CAREERS_PAGE_URL=PAGE, STORAGES=STATIC)
class CareersFeedTests(TestCase):
    def setUp(self):
        cache.clear()
        self.urls = []
        self.feed_down = False

        def fake(req, timeout=None, context=None):
            url = req.full_url
            self.urls.append(url)
            if url.startswith("https://www.careers-page.com/api/"):
                if self.feed_down:
                    raise urllib.error.URLError("feed down")
                return FakeResponse(json.dumps(FEED))
            return FakeResponse(HTML_PAGE1 if url.endswith("?page=1") else "<html></html>")

        p = mock.patch("urllib.request.urlopen", side_effect=fake)
        p.start()
        self.addCleanup(p.stop)

    def test_jobs_read_from_careers_page_with_feed_summaries(self):
        jobs = careers_feed.jobs()
        self.assertEqual([j["title"] for j in jobs], ["Chef <de partie>", "CENTRE DIRECTOR"])  # pinned first
        chef, director = jobs
        self.assertEqual(director["url"], f"{PAGE}/jobs/{DIRECTOR}")
        self.assertEqual(director["location"], "Perth, WA")  # from the feed when the page has none
        self.assertEqual(chef["location"], "Fremantle, Australia")
        self.assertEqual(director["summary"], "Minimum 2 years' experience as a Childcare Centre Director")
        self.assertTrue(chef["summary"].endswith("…"))
        # bad job id skipped; off-site "next" link not followed; only page 1 and 2 of the careers page read
        self.assertEqual(sum(u.startswith(PAGE) for u in self.urls), 2)
        self.assertNotIn("https://evil.example/next", self.urls)

    def test_jobs_still_show_if_feed_is_down(self):
        self.feed_down = True
        jobs = careers_feed.jobs()
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["summary"], "")

    def test_cached_between_visits(self):
        careers_feed.jobs()
        n = len(self.urls)
        careers_feed.jobs()
        self.assertEqual(len(self.urls), n)

    def test_candidates_page_lists_jobs_with_external_links(self):
        r = self.client.get(reverse("core:candidates"))
        self.assertContains(r, "CENTRE DIRECTOR")
        self.assertContains(r, f'href="{PAGE}/jobs/{DIRECTOR}" target="_blank" rel="noopener noreferrer"')
        self.assertContains(r, "Apply <svg")
        self.assertContains(r, f'href="{PAGE}" target="_blank"')
        self.assertContains(r, "Chef &lt;de partie&gt;")
        self.assertNotContains(r, "No roles are advertised right now")
        self.assertNotContains(r, "alert(1)")

    def test_last_good_list_used_when_site_down(self):
        careers_feed.jobs()
        cache.delete("manatal-jobs:sd-recruitment")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            self.assertEqual(len(careers_feed.jobs()), 2)


@override_settings(MANATAL_CAREERS_PAGE_URL=PAGE, STORAGES=STATIC)
class JobOrderAndViewMoreTests(TestCase):
    def setUp(self):
        cache.clear()
        ids = ["%08d-0000-0000-0000-000000000000" % i for i in range(1, 9)]
        page = "<html>" + "".join(card(i, f"Role {n}") for n, i in enumerate(ids, 1)) + "</html>"
        feed = {"results": [{"id": 100 + n, "position_name": f"Role {n}", "description": "",
                             "is_pinned_in_career_page": n == 2} for n in range(1, 9)]}

        def fake(req, timeout=None, context=None):
            if req.full_url.startswith("https://www.careers-page.com/api/"):
                return FakeResponse(json.dumps(feed))
            return FakeResponse(page if req.full_url.endswith("?page=1") else "<html></html>")

        p = mock.patch("urllib.request.urlopen", side_effect=fake)
        p.start()
        self.addCleanup(p.stop)

    def test_pinned_then_most_recent_first(self):
        titles = [j["title"] for j in careers_feed.jobs()]
        self.assertEqual(titles[:3], ["Role 2", "Role 8", "Role 7"])
        self.assertEqual(titles[-1], "Role 1")

    def test_page_has_view_more_control_and_all_jobs(self):
        r = self.client.get(reverse("core:candidates"))
        self.assertContains(r, 'data-job-list', count=1)
        self.assertContains(r, 'aria-controls="job-list"')
        self.assertContains(r, 'class="job job--compact"', count=8)  # all in the page; extra ones hidden by script
        self.assertNotContains(r, "jobs--few")


class CareersPageSettingTests(TestCase):
    def test_only_careers_page_addresses_accepted(self):
        for value, expected in (
            ("https://sd-recruitment.careers-page.com", "https://sd-recruitment.careers-page.com"),
            ("https://sd-recruitment.careers-page.com/", "https://sd-recruitment.careers-page.com"),
            ("http://sd-recruitment.careers-page.com", ""),
            ("https://evil.com", ""),
            ("https://sd-recruitment.careers-page.com.evil.com", ""),
            ("https://evil.com/?x=.careers-page.com", ""),
            ("", ""),
        ):
            with self.subTest(value=value), override_settings(MANATAL_CAREERS_PAGE_URL=value):
                self.assertEqual(careers_feed.careers_page_url(), expected)
        with override_settings(MANATAL_CAREERS_PAGE_URL="https://sd-recruitment.careers-page.com"):
            self.assertEqual(careers_feed.account(), "sd-recruitment")


@override_settings(MANATAL_CAREERS_PAGE_URL="", STORAGES=STATIC)
class CareersFeedOffTests(TestCase):
    def test_off_shows_empty_state(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            r = self.client.get(reverse("core:candidates"))
            urlopen.assert_not_called()
        self.assertContains(r, "No roles are advertised right now")
        self.assertNotContains(r, "See all roles on our careers page")

    def test_site_down_with_no_history_shows_empty_state(self):
        cache.clear()
        with override_settings(MANATAL_CAREERS_PAGE_URL=PAGE), \
                mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            r = self.client.get(reverse("core:candidates"))
        self.assertContains(r, "No roles are advertised right now")
