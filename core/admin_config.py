from django.contrib.admin.apps import AdminConfig


class SDAdminConfig(AdminConfig):
    default_site = "core.admin_site.SDAdminSite"
