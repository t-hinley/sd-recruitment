from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Website"

    def ready(self):
        from . import signals  # noqa: F401  (connects the login signals)
        from django.contrib.auth import get_user_model
        from . import random_ids
        from .models import (AccountStatusChange, AuthenticatorDevice, CandidateRegistration, ContactEnquiry,
                             VacancyEnquiry)
        random_ids.connect([CandidateRegistration, VacancyEnquiry, ContactEnquiry, get_user_model(),
                            AccountStatusChange, AuthenticatorDevice])
