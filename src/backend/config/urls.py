"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("moderation/", include("apps.moderation.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.ads.urls")),
    path("", include("apps.categories.urls")),
    path("", include("apps.locations.urls")),
    path("", include("apps.search.urls")),
    path("", include("apps.core.urls")),
]