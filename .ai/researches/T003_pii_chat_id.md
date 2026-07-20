# Research Report: PII-001 — Stable Bot Identity via `chat_id`

**Task ID:** task_003_research_pii_chat_id  
**Date:** 2026-07-20  
**Status:** COMPLETE — RECOMMENDATION: GO-WITH-CHANGES  
**Feeds:** task_034_pii_chat_id (PII-001)

---

## 1. Problem Statement (PII-001, CRITICAL)

`withdraw_consent()` (`apps/users/services/deletion.py`) sets `telegram_id = None`
immediately on consent withdrawal (the comment says "breaks chat linkage").

The bot permission middleware identifies every inbound message sender by
`User.objects.get(telegram_id=message.from_user.id)`
(`telegram_bot/middlewares/permissions.py:155`). For a withdrawn user, `telegram_id`
is `NULL`, so the lookup raises `User.DoesNotExist` and the middleware returns
`(True, "")` — *"User not registered yet"* — i.e. it treats the revoked identity as a
**fresh, unrestricted user** and grants full bot access (posting, contact, etc.).

This is a privilege-escalation / access-control bypass: a user who explicitly
withdrew consent and was soft-deleted can immediately re-engage the bot as if they
had never had an account.

### Root cause

`telegram_id` is overloaded with two conflicting roles:

1. **PII / auth identifier** — nulled on GDPR withdrawal.
2. **Stable routing & lookup key** — the bot's only way to recognise a returning sender.

When role (2) depends on role (1), erasing the PII also erases the bot's ability to
recognise and re-block the user.

---

## 2. Proposed Schema Change

Introduce a dedicated, stable routing key that is **decoupled from PII erasure**:

```python
# apps/users/models.py — User
chat_id = models.BigIntegerField(
    unique=True,
    db_index=True,
    null=True,                       # nullable only during the one-time backfill window
    help_text="Stable Telegram private-chat id; set on first bot contact, "
              "NEVER nullified on consent withdrawal. Bot lookup/routing key.",
)
```

### Why `chat_id` and not reusing `telegram_id`

For a private 1:1 chat, `telegram_id == chat_id` (the private chat id equals the
user id). The value is identical; the *semantic contract* differs:

| Column | Role | Nulled on withdraw? | Used by |
|--------|------|---------------------|---------|
| `telegram_id` | PII / web-login auth key (`USERNAME_FIELD`) | Yes (erasure) | web login token claim, Django auth |
| `chat_id` | Stable bot routing/lookup key | **Never** | bot middleware, contact delivery, analytics attribution |

Keeping `chat_id` non-null after withdrawal lets the bot still find the row and
enforce `is_deleted` / `consent_revoked_at` gating.

---

## 3. Migration + Backfill Strategy

### Recommended approach (Option 2 — preferred, see §6)

Because `chat_id` should be `NOT NULL` for *every* routable user (including already
withdrawn ones, to close the legacy hole), the cleanest path is to **stop nulling
`telegram_id` at withdraw time** and instead erase it only at the scheduled
hard-delete (already documented in `models.py:68`: *"telegram_id nulled 30 days
after consent withdrawal"*). This means `telegram_id` is non-null throughout the
entire soft-delete window, so the backfill is total and `chat_id` can be `NOT NULL`
unconditionally.

**Migration sequence (3 operations):**

1. `AddField` — `chat_id = BigIntegerField(unique=True, db_index=True, null=True)`.
2. `RunPython` (data) — backfill:
   ```sql
   UPDATE users SET chat_id = telegram_id WHERE telegram_id IS NOT NULL;
   ```
   With Option 2, `telegram_id` is never nulled at withdraw, so **every** row is
   backfilled. No `NULL` `chat_id` remains.
3. `AlterField` — set `chat_id` to `null=False` (enforce `NOT NULL` + uniqueness
   at the DB level). Safe because step 2 fully populated it.

A `SeparateDatabaseAndState` / `RunPython` pair keeps the migration reversible
(`reverse_code` sets `chat_id = NULL`).

> **Alternative (Option 1 — minimal, weaker):** keep `withdraw_consent` nulling
> `telegram_id`. Then already-withdrawn rows have `telegram_id IS NULL` and cannot
> be backfilled into a `NOT NULL` `chat_id`. Those legacy rows remain unlinkable and
> a returning withdrawn user would still be treated as fresh. Only future withdraws
> are fixed. Acceptable only if legacy withdrawn users are considered negligible
> (they hold no active ads and are `is_deleted`), but it does **not** fully close the
> bug. **Not recommended.**

### Uniqueness / downtime

- `chat_id` is `unique=True` → the backfill must not produce duplicates. Since
  `chat_id = telegram_id` and `telegram_id` is already `unique`, no collisions occur.
- Both are `BigIntegerField`, same domain → no type cast needed.
- The `UPDATE` touches every `users` row once. On PostgreSQL this is a fast,
  single-pass sequential scan + index update; for the expected row counts this is
  sub-second and requires **no downtime** (run as a normal online migration). For
  very large tables, wrap in a transaction; the lock is brief.
- After step 3, the unique index `users_chat_id_<hash>_uniq` backs every bot lookup
  (O(log n), index scan) — no query-plan regression vs. the current
  `telegram_id` unique lookup it replaces.

---

## 4. Lookup Call-Site Inventory (to rewrite for task_034)

All sites where `telegram_id` is used as the **bot identity / routing key**
(must switch to `chat_id`). Display-only log/string uses are listed separately.

### 4.1 Identity / routing lookups (must change)

| # | File | Line(s) | Current | Issue | Change |
|---|------|---------|---------|-------|--------|
| 1 | `telegram_bot/middlewares/permissions.py` | 155 | `User.objects.get(telegram_id=telegram_id)` | **The bug** — DoesNotExist → fresh user | `User.objects.get(chat_id=chat_id)` |
| 2 | `telegram_bot/handlers/login.py` | 142–143 | `User.objects.get_or_create(telegram_id=telegram_id, ...)` | New withdrawn user re-created as fresh | `get_or_create(chat_id=chat_id, ...)`; set `chat_id` in `defaults` too |
| 3 | `telegram_bot/handlers/contact.py` | 175 | `User.objects.get(telegram_id=buyer_telegram_id)` | Analytics attribution misses withdrawn users | `User.objects.get(chat_id=buyer_chat_id)` |
| 4 | `telegram_bot/handlers/contact.py` | 146, 155 | `seller.telegram_id` returned as send target | Routing key nulled on withdraw | return `seller.chat_id` |
| 5 | `backend/apps/core/services/contact.py` | 119 | `User.objects.get(telegram_id=buyer_telegram_id)` | Analytics attribution | `User.objects.get(chat_id=buyer_chat_id)` |
| 6 | `backend/apps/core/services/contact.py` | 50, 92 | `seller.telegram_id is None` gate | Routability gate breaks when nulled | `seller.chat_id is None` (still ANDed with `is_deleted`/`is_banned`/`consent_revoked_at`, which already block) |

### 4.2 Send-target (routing) usage

| File | Line | Note |
|------|------|------|
| `telegram_bot/handlers/contact.py` | 91 | `bot.send_message(chat_id=seller_telegram_id, ...)` — value now sourced from `seller.chat_id` (item 4). |

### 4.3 Display / logging only (cosmetic, switch to `chat_id` or `id`)

| File | Line(s) | Note |
|------|---------|------|
| `backend/apps/users/services/account_state.py` | 66, 70, 74, 96 | `logger.info(f"User {user.telegram_id} ...")` — would log `None` after nulling; use `user.chat_id` or `user.id`. |
| `backend/apps/users/admin.py` | 20, 34, 61, 63, 64 | `list_display`/`search_fields` `telegram_id` — add `chat_id` column for ops visibility. |
| `backend/apps/ads/admin.py` | 23–29 | `user_link` shows `obj.user.telegram_id` — display only. |
| `backend/apps/analytics/admin.py` | 31–36 | display only. |
| `backend/apps/moderation/admin.py` | 20–26 | display only. |
| `backend/apps/moderation/admin_actions.py` | 89 | `logger.info(f"User {user.telegram_id} banned ...")` — display only. |

### 4.4 `LoginToken.telegram_id` (separate table — out of scope but note)

`LoginToken.telegram_id` (`models.py:119`) is a claim-stamp set by the bot on
`/start login_<token>` (`login.py:119`) and invalidated in `deletion.py:60`. Its
value equals the sender's chat id. It is **not** the `User` FK and works unchanged
under either option (with Option 2 `telegram_id` stays non-null, so the
`filter(telegram_id=user_telegram_id).delete()` still matches). Optional clarity
rename to `chat_id` in a follow-up; not required for the fix.

### 4.5 Direct `telegram_id` queries (web/admin, not bot key)

- `moderation/admin_actions.py:179` `User.objects.filter(telegram_id__in=user_ids)`
  — **bug, see §7**. Filters `telegram_id` with `User.id` PKs; unrelated to PII-001
  but should be `id__in=user_ids`.
- All other `telegram_id` references are tests, migrations, or docstrings.

---

## 5. Gating Logic Confirmation

The required gating (`is_deleted`, `consent_revoked_at`) **can be enforced via
`chat_id` lookup**:

```python
# permissions.py — target behaviour
user = await self._get_user(chat_id)        # chat_id never nulled → finds withdrawn user
if user.is_banned:        return (False, "…banned…")
if user.is_deleted:       return (False, "…deleted…")          # ← withdrawn user blocked here
if user.consent_revoked_at is not None:
    return (False, "…consent revoked…")     # optional explicit gate
```

Because `chat_id` is preserved on withdrawal, the lookup **succeeds** for a returned
withdrawn user, and the existing `is_deleted`/`consent_revoked_at` checks correctly
reject them. Fresh (never-seen) users still raise `DoesNotExist` → `(True, "")`,
preserving the intended "register on first login" flow. The hole is closed:

- **Before:** withdrawn user → `telegram_id` NULL → lookup misses → treated as fresh.
- **After:** withdrawn user → `chat_id` present → lookup hits → `is_deleted` blocks.

`/post` publish gating (`_check_publish_permission`) already calls the same
`_get_user`, so it inherits the fix automatically.

---

## 6. Verdict: GO-WITH-CHANGES

**Proceed with task_034, adopting Option 2.**

### Reasons to proceed

1. The bug is real, critical (access-control bypass), and the fix is contained:
   one new column, one backfill migration, and a small set of well-isolated lookup
   rewrites (§4.1, six sites).
2. `chat_id == telegram_id` for private chats, so no new data source is needed; the
   backfill is a straight column copy and uniqueness is guaranteed by inheritance
   from `telegram_id`'s existing unique constraint.
3. The gating logic is fully enforceable via `chat_id` (§5); `_get_user` is the
   single choke point for both interaction and publish checks.
4. Option 2 also resolves a latent contradiction: `models.py:68` documents
   *"telegram_id nulled 30 days after consent withdrawal"*, but `withdraw_consent`
   nulls it immediately. Routing via `chat_id` lets us honour that 30-day deferral,
   improving both GDPR correctness and security.

### Changes required (handed to task_034)

1. **Model** (`apps/users/models.py`): add `chat_id` `BigIntegerField(unique=True,
   db_index=True, null=True)`. Keep `telegram_id` as `USERNAME_FIELD` for web auth.
2. **Migration**: `AddField` → `RunPython` backfill (`chat_id = telegram_id`) →
   `AlterField` to `null=False`. Reversible.
3. **`deletion.withdraw_consent`** (behavioural, Option 2): **do not null
   `telegram_id` at withdraw**; null it only at the scheduled hard-delete
   (`hard_delete_at`). This guarantees a complete backfill and closes the legacy
   hole. Keep `is_deleted=True`, `consent_revoked_at`, token invalidation, ad
   soft-delete.
4. **`permissions.py`**: `_get_user` looks up by `chat_id`; rename the param from
   `telegram_id` to `chat_id` and thread `message.from_user.id` as the chat id.
5. **`login.py`**: `get_or_create_user` keys on `chat_id`; set `chat_id` in
   `defaults`.
6. **`contact.py`** (bot) & **`core/services/contact.py`**: use `chat_id` for buyer
   attribution and for the seller send-target / routability gate.
7. **Logging/display** (§4.3): switch `user.telegram_id` log/display strings to
   `user.chat_id`/`user.id`; optionally expose `chat_id` in `users/admin.py`.

### Residual / notes

- LoginToken.telegram_id rename is optional (§4.4).
- The moderation `telegram_id__in` bug (§7) is tracked separately and must NOT be
  fixed inside task_034.

---

## 7. Unrelated Bug Found

While mapping call sites, `moderation/admin_actions.py:179` was found to filter
`User.objects.filter(telegram_id__in=user_ids)` where `user_ids` are `User.id` PKs
(not Telegram ids) — a silent no-op / wrong-target bulk ban. Filed separately at
`.ai/audit/00-bug_report/01-report.md`. Not in scope for task_034.

---

## 8. Files Inspected (read-only)

- `src/backend/apps/users/models.py`
- `src/backend/apps/users/services/deletion.py`
- `src/backend/apps/users/services/account_state.py`
- `src/backend/apps/users/admin.py`
- `src/backend/apps/users/migrations/0001_initial.py`
- `src/telegram_bot/middlewares/permissions.py`
- `src/telegram_bot/handlers/login.py`
- `src/telegram_bot/handlers/contact.py`
- `src/backend/apps/core/services/contact.py`
- `src/backend/apps/core/templatetags/contact_tags.py`
- `src/backend/apps/ads/admin.py`
- `src/backend/apps/analytics/admin.py`
- `src/backend/apps/moderation/admin.py`
- `src/backend/apps/moderation/admin_actions.py`

No source files were modified for this research. Implementation is tracked in
task_034_pii_chat_id.
