from django.core.management import call_command
from django.test import TestCase, override_settings

from core import airtable
from core.models import CandidateRegistration, ContactEnquiry, VacancyEnquiry


class DemoEnquiriesTests(TestCase):
    def test_add_and_remove_leaves_real_enquiries_alone(self):
        real = ContactEnquiry.objects.create(name="Real Person", email="real@example.com", message="Hi")
        call_command("demo_enquiries", stdout=open("/dev/null", "w"))
        self.assertEqual(CandidateRegistration.objects.count(), 8)
        self.assertEqual(VacancyEnquiry.objects.count(), 6)
        self.assertEqual(ContactEnquiry.objects.count(), 5)
        call_command("demo_enquiries", "--remove", stdout=open("/dev/null", "w"))
        self.assertEqual(CandidateRegistration.objects.count() + VacancyEnquiry.objects.count(), 0)
        self.assertEqual(list(ContactEnquiry.objects.all()), [real])

    @override_settings(AIRTABLE_TOKEN="x", AIRTABLE_BASE_ID="appX")
    def test_samples_are_never_sent_to_airtable(self):
        call_command("demo_enquiries", stdout=open("/dev/null", "w"))
        obj = CandidateRegistration.objects.first()
        self.assertFalse(airtable.push(obj))
        self.assertEqual(obj.airtable_id, "")
