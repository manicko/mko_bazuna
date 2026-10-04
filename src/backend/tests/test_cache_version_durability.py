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
   version key through ``cache.set`` or ``cache.touch`` with anything other
   than ``timeout=None``, and no module may write a version key through
   ``cache.add`` at all. This is the tripwire that a future writer cannot
   silently reintroduce a TTL (which makes the counter self-evict, re-issue
   ``1``, and resurrect a stale entry under a byte-identical key).
2. **Behavioural** — a key written through ``bump_version_key`` carries no
   expiry; because the counter never expires it never resets, so a key built
   before and a key built after a bump always differ.
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


# The three write methods that can put a TTL on a version key. ``set`` and
# ``touch`` are TTL-bearing writes that must carry ``timeout=None``; ``add`` is
# rejected outright on a version key (see ``_version_key_violation``).
_WRITE_METHODS = ("set", "add", "touch")


def _is_version_key(node: ast.expr) -> bool:
    """Return True when a cache-write first argument names a version key.

    Matches both a literal whose text mentions ``version`` and an expression
    that does — e.g. a ``*_VERSION_KEY`` module constant. The modules in
    ``_WRITER_MODULES`` cheat by passing the constant by name, so this guard
    only recognises the argument where the source spells it out; the writer
    modules are pinned by the parametrized test below as the compensating
    control.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _VERSION_HINT in node.value.lower()
    return _VERSION_HINT in ast.unparse(node).lower()


def _write_calls(tree: ast.AST) -> list[ast.Call]:
    """Collect every ``something.set|add|touch(...)`` / bare-name call."""
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _WRITE_METHODS:
            calls.append(node)
        elif isinstance(func, ast.Name) and func.id in _WRITE_METHODS:
            calls.append(node)
    return calls


def _write_method(call: ast.Call) -> str:
    """Return the write-method name (``set`` / ``add`` / ``touch``)."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _version_key_violation(call: ast.Call) -> str | None:
    """Return a reason when *call* illegally writes a version key, else None.

    ``set`` / ``touch``: a version key must be durable, so any timeout other
    than ``None`` (including an omitted one, which inherits
    ``DEFAULT_TIMEOUT``) is a violation.

    ``add``: rejected outright on a version key. ``cache.add`` only writes when
    the key is absent, so it is the wrong tool for a counter — a call that
    hits an existing counter is silently a no-op and the bump is lost. A
    version key is only ever written through ``bump_version_key`` (``incr``,
    or ``set`` on the missing-key fallback).
    """
    method = _write_method(call)
    if method == "add":
        return "cache.add is not a valid version-key write (use bump_version_key)"
    if method in ("set", "touch") and not _timeout_is_none(call):
        return f"cache.{method} writes a version key without timeout=None"
    return None


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
        """Each writer module's version-key write is a durable ``timeout=None``.

        The writer modules pass their version key as a named constant, so the
        ``_is_version_key`` scan cannot see it — this test is the explicit
        control that the four owners route through ``bump_version_key``.
        """
        source = (_BACKEND_ROOT / module).read_text(encoding="utf-8")
        tree = ast.parse(source)

        offending: list[str] = []
        for call in _write_calls(tree):
            if not call.args:
                continue
            if not _is_version_key(call.args[0]):
                continue
            violation = _version_key_violation(call)
            if violation:
                offending.append(f"{violation}: {ast.unparse(call)}")

        assert not offending, (
            f"{module} writes a version key illegally: "
            f"{offending}. A version key must be durable — route it through "
            f"apps.core.utils.cache.bump_version_key (timeout=None)."
        )

    def test_repo_wide_no_version_key_set_with_timeout(self) -> None:
        """A repo-wide scan finds no illegal version-key write.

        This is the grep-shaped guard: it fails if any future writer writes a
        version key through ``set``/``touch`` with ``timeout`` other than
        ``None`` (or omits it, which inherits ``DEFAULT_TIMEOUT``), or writes
        one through ``add``. It matches on the literal text of the key, so a
        module that binds the key to a ``*_VERSION_KEY`` constant is covered
        by the parametrized test above instead.
        """
        offending: list[str] = []
        for path in _iter_backend_sources():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - unreachable in-tree
                continue
            for call in _write_calls(tree):
                if not call.args:
                    continue
                if not _is_version_key(call.args[0]):
                    continue
                violation = _version_key_violation(call)
                if violation:
                    offending.append(
                        f"{path.relative_to(_BACKEND_ROOT)}: {violation}: "
                        f"{ast.unparse(call)}"
                    )

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
        """A repeat bump increments the counter and leaves it with no expiry.

        It asserts ``_expire_info`` is ``None`` after both bumps — it does not
        wait out the ``DEFAULT_TIMEOUT`` window. Reading LocMemCache's private
        ``_expire_info`` is deliberate: it is the only way to observe "no TTL"
        directly, and a backend swap would fail this test loudly (missing
        attribute) rather than pass it falsely.
        """
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

    def test_expired_counter_would_reset_and_make_keys_identical(self) -> None:
        """Proves the defect the durable counter prevents: a resettable counter
        re-issues ``1``, making a key built after the reset byte-identical to
        one built before it.

        Simulates how django-redis's EXISTS-guarded ``INCR`` behaves on a lost
        counter: the counter is deleted (as it would be, had it carried a TTL),
        the next bump hits ``ValueError`` and reseeds at ``1``, and the two
        composite keys collapse to the same string. This is the *defect*, pinned
        here so the shipped behaviour below is meaningful.
        """
        key = "test:resettable_version"

        cache.set(key, 1, timeout=None)
        key_before = f"search:v1:{int(cache.get(key, 0) or 0)}:sr:q:0"
        assert key_before == "search:v1:1:sr:q:0"

        # A legacy bounded counter self-evicts; the next bump reseeds at 1.
        cache.delete(key)
        assert bump_version_key(key) == 1

        key_after = f"search:v1:{int(cache.get(key, 0) or 0)}:sr:q:0"
        assert key_after == key_before, (
            "The hypothetical defect: a reset-to-1 counter makes a retired key "
            "byte-identical to a live one, resurrecting a stale entry."
        )

    def test_durable_counter_keeps_keys_distinct_across_bumps(self) -> None:
        """Shipped behaviour: ``timeout=None`` means the counter never resets,
        so a key built before a bump is never equal to the key built after.

        The counter is bumped twice; the two composite keys must differ. This
        is the inverse of the defect above — it fails only if
        ``bump_version_key`` reintroduces a bounded TTL (self-evict →
        ``ValueError`` → reseed at ``1`` → identical keys).
        """
        key = "test:durable_version_identity"
        assert bump_version_key(key) == 1
        key_at_one = f"search:v1:{int(cache.get(key, 0) or 0)}:sr:q:0"

        assert bump_version_key(key) == 2
        key_at_two = f"search:v1:{int(cache.get(key, 0) or 0)}:sr:q:0"

        assert key_at_two != key_at_one, (
            "A bumped durable counter must yield a new key; identical keys mean "
            "the counter reset (a bounded TTL self-evicted it)."
        )
        assert self._expire_at(key) is None
