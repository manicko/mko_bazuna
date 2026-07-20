---
name: validated-findings
description: Validated and cross-verified audit findings for PII Protection & Consent Compliance phase
agent: validator
alwaysApply: false
---

# Phase 06 Validated Audit Findings — PII Protection & Consent Compliance

**Original Source:** `.ai/audit/06-pii-consent/findings.md`  
**Validation Date:** 2026-07-20  
**Status:** Complete

> Note: Runtime verification (§4) was NOT executed. This audit environment is
> Windows (win32) without Docker/PostgreSQL, so the documented Docker compose
> stack could not be started. Findings below are validated from static code review.

---

## Findings

### PII-001: WITHDRAW does not block the bot — revoked identity uncoupled from lookup key

| Field | Value |
|-------|-------|
| **ID** | PII-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/middlewares/permissions.py`, `src/backend/apps/users/services/deletion.py`, `src/backend/apps/users/models.py` |
| **Classification** | mandatory |

**Description:** The bot identifies a user by `telegram_id` and gates banned/deleted users via `User.objects.get(telegram_id=telegram_id)`. `withdraw_consent` NULLs `telegram_id` immediately (to "break chat linkage"). As a result a withdrawn user's row can no longer be found by the bot's lookup: `get(telegram_id=<real_id>)` raises `User.DoesNotExist`, which the middleware treats as "not registered yet" → returns `(True, "")` → **full bot access is granted**. The `is_deleted` check (`permissions.py:111`) is therefore unreachable for withdrawn users. The bot never rejects a revoked/soft-deleted identity, violating phase §f (cross-process consent consistency) and the consent banner covering the bot (spec decision K, line 93).

**Evidence:**
- `permissions.py:104-106` — `_check_user_state` returns `(True, "")` on `DoesNotExist`, so a withdrawn user (telegram_id=NULL) is treated as a brand-new, unrestricted user.
- `deletion.py:62` — `user.telegram_id = None` on WITHDRAW.
- `models.py:72` — `telegram_id` is `USERNAME_FIELD` and unique login key.
- `technical-specification.md:93` — "Site banner consent covers all PII processing including the bot; no separate bot confirmation required."

**Recommendation:** Add a `chat_id` BigInteger column to `User` (unique, indexed, NOT NULL) that is set on first bot contact and never nullified on withdraw/deletion. Update the bot middleware in `permissions.py` to look up users by `chat_id` instead of `telegram_id`, then check `is_deleted` and `consent_revoked_at` to block withdrawn users. The `telegram_id` remains available for web login only. Create a migration for the new field; update `_check_user_state` to use the stable `chat_id` lookup. Effort: medium. Priority: mandatory for compliance.

---

### PII-002: WITHDRAW path is unreachable from the UI/bot — withdrawal flow is dead code

| Field | Value |
|-------|-------|
| **ID** | PII-002 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/views/consent.py`, `src/backend/apps/users/urls.py`, `src/backend/apps/users/services/deletion.py` |
| **Classification** | mandatory |

**Description:** `withdraw_consent()` is defined and exported but is never invoked by any view, URL, or bot handler. The consent banner exposes only ACCEPT (`consent/accept/`) and DECLINE (`consent/decline/`). There is no `consent/withdraw/` route, no admin action calls it, and the bot has no withdrawal entry point. The entire consent-withdrawal + 30-day erasure flow documented in spec decision F/K and zone R1/R3 is therefore unreachable through normal operation; the only way to set `consent_revoked_at` is manual DB edits by a superuser. The consent hard-delete sweep has tests, but nothing in the running system ever produces the rows it operates on.

**Evidence:**
- `urls.py:9-10` — only `accept` and `decline` routes; no withdraw.
- `consent.py:25,54` — only `consent_accept` and `consent_decline` exist.
- `deletion.py:38` — `withdraw_consent` defined but orphaned.
- `technical-specification.md:83-84` — describes WITHDRAW behavior but no implementation exists.

**Recommendation:** Add a `consent/withdraw/` URL route and view that calls `withdraw_consent`, surfaced from the consent banner and user account page. Additionally, add a Django admin action in `users/admin.py` to call `withdraw_consent` for operator-triggered deletions. This ensures GDPR-compliant user-initiated withdrawal while providing admin fallback. Effort: small. Priority: mandatory for the documented GDPR flow.

---

### PII-003: DECLINE does not block seller login (spec requires it)

| Field | Value |
|-------|-------|
| **ID** | PII-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py`, `src/backend/apps/users/services/account_state.py`, `src/telegram_bot/middlewares/permissions.py`, `src/backend/apps/users/views/consent.py` |
| **Classification** | mandatory |

**Description:** Spec decision K (`technical-specification.md:90`) states: "DECLINE = browse-only: blocks only seller login/actions." `decline_consent` only sets `ads_auto_publish=False`. Web login uses Django auth keyed on `telegram_id` (unchanged by DECLINE), and `can_login()` only checks `is_banned`. The bot middleware restricts `/post` for `ads_auto_publish=False` but does not block login/other commands. A declined seller can still log in to the dashboard and perform non-publish seller actions. This diverges from the documented contract.

**Evidence:**
- `deletion.py:33-34` — DECLINE sets only `ads_auto_publish=False`.
- `account_state.py:80-99` (`can_login`) — returns True unless `is_banned`.
- `permissions.py:133` — bot only blocks `/post`, not login.
- `technical-specification.md:90` — "blocks only seller login/actions".

**Recommendation:** Add an `is_declined` boolean field or check `consent_declined` status (e.g., `has_consented=False`) to `can_login()` in `account_state.py` to return `False` for declined users, blocking web dashboard access. Update the bot middleware in `permissions.py` to reject all non-browse commands for declined users (not just `/post`). Align with spec decision K's "browse-only: blocks seller login/actions" semantics. Effort: small. Priority: mandatory.

---

### PII-004: Media files are never erased on consent hard-delete (orphaned PII on disk)

| Field | Value |
|-------|-------|
| **ID** | PII-004 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION + cross-cutting (phase §6) |
| **Affected Modules** | `src/backend/apps/core/management/commands/consent_hard_delete.py`, `src/telegram_bot/services/media.py`, `src/backend/apps/ads/models.py` |
| **Classification** | mandatory |

**Description:** `consent_hard_delete` deletes the User row, which ORM-CASCADEs to ads and `ad_images` rows. However the actual JPEG files written to `MEDIA_ROOT` (`ad_create.py:431-436`) are never `unlink`ed. No delete/storage-cleanup function exists in `media.py` and a grep across the codebase finds no `.delete()`/`os.remove`/`unlink` for media anywhere. The images remain on disk and are still served by nginx `/media/` via their unguessable UUID key. Phase §6 explicitly states: "PII erasure → media cascade: the erasure trigger here must also clear referenced media files." This is unmet — the sweep erases DB rows but leaves the physical PII-bearing media.

**Evidence:**
- `consent_hard_delete.py:71` — `queryset.delete()` only removes ORM rows.
- `media.py` — no file-deletion helper (only `validate_*`, `generate_storage_key`).
- `ad_create.py:431-436` — files written with `open(media_path,"wb")`; no symmetric delete.
- `models.py:305-313` — `on_delete=CASCADE` removes the row, not the file.

**Recommendation:** Add a media-cleanup step to the erasure cascade that, before/after deleting `ad_images` rows, unlinks each `MEDIA_ROOT/<image>` file (and the orphaned DRAFT photos, see PII-005). Keep it simple: iterate `AdImage` storage keys for the target users and `os.remove` under `MEDIA_ROOT`. Effort: small. Priority: mandatory.

---

### PII-005: Withdraw-mid-FSM not purged — DRAFT photos leaked, FSM state stale

| Field | Value |
|-------|-------|
| **ID** | PII-005 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE (cross-cutting edge case §7) |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py`, `src/telegram_bot/handlers/ad_create.py`, `src/telegram_bot/main.py` |
| **Classification** | mandatory |

**Description:** Edge case §7: "Seller withdraws mid-FSM-dialog (DRAFT + photos) → DRAFT and photos purged, no residual PII." `withdraw_consent` calls `soft_delete_user_ads`, which `UPDATE`s all ads (incl. DRAFT) to `DELETED`; the later hard-delete CASCADEs the rows. But: (a) the in-progress `FSMContext` data held in the bot's `MemoryStorage` is never cleared, so a half-built ad (title/description/price/photo keys) survives in bot memory; (b) the DRAFT photos already written to disk are never deleted (same gap as PII-004); (c) there is no signal/hook connecting `withdraw_consent` to the bot at all, so a withdraw performed via the web leaves the bot-side FSM completely unaware. Residual PII (photo bytes + draft text in memory) is not purged.

**Evidence:**
- `deletion.py:79-102` — `soft_delete_user_ads` only flags ads; no FSM/memory or file cleanup.
- `main.py:26` — `MemoryStorage()` holds FSM state; no purge hook on withdrawal.
- No signal connects user withdrawal to bot FSM (grep confirms no `post_save`/`pre_delete` signals for withdrawal).

**Recommendation:** Implement a scheduled reconciliation sweep that (a) queries DRAFT/ads belonging to `is_deleted=True` users, deletes their associated media files from `MEDIA_ROOT`, and removes the corresponding `Ad` and `AdImage` rows; (b) documents that in-memory FSM state in `MemoryStorage` is ephemeral and is cleared automatically on bot restart. Since the bot uses `MemoryStorage` (in-process memory), real-time cross-process FSM purge is infeasible without shared storage; add a comment to `main.py` noting this limitation and optionally emit a Django signal that can be adopted later if Redis-backed FSM storage is implemented. Effort: small-meduim. Priority: mandatory.

---

### PII-006: `hard_delete_at` is a dead/unused field contradicting docs

| Field | Value |
|-------|-------|
| **ID** | PII-006 |
| **Severity** | MEDIUM |
| **Type** | DOC-UPDATE |
| **Affected Modules** | `src/backend/apps/users/models.py`, `src/backend/apps/users/admin.py`, `docs/02-database/db-schema.md` |
| **Classification** | advisory |

**Description:** `User.hard_delete_at` is documented (db-schema.md:52,60) as "Phase 4 30-day hard-delete sweep target." In reality the sweep filters on `consent_revoked_at + 30d` and never reads or writes `hard_delete_at`. The field is set nowhere, only displayed as a readonly admin field. It is dead schema and the docs describe a mechanism the code does not implement.

**Evidence:**
- `models.py:65-69` — `hard_delete_at` defined, never written anywhere (grep confirms).
- `consent_hard_delete.py:45-50` — uses `consent_revoked_at__lt=cutoff_date`.
- `db-schema.md:52,60` — claims sweep targets `hard_delete_at`.
- `admin.py:39` — `hard_delete_at` in `readonly_fields`.

**Recommendation:** Remove the field (with a migration) and fix the doc, OR implement it (set `hard_delete_at = consent_revoked_at + 30d` in `withdraw_consent` and have the sweep filter on it). Simpler is to drop it and align docs. Effort: small. Priority: recommended.

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** Originally marked `DOC-UPDATE / dead-code`. On review, this is properly classified as `DOC-UPDATE` since the code behavior (using `consent_revoked_at`) is consistent and correct; only documentation is inaccurate. The field can be removed or docs updated to reflect actual implementation.

---

### PII-007: Mixed naive/aware timestamps risk timezone-skewed 30-day window

| Field | Value |
|-------|-------|
| **ID** | PII-007 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE (edge case §7 TZ skew) |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py` |
| **Classification** | advisory |

**Description:** `withdraw_consent` and `give_consent` use `datetime.now()` (naive, server-local) for `consent_revoked_at`, `deleted_at`, and `consent_given_at`, while the sweep uses `timezone.now()` (UTC-aware). If the server TZ ≠ UTC, the stored `consent_revoked_at` is interpreted in Postgres as the session TZ, shifting the 30-day boundary. Phase §7 calls out timezone skew on the 30-day window as a must-verify. Django best practice is to use `timezone.now()` everywhere.

**Evidence:**
- `deletion.py:54` — `now = datetime.now()`; lines 57-59, 114 use it.
- `consent_hard_delete.py:13,46` — `timezone.now()` (aware).
- `login.py:111` — correctly uses `timezone.now()`.

**Recommendation:** Replace `datetime.now()` with `timezone.now()` in `deletion.py`. Effort: trivial. Priority: recommended.

---

### PII-008: Raw `telegram_id` written to INFO logs

| Field | Value |
|-------|-------|
| **ID** | PII-008 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE (phase §d: no raw identifier in logs) |
| **Classification** | advisory |

**Description:** Phase §(d) requires no raw identifier/handle in logs/tracebacks. `account_state.py` logs `user.telegram_id` at INFO in four places; `contact.py` logs the buyer `telegram_id` ("Contact initiated event recorded for buyer {buyer_telegram_id}"). These leak the external auth identifier into application logs.

**Evidence:**
- `account_state.py:66,70,74,96` — `logger.info(f"User {user.telegram_id} ...")`.
- `contact.py:127` — `logger.info(f"Contact initiated event recorded for buyer {buyer_telegram_id}")`.

**Recommendation:** Log `user.id` (internal PK) instead of `telegram_id`; drop the raw telegram_id from the contact log line. Effort: trivial. Priority: recommended.

---

### PII-009: `User.__str__` and admin expose `telegram_id`

| Field | Value |
|-------|-------|
| **ID** | PII-009 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE (phase §d) |
| **Classification** | advisory |

**Description:** `User.__str__` returns `f"User {self.telegram_id or self.id}"`, so any string interpolation (admin change list repr, error messages, debug logs) emits the raw identifier. Admin `list_display`/`search_fields` also surface `telegram_id`. This is low severity (admin-restricted) but contradicts the "no raw identifier in logs" goal and the privacy-by-default posture.

**Evidence:**
- `models.py:99-100` — `__str__` includes `telegram_id`.
- `admin.py:20,34` — `telegram_id` in list_display/search_fields.

**Recommendation:** Change `__str__` to use `self.id` only; keep `telegram_id` in admin search if operationally needed but avoid printing it in repr/log paths. Effort: trivial. Priority: recommended.

---

### PII-010: `first_name`/`last_name` retained until hard-delete (not nulled on withdraw)

| Field | Value |
|-------|-------|
| **ID** | PII-010 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE (PII minimization) |
| **Classification** | advisory |

**Description:** `withdraw_consent` NULLs `telegram_id` and `username` immediately but leaves `first_name`/`last_name` (PII from AbstractUser) populated for the full 30-day window until the hard-delete removes the row. Spec decision F lists only `telegram_id`/`username` for nulling, but GDPR minimization argues for erasing name components at withdrawal too (they can still be surfaced via admin/error paths during the window). Not a hard violation of the documented spec, but a forward-looking gap.

**Evidence:**
- `deletion.py:62-63` — only `telegram_id` and `username` set to None.
- `models.py:24-25` (AbstractUser inheritance) — `first_name`/`last_name` retained.

**Recommendation:** Null `first_name` and `last_name` at withdrawal in `withdraw_consent()`, mirroring the existing `telegram_id`/`username` nulling. This aligns with GDPR data minimization principles and ensures PII is removed immediately rather than retained for 30 days. Effort: trivial. Priority: mandatory.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 9 | PII-001, PII-002, PII-003, PII-004, PII-005, PII-007, PII-008, PII-009, PII-010 |
| Reclassified | 1 | PII-006: DOC-UPDATE/dead-code → DOC-UPDATE |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

None. All findings were validated against the codebase and documentation.

### Merged Findings

None. No findings share the same root cause requiring consolidation.

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| PII-006 | DOC-UPDATE / dead-code | DOC-UPDATE | The code is correct (uses `consent_revoked_at` for sweep logic); only documentation is inaccurate. The implementation follows a simpler and valid approach. |

---

## Rollout Analysis

### PII-001 + PII-004 + PII-005 — Cross-Process Cascade Coordination

These findings reveal cross-process coordination issues:
- **PII-001**: Bot cannot detect withdrawn users because `telegram_id` is nulled
- **PII-004**: Physical media files not deleted during hard-delete sweep  
- **PII-005**: FSM state not purged on withdrawal

The bot runs in a separate process from the web. Fixing these requires:
1. PII-001 must be resolved first — the bot needs a reliable identity lookup that survives `telegram_id` nulling
2. PII-004 and PII-005 can then tie into the same lookup mechanism

**Risk:** High architectural impact. PII-001 requires either an immutable internal user identifier or an alternate lookup path.

---

### PII-002 + PII-006 — Documentation/Implementation Alignment

These findings stem from the same system design question:
- Is WITHDRAW intended as a user-accessible feature or admin-only?
- Should `hard_delete_at` field be removed or properly implemented?

Both should be resolved together to ensure the consent flow documentation matches the intended product behavior.

---

## Warnings

- **Architectural Risk:** PII-001 creates a security vulnerability where withdrawn users regain full bot access. This is a compliance failure.
- **Rollout Risk:** PII-005's FSM state purge requires cross-process signaling; MemoryStorage has no built-in broadcast mechanism.
- **Documentation Inconsistency:** `db-schema.md` and `technical-specification.md` describe `hard_delete_at` as a sweep target, but implementation uses `consent_revoked_at` directly.
