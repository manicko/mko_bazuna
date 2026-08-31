"""
Template filters for dictionary lookups in Django templates.

Django's template language does not support subscript syntax
(``{{ dict[key] }}``), so dynamic dictionary lookups require a custom
``get_item`` filter. This follows the same ``@register.filter`` pattern
already established by ``contact_tags.can_contact`` and
``localized_content.get_title``.

Usage in templates::

    {% load dict_tags %}
    {{ status_labels|get_item:status }}
"""

from typing import Any

from django import template

register = template.Library()


@register.filter
def get_item(dictionary: Any, key: Any) -> Any:
    """Look up ``key`` in ``dictionary``, returning ``None`` if absent.

    Works with any mapping that implements ``.get(key)``. Returns ``None``
    when the dictionary is missing, the key is absent, or the value is
    not a mapping at all.

    Args:
        dictionary: A mapping (dict, QueryDict, etc.) or ``None``.
        key: The lookup key (any hashable type).

    Returns:
        The value stored under ``key``, or ``None``.
    """
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except AttributeError, TypeError:
        return None


@register.simple_tag
def query_replace(request: Any, **kwargs: Any) -> str:
    """Copy ``request.GET``, apply keyword overrides, return a urlencoded string.

    Each keyword argument sets (or replaces) the corresponding query parameter.
    Useful in templates for building navigation links that preserve the current
    query string while changing or adding selected parameters.

    Usage in templates::

        {% load dict_tags %}
        <a href="?{% query_replace request lang=language.code %}">

    Args:
        request: The current ``HttpRequest`` (available via the ``request``
            context processor).
        **kwargs: Parameter name/value pairs to set on the resulting query.

    Returns:
        A URL-encoded query string (without the leading ``?``).
    """
    query = request.GET.copy()
    for key, value in kwargs.items():
        query[key] = value
    return query.urlencode()
