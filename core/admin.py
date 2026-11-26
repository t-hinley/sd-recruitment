"""Enquiry pages in the admin.

What the visitor submitted is read-only for everyone, so the record always shows exactly what was sent.
The team only works with: status, assigned to and internal notes. Enquiries arrive from the website
forms only (no "Add" button), and only administrators can delete them.
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from . import airtable
from .models import (AIRTABLE_FAILED, AIRTABLE_SENT, AuthenticatorDevice, CandidateRegistration, ContactEnquiry,
                     VacancyEnquiry)


def person(user):
    return (user.get_full_name() or user.get_username()) if user else ""


class AssignedFilter(admin.SimpleListFilter):
    """Filter by staff member, shown by full name, with 'Me' and 'Unassigned' first."""
    title = "assigned to"
    parameter_name = "assigned"

    def lookups(self, request, model_admin):
        from django.contrib.auth import get_user_model
        staff = get_user_model().objects.filter(is_staff=True, is_active=True).order_by("first_name", "username")
        return [("me", "Me"), ("none", "Unassigned")] + [(str(u.pk), person(u)) for u in staff]

    def queryset(self, request, queryset):
        v = self.value()
        if v == "me":
            return queryset.filter(assigned_to=request.user)
        if v == "none":
            return queryset.filter(assigned_to__isnull=True)
        if v and v.isdigit():
            return queryset.filter(assigned_to_id=int(v))
        return queryset


FOLLOW_UP = ("Follow-up", {
    "fields": ("status", "assigned_to", "notes", "updated_at"),
    "description": "Only these fields can be changed. The details above are exactly what the visitor sent.",
})


AIRTABLE = ("Airtable copy", {
    "classes": ("collapse",),
    "fields": ("airtable_badge", "airtable_synced_at", "airtable_id", "airtable_error"),
    "description": "A copy of this record is sent to the SD Recruitment Airtable base when it arrives.",
})
SYNC_FIELDS = ("airtable_badge", "airtable_synced_at", "airtable_id", "airtable_error")


class EnquiryAdmin(admin.ModelAdmin):
    list_editable = ("status",)
    list_select_related = ("assigned_to",)
    date_hierarchy = "created_at"
    list_per_page = 50
    actions = ["assign_to_me", "mark_contacted", "mark_closed"]

    # ---- permissions ---------------------------------------------------------------
    def has_add_permission(self, request):
        return False  # enquiries only come from the website forms

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        widget = form.base_fields.get("assigned_to") and form.base_fields["assigned_to"].widget
        if widget is not None:  # plain dropdown: no add/edit/delete/view user icons beside it
            widget.can_add_related = widget.can_change_related = widget.can_delete_related = widget.can_view_related = False
        return form

    def get_readonly_fields(self, request, obj=None):
        return self.submitted_fields + ("updated_at",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "assigned_to":
            from django.contrib.auth import get_user_model
            kwargs["queryset"] = get_user_model().objects.filter(is_staff=True, is_active=True).order_by("first_name", "username")
            field = super().formfield_for_foreignkey(db_field, request, **kwargs)
            field.label_from_instance = person
            field.empty_label = "Unassigned"
            return field
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # ---- columns -------------------------------------------------------------------
    @admin.display(description="Received", ordering="created_at")
    def received(self, obj):
        return timezone.localtime(obj.created_at).strftime("%d %b %Y")

    @admin.display(description="Assigned to", ordering="assigned_to__first_name")
    def handler(self, obj):
        return person(obj.assigned_to) or format_html('<span class="sdmuted">Unassigned</span>')

    @admin.display(description="Email address")
    def email_link(self, obj):
        return format_html('<a href="mailto:{0}">{0}</a>', obj.email)

    @admin.display(description="Phone")
    def phone_link(self, obj):
        if not obj.phone:
            return "-"
        return format_html('<a href="tel:{0}">{1}</a>', obj.phone.replace(" ", ""), obj.phone)

    @admin.display(description="Received")
    def received_full(self, obj):
        return timezone.localtime(obj.created_at).strftime("%d %b %Y, %I:%M %p")

    # ---- bulk actions --------------------------------------------------------------
    @admin.action(description="Assign selected to me")
    def assign_to_me(self, request, queryset):
        n = queryset.update(assigned_to=request.user, updated_at=timezone.now())
        self.message_user(request, f"{n} assigned to you.", messages.SUCCESS)

    @admin.action(description="Mark selected as Contacted")
    def mark_contacted(self, request, queryset):
        n = queryset.update(status="contacted", updated_at=timezone.now())
        self.message_user(request, f"{n} marked as Contacted.", messages.SUCCESS)

    @admin.action(description="Mark selected as Closed")
    def mark_closed(self, request, queryset):
        n = queryset.update(status="closed", updated_at=timezone.now())
        self.message_user(request, f"{n} marked as Closed.", messages.SUCCESS)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.has_change_permission(request):
            for name in ("assign_to_me", "mark_contacted", "mark_closed"):
                actions.pop(name, None)
        return actions


class AirtableAdminMixin:
    """Airtable status column, read-only details and a 'send again' action."""

    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj) + SYNC_FIELDS

    def get_actions(self, request):
        actions = super().get_actions(request)
        if self.has_change_permission(request):
            actions["send_to_airtable"] = self.get_action("send_to_airtable")
        return actions

    @admin.action(description="Send selected to Airtable again")
    def send_to_airtable(self, request, queryset):
        if not airtable.enabled():
            self.message_user(request, "Airtable is not set up yet (add AIRTABLE_TOKEN to .env).", messages.ERROR)
            return
        sent = failed = 0
        for obj in queryset:
            if airtable.push(obj):
                sent += 1
            else:
                failed += 1
        self.message_user(request, f"{sent} in Airtable.", messages.SUCCESS if sent else messages.INFO)
        if failed:
            self.message_user(request, f"{failed} could not be sent. See the Airtable error on each record.",
                              messages.WARNING)

    @admin.display(description="Airtable", ordering="airtable_status")
    def airtable_badge(self, obj):
        tone = {AIRTABLE_SENT: "ok", AIRTABLE_FAILED: "bad"}.get(obj.airtable_status, "wait")
        return format_html('<span class="sdsync {}">{}</span>', tone, obj.get_airtable_status_display())


@admin.register(VacancyEnquiry)
class VacancyEnquiryAdmin(AirtableAdminMixin, EnquiryAdmin):
    list_display = ("company", "position", "industry", "location", "status", "handler", "airtable_badge", "received")
    list_filter = ("status", AssignedFilter, "industry", "positions_count", "airtable_status", "created_at")
    search_fields = ("company", "contact_name", "email", "phone", "position", "location", "details", "notes")
    submitted_fields = ("company", "industry", "contact_name", "phone_link", "email_link", "position",
                        "employment_type_display", "positions_count", "location", "details", "consent",
                        "received_full")
    fieldsets = (
        ("Vacancy details", {"fields": (("company", "industry"), ("contact_name", "phone_link"), "email_link",
                                        ("position", "positions_count"), "employment_type_display", "location",
                                        "details", ("consent", "received_full"))}),
        FOLLOW_UP,
        AIRTABLE,
    )

    @admin.display(description="Employment type")
    def employment_type_display(self, obj):
        return obj.employment_type_display or "-"


@admin.register(CandidateRegistration)
class CandidateRegistrationAdmin(AirtableAdminMixin, EnquiryAdmin):
    list_display = ("full_name", "industry", "location", "support_summary", "cv", "status", "handler",
                    "airtable_badge", "received")
    list_filter = ("status", AssignedFilter, "industry", "visa_type", "experience", "support_jobs",
                   "support_resume", "resume_package", "support_interview", "support_career",
                   "airtable_status", "created_at")
    search_fields = ("full_name", "email", "phone", "location", "preferred_location", "position_sought", "notes")
    list_select_related = ("assigned_to",)
    submitted_fields = ("full_name", "phone_link", "email_link", "location", "visa_type", "preferred_location",
                        "industry", "position_sought", "employment_type_display", "experience",
                        "support_summary", "package_display", "preferred_times", "resume_link", "consent",
                        "received_full")
    fieldsets = (
        ("Candidate details", {"fields": ("full_name", ("phone_link", "email_link"), ("location", "visa_type"),
                                          ("preferred_location", "industry"), "position_sought",
                                          ("employment_type_display", "experience"), "support_summary",
                                          ("package_display", "preferred_times"),
                                          "resume_link", ("consent", "received_full"))}),
        FOLLOW_UP,
        AIRTABLE,
    )

    @admin.display(description="Employment type")
    def employment_type_display(self, obj):
        return obj.employment_type_display or "-"

    @admin.display(description="Support requested")
    def support_summary(self, obj):
        return ", ".join(obj.support_list) or "-"

    @admin.display(description="Resume package")
    def package_display(self, obj):
        return obj.package_summary or "-"

    @admin.display(description="CV", boolean=True)
    def cv(self, obj):
        return bool(obj.resume)

    @admin.display(description="Resume / CV")
    def resume_link(self, obj):
        if not obj.resume:
            return format_html('<span class="sdmuted">Not provided</span>')
        return format_html('<a class="button" href="{}">Download CV</a> <span class="sdmuted">{}</span>',
                           reverse("admin:resume_download", args=[obj.pk]), obj.resume_name)


@admin.register(ContactEnquiry)
class ContactEnquiryAdmin(EnquiryAdmin):
    list_display = ("name", "email", "message_preview", "status", "handler", "received")
    list_filter = ("status", AssignedFilter, "created_at")
    search_fields = ("name", "email", "phone", "message", "notes")
    submitted_fields = ("name", "email_link", "phone_link", "message", "received_full")
    fieldsets = (
        ("Enquiry", {"fields": ("name", ("email_link", "phone_link"), "message", "received_full")}),
        FOLLOW_UP,
    )

    @admin.display(description="Message")
    def message_preview(self, obj):
        return (obj.message[:80] + "…") if len(obj.message) > 80 else obj.message


@admin.register(AuthenticatorDevice)
class AuthenticatorDeviceAdmin(admin.ModelAdmin):
    """Administrators only. Delete a user's authenticator app (e.g. lost phone) and they set it up again at
    their next sign-in. The secret is never shown."""
    list_display = ("user", "confirmed", "confirmed_at", "backup_left", "created_at")
    list_filter = ("confirmed",)
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    fields = ("user", "confirmed", "confirmed_at", "created_at")
    readonly_fields = fields

    @admin.display(description="Backup codes left")
    def backup_left(self, obj):
        return obj.backup_codes.filter(used_at__isnull=True).count()

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ---------------------------------------------------------------------------
# Users: suspend instead of delete, with a permanent account history (core/accounts.py)
# ---------------------------------------------------------------------------
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin  # noqa: E402
from django.shortcuts import get_object_or_404, redirect  # noqa: E402
from django.template.response import TemplateResponse  # noqa: E402
from django.urls import path  # noqa: E402

from . import accounts, user_forms  # noqa: E402
from .models import AccountStatusChange  # noqa: E402

User = get_user_model()


class AccountStatusFilter(admin.SimpleListFilter):
    title = "account status"
    parameter_name = "account"

    def lookups(self, request, model_admin):
        return [("active", "Active"), ("suspended", "Suspended")]

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(is_active=True)
        if self.value() == "suspended":
            return queryset.filter(is_active=False)
        return queryset


class AccountHistoryInline(admin.TabularInline):
    model = AccountStatusChange
    fk_name = "user"
    extra = 0
    can_delete = False
    verbose_name_plural = "Account history (suspensions and reactivations – kept permanently)"
    fields = ("changed_at", "action", "reason", "by")
    readonly_fields = fields

    @admin.display(description="By")
    def by(self, obj):
        return person(obj.changed_by) or "—"

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


if admin.site.is_registered(User):
    admin.site.unregister(User)
# Access is chosen as Staff or Administrator on each user (core/user_forms.py), which manages the
# "Staff" group automatically, so the raw Groups page is hidden to avoid confusion.
from django.contrib.auth.models import Group  # noqa: E402
if admin.site.is_registered(Group):
    admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Accounts are suspended, never deleted, so the record of who did what stays for audits.
    'Active' can only be changed with the Suspend / Reactivate buttons, which ask for a reason."""
    list_display = ("username", "full_name", "email", "account_badge", "role", "last_login")
    list_filter = (AccountStatusFilter, "is_superuser")
    inlines = [AccountHistoryInline]
    actions = ["suspend_selected", "reactivate_selected"]
    change_form_template = "admin/user_change_form.html"
    add_form_template = "admin/user_add_form.html"
    form = user_forms.TeamMemberChangeForm
    add_form = user_forms.TeamMemberAddForm
    fieldsets = (
        ("Their details", {"fields": ("first_name", "last_name", "email", "username")}),
        ("What they can do", {"fields": ("role",)}),
        ("Sign-in", {"fields": ("password", "account_status", "two_step", "last_login", "date_joined")}),
    )
    add_fieldsets = (
        ("Their details", {"fields": ("first_name", "last_name", "email", "username")}),
        ("What they can do", {"fields": ("role",)}),
        ("How they get their password", {"fields": ("password_setup", "password1", "password2")}),
    )
    readonly_fields = ("account_status", "two_step", "last_login", "date_joined")

    @admin.display(description="Name", ordering="first_name")
    def full_name(self, obj):
        return obj.get_full_name()

    @admin.display(description="Account", ordering="is_active")
    def account_badge(self, obj):
        if obj.is_active:
            return format_html('<span class="sd-acct sd-acct--on">Active</span>')
        return format_html('<span class="sd-acct sd-acct--off">Suspended</span>')

    @admin.display(description="Account")
    def account_status(self, obj):
        return self.account_badge(obj)

    @admin.display(description="Two-step login")
    def two_step(self, obj):
        device = getattr(obj, "authenticator", None) if obj.pk else None
        if device and device.confirmed:
            left = device.backup_codes.filter(used_at__isnull=True).count()
            when = f" on {timezone.localtime(device.confirmed_at):%d/%m/%Y}" if device.confirmed_at else ""
            return f"Authenticator app set up{when} · {left} of 10 backup codes left"
        return "Not set up yet (they're asked at their next sign-in)"

    @admin.display(description="Role")
    def role(self, obj):
        return "Administrator" if obj.is_superuser else ("Staff" if obj.is_staff else "No admin access")

    def get_inlines(self, request, obj):
        return self.inlines if obj else []  # a new user has no history yet

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            return form

        class WithRequestUser(form):
            def __init__(self, *args, **kw):
                kw["request_user"] = request.user
                super().__init__(*args, **kw)
        return WithRequestUser

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        user_forms.apply_role(obj, form.cleaned_data["role"])
        if not change and form.cleaned_data.get("password_setup") == user_forms.EMAIL_LINK:
            if accounts.send_invite(request, obj):
                self.message_user(request, f"An email has been sent to {obj.email} with a link to choose "
                                           f"their password.", messages.SUCCESS)
            else:
                self.message_user(request, f"The invitation email to {obj.email} couldn't be sent. Check the "
                                           f"email settings, or use 'Set password' below and tell them.",
                                  messages.WARNING)

    def has_delete_permission(self, request, obj=None):
        return False  # suspend instead: keeps the audit trail

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.has_change_permission(request):
            actions.pop("suspend_selected", None)
            actions.pop("reactivate_selected", None)
        return actions

    def get_urls(self):
        return [path("<int:pk>/status/<str:change>/", self.admin_site.admin_view(self.status_view),
                     name="auth_user_status")] + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), "can_set_status": self.has_change_permission(request)}
        return super().change_view(request, object_id, form_url, extra_context)

    # One page (with a required reason) for the buttons and the bulk actions.
    def _status_page(self, request, users, suspend, error="", reason="", bulk=False):
        return TemplateResponse(request, "admin/account_status.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "title": ("Suspend " if suspend else "Reactivate ") + ("accounts" if len(users) > 1 else "account"),
            "users": users, "suspend": suspend, "error": error, "reason": reason, "bulk": bulk,
            "action": "suspend_selected" if suspend else "reactivate_selected",
            "cancel_url": (reverse("admin:auth_user_changelist") if bulk or len(users) != 1
                           else reverse("admin:auth_user_change", args=[users[0].pk])),
        })

    def _apply(self, request, users, suspend, reason):
        done, problems = [], []
        for u in users:
            try:
                if accounts.set_status(request.user, u, suspend, reason):
                    done.append(u.get_username())
            except accounts.StatusError as e:
                problems.append(str(e))
        for p in problems:
            self.message_user(request, p, messages.ERROR)
        if done:
            verb = "Suspended" if suspend else "Reactivated"
            self.message_user(request, f"{verb}: {', '.join(done)}. The reason is saved in the account history.",
                              messages.SUCCESS)
        return done

    def status_view(self, request, pk, change):
        if not self.has_change_permission(request) or change not in ("suspend", "reactivate"):
            raise PermissionDenied
        user = get_object_or_404(User, pk=pk)
        suspend = change == "suspend"
        if request.method == "POST":
            reason = request.POST.get("reason", "").strip()
            if not reason:
                return self._status_page(request, [user], suspend, "Please give a reason.")
            try:
                accounts.check(request.user, user, suspend)
            except accounts.StatusError as e:
                return self._status_page(request, [user], suspend, str(e), reason)
            self._apply(request, [user], suspend, reason)
            return redirect("admin:auth_user_change", user.pk)
        return self._status_page(request, [user], suspend)

    def _bulk(self, request, queryset, suspend):
        users = [u for u in queryset.order_by("username") if u.is_active == suspend]
        if not users:
            self.message_user(request, "Those accounts are already " + ("suspended." if suspend else "active."),
                              messages.WARNING)
            return None
        if request.POST.get("confirm"):
            reason = request.POST.get("reason", "").strip()
            if reason:
                self._apply(request, users, suspend, reason)
                return None
            return self._status_page(request, users, suspend, "Please give a reason.", bulk=True)
        return self._status_page(request, users, suspend, bulk=True)

    @admin.action(description="Suspend selected accounts")
    def suspend_selected(self, request, queryset):
        return self._bulk(request, queryset, True)

    @admin.action(description="Reactivate selected accounts")
    def reactivate_selected(self, request, queryset):
        return self._bulk(request, queryset, False)


@admin.register(AccountStatusChange)
class AccountStatusChangeAdmin(admin.ModelAdmin):
    """Read-only audit list of every suspension and reactivation. Nobody can edit or delete it."""
    list_display = ("changed_at", "username", "full_name", "action", "reason_short", "by")
    list_filter = ("action", "changed_at")
    search_fields = ("username", "full_name", "email", "reason")
    date_hierarchy = "changed_at"
    fields = ("changed_at", "action", "username", "full_name", "email", "reason", "by")
    readonly_fields = fields

    @admin.display(description="By")
    def by(self, obj):
        return person(obj.changed_by) or "—"

    @admin.display(description="Reason")
    def reason_short(self, obj):
        return (obj.reason[:80] + "…") if len(obj.reason) > 80 else obj.reason

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
