---
id: contact-us
problem: "Add contact-us footer link (protected from scrapers), centralize bot username in admin, and add anti-spam protection for Telegram deep-links"
source: ".ai/problems/Problem_02.md"
research: ".ai/research/04_telegram-contact-antispam-research.md"
date: 2026-09-05
status: Signed-off (PO confirmed Q1=A, Q2=A, Q3=A, Q4=A, Q5=A, Q6=A, Q7=A, Q8=C)
---

# Specification 18 — Contact-Us Footer Link, Bot Username Centralization & Anti-Spam Protection

> **Problem:** The site has no general "Contact us" entry point in the footer — only a per-ad
> "Contact Seller" button (`ad_detail` page) that uses `settings.BOT_USERNAME` for the Telegram
> deep-link. Three things are needed:
>
> 1. Add a "Contact us" link to the site footer that opens a Telegram chat with the bot (works for
>    both buyers and sellers).
> 2. Make the bot username admin-configurable via a `SiteConfig` singleton field (same pattern as the
>    site name), referenced from templates via a tag rather than `settings.BOT_USERNAME` directly.
> 3. Protect the bot username and all Telegram deep-link URLs from scraper bots — the username is
>    currently in cleartext inside `href` attributes and is trivially extractable via regex or DOM
>    parsing. The protection must be non-intrusive (no CAPTCHA widgets, no friction for real users).
>
> **Question posed:** *"What are modern practices for protecting Telegram bot usernames and
> contact deep-links from scraper bots, and what lightweight (non-annoying) human verification
> can we use?"*
>
> **Answer:** (Researcher analysis, 8 PO questions answered.) The recommended approach is a
> hybrid of CSS `direction: rtl` text reversal for visible display + JS `data-*` click-to-reveal
> for clickable hrefs, with click-to-reveal itself serving as the zero-friction human gate,
> layered by per-IP web rate limiting and per-Telegram-user bot-side rate limiting. Full
> analysis in [the research report](.ai/research/04_telegram-contact-antispam-research.md).

---

## 1. Problem Statement

### 1.1 Source (translated from Problem_02.md)

> 1) Add another user journey to the documentation — contacting the site (seller or buyer alike).
> 2) Add a "Contact us" link in the footer that leads to a Telegram bot connection. This must be
>    spam-protected.
> 3) Make the bot username configurable via the admin panel (just like the site name) — a template
>    tag that pulls the value from the DB so it auto-populates everywhere it's used (`@bazuna_bot`).
>    The tag must be implemented with parser/spam protection everywhere it appears.
> 4) Anti-spam protection for the bot username and links. We need to study modern practices for
>    protecting such links. How email and contacts in Telegram are hidden from parsers and bots —
>    some kind of "are you human" check. Must not be annoying.

### 1.2 Current State

The bot username (`bazuna_bot`) is sourced from `settings.BOT_USERNAME` (env var) and passed to
templates via the `header_context` context processor. It appears in **cleartext inside `href`
attributes** across 7 locations:

| # | Template | Line | Usage | Protection |
|---|---|---|---|---|
| 1 | `footer.html` | (new) | Footer "Contact us" link → `t.me/<bot_username>?start=contact_us` | Not yet implemented |
| 2 | `ads/detail.html` | 167 | Contact Seller button → `t.me/<bot_username>?start=contact_<ad_id>` | None (cleartext href) |
| 3 | `components/header_catalog.html` | 33 | Submit an ad CTA → `t.me/<bot_username>?start=create_ad` | None (cleartext href) |
| 4 | `privacy.html` | 30 | Contact us link → `t.me/<bot_username>` | None (cleartext href + display) |
| 5 | `privacy.html` | 33 | Display text `@<bot_username>` | None (cleartext) |
| 6 | `privacy.html` | 111 | `<code>t.me/<bot_username></code>` (legal disclosure) | None (cleartext) |
| 7 | `privacy.html` | 148 | Contact us link → `t.me/<bot_username>` | None (cleartext href + display) |
| 8 | `users/login_issue.html` | 21, 40 | Login deep-link → `t.me/<bot_username>?start=login_<token>` | None (cleartext href) |

**Problem:** A scraper reading `response.html` or `soup.find('a')['href']` extracts the bot username
instantly. There is zero obfuscation. The username is hardcoded in an env var, not admin-editable,
and there is no rate limiting on contact deep-link discovery or bot-side `/start` triggers.

### 1.3 Three Sub-Problems

| Sub-problem | What | Scope |
|---|---|---|
| **SP-1 (Footer link)** | Add a "Contact us" link in `footer.html` visible to all visitors, leading to a Telegram deep-link with `?start=contact_us` payload | New footer link only (existing per-ad "Contact Seller" is out of scope for the link itself) |
| **SP-2 (Bot username centralization)** | Migrate `bot_username` from `settings.BOT_USERNAME` env var into `SiteConfig` singleton as a new field, served via `get_bot_username()` service + cache, editable in Django admin | Model, service, migration, admin, all consumers |
| **SP-3 (Anti-spam protection)** | Obfuscate the bot username in all 8 template locations so scrapers can't extract it from static HTML; add non-intrusive human verification (click-to-reveal gate + rate limiting) | Templates, new template tag, bot-side handler, rate limiting |

---

## 2. Confirmed Requirements

### CR-1: Bot username configurable via admin (SiteConfig singleton)

**When** an admin edits the site configuration in Django admin,

**Then** the `SiteConfig` singleton model has a `bot_username` field that stores the Telegram bot
username **without** the `@` prefix. The field is admin-editable, validated with a `RegexValidator`
(alphanumeric + underscore, 3–32 characters), and cached with the existing 1-hour TTL via
`SITE_CONFIG_CACHE_KEY`. The existing `post_save` signal on `SiteConfig` (`/core/signals.py:18`)
already invalidates the cache — no new signal needed.

**Priority:** High.

### CR-2: Templates access bot username via service, not settings

**When** any template needs the bot username,

**Then** it is resolved through a `get_bot_username()` / `get_bot_username_async()` service
(mirroring `get_site_name()` / `get_site_name_async()` in `services/site_config.py`), which reads
from the `SiteConfig` singleton cache. Templates must **never** reference `settings.BOT_USERNAME`
or `{{ bot_username }}` as a raw cleartext context variable. Instead, a `telegram_deep_link`
template tag encapsulates the obfuscation logic and resolves the username from the service at render
time.

**Priority:** High.

### CR-3: Footer "Contact us" link visible to all visitors

**When** the footer component renders on any public page (detail, listings, search, privacy),

**Then** a "Contact us" link is displayed in the footer navigation, visible to all visitors
regardless of consent state (ACCEPTED, DECLINED, or no consent banner interaction). The link opens
`https://t.me/<bot_username>?start=contact_us` (the `contact_us` deep-link payload, no `ad_id`).

**Priority:** High.

### CR-4: Bot has a `contact_us` deep-link handler

**When** the bot receives `/start contact_us` (from the footer link),

**Then** the bot responds with a greeting and basic support instructions (no ad context needed —
this is a general site contact flow, not a per-ad contact). Returns `True` from the handler so the
`/start` router delegates correctly.

**Priority:** High.

### CR-5: Bot has a "Contact us" button for Telegram-bypass users

**When** a seller or buyer is already in a Telegram chat with the bot (Telegram-bypass, not coming
from a web deep-link),

**Then** a "Contact us" button (inline keyboard or reply keyboard) is available that triggers the
same `contact_us` flow as the deep-link handler. This covers users who found the bot via
`t.me/<bot_username>` directly (without `?start=contact_us`).

**Priority:** Medium.

### CR-6: Bot username obfuscated in all template locations

**When** the bot username appears in a template (as visible display text or as a clickable
`href`),

**Then** it is obfuscated using a layered approach:
- **Visible display text** (e.g., `@{{ bot_username }}` in the privacy page, the `<code>` block at
  `privacy.html:111`): protected with CSS `direction: rtl` + `unicode-bidi: bidi-override`
  (the reversed string is in the HTML text node, flipped visually by CSS). Zero JS required.
- **Clickable deep-link hrefs** (Contact Seller button, Submit an ad CTA, footer link, login
  deep-link, privacy page contact links): the real `t.me://` URL is **never** in the static HTML
  `href`. Instead, the username is base64-encoded in a `data-*` attribute, and an inline `<script>`
  click handler assembles the real URL at click time. The static `href` is `#` (or absent).

**Priority:** High.

### CR-7: Click-to-reveal is the human gate (no CAPTCHA widget)

**When** a visitor clicks a contact button/link that triggers the deep-link URL assembly,

**Then** the click event itself (JS execution) is the human verification — no CAPTCHA widget, no
modal, no puzzle. The click fires the JS that decodes the `data-*` attribute and navigates to
Telegram. This is zero-friction for real users.

**Priority:** High.

### CR-8: No `<noscript>` fallback for contact links

**When** JavaScript is disabled,

**Then** the contact links are non-functional (`href="#"` does nothing). No `<noscript>` fallback
text or alternative link is provided. The project already requires JS for core functionality
(consent banner, autocomplete, city filter, login polling), so a no-JS experience is already
degraded. This is an explicit PO decision (Q8=C), overriding the research report's §7.6
recommendation.

**Priority:** Medium (accepted risk).

### CR-9: Bot username storage format (admin + display)

**When** an admin enters the bot username in Django admin,

**Then** it is stored **without** the `@` prefix (e.g., `bazuna_bot`, not `@bazuna_bot`). Input is
validated: alphanumeric characters and underscore only, 3–32 characters. The admin help text reads
"Telegram bot username without @ prefix". Templates prepend `@` only for display purposes (e.g.,
`<span>@</span><span class="bot-username-rtl">...</span>`).

**Priority:** High.

### CR-10: Rate limiting on deep-link discovery and bot-side `/start contact_us`

**When** an anonymous visitor loads pages with contact links (web-side) or a Telegram user initiates
`/start contact_us` (bot-side),

**Then**:
- **Web-side:** Per-IP rate limiting on deep-link page renders, using the existing `cache.add` +
  `cache.incr` pattern from `apps/search/services/rate_limit.py` — key `telegram_dl_rl:{ip}`,
  limit 60 page renders per 10 minutes per IP.
- **Bot-side:** Per-Telegram-user rate limiting on `/start contact_us` triggers, mirroring
  `check_upload_rate_limit` in `telegram_bot/services/rate_limit.py:26` — new function
  `check_contact_start_rate_limit(user_id, limit=5, period=600)` (5 starts per 10 minutes per
  Telegram user). Telegram's native `User.is_bot` check rejects bot accounts immediately.

**Priority:** Medium.

### CR-11: JS-execution proof cookie (invisible human gate)

**When** a page containing contact links is rendered,

**Then** a one-line inline script sets a `js=true` session cookie (`SameSite=Lax; Secure; path=/`).
A server-side check (middleware or context processor) reads `request.COOKIES.get("js")`. If the cookie
is absent (no-JS scraper using `requests`/`urllib`), the `telegram_deep_link` template tag emits
`href="#"` with no `data-*` attribute even at click time (graceful degradation). Real browsers that
execute JS always get the cookie.

**Priority:** Low (defense-in-depth layer, recommended by research §3.2).

---

## 3. Conceptual Development Tasks

### Task 1 — Migrate `bot_username` to `SiteConfig` singleton

- **Purpose:** Centralize the bot username as an admin-editable, cache-backed, cross-process value
  following the exact pattern established for the site name.
- **Expected outcome:** `SiteConfig.bot_username` field exists, served via `get_bot_username()` /
  `get_bot_username_async()` with cache; admin can edit it; existing `post_save` signal invalidates
  cache automatically.
- **Files:**
  - `apps/core/models.py` — add `bot_username` field (CharField, max 32, RegexValidator,
    `help_text="Telegram bot username without @ prefix"`)
  - `apps/core/services/site_config.py` — add `get_bot_username()` and `get_bot_username_async()`
  - `apps/core/migrations/0003_add_bot_username.py` (new) — add field + seed from `settings.BOT_USERNAME`
  - `apps/core/admin.py` — add `bot_username` to `list_display`, add `RegexValidator`
  - `config/settings/base.py:234` — keep `BOT_USERNAME` env var as **seed value only** for the
    migration; at runtime, read from `SiteConfig`
- **Dependencies:** None.

### Task 2 — Create `telegram_deep_link` template tag with JS click-to-reveal

- **Purpose:** Encapsulate the obfuscated deep-link HTML + inline JS in a reusable template tag,
  replacing all cleartext `{{ bot_username }}` references across 7 template locations.
- **Expected outcome:** A `{% telegram_deep_link "contact_us" %}`,
  `{% telegram_deep_link "contact" ad_id %}`, `{% telegram_deep_link "create_ad" %}`,
  `{% telegram_deep_link "login" <token> %}` tag that emits:
  ```html
  <a href="#" data-bot-encoded="<base64>" data-start="contact_<ad_id>"
     class="js-telegram-link" aria-label="{% trans "Contact Seller" %}" ...>
      {% trans "Contact Seller" %}
  </a>
  <script>(function(){ /* click handler: decode + assemble URL */ })();</script>
  ```
  The inline script follows the existing IIFE pattern (`header_catalog.html:218`, `login_issue.html:36`).
- **Files:**
  - `apps/core/templatetags/telegram_tags.py` (new) — `@register.simple_tag`
  - `apps/core/templatetags/__init__.py` (ensure package marker)
- **Dependencies:** Task 1 (bot_username in SiteConfig).

### Task 3 — Apply CSS `direction: rtl` for visible display text

- **Purpose:** Protect the visible `@bazuna_bot` display text (privacy page footer links, `<code>`
  block) using CSS text reversal, with `sr-only` pairing for screen-reader correctness.
- **Expected outcome:** A `bot-username-rtl` CSS class (`.bot-username-rtl { direction: rtl;
  unicode-bidi: bidi-override; }`) applied to reversed display text, paired with a visually-hidden
  `sr-only` element containing the clean text for accessibility. The `sr-only` Tailwind utility is
  already available.
- **Files:**
  - `templates/theme/css/input.css` (or compiled Tailwind output) — add the CSS rule
  - `templates/privacy.html` (lines 30, 33, 111, 148) — apply the technique to display text
  - A template filter `{{ bot_username|rtl_obfuscate }}` (optional, in `dict_tags.py` or
    `telegram_tags.py`)
- **Dependencies:** Task 2 (template tags package must exist).

### Task 4 — Add footer "Contact us" link

- **Purpose:** Add the new "Contact us" link to the footer, visible to all visitors regardless of
  consent state.
- **Expected outcome:** `footer.html` includes a `{% trans "Contact us" %}` link that uses the
  `telegram_deep_link` tag with the `contact_us` payload (no `ad_id`). The link opens
  `https://t.me/<bot_username>?start=contact_us`. No conditional on consent — always visible.
- **Files:** `templates/components/footer.html`
- **Dependencies:** Task 2 (template tag), Q4=A (visible to all).

### Task 5 — Bot-side `contact_us` deep-link handler

- **Purpose:** Handle `/start contact_us` from the footer link, and provide a "Contact us" button
  for Telegram-bypass users who reach the bot directly.
- **Expected outcome:**
  - New pattern `CONTACT_US_PATTERN = re.compile(r"^contact_us$")` in `contact.py` (or a new
    `contact_us.py` handler).
  - `handle_contact_us_start()` is called early in `handle_login_deep_link` (`login.py:58`) before
    the ad-specific `contact_<ad_id>` delegation — or as a new branch.
  - Bot replies with a greeting + support instructions (Russian, matching existing message style).
  - Bot-side rate limiting via `check_contact_start_rate_limit(user_id)` (Task 6).
  - Telegram's native `User.is_bot` check rejects bot accounts.
  - A "Contact us" button (inline keyboard) in the bot's main menu or `/start` response for
    Telegram-bypass users.
- **Files:**
  - `src/telegram_bot/handlers/contact.py` — add `contact_us` pattern + handler
  - `src/telegram_bot/handlers/login.py:55-59` — extend delegation
- **Dependencies:** Task 6 (bot-side rate limiting function).

### Task 6 — Bot-side rate limiting for `contact_us` starts

- **Purpose:** Prevent mass-triggering of `contact_us` deep-links from a single Telegram account.
- **Expected outcome:** New `check_contact_start_rate_limit(user_id, limit=5, period=600)` function
  in `telegram_bot/services/rate_limit.py`, mirroring the existing `check_upload_rate_limit` pattern
  (`cache.add` + `cache.incr` with `bot_contact_rl:{user_id}` key). Returns `bool`. Called at the
  start of the `contact_us` handler.
- **Files:** `src/telegram_bot/services/rate_limit.py`
- **Dependencies:** None (self-contained function).

### Task 7 — Web-side per-IP rate limiting for deep-link page renders

- **Purpose:** Cap how many contact-link-bearing page renders a single IP can trigger per time window.
- **Expected outcome:** A new rate-limit check (or extended existing check) using the
  `cache.add` + `cache.incr` pattern from `apps/search/services/rate_limit.py:26-32`, keyed by
  `telegram_dl_rl:{ip}`, limit 60 renders per 10 minutes. Applied to pages that render contact links
  (detail, privacy, listings, login_issue).
- **Files:** New `apps/core/services/contact_rate_limit.py` or extension of existing rate limit
- **Dependencies:** None.

### Task 8 — JS-execution-proof cookie + middleware

- **Purpose:** Server-side filter for scrapers that don't execute JS (defense-in-depth, research §3.2).
- **Expected outcome:** Inline script sets `js=true` cookie on every page with contact links; a
  middleware or context processor reads `request.COOKIES.get("js")` and passes `js_verified` to the
  template tag. If absent, the tag renders `<a href="#">` without the `data-*` attribute (click
  does nothing).
- **Files:**
  - New `apps/core/middleware/js_check.py` or extension of existing middleware
  - `apps/core/context_processors.py` or the template tag reads the flag
- **Dependencies:** Task 2 (template tag must accept the flag).

### Task 9 — Update existing tests for SiteConfig bot_username

- **Purpose:** Existing tests assert `context["bot_username"] == settings.BOT_USERNAME` or
  `href="https://t.me/{settings.BOT_USERNAME}..."`. These must be updated to use the new
  `SiteConfig`-backed value, per project rule #2 ("Production code is king — fix tests, not
  production code").
- **Expected outcome:** Tests use `get_bot_username()` or `SiteConfig.get_singleton().bot_username`
  instead of `settings.BOT_USERNAME`. Tests that assert `href="https://t.me/..."` cleartext must
  be updated to assert the obfuscated `data-*` attribute + click-to-reveal pattern.
- **Files:**
  - `apps/ads/tests/test_detail_context.py:106-111` — `test_detail_context_contains_bot_username`
  - `apps/ads/tests/test_detail_render.py:67` — `test_telegram_contact_deep_link_href`
  - `apps/search/tests/test_autocomplete_template.py:128-136` — `test_bot_username_comes_from_context`,
    `test_no_settings_dot_access_in_template`
  - `apps/users/tests/test_login.py` (if it asserts deep-link href format)
- **Dependencies:** Tasks 1, 2, 3.

### Task 10 — Add test coverage for new functionality

- **Purpose:** Verify obfuscation, footer link, `contact_us` handler, and rate limiting.
- **Expected outcome:**
  - **Template-level tests (no DB):** Assert `footer.html` includes a `{% trans "Contact us" %}` link
    and a `js-telegram-link` class / `data-bot-encoded` attribute; assert `bot_username` is no
    longer a bare `{{ bot_username }}` cleartext context variable in `detail.html`,
    `header_catalog.html`, `privacy.html`, `login_issue.html`.
  - **View-level tests (DB):** Assert `contact_us` handler returns a greeting; assert rate limiting
    returns cooldown message after 5 triggers.
  - **Admin tests:** Assert `SiteConfig` admin shows the `bot_username` field with `RegexValidator`.
  - **Migration test:** Assert the seed migration populates `bot_username` from `settings.BOT_USERNAME`.
- **Files:** New/modified test files under each app's `tests/` directory.
- **Dependencies:** Tasks 1–9.

---

## 4. Product Owner Decisions

| Decision | Chosen | Rationale |
|---|---|---|
| **Q1: Footer "Contact us" deep-link payload** | **A** — Use `?start=contact_us` (no `ad_id`), and the bot must have a separate "Contact us" button for Telegram-bypass users (same `contact_us` handler) | `contact_<ad_id>` pattern is ad-specific (existing). For site-wide contact, a new `contact_us` payload with no ad context is needed. Telegram-bypass users who find the bot directly (`t.me/bazuna_bot` without `?start=`) also need a button in-chat. |
| **Q2: Which `bot_username` references to obfuscate** | **A** — ALL 7 template locations (footer new, detail L167, header_catalog L33, privacy L30/L33/L111/L148, login_issue L21/L40) | Any cleartext `href="https://t.me/{{ bot_username }}"` is trivially scrapable. Partial obfuscation leaves an attack surface. |
| **Q3: Human verification approach** | **A** — Click-to-reveal as the human gate (no CAPTCHA widget) | Matches Avito/OLX "Show phone" pattern. The click itself proves JS execution. Zero friction for real users. Layered with rate limiting. |
| **Q4: Footer link visibility by consent state** | **A** — Visible to ALL visitors (including DECLINE / no consent) | The footer is part of the site shell, not personalization or analytics. Contact functionality is a core service feature (decision K: DECLINE = browse-only, no erasure; contact still works). |
| **Q5: Where to store the bot username** | **A** — Extend the `SiteConfig` singleton model (new `bot_username` field) | Matches the existing site-name pattern: admin-editable, cache-backed (1h TTL), `post_save` invalidation, shared between web + bot processes via `get_bot_username_async()`. Avoids a separate config table. |
| **Q6: Bot username storage format** | **A** — Store **without** `@`, validate with `RegexValidator` (alphanumeric + underscore, 3–32 chars), admin `help_text="Telegram bot username without @ prefix"` | Telegram usernames are `^[A-Za-z0-9_]{3,32}$` per `core.telegram.org/api/entities`. Storing without `@` matches the existing convention (`settings.BOT_USERNAME` is already without `@`); templates prepend `@` for display. The `RegexValidator` enforces valid Telegram usernames at the admin level. |
| **Q7: New user stories** | **A** — Create `US-B13` (buyer: footer contact-us link) and `US-S12` (seller: bot contact-us button for Telegram-bypass) | The contact-us footer link is primarily a buyer-facing surface; the bot-side button is a seller/buyer-facing surface in Telegram. Both need their own acceptance criteria. |
| **Q8: `<noscript>` fallback** | **C** — No `<noscript>` fallback; link simply does not work without JS | The project already requires JS for core functionality. A `<noscript>` fallback that exposes the username in cleartext would defeat the obfuscation. The PO explicitly chose no fallback (option C). |

---

## 5. Research Summary

### 5.1 Obfuscation technique matrix

| Technique | Scraper resistance | JS required? | Accessibility | Stack fit |
|---|---|---|---|---|
| CSS `direction: rtl` + `unicode-bidi: bidi-override` | Medium (defeats `textContent`/regex scrapers) | No | High (with `sr-only` pairing) | Excellent (one CSS class + one filter) |
| JS `data-*` attribute + click-to-reveal assembly | High (username never in static HTML `href`) | Yes (for hrefs) | Medium (needs `aria-label`) | Excellent (matches existing IIFE pattern) |
| HTML entity encoding | Low (DOM parsers decode automatically) | No | High | Trivial but weak |
| CSS `content` property injection | Low (read from stylesheet) | No (display only) | Poor | Not recommended |
| SVG path text rendering | High (no text nodes) | Yes (for linking) | Poor | Overkill |

**Decision:** Implement **hybrid #1** — CSS `direction: rtl` for visible display text + JS `data-*`
click-to-reveal for actionable hrefs.

### 5.2 Human verification approach matrix

| Approach | Friction | Third-party | GDPR | Scraper resistance |
|---|---|---|---|---|
| Click-to-reveal (click IS the gate) + rate limiting | Zero | No | Neutral | High (defeats non-JS); rate-limited for JS-capable |
| JS-execution cookie + server-side check | Zero (invisible) | No | Neutral (one local cookie) | High (defeats `requests`/`urllib`) |
| Cloudflare Turnstile (invisible) | Near-zero | Yes (Cloudflare) | Overhead | High |
| `navigator.webdriver` check | Zero | No | Neutral | Low (easily spoofed) |
| Honeypot fields | Zero | No | Neutral | N/A (no server-side form) |

**Decision:** Implement **click-to-reveal + JS-execution cookie + rate limiting** as layered defense.
Skip Turnstile (adds GDPR/CSP/compliance overhead for a client-side deep-link with no server-side
form to protect). Skip honeypot (no POST form to intercept — the bot deep-link is a client-side
`t.me://` URL). Skip `navigator.webdriver` (easily spoofed by modern scrapers).

### 5.3 Telegram deep-link payload constraints (verified)

| Constraint | Value | Source |
|---|---|---|
| Max length | 64 characters | `core.telegram.org/api/links` |
| Alphabet | `A-Z a-z 0-9 _ -` only (base64url) | `core.telegram.org/api/links` |
| Case sensitivity | Yes | `core.telegram.org/api/links` |
| Idempotency | Must handle — Telegram Desktop may drop payload on repeat opens | `core.telegram.org/api/links` |

The `contact_<ad_id>` pattern (existing) fits. The new `contact_us` pattern also fits (9 chars,
well under 64).

### 5.4 CSP compatibility (verified)

The existing `Content-Security-Policy-Report-Only` allows `script-src 'self' 'unsafe-inline'
https://unpkg.com https://*.plausible.io`. All recommended JS approaches use inline `<script>`
blocks (IIFE pattern) — **no new `script-src` origins needed**. No CSP changes required.

### 5.5 Existing rate-limiting pattern (verified)

The project already has a consistent per-IP / per-user rate-limiting idiom using Django's cache
framework in three locations:

| Location | Key pattern | Limit |
|---|---|---|
| `apps/search/services/rate_limit.py:26` | `autocomplete_rl:{ip}` | 30 req / 60s |
| `apps/users/services/login_rate_limit.py:28` | `login_rl:{ip}` | 10 req / 60s |
| `src/telegram_bot/services/rate_limit.py:26` | `bot_upload_rl:{user_id}` | 10 uploads / 60s |

All use the same `cache.add` + `cache.incr` pattern. The new web-side deep-link limiter and
bot-side `contact_us` limiter mirror this exactly.

### 5.6 Architecture precedent (verified)

The `SiteConfig` singleton already centralizes the site name with: model (`models.py:10-37`),
sync service (`get_site_name`, `services/site_config.py:16`), async service
(`get_site_name_async`, `services/site_config.py:40`), cache keys
(`utils/cache.py:56-57`, TTL 3600s), `post_save` invalidation (`signals.py:18-25`), admin
(`admin.py:11-28`), seed migration (`migrations/0002_seed_default.py:7-8`), context processor
(`context_processors.py:110-114`). The `bot_username` field follows this exact pattern.

---

## 6. Assumptions

| # | Assumption | Justification |
|---|---|---|
| A1 | The `contact_us` deep-link opens a bot chat with a greeting, not a per-ad forwarding flow | The footer link is site-wide contact (no `ad_id` in the payload). The PO confirmed Q1=A: use `contact_us` payload with no ad_id. The bot responds with support instructions. |
| A2 | The `<code>t.me/{{ bot_username }}</code>` block in privacy policy (L111) is also obfuscated with CSS `direction: rtl` | Q2=A explicitly says "ALL bot_username references." The research §6.4 considered leaving it cleartext for legal clarity, but the PO decision takes precedence. CSS `direction: rtl` protects it while still being visually readable. |
| A3 | The `login_issue.html` deep-link (L21) — which currently uses `{{ deep_link }}` (a pre-built URL string) — is migrated to the `telegram_deep_link` tag or its obfuscation equivalent | The research §1.2 lists it as the 7th cleartext location. Q2=A covers it. The `deep_link` context variable from `consent.py:307` must be replaced by the obfuscated tag output. |
| A4 | The `header_catalog.html` "Submit an ad" CTA (L33) keeps its `data-place-ad` attribute and `target="_blank"` behavior | The obfuscation changes only the `href` mechanism (cleartext → `data-*` + JS), not the link's existing attributes or behavior. |
| A5 | The `data-place-ad` attribute on the "Submit an ad" link is preserved as a selector hook for the JS click handler | Existing inline JS in `header_catalog.html` likely references this attribute. The new handler targets `.js-telegram-link` or `[data-bot-encoded]` class selector. |
| A6 | Existing `cache` backend (Redis in prod, LocMemCache in dev/test) supports `cache.add`/`cache.incr` | All three existing rate-limiters use this pattern; verified working in `search/services/rate_limit.py:26`. |
| A7 | The bot process shares the same `SiteConfig` cache as the web process (Redis) | Per `docs/99-agent/architecture.md:44-53`: web + bot share `django-redis`. `get_bot_username_async()` uses `sync_to_async(get_bot_username)` just as `get_site_name_async()` does. |

---

## 7. Constraints

1. **`SiteConfig` is a singleton (pk=1):** No new singleton pattern — the `bot_username` field is
   added to the existing model. `get_singleton()` already uses `get_or_create(pk=1)`.

2. **Migrations run once before both processes start (advisory-locked):** Adding the `bot_username`
   field requires a migration (`0003_add_bot_username`). The seed value comes from
   `settings.BOT_USERNAME` at migration time, then the admin can edit it at runtime. This is safe
   because migrations run exactly once before web + bot start.

3. **CSP is Report-Only (not enforced):** Inline `<script>` blocks with `'unsafe-inline'` are
   already allowed. No CSP changes needed for the JS click-to-reveal handler.

4. **`privacy.html` is a legal document (GDPR Article 13):** The `t.me/<bot_username>` reference in
   the `<code>` block (L111) is a legal disclosure. CSS `direction: rtl` protects it from scrapers
   while keeping it visually readable to humans. The deep-link `href`s on the same page (L30, L148)
   use JS click-to-reveal (acceptable — the link target is discoverable only via JS execution).

5. **Templates use Django autoescape ON:** The base64-encoded username in `data-*` attributes is
   safe (base64 charset is URL-safe and HTML-safe). No `|safe` filter needed on the encoded value.

6. **Two-process architecture (web + bot):** The web process renders templates; the bot process
   handles deep-links. Both share the `SiteConfig` cache (Redis in prod). The bot uses
   `get_bot_username_async()` for any bot-side URL construction (e.g., if the bot needs to send a
   deep-link to the user).

7. **i18n completeness gate:** All visible text in new template output must be wrapped in
   `{% trans %}` / `{% blocktrans %}`. The `aria-label` attributes on obfuscated links must use
   `{% trans %}` for translated labels. DB-based i18n (`feature_tag.html` via `get_lookup_name`)
   is exempt. `test_i18n_completeness.py` must pass.

8. **AGENTS.md rules:** Use `StrEnum` for fixed values; Pydantic v2 for DTOs; English-only
   comments/docstrings; no `print()`; strict separation of concerns.

9. **Bot FSM persistence:** The ad creation dialog is persisted as an `Ad` row (`DRAFT`) via the
   ORM. The `contact_us` flow is simpler (no FSM needed — just a greeting + instructions), but if
   it evolves into a multi-step support dialog, it should follow the same `Ad`-row persistence
   pattern rather than a bot-framework FSM.

10. **Django 5.2 LTS, aiogram 3.x, HTMX 2.0.10:** The template tag uses Django's `@register.simple_tag`;
    the bot handler uses aiogram's `Router`/`Command` filters (matching `login.py:32`).

---

## 8. Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **CSS `direction: rtl` defeats only static scrapers** — a scraper using Puppeteer/Playwright (renders CSS) sees the correct username in visible text | Medium — the display text is exposed to JS-capable scrapers | The visible display text is only on the privacy page (low-value target). The high-value `href` locations are protected by JS click-to-reveal (no URL in static HTML). Rate limiting covers JS-capable scrapers. |
| R2 | **JS `data-*` click-to-reveal fails if inline `<script>` doesn't load** (e.g., CSP blocking in Phase 2 enforcing mode) | High — contact links become non-functional | CSP is currently Report-Only with `'unsafe-inline'` allowed. If Phase 2 CSP drops `'unsafe-inline'`, inline scripts must be refactored to external files with nonces/hashes. Defer to future CSP hardening. |
| R3 | **`test_detail_template_uses_bot_username_not_settings` (test_detail_context.py:133) asserts `{{ bot_username }}` is in `detail.html`** — after migrating to the template tag, this assertion may break | Medium — test regression | Update the test (Task 9) to assert the new `telegram_deep_link` tag is used instead of the bare `{{ bot_username }}` context variable. Per project rule #2, fix tests, not production code. |
| R4 | **`test_bot_username_comes_from_context` (test_autocomplete_template.py:133) asserts `{{ bot_username }}` is in `header_catalog.html`** — same issue | Medium — test regression | Update test to assert `data-bot-encoded` or `js-telegram-link` class. |
| R5 | **The `deep_link` context variable in `login_issue.html`** is a pre-built URL string from `consent.py:307` — migrating to the obfuscated tag requires restructuring the view | Medium — view + template change | `consent.py:login_issue()` stops building `deep_link` pre-assembled; instead passes `raw_token` to the template and lets the tag assemble the obfuscated link. The `login_issue.html` JS (`L40`: `querySelector('a[href^="https://t.me"]')`) must be updated to find the element by class/attribute instead. |
| R6 | **Base64 in `data-*` attributes may be recognizable as an encoding scheme** — a determined scraper that knows base64 is used can decode it | Low — base64 is a well-known but deliberate extra step | Combine with the JS-execution cookie (§3.2) and rate limiting. A scraper must both decode base64 AND simulate clicks (or bypass the cookie check). The bar is significantly raised. |
| R7 | **Bot-side `is_bot` check may not be enforced yet** — the bot handler needs the check added | Medium — bot accounts could trigger the contact flow | Add `if message.from_user.is_bot: return` at the top of `handle_contact_start` (research §5.3, §6.4). Telegram's `User.is_bot` field is reliable. |
| R8 | **Footer link visible to all (Q4=A) means DECLINE-consent visitors can use it** — this is intentional but may conflict with strict ePrivacy interpretation | Low — the link opens `t.me://` (external), not a tracking pixel | The deep-link navigates to a third-party (Telegram), which is a user-initiated action, not a non-essential cookie. Consistent with decision K (DECLINE = browse-only, no erasure; contact still works). |
| R9 | **No `<noscript>` fallback (Q8=C) — no-JS users cannot contact the site** | Low — the project already requires JS for core features | Acceptable trade-off per PO decision. Document in privacy/consent: "JavaScript is required for contact functionality." |

---

## 9. Open Questions

| # | Question | Status |
|---|---|---|
| OQ1 | Should the bot `is_bot` check reject **before or after** the contact_us rate limit? | Open — placing the `is_bot` check before the rate limit means bot accounts never consume rate-limit budget. Placing it after means all requests are rate-limited regardless. Recommendation: check `is_bot` first (fail fast, save cache operations). |
| OQ2 | Should the JS-execution cookie be set on every page or only on pages with contact links? | Open — setting it on every page is simpler (one shared inline script in `footer.html` or base template) but adds a sub-KB to all pages. Setting it only on contact-bearing pages is more targeted. Default: set on footer render (all pages that include the footer, which is most pages). |
| OQ3 | Should the `contact_us` bot flow eventually become a multi-step support dialog (FSM)? | Open — for now it's a static greeting + instructions. If support volume grows, a queue-based dialog (new `Ad`-row or dedicated `SupportTicket` model) may be needed. Out of scope for this spec. |
| OQ4 | Should the `login_issue.html` deep-link also use `click-to-reveal` (JS assembly) or is cleartext acceptable since it's a login token flow (already rate-limited)? | Open — `login_issue` is behind `login_rate_limit_check` (10 req/60s per IP) and uses a SHA-256-hashed token. The bot username in the deep-link is the exposure point. Q2=A says "ALL" locations, so it should be obfuscated. But the `login_issue.html` JS (`L40`) currently hides the link and polls — the deep-link is already partially protected by `display: none`. Requires refactoring the JS selector. |
| OQ5 | Should the `header_catalog.html` "Submit an ad" CTA (`create_ad` payload) be rate-limited differently from `contact_us`? | Open — `create_ad` initiates ad creation (seller onboarding); `contact_us` is general support. The PO may want different limits. Default: same rate limit applies (any deep-link page render counts). |

---

## 10. Out of Scope

1. **Per-ad "Contact Seller" button redesign** — the `contact_<ad_id>` deep-link on `detail.html:167`
   is obfuscated (Q2=A), but its bot-side flow is unchanged. The per-ad contact handler logic in
   `contact.py:23-152` is not modified.
2. **Backend contact form** — OLX's inline contact form pattern (research §4.2) is not implemented.
   The bot deep-link is the sole contact method.
3. **Cloudflare Turnstile / any third-party CAPTCHA** — rejected per research §3.4 and Q3=A.
4. **`<noscript>` fallback** — explicitly rejected (Q8=C).
5. **Bot-side support ticket model** — the `contact_us` handler responds with a static greeting.
   A persistent `SupportTicket` model (if needed for two-way support) is deferred.
6. **Bot main menu keyboard overhaul** — the "Contact us" button (CR-5) is added to the existing
   bot menu/keyboard structure, but the menu's overall design is unchanged.
7. **Migration of `BOT_USERNAME` env var removal** — the env var stays as the migration seed value.
   Removing it from `.env.example` files is cosmetic and out of scope (the variable is still read
   at migration time to seed the initial `SiteConfig.bot_username` value).

---

## 11. Definition of Ready

A task is "ready" (implementation-planable) when all of the following are true:

1. **[x]** PO has confirmed decisions Q1–Q8 (all confirmed: Q1=A, Q2=A, Q3=A, Q4=A, Q5=A, Q6=A,
   Q7=A, Q8=C).
2. **[x]** Researcher's anti-spam report is reviewed and accepted (`04_telegram-contact-antispam-research.md`).
3. **[x]** The `SiteConfig` singleton pattern is confirmed as the storage mechanism for `bot_username`
   (verified: model, service, cache, signal, admin, migration, context processor).
4. **[x]** The 7 template locations needing obfuscation are identified and confirmed by Q2=A:
   `footer.html` (new), `detail.html:167`, `header_catalog.html:33`, `privacy.html:30/33/111/148`,
   `login_issue.html:21/40`.
5. **[x]** The existing `cache.add` + `cache.incr` rate-limiting pattern is confirmed as the
   mechanism for both web-side (per-IP) and bot-side (per-user) rate limiting (verified in 3
   existing locations).
6. **[x]** The `contact_<ad_id>` deep-link pattern and `CONTACT_PATTERN` regex (contact.py:20) are
   confirmed as the model for the new `contact_us` pattern.
7. **[x]** The existing inline-JS IIFE pattern (`<script>(function(){...})();</script>`) in
   `header_catalog.html:218` and `login_issue.html:36` is confirmed as the mechanism for the
   click-to-reveal handler.
8. **[x]** CSP compatibility verified — `'unsafe-inline'` allows inline scripts; no CSP change
   needed.
9. **[x]** Tests identified for update: `test_detail_context.py:106-140`, `test_detail_render.py:67`,
   `test_autocomplete_template.py:128-136`, `test_login.py:40-85`.
10. **[x]** i18n gate: all new visible template text wrapped in `{% trans %}`; `aria-label`
    attributes use `{% trans %}`; `test_i18n_completeness.py` must pass.

---

## 12. Key Files Reference

| File | Role | Relevant Lines |
|---|---|---|
| `apps/core/models.py` | `SiteConfig` singleton (add `bot_username` field here) | L10-37 |
| `apps/core/services/site_config.py` | `get_site_name()`/`get_site_name_async()` (mirror for `get_bot_username()`) | L16-42 |
| `apps/core/utils/cache.py` | `SITE_CONFIG_CACHE_KEY` / TTL / get/set/invalidate (reuse as-is) | L56-98 |
| `apps/core/signals.py` | `@receiver(post_save, sender=SiteConfig)` invalidation (already covers new field) | L18-26 |
| `apps/core/admin.py` | `SiteConfigAdmin` (add `bot_username` to `list_display`, add `RegexValidator`) | L11-28 |
| `apps/core/migrations/0002_seed_default.py` | Seed migration pattern (new `0003_add_bot_username` mirrors) | L6-17 |
| `apps/core/templatetags/telegram_tags.py` | **NEW** — `telegram_deep_link` template tag | (new file) |
| `apps/core/templatetags/contact_tags.py` | Existing template tag pattern (`@register.filter`) | L13-30 |
| `apps/core/templatetags/dict_tags.py` | `query_replace` template tag (existing pattern) | L47-81 |
| `apps/core/context_processors.py` | `header_context` exposes `bot_username` from `settings` (update to service) | L28-107 (L91) |
| `apps/core/views.py` | `privacy_policy()` passes `bot_username` from `settings` (L31) — update | L13-32 |
| `src/backend/templates/components/footer.html` | **NEW link** — add "Contact us" (visible to all) | L7-8 (insert after privacy) |
| `src/backend/templates/ads/detail.html` | Contact Seller button (obfuscate) | L167 |
| `src/backend/templates/components/header_catalog.html` | Submit an ad CTA (obfuscate) | L33 |
| `src/backend/templates/privacy.html` | 4 references: L30 (link), L33 (display), L111 (`<code>`), L148 (link) | L30,33,111,148 |
| `src/backend/templates/users/login_issue.html` | Login deep-link (obfuscate) + JS selector (L40) | L21, L40 |
| `src/backend/apps/core/views.py` | `privacy_policy()` passes `bot_username` (L31) | L31 |
| `src/backend/apps/ads/views/listings.py` | `ad_detail()` passes `bot_username` to context (L90) | L90 |
| `src/backend/apps/users/views/consent.py` | `login_issue()` builds `deep_link` from `settings.BOT_USERNAME` (L306-307) | L306-307 |
| `src/telegram_bot/handlers/contact.py` | `CONTACT_PATTERN` for `contact_<ad_id>` (L20) — model for `contact_us` pattern | L19-49 |
| `src/telegram_bot/handlers/login.py` | `/start` handler delegates to `handle_contact_start` (L56-59) | L32-59 |
| `src/telegram_bot/services/rate_limit.py` | `check_upload_rate_limit` (L26-52) — model for bot-side `contact_start` limiter | L26-61 |
| `src/backend/apps/search/services/rate_limit.py` | Per-IP `cache.add` + `cache.incr` pattern (L26-32) — model for web-side limiter | L26-77 |
| `config/settings/base.py` | `BOT_USERNAME = os.getenv("BOT_USERNAME", "")` (L234) — seed only after migration | L234 |
| `.env.example` | `BOT_USERNAME=<your-bot-username>` (L36) | L35-36 |
| `.env.dev.example` | `BOT_USERNAME=<your-bot-username>` (L32) | L31-32 |
| `.env.docker.example` | `BOT_USERNAME=bazuna_bot` (L25) | L24-25 |
| `docker/nginx/nginx.conf` | CSP Report-Only: `script-src 'self' 'unsafe-inline' ...` (L47) | L47 |
| `apps/ads/tests/test_detail_context.py` | Asserts `bot_username == settings.BOT_USERNAME` (L106-140) | L106-140 |
| `apps/ads/tests/test_detail_render.py` | Asserts `href="https://t.me/{settings.BOT_USERNAME}..."` (L67) | L48-68 |
| `apps/search/tests/test_autocomplete_template.py` | Asserts `{{ bot_username }}` in header_catalog (L128-136) | L128-136 |
| `apps/users/tests/test_login.py` | Login deep-link assertions (L40-85) | L38-85 |
| `docs/04-user-stories/buyer-stories.md` | Add `US-B13` (footer contact-us link) | (append after US-B12) |
| `docs/04-user-stories/seller-stories.md` | Add `US-S12` (bot contact-us button) | (append after US-S11) |
| `docs/04-user-stories/index.md` | Update story count table | L35-37 |

---

## 13. Related Documents

- **Input problem:** `.ai/problems/Problem_02.md` (RU)
- **Research report:** `.ai/research/04_telegram-contact-antispam-research.md`
- **Architecture:** `docs/99-agent/architecture.md` (§SiteConfig shared cache)
- **Technical specification:** `docs/01-spec/technical-specification.md` (consent states F/K, zones R1-R9, decision C)
- **Spec index:** `docs/01-spec/spec-index.md`
- **DB schema:** `docs/02-database/db-schema.md` (R2 conditions, login token flow)
- **Search journeys:** `docs/04-user-stories/search-journeys.md`
- **Existing similar spec (format reference):** `.ai/problems/17_url-state-preservation_spec.md`
- **SiteConfig pattern:** verified in `apps/core/models.py`, `apps/core/services/site_config.py`,
  `apps/core/utils/cache.py`, `apps/core/signals.py`, `apps/core/migrations/0002_seed_default.py`
- **Rate limiting pattern:** `apps/search/services/rate_limit.py`, `apps/users/services/login_rate_limit.py`,
  `src/telegram_bot/services/rate_limit.py`
- **Bot deep-link handling:** `src/telegram_bot/handlers/contact.py`, `src/telegram_bot/handlers/login.py`
