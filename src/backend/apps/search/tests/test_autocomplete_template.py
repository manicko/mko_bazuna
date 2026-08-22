"""
Verification test for HTMX autocomplete dropdown on the shared catalog header.

Confirms that ``components/header_catalog.html`` (the shared Avito-style header
rendered via ``{% include %}`` on ``ads/list.html`` and ``ads/detail.html``)
wires up the htmx-powered search autocomplete correctly: ``hx-get``,
``hx-trigger``, ``hx-target``, ``hx-swap``, the ``autocomplete-dropdown``
element, the ``search-input`` id, and that an inline ``<script>`` containing an
``htmx:afterRequest`` listener is present.

This test reads the template source directly and performs string assertions —
it does NOT require a database (``SimpleTestCase``).
"""

from pathlib import Path

import pytest
from django.test import SimpleTestCase

pytestmark = [pytest.mark.unit]


class TestAutocompleteTemplate(SimpleTestCase):
    """Verify HTMX autocomplete wiring in ``components/header_catalog.html``."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.template_path = (
            Path("src/backend/templates/components/header_catalog.html").resolve()
        )
        cls.content = cls.template_path.read_text(encoding="utf-8")

    def test_search_input_has_htmx_autocomplete_attributes(self) -> None:
        """The search input carries all htmx autocomplete directives."""
        self.assertIn('id="search-input"', self.content)
        self.assertIn('name="q"', self.content)
        self.assertIn("hx-get=", self.content)
        self.assertIn("search:autocomplete", self.content)
        self.assertIn('hx-trigger="input delay:300ms"', self.content)
        self.assertIn('hx-target="#autocomplete-dropdown"', self.content)
        self.assertIn('hx-swap="none"', self.content)
        self.assertIn('autocomplete="off"', self.content)

    def test_autocomplete_dropdown_element_exists(self) -> None:
        """The dropdown ``<ul>`` element is rendered after the input."""
        self.assertIn('<ul id="autocomplete-dropdown"', self.content)
        self.assertIn("autocomplete-dropdown", self.content)

    def test_inline_script_follows_htmx(self) -> None:
        """An inline ``<script>`` block is present for autocomplete behavior."""
        self.assertIn("<script>", self.content)
        self.assertIn(
            "htmx:afterRequest",
            self.content,
            msg="Script should attach an htmx:afterRequest listener",
        )

    def test_no_settings_dot_access_in_template(self) -> None:
        """Template should not reference ``settings.BOT_USERNAME`` directly
        (settings must be passed via context, not context processors)."""
        self.assertNotIn("settings.BOT_USERNAME", self.content)

    def test_bot_username_comes_from_context(self) -> None:
        """The place-an-ad deep-link uses the ``bot_username`` context var."""
        self.assertIn("{{ bot_username }}", self.content)

    def test_catalog_header_included_in_pages(self) -> None:
        """list.html and detail.html render the shared catalog header."""
        list_path = Path("src/backend/templates/ads/list.html").resolve()
        detail_path = Path("src/backend/templates/ads/detail.html").resolve()
        self.assertIn(
            '{% include "components/header_catalog.html" %}',
            list_path.read_text(encoding="utf-8"),
        )
        self.assertIn(
            '{% include "components/header_catalog.html" %}',
            detail_path.read_text(encoding="utf-8"),
        )


class TestCatalogMenuAccordionTemplate(SimpleTestCase):
    """Verify the category accordion redesign (Spec_020) in the templates.

    Confirms the ``hidden`` class on the dynamically-injected submenu container
    in ``mega_submenu.html`` (the prerequisite for level-2+ expansion) and that
    ``header_catalog.html`` identifies branches via ``closeBranch`` /
    ``collapseSiblings`` rather than the removed ``collapseBranches`` which
    destroyed ancestor state. Template-source assertions only (no DB).
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.header_content = (
            Path("src/backend/templates/components/header_catalog.html")
            .resolve()
            .read_text(encoding="utf-8")
        )
        cls.submenu_content = (
            Path("src/backend/templates/categories/partials/mega_submenu.html")
            .resolve()
            .read_text(encoding="utf-8")
        )

    def test_submenu_container_carries_hidden_class(self) -> None:
        """The lazy-loaded submenu container must start hidden so the accordion
        can detect ``isOpen`` correctly (Spec_020 R-01a)."""
        self.assertIn(
            'class="hidden ml-4" data-category-submenu="',
            self.submenu_content,
            msg="mega_submenu.html submenu container must carry the hidden class",
        )

    def test_closeBranch_function_present(self) -> None:
        """``closeBranch`` must be defined in header_catalog.html."""
        self.assertIn("function closeBranch(", self.header_content)

    def test_collapseSiblings_function_present(self) -> None:
        """``collapseSiblings`` must be defined in header_catalog.html."""
        self.assertIn("function collapseSiblings(", self.header_content)

    def test_collapseBranches_removed(self) -> None:
        """The old all-panel collapse helper must be removed."""
        self.assertNotIn("collapseBranches", self.header_content)

    def test_children_exists_replaces_get_children_count_in_header(self) -> None:
        """Expand-button condition uses ``get_children.exists``, not the
        non-existent ``get_children_count`` (RC-A)."""
        self.assertIn("cat.get_children.exists", self.header_content)
        self.assertNotIn("get_children_count", self.header_content)

    def test_children_exists_replaces_get_children_count_in_submenu(self) -> None:
        """mega_submenu.html uses ``get_children.exists`` (RC-A)."""
        self.assertIn("child.get_children.exists", self.submenu_content)
        self.assertNotIn("get_children_count", self.submenu_content)

    def test_firstof_replaced_with_with_tag(self) -> None:
        """``current_cat`` must be set via ``{% with %}`` so it stays a Category
        instance, not a string (RC-B)."""
        self.assertNotIn("firstof", self.header_content)
        self.assertIn(
            "{% with current_cat=breadcrumb_category %}", self.header_content
        )

    def test_breadcrumb_uses_safe_last_element_access(self) -> None:
        """breadcrumb.html must not index the ancestor queryset with ``|last``
        (crashes on empty); it binds the last ancestor inside the length-guarded
        branch (RC-C)."""
        breadcrumb_content = (
            Path("src/backend/templates/components/breadcrumb.html")
            .resolve()
            .read_text(encoding="utf-8")
        )
        self.assertNotIn("get_ancestors|last", breadcrumb_content)
        self.assertIn('slice:"::-1"|first', breadcrumb_content)

    def test_downward_caret_in_header(self) -> None:
        """Expand buttons in header_catalog.html use a downward caret, not right-chevron."""
        self.assertIn('d="M5 9l7 7 7-7"', self.header_content)
        self.assertNotIn('d="M9 5l7 7-7 7"', self.header_content)

    def test_downward_caret_in_submenu(self) -> None:
        """Expand buttons in mega_submenu.html use a downward caret, not right-chevron."""
        self.assertIn('d="M5 9l7 7 7-7"', self.submenu_content)
        self.assertNotIn('d="M9 5l7 7-7 7"', self.submenu_content)

    def test_expand_button_has_aria_controls(self) -> None:
        """Each expand button has an aria-controls attribute referencing the submenu id."""
        self.assertIn('aria-controls="menu-{{', self.header_content)
        self.assertIn('aria-controls="menu-{{', self.submenu_content)

    def test_submenu_container_has_id(self) -> None:
        """Each submenu container div has an id matching its button's aria-controls."""
        self.assertIn('id="menu-{{', self.header_content)
        self.assertIn('id="menu-{{', self.submenu_content)

    def test_expand_button_meets_44px_hit_area(self) -> None:
        """Expand buttons meet the 44×44px minimum touch target."""
        self.assertIn('min-w-[44px]', self.header_content)
        self.assertIn('min-w-[44px]', self.submenu_content)
        self.assertNotIn('px-2 py-2', self.header_content)
        self.assertNotIn('px-2 py-2', self.submenu_content)

    def test_svg_has_rotation_transition(self) -> None:
        """Expand-button SVGs carry the rotation transition utility for smooth animation."""
        self.assertIn('transition-transform', self.header_content)
        self.assertIn('transition-transform', self.submenu_content)

    def test_js_rotation_toggle_present(self) -> None:
        """Inline JS toggles rotate-180 on the SVG when aria-expanded changes."""
        self.assertIn("classList.add('rotate-180')", self.header_content)
        self.assertIn("classList.remove('rotate-180')", self.header_content)
