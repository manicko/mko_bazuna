---
id: contact-us
domain: spec
tags:
  - contact
  - bot-username
  - anti-spam
  - obfuscation
  - deep-link
  - rate-limiting
  - siteconfig
related:
  - spec-index
  - ui-patterns
  - architecture-structure
  - db-schema
  - url-state-preservation
---

## Purpose

Document the contact-us architecture introduced by Spec 18: the centralized,
admin-configurable Telegram bot username, the spam-protected deep-link
rendering pipeline (CSS `direction: rtl` + JS click-to-reveal), the bot-side
`contact_us` handler with Telegram-bypass button, and the dual-layer rate
limiting (web + bot) that protects the bot username from automated extraction.

This doc is the single source of truth for how bot usernames are surfaced to
users and bots across the site; other docs ([ui-patterns.md](ui-patterns.md),
[architecture-structure.md](architecture-structure.md),
[db-schema.md](../02-database/db-schema.md)) link here rather than restating
the rules.

## Main Concepts

### Bot username centralization

The bot username is no longer read from the `BOT_USERNAME` environment
variable at render time. It lives in a single-row singleton model, editable in
Django admin, with a 1-hour cache:

| Layer | Component | Location |
|---|---|---|
| Storage | `SiteConfig.bot_username` (`CharField`, `RegexValidator ^[A-Za-z0-9_]{3,32}$`) | `apps/core/models.py` |
| Seed migration | `0003_add_bot_username` — seeds from `settings.BOT_USERNAME` env var (seed value only) | `apps/core/migrations/0003_add_bot_username.py` |
| Service | `get_bot_username()` / `get_bot_username_async()` — cached, 1-hour TTL, falls back to `bazuna_bot` | `apps/core/services/site_config.py` |
| Cache | `get_cached_site_config()` / `set_cached_site_config()` — key `site_config:v1` | `apps/core/utils/cache.py` |
| Invalidations | `post_save` receiver on `SiteConfig` clears cache | `apps/core/signals.py` |
| Admin | `SiteConfigAdmin` — `list_display = ["name", "bot_username"]`, no add/delete (singleton) | `apps/core/admin.py` |

All templates and views resolve the bot username through `get_bot_username()`
**only** — `settings.BOT_USERNAME` is a seed value consumed exclusively by the
migration and is **not** a runtime source after migration 0003.

### Deep-link rendering: the `telegram_deep_link` template tag

All bot deep-link URLs are rendered through a single template tag, not by
inlining `https://t.me/{{ bot_username }}` in templates. The tag is registered
in `apps/core/templatetags/telegram_tags.py` and accessed via
`{% load telegram_tags %}`.

| Argument | Deep-link target | `start` payload |
|---|---|---|
| `"contact_us"` | Footer "Contact us" | `start=contact_us` (general site support) |
| `"create_ad"` | Header "Submit an ad" CTA | `start=create_ad` |
| `"contact"` | Ad detail "Contact Seller" | `start=contact_<ad_id>` |
| `"login"` | Login issue deep-link | `start=login_<token>` |

**Rendering strategy (defense in depth):**

1. The anchor's `href` is set to `#` in the server-rendered HTML. The real
   `t.me://<bot_username>?start=<payload>` URL is assembled by JavaScript on
   click from a **base64-encoded** `data-bot-encoded` attribute. This means
   scrapers that read static HTML (no JS execution) never see the bot username
   or even the deep-link URL.

2. The visible display text (where it shows the bot username, e.g.
   `@botname` in `@<username>`) is obfuscated with the `rtl_obfuscate` filter
   — the string is reversed in the HTML text node and flipped back to readable
   form visually by the `.bot-username-rtl { direction: rtl; unicode-bidi: bidi-override; }`
   CSS class. A visually-hidden `<span class="sr-only">` provides the clean
   text for screen readers.

3. A JS-execution-proof cookie (`js=true`, session-scoped) is set by the
   footer include. The tag emits its `data-*` attributes unconditionally; the
   cookie is a defense-in-depth signal rather than a hard gate (see
   [Discrepancy 1](./problems/discrepancy-spec-17-18.md#discrepancy-1)).

4. **No `<noscript>` fallback** is provided for contact links — if JavaScript
   is disabled, the link is inert (`#`), and the buyer cannot deep-link to the
   bot. This is an intentional product decision (Q8=C: DECLINE — no noscript
   fallback).

### Contact-us flows

| Entry point | Trigger | Bot response |
|---|---|---|
| Footer "Contact us" (all public pages) | `{% telegram_deep_link "contact_us" %}` → `start=contact_us` | Greeting + site-support instructions |
| Ad detail "Contact Seller" | `{% telegram_deep_link "contact" ad_id=... %}` → `start=contact_<ad_id>` | Routes to seller via the bot relay (ad-scoped) |
| Header "Submit an ad" | `{% telegram_deep_link "create_ad" %}` → `start=create_ad` | Starts the ad-creation FSM flow |
| Login issue deep-link | `{% telegram_deep_link "login" token=... %}` → `start=login_<token>` | Authenticates the buyer (one-time token) |
| Bot menu "Contact us" button (Telegram-bypass) | Bot-side inline/reply keyboard button | Same `contact_us` handler flow |

Buyers who open `t.me/<bot_username>` directly in Telegram (without clicking a
web deep-link) see a "Contact us" button in the bot's main menu. Pressing it
triggers the same `contact_us` handler as the `/start contact_us` deep-link.
The bot checks `message.from_user.is_bot` and rejects bot accounts immediately.

### Rate limiting (dual-layer)

| Layer | Trigger | Limit | Key storage | Location |
|---|---|---|---|---|
| Web (render) | Per-IP rendering of the deep-link page | 5 renders per 10 min per IP | Django rate-limit (nginx zone or Django decorator) | `apps/core/views.py` + nginx `location` |
| Bot (start) | Per-telegram-user `/start contact_us` | 5 per 10 min per `user_id` | In-memory / Redis counter | `telegram_bot/services/rate_limit.py` |
| Autocomplete | Per-IP autocomplete requests | 30 per minute per IP | In-memory window | `apps/search/views/autocomplete.py` |
| Login deep-link | Per-IP `/login/issue/` | 10 req/s burst 20 | nginx `login_limit` zone | nginx config |

The bot-side check (`check_contact_start_rate_limit`) returns a cooldown
message when exceeded rather than failing silently. See
[architecture-structure.md](architecture-structure.md#rate-limiting-summary)
for the consolidated table.

### JavaScript-execution gate

A `js=true` session cookie is set by the footer JS on first page load,
proving the client executed JavaScript. The `telegram_deep_link` tag's
`data-*` attributes (the base64-encoded URL payload) are emitted to all
clients; the cookie is an **additional signal** for bot-side or future
server-side gating, not a render-time gate. The primary anti-bot mechanism is
the click-to-reveal JS assembly of the `t.me://` URL — static HTML never
contains the bot username or deep-link URL.

## Implementation summary

| Concern | Implementation | Canonical location |
|---|---|---|
| Bot username model | `SiteConfig.bot_username` with `RegexValidator` | `apps/core/models.py` |
| Bot username service | `get_bot_username()` / `get_bot_username_async()` | `apps/core/services/site_config.py` |
| Cache | `get_cached_site_config` / `set_cached_site_config` (1h TTL) | `apps/core/utils/cache.py` |
| Cache invalidation | `post_save` receiver | `apps/core/signals.py` |
| Admin | `SiteConfigAdmin` (singleton: no add/delete) | `apps/core/admin.py` |
| Deep-link rendering tag | `telegram_deep_link` + `rtl_obfuscate` filter | `apps/core/templatetags/telegram_tags.py` |
| JS-execution cookie | `js=true` session cookie, set by footer | `templates/components/footer.html` |
| Web rate limiting | Per-IP render cap (Django + nginx) | `apps/core/views.py` |
| Bot contact_us handler | `/start contact_us` deep-link + Telegram-bypass button | `telegram_bot/handlers/contact.py` |
| Bot rate limiting | `check_contact_start_rate_limit` | `telegram_bot/services/rate_limit.py` |
| Migration | `0003_add_bot_username` seeds from env var | `apps/core/migrations/0003_add_bot_username.py` |

## Related user stories

- [US-B13](../04-user-stories/buyer-stories.md) — Footer "Contact us" link (visible to all visitors, no consent gate)
- [US-S12](../04-user-stories/seller-stories.md) — Bot "Contact us" button (Telegram-bypass for direct-openers)
- [US-B5](../04-user-stories/buyer-stories.md) — Contact Seller button on ad detail
- [US-S7](../04-user-stories/seller-stories.md) — "Submit an ad" deep-link from header CTA

## Discrepancies & known gaps

See the consolidated discrepancy report: [`00-discrepancy-report-url-state-and-contact-us.md`](../../.ai/audit/problems/00-discrepancy-report-url-state-and-contact-us.md). Key items:

- **CSS class verification:** The `.bot-username-rtl` CSS rule (`direction: rtl; unicode-bidi: bidi-override`) is spec-required for display-text reversal. Audit finding F-BB-001 reports it absent from `input.css`/`output.css`; an implementation check reported it present. A re-verification grep is recommended.
- **`js_verified` gate:** The `telegram_deep_link` tag emits `data-*` attributes unconditionally rather than gating on `request.js_verified`. This is test-codified (current behavior) but deviates from a strict CR-11 interpretation.
- **`privacy.html`:** Audit F-BB-002 reported cleartext `{{ bot_username }}` at multiple lines; the implementation check reports full migration. A re-verification grep is recommended.
