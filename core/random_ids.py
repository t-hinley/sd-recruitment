"""Random record IDs, so addresses like /admin/.../4839201758193746/change/ can't be guessed by counting
(1, 2, 3 ...). New records of the models in RANDOM_ID_MODELS get a random ID when first saved; existing
records were renumbered once by a migration (renumber(), which also fixes every link to them).

Every page still checks who is signed in and what they may see: random IDs are an extra layer, not the
protection itself. Users get 10-digit IDs (Django's user table holds 32-bit numbers); everything else
gets 16-digit IDs (below 2**53, so they are safe in JavaScript and Airtable too).
"""

import secrets

from django.conf import settings
from django.db.models.signals import pre_save

USER_RANGE = (1_000_000_000, 2_147_483_647)
BIG_RANGE = (1_000_000_000_000_000, 9_007_199_254_740_991)


def id_range(model):
    label = f"{model._meta.app_label}.{model._meta.object_name}"
    return USER_RANGE if label.lower() == settings.AUTH_USER_MODEL.lower() else BIG_RANGE


def new_id(model, taken=()):
    lo, hi = id_range(model)
    while True:
        n = lo + secrets.randbelow(hi - lo)
        if n not in taken and not model._base_manager.filter(pk=n).exists():
            return n


def _assign(sender, instance, raw=False, **kwargs):
    if not raw and instance.pk is None:
        instance.pk = new_id(sender)


def connect(models):
    for model in models:
        pre_save.connect(_assign, sender=model, dispatch_uid=f"random_id_{model._meta.label_lower}")


def renumber(apps, model_labels, flush_sessions=False):
    """Give every existing row of these models a random ID and update everything that points to it
    (foreign keys, many-to-many tables, admin history). For use in a data migration."""
    LogEntry = apps.get_model("admin", "LogEntry")
    ContentType = apps.get_model("contenttypes", "ContentType")
    for label in model_labels:
        Model = apps.get_model(label)
        reverse_fks = [f for f in Model._meta.get_fields(include_hidden=True)
                       if f.auto_created and not f.concrete and (f.one_to_many or f.one_to_one)]
        ct = ContentType.objects.filter(app_label=Model._meta.app_label, model=Model._meta.model_name).first()
        taken = set()
        for old in list(Model._base_manager.order_by("pk").values_list("pk", flat=True)):
            new = new_id(Model, taken)
            taken.add(new)
            for rel in reverse_fks:
                rel.related_model._base_manager.filter(**{rel.field.attname: old}).update(**{rel.field.attname: new})
            if ct is not None:
                LogEntry.objects.filter(content_type=ct, object_id=str(old)).update(object_id=str(new))
            Model._base_manager.filter(pk=old).update(**{Model._meta.pk.attname: new})
    if flush_sessions:  # sign-in sessions refer to the old user numbers: everyone signs in again once
        apps.get_model("sessions", "Session").objects.all().delete()
