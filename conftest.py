"""Root test configuration for the Mko Bazuna project.

Centralizes shared ``pytest_plugins`` registration so both the backend
(``src/backend``) and bot (``src/telegram_bot``) test trees discover shared
fixtures (e.g. ``permissive_criteria``, ``banning_criteria``) regardless of
which ``testpaths`` are collected.

Previously ``pytest_plugins`` was declared only in ``src/backend/conftest.py``,
which meant bot tests collected in isolation (``pytest src/telegram_bot``) could
not resolve plugin-provided fixtures.  Moving registration to the root conftest
— the pytest-recommended location for shared plugin declarations — makes the
plugin available to every collection path.
"""

pytest_plugins = ("testing.moderation_fixtures",)

# ---------------------------------------------------------------------------
# Backward-compatible re-export of test helpers
#
# Test modules across the codebase do ``from conftest import create_test_ad``,
# which previously resolved to ``src/backend/conftest.py`` via the ``pythonpath``
# entry in ``pyproject.toml``.  With this root conftest present, ``conftest``
# now resolves to *this* file, shadowing the backend conftest.  This
# ``__getattr__`` defers the backend-conftest import to call-time (Django is
# fully set up by pytest-django before any test module is collected), so no
# Django models are imported at this module's load time — preserving the
# import-safety guarantee stated above.
# ---------------------------------------------------------------------------


def __getattr__(name: str):
    """Lazily re-export test helpers from the backend conftest.

    Only ``create_test_ad`` and ``create_test_ads_bulk`` are re-exported —
    the functions test modules import via ``from conftest import ...``.
    """
    if name in ("create_test_ad", "create_test_ads_bulk"):
        import backend.conftest as _backend_conftest

        _value = getattr(_backend_conftest, name)
        globals()[name] = _value  # cache for subsequent lookups
        return _value
    raise AttributeError(f"module 'conftest' has no attribute {name!r}")
