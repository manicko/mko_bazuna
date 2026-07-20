"""
URLs for moderation app admin views.
"""

from django.urls import path

from apps.moderation.views import approve_ad, ban_user, moderation_review, reject_ad

app_name = "moderation"

urlpatterns = [
    path("review/<int:ad_id>/", moderation_review, name="review"),
    path("approve/<int:ad_id>/", approve_ad, name="approve"),
    path("reject/<int:ad_id>/", reject_ad, name="reject"),
    path("ban/<int:ad_id>/", ban_user, name="ban"),
]