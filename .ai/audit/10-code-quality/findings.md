---
phase: "10"
phase_name: "Code Quality"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""
mode: "problems-only"
id_prefix: "CQ"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/10-audit-code-quality.md#severity-taxonomy"
---

# Audit Findings — Code Quality

> **ID-prefix deviation (deliberate).** The phase file §10 mandates `QLT-`, but
> `QLT-###` markers are already hard-coded as in-source provenance tags in
> shipped code (e.g. `ads/views/edit.py:124` "QLT-004",
> `apps/media/schemas.py:7` "10-QLT-008", `submit.py:4` "10-QLT-003 B16").
> Reusing the prefix would make new findings indistinguishable from those
> historical tags. Per the task brief, all findings below use **`CQ-`**.

## Executive Summary

Nineteen maintainability defects were found. None is a security vulnerability and none
loses data under normal UI use, but three are structural: the seller ad-edit screen and
several Telegram bot handlers contain the business and database rules they are supposed
to call, and one required-choice list (moderator reject reasons) is defined in code yet
never enforced, so a moderator's dropdown is a free-text field in disguise. The remaining
sixteen are consistency defects — duplicated helpers, fixed values written as raw text in
screens and templates, hand-copied boilerplate — that raise the cost and the risk of
every future change. No production file was modified.

## Scope & Methodology

**Scope:** All production Python under `src/backend` and `src/telegram_bot`, all Django
templates under `src/backend/templates`, and the shared settings/enum modules. Test files
and migrations were read for context but not audited (Phase 11 owns test quality; migration
correctness is Phase 03). Excluded: performance, security, i18n completeness, and any
defect already filed by phases 01–09.

### Runtime Verification

Static analysis only — this phase has no runtime component. The `mko-bazuna-dev` stack is
crash-looping (CFG-006) and was not used. `uv run pytest` was not run (Phase 11's scope).

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | No `print()` in production code, including entry points | `Grep` for `^\s*print\(` over `src/**/*.py` excluding tests/migrations | PASS — 4 hits, all in `apps/core/tests/test_migrations.py:61,62,90,91` |
| R-02 | Lint clean across repo | `uv run ruff check .` | FAIL-but-not-mine — 2 `UP031` in `.ai/audit/03-db-concurrency/verify_db.py`, a phase-03 probe script; 0 errors in `src/` |
| R-03 | Type-checker clean in CI scope | `uv run basedpyright src/backend` | FAIL — 12 errors, all in test files (`test_edit_views_locking.py`, `test_admin_actions.py`); 0 in production |
| R-04 | Type-checker clean in the bot process (excluded from CI) | `uv run basedpyright src/telegram_bot` | PASS — 2 errors, both in `tests/test_ad_create.py`; 0 in production bot code |
| R-05 | No raw ad-status string literals in presentation code | `Select-String 'on_moderation'` over `*.py` + `*.html` | FAIL — 8 literals in 3 templates, 2 in `moderation/views/review.py`, 1 in `analytics/moderation_dashboard.html` |
| R-06 | Every schema change is versioned by a migration | field-by-field read of `ads/models.py` vs `ads/migrations/0001_initial.py` | PASS — search vectors, GIN indexes, key-format CHECKs and trigger DDL all present in `0001_initial.py` (`:211-235, :537-555, :706-720`) |
| R-07 | No code-path DB mutation outside migrations | `Select-String 'cursor.execute\|RunSQL\|CREATE TABLE\|ALTER TABLE'` | PASS — only `setup_search_triggers` (idempotent re-install of migration DDL) and read-only `SELECT pg_advisory_lock` / `SELECT 1` |
| R-08 | Contact gating + analytics live in ONE shared place, not copied per process | traced `get_seller_for_contact` / `record_contact_initiated` from both processes | PASS — `apps/core/services/contact.py:27` `_check_seller_contactable` is the single predicate; bot delegates via `telegram_bot/handlers/contact.py:269-283` |
| R-09 | Pydantic validates bot input AND web POST before any ORM write | enumerated every `BaseModel` (5) and every `@require_POST` / inline POST view (14) | FAIL — `search/views/save_search.py`, `cabinet/views/saved_searches.py`, `search/views/preferred_city.py` write POST straight to the ORM |
| R-10 | Module/function size within target | AST pass over 734 production functions | FAIL — 13 functions >100 lines, 54 >60; largest is `ads/views/edit.py:73 ad_edit` at 193 |
| R-11 | No unreferenced production definitions | AST-defined names vs a corpus of all `.py`/`.md`/`.html` in `src/`, `docs/`, `.ai/` | FAIL — 6 confirmed-unreferenced symbols (see CQ-016) after removing 27 framework-discovered false positives |
| R-12 | No non-English text in comments, logs, docstrings or errors | `Select-String '[\u0400-\u04FF\u0107\u010D...]'` over production `.py` excluding seed/locale | PASS — 15 hits, all legitimate (regex character classes, user-facing Telegram menu strings, example payloads) |
| R-13 | No `TODO`/`FIXME`/`HACK`/`XXX` in production code | `Select-String` over `.py`/`.html`/`.js`/`.css` | PASS — 3 hits, all test fixture strings |
| R-14 | No deferred/circular-import workarounds hiding layering | AST pass for `Import`/`ImportFrom` inside function bodies | FAIL — 81 function-local imports (see CQ-010) |

**Tools used:** `ruff` 0.14 (check only), `basedpyright`, `Grep`/`Select-String`, custom
AST probes under `.ai/tmp/` (deleted), `uv run python` (read-only AST analysis).

**Assumptions:** `config.settings.test` was never imported (no DB access was performed);
the working tree at `9e96b84` with 8 untracked `.ai/` directories is the audit subject;
Django app-registry auto-discovery (`AppConfig`, `ModelAdmin`, `add_arguments`, `ready()`)
was treated as a legitimate "reference" when classifying dead code.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| CQ-001 | `ad_edit` view embeds the ad-edit FSM, ORM writes and a duplicated DTO block | HIGH | Open | Separation of concerns |
| CQ-002 | Telegram handler modules own the data-access layer instead of `telegram_bot/services/` | HIGH | Open | Separation of concerns |
| CQ-003 | `CategoryRejectReason` StrEnum is exported and documented but never enforced | HIGH | Open | Constants / StrEnum |
| CQ-004 | Three write views reach the ORM with no Pydantic boundary; the int parser is copy-pasted | MEDIUM | Open | Schema/validation boundary |
| CQ-005 | Presentation layer bypasses `AdStatus` with 11 raw status literals | MEDIUM | Open | Constants / StrEnum |
| CQ-006 | `LanguageLocale` exists but raw `"ru"/"bs"/"en"` are fixed values in 9 production sites | MEDIUM | Open | Constants / StrEnum |
| CQ-007 | `apps/core/utils/cache.py` hand-copies 15 get/set/invalidate functions | MEDIUM | Open | DRY / module size |
| CQ-008 | `submit_ad` mixes six responsibilities in 124 lines | MEDIUM | Open | Module size / SRP |
| CQ-009 | `AdEditInput` accepts blank title/description, so a partial POST erases ad content | MEDIUM | Open | Schema/validation boundary |
| CQ-010 | 81 deferred function-local imports; moderation's business layer sits at the app root | MEDIUM | Open | Separation of concerns |
| CQ-011 | Two difflib category-suggestion implementations with different cutoffs (0.6 vs 0.8) | MEDIUM | Open | DRY |
| CQ-012 | Untyped service boundaries: bare `dict` into `update_or_create`, unannotated resolver params | MEDIUM | Open | Type safety |
| CQ-013 | Consent cookie names are constants in one module and raw literals in two others | MEDIUM | Open | DRY / constants |
| CQ-014 | `/alerts` promises a numeric toggle that no handler implements | MEDIUM | Open | Dead code |
| CQ-015 | `listings.py` and `search.py` duplicate the 11-field `ListingsQueryParams` build and context assembly | MEDIUM | Open | DRY |
| CQ-016 | Dead code: deprecated shims, 2 unreferenced resolver methods, 3 prefix aliases, empty `apps/api` | LOW | Open | Dead code |
| CQ-017 | Packaging/convention drift: missing `__init__.py`, private name in `__all__`, unordered enum members | LOW | Open | Naming / conventions |
| CQ-018 | `@require_POST` vs inline `request.method` checks; 5 hardcoded `/admin/` URLs | LOW | Open | Naming / conventions |
| CQ-019 | 1,474 comment-only lines in production Python, many restating the next statement | LOW | Open | Conventions |

## Distribution

**Severity counts**

| Band (per `10-audit-code-quality.md` §8) | Count |
|---|---|
| HIGH | 3 |
| MEDIUM | 12 |
| LOW | 4 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 19 |

## Findings by Severity

### HIGH

#### CQ-001: [HIGH] — `ad_edit` view embeds the ad-edit FSM, ORM writes and a duplicated DTO block

| Field | Value |
|---|---|
| **ID** | CQ-001 |
| **Title** | `ad_edit` view embeds the ad-edit FSM, ORM writes and a duplicated DTO block |
| **Severity** | HIGH |
| **Category** | Separation of concerns / ISO 25010 Modularity |
| **File(s)** | `src/backend/apps/ads/views/edit.py:30` (`_apply_price_change`), `src/backend/apps/ads/views/edit.py:73` (`ad_edit`, 193 lines), `src/backend/apps/ads/views/edit.py:160-173`, `src/backend/apps/ads/views/edit.py:203-216`, `src/backend/apps/ads/views/edit.py:248-265`, `src/backend/apps/ads/views/edit.py:341` |
| **Status** | Open |
| **Reproduction Steps** | 1. `GET /ads/<id>/edit/` for a seller-owned ad in any status. 2. `POST` the form to `/ads/<id>/edit/`. 3. Observe that one 193-line view decides the FSM branch, coerces the currency, builds the `SubmitAdInput`, and — in two of three branches — writes the model directly with `ad.save(update_fields=[...])`. |
| **Problem** | `ad_edit` is the single largest function in the codebase and performs six distinct jobs inside one request: ownership authorization (`:94-101`), `select_for_update` row locking (`:117`), the web-specific currency-fallback business rule (`:136-141`), Pydantic DTO construction (`:130-132`), four-way `AdStatus` FSM branching (`:146`, `:190`, `:233`, `:248`), and two hand-written ORM write paths that bypass `submit_ad` entirely (`:235-243`, `:250-262`). The two `SubmitAdInput(...)` constructions at `:160-173` and `:203-216` are byte-identical 14-line blocks. `_apply_price_change` (`:30-55`) is a business rule (the BR-03 `price_normalized_eur` seam) living in a view module, and is imported by a test (`apps/ads/tests/test_edit.py:30`) as if it were a service. |
| **Impact** | A seller ad becomes PUBLISHED-with-stale-price, or PUBLISHED-with-emptied-text, or a moderated copy of a stale row, depending on a branch that only exists inside a view function. The FSM matrix (`Ad.transition_to` / `ALLOWED_TRANSITIONS`) is now enforced in one place for the bot path and in three ad-hoc branches for the web path, so a rule change to zone C2 must be made and re-verified in four locations. Duplicated blocks mean a future DTO field addition silently lands in one branch and not the other. The reviewer cannot test the branch logic without a full HTTP request. |
| **Root Cause** | The ad-edit orchestration was never extracted into `apps/ads/services/`; the view absorbed it as features were added, and each new status rule appended another `elif` rather than delegating. `apps/ads/services/submission.py:submit_ad` already exists as the shared orchestrator and covers two of the three branches — the third (`else`, `:248-265`) was left as raw ORM writes. |
| **Recommendation** | Extract an `edit_ad(AdEditCommand) -> EditOutcome` service into `apps/ads/services/edit.py` that owns: DTO validation, currency coercion, the status→strategy mapping, and every write. Reduce `ad_edit` to auth-check → call service → render/redirect. Move `_apply_price_change` into `apps/currencies/services/price_normalizer.py` next to `normalize_price_to_eur` so the price rule has one home, and hoist the duplicated `SubmitAdInput` construction into one local `command` variable used by both branches. |
| **Effort** | M |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-008 (`submit_ad` is the other half of this split), CQ-009 (the DTO's blank-title gap), ENT-005 (upstream consent.py service-extraction, separate file) |

**Evidence — `src/backend/apps/ads/views/edit.py:160-173` and `:203-216`** *(supports: "the two `SubmitAdInput(...)` constructions are byte-identical 14-line blocks")*:
```python
# :160-173 (reactivation branch)          # :203-216 (PUBLISHED text-edit branch)
passed, errors = submit_ad(               passed, errors = submit_ad(
    SubmitAdInput(                            SubmitAdInput(
        ad_id=ad_id,                             ad_id=ad_id,
        title_ru=dto.title,                      title_ru=dto.title,
        desc_ru=dto.description,                 desc_ru=dto.description,
        category_id=ad.category_id,              category_id=ad.category_id,
        city_id=ad.city_id,                      city_id=ad.city_id,
        price_amount=dto.price_amount,           price_amount=dto.price_amount,
        price_currency=price_currency_value,     price_currency=price_currency_value,
        photos=[],                               photos=[],
        user_id=ad.user_id,                      user_id=ad.user_id,
        listing_condition_id=ad.listing_condition_id,
    )                                         )
)
```

**Evidence — `src/backend/apps/ads/views/edit.py:248-265`** *(supports: "in two of three branches the view writes the model directly, bypassing `submit_ad`")*:
```python
        else:
            # Other statuses (ON_MODERATION, ON_MODERATION_FAILED): direct save
            ad.title = dto.title
            ad.description = dto.description
            ad = _apply_price_change(ad, dto.price_amount, price_currency_value)
            ad.save(
                update_fields=[
                    "title", "description", "price_amount",
                    "price_currency", "price_normalized_eur", "updated_at",
                ]
            )
            logger.info("Ad %s edited in status %s", ad_id, ad.status)
            return redirect("ads:dashboard")
```

**Evidence — AST function-size measurement** *(supports: "`ad_edit` is the largest function in the codebase")*:
```text
 193  src\backend\apps\ads\views\edit.py:73  ad_edit
 184  src\backend\apps\search\views\search.py:46  search
 166  src\backend\apps\seed\services\seed_service.py:57  run
 140  src\backend\apps\categories\catalog\builder.py:322  _load_bindings
 138  src\backend\apps\ads\models.py:363  transition_to
 124  src\backend\apps\ads\services\submission.py:122  submit_ad
---
TOTAL FUNCS: 734 | FUNCS >60 lines: 54 | FUNCS >100 lines: 13
```

---

#### CQ-002: [HIGH] — Telegram handler modules own the data-access layer instead of `telegram_bot/services/`

| Field | Value |
|---|---|
| **ID** | CQ-002 |
| **Title** | Telegram handler modules own the data-access layer instead of `telegram_bot/services/` |
| **Severity** | HIGH |
| **Category** | Separation of concerns / ISO 25010 Modularity |
| **File(s)** | `src/telegram_bot/handlers/login.py:154` (`_claim_login_token`), `src/telegram_bot/handlers/login.py:190` (`handle_login_orm`), `src/telegram_bot/handlers/alerts.py:92` (`get_user_saved_searches`), `src/telegram_bot/handlers/alerts.py:237` (`_resolve_owned`), `src/telegram_bot/handlers/contact.py:242` (`handle_contact_orm`), `src/telegram_bot/handlers/support.py:159` |
| **Status** | Open |
| **Reproduction Steps** | 1. `grep -n "cursor.execute\|objects\." src/telegram_bot/handlers/*.py` → 4 handler modules contain raw SQL / ORM calls. 2. Compare with `src/telegram_bot/services/ad_data/orm.py`, which wraps the same work in `sync_to_async` for the ad flow. 3. Observe that login, alerts, contact and support have no equivalent service module. |
| **Problem** | `telegram_bot/services/` exists and holds exactly one data-access module (`ad_data/orm.py`, 178 lines). Every other bot flow puts its database code directly in `handlers/`: `login.py:169-187` issues a hand-written `UPDATE login_tokens … RETURNING` and reconstructs the model from `cursor.description`; `login.py:209-262` wraps `User.objects.get_or_create` + `record_event` in an inline `@sync_to_async` closure; `alerts.py:244-263` does `SavedSearch.objects.select_for_update().get(...)` plus `save()` inside the handler module; `alerts.py:92-99` is a bare `@sync_to_async` ORM query. `contact.py:269-271` and `support.py:159-160` work around the missing service by importing `apps.*` *inside* the handler function. |
| **Impact** | The web process cannot reuse any bot business rule, so a rule that both sides need must be written twice. The two-phase login claim — the most security-sensitive sequence in the bot — is only reachable through an HTTP-independent code path that no unit test can call without an aiogram message fixture, and its raw SQL has no owner outside the handler package. Inconsistent `sync_to_async` wrapping (some bot DB access is in `services/`, some in `handlers/`) means the "never touch the ORM on the event loop" rule is enforced by reviewer memory rather than by module structure. |
| **Root Cause** | `ad_data` was extracted into a service package during the ad-flow work; the other four flows were written afterwards directly in their handler modules. `telegram_bot/services/` has no `__init__.py` contract, no module-per-domain layout, and no test asserting that `handlers/` contains no ORM calls. |
| **Recommendation** | Create `telegram_bot/services/login.py`, `services/alerts.py`, `services/contact.py`, `services/support.py` and move each `*_orm` / `sync_to_async` block into them, mirroring `ad_data/orm.py`. Keep handlers to message parsing, keyboard construction and i18n. Add one AST-based architecture test asserting `handlers/` contains no `objects.` / `cursor.execute` call — cheap, and it stops the pattern returning. |
| **Effort** | M |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-010 (the deferred imports are the workaround for this), DB-001/DB-002 (mechanism owners in the same modules) |

**Evidence — `src/telegram_bot/handlers/login.py:169-187`** *(supports: "the login claim is raw SQL inside a handler module")*:
```python
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE login_tokens
               SET telegram_id = %s
             WHERE token_hash = %s
               AND telegram_id IS NULL
               AND consumed_at IS NULL
               AND expires_at > %s
            RETURNING id, token_hash, telegram_id, created_at, expires_at, consumed_at
            """,
            [telegram_id, token_hash, now],
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]

    return LoginToken(**dict(zip(columns, row, strict=True)))
```

**Evidence — bot package layout** *(supports: "`telegram_bot/services/` holds only `ad_data` + 3 helpers; login/alerts/contact/support have no service module")*:
```text
src\telegram_bot\services\ad_data\__init__.py
src\telegram_bot\services\ad_data\feature_helpers.py
src\telegram_bot\services\ad_data\keyboards.py
src\telegram_bot\services\ad_data\media.py
src\telegram_bot\services\ad_data\orm.py          <-- only ORM module
src\telegram_bot\services\ad_data\translation.py
src\telegram_bot\services\rate_limit.py
src\telegram_bot\services\support_delivery_email.py
src\telegram_bot\services\support_delivery_telegram.py
--- handler modules containing ORM / raw SQL:
src\telegram_bot\handlers\login.py     (cursor.execute x1, objects. x3)
src\telegram_bot\handlers\alerts.py    (objects. x4, save x1)
src\telegram_bot\handlers\contact.py   (delegates, but imports apps.* inline)
src\telegram_bot\handlers\support.py   (objects. x3, create x1)
```

---

#### CQ-003: [HIGH] — `CategoryRejectReason` StrEnum is exported and documented but never enforced

| Field | Value |
|---|---|
| **ID** | CQ-003 |
| **Title** | `CategoryRejectReason` StrEnum is exported and documented but never enforced |
| **Severity** | HIGH |
| **Category** | Constants / StrEnum (project rule 10) |
| **File(s)** | `src/backend/apps/core/enums.py:167-182`, `src/backend/apps/core/enums.py:323`, `src/backend/apps/core/__init__.py:6`, `src/backend/apps/moderation/views/review.py:108-114`, `src/backend/templates/admin/moderation/review.html:145` |
| **Status** | Open |
| **Reproduction Steps** | 1. `Select-String -Path src -Pattern CategoryRejectReason -Recurse` → 4 hits: the class body, the `__all__` entry, the `apps.core` re-export, and a docstring. Zero call sites. 2. Open `review.html:145` — a free `<select name="reason_category">`. 3. `review.py:108` reads it as a raw string with no enum coercion. 4. Confirm `ModeratorActionLog.reason` is `models.TextField` (`moderation/models.py:119-120`), so any string is accepted. |
| **Problem** | `CategoryRejectReason` is an 8-member `StrEnum` documented in `docs/02-database/db-enums.md`, re-exported from `apps.core.__init__`, and listed in `apps/core/enums.py.__all__` — yet **no production code references it**. The moderator reject flow reads `request.POST["reason_category"]` as an unvalidated string (`review.py:108`), concatenates it with free text (`review.py:112-114`), and writes it to `ModeratorActionLog.reason`. A `POST` with `reason_category=whatever-i-want` is accepted. The `<select>` in the template is a client-side convenience with no server-side counterpart. |
| **Impact** | The documented "UI/admin vocabulary" is not a constraint. Rejection reasons become free text, so any future report grouping, dashboard aggregation, or translation of the reject vocabulary silently returns partial or null results. It is the exact drift case the phase rubric names: a fixed value modelled as a `StrEnum` in one place and a raw string everywhere it is actually used. |
| **Root Cause** | The enum was modelled (rule 10) but never wired: `ModeratorActionLog.reason` is deliberately `TEXT` (per the enum's own docstring, "NOT stored as a database column"), so no schema constraint forces the write path through the enum, and no Pydantic DTO was added at the `reject_ad` boundary. |
| **Recommendation** | Validate at the `reject_ad` boundary: coerce `reason_category` through `CategoryRejectReason` (returning 400 on an unknown value) and store either the enum `.value` or an empty string. Add a `RejectAdInput(BaseInputModel)` in `apps/moderation/schemas.py` alongside `BulkModerationRequest` so the coercion and the `extra="forbid"` behaviour live in one place. If free-text reasons are a deliberate product decision, then the enum should be deleted rather than left exported and unused. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-004 (same boundary, different view family), CQ-005 (same class of enum bypass in templates) |

**Evidence — `Select-String CategoryRejectReason reason_category`** *(supports: "the enum has zero production call sites; the view reads a raw string")*:
```text
src\backend\apps\core\__init__.py:6:    CategoryRejectReason,          <-- re-export
src\backend\apps\core\enums.py:167: class CategoryRejectReason(StrEnum):
src\backend\apps\core\enums.py:323: "CategoryRejectReason",          <-- __all__
src\backend\apps\moderation\views\review.py:108: reason_category = request.POST.get("reason_category", "") or ""
src\backend\templates\admin\moderation\review.html:145: <select name="reason_category"
--- production call sites of the enum: 0
```

**Evidence — `src/backend/apps/moderation/views/review.py:107-116`** *(supports: "an arbitrary POST string is concatenated and persisted")*:
```python
        # Build reason from category + text
        reason_category = request.POST.get("reason_category", "") or ""
        reason_text = (request.POST.get("reason_text") or "").strip()

        # Combine for internal record
        reason = f"{reason_category}"
        if reason_text:
            reason = f"{reason_category}: {reason_text}"

        do_reject(ad, request.user.id, reason)
```

### MEDIUM

#### CQ-004: [MEDIUM] — Three write views reach the ORM with no Pydantic boundary; the int parser is copy-pasted

| Field | Value |
|---|---|
| **ID** | CQ-004 |
| **Title** | Three write views reach the ORM with no Pydantic boundary; the int parser is copy-pasted |
| **Severity** | MEDIUM |
| **Category** | Schema/validation boundary |
| **File(s)** | `src/backend/apps/search/views/save_search.py:37-57`, `src/backend/apps/cabinet/views/saved_searches.py:113-140`, `src/backend/apps/cabinet/views/saved_searches.py:44,63,93`, `src/backend/apps/search/views/preferred_city.py:42-99`, `src/backend/apps/search/models.py:97,102` |
| **Status** | Open |
| **Reproduction Steps** | 1. `POST /save-search/` with body `query=x&min_price=-1`. 2. `_int_or_none("min_price")` returns `-1`; `SavedSearch.min_price` is a `PositiveIntegerField`. 3. Django's PostgreSQL backend adds `CHECK (min_price >= 0)` → `IntegrityError` → HTTP 500. The same POST against the ad-edit view returns a rendered error page, because `AdEditInput` coerces the same field. |
| **Problem** | Three POST-accepting views bypass Pydantic entirely. `save_search.py:37-57` and `saved_searches.py:113-140` each define a **byte-identical local `_int_or_none(name)` closure** and write the result straight to the ORM via `SavedSearch.objects.create(...)` / `saved_search.save(...)`. `min_price`/`max_price` are `PositiveIntegerField` (`search/models.py:97,102`) with a DB CHECK that a negative POST value violates, so invalid user input reaches the database and surfaces as an unhandled 500 rather than a validation error. `preferred_city.py:42-99` likewise parses `action`/`slug` from `request.POST` by hand, keeps two divergent cookie-emission paths, and writes `request.user.preferred_city` inline in the view. This is the opposite of the pattern `ad_edit` follows two directories away (`edit.py:124` — "Validate POST data via DTO before any ad.save() call"). |
| **Impact** | A user typing `-5` into a price box gets a server error page instead of a form error, and the same invalid value is accepted silently on the edit path. The three write surfaces that create a `SavedSearch` do not agree on validation, so fixing one leaves the others broken. A moderator-facing defect report filed against this is indistinguishable from a bug in the price filter. |
| **Root Cause** | `BaseInputModel` (`apps/core/schemas.py:17`) and the "validate before any ORM write" convention exist and are used in `ads`, `users` and `moderation`, but the `cabinet` and `search` write views predate the convention and were never migrated. There is no lint rule or architecture test that fails when a `views/` module calls `request.POST` and then `save()`/`create()`. |
| **Recommendation** | Add one `SavedSearchInput(BaseInputModel)` in `apps/search/schemas.py` with `query`, `city_id`, `category_id`, `min_price: int \| None = Field(default=None, ge=0)`, `max_price` and reuse it from both `save_search` and `saved_search_edit`, deleting the two `_int_or_none` closures. Route `preferred_city` through a `PreferredCityInput` DTO and move the cookie-emission into one helper. Add an architecture test asserting no `views/*.py` module calls `request.POST` and `.save()`/`.create()` in the same function. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-003, CQ-013 (consent cookie name read raw in `preferred_city.py`) |

**Evidence — the two identical `_int_or_none` closures** *(supports: "the POST int parser is copy-pasted verbatim")*:
```python
# src\backend\apps\search\views\save_search.py:39-46      # src\backend\apps\cabinet\views\saved_searches.py:120-127
def _int_or_none(name: str) -> int | None:                 def _int_or_none(name: str) -> int | None:
    raw = (request.POST.get(name) or "").strip()               raw = (request.POST.get(name) or "").strip()
    if not raw:                                               if not raw:
        return None                                            return None
    try:                                                     try:
        return int(raw)                                          return int(raw)
    except ValueError:                                       except ValueError:
        return None                                            return None
```

**Evidence — `src/backend/apps/search/views/save_search.py:48-57`** *(supports: "invalid user input reaches the ORM directly; `min_price` is a `PositiveIntegerField`")*:
```python
    saved_search = SavedSearch.objects.create(
        user=request.user,
        query=query or None,
        city_id=_int_or_none("city_id"),
        category_id=_int_or_none("category_id"),
        min_price=_int_or_none("min_price"),      # -1 -> CHECK (min_price >= 0) -> IntegrityError
        max_price=_int_or_none("max_price"),
        language=request.LANGUAGE_CODE or "bs",   # raw literal, see CQ-006
        is_active=True,
    )
```

---

#### CQ-005: [MEDIUM] — Presentation layer bypasses `AdStatus` with 11 raw status literals

| Field | Value |
|---|---|
| **ID** | CQ-005 |
| **Title** | Presentation layer bypasses `AdStatus` with 11 raw status literals |
| **Severity** | MEDIUM |
| **Category** | Constants / StrEnum (project rule 10) |
| **File(s)** | `src/backend/templates/ads/dashboard.html:126,128,137`, `src/backend/templates/admin/moderation/review.html:44,89,110`, `src/backend/templates/analytics/moderation_dashboard.html:34`, `src/backend/apps/moderation/views/review.py:120,153` |
| **Status** | Open |
| **Reproduction Steps** | 1. `Select-String -Path src/backend/templates -Pattern "on_moderation"` → 9 hits. 2. `Select-String -Path src/backend/apps -Pattern 'status__exact=on_moderation'` → 2 hits in `review.py`. 3. Note that `dashboard.py:58-88` keys `ads_by_status` and `status_labels` by `AdStatus` members, so Python and template each hold their own copy of the vocabulary. |
| **Problem** | `AdStatus` is a `StrEnum` and is the single source for `Ad.status`'s `choices`, 6 `CheckConstraint`s, the per-status indexes and `ALLOWED_TRANSITIONS`. But the seller dashboard and moderator review templates compare `ad.status` against raw literals (`'on_moderation'`, `'on_moderation_failed'`, `'rejected'`) and index the `ads_by_status` dict by raw attribute names (`.published`, `.on_moderation`, `.on_moderation_failed`, `.archived`, `.rejected`). `moderation/views/review.py:120,153` hardcodes `redirect("/admin/ads/ad/?status__exact=on_moderation")` — a raw status inside a hand-written URL. Eleven sites in total, in the layer that has no way to import the enum. |
| **Impact** | Renaming a status value updates the Python side automatically and silently breaks every template comparison and the two redirect URLs — the seller dashboard would render with no "Action required" or "Pending review" hints and the moderator's post-reject redirect would land on an unfiltered list. Nothing fails loudly; the failure is a missing warning banner. |
| **Root Cause** | Django templates cannot import Python, so some duplication is inherent; the avoidable part is that the *view* does not hand the template a pre-computed boolean/enum-keyed structure, and the URLs are hand-written instead of composed from a named route with a status parameter. |
| **Recommendation** | Do not chase the raw literals in `{% if %}` — instead have `dashboard()` and `moderation_review()` pass a pre-computed `status_flags` dict (e.g. `{"show_action_required": ad.status in {ON_MODERATION_FAILED, REJECTED}}`) so the vocabulary stays in Python. Separately, add a named URL for the moderation queue filtered by status and use `reverse(...)` with `AdStatus.ON_MODERATION.value` instead of the five hand-written `/admin/...` strings in `review.py` (see CQ-018). |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-006, CQ-018 |

**Evidence — `src/backend/templates/ads/dashboard.html:126-137`** *(supports: "the template holds its own copy of the status vocabulary; the view holds another")*:
```html
{% if status == 'on_moderation_failed' or status == 'rejected' %}
    <p class="text-xs text-red-600 mt-2">{% trans "Action required" %}</p>
{% elif status == 'on_moderation' %}
    <p class="text-xs text-yellow-600 mt-2">{% trans "Pending review" %}</p>
{% endif %}
...
{% if not ads_by_status.published and not ads_by_status.on_moderation and not ads_by_status.on_moderation_failed and not ads_by_status.archived and not ads_by_status.rejected %}
```

**Evidence — `src/backend/apps/ads/views/dashboard.py:58,82-88`** *(supports: "the view keys the same structure by `AdStatus` members — two independent sources for one vocabulary")*:
```python
    ads_by_status = {
        AdStatus.PUBLISHED: Ad.objects.filter(...),
        AdStatus.ON_MODERATION: Ad.objects.filter(...),
        AdStatus.ON_MODERATION_FAILED: Ad.objects.filter(...),
        AdStatus.ARCHIVED: Ad.objects.filter(...),
        AdStatus.REJECTED: Ad.objects.filter(...),
    }
    context = {
        "ads_by_status": ads_by_status,
        "status_labels": {
            AdStatus.PUBLISHED: _("Published"),
            AdStatus.ON_MODERATION: _("On Moderation"),
            ...
```

---

#### CQ-006: [MEDIUM] — `LanguageLocale` exists but raw `"ru"/"bs"/"en"` are fixed values in 9 production sites

| Field | Value |
|---|---|
| **ID** | CQ-006 |
| **Title** | `LanguageLocale` exists but raw `"ru"/"bs"/"en"` are fixed values in 9 production sites |
| **Severity** | MEDIUM |
| **Category** | Constants / StrEnum (project rule 10) + DOC-UPDATE |
| **File(s)** | `src/backend/apps/core/enums.py:5` (docstring), `src/backend/apps/core/enums.py:231-244`, `src/backend/apps/categories/models.py:61-62`, `src/backend/apps/locations/models.py:53-54`, `src/backend/apps/lookups/models.py:96-97`, `src/backend/apps/search/services/entity_suggestions.py:69`, `src/backend/apps/search/models.py:115`, `src/backend/apps/search/views/save_search.py:55`, `src/backend/apps/ads/management/commands/backfill_translations.py:20-21,39,106` |
| **Status** | Open |
| **Reproduction Steps** | 1. `Select-String -Path src -Pattern '"ru"\|"bs"\|"en"'` and filter out docstrings/seed data. 2. Observe `"ru"` hardcoded as the fallback key in three separate `get_name(locale)` model methods. 3. Observe `SearchVector`-adjacent `KeyTextTransform("ru", F("name_i18n"))` in a production annotation. 4. Observe `SavedSearch.language` declares `default="bs"` while its `help_text` names `LanguageLocale` codes. |
| **Problem** | `LanguageLocale` (`enums.py:194`) is the declared owner of the locale vocabulary, and the module docstring asserts "**No inline string literals for constants anywhere in the codebase.**" That claim is false. `LanguageLocale.fts_config` and `fts_vector_field` (`enums.py:231-244`) are themselves raw-string-keyed dicts inside the enum. Three models (`categories`, `locations`, `lookups`) each hardcode the same `if "ru" in name_i18n: return name_i18n["ru"]` fallback. `entity_suggestions.py:69` hardcodes `"ru"` inside a `KeyTextTransform`. `SavedSearch.language` uses `default="bs"` on a `CharField` whose help text says "LanguageLocale code". `save_search.py:55` and `backfill_translations.py` add four more. Nine production sites in total, plus a falsified self-claim in the constants module. |
| **Impact** | Adding a fourth locale requires finding all nine sites by grep; missing one produces a locale that silently falls back to Russian for some entity types and works for others. The `default="bs"` on a persisted column means a bad row is only discoverable by reading the data. The false docstring is the more expensive problem: a reviewer who reads `enums.py:5` and stops will assume rule 10 is fully satisfied. |
| **Root Cause** | `LanguageLocale` was introduced with conversion helpers (`values()`, `from_code()`) but the mapping tables and the `get_name` fallback chain were written as literal dicts/dict-keys. Model field `default=` cannot reference a StrEnum member without importing it into `models.py`, which was avoided. |
| **Recommendation** | (1) Delete or reword `enums.py:5` — the claim is not true and is worse than no claim. (2) Convert `fts_config`/`fts_vector_field` from inline dict literals to class-level `Final` maps keyed by `LanguageLocale` members. (3) Add `LanguageLocale.DEFAULT = BOSNIAN`-style accessor and use `default=LanguageLocale.BOSNIAN.value` in `SavedSearch.language`. (4) Extract the triplicated `get_name` fallback into one shared helper (`apps/core/utils/localized.py`) that takes the enum. (5) Use `LanguageLocale.RUSSIAN.value` in `entity_suggestions.py` and `backfill_translations.py`. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-005 (same class of enum bypass), CQ-004 (`save_search.py:55`) |

**Evidence — `src/backend/apps/core/enums.py:1-6, 228-244`** *(supports: "the constants module claims no inline string literals, then uses two raw-string dicts")*:
```python
"""
Core enum types for Mko Bazuna.

All fixed value sets are modeled as Enum or StrEnum per project rule 10.
No inline string literals for constants anywhere in the codebase.      <-- false
"""
...
    @property
    def fts_config(self) -> str:
        """PostgreSQL text search config for this language."""
        return {
            "ru": "russian",
            "bs": "simple",
            "en": "english",
        }[self.value]
```

**Evidence — the triplicated fallback chain** *(supports: "three models hardcode the same raw `"ru"` fallback")*:
```text
src\backend\apps\categories\models.py:61:  if "ru" in name_i18n:
src\backend\apps\categories\models.py:62:  return name_i18n["ru"]
src\backend\apps\locations\models.py:53:   if "ru" in name_i18n:
src\backend\apps\locations\models.py:54:   return name_i18n["ru"]
src\backend\apps\lookups\models.py:96:     if "ru" in name_i18n:
src\backend\apps\lookups\models.py:97:     return name_i18n["ru"]
--- plus:
src\backend\apps\search\services\entity_suggestions.py:69: KeyTextTransform("ru", F("name_i18n")),
src\backend\apps\search\models.py:115:    default="bs",
src\backend\apps\search\views\save_search.py:55:  language=request.LANGUAGE_CODE or "bs",
src\backend\apps\ads\management\commands\backfill_translations.py:20-21,39,106: ("en",...), ("bs",...), "ru"
```

---

#### CQ-007: [MEDIUM] — `apps/core/utils/cache.py` hand-copies 15 get/set/invalidate functions

| Field | Value |
|---|---|
| **ID** | CQ-007 |
| **Title** | `apps/core/utils/cache.py` hand-copies 15 get/set/invalidate functions |
| **Severity** | MEDIUM |
| **Category** | DRY / module size |
| **File(s)** | `src/backend/apps/core/utils/cache.py:15-192` (4 domains), `src/backend/apps/core/utils/cache.py:199-245` (5th domain), `src/backend/apps/lookups/services/cache_service.py:160-184` |
| **Status** | Open |
| **Problem** | The 245-line `cache.py` defines five independent cache domains (moderation criteria, site config, bot username, support contacts, anonymous language) as hand-copied `get_*` / `set_*` / `invalidate_*` triplets — 15 functions, of which 12 are structurally identical modulo the cache key, the TTL constant and the value type. The ratio of docstring to code is roughly 15:1 (e.g. `invalidate_criteria_cache`, `:44-53`, is 3 lines of body under 10 lines of docstring). The module has no `logger` at all, unlike every other module in `apps/core/utils/`. The same "invalidate by bumping a version" pattern appears a third time in `lookups/services/cache_service.py:160-184`, where `invalidate_group(group_code)` ignores its argument and does exactly what `invalidate_all()` does (see CQ-016). |
| **Impact** | A cache-key change or a switch to `cache.get_or_set` must be applied in 12 places. The failure mode is silent: a domain whose `invalidate_*` forgets a key keeps serving stale config with no error, and because every function is a one-liner there is no test that would notice a divergence in TTL or key format. Reading 245 lines to answer "what is the site-config cache key" is a poor ratio for a file imported by a middleware, a context processor and three services. |
| **Root Cause** | Each cache domain was added by copy-paste instead of by composing one small typed helper. The project rule is "avoid overengineering", and a 3-line parameterised helper is not overengineering — the duplication is the over-engineering here. |
| **Recommendation** | Collapse to a single `CacheEntry` helper (`get_cached(key, default)`, `set_cached(key, value, ttl)`, `invalidate(key)`) plus five small modules (or one module with five clearly separated blocks) that declare their key and TTL as `Final` constants. Delete `invalidate_group` or give it a real targeted implementation. Add a module `logger` for consistency with the rest of `apps/core/utils/`. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-016 (`invalidate_group` is the unused half of this) |

**Evidence — `src/backend/apps/core/utils/cache.py:44-98`** *(supports: "three structurally identical triples, differing only in key/TTL/type")*:
```python
def invalidate_criteria_cache(key: str = CRITERIA_CACHE_KEY) -> None:
    """
    Invalidate the cached ModerationCriteria.

    Called when admin updates criteria to ensure fresh values on next access.

    Args:
        key: Cache key to invalidate (defaults to moderation_criteria:v1)

    Returns:
        None
    """
    cache.delete(key)


SITE_CONFIG_CACHE_KEY: Final[str] = "site_config:v1"
SITE_CONFIG_CACHE_TTL: Final[int] = 3600  # 1 hour


def get_cached_site_config(key: str = SITE_CONFIG_CACHE_KEY) -> str | None:
    ...  # 10 lines of docstring
    return cache.get(key)
```

---

#### CQ-008: [MEDIUM] — `submit_ad` mixes six responsibilities in 124 lines

| Field | Value |
|---|---|
| **ID** | CQ-008 |
| **Title** | `submit_ad` mixes six responsibilities in 124 lines |
| **Severity** | MEDIUM |
| **Category** | Module size / SRP |
| **File(s)** | `src/backend/apps/ads/services/submission.py:122-245` |
| **Status** | Open |
| **Problem** | `submit_ad` is the shared orchestrator for both processes, and in 124 lines it performs six separable jobs: (1) thumbnail image generation with per-photo exception swallowing (`:141-159`), (2) staging→permanent file promotion (`:166`), (3) a DB transaction with `select_for_update` (`:169-173`), (4) field assignment including currency coercion and price normalization (`:175-210`), (5) M2M feature writes plus `AdImage` row creation (`:213-227`), (6) FSM transition and auto-moderation dispatch with its own hardcoded error strings (`:229-245`). It also builds its own user-facing message list (`["Ad not found"]`, `["Ad failed moderation checks"]`) inside the service, so i18n and presentation leak into the data layer. A function-local import at `:239` (`from apps.moderation.services.auto_moderation import auto_moderate`) sits inside the transaction. |
| **Impact** | The only shared business-logic seam between the bot and the web cannot be tested in pieces: a thumbnail failure (job 1) and a moderation failure (job 6) both surface as the same `(False, ["…"])` tuple, so a caller cannot tell the seller why submission failed. Because the function owns filesystem promotion *and* the transaction, a change to either forces a full re-read of the other, and the file-promotion rollback story (documented at `:161-165`) is invisible to any caller. |
| **Root Cause** | `_update_and_moderate` was lifted out of the bot handler wholesale (per the module docstring, `:1-9`) rather than decomposed, so the seam was created at the wrong granularity: too coarse to reuse, too mixed to test. |
| **Recommendation** | Split into three small functions with explicit seams: `prepare_photos(photos) -> None` (thumbnail + promote, filesystem only), `persist_ad(input) -> Ad` (transaction, fields, M2M, images, `transition_to`), and `submit_ad(input)` as a thin composer that calls the first two then `auto_moderate` and maps the result to a typed `SubmitOutcome` enum rather than a `list[str]` of English strings. Move the error text to the caller (the bot and the view each have their own `_()` context). |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-001 (the caller that must be split in the same pass), DB-002 (`auto_moderate`'s transaction interaction, mechanism owner) |

**Evidence — `src/backend/apps/ads/services/submission.py:139-169, 229-245`** *(supports: "filesystem promotion, transaction, write, transition and moderation all in one function; English error strings in the service")*:
```python
    # Generate thumbnails BEFORE the DB transaction (filesystem I/O outside tx)
    for photo in input.photos:
        try:
            ...
            photo.thumbnail_small = thumbnail_keys.get(ThumbnailSizeStrEnum.SMALL)
        except Exception:
            logger.exception("Failed to generate thumbnails for %s", photo.storage_key)
    move_staging_to_permanent(input.photos)

    with transaction.atomic():
        ...
        ad.transition_to(AdStatus.ON_MODERATION)

        from apps.moderation.services.auto_moderation import auto_moderate   # deferred, inside tx
        passed = auto_moderate(ad)
    if passed:
        return True, []
    else:
        return False, ["Ad failed moderation checks"]        # English string from a service
```

---

#### CQ-009: [MEDIUM] — `AdEditInput` accepts blank title/description, so a partial POST erases ad content

| Field | Value |
|---|---|
| **ID** | CQ-009 |
| **Title** | `AdEditInput` accepts blank title/description, so a partial POST erases ad content |
| **Severity** | MEDIUM |
| **Category** | Schema/validation boundary |
| **File(s)** | `src/backend/apps/ads/services/submission.py:82-97`, `src/backend/apps/ads/views/edit.py:130-132`, `src/backend/apps/ads/views/edit.py:250-251`, `src/backend/apps/ads/models.py:48-53`, `src/backend/apps/ads/models.py:66-70` |
| **Status** | Open |
| **Reproduction Steps** | 1. `POST /ads/<id>/edit/` with a body containing only `price_amount=10&price_currency=EUR&csrfmiddlewaretoken=…` (no `title`, no `description`). 2. `AdEditInput.model_validate({k: v for k, v in request.POST.items() if k in AdEditInput.model_fields})` yields `title=""`, `description=""`. 3. `ad.title = dto.title` at `edit.py:251` → `ad.save()`. 4. `Ad.title` is `null=True, blank=True` and there is no `CheckConstraint` on it and no `full_clean()` call anywhere, so the blank is committed. |
| **Problem** | `AdEditInput` declares `title: str = ""` and `description: str = ""` and its `_strip_text` validator maps `None` → `""`. The view filters the POST dict to the DTO's declared fields, so **any key the client omits silently becomes an empty string**, and all three branches assign it. The DTO's own docstring documents this as a known gap: "Blank title/description still overwrite the ad's values (matching the original view logic where missing POST keys → `\"\"`). Consider rejecting blanks or requiring an explicit clear signal in a future pass." The gap was recorded, not fixed, and the "future pass" left a live path that destroys seller content. |
| **Impact** | A stale HTMX fragment, a bookmarked form, a partial client, or a malformed retry can erase a seller's title and description with no error and no moderation re-check in the `ON_MODERATION`/`ON_MODERATION_FAILED` branch (which saves directly). The ad stays in its current status, so a published ad can go live with a blank title. Recovery requires the seller to re-type the text. |
| **Root Cause** | The DTO was modelled to reproduce the pre-existing lenient `except ValueError: pass` behaviour for price/currency (correctly, and documented) and that leniency was applied to the text fields too, because the original view treated a missing POST key as `""`. The `Ad` model has no `clean()`/`full_clean()` and no DB constraint, so nothing downstream catches it. |
| **Recommendation** | Make the text fields required in `AdEditInput` (`title: str` with `min_length=1` and a `max_length=200` matching the column; `description: str` with `min_length=1`), so an omitted key fails validation and the view returns a 400/form error instead of saving. Keep the lenient coercion only for `price_amount`/`price_currency`, where it is deliberate and documented. If a genuine "clear the title" action is ever needed, it should be an explicit `action=clear_title` signal, as `preferred_city.py:45` already does. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-001 (the caller being extracted), CQ-004 (same boundary class, other views) |

**Evidence — `src/backend/apps/ads/services/submission.py:82-97`** *(supports: "the gap is documented in the DTO and left unfixed")*:
```python
    NOTE: Blank title/description still overwrite the ad's values (matching the
    original view logic where missing POST keys → ``""``). Consider rejecting
    blanks or requiring an explicit clear signal in a future pass.
    """

    title: str = ""
    description: str = ""
    price_amount: Decimal = Decimal("0")
    price_currency: CurrencyCode | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def _strip_text(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()
```

**Evidence — `src/backend/apps/ads/views/edit.py:130-132, 250-251` + `ads/models.py:48-52`** *(supports: "an omitted POST key becomes `""` and is committed; nothing downstream rejects it")*:
```python
        dto = AdEditInput.model_validate(
            {k: v for k, v in request.POST.items() if k in AdEditInput.model_fields}
        )
...
            ad.title = dto.title
            ad.description = dto.description
---
# ads/models.py
    title = models.CharField(
        max_length=200,
        null=True,
        blank=True,          # blank is DB-legal; no CheckConstraint, no full_clean()
        help_text="Ad title in Russian (translated from seller input)",
    )
```

---

#### CQ-010: [MEDIUM] — 81 deferred function-local imports; moderation's business layer sits at the app root

| Field | Value |
|---|---|
| **ID** | CQ-010 |
| **Title** | 81 deferred function-local imports; moderation's business layer sits at the app root |
| **Severity** | MEDIUM |
| **Category** | Separation of concerns |
| **File(s)** | `src/backend/apps/moderation/admin_actions.py:1-6` (module docstring calls itself a "service"), `src/backend/apps/moderation/views/review.py:69,96,135`, `src/backend/apps/cabinet/views/saved_searches.py:115,116,144,150`, `src/backend/apps/core/context_processors.py:52,53,114,126`, `src/backend/apps/core/services/site_config.py:21,22,50,51`, `src/backend/apps/core/services/support.py:29,30`, `src/backend/apps/lookups/services/cache_service.py:112,139`, `src/backend/apps/ads/models.py:665,666`, `src/telegram_bot/handlers/contact.py:269`, `src/telegram_bot/handlers/support.py:159,160` |
| **Status** | Open |
| **Reproduction Steps** | 1. AST pass for `Import`/`ImportFrom` inside function bodies over `src/**` (excluding tests/migrations). 2. Result: 81 deferred imports. 3. Of those, ~14 are legitimate (`AppConfig.ready()` signal registration × 7, `migrate_locked`/`scheduler` bootstrap × 12). 4. The remainder are avoidable at request time, and three of them exist solely because `admin_actions.py` is not in `services/`. |
| **Problem** | Every module that needs a model at request time imports it inside the function: `review.py:69,96,135` (three views importing `apps.moderation.admin_actions`), `saved_searches.py:115,116,144,150`, `context_processors.py:52,53,114,126`, `site_config.py:21,22,50,51` and `support.py:29,30` (imports *inside service functions*), `cache_service.py:112,139`, `ads/models.py:665,666` (inside `save()`), `auto_moderation.py:246,263`, `submission.py:239`, and three bot handlers. The root cause of the most visible group is structural: `apps/moderation/admin_actions.py` (288 lines) describes itself as "Admin moderation actions **service**" but sits at the app root while `apps/moderation/services/` already exists with six modules — so the view must defer the import instead of declaring a normal dependency. |
| **Impact** | Dependencies are invisible to a reader skimming the module header and to `ruff`'s import sorter, so the real coupling graph differs from the declared one. `submission.py:239` and `auto_moderation.py:246,263` perform a module lookup inside an open transaction on the hot publish path. A circular-import fix becomes a per-call-site patch rather than one structural change, and the moderation app's business layer has two possible homes, so the next contributor picks wrong. |
| **Root Cause** | `admin_actions.py` predates the `services/` package convention and was never moved; the deferred imports are the accumulated scar tissue from working around that, plus a general absence of any rule discouraging function-local imports. |
| **Recommendation** | Move `admin_actions.py` to `apps/moderation/services/actions.py` and update the five importers (`review.py` × 3, `moderation/admin.py`, `telegram_bot` if any) — this alone removes three deferred imports. Then hoist the remaining genuinely-unnecessary deferred imports to module scope, one module at a time, starting with `context_processors.py` and `cabinet/views/saved_searches.py`. Add a `ruff` `PLC0415` (or equivalent) check to the CI `lint` job so new function-local imports fail the build. |
| **Effort** | M |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-002 (the same pattern in the bot), CQ-003 (one of the affected views) |

**Evidence — AST deferred-import inventory (representative extract)** *(supports: "81 function-local imports; the moderation ones exist because `admin_actions` is misplaced")*:
```text
src\backend\apps\moderation\views\review.py:69   inside approve_ad()   import apps.moderation.admin_actions
src\backend\apps\moderation\views\review.py:96   inside reject_ad()    import apps.moderation.admin_actions
src\backend\apps\moderation\views\review.py:135  inside ban_user()     import apps.moderation.admin_actions
src\backend\apps\ads\services\submission.py:239  (inside transaction.atomic, before auto_moderate)
src\backend\apps\ads\models.py:665              inside save()         import apps.media.services.filesystem
src\backend\apps\moderation\services\auto_moderation.py:246/263       import apps.moderation.services.moderation_log
src\backend\apps\core\context_processors.py:52,53,114,126            import apps.categories.models / locations.models / site_config / enums
src\backend\apps\cabinet\views\saved_searches.py:115,116,144,150     import apps.categories.models / locations.models
src\telegram_bot\handlers\contact.py:269         inside handle_contact_orm()  import apps.core.services.contact
---
TOTAL deferred imports: 81   (of which ~26 are AppConfig.ready() / scheduler bootstrap)
```

---

#### CQ-011: [MEDIUM] — Two difflib category-suggestion implementations with different cutoffs (0.6 vs 0.8)

| Field | Value |
|---|---|
| **ID** | CQ-011 |
| **Title** | Two difflib category-suggestion implementations with different cutoffs (0.6 vs 0.8) |
| **Severity** | MEDIUM |
| **Category** | DRY |
| **File(s)** | `src/backend/apps/search/views/search.py:391-413` (`_fuzzy_match_by_name`, cutoff 0.8), `src/backend/apps/ads/views/listings.py:276-282` (`_suggest_category`, cutoff 0.6), `src/backend/apps/search/views/search.py:365-388` (`_fuzzy_category_match`) |
| **Status** | Open |
| **Problem** | Two view modules, in two different apps, each implement "the user typed a category that does not exist, suggest the closest one" with `difflib.get_close_matches`. `search.py:391-413` matches against **display names** from the cached active-category list and uses `cutoff=0.8`. `listings.py:276-282` matches against **slugs** (`Category.objects.filter(is_active=True).values_list("slug", flat=True)`) and uses `cutoff=0.6`. They return different things (a `Category` instance vs a `str` slug), read different data, and apply different thresholds. `search.py:365-388` adds a third variant that first tries an exact slug match and an exact name match before fuzzing. |
| **Impact** | The same typo produces a suggestion on the search page and none on the listings page (or vice versa), so a user is told "did you mean X" in one place and given nothing in the other. Two thresholds mean the behaviour cannot be tuned in one place. `listings.py:278-280` also loads every active category slug on every unrecognised-category request, with no cache, while the search path is cached. |
| **Root Cause** | "Suggest a close category" was implemented once per page that needs it rather than once in `apps/categories/services/`. The shared seam already exists for the *resolve* direction (`CategoryLookupResolver`), which is why the gap is easy to miss. |
| **Recommendation** | Move the suggestion into `apps/categories/services/category_suggestion.py` as one function returning a `Category | None`, take the cutoff as a `Final` constant in that module, and have both views call it. Reuse `get_active_category_names(locale)` (already cached, already locale-aware) instead of the uncached slug query in `listings.py`. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-015 (same view pair, same duplication pattern) |

**Evidence — the two implementations** *(supports: "different data source, different threshold, different return type")*:
```python
# src\backend\apps\search\views\search.py:391-413  — matches NAMES, cutoff 0.8
def _fuzzy_match_by_name(query: str, locale: LanguageLocale) -> Category | None:
    entries = get_active_category_names(locale)
    all_names = [str(entry["name"]) for entry in entries]
    matches = get_close_matches(query, all_names, n=1, cutoff=0.8)
    if matches:
        matched_name = matches[0]
        for entry in entries:
            if str(entry["name"]) == matched_name:
                return Category.objects.get(id=entry["id"])
    return None

# src\backend\apps\ads\views\listings.py:276-282  — matches SLUGS, cutoff 0.6, uncached
def _suggest_category(slug: str) -> str | None:
    all_slugs = list(
        Category.objects.filter(is_active=True).values_list("slug", flat=True)
    )
    matches = get_close_matches(slug, all_slugs, n=1, cutoff=0.6)
    return matches[0] if matches else None
```

---

#### CQ-012: [MEDIUM] — Untyped service boundaries: bare `dict` into `update_or_create`, unannotated resolver params

| Field | Value |
|---|---|
| **ID** | CQ-012 |
| **Title** | Untyped service boundaries: bare `dict` into `update_or_create`, unannotated resolver params |
| **Severity** | MEDIUM |
| **Category** | Type safety (project rules 9, 11) |
| **File(s)** | `src/backend/apps/moderation/services/priority_calculator.py:23,47-53,55,68,70,89`, `src/backend/apps/moderation/services/priority.py:32-37`, `src/backend/apps/categories/services/lookup_resolution.py:110,120,186,190,226,233,252`, `src/backend/apps/categories/services/lookup_resolution.py:175` (`_get_through_model`), `src/backend/apps/analytics/services/seller_stats.py:33,56` |
| **Status** | Open |
| **Problem** | Two service boundaries lose their types. (1) `PriorityCalculator.calculate_priority(ad) -> dict` returns a bare `dict` whose four keys (`base_score`, `priority_level`, `flags`, `confidence_score`, `escalation_required`) are splatted straight into `AdModerationPriority.objects.update_or_create(defaults=data)` at `priority.py:34-37`; renaming a key is a runtime `FieldError`, not a type error. `flags` is a `list[str]` of raw literals `"banned_word"` / `"repeat_offender"` where a `StrEnum` belongs, and it is persisted in a `JSONField` (`moderation/models.py:154`). (2) `CategoryLookupResolver` has five methods with **no annotation on the `category` parameter at all** and a bare `-> list` return, each carrying `# type: ignore[type-arg]` to silence the type-checker (`lookup_resolution.py:110,120,190,252`) plus `grouped: dict[int, list]` and `result: list` inside `_resolve` (`:226,233`). `_get_through_model` (`:175`) additionally selects a model by raw string name with an untyped return. |
| **Impact** | A rename in the priority payload or a change to a resolver's return shape passes `basedpyright` (12 errors, all in tests) and fails at runtime, in the moderation publish path or in a cache producer. `apps/ads/views/listings.py:84` depends on `get_resolved_feature_codes`, one of the untyped methods, so the weakness is already on a user-facing path. The `type: ignore[type-arg]` comments are exactly the phase rubric's "`Any` used to make the type-checker pass, masking real issues" case. |
| **Root Cause** | The JSONField-backed `flags` list and the MPTT `category` object were treated as "dynamic, no type available" rather than modelled. The `type: ignore` was added to clear the CI gate (which is scoped to `src/backend` and currently red on 12 test errors) rather than to fix the signature. |
| **Recommendation** | Introduce `PriorityFlags(StrEnum)` (`BANNED_WORD`, `REPEAT_OFFENDER`) and a `PriorityScore(BaseModel)` in `apps/moderation/schemas.py`; have `calculate_priority` return `PriorityScore` and `priority.py` pass `defaults=score.model_dump()`. For the resolver, annotate `category: Category` and return `list[LookupItem]`, then drop all four `type: ignore[type-arg]` suppressions. Do the same for `seller_stats.SellerStats.get_stats`, which is the same untyped-`dict` shape. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-003 (a `StrEnum` that was never wired, same root pattern) |

**Evidence — `src/backend/apps/moderation/services/priority_calculator.py:23,47-53` + `priority.py:32-37`** *(supports: "an untyped dict crosses the service boundary into `update_or_create`")*:
```python
    def calculate_priority(self, ad: Ad) -> dict:            # bare dict
        ...
        return {
            "base_score": total,
            "priority_level": self._get_priority_level(total).value,
            "flags": flags,                    # list[str] of raw literals
            "confidence_score": self._estimate_confidence(ad),
            "escalation_required": total >= 80 or len(flags) >= 3,
        }
---
# priority.py
        data = self.calculator.calculate_priority(ad)
        obj, created = AdModerationPriority.objects.update_or_create(
            ad=ad,
            defaults=data,                     # untyped dict -> ORM
        )
```

**Evidence — `src/backend/apps/categories/services/lookup_resolution.py:110,120,190,252`** *(supports: "unannotated parameter + bare `list` + four type-checker suppressions in a shared service")*:
```python
    @staticmethod
    def get_resolved_purposes(category) -> list:  # type: ignore[type-arg]
    @staticmethod
    def get_resolved_features(category) -> list:  # type: ignore[type-arg]
    def _resolve(category, through_model_name: str, key_segment: str, item_field: str) -> list:  # type: ignore[type-arg]
    @staticmethod
    def get_resolved_conditions(category) -> list:  # type: ignore[type-arg]
---
# and inside _resolve:
            grouped: dict[int, list] = {}            # :226
            result: list = []                        # :233
```

---

#### CQ-013: [MEDIUM] — Consent cookie names are constants in one module and raw literals in two others

| Field | Value |
|---|---|
| **ID** | CQ-013 |
| **Title** | Consent cookie names are constants in one module and raw literals in two others |
| **Severity** | MEDIUM |
| **Category** | DRY / constants (project rule 10) |
| **File(s)** | `src/backend/apps/users/views/consent.py:51-54` (definitions), `src/backend/apps/users/context_processors.py:54,86,87,96` (raw reads), `src/backend/apps/search/views/preferred_city.py:90` (raw read), `src/backend/templates/privacy.html:74,80,86` (documented contract) |
| **Status** | Open |
| **Problem** | The four consent cookie names are declared once, correctly, as module constants in `apps/users/views/consent.py:51-54` (`CONSENT_COOKIE_NAME`, `CONSENT_ANALYTICS_COOKIE`, `CONSENT_PREFERENCES_COOKIE`, `CONSENT_TIMESTAMP_COOKIE`). The writer uses the constants; the two **readers** do not. `apps/users/context_processors.py:54,86,87,96` re-spells all four as literals, and `apps/search/views/preferred_city.py:90` inlines `"consent_preferences" == "true"` to gate a cookie write. Six raw literals duplicate four constants. These names are also part of the published privacy contract (`privacy.html:74,80,86` documents them in a table) and drive ePrivacy gating in 15 templates via the `consent_analytics` context key. |
| **Impact** | Renaming or correcting a cookie name updates the writer and leaves the readers reading a value that is never written. The failure is silent and one-directional: `consent_state()` would report `consent_analytics=False` for every user, so analytics would be gated off site-wide with no error, and `preferred_city` would never persist its cookie, so a buyer would lose their city choice on every page load. |
| **Root Cause** | The constants were introduced in the view that *writes* the cookies; the read-side context processor and the `search` app's privacy gate were written separately and reached for the literal because the constants live in a `views/` module (a reader importing from another app's `views/` is itself a layering smell, which is likely why it was avoided). |
| **Recommendation** | Move the four names into `apps/core/enums.py` as a `ConsentCookieName(StrEnum)` (satisfying rule 10 rather than module-level `str` constants) and import that enum in all three modules. A rename then becomes a single edit caught by `ruff` at every use site. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-006, CQ-004 (`preferred_city.py` is one of the three unvalidated write views) |

**Evidence — `src/backend/apps/users/views/consent.py:51-54` vs its readers** *(supports: "constants defined once, re-spelled as literals six times by the readers")*:
```python
# consent.py:51-54  — the single definition
CONSENT_COOKIE_NAME = "consent_given"
CONSENT_ANALYTICS_COOKIE = "consent_analytics"
CONSENT_PREFERENCES_COOKIE = "consent_preferences"
CONSENT_TIMESTAMP_COOKIE = "consent_timestamp"

# users/context_processors.py:54,86,87,96  — the reader
    cookie = request.COOKIES.get("consent_given", "")
    consent_analytics = request.COOKIES.get("consent_analytics") == "true"
    consent_preferences = request.COOKIES.get("consent_preferences") == "true"
    consent_timestamp = request.COOKIES.get("consent_timestamp")

# search/views/preferred_city.py:90  — a third module, different app
    if request.COOKIES.get("consent_preferences") == "true":
```

---

#### CQ-014: [MEDIUM] — `/alerts` promises a numeric toggle that no handler implements

| Field | Value |
|---|---|
| **ID** | CQ-014 |
| **Title** | `/alerts` promises a numeric toggle that no handler implements |
| **Severity** | MEDIUM |
| **Category** | Dead code (user-visible) |
| **File(s)** | `src/telegram_bot/handlers/alerts.py:88`, `src/telegram_bot/states.py:26-34` (`SavedSearchState`), `src/telegram_bot/handlers/alerts.py:33-89` (`cmd_alerts`) |
| **Status** | Open |
| **Reproduction Steps** | 1. Send `/alerts` to the bot as a logged-in seller with ≥1 saved search. 2. The bot lists the searches and ends with `_("\nReply with number to toggle, or /cancel to exit.")`. 3. Reply `1`. 4. Nothing happens — the message is not handled by any state or filter in `alerts.py`. 5. `grep -rn SavedSearchState src/` returns exactly one hit: the class definition. |
| **Problem** | `SavedSearchState` (`states.py:26-34`) declares six FSM states (`IDLE`, `QUERY`, `CITY`, `CATEGORY`, `PRICE`, `CONFIRM`) and is referenced by **nothing** — no handler, no test, no middleware. The sibling enums in the same module are both live (`AdCreateState` in 10 places, `ContactUsState` in 5). `cmd_alerts` still emits the instruction that this state machine was meant to serve: it prints the numbered list and then tells the user to "Reply with number to toggle". Toggle capability does exist, but only through the inline `unsub:`/`unsub_on:` callback buttons on digest messages (`alerts.py:107-180`), which this screen does not render. The `/alerts` screen also advertises `/cancel` while accepting no `cancel` text. |
| **Impact** | A seller follows the bot's own instruction, gets no response, and has no path to disable a saved search from `/alerts` at all — the only working route is finding the original digest message. The orphaned `StrEnum` implies a six-step flow that a future maintainer may try to wire up, discovering halfway through that the current screen was never designed for it. |
| **Root Cause** | The numeric-toggle flow was designed (`SavedSearchState` is the trace) and then dropped in favour of inline callback buttons; the prompt string and the state enum were never removed. This is the "test-only code that distorts production patterns" / incomplete-feature shape the phase rubric flags, with a user-facing symptom. |
| **Recommendation** | Decide which mechanism is canonical. Recommended: keep the inline callback buttons (already implemented, already used, already ownership-checked) and change the `/alerts` closing line to describe the actual affordance — e.g. "Notifications are toggled from the buttons on each alert message." — then delete `SavedSearchState`. If the numeric toggle is wanted instead, implement the state handlers against the existing `resolve_unsubscribe` / `resolve_reenable` seams and keep the enum. Either way, do not leave a live instruction with no handler. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-016 (the rest of the dead-code inventory) |

**Evidence — `src/telegram_bot/handlers/alerts.py:66-89`** *(supports: "the screen issues an instruction no handler serves")*:
```python
    lines = [_("Your saved searches:")]
    for i, ss in enumerate(saved_searches, 1):
        status = _("ON") if ss.is_active else _("OFF")
        ...
    lines.append(_("\nReply with number to toggle, or /cancel to exit."))
    await message.answer("\n".join(lines))

# No @router.message(...) in this module matches a bare number or the word "cancel".
# The only handlers registered are:
#   :33  @router.message(Command("alerts"))
#   :107 @router.callback_query(F.data.startswith(BotCallbackPrefix.UNSUB))
#   :147 @router.callback_query(F.data.startswith(BotCallbackPrefix.UNSUB_ON))
```

**Evidence — `src/telegram_bot/states.py:26-34` vs its siblings** *(supports: "`SavedSearchState` is the only orphan in the module")*:
```text
Select-String -Pattern 'AdCreateState|ContactUsState|SavedSearchState'  ->  reference counts
AdCreateState    : 10 references  (handlers/ad_create/__init__.py:19,59-77; ad_copy.py:19,65)
ContactUsState   :  5 references  (handlers/support.py:32,87,91,142 + tests)
SavedSearchState :  0 references  (states.py:26 is the definition)
```

---

#### CQ-015: [MEDIUM] — `listings.py` and `search.py` duplicate the 11-field `ListingsQueryParams` build and context assembly

| Field | Value |
|---|---|
| **ID** | CQ-015 |
| **Title** | `listings.py` and `search.py` duplicate the 11-field `ListingsQueryParams` build and context assembly |
| **Severity** | MEDIUM |
| **Category** | DRY |
| **File(s)** | `src/backend/apps/ads/views/listings.py:246-273`, `src/backend/apps/search/views/search.py:102-114,196-224`, `src/backend/apps/ads/services/listings_query.py:65-95` (`ListingsQueryParams`) |
| **Status** | Open |
| **Problem** | Two views in two apps build the same `ListingsQueryParams` DTO with the same 11 fields from the same `request` sources: `category_slug`, `city_slug`, `min_price`, `max_price`, `purpose_slug`, `condition_slug`, `feature_slugs`, `sort` (default `AdSort.DATE_NEW`), `user_id` (guarded by `is_authenticated`), `page` (default 1), `per_page` (`ListingsQuery.PER_PAGE`). The blocks are structurally identical; only the source of `category_slug` (`listings.py:246` takes the URL kwarg, `search.py:103` takes `request.GET["category"]`) and the source of `city_slug` (URL/middleware vs `request.GET` + fallback) differ. Both then call the identical four-line sequence `ListingsQuery.build_queryset(params)` → `resolve_filter_options` → `Paginator` → `active_price_range`, and both assemble a ~20-key template context with ~15 keys in common (`page_obj`, `suggested_category`, `suggested_city`, `breadcrumb_category`, `current_sort`, `min_price`, `max_price`, `active_price_min`, `active_price_max`, `current_listing_purpose`, `current_features`, `current_condition`, `resolved_purposes`, `resolved_features`, `resolved_conditions`, `show_filters`). `search.py:217-218` additionally embeds two live ORM queries inside the context dict literal. |
| **Impact** | Adding a filter means touching both views, and forgetting one produces a listing page and a search page that disagree about the same filter — a bug that reads as a data problem, not a code problem. The context contract is duplicated rather than owned, so a template shared by `ads/list.html` and `search`-rendered `ads/partials/ad_list.html` depends on two independent producers keeping the same 15 keys. |
| **Root Cause** | `ListingsQuery` was extracted as a service, but only its *queryset* half; the request→DTO→context half was left in each view. There is no `from_request(request) -> ListingsQueryParams` classmethod on the DTO. |
| **Recommendation** | Add `ListingsQueryParams.from_request(request, *, category_slug=None, city_slug=None)` as a classmethod on the DTO so both views delegate, and move the shared context assembly into a `ListingsQuery.build_context(params, request) -> dict[str, object]` so the ~15 common keys are produced once. Leave the search-specific keys (`query`, `total_count`, `results_truncated`, `show_filters`) in the search view. Hoist the two inline `City.objects`/`Category.objects` queries at `search.py:217-218` into the same helper. |
| **Effort** | M |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-011 (same view pair), CQ-004 (the DTO-coercion story that `ListingsQueryParams` does implement correctly, unlike `SavedSearch`) |

**Evidence — the two `ListingsQueryParams` blocks** *(supports: "same 11 fields, same sources, only two differ")*:
```python
# src\backend\apps\ads\views\listings.py:246-253
    params = ListingsQueryParams(
        category_slug=category_slug, city_slug=effective_city,
        min_price=request.GET.get("min_price"), max_price=request.GET.get("max_price"),
        purpose_slug=request.GET.get("listing_purpose"), condition_slug=request.GET.get("condition"),
        feature_slugs=request.GET.getlist("features"), sort=request.GET.get("sort", AdSort.DATE_NEW),
        user_id=request.user.id if request.user.is_authenticated else None,
        page=request.GET.get("page", 1), per_page=ListingsQuery.PER_PAGE,
    )

# src\backend\apps\search\views\search.py:102-114
    params = ListingsQueryParams(
        category_slug=current_category,          # <-- only this differs
        city_slug=current_city,                  # <-- and this
        min_price=min_price, max_price=max_price, # (pre-extracted into locals)
        purpose_slug=listing_purpose_slug, condition_slug=condition_slug,
        feature_slugs=feature_slugs, sort=request.GET.get("sort", AdSort.DATE_NEW),
        user_id=request.user.id if request.user.is_authenticated else None,
        page=request.GET.get("page", 1), per_page=ListingsQuery.PER_PAGE,
    )
```

### LOW

#### CQ-016: [LOW] — Dead code: deprecated shims, 2 unreferenced resolver methods, 3 prefix aliases, empty `apps/api`

| Field | Value |
|---|---|
| **ID** | CQ-016 |
| **Title** | Dead code: deprecated shims, 2 unreferenced resolver methods, 3 prefix aliases, empty `apps/api` |
| **Severity** | LOW |
| **Category** | Dead code / maintainability |
| **File(s)** | `src/backend/apps/users/views/consent.py:278-294` (`is_consent_given`), `src/backend/apps/categories/services/lookup_resolution.py:130-135` (`get_resolved_purpose_codes`), `src/backend/apps/categories/services/lookup_resolution.py:262-267` (`get_resolved_condition_codes`), `src/backend/apps/categories/services/lookup_resolution.py:65-67` (`RESOLVED_*_PREFIX`), `src/backend/apps/lookups/services/cache_service.py:170-184` (`invalidate_group`), `src/backend/apps/api/` (empty tree) |
| **Status** | Open |
| **Problem** | An AST pass over all 734 production functions, cross-referenced against every `.py`, `.md`, `.html`, `.yml` and `.sh` in `src/`, `docs/` and `.ai/`, surfaced 33 candidate-unreferenced definitions. 27 are false positives (Django auto-discovers `AppConfig`, `ModelAdmin`, `add_arguments`, `ready()`, and locustfile tasks). The remaining 6 are genuinely unreferenced: `is_consent_given` — a shim whose own docstring says "[Deprecated] … kept as a backward-compatible shim", with 0 callers (the real implementation it defers to is `context_processors.consent_state`); `get_resolved_purpose_codes` and `get_resolved_condition_codes` (only `get_resolved_feature_codes` is used, at `ads/views/listings.py:84`); the three `RESOLVED_*_PREFIX` aliases at `lookup_resolution.py:65-67`, commented as "kept for backward compatibility with **any external callers**" — there are none, this is an application inside one repository; and `LookupsCacheService.invalidate_group(group_code)`, which accepts an argument, never reads it, and calls the same `bump_lookup_version()` as `invalidate_all()`. Separately, `src/backend/apps/api/` is a directory tree (`api/`, `api/serializers/`, `api/views/`) containing **zero files**, and is not in `INSTALLED_APPS` (`base.py:180-193`). |
| **Impact** | Six unused symbols plus an empty app skeleton. `invalidate_group` is the most misleading: its signature and docstring promise a targeted invalidation it does not perform, so a caller who reaches for it would believe it is cheaper than `invalidate_all()` and would be wrong about the cache-blast radius. The rest is low-cost but compounds — a reader cannot tell a deliberately-retained seam from an abandoned experiment. |
| **Root Cause** | Successive refactors left shims without a deprecation deadline, and an early API layer was scaffolded and never populated. None of the six is covered by a test, so nothing fails when a caller disappears. |
| **Recommendation** | Per the project's dead-code policy, **investigate purpose before deleting.** Concretely: confirm with the team whether a public REST API is still planned for `apps/api/` — if not, remove the empty tree; if yes, add a one-line `README.md` stating the intent so the next reader does not have to guess. For `is_consent_given` and the three `RESOLVED_*_PREFIX` aliases, there is no external consumer in this repository, so removing them is safe; do it in one commit. For the two unreferenced `*_codes` methods, either wire them or remove them alongside their siblings. For `invalidate_group`, either implement the targeted delete its name implies or delete it — an argument-taking no-op should not exist. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-007 (`invalidate_group` lives in the hand-copied cache layer), CQ-014 (`SavedSearchState`, the sixth orphan, is user-visible so it is filed separately) |

**Evidence — dead-code probe output (unreferenced only; false positives removed)** *(supports: "6 genuinely unreferenced production symbols + an empty app tree")*:
```text
src\backend\apps\users\views\consent.py:278           func  occurrences_in_repo=1  is_consent_given
src\backend\apps\categories\services\lookup_resolution.py:130  method  occurrences_in_repo=1  get_resolved_purpose_codes
src\backend\apps\categories\services\lookup_resolution.py:262  method  occurrences_in_repo=1  get_resolved_condition_codes
src\backend\apps\lookups\services\cache_service.py:171        method  occurrences_in_repo=1  invalidate_group
src\backend\apps\categories\services\lookup_resolution.py:65-67  RESOLVED_{PURPOSES,FEATURES,CONDITIONS}_PREFIX  (0 uses)
src\telegram_bot\states.py:26                        class  occurrences_in_repo=1  SavedSearchState   (see CQ-014)
---
src\backend\apps\api\           -> 0 files
src\backend\apps\api\serializers\  -> 0 files
src\backend\apps\api\views\        -> 0 files
("apps.api" does not appear in INSTALLED_APPS, base.py:180-193)
--- removed as false positives (framework-discovered): 27
```

**Evidence — `src/backend/apps/lookups/services/cache_service.py:170-184`** *(supports: "`invalidate_group` takes an argument it never reads and duplicates `invalidate_all`")*:
```python
    @staticmethod
    def invalidate_group(group_code: str) -> None:
        """Invalidate cache for a specific group by bumping the content version.

        A single global version bump is used (rather than a targeted key
        delete) because lookup invalidation is infrequent (admin operation)
        and version-bump prevents thundering-herd across all lookup entries.

        Args:
            group_code: The code of the group to invalidate.
        """
        bump_lookup_version()
        logger.debug(
            "Invalidated lookup cache for group: %s (version bump)", group_code
        )
```

---

#### CQ-017: [LOW] — Packaging/convention drift: missing `__init__.py`, private name in `__all__`, unordered enum members

| Field | Value |
|---|---|
| **ID** | CQ-017 |
| **Title** | Packaging/convention drift: missing `__init__.py`, private name in `__all__`, unordered enum members |
| **Severity** | LOW |
| **Category** | Naming / conventions (project rules 8, 15) |
| **File(s)** | `src/backend/apps/ads/services/` (no `__init__.py`), `src/backend/apps/api/` (no `__init__.py`, also CQ-016), `src/telegram_bot/services/ad_data/orm.py:21-30`, `src/backend/apps/core/enums.py:35-43` (`AdvisoryLockId`) |
| **Status** | Open |
| **Problem** | Three small consistency breaks. (1) All 12 other `services/` packages ship an `__init__.py`; `apps/ads/services/` does not, so it is an implicit namespace package while every sibling is a regular one. (2) `telegram_bot/services/ad_data/orm.py:21-30` declares `__all__` and includes `"_get_ad_status"` — a leading-underscore private name in an explicit public export list, which reads as a contradiction. (3) In `AdvisoryLockId` (`enums.py:23-43`) the members are numerically ordered 1-8, then 100-104, then **11, 12**, then 110, 111 — `PURGE_DELETED_ADS = 11` and `RECOMPUTE_NORMALIZED_PRICES = 12` were appended after the 100-series, so the enum cannot be read in order and two members are trivially mistaken for duplicates of the 1-8 range at a glance. |
| **Impact** | Individually trivial. Together they are the cost of "does this repo have a convention?" — a contributor copying the `services/` layout may omit `__init__.py`; a caller using `from ... import *` on `orm.py` gets a private name it should not rely on; and a reader scanning `AdvisoryLockId` for lock 11 will find it after 104. No runtime defect; `AdvisoryLockId` values are correct and the numbering is intentional (a reserved 1-12 band, a 100-series for infrastructure). |
| **Root Cause** | Incremental growth without a periodic convention pass. The `AdvisoryLockId` ordering is a consequence of a deliberate numbering scheme that was not reflected in declaration order. |
| **Recommendation** | Add an empty `src/backend/apps/ads/services/__init__.py` to match the 12 siblings. Remove `"_get_ad_status"` from `orm.py.__all__` (or drop the underscore from the function, since it is part of the module's published surface). Reorder `AdvisoryLockId` into ascending numeric order with a comment block separating the "scheduled job" band (1-12) from the "infrastructure" band (100+). All three are single-line-or-smaller edits. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-016 (`apps/api` empty tree) |

**Evidence — services package contents** *(supports: "12 of 13 `services/` packages have `__init__.py`")*:
```text
src\backend\apps\ads\services : copy_service.py, favorites.py, images.py, listings_query.py, submission.py   <-- no __init__.py
src\backend\apps\analytics\services : __init__.py, moderation_analytics.py, seller_stats.py, trust_analytics.py
src\backend\apps\categories\services : __init__.py, lookup_resolution.py
src\backend\apps\core\services : __init__.py, analytics.py, contact_rate_limit.py, contact.py, site_config.py, support.py, translation.py
... (all 10 remaining services/ packages also ship __init__.py)
```

**Evidence — `src/backend/apps/core/enums.py:26-43`** *(supports: "members are not in numeric order: 11 and 12 sit after 104")*:
```python
class AdvisoryLockId(IntEnum):
    ARCHIVE_SWEEP = 1
    DELETE_SWEEP = 2
    CONSENT_HARD_DELETE = 3
    SWEEP_DRAFTS = 4
    CLEANUP_LOGIN_TOKENS = 5
    PURGE_FAILED_ADS = 6
    PURGE_REJECTED_ADS = 7
    ROLLUP_DAILY_METRICS = 8
    ALERT_DELIVERY_TASK = 9
    MIGRATE = 100
    CREATE_ADMIN = 101
    BACKFILL_THUMBNAILS = 102
    SWEEP_ORPHANED_MEDIA = 103
    CATALOG_LOAD = 104
    PURGE_DELETED_ADS = 11            # <-- out of order
    RECOMPUTE_NORMALIZED_PRICES = 12  # <-- out of order
    SEED = 110
    TEST_SCHEMA_SETUP = 111
```

---

#### CQ-018: [LOW] — `@require_POST` vs inline `request.method` checks; 5 hardcoded `/admin/` URLs

| Field | Value |
|---|---|
| **ID** | CQ-018 |
| **Title** | `@require_POST` vs inline `request.method` checks; 5 hardcoded `/admin/` URLs |
| **Severity** | LOW |
| **Category** | Naming / conventions (project rule 8) |
| **File(s)** | `src/backend/apps/ads/views/edit.py:268,305`, `src/backend/apps/ads/views/delete.py:26`, `src/backend/apps/ads/views/favorite.py:27`, `src/backend/apps/moderation/views/review.py:51`, `src/backend/apps/search/views/preferred_city.py:25`, `src/backend/apps/users/views/consent.py:125,182,236,379`, `src/backend/apps/users/views/logout.py:15` (6 `@require_POST`) vs `src/backend/apps/cabinet/views/saved_searches.py:44,63,93`, `src/backend/apps/cabinet/views/search_history.py:42`, `src/backend/apps/core/views.py:156`, `src/backend/apps/moderation/views/decorators.py:55`, `src/backend/apps/moderation/views/review.py:98,137`, `src/backend/apps/search/views/save_search.py:34` (9 inline `if request.method != "POST"`) plus `src/backend/apps/moderation/views/review.py:81,99,120,138,153` |
| **Status** | Open |
| **Problem** | POST-only endpoints are declared two different ways. Six views use the `@require_POST` decorator (which returns a real 405 with an `Allow` header); nine use a hand-written `if request.method != "POST": return HttpResponse(status=405)` or a `!= "POST"` branch that `redirect`s instead of returning 405. The consequences are not identical: `review.py:98-99` and `:137-138` **redirect** to the change page on a GET rather than returning 405, so a GET to those URLs is a 302, not a 405. Separately, `review.py` builds five redirect targets as string literals (`/admin/ads/ad/{id}/change/`, `/admin/ads/ad/?status__exact=on_moderation`) instead of using `reverse()`, unlike the rest of the codebase which uses `redirect("ads:dashboard")` / `reverse("cabinet:saved-searches")`. |
| **Impact** | No correctness bug today, but a monitor or a `HEAD` probe sees three different responses for "wrong method" depending on which endpoint it hits, and the two hardcoded `/admin/...` URLs also embed the raw `on_moderation` status (see CQ-005). If the admin URLs are ever namespaced or mounted under a prefix, these five sites break silently. |
| **Root Cause** | The `cabinet`, `search/save_search` and `moderation/review` endpoints predate or bypass the convention; the "redirect instead of 405" behaviour in `review.py` looks deliberate (a moderator clicking a link should land back on the form) but is not documented as such. |
| **Recommendation** | Standardise on `@require_POST` (or `@require_http_methods(["POST"])` where a redirect-on-GET is the intended behaviour, which makes the intent explicit). Add a named URL for the moderation queue filtered by status and use `reverse()` in the five `review.py` redirects. This is a mechanical, testable change; the existing moderation view tests (`apps/moderation/tests/test_moderation_views.py`) already cover the happy paths. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-005 (the raw `on_moderation` inside the hardcoded URL) |

**Evidence — the two conventions side by side** *(supports: "6 decorator vs 9 inline checks; two of the inline ones redirect instead of returning 405")*:
```text
@require_POST  (6):  ads/views/edit.py:268,305 · ads/views/delete.py:26 · ads/views/favorite.py:27
                    moderation/views/review.py:51 · search/views/preferred_city.py:25
                    users/views/consent.py:125,182,236,379 · users/views/logout.py:15
inline  (9):        cabinet/views/saved_searches.py:44,63,93 · cabinet/views/search_history.py:42
                    core/views.py:156 · moderation/views/decorators.py:55
                    moderation/views/review.py:98,137 · search/views/save_search.py:34

# the two that redirect rather than 405:
src\backend\apps\moderation\views\review.py:98    if request.method != "POST":
src\backend\apps\moderation\views\review.py:99        return redirect(f"/admin/ads/ad/{ad_id}/change/")
src\backend\apps\moderation\views\review.py:137   if request.method != "POST":
src\backend\apps\moderation\views\review.py:138       return redirect(f"/admin/ads/ad/{ad_id}/change/")

# the hardcoded URLs (no reverse()):
src\backend\apps\moderation\views\review.py:81    return redirect(f"/admin/ads/ad/{ad_id}/change/")
src\backend\apps\moderation\views\review.py:120   return redirect("/admin/ads/ad/?status__exact=on_moderation")
src\backend\apps\moderation\views\review.py:153   return redirect("/admin/ads/ad/?status__exact=on_moderation")
```
*(`review.py:99` and `:138` are the same string as `:81`; 5 literal occurrences total.)*

---

#### CQ-019: [LOW] — 1,474 comment-only lines in production Python, many restating the next statement

| Field | Value |
|---|---|
| **ID** | CQ-019 |
| **Title** | 1,474 comment-only lines in production Python, many restating the next statement |
| **Severity** | LOW |
| **Category** | Conventions (project rule 12: "comment only non-trivial logic, avoid obvious or redundant comments") |
| **File(s)** | `src/backend/apps/ads/views/edit.py:104`, `src/backend/apps/ads/services/submission.py:175,229`, `src/backend/apps/ads/management/commands/backfill_translations.py:90,95`, `src/backend/apps/ads/views/dashboard.py:50,57`, `src/backend/apps/moderation/views/review.py:107`, `src/backend/apps/core/utils/scheduler.py:38`, `src/backend/apps/media/services/filesystem.py:147,151`, `src/backend/apps/categories/services/lookup_resolution.py:232`, `src/backend/apps/analytics/services/seller_stats.py:65` |
| **Status** | Open |
| **Problem** | Production Python contains 1,474 comment-only lines. The codebase is otherwise well documented — the design comments explaining *why* (e.g. `edit.py:112-115` on the row-lock scope, `submission.py:161-165` on the TX-then-Filesystem ordering, `swr_cache.py:12-25` on the state machine, `swr_cache.py:84-88` on `lock_ttl < stale_ttl`) are exactly what the project wants. The problem is a smaller class of comment that restates the following line and adds nothing: `# Prefetch images for the edit template` above `ad = Ad.objects.prefetch_related("images").get(id=ad_id)` (`edit.py:104-105`); `# Update ad fields — Russian remains the base content` above `ad.title = input.title_ru` (`submission.py:175-176`); `# Transition DRAFT -> ON_MODERATION` above `ad.transition_to(AdStatus.ON_MODERATION)` (`submission.py:229-230`); `# Translate title` / `# Translate description` above two `translate_text(...)` calls (`backfill_translations.py:90,95`); `# Build reason from category + text` above the reason concatenation (`review.py:107`); `# Check magic bytes` above the magic-byte comparison (`filesystem.py:147`); `# Build timestamps consistent with status` above the seed timestamp block (`seed/generators/ads.py:459`). A related symptom in the bot: `submit.py:46-48` writes `original_title = data.get("title", "")`, a blank line, `original_desc = data.get("description", "")`, a blank line — each assignment isolated by whitespace as if each were a section. |
| **Impact** | No behavioural risk. The cost is signal-to-noise: a reader scanning for the design comments has to filter out the narrating ones, and the narrating comments become stale silently (e.g. `# Translate title` above a call that later also translates the description). Roughly 5-8% of production comment lines are of this kind. |
| **Root Cause** | Comments were written alongside the code rather than after, with no distinction drawn between "why" and "what". Nothing in review or tooling distinguishes the two. |
| **Recommendation** | No bulk rewrite. On the next file a contributor touches in `apps/ads/views/` or `apps/ads/services/`, delete the narrating comments in that file and keep every "why" comment. Do **not** touch the design comments — they are the most valuable documentation in the repository and CQ-001/CQ-008's recommendations depend on several of them being accurate. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | CQ-001, CQ-008 (the "why" comments in these two files must be preserved) |

**Evidence — narrating vs explaining comments in the same file** *(supports: "the design comments are valuable; a minority restate the code")*:
```python
# src\backend\apps\ads\views\edit.py
104:    # Prefetch images for the edit template                       <-- narrating (adds nothing)
105:    ad = Ad.objects.prefetch_related("images").get(id=ad_id)
...
112:    # DB-003: re-fetch the Ad under a row lock inside a transaction so the   <-- explaining
113:    # status-driven branch below and the subsequent transition_to() operate    (keep)
114:    # on a locked, consistent row. The GET path returns before this block, so
115:    # the lock is scoped to POST mutations only (mirrors review.py reject_ad).
```

## Cross-Finding Analysis

- **Merge candidates:**
  - **CQ-011 + CQ-015** share one root cause: `apps/categories` and `apps/ads/services` were extracted as services, but the *view-side* glue was left in each view, so the search and listings pages each grew their own copy. One "extract the view-side glue" change (a `from_request` classmethod plus a `build_context` helper) closes both. Kept separate because the fixes are in different files and can land independently.
  - **CQ-016 + CQ-017** are both "small consistency breaks in module layout" and could ship as one tidy-up commit. Kept separate because the dead-code one requires a product decision on `apps/api` (investigate before delete) and the other needs none.
  - **CQ-003 + CQ-012** both stem from modelling a fixed vocabulary as an untyped/unenforced value (`CategoryRejectReason` never wired; `PriorityFlags` never created). One pass through `apps/moderation/schemas.py` could introduce the missing enum and the missing Pydantic payload together.

- **Conflicting evidence:** None. No two findings rest on contradictory measurements; the two linter/type-checker results (R-02, R-03) are reported as-is and the only non-production `ruff` error is in a phase-03 probe script, not in `src/`.

- **Dependency chains:**
  - **CQ-001 must land before or with CQ-008.** Both split the same ad-submission path. Extracting `ad_edit`'s branches (CQ-001) while `submit_ad` still mixes six responsibilities (CQ-008) leaves the seam at the wrong granularity; doing CQ-008's decomposition first gives CQ-001 a clean target. Recommended order: CQ-008 → CQ-001.
  - **CQ-007 should precede CQ-016's `invalidate_group` removal**, so the cache layer is tidy before its unused half is deleted.
  - **CQ-004 is a prerequisite for CQ-013** in `preferred_city.py`: introducing `PreferredCityInput` is the natural moment to import `ConsentCookieName` instead of the raw literal.
  - **CQ-003's fix (a `RejectAdInput` DTO) is independent** and can ship any time; it does not depend on CQ-004.

- **Deliberately NOT re-filed (owned elsewhere):**
  - `_get_client_ip` exists in **three** service modules — `apps/users/services/login_rate_limit.py:63`, `apps/search/services/rate_limit.py:69`, `apps/core/services/contact_rate_limit.py:24` — all three with byte-identical bodies. The duplication was already measured and is owned by **AUT-003** (Phase 04). *Correction to the brief's context note:* the copies are no longer "in the login and consent views"; they have already been refactored into `services/` modules. The duplication is real but has moved, so AUT-003's file list needs updating.
  - `consent.py` is 470 lines and is the subject of the service-extraction recommendation in **ENT-005** (Phase 01, downgraded to MEDIUM by the phase-01 validator). Not re-filed here. Note that CQ-013 recommends relocating consent *cookie names* out of that module — coordinate with ENT-005 so the constants are not moved twice.
  - `create_draft_ad`'s missing savepoint is **DB-001** / **AD-005**; `record_event`'s transaction interaction is **DB-002**. Both live in code this phase measured (`telegram_bot/services/ad_data/orm.py`, `apps/core/services/analytics.py`) but the mechanisms are owned by Phase 03.
  - `CONN_MAX_AGE=0` + per-update `close()` is documented intentional design (`base.py:260`, `apps/core/db/connection.py:1-16`) — **not** a defect, not filed.
  - `squash_rehydrate_runsql.py` rewrites a committed migration file, which looks alarming on first read, but the trigger DDL is correctly present in `ads/migrations/0001_initial.py:706-720` (R-06), the marker is already present (`:705`), the command has a `--dry-run`, and the workflow is documented in `docs/ops/migration-workflow.md:243,397`. Documented tooling, not dead code — **not** filed.
  - `health_check` in `apps/core/views.py:141` is a "backward-compatible alias", but it is routed (`apps/core/urls.py:10` → `path("health/", views.health_check)`), so it is live — **not** dead code, **not** filed.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | CQ-001 | HIGH | M | P0 | Extract `edit_ad` into `apps/ads/services/edit.py`; hoist the duplicated `SubmitAdInput` block; move `_apply_price_change` to the price normalizer |
| 2 | CQ-002 | HIGH | M | P0 | Create `telegram_bot/services/{login,alerts,contact,support}.py`; add an architecture test forbidding ORM in `handlers/` |
| 3 | CQ-003 | HIGH | S | P1 | Coerce `reason_category` through `CategoryRejectReason` in a new `RejectAdInput(BaseInputModel)`; or delete the enum if free text is intended |
| 4 | CQ-008 | MEDIUM | M | P1 | Split `submit_ad` into `prepare_photos` / `persist_ad` / composer; return a typed `SubmitOutcome` instead of `list[str]` |
| 5 | CQ-009 | MEDIUM | S | P1 | Make `AdEditInput.title`/`.description` required with `min_length=1` so an omitted POST key cannot blank an ad |
| 6 | CQ-014 | MEDIUM | S | P1 | Fix the `/alerts` closing instruction to match the inline-button reality, or implement the numeric toggle; delete `SavedSearchState` either way |
| 7 | CQ-004 | MEDIUM | S | P1 | Add `SavedSearchInput(BaseInputModel)` with `ge=0` price bounds; delete both `_int_or_none` closures |
| 8 | CQ-012 | MEDIUM | S | P2 | Add `PriorityScore` Pydantic model + `PriorityFlags(StrEnum)`; annotate `CategoryLookupResolver` and drop 4 `type: ignore[type-arg]` |
| 9 | CQ-010 | MEDIUM | M | P2 | Move `admin_actions.py` into `apps/moderation/services/actions.py`; hoist the other deferred imports; enable `PLC0415` in CI |
| 10 | CQ-013 | MEDIUM | S | P2 | Add `ConsentCookieName(StrEnum)` to `apps/core/enums.py`; import it in the 3 reader modules |
| 11 | CQ-015 | MEDIUM | M | P2 | Add `ListingsQueryParams.from_request()` and `ListingsQuery.build_context()` so both views share one producer |
| 12 | CQ-006 | MEDIUM | S | P2 | Fix the false `enums.py:5` docstring claim; enum-key the FTS maps; share the `get_name` fallback chain |
| 13 | CQ-005 | MEDIUM | S | P2 | Pass pre-computed `status_flags` from the views instead of comparing raw literals in templates; `reverse()` the queue URL |
| 14 | CQ-011 | MEDIUM | S | P2 | One `apps/categories/services/category_suggestion.py` with a single `Final` cutoff, used by both views |
| 15 | CQ-007 | MEDIUM | S | P2 | Collapse 15 hand-copied cache functions into one helper + 5 key/TTL blocks; add a module logger |
| 16 | CQ-016 | LOW | S | P2 | Investigate `apps/api` intent, then remove the empty tree and the 5 unreferenced symbols (or document `api` with a README) |
| 17 | CQ-017 | LOW | S | P2 | Add `apps/ads/services/__init__.py`; drop `_get_ad_status` from `orm.__all__`; reorder `AdvisoryLockId` |
| 18 | CQ-018 | LOW | S | P2 | Standardise on `@require_POST`; add a named moderation-queue URL and use `reverse()` |
| 19 | CQ-019 | LOW | S | P2 | Opportunistic: delete narrating comments in files being touched; preserve all "why" comments |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| CQ-001 | High — rewrites the seller ad-edit state machine | No (behaviour-preserving refactor, but any mistake publishes a wrong ad) | `apps/ads/tests/test_edit.py` + `test_edit_views_locking.py` (302, 294 use an untyped `advisory_lock` CM and already fail `basedpyright`) must stay green for all four status branches |
| CQ-002 | Med — moves the login claim and unsubscribe toggle | Yes if the public function signatures are kept as re-exports | `src/telegram_bot/tests/test_unsubscribe.py`, `test_login*.py`, `test_support.py`; add a case for the new architecture test |
| CQ-003 | Low — rejects POSTs that previously succeeded | **No** — a moderator posting an unknown `reason_category` now gets 400 | New: unknown-category rejection + all 8 valid categories still accepted (`test_moderation_views.py:398,423,444,488` cover `spam_scam` only) |
| CQ-004 | Med — turns 500s into 400s | Yes for valid input; invalid input changes status code | New: `min_price=-1` returns 400 not 500 on **both** `save_search` and `saved_search_edit` |
| CQ-005 | Low — template-only | Yes | `apps/ads/tests/test_breadcrumbs_render.py` and any dashboard template smoke test must still show the "Action required" / "Pending review" hints |
| CQ-006 | Low — pure constant refactor | Yes | `apps/search/tests/test_search_fuzzy.py`, `apps/categories` i18n tests; `test_i18n_completeness.py` after touching any msgid-adjacent code |
| CQ-007 | Low — cache key/TTL consolidation | Yes if TTLs are preserved exactly | Every `*_CACHE_TTL` assertion in the suite; run twice to catch a stale-entry regression |
| CQ-008 | Med — the shared bot↔web seam | Yes | `apps/ads/tests/test_submission.py` (82 tests), `src/telegram_bot/tests/test_ad_create.py`, `test_create_draft_ad.py` |
| CQ-009 | Med — rejects previously-accepted partial POSTs | **No** — a client that omits `title` now gets a validation error instead of a blanked ad | New: partial POST returns 400 and the ad is **unchanged** in the DB |
| CQ-010 | Med — moves a module | Yes | `apps/moderation/tests/test_admin_actions.py` (4 pre-existing `basedpyright` errors on an untyped `advisory_lock` CM) |
| CQ-011 | Low — changes which suggestion a user sees | Yes (behaviour change on the listings page) | Add a test pinning the chosen cutoff |
| CQ-012 | Low — types only | Yes | `apps/moderation/tests/test_priority_service.py`; must confirm the `update_or_create` payload keys are unchanged |
| CQ-013 | Med — cookie-name consolidation | Yes if values are unchanged | `apps/users/tests/test_consent.py`, `test_consent_context.py` (159 lines of cookie assertions), `apps/search/tests/test_preferred_city*.py` |
| CQ-014 | Low — removes a broken instruction | **No** — the `/alerts` closing text changes | `src/telegram_bot/tests/test_alerts*.py`: assert the new instruction and that a bare number is no longer implied |
| CQ-015 | Med — one producer for a shared template context | Yes if all 15 shared keys are preserved | Both `ads/list.html` and the HTMX `ads/partials/ad_list.html` render paths (HTMX is easy to miss) |
| CQ-016 | Low — removals | Yes, unless something outside the repo imports them (nothing does) | Run the full suite after removal; `ruff` will surface any missed import |
| CQ-017 | Low | Yes | Import-time only; `apps/ads/tests/test_edit.py` imports from `services/` and must still resolve |
| CQ-018 | Low — status codes change on wrong-method requests | **No** — two moderation endpoints change 302→405 | New assertions for the wrong-method response on `reject_ad` and `ban_user` |
| CQ-019 | Low — comment-only | Yes | None required |

## Appendices

### Appendix A — Commands used (read-only)

```powershell
uv run ruff check .                                        # 2 errors, both in .ai/audit/03-db-concurrency/verify_db.py
uv run basedpyright src/backend                            # 12 errors, all in test files
uv run basedpyright src/telegram_bot                       # 2 errors, both in tests/test_ad_create.py
Select-String -Path <src py files> -Pattern '^\s*print\('  # 4 hits, all in apps/core/tests/test_migrations.py
Select-String -Path <src py/html> -Pattern 'on_moderation'  # 11 production literal sites
Select-String -Path <src py> -Pattern 'pyright: ignore'     # 53, all django-stubs Atomic.__enter__/__exit__
Select-String -Path <src py/html> -Pattern '[\u0400-\u04FF]' # 15 hits, all legitimate (R-12)
uv run python .ai/tmp/cqsizes.py                           # AST function-length census (deleted)
uv run python .ai/tmp/cqdead.py                            # AST dead-symbol probe (deleted)
uv run python .ai/tmp/cqorm.py                             # AST ORM-density-in-views probe (deleted)
uv run python .ai/tmp/cqimp.py                             # AST deferred-import probe (deleted)
```

*(All four `.ai/tmp/` probe scripts were deleted after the run; `git status --porcelain`
shows only the untracked `.ai/audit/` and `.ai/tmp/` directories — no source file was
modified.)*

### Appendix B — R-01, R-08, R-12, R-13, R-06, R-07: what passed, and why it matters

These are the checks the brief listed as known-or-expected, re-verified rather than assumed.

```text
R-01  print() in production code
      grep '^\s*print\(' over src/**/*.py (excl. tests, migrations)
      -> 4 hits: apps/core/tests/test_migrations.py:61,62,90,91 (a StringIO-capturing migration test)
      -> 0 hits in production code, including entry points (telegram_bot/main.py, manage.py, gunicorn.conf.py)

R-06/R-07  migration discipline
      ads/migrations/0001_initial.py:211-235   search_vector{,_ru,_bs,_en} columns
      ads/migrations/0001_initial.py:537-555   IX_ads_search_gin{,_ru,_bs,_en} GIN indexes
      ads/migrations/0001_initial.py:616-630   ck_ad_images_*_key_format CHECK constraints (declared in models.py)
      ads/migrations/0001_initial.py:706-720   4x migrations.RunSQL: trigger functions + CREATE TRIGGER
      -> every model field in apps/ads/models.py has a migration; the only raw DDL outside migrations
         is setup_search_triggers.py, which idempotently re-installs the migration's own DDL
      -> no CREATE/ALTER/DROP TABLE anywhere in src/

R-08  contact gating is shared, not copied
      apps/core/services/contact.py:27-45  _check_seller_contactable  <- the single Zone-R2 predicate
      apps/core/services/contact.py:48      can_contact_seller   (web render path)
      apps/core/services/contact.py:71      get_seller_for_contact (bot path)
      apps/core/services/contact.py:97      record_contact_initiated (both paths)
      telegram_bot/handlers/contact.py:269-283  delegates to both; no condition list re-implemented
      -> the phase rubric's DRY-across-processes check PASSES for the contact flow

R-12  English-only
      15 Cyrillic/diacritic hits in production .py, all legitimate:
        core/utils/sanitize.py:29,31,34,37  regex character classes (А-Яа-яЁё) - REQUIRED
        search/services/entity_suggestions.py:26, search/views/save_search.py:4  docstring examples
        categories/models.py:96  help_text example
        cabinet/apps.py:5, core/management/commands/profile_queries.py:13  docstring examples
        telegram_bot/handlers/language.py:110  native language names (intentional)
        telegram_bot/handlers/ad_create/city.py:49  an English string containing a Serbian place name
        telegram_bot/lifecycle.py:38-41,44,47  user-facing Telegram command menu - documented design (see lifecycle.py:31-35)

R-13  no TODO/FIXME/HACK/XXX in production code (3 hits, all test fixture strings)
```

### Appendix C — Full inventory: raw fixed-value literals where a StrEnum exists

```text
Ad status (AdStatus) in templates / URLs                          11 sites
  templates/ads/dashboard.html:126,128,137
  templates/admin/moderation/review.html:44,89,110
  templates/analytics/moderation_dashboard.html:34
  apps/moderation/views/review.py:120,153

Locale (LanguageLocale) as raw "ru"/"bs"/"en"                      9 sites
  apps/core/enums.py:231-244        (the enum's own fts_config / fts_vector_field dicts)
  apps/categories/models.py:61-62
  apps/locations/models.py:53-54
  apps/lookups/models.py:96-97
  apps/search/services/entity_suggestions.py:69
  apps/search/models.py:115          (default="bs" on a persisted column)
  apps/search/views/save_search.py:55
  apps/ads/management/commands/backfill_translations.py:20,21,39,106

Consent cookie names                                               6 sites  (CQ-013)
  users/context_processors.py:54,86,87,96
  search/views/preferred_city.py:90
  (definitions: users/views/consent.py:51-54)

Moderation reject reason (CategoryRejectReason)                     0 enforced (CQ-003)
  users/... review.py:108 reads a raw string; the enum is never referenced
```
