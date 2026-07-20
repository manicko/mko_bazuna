"""
Template tags for contact button render conditions.

Provides `can_contact` filter for zone R2 conditions in templates.
"""

from django import template

from apps.core.services.contact import can_contact_seller

register = template.Library()


@register.filter
def can_contact(ad) -> bool:
    """
    Check if contact button should render for an ad.

    Zone R2 conditions:
        - ad.status == PUBLISHED
        - seller.telegram_id IS NOT NULL
        - NOT seller.is_deleted
        - NOT seller.is_banned
        - seller.consent_revoked_at IS NULL

    Args:
        ad: The ad object to check.

    Returns:
        True if contact button should render, False otherwise.
    """
    return can_contact_seller(ad)