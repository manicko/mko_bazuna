# Phase 06 Audit Findings — PII Protection & Consent Compliance (VALIDATED)

**Executor:** audit-executor
**Template:** `.kilo/commands/audit/phases/06-audit-pii-consent.md`
**Status:** complete
**Validated:** yes

> **Validator scope note:** This report validates the six findings in
> `06-pii-consent/findings.md` (PC-001–PC-006) against the current working tree
> (`src/backend`, `src/telegram_bot`, `docs/01-spec`, `docs/02-database`, and
> `src/**/tests`). All six findings were reproduced via targeted `grep` + file
> reads of the cited code. No source code was modified. The spec section
> references (§4.1, §4.2, §5a/§5b/§5d, §8) in the original findings point to an
> external/master spec not present in this repo; validation therefore relies on
> the repo's own spec (`docs/01-spec/technical-specification.md`,
> `docs/01-spec/spec-index.md`, `docs/97-plans/consent-banner-gdpr-research-report.md`)
> and on direct code reproduction. All six claims hold against the implementation.

---

## Findings

### PC-001: DECLINE/WITHDRAW never clear `consent_given_at`, so analytics (Plausible) fire for revoked/declined users

| Field | Value |
|-------|-------|
| **ID** | PC-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION → [SPEC-DEVIATION] (validated) |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py`, `src/backend/apps/users/context_processors.py`, `src/backend/templates/ads/detail.html` (+ `list.html`) |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced in full. `decline_consent` (`deletion.py:63-67`) sets `ads_auto_publish=False` and `is_declined=True` with `update_fields=["ads_auto_publish", "is_declined"]` — `consent_given_at` is never cleared. `withdraw_consent` (`deletion.py:140-149`) saves `update_fields=["consent_revoked_at", "is_deleted", "deleted_at", "telegram_id", "username", "first_name", "last_name"]` — `consent_given_at` is omitted. The context processor (`context_processors.py:68-76`) then sets `consent_analytics=True` whenever `consent_given_at is not None` and not expired (12 months), **without** checking `is_declined` or `consent_revoked_at`. For any authenticated user who previously *Accepted* and later Declined/Withdrew, `consent_given_at` remains set, so `consent_analytics` is still `True`. The soft-deleted-user override at `context_processors.py:94-96` only sets `consent_shown=True` — it does **not** zero `consent_analytics`, so withdrawn users still get the Plausible tracker injected. `detail.html:17-21` and `list.html:12` both gate the Plausible `<script>` on `{% if consent_analytics and PLAUSIBLE_HOST %}`. The web-side cookies ARE correct (`views/consent.py:186` sets `analytics=False` for decline, `:244-245` for withdraw) — but the server-side context processor ignores cookies for authenticated users and re-derives `consent_analytics` from the stale `consent_given_at`. The spec confirms the intent: `technical-specification.md:85` (DECLINE ≠ WITHDRAW, decision F/K) and `technical-specification.md:95` (Plausible gated behind `consent_analytics`). The test suite does **not** cover this transition: `test_consent_context.py:105-118` tests declined and deleted states in isolation but never sets `consent_given_at` before declining/deleting, so `consent_analytics` stays at its default `False` and the bug escapes detection.
> - **Evidence-quality issue:** The finding cites `context_processors.py:95-96` for the soft-deleted-user override; the actual lines are **94-96** (the `if` guard starts at line 94). Also, the cookie file path is `src/backend/apps/users/views/consent.py` (the finding's `consent.py` shorthand is correct but path-qualified). These do not affect validity.

**Description:** The spec requires DECLINE to reject analytics (§4.1) and WITHDRAW to erase PII immediately (§4.2). But `decline_consent` (`deletion.py:63-67`) sets only `ads_auto_publish`/`is_declined` and `withdraw_consent` (`deletion.py:141-149`) lists `update_fields = [consent_revoked_at, is_deleted, deleted_at, telegram_id, username, first_name, last_name]` — **neither clears `consent_given_at`**. The consent context processor (`context_processors.py:59-76`) then re-derives `consent_analytics`/`consent_preferences` purely from `consent_given_at`, ignoring `is_declined`/`consent_revoked_at`: for any authenticated user who previously *Accepted* the banner and later Declined/Withdrew, `consent_given_at` is still fresh, so `consent_analytics` is set back to `True`. `detail.html:17` (`{% if consent_analytics %}`) then injects the Plausible tracker on pages the user explicitly opted out of.

**Evidence (reproduced against code):**
- `deletion.py:63-67` — `decline_consent`: `user.ads_auto_publish = False; user.is_declined = True; user.save(update_fields=["ads_auto_publish", "is_declined"])` — confirmed no `consent_given_at` reset.
- `deletion.py:140-149` — `withdraw_consent`: `update_fields` list confirmed to omit `consent_given_at`.
- `context_processors.py:61-76` — authenticated branch: `consent_given_at = user.consent_given_at` (line 61); `if consent_given_at is not None:` → `consent_analytics = True` (line 68-74) — no `is_declined`/`consent_revoked_at` check before setting analytics.
- `context_processors.py:94-96` — `if user.is_authenticated and user.is_deleted: consent_shown = True` — sets only `consent_shown`, leaves stale `consent_analytics`.
- `detail.html:17-21` — `{% if consent_analytics and PLAUSIBLE_HOST %}` injects Plausible `<script>` — confirmed.
- `list.html:12` — same Plausible gate — confirmed.
- `views/consent.py:186, 199-204` — `consent_decline` sets `analytics=False` and writes cookie `"false"` — web cookies correct; server-side gate ignores them for authenticated users.

**Recommendation:** Treat consent as a one-way gate on the server: when `is_declined` or `consent_revoked_at` is set, force `consent_analytics=False` and `consent_preferences=False` in the context processor, and clear `consent_given_at` inside `decline_consent`/`withdraw_consent`. Decouple the cookie banner state from the server-side Plausible injection. Effort: small. Priority: recommended.

---

### PC-002: Bot consent/contact-denial messages are not localized and use identical wording for DECLINE, WITHDRAW, and ban states

| Field | Value |
|-------|-------|
| **ID** | PC-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/handlers/contact.py`, `src/telegram_bot/middlewares/permissions.py`, `src/telegram_bot/handlers/login.py`, `src/telegram_bot/handlers/language.py` |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced in full. (1) Negative grep for `gettext`/`gettext_lazy`/`aiogram_i18n` across all of `src/telegram_bot/**/*.py` returns **zero matches** — no translation infrastructure exists in the bot. (2) `contact.py` hardcodes Cyrillic user-facing strings at lines 74 (`"Ошибка: не удалось определить отправителя"`), 86 (`"объявление больше недоступно"`), 90 (`"продавец больше недоступен для связи"`), 97-100 (the `send_message` text block — `"Новый запрос от покупателя!"` / `"Покупатель:"`), 106 (`"Ваш запрос отправлен продавцу анонимно. Ожидайте ответа в этом чате."`), 155 (`ANONYMOUS_BUYER_LABEL = "Покупатель"`). (3) `permissions.py:115` (`is_deleted`), `:118` (`is_declined`), and `:121` (`consent_revoked_at`) all return the **identical** string `"Your account has been deleted."` — three semantically distinct states with one message. The spec requires DECLINE ≠ WITHDRAW (`technical-specification.md:85`, `spec-index.md:72-74`): DECLINE is browse-only with data retained and contact still functional; WITHDRAW erases. (4) `login.py` hardcodes English strings at lines 49, 71, 88, 97-98, 101. (5) `language.py` docstring (lines 4-7) promises localized "alert messages and other bot output" but no `gettext`/translation call exists to fulfill this. The bot process calls `django.setup()` (`telegram_bot/main.py:10`) and shares the Django settings, so it has access to the existing ru/en/bs `.po` catalog — but uses none of it. Contrast with the web layer, where `detail.html` and `consent_banner.html` use `{% load i18n %}` and `{% trans %}` tags throughout.

**Original description (reproduced against code):**
Bot consent/contact-denial messages are hardcoded, language-mixed (Cyrillic in `contact.py`, English in `permissions.py`/`login.py`), and three distinct account states return the identical denial string.

**Evidence (reproduced against code):**
- `contact.py:74,86,90,98,106-107,155` — all hardcoded Cyrillic.
- `permissions.py:112` (`is_banned` → English), `:115` (`is_deleted` → `"Your account has been deleted."`), `:118` (`is_declined` → same), `:121` (`consent_revoked_at` → same).
- `login.py:49,71,88,97-98,101` — all hardcoded English.
- `language.py:5-7` — docstring promises localization that is never implemented.
- Negative grep: no `gettext`/`gettext_lazy`/`aiogram_i18n`/`trans` in `src/telegram_bot/` (confirmed: zero matches).
- Web contrast: `detail.html:5` (`{% load i18n %}`), `consent_banner.html` fully `{% trans %}`-wrapped.

**Recommendation:** Route every bot user-facing string through Django `gettext` (the bot process calls `django.setup()` and can share the existing ru/en/bs `.po` catalog), select language from `User.telegram_language` (default `ru`), and make denial messages state-specific. Effort: medium. Priority: recommended.

---

### PC-003: Bot `AccountStateMiddleware` reimplements account-state logic instead of reusing the shared `get_account_state` predicate

| Field | Value |
|-------|-------|
| **ID** | PC-003 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/telegram_bot/middlewares/permissions.py`, `src/backend/apps/users/services/account_state.py` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced. `permissions.py` imports only `from apps.users.models import User` (line 16) — no import of `get_account_state`. Negative grep for `get_account_state|account_state` across `src/telegram_bot/**/*.py` returns **zero matches**. The `_check_user_state` method (lines 93-123) reimplements the same five-flag matrix (`is_banned`, `is_deleted`, `is_declined`, `consent_revoked_at`, `ads_auto_publish`) inline, and `_check_publish_permission` (lines 125-148) re-checks `ads_auto_publish` separately. The shared predicate `apps.users.services.account_state.get_account_state` (`account_state.py:26-48`) returns an `AccountState` NamedTuple with all five flags and is used by the web layer's `can_login` (line 96) and `can_publish_ad` (line 66). The bot's duplicated implementation means any future consent/account flag added to `get_account_state` for the web will not be reflected in the bot. The spec requires both sides to honor identical consent state (`technical-specification.md:96`: "Banner covers bot too — no separate bot confirmation"). No test asserts agreement between the bot's `_check_user_state` and the shared `get_account_state` predicate.

**Original description (reproduced against code):**
The bot enforces consent/account state by reimplementing the ban/delete/decline/revoke checks inline, rather than calling the canonical shared predicate.

**Evidence (reproduced against code):**
- `permissions.py:16` — `from apps.users.models import User` only; no `get_account_state` import.
- `permissions.py:111-123` — inline `_check_user_state` reimplements all five flags.
- `permissions.py:125-148` — `_check_publish_permission` re-checks `ads_auto_publish` separately.
- `account_state.py:26-48` — the shared `get_account_state` returning `AccountState` NamedTuple.
- Negative grep: no `get_account_state|account_state` in `src/telegram_bot/` (confirmed: zero matches).

**Recommendation:** Import and delegate to `get_account_state(user)` from the middleware, mapping `AccountState` → `(can_interact, reason)`, eliminating the duplicate implementation. Add a regression test asserting agreement. Effort: small. Priority: recommended.

---

### PC-004: Media erasure cascade is incomplete — thumbnail derivatives are orphaned on disk

| Field | Value |
|-------|-------|
| **ID** | PC-004 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/core/management/commands/consent_hard_delete.py`, `src/backend/apps/users/services/deletion.py`, `src/backend/apps/ads/models.py`, `src/telegram_bot/services/media.py` |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced. `AdImage` stores three thumbnail columns (`thumbnail_small`, `thumbnail_medium`, `thumbnail_large`, `ads/models.py:539-555`) named `<uuid>-small/-medium/-large.jpg`, but both erasure paths collect only the main `image` key:
>   - `soft_delete_user_ads` (`deletion.py:198-202`): `AdImage.objects.filter(ad_id__in=draft_ad_ids).values_list("image", flat=True)` — `image` only.
>   - `consent_hard_delete` (`consent_hard_delete.py:69-73`): `AdImage.objects.filter(ad__user_id__in=user_ids).values_list("image", flat=True)` — `image` only.
>   Both then call `delete_photo(storage_key)` per key (`media.py:85`), which removes exactly one file (`os.remove(path)` at line 104; `path = os.path.join(...)` at line 101). No code path ever reads `thumbnail_small`/`thumbnail_medium`/`thumbnail_large` for deletion. The `AdImage` model has no `storage_keys()` helper (only `image_url`, `thumbnail_small_url`, etc. properties at lines 594-614). The spec's erasure contract requires associated data purged (`consent-banner-gdpr-research-report.md:43` tracks `consent_given_at`/`is_declined`/`consent_revoked_at`; `technical-specification.md:93` describes the 30-day PII erasure path reading `consent_revoked_at`). The `delete_photo` function itself has retry/error-handling (contradicting no claim about that — that is a Phase-05 concern), but it is only ever called with `image` keys, never thumbnail keys.
> - **Evidence-quality issue:** The finding cites `media.py:101` for the `os.remove` call; the actual `os.remove(path)` is at **line 104** (line 101 is `path = os.path.join(...)`). Also, `ads/models.py:539-555` should be `:539-556` (the `thumbnail_large` closing paren is at line 556). These offsets do not affect validity.

**Original description (reproduced against code):**
Both the immediate withdrawal path and the 30-day hard-delete sweep erase only the main `AdImage.image` storage key and never the generated thumbnail derivatives (`thumbnail_small`/`thumbnail_medium`/`thumbnail_large`).

**Evidence (reproduced against code):**
- `deletion.py:198-202` — `values_list("image", flat=True)` only; `thumbnail_*` never read.
- `consent_hard_delete.py:69-73` — same `image`-only collection.
- `ads/models.py:539-555` — three `thumbnail_*` CharField definitions confirmed (actual close-parens at 544, 550, 556).
- `media.py:101,104` — `delete_photo` builds single `path` (line 101) and calls `os.remove` once (line 104); no thumbnail expansion.
- `delete_photo` (lines 85-123) has its own try/except + retry; the gap is that it is never called with thumbnail keys.

**Recommendation:** Have `AdImage` expose a `storage_keys()` method returning all non-empty keys (`image` + any set `thumbnail_*`), and use it in both `soft_delete_user_ads` and `consent_hard_delete` so `delete_photo` runs for every derivative. Effort: small. Priority: recommended.

---

### PC-005: IPv6 consent IPs are stored un-masked despite the "anonymized IP" contract

| Field | Value |
|-------|-------|
| **ID** | PC-005 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/users/services/consent_record.py`, `src/backend/apps/users/models.py` |
| **Classification** | advisory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced. `_anonymize_ip` (`consent_record.py:18-28`): `if "." in ip:` masks the last IPv4 octet (`.split(".")` → rejoin with `["0"]`); the fall-through `return ip` (line 28) returns IPv6 addresses unchanged (IPv6 uses `:` not `.`, so the `if` branch is never entered). The function's own docstring (lines 19-22) states: "IPv6 addresses are returned unchanged (no reliable in-band masking)." The result is stored at line 59: `ip_address=_anonymize_ip(request.META.get("REMOTE_ADDR") or None)` into `ConsentRecord.ip_address`. The model field (`users/models.py:238-242`) is `GenericIPAddressField` with `help_text="Anonymized IP (last IPv4 octet zeroed)"` — promising anonymization but only covering IPv4. A full IPv6 address (/64+ subnet) is more identifying than an IPv4 /24. The spec §8 ("raw identity in logs") and `consent-banner-gdpr-research-report.md:211` (anonymized IP) contract is violated for IPv6-only clients. No masking for IPv6 exists in any code path.

**Original description (reproduced against code):**
`ConsentRecord.ip_address` documents itself as "Anonymized IP (last IPv4 octet zeroed)" but `_anonymize_ip` correctly masks IPv4 and returns IPv6 addresses unchanged.

**Evidence (reproduced against code):**
- `consent_record.py:18-28` — `_anonymize_ip`: IPv4 branch (lines 25-27) masks last octet; fall-through `return ip` (line 28) for IPv6.
- `consent_record.py:59` — `_anonymize_ip(...)` stored into `ConsentRecord.ip_address`.
- `users/models.py:238-242` — field `help_text="Anonymized IP (last IPv4 octet zeroed)"`.

**Recommendation:** For IPv6, zero the low 80 bits to /64 (or truncate to the /64 prefix) before storage, matching the IPv4 `/24`-equivalent granularity. Update the field `help_text` to reflect the IPv6 policy. Effort: trivial. Priority: recommended.

---

### PC-006: Withdrawal/hard-delete do not null the inherited `email` PII field

| Field | Value |
|-------|-------|
| **ID** | PC-006 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/users/services/deletion.py`, `src/backend/apps/users/models.py`, `src/backend/apps/users/admin.py`, `src/backend/apps/core/management/commands/create_admin_user.py` |
| **Classification** | mandatory |

> **Validation Note:**
> - **Action:** validated (unchanged)
> - **Detail:** Reproduced. `withdraw_consent` (`deletion.py:140-149`) nulls `telegram_id`, `username`, sets `first_name=""`, `last_name=""`, but `update_fields` omits `email`. The `User` model (`users/models.py:13`) extends `AbstractUser` and does **not** override `email` — it is inherited as `EmailField(blank=True, default="")`. `create_admin_user.py:111` sets `email=email` when provisioning admin accounts (the `--email` arg defaults to `""` at line 50, but can be set to a real address). The test `test_create_with_email` confirms this: `test_create_admin_user.py:66` passes `email="admin@example.com"` and line 70 asserts `user.email == "admin@example.com"`. Because `email` is never added to `withdraw_consent`'s `update_fields`, an admin-provisioned account's email survives the immediate PII-nulling window (and is only removed by physical row deletion at the 30-day hard-delete, not by the immediate nulling the spec §4.2 requires). The `give_consent` function (`deletion.py:224-264`) also never touches `email`, confirming `email` is entirely unmanaged across the consent lifecycle. The spec's DECLINE ≠ WITHDRAW contract (`technical-specification.md:85`) and the erasure path (`technical-specification.md:93`) support the finding that PII should be purged immediately on WITHDRAW.
> - **Evidence-quality issue:** The finding cites `src/backend/apps/users/tests/test_create_admin_user.py:66-70`, but the actual file is at `src/backend/apps/core/tests/test_create_admin_user.py` (the command lives in `apps.core`, not `apps.users`). The test content and assertions are confirmed at the actual path. Also, `users/models.py:24-32` covers the `username` field override (with the comment at line 24), not `email` per se — the finding's parenthetical "(email not overridden)" is correct by omission, but the cited line range should more precisely state "Lines 7-13 declare `AbstractUser` import and `class User(AbstractUser):`; no `email` field appears in the class body (lines 13-149)."

**Original description (reproduced against code):**
The `User` model extends `AbstractUser`, which carries an `email` field never overridden or nulled. `withdraw_consent` documents "NULLs telegram_id, username immediately" but its `update_fields` omits `email`.

**Evidence (reproduced against code):**
- `deletion.py:140-149` — `update_fields=["consent_revoked_at", "is_deleted", "deleted_at", "telegram_id", "username", "first_name", "last_name"]` — confirmed `email` absent.
- `users/models.py:7` — `from django.contrib.auth.models import AbstractUser`.
- `users/models.py:13` — `class User(AbstractUser):` — scan of the full class body (lines 13-149) confirms no `email =` field declaration; `email` is inherited from `AbstractUser` (`models.EmailField(blank=True, default="")`).
- `create_admin_user.py:111` — `email=email,` in `User.objects.create(...)`.
- `core/tests/test_create_admin_user.py:66` — `email="admin@example.com"` passed; `:70` — `assert user.email == "admin@example.com"`.

**Recommendation:** Either drop `email` as a login/contact field for this Telegram-first model (override `email = None` on `User`), or add `email` to the `update_fields` in `withdraw_consent` so PII nulling matches the documented contract §4.2. Effort: small. Priority: recommended.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 3 (PC-001, PC-002, PC-003) |
| MEDIUM | 3 (PC-004, PC-005, PC-006) |
| LOW | 0 |

All six findings reproduced against the current working tree. No findings rejected, recategorized, or merged.

## Mandatory Fixes

- **PC-001** (HIGH): Clear `consent_given_at` on decline/withdraw, and force `consent_analytics=False` / `consent_preferences=False` server-side in the context processor when `is_declined` or `consent_revoked_at` is set.
- **PC-002** (HIGH): Route all bot user-facing strings through Django `gettext`; emit state-specific denial messages for DECLINE/WITHDRAW/ban.
- **PC-004** (MEDIUM): Delete `thumbnail_small`/`medium`/`large` derivative files in both `soft_delete_user_ads` and `consent_hard_delete`.
- **PC-006** (MEDIUM): Null `email` (or remove the field) on withdrawal so PII nulling matches the §4.2 contract.

## Advisory Recommendations

- **PC-003** (HIGH→advisory): Have `AccountStateMiddleware` delegate to the shared `get_account_state` predicate to prevent cross-process drift; add a regression test.
- **PC-005** (MEDIUM): Mask IPv6 to /64 in `_anonymize_ip` to honor the "anonymized IP" contract.

## Doc Updates Needed

- `language.py:5-7` over-promises localized bot output; update to reflect current state until gettext is wired.
- `consent_banner.md` / DoD should state bot strings must be in the shared `django` translation catalog.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 6 | PC-001, PC-002, PC-003, PC-004, PC-005, PC-006 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

_None._ All six findings were verified against the current working tree and found technically correct, currently applicable, and architecturally sound. No stale, duplicate, or low-ROI findings.

### Merged Findings

_None._ All six findings have distinct root causes:
- PC-001 + PC-002 share an i18n/consent theme but are distinct (server-side analytics gating vs. bot string localization).
- PC-001 + PC-006 share a deletion-service theme but are distinct (`consent_given_at` vs `email` nulling).
- PC-004 + PC-006 share a media/PII-erasure theme but are distinct (thumbnail files vs `email` field).

### Reclassified Findings

_None._ PC-005 (BEST-PRACTICE) was evaluated for rejection as low-ROI but is retained: IPv6 masking is a trivial code change with clear GDPR data-minimization value and a matching field-contract fix. All other findings retain their original classifications.

## Cross-Finding Analysis

- **PC-001 ↔ PC-002 (shared consent/i18n surface):** Both relate to consent enforcement, but PC-001 is about server-side analytics gating (web templates) while PC-002 is about bot string localization/denial messages. Distinct root causes; no merge.
- **PC-001 ↔ PC-006 (shared `deletion.py` service):** Both are in `withdraw_consent` (`deletion.py`) — PC-001 omits `consent_given_at` from `update_fields`, PC-006 omits `email`. These are independent fields with independent consequences (analytics leak vs. PII retention); no merge appropriate.
- **PC-003 ↔ PC-006 (shared account-state surface):** PC-003 is about the bot middleware duplicating `get_account_state`; PC-006 is about `email` not nulled. Orthogonal concerns.
- **PC-004 ↔ Phase 05 (media deletion):** Phase 05's AL-004 was rejected because `delete_photo` (`media.py:85-123`) already has per-file try/except + retry + logging and never raises. PC-004 depends on this same `delete_photo` — its gap is not error handling (already covered) but **call-site coverage**: `delete_photo` is never called with thumbnail keys. Resolving PC-004's root cause (collecting `storage_keys()` including `thumbnail_*`) would reuse the existing robust `delete_photo`, so there is no conflict with AL-004.
- **No cross-phase conflicts** were introduced. No other phase asserts contradictory claims about consent `update_fields`, bot localization, or thumbnail erasure.

## Rollout Safety

- **PC-001 (mandatory, HIGH):** Two-part fix. (a) Add `consent_given_at` to `update_fields` in `decline_consent` and `withdraw_consent` — atomic, single-row writes; no ordering dependency. (b) Update `consent_state` context processor to force `consent_analytics=False` / `consent_preferences=False` when `is_declined` or `consent_revoked_at is not None` — pure logic change, evaluated per request. No circular dependencies; no hidden consumers. Safe. **Rollout ordering:** the context-processor fix must precede (or accompany) removing `consent_given_at` from any re-derivation path; both should ship together to avoid a window where `consent_given_at` is cleared but `consent_analytics` still re-derives from a non-null value.
- **PC-002 (mandatory, HIGH):** Adding `gettext` to bot strings and the ru/en/bs `.po` compilation is independent of other phases. State-specific denial messages require no schema or migration changes. The bot calls `django.setup()`, so it shares the same translation catalog as the web layer. No ordering dependency.
- **PC-004 (mandatory, MEDIUM):** Adding `storage_keys()` to `AdImage` and collecting `thumbnail_*` keys in both `soft_delete_user_ads` (DRAFT path only) and `consent_hard_delete` (30-day sweep). Both call sites use the existing `delete_photo` with its retry/log handling. No circular dependency; `AdImage` model change is additive (new method, no new fields). Safe. **Rollout ordering:** the `consent_hard_delete` sweep must run after the `AdImage.storage_keys()` method is deployed; both are in the same release, no migration required.
- **PC-006 (mandatory, MEDIUM):** Two options: (a) override `email = None` on `User` (requires a migration to drop the column), or (b) add `email` to `update_fields` in `withdraw_consent` (no migration). Option (b) is lower-risk. Either way, no circular dependency. If option (a) is chosen, verify all admin provisioning paths don't set `email`.
- No unsafe insertion points, circular dependencies, or hidden dependency chains were detected.

## Execution Validation

| Finding | Targets still exist? | Static verified? | Rollback feasible? | Ready for execution |
|---------|----------------------|------------------|--------------------|---------------------|
| PC-001 | Yes — `deletion.py:63-67,140-149`; `context_processors.py:59-76,94-96`; `detail.html:17-21`; `list.html:12` | Yes (file reads + greps) | Yes — revert `update_fields` list and context processor logic | Yes |
| PC-002 | Yes — `contact.py:74,86,90,98,106,155`; `permissions.py:112,115,118,121,145`; `login.py:49,71,88,97-101`; `language.py:5-7` | Yes (file reads + negative grep) | Yes — revert string wrapping; .po files unaffected | Yes |
| PC-003 | Yes — `permissions.py:16,93-123,125-148`; `account_state.py:26-48` | Yes (file reads + negative grep) | Yes — revert import/delegation + re-add inline checks | Yes |
| PC-004 | Yes — `deletion.py:198-202`; `consent_hard_delete.py:69-73`; `ads/models.py:539-556`; `media.py:85-123` | Yes (file reads) | Yes — revert `storage_keys()` method + `values_list` change | Yes |
| PC-005 | Yes — `consent_record.py:18-28,59`; `users/models.py:238-242` | Yes (file reads) | Yes — revert masking logic + help_text | Yes |
| PC-006 | Yes — `deletion.py:140-149`; `users/models.py:7,13`; `create_admin_user.py:111`; `test_create_admin_user.py:66,70` | Yes (file reads) | Yes — both options reversible | Yes |

All cited targets remain present in the working tree and were read in full. All six findings are ready for execution.

## Warnings

- **Test-coverage gap (PC-001):** `test_consent_context.py` (`TestAuthenticatedState`, lines 105-118) tests `is_declined` and `is_deleted` states in isolation but never sets `consent_given_at` beforehand, so it does not exercise the "accept→decline/withdraw" transition where the bug manifests. A regression test covering `consent_given_at` set + `is_declined=True` → `consent_analytics == False` (and the withdraw equivalent) should be added before or alongside the fix.
- **Evidence-quality issues (no impact on validity):** PC-001 cites `context_processors.py:95-96` (actual: 94-96); PC-004 cites `media.py:101` for `os.remove` (actual: line 104) and `ads/models.py:539-555` (actual: 539-556); PC-006 cites `users/tests/test_create_admin_user.py` (actual: `core/tests/test_create_admin_user.py`). These are line-number or path offsets that do not change any finding's conclusion.
- **Spec-section references:** The findings reference §4.1, §4.2, §5a/§5b/§5d, §8 from an external/master spec document not present in this repo's `docs/` tree. The repo's own spec documents (`technical-specification.md`, `spec-index.md`, `consent-banner-gdpr-research-report.md`) confirm the same intent (DECLINE ≠ WITHDRAW, analytics consent-gated, PII purged on withdrawal), so the section references do not affect validation conclusions.
- **No architectural integrity, maintainability, rollout, or dependency risks** were detected beyond what the six findings describe.

## Required Fixes

1. **PC-001** (mandatory): In `withdraw_consent` and `decline_consent` (`deletion.py`), add `consent_given_at` to the `update_fields` list (clear it on decline/withdraw). In `consent_state` (`context_processors.py`), force `consent_analytics=False` and `consent_preferences=False` when `user.is_declined` or `user.consent_revoked_at is not None`, **before** the `consent_given_at` re-derivation branch. Add a regression test in `test_consent_context.py` for the "accepted→declined" transition.

2. **PC-002** (mandatory): Wrap all bot user-facing strings in `gettext`/`gettext_lazy` (bot shares Django's `.po` catalog via `django.setup()`). Make denial messages state-specific: DECLINE → browse-only + contact still works; WITHDRAW → "data is being erased"; BAN → "account restricted". Add `gettext` import to `contact.py`, `permissions.py`, `login.py`, `language.py`. Run `make makemessages` + `make compilemessages`.

3. **PC-004** (mandatory): Add `AdImage.storage_keys()` returning `["image"] + [thumbnail_* for each set]`, then replace `values_list("image", flat=True)` with `values_list("storage_keys", flat=True)` — or collect all four keys — in both `soft_delete_user_ads` (`deletion.py`) and `consent_hard_delete.py`.

4. **PC-006** (mandatory): Add `email` to `withdraw_consent`'s `update_fields` (line 141-149) and set `user.email = ""` (or `None` if nullable) before save. Decide whether to keep `email` null vs empty-string based on `AbstractUser`'s `EmailField(blank=True)`.

### Advisory Recommendations

1. **PC-003:** Import `get_account_state` from `apps.users.services.account_state` in `permissions.py`; map `AccountState` → `(can_interact, reason)` to eliminate the inline reimplementation in `_check_user_state`; add a regression test asserting the bot middleware and the shared predicate agree on the same `User` row.
2. **PC-005:** Extend `_anonymize_ip` to mask IPv6 to /64 (zero the low 80 bits) using `ipaddress` module; update `ConsentRecord.ip_address` `help_text` to reflect the IPv6 policy.
