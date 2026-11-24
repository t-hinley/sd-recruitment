"""CSV and PDF exports of website enquiries for the admin Reports page.

Each report is defined once (REPORTS below): its records and its columns. A column marked for the PDF
also appears in the PDF table; the CSV always has every column.
"""

import csv
import io
from xml.sax.saxutils import escape

from django import forms
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from .models import CandidateRegistration, ContactEnquiry, VacancyEnquiry

CANDIDATES = "candidates"
VACANCIES = "vacancies"
CONTACTS = "contact"
CSV, PDF = "csv", "pdf"

REPORT_CARDS = {
    CANDIDATES: ("Candidates", "Candidate registrations, with industry, visa type, experience, support requested and status.",
                 "candidateregistration"),
    VACANCIES: ("Vacancies", "Vacancies submitted by employers, with position, industry, location and status.",
                "vacancyenquiry"),
    CONTACTS: ("Contact enquiries", "General messages sent from the Contact Us page.", "contactenquiry"),
}
FORMATS = [(CSV, "CSV"), (PDF, "PDF")]
FORMAT_HELP = {CSV: "Opens in Excel. Every field.", PDF: "Ready to print or share. Main fields."}


class ReportForm(forms.Form):
    report = forms.ChoiceField(choices=[(k, v[0]) for k, v in REPORT_CARDS.items()])
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    format = forms.ChoiceField(choices=FORMATS, required=False)

    def clean(self):
        d = super().clean()
        if d.get("date_from") and d.get("date_to") and d["date_from"] > d["date_to"]:
            self.add_error("date_to", "The end date must be on or after the start date.")
        d["format"] = d.get("format") or CSV
        return d


def safe(value):
    """Stop spreadsheet programs from running a cell as a formula (CSV injection)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def handler(e):
    u = e.assigned_to
    return (u.get_full_name() or u.get_username()) if u else ""


def received(e):
    return timezone.localtime(e.created_at).strftime("%d/%m/%Y %I:%M %p")


def received_date(e):
    return timezone.localtime(e.created_at).strftime("%d/%m/%Y")


# Shorter header or value in the PDF table, where columns are narrow.
PDF_HEADERS = {"CV provided": "CV", "Relevant work experience": "Experience", "Number of vacancies": "Vacancies"}
PDF_VALUES = {received: received_date}


def yes_no(v):
    return "Yes" if v else "No"


# (header, value, PDF column width in mm or None = CSV only)
REPORTS = {
    CANDIDATES: {
        "title": "Candidates",
        "queryset": lambda: CandidateRegistration.objects.select_related("assigned_to", "job"),
        "statuses": CandidateRegistration.STATUSES,
        "columns": [
            ("Received", received, 18),
            ("Full name", lambda e: e.full_name, 28),
            ("Phone number", lambda e: e.phone, 24),
            ("Email address", lambda e: e.email, 42),
            ("Country / location", lambda e: e.location, 24),
            ("Visa type", lambda e: e.visa_type, 24),
            ("Preferred job location", lambda e: e.preferred_location, None),
            ("Industry / job category", lambda e: e.industry, 24),
            ("Position(s) interested in", lambda e: e.position_sought, None),
            ("Employment type", lambda e: e.employment_type_display, None),
            ("Relevant work experience", lambda e: e.experience, 18),
            ("Applied for", lambda e: e.job.title if e.job else "", None),
            ("Support requested", lambda e: ", ".join(e.support_list), 24),
            ("Resume package", lambda e: e.package_summary, None),
            ("Preferred days and times", lambda e: e.preferred_times, None),
            ("CV provided", lambda e: yes_no(e.resume), 10),
            ("Status", lambda e: e.get_status_display(), 17),
            ("Assigned to", handler, 18),
            ("Internal notes", lambda e: e.notes, None),
        ],
    },
    VACANCIES: {
        "title": "Vacancies",
        "queryset": lambda: VacancyEnquiry.objects.select_related("assigned_to"),
        "statuses": VacancyEnquiry.STATUSES,
        "columns": [
            ("Received", received, 18),
            ("Company name", lambda e: e.company, 32),
            ("Industry / sector", lambda e: e.industry, 26),
            ("Contact person", lambda e: e.contact_name, 26),
            ("Mobile number", lambda e: e.phone, 24),
            ("Email address", lambda e: e.email, 34),
            ("Position recruiting for", lambda e: e.position, 32),
            ("Employment type", lambda e: e.employment_type_display, 28),
            ("Number of vacancies", lambda e: e.positions_count, 19),
            ("Work location", lambda e: e.location, None),
            ("Additional requirements or comments", lambda e: e.details, None),
            ("Consent to contact", lambda e: yes_no(e.consent), None),
            ("Status", lambda e: e.get_status_display(), 17),
            ("Assigned to", handler, 17),
            ("Internal notes", lambda e: e.notes, None),
        ],
    },
    CONTACTS: {
        "title": "Contact enquiries",
        "queryset": lambda: ContactEnquiry.objects.select_related("assigned_to"),
        "statuses": ContactEnquiry.STATUSES,
        "columns": [
            ("Received", received, 18),
            ("Name", lambda e: e.name, 32),
            ("Email address", lambda e: e.email, 50),
            ("Phone", lambda e: e.phone, 24),
            ("I am", lambda e: e.get_enquirer_type_display(), 20),
            ("Message", lambda e: e.message, 93),
            ("Status", lambda e: e.get_status_display(), 18),
            ("Assigned to", handler, 18),
            ("Internal notes", lambda e: e.notes, None),
        ],
    },
}


def _records(report, date_from, date_to):
    qs = REPORTS[report]["queryset"]()
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return qs.order_by("-created_at")


def _filename(report, ext):
    return f"sd-recruitment-{report}-{timezone.localdate().isoformat()}.{ext}"


def response(report, date_from=None, date_to=None, fmt=CSV):
    report = report if report in REPORTS else CANDIDATES
    if fmt == PDF:
        return pdf_response(report, date_from, date_to)
    return csv_response(report, date_from, date_to)


def csv_response(report, date_from=None, date_to=None):
    spec = REPORTS[report]
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{_filename(report, "csv")}"'
    response.write("﻿")  # lets Excel read the file as UTF-8
    writer = csv.writer(response)
    writer.writerow([h for h, _get, _w in spec["columns"]])
    for e in _records(report, date_from, date_to):
        writer.writerow([safe(get(e)) for _h, get, _w in spec["columns"]])
    return response


def _period(date_from, date_to):
    fmt = lambda d: d.strftime("%d %b %Y").lstrip("0")  # noqa: E731
    if date_from and date_to:
        return f"{fmt(date_from)} – {fmt(date_to)}"
    if date_from:
        return f"From {fmt(date_from)}"
    if date_to:
        return f"Up to {fmt(date_to)}"
    return "All dates"


def pdf_response(report, date_from=None, date_to=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    spec = REPORTS[report]
    cols = [(PDF_HEADERS.get(h, h), PDF_VALUES.get(get, get), w) for h, get, w in spec["columns"] if w]
    records = list(_records(report, date_from, date_to))
    blue, ink, muted, line, grey = (colors.HexColor(c) for c in ("#304B98", "#1B2440", "#5A6480", "#E1E6EF", "#F3F5F8"))

    base = ParagraphStyle("base", fontName="Helvetica", fontSize=7.6, leading=9.6, textColor=ink)
    head = ParagraphStyle("head", parent=base, fontName="Helvetica-Bold", textColor=colors.white)
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=blue)
    meta = ParagraphStyle("meta", parent=base, fontSize=9, leading=12, textColor=muted)
    meta_r = ParagraphStyle("meta_r", parent=meta, alignment=TA_RIGHT)

    def cell(value, style=base):
        text = escape("" if value is None else str(value)).replace("\n", "<br/>")
        return Paragraph(text, style)

    # Header: logo, report title and period, totals by status.
    now = timezone.localtime().strftime("%d %b %Y, %I:%M %p").lstrip("0")
    logo_path = settings.BASE_DIR / "static" / "images" / "logo.png"
    logo = Image(str(logo_path), width=62 * mm, height=62 * mm * 168 / 843) if logo_path.exists() else ""
    by_status = {}
    for e in records:
        by_status[e.status] = by_status.get(e.status, 0) + 1
    totals = " · ".join(f"{label}: {by_status.get(v, 0)}" for v, label in spec["statuses"])
    header = Table([[logo, Paragraph(f"Generated {escape(now)}", meta_r)]], colWidths=[140 * mm, None])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story = [
        header, Spacer(1, 6 * mm),
        Paragraph(f"{escape(spec['title'])} report", title),
        Paragraph(f"{escape(_period(date_from, date_to))} &nbsp;·&nbsp; <b>{len(records)}</b> "
                  f"record{'s' if len(records) != 1 else ''} &nbsp;·&nbsp; {escape(totals)}", meta),
        Spacer(1, 5 * mm),
    ]

    if records:
        data = [[cell(h, head) for h, _g, _w in cols]]
        data += [[cell(get(e)) for _h, get, _w in cols] for e in records]
        table = LongTable(data, colWidths=[w * mm for _h, _g, w in cols], repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), blue),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, line),
        ]
        style += [("BACKGROUND", (0, r), (-1, r), grey) for r in range(2, len(data), 2)]
        table.setStyle(TableStyle(style))
        story.append(table)
    else:
        story.append(Paragraph("No records for this period.", meta))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(doc.leftMargin, 8 * mm,
                          "SD Recruitment · Confidential: contains personal information. Keep private and delete when no longer needed.")
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=15 * mm,
                            title=f"SD Recruitment – {spec['title']} report", author="SD Recruitment")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)

    response = HttpResponse(buf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{_filename(report, "pdf")}"'
    return response
