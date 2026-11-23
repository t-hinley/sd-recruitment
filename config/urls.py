from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core.sitemaps import StaticViewSitemap
from core import views as core_views
from core.views import robots_txt

urlpatterns = [
    # "Forgot your password?" on the admin login page (Django looks for this name).
    path("admin/password_reset/", core_views.PasswordResetView.as_view(), name="admin_password_reset"),
    path("admin/", admin.site.urls),
    path("account/password-reset/", core_views.PasswordResetView.as_view(), name="password_reset"),
    path("account/password-reset/sent/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("account/reset/<uidb64>/<token>/", core_views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("account/reset/done/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("session/ping/", core_views.session_ping, name="session_ping"),
    path("session/expire/", core_views.session_expire, name="session_expire"),
    path("sitemap.xml", sitemap, {"sitemaps": {"pages": StaticViewSitemap}}, name="sitemap"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("", include("core.urls")),
]
