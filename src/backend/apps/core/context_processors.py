"""
Context processors for Mko Bazuna.

Makes configuration values available to all templates.
"""

from django.conf import settings


def plausible_host(request):
    """
    Add PLAUSIBLE_HOST to template context.

    Returns empty string if not configured (no analytics snippet rendered).
    """
    return {"PLAUSIBLE_HOST": settings.PLAUSIBLE_HOST}


def language(request) -> dict:
    """Expose current language to templates."""
    return {"LANGUAGE_CODE": getattr(request, "LANGUAGE_CODE", "ru")}


def header_context(request) -> dict:
    """Add shared catalog-header context to every template.

    Exposes:
    - ``bot_username``: Telegram bot username (deep-link target for the
      "place an ad" CTA). Templates must never reference ``settings.BOT_USERNAME``
      directly.
    - ``root_categories``: ordered list of top-level active ``Category`` nodes
      (rendered server-side inside the header's "All Categories" dropdown).
    - ``preferred_city_display``: localized name of the effective preferred city
      (from ``request.preferred_city``), or the country-wide label (``Вся страна``)
      when none is set — shown by the header city button.
    - ``cities``: ordered list of Montenegro ``City`` objects for the header
      city dropdown.

    A single indexed MPTT query is acceptable for the MVP (no per-request
    profiling concern).
    """
    from apps.categories.models import Category
    from apps.locations.models import City

    # Default label when no preferred city is set (Q-2 recommended default).
    preferred_city_display = "Вся страна"
    preferred_city_slug = getattr(request, "preferred_city", None)
    if preferred_city_slug:
        city = City.objects.filter(slug=preferred_city_slug).first()
        if city is not None:
            locale = getattr(request, "LANGUAGE_CODE", "ru") or "ru"
            preferred_city_display = city.get_name(locale)

    return {
        "bot_username": settings.BOT_USERNAME,
        "root_categories": list(
            Category.objects.root_nodes().filter(is_active=True).order_by("name")
        ),
        "preferred_city_display": preferred_city_display,
        "cities": list(City.objects.order_by("name")),
    }
