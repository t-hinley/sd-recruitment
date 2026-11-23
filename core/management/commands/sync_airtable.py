"""Send employer enquiries and candidate registrations that have not reached Airtable yet
(failed, or saved before Airtable was set up).

Run it from a cron job every 15 minutes, or by hand:
    python manage.py sync_airtable
"""

import time

from django.core.management.base import BaseCommand, CommandError

from core import airtable
from core.models import AIRTABLE_SENT, CandidateRegistration, VacancyEnquiry


class Command(BaseCommand):
    help = "Send website submissions that are not yet in Airtable."

    def handle(self, *args, **opts):
        if not airtable.enabled():
            raise CommandError("Airtable is not set up: add AIRTABLE_TOKEN to .env.")
        sent = failed = 0
        for model in (VacancyEnquiry, CandidateRegistration):
            for obj in model.objects.exclude(airtable_status=AIRTABLE_SENT).filter(airtable_id="").order_by("pk"):
                if airtable.push(obj):
                    sent += 1
                else:
                    failed += 1
                    self.stderr.write(f"{model._meta.verbose_name} #{obj.pk}: {obj.airtable_error}")
                time.sleep(0.25)  # Airtable allows 5 requests per second per base
        self.stdout.write(f"Sent {sent}, failed {failed}.")
        if failed:
            raise CommandError(f"{failed} could not be sent.")
