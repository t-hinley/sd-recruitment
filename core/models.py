import uuid
from pathlib import Path

from django.conf import settings
from django.db import models

from .content import INDUSTRIES

INDUSTRY_CHOICES = [(slug, title) for slug, _icon, title, _ex in INDUSTRIES] + [("other", "Other")]


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


class Job(models.Model):
    """A current opportunity shown on the Candidates page. Staff add these in the admin."""

    EMPLOYMENT_TYPES = [
        ("full-time", "Full time"),
        ("part-time", "Part time"),
        ("casual", "Casual"),
        ("contract", "Contract / temporary"),
    ]

    title = models.CharField("Job title", max_length=140)
    industry = models.CharField(max_length=20, choices=INDUSTRY_CHOICES)
    location = models.CharField(max_length=120, help_text="e.g. Osborne Park, WA")
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES, default="full-time")
    summary = models.TextField(help_text="Two or three short sentences about the role. Keep it brief.")
    is_published = models.BooleanField("Show on website", default=True)
    created_at = models.DateTimeField("Added", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "current opportunity"
        verbose_name_plural = "current opportunities"

    def __str__(self):
        return f"{self.title} – {self.location}"


class VacancyEnquiry(FollowUp):
    """'Submit a Vacancy' form on the Employers page."""

    EMPLOYMENT_TYPES = Job.EMPLOYMENT_TYPES + [("unsure", "Not sure yet")]
    STATUSES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("recruiting", "Recruiting"),
        ("placed", "Placed"),
        ("closed", "Closed"),
    ]

    contact_name = models.CharField("Your name", max_length=120)
    company = models.CharField("Business name", max_length=160)
    email = models.EmailField("Email address")
    phone = models.CharField("Contact number", max_length=30)
    industry = models.CharField(max_length=20, choices=INDUSTRY_CHOICES)
    position = models.CharField("Position(s) to fill", max_length=160)
    positions_count = models.PositiveSmallIntegerField("Number of positions", default=1)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES)
    location = models.CharField("Work location", max_length=160)
    start_timeframe = models.CharField("Ideal start date", max_length=80, blank=True)
    details = models.TextField("About the role", blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="new")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "vacancy enquiry"
        verbose_name_plural = "vacancy enquiries"

    def __str__(self):
        return f"{self.company} – {self.position}"


class CandidateRegistration(FollowUp):
    """'Register Your Interest' form on the Candidates page."""

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
    email = models.EmailField("Email address")
    phone = models.CharField("Mobile number", max_length=30)
    location = models.CharField("Current location", max_length=160)
    position_sought = models.CharField("Type of work or position sought", max_length=160)
    industry = models.CharField("Preferred industry", max_length=20, choices=INDUSTRY_CHOICES)
    experience = models.TextField("Relevant experience and qualifications", blank=True)
    resume = models.FileField("Resume / CV", upload_to=resume_path, blank=True)
    resume_name = models.CharField("Original file name", max_length=200, blank=True, editable=False)
    support_jobs = models.BooleanField("Job opportunities", default=False)
    support_resume = models.BooleanField("Resume support", default=False)
    support_interview = models.BooleanField("Interview preparation", default=False)
    support_career = models.BooleanField("Career counselling", default=False)
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
        return f"{self.full_name} – {self.position_sought}"

    @property
    def support_list(self):
        return [label for key, label in self.SUPPORT_CHOICES if getattr(self, f"support_{key}")]


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
