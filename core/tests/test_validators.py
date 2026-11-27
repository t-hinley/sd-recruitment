from unittest import mock

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core import validators as v


class PhoneTests(SimpleTestCase):
    def test_australian_numbers_are_tidied(self):
        for typed, saved in [("0412345678", "0412 345 678"), ("+61 412 345 678", "0412 345 678"),
                             ("+61 (0)412-345-678", "0412 345 678"), ("08 9200 1234", "08 9200 1234"),
                             ("(08) 92001234", "08 9200 1234"), ("1300123456", "1300 123 456"),
                             ("0061 412 345 678", "0412 345 678")]:
            self.assertEqual(v.clean_phone(typed), saved, typed)

    def test_overseas_numbers(self):
        self.assertEqual(v.clean_phone("+975 17 123 456"), "+97517123456")
        self.assertEqual(v.clean_phone("+977 098 1234 5678"), "+9779812345678")   # leading 0 dropped
        self.assertEqual(v.clean_phone("+33 6 12 34 56 78"), "+33612345678")      # other countries: 8-15 digits
        with self.assertRaisesMessage(ValidationError, "Bhutan"):
            v.clean_phone("+975 12 345 678")

    def test_bad_numbers(self):
        for bad in ["12345", "0412 345 67", "0412 345 6789", "9200 1234", "0400 000 000", "phone me",
                    "0512 345 678", "+0 123"]:
            with self.assertRaises(ValidationError, msg=bad):
                v.clean_phone(bad)
        self.assertEqual(v.clean_phone(""), "")


@override_settings(EMAIL_DOMAIN_CHECK=True)
class EmailTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_format_typos_and_throwaway(self):
        with mock.patch.object(v, "_lookup", return_value="yes"):
            self.assertEqual(v.clean_email("  Ann.Lee@Gmail.COM "), "ann.lee@gmail.com")
            for bad in ["ann", "ann@", "ann@gmail", "ann..lee@gmail.com", "ann@gmail.c", ".ann@gmail.com"]:
                with self.assertRaises(ValidationError, msg=bad):
                    v.clean_email(bad)
            with self.assertRaisesMessage(ValidationError, "Did you mean ann@gmail.com?"):
                v.clean_email("ann@gmial.com")
            with self.assertRaisesMessage(ValidationError, "temporary inboxes"):
                v.clean_email("ann@mailinator.com")

    def test_domain_that_cannot_receive_email_is_refused(self):
        with mock.patch.object(v, "_lookup", side_effect=lambda d: "yes" if d == v.CONTROL_DOMAIN else "no"):
            with self.assertRaisesMessage(ValidationError, "can't be delivered"):
                v.clean_email("ann@gmail.comm")

    def test_broken_dns_never_blocks_anyone(self):
        with mock.patch.object(v, "_lookup", return_value="no"):          # everything "doesn't exist"
            self.assertEqual(v.clean_email("ann@realbusiness.com.au"), "ann@realbusiness.com.au")
        cache.clear()
        with mock.patch.object(v, "_lookup", return_value="unknown"):     # timeout / unreachable
            self.assertEqual(v.clean_email("ann@realbusiness.com.au"), "ann@realbusiness.com.au")


class FormTests(TestCase):
    def test_contact_form_shows_helpful_errors(self):
        r = self.client.post(reverse("core:contact"), {"contact-name": "Ann", "contact-email": "ann@gmial.com",
                                                      "contact-phone": "12345", "contact-message": "Hi"})
        self.assertContains(r, "Did you mean ann@gmail.com?")
        self.assertContains(r, "Enter an Australian number")
        r = self.client.post(reverse("core:contact"), {"contact-name": "Ann", "contact-email": "Ann@Gmail.com",
                                                      "contact-phone": "+61412345678", "contact-message": "Hi"})
        self.assertEqual(r.status_code, 302)
        from core.models import ContactEnquiry
        e = ContactEnquiry.objects.get()
        self.assertEqual((e.email, e.phone), ("ann@gmail.com", "0412 345 678"))
