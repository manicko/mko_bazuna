---
id: pii-consent-execution-plan
domain: plan
tags:
  - pii-consent
  - pc-001
  - pc-002
  - pc-003
  - pc-004
  - pc-005
  - pc-006
related:
  - docs/99-agent/architecture.md
  - .ai/audit/99-validation/06-pii-consent-validated-findings.md
---

# Phase 06 — PII Consent Execution DAG

**Source findings:** PC-001 through PC-006 (validated against the working tree).
**Scope:** 6 findings across 11 files, 3 test files created, 4 test files modified.
**Constraint:** Single Implementor per block; blocks execute strictly sequentially.

---

## Execution Graph (dependency-ordered)

```
Block 1  PC-004-model      AdImage.storage_keys()         [no deps]
Block 2  PC-005            IPv6 anonymization             [no deps]
Block 3  PC-001-ctx        consent_state flag forcing     [no deps]
Block 4  PC-001-del        consent_given_at in update_fields [no deps on code]
Block 5  PC-006            email in withdraw_consent       [Block 4]
Block 6  PC-004-softdel    storage_keys in soft_delete_user_ads [Block 1, Block 5]
Block 7  PC-004-hardcmd    storage_keys in consent_hard_delete  [Block 1]
Block 8  PC-002-bot        Bot gettext wrapping (3 files)   [no deps]
Block 9  PC-002+003-perm   permissions.py: i18n + state-specific + get_account_state [Block 8]
Block 10 PC-002-i18n       makemessages + compilemessages   [Blocks 8, 9]
Block 11 Verification     Full fast-gate + i18n completeness [all blocks]
```

---

## Block 1 — PC-004: AdImage.storage_keys() Model Method

**Finding:** PC-004 (mandatory, MEDIUM) — thumbnail derivatives orphaned on disk.

### Files to modify
- `src/backend/apps/ads/models.py` — add `storage_keys()` method to the `AdImage` class (after the existing `thumbnail_large_url` property, before `class AdFeature`).
  - Returns `list[str]` of all non-empty keys: `"image"` (always non-empty) + any set `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`.
  - Implementation: build a list starting with `self.image`, then append each non-null, non-empty thumbnail field. Filter out `None` and `""`.
  - No schema change; pure Python method.

### Test files
- **Create:** `src/backend/apps/ads/tests/test_adimage_storage_keys.py`
  - Unit tests (no DB): use `AdImage.__new__(AdImage)` pattern from `test_adimage_thumbnail_urls.py`.
  - `pytestmark = [pytest.mark.unit]`
  - Assert `storage_keys()` returns `["<image>"]` when no thumbnails set.
  - Assert returns all 4 keys when all thumbnails are set.
  - Assert returns only set keys when some thumbnails are `None` or `""`.
  - Cross-check: assert that `storage_keys()` is the union of `image` and the three `thumbnail_*` fields.

### Dependencies
- None. This is a pure additive model method.

### Dependencies it unblocks
- Block 6 (soft_delete_user_ads call-site)
- Block 7 (consent_hard_delete call-site)

### Risks
- **Low.** New method, no migration, no existing consumer changed. `delete_photo` already handles missing files (`FileNotFoundError` is terminal and swallowed).
- The method returns `list[str]` — call-sites must flatten, not yield a single string per row.

### Supporting agents
- **Implementor** (primary) — adds the method + test.
- **Validator** (post-block) — confirms `storage_keys()` exists via grep.

---

## Block 2 — PC-005: IPv6 Consent IP Anonymization

**Finding:** PC-005 (advisory, MEDIUM) — IPv6 addresses stored un-masked.

### Files to modify
- `src/backend/apps/users/services/consent_record.py` — rewrite `_anonymize_ip`:
  - Add `import ipaddress` at the top.
  - IPv4 path: keep existing behavior (zero last octet). Optionally refactor through `ipaddress` module for robustness.
  - IPv6 path: parse with `ipaddress.IPv6Address`, truncate to `/64` by zeroing the lower 80 bits, return `str()` of the resulting address.
  - `None` input: return `None` (unchanged).
  - Update the docstring to reflect IPv6 `/64` masking.
- `src/backend/apps/users/models.py` — update `ConsentRecord.ip_address` `help_text` from `"Anonymized IP (last IPv4 octet zeroed)"` to reflect both IPv4 `/24` and IPv6 `/64` masking.

### Test files
- **Modify:** `src/backend/apps/users/tests/test_consent_records.py`
  - Extend `test_ip_is_anonymized_and_ua_truncated` or add new test methods:
    - Test IPv6 input: `2001:db8:85a3::8a2e:370:7334` → masked to `/64` prefix (`2001:db8:85a3:0::`).
    - Test IPv4 still works: `192.168.1.100` → `192.168.1.0`.
    - Test `None` input → `None`.
  - Keep `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`.

### Dependencies
- None. Independent file (`consent_record.py` is not imported by any other target in this plan).

### Risks
- **Low.** Pure logic change in a single private function. No migration. `GenericIPAddressField` accepts IPv6 strings natively.
- IPv6 `/64` truncation: must use `ipaddress` module correctly — zero the lower 80 bits of the 128-bit address.

### Supporting agents
- **Implementor** (primary) — rewrites `_anonymize_ip` + updates help_text + tests.
- **Validator** — confirms IPv6 addresses are masked via test assertions.

---

## Block 3 — PC-001: Consent State Context Processor Fix

**Finding:** PC-001 (mandatory, HIGH) — analytics/preferences flags not zeroed for declined/withdrawn users.

### Files to modify
- `src/backend/apps/users/context_processors.py` — modify the `consent_state` function:
  - After computing `consent_shown` and before the `if consent_given_at is not None:` re-derivation branch, add an explicit guard:
    ```python
    if user.is_declined or user.consent_revoked_at is not None:
        consent_analytics = False
        consent_preferences = False
    ```
  - Place this guard inside the `if user is not None and user.is_authenticated:` block, before `if consent_given_at is not None:`.
  - The existing `else:` (anonymous branch) and the soft-deleted-user override are untouched.

### Test files
- **Modify:** `src/backend/apps/users/tests/test_consent_context.py`
  - Add a new test class `TestConsentTransition` (or extend `TestAuthenticatedState`):
    - `test_accepted_then_declined_disables_analytics`: user with `consent_given_at` set + `is_declined=True` → `consent_analytics is False`, `consent_preferences is False`.
    - `test_accepted_then_withdrawn_disables_analytics`: user with `consent_given_at` set + `consent_revoked_at` set → `consent_analytics is False`, `consent_preferences is False`.
  - The tests should set `consent_given_at` to a recent timestamp (within 12 months) to prove the bug would otherwise trigger `True`.

### Dependencies
- None. `context_processors.py` is consumed by Django template rendering; no other block modifies it.

### Risks
- **Medium.** This is the core of PC-001 — a logic change to the consent state that affects every page render. Incorrect placement could leave the Plausible tracker active for opted-out users.
- The existing `TestAuthenticatedState` tests (declined, deleted, accepted) must still pass — the guard is additive (sets to `False`, which is already the default unless the re-derivation branch sets `True`).

### Supporting agents
- **Implementor** (primary) — context processor fix + tests.
- **Test Engineer** — review test coverage for the transition scenarios.
- **Validator** — verify the Plausible gate in `detail.html` / `list.html` reads `consent_analytics` from context.

---

## Block 4 — PC-001: Clear consent_given_at in decline_consent / withdraw_consent

**Finding:** PC-001 (mandatory, HIGH) — `consent_given_at` omitted from `update_fields`.

### Files to modify
- `src/backend/apps/users/services/deletion.py`:
  - `decline_consent`: add `user.consent_given_at = None` before `save()`; add `"consent_given_at"` to `update_fields`.
  - `withdraw_consent`: add `user.consent_given_at = None` before `save()`; add `"consent_given_at"` to the `update_fields` list (currently `["consent_revoked_at", "is_deleted", "deleted_at", "telegram_id", "username", "first_name", "last_name"]`).

### Test files
- **Modify:** `src/backend/apps/users/tests/test_deletion.py`
  - In `TestDeclineConsentDoesNotInvalideTokens.test_decline_preserves_login_tokens`: assert `user.consent_given_at is None` after decline (when it was set beforehand).
  - In `TestWithdrawConsentInvalidatesTokens.test_withdraw_prevents_second_claim`: assert `user.consent_given_at is None` after withdraw.
  - Add a dedicated test: user with `consent_given_at` set → `decline_consent` → `consent_given_at` is `None`.
  - Add a dedicated test: user with `consent_given_at` set → `withdraw_consent` → `consent_given_at` is `None`.

### Dependencies
- None (code-wise). However, this block and Block 5 both modify `withdraw_consent` in `deletion.py`. Execute Block 4 **before** Block 5 to avoid `update_fields` list conflicts.

### Risks
- **Medium.** Touches the consent revocation/deletion critical path. The `consent_given_at = None` assignment must come before `save()`. The `update_fields` list must include the new field.
- `decline_consent` currently does NOT set `consent_given_at = None` — the implementor must add both the assignment and the `update_fields` entry.

### Supporting agents
- **Implementor** (primary) — code change + tests.
- **Validator** — confirm `update_fields` includes `consent_given_at` in both functions.

---

## Block 5 — PC-006: Null email in withdraw_consent

**Finding:** PC-006 (mandatory, MEDIUM) — `email` PII field not nulled on withdrawal.

### Files to modify
- `src/backend/apps/users/services/deletion.py` — `withdraw_consent` function:
  - Add `user.email = ""` before `save()` (alongside the existing `first_name`/`last_name` emptying).
  - Add `"email"` to the `update_fields` list.
  - No migration: `email` is inherited from `AbstractUser` as `EmailField(blank=True, default="")`, so empty string is valid.

### Test files
- **Modify:** `src/backend/apps/users/tests/test_deletion.py`
  - In `TestWithdrawConsentSoftDeletesAds.test_withdraw_triggers_user_soft_delete`: assert `user.email == ""` after withdraw.
  - Add a dedicated test: user with `email="admin@example.com"` → `withdraw_consent` → `user.email == ""`.
  - Verify this does not break `test_create_admin_user.py` (email is only set during admin provisioning; withdrawal only nulls it).

### Dependencies
- **Block 4** — both modify the same `update_fields` list in `withdraw_consent`. Block 4 adds `"consent_given_at"`, Block 5 adds `"email"`. Sequential to avoid merge conflicts in the `update_fields` list literal.

### Risks
- **Low.** Adding `"email"` to an existing `update_fields` list and setting it to `""` follows the established pattern for `first_name`/`last_name`. The `email` column is `NOT NULL` with `default ""` — setting `""` is safe. No migration required.
- The `consent_hard_delete` 30-day sweep physically deletes the row, so the `email` field is removed regardless — this fix closes the immediate-erasure window.

### Supporting agents
- **Implementor** (primary) — code change + tests.
- **Validator** — confirm `email` is in `update_fields` and `user.email = ""` is set before save.

---

## Block 6 — PC-004: storage_keys() in soft_delete_user_ads

**Finding:** PC-004 (mandatory, MEDIUM) — DRAFT-ad thumbnails orphaned.

### Files to modify
- `src/backend/apps/users/services/deletion.py` — `soft_delete_user_ads` function:
  - Replace the current DRAFT-ad storage key collection:
    ```python
    AdImage.objects.filter(ad_id__in=draft_ad_ids).values_list("image", flat=True)
    ```
  - With iteration over `AdImage` instances calling `.storage_keys()` on each:
    ```python
    draft_storage_keys = [
        key
        for img in AdImage.objects.filter(ad_id__in=draft_ad_ids)
        for key in img.storage_keys()
    ]
    ```
  - `delete_photo` is still called per key in `withdraw_consent` (unchanged call-site).

### Test files
- **Modify:** `src/backend/apps/users/tests/test_deletion.py`
  - In `TestWithdrawConsentSoftDeletesAds.test_withdraw_soft_deletes_user_ads` or `test_withdraw_returns_storage_keys`: extend the `AdImage.objects.create(...)` call to also set `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`, and assert all keys are in the returned list.
  - Add a dedicated test: `AdImage` with all thumbnails set → `withdraw_consent` returns all 4 keys and `delete_photo` is called for each.

### Dependencies
- **Block 1** (storage_keys method must exist).
- **Block 5** (same file, `deletion.py` — Block 5 touches `withdraw_consent`, Block 6 touches `soft_delete_user_ads`; both must not conflict. Sequential execution suffices.)

### Risks
- **Medium.** Changes the media cleanup path for DRAFT ads on consent withdrawal. The `values_list()` → list-comprehension-over-instances change is a different query pattern (fetches full rows instead of a single column). For DRAFT ads this is fine (small volume).
- Must use model instance iteration, not `values_list("storage_keys")` — `storage_keys()` is a Python method, not a DB column.

### Supporting agents
- **Implementor** (primary) — code change + tests.
- **Test Engineer** — review that the test covers all three thumbnail fields + the main image key.

---

## Block 7 — PC-004: storage_keys() in consent_hard_delete

**Finding:** PC-004 (mandatory, MEDIUM) — 30-day sweep misses thumbnails.

### Files to modify
- `src/backend/apps/core/management/commands/consent_hard_delete.py`:
  - Replace:
    ```python
    storage_keys = list(
        AdImage.objects.filter(ad__user_id__in=user_ids).values_list("image", flat=True)
    )
    ```
  - With:
    ```python
    storage_keys = [
        key
        for img in AdImage.objects.filter(ad__user_id__in=user_ids)
        for key in img.storage_keys()
    ]
    ```
  - The `delete_photo` loop (lines 89-90, outside the transaction) is unchanged.

### Test files
- **Modify:** `src/backend/apps/core/tests/test_sweep_commands.py` — `TestConsentHardDelete` class
  - Add a test: create a `User` with `consent_revoked_at` set >30 days ago, create an `Ad` + `AdImage` with `image` + all 3 `thumbnail_*` keys, monkeypatch `apps.core.management.commands.consent_hard_delete.delete_photo` to record calls, run `consent_hard_delete`, assert all 4 keys were passed to `delete_photo`.
  - The monkeypatch path must be `apps.core.management.commands.consent_hard_delete.delete_photo` (module-level import in the command file).

### Dependencies
- **Block 1** (storage_keys method).
- Not dependent on deletion.py changes (different file, different module).

### Risks
- **Low.** The `consent_hard_delete` sweep runs hourly on users past the 30-day grace period — not an immediate user-facing path. The change is mechanical: swapping one query pattern for another in the same function.
- The command's `delete_photo` is imported at module level, so tests monkeypatch via the module path.

### Supporting agents
- **Implementor** (primary) — code change + tests.
- **Test Engineer** — ensure the test verifies thumbnail keys reach `delete_photo`.

---

## Block 8 — PC-002: Bot i18n Wrapping (contact.py, login.py, language.py)

**Finding:** PC-002 (mandatory, HIGH) — bot strings not localized.

### Files to modify
- `src/telegram_bot/handlers/contact.py`:
  - Add `from django.utils.translation import gettext as _` import.
  - Wrap all user-facing string literals in `_()`:
    - `_CONTACT_US_GREETING` constant (lines 38-42).
    - `CONTACT_US_RATE_LIMITED_MESSAGE` constant (line 45-47).
    - `"Ошибка: не удалось определить отправителя"` (line 164).
    - `"объявление больше недоступно"` (line 176).
    - `"продавец больше недоступен для связи"` (line 180).
    - The `send_message` text block (lines 186-191).
    - `"Ваш запрос отправлен продавцу анонимно. Ожидайте ответа в этом чате."` (line 196).
    - `ANONYMOUS_BUYER_LABEL = "Покупатель"` (line 245) → `_("Покупатель")` as a callable or keep as constant (see note below).
  - **Note on `ANONYMOUS_BUYER_LABEL`:** This is used in an f-string for `bot.send_message`. Wrapping in `_()` at module level means the string is translated at import time (before Django's language activation). The bot must activate the user's `telegram_language` before sending. For the scope of PC-002, wrapping the constant in `_()` is acceptable — the implementor should also add `translation_activate` in the bot's request flow (see Block 9 / PC-003 for language context). **Implementation note:** Use `_("Покупатель")` and defer to `gettext` at call time if language activation is in scope; otherwise keep as a constant and document the limitation.

- `src/telegram_bot/handlers/login.py`:
  - Add `from django.utils.translation import gettext as _` import.
  - Wrap all user-facing string literals in `_()`:
    - The welcome message (line 50): `f"Welcome to {await get_site_name_async()}! ..."`. Note: `gettext` + f-string — the static part should be wrapped, the dynamic site name inserted via `.format()` or lazy interpolation. Recommendation: use `gettext("Welcome to %(site)s! To login, use a deep-link: /start login_<your_token>") % {"site": site_name}`.
    - `"Invalid login link format. Expected: /start login_<token>"` (line 81).
    - `"This login link is invalid, expired, or already used."` (line 98).
    - `"Login successful! Your account has been created. You can now create ads with /post."` (line 107).
    - `"Login successful! You can now create ads with /post."` (line 111).

- `src/telegram_bot/handlers/language.py`:
  - Add `from django.utils.translation import gettext as _` import.
  - Wrap user-facing strings in `_()`:
    - `"Please login first with /start login_<token>"` (line 38).
    - `"Select your preferred language:"` (line 44).
    - `"Unsupported language."` (line 61).
    - `"Please login first."` (line 67).
    - `f"Language set to {locale.value}"` (line 75) — wrap the static part.

### Test files
- **Modify:** `src/telegram_bot/tests/test_contact_us.py`
  - Assertions on `_CONTACT_US_GREETING` and `CONTACT_US_RATE_LIMITED_MESSAGE` will still pass because in test settings (`LANGUAGE_CODE = "en"`), `gettext()` returns the msgid (Russian text) unchanged. No test changes needed unless the msgid changes.
  - If the implementor changes message text (not just wrapping), update assertions accordingly.

- **Modify:** `src/telegram_bot/tests/test_login.py`
  - Currently asserts on token claim behavior, not message text. No changes expected. Verify no message-text assertions exist.

- **No new test file** for the wrapping itself — the i18n completeness gate (`test_i18n_completeness.py`, Block 10) covers extraction.

### Dependencies
- None. These are independent bot handler files.
- Does NOT touch `permissions.py` in this block — that is handled in **Block 9** (PC-002+PC-003 combined) to avoid double-touching the same file.

### Risks
- **Medium.** The `ANONYMOUS_BUYER_LABEL` constant is used in an f-string at `bot.send_message`. If wrapped in `_()` at module level, it translates at import time. The recommended approach: keep it as a module-level constant but wrap in `_()` so it's extractable by `makemessages`, and the bot process activates the user's language at runtime. **Decision point:** the implementor should use `_("Покупатель")` and document that language activation is needed (or keep the raw string and note it as a limitation).
- f-strings with `gettext`: Python 3.12+ allows `_(f"...")` but the translation must be on the literal, not the f-string. Use `gettext("static text") % {"var": value}` or `gettext("static text").format(site=site_name)` pattern instead.
- Existing test assertions in `test_contact_us.py` assert on exact Russian text. After wrapping in `_()`, in `en` test locale, `gettext("Привет!")` returns `"Привет!"` (the msgid). So tests pass unchanged.
- The `makemessages` extraction (Block 10) will fail if `gettext` is not properly imported or if strings are not wrapped correctly.

### Supporting agents
- **Implementor** (primary) — adds gettext imports + wraps strings.
- **Test Engineer** — reviews existing bot tests for fragile string assertions.

---

## Block 9 — PC-002 + PC-003: permissions.py i18n + get_account_state Refactor

**Finding:** PC-002 (permissions.py state-specific messages) + PC-003 (refactor to use shared `get_account_state`).

### Files to modify
- `src/telegram_bot/middlewares/permissions.py`:
  - Add `from django.utils.translation import gettext as _` import.
  - Add `from apps.users.services.account_state import get_account_state` import.
  - Rewrite `_check_user_state`:
    - Replace the inline `if user.is_banned: ... if user.is_deleted: ... if user.is_declined: ... if user.consent_revoked_at is not None: ...` chain with a single `state = get_account_state(user)` call, then map `AccountState` → `(can_interact, reason)`:
      ```python
      state = get_account_state(user)
      if state.is_banned:
          return (False, _("Your account is restricted. Contact support for assistance."))
      if state.is_deleted:
          return (False, _("Your account has been deleted."))
      if state.is_declined:
          return (False, _("Consent declined: browsing only, contact still works."))
      if state.consent_revoked:
          return (False, _("Consent withdrawn: your data is being erased."))
      return (True, "")
      ```
    - The `state_reason` returned by `_check_user_state` is passed to `message.answer(state_reason)` in `__call__` — unchanged.
  - The `_check_publish_permission` method also uses `ads_auto_publish` — it can optionally use `state.ads_auto_publish`, but PC-003's scope is `_check_user_state`. Keep `_check_publish_permission` as-is (or align it with `can_publish_ad` for consistency — document as a decision point).
  - Update the class docstring to reflect delegation to `get_account_state`.
  - **State-specific messages (PC-002 requirement):** DECLINE → browse-only + contact works; WITHDRAW → data being erased; BAN → account restricted. These three messages replace the current identical `"Your account has been deleted."` for all three states.

### Test files
- **Create:** `src/telegram_bot/tests/test_account_state_middleware.py`
  - Import `AccountStateMiddleware` and `get_account_state` from `apps.users.services.account_state`.
  - **Bot tests use `django_db(transaction=True)` + `pytest.mark.asyncio`** (per `test_login.py` convention; bot tests live outside `src/backend/conftest.py` hierarchy and have their own async `user` fixture).
  - Use the bot conftest's `user` fixture (telegram_id `900000100`).
  - Test cases:
    - Banned user → `(False, "restricted")` message contains "restricted".
    - Deleted user → `(False, ...)` message contains "deleted".
    - Declined user → `(False, ...)` message contains "browse-only" or "browsing only".
    - Withdrawn user (consent_revoked_at set) → `(False, ...)` message contains "erased" or "being erased".
    - Normal user → `(True, "")`.
    - **Cross-predicate agreement test:** for each flag combination, assert `_check_user_state` returns `(True, "")` if and only if `AccountStateMiddleware` and `can_login`/`can_publish_ad` agree. Specifically: `can_interact == True` iff `not state.is_banned and not state.is_deleted and not state.is_declined and not state.consent_revoked`.

### Dependencies
- **Block 8** (gettext must be imported in permissions.py before state-specific messages are wrapped; the messages in Block 9 include `_()` calls).
- The shared `get_account_state` function (`apps/users/services/account_state.py`) already exists and is tested (`test_account_state.py`) — no new dependency.

### Risks
- **Medium.** The `_check_user_state` method is the core access-control gate for all bot interactions. Refactoring from inline flag checks to `get_account_state` changes behavior only if `get_account_state` differs from the inline checks. Per the validated findings, `get_account_state` returns `AccountState(is_banned=..., is_deleted=..., is_declined=..., ads_auto_publish=..., consent_revoked=(consent_revoked_at is not None))` — semantically identical to the inline checks.
- **State-specific messages change user-facing text.** Any existing test asserting on the old `"Your account has been deleted."` message will break. Grep confirms no existing test asserts on these denial messages (no `test_permissions.py` exists).
- `_check_publish_permission` still uses `user.ads_auto_publish` directly. If the implementor aligns it with `get_account_state`, that's a bonus; if not, ensure the `ads_auto_publish=False` path for non-banned/deleted/declined/withdrawn users still returns the publish restriction message (now also wrapped in `_()`).

### Supporting agents
- **Implementor** (primary) — code refactor + new test file.
- **Test Engineer** — design the cross-predicate agreement test.
- **Validator** — confirm no other file in `src/telegram_bot` imports from `permissions.py` or asserts on the old denial messages.

---

## Block 10 — PC-002: i18n Extraction & Compilation

**Finding:** PC-002 (mandatory, HIGH) — `makemessages` + `compilemessages`.

### Action items
1. Run `make makemessages` (or equivalent `uv run python src/backend/manage.py makemessages -l ru -l bs -l en --no-location`).
   - This scans all `.py` files under the container's WORKDIR (`/app`, which includes `src/telegram_bot/`), extracts new `gettext` msgids, and merges them into the three `.po` files.
2. Fill in non-empty `msgstr` for every new msgid in `ru` and `bs` `.po` files (the `test_no_empty_msgstr` guard requires this).
   - `en` `.po` may have empty `msgstr` (msgid is English).
3. Run `make compilemessages` (or `uv run python src/backend/manage.py compilemessages --locale ru --locale bs --locale en`).
   - Produces `.mo` files (required by `test_mo_compiled` guard).
4. Run `test_i18n_completeness.py` to verify all 4 guards pass.

### Files affected (generated, not hand-edited)
- `src/backend/locale/ru/LC_MESSAGES/django.po` — new msgids + ru translations.
- `src/backend/locale/bs/LC_MESSAGES/django.po` — new msgids + bs translations.
- `src/backend/locale/en/LC_MESSAGES/django.po` — new msgids (empty msgstr OK).
- `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.mo` — compiled (gitignored).

### Test files
- **No new test.** The gate is `apps/ads/tests/test_i18n_completeness.py` (4 tests, `@pytest.mark.unit`).

### Dependencies
- **Blocks 8 and 9** — all `gettext` calls must exist before `makemessages` runs.
- **Block 10 depends on every code change** that introduces `gettext` calls.

### Risks
- **Low.** Extraction and compilation are non-destructive. `makemessages` merges into existing `.po` files (preserves existing translations). `compilemessages` overwrites `.mo` files.
- **Translation completeness:** `test_no_empty_msgstr` fails if any new msgid has empty `msgstr` in `ru` or `bs`. All new bot strings need translations. The `.po` files already have ~100+ entries with translations; new entries must be consistent in style.
- **.po file conflicts:** If multiple implementors edit the same `.po` file, merge conflicts may arise. Only one Implementor works at a time, so this is mitigated by sequential execution.

### Supporting agents
- **Implementor** (primary) — runs makemessages, fills translations, runs compilemessages.
- **Docs Specialist** — if documentation (e.g., `language.py` docstring) needs updating to reflect that localization is now wired.
- **Validator** — runs `test_i18n_completeness.py` and confirms `POT-Creation-Date` is updated.

---

## Block 11 — Verification

**No new code changes.** Runs the full fast-gate test suite + i18n completeness gate.

### Commands
```powershell
# 1. Start test DB (if not running)
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db

# 2. Run fast gate (skips seed suite)
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed test

# 3. Run i18n completeness gate (no DB needed)
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm test pytest apps/ads/tests/test_i18n_completeness.py -v

# 4. Lint + typecheck (in dev container)
docker compose --project-name mko-bazuna-dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check src/
docker compose --project-name mko-bazuna-dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run basedpyright src/telegram_bot src/backend/apps/users src/backend/apps/ads
```

### Test files to verify
- `src/backend/apps/users/tests/test_consent_context.py` — transition tests (Block 3)
- `src/backend/apps/users/tests/test_deletion.py` — consent_given_at + email clearing (Blocks 4, 5, 6)
- `src/backend/apps/ads/tests/test_adimage_storage_keys.py` — new storage_keys tests (Block 1)
- `src/backend/apps/users/tests/test_consent_records.py` — IPv6 anonymization (Block 2)
- `src/backend/apps/core/tests/test_sweep_commands.py` — consent_hard_delete thumbnail coverage (Block 7)
- `src/backend/apps/ads/tests/test_i18n_completeness.py` — i18n gate (Block 10)
- `src/telegram_bot/tests/test_account_state_middleware.py` — new permissions refactor test (Block 9)
- `src/telegram_bot/tests/test_contact_us.py` — existing tests still pass (Block 8)
- `src/telegram_bot/tests/test_login.py` — existing tests still pass (Block 8)

### Dependencies
- All preceding blocks.

### Risks
- **Low.** Verification only — no code changes. If any test fails, the responsible block's implementor is revisited.

### Supporting agents
- **Validator** (primary) — runs full suite + gates.
- **Implementor** — addresses any failures.

---

## Execution Order Summary

| Order | Block | Finding | File(s) modified | Test file(s) | Risk |
|-------|-------|---------|-------------------|-------------|------|
| 1 | Block 1 | PC-004-model | `ads/models.py` | **create** `test_adimage_storage_keys.py` | Low |
| 2 | Block 2 | PC-005 | `consent_record.py`, `users/models.py` | modify `test_consent_records.py` | Low |
| 3 | Block 3 | PC-001-ctx | `context_processors.py` | modify `test_consent_context.py` | Medium |
| 4 | Block 4 | PC-001-del | `deletion.py` (decline/withdraw) | modify `test_deletion.py` | Medium |
| 5 | Block 5 | PC-006 | `deletion.py` (withdraw email) | modify `test_deletion.py` | Low |
| 6 | Block 6 | PC-004-softdel | `deletion.py` (soft_delete_user_ads) | modify `test_deletion.py` | Medium |
| 7 | Block 7 | PC-004-hardcmd | `consent_hard_delete.py` | modify `test_sweep_commands.py` | Low |
| 8 | Block 8 | PC-002-bot | `contact.py`, `login.py`, `language.py` | modify `test_contact_us.py` | Medium |
| 9 | Block 9 | PC-002+003-perm | `permissions.py` | **create** `test_account_state_middleware.py` | Medium |
| 10 | Block 10 | PC-002-i18n | `.po`/`.mo` files (generated) | gate: `test_i18n_completeness.py` | Low |
| 11 | Block 11 | — | — | all of the above | Low |

### Key ordering constraints
1. **Block 1 → Blocks 6, 7:** `storage_keys()` must exist before call-sites use it.
2. **Block 4 → Block 5:** Both modify `withdraw_consent`'s `update_fields` list; sequential to avoid list conflict.
3. **Blocks 4+5 → Block 6:** All three modify `deletion.py`; Block 6 touches a different function (`soft_delete_user_ads`), but sequential execution avoids review friction.
4. **Block 8 → Block 9:** `permissions.py` needs `gettext` import from the i18n wrapping pattern established in Block 8.
5. **Blocks 8+9 → Block 10:** `makemessages` must see all `gettext` calls before extraction.
6. **All code blocks → Block 11:** Verification runs after all changes.
```