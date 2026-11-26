"""Renumber existing records with random IDs (see core/random_ids.py). Signs everyone out once."""

from django.db import migrations

MODELS = ["core.CandidateRegistration", "core.VacancyEnquiry", "core.ContactEnquiry", "core.AccountStatusChange",
          "core.AuthenticatorDevice", "auth.User"]


def forwards(apps, schema_editor):
    from core import random_ids
    random_ids.renumber(apps, MODELS, flush_sessions=True)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_account_history_label"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("sessions", "0001_initial"),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
