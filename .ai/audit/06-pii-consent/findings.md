---
name: audit-findings
description: Phase 06 PII & Consent Compliance findings (problems-only)
agent: audit-executor
alwaysApply: false
---

# Phase 06 Audit Findings — PII Protection & Consent Compliance

**Executor:** audit-executor
**Phase Template:** `.kilo/commands/audit/phases/06-audit-pii-consent.md`
**Status:** complete
**Validated:** no
**Scope reviewed:** consent models · consent/deep-link views · ad PII masking in search/listing · `consent_hard_delete` command · i18n of PII strings

Method: static discovery (grep/read ≤60-line ranges) + targeted evidence. No production changes made.

---

## Findings

### PC-001: DECLINE/WITHDRAW never clear `consent_given_at`, so analytics (Plausible) fire for revoked/declined users

| Field | Value |
|-------|-------|
| **ID** | PC-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py`, `src/backend/apps/users/context_processors.py`, `src/backend/templates/ads/detail.html` (+ `list.html`) |
| **Classification** | mandatory |

**Description:** The spec requires DECLINE to reject analytics (PO-02 / §4.1) and WITHDRAW to erase PII immediately (§4.2). But `decline_consent` (`deletion.py:63-67`) sets only `ads_auto_publish`/`is_declined` and `withdraw_consent` (`deletion.py:141-149`) lists `update_fields = [consent_revoked_at, is_deleted, deleted_at, telegram_id, username, first_name, last_name]` — **neither clears `consent_given_at`**. The consent context processor (`context_processors.py:59-76`) then re-derives `consent_analytics`/`consent_preferences` purely from `consent_given_at`, ignoring `is_declined`/`consent_revoked_at`: for any authenticated user who previously *Accepted* the banner and later Declined/Withdrew, `consent_given_at` is still fresh, so `consent_analytics` is set back to `True`. `detail.html:17` (`{% if consent_analytics %}`) then injects the Plausible tracker on pages the user explicitly opted out of — a GDPR analytics-consent violation and a breach of §1/§5d (identity data flowed into analytics after revocation). Contact gating is correctly blocked (telegram_id NULL / revoked_at set), so this is narrower than a contact leak, but the analytics gate is honored neither web-side nor consistent with the cookies the views set.

**Evidence:**
- `src/backend/apps/users/services/deletion.py:63-67` (decline — no consent_given_at reset)
- `src/backend/apps/users/services/deletion.py:141-150` (withdraw `update_fields` omits `consent_given_at`)
- `src/backend/apps/users/context_processors.py:59-76` (`consent_analytics` derived from `consent_given_at` only)
- `src/backend/apps/users/context_processors.py:95-96` (deletion users force `consent_shown=True` but analytics still derived from stale given_at)
- `src/backend/templates/ads/detail.html:17-21` (`{% if consent_analytics %}` injects Plausible)
- Web cookies are correct (`consent.py:199-204` sets analytics=false on decline), but the **server-side** template gate ignores them for authenticated users.

**Recommendation:** Treat consent as a one-way gate on the server: when `is_declined` or `consent_revoked_at` is set, force `consent_analytics=False` and `consent_preferences=False` in the context processor (and clear `consent_given_at` inside `decline_consent`/`withdraw_consent`). This decouples the cookie banner state from the server-side Plausible injection. Effort: small. Priority: recommended.
### PC-002: Bot consent/contact-denial messages are not localized and use identical wording for DECLINE, WITHDRAW, and ban states

| Field | Value |
|-------|-------|
| **ID** | PC-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/handlers/contact.py`, `src/telegram_bot/middlewares/permissions.py`, `src/telegram_bot/handlers/login.py`, `src/telegram_bot/handlers/language.py` |
| **Classification** | mandatory |

**Description:** The bot ships a `/language` UX and a `User.telegram_language` field (`language.py:5-7` promises localized "alert messages and other bot output" across ru/en/bs), but **zero** `gettext`/translation calls exist anywhere under `src/telegram_bot` (no `gettext`, no `aiogram_i18n`, no `.po` catalog). User-facing consent/contact strings are hardcoded and language-mixed: `contact.py` uses Cyrillic (`"Покупатель"` at `:155`, `"объявление больше недоступно"` at `:86`, `"продавец больше недоступен для связи"` at `:90`), while `permissions.py` and `login.py` use English. Worse, the bot reports three semantically distinct consent states with the **same** message: `is_deleted` (`:115`), `is_declined` (`:118`), and `consent_revoked_at` (`:121`) all return `"Your account has been deleted."`. This violates DECLINE≠WITHDRAW (§5a: DECLINE is browse-only with data retained and contact still functional; WITHDRAW erases and must be distinguishable) and i18n DoD rule #16. A user who only Declined (no erasure) is told their account "has been deleted," misrepresenting the data fate, and the message language ignores their `/language` choice.

**Evidence:**
- `src/telegram_bot/handlers/contact.py:74,86,90,98,106-107,155` (hardcoded Cyrillic contact denials + `ANONYMOUS_BUYER_LABEL`)
- `src/telegram_bot/middlewares/permissions.py:112,115,118,121,145` (English, identical strings for 3 states)
- `src/telegram_bot/handlers/login.py:49,71,88,97-98,101` (English welcome/rejection text)
- `src/telegram_bot/handlers/language.py:5-7` (promised localization never implemented)
- Negative grep: no `gettext`/`gettext_lazy`/`aiogram_i18n`/`trans` matches in `src/telegram_bot`
- Contrast with web: `consent_banner.html:11-76`, `footer.html:7-9`, `detail.html` fully `{% trans %}`-wrapped

**Recommendation:** Route every bot user-facing string through Django `gettext` (the bot process calls `django.setup()` and can share the existing ru/en/bs `.po` catalog), select language from `User.telegram_language` (default `ru`), and make denial messages state-specific: Decline → "consent declined; browsing only, contact still works", Withdraw → "consent withdrawn; data is being erased", Ban → "account restricted". Effort: medium. Priority: recommended.
### PC-003: Bot `AccountStateMiddleware` reimplements account-state logic instead of reusing the shared `get_account_state` predicate

| Field | Value |
|-------|-------|
| **ID** | PC-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/middlewares/permissions.py`, `src/backend/apps/users/services/account_state.py` |
| **Classification** | advisory |

**Description:** The bot enforces consent/account state by **reimplementing** the ban/delete/decline/revoke checks inline in `_check_user_state` (`permissions.py:93-123`), rather than calling the canonical shared predicate `apps.users.services.account_state.get_account_state` (`account_state.py:26-48`) that the web layer relies on. The bot duplicates the same five-flag matrix (`is_banned`, `is_deleted`, `is_declined`, `ads_auto_publish`, `consent_revoked_at`) in two branches (`_check_user_state` + `_check_publish_permission`). This is a latent cross-process-consistency defect (§5f/§4.6 require identical consent state honored on both sides): any future consent/account flag added via `get_account_state` for the web will not be reflected in the bot until someone updates the duplicated block, silently breaking "revocation reflects immediately on both sides." There is currently no test asserting the bot predicate and the shared predicate agree on the same `User` row.

**Evidence:**
- `src/telegram_bot/middlewares/permissions.py:111-123` (inline reimplementation; imports only `User` model, never `get_account_state`)
- `src/telegram_bot/middlewares/permissions.py:125-148` (`_check_publish_permission` rechecks `ads_auto_publish` separately)
- `src/backend/apps/users/services/account_state.py:26-48` (the shared, web-reused `AccountState` predicate)
- No `from apps.users.services.account_state import` in `src/telegram_bot/` (grep negative)

**Recommendation:** Import and delegate to `get_account_state(user)` from the middleware (map `AccountState` → `(can_interact, reason)`), eliminating the second implementation. Add a regression test asserting `AccountStateMiddleware` rejects the exact same identity states as `can_login`/`can_publish_ad` for a shared fixture user. Effort: small. Priority: recommended.
### PC-004: Media erasure cascade is incomplete — thumbnail derivatives are orphaned on disk

| Field | Value |
|-------|-------|
| **ID** | PC-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/core/management/commands/consent_hard_delete.py`, `src/backend/apps/users/services/deletion.py`, `src/backend/apps/ads/models.py`, `src/telegram_bot/services/media.py` |
| **Classification** | mandatory |

**Description:** Both the immediate withdrawal path and the 30-day hard-delete sweep erase only the **main** `AdImage.image` storage key and never the generated thumbnail derivatives. `AdImage` stores three separate thumbnail keys (`thumbnail_small`/`thumbnail_medium`/`thumbnail_large`, `ads/models.py:539-555`, named `<uuid>-small/-medium/-large.jpg`), but:
- `withdraw_consent` → `soft_delete_user_ads` (`deletion.py:198-202`) collects `AdImage.objects.filter(...).values_list("image", flat=True)` — main key only — then calls `delete_photo` per key.
- `consent_hard_delete` (`consent_hard_delete.py:69-73`) collects the same `image`-only values and deletes only those.
- `delete_photo` (`media.py:85-123`) removes exactly one file path.

So every withdrawn user's ad images leaves 3 orphaned thumbnail files on disk indefinitely, surviving the entire 30-day erasure window and the hard-delete. This is a PII/data-remanence gap (§5b "associated data purged" / §7 edge case "Media cascade incomplete on erasure") — image content of a GDPR-withdrawn identity persists on the media store after the DB row is gone, and the files are no longer referenced by any row, so a future accidental re-listing cannot reclaim them.

**Evidence:**
- `src/backend/apps/users/services/deletion.py:191-205` (`values_list("image", flat=True)`; never reads `thumbnail_*`)
- `src/backend/apps/core/management/commands/consent_hard_delete.py:69-73` (same `image`-only collection)
- `src/backend/apps/ads/models.py:539-555` (the three thumbnail column definitions)
- `src/telegram_bot/services/media.py:101` (`os.remove` of a single key)

**Recommendation:** Have `AdImage` expose a `storage_keys()` returning all non-empty keys (`image` + any set `thumbnail_*`), and use it in both `soft_delete_user_ads` and `consent_hard_delete` so `delete_photo` runs for every derivative. Alternatively, delete by UUID prefix so `<uuid>-small.jpg` is caught. Effort: small. Priority: recommended.
### PC-005: IPv6 consent IPs are stored un-masked despite the "anonymized IP" contract

| Field | Value |
|-------|-------|
| **ID** | PC-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/users/services/consent_record.py`, `src/backend/apps/users/models.py` |
| **Classification** | advisory |

**Description:** `ConsentRecord.ip_address` documents itself as "Anonymized IP (last IPv4 octet zeroed)" (`users/models.py:238-242`), and the spec (§5d) requires no raw identity in analytics/logs. `_anonymize_ip` (`consent_record.py:18-28`) correctly zero-masks IPv4 but **returns IPv6 addresses unchanged** (the function's own comment says "IPv6 addresses are returned unchanged (no reliable in-band masking)"). A full IPv6 address is far more identifying than an IPv4 /24 (a /64 subnet can pinpoint a user's LAN/ISP), so any consent action from an IPv6-only client is stored in full in `consent_records` — a GDPR data-minimization shortfall that contradicts the field's contract and §8 MEDIUM ("Analytics/logs store raw identity in text").

**Evidence:**
- `src/backend/apps/users/services/consent_record.py:18-28` (`_anonymize_ip`: IPv4 masked, IPv6 passthrough)
- `src/backend/apps/users/services/consent_record.py:59` (stored into `ConsentRecord.ip_address`)
- `src/backend/apps/users/models.py:238-242` (field help_text promises anonymization)

**Recommendation:** For IPv6, zero the low 80 bits to /64 (or truncate to the /64 prefix) before storage — matching the IPv4 `/24`-equivalent granularity — and update the field help_text to reflect the IPv6 policy. Effort: trivial. Priority: recommended.
### PC-006: Withdrawal/hard-delete do not null the inherited `email` PII field

| Field | Value |
|-------|-------|
| **ID** | PC-006 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py`, `src/backend/apps/users/models.py`, `src/backend/apps/users/admin.py`, `src/backend/apps/core/management/commands/create_admin_user.py` |
| **Classification** | mandatory |

**Description:** The `User` model extends `AbstractUser`, which carries an `email` field never overridden or nulled. `withdraw_consent` documents "NULLs telegram_id, username immediately" (`deletion.py:85-86`) and its `update_fields` (`deletion.py:141-150`) lists exactly `consent_revoked_at, is_deleted, deleted_at, telegram_id, username, first_name, last_name` — **`email` is omitted**. `email` is in fact populated for real identities: `create_admin_user.py:111` sets `email=email` when provisioning admin accounts (and `test_create_admin_user.py:66-70` asserts `user.email == "admin@example.com"`). Consequently, a withdrawn identity retains their `email` in the `users` row for the full 30-day grace period (and is only removed by the physical row deletion at hard-delete, not by the immediate PII nulling the spec requires at §4.2). This is an incomplete-PII nulling defect for a field populated downstream of bot registration.

**Evidence:**
- `src/backend/apps/users/services/deletion.py:134-150` (`update_fields` omits `email`; first/last name emptied but email untouched)
- `src/backend/apps/users/models.py:7,24-32` (`class User(AbstractUser)`; `email` not overridden)
- `src/backend/apps/core/management/commands/create_admin_user.py:111` (`email=email` set at provisioning)
- `src/backend/apps/users/tests/test_create_admin_user.py:70` (`assert user.email == "admin@example.com"`)

**Recommendation:** Either drop `email` as a login/contact field for this Telegram-first model (override `email = None` on `User`), or add `email` to the `update_fields` in `withdraw_consent` (and confirm it is nulled before hard-delete) so PII nulling matches the documented contract at §4.2. Effort: small. Priority: recommended.
---

## Summary

6 findings filed against Phase 06 (PII & Consent). Coverage spans all five requested surfaces: consent models (PC-006), consent/deep-link views + analytics-consent enforcement (PC-001), `consent_hard_delete` + withdrawal erasure (PC-004, PC-006), and i18n of PII/consent-gating strings (PC-002, PC-003). Ad PII masking in public search/listing was verified clean: `listings`/`search` filter to `PUBLISHED`, public templates expose no seller `telegram_id`/`username`/`first_name`/`last_name` (contact is via `contact_<ad.id>` deep-link only), and `AnalyticsEvent` stores identity by FK only — no raw-handle leakage (no finding).

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 3 (PC-001, PC-002, PC-003) |
| MEDIUM | 3 (PC-004, PC-005, PC-006) |
| LOW | 0 |

## Mandatory Fixes

- **PC-001** — clear `consent_given_at` on decline/withdraw and force `consent_analytics=False` server-side (Plausible injection bypasses the banner on the server).
- **PC-002** — localize all bot user-facing strings via gettext and emit state-specific denial messages (Decline/Withdraw/ban must be distinguishable).
- **PC-004** — erase `thumbnail_small/medium/large` derivative files in both withdrawal and the 30-day sweep.
- **PC-006** — null `email` (or remove the field) on withdrawal so PII nulling matches the §4.2 contract for admin-provisioned accounts.

## Advisory Recommendations

- **PC-003** — have `AccountStateMiddleware` delegate to the shared `get_account_state` predicate to prevent cross-process drift; add a regression test.
- **PC-005** — mask IPv6 to /64 in `_anonymize_ip` to honor the "anonymized IP" contract.

## Doc Updates Needed

- `language.py:5-7` over-promises localized bot output; update to reflect current state until gettext is wired.
- `consent_banner.md` / DoD should state bot strings must be in the shared `django` translation catalog.

---

**Status:** complete · **Findings: 6** (3 HIGH, 3 MEDIUM, 0 CRITICAL, 0 LOW)
