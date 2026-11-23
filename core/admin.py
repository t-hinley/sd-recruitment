"""Enquiry pages in the admin.

What the visitor submitted is read-only for everyone, so the record always shows exactly what was sent.
The team only works with: status, assigned to and internal notes. Enquiries arrive from the website
forms only (no "Add" button), and only administrators can delete them.
Current opportunities (jobs shown on the Candidates page) are added and edited here by staff.
"""

from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import CandidateRegistration, ContactEnquiry, Job, VacancyEnquiry


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


@admin.register(VacancyEnquiry)
class VacancyEnquiryAdmin(EnquiryAdmin):
    list_display = ("company", "position", "industry", "location", "status", "handler", "received")
    list_filter = ("status", AssignedFilter, "industry", "employment_type", "created_at")
    search_fields = ("company", "contact_name", "email", "phone", "position", "location", "details", "notes")
    submitted_fields = ("contact_name", "company", "email_link", "phone_link", "industry", "position",
                        "positions_count", "employment_type", "location", "start_timeframe", "details", "received_full")
    fieldsets = (
        ("Vacancy details", {"fields": (("contact_name", "company"), ("email_link", "phone_link"),
                                        ("industry", "employment_type"), ("position", "positions_count"),
                                        ("location", "start_timeframe"), "details", "received_full")}),
        FOLLOW_UP,
    )


@admin.register(CandidateRegistration)
class CandidateRegistrationAdmin(EnquiryAdmin):
    list_display = ("full_name", "position_sought", "industry", "location", "support_summary", "cv", "status",
                    "handler", "received")
    list_filter = ("status", AssignedFilter, "industry", "support_jobs", "support_resume", "support_interview",
                   "support_career", "job", "created_at")
    search_fields = ("full_name", "email", "phone", "location", "position_sought", "experience", "notes")
    list_select_related = ("assigned_to", "job")
    submitted_fields = ("full_name", "email_link", "phone_link", "location", "position_sought", "industry",
                        "job", "experience", "support_summary", "resume_link", "consent", "received_full")
    fieldsets = (
        ("Candidate details", {"fields": ("full_name", ("email_link", "phone_link"), ("location", "industry"),
                                          ("position_sought", "job"), "experience", "support_summary",
                                          "resume_link", ("consent", "received_full"))}),
        FOLLOW_UP,
    )

    @admin.display(description="Support requested")
    def support_summary(self, obj):
        return ", ".join(obj.support_list) or "-"

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
    list_display = ("name", "enquirer_type", "email", "status", "handler", "received")
    list_filter = ("status", AssignedFilter, "enquirer_type", "created_at")
    search_fields = ("name", "email", "phone", "message", "notes")
    submitted_fields = ("name", "email_link", "phone_link", "enquirer_type", "message", "received_full")
    fieldsets = (
        ("Enquiry", {"fields": ("name", ("email_link", "phone_link"), "enquirer_type", "message", "received_full")}),
        FOLLOW_UP,
    )


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "industry", "location", "employment_type", "is_published", "applicants", "created_at")
    list_editable = ("is_published",)
    list_filter = ("is_published", "industry", "employment_type")
    search_fields = ("title", "location", "summary")
    fields = ("title", ("industry", "employment_type"), "location", "summary", "is_published")

    @admin.display(description="Registrations")
    def applicants(self, obj):
        n = obj.registrations.count()
        if not n:
            return 0
        url = reverse("admin:core_candidateregistration_changelist") + f"?job__id__exact={obj.pk}"
        return format_html('<a href="{}">{}</a>', url, n)
