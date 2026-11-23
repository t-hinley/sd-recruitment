"""
Django settings for the SD Recruitment website.

Settings are read from environment variables (optionally loaded from a
``.env`` file in the project root) so the same code runs locally and in
production. See ``.env.example`` for the full list.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Minimal .env loader so no extra dependency is needed."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me-in-production",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "core.admin_config.SDAdminConfig",  # custom-styled admin (core/admin_site.py)
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.business",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-au"
TIME_ZONE = "Australia/Perth"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Email – enquiry notifications
# ---------------------------------------------------------------------------
# In development emails are printed to the console. In production set
# EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD to use SMTP.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend"
    if os.environ.get("EMAIL_HOST")
    else "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)  # port 465
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", not EMAIL_USE_SSL)  # port 587
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "SD Recruitment Website <webmaster@localhost>")
# Inbox(es) that receive website enquiries, comma separated. Empty = no notification emails are sent
# (enquiries are still saved and shown in the admin).
ENQUIRY_NOTIFICATION_EMAILS = env_list("ENQUIRY_NOTIFICATION_EMAILS")

# ---------------------------------------------------------------------------
# Admin sign-in and sessions (same rules as the SD Education admin)
# ---------------------------------------------------------------------------
# Staff are signed out after this many seconds without activity. While the admin is open,
# the page keeps the session alive and shows a "Still there?" notice shortly before time runs out.
STAFF_IDLE_SECONDS = max(60, int(os.environ.get("STAFF_IDLE_SECONDS", "1800")))
SESSION_COOKIE_AGE = STAFF_IDLE_SECONDS
SESSION_SAVE_EVERY_REQUEST = True
# Pause sign-in for 15 minutes after repeated failures from one address or username.
LOGIN_FAIL_WINDOW = 15 * 60
LOGIN_FAIL_LIMIT_IP = 20
LOGIN_FAIL_LIMIT_USER = 5
LOGIN_URL = "admin:login"
# True when the site runs behind Nginx on a VPS (see DEPLOY_VPS.md); not needed on cPanel.
BEHIND_PROXY = env_bool("DJANGO_BEHIND_PROXY", False)

AUTH_PASSWORD_VALIDATORS[1]["OPTIONS"] = {"min_length": 12}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"core": {"handlers": ["console"], "level": "INFO"}},
}

# Optional links shown on the site when set.
GOOGLE_BUSINESS_PROFILE_URL = os.environ.get("GOOGLE_BUSINESS_PROFILE_URL", "")
LINKEDIN_URL = os.environ.get("LINKEDIN_URL", "")
# The public web address, e.g. https://www.sdrecruitment.com.au (used for links in emails, the sitemap
# and search engines). Empty = worked out from each request.
SITE_URL = os.environ.get("SITE_URL", "")

# ---------------------------------------------------------------------------
# Resumes / CVs uploaded by candidates
# ---------------------------------------------------------------------------
# Kept OUTSIDE the static folder and never served directly by the web server: staff open them
# through the admin only (see core/views.py: resume_download).
MEDIA_ROOT = Path(os.environ.get("PRIVATE_MEDIA_ROOT", BASE_DIR / "private_media"))
RESUME_MAX_MB = int(os.environ.get("RESUME_MAX_MB", "5"))
RESUME_EXTENSIONS = ["pdf", "doc", "docx", "rtf", "odt", "txt"]
FILE_UPLOAD_PERMISSIONS = 0o640

# ---------------------------------------------------------------------------
# Airtable: a copy of each vacancy and candidate registration goes to the SD Recruitment base
# (core/airtable.py). Leave AIRTABLE_TOKEN empty to switch it off.
# ---------------------------------------------------------------------------
AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appv3PA1WBgRGxeX5").strip()
AIRTABLE_TABLE = os.environ.get("AIRTABLE_TABLE", "tblZaBP5px3dqWuaD").strip()
AIRTABLE_TIMEOUT = int(os.environ.get("AIRTABLE_TIMEOUT", "8"))

# ---------------------------------------------------------------------------
# Production security
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    # Secure cookies need https. Only for temporary testing over plain http: DJANGO_SECURE_COOKIES=False
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
