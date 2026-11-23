from django.conf import settings

from .content import BUSINESS


def _asset_version():
    """Changes whenever a static file changes, so browsers fetch the new CSS/JS straight away."""
    from pathlib import Path
    folder = Path(settings.BASE_DIR) / "static"
    try:
        return str(int(max(f.stat().st_mtime for f in folder.rglob("*") if f.is_file())))
    except ValueError:
        return "1"


ASSET_V = _asset_version()


def business(request):
    return {
        "business": BUSINESS,
        "google_business_url": settings.GOOGLE_BUSINESS_PROFILE_URL,
        "linkedin_url": settings.LINKEDIN_URL,
        "site_url": settings.SITE_URL.rstrip("/") or request.build_absolute_uri("/").rstrip("/"),
        "asset_v": ASSET_V,
        "staff_idle_seconds": settings.STAFF_IDLE_SECONDS,
    }
