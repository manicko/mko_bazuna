"""
Context processors for Mko Bazuna.

Makes configuration values available to all templates.
"""

import json
from enum import StrEnum

from django.conf import settings
from django.utils.translation import gettext as _


def plausible_host(request):
    """
    Add PLAUSIBLE_HOST to template context.

    Returns empty string if not configured (no analytics snippet rendered).
    """
    return {"PLAUSIBLE_HOST": settings.PLAUSIBLE_HOST}


def language(request) -> dict:
    """Expose current language to templates."""
    return {"LANGUAGE_CODE": getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)}


def header_context(request) -> dict:
    """Add shared catalog-header context to every template.

    Exposes:
    - ``bot_username``: Telegram bot username (deep-link target for the
      "place an ad" CTA). Templates must never reference ``settings.BOT_USERNAME``
      directly.
    - ``root_categories``: ordered list of top-level active ``Category`` nodes
      (rendered server-side inside the header's "All Categories" dropdown).
    - ``preferred_city_display``: localized name of the effective preferred city
      (from ``request.preferred_city``), or the country-wide label
      (``gettext("Entire country")``) when none is set — shown by the header
      city button.
    - ``cities``: ordered list of Montenegro ``City`` objects for the header
      city dropdown.
    - ``catalog_js_labels``: JSON-encoded dict of translated strings consumed by
      the inline JS in ``components/header_catalog.html`` (Q6=A — pre-translated
      context variables, no Cyrillic literals in the ``<script>`` block).

    A single indexed MPTT query is acceptable for the MVP (no per-request
    profiling concern).
    """
    from apps.categories.models import Category
    from apps.locations.models import City

    # The header city badge reflects the *effective* city — the one whose ads
    # are actually being filtered — not the stored preference. The effective
    # slug is an explicit URL selection (``/city/<slug>/`` or ``?city=``) that
    # ``CityResolutionMiddleware`` exposes as ``request.current_city`` on every
    # request; the persisted
    # preference (``request.preferred_city``) is only the fallback when the URL
    # carries no city. Reading the badge from the preference alone is incorrect:
    # that preference is written by an asynchronous POST (set_preferred_city)
    # that races with the client-side ``window.location.href`` navigation, so
    # the rendered page paints the *previous* selection — the off-by-one
    # reported in Problem 04. Deriving the label from the effective URL city
    # keeps it in lock-step with the address bar and the ad filter.
    preferred_city_display = _("Entire country")
    for city_slug in (
        getattr(request, "current_city", None),
        getattr(request, "preferred_city", None),
    ):
        if not city_slug:
            continue
        city = City.objects.filter(slug=city_slug).first()
        if city is not None:
            locale = (
                getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)
                or settings.LANGUAGE_CODE
            )
            preferred_city_display = city.get_name(locale)
            break

    # Number of the authenticated user's favorites (header heart badge).
    # Anonymous visitors get ``None`` (the badge renders an outline heart with
    # no count). Uses ``getattr`` so bare ``HttpRequest()`` (no middleware-set
    # ``user``) does not raise — existing context-processor tests rely on this.
    user = getattr(request, "user", None)
    favorites_count = None
    if user is not None and user.is_authenticated:
        favorites_count = user.favorites.count()

    return {
        "bot_username": settings.BOT_USERNAME,
        "root_categories": list(
            Category.objects.root_nodes().filter(is_active=True).order_by("name")
        ),
        "preferred_city_display": preferred_city_display,
        "cities": list(City.objects.order_by("name")),
        "favorites_count": favorites_count,
        "catalog_js_labels": json.dumps(
            {
                "show_all_results": _("Show all results"),
                "cities": _("Cities"),
                "categories": _("Categories"),
                "popular_queries": _("Popular queries"),
                "history": _("History"),
            }
        ),
    }


def site_config(request) -> dict:
    """Inject the admin-configured site name into every template context."""
    from apps.core.services.site_config import get_site_name

    return {"site_name": get_site_name()}


def price_step(request) -> dict[str, StrEnum]:
    """Expose the HTML price-input step to all templates.

    Returns the ``PriceStep.DEFAULT`` enum member so templates can
    render ``step="{{ price_step.value }}"`` instead of hardcoding
    a numeric string.
    """
    from apps.core.enums import PriceStep

    return {"price_step": PriceStep.DEFAULT}
