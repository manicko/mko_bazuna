"""Categories app URLs."""

from apps.categories.views import category_submenu
from django.urls import path

app_name = "categories"

urlpatterns = [
    path(
        "categories/<slug:slug>/submenu/",
        category_submenu,
        name="category_submenu",
    ),
]
