"""Users app URLs."""

from django.urls import path

from apps.users.views.consent import (
    consent_accept,
    consent_decline,
    consent_withdraw,
    login_issue,
    login_status,
)
from apps.users.views.logout import logout_view

app_name = "consent"

urlpatterns = [
    path("consent/accept/", consent_accept, name="accept"),
    path("consent/decline/", consent_decline, name="decline"),
    path("consent/withdraw/", consent_withdraw, name="withdraw"),
    path("login/issue/", login_issue, name="login_issue"),
    path("login/status/", login_status, name="login_status"),
    path("logout/", logout_view, name="logout"),
]
