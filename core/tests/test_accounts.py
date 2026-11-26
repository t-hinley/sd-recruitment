from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import AccountStatusChange, ContactEnquiry

STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
PW = "a-strong-pass-123"


@override_settings(STORAGES=STATIC, ADMIN_TWO_FACTOR=False)
class SuspendTests(TestCase):
    def setUp(self):
        cache.clear()
        self.boss = User.objects.create_superuser("boss", "boss@example.com", PW)
        self.sam = User.objects.create_user("sam", "sam@example.com", PW, is_staff=True,
                                            first_name="Sam", last_name="Lee")
        self.enquiry = ContactEnquiry.objects.create(name="A", email="a@example.com", message="Hi",
                                                     assigned_to=self.sam)
        self.client.force_login(self.boss)

    def suspend(self, user, reason="Left the company"):
        return self.client.post(reverse("admin:auth_user_status", args=[user.pk, "suspend"]), {"reason": reason})

    def test_suspend_blocks_sign_in_and_keeps_everything(self):
        sam = self.client_class()
        sam.force_login(self.sam)
        self.assertEqual(sam.get(reverse("admin:index")).status_code, 200)

        r = self.suspend(self.sam)
        self.assertRedirects(r, reverse("admin:auth_user_change", args=[self.sam.pk]))
        self.sam.refresh_from_db()
        self.assertFalse(self.sam.is_active)
        # Signed out on the next click, and can't sign in again.
        self.assertEqual(sam.get(reverse("admin:index")).status_code, 302)
        self.assertFalse(self.client_class().login(username="sam", password=PW))
        # Nothing deleted: the enquiry is still assigned to them, and the change is on record.
        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.assigned_to, self.sam)
        entry = AccountStatusChange.objects.get()
        self.assertEqual((entry.action, entry.reason, entry.changed_by, entry.username, entry.full_name),
                         ("suspended", "Left the company", self.boss, "sam", "Sam Lee"))
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.sam.pk),
                                                change_message__contains="Left the company").exists())
        page = self.client.get(reverse("admin:auth_user_change", args=[self.sam.pk]))
        self.assertContains(page, "Reactivate account")
        self.assertContains(page, "Left the company")

    def test_reason_required(self):
        r = self.suspend(self.sam, reason="  ")
        self.assertContains(r, "Please give a reason")
        self.sam.refresh_from_db()
        self.assertTrue(self.sam.is_active)
        self.assertFalse(AccountStatusChange.objects.exists())

    def test_reactivate(self):
        self.suspend(self.sam)
        self.client.post(reverse("admin:auth_user_status", args=[self.sam.pk, "reactivate"]),
                         {"reason": "Rehired"})
        self.sam.refresh_from_db()
        self.assertTrue(self.sam.is_active)
        self.assertEqual(list(AccountStatusChange.objects.values_list("action", flat=True)),
                         ["reactivated", "suspended"])

    def test_cannot_suspend_self_or_last_admin(self):
        self.suspend(self.boss)
        self.boss.refresh_from_db()
        self.assertTrue(self.boss.is_active)
        other = User.objects.create_superuser("other", "o@example.com", PW)
        self.client.force_login(other)
        self.suspend(self.boss)  # another admin still active: allowed
        self.boss.refresh_from_db()
        self.assertFalse(self.boss.is_active)

    def test_bulk_action_asks_for_reason(self):
        url = reverse("admin:auth_user_changelist")
        r = self.client.post(url, {"action": "suspend_selected", "_selected_action": [self.sam.pk]})
        self.assertContains(r, "Reason")
        self.assertTrue(User.objects.get(pk=self.sam.pk).is_active)
        self.client.post(url, {"action": "suspend_selected", "_selected_action": [self.sam.pk],
                               "confirm": "1", "reason": "Contract ended"})
        self.assertFalse(User.objects.get(pk=self.sam.pk).is_active)
        self.assertEqual(AccountStatusChange.objects.get().reason, "Contract ended")

    def test_no_delete_and_history_read_only(self):
        self.suspend(self.sam)
        r = self.client.get(reverse("admin:auth_user_delete", args=[self.sam.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertNotContains(self.client.get(reverse("admin:auth_user_changelist")), "delete_selected")
        entry = AccountStatusChange.objects.get()
        self.assertEqual(self.client.get(reverse("admin:core_accountstatuschange_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:core_accountstatuschange_delete",
                                                 args=[entry.pk])).status_code, 403)
        with self.assertRaises(ProtectedError):
            self.sam.delete()

    def test_active_box_not_editable_directly(self):
        r = self.client.get(reverse("admin:auth_user_change", args=[self.sam.pk]))
        self.assertNotContains(r, 'name="is_active"')

    def test_staff_cannot_suspend(self):
        self.client.force_login(self.sam)
        r = self.suspend(self.boss)
        self.assertIn(r.status_code, (302, 403))
        self.boss.refresh_from_db()
        self.assertTrue(self.boss.is_active)
