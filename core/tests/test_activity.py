from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

PW = "a-long-pass-12345"
STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
          "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


@override_settings(STORAGES=STATIC, ADMIN_TWO_FACTOR=False)
class ActivityPageTests(TestCase):
    def setUp(self):
        from django.contrib.admin.models import CHANGE, LogEntry
        self.boss = User.objects.create_superuser("boss", "boss@x.com", PW)
        self.ann = User.objects.create_user("ann", "ann@x.com", PW, is_staff=True)
        for u, name in ((self.boss, "Boss edit"), (self.ann, "Ann edit")):
            LogEntry.objects.log_actions(user_id=u.pk, queryset=[u], action_flag=CHANGE, single_object=True,
                                         change_message=name)
        self.url = reverse("admin:admin_logentry_changelist")

    def test_staff_see_only_their_own_and_admins_can_see_everyone(self):
        self.client.force_login(self.ann)
        r = self.client.get(self.url + "?who=all")
        self.assertContains(r, "Ann edit")
        self.assertNotContains(r, "Boss edit")
        self.client.force_login(self.boss)
        r = self.client.get(self.url + "?who=me")
        self.assertContains(r, "Boss edit")
        self.assertNotContains(r, "Ann edit")
        r = self.client.get(self.url)
        self.assertContains(r, "Ann edit")
        self.assertContains(r, "Boss edit")

    def test_read_only_and_linked_from_dashboard(self):
        from django.contrib.admin.models import LogEntry
        self.client.force_login(self.boss)
        entry = LogEntry.objects.first()
        self.assertEqual(self.client.get(reverse("admin:admin_logentry_delete", args=[entry.pk])).status_code, 403)
        self.assertContains(self.client.get(reverse("admin:index")), self.url + "?who=me")
