"""Enquiry pages in the admin.

What the visitor submitted is read-only for everyone, so the record always shows exactly what was sent.
The team only works with: status, assigned to and internal notes. Enquiries arrive from the website
forms only (no "Add" button), and only administrators can delete them.
"""

from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from . import airtable
from .models import AIRTABLE_FAILED, AIRTABLE_SENT, CandidateRegistration, ContactEnquiry, VacancyEnquiry


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
