---
name: audit-findings
description: Structured findings template for audit phase output
agent: audit-executor
alwaysApply: false
---

# Phase 06 Audit Findings — PII Protection & Consent Compliance

**Executor:** audit-executor
**Template:** .kilo/commands/audit/phases/06-audit-pii-consent.md
**Status:** complete
**Validated:** no

> Note: Runtime verification (§4) was NOT executed. This audit environment is
> Windows (win32) without Docker/PostgreSQL, so the documented Docker compose
> stack could not be started. Findings below are from static discovery +
> review of the consent/PII test suite (`test_sweep_commands.py`,
> `test_contact.py`). The sweep/contact logic is covered by tests; the
> WITHDRAW trigger gap and bot identity-lookup gap are untested by any
> integration test. Recommend re-running §4 against a live stack before sign-off.

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

**Description:** The bot identifies a user by `telegram_id` and gates banned/deleted
users via `User.objects.get(telegram_id=telegram_id)`. `withdraw_consent` NULLs
`telegram_id` immediately (to "break chat linkage"). As a result a withdrawn user's
row can no longer be found by the bot's lookup: `get(telegram_id=<real_id>)` raises
`User.DoesNotExist`, which the middleware treats as "not registered yet" → returns
`(True, "")` → **full bot access is granted**. The `is_deleted` check
(`permissions.py:111`) is therefore unreachable for withdrawn users. The bot never
rejects a revoked/soft-deleted identity, violating phase §f (cross-process consent
consistency) and the consent banner covering the bot (spec decision K, line 93).

**Evidence:**
- `permissions.py:104-114` — `_check_user_state` returns `(True, "")` on `DoesNotExist`, so a withdrawn user (telegram_id=NULL) is treated as a brand-new, unrestricted user.
- `deletion.py:62` — `user.telegram_id = None` on WITHDRAW.
- `models.py:30,72` — `telegram_id` is `USERNAME_FIELD` and unique login key.

**Recommendation:** Decouple the gate from the mutable `telegram_id`. Persist an
immutable internal identity key (or a separate `consent_state`/`is_deleted` lookup by
a non-nullable id) and have the bot middleware reject `is_deleted`/`consent_revoked`
users even when `telegram_id` is NULL. At minimum, after NULLing `telegram_id`, keep
a separate indexed `banned_or_deleted` resolution path (e.g., a `LoginToken`-free
bot-side mapping keyed by a stable chat id that is cleared only at hard-delete).
Effort: medium. Priority: recommended (mandatory for compliance).

---

### PII-002: WITHDRAW path is unreachable from the UI/bot — withdrawal flow is dead code

| Field | Value |
|-------|-------|
| **ID** | PII-002 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/views/consent.py`, `src/backend/apps/users/urls.py`, `src/backend/apps/users/services/deletion.py` |
| **Classification** | mandatory |

**Description:** `withdraw_consent()` is defined and exported but is never invoked by
any view, URL, or bot handler. The consent banner exposes only ACCEPT
(`consent/accept/`) and DECLINE (`consent/decline/`). There is no `consent/withdraw/`
route, no admin action calls it, and the bot has no withdrawal entry point. The
entire consent-withdrawal + 30-day erasure flow documented in spec decision F/K and
zone R1/R3 is therefore unreachable through normal operation; the only way to set
`consent_revoked_at` is manual DB edits by a superuser. The consent hard-delete sweep
has tests, but nothing in the running system ever produces the rows it operates on.

**Evidence:**
- `urls.py:9-11` — only `accept` and `decline` routes; no withdraw.
- `consent.py:25,54` — only `consent_accept` and `consent_decline` exist.
- Grep for `withdraw_consent` returns only its definition + `__init__.py` export,
  never a caller (incl. admin actions in `users/admin.py`).
- `deletion.py:38` — `withdraw_consent` defined but orphaned.

**Recommendation:** Either (a) wire WITHDRAW into the consent banner/account page and
bot settings menu (recommended if the product intends to offer GDPR deletion to
users), or (b) if withdrawal is admin-only by design, update the spec/docs to say so
and add an explicit admin action that calls `withdraw_consent`. Per Dead-Code policy,
investigate the intended trigger before deleting. Effort: small (wire a view) / tiny
(doc update). Priority: recommended (mandatory for the documented GDPR flow).

---

### PII-003: DECLINE does not block seller login (spec requires it)

| Field | Value |
|-------|-------|
| **ID** | PII-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py`, `src/backend/apps/users/services/account_state.py`, `src/telegram_bot/middlewares/permissions.py`, `src/backend/apps/users/views/consent.py` |
| **Classification** | mandatory |

**Description:** Spec decision K (technical-specification.md:90) states: "DECLINE =
browse-only: blocks only seller login/actions." `decline_consent` only sets
`ads_auto_publish=False`. Web login uses Django auth keyed on `telegram_id`
(unchanged by DECLINE), and `can_login()` only checks `is_banned`. The bot middleware
restricts `/post` for `ads_auto_publish=False` but does not block login/other
commands. A declined seller can still log in to the dashboard and perform non-publish
seller actions. This diverges from the documented contract.

**Evidence:**
- `deletion.py:33-34` — DECLINE sets only `ads_auto_publish=False`.
- `account_state.py:80-99` (`can_login`) — returns True unless `is_banned`.
- `permissions.py:133` — bot only blocks `/post`, not login.
- `technical-specification.md:90` — "blocks only seller login/actions".

**Recommendation:** Decide the intended semantics. If DECLINE must block seller login,
add an explicit `is_declined`/`cannot_login` check to `can_login` (web) and to the
bot middleware, and reflect it in `AccountState`. If the spec is wrong, update the doc
to match current browse-only-publishing behavior. Effort: small. Priority: recommended.

---

### PII-004: Media files are never erased on consent hard-delete (orphaned PII on disk)

| Field | Value |
|-------|-------|
| **ID** | PII-004 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION + cross-cutting (phase §6) |
| **Affected Modules** | `src/backend/apps/core/management/commands/consent_hard_delete.py`, `src/telegram_bot/services/media.py`, `src/backend/apps/ads/models.py` |
| **Classification** | mandatory |

**Description:** `consent_hard_delete` deletes the User row, which ORM-CASCADEs to ads
and `ad_images` rows. However the actual JPEG files written to `MEDIA_ROOT`
(`ad_create.py:431-436`) are never `unlink`ed. No delete/storage-cleanup function
exists in `media.py` and a grep across the codebase finds no `.delete()`/`os.remove`/
`unlink` for media anywhere. The images remain on disk and are still served by nginx
`/media/` via their unguessable UUID key. Phase §6 explicitly states: "PII erasure →
media cascade: the erasure trigger here must also clear referenced media files."
This is unmet — the sweep erases DB rows but leaves the physical PII-bearing media.

**Evidence:**
- `consent_hard_delete.py:72` — `queryset.delete()` only removes ORM rows.
- `media.py` — no file-deletion helper (only `validate_*`, `generate_storage_key`).
- `ad_create.py:431-436` — files written with `open(media_path,"wb")`; no symmetric delete.
- `models.py:AdImage` — `on_delete=CASCADE` removes the row, not the file.

**Recommendation:** Add a media-cleanup step to the erasure cascade that, before/after
deleting `ad_images` rows, unlinks each `MEDIA_ROOT/<image>` file (and the orphaned
DRAFT photos, see PII-005). Keep it simple: iterate `AdImage` storage keys for the
target users and `os.remove` under `MEDIA_ROOT`. Effort: small. Priority: recommended.

---

### PII-005: Withdraw-mid-FSM not purged — DRAFT photos leaked, FSM state stale

| Field | Value |
|-------|-------|
| **ID** | PII-005 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE (cross-cutting edge case §7) |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py`, `src/telegram_bot/handlers/ad_create.py`, `src/telegram_bot/main.py` |
| **Classification** | mandatory |

**Description:** Edge case §7: "Seller withdraws mid-FSM-dialog (DRAFT + photos) →
DRAFT and photos purged, no residual PII." `withdraw_consent` calls
`soft_delete_user_ads`, which `UPDATE`s all ads (incl. DRAFT) to `DELETED`; the later
hard-delete CASCADEs the rows. But: (a) the in-progress `FSMContext` data held in the
bot's `MemoryStorage` is never cleared, so a half-built ad (title/description/price/
photo keys) survives in bot memory; (b) the DRAFT photos already written to disk are
never deleted (same gap as PII-004); (c) there is no signal/hook connecting
`withdraw_consent` to the bot at all, so a withdraw performed via the web leaves the
bot-side FSM completely unaware. Residual PII (photo bytes + draft text in memory) is
not purged.

**Evidence:**
- `deletion.py:79-102` — `soft_delete_user_ads` only flags ads; no FSM/memory or file cleanup.
- `ad_create.py:361-380` — DRAFT created/kept; bot has `delete_draft` but nothing calls it on withdraw.
- `main.py:26` — `MemoryStorage()` holds FSM state; no purge hook on withdrawal.
- No `post_save`/`pre_delete` signal links user withdrawal to bot FSM (grep: only moderation signals exist).

**Recommendation:** When a user is withdrawn, purge any DRAFT ads' media files and
clear the bot FSM state for that user (e.g., keyed by `user_id`). Given the bot runs
as a separate process, route the purge through a shared signal or a scheduled
reconciliation (sweep picks up DRAFT rows belonging to `is_deleted` users). Effort:
medium. Priority: recommended.

---

### PII-006: `hard_delete_at` is a dead/unused field contradicting docs

| Field | Value |
|-------|-------|
| **ID** | PII-006 |
| **Severity** | MEDIUM |
| **Type** | DOC-UPDATE / dead-code |
| **Affected Modules** | `src/backend/apps/users/models.py`, `src/backend/apps/users/admin.py`, `docs/02-database/db-schema.md` |
| **Classification** | advisory |

**Description:** `User.hard_delete_at` is documented (db-schema.md:52,60) as "Phase 4
30-day hard-delete sweep target." In reality the sweep filters on
`consent_revoked_at + 30d` and never reads or writes `hard_delete_at`. The field is
set nowhere, only displayed as a readonly admin field. It is dead schema and the docs
describe a mechanism the code does not implement.

**Evidence:**
- `models.py:65-69` — `hard_delete_at` defined, never written anywhere (grep confirms).
- `consent_hard_delete.py:46-51` — uses `consent_revoked_at__lt=cutoff_date`.
- `db-schema.md:52,60` — claims sweep targets `hard_delete_at`.

**Recommendation:** Remove the field (with a migration) and fix the doc, OR implement
it (set `hard_delete_at = consent_revoked_at + 30d` in `withdraw_consent` and have the
sweep filter on it). Simpler is to drop it and align docs. Effort: small. Priority:
recommended.

---

### PII-007: Mixed naive/aware timestamps risk timezone-skewed 30-day window

| Field | Value |
|-------|-------|
| **ID** | PII-007 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE (edge case §7 TZ skew) |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py` |
| **Classification** | advisory |

**Description:** `withdraw_consent` and `give_consent` use `datetime.now()` (naive,
server-local) for `consent_revoked_at`, `deleted_at`, and `consent_given_at`, while
the sweep uses `timezone.now()` (UTC-aware). If the server TZ ≠ UTC, the stored
`consent_revoked_at` is interpreted in Postgres as the session TZ, shifting the 30-day
boundary. Phase §7 calls out timezone skew on the 30-day window as a must-verify.
Django best practice is to use `timezone.now()` everywhere.

**Evidence:**
- `deletion.py:54` — `now = datetime.now()`; lines 57-59, 114 use it.
- `consent_hard_delete.py:13,46` — `timezone.now()` (aware).
- `login.py:111` — correctly uses `timezone.now()`.

**Recommendation:** Replace `datetime.now()` with `timezone.now()` in `deletion.py`.
Effort: trivial. Priority: recommended.

---

### PII-008: Raw `telegram_id` written to INFO logs

| Field | Value |
|-------|-------|
| **ID** | PII-008 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE (phase §d: no raw identifier in logs) |
| **Affected Modules** | `src/backend/apps/users/services/account_state.py`, `src/backend/apps/core/services/contact.py` |
| **Classification** | advisory |

**Description:** Phase §(d) requires no raw identifier/handle in logs/tracebacks.
`account_state.py` logs `user.telegram_id` at INFO in four places; `contact.py`
logs the buyer `telegram_id` ("Contact initiated event recorded for buyer
{buyer_telegram_id}"). These leak the external auth identifier into application logs.

**Evidence:**
- `account_state.py:66,70,74,96` — `logger.info(f"User {user.telegram_id} ...")`.
- `contact.py:127` — `logger.info(f"Contact initiated event recorded for buyer {buyer_telegram_id}")`.

**Recommendation:** Log `user.id` (internal PK) instead of `telegram_id`; drop the
raw telegram_id from the contact log line. Effort: trivial. Priority: recommended.

---

### PII-009: `User.__str__` and admin expose `telegram_id`

| Field | Value |
|-------|-------|
| **ID** | PII-009 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE (phase §d) |
| **Affected Modules** | `src/backend/apps/users/models.py`, `src/backend/apps/users/admin.py` |
| **Classification** | advisory |

**Description:** `User.__str__` returns `f"User {self.telegram_id or self.id}"`, so
any string interpolation (admin change list repr, error messages, debug logs) emits the
raw identifier. Admin `list_display`/`search_fields` also surface `telegram_id`. This
is low severity (admin-restricted) but contradicts the "no raw identifier in logs"
goal and the privacy-by-default posture.

**Evidence:**
- `models.py:99-100` — `__str__` includes `telegram_id`.
- `admin.py:21,35,62,64` — `telegram_id` in list/search fields.

**Recommendation:** Change `__str__` to use `self.id` only; keep `telegram_id` in
admin search if operationally needed but avoid printing it in repr/log paths. Effort:
trivial. Priority: recommended.

---

### PII-010: `first_name`/`last_name` retained until hard-delete (not nulled on withdraw)

| Field | Value |
|-------|-------|
| **ID** | PII-010 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE (PII minimization) |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py`, `src/backend/apps/users/models.py` |
| **Classification** | advisory |

**Description:** `withdraw_consent` NULLs `telegram_id` and `username` immediately but
leaves `first_name`/`last_name` (PII from AbstractUser) populated for the full 30-day
window until the hard-delete removes the row. Spec decision F lists only
`telegram_id`/`username` for nulling, but GDPR minimization argues for erasing name
components at withdrawal too (they can still be surfaced via admin/error paths during
the window). Not a hard violation of the documented spec, but a forward-looking gap.

**Evidence:**
- `deletion.py:62-63` — only `telegram_id` and `username` set to None.
- `models.py:24-25` (migration) — `first_name`/`last_name` retained.

**Recommendation:** Null `first_name`/`last_name` at withdrawal (mirror the
`telegram_id` handling), or document explicitly that names are retained until the
30-day hard-delete. Effort: trivial. Priority: recommended.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH | 3 |
| MEDIUM | 4 |
| LOW | 1 |

## Mandatory Fixes

- **PII-001** — Bot does not reject withdrawn users (telegram_id NULLed breaks lookup).
- **PII-002** — WITHDRAW path unreachable; GDPR withdrawal + 30-day erasure never triggered in normal operation.
- **PII-003** — DECLINE does not block seller login (spec requires it).
- **PII-004** — Media files never deleted on erasure (orphaned PII on disk).
- **PII-005** — Withdraw-mid-FSM leaves DRAFT photos + bot FSM state unpurged.

## Advisory Recommendations

- **PII-006** — Drop unused `hard_delete_at` field; align docs.
- **PII-007** — Use `timezone.now()` instead of `datetime.now()` in deletion service.
- **PII-008** — Remove raw `telegram_id` from INFO logs.
- **PII-009** — Stop exposing `telegram_id` in `User.__str__`/admin repr.
- **PII-010** — Null `first_name`/`last_name` on withdrawal (PII minimization).

## Doc Updates Needed

- **PII-002 / PII-006** — `docs/02-database/db-schema.md` (hard_delete_at described as sweep target; WITHDRAW described as user-reachable) must be reconciled with code, or code must implement the documented behavior.
- **PII-003** — `docs/01-spec/technical-specification.md:90` (DECLINE blocks seller login) vs current code (blocks publish only).
- **PII-010** — Decide and document whether name components are PII erased at withdrawal.

---
