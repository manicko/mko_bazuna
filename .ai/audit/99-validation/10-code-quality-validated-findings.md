# Phase 10 Audit Findings — Code Quality (Validated)

**Executor:** audit-executor (Kilo auditor)
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** yes
**Validator:** validator (Kilo)
**Validation Date:** 2026-07-20

---

## Findings

### QLT-001: Bot ad-create handler re-implements auto-moderation instead of using the shared service

| Field | Value |
|-------|-------|
| **ID** | QLT-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py`, `src/backend/apps/moderation/services/auto_moderation.py` |
| **Classification** | mandatory |

**Description:** The bot handler `update_ad_and_moderate()` (ad_create.py, lines 485-570) re-implements the entire auto-moderation gate inline — title/description length checks, price-required, image-count, and max-ads-per-user — rather than delegating to the shared `moderation.services.auto_moderation.auto_moderate()` / `check()`. The shared service is the single source of truth and IS used by the web flow (`ads/views/edit.py` lines 109, 226 call `auto_moderate`). This is the core "DRY across processes" violation.

Critically, the bot's inline copy is a SUBSET of the shared logic: it omits the `banned_words` check (`_contains_banned_words`) and the `duplicate_title` check (`_is_duplicate_title`). It also does not go through `moderation_log.set_moderation_failed` / `set_published`, so `ModeratorActionLog` is never written for bot-submitted ads, and the same moderation failure does not produce the same audit trail as the web path. This is a real correctness + spec deviation: the bot and web accept different ad content under the same `ModerationCriteria`.

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py:499-568` — inline validation + status transition, no import of `auto_moderate`.
- `src/backend/apps/moderation/services/auto_moderation.py:144-156, 179-188, 202-214` — banned-words and duplicate-title checks present in shared service, absent in handler.
- `src/backend/apps/ads/views/edit.py:15,109,226` — web flow correctly reuses `auto_moderate`.
- `src/backend/apps/moderation/services/moderation_log.py` — ModeratorActionLog writes bypassed by bot path.

**Recommendation:** Replace `update_ad_and_moderate()`'s inline moderation with a call to the shared `auto_moderate(ad)` (after persisting the translated ad + images). Keep the handler as a thin adapter that builds the `Ad` row and delegates; remove the duplicated validation block. This guarantees identical gate behavior and a single audit trail across both processes. Effort: small. Priority: recommended (mandatory per severity - correctness/spec deviation).

> **Validation Note:**
> - **Action:** Validated
> - **Detail:** Finding is confirmed. The bot's inline moderation (lines 517-541) lacks `_contains_banned_words` (lines 179-188) and `_is_duplicate_title` (lines 202-214) checks present in `auto_moderation.py`. Additionally, bot does not log to `ModeratorActionLog`, breaking audit trail consistency. This is a SPEC-DEVIATION: code violates the architectural rule of shared services while creating correctness risk.

---

### QLT-002: Bot contact handler duplicates R2 contact-gating logic instead of reusing the shared contact service

| Field | Value |
|-------|-------|
| **ID** | QLT-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/handlers/contact.py`, `src/backend/apps/core/services/contact.py` |
| **Classification** | mandatory |

**Description:** The bot handler `check_seller_available()` (contact.py, lines 108-157) re-implements the exact Zone R2 contact-gating conditions (`status == PUBLISHED`, `telegram_id IS NOT NULL`, `NOT is_deleted`, `NOT is_banned`, `consent_revoked_at IS NULL`) that already exist as `core.services.contact.can_contact_seller()` / `get_seller_for_contact()` (lines 26-104). The web path uses the shared service (listings detail template / contact render). The duplication means any future change to R2 conditions (e.g. a new gating rule) must be edited in two places, and they can silently drift — a correctness risk for the privacy-sensitive contact path.

`record_contact_event()` in the bot (lines 160-185) is also a duplicate of `core.services.contact.record_contact_initiated()` (lines 107-128); both create the `CONTACT_INITIATED` analytics row.

**Evidence:**
- `src/telegram_bot/handlers/contact.py:136-153` — inline R2 checks, duplicate of `core/services/contact.py:43-62` and `65-104`.
- `src/backend/apps/core/services/contact.py` — single source of truth already present and used by web.

**Recommendation:** Have the bot handler delegate to `core.services.contact.get_seller_for_contact(ad_id)` and `record_contact_initiated()`. Remove `check_seller_available` / `record_contact_event` from the bot. Effort: small. Priority: recommended (mandatory per severity).

> **Validation Note:**
> - **Action:** Validated
> - **Detail:** Finding is confirmed. Bot's `check_seller_available` (lines 136-153) duplicates the exact 5-condition logic from `get_seller_for_contact` (lines 80-102) with only cosmetic differences. The web path correctly delegates via template tag to `can_contact_seller`. This violates the project's shared-service architecture and creates drift risk for privacy-sensitive contact path.

---

### QLT-003: StrEnum value passed as raw string to AnalyticsEvent instead of enum member

| Field | Value |
|-------|
| **ID** | QLT-003 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` |
| **Classification** | mandatory |

**Description:** At line 565 the bot handler records the analytics event with `event_type=AnalyticsEventType.AD_PUBLISHED.value` — i.e. a raw string `"ad_published"` — whereas the shared `auto_moderation._pass_moderation` (line 231) correctly passes the enum member `AnalyticsEventType.AD_PUBLISHED` and the web `login.py` (line 152) passes `AnalyticsEventType.REGISTRATION_CREATED`. The `event_type` field is a `CharField` whose `choices` are the enum's `.value`s, so it works at runtime, but passing `.value` defeats the project rule that all fixed values are `StrEnum` and creates drift between two call sites in the same codebase (one uses the member, one uses `.value`). It is a StrEnum-usage inconsistency and a latent bug if the field is ever typed to expect the enum.

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py:565` — `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.AD_PUBLISHED.value, user=user_id)`.
- `src/backend/apps/moderation/services/auto_moderation.py:231` — `event_type=AnalyticsEventType.AD_PUBLISHED` (correct).
- `src/backend/apps/analytics/models.py:18-22` — `event_type` is a CharField with enum-derived choices.

**Recommendation:** Change line 565 to `event_type=AnalyticsEventType.AD_PUBLISHED` (enum member, not `.value`), matching the shared service. Optionally wrap the ad-publish analytics recording into the shared `auto_moderate`/`_pass_moderation` path so it is never written directly from the bot (ties into QLT-001). Effort: trivial. Priority: recommended.

> **Validation Note:**
> - **Action:** Validated
> - **Detail:** Finding is confirmed. Line 565 passes `.value` (raw string) while line 231 of `auto_moderation.py` and line 152 of `login.py` correctly pass the enum member. This violates project rule 10 (StrEnum for all constants). Note that this finding is blocked on QLT-001 - if the bot delegates to `auto_moderate`, the analytics recording moves to `_pass_moderation` and this issue disappears automatically.

---

### QLT-004: Listing sort options defined as raw module-level strings instead of StrEnum

| Field | Value |
|-------|-------|
| **ID** | QLT-004 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/ads/views/listings.py` |
| **Classification** | advisory |

**Description:** `listings.py` (lines 21-25) defines sort options as plain string constants `SORT_DATE_NEW = "date_desc"`, etc., and compares them as raw strings (lines 138-145). The same sort token also appears in the template/query-string contract. Per project rule 10 every fixed value set must be a `StrEnum`. This is the only set of fixed values in `src/` not modeled as `StrEnum`; it is a drift risk if a new sort is added or the token value changes (the raw string must be edited in the view and any template that emits the `?sort=` link).

**Evidence:**
- `src/backend/apps/ads/views/listings.py:21-25` and `138-145` — raw string constants + `==` comparisons.

**Recommendation:** Introduce an `AdSort(StrEnum)` (e.g. `DATE_DESC = "date_desc"`) in `core/enums.py` and use its members for both the default and the branch comparisons. Templates should reference the same values. Effort: small. Priority: recommended.

> **Validation Note:**
> - **Action:** Validated
> - **Detail:** Finding is valid. The raw string constants (SORT_DATE_NEW, SORT_DATE_OLD, SORT_PRICE_LOW, SORT_PRICE_HIGH) violate project rule 10 which mandates StrEnum for all fixed value sets. This is a legitimate improvement opportunity without overengineering.

---

### QLT-005: User consent/soft-delete service uses naive `datetime.now()` instead of `timezone.now()`

| Field | Value |
|-------|-------|
| **ID** | QLT-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py` |
| **Classification** | advisory |

**Description:** `withdraw_consent`, `soft_delete_user_ads`, and `give_consent` use `datetime.datetime.now()` (naive local time) to stamp `consent_revoked_at`, `deleted_at`, `consent_given_at`, and the ads' `deleted_at`. The rest of the codebase (e.g. `ad_create.py`, `edit.py`) uses Django's `django.utils.timezone.now()`, which yields timezone-aware UTC datetimes. Mixing naive and aware datetimes can produce comparison/sweep bugs in the timezone-aware `archive_sweep` / `delete_sweep` / `purge_*` management commands that compare these timestamps against `timezone.now()`. Noted as LOW because the project runs with `USE_TZ` and the impact is subtle, but it is an inconsistency that can surface in the scheduled sweeps.

**Evidence:**
- `src/backend/apps/users/services/deletion.py:54, 92, 114` — `datetime.now()`.
- Contrast with `src/backend/apps/ads/views/edit.py:19,146` and `src/telegram_bot/handlers/ad_create.py:16,543` — `timezone.now()`.

**Recommendation:** Replace `datetime.now()` with `from django.utils import timezone; timezone.now()` throughout `deletion.py`. Effort: trivial. Priority: recommended.

> **Validation Note:**
> - **Action:** Validated
> - **Detail:** Finding is confirmed. Lines 54, 92, and 114 use `datetime.now()` (naive) while management commands like `archive_sweep.py` (line 42) and `delete_sweep.py` (line 43) use `timezone.now()`. The sweep commands compare `published_at__lt=cutoff_date` where cutoff uses `timezone.now()`, creating potential timezone issues. This is a legitimate timezone consistency issue.

---

### QLT-006: Root-level scaffold/scratch scripts with `print()` pollute the repo root

| Field | Value |
|-------|
| **ID** | QLT-006 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `main.py`, `count_cats.py`, `count_cities.py`, `count_seeds.py` (repo root) |
| **Classification** | advisory |

**Description:** The repo root contains `main.py` (a Django-project template stub: `print("Hello from mko-bazuna!")`) and three `count_*.py` scratch scripts that use `print()` for output. None of these are part of the installed application (`src/`), and `ruff`/`basedpyright` were run only against `src/` so they pass clean. However, these scripts (a) violate the no-`print()` rule if ever linted at repo level, (b) are untested scratch tooling that can confuse contributors about what is production code, and (c) `main.py` shadows a conventional entrypoint name. The `print()` audit for this phase (grep) correctly found 8 hits, all in these root files — none inside `src/` (confirmed clean).

**Evidence:**
- `grep print\()` → 8 hits, all in repo-root `main.py`/`count_*.py`; zero hits in `src/`.
- `src/backend/manage.py` and `src/telegram_bot/main.py` use `logger`, not `print()`.

**Recommendation:** Delete `main.py` and the `count_*.py` scratch scripts from the repo root. These are unused template/scaffold files not referenced by any application code or command. If counting logic is needed later, reintroduce it as a proper Django management command under `src/backend/apps/`. Effort: trivial. Priority: recommended.

> **Validation Note:**
> - **Action:** Validated
> - **Detail:** Finding is confirmed. All 8 `print()` calls are in repo-root `main.py` and `count_*.py` files, none in `src/`. These are clearly scaffold/scratch files not part of the production codebase. They violate the no-print rule and should be removed or relocated.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 6 | QLT-001, QLT-002, QLT-003, QLT-004, QLT-005, QLT-006 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

None. All findings are valid.

### Merged Findings

None. Findings identify distinct issues.

### Reclassified Findings

None. QLT-003 is correctly identified as SPEC-DEVIATION (StrEnum rule violation), not DOC-UPDATE.

---

## Cross-Finding Analysis

### Dependency Chains

- **QLT-001 and QLT-003 are coupled**: If QLT-001 is fixed (bot delegates to `auto_moderate`), QLT-003 resolves automatically since analytics recording moves into `_pass_moderation`.

### Rollout Safety Assessment

All recommended fixes are:
- **Non-breaking**: No database schema changes, no API contract changes
- **Isolated**: Changes confined to single functions/files
- **Low-risk**: No cross-module dependencies introduced

---

## Architectural Consistency Check

The findings highlight a pattern: **bot handlers embed business logic instead of delegating to shared services**. This violates the documented architecture principle of "strict separation of concerns" and creates:

1. **Correctness gaps** (QLT-001 lacks banned_words/duplicate_title checks)
2. **Audit trail gaps** (QLT-001 bypasses ModeratorActionLog)
3. **DRY violations** (QLT-002 duplicates contact-gating logic)

The project architecture (docs/99-agent/architecture.md) mandates shared services via `apps/*/services`, but this is not fully honored in bot handlers. A DOC-UPDATE to `docs/99-agent/architecture.md` reaffirming "bot handlers MUST delegate to `apps/*/services`, never re-implement business logic" would improve clarity.