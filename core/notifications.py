import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone

from .models import CandidateRegistration, ContactEnquiry, VacancyEnquiry

logger = logging.getLogger(__name__)

FIELDS = {
    VacancyEnquiry: ("New vacancy", ["company", "industry", "contact_name", "phone", "email", "position",
                                    "employment_types", "positions_count", "location", "details", "consent"]),
    CandidateRegistration: ("New candidate registration", ["full_name", "phone", "email", "location", "visa_type",
                                                          "preferred_location", "industry", "position_sought",
                                                          "employment_types", "experience", "job"]),
    ContactEnquiry: ("New contact enquiry", ["name", "email", "phone", "enquirer_type", "message"]),
}


def _value(obj, field):
    display = getattr(obj, f"get_{field}_display", None)
    value = display() if display else getattr(obj, field)
    if isinstance(value, list):
        value = ", ".join(value)
    if isinstance(value, bool):
        value = "Yes" if value else "No"
    return value if value not in (None, "") else "-"


def _subject(obj):
    if isinstance(obj, VacancyEnquiry):
        return f"New vacancy: {obj.position} – {obj.company}"
    if isinstance(obj, CandidateRegistration):
        return f"New candidate: {obj.full_name} – {obj.industry}"
    return f"New website enquiry from {obj.name}"


def send_enquiry_notification(obj, request=None):
    """Email the business inbox about a new submission. Never raises; does nothing when no inbox is set."""
    if not settings.ENQUIRY_NOTIFICATION_EMAILS:
        return False
    title, fields = FIELDS[type(obj)]
    lines = [title, "=" * len(title), ""]
    for field in fields:
        label = str(obj._meta.get_field(field).verbose_name)
        lines.append(f"{label[:1].upper() + label[1:]}: {_value(obj, field)}")
    if isinstance(obj, CandidateRegistration):
        lines.append(f"Support requested: {', '.join(obj.support_list) or '-'}")
        lines.append(f"Resume / CV: {'attached in the admin' if obj.resume else 'not provided'}")
        lines.append("Consent to be contacted: yes")
    lines += ["", f"Received: {timezone.localtime(obj.created_at):%d %b %Y %I:%M %p}"]
    admin_path = reverse(f"admin:core_{obj._meta.model_name}_change", args=[obj.pk])
    base = settings.SITE_URL.rstrip("/") or (request.build_absolute_uri("/").rstrip("/") if request else "")
    lines.append(f"Open in the admin: {base}{admin_path}")
    try:
        EmailMessage(
            subject=_subject(obj),
            body="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=settings.ENQUIRY_NOTIFICATION_EMAILS,
            reply_to=[obj.email] if obj.email else None,
        ).send()
        return True
    except Exception:  # pragma: no cover - depends on mail server
        logger.exception("Failed to send notification for %s", obj)
        return False
