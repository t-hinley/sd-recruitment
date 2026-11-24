from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("employers/", views.employers, name="employers"),
    path("candidates/", views.candidates, name="candidates"),
    path("career-services/", views.career_services, name="career_services"),
    path("contact/", views.contact, name="contact"),
    path("privacy/", views.privacy, name="privacy"),
]
