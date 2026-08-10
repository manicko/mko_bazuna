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
    except (AttributeError, TypeError):
        return None
