---
id: rules
domain: agent
tags:
  - rules
related:
  - architecture
  - references
---

## Purpose

This file contains coding standards and rules for the Mko Bazuna project.

## Rules

### Quality & Maintenance

- **Type safety:** Type hints on all public functions. Use strict typing throughout.
- **Logging:** `logger = logging.getLogger(__name__)` — never `print()`.
- **Error handling:** Custom exceptions from `core/errors.py`. Never silently swallow errors.
- **Cleanup:** Clean up temp files with `try/finally` — never leave orphaned cache files.
- **English only:** English only in code, comments, logs.
- **Production code is king:** If tests conflict with architecture/business logic, fix or remove tests; never distort production code for tests.
- **Audit reports:** Write audit reports incrementally — append blocks of ≤100 lines per tool call.

### Coding Standards

- **Indentation:** 4-space indentation, never tabs.
- **Code review:** Read full function/class before rewriting.
- **Linting:** After edits run `uv run ruff check <path>` and `uv run basedpyright <path>`.

### Testing Conventions

- **Framework:** pytest-django. Test classes are plain `class TestX:` — do NOT use `django.test.TestCase` or `unittest.TestCase`.
- **Markers:** Use `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` at module level for DB-backed tests. Use `pytest.mark.unit` for DB-free tests. The `e2e` marker was removed — do not reference it.
- **Fixtures:** Root `conftest.py` at `src/backend/conftest.py` provides canonical `seller`, `user`, `category`, `city` fixtures. Do NOT redefine these locally — import or use directly. Bot tests under `src/telegram_bot/` have a separate conftest and cannot resolve backend fixtures.
- **Ad creation:** Use `from conftest import create_test_ad(user, category, city, *, title, description, status, price, source, **kwargs)` — it sets status-specific timestamps automatically. Add `status=AdStatus.PUBLISHED` explicitly if the test requires it.
- **Backdating `created_at`:** `create_test_ad` cannot backdate `created_at` (auto_now_add=True). Use: `ad = create_test_ad(...)` then `Ad.objects.filter(pk=ad.pk).update(created_at=...)` then `ad.refresh_from_db()`.
- **Assertions:** Use plain `assert` statements — do NOT use `self.assertEqual`, `self.assertTrue`, etc.
- **Local `uv run pytest` runs require `--create-db`** (no `--reuse-db` — stale-schema errors, ~527 on reuse). When using the Docker entrypoint via `make test`/`make test-all`, the entrypoint defaults to `--reuse-db` (safe: the test PG container persists via a named volume); use `make test-recreate` (`--no-reuse-db --create-db`) to force a fresh schema. CI may use `--reuse-db` (ephemeral service DB). Root conftest at `src/backend/conftest.py` provides canonical fixtures and `create_test_ad`.