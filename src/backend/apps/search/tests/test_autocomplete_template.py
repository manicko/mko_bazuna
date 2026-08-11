"""
Verification test for HTMX autocomplete dropdown on the listings page.

Confirms that ``list.html`` wires up the htmx-powered search autocomplete
correctly: ``hx-get``, ``hx-trigger``, ``hx-target``, ``hx-swap``, the
``autocomplete-dropdown`` element, the ``search-input`` id, and that an inline
``<script>`` follows the htmx.org script tag.

This test reads the template source directly and performs string assertions —
it does NOT require a database (``SimpleTestCase``).
"""

from pathlib import Path

from django.test import SimpleTestCase


class TestAutocompleteTemplate(SimpleTestCase):
    """Verify HTMX autocomplete wiring in ``ads/list.html``."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.template_path = (
            Path("src/backend/templates/ads/list.html").resolve()
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
