"""URL routes for the ``moderation`` JSON API surface (``/api/v1/moderation/``).

Mounted by ``apps/api/urls.py`` under the ``moderation/`` prefix. ``app_name`` is
``moderation_api`` to avoid colliding with the HTML ``moderation`` namespace
(``apps/moderation/urls.py``).
"""

from django.urls import path

from apps.moderation.views.api.actions import approve_view, ban_view, reject_view
from apps.moderation.views.api.queue import queue_view
from apps.moderation.views.api.review import review_view

app_name = "moderation_api"

urlpatterns = [
    path("queue/", queue_view, name="queue"),
    path("review/<int:ad_id>/", review_view, name="review"),
    # S4.7 — single-ad actions (plan §2.4 row 13): the JSON siblings of the HTML
    # ``approve`` / ``reject`` / ``ban`` repair views. The action name is on the
    # URL and the ad id follows it, matching the HTML mirror routes.
    path("approve/<int:ad_id>/", approve_view, name="approve"),
    path("reject/<int:ad_id>/", reject_view, name="reject"),
    path("ban/<int:ad_id>/", ban_view, name="ban"),
]
