---
id: code-quality-fixes
domain: plan
status: "8 findings (QLT-001–007) + 1 prerequisite (FQ-001) · 5 execution blocks · A: COMMITTED at HEAD 7ec80c7 (G004/I001 fix in de0df4f) · B–E: IMPLEMENTED-UNCOMMITTED in working tree (fast gate 1576 passed) · QLT-007: NOT VERIFIED (basedpyright not run) · 2 residual fixes before atomic commit (QLT-007 typecheck + QLT-002 contact.py sentinel consolidation)"
source: .ai/audit/99-validation/10-code-quality-validated-findings.md
code_context: .ai/audit/99-validation/10-code-context.md
task_template: .ai/tasks/templates/task_template.yaml
order_template: .ai/tasks/templates/order_template.yaml
tags:
  - code-quality
  - bot-refactor
  - i18n
  - ruff
  - pydantic
  - service-extraction
  - telegram-bot
  - web-views
related:
  - .ai/audit/99-validation/10-code-quality-validated-findings.md
  - .ai/audit/99-validation/10-code-context.md
  - src/telegram_bot/handlers/ad_create.py
  - src/telegram_bot/handlers/alerts.py
  - src/telegram_bot/handlers/contact.py
  - src/telegram_bot/handlers/login.py
  - src/telegram_bot/main.py
  - src/telegram_bot/tests/conftest.py
  - src/telegram_bot/services/rate_limit.py
  - src/backend/apps/ads/views/edit.py
  - src/backend/apps/ads/views/listings.py
  - src/backend/apps/ads/services/submission.py
  - src/backend/apps/search/views/search.py
  - src/backend/apps/search/services/alert_query.py
  - src/backend/apps/ads/tests/test_i18n_completeness.py
  - src/backend/apps/ads/migrations/0005_remove_ad_ix_ads_delete_sweep_ad_ix_ads_delete_sweep.py
  - src/backend/apps/ads/migrations/0006_ad_ix_ads_draft_sweep.py
  - pyproject.toml
---

# Execution Plan 22 — Code Quality Fixes (QLT-001–QLT-007 + FQ-001)

> **Source (validated):** `.ai/audit/99-validation/10-code-quality-validated-findings.md`
> **Code context (live):** `.ai/audit/99-validation/10-code-context.md`
> **Validated on:** 2026-09-12
>
> QLT-001 Stage 1 (submit_ad extraction) is already DONE — 15 inline `sync_to_async`
> ORM helpers remain in `ad_create.py` and form the core of Block C.

---

## 0. Resolution Status & Scope

All 8 findings are **VALIDATED** and currently applicable against the live codebase.

| Finding | Severity | Priority | Status | Block |
|---|---|---|---|---|
| QLT-001 | HIGH | P1 | Validated (partial: Stage 1 done) | C |
| QLT-002 | HIGH | P1 | Validated (narrower scope) | C |
| QLT-005 | MEDIUM | P2 | Validated (+ FQ-001 prereq) | B |
| FQ-001 | MEDIUM | P2 | Validated (new) | B |
| QLT-006 | LOW | P2 | Validated (count corrected to 48) | A |
| QLT-003 | MEDIUM | P2 | Validated | D |
| QLT-004 | MEDIUM | P2 | Validated | E |
| QLT-007 | LOW | P2 | Validated (folded into C) | C |

**Cross-finding dependencies (validated, current):**

1. **QLT-001 → QLT-002:** The 4 inline keyboard builders (`build_purpose_keyboard`,
   `build_condition_keyboard`, `build_feature_keyboard`, `build_currency_keyboard`)
   are the SAME code targeted by both extraction (QLT-001) and token-centralization
   (QLT-002). `BotCallbackPrefix` StrEnum must be introduced **within** QLT-001's
   keyboard-builder extraction — otherwise raw token literals are merely *relocated*
   into `services/ad_data.py` instead of eliminated.
2. **QLT-002 → QLT-005:** The `build_*` keyboard functions are the only sites where
   callback tokens are constructed, and also where button **labels** are hardcoded.
   The `_()` wrapping for keyboard labels should be done in the same pass as
   token-centralization to avoid churning the same functions twice.
3. **FQ-001 → QLT-005:** Wrapping bot strings in `_()` is a no-op without per-user
   `translation.activate()`. FQ-001 must be implemented alongside QLT-005 for the
   i18n wrapping to have behavioral effect.
4. **QLT-007 → QLT-001 (fold-in):** All 9 bare `dict`/`list`/`set` annotations and
   the `except ValueError, Exception:` fix target the helper section that QLT-001
   extracts — parameterizing them during extraction avoids a second pass.

---

## 1. Dependency DAG & Rollout Order

### 1.1 Inter-block dependency analysis

```
Block A (QLT-006)         ──►  Config + auto-fix          ──► unblocks ruff gate for B–E
                                 │
Block B (FQ-001 + QLT-005) ──►  Bot i18n activation + wrapping  ──► independent of A
                                 │
Block C (QLT-001 + 002 + 007) ──►  Bot god-module extraction  ──► depends on nothing,
                                 │                            but B's i18n wrapping
                                 │                            targets the SAME keyboard
                                 │                            builders (B2→QLT-005)
                                 │
Block D (QLT-003)         ──►  ListingsQuery service        ──► web-only, independent
                                 │
Block E (QLT-004)         ──►  AdEditInput DTO              ──► web-only, independent
```

**Why this order:**

- **Block A first** (despite being LOW severity) because it fixes the **lint gate**.
  Code context §QLT-006 confirms the default `ruff check src/backend src/telegram_bot`
  gate is currently broken by 2 pre-existing I001 errors in auto-generated migrations
  (`0005`, `0006`). All subsequent blocks rely on `ruff check` passing; fixing
  migrations + enabling G004 first means every subsequent block's lint gate is green
  from the start.
- **Blocks B–E are independent** after A: B touches bot i18n/middleware, C touches
  bot handler/service extraction, D touches web listings, E touches web edit. No
  file overlap between B/D/E, and C is the only block touching `ad_create.py`
  alongside B (but B's `_()` wrapping for keyboard labels is sequenced *within* C
  per the QLT-002→QLT-005 dependency note above — see Block B sequencing note).
- **C is sequenced last among the bot blocks** because it has the highest test
  coupling (7 bot test files + 2 backend test files importing ~30 symbols from
  `ad_create.py`). B's i18n wrapping of keyboard builders is explicitly folded
  into C's extraction pass per the validated dependency chain.

### 1.2 Sequence (YAML order spec)

```yaml
# order_template.yaml for code-quality-fixes
tasks:
  - id: block_A
    depends_on: []

  - id: block_B
    depends_on:
      - block_A

  - id: block_C
    depends_on:
      - block_A
      - block_B

  - id: block_D
    depends_on:
      - block_A

  - id: block_E
    depends_on:
      - block_A
```

**Rationale for `block_C → depends_on: [block_A, block_B]`:**
- `block_A` (QLT-006) fixes the migrations that would otherwise block C's
  `ruff check --fix` on `ad_create.py` (which has 2 G004 hits).
- `block_B` (FQ-001 + QLT-005) is sequenced before C because the validated
  dependency **QLT-002 → QLT-005** states keyboard *labels* get `_()` wrapping
  in the same pass as token-centralization. C introduces `BotCallbackPrefix`
  and rewrites the keyboard builders — B's `_()` wrapping is applied to the
  rewritten builders during C's extraction pass (not as a separate pre-pass).
  FQ-001's locale middleware must also be live before the rewritten builders'
  `_()`-wrapped labels are exercised in tests. B therefore **must** complete
  first so C's extraction produces i18n-ready keyboard functions.

---

## 2. Block A — QLT-006: Enable G004 ruff rule + canonicalize f-string logging

```yaml
task_id: QLT-006-enable-g004-logging-format
title: Enable G004 ruff rule and canonicalize f-string logging to lazy %s format
priority: low  # P2
depends_on: []
```

### Description

Enable ruff rule `G004` (f-string without `%`-formatting in logging) in
`pyproject.toml` `[tool.ruff.lint] select`, then run `ruff check --fix` to
canonicalize all 48 live G004 hits to lazy `%s` formatting. Also resolves the
2 pre-existing I001 migration-sort errors that currently break the default
`ruff check` gate.

### Goals

- `G004` rule enabled in ruff config
- All 48 G004 f-string logging sites canonicalized to `%s` lazy format
- 2 I001 migration import-sort errors resolved (so `ruff check` is clean)
- Default `ruff check src/backend src/telegram_bot` passes clean (0 errors)
- No behavioral changes — `%s` vs f-string in logging is semantically equivalent

### Semantic targets (files, classes, functions — no line numbers)

| File | Symbol | Change |
|---|---|---|
| `pyproject.toml` | `[tool.ruff.lang] select` list | Add `"G"` entry after `"UP"` |
| `apps/ads/migrations/0005_remove_ad_ix_ads_delete_sweep_ad_ix_ads_delete_sweep.py` | module-level imports | `ruff check --fix` resolves I001 import sort |
| `apps/ads/migrations/0006_ad_ix_ads_draft_sweep.py` | module-level imports | `ruff check --fix` resolves I001 import sort |
| `apps/ads/views/edit.py` | module-level (8 f-string logger calls) | `ruff check --fix` canonicalizes to `%s` |
| `apps/users/views/consent.py` | module-level (8 f-string logger calls) | `ruff check --fix` canonicalizes to `%s` |
| `apps/moderation/services/moderation_log.py` | module-level (6 f-string logger calls) | `ruff check --fix` canonicalizes |
| `apps/media/services/filesystem.py` | module-level (5 f-string logger calls) | `ruff check --fix` canonicalizes |
| `apps/users/services/account_state.py` | module-level (5 f-string logger calls) | `ruff check --fix` canonicalizes |
| `apps/users/services/deletion.py` | module-level (5 f-string logger calls) | `ruff check --fix` canonicalizes |
| `apps/moderation/admin_actions.py` | module-level (4 f-string logger calls) | `ruff check --fix` canonicalizes |
| `apps/moderation/views/review.py` | module-level (3 f-string logger calls) | `ruff check --fix` canonicalizes |
| `apps/ads/views/delete.py` | module-level (2 f-string logger calls) | `ruff check --fix` canonicalizes |
| `telegram_bot/handlers/ad_create.py` | `save_photo`, `download_photo` (2 f-string logger calls) | `ruff check --fix` canonicalizes |

### Implementation notes

- `fix = false` is the project default (`pyproject.toml`). Enabling `G` in `select`
  without `--fix` will make the default `ruff check` **fail** (48 new errors) until
  `ruff check --fix` is run. The two operations must be committed together.
- The I001 migration errors are in auto-generated Django migration files. Per
  project rule #13 (migrations for schema changes) and the validation note, these
  are safe to fix-sort — they are import-ordering only, not schema-affecting.
- `ruff check --fix --select I,G` will address both I001 and G004 in one pass.
  Use `ruff check --fix --select I,G src/backend src/telegram_bot` to scope
  correctly (the global `select` already has `I`, and `G004` is the only `G` rule
  that catches f-string logging).
- `make format` runs `ruff check --fix src/` — after enabling `G`, this will
  automatically canonicalize on every format cycle.
- **Do NOT** touch `listings.py` (0 G004 hits confirmed — it uses plain
  `logger.warning("...")` literals).

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `fix = false` default means enabling `G` immediately breaks `ruff check` gate | Build: CI fast gate fails until `--fix` is committed | Commit config + `--fix` in the same change; verify `ruff check` is clean before merge |
| G004 auto-fix on migration files could reorder imports in a way Django dislikes | Functional: migration import order is cosmetic in Django | Django migrations import `models` module — `isort` reordering is safe; existing migrations already pass `I` rule after `--fix` |
| `%s` substitution in logging changes message format slightly (lazy vs eager) | Observability: identical output at emission; only difference is formatting is deferred | Zero user-visible difference; the validator confirmed `%s` is the project convention (`core/services/contact.py`) |

### Affected tests to run

- `ruff check src/backend src/telegram_bot` → must report 0 errors after fix
- `ruff check --select G004 src/backend src/telegram_bot` → must report 0 errors
- `make test` (fast gate, skips seed) — no behavioral tests affected (logging format only)

### Acceptance criteria

- `G` is present in `pyproject.toml` `[tool.ruff.lint] select`
- `ruff check src/backend src/telegram_bot` → **0 errors** (clean)
- `ruff check --select G004 src/backend src/telegram_bot` → **0 errors**
- All 48 f-string logging sites converted to `%s` lazy format
- 2 I001 migration import-sort errors resolved
- No code-behavior tests regress

### Agents

- **Implementor** — add `G` to select, run `ruff check --fix --select I,G`, verify
- **Validator** — confirm `ruff check` is clean, review the G004→`%s` conversion
  for any semantic edge cases

---

## 3. Block B — FQ-001 + QLT-005: Bot locale activation + i18n wrapping + msgid fixes + gate extension

```yaml
task_id: FQ-001_QLT-005-bot-i18n-activation-wrapping
title: Add per-user translation.activate() in bot middleware; wrap all bot strings in gettext; fix Russian msgids; extend i18n gate to bot handlers
priority: medium  # P2
depends_on:
  - block_A
```

### Description

This block has two interdependent halves: **(a) FQ-001** — add a bot-side i18n
activation middleware that calls `translation.activate(user.telegram_language)`
around handler dispatch; and **(b) QLT-005** — wrap all unwrapped bot strings in
`gettext`/`_()` and fix Russian-as-msgid in `contact.py`. Without FQ-001, QLT-005's
`_()` wrapping produces zero behavioral effect — all bot messages render in the
default thread-local locale regardless of the per-user language setting.

### Goals

- FQ-001: Per-user `translation.activate()` fires before handler dispatch for
  every bot Update (Message + CallbackQuery)
- FQ-001: NEW `LanguageMiddleware` registered in `main.py` `dp.update.middleware`
  AND `conftest.py` `dp` fixture (both wired identically)
- QLT-005: All user-facing strings in `alerts.py` wrapped in `gettext`/`_()`
  (add import; wrap ~18 Russian + English literals)
- QLT-005: All user-facing strings in `ad_create.py` wrapped in `_()`
  (add import; wrap hardcoded Russian fallback at the top-level-category message
  and ~10 other message-answer strings)
- QLT-005: `contact.py` Russian msgids → English msgid (5 sites: `Ошибка...`,
  `объявление больше недоступно`, `продавец больше недоступен`,
  `Ваш запрос отправлен...`, `ANONYMOUS_BUYER_LABEL`)
- QLT-005: Extend `test_i18n_completeness.py` to scan
  `src/telegram_bot/handlers/*.py` for bare user-facing literals and non-English
  msgids
- Extract new strings via `makemessages` and ensure `ru`/`bs` `.po` files have
  non-empty `msgstr`

### Semantic targets (files, classes, functions — no line numbers)

| File | Symbol | Change |
|---|---|---|
| `telegram_bot/middlewares/` (NEW module) | NEW `LanguageMiddleware` class | Class implementing aiogram `MessageHandler`/`BaseMiddleware.__call__` that resolves `event.from_user.id` → `User.telegram_language` → calls `translation.activate(lang)` before `handler(event, data)` and restores previous active locale after |
| `telegram_bot/middlewares/__init__.py` | module exports | Export `LanguageMiddleware` |
| `telegram_bot/main.py` | `main` function — middleware registration | Add `from telegram_bot.middlewares import LanguageMiddleware` to existing import block; add `dp.update.middleware(LanguageMiddleware())` after `UpdateIdDedupMiddleware()` and before `AccountStateMiddleware()` (so locale is active when account-state denial messages are rendered) |
| `telegram_bot/tests/conftest.py` | `dp` fixture (middleware registration section) | Add same `LanguageMiddleware` import + `dp.update.middleware(LanguageMiddleware())` registration, mirroring `main.py` exactly. **Note:** conftest currently omits `ad_copy_router` and `language_router` that `main.py` includes (validation §FQ-001 / code-context §FQ-001) — do NOT add those here unless the test suite requires them; only add the locale middleware. |
| `telegram_bot/handlers/alerts.py` | module imports | Add `from django.utils.translation import gettext as _` |
| `telegram_bot/handlers/alerts.py` | `handle_alerts_start`, `process_alerts_toggle`, `handle_alerts_delete_callback`, `process_alerts_toggle_purpose` (all handler functions with user-facing messages) | Wrap all user-facing string literals (English + Russian) in `_()` |
| `telegram_bot/handlers/alerts.py` | module-level comment (the Cyrillic word at the Re-enable comment) | (QLT-007) Replace Cyrillic word with English "Disable" — **folded into this block** since it's the same file |
| `telegram_bot/handlers/ad_create.py` | module imports | Add `from django.utils.translation import gettext as _` |
| `telegram_bot/handlers/ad_create.py` | `cmd_start`/`cmd_post` greeting messages, top-level-category fallback message, `process_purpose`/`process_condition`/`process_feature`/`process_price`/`process_photos`/`process_preview` handler messages, `show_preview`/`_format_preview_price` messages | Wrap all user-facing string literals in `_()` |
| `telegram_bot/handlers/contact.py` | `ANONYMOUS_BUYER_LABEL` (module constant) | Change `_("Покупатель")` → `_("Buyer")`; update `.po` files to add Russian translation for "Buyer" msgid |
| `telegram_bot/handlers/contact.py` | `handle_contact_orm` (and other contact handler messages) | Change 4 Russian-as-msgid `_("...")` calls to English msgids: `_("Ошибка: не удалось определить отправителя")` → `_("Error: could not determine sender")`, `_("объявление больше недоступно")` → `_("Announcement is no longer available")`, `_("продавец больше недоступен для связи")` → `_("Seller is no longer available for contact")`, `_("Ваш запрос отправлен продавцу анонимно...")` → `_("Your request has been sent to the seller anonymously...")` |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `_collect_template_files` → NEW `_collect_bot_files()` helper | Add function to collect `src/telegram_bot/handlers/*.py` files |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | NEW test `test_bot_no_hardcoded_messages` | Assert bot handler `.py` files have no bare user-facing string literals (i.e., all `message.answer("...")` / `callback.answer("...")` / `text="..."` are wrapped in `_()`) |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | NEW test `test_no_cyrillic_msgids` | Assert no `_("...")` call in bot code uses a non-English (Cyrillic) msgid |
| `.po` files (ru, bs, en) | new msgids extracted from wrapping | Run `makemessages -l ru -l bs -l en` to extract; ensure `ru`/`bs` `msgstr` non-empty |

### Implementation notes

- **FQ-001 middleware design:** The `LanguageMiddleware.__call__` receives
  `(event: Update, data: dict, handler)`. It checks `if event.from_user` (may be
  `None` for channel posts), loads `User.telegram_language` via `sync_to_async`
  (ORM access in async context), calls `translation.activate(lang)` (with a
  fallback to `settings.LANGUAGE_CODE` if the user doesn't exist or has no
  language set), then calls `await handler(event, data)`. The active locale is
  thread-local, so it must be activated **before** the handler runs (which
  renders `_()` calls). No need to restore — the activate is scoped to the
  handler execution per Update; `translation.deactivate()` is implicitly handled
  by Django's thread-local management between updates. Actually, to be safe
  and avoid leaking locale between updates on the same thread, call
  `translation.deactivate()` in a `finally` block after `handler` returns.
- **Middleware ordering:** `LanguageMiddleware` must run BEFORE
  `AccountStateMiddleware` because the account-state denial messages are
  themselves `_()`-wrapped and must render in the user's locale. Placement:
  after `UpdateIdDedupMiddleware` + `LivenessMiddleware`, before
  `AccountStateMiddleware`. This is `main.py` registration order.
- **Conftest wiring:** The `dp` fixture in `conftest.py` must mirror `main.py`
  exactly for the locale middleware. The validation report notes conftest
  currently differs (omits `ad_copy_router` + `language_router`) — this is a
  pre-existing drift to be noted but NOT in scope for this block (FQ-001 only
  adds the locale middleware to both files).
- **Keyboard label wrapping:** Per the QLT-002→QLT-005 dependency, the
  `_()` wrapping of keyboard button labels in `build_*_keyboard` functions is
  deferred to **Block C** (where those builders are extracted and rewritten
  with `BotCallbackPrefix`). This block wraps only the direct `message.answer()`
  / `callback.answer()` / `text=` string literals.
- **Russian-as-msgid fix:** Changing `_("объявление больше недоступно")` →
  `_("Announcement is no longer available")` removes the old msgid from the
  catalog. `makemessages` will drop the old msgid and add the new one. Ensure
  `ru`/`bs` translations are populated for the new English msgids (add entries
  to `.po` files with `msgstr` = the previously-Russian text, since those
  translations already exist in the catalog under the old msgid).
- **i18n gate extension:** The new tests scan `src/telegram_bot/handlers/*.py`
  using AST to find string literals passed to `message.answer()`,
  `callback.answer()`, `builder.button(text=...)`, and `edit_message` calls.
  These are marked `@pytest.mark.unit` (fast gate, no DB).

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Locale middleware not activated before handler renders `_()` calls | UX: bot strings still render in default locale | Verify middleware registration order in both `main.py` and `conftest.py`; test via `test_multi_lang_translation.py` |
| ORM `User.telegram_language` lookup in middleware adds DB latency per update | Performance: one async DB hit per incoming Update | Cache user locale per `from_user.id` in-memory for the update lifetime (simple dict) — optional optimization; the bot processes updates sequentially per chat |
| Conftest/test-prod wiring drift: if `LanguageMiddleware` is added to `main.py` but not `conftest.py` | Test: bot i18n tests pass but production doesn't activate locale | **Both files must be edited atomically** (same task); acceptance criteria verifies both |
| Russian→English msgid change leaves orphaned `.po` entries | I18n: `test_no_empty_msgstr` or `test_extraction_completeness` may fail | Run `makemessages` after wrapping; prune orphaned msgids with `msgfmt --check` or `makemessages --no-location --no-obsolete` |
| Over-wrapping non-user-facing strings (debug logs, internal error strings) | I18n: bloats `.po` catalog with non-translatable entries | Gate the new test to only flag strings passed to user-facing answer/text APIs, not `logger.*` calls |

### Affected tests to run

- `$dc run --rm -e PYTEST_OPTS="-k test_i18n_completeness" test` (extended gate)
- `$dc run --rm -e PYTEST_OPTS="-k test_multi_lang_translation" test` (per-user locale activation)
- `$dc run --rm -e PYTEST_OPTS="-k test_contact or -k test_login or -k test_alerts" test` (bot handler tests after wrapping)
- `uv run ruff check src/telegram_bot/` (no new lint errors from wrapping)
- `uv run python src/backend/manage.py makemessages -l ru -l bs -l en --no-location` (extraction succeeds)

### Acceptance criteria

- FQ-001: `LanguageMiddleware` class exists in `telegram_bot/middlewares/`, exported from `__init__.py`
- FQ-001: `main.py` registers `LanguageMiddleware` on `dp.update.middleware` (before `AccountStateMiddleware`)
- FQ-001: `conftest.py` `dp` fixture registers `LanguageMiddleware` identically
- FQ-001: `translation.activate()` is called with `user.telegram_language` before handler dispatch (verified by `test_multi_lang_translation.py` extension)
- QLT-005: `alerts.py` imports `gettext as _` and all user-facing strings are wrapped
- QLT-005: `ad_create.py` imports `gettext as _` and all user-facing strings are wrapped
- QLT-005: `contact.py` msgids are English (no `_("...Russian...")` calls remain)
- QLT-005: `test_i18n_completeness.py` has new tests scanning bot handler `.py` files; they pass
- QLT-005: `ru`/`bs` `.po` files have non-empty `msgstr` for all new msgids (via `test_no_empty_msgstr`)
- QLT-007: Cyrillic comment in `alerts.py` replaced with English
- `ruff check src/telegram_bot/` → 0 errors

### Sequencing within block

1. Create `LanguageMiddleware` class in `telegram_bot/middlewares/language.py`
2. Export from `telegram_bot/middlewares/__init__.py`
3. Register in `main.py` (`main()` function, middleware registration section)
4. Register in `conftest.py` (`dp` fixture)
5. Add `_()` import to `alerts.py`; wrap all user-facing strings
6. Fix Cyrillic comment in `alerts.py` (QLT-007 fold-in)
7. Add `_()` import to `ad_create.py`; wrap all user-facing strings
8. Fix `contact.py` Russian msgids → English (4 string changes + `ANONYMOUS_BUYER_LABEL`)
9. Run `makemessages -l ru -l bs -l en` to extract new/renamed msgids
10. Populate `ru`/`bs` `.po` `msgstr` for new English msgids
11. Extend `test_i18n_completeness.py` with `_collect_bot_files()` + 2 new gate tests
12. Extend `test_multi_lang_translation.py` to assert per-user locale activation
13. Run bot handler tests + i18n gate tests

### Agents

- **Implementor** (primary) — middleware class, registration in both files, string
  wrapping, msgid fixes, gate extension
- **Validator** — verify middleware placement in `main.py` vs `conftest.py`, review
  msgid English-ness, run i18n gate + bot handler tests

**Note:** QLT-007's Cyrillic comment fix is explicitly folded into this block
(the file is `alerts.py`, same file being wrapped for QLT-005). The 9 bare
`dict`/`list`/`set` annotation parameterizations are folded into **Block C**
(per QLT-007 validation note: "these annotations live in the helper section
targeted by QLT-001's extraction").

---

## 4. Block C — QLT-001 + QLT-002 + QLT-007: Bot god-module extraction + callback StrEnum + generics parameterization

```yaml
task_id: QLT-001_002_007-bot-god-module-extraction
title: Extract 15 sync_to_async ORM helpers + keyboard builders from ad_create.py into services/ad_data.py; introduce BotCallbackPrefix StrEnum; parameterize bare generics; fix except clause
priority: high  # P1
depends_on:
  - block_A
  - block_B
```

### Description

The highest-risk block. Extracts the 15 inlined `sync_to_async` ORM helpers,
the 4 inline keyboard builders, the media helpers (`download_photo`,
`save_photo`), and `translate_all_languages` out of the 1393-line
`ad_create.py` handler into a new `telegram_bot/services/ad_data.py` service
module. In the **same pass**, introduces the `BotCallbackPrefix` StrEnum in
`telegram_bot/schemas/callbacks.py` and routes all 6 token pairs + the
`contact_us` literal through it. Also parameterizes the 9 bare
`dict`/`list`/`set` annotations (QLT-007), fixes the redundant
`except ValueError, Exception:` clause (QLT-001), replaces the Cyrillic
locale list `["ru","bs","en"]` with `LanguageLocale.values()` (QLT-002), and
applies `_()` wrapping to the newly-extracted keyboard builder button labels
(QLT-002→QLT-005 dependency).

Stage 1 (submit_ad extraction) is DONE — this block starts at the helper
section (currently `# Helper functions using sync_to_async`) and the keyboard
builders scattered in the handler body.

### Goals

- 15 `sync_to_async` ORM helpers extracted to `telegram_bot/services/ad_data.py`
- 4 keyboard builders (`build_purpose_keyboard`, `build_condition_keyboard`,
  `build_feature_keyboard`, `build_currency_keyboard`) extracted to
  `ad_data.py`
- `download_photo`, `save_photo`, `translate_all_languages` extracted to
  `ad_data.py` (media + translation helpers)
- `BotCallbackPrefix` StrEnum created in `telegram_bot/schemas/callbacks.py`
- All 6 ad_create.py callback token pairs routed through `BotCallbackPrefix`
  (both filter lambdas and builder f-strings/literals)
- `login.py` `contact_us` literal → `CONTACT_US_CALLBACK` from `contact.py`
- Locale list `["ru","bs","en"]` → `LanguageLocale.values()` in
  `translate_all_languages` call site
- 9 bare `dict`/`list`/`set` annotations parameterized (in the extracted
  `ad_data.py`)
- `except ValueError, Exception:` → `except (ValueError, ArithmeticError):`
- Keyboard builder button labels wrapped in `_()` (QLT-005 continuation from
  Block B)
- All test imports/patches that reference `telegram_bot.handlers.ad_create.*`
  symbols updated or re-exported
- `ad_create.py` remains as a thin handler-only module

### Semantic targets (files, classes, functions — no line numbers)

| File | Symbol | Current state | Change |
|---|---|---|---|
| `telegram_bot/schemas/callbacks.py` (NEW) | NEW module | Does not exist (`schemas/` has only `__init__.py`, `message_payloads.py`, `saved_search.py`) | Create module with `BotCallbackPrefix(StrEnum)` covering: `purpose`, `condition`, `feature`, `price_currency`, `price_free`, `features_done`, `contact_us` |
| `telegram_bot/services/ad_data.py` (NEW) | NEW module | Does not exist | Create with: 15 extracted `sync_to_async` ORM helpers, 4 keyboard builders, `download_photo`, `save_photo`, `translate_all_languages`. All with parameterized generics. `BotCallbackPrefix` imported and used in builders. `LanguageLocale.values()` used in `translate_all_languages`. |
| `telegram_bot/handlers/ad_create.py` | module imports | Imports ORM models, `sync_to_async`, etc. directly | Remove ORM model imports now only used by extracted helpers; add `from telegram_bot.services.ad_data import ...` for the extracted symbols; keep `gettext as _` import from Block B |
| `telegram_bot/handlers/ad_create.py` | all 15 `sync_to_async` helpers + `download_photo` + `save_photo` + `translate_all_languages` + 4 `build_*_keyboard` functions | Defined inline in handler body | **DELETE** from `ad_create.py` (moved to `ad_data.py`) |
| `telegram_bot/handlers/ad_create.py` | 6 router callback filter lambdas | `lambda c: c.data.startswith("purpose:")` etc. | Replace raw string with `BotCallbackPrefix.PURPOSE` etc. |
| `telegram_bot/handlers/ad_create.py` | `except ValueError, Exception:` clause (in price/photo handler) | Redundant compound except | Replace with `except (ValueError, ArithmeticError):` |
| `telegram_bot/handlers/ad_create.py` | `translate_all_languages` call sites (2) | `["ru", "bs", "en"]` literal | Replace with `LanguageLocale.values()` |
| `telegram_bot/handlers/login.py` | `handle_login_deep_link` function | `callback_data="contact_us"` literal | Replace with imported `CONTACT_US_CALLBACK` from `contact.py` |
| `telegram_bot/handlers/contact.py` | module-level `CONTACT_US_CALLBACK` constant | `Final[str] = "contact_us"` (already defined) | Confirm it can be imported by `login.py` (no change if already importable) |
| `apps/media/tests/test_save_photo_exif.py` | test imports | `from telegram_bot.handlers.ad_create import save_photo` | Update to `from telegram_bot.services.ad_data import save_photo` |
| `apps/media/tests/test_save_photo_exif.py` | test patch targets | `mock.patch("telegram_bot.handlers.ad_create.save_photo")` | Update to `mock.patch("telegram_bot.services.ad_data.save_photo")` or re-export path |
| `apps/media/tests/test_thumbnail_integration.py` | test imports | `from telegram_bot.handlers.ad_create import save_photo` | Update to `from telegram_bot.services.ad_data import save_photo` |
| `src/telegram_bot/tests/test_ad_create.py` | imports | `create_draft_ad, process_preview, cmd_cancel, delete_draft, process_photos, translate_all_languages` from `ad_create` | Update helper imports to `ad_data.py`; keep handler-only imports (`process_preview`, `cmd_cancel`, `process_photos`) from `ad_create` |
| `src/telegram_bot/tests/test_ad_create.py` | patch targets | `mock.patch("telegram_bot.handlers.ad_create.download_photo")`, `.save_photo`, `.validate_photo`, `.check_upload_rate_limit`, `.delete_photo`, `.translate_all_languages` | Update to `mock.patch("telegram_bot.services.ad_data.download_photo")` etc. — OR use re-export approach (see Implementation notes) |
| `src/telegram_bot/tests/test_ad_create_condition.py` | imports | `AdCreateForm, process_condition, build_feature_keyboard` from `ad_create` | Update `build_feature_keyboard` import to `ad_data.py`; keep `AdCreateForm`, `process_condition` from `ad_create` |
| `src/telegram_bot/tests/test_multi_lang_translation.py` | imports | `translate_all_languages` from `ad_create` | Update to import from `ad_data.py` |
| `src/telegram_bot/tests/test_price_payload.py` | imports | `AdCreateForm, process_price_currency` from `ad_create` | These are handlers — keep from `ad_create`. No change needed unless `AdCreateForm` is affected. |
| `src/telegram_bot/tests/test_create_draft_ad.py` | imports | `create_draft_ad, delete_draft` from `ad_create` | Update to `ad_data.py` |
| `src/telegram_bot/tests/test_site_name_greeting.py` | imports + patches | `cmd_post` from `ad_create`; `mock.patch("telegram_bot.handlers.ad_create.create_draft_ad")`, `.get_site_name_async` | Update `create_draft_ad` import + patch path to `ad_data.py`; `get_site_name_async` — verify if it's also extracted (check if it's one of the 15 — it is NOT in the cited list; it may be a separate helper — verify in source) |

### Implementation notes

- **Re-export vs. update-test approach:** The validation report's code-context §QLT-001
  identifies the choice: either leave re-exports in `ad_create.py`
  (`from telegram_bot.services.ad_data import create_draft_ad  # re-export`) or update
  every test import/patch site (~30 sites). The validation notes the re-export approach
  is faster but leaves a stale indirection; updating all sites is cleaner but riskier
  (patch paths are exact-match strings — a single wrong path silently no-ops the mock).
  **Recommendation:** Update all test import/patch sites explicitly (no re-exports).
  This is the cleaner approach and avoids masking future breakage via stale
  re-exports. The patch-path updates must be exhaustive — grep for ALL
  `mock.patch("telegram_bot.handlers.ad_create.X")` patterns.
- **`get_site_name_async` verification:** This function is patched by
  `test_site_name_greeting.py` but is NOT in the audit's 14-helper (now 15-helper)
  list. The code-context notes this is a "false positive in the audit's concern."
  The Implementor MUST verify whether `get_site_name_async` is extracted or stays in
  `ad_create.py` — if it remains, its patch path is unchanged.
- **`save_photo` backend test imports:** `test_save_photo_exif.py` and
  `test_thumbnail_integration.py` both import `save_photo` from
  `telegram_bot.handlers.ad_create` — these are **backend** tests under
  `apps/media/tests/`. Updating them to `telegram_bot.services.ad_data` creates a
  backend→bot import (which is the correct direction: backend test imports bot
  service, NOT bot importing backend). This is acceptable — the constraint is
  "backend must never import telegram_bot for *production code*," but test imports
  from the bot are already established here (pre-existing pattern).
- **`build_currency_keyboard` co-relocation:** Validation §Cross-Finding notes this
  builder sits at line 526 (near `process_price_currency`), OUTSIDE the helper section
  (889–1393). It handles `price_currency:` and `price_free` tokens — it MUST be
  relocated alongside the other 3 builders into `ad_data.py` to capture the
  `price_currency:`/`price_free` literals for `BotCallbackPrefix` centralization.
- **`translate_all_languages` and `_()` wrapping:** This function calls
  `message.answer` with translated content — its user-facing strings must be wrapped
  in `_()` as part of Block B's QLT-005 scope. Since it's extracted in this block,
  the `_()` import (added in Block B) carries into `ad_data.py`.
- **Bot→backend import direction:** `ad_data.py` may import backend models
  (`apps.ads.models.Ad`, `apps.categories.models.Category`, etc.) and shared
  services (`apps.categories.services.lookup_resolution.CategoryLookupResolver`) —
  this is bot→backend, which is correct. The extracted helpers that delegate to
  `CategoryLookupResolver` (`get_resolved_purposes`, `get_resolved_features`,
  `get_resolved_conditions`) should call the shared resolver directly.
- **Orphan .pyc:** Code-context §QLT-001 confirms the orphaned
  `telegram_bot/services/__pycache__/media.cpython-314.pyc` is **already absent**.
  No pruning action needed (the audit's recommendation is resolved).

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| 7 bot test files + 2 backend test files with ~30 import/patch sites break | Build/Tests: 14 test files may fail to collect or mock silently no-op | Exhaustive grep for `from telegram_bot.handlers.ad_create import` and `mock.patch("telegram_bot.handlers.ad_create.` patterns; update ALL sites; verify each patch path with a focused test run |
| Patch-path mismatch silently no-ops mocks (old path doesn't exist → `patch` targets nonexistent attribute) | Correctness: tests pass but mocks don't apply → false green | After extraction, run `pytest --co -q` to verify all test files collect; then run each affected test file individually |
| `LanguageMiddleware` (from Block B) + locale not active during keyboard builder extraction | UX: button labels wrap in `_()` but render in default locale | Block B completes first (dependency ensures `LanguageMiddleware` is wired before C's `_()`-wrapped builders are tested) |
| Circular import: `ad_data.py` imports backend models, backend has no bot imports (correct) | Architecture: import cycle at startup | Verified: bot→backend only; `ad_data.py` imports from `apps.*` but `apps.*` never imports `telegram_bot.*` |
| `get_site_name_async` misidentified as extracted (false positive) | Tests: `test_site_name_greeting.py` patch breaks | Verify in source before extraction; if it stays in `ad_create.py`, leave its patch path unchanged |
| `build_currency_keyboard` at line 526 missed during extraction (outside helper section) | QLT-002: `price_currency:`/`price_free` literals not centralized | Explicitly include as a named extraction target (see semantic targets) |

### Affected tests to run

- `$dc run --rm -e PYTEST_OPTS="-k test_ad_create" test` (main handler tests)
- `$dc run --rm -e PYTEST_OPTS="-k test_ad_create_condition" test`
- `$dc run --rm -e PYTEST_OPTS="-k test_multi_lang_translation" test`
- `$dc run --rm -e PYTEST_OPTS="-k test_price_payload" test`
- `$dc run --rm -e PYTEST_OPTS="-k test_create_draft_ad" test`
- `$dc run --rm -e PYTEST_OPTS="-k test_site_name_greeting" test`
- `$dc run --rm -e PYTEST_OPTS="-k test_save_photo" test`
- `$dc run --rm -e PYTEST_OPTS="-k test_thumbnail" test`
- `$dc run --rm -e PYTEST_OPTS="-k test_i18n_completeness" test` (keyboard labels wrapped)
- `uv run ruff check src/telegram_bot/` → 0 errors
- `uv run basedpyright src/telegram_bot/services/ad_data.py`

### Acceptance criteria

- `telegram_bot/services/ad_data.py` contains all 15 extracted `sync_to_async` ORM
  helpers + `download_photo` + `save_photo` + `translate_all_languages` + 4
  `build_*_keyboard` functions
- `ad_create.py` handler section no longer contains the helper functions (only
  handler/route functions remain — module is significantly smaller, ~300 lines)
- `telegram_bot/schemas/callbacks.py` exists with `BotCallbackPrefix(StrEnum)`
  containing all 6 ad_create tokens + `contact_us`
- All 6 token pairs in `ad_create.py` use `BotCallbackPrefix` (both filter lambdas
  and builder sites) — no raw `"purpose:"` / `"condition:"` / etc. string literals
- `login.py` `handle_login_deep_link` imports `CONTACT_US_CALLBACK` from `contact.py`
- `["ru", "bs", "en"]` literal in `translate_all_languages` call replaced with
  `LanguageLocale.values()`
- `except ValueError, Exception:` → `except (ValueError, ArithmeticError):`
- All 9 bare `dict`/`list`/`set` annotations parameterized in `ad_data.py`
- Keyboard builder button labels wrapped in `_()` (from Block B import)
- All 7 bot test files + 2 backend test files import/patch sites updated to
  `ad_data.py` paths
- `pytest --co -q src/telegram_bot/tests/ src/backend/apps/media/tests/` → all
  collect without ImportError
- `ruff check src/telegram_bot/` → 0 errors
- `basedpyright src/telegram_bot/services/ad_data.py` → 0 type errors

### Sequencing within block

1. Create `telegram_bot/schemas/callbacks.py` with `BotCallbackPrefix(StrEnum)`
2. Create `telegram_bot/services/ad_data.py` with all 15 extracted helpers +
   `download_photo` + `save_photo` + `translate_all_languages` + 4 keyboard
   builders — using `BotCallbackPrefix` and `LanguageLocale.values()`, with
   parameterized generics, `_()`-wrapped labels, and `except (ValueError,
   ArithmeticError):`
3. Remove extracted functions from `ad_create.py`; update its imports (remove
   ORM models, add `from telegram_bot.services.ad_data import ...`)
4. Update `ad_create.py` callback filter lambdas to use `BotCallbackPrefix`
5. Update `login.py` to import `CONTACT_US_CALLBACK` from `contact.py`
6. Update all 7 bot test files' import + patch paths (exhaustive grep-verification)
7. Update 2 backend test files' import + patch paths for `save_photo`
8. Run `pytest --co -q` to verify clean collection
9. Run all affected tests (listed above)
10. Run `ruff check` + `basedpyright` on `ad_data.py` + `ad_create.py`

### Agents

- **Implementor** (primary) — service extraction, StrEnum creation, test path
  updates, `_()` wrapping of keyboard labels
- **Validator** — verify all filter+builder token sites are centralized (grep for
  raw literals in `ad_create.py`), verify import direction (bot→backend only),
  verify test collection + patch-path correctness, run full affected test suite

---

## 5. Block D — QLT-003: Extract `ListingsQuery` service + share with `search.py`

```yaml
task_id: QLT-003-listings-query-service
title: Extract ListingsQuery service with Pydantic DTO for parsed filter params; make listings() a thin adapter; share query object with search.py
priority: medium  # P2
depends_on:
  - block_A
```

### Description

The web `listings()` view function (~260 lines of body) embeds request-parameter
parsing, queryset filtering (category subtree, city did-you-mean, price-range
coercion, purpose/condition/features slug filters), sort mapping (`if/elif`
against `AdSort`), favorite-state annotation, pagination, and context assembly.
Extract a `ListingsQuery` service that accepts a Pydantic DTO of parsed params
and returns a `QuerySet`/paginated result; make `listings()` a thin adapter
(parse params → call service → render). Share the query object with
`search/views/search.py` to eliminate the parallel filter-logic duplication
confirmed at `search.py` lines 79/106/111/132/148/256/258.

### Goals

- `ListingsQuery` service class in `apps/ads/services/listings_query.py`
- Pydantic DTO (`ListingsQueryParams`) for all parsed request params
- `listings()` view becomes a thin adapter (parse → service → render)
- `search.py` imports and uses the shared `ListingsQuery` (or its DTO) to
  de-duplicate filter logic
- Queryset/filter/sort/pagination semantics preserved exactly (existing
  `test_listings.py` must pass)
- All manual `int(min_price)`/`Decimal` coercion with silent `except: pass`
  replaced by Pydantic validation (errors → user-friendly, not silent)

### Semantic targets (files, classes, functions — no line numbers)

| File | Symbol | Current state | Change |
|---|---|---|
| `apps/ads/services/listings_query.py` (NEW) | NEW module | Does not exist | Create `ListingsQuery` class + `ListingsQueryParams` Pydantic DTO |
| `apps/ads/services/__init__.py` | (package) | May or may not exist | Ensure `__init__.py` exports `ListingsQuery` if needed |
| `apps/ads/views/listings.py` | `listings()` function | ~260-line body with inline filter/sort/pagination | Replace body with: parse `request.GET` → `ListingsQueryParams.model_validate(...)` → `ListingsQuery.build_queryset(params)` → `Paginator` → context dict → `render()` |
| `apps/ads/views/listings.py` | `listings()` import block | Imports ORM, `suggest_city`, `get_descendants`, `Paginator`, `AdSort` directly | Keep only `render`-level imports; delegate ORM/filter logic to `ListingsQuery` |
| `apps/search/views/search.py` | `search()` function (filter/sort section) | Re-implements `get_descendants`, `price_normalized_eur__gte=int(min_price)`, `listing_purpose__slug`, `features__slug`, `order_by(F(...))` | Replace inline filter predicates with `ListingsQuery.build_queryset(ListingsQueryParams(...))` or a shared filter-builder method |
| `apps/ads/tests/test_listings.py` | (existing tests) | Tests assert on `listings()` HTTP response | Must still pass — `ListingsQuery` must produce identical queryset semantics |
| `apps/search/services/alert_query.py` | (thin-service precedent) | 228 lines, uses `get_descendants` + `price_normalized_eur__gte` | Reference pattern for `ListingsQuery` (mirror its import style + structure) |

### Implementation notes

- **DTO design:** `ListingsQueryParams` Pydantic model fields: `category_slug: str | None`,
  `city_slug: str | None`, `min_price: int | None`, `max_price: int | None`,
  `purpose_slug: str | None`, `condition_slug: str | None`, `feature_slugs: list[str]`,
  `sort: AdSort`, `page: int = 1`, `per_page: int = PER_PAGE`. Pydantic handles
  `int`/`Decimal` coercion with proper error reporting (no more silent `except: pass`).
- **Service design:** `ListingsQuery` class (or a single function — keep it
  simple per project rule #5) takes `ListingsQueryParams`, builds the `QuerySet`
  with all filter/sort/pagination, and returns either a paginated result object
  or the `QuerySet` + `Paginator` page object. The validation report's recommendation
  cites a class mirroring `alert_query.py` — use a class for consistency.
- **`search.py` integration:** `search.py` (374 lines) has its own parameter parsing
  (slightly different from `listings.py` — it has query-string input). The shared
  `ListingsQuery` should accept the DTO and produce the queryset; `search.py`
  parses its params into the same DTO, then calls `ListingsQuery`. Verify the
  filter predicates in `search.py` map 1:1 to `listings.py`'s (the validation
  confirms they do at lines 79/106/111/132/148/256/258).
- **`distinct()` preservation:** `listings.py` uses `.distinct()` after
  multi-value `features__slug` filtering — `ListingsQuery` must include this.
- **`annotate_favorites`:** `listings.py` calls `annotate_favorites` on the
  queryset. This should be called inside `ListingsQuery` (or as a separate
  post-query step) — verify it doesn't depend on request-scoped `User` (it
  likely uses `request.user` — if so, the DTO must carry `user_id` or the
  service must accept the request separately).
- **`suggest_city` did-you-mean:** The city-did-you-mean logic (`suggest_city`)
  produces a suggestion string for the template context — this is view-level
  (not queryset-level). `ListingsQuery` should return the queryset; the
  did-you-mean suggestion stays in the view adapter or is a separate
  `suggest_city` call in the thin view.

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Queryset semantics change (filter order, `distinct()`, annotation) | Functional: listings/search may return different results | Preserve exact filter order + `distinct()`; use `str(queryset.query)` diff to compare before/after |
| `annotate_favorites` requires `request.user` (request-scoped) | Architecture: service can't be stateless | Pass `user` to `ListingsQuery.build(user=...)` or keep annotation in the view adapter |
| Pydantic validation rejects previously-silent inputs (e.g. non-numeric min_price) | UX: previously-swallowed bad input now errors | Pydantic validation errors → return user-friendly 400 message, not 500 |
| `search.py` param-parsing differs from `listings.py` | Correctness: shared DTO may not cover search's params | Audit `search.py` param parsing; extend DTO if search has extra params (e.g. query string `q`) |
| `PER_PAGE` constant location / value | Correctness: pagination page size must match | Preserve existing `PER_PAGE` import/source |

### Affected tests to run

- `$dc run --rm -e PYTEST_OPTS="-k test_listings" test`
- `$dc run --rm -e PYTEST_OPTS="-k test_search" test`
- `uv run ruff check src/backend/apps/ads/views/listings.py src/backend/apps/search/views/search.py src/backend/apps/ads/services/listings_query.py`
- `uv run basedpyright src/backend/apps/ads/services/listings_query.py`

### Acceptance criteria

- `ListingsQuery` class exists in `apps/ads/services/listings_query.py`
- `ListingsQueryParams` Pydantic DTO validates all filter params (no silent `except: pass`)
- `listings()` view body is < 60 lines (thin adapter)
- `listings()` uses `ListingsQuery.build_queryset(params)` / `ListingsQuery.execute(params)`
- `search.py` imports `ListingsQuery` or `ListingsQueryParams` (no duplicate filter predicates)
- No raw `int(min_price)` / `Decimal` coercion with `except: pass` remains in `listings.py`
- `test_listings.py` tests pass (identical queryset semantics)
- `test_search.py` tests pass (search reuses shared logic)
- `ruff check` + `basedpyright` clean on all 3 files

### Sequencing within block

1. Read `listings.py` `listings()` body + `search.py` `search()` body in full to
   map all filter/sort/pagination predicates
2. Read `alert_query.py` as the thin-service precedent
3. Design `ListingsQueryParams` Pydantic DTO (all fields + validation)
4. Design `ListingsQuery` class (build_queryset + pagination + annotate_favorites)
5. Create `apps/ads/services/listings_query.py`
6. Refactor `listings()` view to thin adapter
7. Refactor `search.py` to use shared `ListingsQuery`
8. Run `test_listings.py` + `test_search.py`
9. Run `ruff check` + `basedpyright`

### Agents

- **Implementor** (primary) — DTO + service extraction, view thinning, search.py
  integration
- **Validator** — verify queryset semantics preservation (field-level diff), review
  Pydantic validation design, run listings + search test suites

---

## 6. Block E — QLT-004: Introduce `AdEditInput` Pydantic DTO for web edit POST

```yaml
task_id: QLT-004-ad-edit-input-dto
title: Introduce AdEditInput Pydantic DTO for edit POST; validate before ORM write; explicitly model currency-fallback-on-invalid and no-change-vs-clear semantics
priority: medium  # P2
depends_on:
  - block_A
```

### Description

The `ad_edit` POST handler reads `request.POST.get("title")`, `("description")`,
`("price_amount")`, `("price_currency")` directly with manual `.strip()` +
`Decimal()` coercion and writes to the ORM via `ad.save(update_fields=...)`
without any Pydantic DTO. The sibling reactivation branch already validates via
`SubmitAdInput`. Introduce an `AdEditInput` Pydantic DTO that validates the edit
POST **before** any ORM write, explicitly modeling the currency-fallback-on-invalid
and no-change-vs-clear semantics that are currently undocumented edge behaviors
in `edit.py`.

**Critical constraint:** The edit path deliberately diverges from the bot flow —
it preserves the ad's **current currency on invalid input** (with explicit
comment), while the bot flow always passes a valid `CurrencyCode`. A naive
drop-in of `SubmitAdInput` would lose that semantic. The DTO must encode:
"keep current currency when input is invalid/blank."

### Goals

- `AdEditInput` Pydantic DTO created (extends or alongside `SubmitAdInput`)
- `ad_edit` POST validates via `AdEditInput` before any `ad.save()`
- Currency-fallback-on-invalid explicitly modeled (default = current ad currency
  when input currency is invalid/blank)
- No-change-vs-clear semantics explicitly modeled (blank title/description =
  preserve current values; this surfaces the latent validation gap where blank
  values currently overwrite unconditionally)
- All 3 unvalidated `ad.save(update_fields=...)` branches routed through DTO
- `test_edit.py` passes (behavior preserved or test contract updated if the
  blank-overwrite gap is closed)

### Semantic targets (files, classes, functions — no line numbers)

| File | Symbol | Current state | Change |
|---|---|---|
| `apps/ads/services/submission.py` | `SubmitAdInput` class | Pydantic `BaseModel` used by reactivation branch | Either extend `SubmitAdInput` with edit-specific fields, or create `AdEditInput` as a sibling DTO |
| `apps/ads/views/edit.py` | `ad_edit` POST handler — text-edit branch | `request.POST.get("title")`, `.strip()`, `ad.save(update_fields=[...])` | Validate via `AdEditInput.model_validate(...)` before `ad.save` |
| `apps/ads/views/edit.py` | `ad_edit` POST handler — price-edit branch | `Decimal()`, `except Exception: price_amount = Decimal("0")`, `CurrencyCode()`, `except ValueError: pass`, `ad.save(update_fields=[...])` | Route through `AdEditInput` with currency-fallback modeling |
| `apps/ads/views/edit.py` | `ad_edit` POST handler — else/other-status branch | `ad.save(update_fields=[...])` (unvalidated) | Route through `AdEditInput` |
| `apps/ads/views/edit.py` | `_text_fields_changed` + `_apply_price_change` (private helpers) | Already exist (partial extraction for price/text diffing) | Keep; integrate with DTO validation results |
| `apps/ads/views/edit.py` | reactivation branch | `submit_ad(SubmitAdInput(...))` | No change (already validated — serves as reference for the DTO pattern) |
| `apps/ads/tests/test_edit.py` | (existing tests) | Asserts on current currency-fallback and unconditional overwrite behavior | Must pass — either behavior preserved or contract explicitly updated |

### Implementation notes

- **DTO placement decision:** `SubmitAdInput` lives in
  `apps/ads/services/submission.py:36`. The audit asks to "extend `SubmitAdInput`
  or add `AdEditInput`." Recommendation: create `AdEditInput` as a **sibling**
  DTO (not extend `SubmitAdInput`) because the two flows have divergent semantics:
  - `SubmitAdInput` (bot/reactivation): always provides valid `CurrencyCode`,
    validates against auto-moderation, creates a new `Ad`
  - `AdEditInput` (web edit): updates an existing `Ad`, must handle
    "currency-fallback-on-invalid" (keep current), must handle
    "no-change-vs-clear" (blank = keep), partial field updates (`update_fields`
    subsets per branch)
  Same file (`submission.py`), new class. This keeps the service layer cohesive.
- **Currency-fallback-on-invalid:** `AdEditInput` field `price_currency: CurrencyCode | None = None`.
  A Pydantic `field_validator` on `price_currency` that returns `None` on
  `ValueError`/`decimal.InvalidOperation` (invalid currency code). The view
  then applies: `if dto.price_currency is None: use ad.currency` (preserve
  current). This models the current `except ValueError: pass` → "keep existing"
  behavior explicitly.
- **No-change-vs-clear:** `AdEditInput` field `title: str | None = None`,
  `description: str | None = None`. A `None` sentinel = "field not provided in
  POST" → skip `update_fields` for that field. An empty string `""` = "user
  wants to clear" → `update_fields` includes the field with `""`. This surfaces
  the latent validation gap: currently `request.POST.get("title")` returns `""`
  if the field is blank, and `"".strip()` → `""` overwrites the title with
  empty. The DTO should make this explicit — either reject blank titles
  (validation error) or require a separate "clear" signal. **Recommendation:**
  default to rejecting blank `title`/`description` (Pydantic min_length=1)
  UNLESS the POST explicitly sends `clear_title=1`. This closes the gap
  documented in the audit ("unconditional title/description overwrite is itself
  a latent validation gap a DTO would surface"). **Risk:** this changes behavior
  — verify `test_edit.py` assertions. If tests assert blank overwrites, update
  them with the Product Owner's decision.
  - **Safer alternative:** preserve current behavior (blank overwrites) but
    make it explicit via the DTO (document `blank_ok=True` on the field),
    and add a TODO for the validation gap. This avoids behavioral regression
    while still routing through the DTO. **Recommendation:** use this safer
    approach — preserve behavior, make it explicit, document the gap.
- **`price_amount` Decimal coercion:** Replace `Decimal()` +
  `except Exception: Decimal("0")` with Pydantic `Decimal` field with
  `ge=0`. If the input can't coerce, Pydantic raises `ValidationError` →
  view returns a user-friendly error (not a silent `Decimal("0")` fallback).
  **Risk:** currently invalid `price_amount` silently becomes `Decimal("0")`
  (Free). Changing this to a validation error changes behavior for users
  sending garbage. Verify `test_edit.py`. **Safer alternative:** keep the
  fallback in the DTO validator:
  `field_validator("price_amount")` that catches `InvalidOperation` and
  returns `Decimal("0")` (explicitly modeling "invalid → Free").
- **`auto_moderate` bool-branch:** The audit notes `edit.py:238` (now shifted)
  renders `_("Ad failed moderation checks")`. The DTO must not interfere with
  the auto-moderation re-check after save.

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Currency-fallback semantics lost (naive SubmitAdInput drop-in) | Functional: invalid currency → new ad row, not "keep current" | DTO explicitly models `price_currency: CurrencyCode | None` with `None` = preserve current; validator catches `ValueError` → `None` |
| Blank title/description overwrite behavior changes | UX/test: currently blank inputs overwrite with empty string | **Preserve** current blanket-overwrite behavior but make explicit in the DTO (documented `blank_ok`); do NOT close the validation gap in this pass (defer as TODO) |
| `Decimal("0")` fallback for invalid price_amount lost | Functional: garbage price → validation error instead of Free | Model the fallback explicitly in a `field_validator` returning `Decimal("0")` on `InvalidOperation` |
| `test_edit.py` asserts on undocumented edge behaviors | Test: 3 test methods may regress | Read `test_edit.py` BEFORE implementing; map each assertion to a DTO semantic; update test contract only with explicit PO sign-off |
| `SubmitAdInput` is imported by bot code (`ad_create.py` via `submission.py`) | Architecture: changing `submission.py` affects both bot + web | `AdEditInput` is a NEW class in `submission.py` — `SubmitAdInput` unchanged; bot code unaffected |
| DTO validation rejects edge-case inputs previously accepted | Functional: edge-case POSTs that silently "worked" now error | Default to permissive validators that model existing behavior (fallbacks preserved, not rejected) |

### Affected tests to run

- `$dc run --rm -e PYTEST_OPTS="-k test_edit" test`
- `$dc run --rm -e PYTEST_OPTS="-k test_submit" test` (ensure `submit_ad`/`SubmitAdInput` unchanged)
- `uv run ruff check src/backend/apps/ads/views/edit.py src/backend/apps/ads/services/submission.py`
- `uv run basedpyright src/backend/apps/ads/views/edit.py src/backend/apps/ads/services/submission.py`

### Acceptance criteria

- `AdEditInput` Pydantic DTO exists in `apps/ads/services/submission.py` (sibling
  to `SubmitAdInput`, NOT a modification of it)
- `ad_edit` POST validates via `AdEditInput.model_validate(...)` before ANY
  `ad.save(update_fields=...)` call
- Currency-fallback-on-invalid is explicitly modeled: invalid/blank
  `price_currency` → `AdEditInput.price_currency` is `None` → view preserves
  `ad.currency` (current behavior encoded in the DTO, not a silent `except: pass`)
- No-change-vs-clear semantics are explicitly modeled: `title=None` /
  `description=None` (field not in POST) → skip field in `update_fields`;
  documented that blank-string overwrite is preserved (gap tracked as TODO,
  not changed)
- Invalid `price_amount` → `Decimal("0")` (Free), modeled via
  `field_validator` (not silent `except Exception`)
- All 3 unvalidated `ad.save()` branches now occur after DTO validation
- `SubmitAdInput` + reactivation branch unchanged (bot code unaffected)
- `test_edit.py` passes (behavior preserved; if contract updated, the
  specific changed assertions are documented)
- `ruff check` + `basedpyright` clean on `edit.py` + `submission.py`

### Sequencing within block

1. Read `edit.py` `ad_edit` POST handler in full (all 3 branches + reactivation)
2. Read `test_edit.py` — map every assertion to a DTO semantic (identify
   which assertions encode the currency-fallback / blank-overwrite / price-0
   edge behaviors)
3. Read `SubmitAdInput` in `submission.py` (to mirror its Pydantic style)
4. Design `AdEditInput` DTO with `field_validator`s for:
   `price_currency` (invalid → `None`), `price_amount` (invalid →
   `Decimal("0")`), `title`/`description` (preserve current blank-overwrite
   behavior, document gap as TODO)
5. Implement `AdEditInput` in `submission.py`
6. Refactor `ad_edit` POST: validate → handle errors → apply to `ad.save`
7. Run `test_edit.py`
8. Run `test_submit.py` (regression guard for `SubmitAdInput`)
9. Run `ruff check` + `basedpyright`

### Agents

- **Implementor** (primary) — DTO design + implementation, edit.py refactor
- **Validator** — verify `test_edit.py` assertions are mapped to DTO semantics;
  confirm `SubmitAdInput` is unchanged; review currency-fallback modeling;
  run edit + submit test suites

---

## 7. Post-Implementation Regression Gate

After all blocks complete:

```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test
# Also verify the specific affected test groups:
$dc run --rm -e PYTEST_OPTS="-k test_i18n_completeness" test
$dc run --rm -e PYTEST_OPTS="-k test_ad_create or -k test_edit or -k test_listings or -k test_multi_lang or -k test_contact or -k test_login" test
uv run ruff check src/backend src/telegram_bot
```

---

## 8. File Manifest

### Files to be created

| File | Block | Purpose |
|---|---|---|
| `src/telegram_bot/schemas/callbacks.py` | C | `BotCallbackPrefix` StrEnum (QLT-002) |
| `src/telegram_bot/services/ad_data.py` | C | Extracted 15 ORM helpers + 4 keyboard builders + media/translation helpers (QLT-001, 002, 007) |
| `src/telegram_bot/middlewares/language.py` | B | `LanguageMiddleware` for FQ-001 per-user locale activation |
| `src/backend/apps/ads/services/listings_query.py` | D | `ListingsQuery` service + `ListingsQueryParams` DTO (QLT-003) |

### Files to be modified

| File | Block | Change |
|---|---|---|
| `pyproject.toml` | A | Add `"G"` to `[tool.ruff.lint] select` |
| `apps/ads/migrations/0005_...py` | A | `ruff --fix` resolves I001 import sort |
| `apps/ads/migrations/0006_...py` | A | `ruff --fix` resolves I001 import sort |
| `apps/ads/views/edit.py` | A (2 G004), E (DTO) | G004 canonicalize; route POST through `AdEditInput` |
| `apps/users/views/consent.py` | A (8 G004), B (Russian msgids→English) | G004 canonicalize; fix Russian msgids |
| `apps/moderation/services/moderation_log.py` | A | 6 G004 → `%s` |
| `apps/media/services/filesystem.py` | A | 5 G004 → `%s` |
| `apps/users/services/account_state.py` | A | 5 G004 → `%s` |
| `apps/users/services/deletion.py` | A | 5 G004 → `%s` |
| `apps/moderation/admin_actions.py` | A | 4 G004 → `%s` |
| `apps/moderation/views/review.py` | A | 3 G004 → `%s` |
| `apps/ads/views/delete.py` | A | 2 G004 → `%s` |
| `telegram_bot/middlewares/__init__.py` | B | Export `LanguageMiddleware` |
| `telegram_bot/main.py` | B | Register `LanguageMiddleware` on `dp.update.middleware` |
| `telegram_bot/tests/conftest.py` | B | Register `LanguageMiddleware` in `dp` fixture |
| `telegram_bot/handlers/alerts.py` | B (wrap + Cyrillic fix), A (2 G004), C (extracted) | Add `_` import; wrap strings; fix Cyrillic comment |
| `telegram_bot/handlers/ad_create.py` | C (extract helpers + builders), B (wrap), A (2 G004), QLT-002 (tokens), QLT-007 (generics) | Remove extracted functions; use `BotCallbackPrefix`; parameterize generics |
| `telegram_bot/handlers/login.py` | C (QLT-002: contact_us import) | Import `CONTACT_US_CALLBACK` from `contact.py` |
| `telegram_bot/handlers/contact.py` | B (Russian msgids→English) | Fix 5 Russian-as-msgid `_()` calls |
| `apps/ads/services/submission.py` | E | Add `AdEditInput` Pydantic DTO |
| `apps/ads/views/listings.py` | D | Thin adapter using `ListingsQuery` |
| `apps/search/views/search.py` | D | Use shared `ListingsQuery` |
| `apps/ads/tests/test_i18n_completeness.py` | B | Extend gate to bot handler `.py` files |
| `apps/ads/tests/test_edit.py` | E | Verify/assert updated currency-fallback + DTO behavior |
| `apps/ads/tests/test_listings.py` | D | Verify queryset semantics (may need param updates) |
| `src/backend/apps/media/tests/test_save_photo_exif.py` | C | Update `save_photo` import path |
| `src/backend/apps/media/tests/test_thumbnail_integration.py` | C | Update `save_photo` import path |
| `src/telegram_bot/tests/test_ad_create.py` | C | Update import + patch paths (~6 sites) |
| `src/telegram_bot/tests/test_ad_create_condition.py` | C | Update `build_feature_keyboard` import path |
| `src/telegram_bot/tests/test_multi_lang_translation.py` | B, C | Extend for locale activation; update `translate_all_languages` import path |
| `src/telegram_bot/tests/test_price_payload.py` | C | Update if `AdCreateForm` path changes |
| `src/telegram_bot/tests/test_create_draft_ad.py` | C | Update `create_draft_ad` + `delete_draft` import paths |
| `src/telegram_bot/tests/test_site_name_greeting.py` | C | Update `create_draft_ad` import + patch path; verify `get_site_name_async` status |

### Files already resolved (no action)

| File | Finding | Resolution |
|---|---|---|
| `telegram_bot/services/__pycache__/` | QLT-001 (orphan .pyc) | Already absent — confirmed by code-context §QLT-001 discrepancy #5 |
| `core/enums.py` `LanguageLocale` | QLT-002 | `.values()` method confirmed to exist — used as-is, no change needed |
| `contact.py` `CONTACT_US_CALLBACK` | QLT-002 | Already defined as `Final[str]` — no change, only import added in `login.py` |
| `apps/search/services/alert_query.py` | QLT-003 | Thin-service precedent confirmed — referenced as pattern, not modified |

---

## 9. Agent Requirements Summary

| Block | Primary Agent | Supporting Agents | Review Gate |
|---|---|---|---|
| A (QLT-006) | Implementor | Validator | `ruff check` clean (0 errors); G004 = 0; I001 migrations fixed |
| B (FQ-001 + QLT-005) | Implementor | Validator | Middleware in `main.py` + `conftest.py`; i18n gate extended; `ru`/`bs` msgstr non-empty |
| C (QLT-001 + 002 + 007) | Implementor | Validator | All 9 test files collect + pass; no raw callback tokens in `ad_create.py`; bot→backend import direction verified |
| D (QLT-003) | Implementor | Validator | `listings()` + `search()` tests pass; queryset semantics identical |
| E (QLT-004) | Implementor | Validator | `test_edit.py` passes (behavior preserved); `SubmitAdInput` unchanged |

### Key decision points

1. **Block C:** Re-export vs. update-all-test-paths: this plan mandates
   **update-all-test-paths** (no re-exports). The Implementor must exhaustively
   grep for `from telegram_bot.handlers.ad_create import` and
   `mock.patch("telegram_bot.handlers.ad_create.` to catch every site.
2. **Block C:** `build_currency_keyboard` (outside helper section at line 526) —
   must be explicitly co-relocated with the other 3 builders.
3. **Block C:** `get_site_name_async` — verify extraction status before patching
   its test sites (validation report flags it as a false-positive concern).
4. **Block B:** `_()` wrapping of keyboard builder labels is deferred to C
   (per QLT-002→QLT-005 dependency) — B wraps only direct `answer()`/`text=`
   literals, not builder labels.
5. **Block E:** Blank title/description overwrite — **preserve current
   behavior** (documented gap), do NOT close the validation gap in this pass.

---

## 10. Working-Tree Status Reconciliation (2026-09-17)

> **Source of truth:** `.ai/audit/99-validation/10-code-context.md` (live,
> 2026-09-17). HEAD = `7ec80c7 chore plans`. The refactor is **implemented but
> not committed** (except Block A). This section supersedes §0–§9's
> forward-looking sequencing: Blocks B–E are already in the working tree, so the
> remaining work is two residual fixes → one atomic commit, not a sequential
> block rollout.

### 10.1 Current working-tree state

`git status` (READ FIRST — gates commit risk):

- **Block A — COMMITTED** (reachable from HEAD `7ec80c7`). The G004/I001 lint-gate
  fix lives in parent commit `de0df4f` (`fix(quality): enable ruff G004 rule…`,
  immediate parent of HEAD). `ruff check src/backend src/telegram_bot` → clean.
- **Blocks B–E — IMPLEMENTED-UNCOMMITTED.** All target files are ` M` (modified)
  or `??` (untracked); no Block B–E change is in any commit.
  - 4 new (untracked): `src/telegram_bot/services/ad_data.py` (533),
    `src/telegram_bot/schemas/callbacks.py` (29),
    `src/telegram_bot/middlewares/language.py` (80),
    `src/backend/apps/ads/services/listings_query.py` (263).
  - ~20 modified files spanning B (locale `.po`×3, `alerts.py`, `ad_copy.py`,
    `contact.py`, `login.py`, `main.py`, `middlewares/__init__.py`,
    `tests/conftest.py`, bot `test_*.py`, `test_i18n_completeness.py`) and
    C/D/E (`ad_create.py` 1393→926, `submission.py`, `edit.py`, `listings.py`,
    `search.py`, + test path updates).
- **Runtime gate (fast gate):** `1576 passed, 0 failed, 0 errors (104.74s)`
  against `mko-bazuna-test-db-1` (postgres:18-alpine). `testpaths`
  (`pyproject.toml:163`) = `["src/backend", "src/telegram_bot"]` — both trees
  exercised; the B–E refactor is green.
- **Typecheck gate:** `basedpyright` NOT executed (QLT-007 open). ⏳

#### Per-block status

| Block | Finding(s) | Live status | Evidence |
|---|---|---|---|
| A | QLT-006 | **committed** (HEAD `7ec80c7`; fix `de0df4f`) | `"G"` in `pyproject.toml select`; ruff clean; I001 migrations fixed |
| B | FQ-001, QLT-005 | **implemented-uncommitted** | `middlewares/language.py`; `main.py` + `conftest.py` register it before `AccountStateMiddleware`; ru/bs 0 empty non-header `msgstr` (394 msgids); bot strings `_()`-wrapped |
| C | QLT-001, QLT-002 | **implemented-uncommitted** | `ad_data.py` (533) holds 15 helpers + 4 builders + media/translation; `callbacks.py` `BotCallbackPrefix`; `ad_create.py` 1393→926; 0 raw callback tokens |
| C | QLT-007 (typecheck) | **partial / not-verified** | 4 `# pyright: ignore` suppressions remain; basedpyright not run |
| D | QLT-003 | **implemented-uncommitted** | `ListingsQuery` (263) + `ListingsQueryParams` DTO; `listings()`/`search()` thin |
| E | QLT-004 | **implemented-uncommitted** | `AdEditInput` Pydantic DTO sibling to `SubmitAdInput` in `submission.py`; `edit.py` POST validates via DTO before `save()` |

### 10.2 Residual fixes (must clear before commit is safe)

Per the code-context §Discrepancies & gaps, two items remain before the working
tree can be committed as the code-quality-fixes commit:

1. **QLT-007 — run `basedpyright` + remediate suppressions.** Not covered by ruff.
   Remaining `# pyright: ignore` directives in live source:
   - `src/backend/apps/ads/views/edit.py:124, 285, 322` →
     `# pyright: ignore[reportGeneralTypeIssues]` on `with transaction.atomic():`
     (root cause: `django-stubs` not installed → `Atomic.__enter__/__exit__`
     untyped).
   - `src/telegram_bot/tests/conftest.py:83` →
     `# pyright: ignore[reportAbstractUsage]` on `AccountStateMiddleware()`.
   - **Remediation:** install `django-stubs` and/or annotate the `Atomic`
     context manager to clear the 3 `transaction.atomic()` suppressions;
     restructure the conftest registration to drop the `reportAbstractUsage`
     suppression. **Do not** touch `apps/common/models/ad.py` StrEnum fields
     until pyright confirms current state (no ignores there today, but the plan's
     9-bare-annotation target is stale — `ad.py` is unchanged since `7ec80c7`).
   - **Note on path:** code-context §QLT-007 recommendation cites
     `src/telegram_bot/services/language.py` for the typecheck run — that is a
     **path typo**. The actual file is `src/telegram_bot/middlewares/language.py`
     (untracked, confirmed). The corrected 3-file typecheck scope is
     `edit.py` + `ad_data.py` + `middlewares/language.py`; `conftest.py:83` is
     the additional test-only suppression to clear.

2. **QLT-002 gap — `contact.py` sentinel consolidation.** `contact.py:35` declares
   `CONTACT_US_CALLBACK: Final[str] = "contact_us"`, duplicating
   `BotCallbackPrefix.CONTACT_US = "contact_us"` (`schemas/callbacks.py:26`).
   QLT-002's acceptance scopes only `ad_create.py` (which is clean), so this is a
   **consistency** gap, not a regression — but it must be closed before commit:
   route `contact.py` through `BotCallbackPrefix.CONTACT_US` (update
   `CONTACT_US_PATTERN` + `login.py` deep-link too) and re-run
   `test_contact_us.py`.

### 10.3 Dependency verification (inter-block deps satisfied)

Verified from `10-code-context.md` + direct source grep:

- **FQ-001 → QLT-005 (Block B):** ✓. `LanguageMiddleware` registered in
  `main.py` on `dp.update.middleware` before `AccountStateMiddleware`; mirrored in
  `tests/conftest.py:81` before `AccountStateMiddleware` (`conftest.py:83`), with
  comment "Locale middleware must run before AccountStateMiddleware (FQ-001)".
  ru/bs `.po` have 0 empty non-header `msgstr` (394 msgids). Bot strings wrapped
  in `_()`.
- **B→C keyboard label wrapping (QLT-002→QLT-005):** ✓. All 4 keyboard builders
  relocated to `ad_data.py`; currency builder uses
  `text=_("🆓 Free"), callback_data=BotCallbackPrefix.PRICE_FREE`
  (`ad_data.py:455`); features builder uses
  `text=_("✔️ Done"), callback_data=BotCallbackPrefix.FEATURES_DONE`
  (`ad_data.py:529`); all builders consume `BotCallbackPrefix` (25 refs across
  `ad_data.py` + `ad_create.py` + `callbacks.py`). 0 raw callback tokens in
  `ad_create.py`.
- **Import direction (two-process model):** ✓. bot→backend only
  (`ad_data.py`, `ad_create.py`, `language.py` import `apps.*`); no `apps.*`
  module imports `telegram_bot.*`. No cyclic risk.

### 10.4 Commit strategy (NOT a sequential rollout)

Because Blocks B–E are already implemented and green, the work is **two residual
fixes → one atomic commit**, not phased block execution:

1. Fix QLT-007 (run `basedpyright`, clear the 4 `pyright: ignore` suppressions).
2. Fix QLT-002 gap (route `contact.py` through `BotCallbackPrefix.CONTACT_US`;
   re-run `test_contact_us.py`).
3. Re-verify: `ruff check` clean → `basedpyright` clean (3 files + conftest) →
   fast-gate `1576 passed, 0 failed`.
4. **Single atomic commit** of all Block B–E sources + the 2 residual fixes.

#### Commit scoping (staging must be selective — risk if `git add -A` is used)

The working tree contains files **NOT** part of plan 22 that must be excluded:

- **6 DELETED (staged or unstaged) — exclude entirely** (belong to other
  already-completed/superseded plans):
  - `.ai/audit/99-validation/10-failing-tests-root-cause-audit.md` (test-audit doc)
  - `.ai/audit/99-validation/11-failing-tests-solution-decisions.md` (test-audit doc)
  - `.ai/plans/19-pii-consent-middleware-fix.md` (PII consent plan — superseded)
  - `.ai/plans/21-external-api-findings.md` (external-API plan — superseded)
  - `.kilo/plans/phase-06-pii-consent-execution-dag.md` (PII consent exec DAG)
  - `scripts/run-profile.sh` (one-off profiling script)
- **4 NEW untracked — exclude** (`.ai/context/test-audit-code-context.md`,
  `.ai/plans/23-test-quality-audit-execution.md`, and the 7
  `docs/99-agent/test-audit-*-findings.md` / `test-audit-*.md` artifacts are
  standalone test-audit deliverables, not plan-22 scope).
- **Include only:** the 4 plan-22 new files (`ad_data.py`, `callbacks.py`,
  `language.py`, `listings_query.py`) + the plan-22 modified source/test/locale
  files listed in §10.1 + the 2 residual-fix edits. (`.ai/audit/99-validation/10-code-context.md`
  itself is ` M` in the tree — it is audit documentation, not a source artifact;
  leave it out of the source commit or fold in only if the maintainer wants the
  audit doc's own diff captured alongside. It is **not** a prerequisite for
  plan-22 code to compile or tests to pass.)

### 10.5 Verification checklist (pre-commit gate)

| # | Check | Command | Target |
|---|---|---|---|
| 1 | ruff clean | `uv run ruff check src/backend src/telegram_bot` | 0 errors (incl. `G`/`G004` + `I`/`I001`) |
| 2 | basedpyright clean | `uv run basedpyright src/backend/apps/ads/views/edit.py src/telegram_bot/services/ad_data.py src/telegram_bot/middlewares/language.py` | 0 type errors; 4 `pyright: ignore` suppressions (edit.py:124/285/322 + conftest.py:83) remediated |
| 3 | test suite green | docker compose `test` service (fast gate, `PYTEST_SKIP_MARKERS=seed`) | `1576 passed, 0 failed, 0 errors` |

**Post-residual re-run targets:** `-k test_edit`, `-k test_contact_us`,
`-k test_i18n_completeness`, `-k test_ad_create`, `-k test_listings_sort`,
`-k test_search_view`, `-k test_multi_lang_translation`,
`-k test_save_photo` — all green before the atomic commit.

### 10.6 Accuracy notes on `10-code-context.md`

- The "4 legacy `apps/ads/services/*.py` created in `7ec80c7`" claim is a minor
  misstatement: `git ls-tree 7ec80c7 -- src/backend/apps/ads/services/` shows
  `copy_service.py`, `images.py`, `submission.py` (3 files), and these appear in
  much older history (not created by `7ec80c7`). Does not affect the
  **Block-A-committed** conclusion.
- The code-context §QLT-007 recommendation path `services/language.py` is a typo
  for `middlewares/language.py` (corrected above).
- The code-context §Block C "keyboard label wrapping deferred to C" observation is
  confirmed live in `ad_data.py` (labels already `_()`-wrapped at :455, :529).
- The code-context §QLT-007 recommendation omits `conftest.py:83` from its 3-file
  basedpyright scope; that suppression is test-only but in-scope for QLT-007
  remediation — tracked explicitly in §10.2 item 1.
