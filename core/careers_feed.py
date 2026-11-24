"""Jobs posted on the client's Manatal careers page (careers-page.com), shown on the Candidates page.

Each job links to its own page on careers-page.com, where candidates read the full ad and apply.
The list is read from Manatal's public careers-page feed:
    https://www.careers-page.com/api/v1.0/c/<account>/jobs/

- Set MANATAL_CAREERS_ACCOUNT in .env (the name in the careers page address). Empty = switched off.
- Results are cached for MANATAL_CACHE_MINUTES (default 15), so a new job appears within that time
  without slowing the page down.
- If careers-page.com can't be reached, the last list that worked is shown (kept for 24 hours), and
  the page never breaks.
- Only plain text from the feed is shown. Job links are always built by this code from the job's
  short code; no link from the feed is ever used.
"""

import html
import json
import logging
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

BASE = "https://www.careers-page.com"
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
HASH_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")
MAX_PAGES = 5


def account():
    value = (getattr(settings, "MANATAL_CAREERS_ACCOUNT", "") or "").strip().strip("/")
    return value if ACCOUNT_RE.match(value) else ""


def careers_page_url():
    a = account()
    return f"{BASE}/{a}" if a else ""


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover
        return ssl.create_default_context()


def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "SD-Recruitment-Website"})
    with urllib.request.urlopen(req, timeout=getattr(settings, "MANATAL_TIMEOUT", 6), context=_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _text(value, limit=None):
    """HTML from the feed -> plain text (tags removed, entities decoded, spaces tidied)."""
    text = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", value or "", flags=re.I | re.S)
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", " ", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:–- ") + "…"
    return text


def _job(raw, acct):
    code = str(raw.get("hash", ""))
    title = _text(raw.get("position_name", ""))
    if not HASH_RE.match(code) or not title:
        return None
    location = _text(raw.get("location_display", "")) or ", ".join(
        p for p in (_text(raw.get("city", "")), _text(raw.get("state", "")), _text(raw.get("country", ""))) if p)
    return {
        "title": title,
        "location": location,
        "summary": _text(raw.get("description", ""), limit=220),
        "pinned": bool(raw.get("is_pinned_in_career_page")),
        "url": f"{BASE}/{urllib.parse.quote(acct)}/job/{code}",
    }


def _fetch(acct):
    jobs, url, pages = [], f"{BASE}/api/v1.0/c/{urllib.parse.quote(acct)}/jobs/", 0
    while url and pages < MAX_PAGES:
        data = _get(url)
        for raw in data.get("results", []):
            job = _job(raw, acct)
            if job:
                jobs.append(job)
        nxt = data.get("next") or ""
        # follow pagination only on careers-page.com itself
        url = nxt if nxt.startswith(f"{BASE}/api/v1.0/c/") else ""
        pages += 1
    jobs.sort(key=lambda j: not j["pinned"])  # pinned first, otherwise Manatal's order
    return jobs


def jobs():
    """Current jobs from Manatal (list of dicts), [] when switched off or nothing is available."""
    acct = account()
    if not acct:
        return []
    key, stale_key = f"manatal-jobs:{acct}", f"manatal-jobs-last-good:{acct}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        result = _fetch(acct)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, AttributeError) as e:
        logger.warning("Could not read Manatal jobs for %s: %s", acct, e)
        result = cache.get(stale_key, [])
        cache.set(key, result, 120)  # try again in two minutes
        return result
    minutes = getattr(settings, "MANATAL_CACHE_MINUTES", 15)
    cache.set(key, result, minutes * 60)
    cache.set(stale_key, result, 24 * 3600)
    return result
