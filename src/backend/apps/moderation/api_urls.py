"""URL routes for the ``moderation`` JSON API surface (``/api/v1/moderation/``).

Mounted by ``apps/api/urls.py`` under the ``moderation/`` prefix. ``app_name`` is
``moderation_api`` to avoid colliding with the HTML ``moderation`` namespace
(``apps/moderation/urls.py``).
"""

from django.urls import path

from apps.moderation.views.api.queue import queue_view
from apps.moderation.views.api.review import review_view

app_name = "moderation_api"

urlpatterns = [
    path("queue/", queue_view, name="queue"),
    path("review/<int:ad_id>/", review_view, name="review"),
]
