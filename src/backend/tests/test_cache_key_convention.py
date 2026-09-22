"""
Cross-cutting cache-key convention verification (13-PERF-006).

Verifies that lookup cache keys across ``LookupCacheService`` and
``CategoryLookupResolver`` follow the documented naming convention from
``docs/architecture/cache-strategy.md``::

    <namespace>:v<N>:<version>:<segments...>

Specifically:
  - ``all_groups_key()``           -> ``lookup:v1:{version}:all_groups``
  - ``active_items_key(code)``    -> ``lookup:v1:{version}:items:{code}``
  - ``resolved_lookup_key(seg, cat)`` -> ``lookup:v1:resolve:{version}:{seg}:{cat}``

All keys must:
  - Start with ``lookup:v1`` (namespace + static format version)
  - Include a numeric content-version segment
  - Change when the version is bumped (old entries become unreachable)
"""

from __future__ import annotations

import re
import time

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

# All lookup cache keys must match: lookup:v1:<version-segment-and-beyond>
_KEY_RE = re.compile(r"^lookup:v1:.+$")


class TestCacheKeyConvention:
    """Lookup cache keys follow the ``lookup:v1:{version}:...`` convention."""

    pytestmark = pytest.mark.unit

    # --- all_groups key ------------------------------------------------------

    def test_all_groups_key_follows_convention(self):
        """``all_groups_key()`` produces ``lookup:v1:{version}:all_groups``."""
        version = get_lookup_version()
        key = all_groups_key()
        assert _KEY_RE.match(key), f"Key '{key}' does not match convention"
        assert key == f"{LookupCacheKey.V1}:{version}:all_groups"

    def test_all_groups_key_no_uppercase(self):
        key = all_groups_key()
        assert re.search(r"[A-Z]", key) is None

    # --- active_items key ----------------------------------------------------

    def test_active_items_key_follows_convention(self):
        """``active_items_key()`` produces ``lookup:v1:{version}:items:{code}``."""
        version = get_lookup_version()
        key = active_items_key("listing_purpose")
        assert _KEY_RE.match(key), f"Key '{key}' does not match convention"
        assert key == f"{LookupCacheKey.V1}:{version}:items:listing_purpose"

    def test_active_items_key_no_wildcard_chars(self):
        """group_code must not inject wildcard characters into the key."""
        key = active_items_key("listing_purpose")
        assert "*" not in key
        assert "%" not in key

    # --- resolved-lookup key -------------------------------------------------

    def test_resolved_lookup_key_follows_convention(self):
        """``resolved_lookup_key()`` produces the versioned resolve key."""
        version = get_lookup_resolve_version()
        key = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 42)
        assert _KEY_RE.match(key), f"Key '{key}' does not match convention"
        assert key == (
            f"{LookupCacheKey.V1}:resolve:{version}"
            f":{RESOLVED_PURPOSES_SEGMENT}:42"
        )

    def test_resolved_lookup_key_all_segments(self):
        for segment in (
            RESOLVED_PURPOSES_SEGMENT,
            RESOLVED_FEATURES_SEGMENT,
            RESOLVED_CONDITIONS_SEGMENT,
        ):
            key = resolved_lookup_key(segment, 1)
            assert _KEY_RE.match(key)
            assert segment in key

    def test_resolved_lookup_key_version_is_numeric(self):
        """The version segment in resolved keys must be a numeric integer."""
        key = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 1)
        parts = key.split(":")
        # lookup, v1, resolve, <version>, purposes, 1
        assert parts[0] == "lookup"
        assert parts[1] == "v1"
        assert parts[2] == "resolve"
        assert parts[3].isdigit()

    # --- namespace consistency ----------------------------------------------

    def test_all_keys_share_lookup_v1_namespace(self):
        assert all_groups_key().startswith(f"{LookupCacheKey.V1}:")
        assert active_items_key("test").startswith(f"{LookupCacheKey.V1}:")
        assert resolved_lookup_key("purposes", 1).startswith(f"{LookupCacheKey.V1}:")

    # --- version-bump changes keys -------------------------------------------

    def test_groups_key_changes_on_bump(self):
        key_before = all_groups_key()
        bump_lookup_version()
        key_after = all_groups_key()
        assert key_after != key_before

    def test_items_key_changes_on_bump(self):
        key_before = active_items_key("listing_purpose")
        bump_lookup_version()
        key_after = active_items_key("listing_purpose")
        assert key_after != key_before

    def test_resolved_key_changes_on_bump(self):
        key_before = resolved_lookup_key(RESOLVED_FEATURES_SEGMENT, 1)
        bump_lookup_resolve_version()
        key_after = resolved_lookup_key(RESOLVED_FEATURES_SEGMENT, 1)
        assert key_after != key_before

    def test_old_key_unreachable_after_bump(self):
        """After bumping versions, old cache entries are unreachable under
        the new version key (they persist via TTL but the new key is a miss).
        """
        from django.core.cache import cache

        groups_before = all_groups_key()
        resolve_before = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 1)

        bump_lookup_version()
        bump_lookup_resolve_version()

        groups_after = all_groups_key()
        resolve_after = resolved_lookup_key(RESOLVED_PURPOSES_SEGMENT, 1)

        assert groups_after != groups_before
        assert resolve_after != resolve_before

        # Prime old keys - they should not be visible via new keys
        cache.set(
            groups_before,
            {"value": ["old"], "stored_at": time.time()},
            timeout=300,
        )
        assert cache.get(groups_before) is not None  # old data persists
        assert cache.get(groups_after) is None       # new key is a miss
        assert cache.get(resolve_after) is None      # new resolve key is a miss
