---
id: pii-consent-execution-dag
domain: plan
tags:
  - pii-consent
  - pc-001
  - pc-002
  - pc-003
  - pc-004
  - pc-005
  - pc-006
  - i18n
  - block-10
  - block-11
related:
  - docs/99-agent/architecture.md
  - docs/99-agent/rules.md
  - .kilo/plans/phase-06-pii-consent-execution-dag.md
  - src/backend/apps/ads/tests/test_i18n_completeness.py
---

# PII Consent — Execution DAG (Post-Commit Decommissioning)

**Source findings:** PC-001 through PC-006 (validated against working tree at `7ed761c`).
**Status snapshot:** Blocks 1–9 are **committed**. Block 10 (i18n extraction/compilation) and Block 11 (verification) are **remaining**.

---

## 1. Execution Graph (dependency-ordered)

```
Block 1  PC-004-model     ✅ Committed  — AdImage.storage_keys()            [no deps]
Block 2  PC-005           ✅ Committed  — IPv6 /64 masking                    [no deps]
Block 3  PC-001-ctx       ✅ Committed  — consent_state flag forcing          [no deps]
Block 4  PC-001-del       ✅ Committed  — consent_given_at in update_fields   [no deps]
Block 5  PC-006           ✅ Committed  — email=null in withdraw              [Block 4]
Block 6  PC-004-softdel   ✅ Committed  — storage_keys() in soft_delete_user_ads [Block 1,5]
Block 7  PC-004-hardcmd   ✅ Committed  — storage_keys() in consent_hard_delete  [Block 1]
Block 8  PC-002-bot       ✅ Committed  — Bot gettext wrapping (3 files)      [no deps]
Block 9  PC-002+003-perm  ✅ Committed  — permissions.py: i18n + get_account_state [Block 8]
Block 10 PC-002-i18n      ⏳ Remaining  — makemessages + fill + compilemessages  [Blocks 8,9]
Block 11 Verification    ⏳ Remaining  — Full fast-gate + i18n completeness   [all blocks]
```

All 9 commits verified in git log (`8d78ab2` → `7ed761c`). Block 10 is the sole remaining implementation block; Block 11 is verification only.

---

## Blocks 1–9 — Status: COMMITTED (Verification Summary)

No further work required. Details below confirm each block is fully implemented and tested.

### Block 1 — PC-004: `AdImage.storage_keys()` Model Method

- **Commit:** `8d78ab2`
- **File:** `src/backend/apps/ads/models.py` — `AdImage.storage_keys()` at line 622
- **Returns:** `list[str]` — `image` + non-empty `thumbnail_small`/`thumbnail_medium`/`thumbnail_large`
- **Test file:** `src/backend/apps/ads/tests/test_adimage_storage_keys.py` (5 unit tests, `pytest.mark.unit`)
- **Verified:** `storage_keys()` present; test file exists with 5 test methods covering all-4-keys, image-only, partial, and truthy-filter cross-check.

### Block 2 — PC-005: IPv6 Consent IP Anonymization

- **Commit:** `eaf5795`
- **File:** `src/backend/apps/users/services/consent_record.py` — `_anonymize_ip()` uses `ipaddress.IPv6Address`, bitmask `& (0xFFFFFFFFFFFFFFFF << 64)`, returns `str()` for IPv6 /64 truncation
- **Also:** `src/backend/apps/users/models.py` — `ConsentRecord.ip_address` `help_text` updated to `"Anonymized IP (IPv4 last octet zeroed; IPv6 /64 prefix retained)"` (line 241)
- **Test file:** `src/backend/apps/users/tests/test_consent_records.py` — `TestAnonymizeIp` class (lines 81–95) with `test_ipv6_masked_to_64_prefix`, `test_ipv4_last_octet_zeroed`, `test_none_input_returns_none`
- **Verified:** IPv6 `"2001:db8:85a3::8a2e:370:7334"` → `"2001:db8:85a3::"`; IPv4 `"192.168.1.100"` → `"192.168.1.0"`; `None` → `None`.

### Block 3 — PC-001: Consent State Context Processor Fix

- **Commit:** `a3bf3c9`
- **File:** `src/backend/apps/users/context_processors.py` — `consent_state()` function, lines 68–72 contain the explicit guard:
  ```python
  if user.is_declined or user.consent_revoked_at is not None:
      consent_analytics = False
      consent_preferences = False
  ```
- **Test file:** `src/backend/apps/users/tests/test_consent_context.py` — `TestConsentTransition` class (lines 161–186) with `test_accepted_then_declined_disables_analytics` and `test_accepted_then_withdrawn_disables_analytics`
- **Verified:** Both tests set `consent_given_at` to 100 days ago (within 12-month window) to prove the guard is necessary.

### Block 4 — PC-001: Clear `consent_given_at` in `decline_consent` / `withdraw_consent`

- **Commit:** `3fa1d65`
- **File:** `src/backend/apps/users/services/deletion.py`
  - `decline_consent` (line 67–69): sets `user.consent_given_at = None`, `update_fields` includes `"consent_given_at"`
  - `withdraw_consent` (lines 141–155): sets `user.consent_given_at = None`, `update_fields` includes `"consent_given_at"`
- **Test file:** `src/backend/apps/users/tests/test_deletion.py`
  - `TestClearConsentGivenAt` class (lines 452–477): `test_accept_then_decline_clears_consent_given_at`, `test_accept_then_withdraw_clears_consent_given_at`
  - Existing tests in `TestDeclineConsentDoesNotInvalideTokens` and `TestWithdrawConsentInvalidatesTokens` assert `consent_given_at is None`
- **Verified:** `consent_given_at = None` is set before both `save()` calls; `update_fields` lists include the field.

### Block 5 — PC-006: Null `email` in `withdraw_consent`

- **Commit:** `c391cd4`
- **File:** `src/backend/apps/users/services/deletion.py` — `withdraw_consent` function (line 141: `user.email = ""`; line 155: `"email"` in `update_fields`)
- **Test file:** `src/backend/apps/users/tests/test_deletion.py`
  - `TestWithdrawConsentSoftDeletesAds.test_withdraw_soft_deletes_user_sets_pii_nulls` (lines 184–196): sets `email="admin@example.com"`, asserts `user.email == ""` after withdraw
- **Verified:** `email = ""` follows the `first_name`/`last_name` pattern; no migration needed (`EmailField(blank=True, default="")` from `AbstractUser`).

### Block 6 — PC-004: `storage_keys()` in `soft_delete_user_ads`

- **Commit:** `519ea5c`
- **File:** `src/backend/apps/users/services/deletion.py` — `soft_delete_user_ads` function (lines 204–208):
  ```python
  draft_storage_keys = [
      key
      for img in AdImage.objects.filter(ad_id__in=draft_ad_ids)
      for key in img.storage_keys()
  ]
  ```
- **Test file:** `src/backend/apps/users/tests/test_deletion.py`
  - `TestWithdrawConsentSoftDeletesAds.test_withdraw_returns_all_thumbnail_storage_keys` (lines 198–252): creates `AdImage` with all 4 keys, asserts all 4 returned + all 4 passed to `delete_photo`
  - `TestWithdrawConsentAtomicity.test_soft_delete_user_ads_returns_keys_not_count` (lines 398–449): verifies `soft_delete_user_ads` is DB-only (returns keys, never calls `delete_photo`)
- **Verified:** Replaced `values_list("image", flat=True)` with instance iteration over `storage_keys()`.

### Block 7 — PC-004: `storage_keys()` in `consent_hard_delete`

- **Commit:** `de60720`
- **File:** `src/backend/apps/core/management/commands/consent_hard_delete.py` — lines 71–75:
  ```python
  storage_keys = [
      key
      for img in AdImage.objects.filter(ad__user_id__in=user_ids)
      for key in img.storage_keys()
  ]
  ```
- **Test file:** `src/backend/apps/core/tests/test_sweep_commands.py` — `TestConsentHardDelete.test_collects_thumbnail_keys_for_media_cleanup` (lines 318–356): creates `AdImage` with image + 3 thumbnails, monkeypatches `delete_photo`, asserts all 4 keys passed to `delete_photo`
- **Verified:** `delete_photo` loop (lines 91–92) unchanged, still runs after transaction commit.

### Block 8 — PC-002: Bot i18n Wrapping

- **Commit:** `bad66e3`
- **Files:**
  - `src/telegram_bot/handlers/contact.py`: `_CONTACT_US_GREETING` (line 39), `CONTACT_US_RATE_LIMITED_MESSAGE` (line 46), `_("Ошибка: не удалось определить отправителя")` (line 163), `_("объявление больше недоступно")` (line 175), `_("продавец больше недоступен для связи")` (line 179), seller-message `%(...)` dict (line 186), `_("Ваш запрос отправлен продавцу анонимно...")` (line 197), `ANONYMOUS_BUYER_LABEL = _("Покупатель")` (line 247)
  - `src/telegram_bot/handlers/login.py`: `_("Welcome to %(site)s!...")` (line 52), `_("Invalid login link format...")` (line 87), `_("This login link is invalid...")` (line 104), `_("Login successful!...")` (lines 113, 119)
  - `src/telegram_bot/handlers/language.py`: `_("Please login first with /start login_<token>")` (line 39), `_("Select your preferred language:")` (line 45), `_("Unsupported language.")` (line 62), `_("Please login first.")` (line 68), `_("Language set to %(lang)s")` (line 76)
- **Test files:** `src/telegram_bot/tests/test_contact_us.py` (asserts `"службой поддержки" in sent_text` at line 93 — passes because `en` test locale returns msgid unchanged), `src/telegram_bot/tests/test_login.py` (no message-text assertions)
- **Verified:** All imports use `from django.utils.translation import gettext as _`; `ANONYMOUS_BUYER_LABEL` wrapped as `Final[str] = _("Покупатель")`.

### Block 9 — PC-002 + PC-003: `permissions.py` i18n + `get_account_state` Refactor

- **Commit:** `7ed761c` (HEAD)
- **File:** `src/telegram_bot/middlewares/permissions.py`
  - Imports `_` from `django.utils.translation` (line 15), `get_account_state` from `apps.users.services.account_state` (line 18)
  - `_check_user_state` delegates to `get_account_state(user)` (line 121), maps 4 states to state-specific `_()` messages (lines 123–144)
  - `_check_publish_permission` also uses `get_account_state` (line 164) with `state.ads_auto_publish` check and `_()`-wrapped message (lines 166–172)
- **Shared predicate:** `src/backend/apps/users/services/account_state.py` — `AccountState` NamedTuple + `get_account_state()` (returns `is_banned`, `is_deleted`, `is_declined`, `ads_auto_publish`, `consent_revoked`)
- **Test file:** `src/telegram_bot/tests/test_account_state_middleware.py` — `TestCheckUserStateMessages` (5 tests: banned, deleted, declined, revoked, normal, unregistered) + `TestCrossPredicateAgreement` (parametrized flag-matrix + `can_login` agreement tests)
- **Verified:** All 4 state-specific messages differ from each other; `_check_publish_permission` aligned with `get_account_state` (bonus consistency, beyond the plan's minimum requirement).

---

## Block 10 — PC-002: i18n Extraction & Compilation

**Status:** ⏳ REMAINING — **BLOCKED on nothing** (depends only on committed Blocks 8+9, which are done)

### Current State (verified)

| File | Working-tree state | Committed state | Gap |
|---|---|---|---|
| `src/backend/locale/en/LC_MESSAGES/django.po` | Modified, 327 msgids, POT-Creation-Date `2026-09-09 17:11`. All 24 new bot-string msgids present with empty msgstr (acceptable for en). | 244 msgids | 24 new msgids + re-sorting of existing entries |
| `src/backend/locale/ru/LC_MESSAGES/django.po` | Modified, 315 msgids. Only 3 fuzzy fixes applied (9 lines changed). **24 new msgids NOT present.** POT-Creation-Date `2026-09-04` (STALE). | 315 msgids | 24 missing msgids from Blocks 8+9 |
| `src/backend/locale/bs/LC_MESSAGES/django.po` | Modified, 315 msgids. Same as ru — only fuzzy fixes, no new msgids. POT-Creation-Date `2026-09-04` (STALE). | 315 msgids | 24 missing msgids from Blocks 8+9 |
| `src/backend/locale/{en,ru,bs}/LC_MESSAGES/django.mo` | All exist (gitignored). ru/bs are STALE (compiled before bot strings extracted). | — | `.mo` files stale, will be overwritten by compilemessages |
| `fill_translations.py` (untracked, project root) | Contains `ru_translations` and `bs_translations` dicts with 24 + 4 (=28) translation keys. Uses line-based .po parser. **Known limitation:** does not unescape `\n` escape sequences in msgid continuation lines before dictionary lookup — multi-line msgids will not match. | — | Script has unescaping bug for multi-line entries |
| `fill_translations2.py` (untracked, project root) | Alternative script with same translation dictionaries. **Known bug:** `get_msgid_from_block()` references undefined `msgid_plural_parts` at line 73 (`NameError`). | — | Script is non-functional |
| `analyze_po.py` (untracked, project root) | Contains `_unescape()` that properly converts `\n` → newline. Reports 305 entries, 0 fuzzy, 0 empty msgstr for committed ru/bs. | — | Analysis-only, not a fix tool |

### 4 New msgids requiring translation in ru/bs

The 24 missing msgids (all present in en .po) are:

**Bot strings (Blocks 8+9) — 23 entries:**

| # | Source file | msgid | ru translation | bs translation |
|---|---|---|---|---|
| 1 | contact.py | `👋 Привет! Вы связались со службой поддержки Bazuna.\n\nНапишите ваш вопрос — мы ответим как можно скорее.\n\nДля создания объявления использовать /post.` | (identity — Russian source) | Bosnian translation |
| 2 | contact.py | `Слишком много запросов в поддержку. Попробуйте позже.` | (identity) | Bosnian translation |
| 3 | contact.py | `Contact us` | `Связаться с нами` (already exists in en as new entry) | Bosnian |
| 4 | contact.py | `Ошибка: не удалось определить отправителя` | (identity) | Bosnian |
| 5 | contact.py | `объявление больше недоступно` | (identity) | Bosnian |
| 6 | contact.py | `продавец больше недоступен для связи` | (identity) | Bosnian |
| 7 | contact.py | `Новый запрос от покупателя!\n\nПокупатель: %(buyer)s\nAd ID: %(ad_id)s\n\nНапишите своё сообщение — оно будет переслано анонимно.` | (identity) | Bosnian |
| 8 | contact.py | `Ваш запрос отправлен продавцу анонимно. Ожидайте ответа в этом чате.` | (identity) | Bosnian |
| 9 | contact.py | `Покупатель` | (identity) | Bosnian |
| 10 | language.py | `Please login first with /start login_<token>` | Russian | Bosnian |
| 11 | language.py | `Select your preferred language:` | Russian | Bosnian |
| 12 | language.py | `Unsupported language.` | Russian | Bosnian |
| 13 | language.py | `Please login first.` | Russian | Bosnian |
| 14 | language.py | `Language set to %(lang)s` | Russian | Bosnian |
| 15 | login.py | `Welcome to %(site)s! To login, use a deep-link: /start login_<your_token>` | Russian | Bosnian |
| 16 | login.py | `Invalid login link format. Expected: /start login_<token>` | Russian | Bosnian |
| 17 | login.py | `This login link is invalid, expired, or already used.` | Russian (already in en diff as moved entry) | Bosnian (already exists in committed ru/bs) |
| 18 | login.py | `Login successful! Your account has been created. You can now create ads with /post.` | Russian | Bosnian |
| 19 | login.py | `Login successful! You can now create ads with /post.` | Russian | Bosnian |
| 20 | permissions.py | `Your account is restricted. Contact support for assistance.` | Russian | Bosnian |
| 21 | permissions.py | `Your account has been deleted.` | Russian (already exists in committed ru/bs!) | Bosnian (already exists) |
| 22 | permissions.py | `Consent declined: you can browse but cannot post. Contact still works.` | Russian | Bosnian |
| 23 | permissions.py | `Consent withdrawn: your data is being erased.` | Russian | Bosnian |
| 24 | permissions.py | `Your account has publishing restrictions. Contact support for assistance.` | Russian | Bosnian |

**Additional entry:** `Contact Seller`, `Submit an ad`, `Login via Telegram` — these were MOVED in the en .po (re-sorted by makemessages) but already exist in committed ru/bs .po with translations. No new work needed.

**Privacy policy text change:** The en .po also has a modified msgid for the Telegram privacy policy text (line 971–977 in en .po diff):
```
Old: "authentication and seller-buyer contact relay via deep-links (<code>t.me/%(bot_username)s</code>). No ad content is shared; only the identifiers needed for the action."
New: "authentication and seller-buyer contact relay via deep-links (<code>t.me/@<span class=\"bot-username-rtl\" aria-hidden=\"true\">%(obfuscated)s</span><span class=\"sr-only\">%(bot_username)s</span></code>). No ad content is shared; only the identifiers needed for the action."
```
When `makemessages` runs for ru/bs, this will be marked `#, fuzzy` with the old translation preserved. The `test_no_empty_msgstr` gate does not check fuzzy entries (it only checks for empty msgstr), so this entry will pass. However, the `fill_translations.py` script does not include this translation — if the translator wants to update it, they should do so manually.

### Execution Sequence

**Step 1: Run `makemessages`**

```powershell
# Inside Docker (uses the project's Docker Compose dev setup):
docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py makemessages -l ru -l bs -l en --no-location
```

- This scans all `.py` files under the container WORKDIR (including `src/telegram_bot/`) and merges new msgids into all three `.po` files.
- `ru/bs` will receive the 24 new msgids with empty `msgstr` (and `#, fuzzy` for the privacy-policy text change).
- `en` will be re-merged (no new content, POT-Creation-Date updated to current time).
- **No code changes** — `makemessages` only modifies `.po` files.

**Step 2: Fill translations in ru/bs .po files**

Two approaches are available:

**Approach A — Fix and run `fill_translations.py` (RECOMMENDED):**
1. Fix the unescaping bug in `fill_translations.py`: add `.replace('\\n', '\n')` in the msgid extraction logic (mirroring the `_unescape` pattern in `analyze_po.py` / `test_i18n_completeness.py`).
2. Run `python fill_translations.py` — fills all 24 new entries + fixes any remaining fuzzy entries.
3. **OR** use `fill_translations2.py` after fixing the `msgid_plural_parts` `NameError` (line 73).

**Approach B — Manual fill (fallback):**
- For each of the 24 new msgids in ru/bs .po, copy the translation from `fill_translations.py`'s `ru_translations` / `bs_translations` dictionaries into the empty `msgstr` field.
- For the 5 Russian-source msgids (entries 1–9 above), the msgstr = msgid (identity translation).
- For the 15 English-source msgids (entries 10–24), use the dictionary translations.

**Approach C — `polib` (not currently a dependency):**
- `uv add --dev polib` then use `polib.pofile()` for robust parsing.
- Not recommended — adds a new dependency for a one-time task. The existing scripts suffice with the unescape fix.

**Step 3: Run `compilemessages`**

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run python src/backend/manage.py compilemessages \
    --locale ru --locale bs --locale en
```

- Produces `.mo` files (gitignored — overwritten on every container start and CI run).

**Step 4: Verify with i18n gate**

```powershell
# No DB needed — these are @pytest.mark.unit tests
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm \
    -e PYTEST_OPTS="-k i18n_completeness --override-ini='addopts=-p no:xdist'" test \
    pytest apps/ads/tests/test_i18n_completeness.py -v
```

The 4 gate tests:
1. `test_no_hardcoded_visible_text` — scans templates (no .po change needed; passes if no new hardcoded template text)
2. `test_extraction_completeness` — all msgids in en must exist in ru/bs and vice versa → **fails if makemessages didn't merge**
3. `test_no_empty_msgstr` — ru/bs must have 0 empty msgstr → **fails if translations not filled**
4. `test_mo_compiled` — .mo files must exist → passes after compilemessages

### Architectural Constraints

1. **`.mo` files are gitignored** — the test entrypoint (`entrypoint-test.sh`) auto-compiles them via `compilemessages` before pytest. Production compiles at image build / container startup. The `.mo` files need NOT be committed, but must be present at test time.
2. **`makemessages` must run in Docker** — the command scans `.py` files under `/app` in the container WORKDIR (which includes `src/telegram_bot/`). Running locally outside Docker would not find the bot source files unless the working directory includes them.
3. **No schema changes** — i18n extraction/compilation touches only `.po`/`.mo` files and helper scripts. No migrations.
4. **`--no-location` flag** — the Makefile uses `--no-location` which suppresses source location comments in `.po` files, keeping diffs clean. This is already applied in the en .po working-tree state.
5. **en msgstr may be empty** — per the project's i18n spec (doc rule #16), `en` .po files may have empty msgstr (msgid is English). Only `ru` and `bs` require non-empty translations.
6. **The `ANONYMOUS_BUYER_LABEL = _("Покупатель")` pattern** (contact.py line 247) means `gettext` is called at module import time. In the test locale (`LANGUAGE_CODE = "en"`), this returns the msgid unchanged. The bot process must activate the user's `telegram_language` at runtime for actual localization — this is a known limitation, not a Block 10 concern.
7. **`fill_translations.py` multi-line msgid bug**: The script does NOT unescape `\n` escape sequences in .po msgid continuation lines before dictionary lookup. The `ru_translations`/`bs_translations` dictionaries use Python `\n` (actual newlines), but the .po parser concatenates continuation lines keeping literal `\n` (backslash-n). This causes dictionary lookup to **fail** for multi-line msgids:
   - Entry #1: Bot greeting (`👋 Привет!...`)
   - Entry #7: Seller notification (`Новый запрос от покупателя!...`)
   
   **Fix:** Add `.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')` to the msgid extraction in `find_empty_msgstr_entries` and `find_fuzzy_entries`, mirroring the `_unescape` function already used in `analyze_po.py` (line 25) and `test_i18n_completeness.py` (line 49).

### Required Tests

No new test files. The i18n gate `test_i18n_completeness.py` (4 unit tests, `@pytest.mark.unit`) is the sole verification. These are already committed and run on every fast-gate CI cycle.

### Supporting Agents

| Agent | Role | When |
|---|---|---|
| **Implementor** (primary) | Run makemessages, fix+run fill_translations, run compilemessages, commit .po files | Block 10 |
| **Auditor** (optional) | Verify no msgstr left empty in ru/bs after fill; confirm POT-Creation-Date updated | Post-step 2 |
| **Validator** | Run `test_i18n_completeness.py` (4 gates); verify `test_extraction_completeness` and `test_no_empty_msgstr` pass | Post-step 4 |

### Risks

- **Medium — `fill_translations.py` multi-line msgid bug**: Without the unescape fix, entries #1 and #7 (and the privacy-policy multi-line msgid if it gets a new empty msgstr) will remain empty in ru/bs .po, failing `test_no_empty_msgstr`. **Mitigation:** Apply Approach A (fix + re-run script) or manually fill multi-line entries.
- **Low — `fill_translations2.py` `NameError`**: The alternative script references `msgid_plural_parts` (undefined) at line 73 of `get_msgid_from_block()` → `NameError`. This script is non-functional as-is. **Recommendation:** Use `fill_translations.py` with the unescape fix, not `fill_translations2.py`.
- **Low — Fuzzy privacy-policy text**: `makemessages` will mark the modified Telegram privacy-policy msgid as `#, fuzzy` in ru/bs, preserving the old translation as msgstr. `test_no_empty_msgstr` does not check fuzzy entries, so this passes. The fuzzy flag should be removed and the translation updated to match the new msgid (the `fill_translations.py` script handles fuzzy entry cleanup, but this specific msgid is NOT in the translation dictionaries — must be handled manually).
- **Low — Helper scripts at project root**: `fill_translations.py`, `fill_translations2.py`, and `analyze_po.py` are untracked root-level scripts. After Block 10 completes, they should be **removed** (not committed) to avoid polluting the repo. The `.git/info/exclude` or a cleanup step should remove them.
- **Low — `.mo` staleness**: The existing `.mo` files are from before the bot-string gettext wrapping. After `compilemessages`, they will be regenerated with the new strings. Tests that depend on translated text in bot messages will see the msgid (English source) since the test `LANGUAGE_CODE = "en"`, so no behavior change for existing tests.

---

## Block 11 — Verification

**Status:** ⏳ REMAINING — **Blocked on Block 10** (i18n gate must pass before full suite is green)

### Execution Sequence

```powershell
# 0. Ensure helper scripts are NOT committed (keep working tree clean)
#    They are untracked; if accidentally staged, unstage:
git reset -- src/backend/locale/*/LC_MESSAGES/django.po  # if needed before re-running

# 1. Start test DB (if not running)
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db

# 2. Run fast gate (skips seed suite ~17min; auto-starts/reuses test DB)
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed test

# 3. Run i18n completeness gate explicitly (unit, no DB)
docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm \
    -e PYTEST_OPTS="-k i18n_completeness" test pytest apps/ads/tests/test_i18n_completeness.py -v

# 4. Lint + typecheck
docker compose --project-name mko-bazuna-dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check src/
docker compose --project-name mko-bazuna-dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run basedpyright src/telegram_bot src/backend/apps/users src/backend/apps/ads
```

### Test Files to Verify

| Test file | Block(s) | Mark | Status |
|---|---|---|---|
| `src/backend/apps/ads/tests/test_adimage_storage_keys.py` | Block 1 | unit | 5 tests — all pass (committed) |
| `src/backend/apps/users/tests/test_consent_records.py` | Block 2 | django_db, slow, integration | `TestAnonymizeIp` — IPv6/IPv4/None (committed) |
| `src/backend/apps/users/tests/test_consent_context.py` | Block 3 | django_db, slow, integration | `TestConsentTransition` — decline/withdraw disables analytics (committed) |
| `src/backend/apps/users/tests/test_deletion.py` | Blocks 4,5,6 | django_db, slow, integration | `TestClearConsentGivenAt`, PII nulls, storage_keys in withdraw (committed) |
| `src/backend/apps/core/tests/test_sweep_commands.py` | Block 7 | django_db, slow, integration | `test_collects_thumbnail_keys_for_media_cleanup` (committed) |
| `src/telegram_bot/tests/test_contact_us.py` | Block 8 | django_db, integration | `test_greeting_with_keyboard` asserts `"службой поддержки" in sent_text` (committed, passes in `en` locale) |
| `src/telegram_bot/tests/test_account_state_middleware.py` | Block 9 | django_db, concurrent | `TestCheckUserStateMessages` + `TestCrossPredicateAgreement` (committed) |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | Block 10 | unit | 4 gates: hardcoded text, extraction completeness, no empty msgstr, .mo compiled |

### Verification Criteria

1. **Fast gate passes** — `make test` (skips seed suite) exits 0.
2. **i18n gate passes** — all 4 `test_i18n_completeness.py` tests exit 0.
3. **No new lint errors** — `uv run ruff check src/` exits 0.
4. **No new typecheck errors** — `uv run basedpyright src/telegram_bot src/backend/apps/users src/backend/apps/ads` exits 0.
5. **No regressions** — no previously-passing test fails.

### Supporting Agents

| Agent | Role |
|---|---|
| **Validator** (primary) | Runs full fast-gate + i18n gate; reports any failures |
| **Implementor** | Addresses any failures (re-visits the responsible block) |

---

## Execution Order Summary

| Order | Block | Finding | File(s) | Test file(s) | Status | Risk | Agents |
|---|---|---|---|---|---|---|---|
| 1 | Block 1 | PC-004-model | `ads/models.py` | create `test_adimage_storage_keys.py` | ✅ Committed `8d78ab2` | Low | Implementor, Validator |
| 2 | Block 2 | PC-005 | `consent_record.py`, `users/models.py` | modify `test_consent_records.py` | ✅ Committed `eaf5795` | Low | Implementor, Validator |
| 3 | Block 3 | PC-001-ctx | `context_processors.py` | modify `test_consent_context.py` | ✅ Committed `a3bf3c9` | Medium | Implementor, Test Engineer, Validator |
| 4 | Block 4 | PC-001-del | `deletion.py` (decline/withdraw) | modify `test_deletion.py` | ✅ Committed `3fa1d65` | Medium | Implementor, Validator |
| 5 | Block 5 | PC-006 | `deletion.py` (withdraw email) | modify `test_deletion.py` | ✅ Committed `c391cd4` | Low | Implementor, Validator |
| 6 | Block 6 | PC-004-softdel | `deletion.py` (soft_delete_user_ads) | modify `test_deletion.py` | ✅ Committed `519ea5c` | Medium | Implementor, Test Engineer |
| 7 | Block 7 | PC-004-hardcmd | `consent_hard_delete.py` | modify `test_sweep_commands.py` | ✅ Committed `de60720` | Low | Implementor, Test Engineer |
| 8 | Block 8 | PC-002-bot | `contact.py`, `login.py`, `language.py` | modify `test_contact_us.py` | ✅ Committed `bad66e3` | Medium | Implementor, Test Engineer |
| 9 | Block 9 | PC-002+003-perm | `permissions.py` | create `test_account_state_middleware.py` | ✅ Committed `7ed761c` | Medium | Implementor, Test Engineer, Validator |
| 10 | Block 10 | PC-002-i18n | `.po`/`.mo` (generated) | gate: `test_i18n_completeness.py` | ⏳ Remaining | Medium* | Implementor, Auditor, Validator |
| 11 | Block 11 | — | — | all of the above | ⏳ Remaining | Low | Validator |

\*Block 10 risk is Medium due to the `fill_translations.py` multi-line msgid unescaping bug. Mitigated by applying the fix (Approach A) or using manual fill for the 2 affected multi-line entries.

### Key Ordering Constraints

1. **Block 1 → Blocks 6, 7:** `storage_keys()` must exist before call-sites use it. ✅ (Both dependents committed)
2. **Block 4 → Block 5:** Both modify `withdraw_consent`'s `update_fields` list; sequential to avoid list conflict. ✅ (Both committed)
3. **Blocks 4+5 → Block 6:** All three modify `deletion.py`; sequential execution avoids review friction. ✅ (All committed)
4. **Block 8 → Block 9:** `permissions.py` `_()` calls depend on the gettext import pattern established in Block 8. ✅ (Both committed)
5. **Blocks 8+9 → Block 10:** `makemessages` must see all `gettext` calls before extraction. ⏳ (Block 10 REMAINING — this is the active dependency chain)
6. **All code blocks → Block 11:** Verification runs after all changes. ⏳ (Block 11 REMAINING — blocked on Block 10)

---

## 12. Artifacts Summary

| Artifact | Status | Location |
|---|---|---|
| Source findings (PC-001–006) | ✅ Validated | `.ai/audit/99-validation/06-pii-consent-validated-findings.md` |
| Original 11-block plan | ✅ Superseded | `.kilo/plans/phase-06-pii-consent-execution-dag.md` |
| **This decomposition** | ✅ Active | `.ai/plans/01-pii-consent-execution-dag.md` |
| Helper scripts (untracked) | ⏳ To be removed after Block 10 | `fill_translations.py`, `fill_translations2.py`, `analyze_po.py` |

---

*Generated: 2026-09-10 — Planning only. No code modified.*
