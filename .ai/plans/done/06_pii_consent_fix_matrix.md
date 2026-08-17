---
id: 06-pii-consent-fix-matrix
domain: audit-remediation
tags:
  - pii
  - consent
  - gdpr
  - erasure
  - logging
phase: "06-pii-consent"
status: done
validated-source: ".ai/audit/99-validation/06-pii-consent-validated-findings.md"
---

# PII Consent Fix Matrix — Test & Documentation Requirements

> Phase: `06-pii-consent` · Audit source:
> `.ai/audit/99-validation/06-pii-consent-validated-findings.md`
> Generated during Step 3 of the remediation workflow (research → matrix → implement → docs).
>
> This matrix consolidates the 5 actionable findings from the Phase 06 PII/consent audit,
> their **preferred remediation** (selected in Step 2.1 research), the **tests required**
> to guard each change, and the **documentation changes** needed. Status moves to
> `done` only after the Implementor commits + passes quality gates and the Doc-specialist
> updates the listed docs.
>
> **Note on paths:** Python source/test paths use the `apps/` module convention (e.g.
> `apps/core/utils/sanitize.py` → filesystem `src/backend/apps/core/utils/sanitize.py`).
> Template and doc paths are repo-root-relative.

---

## Decision Log (resolved during Step 2.1 research)

| Decision | Resolution | Rationale |
|---|---|---|
| **PII-001 root cause** | `User.telegram_id` made nullable | Already fixed in model (`models.py:34-39` — `null=True, blank=True`). Prerequisite unblocks PII-008 transaction and PII-006 token-deletion tests. |
| **PII-002 mask format** | Non-reversible SHA-256 hash, 8 hex chars, `tg_` prefix | `token.telegram_id` is a stable, guessable identifier (~10-digit integer). Raw IDs in logs let anyone with log access reconstruct the full user graph. SHA-256 hash is non-reversible yet stable (same input → same output, enabling correlation without exposure). Plain `None` → string `"None"`. |
| **PII-004 retention timeline** | 30 days post-withdrawal → hard-delete | Spec Decision F: `consent_revoked_at` set at withdrawal; `consent_hard_delete` sweep hard-purges 30 days later. `sweep_deleted_records.py` handles 30-day ad purge. Both use `ERASURE_RETENTION_DAYS=30`. |
| **PII-008 TX-then-FS pattern source** | `consent_hard_delete.py` (lines 45–90) | The established sweep-command pattern: all DB writes inside `transaction.atomic()`, filesystem `delete_photo()` loop **after** the block commits. `soft_delete_user_ads()` must be refactored to collect+return storage keys (DB-only) so `delete_photo()` can run outside the transaction in `withdraw_consent()`. |
| **PII-008 idempotency** | Guard at top of `withdraw_consent()` | If `user.is_deleted` is already `True`, return early — prevents double-withdrawal from corrupting state. |
| **PII-009 guard placement** | Per-include guard in each template | No web-side middleware redirects deleted users (verified: `MIDDLEWARE` in `base.py:111-121` has no `WebAccountStateMiddleware`). The consent banner renders in templates for authenticated users regardless of `is_deleted`. Adding `{% if not request.user.is_authenticated or not request.user.is_deleted %}` around the include is the primary fix (5 template sites). `is_authenticated` is checked first because `AnonymousUser` lacks `is_deleted`. |
| **PII-003 POST withdrawal** | Dashboard button POSTs to existing view | `consent_withdraw` is `@login_required` with no method restriction — accepts POST immediately. CSRF token auto-included via `{% csrf_token %}`. `@require_POST` on the view is **recommended** (destructive action should not be GET-triggerable) but not strictly required for the button to work; existing GET-based tests in `test_consent.py` would need updating if added. |

---

## Summary Table

| ID | Finding | Severity | Classification | Preferred Fix Location | Migration | Tests | Docs | Status |
|----|---------|----------|----------------|------------------------|-----------|-------|------|--------|
| PII-002 | `telegram_id` logged in plaintext (7 logger + 3 stdout) | CRITICAL | Simple / Low-risk | `apps/core/utils/sanitize.py` (new fn), 4 source files | none | `test_sanitize.py` (new), additions to `test_consent.py`, `test_contact.py`, `test_create_admin_user.py` | `technical-specification.md` | ✅ Done |
| PII-003 | No "Withdraw consent" UI on seller dashboard | HIGH | Simple / Low-risk | `src/backend/templates/ads/dashboard.html` | none | `test_consent.py` (POST variant) | `technical-specification.md` Decision F | ✅ Done |
| PII-004 | No retention timeline documented for anonymized data | HIGH | DOC-UPDATE | (docs only) | none | none | `db-retention.md` (new section), `technical-specification.md` Decision F | ✅ Done |
| PII-008 | `withdraw_consent()` not atomic; FS deletion inside TX | MEDIUM | Complex / High-risk | `apps/users/services/deletion.py` | none | `test_deletion.py` | none | ✅ Done |
| PII-009 | Consent banner renders for deleted users | LOW | Simple / Low-risk | 5 template files (`src/backend/templates/...`) | none | `test_consent.py` or new `test_templates.py` | none | ✅ Done |

---

## PII-002 — `telegram_id` logged in plaintext across web + bot processes

**Classification:** Simple / Low-risk (utility function + targeted call-site edits)
**Severity:** CRITICAL · **Priority:** high

### Preferred Solution

1. Add `mask_telegram_id(value: int | None) -> str` to `apps/core/utils/sanitize.py`:
   - `None` → `"None"`
   - `int` → `f"tg_{hashlib.sha256(str(value).encode()).hexdigest()[:8]}"` (non-reversible, stable)
2. Apply `mask_telegram_id()` at all **10** exposure sites:

| # | File | Line | Current code | Fix |
|---|------|------|-------------|-----|
| 1 | `apps/users/views/consent.py` | 254 | `logger.info(f"...telegram_id={token.telegram_id}")` | `mask_telegram_id(token.telegram_id)` |
| 2 | `apps/users/views/consent.py` | 260 | `logger.error(f"...telegram_id={token.telegram_id}")` | `mask_telegram_id(token.telegram_id)` |
| 3 | `apps/users/views/consent.py` | 265 | `logger.warning(f"...telegram_id={token.telegram_id}:...")` | `mask_telegram_id(token.telegram_id)` |
| 4 | `apps/users/views/consent.py` | 273 | `logger.info(f"...(telegram_id={token.telegram_id})")` | `mask_telegram_id(token.telegram_id)` |
| 5 | `apps/core/services/contact.py` | 149 | `logger.warning("...telegram_id %s", seller_telegram_id)` | `mask_telegram_id(seller_telegram_id)` |
| 6 | `apps/moderation/admin_actions.py` | 99* | `logger.info(f"...telegram_id={user.telegram_id}...")` | `mask_telegram_id(user.telegram_id)` |
| 7 | `apps/core/management/commands/create_admin_user.py` | 109 | `logger.info("...telegram_id=%s...", ..., telegram_id)` | `mask_telegram_id(telegram_id)` |
| 8 | `apps/core/management/commands/create_admin_user.py` | 76 | `self.stdout.write(f"...telegram_id={telegram_id}...")` | `mask_telegram_id(telegram_id)` |
| 9 | `apps/core/management/commands/create_admin_user.py` | 89 | `self.stdout.write(f"  telegram_id: {telegram_id}\n")` | `mask_telegram_id(telegram_id)` |
| 10 | `apps/core/management/commands/create_admin_user.py` | 113 | `self.stdout.write(f"  telegram_id: {telegram_id}\n")` | `mask_telegram_id(telegram_id)` |

\* *Line numbers may shift after PII-002 edits in the same file; re-grep before editing.*

3. **[Recommended] Add a CI grep gate** (`pyproject.toml` or a new `scripts/` check) that fails if raw `telegram_id` interpolation appears inside any `logger.*` or `stdout.write` call without `mask_telegram_id()`.

### Tests Required

| Scope | Test File | Test Case | Type | Key Assertions |
|-------|-----------|-----------|------|----------------|
| Unit | `apps/core/tests/test_sanitize.py` (NEW) | `test_mask_telegram_id_masks_int` | unit | `mask_telegram_id(1098765432)` returns `"tg_<8-hex>"`; raw `1098765432` not in result; output length == 13 (`tg_` + 8 hex) |
| Unit | `apps/core/tests/test_sanitize.py` (NEW) | `test_mask_telegram_id_none` | unit | `mask_telegram_id(None)` returns `"None"` |
| Unit | `apps/core/tests/test_sanitize.py` (NEW) | `test_mask_telegram_id_is_stable` | unit | Two calls with same int return identical string (deterministic for correlation) |
| Unit | `apps/core/tests/test_sanitize.py` (NEW) | `test_mask_telegram_id_different_inputs` | unit | `mask_telegram_id(111)` ≠ `mask_telegram_id(222)` (different IDs → different masks) |
| Unit | `apps/core/tests/test_sanitize.py` (NEW) | `test_mask_telegram_id_no_raw_id` | unit | `str(1098765432)` not in `mask_telegram_id(1098765432)` |
| Integration | `apps/users/tests/test_consent.py` | `test_login_consume_does_not_log_raw_telegram_id` | integration | POST to `login_status` with caplog at INFO; assert `token.telegram_id` (raw int) NOT in any log record; assert masked form present |
| Integration | `apps/users/tests/test_consent.py` | `test_login_no_user_does_not_log_raw_telegram_id` | integration | Trigger `User.DoesNotExist` path; assert raw `telegram_id` not in caplog; assert masked form present |
| Integration | `apps/users/tests/test_consent.py` | `test_login_banned_does_not_log_raw_telegram_id` | integration | Trigger banned-user path; assert raw `telegram_id` not in caplog |
| Integration | `apps/core/tests/test_contact.py` | `test_contact_no_seller_no_pii_in_log` | integration | `record_contact_response(seller_telegram_id=999999)`; assert raw `999999` not in caplog at WARNING; assert masked `tg_…` present |
| Integration | `apps/core/tests/test_contact.py` | `test_contact_seller_found_no_pii_in_log` | integration | Existing + existing seller; assert `contact_response` log uses `user.id` (not telegram_id) — no raw telegram_id in any log line |
| Integration | `apps/moderation/tests/test_admin_actions.py` (NEW) | `test_ban_action_logs_masked_telegram_id` | integration | `ban_account()` or equivalent; assert raw `user.telegram_id` not in caplog; masked form present |
| Integration | `apps/core/tests/test_create_admin_user.py` | `test_command_dry_run_does_not_leak_telegram_id` | integration | `call_command("create_admin_user", …, stdout=out)` + caplog; assert raw `telegram_id` value not in `out.getvalue()` or caplog; assert masked form in output |
| Integration | `apps/core/tests/test_create_admin_user.py` | `test_command_success_does_not_leak_telegram_id` | integration | `call_command("create_admin_user", …)` + caplog; assert raw telegram_id not in stdout StringIO or log records; assert masked form present |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/01-spec/technical-specification.md` | Decision F (§1, bullet on PII erasure) | Add note: "All `telegram_id` values in logs are masked via `mask_telegram_id()` (SHA-256 hash, non-reversible). Raw telegram_id must never appear in logger or stdout output. See `apps/core/utils/sanitize.py`." |
| `pyproject.toml` | `[tool.ruff.lint]` (CI gate recommendation) | Document recommendation: consider a custom grep-based CI check that flags `telegram_id` inside `logger.*` or `stdout.write` arguments without `mask_telegram_id()`. |
| `apps/core/utils/sanitize.py` | `mask_telegram_id` docstring | Document the masking strategy (SHA-256, non-reversible, stable for correlation, `None` → `"None"`). |

---

## PII-003 — No "Withdraw consent" UI on seller dashboard

**Classification:** Simple / Low-risk (template change + view method update)
**Severity:** HIGH · **Priority:** medium

### Preferred Solution

1. On the seller dashboard (`src/backend/templates/ads/dashboard.html`), add a "Withdraw Data" POST button **beside the existing "Logout" link** (line 25):
   ```html
   <div class="mt-2 flex gap-4 items-center">
       <a href="/logout/" class="text-sm text-gray-600 hover:text-red-600">Logout</a>
       <form method="post" action="{% url 'consent:withdraw' %}" class="inline">
           {% csrf_token %}
           <button type="submit"
                   class="text-sm text-red-600 hover:text-red-800 font-medium"
                   onclick="return confirm('Withdrawing consent permanently erases your Telegram ID, all ads, and prevents re-login. Are you sure?');">
               Withdraw Data
           </button>
       </form>
   </div>
   ```
   - Label: "Withdraw Data" (clear, irreversible connotation)
   - Confirmation: `onclick="return confirm(…)"` — irreversible action requires explicit user confirmation
   - CSRF token: included via `{% csrf_token %}`
   - POST target: `{% url 'consent:withdraw' %}` → `consent_withdraw` view

2. **Recommended:** Add `@require_POST` to `consent_withdraw` view (`apps/users/views/consent.py:100`) — destructive actions should not be GET-triggerable. Update existing GET-based tests in `test_consent.py` to POST if this is applied.

### Tests Required

| Scope | Test File | Test Case | Type | Key Assertions |
|-------|-----------|-----------|------|----------------|
| Integration | `apps/users/tests/test_consent.py` | `test_withdraw_requires_authentication` (update) | integration | Anonymous POST to `/consent/withdraw/` → 302 redirect to login |
| Integration | `apps/users/tests/test_consent.py` | `test_withdraw_button_renders_on_dashboard` | integration | Authenticated GET `/dashboard/`; assert `"Withdraw Data"` button + `{% url 'consent:withdraw' %}` form in response body |
| Integration | `apps/users/tests/test_consent.py` | `test_withdraw_post_triggers_soft_delete` (update from GET) | integration | Authenticated POST `/consent/withdraw/`; assert 302 to dashboard; `user.is_deleted=True`, `telegram_id=None`, `consent_revoked_at` set |
| Integration | `apps/users/tests/test_consent.py` | `test_withdraw_post_soft_deletes_ads` | integration | Authenticated POST; assert user's ads are `DELETED` + `deleted_at` set |
| Integration | `apps/users/tests/test_consent.py` | `test_withdraw_post_sets_cookie` | integration | Authenticated POST; assert `consent_given` cookie = `"withdrawn"` |
| Edge | `apps/users/tests/test_consent.py` | `test_withdraw_via_get_is_forbidden` | integration | If `@require_POST` applied: authenticated GET `/consent/withdraw/` → 405 |
| Edge | `apps/users/tests/test_consent.py` | `test_withdraw_without_csrf_fails` | integration | Authenticated POST without CSRF token → 403 |
| Regression | `apps/users/tests/test_deletion.py` | `test_withdraw_consent_service_still_works` | integration | Direct `withdraw_consent(user)` call still succeeds (view-layer change doesn't break service) |
| Browser | `apps/ads/tests/test_dashboard.py` (or new) | `test_dashboard_has_no_withdraw_button_for_anonymous` | browser | Anonymous GET `/dashboard/` → no "Withdraw Data" button in response |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/01-spec/technical-specification.md` | Decision F (§1) | Add: "Authenticated sellers can withdraw consent via a 'Withdraw Data' POST button on the dashboard (`/dashboard/`), beside the Logout link. Withdrawal is irreversible — requires confirmation modal/label. Triggers `withdraw_consent()` (soft-delete + PII null + 30-day hard-delete)." |
| `docs/04-user-stories/seller-stories.md` | Consent section | Add user story: "As a seller who previously consented, I want to withdraw my consent from the dashboard so that all my data is permanently erased." |

---

## PII-004 — No retention timeline documented for anonymized ad data

**Classification:** DOC-UPDATE
**Severity:** HIGH · **Priority:** medium

### Preferred Solution (doc-only)

No code changes. The `consent_hard_delete` sweep command (`apps/core/management/commands/consent_hard_delete.py:45-90`) already implements the 30-day hard-delete via `transaction.atomic()` + advisory lock + TX-then-FS `delete_photo()` pattern. `User.telegram_id` is already nullable (PII-001 resolved), so the full withdrawal → anonymized state → 30-day purge flow works end-to-end. This is strictly a documentation gap.

Post-withdrawal lifecycle (current, verified):
1. T+0: User withdraws → `consent_revoked_at=now()`, `is_deleted=True`, `telegram_id=NULL`, ads soft-deleted (`status=DELETED`, `deleted_at=now()`)
2. T+0→30d: User is anonymized — `telegram_id`/`username` NULLed, ads remain soft-deleted (hidden from buyers, searchable via FTS only if published — but ads are set to `DELETED` status so they're already hidden)
3. T+30d: `consent_hard_delete` sweep hard-deletes the User row → cascades to all Ad + AdImage rows (CASCADE from User→Ad→AdImage)
4. Physical media files deleted via `delete_photo()` loop after transaction commits

### Tests Required

No new tests required — existing tests already cover the behavior:

| Scope | Test File | Test Case | Type | Key Assertions |
|-------|-----------|-----------|------|----------------|
| (existing) | `apps/core/tests/test_sweep_commands.py` | `TestConsentHardDelete::test_hard_deletes_users_past_grace_period` | integration | User past 30-day grace period is hard-deleted by `consent_hard_delete` |
| (existing) | `apps/core/tests/test_sweep_commands.py` | `TestConsentHardDelete::test_does_not_delete_within_grace_period` | integration | User within 30-day window is preserved |
| (existing) | `apps/core/tests/test_sweep_commands.py` | `TestConsentHardDelete::test_dry_run_does_not_delete` | integration | `--dry-run` mode deletes nothing |
| (existing) | `apps/users/tests/test_deletion.py` | `TestWithdrawConsentSoftDeletesAds::test_withdraw_soft_deletes_user_ads` | integration | Withdrawal soft-deletes all user ads |
| (documented) | `apps/core/tests/test_sweep_commands.py` | `TestConsentHardDelete::test_crash_between_updates_and_delete_rolls_back` | integration | Rollback test (already has `.exists()` stub — PII-010 resolved) |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/02-database/db-retention.md` | New section: "§3 Post-Withdrawal Data Retention" | Add: Post-withdrawal anonymized retention timeline. User row: `consent_revoked_at` set at withdrawal → hard-deleted by `consent_hard_delete` sweep after 30 days (`ERASURE_RETENTION_DAYS=30`, advisory lock 3). Ads: soft-deleted immediately (`status=DELETED`, `deleted_at=now()`) → hard-deleted via ORM CASCADE when User row is hard-deleted. AdImage media: physical files deleted via `delete_photo()` **after** the transaction commits (TX-then-FS pattern, see `consent_hard_delete.py:86-90`). No separate anonymized-data sweep is needed — the 30-day `consent_hard_delete` sweep handles the full cascade. Link to `consent_hard_delete` command reference. |
| `docs/01-spec/technical-specification.md` | Decision F (lines 79–87), 4th bullet | Clarify: "soft-delete immediately (`is_deleted=True`, `deleted_at=now()`) + full PII erasure exactly 30 days after `consent_revoked_at` via the `consent_hard_delete` sweep (advisory lock 3, `ERASURE_RETENTION_DAYS=30`). The sweep hard-deletes the User row, cascading to Ad and AdImage rows via Django ORM `on_delete=CASCADE`. Physical ad-image files are removed via `delete_photo()` after the transaction commits (TX-then-FS pattern)." |

---

## PII-008 — `withdraw_consent()` not atomic; filesystem deletion inside transaction

**Classification:** Complex / High-risk (transaction boundary refactoring)
**Severity:** MEDIUM · **Priority:** high

### Preferred Solution

Refactor `apps/users/services/deletion.py`:

**1. Wrap `withdraw_consent()` body in `transaction.atomic()`:**
```python
def withdraw_consent(user: User) -> list[str]:
    """..."""
    now = timezone.now()
    user_telegram_id = user.telegram_id

    with transaction.atomic():
        # Idempotency guard
        if user.is_deleted:
            return []

        # Phase 1: invalidate tokens
        LoginToken.objects.filter(telegram_id=user_telegram_id).delete()

        # Phase 2: null PII + set flags
        user.consent_revoked_at = now
        user.is_deleted = True
        user.deleted_at = now
        user.telegram_id = None
        user.username = None
        user.first_name = ""
        user.last_name = ""
        user.save(update_fields=[...])

        # Phase 3: soft-delete ads (DB-only — collect keys, no FS ops)
        storage_keys = soft_delete_user_ads(user)

    # Phase 4: filesystem cleanup OUTSIDE transaction (TX-then-FS pattern)
    for key in storage_keys:
        delete_photo(key)

    logger.info(f"User {user.id} withdrew consent - soft-delete triggered")
    return storage_keys
```

**2. Refactor `soft_delete_user_ads()` to be DB-only:**
- Collect `draft_storage_keys` from `AdImage.objects.filter(...)` (already done)
- Delete `AdImage` rows (DB-only)
- Do NOT call `delete_photo()` inline — collect and return keys
- Continue: bulk `Ad.objects.filter(user=user).update(status=DELETED, deleted_at=now)`
- Return `(ads_deleted_count, storage_keys)` or just `storage_keys`

This follows the exact pattern of `consent_hard_delete.py:68-90` (collect keys inside atomic, delete files after commit) and `purge_deleted_ads.py` (same pattern, lines 68–90).

### Tests Required

| Scope | Test File | Test Case | Type | Key Assertions |
|-------|-----------|-----------|------|----------------|
| Integration | `apps/users/tests/test_deletion.py` | `test_withdraw_is_atomic_rollback` | integration | Force a DB error after LoginToken deletion but before `user.save()`; assert LoginTokens are **restored** (rolled back) and user is NOT soft-deleted |
| Integration | `apps/users/tests/test_deletion.py` | `test_withdraw_returns_storage_keys` | integration | `withdraw_consent(user)` with a DRAFT ad + AdImage; assert return value is a list of storage keys (str); assert keys match AdImage `image` field values |
| Integration | `apps/users/tests/test_deletion.py` | `test_withdraw_deletes_files_after_commit` | integration | Mock `delete_photo` with `monkeypatch`; assert `delete_photo` is called for each returned key; assert no `delete_photo` call occurs **inside** `transaction.atomic()` (inspect source or use a flag set during a forced in-transaction failure) |
| Integration | `apps/users/tests/test_deletion.py` | `test_withdraw_soft_deletes_ads_returns_keys` | integration | `soft_delete_user_ads(user)` returns list of storage keys; assert AdImage rows for DRAFT ads are deleted (DB); assert `delete_photo` is **not** called by `soft_delete_user_ads` (spy/mock) |
| Edge | `apps/users/tests/test_deletion.py` | `test_withdraw_idempotent` | integration | Call `withdraw_consent(user)` twice; second call returns `[]`, no new LoginToken deletion, no extra file ops; user state unchanged after first |
| Edge | `apps/users/tests/test_deletion.py` | `test_withdraw_no_draft_ads_returns_empty_keys` | integration | User with only PUBLISHED ads; `withdraw_consent` returns `[]` (no DRAFT media keys to delete) |
| Regression | `apps/users/tests/test_consent.py` | `test_withdraw_post_triggers_soft_delete` | integration | Existing consent view test (updated to POST) still passes after refactoring `soft_delete_user_ads` return signature |
| Regression | `apps/core/tests/test_sweep_commands.py` | `TestConsentHardDelete::test_crash_between_updates_and_delete_rolls_back` | integration | Existing crash rollback test still passes (pattern consistency) |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| (none — code-only) | — | The TX-then-FS pattern is already documented in `consent_hard_delete.py` docstring (lines 1–7) and `db-retention.md` §2. No doc change needed; the refactor aligns `deletion.py` with the existing pattern. |
| `apps/users/services/deletion.py` | `withdraw_consent` docstring | Update docstring to note: transaction.atomic() wrapping, idempotency guard, and that `soft_delete_user_ads` returns storage keys (DB-only) — `delete_photo` called after commit. |
| `apps/users/services/deletion.py` | `soft_delete_user_ads` docstring | Update return type: now returns `list[str]` of storage keys instead of `int` (count). Document that filesystem deletion is delegated to `withdraw_consent`. |

---

## PII-009 — Consent banner renders for deleted users

**Classification:** Simple / Low-risk (template guard in 5 files)
**Severity:** LOW · **Priority:** low

### Preferred Solution

Add `{% if not request.user.is_authenticated or not request.user.is_deleted %}` guard around the `{% include "components/consent_banner.html" %}` in all 5 templates:

| Template | Include Line | Guard |
|----------|-------------|-------|
| `src/backend/templates/ads/dashboard.html` | 161 | `{% if not request.user.is_authenticated or not request.user.is_deleted %}{% include "components/consent_banner.html" %}{% endif %}` |
| `src/backend/templates/ads/detail.html` | 106 | (same guard) |
| `src/backend/templates/ads/list.html` | 56 | (same guard) |
| `src/backend/templates/analytics/seller_dashboard.html` | 128 | (same guard) |
| `src/backend/templates/analytics/moderation_dashboard.html` | 150 | (same guard) |

The `request.user.is_deleted` field is a `BooleanField(default=False)` on `User` (`users/models.py:53-56`). **There is no web-side `WebAccountStateMiddleware`** — the `MIDDLEWARE` list in `config/settings/base.py:111-121` contains only security, session, common, CSRF, auth, language, messages, and clickjacking middleware. The validated findings doc incorrectly cited `apps/web/middleware.py`; that path does not exist. Deleted users on the web side are **not redirected** — the banner renders in the initial template pass. The `{% if not request.user.is_authenticated or not request.user.is_deleted %}` guard is therefore the **primary fix**, not defense-in-depth. The `is_authenticated` check is essential: `AnonymousUser` has no `is_deleted` attribute, so a bare `not request.user.is_deleted` would raise `AttributeError` for anonymous users.

### Tests Required

| Scope | Test File | Test Case | Type | Key Assertions |
|-------|-----------|-----------|------|----------------|
| Integration | `apps/users/tests/test_consent.py` | `test_banner_hidden_for_deleted_user` | integration | Create a `User` with `is_deleted=True`; force_login; GET `/dashboard/`; assert `"consent-banner"` div NOT in response body |
| Integration | `apps/users/tests/test_consent.py` | `test_banner_shown_for_active_user` | integration | Active user (is_deleted=False, not consented); GET `/dashboard/`; assert consent banner div IS in response body |
| Unit | `apps/core/tests/test_templates.py` (NEW) | `test_consent_banner_guard_in_all_templates` | unit | Grep all 5 template files; assert each `consent_banner.html` include is wrapped in `{% if not request.user.is_authenticated or not request.user.is_deleted %}` guard |
| Integration | `apps/core/tests/test_sweep_commands.py` or `apps/users/tests/` | `test_is_deleted_flag_blocks_banner` | integration | Verify `User.is_deleted=True` causes `can_contact_seller` to return `False` (`contact.py:53`); verify deleted user sees no banner by checking the `is_deleted` guard path (no web middleware exists to redirect — the template guard is the primary gate) |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/01-spec/technical-specification.md` | Decision F (§1) | Add note: "No web-side middleware redirects deleted users; the consent banner include is guarded by `{% if not request.user.is_authenticated or not request.user.is_deleted %}` in all 5 template sites to prevent rendering for `is_deleted` users. (`AnonymousUser` lacks `is_deleted`, so `is_authenticated` is checked first.)" |
| `docs/02-database/db-schema.md` | User model (is_deleted field) | Confirm `is_deleted` is the canonical soft-delete flag used by the template guard; reference the 5 template sites that check it. |

---

## Already-Resolved / Rejected Findings (no action)

The following 6 findings were validated during the audit but require **no action** in this remediation cycle. They are included here for completeness.

| Finding | Status | Brief Reason |
|---------|--------|-------------|
| **PII-001** | ✅ Already resolved | `User.telegram_id` is already `BigIntegerField(unique=True, blank=True, null=True)` (`users/models.py:34-39`). The NOT NULL crash in `withdraw_consent()` is fixed. Prerequisite for PII-008. |
| **PII-005** | ❌ Rejected | The finding references `ConsentWithdrawView` (class-based) which doesn't exist — actual view is function `consent_withdraw()`. No rate-limiting infrastructure exists project-wide (login, contact, ad-create all unprotected). The single-use login token already provides natural rate limiting. Adding rate limiting to one endpoint is inconsistent security theater. |
| **PII-006** | ✅ Already resolved | `withdraw_consent()` at `deletion.py:132` already deletes ALL LoginTokens by `telegram_id` via `LoginToken.objects.filter(telegram_id=user_telegram_id).delete()`. `LoginToken.telegram_id` is already `BigIntegerField(blank=True, null=True)` (`models.py:135-138`). No FK migration needed. |
| **PII-007** | ✅ Already addressed | The 3 pending `ads` migration alterations are resolved by migrations `apps/ads/migrations/0005_alter_ad_category_name_alter_ad_description_and_more.py` and `apps/ads/migrations/0006_ad_ix_ads_purge_deleted_and_more.py` (both committed). `makemigrations --check` passes. `.env.example` already has `DJANGO_SECRET_KEY`. |
| **PII-010** | ✅ Already resolved | The `_CrashOnDeleteQuerySet` mock in `test_sweep_commands.py:402-416` already stubs `.exists()` (returns `True`), `.count()`, `.values_list()`, and `.delete()`. The crash-rollback test (`test_crash_between_updates_and_delete_rolls_back`) now passes. |
| **PII-011** | ✅ Already resolved | `LoginToken.returning` field and its `logger.info` reference in `login.py:157` do not appear in the current codebase — grep returns zero matches. The field was never added or was removed in a prior commit; the login flow is functional. |

---

## Rollout Ordering

Findings are implemented in dependency order. PII-001 (nullable telegram_id) is the **prerequisite** — it is already resolved, so all 5 actionable findings can proceed.

| Step | Finding | Risk | Notes | Status |
|------|---------|------|-------|--------|
| 1 | **PII-001** (prerequisite) | High | ✅ Already resolved — `User.telegram_id` nullable. Unblocks PII-008 transaction tests and PII-006 assertions. | ✅ Done |
| 2 | **PII-008** | High | ✅ Implemented — wrapped `withdraw_consent()` in `transaction.atomic()` + refactored `soft_delete_user_ads()` to DB-only (returns storage keys). `delete_photo()` after commit. Committed as `fix(withdraw): wrap withdraw_consent in transaction.atomic`. | ✅ Done |
| 3 | **PII-002** | Low | ✅ Implemented — created `mask_telegram_id()` in `sanitize.py`, applied to all 10 sites (7 logger + 3 stdout.write). Committed as `fix(pii): mask telegram_id in all logger and stdout output`. | ✅ Done |
| 4 | **PII-003** | Medium | ✅ Implemented — added "Withdraw Data" POST button on dashboard + `@require_POST` on view. Existing tests updated to POST. Committed as `feat(consent): add withdraw consent button to seller dashboard`. | ✅ Done |
| 5 | **PII-009** | Trivial | ✅ Implemented — added `{% if not request.user.is_authenticated or not request.user.is_deleted %}` guard in 5 templates. Committed as `fix(templates): guard consent banner for deleted users`. | ✅ Done |
| 6 | **PII-004** | Low | ✅ Doc-only — documented 30-day anonymized retention → hard-delete via `consent_hard_delete` sweep. Fixed `db-retention.md` DELETED retention from 30→120 days. Committed as `docs(pii): update retention, consent, and banner-guard documentation`. | ✅ Done |

### Backward Compatibility

- **PII-008** (transactional `withdraw_consent`): backward-compatible. The `transaction.atomic()` wrapper and `soft_delete_user_ads` return-type change are internal to the service layer. The `consent_withdraw` view calls the service without inspecting the return value.
- **PII-002** (masked logging): zero business-logic impact. Log output format changes (raw ID → hash); downstream log parsers must update if they parse telegram_id.
- **PII-003** (`@require_POST`): if applied, existing GET-based tests in `test_consent.py` must be updated to POST. If not applied, existing GET tests continue to pass unmodified. Browser users who bookmark the GET URL would still trigger withdrawal if `@require_POST` is not applied — this is the security trade-off.
- **PII-009** (template guard): zero logic impact. `is_authenticated` check ensures anonymous users are unaffected.
