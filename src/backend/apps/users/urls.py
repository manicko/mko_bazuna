"""Users app URLs."""

from apps.users.views.consent import consent_accept, consent_decline
from django.urls import path

app_name = "consent"

urlpatterns = [
    path("consent/accept/", consent_accept, name="accept"),
    path("consent/decline/", consent_decline, name="decline"),
]