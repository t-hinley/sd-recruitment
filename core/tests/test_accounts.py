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


@override_settings(STORAGES=STATIC, ADMIN_TWO_FACTOR=False)
class TeamMemberFormTests(TestCase):
    def setUp(self):
        cache.clear()
        self.boss = User.objects.create_superuser("boss", "boss@example.com", PW)
        self.client.force_login(self.boss)
        self.add_url = reverse("admin:auth_user_add")

    def test_add_page_is_simple(self):
        r = self.client.get(self.add_url)
        self.assertContains(r, "Email them a link")
        self.assertContains(r, ">Admin<")
        self.assertNotContains(r, "user_permissions")
        self.assertNotContains(r, "Superuser status")

    def test_add_staff_with_email_link(self):
        from django.core import mail
        r = self.client.post(self.add_url, {"first_name": "Amy", "last_name": "Ng", "email": "Amy.Ng@example.com",
                                            "username": "", "role": "staff", "password_setup": "email"})
        self.assertEqual(r.status_code, 302)
        amy = User.objects.get(email="Amy.Ng@example.com")
        self.assertEqual(amy.username, "amy.ng")
        self.assertTrue(amy.is_staff and not amy.is_superuser)
        self.assertEqual(list(amy.groups.values_list("name", flat=True)), ["Staff"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/account/reset/", mail.outbox[0].body)
        self.assertIn("Username: amy.ng", mail.outbox[0].body)

    def test_add_admin_with_password(self):
        r = self.client.post(self.add_url, {"first_name": "Al", "last_name": "Bo", "email": "al@example.com",
                                            "username": "al", "role": "admin", "password_setup": "set",
                                            "password1": "Another-pass-889", "password2": "Another-pass-889"})
        self.assertEqual(r.status_code, 302)
        al = User.objects.get(username="al")
        self.assertTrue(al.is_superuser and al.check_password("Another-pass-889"))

    def test_add_errors(self):
        r = self.client.post(self.add_url, {"first_name": "X", "last_name": "Y", "email": "BOSS@example.com",
                                            "role": "staff", "password_setup": "set", "password1": "a"})
        self.assertContains(r, "Another user already has this email address")
        self.assertContains(r, "match")

    def test_change_role_and_last_admin_guard(self):
        sam = User.objects.create_user("sam", "sam@example.com", PW, is_staff=True)
        url = reverse("admin:auth_user_change", args=[sam.pk])
        data = {"username": "sam", "first_name": "Sam", "last_name": "Lee", "email": "sam@example.com",
                "role": "admin", "status_changes-TOTAL_FORMS": 0, "status_changes-INITIAL_FORMS": 0}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        sam.refresh_from_db()
        self.assertTrue(sam.is_superuser)
        # Boss can't change their own role (field disabled), so they stay an administrator.
        own = dict(data, username="boss", email="boss@example.com", role="staff")
        self.client.post(reverse("admin:auth_user_change", args=[self.boss.pk]), own)
        self.boss.refresh_from_db()
        self.assertTrue(self.boss.is_superuser)


@override_settings(STORAGES=STATIC, ADMIN_TWO_FACTOR=False)
class SettingsListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.boss = User.objects.create_superuser("boss", "boss@example.com", PW)
        self.sam = User.objects.create_user("sam", "sam@example.com", PW, is_staff=True)
        self.client.force_login(self.boss)

    def test_users_list_tabs_and_filters(self):
        from core import accounts
        accounts.set_status(self.boss, self.sam, True, "Left")
        url = reverse("admin:auth_user_changelist")
        r = self.client.get(url)
        self.assertContains(r, "Suspended <b>1</b>", html=False)
        self.assertContains(r, "Administrators <b>1</b>", html=False)
        self.assertContains(r, "+</span> Add user", html=False)
        r = self.client.get(url + "?account=suspended")
        self.assertContains(r, "<small>sam</small>", html=False)
        self.assertContains(r, "Showing 1 of 2")

    def test_history_and_authenticator_lists(self):
        from core import accounts
        accounts.set_status(self.boss, self.sam, True, "Left")
        r = self.client.get(reverse("admin:core_accountstatuschange_changelist") + "?action__exact=suspended")
        self.assertContains(r, "Left")
        self.assertContains(r, 'class="fb-tab is-on')
        r = self.client.get(reverse("admin:core_authenticatordevice_changelist"))
        self.assertContains(r, "Not finished")


@override_settings(STORAGES=STATIC, ADMIN_TWO_FACTOR=False)
class PasswordPanelTests(TestCase):
    def setUp(self):
        cache.clear()
        self.boss = User.objects.create_superuser("boss", "boss@example.com", PW)
        self.sam = User.objects.create_user("sam", "sam@example.com", PW, is_staff=True)
        self.client.force_login(self.boss)

    def test_no_hash_details_and_reset_link_email(self):
        from django.core import mail
        url = reverse("admin:auth_user_change", args=[self.sam.pk])
        r = self.client.get(url)
        self.assertNotContains(r, "pbkdf2")
        self.assertNotContains(r, "salt")
        self.assertContains(r, "Email a reset link")
        self.assertContains(r, "Set a new password")
        r = self.client.post(reverse("admin:auth_user_send_reset", args=[self.sam.pk]))
        self.assertRedirects(r, url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/account/reset/", mail.outbox[0].body)
        self.assertTrue(self.sam.check_password(PW))  # old password still works until they choose a new one
        self.assertEqual(self.client.get(reverse("admin:auth_user_send_reset", args=[self.sam.pk])).status_code, 403)
