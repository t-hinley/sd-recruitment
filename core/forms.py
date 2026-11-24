import re
from pathlib import Path

from django import forms
from django.conf import settings

from .models import (CANDIDATE_INDUSTRIES, EMPLOYER_INDUSTRIES, EMPLOYMENT_TYPES, EXPERIENCE_LEVELS,
                     VACANCY_COUNTS, VISA_TYPES, CandidateRegistration, ContactEnquiry, Job, ServiceRequest,
                     VacancyEnquiry)

PHONE_RE = re.compile(r"^[0-9 +()\-]{8,20}$")

# First bytes of the allowed document types, so a renamed program or image is not accepted as a CV.
SIGNATURES = {
    "pdf": [b"%PDF"],
    "doc": [b"\xd0\xcf\x11\xe0"],
    "docx": [b"PK\x03\x04"],
    "odt": [b"PK\x03\x04"],
    "rtf": [b"{\\rtf"],
}


class HoneypotMixin(forms.Form):
    """Hidden field that real visitors leave empty; bots tend to fill it."""

    website = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "tabindex": "-1", "autocomplete": "off",
    }))

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return ""

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if phone and not PHONE_RE.match(phone):
            raise forms.ValidationError("Please enter a valid phone number.")
        return phone


def clean_resume_file(f):
    """Check an uploaded resume: allowed type, size limit, and that it really is a document."""
    if not f or not hasattr(f, "size"):
        return f
    ext = Path(f.name).suffix.lower().lstrip(".")
    if ext not in settings.RESUME_EXTENSIONS:
        raise forms.ValidationError("Please upload a PDF or Word document (.pdf, .doc or .docx).")
    if f.size > settings.RESUME_MAX_MB * 1024 * 1024:
        raise forms.ValidationError(f"The file is too large. The limit is {settings.RESUME_MAX_MB} MB.")
    if ext in SIGNATURES:
        head = f.read(8)
        f.seek(0)
        if not any(head.startswith(sig) for sig in SIGNATURES[ext]):
            raise forms.ValidationError("This file doesn't look like a valid document. Please try another file.")
    return f


def _choices(placeholder, choices):
    return [("", placeholder)] + list(choices)


def employment_type_field():
    return forms.MultipleChoiceField(
        label="Employment type", required=False, choices=EMPLOYMENT_TYPES,
        widget=forms.CheckboxSelectMultiple, help_text="Choose all that apply.",
    )


class VacancyForm(HoneypotMixin, forms.ModelForm):
    """Same fields, options and required fields as the Airtable Employer Enquiry Form."""

    prefix = "vacancy"
    employment_types = employment_type_field()

    class Meta:
        model = VacancyEnquiry
        fields = [
            "company", "industry", "contact_name", "phone", "email", "position",
            "employment_types", "positions_count", "location", "details", "consent",
        ]
        labels = {
            "company": "Company name",
            "industry": "Industry / sector",
            "contact_name": "Contact person",
            "phone": "Mobile number",
            "position": "Position recruiting for",
            "positions_count": "Number of vacancies",
            "details": "Additional requirements or comments",
        }
        widgets = {
            "company": forms.TextInput(attrs={"autocomplete": "organization"}),
            "contact_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "04xx xxx xxx"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@business.com.au"}),
            "position": forms.TextInput(attrs={"placeholder": "e.g. Support Worker, Chef, Site Supervisor"}),
            "location": forms.TextInput(attrs={"placeholder": "Suburb and state"}),
            "details": forms.Textarea(attrs={"rows": 4, "placeholder": "Experience, licences, shifts, start date, pay range – anything that helps"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["industry"].choices = _choices("Select an industry", EMPLOYER_INDUSTRIES)
        self.fields["positions_count"].choices = _choices("Select", VACANCY_COUNTS)
        self.fields["consent"].label = ("I agree to be contacted by SD Recruitment regarding my recruitment "
                                        "enquiry using the contact details provided.")


class CandidateForm(HoneypotMixin, forms.ModelForm):
    """The Airtable Talent Registration Form fields, plus support requested, CV and consent."""

    prefix = "candidate"

    employment_types = employment_type_field()
    support = forms.MultipleChoiceField(
        label="What can we help with?",
        choices=CandidateRegistration.SUPPORT_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Please choose at least one option."},
    )
    consent = forms.BooleanField(
        required=True,
        label="I agree to SD Recruitment storing my details and contacting me about recruitment "
              "opportunities and services, as described in the Privacy Policy.",
        error_messages={"required": "Please tick this box so we can contact you."},
    )
    job = forms.ModelChoiceField(queryset=Job.objects.none(), required=False, widget=forms.HiddenInput)

    class Meta:
        model = CandidateRegistration
        fields = [
            "full_name", "phone", "email", "location", "visa_type", "preferred_location", "industry",
            "position_sought", "employment_types", "experience", "resume", "job", "consent",
        ]
        labels = {
            "full_name": "Full name",
            "location": "Country / location",
            "industry": "Industry / job category",
        }
        help_texts = {
            "visa_type": "Your current visa type or residency status in Australia. "
                         "If you are applying from overseas, select “Offshore Applicant / Unsure”.",
            "position_sought": "e.g. Support Worker, Registered Nurse, Chef or Warehouse Assistant.",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "04xx xxx xxx"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@email.com"}),
            "location": forms.TextInput(attrs={"placeholder": "e.g. Perth WA, or Manila, Philippines"}),
            "preferred_location": forms.TextInput(attrs={"placeholder": "e.g. Perth metro, regional WA, anywhere"}),
            "position_sought": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["visa_type"].choices = _choices("Select your visa type", VISA_TYPES)
        self.fields["industry"].choices = _choices("Select an industry", CANDIDATE_INDUSTRIES)
        self.fields["experience"].choices = _choices("Select", EXPERIENCE_LEVELS)
        self.fields["job"].queryset = Job.objects.filter(is_published=True)
        exts = ", ".join(f".{e}" for e in settings.RESUME_EXTENSIONS)
        self.fields["resume"].widget.attrs["accept"] = exts
        self.fields["resume"].help_text = (
            f"Optional. PDF or Word document, up to {settings.RESUME_MAX_MB} MB. "
            "No resume yet? Leave this empty – you can send it later."
        )

    def clean_resume(self):
        return clean_resume_file(self.cleaned_data.get("resume"))

    def save(self, commit=True):
        obj = super().save(commit=False)
        chosen = set(self.cleaned_data.get("support") or [])
        for key, _label in CandidateRegistration.SUPPORT_CHOICES:
            setattr(obj, f"support_{key}", key in chosen)
        f = self.cleaned_data.get("resume")
        if f and hasattr(f, "name"):
            obj.resume_name = Path(f.name).name[:200]
        if commit:
            obj.save()
        return obj


class ContactForm(HoneypotMixin, forms.ModelForm):
    prefix = "contact"

    class Meta:
        model = ContactEnquiry
        fields = ["name", "email", "phone", "enquirer_type", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@email.com"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "Optional"}),
            "enquirer_type": forms.RadioSelect,
            "message": forms.Textarea(attrs={"rows": 5, "placeholder": "How can we help?"}),
        }


class ServiceRequestForm(HoneypotMixin, forms.ModelForm):
    """Request form on the Career Services page. The package is needed for resume writing, and the number
    of criteria for Selection Criteria Writing."""

    prefix = "service"

    consent = forms.BooleanField(
        required=True,
        label="I agree to SD Recruitment storing my details and contacting me about this request, "
              "as described in the Privacy Policy.",
        error_messages={"required": "Please tick this box so we can contact you."},
    )

    class Meta:
        model = ServiceRequest
        fields = ["service", "package", "criteria_count", "full_name", "email", "phone", "role",
                  "preferred_times", "resume", "details", "consent"]
        labels = {"full_name": "Full name"}
        widgets = {
            "service": forms.RadioSelect,
            "criteria_count": forms.NumberInput(attrs={"min": 1, "max": 50, "inputmode": "numeric"}),
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@email.com"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "04xx xxx xxx"}),
            "role": forms.TextInput(attrs={"placeholder": "e.g. Registered Nurse, Store Manager"}),
            "preferred_times": forms.TextInput(attrs={"placeholder": "e.g. Weekday evenings, or Saturday morning"}),
            "details": forms.Textarea(attrs={"rows": 3, "placeholder": "e.g. the job you're applying for, or your deadline"}),
        }
        help_texts = {
            "preferred_times": "We'll contact you to confirm a time.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].choices = ServiceRequest.SERVICES
        self.fields["package"].choices = _choices("Select a package", ServiceRequest.PACKAGES)
        self.fields["criteria_count"].min_value = 1
        self.fields["criteria_count"].max_value = 50
        exts = ", ".join(f".{e}" for e in settings.RESUME_EXTENSIONS)
        self.fields["resume"].widget.attrs["accept"] = exts
        self.fields["resume"].help_text = (f"Optional. If you have one, PDF or Word document up to "
                                           f"{settings.RESUME_MAX_MB} MB.")

    def clean_resume(self):
        return clean_resume_file(self.cleaned_data.get("resume"))

    def clean(self):
        d = super().clean()
        service = d.get("service")
        if service == "resume":
            if not d.get("package"):
                self.add_error("package", "Please choose a resume package.")
            elif d.get("package") == "criteria" and not d.get("criteria_count"):
                self.add_error("criteria_count", "Please tell us how many selection criteria you need.")
        else:
            d["package"] = ""
        if d.get("package") != "criteria":
            d["criteria_count"] = None
        if service == "resume":
            d["preferred_times"] = ""
        return d

    def save(self, commit=True):
        obj = super().save(commit=False)
        f = self.cleaned_data.get("resume")
        if f and hasattr(f, "name"):
            obj.resume_name = Path(f.name).name[:200]
        if commit:
            obj.save()
        return obj
