"""Users app URLs."""

from apps.users.views.consent import (
    consent_accept,
    consent_decline,
    login_issue,
    login_status,
    consent_withdraw,
)
from apps.users.views.logout import logout_view
from django.urls import path

app_name = "consent"

urlpatterns = [
    path("consent/accept/", consent_accept, name="accept"),
    path("consent/decline/", consent_decline, name="decline"),
    path("consent/withdraw/", consent_withdraw, name="withdraw"),
    path("login/issue/", login_issue, name="login_issue"),
    path("login/status/", login_status, name="login_status"),
    path("logout/", logout_view, name="logout"),
]
