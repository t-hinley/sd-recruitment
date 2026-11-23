"""CSV exports of website enquiries for the admin Reports page."""

import csv

from django import forms
from django.http import HttpResponse
from django.utils import timezone

from .models import CandidateRegistration, ContactEnquiry, VacancyEnquiry

CANDIDATES = "candidates"
VACANCIES = "vacancies"
CONTACTS = "contact"

REPORT_CARDS = {
    CANDIDATES: ("Candidates", "Candidate registrations, with industry, visa type, experience, support requested and status.",
                 "candidateregistration"),
    VACANCIES: ("Vacancies", "Vacancies submitted by employers, with position, industry, location and status.",
                "vacancyenquiry"),
    CONTACTS: ("Contact enquiries", "General messages sent from the Contact Us page.", "contactenquiry"),
}


class ReportForm(forms.Form):
    report = forms.ChoiceField(choices=[(k, v[0]) for k, v in REPORT_CARDS.items()])
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)

    def clean(self):
        d = super().clean()
        if d.get("date_from") and d.get("date_to") and d["date_from"] > d["date_to"]:
            self.add_error("date_to", "The end date must be on or after the start date.")
        return d


def safe(value):
    """Stop spreadsheet programs from running a cell as a formula (CSV injection)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def handler(e):
    u = e.assigned_to
    return (u.get_full_name() or u.get_username()) if u else ""


def csv_response(report, date_from=None, date_to=None):
    if report == VACANCIES:
        qs = VacancyEnquiry.objects.select_related("assigned_to")
        header = ["Received", "Company name", "Industry / sector", "Contact person", "Mobile number", "Email address",
                  "Position recruiting for", "Employment type", "Number of vacancies", "Work location",
                  "Additional requirements or comments", "Consent to contact", "Status", "Assigned to", "Internal notes"]

        def row(e):
            return [e.created_at, e.company, e.industry, e.contact_name, e.phone, e.email, e.position,
                    e.employment_type_display, e.positions_count, e.location, e.details, "Yes" if e.consent else "No",
                    e.get_status_display(), handler(e), e.notes]
    elif report == CONTACTS:
        qs = ContactEnquiry.objects.select_related("assigned_to")
        header = ["Received", "Name", "Email", "Phone", "I am", "Message", "Status", "Assigned to", "Internal notes"]

        def row(e):
            return [e.created_at, e.name, e.email, e.phone, e.get_enquirer_type_display(), e.message,
                    e.get_status_display(), handler(e), e.notes]
    else:
        report = CANDIDATES
        qs = CandidateRegistration.objects.select_related("assigned_to", "job")
        header = ["Received", "Full name", "Phone number", "Email address", "Country / location", "Visa type",
                  "Preferred job location", "Industry / job category", "Position(s) interested in", "Employment type",
                  "Relevant work experience", "Applied for", "Support requested", "CV provided", "Status",
                  "Assigned to", "Internal notes"]

        def row(e):
            return [e.created_at, e.full_name, e.phone, e.email, e.location, e.visa_type, e.preferred_location,
                    e.industry, e.position_sought, e.employment_type_display, e.experience,
                    e.job.title if e.job else "", ", ".join(e.support_list), "Yes" if e.resume else "No",
                    e.get_status_display(), handler(e), e.notes]

    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    stamp = timezone.localdate().isoformat()
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="sd-recruitment-{report}-{stamp}.csv"'
    response.write("﻿")  # lets Excel read the file as UTF-8
    writer = csv.writer(response)
    writer.writerow(header)
    for e in qs.order_by("-created_at"):
        cells = row(e)
        cells[0] = timezone.localtime(cells[0]).strftime("%d/%m/%Y %I:%M %p")
        writer.writerow([safe(c) for c in cells])
    return response
