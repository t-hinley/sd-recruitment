"""Let the 'Staff' role view service requests and update their status, assignment and notes."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

PERMS = ["view_servicerequest", "change_servicerequest"]


def add_perms(apps, schema_editor):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, verbosity=0)
        app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name="Staff")
    group.permissions.add(*Permission.objects.filter(content_type__app_label="core", codename__in=PERMS))


def remove_perms(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.filter(name="Staff").first()
    if group:
        group.permissions.remove(*Permission.objects.filter(content_type__app_label="core", codename__in=PERMS))


class Migration(migrations.Migration):
    dependencies = [("core", "0003_service_request")]
    operations = [migrations.RunPython(add_perms, remove_perms)]
