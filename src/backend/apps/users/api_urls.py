"""URL routes for the ``users`` JSON API surface (``/api/v1/``).

Mounted by ``apps/api/urls.py`` at the ``/api/v1/`` root. The routes are
prefix-based and orthogonal to the module host (plan §2.3 Q1): the consent
endpoints live under ``consent/`` and the logout endpoint under ``auth/``.

``app_name = "users_api"`` (no collision with the HTML ``consent`` namespace).
"""

from django.urls import path

from apps.users.views.api.consent import (
    consent_accept_view,
    consent_decline_view,
    consent_withdraw_view,
)
from apps.users.views.api.logout import logout_api_view

app_name = "users_api"

urlpatterns = [
    path("consent/accept/", consent_accept_view, name="consent_accept"),
    path("consent/decline/", consent_decline_view, name="consent_decline"),
    path("consent/withdraw/", consent_withdraw_view, name="consent_withdraw"),
    path("auth/logout/", logout_api_view, name="logout"),
]
