"""Jobs posted on the client's Manatal careers page, shown on the Candidates page.

The client's careers page is MANATAL_CAREERS_PAGE_URL (default https://sd-recruitment.careers-page.com).
Each job links to its own page there (…/jobs/<job id>), where candidates read the full ad and apply.

- Jobs are read from the careers page itself (title, city, country and job id of each job card), so the
  list and links always match what candidates see there.
- A short summary and the "pinned" order come from Manatal's public careers-page feed
  (https://www.careers-page.com/api/v1.0/c/<account>/jobs/), matched by job title. If that feed is
  unavailable, the jobs still show, just without a summary.
- Results are cached for MANATAL_CACHE_MINUTES (default 15). If careers-page.com can't be reached, the
  last list that worked is shown (kept for 24 hours), and the page never breaks.
- Only plain text is shown. Job links are built by this code from the job id and the configured
  careers page, which must be a https://<name>.careers-page.com address.
"""

import html
import json
import logging
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

FEED_BASE = "https://www.careers-page.com"
PAGE_RE = re.compile(r"^https://([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.careers-page\.com/?$")
JOB_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
MAX_PAGES = 5


def careers_page_url():
    """The client's careers page, e.g. https://sd-recruitment.careers-page.com ('' when switched off)."""
    value = (getattr(settings, "MANATAL_CAREERS_PAGE_URL", "") or "").strip()
    match = PAGE_RE.match(value)
    return f"https://{match.group(1)}.careers-page.com" if match else ""


def account():
    """The Manatal account name, taken from the careers page address."""
    match = PAGE_RE.match(careers_page_url() + "/") if careers_page_url() else None
    return match.group(1) if match else ""


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover
        return ssl.create_default_context()


def _get(url, accept):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "SD-Recruitment-Website"})
    with urllib.request.urlopen(req, timeout=getattr(settings, "MANATAL_TIMEOUT", 6), context=_ssl_context()) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _text(value, limit=None):
    """HTML -> plain text (scripts/styles dropped, tags removed, entities decoded, spaces tidied)."""
    text = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", value or "", flags=re.I | re.S)
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", " ", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:–- ") + "…"
    return text


def _plain(value):
    """Text that is already plain (titles, places): decode entities and tidy spaces only.
    The page template escapes it when shown."""
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _key(title):
    return re.sub(r"\s+", " ", title or "").strip().casefold()


class _JobCards(HTMLParser):
    """Collects the job title links on a careers page: <a class="job-title-link" data-job-id=… …>."""

    def __init__(self):
        super().__init__()
        self.cards = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and "job-title-link" in (a.get("class") or "").split():
            self.cards.append({k: (a.get(k) or "") for k in ("data-job-id", "data-job-title", "data-job-city",
                                                              "data-job-country")})


def _cards(page_url):
    cards, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        parser = _JobCards()
        parser.feed(_get(f"{page_url}/?page={page}", "text/html"))
        new = [c for c in parser.cards if c["data-job-id"] not in seen]
        if not new:
            break
        for c in new:
            seen.add(c["data-job-id"])
            cards.append(c)
    return cards


def _feed_details(acct):
    """title -> {summary, location, pinned} from Manatal's careers-page feed. {} if it can't be read."""
    details, url, pages = {}, f"{FEED_BASE}/api/v1.0/c/{urllib.parse.quote(acct)}/jobs/", 0
    try:
        while url and pages < MAX_PAGES:
            data = json.loads(_get(url, "application/json"))
            for raw in data.get("results", []):
                details.setdefault(_key(_plain(raw.get("position_name", ""))), {
                    "summary": _text(raw.get("description", ""), limit=220),
                    "location": _plain(raw.get("location_display", "")),
                    "pinned": bool(raw.get("is_pinned_in_career_page")),
                })
            nxt = data.get("next") or ""
            url = nxt if nxt.startswith(f"{FEED_BASE}/api/v1.0/c/") else ""
            pages += 1
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, AttributeError) as e:
        logger.info("Manatal feed details unavailable for %s: %s", acct, e)
    return details


def _fetch(page_url, acct):
    extra = _feed_details(acct)
    jobs = []
    for c in _cards(page_url):
        job_id, title = c["data-job-id"], _plain(c["data-job-title"])
        if not JOB_ID_RE.match(job_id) or not title:
            continue
        d = extra.get(_key(title), {})
        location = ", ".join(p for p in (_plain(c["data-job-city"]), _plain(c["data-job-country"])) if p)
        jobs.append({
            "title": title,
            "location": location or d.get("location", ""),
            "summary": d.get("summary", ""),
            "pinned": d.get("pinned", False),
            "url": f"{page_url}/jobs/{job_id.lower()}",
        })
    jobs.sort(key=lambda j: not j["pinned"])  # pinned first, otherwise the careers page order
    return jobs


def jobs():
    """Current jobs on the client's careers page (list of dicts); [] when switched off or unavailable."""
    page_url, acct = careers_page_url(), account()
    if not page_url:
        return []
    key, stale_key = f"manatal-jobs:{acct}", f"manatal-jobs-last-good:{acct}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        result = _fetch(page_url, acct)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        logger.warning("Could not read the careers page %s: %s", page_url, e)
        result = cache.get(stale_key, [])
        cache.set(key, result, 120)  # try again in two minutes
        return result
    cache.set(key, result, getattr(settings, "MANATAL_CACHE_MINUTES", 15) * 60)
    cache.set(stale_key, result, 24 * 3600)
    return result
