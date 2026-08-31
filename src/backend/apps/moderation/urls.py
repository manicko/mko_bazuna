"""
URLs for moderation app admin views.
"""

from apps.moderation.views import approve_ad, ban_user, moderation_review, reject_ad
from apps.moderation.views.api_bulk import bulk_moderation_action
from apps.moderation.views.queue import moderation_queue
from django.urls import path

app_name = "moderation"

urlpatterns = [
    path("queue/", moderation_queue, name="queue"),
    path("review/<int:ad_id>/", moderation_review, name="review"),
    path("approve/<int:ad_id>/", approve_ad, name="approve"),
    path("reject/<int:ad_id>/", reject_ad, name="reject"),
    path("ban/<int:ad_id>/", ban_user, name="ban"),
    path("bulk-action/", bulk_moderation_action, name="bulk_action"),
]
