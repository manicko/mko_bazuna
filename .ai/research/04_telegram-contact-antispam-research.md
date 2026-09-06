# Research Report: Protecting Telegram Bot Usernames & Contact Deep-Links from Scraper Bots

**Project:** Mko Bazuna (Django 5.2 LTS + PostgreSQL 18 + aiogram 3.x + HTMX 2.0.10 MPA + gunicorn sync WSGI + nginx)  
**Date:** 2026-09-05  
**Scope:** Modern, lightweight practices for (a) obfuscating Telegram bot usernames and contact deep-link URLs in server-rendered Django templates, and (b) non-intrusive human verification for anonymous buyers on a classifieds site. No heavy third-party CAPTCHA widgets.  
**Confidence key:** HIGH = verified against project source code + official docs; MEDIUM = cross-referenced with web sources + project conventions; LOW = inferred/gap.  

---

## TL;DR

The bot username currently lives in `settings.BOT_USERNAME` (env var), is passed to every template via the `header_context` context processor, and appears in cleartext inside `href` attributes (`https://t.me/{{ bot_username }}?start=...`). Scrapers with a simple regex or DOM parse extract it trivially.

**Recommended obfuscation (top 2):**
1. **CSS `direction: rtl` text reversal** for the *visible display* of the username (e.g., `@bazuna_bot` shown in the privacy page footer) — zero JS, scraper-unfriendly in `textContent`, accessible with a paired `sr-only` element.
2. **JS `data-*` attribute + click-to-reveal** for the *clickable deep-link href* — the username is stored base64-encoded (or split into char-code fragments) in a `data-` attribute; a click handler assembles `t.me/<username>?start=...` at runtime. The static HTML `href` is `#` or absent — scrapers without JS execution never see the username.

**Recommended human verification (top 2):**
1. **Click-to-reveal itself is the human gate** — no CAPTCHA widget needed. The click event that assembles the URL proves a human interaction. Layer rate-limiting on top (per-IP web-side + per-Telegram-user-id bot-side) using the existing `cache.add` + `cache.incr` pattern.
2. **JS-execution proof via a session cookie** — a tiny inline script sets a cookie at page load; only requests carrying that cookie get a real deep-link URL from a lightweight HTMX endpoint. Scrapers using `requests`/`urllib` (no JS) are filtered without any friction for real users.

**Architectural recommendation:** Migrate `bot_username` from `settings.BOT_USERNAME` (env var) into the existing `SiteConfig` singleton model as a new `bot_username` field, following the exact pattern already established for the site name (`get_site_name()` / `get_site_name_async()` / cache + `post_save` invalidation). This centralizes the bot username as an admin-editable, cache-backed, cross-process value — consistent with project rule #10 (fixed values in models/enums) and the existing `SiteConfig` convention.

**CSP compatibility:** The existing `Content-Security-Policy-Report-Only` allows `script-src 'self' 'unsafe-inline' https://unpkg.com https://*.plausible.io`. All recommended JS approaches use inline scripts (no new `script-src` origins needed) and are fully compatible. No CSP changes required.

---

## 1. Current State in the Codebase

### 1.1 How `bot_username` is sourced and distributed (HIGH — verified source)

| Aspect | Detail | File |
|---|---|---|
| Source | `os.getenv("BOT_USERNAME", "")` → `settings.BOT_USERNAME` | `config/settings/base.py:234` |
| Context processor | `header_context()` returns `{"bot_username": settings.BOT_USERNAME}` | `apps/core/context_processors.py:91` |
| Registered as | `"apps.core.context_processors.header_context"` in `TEMPLATES[0].OPTIONS.context_processors` | `config/settings/base.py:154` |
| Template access | `{{ bot_username }}` — templates must NOT use `settings.BOT_USERNAME` directly | `context_processors.py:33-34` (docstring) |

### 1.2 Where `bot_username` appears in rendered HTML (HIGH — verified source)

| Template | Line | Usage |
|---|---|---|
| `ads/detail.html` | 167 | `<a href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}">` — Contact Seller button |
| `components/header_catalog.html` | 33 | `<a href="https://t.me/{{ bot_username }}?start=create_ad"` — Submit an ad CTA |
| `privacy.html` | 30 | `<a href="https://t.me/{{ bot_username }}">@{{ bot_username }}</a>` — Contact us link |
| `privacy.html` | 111 | `t.me/{{ bot_username }}` inside a `<code>` block in the privacy text |
| `privacy.html` | 148 | `<a href="https://t.me/{{ bot_username }}">@{{ bot_username }}</a>` — Contact us link |
| `users/views/consent.py` / `login_issue.html` | 307 / 21 | `deep_link = f"https://t.me/{bot_username}?start=login_{raw_token}"` → `<a href="{{ deep_link }}">` |

**Problem:** The username is embedded in cleartext inside `href` attributes. A scraper reading `response.html` or `soup.find('a')['href']` extracts it instantly. There is no obfuscation at all currently.

### 1.3 The `SiteConfig` singleton pattern (HIGH — verified source)

The site name follows a well-established pattern that `bot_username` should mirror:

| Layer | File | Mechanism |
|---|---|---|
| Model | `apps/core/models.py:10` | `SiteConfig(models.Model)` with `name = CharField(max_length=255, default="Bazuna")`, `get_singleton()` classmethod (`pk=1`) |
| Service (sync) | `apps/core/services/site_config.py:16` | `get_site_name()` — reads from cache (`get_cached_site_config()`), falls back to DB + cache set, falls back to `"Bazuna"` on error |
| Service (async) | `apps/core/services/site_config.py:40` | `get_site_name_async()` — `sync_to_async(get_site_name)`, used by the bot |
| Cache keys | `apps/core/utils/cache.py:56-57` | `SITE_CONFIG_CACHE_KEY = "site_config:v1"`, TTL = 3600s |
| Cache utils | `apps/core/utils/cache.py:60-98` | `get_cached_site_config()`, `set_cached_site_config()`, `invalidate_site_config()` |
| Invalidation | `apps/core/signals.py:18` | `@receiver(post_save, sender=SiteConfig)` → `invalidate_site_config()` |
| Admin | `apps/core/admin.py:11` | `SiteConfigAdmin(ModelAdmin)` with `has_add_permission=False`, `has_delete_permission=False` |
| Migration | `apps/core/migrations/0001_initial.py` + `0002_seed_default.py` | Creates the singleton row via `get_or_create(pk=1, defaults={"name": "Bazuna"})` |
| Context processor | `apps/core/context_processors.py:110` | `site_config()` → `{"site_name": get_site_name()}` |

This is the established pattern for any admin-editable config value shared between the web process and the bot process. The bot username should be added as a field on `SiteConfig`, served via `get_site_name()`-style functions, and invalidated via the same `post_save` signal.

### 1.4 Existing rate-limiting pattern (HIGH — verified source)

The project already has a consistent per-IP / per-user rate-limiting idiom using Django's cache framework, used in three places:

| Location | Key pattern | Limit | Purpose |
|---|---|---|---|
| `apps/search/services/rate_limit.py:26` | `autocomplete_rl:{ip}` | 30 req / 60s | Autocomplete API |
| `apps/users/services/login_rate_limit.py:28` | `login_rl:{ip}` | 10 req / 60s | Login token issuance (`/login/issue/`) |
| `src/telegram_bot/services/rate_limit.py:26` | `bot_upload_rl:{user_id}` | 10 uploads / 60s | Bot photo upload per seller |

**Common implementation pattern (all three):**
```python
key = _RATE_LIMIT_KEY_PATTERN.format(ip=ip)  # or user_id
added = cache.add(key, 1, timeout=RATE_LIMIT_PERIOD)
if added:
    current = 1
else:
    current = cache.incr(key)
return current <= RATE_LIMIT_REQUESTS
```

This pattern is shared via Redis in production (web + bot share `django-redis`) and `LocMemCache` in dev/test. It is the foundation for any rate-limiting recommendation in this report.

### 1.5 CSP and template constraints (HIGH — verified source)

- **CSP:** `Content-Security-Policy-Report-Only` (Report-Only, NOT enforced) with `script-src 'self' 'unsafe-inline' https://unpkg.com https://*.plausible.io`. Inline `<script>` blocks are allowed. No new script origins needed for any recommended approach. ([`docker/nginx/nginx.conf:47`](file:///C:/py_dev/mko_bazuna/docker/nginx/nginx.conf))
- **Templates:** Django templates with autoescape ON. No React/Vue. HTMX 2.0.10 loaded per-template (only `list.html` currently). Inline JS uses IIFE `(function(){ 'use strict'; ... })()` pattern extensively (e.g., `header_catalog.html`, `consent_banner.html`, `login_issue.html`).
- **Custom template tags:** Established pattern via `@register.filter` and `@register.simple_tag` in `apps/core/templatetags/` (`contact_tags.py`, `dict_tags.py`, `localized_content.py`).

### 1.6 Bot deep-link architecture (HIGH — verified source)

- The bot's `/start` handler is `handle_login_deep_link` in `telegram_bot/handlers/login.py:32`.
- Deep-link payload patterns: `contact_<ad_id>` (contact), `login_<token>` (login), `unsub_<token>` (unsubscribe).
- The `contact_<ad_id>` pattern is parsed by `CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")` in `telegram_bot/handlers/contact.py:20`.
- The bot can access `message.from_user.is_bot` (Telegram Bot API `User` object) to reject bot-initiated contacts.

---

## 2. Obfuscation Techniques for Bot Usernames in Server-Rendered HTML

### 2.1 Technique matrix

| # | Technique | Scraper-resistance | Human readability | Accessibility (screen readers) | Django template maintainability | SEO / link impact | JS required? |
|---|---|---|---|---|---|---|---|
| 1 | CSS `direction: rtl` + `unicode-bidi: bidi-override` | Medium — defeats `textContent` and regex scrapers; trivially reversible by a CSS-aware parser | High — renders perfectly visually | High — with paired `sr-only` clean text; without it, screen readers read reversed text | High — single CSS class, no template changes | High — the `href` still needs the real username, so this only protects visible text, not the link target | No |
| 2 | JS char-code / split-string reconstruction (`atob`, `String.fromCharCode`, fragments) | High — username never appears as a literal string in HTML source | High — assembled at runtime in the browser | Medium — requires `aria-label` on the link since `href` is dynamically set | Medium — needs an inline `<script>` block + data attribute | Low for SEO — `href` is `javascript:void(0)` or `#` until JS runs; search engines won't index the real t.me link | Yes |
| 3 | HTML entity encoding (decimal `&#116;&#101;&#108;...` or hex `&#x74;&#101;&#108;...`) | Low — DOM parsers (BeautifulSoup, lxml) decode entities automatically; `response.html` sees the clean string | High — renders perfectly | High — entities are decoded by the browser for AT | Very high — `{{ bot_username|entity_encode }}` filter, one line | Low impact — the decoded `href` is what browsers and scrapers see | No |
| 4 | CSS `content` property injection (`::before { content: "..." }`) | Low — the username is in a CSS property value, trivially extracted by any scraper that reads stylesheets | Medium — visible text is correct | Poor — `::before`/`::after` content is invisible to screen readers by default (`aria-hidden`); no semantic text node | Low — CSS must be dynamically generated per username; not feasible for admin-editable values | Poor — cannot be used for `href` attributes; links break | No, but limited to display only |
| 5 | SVG path text rendering (vector outlines) | High against text scrapers — no text nodes at all | Low — text is distorted/encoded as paths, may be hard to read at small sizes | Poor — no text content for screen readers; needs `aria-label` or `<title>` | Low — requires generating SVG paths from the username; overkill for a simple handle | Poor — `<a>` wrapping SVG with no real `href` means no native linking; needs JS | Yes (for linking) |
| 6 | `data-*` attribute + JS DOM construction | High — username is encoded in a `data-*` attribute, `href` built at click time | High — correct URL at runtime | Medium — link needs `aria-label` for context | High — `<a data-bot="{{ encoded }}" href="#">` + small script; follows existing IIFE pattern in templates | Low for SEO — same as technique 2 | Yes |

### 2.2 Detailed analysis

#### Technique 1: CSS `direction: rtl` text reversal

**How it works:** The username is stored reversed in the HTML text node (e.g., `not_banuz` instead of `bazuna_bot`), and a CSS class flips it visually:

```css
.bot-username-rtl { direction: rtl; unicode-bidi: bidi-override; }
```

**Scraper resistance (Medium):** A scraper doing `soup.find(text=...)` or regex-matching `t.me/(\w+)` sees the reversed string. However, a scraper that renders CSS (Puppeteer, Playwright) sees the correct value. A determined scraper that knows the `direction: rtl` trick simply reverses the string back — but this requires knowing the technique is in use.

**Accessibility:** By itself, `direction: rtl` on reversed text is read backwards by screen readers. The obscrd approach (2026) solves this by placing the clean, correct text in a visually-hidden `sr-only` element and setting `aria-hidden="true"` on the obfuscated span. The screen reader reads the hidden element; the visual user sees the CSS-reversed text.

**Template fit:** Trivial in Django — a simple template filter `{{ bot_username|reverse_text }}` paired with a CSS class. Already used by the obscrd service for email/phone obfuscation.

**Limitation:** This only protects the *visible text* (e.g., `@bazuna_bot` displayed in the privacy page). It does **not** protect the `href` attribute — the `t.me/{{ bot_username }}` URL must contain the real username for the link to work without JS.

#### Technique 2: JS character-code / split-string reconstruction

**How it works:** The username is split into character codes or fragments (or base64-encoded) in a `data-*` attribute. An inline `<script>` reads it, decodes it, and constructs the full `href` URL at runtime:

```html
<a href="#" data-bot-encoded="YmF6dW5hX2JvdA==" class="js-telegram-link"
   data-start="contact_{{ ad.id }}" aria-label="Contact seller via Telegram">
    Contact Seller
</a>
<script>
(function(){
    var el = document.querySelector('a.js-telegram-link');
    var username = atob(el.dataset.botEncoded);
    el.href = 'https://t.me/' + username + '?start=' + el.dataset.start;
})();
</script>
```

**Scraper resistance (High):** The literal string `bazuna_bot` never appears in the HTML source. Scrapers that only fetch HTML (without executing JS) see `href="#"` or no `href` at all. The encoded value (`YmF6dW5hX2JvdA==`) is recognizable as base64 but requires a deliberate decode step.

**Template fit:** The existing codebase already uses this pattern extensively — `login_issue.html` has inline JS that hides the deep-link element (`deepLinkEl.style.display = "none"`) and polls via JS. The `header_catalog.html` template has a 400-line IIFE `(function(){ 'use strict'; ... })()` for autocomplete/dropdown behavior. CSP allows `'unsafe-inline'`.

**Accessibility:** The link needs a descriptive `aria-label` since the `href` is built at runtime. Screen readers handle this well.

**Limitation:** Without JS, the link does not work (`href="#"` goes nowhere). This is acceptable for this project since HTMX and inline JS are already required for core functionality (autocomplete, consent banner, city filter). However, a small fallback could be provided via `<noscript>`.

#### Technique 3: HTML entity encoding

**How it works:** Each character of the username is replaced with its numeric HTML entity: `bazuna_bot` → `&#98;&#97;&#122;&#117;&#110;&#97;&#95;&#98;&#111;&#116;`.

**Scraper resistance (Low):** Any DOM parser (BeautifulSoup, lxml, `jq`) automatically decodes HTML entities. `soup.find('a')['href']` returns the fully decoded URL. This technique only defeats the most naive scrapers that regex-match the raw HTML source without parsing it.

**Template fit:** A simple Django template filter `{{ bot_username|encode_entities }}`.

**Accessibility:** Perfect — the browser decodes entities before rendering, so AT sees clean text.

**Limitation:** Virtually useless against any scraper that parses HTML (which is all of them). Provides a false sense of security. Best used as a secondary layer, not primary.

#### Technique 4: CSS `content` property injection

**How it works:** The username is injected via `::after { content: "bazuna_bot" }`, so it appears in CSS not in HTML text nodes.

**Scraper resistance (Low-Medium):** Any scraper that reads `<style>` blocks or computed styles can extract the value. Also, CSS `content` is purely visual — it cannot be used for `href` attributes, so this only works for display text, not for making the link clickable.

**Accessibility:** Poor — `::before`/`::after` content with `content:` property is invisible to most screen readers. Must be paired with `aria-label` or a hidden text element.

**Template fit:** Requires generating CSS dynamically with the username embedded, which is messy for admin-editable values. Not recommended.

#### Technique 5: SVG path text rendering

**How it works:** Each character of the username is rendered as a vector path (outline), so no `<text>` node exists in the SVG.

**Scraper resistance (High against text extraction):** No text nodes to scrape. However, SVG path data can be reverse-engineered to reconstruct glyphs, and OCR on rendered output defeats it entirely.

**Accessibility:** Poor — needs `<title>` or `aria-label` for screen readers. The visual rendering at small sizes may be illegible.

**Template fit:** Requires pre-generating SVG path data for each username character, either at build time (static usernames) or via a library at runtime (dynamic). For a classifieds site where the bot username rarely changes, this could be pre-generated. But it's overkill for a simple `@handle` display.

**Limitation:** Does not help with `href` linking. Requires JS to make it clickable. Not recommended for this use case.

#### Technique 6: `data-*` attribute + JS DOM construction

**How it works:** Same as Technique 2 but uses a `data-*` attribute with an encoded username and JS at click time (not just page-load time):

```html
<a href="#" data-bot="YmF6dW5hX2JvdA==" data-start="contact_{{ ad.id }}"
   data-label="Contact Seller" class="js-reveal-link">Contact Seller</a>
<script>
document.addEventListener('click', function(e){
    var el = e.target.closest('a.js-reveal-link');
    if (!el) return;
    e.preventDefault();
    var username = atob(el.dataset.bot);
    window.open('https://t.me/' + username + '?start=' + el.dataset.start);
});
</script>
```

**Scraper resistance (High):** The username is in a `data-*` attribute (encoded), and the `href` is only constructed on click. A scraper that doesn't execute JS sees `href="#"`. Even a JS-executing scraper only sees the decoded URL when it simulates a click — which requires knowing the click handler exists.

**Template fit:** Follows the existing IIFE + `addEventListener` pattern in `header_catalog.html` and `consent_banner.html`. The `data-*` attributes are clean Django template output.

**Accessibility:** Needs `aria-label` and `role="button"` since the `<a>` is intercepted by JS.

**Limitation:** Requires JS. Best combined with a `<noscript>` fallback that links directly (accepting that no-JS users get less protection — but the project already requires JS for core features).

### 2.3 Ranked recommendations

#### **Recommended #1: CSS `direction: rtl` for visible text + JS `data-*` assembly for hrefs (hybrid)**

**Rationale:** This combines two complementary techniques:
- **Visible display text** (e.g., `@{{ bot_username }}` in the privacy page) uses CSS `direction: rtl` + `unicode-bidi: bidi-override` with the reversed string in the HTML and a paired `sr-only` element for screen-reader correctness. Zero JS, zero CSP impact, defends the rendered text against `textContent` scrapers.
- **Clickable deep-link hrefs** (Contact Seller, Submit an ad, Login via Telegram) use `data-*` attribute with base64-encoded username + JS click handler that assembles the `t.me://` URL at click time. The static HTML `href` is `#` or absent.

**Why this wins:**
1. The CSS technique is trivially maintainable in Django templates (one filter + one class).
2. The JS technique leverages the project's existing inline-JS pattern and CSP allows `'unsafe-inline'`.
3. Together, they protect both the visible text AND the link target.
4. A scraper must both (a) know the CSS reversal trick AND (b) execute JS + simulate clicks — a combination that most scrapers do not attempt.
5. The bot username being admin-editable (recommended migration to `SiteConfig`) means the obfuscation must be dynamic — CSS class + base64 encoding handle this naturally.

#### **Recommended #2: JS `data-*` + click-to-reveal only (href-only protection)**

**Rationale:** If the visual display of `@bazuna_bot` in the privacy page is acceptable in cleartext (it's the privacy policy — low-value target), then JS `data-*` + click-to-reveal is sufficient for the high-value targets: the Contact Seller button, the Submit an ad CTA, and the Login deep-link. The privacy page's footer links could remain cleartext since they are in a legal document where the username is already "expected" to be visible.

**Implementation:** Wrap the deep-link `<a>` in a small inline script that reads `data-bot-encoded` (base64) and sets `href` at click time. This is the Stack Overflow-recommended pattern (base64 + `atob`) and is widely used in classifieds for WhatsApp/phone protection.

#### **Recommended #3: HTML entity encoding (defense-in-depth layer)**

**Rationale:** Add HTML entity encoding as a thin additional layer on the `href` attribute specifically. Even though DOM parsers decode entities, this adds one more step for scrapers that regex-match the raw HTML response without parsing. Combined with the JS `data-*` approach, it means a `requests`-based scraper sees neither the cleartext username nor an actionable URL.

**Not recommended as primary:** Techniques 4 (CSS `content`) and 5 (SVG paths) are dismissed — technique 4 can't protect `href` values and is inaccessible, and technique 5 is over-engineered for a simple username display.

---

## 3. Lightweight Human Verification (Non-Intrusive, No CAPTCHA Widgets)

### 3.1 Approach: Click-to-reveal as the human gate

**How it works:** The Contact Seller / Submit an ad button has no real `href` until a human clicks it. The click handler fires JS that assembles the `t.me://` URL from an encoded `data-*` attribute. For scrapers, the absence of a clickable element that produces the URL means the bot username is never exposed. For humans, the experience is identical — one click to contact.

**Stack fit:** The project already uses click-driven JS patterns in every template (consent banner checkboxes, city dropdown, autocomplete). A click-to-reveal handler is consistent.

**Scraper resistance:**
- `requests` / `urllib` (no JS): never sees the URL. ✅ Blocked.
- `BeautifulSoup` (no JS): sees `href="#"` or `data-bot="YmF6dW5h..."`. Must base64-decode — most scrapers don't. ✅ Partially blocked.
- Puppeteer / Playwright (full JS): sees the URL after click. ❌ Not blocked — but rate limiting (§3.3) covers this.

**Accessibility:** The button must have a clear `aria-label` and `role="button"` (or be a real `<button>` + `window.location` on click). WCAG 2.2 AA.

**GDPR:** Zero third-party dependencies. Only vanilla JS in an inline script. No data is collected from the user. ✅ Fully compliant.

### 3.2 Approach: JS-execution proof via session cookie

**How it works:** A tiny inline script at the top of every page sets a cookie:

```html
<script>
    document.cookie = "js=true; SameSite=Lax; Secure; path=/";
</script>
```

A lightweight middleware or view decorator checks for this cookie. If the cookie is **absent** (no-JS scraper), the deep-link endpoint returns `href="#"` or a 403. If the cookie is **present** (real browser), the full `t.me://...` URL is rendered.

**Stack fit:**
- The cookie-setting script is a one-liner inline block — CSP allows `'unsafe-inline'`.
- The check can be done server-side via a custom middleware reading `request.COOKIES.get("js")`.
- The deep-link URL can be rendered via a Django template tag (`{% telegram_contact_link ad.id %}`) that checks the cookie and either emits the real URL or a `#` placeholder.

This is strictly more effective than the User-Agent filtering mentioned in the Stack Overflow answer — it tests for actual JS execution, not just a header string that scrapers can spoof.

**Scraper resistance:**
- `requests` / `urllib`: never executes JS, never sets the cookie → never gets the real URL. ✅ Blocked.
- Scrapers that set the cookie manually: possible but unusual; combined with rate limiting, this raises the bar significantly. ✅ Mostly blocked.
- Puppeteer / Playwright: cookie is set automatically → URL is rendered. ❌ Not blocked (rate-limited instead).

**GDPR:** Zero third-party. Only a local session cookie. Must be documented in the privacy policy (it's non-essential but non-tracking). ✅ Compatible.

**Limitation:** The cookie must be set before the page renders the deep-link — so the template needs to conditionally render based on the cookie. This can be done in the template via `{{ request.COOKIES.js }}` or in the context processor.

### 3.3 Approach: Rate limiting (defense-in-depth, already in codebase)

**Web side (per-IP):** Mirror the existing autocomplete rate-limit pattern (`cache.add` + `cache.incr` with per-IP key). Limit deep-link URL generation to, say, 60 requests per minute per IP. The `X-Forwarded-For` IP extraction in `_get_client_ip()` (`search/services/rate_limit.py:61-77`) already handles the nginx reverse-proxy setup.

**Bot side (per user_id):** Extend the existing `check_upload_rate_limit` (`telegram_bot/services/rate_limit.py:26`) to a new `check_contact_rate_limit(user_id, limit=5, period=600)` that limits how many `contact_<ad_id>` starts a single Telegram user can initiate per 10-minute window. A real buyer contacts a few sellers per session; a scraper bot that has been added to a group and is mass-triggering deep-links is rate-limited.

**Combined effect:** Even if a scraper uses a headless browser to bypass click-to-reveal and JS-execution proof, rate limiting caps the throughput. The `contact_<ad_id>` payload means each deep-link is ad-specific — rate-limiting per `(ip, ad_id)` or per `(tg_user_id, ad_id)` prevents mass harvesting of a single ad's seller.

### 3.4 Approach: Cloudflare Turnstile (invisible mode) — evaluated, NOT recommended

**How it works:** Cloudflare Turnstile's invisible mode runs a JS challenge in the browser and returns a token that the backend validates via `https://challenges.cloudflare.com/cdn-cgi/v0/sites/<sitekey>/turnstile/v0/api/js/verify`. No visible widget appears.

**Pros:**
- Free, widely deployed, battle-tested.
- Invisible mode is genuinely non-intrusive — most visitors see nothing.
- Reduces bot traffic significantly.

**Cons for this project:**
1. **Third-party script:** Requires `script-src https://challenges.cloudflare.com` and `frame-src https://challenges.cloudflare.com` in the CSP. The current CSP only allows `unpkg.com` and `*.plausible.io`. Would need CSP expansion. (Report-Only mode means this is low-risk to test, but it's a change.)
2. **GDPR / data residency:** Per the Friendly Captcha privacy analysis (2026-07-20) and Cloudflare's own Turnstile privacy policy, "various signals" are collected and data may transit US servers. The site is GDPR-subject (Montenegro — EU-aligned, consent system already built per ePrivacy Art. 5(3)). Using Turnstile requires disclosing this processing and documenting a lawful basis (legitimate interest for anti-bot). The project already documents data processing in `privacy.html` — adding a third-party JS challenge increases the compliance surface.
3. **Requires a Cloudflare account** and sitekey/secret — adds operational overhead (rotate keys, monitor expiration).
4. **Accessibility limitations:** Friendly Captcha's 2026 analysis notes Turnstile struggles with screen readers and alternative browsers, generating false positives on Android and VPN connections. The project already has WCAG 2.2 AA aspirations.
5. **Overkill for deep-link protection:** Turnstile protects *forms* that submit to a backend. The Telegram deep-link is a client-side `t.me://` URL — there is no form submission to intercept. Turnstile would need to gate a click handler that builds the URL, which is what click-to-reveal already does for free.

**Verdict:** Skip for this use case. Turnstile is better suited for form spam (contact forms, login forms) where server-side validation of a token is available. For client-side deep-link URL construction, click-to-reveal + rate limiting is lighter, has zero third-party dependencies, and is GDPR-neutral.

### 3.5 Approach: Honeypot fields — limited applicability here

Honeypot fields (`django-honeypot` PyPI package, 2025 release) work by injecting a hidden form field that only bots fill out. If the field has a value on POST, the submission is rejected.

**Why limited for Mko Bazuna:** The contact flow is a Telegram deep-link (`t.me://...`), not a server-side form submission. There is no POST to intercept — the buyer is navigated away from the site entirely into the Telegram app. Honeypots require a server-rendered form with a POST handler.

**Where honeypots WOULD apply:** If the project later introduces a contact form (as an alternative to the Telegram deep-link for buyers without Telegram), a honeypot field on that form would be an excellent zero-friction human gate. The `django-honeypot` package's middleware auto-injects into all POST forms — but the project's current pattern is per-view, so a manual honeypot hidden field in a contact form template would be more consistent with the codebase.

### 3.6 Approach: JS-challenge middleware (navigator.webdriver, execution proof)

**How it works:** An inline script runs at page load and performs a simple JS operation (e.g., setting a cookie, computing a timestamp hash, writing to `sessionStorage`). The server checks for the result. If absent, the visitor is likely a bot without JS execution.

**Stack fit:** Identical to approach §3.2 (session cookie) — the "JS-execution proof" IS a JS challenge. The `navigator.webdriver` check is a weaker variant: it only detects the most naive headless setups. Modern scrapers (Playwright with `--headed`, Camoufox, Patchright) spoof or remove the `webdriver` flag. The execution-proof cookie is strictly better because it tests whether *any* JS ran, not just whether a specific flag is spoofed.

**Recommendation:** Use the cookie approach (§3.2), not `navigator.webdriver` checks. The cookie proves JS execution; `navigator.webdriver === false` only proves a flag was patched (the browser might still be headless).

### 3.7 Telegram-native signals

The bot can and should perform these checks on the bot side (after the deep-link is followed), but they do NOT protect the web-side username exposure:

| Signal | Source | Action |
|---|---|---|
| `message.from_user.is_bot` | Telegram `User` object | Immediately reject / block — bots cannot be real buyers |
| `message.from_user.is_fake` | Telegram Bot API (premium feature) | Flag for review — Telegram detects fake accounts |
| `message.from_user.is_support` | Telegram Bot API | Distinguish support accounts |
| Telegram's own antispam | `telegram_antispam_user_id` | Enable native antispam in group chats |
| Per-user rate limit on `/start` | Bot-side (`cache.add` + `cache.incr`) | Cap `contact_<ad_id>` starts per `user_id` (e.g., 5/10min) |

**Bot-side rate limiting on deep-link starts** should mirror the existing `check_upload_rate_limit` pattern (`telegram_bot/services/rate_limit.py:26`) but keyed by `(user_id, deep_link_prefix)`:

```python
# New function mirroring the existing pattern
def check_contact_start_rate_limit(user_id: int, limit=5, period=600) -> bool:
    key = f"bot_contact_rl:{user_id}"
    ...
```

This complements web-side rate limiting: even if a scraper has a real Telegram account and triggers the deep-link, the bot limits how many contacts they can initiate per unit time.

---

## 4. Real-World Classifieds / Marketplace Examples

### 4.1 Avito (avito.ru) — "Show phone number" button

Avito hides the seller's phone number behind a **"Показать телефон" (Show phone)** button. The number is **not** in the initial HTML response — it is fetched via an AJAX/XHR request only after the button is clicked. The button itself is a real `<button>` element (not an `<a>` with an encoded `href`), and it fires a `fetch()` to an endpoint that returns the phone number as JSON, then renders it.

**Key protection layers:**
1. **Obfuscation:** Phone number is not in HTML source at all.
2. **Click-to-reveal:** Button click triggers XHR; the number is assembled server-side.
3. **Rate limiting:** Per-IP and per-session limits on the phone-reveal endpoint.
4. **Behavioral analysis:** Avito's anti-bot system detects "clicking Show phone on every ad" as anomalous behavior.

**What Mko Bazuna can adopt:** The deep-link URL assembly on click (§3.1) mirrors this exactly — the real URL is not in the HTML until the click fires JS. The bot username follows the same "not in source until interaction" model.

**Source:** Avito anti-bot analysis (proxycove.com, 2026-04-02), "Contact Information and Lead Generation" section describing the "Show Phone" click requirement.

### 4.2 OLX — "Show contact" with optional form

OLX uses a **"Show contact"** button that reveals the phone number via AJAX (same pattern as Avito). Some regional OLX instances (e.g., OLX Pakistan) offer an **inline contact form** as an alternative — the buyer fills a form, and OLX relays the message to the seller's email/Telegram. The phone number is never exposed to the buyer's browser.

**What's relevant:** The inline form approach means the contact method (Telegram) is abstracted behind a server-side relay — the bot username never appears on the public page at all. This is the "maximum protection" option but requires a server-side contact relay (which the Mko Bazuna bot already partially implements via `handle_contact_start` in `telegram_bot/handlers/contact.py`).

**Source:** OLX Pakistan "hide phone number" feature (2019-10-21 Facebook video), OLX help documentation.

### 4.3 Auto.ru — AJAX phone reveal + behavioral gating

Auto.ru (Russian auto classifieds) hides phone numbers behind a **"Показать телефон"** button that requires AJAX. Additionally, the button requires the user to have a Telegram account or be logged in — anonymous users must complete an additional step (send a code to Telegram) before the number is revealed. This couples the human gate to Telegram itself.

**What's relevant:** Mko Bazuna already requires Telegram for the full contact flow (the deep-link opens Telegram). The "human gate" is inherently the Telegram app — but the *bot username* must be exposed on the web page first. The click-to-reveal + rate-limiting pattern ensures only real browsers (with JS) can even discover the username.

### 4.4 General classifieds pattern

The industry standard for classifieds contact protection is:

1. **Don't put the contact identifier in the initial HTML** — fetch or assemble it only after a user action.
2. **Click-to-reveal is the gate** — the click itself proves human interaction.
3. **Rate-limit the reveal endpoint** — cap per-IP and per-session.
4. **Behavioral detection** — flag "click Show on every listing" patterns.

For Mko Bazuna's Telegram deep-link model, steps 1–3 translate directly:
- Step 1 → JS `data-*` attribute assembly (URL not in `href` until click).
- Step 2 → click-to-reveal handler.
- Step 3 → per-IP rate limit on the web + per-user rate limit on the bot's `/start` handler.
- Step 4 → bot-side `is_bot` check + Telegram's native antispam.

---

## 5. Telegram-Specific Considerations

### 5.1 Deep-link payload constraints (HIGH — verified via core.telegram.org/api/links)

| Constraint | Value |
|---|---|
| Max length | 64 characters |
| Alphabet | `A-Z a-z 0-9 _ -` only (base64url, no `+`/`/`/`=`/spaces) |
| Case sensitivity | Yes |
| Idempotency | Must handle — Telegram Desktop may drop the payload on repeat opens |

The project's payload patterns (`contact_<ad_id>`, `login_<token>`, `unsub_<token>`) all fit within these constraints. The `contact_<ad_id>` pattern is parsed by `CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")` (`telegram_bot/handlers/contact.py:20`).

### 5.2 The bot username in the `t.me://` URL is the attack surface

The deep-link URL format is:
```
https://t.me/<bot_username>?start=<payload>
```

The `<bot_username>` part is the value to protect. The `<payload>` part is ad-specific and changes per listing (`contact_12345`), so even if a scraper extracts one deep-link, it's only useful for that one ad. This means:

- **Protecting the username** (so the scraper can't construct arbitrary `contact_<ad_id>` deep-links) is the primary goal.
- **Rate-limiting the payload** is secondary — even if a scraper has the username, they need to enumerate `ad_id` values, which the bot can rate-limit per Telegram user.

### 5.3 Bot-side `/start` handler flow (HIGH — verified source)

1. Bot receives `/start contact_<ad_id>` → `handle_login_deep_link` (`telegram_bot/handlers/login.py:32`).
2. Delegates to `handle_contact_start(message, bot, deep_link)` (`telegram_bot/handlers/contact.py:23`).
3. `CONTACT_PATTERN.match(deep_link)` extracts `ad_id`.
4. `handle_contact_orm(ad_id)` checks seller availability via `get_seller_for_contact()` (which loads the ad with `select_related("user")` and checks Zone R2 conditions).
5. `record_contact_initiated(buyer_telegram_id)` records the analytics event.

**Rate-limiting insertion point:** Between steps 1 and 2, or at the start of `handle_contact_start`, add a `check_contact_start_rate_limit(user_id)` call using the existing `cache.add` + `cache.incr` pattern. If rate-limited, the bot replies with a cooldown message instead of forwarding the contact.

### 5.4 Telegram's native anti-spam capabilities

- **`User.is_bot`** — Telegram Bot API field. The bot can reject any `/start` from a bot account immediately. This protects against scraper bots that have their own Telegram bot accounts trying to trigger contact flows.
- **`User.is_fake`** — Telegram Bot API field (available to bots with appropriate permissions). Flags accounts Telegram has identified as fake.
- **Native antispam** — Telegram's own antispam system (`telegram_antispam_user_id`) can be enabled in group chats where the bot operates.
- **Account restrictions** — Telegram can limit accounts that exhibit spam-like behavior (mass `/start` deep-link triggering, rapid messaging). The bot doesn't control this, but it's a backstop.
- **Bot-level spam** — Telegram can detect and limit the *site's* bot if it's used for spam relay. Protecting the username from scraping prevents the bot from being abused as an open relay.

**Source:** core.telegram.org/api/antispam, core.telegram.org/api/links, GramIO deep-link guide (2026-08-25).

---

## 6. Feasible Implementation Approaches

> **Note:** Per the task constraints, these are architectural descriptions — not code. They follow existing codebase patterns.

### 6.1 Architecture: Migrate `bot_username` to the `SiteConfig` singleton

**Current:** `bot_username` is `settings.BOT_USERNAME` (env var), cached nowhere, read on every request from `os.getenv`.

**Recommended:** Add `bot_username = models.CharField(max_length=255, default="bazuna_bot", help_text="Telegram bot username without @ prefix")` to `SiteConfig` (`apps/core/models.py`). Create `get_bot_username()` / `get_bot_username_async()` in `apps/core/services/site_config.py` following the exact `get_site_name()` / `get_site_name_async()` pattern (cache with 1h TTL via `SITE_CONFIG_CACHE_KEY`). The existing `post_save` signal on `SiteConfig` (`apps/core/signals.py:18`) already invalidates the cache — no new signal needed.

**Why this matters for obfuscation:** The context processor would pass `bot_username` (already obfuscated-ready as a string) to templates. A custom template tag `{% load telegram_tags %}` + `{% telegram_deep_link "contact" ad.id %}` could emit the obfuscated HTML. The admin-editable nature means the obfuscation layer must handle arbitrary usernames — CSS `direction: rtl` and base64 encoding both work for any input.

**Migration impact:** Adding a field to `SiteConfig` requires a migration (`apps/core/migrations/0003_add_bot_username`). The project runs migrations once before web + bot start (advisory-locked), so this is safe. The env var (`BOT_USERNAME`) becomes the seed value for the initial migration data. No runtime env var needed after migration.

**Existing tests that reference `settings.BOT_USERNAME`:** `test_detail_context.py:107` asserts `context["bot_username"] == settings.BOT_USERNAME`, and `test_detail_render.py:67` builds `expected_href = f"https://t.me/{settings.BOT_USERNAME}?start=contact_{ad.id}"`. These tests would need updating to use `SiteConfig.get_singleton().bot_username` instead. Per project rule #2 ("Production code is king"), the tests should be updated to match the new architecture, not the other way around.

### 6.2 Obfuscation approach: Custom template tag + inline JS

**Template tag:** Create `apps/core/templatetags/telegram_tags.py` with a `@register.simple_tag` or `@register.inclusion_tag` called `telegram_deep_link(payload, ...)` that:
- Reads the bot username from the new `get_bot_username()` service.
- Renders: `<a href="#" data-bot-encoded="<base64>" data-start="<payload>" class="js-telegram-link" aria-label="<translated label>">{% trans "Contact Seller" %}</a>`
- Includes an inline `<script>` IIFE (following the `header_catalog.html` pattern) that:
  1. Attaches a `click` handler to `[data-bot-encoded]`.
  2. On click: `e.preventDefault()`, reads `btoa`/`atob` from the `data-bot-encoded` attribute, constructs `https://t.me/${username}?start=${start}`, and calls `window.open(url)` or sets `window.location.href`.
  3. Also sets the `js=true` session cookie for the JS-execution-proof middleware (§3.2).

**CSS `direction: rtl` for display:** Create a template filter `{{ bot_username|rtl_obfuscate }}` that reverses the string and wraps it in `<span class="bot-username-rtl sr-only" aria-hidden="true">{{ reversed }}</span><span class="sr-only">{{ original }}</span>`. The CSS class is in the compiled Tailwind output (add to `input.css` as a custom rule, or use inline `style`). The `sr-only` class is already a Tailwind utility (`sr-only` is built into Tailwind).

**Why a template tag instead of context processor output:** The existing pattern uses template tags for view-specific logic (`contact_tags.can_contact` filter for Zone R2 conditions, `dict_tags.query_replace` for URL building). A `telegram_deep_link` tag encapsulates the obfuscation logic (encoding + JS assembly) at the point of use, keeping the context processor clean and the templates DRY.

### 6.3 Human verification: layered without Friction

**Layer 1 — Click-to-reveal (zero friction):** The `<a>` has no real `href` until clicked. A human click fires JS → URL assembled → browser navigates to Telegram. No modal, no puzzle, no delay. The click IS the verification.

**Layer 2 — JS-execution cookie (invisible):** The inline script in §6.2 also sets `document.cookie = "js=true; SameSite=Lax; Secure; path=/"`. A custom middleware (`apps/core/middleware/js_check.py` or added to the existing `CityResolutionMiddleware` pattern in `apps/core/middleware/`) checks `request.COOKIES.get("js")`. If absent, a context variable `js_verified` is set to `False`, and the `telegram_deep_link` template tag emits `href="#"` even if clicked (with a `noscript` fallback showing a plain text label). This filters out `requests`-based scrapers that never run JS.

**Layer 3 — Rate limiting (using existing pattern):** 
- **Web side:** Add a `telegram_dl_rl:{ip}` key using the same `cache.add` + `cache.incr` idiom from `search/services/rate_limit.py`. Limit to 60 deep-link page renders per IP per 10 minutes (pages can have 2–3 deep-links each, so 60 renders ≈ 20–30 actual clicks).
- **Bot side:** Add `check_contact_start_rate_limit(user_id, limit=5, period=600)` to `telegram_bot/services/rate_limit.py`, mirroring `check_upload_rate_limit`. Reject excess `/start contact_<ad_id>` with a cooldown message.

**Layer 4 — Telegram-native (bot side only):** `handle_login_deep_link` (`telegram_bot/handlers/login.py:58`) already checks `message.from_user.is_bot`:

```python
# Verify from the existing contact handler flow
if message.from_user and message.from_user.is_bot:
    await message.answer("Bots cannot use this feature.")
    return
```

### 6.4 Privacy page consideration (privacy.html)

The privacy page (`privacy.html`) has three references to `bot_username`:
1. **Line 30–33:** `@{{ bot_username }}` as a clickable "contact us" link in section "1. Controller".
2. **Line 111:** `t.me/{{ bot_username }}` inside a `<code>` block in the "Third-Party Disclosures" section.
3. **Line 148–151:** `@{{ bot_username }}` as a clickable "contact us" link in section "7. Manage Your Consent".

For the **clickable links** (lines 30, 148): Apply the same JS click-to-reveal pattern. A human clicking "contact us on Telegram" gets the URL assembled client-side.

For the **inline `<code>` reference** (line 111): This is in a legal/privacy document context where transparency is required. The username here can remain cleartext — GDPR Article 13 requires disclosure of the data controller's contact method, and the deep-link pattern is described in prose. Obfuscation in a legal document undermines the disclosure obligation. Apply CSS `direction: rtl` only if desired for consistency, but cleartext is acceptable and arguably required for legal clarity.

**i18n note:** The `telegram_deep_link` template tag must wrap user-visible text (`"Contact Seller"`, `"Submit an ad"`, etc.) in `{% trans %}` / `{% blocktrans %}` per project rule #16. The base64-encoded username is not user-visible (it's in a `data-*` attribute), so it doesn't need translation. The existing `catalog_js_labels` pattern (`context_processors.py:98-106`) demonstrates how to pass translated strings into inline JS — the label for the click handler can follow the same pattern.

### 6.5 Footer "Contact us" link (to be added)

The footer component (`components/footer.html`, 11 lines) currently has only Privacy Policy and Cookie settings links. The task mentions a "Contact us" link to be added. This new link should use the same obfuscation pattern — a `{% telegram_deep_link "contact_us" %}` tag that assembles `t.me://<bot_username>` (no `?start=` payload needed for the footer contact link, since it just opens a chat with the bot).

The existing inline JS in the footer area (or a shared script loaded once per page) would handle all `.js-telegram-link` elements, so adding a new obfuscated link requires only the template tag invocation, not new script code.

---

## 7. Known Limitations and Mitigations

### 7.1 Headless browsers execute JS (LIMITATION — unavoidable at application layer)

**What it defeats:** All JS-based obfuscation (Techniques 2, 6) and the JS-execution-proof cookie (§3.2). A scraper using Puppeteer/Playwright/Camoufox sees the fully assembled URL.

**Mitigation:** 
- **Rate limiting** (§3.3) is the primary defense — cap the number of deep-link discoveries per IP/user per time window. Even a headless browser is limited to N reveals.
- **Behavioral anomaly detection** — the bot-side `is_bot` check and Telegram's native antispam catch automated accounts.
- **Per-ad_id rate limiting on the bot** — even if the username is known, the bot can limit how many `contact_<ad_id>` starts a single Telegram user can trigger per hour.

**What it does NOT stop:** A determined attacker with a real Telegram user account and a headless browser can contact every seller. But the cost (real accounts, real browser sessions, real Telegram interactions) makes large-scale scraping economically unfeasible — which is the goal.

### 7.2 CSS `direction: rtl` is reversible by CSS-aware scrapers (LIMITATION)

**What it defeats:** `requests`-based `re.search(r't\.me/(\w+)')` regex scrapers.
**What it doesn't:** Scrapers that use `cssutils` or `stylis` to parse CSS and apply `direction: rtl` before reading text content.

**Mitigation:** Use CSS `direction: rtl` only for the **display text** (e.g., `@bazuna_bot` shown in the privacy page), NOT as the sole protection for the `href`. The `href` is protected by the JS `data-*` assembly. Layer both — the display text reversal adds friction for scrapers that parse CSS, and the JS assembly protects the actual link.

### 7.3 Screen reader accessibility (LIMITATION — mitigated)

**Risk:** CSS-reversed text (`direction: rtl` on reversed string) is read backwards by screen readers. JS-assembled `href`s have no accessible text until the script runs.

**Mitigation (already in the obscrd approach, 2026-03-11):**
- For CSS-reversed display text: pair the obfuscated span with a visually-hidden `sr-only` element containing the correct text: `<span class="sr-only">@bazuna_bot</span><span class="bot-username-rtl" aria-hidden="true">not_banuz@</span>`.
- For JS-assembled links: always include a static `aria-label` (e.g., `aria-label="Contact seller via Telegram"`) so the link purpose is clear even if the `href` is `javascript:void(0)`.

The project already uses `aria-label` and `aria-hidden` extensively in templates (e.g., `header_catalog.html` SVG icons all have `aria-label`, `consent_banner.html` uses semantic structure).

### 7.4 SEO impact (LIMITATION — acceptable trade-off)

**Risk:** Search engines that don't execute JS (Googlebot historically did not, though it now runs Puppeteer-level JS) would see `href="#"` links, reducing SEO value of the deep-link targets.

**Mitigation:**
- The deep-links point to `t.me://` (external to the site), so they carry minimal SEO value for the site's own search ranking.
- The `aria-label` text ("Contact Seller", "Submit an ad") provides semantic context for crawlers.
- Googlebot does render JS (since 2015+), so the links will be discovered on Google's index.
- If SEO of deep-link targets is critical, a `<noscript>` fallback with a `rel="nofollow"` direct link can be provided — accepting less protection for the no-JS case.

### 7.5 CSP is Report-Only (LIMITATION — monitoring required)

**Risk:** The CSP is `Content-Security-Policy-Report-Only` (nginx `nginx.conf:47`), meaning violations are *reported but not enforced*. If a stricter CSP is later flipped to enforcing (the deferred "Phase 2" per `architecture-structure.md:307`), the inline `<script>` blocks used for JS assembly must be allowed via `script-src 'unsafe-inline'` (already present) or migrated to nonces/hashes.

**Mitigation:** The recommended approaches use only `'unsafe-inline'` scripts (already in the CSP). No new `script-src` origins are needed. If Phase 2 enforcing CSP drops `'unsafe-inline'`, the inline scripts would need to be refactored to external files with nonces — but this is a future concern, not a blocker.

### 7.6 No-JS fallback degrades to non-functional links (LIMITATION — acceptable)

**Risk:** Users with JavaScript disabled see `href="#"` and clicking does nothing useful.

**Mitigation:** Provide a `<noscript>` block with a plain-text instruction:
```html
<noscript>
    <p>To contact this seller, open Telegram and search for @bazuna_bot,
       then send /start contact_{{ ad.id }}.</p>
</noscript>
```
This accepts that no-JS users get a degraded experience (manual step) in exchange for protecting the majority of visitors (95%+ of users have JS enabled, and the project already requires JS for HTMX/autocomplete). The `<noscript>` fallback gives instructions without exposing the username in an actionable `href`.

**Note:** The project already requires JS for core functionality — the consent banner, autocomplete search, city filter, and login polling all use inline JS. A no-JS experience is already degraded, so this is consistent with the existing UX contract.

---

## 8. Ranked Recommendations Summary

### Obfuscation (for the bot username in templates)

| Rank | Technique | Protection level | JS required? | Accessibility | Stack fit |
|---|---|---|---|---|---|
| **1** | CSS `direction: rtl` for display text + JS `data-*` click-to-reveal for href | High (defeats static HTML scraping + non-JS scrapers) | For hrefs: yes; for display: no | High (with `sr-only` pairing) | Excellent — matches existing inline JS + `aria-label` patterns |
| **2** | JS `data-*` click-to-reveal for hrefs only; display text in cleartext | Medium-High (defeats non-JS; display is exposed) | Yes for hrefs | Medium (needs `aria-label`) | Excellent — minimal template changes |
| **3** | HTML entity encoding in `href` | Low (DOM parsers decode automatically) | No | High | Trivial — one filter, but weak protection |

**Decision:** Implement **Rank 1** — the hybrid approach. Use CSS `direction: rtl` for the visible `@{{ bot_username }}` display text on the privacy page, and JS `data-*` click-to-reveal for all actionable deep-link buttons (Contact Seller, Submit an ad, Login, Footer Contact Us).

### Human verification (for anonymous visitors)

| Rank | Approach | Friction | Third-party? | GDPR | Stack fit |
|---|---|---|---|---|---|
| **1** | Click-to-reveal (click IS the gate) + rate limiting (web IP + bot user_id) | Zero (same as a normal click) | No | Neutral (no data collected) | Excellent — click handler + existing `cache.add`/`incr` pattern |
| **2** | JS-execution cookie + server-side check | Zero (cookie set invisibly) | No | Neutral (one local cookie) | Excellent — one-line inline script + middleware check |
| 3 | Cloudflare Turnstile invisible | Near-zero (runs in background) | Yes (Cloudflare) | Overhead (DPA, privacy disclosure, legitimate interest) | Moderate — needs CSP + Cloudflare account + backend validation |
| 4 | `navigator.webdriver` check | Zero (invisible) | No | Neutral | Low — easily spoofed by modern scrapers |

**Decision:** Implement **Rank 1 + Rank 2** as layered defense. Click-to-reveal handles the primary gate (non-JS scrapers never get the URL). JS-execution cookie adds a server-side filter for `requests`-based scrapers that somehow parse the `data-*` attributes. Rate limiting (using the existing pattern) caps throughput for JS-capable scrapers. Skip Turnstile — it adds GDPR/CSP/compliance overhead for marginal gain on a client-side deep-link use case where there's no server-side form to protect.

### Architectural prerequisite (before obfuscation)

1. **Migrate `bot_username` to `SiteConfig`** as a new `bot_username` field, served via `get_bot_username()` / `get_bot_username_async()` with 1h cache TTL and `post_save` invalidation — following the exact `SiteConfig` pattern verified in source.
2. **Create a `telegram_deep_link` template tag** in `apps/core/templatetags/telegram_tags.py` that encapsulates the obfuscated HTML + inline JS.
3. **Update existing tests** that assert `context["bot_username"] == settings.BOT_USERNAME` to use the new service instead (project rule #2: fix tests, not production code).
4. **Extend rate limiting** — add `check_contact_start_rate_limit()` to `telegram_bot/services/rate_limit.py` mirroring `check_upload_rate_limit()`, and a web-side per-IP limiter for deep-link page renders.

---

## 9. Sources

### Project source code (HIGH confidence — direct file reads)

- `config/settings/base.py:234` — `BOT_USERNAME = os.getenv("BOT_USERNAME", "")`
- `apps/core/context_processors.py:91` — `"bot_username": settings.BOT_USERNAME`
- `apps/core/models.py:10-37` — `SiteConfig` singleton model with `get_singleton()`
- `apps/core/services/site_config.py:16-42` — `get_site_name()` / `get_site_name_async()`
- `apps/core/utils/cache.py:56-98` — `SITE_CONFIG_CACHE_KEY`, cache TTL 3600s, invalidate functions
- `apps/core/signals.py:18-26` — `@receiver(post_save, sender=SiteConfig)` invalidation
- `apps/core/admin.py:11-15` — `SiteConfigAdmin` with add/delete disabled
- `apps/search/services/rate_limit.py:26-77` — per-IP `cache.add` + `cache.incr` pattern
- `apps/users/services/login_rate_limit.py:28-78` — same pattern, 10/60s
- `src/telegram_bot/services/rate_limit.py:26-61` — same pattern, per `user_id`
- `apps/core/templatetags/contact_tags.py:13-30` — existing template tag pattern (`@register.filter`)
- `apps/core/templatetags/dict_tags.py:23-43,46-81` — existing template tag pattern (`@register.filter`, `@register.simple_tag`)
- `src/backend/templates/ads/detail.html:167` — Contact Seller deep-link href
- `src/backend/templates/components/header_catalog.html:33` — Submit an ad deep-link href
- `src/backend/templates/privacy.html:30,111,148` — bot_username display + links
- `src/backend/templates/components/footer.html` — current footer (Privacy Policy + Cookie settings only)
- `src/backend/templates/users/login_issue.html:21,35-65` — deep-link href + inline JS cookie/poll pattern
- `src/telegram_bot/handlers/login.py:32-68` — `/start` handler delegates to contact
- `src/telegram_bot/handlers/contact.py:19-50` — `CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")`
- `src/backend/apps/core/services/contact.py:97-118` — `record_contact_initiated()` analytics
- `docker/nginx/nginx.conf:47` — CSP: `script-src 'self' 'unsafe-inline' https://unpkg.com https://*.plausible.io`
- `docs/99-agent/architecture.md:44-53` — SiteConfig shared cache architecture

### Web sources (HIGH confidence cross-reference)

- obscrd blog: "How CSS Can Scramble Your HTML" (2026-03-11) — CSS `direction: rtl` for emails, `order` shuffling for text, `sr-only` for screen readers, decoy injection, deterministic seeding. https://www.obscrd.dev/blog/how-css-scrambles-html
- obscrd GitHub (Show HN, 2025) — "I built an SDK that scrambles HTML so scrapers get garbage". Hacker News, 6 months ago.
- monocalc.com Email Obfuscator (2026-04-05) — comparison table of obfuscation methods (HTML entities, ROT13, JS charCodeAt, base64+atob, CSS direction, zero-width injection) with spam-safety + JS-required ratings. https://monocalc.com/tool/encode_decode/email_obfuscator
- Cloudflare Turnstile docs (2026-05) — Managed/Non-Interactive/Invisible modes, Privacy Addendum requirement for Invisible mode. https://developers.cloudflare.com/turnstile/get-started
- Cloudflare Turnstile Privacy Policy (2025-06-18) — "minimal signals", legitimate interest basis. https://www.cloudflare.com/turnstile-privacy-policy/
- Friendly Captcha analysis (2026-07-20) — Turnstile GDPR compliance concerns, accessibility issues, operator responsibility. https://friendlycaptcha.com/insights/cloudflare-turnstile-gdpr
- Friendly Captcha analysis (2026-07-28) — Turnstile accessibility limitations, screen reader issues. https://friendlycaptcha.com/insights/cloudflare-turnstile
- captcha.eu (2026-03-21) — Turnstile GDPR compliance analysis, Invisible mode requirements. https://www.captcha.eu/is-cloudflare-turnstile-gdpr-compliant
- FlowConsent (2026) — "Cloudflare Turnstile and GDPR: consent free CAPTCHA explained". https://www.flowconsent.com/en/services/security/cloudflare-turnstile
- GramIO deep-link guide (2026-08-25) — All eight `t.me` link families, payload encoding rules (64 chars, base64url, case-sensitive), Telegram deep-link spec mapping. https://gramio.dev/guides/deep-links
- Telegram API: Deep links (core.telegram.org/api/links) — Authoritative spec for `t.me` link syntax, payload constraints. https://core.telegram.org/api/links
- Telegram API: Native antispam system (core.telegram.org/api/antispam) — `telegram_antispam_user_id`, `User.is_bot`, `User.is_fake`. https://core.telegram.org/api/antispam
- StackOverflow (2023-06-12) — "How to Protect click to chat whatsapp button from bots web scraping" — base64 + atob answer. https://stackoverflow.com/questions/76459282
- Apify Academy (2026-05-27) — Anti-scraping techniques: honeypots, JS-environment analysis, behavioral analysis (mouse path, scroll cadence), rate limiting. https://use-apify.com/docs/academy/anti-scraping/techniques
- Use Apify (2026) — "17 Common Anti-Scraping Mechanisms And How Scrapers Get Around Them" — honeypot fields, behavioral scoring. https://www.datahen.com/blog/common-anti-scraping-mechanisms
- Castle blog (2026-01-05) — "Roll your own bot detection: fingerprinting/JavaScript (part 1)" — JS execution proof, canvas fingerprinting, payload encryption. https://blog.castle.com/roll-your-own-bot-detection
- AlterLab (2026-02-07) — "Headless Browser Detection: 6 Signals Sites Use" — `navigator.webdriver`, CDP markers, plugins, canvas/WebGL, timing. https://alterlab.io/blog/why-headless-browser-gets-detected
- webbrowserbot.com (2026-06-20) — "How Headless Browsers Get Detected" — webdriver flag, CDP artifacts, prototype chain checks. https://www.webbrowserbot.com/headless-browsers/headless-browser-detection.php
- SpiderNow/Youtube (2024-09-15) — "How To Hide Phone Number In Olx". YouTube.
- ProxyCove (2026-04-02) — "Avito Parsing Without Blocks" — Avito anti-bot, "Show phone" click pattern, contact info scraping. https://proxycove.com/en/blog/proxy-for-parsing-avito
- Django docs — Accessibility (WCAG 2.2 AA). https://docs.djangoproject.com/en/dev/internals/contributating/accessibility/
- django-honeypot (PyPI, 2025-06-13) — honeypot field utilities, middleware auto-injection. https://pypi.org/project/django-honeypot
- OpenReplay blog (2025-11-25) — "Honeypot Fields 101: Stop Bots Without CAPTCHAs". https://blog.openreplay.com/honeypot-fields-stop-bots
- Django Forum (2022-02-10) — honeypot field implementation discussion (avoid `type=hidden`, use CSS `display: none`). https://forum.djangoproject.com/t/bot-protection-for-publicly-accessible-form
- Wagtail blog (2025-06-24) — "htmx accessibility gaps: data and recommendations". https://wagtail.org/blog/htmx-accessibility-gaps-data-and-recommendations

### Source trust assessment (per research agent protocol)

| Source | Confidence | Justification |
|---|---|---|
| Project source code (direct file reads) | HIGH | Primary source of truth — actual files in the repo |
| Telegram Bot API docs (core.telegram.org) | HIGH | Official documentation, cross-referenced with GramIO guide |
| Django 5.2 docs (docs.djangoproject.com) | HIGH | Official framework docs, verified version |
| obscrd blog (2026-03-11) | HIGH | Recent, detailed technical write-up with code examples, open-source project (MIT) |
| monocalc.com email obfuscator (2026-04-22) | HIGH | Clear comparison table with method ratings; content is tool documentation |
| Cloudflare Turnstile docs | HIGH | Official vendor documentation |
| Friendly Captcha / captcha.eu analyses (2026) | MEDIUM | Third-party analysis of Cloudflare's privacy practices — valuable but has vendor bias (promoting Friendly Captcha); cross-referenced with Cloudflare's own privacy policy |
| Apify/AlterLab/Zenrows anti-bot articles (2026) | MEDIUM | Industry analysis, good for threat-model awareness but not prescriptive for this specific use case |
| ProxyCove Avito analysis (2026-04-02) | MEDIUM | Useful real-world example but third-party SEO/content site |
| Django Forum, StackOverflow | MEDIUM | Community-sourced, verified against accepted answers + project conventions |

---

## 10. Implementation Priority

| Priority | Task | Estimated effort | Dependencies |
|---|---|---|---|
| **P0** | Migrate `bot_username` to `SiteConfig` model (new field + service + migration) | Low (2–3h) | Existing `SiteConfig` + cache + signal infrastructure |
| **P1** | Create `telegram_deep_link` template tag with JS click-to-reveal + `data-*` assembly | Low (1–2h) | P0 (bot_username in SiteConfig); existing inline JS patterns |
| **P2** | Add CSS `direction: rtl` filter for visible display text on privacy page | Low (30m) | Tailwind `sr-only` utility (already available) |
| **P3** | Add bot-side rate limiting for `contact_<ad_id>` starts (`check_contact_start_rate_limit`) | Low (1h) | Existing `check_upload_rate_limit` pattern |
| **P4** | Add JS-execution cookie middleware | Low (1h) | Existing middleware stack (`apps/core/middleware/`) |
| **P5** | Update tests that assert `settings.BOT_USERNAME` → use `get_bot_username()` | Low (1h) | P0 |
| **P6** | Update existing tests that assert `{{ bot_username }}` in templates → assert the new tag output | Low (1h) | P1, P2 |
| SKIP | Cloudflare Turnstile | — | Not recommended (§3.4) — adds GDPR/CSP/compliance overhead for a client-side deep-link use case with no server-side form to protect |
