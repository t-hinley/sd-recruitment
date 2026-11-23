"""Create the 'Staff' role: view candidates, vacancies and contact enquiries and update their status,
assignment and notes; add and edit current opportunities (jobs). Staff cannot delete enquiries,
download reports or manage users (administrators only)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

STAFF_PERMS = [
    "view_candidateregistration", "change_candidateregistration",
    "view_vacancyenquiry", "change_vacancyenquiry",
    "view_contactenquiry", "change_contactenquiry",
    "view_job", "add_job", "change_job", "delete_job",
]


def create_staff_group(apps, schema_editor):
    # Make sure the model permissions exist before linking them (they are normally created after migrate).
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, verbosity=0)
        app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name="Staff")
    group.permissions.add(*Permission.objects.filter(content_type__app_label="core", codename__in=STAFF_PERMS))


def remove_staff_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name="Staff").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_staff_group, remove_staff_group)]
