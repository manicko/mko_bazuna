"""
Template filters for localized ad content.

Provides filters that call Ad.get_title(locale) and Ad.get_description(locale)
using LANGUAGE_CODE from template context.

Usage:
    {% load localized_content %}
    {{ ad|get_title:LANGUAGE_CODE }}
    {{ ad|get_description:LANGUAGE_CODE }}
"""

from django import template

register = template.Library()


@register.filter
def get_title(ad, locale: str = "ru") -> str:
    """
    Return localized ad title using the given locale.

    Delegates to Ad.get_title(locale) with fallback chain: locale → ru → original.

    Args:
        ad: The Ad instance.
        locale: Language code (e.g. "ru", "bs", "en").

    Returns:
        Localized title string.
    """
    return ad.get_title(locale=locale)


@register.filter
def get_description(ad, locale: str = "ru") -> str:
    """
    Return localized ad description using the given locale.

    Delegates to Ad.get_description(locale) with fallback chain: locale → ru → original.

    Args:
        ad: The Ad instance.
        locale: Language code (e.g. "ru", "bs", "en").

    Returns:
        Localized description string.
    """
    return ad.get_description(locale=locale)


@register.filter
def get_lookup_name(item, locale: str = "ru") -> str:
    """
    Return the localized name of a lookup item (purpose/feature).

    Delegates to LookupItem.get_name(locale) with fallback chain:
    locale → ru → slug.

    Args:
        item: The LookupItem instance.
        locale: Language code (e.g. "ru", "bs", "en").

    Returns:
        Localized name string.
    """
    return item.get_name(locale=locale)


@register.filter
def get_category_name(category, locale: str = "ru") -> str:
    """
    Return the localized name of a Category.

    Delegates to Category.get_name(locale) with fallback chain:
    locale → ru → name.

    Args:
        category: The Category instance (or None).
        locale: Language code (e.g. "ru", "bs", "en").

    Returns:
        Localized name string, or "" if category is None.
    """
    if category is None:
        return ""
    return category.get_name(locale=locale)


@register.filter
def get_city_name(city, locale: str = "ru") -> str:
    """
    Return the localized name of a City.

    Delegates to City.get_name(locale) with fallback chain:
    locale → ru → name.

    Args:
        city: The City instance (or None).
        locale: Language code (e.g. "ru", "bs", "en").

    Returns:
        Localized name string, or "" if city is None.
    """
    if city is None:
        return ""
    return city.get_name(locale=locale)