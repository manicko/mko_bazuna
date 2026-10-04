"""
Durability guard for cache-version keys (08-SRCH-007).

A cache-version key is a correctness mechanism, not a cache entry: it is
embedded in every key it retires, so it must **outlive** those entries. The
contract is "written with ``timeout=None``" and it lives in
:func:`apps.core.utils.cache.bump_version_key`. Redis is assumed to run
``noeviction`` (no ``maxmemory`` / ``maxmemory-policy`` in any compose file),
so a TTL-less key is retained.

Two guards keep the invariant honest:

1. **Static (grep-shaped)** — no module in ``src/backend`` may write a
   version key through ``cache.set`` with anything other than ``timeout=None``.
   This is the tripwire that a future writer cannot silently reintroduce a TTL
   (which makes the counter self-evict, re-issue ``1``, and resurrect a stale
   entry under a byte-identical key).
2. **Behavioural** — a key written through ``bump_version_key`` carries no
   expiry, and survives the window that would evict a ``DEFAULT_TIMEOUT`` key.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.core.cache import cache

from apps.core.utils.cache import bump_version_key

# A version key is any cache-key expression whose source mentions "version".
# Writers name them as ``*_VERSION_KEY`` constants or string literals.
_VERSION_HINT = "version"

# The four writer modules that own a version counter. Kept explicit so a fifth
# writer added elsewhere is still caught by the repo-wide scan below.
_WRITER_MODULES = (
    "apps/search/services/cache.py",
    "apps/categories/cache.py",
    "apps/categories/services/lookup_resolution.py",
    "apps/lookups/services/cache_service.py",
)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _is_version_key(node: ast.expr) -> bool:
    """Return True when a ``cache.set`` first argument names a version key."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _VERSION_HINT in node.value.lower()
    return _VERSION_HINT in ast.unparse(node).lower()


def _set_calls(tree: ast.AST) -> list[ast.Call]:
    """Collect every ``something.set(...)`` / bare ``set(...)`` call."""
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "set":
            calls.append(node)
        elif isinstance(func, ast.Name) and func.id == "set":
            calls.append(node)
    return calls


def _timeout_is_none(call: ast.Call) -> bool:
    """Return True when the call passes ``timeout=None`` explicitly."""
    for keyword in call.keywords:
        if keyword.arg == "timeout":
            return isinstance(keyword.value, ast.Constant) and keyword.value.value is None
    return False


def _iter_backend_sources() -> list[Path]:
    """Yield every non-test Python module under ``src/backend``."""
    return [
        path
        for path in _BACKEND_ROOT.rglob("*.py")
        if "tests" not in path.parts and "migrations" not in path.parts
    ]


class TestNoVersionKeyWrittenWithTimeout:
    """No version-key write in the tree may carry a bounded TTL (08-SRCH-007)."""

    pytestmark = pytest.mark.unit

    @pytest.mark.parametrize("module", _WRITER_MODULES)
    def test_writer_module_uses_no_timeout_for_version_set(self, module: str) -> None:
        """Each writer module's version-key ``cache.set`` uses ``timeout=None``."""
        source = (_BACKEND_ROOT / module).read_text(encoding="utf-8")
        tree = ast.parse(source)

        offending: list[str] = []
        for call in _set_calls(tree):
            if not call.args:
                continue
            if not _is_version_key(call.args[0]):
                continue
            if not _timeout_is_none(call):
                offending.append(ast.unparse(call))

        assert not offending, (
            f"{module} writes a version key with a bounded/absent timeout: "
            f"{offending}. A version key must be durable — route it through "
            f"apps.core.utils.cache.bump_version_key (timeout=None)."
        )

    def test_repo_wide_no_version_key_set_with_timeout(self) -> None:
        """A repo-wide scan finds no version-key ``cache.set`` carrying a TTL.

        This is the grep-shaped guard: it fails if any future writer writes a
        version key with ``timeout`` other than ``None`` (or omits it, which
        inherits ``DEFAULT_TIMEOUT``).
        """
        offending: list[str] = []
        for path in _iter_backend_sources():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - unreachable in-tree
                continue
            for call in _set_calls(tree):
                if not call.args:
                    continue
                if not _is_version_key(call.args[0]):
                    continue
                if not _timeout_is_none(call):
                    offending.append(f"{path.relative_to(_BACKEND_ROOT)}: {ast.unparse(call)}")

        assert not offending, (
            "Version keys must never be written with a TTL:\n" + "\n".join(offending)
        )


class TestVersionKeyIsDurable:
    """A version key written through the helper never expires (08-SRCH-007)."""

    pytestmark = pytest.mark.unit

    def _expire_at(self, key: str) -> float | None:
        """Return the LocMemCache expiry for *key* (``None`` means never)."""
        return cache._expire_info.get(cache.make_key(key))

    def test_bump_version_key_has_no_expiry(self) -> None:
        """``bump_version_key`` seeds the counter with ``timeout=None``."""
        key = "test:durable_version"
        value = bump_version_key(key)
        assert value == 1
        assert cache.get(key) == 1
        assert self._expire_at(key) is None, (
            "A version key must never expire: a bounded TTL lets the counter "
            "self-evict and resurrect a stale entry under a byte-identical key."
        )

    def test_bump_version_key_increments_without_expiry(self) -> None:
        """A repeat bump stays durable across the ``DEFAULT_TIMEOUT`` window."""
        key = "test:durable_version_increment"
        assert bump_version_key(key) == 1
        assert bump_version_key(key) == 2
        assert self._expire_at(key) is None

    def test_legacy_expired_key_reseeds_durably(self) -> None:
        """A missing key (legacy evictable counter) is reseeded with no expiry.

        Simulates the legacy failure: seed a bounded key, drop it, then bump —
        the reseed must be durable rather than repeating the defect.
        """
        key = "test:legacy_version"
        cache.set(key, 7, timeout=1)
        cache.delete(key)

        assert bump_version_key(key) == 1
        assert self._expire_at(key) is None
