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
