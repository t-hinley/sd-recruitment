"""Turns the admin's list filters into the compact filter bar used on the enquiry lists:
quick tabs with counts, a few dropdowns, a 'More filters' panel and removable chips.
(templates/admin/enquiry_change_list.html). The URLs are Django's own, so links such as
?status__exact=new from the dashboard keep working."""

from urllib.parse import urlencode

from django.contrib.admin.filters import FieldListFilter
from django.utils.text import capfirst

IGNORED = {"q", "o", "p", "e", "_facets"}


def _key(spec):
    return spec.field_path if isinstance(spec, FieldListFilter) else spec.parameter_name


def _filters(model_admin, cl):
    out = []
    titles = getattr(model_admin, "filter_titles", {})
    for spec in cl.filter_specs:
        key = _key(spec)
        choices = list(spec.choices(cl))
        if not choices:
            continue
        options = [{"label": str(c["display"]), "url": c["query_string"], "selected": c["selected"]}
                   for c in choices]
        chosen = next((o for o in options[1:] if o["selected"]), None)
        out.append({
            "key": key, "title": titles.get(key) or capfirst(str(spec.title)),
            "options": options, "active": chosen is not None,
            "value": chosen["label"] if chosen else "", "clear_url": options[0]["url"],
        })
    return out


def _params(request):
    return {k: v for k, v in request.GET.items() if k not in IGNORED}


def _tab_queryset(request, model_admin, qs, params):
    """Apply a tab's parameters: through the matching custom filter if there is one, else as a lookup."""
    from django.contrib import admin
    simple = {f.parameter_name: f for f in model_admin.list_filter
              if isinstance(f, type) and issubclass(f, admin.SimpleListFilter)}
    for k, v in params.items():
        if k in simple:
            spec = simple[k](request, {k: [v]}, model_admin.model, model_admin)
            qs = spec.queryset(request, qs)
        else:
            qs = qs.filter(**{k: v})
    return qs


def build(request, model_admin, cl):
    filters = _filters(model_admin, cl)
    primary_keys = list(getattr(model_admin, "primary_filters", ()))
    primary = sorted([f for f in filters if f["key"] in primary_keys], key=lambda f: primary_keys.index(f["key"]))
    more = [f for f in filters if f["key"] not in primary_keys]

    current = _params(request)
    base = model_admin.get_queryset(request)
    tabs, active_tab = [], None
    for label, params, tone in model_admin.list_tabs:
        on = current == params
        if on:
            active_tab = params
        tabs.append({"label": label, "url": "?" + urlencode(params), "on": on, "tone": tone,
                     "count": _tab_queryset(request, model_admin, base, params).count()})

    # Chips for everything switched on, except what the selected tab already says.
    chips = []
    tab_keys = set(active_tab or {})
    for f in filters:
        if f["active"] and not any(f["key"] == k.split("__")[0] or f["key"] == k for k in tab_keys):
            chips.append({"label": f"{f['title']}: {f['value']}", "url": f["clear_url"]})
    if cl.query:
        rest = {k: v for k, v in request.GET.items() if k not in ("q", "p")}
        chips.insert(0, {"label": f"Search: {cl.query}", "url": "?" + urlencode(rest)})

    return {
        "fb_tabs": tabs, "fb_primary": primary, "fb_more": more,
        "fb_more_active": sum(1 for f in more if f["active"]),
        "fb_chips": chips, "fb_clear_url": "?",
        "fb_hidden": [(k, v) for k, v in request.GET.items() if k not in ("q", "p")],
        "fb_list_title": model_admin.list_title or capfirst(str(model_admin.model._meta.verbose_name_plural)),
        "fb_list_subtitle": model_admin.list_subtitle,
        "fb_search_placeholder": model_admin.search_placeholder, "fb_has_search": bool(model_admin.search_fields),
        "fb_add_label": model_admin.add_label if model_admin.has_add_permission(request) else "",
    }
