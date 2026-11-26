"""Custom-styled Django admin (same look as the other SD admins): a sidebar,
a welcome bar, a dashboard of headline numbers, a profile page and CSV reports."""

from datetime import timedelta

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from .models import CandidateRegistration, ContactEnquiry, VacancyEnquiry

# Small outline icons (24x24, stroke) for the sidebar and dashboard cards.
ICONS = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "vacancyenquiry": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/><path d="M3 12.5h18"/>',
    "candidateregistration": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.5-7 8-7s8 3 8 7"/>',
    "contactenquiry": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5L12 13l8.5-6.5"/>',
    "cv": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M12 11v6M9.5 14.5L12 17l2.5-2.5"/>',
    "placed": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "new": '<path d="M4 5h16v11H8l-4 4z"/>',
    "quote": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "subcontractor": '<circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="M12 7.5v4M12 11.5l-5.5 4.3M12 11.5l5.5 4.3"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "report": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 17v-3M12 17v-6M15 17v-4"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.5-7 8-7s8 3 8 7"/>',
    "group": '<circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.5 3-6 7-6s7 2.5 7 6M17 5a3 3 0 0 1 0 6M22 19c0-2.5-1.5-4.5-4-5"/>',
    "accountstatuschange": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "site": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    "default": '<rect x="4" y="4" width="16" height="16" rx="3"/>',
}


def icon(name, size=20):
    return ('<svg class="sdi" width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>'
            % (size, size, ICONS.get(name, ICONS["default"])))


def bars(rows):
    top = max([n for _, n in rows] or [1]) or 1
    return [{"label": label, "n": n, "pct": max(4, round(100 * n / top)) if n else 0} for label, n in rows]


class SDAdminSite(admin.AdminSite):
    site_header = "SD Recruitment - Admin"
    site_title = "SD Recruitment admin"
    index_title = "Website enquiries"
    enable_nav_sidebar = False  # we draw our own sidebar

    MAIN = ["candidateregistration", "vacancyenquiry", "contactenquiry"]
    SHORT = {"candidateregistration": "Candidates", "vacancyenquiry": "Vacancies",
             "contactenquiry": "General"}  # fit the sidebar
    SETTINGS = ["user", "accountstatuschange"]

    # ---- pages -------------------------------------------------------------
    def get_urls(self):
        from django.urls import path
        from .views import resume_download
        return [path("profile/", self.admin_view(self.profile_view), name="profile"),
                path("reports/", self.admin_view(self.reports_view), name="reports"),
                path("cv/<int:pk>/", self.admin_view(resume_download), name="resume_download"),
                path("two-step/", self.two_step_verify, name="two_step"),
                path("two-step/setup/", self.two_step_setup, name="two_step_setup"),
                path("two-step/backup-codes/", self.admin_view(self.two_step_page("codes")), name="two_step_codes"),
                path("two-step/backup-codes/new/", self.admin_view(self.two_step_page("new_codes")),
                     name="two_step_new_codes"),
                path("two-step/new-phone/", self.admin_view(self.two_step_page("new_phone")),
                     name="two_step_new_phone")] + super().get_urls()

    def two_step_page(self, name):
        from django.views.decorators.cache import never_cache
        from . import two_step
        return never_cache(lambda request: getattr(two_step, name)(request, self))

    # Two-step sign-in pages (core/two_step.py). Not wrapped in admin_view: the person isn't signed in yet.
    def two_step_verify(self, request):
        from django.views.decorators.cache import never_cache
        from . import two_step
        return never_cache(lambda r: two_step.verify(r, self))(request)

    def two_step_setup(self, request):
        from django.views.decorators.cache import never_cache
        from . import two_step
        return never_cache(lambda r: two_step.setup(r, self))(request)

    def login(self, request, extra_context=None):
        """Pause sign-in after repeated failures, so the admin address cannot be used to guess passwords."""
        from . import security
        if request.method == "POST" and security.login_blocked(request):
            from django.shortcuts import render
            security.logger.warning("Admin sign-in paused for %s (too many failures)", security.client_ip(request))
            return render(request, "admin/login.html", {
                "blocked": "Too many failed sign-in attempts. Please wait 15 minutes and try again.",
                "site_name": "SD Recruitment"}, status=429)
        from django.conf import settings
        from . import two_step
        self.login_form = two_step.AdminLoginForm  # "username or email" wording
        if not settings.ADMIN_TWO_FACTOR:
            return super().login(request, {"site_name": "SD Recruitment", **(extra_context or {})})
        return self._two_step_login(request, {"site_name": "SD Recruitment", **(extra_context or {})})

    def _two_step_login(self, request, extra_context):
        """Django's admin login, but a correct password leads to the code step instead of signing in."""
        from django.contrib.auth import REDIRECT_FIELD_NAME
        from django.http import HttpResponseRedirect
        from . import two_step
        if request.method == "GET" and self.has_permission(request):
            return HttpResponseRedirect(reverse("admin:index", current_app=self.name))
        context = {**self.each_context(request), "title": "Log in", "subtitle": None,
                   "app_path": request.get_full_path(), "username": request.user.get_username()}
        if REDIRECT_FIELD_NAME not in request.GET and REDIRECT_FIELD_NAME not in request.POST:
            context[REDIRECT_FIELD_NAME] = reverse("admin:index", current_app=self.name)
        context.update(extra_context)
        request.current_app = self.name
        return two_step.TwoStepLoginView.as_view(
            extra_context=context, authentication_form=two_step.AdminLoginForm,
            template_name="admin/login.html")(request)

    def logout(self, request, extra_context=None):
        """After Log out, return to the admin log in page instead of a separate 'logged out' page."""
        if request.method == "POST":
            from django.contrib.auth import logout as auth_logout
            from django.shortcuts import redirect
            auth_logout(request)
            return redirect("admin:login")
        return super().logout(request, extra_context)

    def profile_view(self, request):
        from django.template.response import TemplateResponse
        from . import backup_codes
        user = request.user
        device = getattr(user, "authenticator", None)
        return TemplateResponse(request, "admin/profile.html", {
            **self.each_context(request), "title": "Profile",
            "p_name": user.get_full_name() or user.get_username(),
            "p_email": user.email,
            "p_joined": user.date_joined,
            "p_active": user.is_active,
            "p_role": "Administrator" if user.is_superuser else "Staff",
            "p_last_login": user.last_login,
            "p_two_step_on": __import__("django.conf").conf.settings.ADMIN_TWO_FACTOR,
            "p_authenticator": device,
            "p_backup_left": backup_codes.remaining(device),
        })

    def reports_view(self, request):
        """Download website enquiries as a CSV file (administrators only)."""
        from django.core.exceptions import PermissionDenied
        from django.template.response import TemplateResponse
        from . import reports
        if not request.user.is_superuser:
            raise PermissionDenied
        # The dashboard links here with only ?format=pdf (or csv): pre-select it without showing errors.
        if "report" in request.GET:
            form = reports.ReportForm(request.GET)
        else:
            form = reports.ReportForm(initial={"format": request.GET.get("format")})
        if form.is_bound and form.is_valid():
            d = form.cleaned_data
            return reports.response(d["report"], d["date_from"], d["date_to"], d["format"])
        chosen = form["report"].value() or reports.CANDIDATES
        cards = [{"value": v, "title": t, "help": h, "icon": ICONS[i], "checked": v == chosen}
                 for v, (t, h, i) in reports.REPORT_CARDS.items()]
        chosen_fmt = form["format"].value() or reports.CSV
        formats = [{"value": v, "label": label, "help": reports.FORMAT_HELP[v], "checked": v == chosen_fmt}
                   for v, label in reports.FORMATS]
        return TemplateResponse(request, "admin/reports.html", {
            **self.each_context(request), "title": "Reports", "form": form, "report_cards": cards,
            "formats": formats})

    # ---- shared context ----------------------------------------------------
    def each_context(self, request):
        ctx = super().each_context(request)
        if request.user.is_authenticated and request.user.is_staff:
            ctx["sd_nav"] = self._nav(request)
            ctx["sd_icon_site"] = icon("site")
        return ctx

    def _nav(self, request):
        path = request.path
        found = {}
        for app in self.get_app_list(request):
            for m in app["models"]:
                found[m["object_name"].lower()] = m

        def item(key, label, url, ic):
            active = path == url if key == "dashboard" else path.startswith(url)
            return {"label": label, "url": url, "icon": icon(ic), "active": active}

        main = [item("dashboard", "Dashboard", reverse("admin:index"), "dashboard")]
        for k in self.MAIN:
            m = found.get(k)
            if m and m.get("admin_url"):
                main.append(item(k, self.SHORT.get(k, m["name"]), m["admin_url"], k))
        if request.user.is_superuser:
            main.append(item("reports", "Reports", reverse("admin:reports"), "report"))
        rest = []
        for k in self.SETTINGS:
            m = found.get(k)
            if m and m.get("admin_url"):
                rest.append(item(k, m["name"], m["admin_url"], k))
        known = set(self.MAIN) | set(self.SETTINGS)
        for k, m in found.items():
            if k not in known and m.get("admin_url"):
                rest.append(item(k, m["name"], m["admin_url"], "default"))
        return {"main": main, "rest": rest}

    # ---- dashboard ---------------------------------------------------------
    def index(self, request, extra_context=None):
        cands = CandidateRegistration.objects.all()
        vacs = VacancyEnquiry.objects.all()
        contacts = ContactEnquiry.objects.all()
        month_start = timezone.localdate().replace(day=1)
        week_ago = timezone.now() - timedelta(days=7)
        cand_url = reverse("admin:core_candidateregistration_changelist")
        vac_url = reverse("admin:core_vacancyenquiry_changelist")
        contact_url = reverse("admin:core_contactenquiry_changelist")
        new_total = (cands.filter(status="new").count() + vacs.filter(status="new").count()
                     + contacts.filter(status="new").count())

        def open_(qs):
            return qs.exclude(status__in=["closed", "placed"])

        everything = (cands, vacs, contacts)
        mine = sum(open_(qs).filter(assigned_to=request.user).count() for qs in everything)
        unassigned = sum(open_(qs).filter(assigned_to__isnull=True).count() for qs in everything)
        failed = cands.filter(airtable_status="failed").count() + vacs.filter(airtable_status="failed").count()

        def rows(items):
            """Horizontal bars for one group of counts. Each group has its own scale (longest bar = largest
            count in that group), so unrelated numbers are never compared on one axis."""
            top = max([n for _, n, *_ in items] or [1]) or 1
            return [{"label": label, "n": n, "icon": icon(ic, 18), "tone": tone, "url": url,
                     "pct": max(3, round(100 * n / top)) if n else 0} for label, n, ic, tone, url in items]

        # Things someone needs to act on.
        attention = [
            ("New candidates", cands.filter(status="new").count(), "candidateregistration", "orange",
             cand_url + "?status__exact=new"),
            ("New vacancies", vacs.filter(status="new").count(), "vacancyenquiry", "orange",
             vac_url + "?status__exact=new"),
            ("New general enquiries", contacts.filter(status="new").count(), "contactenquiry", "orange",
             contact_url + "?status__exact=new"),
            ("Unassigned (open)", unassigned, "group", "orange", cand_url + "?assigned=none"),
        ]
        if failed:  # status, not a series: only shown when something actually failed
            attention.append(("Airtable send failures", failed, "alert", "bad",
                              cand_url + "?airtable_status__exact=failed"))
        # Overall picture.
        glance = [
            ("Candidates", cands.count(), "candidateregistration", "blue", cand_url),
            ("Candidates with a CV", cands.exclude(resume="").count(), "cv", "blue", cand_url),
            ("Vacancies being recruited", vacs.filter(status="recruiting").count(), "group", "blue",
             vac_url + "?status__exact=recruiting"),
            ("Placements", vacs.filter(status="placed").count() + cands.filter(status="placed").count(), "placed",
             "blue", vac_url + "?status__exact=placed"),
            ("Received this month", sum(qs.filter(created_at__date__gte=month_start).count()
                                        for qs in everything), "calendar", "blue", cand_url),
        ]
        attention_rows, glance_rows = rows(attention), rows(glance)
        waiting_total = sum(r["n"] for r in attention_rows[:3])

        by_status = dict(cands.values_list("status").annotate(n=Count("id")))
        cand_status_rows = bars([(label, by_status.get(v, 0)) for v, label in CandidateRegistration.STATUSES])
        by_vstatus = dict(vacs.values_list("status").annotate(n=Count("id")))
        vac_status_rows = bars([(label, by_vstatus.get(v, 0)) for v, label in VacancyEnquiry.STATUSES])

        # Activity by industry: candidates and vacancies side by side (the two Airtable forms use
        # slightly different industry names, so each row links to whichever list uses that name).
        from .models import CANDIDATE_INDUSTRIES, EMPLOYER_INDUSTRIES
        c_ind = dict(cands.values_list("industry").annotate(n=Count("id")))
        v_ind = dict(vacs.values_list("industry").annotate(n=Count("id")))
        v_open = dict(open_(vacs).values_list("industry").annotate(n=Count("id")))
        names = list(dict.fromkeys([v for v, _ in CANDIDATE_INDUSTRIES] + [v for v, _ in EMPLOYER_INDUSTRIES]))
        industry_rows = [{"label": name, "filter": name, "cands": c_ind.get(name, 0), "vacs": v_ind.get(name, 0),
                          "open": v_open.get(name, 0)} for name in names if c_ind.get(name) or v_ind.get(name)]

        support = cands.aggregate(**{key: Count("id", filter=Q(**{f"support_{key}": True}))
                                     for key, _ in CandidateRegistration.SUPPORT_CHOICES})
        support_rows = bars([(label, support[key]) for key, label in CandidateRegistration.SUPPORT_CHOICES])
        support_links = {label: f"{cand_url}?service={key}" for key, label in CandidateRegistration.SUPPORT_CHOICES}
        for r in support_rows:
            r["url"] = support_links[r["label"]]

        recent = [{"name": e.full_name, "email": e.email, "kind": "Candidate · " + e.industry,
                   "message": e.position_sought, "status": e.status, "status_label": e.get_status_display(),
                   "when": e.created_at, "url": reverse("admin:core_candidateregistration_change", args=[e.pk])}
                  for e in cands[:6]]
        recent += [{"name": e.company, "email": e.email, "kind": "Vacancy · " + e.position, "message": e.details,
                    "status": e.status, "status_label": e.get_status_display(), "when": e.created_at,
                    "url": reverse("admin:core_vacancyenquiry_change", args=[e.pk])} for e in vacs[:6]]
        recent += [{"name": e.name, "email": e.email, "kind": "General enquiry",
                    "message": e.message, "status": e.status, "status_label": e.get_status_display(),
                    "when": e.created_at, "url": reverse("admin:core_contactenquiry_change", args=[e.pk])}
                   for e in contacts[:6]]
        recent = sorted(recent, key=lambda r: r["when"], reverse=True)[:8]

        actions = [{"flag": e.action_flag, "repr": e.object_repr, "type": e.content_type.name if e.content_type else "",
                    "url": e.get_admin_url(), "when": e.action_time}
                   for e in LogEntry.objects.filter(user=request.user).select_related("content_type")[:8]]

        extra_context = {
            **(extra_context or {}),
            "attention_rows": attention_rows, "glance_rows": glance_rows, "waiting_total": waiting_total,
            "mine": mine, "icon_user": icon("user", 22),
            "mine_parts": [p for p in (
                {"label": one if n == 1 else many, "n": n, "url": url + "?assigned=me"}
                for one, many, n, url in (
                    ("candidate", "candidates", open_(cands).filter(assigned_to=request.user).count(), cand_url),
                    ("vacancy", "vacancies", open_(vacs).filter(assigned_to=request.user).count(), vac_url),
                    ("general enquiry", "general enquiries",
                     open_(contacts).filter(assigned_to=request.user).count(), contact_url),
                )) if p["n"]],
            "cand_status_rows": cand_status_rows, "cand_total": cands.count(),
            "vac_status_rows": vac_status_rows, "vac_total": vacs.count(),
            "industry_rows": industry_rows, "support_rows": support_rows,
            "cand_url": cand_url, "vac_url": vac_url,
            "waiting": new_total,
            "this_week": sum(qs.filter(created_at__gte=week_ago).count() for qs in (cands, vacs, contacts)),
            "recent": recent,
            "recent_actions": actions,
            "is_admin": request.user.is_superuser,
        }
        return super().index(request, extra_context)
