from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core import random_ids
from core.models import ContactEnquiry

STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
          "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


@override_settings(STORAGES=STATIC, ADMIN_TWO_FACTOR=False)
class RandomIdTests(TestCase):
    def test_new_records_and_users_get_random_ids(self):
        u1 = User.objects.create_user("a", "a@x.com", "a-long-pass-123")
        u2 = User.objects.create_user("b", "b@x.com", "a-long-pass-123")
        for u in (u1, u2):
            self.assertGreaterEqual(u.pk, random_ids.USER_RANGE[0])
        self.assertNotEqual(u2.pk - u1.pk, 1)
        e = ContactEnquiry.objects.create(name="X", email="x@x.com", message="hi")
        self.assertGreaterEqual(e.pk, random_ids.BIG_RANGE[0])
        self.assertLess(e.pk, 2 ** 53)

    def test_counting_ids_no_longer_open_anything(self):
        boss = User.objects.create_superuser("boss", "boss@x.com", "a-long-pass-123")
        e = ContactEnquiry.objects.create(name="Sam", email="s@x.com", message="hi")
        self.client.force_login(boss)
        self.assertEqual(self.client.get(reverse("admin:core_contactenquiry_change", args=[e.pk])).status_code, 200)
        r = self.client.get(reverse("admin:core_contactenquiry_change", args=[1]), follow=True)
        self.assertContains(r, "doesn’t exist")

    def test_website_forms_still_save(self):
        r = self.client.post(reverse("core:contact"), {"contact-name": "Ann", "contact-email": "ann@x.com",
                                                      "contact-message": "Hello"})
        self.assertEqual(r.status_code, 302)
        self.assertGreaterEqual(ContactEnquiry.objects.get().pk, random_ids.BIG_RANGE[0])
