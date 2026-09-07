---
name: audit-findings
description: Block C — evidence-gathering for migrating views from settings.BOT_USERNAME to get_bot_username() + template migration to telegram_deep_link tag
agent: auditor
phase: 11-bot-username-migration
block: C
scope: "Verbatim study of the 4 Python view locations that pass settings.BOT_USERNAME bot_username to template context, and the 6 remaining template locations that emit cleartext {{ bot_username }} / {{ deep_link }} deep-link hrefs (detail.html:167, header_catalog.html:33, privacy.html:31/149, login_issue.html:21/40). Does NOT include Block B display-text obfuscation (privacy.html:34/112/152 sr-only spans) or Block A footer link (already migrated)."
status: complete
validated: n/a
---

# Block C Audit Report — Migrate Views from `settings.BOT_USERNAME` to `get_bot_username()` + Template Migration to `telegram_deep_link` Tag

**Scope:** Verbatim evidence from the 4 Python view locations and 6 remaining template locations that still emit cleartext `{{ bot_username }}` or `{{ deep_link }}` in deep-link `href` attributes. The `telegram_deep_link` template tag (already implemented in Block A/Task 2) is the migration target — no new tag needs to be written. This report catalogs exact current code, not proposed changes.

**Spec anchor:** `.ai/problems/18_contact-us_spec.md` CR-2 (Templates access bot username via service, not settings), CR-6 (Bot username obfuscated in all template locations), Task 9 (Update existing tests).

---

## 1. Current State Summary — What Is Already Migrated (Reference Only)

| Block | What | Files | Status |
|---|---|---|---|
| **Block A** (footer + JS cookie) | Footer `contact_us` link uses `{% telegram_deep_link "contact_us" %}`; footer sets `js=true` cookie | `footer.html`, `js_check.py`, `contact_rate_limit.py` (web-side RL) | Done |
| **Block B** (display text) | `privacy.html` display text (L34, L112, L152) uses `{{ bot_username\|rtl_obfuscate }}` + `sr-only`; `.bot-username-rtl` CSS rule in `input.css`/`output.css`; `telegram_deep_link` tag omits `bot-username-rtl` from `class_attr` | `privacy.html`, `input.css`, `output.css`, `telegram_tags.py` | Done |

**Block C remaining scope:** 4 Python views + 6 template locations that still emit cleartext deep-link hrefs or the `{{ deep_link }}` variable.

---

## 2. Python Views — `settings.BOT_USERNAME` References (4 locations)

### Q1: Exact current code at each of the 4 Python view locations

#### 2.1 `apps/core/context_processors.py` — `header_context()` (line 91)

**Import:** Line 10: `from django.conf import settings`

**Context return (lines 90–107):**
```python
    return {
        "bot_username": settings.BOT_USERNAME,           # ← line 91
        "root_categories": list(
            Category.objects.root_nodes().filter(is_active=True).order_by("name")
        ),
        "preferred_city_display": preferred_city_display,
        "cities": list(City.objects.order_by("name")),
        "favorites_count": favorites_count,
        "catalog_js_labels": json.dumps(
            {
                "show_all_results": _("Show all results"),
                "cities": _("Cities"),
                "categories": _("Categories"),
                "popular_queries": _("Popular queries"),
                "history": _("History"),
            }
        ),
    }
```

**Docstring note (lines 32–34):** The docstring already says `"bot_username": Telegram bot username (deep-link target for the "place an ad" CTA). Templates must never reference settings.BOT_USERNAME directly.` — but the implementation still reads `settings.BOT_USERNAME`.

**Audit finding:** The docstring is aspirational (references `telegram_deep_link` tag at line 132–134), but line 91 still passes the raw settings value into context. Per CR-2, this should use `get_bot_username()` from `apps.core.services.site_config`.

#### 2.2 `apps/core/views.py` — `privacy_policy()` (line 37)

**Import:** Line 32 (local import inside the function): `from django.conf import settings`

**Render call (lines 34–38):**
```python
    return render(
        request,
        "privacy.html",
        {"bot_username": settings.BOT_USERNAME},           # ← line 37
    )
```

**Audit finding:** `privacy_policy()` passes `bot_username` into context as a cleartext `{{ bot_username }}` variable. This is consumed by `privacy.html` lines 31, 34, 112, 149, 152. If the template is migrated to `{% telegram_deep_link %}` (which resolves the username internally via `get_bot_username()`), this context injection becomes unnecessary entirely — the view should pass no `bot_username` at all.

#### 2.3 `apps/ads/views/listings.py` — `ad_detail()` (line 94)

**Import:** Line 36: `from django.conf import settings`

**Context dict (lines 91–101):**
```python
    context = {
        "ad": ad,
        "breadcrumb_category": ad.category,
        "bot_username": settings.BOT_USERNAME,            # ← line 94
        "display_features": display_features,
        "is_favorited": (
            ad.favorites.filter(user_id=request.user.id).exists()
            if request.user.is_authenticated
            else False
        ),
    }
```

**Audit finding:** `ad_detail()` passes `bot_username` for `detail.html:167`. Once `detail.html:167` migrates to `{% telegram_deep_link "contact" ad.id %}`, this context key is no longer needed.

#### 2.4 `apps/users/views/consent.py` — `login_issue()` (lines 306–324)

**Import:** Line 22: `from django.conf import settings`

**Body (lines 303–324):**
```python
    raw_token = secrets.token_urlsafe(24)  # 32 URL-safe chars, matches bot regex `{32}`
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    LoginToken.objects.create(
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    bot_username = settings.BOT_USERNAME                    # ← line 311
    deep_link = f"https://t.me/{bot_username}?start=login_{raw_token}"  # ← line 312

    logger.info(f"Issued login token hash={token_hash[:8]}...")

    return render(
        request,
        "users/login_issue.html",
        {
            "deep_link": deep_link,                        # ← line 320
            "bot_username": bot_username,                  # ← line 321
            "raw_token": raw_token,                        # ← line 322
        },
    )
```

### Q7: What does `consent.py` `login_issue()` pass to the template context besides `deep_link` and `bot_username`?

**Answer:** `"raw_token": raw_token` (line 322). This is consumed by `login_issue.html:38`:
```javascript
var pollUrl = "{% url 'consent:login_status' %}?token={{ raw_token }}";
```

**Migration impact:** The `deep_link` and `bot_username` context variables can be removed entirely if `login_issue.html:21` is migrated to `{% telegram_deep_link "login" raw_token %}`. The `raw_token` variable must be retained — the tag needs it as the positional argument for the `login` command.

---

## 3. Template Locations — Cleartext `{{ bot_username }}` / `{{ deep_link }}` (8 occurrences across 6 locations)

### Q2: Exact current code at each of the 8 cleartext template locations

#### 3.1 `ads/detail.html` — Contact Seller button (line 167)

**Loads:** `{% load static %}` (L2), `{% load contact_tags %}` (L3), `{% load localized_content %}` (L4), `{% load i18n %}` (L5), `{% load trust_tags %}` (L6), `{% load price_tags %}` (L7). **Does NOT load `{% load telegram_tags %}`** (see Q10).

**Exact code (lines 164–176):**
```html
<!-- Contact button - zone R2 conditions enforced -->
<div class="p-6 border-t bg-gray-50">
    {% if ad|can_contact %}
        <a href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}"
           class="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
            {% trans "Contact Seller" %}
        </a>
    {% else %}
        <button type="button"
                class="px-6 py-3 bg-gray-400 text-white rounded-lg font-medium cursor-not-allowed"
                disabled>{% trans "Contact Seller" %}</button>
        <p class="text-xs text-gray-500 mt-2">{% trans "Seller unavailable for contact" %}</p>
    {% endif %}
</div>
```

### Q9: Exact HTML of the Contact Seller button. Any existing JS?

**Answer (when `can_contact` is true):**
```html
<a href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}"
   class="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
    {% trans "Contact Seller" %}
</a>
```

**Existing JS:** The only inline JS in `detail.html` (lines 112–122) powers the image gallery thumbnail strip + prev/next arrow navigation. It queries `[data-detail-gallery]`, `#detail-main-image`, `#detail-main-link`, `#detail-prev`, `#detail-next`, and `[data-detail-thumbs]`. It does **not** reference the contact button, `bot_username`, or any Telegram deep-link element.

**Migration target:** `{% telegram_deep_link "contact" ad.id classes="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium" %}`. The `can_contact` guard wraps the tag (the else branch stays a disabled `<button>`).

#### 3.2 `components/header_catalog.html` — Submit an ad CTA (line 33)

**Loads:** `{% load i18n %}` (L8), `{% load localized_content %}` (L9), `{% load static %]` (L10), `{% load dict_tags %}` (L11). **Does NOT load `{% load telegram_tags %}`** (see Q10).

**Exact code (lines 33–37):**
```html
<a href="https://t.me/{{ bot_username }}?start=create_ad"
   target="_blank"
   rel="noopener"
   class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700"
   data-place-ad>+ {% trans "Submit an ad" %}</a>
```

### Q8: Does `header_catalog.html` have any existing inline JS that references the "Submit an ad" link?

**Answer:** **No.** The template has a large inline IIFE (lines 217–673) but it handles only: search autocomplete dropdown, city filter navigation, "All Categories" dropdown + lazy submenu, mobile off-canvas categories, preferred-city dropdown, header auth dropdown, and favorites-badge refresh via `htmx.ajax`. None of it references `data-place-ad` or the "Submit an ad" anchor. The `data-place-ad` attribute is a dormant selector hook (spec assumption A5) with no corresponding JS handler.

**Header comment (line 6):** `Context: bot_username + root_categories (context processor), query,` — this comment references `bot_username` from the context processor. Should be updated to reference `get_bot_username()` service when the view migration removes the context variable.

**Migration target:** `{% telegram_deep_link "create_ad" classes="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700" %}`. Per spec assumption A4, `target="_blank"` and `data-place-ad` should be preserved.

**Technical concern:** The `telegram_deep_link` tag currently only emits `class="js-telegram-link {classes}"` and does not support `target="_blank"`, `rel="noopener"`, or `data-place-ad` attributes. The implementer needs to either extend the tag to accept extra attributes (`attrs` parameter) or accept that the "Submit an ad" link will navigate in the same window via JS `window.location.href`. This is a design decision for the implementer — flagged as an open consideration, not a code defect.

#### 3.3 `privacy.html` — Contact link href (line 31, spec says L30)

**Loads:** `{% load static %}` (L2), `{% load i18n %}` (L3), `{% load telegram_tags %}` (L4). **Already loads `{% load telegram_tags %}`** (see Q10).

**Exact code (lines 29–35):**
```html
<p class="text-sm text-gray-700">
    {% blocktrans with site_name=site_name %}The data controller for this service is the operator of the {{ site_name }} classifieds board. You can contact us over Telegram at{% endblocktrans %}
    <a href="https://t.me/{{ bot_username }}"
       class="text-blue-600 underline hover:text-blue-800"
       target="_blank"
       rel="noopener noreferrer">@<span class="bot-username-rtl" aria-hidden="true">{{ bot_username|rtl_obfuscate }}</span><span class="sr-only">{{ bot_username }}</span></a>.
</p>
```

### Q5: For `privacy.html` line 148 (actual L149) — what is the exact href? With or without `?start=`?

**Answer:**
```html
<a href="https://t.me/{{ bot_username }}"
   class="text-blue-600 underline hover:text-blue-800"
   target="_blank"
   rel="noopener noreferrer">@<span class="bot-username-rtl" aria-hidden="true">{{ bot_username|rtl_obfuscate }}</span><span class="sr-only">{{ bot_username }}</span></a>.
```

**The href is `https://t.me/{{ bot_username }}` — NO `?start=` query parameter.** This is a bare "open chat" link, not a deep-link with a payload.

**Key distinction for migration:** Unlike the footer (`contact_us`), `detail.html` (`contact_<ad.id>`), and `header_catalog.html` (`create_ad`) — which all use `?start=<payload>` — the privacy.html contact links are bare `t.me/<bot_username>` links. The `telegram_deep_link` tag currently always emits a `data-start` attribute (either the command name for arg-less commands, or `command_arg` for arg commands). For a bare "open chat" link, the `data-start` should be empty/absent or the tag needs a "no payload" mode. This is a design consideration: the existing `contact_us` deep-link tag in `footer.html` uses `data-start="contact_us"`, so the privacy page links could use the same `contact_us` payload rather than a bare chat link. The spec (CR-3) says the footer uses `contact_us`; there's no explicit spec decision for the privacy page links.

#### 3.4 `privacy.html` — Contact link href (line 149, spec says L148)

**Exact code (lines 148–152):**
```html
<a href="https://t.me/{{ bot_username }}"
   class="text-blue-600 underline hover:text-blue-800"
   target="_blank"
   rel="noopener noreferrer">@<span class="bot-username-rtl" aria-hidden="true">{{ bot_username|rtl_obfuscate }}</span><span class="sr-only">{{ bot_username }}</span></a>.
```

**Same as §3.3** — bare `https://t.me/{{ bot_username }}`, no `?start=`.

#### 3.5 `privacy.html` — Display text `sr-only` span (line 34, spec says L33)

**Exact code (line 34):**
```html
@<span class="bot-username-rtl" aria-hidden="true">{{ bot_username|rtl_obfuscate }}</span><span class="sr-only">{{ bot_username }}</span>
```

**Status:** Block B already migrated the *visible* display text to `{{ bot_username|rtl_obfuscate }}` with the `bot-username-rtl` CSS class. The `sr-only` span deliberately retains the cleartext `{{ bot_username }}` for screen-reader accessibility (spec Task 3: "paired with a visually-hidden `sr-only` element containing the clean username for accessibility"). This is **by design** — the `sr-only` span is hidden visually via CSS and read by screen readers.

**Migration target:** No change needed for display text. Only the `href` attribute (§3.3) needs migration to the `telegram_deep_link` tag. The `sr-only` span will continue to use `{{ bot_username }}` — but this means `privacy.html` still needs `bot_username` in context. However, `privacy_policy()` view (§2.2) passes it. If the view stops passing `bot_username`, the `sr-only` span breaks. **Conflict to resolve:** either (a) keep `bot_username` in context for `sr-only` spans and accept that the username is visible to screen readers (acceptable per spec — it's the visible display that must be obfuscated, and `sr-only` is hidden from visual/scraper view), or (b) remove `sr-only` spans entirely and rely on the `aria-label` from the tag.

**Recommendation (advisory):** Keep `bot_username` context for the `sr-only` display-text spans but migrate the `href` to `telegram_deep_link`. This requires `privacy_policy()` to still pass `bot_username` via `get_bot_username()`.

#### 3.6 `privacy.html` — `<code>` legal disclosure display text (line 112, spec says L111)

**Exact code (line 112):**
```html
<li><strong>{% trans "Telegram" %}</strong> — {% blocktrans with obfuscated=bot_username|rtl_obfuscate %}authentication and seller-buyer contact relay via deep-links (<code>t.me/@<span class="bot-username-rtl" aria-hidden="true">{{ obfuscated }}</span><span class="sr-only">{{ bot_username }}</span></code>). No ad content is shared; only the identifiers needed for the action.{% endblocktrans %}
```

**Status:** Same as §3.5 — Block B handled the visible text (`{{ obfuscated }}` = `bot_username|rtl_obfuscate`), with `sr-only` span for accessibility. The `{{ bot_username }}` in the `sr-only` span is by design.

**Migration target:** No change for display text. The `<code>` block is inside a `<li>` — it's not a clickable link, so no `telegram_deep_link` tag migration needed here.

#### 3.7 `privacy.html` — Contact link href (line 149) — see §3.4

#### 3.8 `privacy.html` — Display text `sr-only` span (line 152, spec says L148 display)

**Exact code (line 152):**
```html
@<span class="bot-username-rtl" aria-hidden="true">{{ bot_username|rtl_obfuscate }}</span><span class="sr-only">{{ bot_username }}</span></a>.
```

**Same as §3.5** — Block B display-text migration complete; `sr-only` span retains cleartext `{{ bot_username }}` by design.

#### 3.9 `users/login_issue.html` — Deep-link href (line 21)

**Loads:** `{% load static %}` (L2), `{% load i18n %}` (L3). **Does NOT load `{% load telegram_tags %}`** (see Q10).

**Exact code (lines 21–24):**
```html
<a href="{{ deep_link }}"
   class="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition-colors">
    {% trans "Login via Telegram" %}
</a>
```

### Q6: For `login_issue.html` line 40 — what is the existing JS `querySelector` selector? What does it do?

**Exact code (line 40):**
```javascript
var deepLinkEl = document.querySelector('a[href^="https://t.me"]');
```

**What it does (lines 35–43):**
```javascript
<script>
(function () {
    "use strict";
    var pollUrl = "{% url 'consent:login_status' %}?token={{ raw_token }}";
    var statusEl = document.getElementById("login-status");
    var deepLinkEl = document.querySelector('a[href^="https://t.me"]');

    statusEl.classList.remove("hidden");
    deepLinkEl.style.display = "none";
    // ... polling logic follows ...
})();
</script>
```

The selector `a[href^="https://t.me"]` matches the `<a>` element whose `href` starts with `https://t.me`. Currently this matches line 21's `<a href="{{ deep_link }}">` which renders to `href="https://t.me/bazuna_bot?start=login_..."`.

The script then **hides** the deep-link element (`deepLinkEl.style.display = "none"`) because the login flow is polling-based: the user must manually open the Telegram link (tap-and-hold → "Open in Telegram") while the JS polls `/login/status/` for the bot to claim the token. The hidden link is not meant to be clicked directly.

**Migration impact:** After migrating to `{% telegram_deep_link "login" raw_token %}`, the rendered `<a>` will have `href="#"` (not `href="https://t.me/..."`), so `a[href^="https://t.me"]` will **no longer match**. The JS selector must be updated to find the element by a class or data attribute. The tag emits `class="js-telegram-link"` and `data-bot-encoded="..."`, `data-start="login_..."`. A suitable replacement selector would be `document.querySelector('.js-telegram-link')` or `document.querySelector('[data-start^="login_"]')`.

**Additional concern:** The `telegram_deep_link` tag's inline `<script>` IIFE attaches a click handler that calls `e.preventDefault()` and then `window.location.href = 'https://t.me/' + ...`. But the `login_issue.html` JS *hides* the link element. If the link is `display: none`, the user can't click it — which is the current intent (user opens it manually from a long-press/share). However, the tag's IIFE click handler would still fire if the link is somehow clicked. The migration needs to decide: does the login deep-link use the tag's click-to-reveal (visible, clickable) or keep the current hide-and-poll pattern (hidden, manual open)? Per spec Q2=A, all locations must be obfuscated — so the tag should be used. But the hide-and-poll UX means the link should remain hidden. The implementer should keep the `display: none` after finding the element by its new selector.

---

## 4. Template Tag Reference

### Q3: What commands does the `TelegramDeepLinkCommand` enum have? Which ones take arguments (`_HAS_ARG`)?

**Enum (telegram_tags.py lines 46–53):**
```python
class TelegramDeepLinkCommand(StrEnum):
    """Telegram deep-link ``start`` payloads (CR-2)."""

    CONTACT = "contact"
    CONTACT_US = "contact_us"
    CREATE_AD = "create_ad"
    LOGIN = "login"
```

**`_HAS_ARG` set (telegram_tags.py lines 64–69):**
```python
_HAS_ARG: frozenset[TelegramDeepLinkCommand] = frozenset(
    {
        TelegramDeepLinkCommand.CONTACT,
        TelegramDeepLinkCommand.LOGIN,
    }
)
```

**Summary:**

| Command | Enum value | Takes argument? | Argument meaning |
|---|---|---|---|
| `CONTACT` | `"contact"` | Yes | `ad.id` — produces `data-start="contact_<ad_id>"` |
| `CONTACT_US` | `"contact_us"` | No | produces `data-start="contact_us"` (no arg) |
| `CREATE_AD` | `"create_ad"` | No | produces `data-start="create_ad"` (no arg) |
| `LOGIN` | `"login"` | Yes | `raw_token` — produces `data-start="login_<token>"` |

### Q4: Does the `telegram_deep_link` tag accept a `classes` parameter? What does it do with it?

**Answer:** Yes. Signature (telegram_tags.py lines 86–92):
```python
@register.simple_tag(takes_context=True)
def telegram_deep_link(
    context: template.Context,
    command: str,
    *args: str,
    classes: str = "",
) -> str:
```

**What it does (line 139):**
```python
class_attr = f"js-telegram-link {classes}".strip()
```

The `classes` string is appended to the base `js-telegram-link` class and placed in the rendered `<a>`'s `class` attribute. Example usage from the docstring (lines 97–100):
```html
{% telegram_deep_link "create_ad" classes="..." %}
{% telegram_deep_link "contact" ad.id classes="..." %}
{% telegram_deep_link "contact_us" classes="..." %}
{% telegram_deep_link "login" raw_token classes="..." %}
```

**What it does NOT do:** The tag does not accept arbitrary HTML attributes (`target`, `rel`, `data-*`, `aria-label`). It only accepts the `classes` string. The visible text is always the translatable label from `_LABELS` (lines 56–61), and the `aria-label` is also set to the label. Any view-specific attributes (like `target="_blank"` on the header catalog CTA, or `data-place-ad`) cannot be passed through the current tag interface.

**IIFE script (telegram_tags.py lines 73–83):**
```python
_JS_IIFE: Final[str] = (
    '<script>(function() { "use strict";'
    "var el = document.currentScript.previousElementSibling;"
    "if (!el) return;"
    "el.addEventListener('click', function(e) {"
    "e.preventDefault();"
    "var username = atob(el.dataset.botEncoded);"
    "window.location.href = 'https://t.me/' + username + '?start=' + encodeURIComponent(el.dataset.start);"
    "});"
    "})();</script>"
)
```

The IIFE targets its preceding `<a>` element via `document.currentScript.previousElementSibling`, reads `data-bot-encoded` (base64 username) and `data-start` (the start payload), decodes the base64 with `atob()`, and on click navigates to `https://t.me/<username>?start=<payload>`. The `js_verified` flag (CR-11) gates whether the full markup or an inert `#` anchor is emitted.

### Q10: Does each template already load `{% load telegram_tags %}`?

| Template | Loads `{% load telegram_tags %}`? | Current `{% load %}` lines |
|---|---|---|
| `ads/detail.html` | **No** | L2: `static`, L3: `contact_tags`, L4: `localized_content`, L5: `i18n`, L6: `trust_tags`, L7: `price_tags` |
| `components/header_catalog.html` | **No** | L8: `i18n`, L9: `localized_content`, L10: `static`, L11: `dict_tags` |
| `privacy.html` | **Yes** | L2: `static`, L3: `i18n`, L4: `telegram_tags` |
| `users/login_issue.html` | **No** | L2: `static`, L3: `i18n` |

**3 of 4 templates need `{% load telegram_tags %}` added.** Only `privacy.html` already has it.

---

## 5. Test Impact Analysis

Based on verbatim reading of the test files:

### 5.1 `apps/ads/tests/test_detail_context.py`

- **`test_detail_context_contains_bot_username` (L106–111):**
  ```python
  def test_detail_context_contains_bot_username() -> None:
      """``ad_detail`` must pass ``bot_username`` matching ``settings.BOT_USERNAME``."""
      ad = MagicMock()
      context = _run_detail(ad)
      assert "bot_username" in context, "bot_username must be passed in the context dict"
      assert context["bot_username"] == settings.BOT_USERNAME
  ```
  **Impact:** If `ad_detail()` stops passing `bot_username` (because `detail.html:167` migrates to the tag), this test breaks. Per project rule #2, the test must be updated — either to assert the tag is used in the template, or to assert `bot_username` is no longer needed.

- **`test_detail_template_uses_bot_username_not_settings` (L133–140):**
  ```python
  def test_detail_template_uses_bot_username_not_settings() -> None:
      """The rendered template variable name is ``bot_username``, not
      ``settings.BOT_USERNAME``."""
      content = (Path(__file__).resolve().parents[3] / "templates/ads/detail.html").read_text(...)
      assert "{{ bot_username }}" in content
      assert "settings.BOT_USERNAME" not in content
  ```
  **Impact:** After migration, `"{{ bot_username }}"` should no longer appear in `detail.html` (the href becomes `{% telegram_deep_link "contact" ad.id ... %}`). This assertion must flip to assert the tag is present and `{{ bot_username }}` is absent.

### 5.2 `apps/ads/tests/test_detail_render.py`

- **`test_telegram_contact_deep_link_href` (L48–68):**
  ```python
  def test_telegram_contact_deep_link_href(self, ...) -> None:
      """G4: The contact link deep-links to Telegram with contact_<ad.id>."""
      ...
      content = response.content.decode("utf-8")
      expected_href = f"https://t.me/{settings.BOT_USERNAME}?start=contact_{ad.id}"
      assert f'href="{expected_href}"' in content
  ```
  **Impact:** After migration, the `href` is `#` (not the cleartext `t.me/` URL). The test must be rewritten to assert `data-bot-encoded` and `data-start="contact_<ad.id>"` and `js-telegram-link` class instead.

### 5.3 `apps/search/tests/test_autocomplete_template.py`

- **`test_bot_username_comes_from_context` (L133–135):**
  ```python
  def test_bot_username_comes_from_context() -> None:
      """The place-an-ad deep-link uses the ``bot_username`` context var."""
      assert "{{ bot_username }}" in _HEADER_CATALOG_CONTENT
  ```
  **Impact:** After migrating `header_catalog.html:33` to `{% telegram_deep_link "create_ad" ... %}`, `{{ bot_username }}` will no longer appear in the template. This assertion must be updated to check for `telegram_deep_link` / `js-telegram-link` / `data-bot-encoded`.

- **`test_no_settings_dot_access_in_template` (L127–130):**
  ```python
  def test_no_settings_dot_access_in_template() -> None:
      assert "settings.BOT_USERNAME" not in _HEADER_CATALOG_CONTENT
  ```
  **Impact:** Should still pass (the template doesn't reference `settings.BOT_USERNAME`). No change needed, but verify after migration.

### 5.4 `apps/users/tests/test_login.py`

- **`test_login_issue_renders_deep_link` (L40–48):**
  ```python
  def test_login_issue_renders_deep_link(self) -> None:
      """login_issue returns 200 and renders the Telegram deep-link."""
      client = Client()
      response = client.get("/login/issue/")
      assert response.status_code == 200
      content = response.content.decode()
      assert "t.me" in content
      assert "start=login_" in content
  ```
  **Impact:** After migration, `t.me` may not appear as cleartext (it's assembled by JS from base64). The `data-start` attribute will contain `login_<token>`. The test should assert `data-start="login_..."` and `js-telegram-link` instead of `"t.me" in content`. However, the token value is random, so the test may need to extract `data-start` and verify it starts with `login_`.

- **`test_login_issue_passes_raw_token_to_template` (L85–92):**
  ```python
  def test_login_issue_passes_raw_token_to_template(self) -> None:
      assert response.status_code == 200
      assert "raw_token" in response.context
      assert len(response.context["raw_token"]) == 32
  ```
  **Impact:** No change needed — `raw_token` is still passed to context (the tag needs it as the `login` argument).

---

## 6. Migration Dependencies and Considerations

### 6.1 Tag limitations that affect migration

The `telegram_deep_link` tag currently:
- Does **not** support `target="_blank"` — the header catalog CTA (§3.2) and privacy contact links use `target="_blank"`. The tag's IIFE uses `window.location.href = ...` which navigates the current tab. **Decision needed:** either add a `target` parameter, or accept same-tab navigation.
- Does **not** support `rel="noopener"` / `rel="noopener noreferrer"` — needed for security when opening in a new tab.
- Does **not** support arbitrary `data-*` attributes — `data-place-ad` on the header catalog CTA (§3.2) cannot be passed.
- Does **not** support the `transition-colors` Tailwind class cleanly — it passes `classes` which is concatenated, so this works fine.

### 6.2 `privacy.html` href migration ambiguity

The privacy page contact links (§3.3, §3.4) are **bare** `https://t.me/{{ bot_username }}` links without `?start=`. The `telegram_deep_link` tag always emits a `data-start` payload. Options:
- (a) Use `{% telegram_deep_link "contact_us" %}` — this emits `data-start="contact_us"` and navigates to `https://t.me/<bot>?start=contact_us`. This changes behavior: clicking the privacy link would start a `contact_us` deep-link flow rather than a bare chat open. This may be acceptable/desired per CR-3 (footer also uses `contact_us`).
- (b) Add a "no payload" mode to the tag (e.g., `{% telegram_deep_link "open_chat" %}` or a flag). This requires new tag code — outside Block C's spec scope.
- (c) Leave as-is (cleartext `href` with `rtl_obfuscate` display text). This fails CR-6.

**Recommendation:** Option (a) is simplest and consistent with the footer link. The privacy page contact links would use the same `contact_us` deep-link payload as the footer.

### 6.3 `header_catalog.html` comment cleanup

Line 6 of `header_catalog.html`:
```
Context: bot_username + root_categories (context processor), query,
```
After migration, `bot_username` is no longer a template variable — the tag resolves it via `get_bot_username()` internally. The comment should be updated to reference `get_bot_username()` or removed. However, `header_context()` (context_processors.py:91) still passes `bot_username` — and `header_catalog.html` is included on every page that uses `header_context`. If the context processor stops passing `bot_username`, any other template still using `{{ bot_username }}` would break. Currently, only `header_catalog.html:33` and `privacy.html` (via `privacy_policy()` view context) use it. After both are migrated, the context processor can stop passing it.

---

## 7. Verbatim Evidence Map (Q1/Q2)

### Python view locations (`settings.BOT_USERNAME` → `get_bot_username()`):

```
src/backend/apps/core/context_processors.py:91     "bot_username": settings.BOT_USERNAME,
src/backend/apps/core/views.py:37                {"bot_username": settings.BOT_USERNAME},
src/backend/apps/ads/views/listings.py:94         "bot_username": settings.BOT_USERNAME,
src/backend/apps/users/views/consent.py:311       bot_username = settings.BOT_USERNAME
```

### Template locations (cleartext `{{ bot_username }}` or `{{ deep_link }}` in hrefs):

```
src/backend/templates/ads/detail.html:167               href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}"
src/backend/templates/components/header_catalog.html:33 href="https://t.me/{{ bot_username }}?start=create_ad"
src/backend/templates/components/header_catalog.html:6  Context comment: "bot_username + root_categories (context processor)"
src/backend/templates/privacy.html:31                   href="https://t.me/{{ bot_username }}"
src/backend/templates/privacy.html:34                   sr-only: {{ bot_username }}  (Block B: visible text obfuscated)
src/backend/templates/privacy.html:112                  sr-only: {{ bot_username }}  (Block B: visible text obfuscated, via blocktrans {{ obfuscated }})
src/backend/templates/privacy.html:149                  href="https://t.me/{{ bot_username }}"
src/backend/templates/privacy.html:152                  sr-only: {{ bot_username }}  (Block B: visible text obfuscated)
src/backend/templates/users/login_issue.html:21           href="{{ deep_link }}"
src/backend/templates/users/login_issue.html:40           document.querySelector('a[href^="https://t.me"]')
```

### Already migrated (Block A/B reference):

```
src/backend/templates/components/footer.html:10       {% telegram_deep_link "contact_us" classes="underline hover:text-gray-800" %}
src/backend/templates/components/footer.html:13        <script>(function () { 'use strict'; document.cookie = "js=true; SameSite=Lax; Secure; path=/"; })();</script>
```

### Tests that assert cleartext `{{ bot_username }}` or `href="https://t.me/..."` (must be updated per Task 9):

```
apps/ads/tests/test_detail_context.py:110     assert "bot_username" in context
apps/ads/tests/test_detail_context.py:111     assert context["bot_username"] == settings.BOT_USERNAME
apps/ads/tests/test_detail_context.py:139     assert "{{ bot_username }}" in content
apps/ads/tests/test_detail_render.py:67        expected_href = f"https://t.me/{settings.BOT_USERNAME}?start=contact_{ad.id}"
apps/ads/tests/test_detail_render.py:68        assert f'href="{expected_href}"' in content
apps/search/tests/test_autocomplete_template.py:135  assert "{{ bot_username }}" in _HEADER_CATALOG_CONTENT
apps/users/tests/test_login.py:47               assert "t.me" in content
apps/users/tests/test_login.py:48               assert "start=login_" in content
```

---

## 8. Files Read in Full (Audit Trail)

| File | Purpose |
|---|---|
| `src/backend/apps/core/context_processors.py` | `header_context()` — passes `bot_username: settings.BOT_USERNAME` (Q1, §2.1) |
| `src/backend/apps/core/views.py` | `privacy_policy()` — passes `bot_username: settings.BOT_USERNAME` (Q1, §2.2) |
| `src/backend/apps/ads/views/listings.py` | `ad_detail()` — passes `bot_username: settings.BOT_USERNAME` (Q1, §2.3) |
| `src/backend/apps/users/views/consent.py` | `login_issue()` — builds `deep_link` from `settings.BOT_USERNAME`, passes `deep_link` + `bot_username` + `raw_token` (Q1/Q7, §2.4) |
| `src/backend/apps/core/templatetags/telegram_tags.py` | `TelegramDeepLinkCommand` enum, `_HAS_ARG`, `_JS_IIFE`, `telegram_deep_link()` tag with `classes` kwarg, `rtl_obfuscate` filter (Q3/Q4 §4) |
| `src/backend/apps/core/services/site_config.py` | `get_bot_username()` — resolves from `SiteConfig` singleton cache, falls back to `'bazuna_bot'` (service that replaces `settings.BOT_USERNAME`) |
| `src/backend/apps/core/middleware/js_check.py` | `JSExecutionMiddleware` — sets `request.js_verified` from `js=true` cookie (CR-11) |
| `src/backend/apps/core/utils/cache.py` | `get_cached_bot_username` / `set_cached_bot_username` / `invalidate_bot_username_cache` — cache helpers (verified) |
| `src/backend/templates/ads/detail.html` | Contact Seller button cleartext href (Q2/Q9, §3.1) |
| `src/backend/templates/components/header_catalog.html` | Submit an ad CTA cleartext href + comment (Q2/Q8, §3.2) |
| `src/backend/templates/privacy.html` | 4 cleartext `{{ bot_username }}` refs (2 hrefs, 2 sr-only; display text already Block B) (Q2/Q5, §3.3–3.8) |
| `src/backend/templates/users/login_issue.html` | `{{ deep_link }}` href + JS `querySelector('a[href^="https://t.me"]')` (Q2/Q6, §3.9) |
| `src/backend/templates/components/footer.html` | Block A reference — already uses `{% telegram_deep_link "contact_us" %}` + JS cookie (§1) |
| `src/backend/apps/ads/tests/test_detail_context.py` | Test assertions on `bot_username` context + `{{ bot_username }}` in template (§5.1) |
| `src/backend/apps/ads/tests/test_detail_render.py` | Test assertion on cleartext `href="https://t.me/..."` (§5.2) |
| `src/backend/apps/search/tests/test_autocomplete_template.py` | Test assertion `{{ bot_username }}` in header_catalog (§5.3) |
| `src/backend/apps/users/tests/test_login.py` | Test assertions `"t.me" in content` + `"start=login_"` (§5.4) |
| `src/backend/apps/core/tests/test_rtl_obfuscation.py` | Block B tests — confirms privacy.html display text already migrated, notes hrefs are Block C scope (§1) |
| `src/backend/apps/core/tests/test_footer_contact_link.py` | Block A tests — reference for how `telegram_deep_link` tag rendering is tested (§1) |
| `.ai/problems/18_contact-us_spec.md` | Full spec — CR-2, CR-6, Task 9, Q2=A, Q6=A, A3/A4/A5 (spec anchor for all findings) |
| `theme/static/theme/css/input.css` | `.bot-username-rtl { direction: rtl; unicode-bidi: bidi-override; }` rule exists (Block B §1) |
| `theme/static/theme/css/output.css` | Compiled `.bot-username-rtl` rule exists (Block B §1) |

---

## 9. Summary — Answers to the 10 Questions

1. **4 Python view locations referencing `settings.BOT_USERNAME`:**
   - `context_processors.py:91` — `"bot_username": settings.BOT_USERNAME` in `header_context()` return dict
   - `views.py:37` — `{"bot_username": settings.BOT_USERNAME}` in `privacy_policy()` render context
   - `listings.py:94` — `"bot_username": settings.BOT_USERNAME,` in `ad_detail()` context dict
   - `consent.py:311` — `bot_username = settings.BOT_USERNAME` in `login_issue()`, used to build `deep_link` and passed to context

2. **8 cleartext template locations (`{{ bot_username }}` or `{{ deep_link }}`):**
   - `detail.html:167` — `href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}"`
   - `header_catalog.html:33` — `href="https://t.me/{{ bot_username }}?start=create_ad"`
   - `privacy.html:31` — `href="https://t.me/{{ bot_username }}"` (no `?start=`)
   - `privacy.html:34` — `@<span ...>{{ bot_username|rtl_obfuscate }}</span><span class="sr-only">{{ bot_username }}</span>` (sr-only only; visible text already Block B)
   - `privacy.html:112` — `<code>t.me/@<span ...>{{ obfuscated }}</span><span class="sr-only">{{ bot_username }}</span>` (sr-only only; visible text already Block B, via blocktrans)
   - `privacy.html:149` — `href="https://t.me/{{ bot_username }}"` (no `?start=`)
   - `privacy.html:152` — same sr-only pattern as L34 (visible text already Block B)
   - `login_issue.html:21` — `href="{{ deep_link }}"`

3. **`TelegramDeepLinkCommand` enum values:** `CONTACT`, `CONTACT_US`, `CREATE_AD`, `LOGIN`. **Take arguments (`_HAS_ARG`):** `CONTACT` (arg = `ad.id`), `LOGIN` (arg = `raw_token`). **No arguments:** `CONTACT_US`, `CREATE_AD`.

4. **`classes` parameter:** Yes — `classes: str = ""` (line 91). It is concatenated into `class_attr = f"js-telegram-link {classes}".strip()` (line 139) and placed on the rendered `<a>`. The tag does NOT support `target`, `rel`, `data-*`, or other arbitrary attributes — only a CSS class string.

5. **`privacy.html` line 149 (spec L148) href:** `href="https://t.me/{{ bot_username }}"` — **without** `?start=`. It is a bare "open Telegram chat" link, no deep-link payload.

6. **`login_issue.html` line 40 JS selector:** `document.querySelector('a[href^="https://t.me"]')`. It selects the `<a>` whose href starts with `https://t.me`, then hides it (`deepLinkEl.style.display = "none"`) because the login flow is polling-based (user manually opens the deep-link, JS polls for token claim). **Breaks after migration** because the tag renders `href="#"`, not `href="https://t.me/..."`.

7. **`consent.py` `login_issue()` context besides `deep_link` and `bot_username`:** `"raw_token": raw_token` (line 322) — used by the polling JS at `login_issue.html:38`: `var pollUrl = "{% url 'consent:login_status' %}?token={{ raw_token }}"`.

8. **`header_catalog.html` inline JS referencing "Submit an ad":** **None.** The template's IIFE (lines 217–673) handles search autocomplete, city/category dropdowns, mobile nav, auth dropdown, and favorites refresh. The `data-place-ad` attribute on the CTA (line 37) is a dormant selector hook with no corresponding JS handler.

9. **`detail.html:167` Contact Seller button:** `<a href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}" class="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">{% trans "Contact Seller" %}</a>`. The only inline JS in `detail.html` (lines 112–122) handles the image gallery — no JS references the contact button.

10. **`{% load telegram_tags %}` status:**
    - `detail.html`: **No** (loads `static`, `contact_tags`, `localized_content`, `i18n`, `trust_tags`, `price_tags`)
    - `header_catalog.html`: **No** (loads `i18n`, `localized_content`, `static`, `dict_tags`)
    - `privacy.html`: **Yes** (loads `static`, `i18n`, `telegram_tags`)
    - `login_issue.html`: **No** (loads `static`, `i18n`)
