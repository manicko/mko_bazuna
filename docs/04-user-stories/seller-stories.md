---
id: seller-stories
domain: user-stories
tags:
  - user-stories
  - seller
  - telegram-bot
related:
  - user-stories-index
  - technical-specification
  - db-schema
---

## Purpose

Seller-role user stories. Sellers interact only through the **Telegram bot** (phase 1).
Domain rules referenced as "decision X" live in
[technical-specification.md](../01-spec/technical-specification.md).

## Stories

### US-S1 — Login & Telegram binding
Site "Login via Telegram" opens a QR/code page encoding deep-link
`https://t.me/<bot_username>?start=login_<token>` (32-char URL-safe token). Tapping "Login" in
the bot writes the sender `telegram_id` into `login_tokens`; the site authenticates by `telegram_id`
(create/find). One-time atomic token, constant-time compare; expired/invalid tokens show a clear
retry path. Persistent session cookie. Re-login reuses the existing account. See decision H.

The shared header renders a persistent **Login** link (to `consent:login_issue`) for anonymous
visitors on all public pages. Once authenticated, sellers reach the dashboard (their cabinet) via
the header **Dashboard** link and log out via the header's POST+CSRF **Logout** form (logout is
POST-only — there is no dead GET logout link).

### US-S2 — Create ad via bot
Strictly step-by-step dialog: category → city → title → description → price (if applicable) →
photos, each confirmed. Category from the closed admin tree (bot suggests top 3–5; free-text as new
category rejected). 1–5 **Telegram-compressed** photos only (documents rejected). Preview before
send. On submit → `ON_MODERATION`, not visible until checks pass. Abandoned drafts auto-deleted on
idle timeout (~30 min); no partial ads saved. See decisions I, E.

### US-S5 — Edit ad
Seller edits description/price/photos. **Text edits** (title/description) →
`PUBLISHED → ON_MODERATION` and the ad is **hidden immediately** until it passes re-check
(zone C2). Price/photo edits publish instantly (≤5s). A mixed edit follows the text rule. See
decision J.

### US-S6 — Delete own ad
Seller deletes an ad → `DELETED` (soft), hidden from the site.

### US-S7 — Auto-archive & removal
2 months after last publish/edit → `ARCHIVED`; 4 months → permanently removed. Timers count from
`published_at` (reset on every `PUBLISHED` transition). Seller sees archived ads in the dashboard
and can reactivate them (text re-checked). See decision J.

### US-S8 — Delete account
Seller withdraws consent via a 'Withdraw Data' button on the dashboard (POST, CSRF-protected, confirmation dialog); ads are soft-deleted; `telegram_id`/`username` are nulled exactly **30 days** after `consent_revoked_at` (decision F / zone R1). Independent of the
`ads_auto_publish` flag (US-S9). Re-registration only allowed after the 30-day null (zone R9).

### US-S9 — Publishing ban
`ads_auto_publish=False` blocks new ads and hides existing ads (not deleted). Reversible;
independent of account deletion and account ban (decision O1).

### US-S10 — Seller dashboard statistics
Seller views per-ad analytics on the dashboard: total views, total contacts, ads published,
and per-ad view counts filtered by time range (all time, last 30 days, last 7 days).
Statistics are cached for 5 minutes and aggregated from `AnalyticsEvent` records.
See decision P.

### US-S11 — View ad analytics
Seller sees per-ad view and contact statistics on the ad detail page in the dashboard.
Individual `AD_VIEWED` events are recorded when buyers view ad details (seller-scoped).
See decision P.

### US-S12 — Bot "Contact us" button (Telegram-bypass)
Sellers and buyers who reach the bot directly in Telegram (without clicking a web deep-link —
e.g., they opened `t.me/<bot_username>` directly) have a **"Contact us"** button (inline keyboard
or reply keyboard) available in the bot interface. Pressing it triggers the same `contact_us`
flow as the `/start contact_us` deep-link, showing a greeting and support instructions.
Bot-side `is_bot` check and per-user rate limiting apply (5 `contact_us` starts per 10 min
per Telegram user). See Spec 18 CR-4/CR-5/CR-10.

**Acceptance criteria:**
- AC1: A "Contact us" button is rendered in the bot's main menu or `/start` response.
- AC2: Pressing the button triggers the `contact_us` handler (same as `/start contact_us`
  deep-link from the footer).
- AC3: The bot replies with a greeting and brief support instructions (no ad context).
- AC4: `message.from_user.is_bot` is checked — bot accounts are rejected immediately.
- AC5: Per-Telegram-user rate limiting: max 5 `contact_us` starts per 10 minutes per `user_id`
  (`check_contact_start_rate_limit`); excess triggers return a cooldown message.
