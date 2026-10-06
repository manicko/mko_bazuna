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

### Finding-id citations

- **Format:** A finding id is cited as `NN-<PREFIX>-00N` — a two-digit phase, a hyphen, the finding prefix, a hyphen, then the finding number (e.g. `03-DB-004`).
- **Always phase-scoped:** A citation **must** carry its phase prefix. A bare `DB-004` is ambiguous because ids are reissued every cycle and the audit records that resolved the old ones are deleted.
- **Self-contained comments:** A comment that defends a past fix should be self-contained — describe the invariant it protects, or name the guarding symbol or test — so it is useful without an id lookup.
- **Cross-phase references:** Where a cross-phase reference is genuinely needed, name the phase in words (for example, "the phase-06 predicate").
- **English only:** Citation text and its surrounding comment are written in English.

### Testing Conventions

- **Framework:** pytest-django. Test classes are plain `class TestX:` — do NOT use `django.test.TestCase` or `unittest.TestCase`.
- **Markers:** Pytest-django + pytest-asyncio. Custom markers are registered in `pyproject.toml` under `[tool.pytest.ini_options].markers`. Use `pytestmark` at module level. The fast gate (`make test`) excludes **only** the `seed` marker (`-m "not (seed)"` via `PYTEST_SKIP_MARKERS=seed`); all other markers run in both the fast gate and the full suite (`make test-all` — the `slow` marker is **not** excluded by the fast gate).

  | Marker | Scope / purpose |
  |---|---|
  | `unit` | Pure unit tests, no database — runs in the fast gate |
  | `integration` | Tests that exercise the DB / Django `Client` stack |
  | `seed` | Separate-workflow only (`ci-seed.yml`, once per push); invokes `call_command('seed')` or `ImageGenerator`. Excluded from `make test`, included in `make test-all` |
  | `settings` | Import-time settings validation in a subprocess (e.g. `config/settings/tests/test_settings_secrets.py`) |
  | `concurrent` | Requires `transaction=True` (TRUNCATE per test) — bot tests mutating shared DB state |
  | `slow` | Individually slow tests (>5 s); **not** excluded by the fast gate |
  | `real_images` | Opts out of the no-op `ImageGenerator` stub in `apps/seed/tests/conftest.py` to use the real pipeline |
  | `xdist_group("name")` | Pins tests to a single xdist worker via `--dist loadgroup` (e.g. `"bot_concurrent"`) |
  | `django_db` (pytest-django) | DB-backed tests; use `transaction=True` when a test needs TRUNCATE isolation (bot tests) |
  | `asyncio` (pytest-asyncio, strict mode) | Async Telegram bot handlers |

  The `e2e` marker was removed — do not reference it.
- **Fixtures:** Root `conftest.py` at `src/backend/conftest.py` provides canonical `seller`, `user`, `category`, `city` fixtures. Do NOT redefine these locally — import or use directly. Bot tests under `src/telegram_bot/` have a separate conftest and cannot resolve backend fixtures. All canonical fixtures (and their bot-test counterparts) use `get_or_create` keyed on fixed IDs so they are **idempotent** and survive `--reuse-db` (stale rows from an interrupted run do not cause `IntegrityError`).
- **Ad creation:** Use `from conftest import create_test_ad(user, category, city, *, title, description, status, price, source, **kwargs)` — it sets status-specific timestamps automatically. **Always pass `status=` explicitly**; every call site does, and `apps/core/tests/test_ad_factory_contract.py` fails the suite on a call that is not status-grounded (a literal `status=`, or an enclosing helper that declares a `status` parameter or splats a dict containing `"status"`). The default is `AdStatus.PUBLISHED`, **not** `ON_MODERATION`: `auto_moderate` resolves `ON_MODERATION` in the same transaction (pass → `PUBLISHED`, fail → `ON_MODERATION_FAILED`, raise → rollback), so a row only ever rests in it transiently and a default of `ON_MODERATION` fabricates a state production cannot durably hold. A moderation-queue test therefore supplies its own status — `ON_MODERATION` for an approve/reject *input*, `ON_MODERATION_FAILED` for a durably reachable queue entry.
- **Backdating `created_at`:** `create_test_ad` cannot backdate `created_at` (auto_now_add=True). Use: `ad = create_test_ad(...)` then `Ad.objects.filter(pk=ad.pk).update(created_at=...)` then `ad.refresh_from_db()`.
- **Assertions:** Use plain `assert` statements — do NOT use `self.assertEqual`, `self.assertTrue`, etc.
- **Local `uv run pytest` runs require `--create-db`** (no `--reuse-db` — stale-schema errors, ~527 on reuse). When using the Docker entrypoint via `make test`/`make test-all`, the entrypoint defaults to `--reuse-db` (safe: the test PG container persists via a named volume); use `make test-recreate` (`--create-db`) to force a fresh schema. CI may use `--reuse-db` (ephemeral service DB). Root conftest at `src/backend/conftest.py` provides canonical fixtures and `create_test_ad`.

### i18n / Language Testing

The test environment uses English as the default language
(`LANGUAGE_CODE = "en"` in `config/settings/test.py`), matching the msgid
source language. This means tests asserting on English UI strings (e.g.
`"Clear all filters"`, `"Page navigation"`) pass without explicit language
setup.

**Integration tests (using Django `Client`):**

- Set the language via the middleware's documented priority order:
  `?lang=X` query parameter or `Accept-Language` HTTP header.
- **Never** call `translation.activate()` before `client.get()` — the
  `LanguagePreMiddleware` overrides it during request processing, making
  the pre-activation a no-op for rendered content. Use `?lang=ru` or
  `Accept-Language: ru` to get Russian output.
- For URLs with no other query params, `?lang=ru` is convenient. Where the
  URL carries meaningful query params, prefer `Accept-Language` header to
  avoid polluting the URL under test.

**Unit tests (no middleware, direct function calls):**

- Use the `translation.override(lang)` context manager for any
  locale-specific rendering. It provides automatic rollback (even on
  exceptions) and restores the *previous* language on exit.

**Thread-local cleanup:**

- An autouse `translation.deactivate()` fixture in `src/backend/conftest.py`
  eliminates all thread-local translation state leakage between tests. Do
  **not** add per-file `deactivate()` calls — they are now redundant.

**Parametrized multi-language tests:**

- Use `LanguageLocale.values()` (the StrEnum), not bare string literals,
  per project rule #10.

### Inline-JS i18n (Q6=A Pattern)

**Problem:** The completeness gate's `test_no_hardcoded_visible_text` strips
`<script>` blocks (via `_SKIP_TAGS` in
`apps/ads/tests/test_i18n_completeness.py:94`, which includes `"script"`), so any
user-visible text inside inline `<script>` tags is invisible to the gate. Hardcoded
string literals in inline JS are a testing gap — they will never be flagged by
`test_no_hardcoded_visible_text`, `test_extraction_completeness`, or
`test_no_empty_msgstr`, and they will never reach the `.po` extraction pipeline
(`make makemessages` does not scan template `<script>` contents).

**Prescribed solution:** The **catalog_js_labels** pattern. Wrap every user-visible
string in `gettext` (`_()`) at the Python layer — inside a context processor — then
JSON-encode the dict and inject it into the template context. Inline JS parses the
injected JSON and reads `labels.<key>` instead of using string literals. Because the
`_(...)` calls live in Python (not inside a `<script>` block), `make makemessages`
extracts them and the msgids flow through the full completeness gate.

**Implementation reference:** `apps/core/context_processors.py` → `header_context`,
lines 100–108:

```python
"catalog_js_labels": json.dumps(
    {
        "show_all_results": _("Show all results"),
        "cities": _("Cities"),
        "categories": _("Categories"),
        "popular_queries": _("Popular queries"),
        "history": _("History"),
    }
),
```

The template consumes it (example from `templates/components/header_catalog.html:235`):

```django
<script>
    var labels = JSON.parse('{{ catalog_js_labels|escapejs }}');
    // Use labels.show_all_results, labels.cities, etc. — never raw string literals.
</script>
```

Guidelines:

- Use `|escapejs` on the template variable to safely embed the JSON string inside a
  JS string literal (prevents `</script>` injection and quote breakage).
- Every label key is a stable snake_case identifier, not a sentence; the translatable
  text is the `_()` argument in Python, keeping msgids English per rule #10.
- **Do NOT** add new inline `<script>` string literals containing user-visible text
  (Cyrillic or otherwise). They bypass the gate entirely. If JS needs a translated
  string, add it to the `catalog_js_labels` dict — or a new context-processor dict —
  and reference it via the injected `labels` object.

## Test Infrastructure

### Test database lifecycle

- **Test DB:** PostgreSQL 18 in Docker (`mko-bazuna-test` project, host port 5433).
- **`--reuse-db`:** The Docker entrypoint (`docker/entrypoint-test.sh`) defaults to `--reuse-db`, caching the `test_mko_bazuna` schema between runs (~1.5 s saved per run). CI may also use `--reuse-db` since the service DB is ephemeral.
- **`test-clean-db`:** Pre-flight target that drops stale `test_mko_bazuna*` and `gw*` databases (from crashed xdist workers) before `test-recreate`. Run automatically as the first step of `make test-recreate`.
- **`test-recreate`:** Drops and rebuilds the test DB schema (`--create-db`). Use after migration changes or interrupted runs.
- **Local `uv run pytest`** always requires `--create-db` (no `--reuse-db`) — the test DB on `localhost:5432` is not reachable; tests must run in Docker.

### Parallel execution

- **`--dist loadgroup`** with `xdist_group("name")` pins tests that mutate shared DB state (e.g. bot tests with `transaction=True`) to the same worker.
- `-n auto` auto-detects CPU cores; bot tests use `transaction=True` (TRUNCATE isolation) for correctness.

## CI Workflow

The CI pipeline (`.github/workflows/ci.yml`, `name: CI`) runs on `ubuntu-latest` for pushes to `main`/`develop`:

| Job | Purpose | Key steps |
|---|---|---|
| `build` | Docker image + test env | Checkout → Buildx → Build image → Trivy scan → Upload SARIF |
| `test` | Unit + integration tests | DB service → `bootstrap_reference_data` → `compilemessages` → pytest with coverage |
| `lint` | Code linting | `uv sync` → `ruff check src/` (from the repository root) |
| `typecheck` | Type checking | `uv sync` → `basedpyright src/` (from the repository root) |
| `lint-templates` | Template linting | `uv sync` → `djlint templates/` |
| `i18n` | i18n completeness gate | `uv sync` → `compilemessages` → `pytest test_i18n_completeness.py test_i18n_pipeline.py -v` |
| `security` | Vuln + secret scanning | `pip-audit` → Trivy (fs) → gitleaks → SARIF upload. Commit-time prevention is also enforced via a pre-commit hook: `.pre-commit-config.yaml` registers a `gitleaks protect --verbose` hook at the `commit` stage that scans staged changes against `.gitleaks.toml` and rejects the commit if any secret is detected — complementing the post-commit CI scan so leaks never enter history. |
| `deploy-check` | Production deploy gate | `check --deploy --fail-level WARNING` against `config.settings.prod` with all required env vars (blocking) |

- The `test` job in CI runs `compilemessages` **before** pytest to ensure `.mo` files are present (T-01).
- Coverage report is uploaded as an artifact (`src/backend/coverage.xml`, 30-day retention).
- The `lint` and `typecheck` jobs run from the **repository root** over `src/`, so both process trees
  (`src/backend` and `src/telegram_bot`) are in scope — the same scope as `make lint` /
  `make typecheck`. The gate is `src/`, **not** `.`: `ruff check .` from the root also walks
  `.ai/**`, which `[tool.ruff] exclude` does not cover.
- CI uses SQLite-backed PostgreSQL service (not Docker Compose) — migrations run via `migrate_locked.py`.
- A dedicated, **blocking** `deploy-check` job runs `manage.py check --deploy --fail-level WARNING` against `config.settings.prod` (not the test settings) with all required production env vars set to valid non-secret placeholders (`DJANGO_SETTINGS_MODULE`, `DJANGO_SECRET_KEY` 50+ chars, `BOT_TOKEN`, `BOT_USERNAME` matching `^[A-Za-z0-9_]{3,32}$`, `GOOGLE_TRANSLATE_API_KEY`, `SITE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `EMAIL_HOST`, `REDIS_URL=redis://localhost:6379/0`, `DATABASE_URL`). `--fail-level WARNING` means any W-series finding fails the build; there is no `continue-on-error`. This replaced the previous `test`-job step that ran against `config.settings.test` and produced 6 false-positive warnings. The `web`/`bot` entrypoints also call `check --deploy` at boot (non-fatal, logs a `WARNING` and continues).
- The `deploy-check` `env:` block is a **contract**, not just fixtures. `config/settings/tests/test_deploy_check_env_parity.py` parses it out of `ci.yml` and imports `config.settings.prod` with exactly that set, so a new production guard fails the test suite until the key is added here in the same change. Never add `DJANGO_BUILD` or `DJANGO_ONESHOT` to that block — either one suppresses the guards and makes the gate pass while checking nothing.

## i18n Pipeline

### Workflow

1. **Tag strings** in templates (`{% trans %}` / `{% blocktrans %}`) and Python (`gettext` / `gettext_lazy`)
2. **`make makemessages`** (`Makefile:167`) — extracts strings into `.po` files for `ru`, `bs`, `en` via `manage.py makemessages -l ru -l bs -l en --no-location`
3. **Edit `.po` files** — fill `msgstr` for `ru` and `bs` (non-empty); `en` may be empty (msgid is English)
4. **`make compilemessages`** (`Makefile:170`) — compiles `.po` → `.mo` with ignore patterns: `--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc'`
5. **Runtime:** the web `LanguagePreMiddleware` activates the locale per request; the bot `LanguageMiddleware` (`telegram_bot/middlewares/language.py`, FQ-001) activates per-user locale (`User.telegram_language`) around bot handler dispatch, before `AccountStateMiddleware`. In both, gettext reads `.mo` catalogs under `LOCALE_PATHS` (`src/backend/locale/`)

### Completeness gate

`apps/ads/tests/test_i18n_completeness.py` (marked `@pytest.mark.unit`) enforces the multilingual Definition of Done. The gate was widened (BLOCK 8 / 14-I18N-006, -007, -008) so its collectors are **derived, never listed**:
- The bot collector (`_collect_bot_source_files`) walks **all of `src/telegram_bot`, excluding only `tests/`** (`rglob("*.py")`). `_collect_bot_handler_files` is retained and delegates to it, narrowing to the `handlers` package. The widened set therefore reaches the `middlewares/` package (including the locale-activating `language.py`), `retry.py`, `states.py`, `main.py`, the `schemas/` package and the nine-module `handlers/ad_create/` package.
- The template collector (`_collect_template_files`) discovers roots via `_template_roots()`: **root-scoping** — the configured `TEMPLATES["DIRS"]` unioned with each *in-repo* installed app's `<path>/templates` (an app root is admitted only when it resolves inside `settings.BASE_DIR`, so third-party `.venv` distributions are excluded). `exclude_subpaths` is applied relative to each root. The gate asserts at least one root and a non-empty in-scope set.
- **Named exemption sets — one definition each, never a second divergent list:**
  - `_BOT_EXEMPT_FUNCTIONS` (BLOCK 8, 14-I18N-006) — read by the bot predicate callers and the template scanners. Its first member is `("telegram_bot/services/ad_data/keyboards.py", "build_currency_keyboard")`: the currency button label is an emoji flag plus a `CurrencyCode` value (`f"{_CURRENCY_FLAGS[code]} {code.value}"`), which carries no prose to translate. It is consulted by **enclosing-function name**, never by line number, and `_find_untranslated` is never weakened.
  - `_BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS` (BLOCK 9, N-1) — the three `bs` `msgstr`s knowingly shipped untranslated while the Q1 ruling is `OPEN-PENDING-REVIEWER` (2026-10-05, option b; required reviewer: a native Bosnian speaker, preferably Montenegrin; owner: Product Owner). Consulted **by msgid** from `test_bs_msgstr_has_no_cyrillic`. The finding is **not closed** for these entries; a follow-up commit replaces the values and removes them from the set once a reviewer signs off.
  - `_EXTRACTION_GAP_MSGIDS` (BLOCK 11, 14-I18N-014) — the three runtime-live `_lazy` strings (in `submit.py::_NON_CONTENT_REPLIES`) that `xgettext` does not extract because it does not scan `_lazy` as a keyword. Consulted **by msgid** from `test_reverse_stale_entry_gate`. The comment names the xgettext `_lazy` keyword gap (commit `d0a3ac2a`) and the owner.
- **Not flagged, no exemption (BLOCK 8, D-C):** `telegram_bot/lifecycle.py`'s `_COMMANDS` holds `BotCommand(command=…, description=…)` literals that are deliberately not msgids (an eager `_()` would freeze them to the import-time locale). The bot predicate matches `ast.Attribute` methods (`.answer`/`.button`/…), so a bare `BotCommand(...)` constructor is never flagged.
- `test_hreflang_present` renders the partial in isolation; an additive sibling assertion (`test_hreflang_include_in_every_page_template`) additionally asserts **source-level** that every in-scope non-partial page template contains the `components/locale_head.html` include. A template is a partial when its path has a `partials/` segment or starts with `components/` (so the partial itself is excluded). The two templates that are both excluded *and* include the partial (`admin/moderation/review.html`, `analytics/moderation_dashboard.html`) reconcile rather than fail.

| Guard | Scope |
|---|---|
| `test_no_hardcoded_visible_text` | Public/seller-facing templates for visible text not wrapped in `{% trans %}` |
| `test_extraction_completeness` | Every `{% trans %}` / `{{ _("…") }}` msgid exists in all 3 `.po` files |
| `test_no_empty_msgstr` | `ru` and `bs` have no empty `msgstr` for non-header entries |
| `test_no_raw_get_name_in_templates` | No raw `{{ obj.get_name }}` — must use locale-aware filters |
| `test_mo_compiled` | `.mo` files exist for all 3 locales |
| `test_template_extraction_coverage` | Msgids extracted from `{% trans %}` / `{{ _("…") }}` / `{% blocktrans %}` each exist in all 3 `.po` files |
| `test_hreflang_present` | Every page template renders `<link rel="alternate" hreflang>` (I18N-004) |
| `test_hreflang_include_in_every_page_template` | Every in-scope non-partial page template includes `components/locale_head.html` (source-level, BLOCK 8) |
| `test_plural_forms` | Each `.po` `Plural-Forms` header matches CLDR rules |
| `test_locale_switch_re_render` | `?lang=bs` content re-renders in the Bosnian locale |
| `test_bot_no_hardcoded_messages` | AST-scans every `src/telegram_bot` module except `tests/` for user-facing Bot/API method calls whose text argument is a bare literal/f-string rather than a `_()` call |
| `test_bot_no_raw_model_field_access` | AST-scans the same widened bot scope for `name_i18n.get("<literal>")` and raw `.name`/`.title`/`.description` access |
| `test_no_cyrillic_msgids` | No `msgid` in any `.po` file contains Cyrillic characters; msgids must be English (inspects `msgid` only — see the `bs`-scoped sibling below) |
| `test_bs_msgstr_has_no_cyrillic` | (BLOCK 9, N-1) Locale-scoped sibling of `test_no_cyrillic_msgids`: a Cyrillic code point in a **`bs` `msgstr`** is a violation (every `msgstr` form inspected), while `ru`'s legitimate Cyrillic stays exempt. The three exempt msgids are read from `_BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS` |
| `test_reverse_stale_entry_gate` | (BLOCK 11, 14-I18N-014) Reverse of `test_extraction_completeness`: every catalogue msgid must exist in a real in-process source extraction (Python `ast` + full-root template scan). No regex — a wrapped multi-line msgid is compared as its joined string. The three `_lazy` gaps are read from `_EXTRACTION_GAP_MSGIDS` |
| `test_no_obsolete_entries_in_any_catalogue` | (BLOCK 11, 14-I18N-014, `test_i18n_pipeline.py`) Zero `#~` obsolete blocks in **every** catalogue (post-prune target is zero; `7/7/1` justified the block but is not the invariant asserted) |

A dedicated `i18n` CI job runs `compilemessages` + these tests on every push.

### Key facts
- `.mo` files are **not** in version control (`.gitignore` line 55) — build-time artifacts
- DB-based i18n (`components/feature_tag.html` via `get_lookup_name`) is exempt from the completeness gate
- Scan scope excludes `admin/` staff templates, `analytics/moderation_dashboard.html`, and `components/feature_tag.html`; the excluded set is kept in sync with the `exclude_subpaths` definition in `test_i18n_completeness.py`, and every deliberate non-translation is a named exemption set in one module (`_BOT_EXEMPT_FUNCTIONS`, `_BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS`, `_EXTRACTION_GAP_MSGIDS`) — never a silent omission, never a `pytest.skip`
- **Model metadata is an explicit exemption (14-I18N-013 Option A):** `verbose_name` / `help_text` on Django model fields are not scanned and are deliberately not wrapped in `gettext_lazy`. The exemption is unconditional, adds no catalogue entry, and leaves the admin tests asserting English field text unchanged. It sits alongside the three template exclusions above and, like them, is not a silent omission.

## Performance Discipline

### Caching Rules

- **Invalidate on write:** Every model `.save()` / `.delete()` that affects a cached result must invalidate the corresponding cache key. Search results are cached by `apps/search/services/cache.py` and invalidated by `apps/search/signals.py` on `Ad` publish.
- **Single-flight on thundering herd:** Use `apps/core/utils/swr_cache.py` (`get_with_stale_revalidate`) for any cache path that recomputes an expensive result. Concurrent identical requests share a single recompute — subsequent callers receive the stale fallback while the fresh value is computed once. Pattern-based invalidation uses `invalidate_by_prefix` (Redis-only; no-op under LocMemCache — see [cache-strategy](../architecture/cache-strategy.md)).
- **Cache hit-rate tracking:** SLO #6 requires >85% Redis cache hit rate. If hit rate drops below 85% in production metrics, investigate invalidation churn or key cardinality before adding capacity.
- **Pattern-based invalidation:** `cache.delete_pattern()` is Redis-only. Under LocMemCache (dev/test) it is a no-op — do not rely on it in unit tests that assert cache state.

### Profiling Rules

- **Profile before optimizing:** Never optimize a hot path without first confirming it in a cProfile run (`scripts/profile_search.py`) or `EXPLAIN (ANALYZE, BUFFERS)` output (`python -m manage.py profile_queries`).
- **Assert no sequential scans at scale:** The `profile_queries` command asserts no `Seq Scan` on `ads_ad` at seed scale (>10k rows). If it fails, add an index before tuning the query.
- **Regression threshold:** If the Locust load test shows p95 regression >10% against SLO constants (`PerformanceSLO.P95_SLO_MS`, `PerformanceSLO.P99_SLO_MS` from `src/benchmark/constants.py`), halt feature work and profile. See [`docs/ops/profiling.md`](../ops/profiling.md).