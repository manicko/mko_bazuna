"""
Tests for lookup cache-key naming convention (13-PERF-006).

Verifies that lookup cache keys follow the documented convention in
``docs/architecture/cache-strategy.md``:

    <namespace>:v<N>:<segments...>

All keys must:
  - Start with ``lookup:v1`` (namespace + static version for format)
  - Include a content-version segment after the static version
  - Use lowercase, colon-separated segments
  - Change when the content version bumps

Unlike the old prefix-wipe approach (``lookup:active_items:{group_code}``,
``lookup:resolved_purposes:{category_id}``), the new keys embed a version
counter so invalidation makes old entries unreachable without a global
``delete_pattern``.
"""

from __future__ import annotations

import re

import pytest

from apps.categories.services.lookup_resolution import (
    RESOLVED_CONDITIONS_SEGMENT,
    RESOLVED_FEATURES_SEGMENT,
    RESOLVED_PURPOSES_SEGMENT,
    bump_lookup_resolve_version,
    get_lookup_resolve_version,
    resolved_lookup_key,
)
from apps.lookups.services.cache_service import (
    LookupCacheKey,
    active_items_key,
    all_groups_key,
    bump_lookup_version,
    get_lookup_version,
)

# All lookup cache keys must match this pattern:
#   lookup:v1:<segments...>
# The version-bump counter appears as a numeric segment after the
# static :v1: format marker (and an optional sub-namespace like :resolve:).
_KEY_RE = re.compile(r"^lookup:v1:.+$")


class TestLookupCacheKeyConvention:
    """All lookup cache keys conform to the ``<namespace>:v<N>:<segments>`` format."""

    pytestmark = pytest.mark.unit

    def test_all_groups_key_format(self):
        key = all_groups_key()
        assert _KEY_RE.match(key), f"Key '{key}' does not match convention"
        assert key.startswith("lookup:v1:")
        assert ":all_groups" in key

    def test_all_groups_key_no_uppercase(self):
        key = all_groups_key()
        assert re.search(r"[A-Z]", key) is None, (
            f"Key '{key}' contains uppercase letters"
        )

    def test_active_items_key_format(self):
        key = active_items_key("listing_purpose")
        assert _KEY_RE.match(key), f"Key '{key}' does not match convention"
        assert ":items:listing_purpose" in key

    def test_active_items_key_no_special_chars_in_group_code(self):
        """group_code must not inject wildcard/special characters into the key."""
        key = active_items_key("listing_purpose")
        assert "*" not in key

    def test_all_groups_key_starts_with_lookup_namespace(self):
        key = all_groups_key()
        assert key.startswith(f"{LookupCacheKey.V1}:")

    def test_active_items_key_starts_with_lookup_namespace(self):
        key = active_items_key("listing_purpose")
        assert key.startswith(f"{LookupCacheKey.V1}:")


class TestLookupResolveCacheKeyConvention:
    """Resolved-lookup cache keys follow the versioned convention."""

    pytestmark = pytest.mark.unit

    def test_resolved_lookup_key_format(self):
        key = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 42)
        assert _KEY_RE.match(key), f"Key '{key}' does not match convention"
        assert ":purposes:42" in key

    def test_resolved_lookup_key_all_segments(self):
        for segment in (
            RESOLVED_PURPOSES_SEGMENT,
            RESOLVED_FEATURES_SEGMENT,
            RESOLVED_CONDITIONS_SEGMENT,
        ):
            key = resolved_lookup_key(segment, 1)
            assert _KEY_RE.match(key), f"Key '{key}' does not match convention"
            assert segment in key

    def test_resolved_lookup_key_no_uppercase(self):
        key = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 1)
        assert re.search(r"[A-Z]", key) is None

    def test_resolved_lookup_key_version_segment_present(self):
        key = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 1)
        # Format: lookup:v1:resolve:<version>:purposes:1
        parts = key.split(":")
        # lookup, v1, resolve, version, purposes, 1
        assert len(parts) >= 6
        assert parts[0] == "lookup"
        assert parts[1] == "v1"
        assert parts[2] == "resolve"
        assert parts[3].isdigit()  # version is numeric


class TestKeysChangeOnVersionBump:
    """Cache keys change when the content version is bumped."""

    pytestmark = pytest.mark.unit

    def test_all_groups_key_changes_after_bump(self):
        key_before = all_groups_key()
        bump_lookup_version()
        key_after = all_groups_key()
        assert key_after != key_before
        assert "lookup:v1:1:" in key_after

    def test_active_items_key_changes_after_bump(self):
        key_before = active_items_key("listing_purpose")
        bump_lookup_version()
        key_after = active_items_key("listing_purpose")
        assert key_after != key_before

    def test_resolved_lookup_key_changes_after_bump(self):
        key_before = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 1)
        bump_lookup_resolve_version()
        key_after = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 1)
        assert key_after != key_before
        assert "resolve:1:" in key_after

    def test_lookup_version_key_exists(self):
        """Version is stored in the cache under the expected key."""
        bump_lookup_version()
        assert get_lookup_version() == 1

    def test_resolve_version_key_exists(self):
        """Resolve version is stored in the cache under the expected key."""
        bump_lookup_resolve_version()
        assert get_lookup_resolve_version() == 1
