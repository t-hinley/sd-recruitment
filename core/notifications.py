import logging

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone

from .content import BUSINESS
from .models import CandidateRegistration, ContactEnquiry, VacancyEnquiry

logger = logging.getLogger(__name__)

FIELDS = {
    VacancyEnquiry: ("New vacancy", ["company", "industry", "contact_name", "phone", "email", "position",
                                    "employment_types", "positions_count", "location", "details", "consent"]),
    CandidateRegistration: ("New candidate registration", ["full_name", "phone", "email", "location", "visa_type",
                                                          "preferred_location", "industry", "position_sought",
                                                          "employment_types", "experience"]),
    ContactEnquiry: ("New general enquiry", ["name", "email", "phone", "message"]),
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
        if obj.package_summary:
            lines.append(f"Resume package: {obj.package_summary}")
        if obj.preferred_times:
            lines.append(f"Preferred days and times: {obj.preferred_times}")
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


# ---------------------------------------------------------------------------
# Copy of the registration for the candidate
# ---------------------------------------------------------------------------
# The copy goes to whatever address was typed into the form, so it's limited to stop the form being
# used to send email to strangers. Registrations are always saved; only the copy is skipped.
CONFIRM_LIMIT_PER_IP_PER_HOUR = 5
CONFIRM_LIMIT_PER_ADDRESS_PER_DAY = 3


def _allowed(key, limit, seconds):
    cache.add(key, 0, seconds)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, seconds)
        count = 1
    return count <= limit


def send_candidate_confirmation(reg, request=None):
    """Email the candidate a copy of their registration. Never raises."""
    if not getattr(settings, "CANDIDATE_CONFIRMATION_EMAILS", True) or not reg.email:
        return False
    from .security import client_ip
    ip = client_ip(request) if request is not None else "unknown"
    if not (_allowed(f"confirm-ip:{ip}", CONFIRM_LIMIT_PER_IP_PER_HOUR, 3600)
            and _allowed(f"confirm-to:{reg.email.lower()}", CONFIRM_LIMIT_PER_ADDRESS_PER_DAY, 86400)):
        logger.warning("Candidate confirmation not sent to %s: sending limit reached", reg.email)
        return False

    first = reg.full_name.split()[0] if reg.full_name.split() else reg.full_name
    rows = [
        ("Full name", reg.full_name),
        ("Phone number", reg.phone),
        ("Email address", reg.email),
        ("Country / location", reg.location),
        ("Visa type", reg.visa_type),
        ("Preferred job location", reg.preferred_location),
        ("Industry / job category", reg.industry),
        ("Position(s) interested in", reg.position_sought),
        ("Employment type", reg.employment_type_display),
        ("Relevant work experience", reg.experience),
        ("What we can help with", ", ".join(reg.support_list)),
        ("Resume package", reg.package_summary),
        ("Preferred days and times", reg.preferred_times),
        ("Resume / CV", reg.resume_name if reg.resume else "Not provided"),
    ]
    lines = [
        f"Hi {first},",
        "",
        f"Thank you for registering your interest with {BUSINESS['name']}. Here is a copy of the details you sent us.",
        "",
    ]
    lines += [f"{label}: {value}" for label, value in rows if value]
    lines += [
        f"Received: {timezone.localtime(reg.created_at):%d %b %Y %I:%M %p}",
        "",
        "What happens next",
        "Our team will review your details and contact you to discuss your goals and any suitable opportunities"
        " or services. Registering does not guarantee an interview, job offer or placement.",
        "",
        "If anything above needs correcting, just reply to this email.",
        "",
        "Kind regards,",
        BUSINESS["name"],
    ]
    contact = " | ".join(x for x in (BUSINESS.get("phone_display"), BUSINESS.get("email")) if x)
    if contact:
        lines.append(contact)
    lines += ["", "You received this email because this address was entered on our website's candidate form."]

    reply_to = [BUSINESS["email"]] if BUSINESS.get("email") else list(settings.ENQUIRY_NOTIFICATION_EMAILS[:1])
    try:
        EmailMessage(
            subject=f"We've received your registration – {BUSINESS['name']}",
            body="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[reg.email],
            reply_to=reply_to or None,
        ).send()
        return True
    except Exception:  # pragma: no cover - depends on mail server
        logger.exception("Failed to send candidate confirmation to %s", reg.email)
        return False
