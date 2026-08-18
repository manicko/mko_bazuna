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

    A single indexed MPTT query is acceptable for the MVP (no per-request
    profiling concern).
    """
    from apps.categories.models import Category

    return {
        "bot_username": settings.BOT_USERNAME,
        "root_categories": list(
            Category.objects.root_nodes().filter(is_active=True).order_by("name")
        ),
    }
