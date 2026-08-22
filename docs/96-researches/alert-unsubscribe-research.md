---
id: alert-unsubscribe-research
domain: agent
tags:
  - research
  - telegram
  - alerts
related:
  - architecture
  - references
---

# Research: Saved-Search Alert Unsubscribe via Telegram

## Objective

Research the Mko Bazuna Telegram bot architecture to design saved-search alert
unsubscribe functionality (inline callback button + deep-link `/start` fallback).
This is a research-only report — no code changes were made.

## Implementation Status

**Outcome: Implemented.** Saved-search alert unsubscribe is implemented across the
bot:

- **Per-ad alert message builder** `build_alert_message` (`apps/search/services/immediate_alerts.py:90`):
  the inline alert message includes the ad title/city/price, an **absolute ad
  link** (`<a href="{SITE_URL}{reverse('ads:detail', args=[id])}">`,
  `ads/models.py:461 get_absolute_url`), and an inline keyboard button
  `callback_data=f"unsub:{token}"` (`UNSUB_CALLBACK_PREFIX = "unsub:"`).
- **Opaque token:** `SavedSearch.unsubscribe_token` =
  `secrets.token_urlsafe(24)` (32 URL-safe chars), stored in the DB, never derived
  from the PK (`search/models.py:113-138`).
- **Inline callback handler** `handle_unsubscribe_callback`
  (`telegram_bot/handlers/alerts.py:105`) matches `F.data.startswith("unsub:")`,
  looks up the `SavedSearch` by token, and enforces **ownership** by comparing
  `saved_search.user.chat_id == callback.from_user.id` (stable `chat_id`).
  Swaps the button to a re-enable (`unsub_on:`) variant. Symmetric
  `handle_reenable_callback` re-enables.
- **`/start unsub_<token>` deep-link branch** (`login.py:60` delegates to
  `alerts.handle_unsubscribe_start`) matches
  `UNSUB_DEEPLINK_PATTERN = r"^unsub_([A-Za-z0-9_-]{32})$"` and resolves via the
  same `resolve_unsubscribe(token, chat_id)` ownership check. `alerts_router` is
  registered in `telegram_bot/main.py:50` and the test conftest.

> **Deviation:** the per-ad message + inline unsubscribe is present **only on the
> publish-time (immediate) path**. The daily `send_alerts` digest sends a
> consolidated plain-text summary with **no** absolute ad links and **no** inline
> unsubscribe button. `/start unsub_<token>` and the inline button only disable
> (re-enable is via the inline `unsub_on:` button + `/alerts`). See
> `.ai/audit/problems/17_doc-update-discrepancies-plan14-16.md` #6.

## Scope of Investigation

Five areas:

1. Bot entrypoint & router wiring
2. Deep-link `/start` payload parsing & delegation
3. Django `Signer` compatibility with Telegram deep-link charset
4. SavedSearch model, `is_active` toggle, and alert sender
5. User model (`chat_id` vs `telegram_id`) and `AccountStateMiddleware`

## Findings

### 1. Bot entrypoint & router wiring

**File:** `src/telegram_bot/main.py`

- `main()` (line 21) reads `settings.BOT_TOKEN` (line 26). If empty, logs a
  warning and returns (dev mode) — lines 28-31.
- Uses `MemoryStorage` (line 39) — **FSM state is ephemeral**. The ad-creation
  FSM survives restarts only via `Ad.DRAFT` ORM rows, not FSM state — lines 33-38.
  Note: the `/alerts` listing handler stores `user_id` in FSM state (see §2).
- `Dispatcher` (line 40), `AccountStateMiddleware` registered on `dp.message`
  only (line 43) — **not on `dp.callback_query`** (but the middleware extracts
  `from_user.id` from callback events anyway, see §5).
- Routers included (lines 46-51): `login_router`, `ad_create_router`,
  `alerts_router`, `ad_copy_router`.
- `dp.run_polling(bot)` (line 58). Bot runs as `python -m telegram_bot.main`
  in Docker (docker-compose.yml:168).

**Test harness** (`src/telegram_bot/tests/conftest.py:38-55`) replicates
`main()` but includes only `login_router` and `ad_create_router` in the test
`Dispatcher` — **`alerts_router` is NOT registered in tests**. Callback-query
tests for unsubscribe must register the callback router.

### 2. Deep-link `/start` parsing & delegation

**File:** `src/telegram_bot/handlers/login.py`

- Handler: `@router.message(Command("start"))` at line 31 (`handle_login_deep_link`).
- Parsing is **manual** (no custom filter): `args = message.text.split(maxsplit=1)`
  (line 45); `deep_link = args[1]` (line 52). If no argument → welcome message
  (lines 46-50).
- `LOGIN_PATTERN = re.compile(r"^login_([A-Za-z0-9_-]{32})$")` (line 26).
  Group 1 captures the 32-char raw token; the handler hashes it with SHA-256
  immediately (line 69).
- `handle_login_orm` (lines 133-190) wraps the claim in `@sync_to_async` +
  `transaction.atomic`. The atomic claim uses raw `UPDATE ... RETURNING`
  (lines 112-130 in `_claim_login_token`) — PostgreSQL row lock, zero TOCTOU.
- **Delegation pattern:** `login.py:57` calls `handle_contact_start(message,
  bot, deep_link)` **before** checking `LOGIN_PATTERN`. If it returns `True`
  (handled), login returns early; if `False`, login processing continues.

**Contact deep-link** (`src/telegram_bot/handlers/contact.py:20-49`):
- `CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")` — `contact_` prefix
  followed by the numeric `ad_id`.

**Constraint — Telegram Bot API deep-link `/start` payload:**
- Maximum **64 characters**, charset `[A-Za-z0-9_-]` only.

### 3. Django `Signer` — incompatible with deep-link payloads

**Source:** `.venv/Lib/site-packages/django/core/signing.py`

- `_SEP_UNSAFE = _lazy_re_compile(r"^[A-z0-9-_=]*$")` (line 48). A separator
  is rejected if it consists **entirely** of `[A-z0-9-_=]` chars.
- `Signer.__init__` (line 203): default `sep=":"`. If
  `_SEP_UNSAFE.match(self.sep)` is truthy, raises `ValueError` (lines 217-221).
- Therefore a valid Django separator MUST contain at least one char **outside**
  `[A-z0-9-_=...]`.

**Empirically verified** (run against the project venv with the real Django
package):

| Separator | Django check | Telegram charset `[A-Za-z0-9_-]`? |
|-----------|-------------|-----------------------------------|
| `:` (default) | accepted | invalid char |
| `-` | rejected (`Unsafe Signer separator`) | valid char |
| `_` | rejected | valid char |
| `a` | rejected | valid char |
| `.` | accepted | invalid char |

The set of Django-"safe" chars `[A-z0-9-_=]` **supersedes** the Telegram
charset `[A-Za-z0-9_-]` — every Telegram-legal char is Django-"unsafe". No
separator can satisfy both: a Django-legal separator always contains a char
that violates the Telegram deep-link charset. The `Signer` output format is
`value + sep + signature`, where `value` and `signature` are already
base64url (`[A-Za-z0-9-_]`), so the separator is the only breaking element.

**Conclusion:** Django's `Signer` / `TimestampSigner` cannot produce a payload
that fits the Telegram deep-link charset. A **custom HMAC** (e.g.
`hmac.new(SECRET_KEY, payload, sha256).hexdigest()[:16]`) is required for any
signed deep-link fallback token. This is consistent with the existing
`LoginToken` approach, which stores a SHA-256 hash of a
`secrets.token_urlsafe(24)` raw token and never relies on `Signer`.

### 4. SavedSearch model & alert sender

**SavedSearch** (`src/backend/apps/search/models.py:47-113`):
- `user` FK → `users.User`, `related_name="saved_searches"` (lines 50-55).
- `is_active` `BooleanField(default=True)` (lines 87-90) — "Inactive searches
  do not receive notifications." **This is the unsubscribe toggle.**
- Index `IX_saved_searches_user_active` on `(user_id, is_active)` (lines 106-109).
- No `updated_at` field — only `created_at` (lines 98-101).

**Alert sender** (`src/backend/apps/search/management/commands/send_alerts.py`):
- Advisory-lock-gated: `AdvisoryLockId.ALERT_DELIVERY_TASK = 9`
  (`src/backend/apps/core/enums.py:31`).
- `_collect_alerts` (lines 78-115) iterates
  `SavedSearch.objects.filter(is_active=True)` (line 91) — **already filters on
  `is_active`**. Setting `is_active=False` immediately ceases future alert
  generation for that search.
- Groups notifications by `user_id` only (line 99-101): all of a user's
  matching ads are pooled into one digest — **not** grouped per-saved-search.
  Per-search unsubscribe is therefore possible (toggle `is_active`), but the
  digest message itself cannot attribute matches to individual searches without
  restructuring `_collect_alerts`.
- `_format_digest` (lines 182-195): plain text, `parse_mode="HTML"`, **no inline
  keyboard and no unsubscribe button** currently. Sends to `user.chat_id`
  (line 163).
- `_send_user_digests` (lines 134-180): looks up `User` by `id`, skips if no
  `chat_id` (line 149). Catches `TelegramBadRequest` /
  `TelegramForbiddenError` per user (lines 168-171).
- `find_matching_ads` (`src/backend/apps/search/services/alert_query.py:27-96`):
  excludes already-notified ads via correlated `NOT EXISTS` subquery on
  `SavedSearchNotification` (lines 90-94), caps at 10 per search.

### 5. User model & middleware

**User** (`src/backend/apps/users/models.py:12-116`):
- `telegram_id` `BigIntegerField(unique, blank=True, null=True)` (line 34) —
  **nullable**, nulled on GDPR withdrawal (`help_text` line 38). Do **not** use
  for lookup in bot/middleware.
- `chat_id` `BigIntegerField(unique, db_index=True)` (line 42) — "Stable
  Telegram chat ID; set on first bot contact, never nullified." This is the
  stable identifier.

**AccountStateMiddleware** (`src/telegram_bot/middlewares/permissions.py`):
- `BaseMiddleware` subclass (line 21). Registered on `dp.message` in `main.py:43`.
- `_get_user(chat_id)` (lines 154-170) looks up by stable `chat_id`. If
  `User.DoesNotExist`, returns `(True, "")` — treats unregistered users as
  allowed (line 110-111).
- For `callback_query` events (lines 60-66): extracts
  `event.callback_query.message` if it is a `Message`, then uses
  `message.from_user.id` as `chat_id` (line 75). So **callback-query events
  ARE subject to account-state checks** via this middleware.
- Block conditions checked (lines 113-123): `is_banned`, `is_deleted`,
  `is_declined`, `consent_revoked_at is not None`.
- Publish restriction (lines 127-152): `ads_auto_publish=False` blocks only
  `/post`, allows other commands.

### 6. Inline-button pattern (reference implementation)

**File:** `src/telegram_bot/handlers/ad_create.py`

- `InlineKeyboardBuilder` from `aiogram.utils.keyboard` (import line 15).
- `builder.button(text=..., callback_data=...)` (lines 907-919, 920).
- `builder.adjust(2)` (line 908) → `builder.as_markup()` (line 909).
- Callback handler: `@router.callback_query(AdCreateForm.purpose, lambda c: c.data
  and c.data.startswith("purpose:"))` (line 193). Calls `callback.answer()`
  (line 207) and `callback.message.edit_reply_markup(...)` (line 245).

**Constraint — Telegram callback_data:** max **64 bytes** (UTF-8), no charset
restriction.

### 7. Settings — domain config

**File:** `src/backend/config/settings/base.py`

- `SECRET_KEY = env("DJANGO_SECRET_KEY")` (line 42).
- `BOT_TOKEN = env("BOT_TOKEN", default="")` (line 49).
- `BOT_USERNAME = os.getenv("BOT_USERNAME", "")` (line 215) — used by
  `consent.py:191` to build `https://t.me/<BOT_USERNAME>?start=...`.
- **No `SITE_URL` / `SITE_ID` / `django.contrib.sites`** anywhere in
  `INSTALLED_APPS` (base.py:82-109), `base.py` (read to end), `prod.py`, or
  `.env.docker.example` (read to end, line 33). Docker Compose (read to end,
  line 210) also has no domain env var.

**Consequence:** No absolute site-domain is available in-process. Building an
absolute ad-detail URL requires a new `SITE_URL` setting. `Ad` has no
`get_absolute_url`; the ad-detail URL is `reverse("ads:detail", args=[ad.id])`
→ relative path `/<id>/` (ads/urls.py:25).

## Decision

**Use an opaque random token (option A) with an `is_active` toggle.**

- Add an `unsubscribe_token` column to `SavedSearch` (UUID4 hex, 32 chars) —
  generated server-side, stored in the DB. Do **not** expose the raw
  `SavedSearch.id` in the `callback_data`.
- Inline button `callback_data=f"unsub:{token_hex}"` → 41 bytes, well within
  the 64-byte callback budget. The callback handler looks up
  `SavedSearch` by `unsubscribe_token`, toggles `is_active`, and edits the
  message markup (swap button text to "🔕 Re-enable alerts" /
  "✅ Enabled" per the toggle state).
- For the deep-link `/start` fallback (when the bot needs to reach a user
  whose saved-search message is gone): use the **existing login deep-link
  flow** (`login.py`) to resolve the `User` via stable `chat_id`, then apply
  the unsubscribe token through the same `/start` handler delegation (mirror
  the `handle_contact_start` pattern at `contact.py:23`).
- Do **not** use Django `Signer` — verified incompatible with the 64-char
  `[A-Za-z0-9_-]` deep-link charset (§3).
- For ad-detail links inside alert messages: introduce a `SITE_URL` setting
  (currently absent) and construct absolute URLs in the digest. This is a
  prerequisite if ad links are desired in the alert message.

## Relevant Files

| File | Role |
|------|------|
| `src/telegram_bot/main.py` | Bot entrypoint; FSM, middleware, router setup |
| `src/telegram_bot/handlers/__init__.py` | Router exports |
| `src/telegram_bot/handlers/login.py` | Deep-link `/start` handler; LoginToken claim |
| `src/telegram_bot/handlers/contact.py` | Deep-link delegation pattern |
| `src/telegram_bot/handlers/alerts.py` | `/alerts` listing handler |
| `src/telegram_bot/handlers/ad_create.py` | InlineKeyboardBuilder + callback_query pattern |
| `src/telegram_bot/middlewares/permissions.py` | AccountStateMiddleware |
| `src/telegram_bot/tests/conftest.py` | Test bot/dp fixtures |
| `src/telegram_bot/tests/test_claim_login_token.py` | LoginToken claim tests |
| `src/backend/apps/search/models.py` | SavedSearch (`is_active` toggle) |
| `src/backend/apps/search/services/alert_query.py` | find_matching_ads |
| `src/backend/apps/search/management/commands/send_alerts.py` | Alert delivery command |
| `src/backend/apps/users/models.py` | User (chat_id, telegram_id), LoginToken |
| `src/backend/apps/users/views/consent.py` | login_issue / login_status (two-phase claim) |
| `src/backend/apps/core/enums.py` | AdvisoryLockId, AnalyticsEventType |
| `src/backend/apps/ads/urls.py` | `ads:detail` URL pattern |
| `src/backend/config/settings/base.py` | SECRET_KEY, BOT_TOKEN, BOT_USERNAME |
| `.env.docker.example` | Env var template (no SITE_URL) |
| `pyproject.toml` | aiogram>=3.15.0, Django>=5.2.16 |
| docker-compose.yml | Service topology |
