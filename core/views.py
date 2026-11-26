import mimetypes
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import views as auth_views
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_GET, require_POST

from . import airtable, careers_feed, content
from .forms import CandidateForm, ContactForm, VacancyForm
from .models import RESUME_PACKAGES, CandidateRegistration
from .notifications import send_candidate_confirmation, send_enquiry_notification

SERVICE_KEYS = {key for key, _label in CandidateRegistration.SUPPORT_CHOICES}
# Employers page industry cards -> Airtable "Industry / Sector" option.
INDUSTRY_PRESELECT = {
    "healthcare": "Healthcare",
    "hospitality": "Hospitality",
    "construction": "Construction & Trades",
}


def home(request):
    return render(request, "core/home.html", {
        "highlights": content.HOME_HIGHLIGHTS,
        "services": content.HOME_SERVICES,
    })


def about(request):
    return render(request, "core/about.html", {
        "approach": content.ABOUT_APPROACH,
        "values": content.ABOUT_VALUES,
        "industries": content.INDUSTRIES,
    })


def employers(request):
    form = VacancyForm()
    # Industry cards on the page pre-select the closest Airtable industry option.
    industry = INDUSTRY_PRESELECT.get(request.GET.get("industry", ""))
    if industry:
        form = VacancyForm(initial={"industry": industry})
    if request.method == "POST":
        form = VacancyForm(request.POST)
        if form.is_valid():
            enquiry = form.save()
            airtable.push(enquiry)
            send_enquiry_notification(enquiry, request)
            messages.success(request, "Thank you – your vacancy has been received. "
                                      "We'll be in touch shortly to discuss your hiring needs.")
            return redirect(reverse("core:employers") + "?sent=1#vacancy")
    return render(request, "core/employers.html", {
        "form": form,
        "sent": request.GET.get("sent"),
        "benefits": content.EMPLOYER_BENEFITS,
        "industries": content.INDUSTRIES,
        "process": content.EMPLOYER_PROCESS,
    })


def candidates(request):
    """Candidates page. ?service=resume|interview|career pre-selects that support option;
    ?package=<slug> pre-selects a resume package. Current opportunities come from the careers page."""
    service = request.GET.get("service")
    initial = {}
    if service in SERVICE_KEYS:
        initial["support"] = [service]
    package = request.GET.get("package")
    if package in {k for k, _ in RESUME_PACKAGES}:
        initial.update(support=["resume"], resume_package=package)
    form = CandidateForm(initial=initial or None)

    if request.method == "POST":
        form = CandidateForm(request.POST, request.FILES)
        if form.is_valid():
            registration = form.save()
            airtable.push(registration)
            send_enquiry_notification(registration, request)
            send_candidate_confirmation(registration, request)
            messages.success(request, "Thank you for registering your interest. We've received your details "
                                      "and emailed you a copy. We'll be in touch.")
            return redirect(reverse("core:candidates") + "?sent=1#register")

    return render(request, "core/candidates.html", {
        "form": form,
        "sent": request.GET.get("sent"),
        "external_jobs": careers_feed.jobs(),
        "careers_page_url": careers_feed.careers_page_url(),
        "selected_service": service if service in SERVICE_KEYS else "",
        "price_note": content.PRICE_NOTE,
        "benefits": content.CANDIDATE_BENEFITS,
        "services": content.CAREER_SERVICES,
        "process": content.CANDIDATE_PROCESS,
    })


def contact(request):
    form = ContactForm()
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            enquiry = form.save()
            send_enquiry_notification(enquiry, request)
            messages.success(request, "Thank you – your message has been sent. We'll get back to you soon.")
            return redirect(reverse("core:contact") + "?sent=1#enquiry")
    return render(request, "core/contact.html", {"form": form, "sent": request.GET.get("sent")})


def career_services(request):
    """Resume writing, interview preparation and career counselling with prices. Every button opens the
    candidate registration form (Candidates page) with that service, and package, already chosen."""
    return render(request, "core/career_services.html", {
        "packages": content.RESUME_PACKAGES,
        "interview": content.INTERVIEW_SERVICE,
        "counselling": content.COUNSELLING_SERVICE,
        "price_note": content.PRICE_NOTE,
    })


def privacy(request):
    return render(request, "core/privacy.html")


def resume_download(request, pk):
    """Staff-only: open a candidate's CV. Wrapped in admin_view() in core/admin_site.py, so only
    signed-in staff with permission to view candidates can reach it."""
    if not request.user.has_perm("core.view_candidateregistration"):
        raise Http404
    obj = get_object_or_404(CandidateRegistration, pk=pk)
    if not obj.resume:
        raise Http404
    try:
        handle = obj.resume.open("rb")
    except FileNotFoundError:
        raise Http404
    ext = Path(obj.resume.name).suffix.lower()
    safe_name = "".join(c for c in obj.full_name if c.isalnum() or c in " -_").strip().replace(" ", "-") or "candidate"
    response = FileResponse(handle, as_attachment=True, filename=f"CV-{safe_name}{ext}",
                            content_type=mimetypes.guess_type(f"x{ext}")[0] or "application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


@require_GET
def robots_txt(request):
    sitemap = request.build_absolute_uri(reverse("sitemap"))
    lines = ["User-agent: *", "Disallow: /admin/", "Allow: /", f"Sitemap: {sitemap}"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


# ---------------------------------------------------------------------------
# Admin session helpers (used by static/core/admin_shell.js)
# ---------------------------------------------------------------------------
@require_POST
def session_ping(request):
    """Called by the admin page while the person is active, so the session does not time out."""
    if not (request.user.is_authenticated and request.user.is_staff):
        return HttpResponse(status=401)
    return HttpResponse(status=204)


@require_POST
def session_expire(request):
    """Called by the admin page when the idle time is up: ends the session."""
    if request.user.is_authenticated:
        auth_logout(request)
    return HttpResponse(status=204)


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    success_url = reverse_lazy("password_reset_complete")
