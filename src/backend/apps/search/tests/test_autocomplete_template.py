"""
Verification test for HTMX autocomplete dropdown on the shared catalog header.

Confirms that ``components/header_catalog.html`` (the shared Avito-style header
rendered via ``{% include %}`` on ``ads/list.html`` and ``ads/detail.html``)
wires up the htmx-powered search autocomplete correctly: ``hx-get``,
``hx-trigger``, ``hx-target``, ``hx-swap``, the ``autocomplete-dropdown``
element, the ``search-input`` id, and that an inline ``<script>`` containing an
``htmx:afterRequest`` listener is present.

This test reads the template source directly and performs string assertions —
it does NOT require a database.
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Module-level template content (loaded once, like setUpClass)
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path("src/backend/templates")

_HEADER_CATALOG_CONTENT = (
    (_TEMPLATES_DIR / "components/header_catalog.html")
    .resolve()
    .read_text(encoding="utf-8")
)
_SUBMENU_CONTENT = (
    (_TEMPLATES_DIR / "categories/partials/mega_submenu.html")
    .resolve()
    .read_text(encoding="utf-8")
)
_BREADCRUMB_CONTENT = (
    (_TEMPLATES_DIR / "components/breadcrumb.html")
    .resolve()
    .read_text(encoding="utf-8")
)


def _read_template(rel_path: str) -> str:
    """Read a template file relative to the templates directory."""
    return (_TEMPLATES_DIR / rel_path).resolve().read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# autocomplete template
# ---------------------------------------------------------------------------


def test_search_input_has_htmx_autocomplete_attributes() -> None:
    """The search input carries all htmx autocomplete directives."""
    assert 'id="search-input"' in _HEADER_CATALOG_CONTENT
    assert 'name="q"' in _HEADER_CATALOG_CONTENT
    assert "hx-get=" in _HEADER_CATALOG_CONTENT
    assert "search:autocomplete" in _HEADER_CATALOG_CONTENT
    assert 'hx-trigger="input delay:300ms"' in _HEADER_CATALOG_CONTENT
    assert 'hx-target="#autocomplete-dropdown"' in _HEADER_CATALOG_CONTENT
    assert 'hx-swap="none"' in _HEADER_CATALOG_CONTENT
    assert 'autocomplete="off"' in _HEADER_CATALOG_CONTENT


def test_autocomplete_dropdown_element_exists() -> None:
    """The dropdown ``<ul>`` element is rendered after the input."""
    assert '<ul id="autocomplete-dropdown"' in _HEADER_CATALOG_CONTENT
    assert "autocomplete-dropdown" in _HEADER_CATALOG_CONTENT


def test_inline_script_follows_htmx() -> None:
    """An inline ``<script>`` block is present for autocomplete behavior."""
    assert "<script>" in _HEADER_CATALOG_CONTENT
    assert "htmx:afterRequest" in _HEADER_CATALOG_CONTENT, (
        "Script should attach an htmx:afterRequest listener"
    )


def test_no_settings_dot_access_in_template() -> None:
    """Template should not reference ``settings.BOT_USERNAME`` directly
    (settings must be passed via context, not context processors)."""
    assert "settings.BOT_USERNAME" not in _HEADER_CATALOG_CONTENT


def test_bot_username_comes_from_context() -> None:
    """The place-an-ad deep-link uses the ``bot_username`` context var."""
    assert "{{ bot_username }}" in _HEADER_CATALOG_CONTENT


def test_catalog_header_included_in_pages() -> None:
    """list.html and detail.html render the shared catalog header."""
    list_path = _read_template("ads/list.html")
    detail_path = _read_template("ads/detail.html")
    assert '{% include "components/header_catalog.html" %}' in list_path
    assert '{% include "components/header_catalog.html" %}' in detail_path


# ---------------------------------------------------------------------------
# catalog menu accordion template (Spec_020)
# ---------------------------------------------------------------------------


def test_submenu_container_carries_hidden_class() -> None:
    """The lazy-loaded submenu container must start hidden so the accordion
    can detect ``isOpen`` correctly (Spec_020 R-01a)."""
    assert 'class="hidden ml-4" data-category-submenu="' in _SUBMENU_CONTENT, (
        "mega_submenu.html submenu container must carry the hidden class"
    )


def test_closeBranch_function_present() -> None:
    """``closeBranch`` must be defined in header_catalog.html."""
    assert "function closeBranch(" in _HEADER_CATALOG_CONTENT


def test_collapseSiblings_function_present() -> None:
    """``collapseSiblings`` must be defined in header_catalog.html."""
    assert "function collapseSiblings(" in _HEADER_CATALOG_CONTENT


def test_collapseBranches_removed() -> None:
    """The old all-panel collapse helper must be removed."""
    assert "collapseBranches" not in _HEADER_CATALOG_CONTENT


def test_children_exists_replaces_get_children_count_in_header() -> None:
    """Expand-button condition uses ``get_children.exists``, not the
    non-existent ``get_children_count`` (RC-A)."""
    assert "cat.get_children.exists" in _HEADER_CATALOG_CONTENT
    assert "get_children_count" not in _HEADER_CATALOG_CONTENT


def test_children_exists_replaces_get_children_count_in_submenu() -> None:
    """mega_submenu.html uses ``get_children.exists`` (RC-A)."""
    assert "child.get_children.exists" in _SUBMENU_CONTENT
    assert "get_children_count" not in _SUBMENU_CONTENT


def test_firstof_replaced_with_with_tag() -> None:
    """``current_cat`` must be set via ``{% with %}`` so it stays a Category
    instance, not a string (RC-B)."""
    assert "firstof" not in _HEADER_CATALOG_CONTENT
    assert "{% with current_cat=breadcrumb_category %}" in _HEADER_CATALOG_CONTENT


def test_breadcrumb_uses_safe_last_element_access() -> None:
    """breadcrumb.html must not index the ancestor queryset with ``|last``
    (crashes on empty); it binds the last ancestor inside the length-guarded
    branch (RC-C)."""
    assert "get_ancestors|last" not in _BREADCRUMB_CONTENT
    assert 'slice:"::-1"|first' in _BREADCRUMB_CONTENT


def test_downward_caret_in_header() -> None:
    """Expand buttons in header_catalog.html use a downward caret, not right-chevron."""
    assert 'd="M5 9l7 7 7-7"' in _HEADER_CATALOG_CONTENT
    assert 'd="M9 5l7 7-7 7"' not in _HEADER_CATALOG_CONTENT


def test_downward_caret_in_submenu() -> None:
    """Expand buttons in mega_submenu.html use a downward caret, not right-chevron."""
    assert 'd="M5 9l7 7 7-7"' in _SUBMENU_CONTENT
    assert 'd="M9 5l7 7-7 7"' not in _SUBMENU_CONTENT


def test_expand_button_has_aria_controls() -> None:
    """Each expand button has an aria-controls attribute referencing the submenu id."""
    assert 'aria-controls="menu-{{' in _HEADER_CATALOG_CONTENT
    assert 'aria-controls="menu-{{' in _SUBMENU_CONTENT


def test_submenu_container_has_id() -> None:
    """Each submenu container div has an id matching its button's aria-controls."""
    assert 'id="menu-{{' in _HEADER_CATALOG_CONTENT
    assert 'id="menu-{{' in _SUBMENU_CONTENT


def test_expand_button_meets_44px_hit_area() -> None:
    """Expand buttons meet the 44×44px minimum touch target."""
    assert "min-w-[44px]" in _HEADER_CATALOG_CONTENT
    assert "min-w-[44px]" in _SUBMENU_CONTENT
    assert "px-2 py-2" not in _HEADER_CATALOG_CONTENT
    assert "px-2 py-2" not in _SUBMENU_CONTENT


def test_svg_has_rotation_transition() -> None:
    """Expand-button SVGs carry the rotation transition utility for smooth animation."""
    assert "transition-transform" in _HEADER_CATALOG_CONTENT
    assert "transition-transform" in _SUBMENU_CONTENT


def test_js_rotation_toggle_present() -> None:
    """Inline JS toggles rotate-180 on the SVG when aria-expanded changes."""
    assert "classList.add('rotate-180')" in _HEADER_CATALOG_CONTENT
    assert "classList.remove('rotate-180')" in _HEADER_CATALOG_CONTENT
