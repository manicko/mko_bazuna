"""
Global template tags for the Mko Bazuna ads app.

Provides the ``component_tag`` filter for rendering reusable component partials
(e.g. feature tags) with a context dict, keeping includes DRY and unit-testable.
"""

from django import template
from django.template.loader import render_to_string
from django.utils.safestring import SafeString

register = template.Library()


@register.filter
def component_tag(feature) -> SafeString:
    """Render a feature tag component for a LookupItem.

    Wraps the ``{% include "components/feature_tag.html" %}`` partial so the
    rendering path is DRY and can be unit-tested as a template filter.

    Args:
        feature: A ``LookupItem`` instance (typically from ``ad.features.all()``).

    Returns:
        Rendered HTML for the feature-tag span, marked safe so the template
        engine does not escape it.
    """
    html: str = render_to_string(
        "components/feature_tag.html",
        {"feature": feature},
    )
    return SafeString(html)
