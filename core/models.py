import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


def _same(*labels):
    """Choices whose stored value is the label itself, so they match the Airtable options exactly."""
    return [(label, label) for label in labels]


# ---- Options copied exactly from the SD Recruitment Airtable forms ---------------------------
EMPLOYER_INDUSTRIES = _same("Aged Care & Disability", "Healthcare", "Hospitality", "Construction & Trades",
                            "Retail & Warehousing", "Administration & Office", "Other")
CANDIDATE_INDUSTRIES = _same("Aged Care & Disability", "Healthcare & Nursing", "Hospitality & Tourism",
                             "Construction & Trades", "Retail & Warehousing", "Administration & Office",
                             "Cleaning & Maintenance", "Other")
EMPLOYMENT_TYPES = _same("Full Time", "Part - Time", "Casual", "Temporary / Contract", "Flexible")
VACANCY_COUNTS = _same("1", "2-5", "6-10", "More than 10", "Not sure yet")
VISA_TYPES = _same(
    "Australian Citizen", "Australian Permanent Resident", "New Zealand Citizen (Subclass 444)",
    "Student Visa (Subclass 500)", "Temporary Graduate Visa (Subclass 485)",
    "Working Holiday / Work and Holiday Visa (417/462)", "Employer-Sponsored Visa (482/494/186)",
    "Skilled Visa (189/190/491)", "Partner Visa", "Bridging Visa", "Other Visa", "Offshore Applicant / Unsure",
)
EXPERIENCE_LEVELS = _same("No Experience", "Less than 1 Year", "1–3 Years", "3–5 Years", "More than 5 Years")

RESUME_PACKAGES = [
    ("student", "Student Resume – $50"),
    ("basic", "Basic Resume – $95"),
    ("professional", "Professional Resume – $200"),
    ("executive", "Executive Resume – $350"),
    ("criteria", "Selection Criteria Writing – $35 per criterion"),
]

AIRTABLE_PENDING, AIRTABLE_SENT, AIRTABLE_FAILED, AIRTABLE_OFF = "pending", "sent", "failed", "off"
AIRTABLE_STATUSES = [
    (AIRTABLE_PENDING, "Not sent yet"),
    (AIRTABLE_SENT, "Sent"),
    (AIRTABLE_FAILED, "Failed"),
    (AIRTABLE_OFF, "Airtable not set up"),
]


def resume_path(instance, filename):
    """Store resumes under a random name, so file names never reveal who a CV belongs to."""
    ext = Path(filename).suffix.lower()[:8]
    return f"resumes/{uuid.uuid4().hex}{ext}"


class FollowUp(models.Model):
    """Fields the team works with. Everything else on an enquiry is what the visitor submitted and stays read-only."""

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", limit_choices_to={"is_staff": True, "is_active": True},
        help_text="The staff member handling this record.",
    )
    notes = models.TextField("Internal notes", blank=True,
                             help_text="Only visible to staff, e.g. 'Phone screen 20 Nov, strong fit for chef role'.")
    updated_at = models.DateTimeField("Last updated", auto_now=True)

    class Meta:
        abstract = True


class AirtableCopy(FollowUp):
    """Records that are also sent to Airtable (see core/airtable.py)."""

    airtable_status = models.CharField("Airtable", max_length=10, choices=AIRTABLE_STATUSES, default=AIRTABLE_PENDING)
    airtable_id = models.CharField("Airtable record ID", max_length=30, blank=True)
    airtable_error = models.TextField("Airtable error", blank=True)
    airtable_synced_at = models.DateTimeField("Sent to Airtable", null=True, blank=True)

    class Meta:
        abstract = True


def _list_display(values):
    return ", ".join(values or [])


class Job(models.Model):
    """A current opportunity shown on the Candidates page. Staff add these in the admin."""

    title = models.CharField("Job title", max_length=140)
    industry = models.CharField(max_length=40, choices=CANDIDATE_INDUSTRIES)
    location = models.CharField(max_length=120, help_text="e.g. Osborne Park, WA")
    employment_type = models.CharField(max_length=30, choices=EMPLOYMENT_TYPES, default="Full Time")
    summary = models.TextField(help_text="Two or three short sentences about the role. Keep it brief.")
    is_published = models.BooleanField("Show on website", default=True)
    created_at = models.DateTimeField("Added", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "current opportunity"
        verbose_name_plural = "current opportunities"

    def __str__(self):
        return f"{self.title} – {self.location}"


class VacancyEnquiry(AirtableCopy):
    """'Submit a Vacancy' form on the Employers page. Same fields as the Airtable
    'SD Recruitment | Employer Enquiry Form'."""

    STATUSES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("recruiting", "Recruiting"),
        ("placed", "Placed"),
        ("closed", "Closed"),
    ]

    company = models.CharField("Company name", max_length=160)
    industry = models.CharField("Industry / sector", max_length=40, choices=EMPLOYER_INDUSTRIES)
    contact_name = models.CharField("Contact person", max_length=120, blank=True)
    phone = models.CharField("Mobile number", max_length=30)
    email = models.EmailField("Email address", blank=True)
    position = models.CharField("Position recruiting for", max_length=160)
    employment_types = models.JSONField("Employment type", default=list, blank=True)
    positions_count = models.CharField("Number of vacancies", max_length=20, choices=VACANCY_COUNTS, blank=True)
    location = models.CharField("Work location", max_length=160, blank=True)
    details = models.TextField("Additional requirements or comments", blank=True)
    consent = models.BooleanField("Consent to contact", default=False)
    status = models.CharField(max_length=12, choices=STATUSES, default="new")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "vacancy enquiry"
        verbose_name_plural = "vacancy enquiries"

    def __str__(self):
        return f"{self.company} – {self.position}"

    @property
    def employment_type_display(self):
        return _list_display(self.employment_types)


class CandidateRegistration(AirtableCopy):
    """'Register Your Interest' form on the Candidates page. Same fields as the Airtable
    'SD Recruitment | Talent Registration Form', plus the support requested, CV upload and consent
    from the Candidate Website Content document."""

    SUPPORT_CHOICES = [
        ("jobs", "Job opportunities"),
        ("resume", "Resume support"),
        ("interview", "Interview preparation"),
        ("career", "Career counselling"),
    ]
    STATUSES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("active", "Actively matching"),
        ("placed", "Placed"),
        ("closed", "Closed"),
    ]

    full_name = models.CharField(max_length=120)
    phone = models.CharField("Phone number", max_length=30)
    email = models.EmailField("Email address")
    location = models.CharField("Country / location", max_length=160)
    visa_type = models.CharField("Visa type", max_length=60, choices=VISA_TYPES, blank=True)
    preferred_location = models.CharField("Preferred job location", max_length=160, blank=True)
    industry = models.CharField("Industry / job category", max_length=40, choices=CANDIDATE_INDUSTRIES)
    position_sought = models.TextField("Position(s) interested in", blank=True)
    employment_types = models.JSONField("Employment type", default=list, blank=True)
    experience = models.CharField("Relevant work experience", max_length=30, choices=EXPERIENCE_LEVELS, blank=True)
    resume = models.FileField("Resume / CV", upload_to=resume_path, blank=True)
    resume_name = models.CharField("Original file name", max_length=200, blank=True, editable=False)
    support_jobs = models.BooleanField("Job opportunities", default=False)
    support_resume = models.BooleanField("Resume support", default=False)
    support_interview = models.BooleanField("Interview preparation", default=False)
    support_career = models.BooleanField("Career counselling", default=False)
    # Career Services details (shown on the form only when the matching service is chosen)
    resume_package = models.CharField("Resume package", max_length=14, choices=RESUME_PACKAGES, blank=True)
    criteria_count = models.PositiveSmallIntegerField("Number of selection criteria", null=True, blank=True)
    preferred_times = models.CharField("Preferred days and times", max_length=200, blank=True,
                                       help_text="For interview preparation or career counselling sessions.")
    job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.SET_NULL, related_name="registrations",
                            verbose_name="Applied for")
    consent = models.BooleanField("Consent to be contacted", default=False)
    status = models.CharField(max_length=12, choices=STATUSES, default="new")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "candidate registration"
        verbose_name_plural = "candidate registrations"

    def __str__(self):
        first = (self.position_sought or "").splitlines()[0][:60] if self.position_sought else self.industry
        return f"{self.full_name} – {first}"

    @property
    def support_list(self):
        return [label for key, label in self.SUPPORT_CHOICES if getattr(self, f"support_{key}")]

    @property
    def package_summary(self):
        """e.g. 'Selection Criteria Writing – $35 per criterion × 4'."""
        if not self.resume_package:
            return ""
        text = self.get_resume_package_display()
        if self.resume_package == "criteria" and self.criteria_count:
            text += f" × {self.criteria_count}"
        return text

    @property
    def employment_type_display(self):
        return _list_display(self.employment_types)


class ContactEnquiry(FollowUp):
    """General enquiry form on the Contact Us page."""

    ENQUIRER_TYPES = [
        ("employer", "An employer"),
        ("candidate", "A candidate"),
        ("other", "Other"),
    ]
    STATUSES = [("new", "New"), ("contacted", "Contacted"), ("closed", "Closed")]

    name = models.CharField(max_length=120)
    email = models.EmailField("Email address")
    phone = models.CharField("Contact number", max_length=30, blank=True)
    enquirer_type = models.CharField("I am", max_length=12, choices=ENQUIRER_TYPES, default="other")
    message = models.TextField()
    status = models.CharField(max_length=12, choices=STATUSES, default="new")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "contact enquiry"
        verbose_name_plural = "contact enquiries"

    def __str__(self):
        return f"{self.name} – {self.get_enquirer_type_display()}"

