import re
from pathlib import Path

from django import forms
from django.conf import settings

from .models import INDUSTRY_CHOICES, CandidateRegistration, ContactEnquiry, Job, VacancyEnquiry

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


def _choices(placeholder, choices):
    return [("", placeholder)] + list(choices)


class VacancyForm(HoneypotMixin, forms.ModelForm):
    prefix = "vacancy"

    class Meta:
        model = VacancyEnquiry
        fields = [
            "contact_name", "company", "email", "phone", "industry", "position",
            "positions_count", "employment_type", "location", "start_timeframe", "details",
        ]
        widgets = {
            "contact_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "company": forms.TextInput(attrs={"autocomplete": "organization"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@business.com.au"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "04xx xxx xxx"}),
            "position": forms.TextInput(attrs={"placeholder": "e.g. Restaurant Manager"}),
            "positions_count": forms.NumberInput(attrs={"min": 1, "max": 99}),
            "location": forms.TextInput(attrs={"placeholder": "Suburb and state"}),
            "start_timeframe": forms.TextInput(attrs={"placeholder": "e.g. As soon as possible, or early March"}),
            "details": forms.Textarea(attrs={"rows": 4, "placeholder": "Key duties, experience needed, hours, pay range – whatever helps us understand the role"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["industry"].choices = _choices("Select an industry", INDUSTRY_CHOICES)
        self.fields["employment_type"].choices = _choices("Select type", VacancyEnquiry.EMPLOYMENT_TYPES)
        self.fields["positions_count"].min_value = 1
        self.fields["positions_count"].max_value = 99


class CandidateForm(HoneypotMixin, forms.ModelForm):
    prefix = "candidate"

    support = forms.MultipleChoiceField(
        label="Support requested",
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
            "full_name", "email", "phone", "location", "position_sought", "industry",
            "experience", "resume", "job", "consent",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@email.com"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "04xx xxx xxx"}),
            "location": forms.TextInput(attrs={"placeholder": "Suburb and state"}),
            "position_sought": forms.TextInput(attrs={"placeholder": "e.g. Chef, Aged Care Worker, Site Supervisor"}),
            "experience": forms.Textarea(attrs={"rows": 4, "placeholder": "Recent roles, years of experience, licences, certificates or qualifications"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["industry"].choices = _choices("Select an industry", INDUSTRY_CHOICES)
        self.fields["job"].queryset = Job.objects.filter(is_published=True)
        exts = ", ".join(f".{e}" for e in settings.RESUME_EXTENSIONS)
        self.fields["resume"].widget.attrs["accept"] = exts
        self.fields["resume"].help_text = (
            f"Optional. PDF or Word document, up to {settings.RESUME_MAX_MB} MB. "
            "No resume yet? Leave this empty – you can send it later."
        )

    def clean_resume(self):
        f = self.cleaned_data.get("resume")
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
