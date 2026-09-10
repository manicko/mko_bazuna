"""Categories app URLs."""

from django.urls import path

from apps.categories.views import category_submenu

app_name = "categories"

urlpatterns = [
    path(
        "categories/<slug:slug>/submenu/",
        category_submenu,
        name="category_submenu",
    ),
]
