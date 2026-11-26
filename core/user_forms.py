"""Simple forms for adding and editing admin users: details, a role (Staff or Administrator) and how the
password is set. Replaces Django's raw permission lists, which were confusing."""

import re
import secrets

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Group
from django.utils.html import format_html, format_html_join

User = get_user_model()

STAFF, ADMIN = "staff", "admin"
ROLES = [
    (STAFF, "Staff", "Sees candidates, vacancies and general enquiries, opens CVs, and updates status, "
                     "assignment and notes. Can't delete records, download reports or manage users."),
    (ADMIN, "Admin", "Everything Staff can do, plus reports, deleting enquiries, managing users, "
                     "suspending accounts and the account history."),
]
ROLE_ICONS = {
    STAFF: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.5-7 8-7s8 3 8 7"/>',
    ADMIN: '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
}
ROLE_HELP = ("Staff get the Staff role's permissions (work on enquiries); Admin can do everything. "
             "Hover over a role to see what it allows.")
EMAIL_LINK, SET_NOW = "email", "set"
PASSWORD_CHOICES = [
    (EMAIL_LINK, "Email them a link (recommended)",
     "They choose their own password. The link works once and expires in 3 days."),
    (SET_NOW, "Set a password now", "You choose it and tell them. Ask them to change it after signing in."),
]


class CardRadio(forms.RadioSelect):
    """Radio buttons shown as cards with a title and a short explanation (compact=True: a name and an icon
    only, with the explanation as a tooltip)."""

    def __init__(self, cards, *args, compact=False, icons=None, **kwargs):
        self.cards, self.compact, self.icons = cards, compact, icons or {}
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        disabled = (attrs or {}).get("disabled") or self.attrs.get("disabled")
        if self.compact:
            rows = [(text, name, key, "checked" if str(value) == key else "", "disabled" if disabled else "",
                     format_html('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                                 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                                 '{}</svg>', format_html(self.icons.get(key, ""))), title)
                    for key, title, text in self.cards]
            return format_html('<div class="sd-roles" role="radiogroup">{}</div>', format_html_join(
                "", '<label class="sd-role" title="{}"><input type="radio" name="{}" value="{}" {} {}>'
                    '<span>{}{}</span></label>', rows))
        rows = [(name, key, "checked" if str(value) == key else "", "disabled" if disabled else "", title, text)
                for key, title, text in self.cards]
        return format_html('<div class="sd-cards" role="radiogroup">{}</div>', format_html_join(
            "", '<label class="sd-card"><input type="radio" name="{}" value="{}" {} {}>'
                '<span class="sd-card__body"><strong>{}</strong><span>{}</span></span></label>', rows))


def role_of(user):
    return ADMIN if user.is_superuser else STAFF


def apply_role(user, role):
    user.is_staff = True
    user.is_superuser = role == ADMIN
    user.save(update_fields=["is_staff", "is_superuser"])
    group = Group.objects.filter(name="Staff").first()
    if group:
        (user.groups.add if role == STAFF else user.groups.remove)(group)


def _role_field():
    return forms.ChoiceField(label="Role", choices=[(k, t) for k, t, _ in ROLES], initial=STAFF,
                             help_text=ROLE_HELP, widget=CardRadio(ROLES, compact=True, icons=ROLE_ICONS))


def _clean_email(form):
    email = (form.cleaned_data.get("email") or "").strip()
    others = User.objects.filter(email__iexact=email)
    if form.instance.pk:
        others = others.exclude(pk=form.instance.pk)
    if email and others.exists():
        raise forms.ValidationError("Another user already has this email address.")
    return email


class TeamMemberAddForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(label="Email address")
    username = forms.CharField(max_length=150, required=False,
                               widget=forms.TextInput(attrs={"placeholder": "Optional"}))
    role = _role_field()
    password_setup = forms.ChoiceField(label="Password", choices=[(k, t) for k, t, _ in PASSWORD_CHOICES],
                                       initial=EMAIL_LINK, widget=CardRadio(PASSWORD_CHOICES))
    password1 = forms.CharField(label="New password", required=False, strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="At least 8 characters, not too common and not all numbers.")
    password2 = forms.CharField(label="Type it again", required=False, strip=False,
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "username")

    def clean_email(self):
        return _clean_email(self)

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if username:
            if not re.fullmatch(r"[\w.@+-]+", username):
                raise forms.ValidationError("Use letters, numbers and @ . + - _ only.")
            if User.objects.filter(username__iexact=username).exists():
                raise forms.ValidationError("That username is taken.")
        return username

    def clean(self):
        data = super().clean()
        if not data.get("username") and data.get("email"):
            base = re.sub(r"[^\w.+-]", "", data["email"].split("@")[0]).lower()[:140] or "user"
            name, n = base, 2
            while User.objects.filter(username__iexact=name).exists():
                name, n = f"{base}{n}", n + 1
            data["username"] = name
        if data.get("password_setup") == SET_NOW:
            p1, p2 = data.get("password1"), data.get("password2")
            if not p1:
                self.add_error("password1", "Enter a password, or choose to email them a link.")
            elif p1 != p2:
                self.add_error("password2", "The two passwords don't match.")
            else:
                user = User(username=data.get("username", ""), email=data.get("email", ""),
                            first_name=data.get("first_name", ""), last_name=data.get("last_name", ""))
                try:
                    password_validation.validate_password(p1, user)
                except forms.ValidationError as e:
                    self.add_error("password1", e)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["username"]
        user.is_staff = True
        user.is_superuser = self.cleaned_data["role"] == ADMIN
        if self.cleaned_data["password_setup"] == SET_NOW:
            user.set_password(self.cleaned_data["password1"])
        else:  # a random password nobody knows; they set their own from the emailed link
            user.set_password(secrets.token_urlsafe(32))
        if commit:
            user.save()
            self.save_m2m()
        return user


class TeamMemberChangeForm(UserChangeForm):
    role = _role_field()

    class Meta(UserChangeForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].help_text = ""
        self.fields["username"].help_text = ""
        if self.instance.pk:
            self.fields["role"].initial = role_of(self.instance)
            if self.request_user and self.request_user.pk == self.instance.pk:
                self.fields["role"].disabled = True
                self.fields["role"].help_text = "You can't change your own access."

    def clean_email(self):
        return _clean_email(self)

    def clean_role(self):
        role = self.cleaned_data["role"]
        if self.instance.is_superuser and role != ADMIN:
            others = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=self.instance.pk)
            if not others.exists():
                raise forms.ValidationError("This is the only active administrator, so it must stay one.")
        return role
