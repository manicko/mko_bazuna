---
name: audit-findings
description: Evidence-gathering (Block B) — CSS direction:rtl + bot-username-rtl + rtl_obfuscate filter, and privacy.html consumer migration
agent: auditor
phase: 11-bot-username-migration
block: B
scope: "CSS direction:rtl technique (Task 3), the bot-username-rtl class, the rtl_obfuscate filter, and the privacy.html display-text consumer migration ONLY. Footer 'Contact us' link (Block A) is in scope only where its class_attr carries bot-username-rtl. Other consumer templates (detail.html, header_catalog.html, login_issue.html) are referenced for context but are Block C/E scope."
status: complete
validated: n/a
---

# Block B Audit Report — CSS `direction: rtl` + `bot-username-rtl` + `rtl_obfuscate` filter

**Scope:** Spec 18, Task 3 ("Apply CSS `direction: rtl` for visible display text") — the visible-display-text obfuscation layer of the bot-username anti-spam scheme. No production code was modified; this is read-only evidence gathering.

**Spec anchor:** `.ai/problems/18_contact-us_spec.md` §5.1, §6.4, Task 3 (L257-269), Constraint #4 (L482-485):

> Visible display text … protected with CSS `direction: rtl` + `unicode-bidi: bidi-override`
> (the reversed string is in the HTML text node, flipped visually by CSS). … paired with a
> visually-hidden `sr-only` element containing the clean text for accessibility.
>
> `.bot-username-rtl { direction: rtl; unicode-bidi: bidi-override; }` applied to reversed
> display text, paired with a visually-hidden `sr-only` element containing the clean text

> A template filter `{{ bot_username|rtl_obfuscate }}` (optional, in `dict_tags.py` or `telegram_tags.py`)

---

## 0. HEADLINE VERDICT — Task 3 is NOT wired; CSS rule absent; filter technique diverges from spec

The partial implementation added two pieces relevant to Block B:

1. The `rtl_obfuscate` filter **exists** in `telegram_tags.py:154-172` and is imported by the `telegram_deep_link` tag's module.
2. The `bot-username-rtl` class string **is emitted** into the rendered anchor via `telegram_deep_link`'s `class_attr` (`telegram_tags.py:131`).

**But none of the remaining Task-3 obligations are satisfied:**

- **The `.bot-username-rtl` CSS rule is not defined anywhere** — not in the Tailwind source, not in the compiled output, not as an inline style. The class is a no-op wherever it appears.
- **The `rtl_obfuscate` filter does NOT match the documented technique.** It inserts Unicode RTL marks (U+200F) between characters; the spec §5.1 / Task 3 require **string reversal** paired with `direction: rtl; unicode-bidi: bidi-override`. These are different obfuscation strategies and the current filter cannot pair with the declared CSS class.
- **`privacy.html` was not migrated.** It still renders cleartext `{{ bot_username }}` at L30, L33, L111, L148 (and L151), does **not** `{% load telegram_tags %}`, and uses neither the `telegram_deep_link` tag nor the `rtl_obfuscate` filter for its display text.

**Status of Block B's three Task-3 artifacts:**

| Artifact | Spec requirement | Current state | Verdict |
|---|---|---|---|
| `.bot-username-rtl` CSS class (`direction: rtl; unicode-bidi: bidi-override`) | Must exist in stylesheet | **Not defined** anywhere | ❌ Missing |
| `rtl_obfuscate` filter | Reverse the string (to be flipped back by CSS) | **Inserts U+200F marks** (no reversal) | ⚠ Spec deviation |
| `privacy.html` display text (L30/L33/L111/L148/L151) | Use `telegram_deep_link` tag (href) + `rtl_obfuscate`+`sr-only` (display) | Still **cleartext `{{ bot_username }}`**; `telegram_tags` not loaded | ❌ Not migrated |

---

## 1. Findings

### F-BB-001: `.bot-username-rtl` CSS rule is referenced in code but defined nowhere

| Field | Value |
|---|---|
| **ID** | F-BB-001 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Classification** | mandatory (correctness — obfuscation silently does nothing) |
| **Affected Modules** | `src/theme/static/theme/css/input.css`, `src/theme/static/theme/css/output.css`, `src/backend/apps/core/templatetags/telegram_tags.py:131` |

**Description:** The `telegram_deep_link` tag unconditionally appends `bot-username-rtl` to every rendered anchor's `class` attribute (`telegram_tags.py:131`):

```python
# telegram_tags.py:130-131
# Always include bot-username-rtl for visual obfuscation of the link text.
class_attr = f"js-telegram-link bot-username-rtl {classes}".strip()
```

The spec (Task 3, L261-263) requires the matching stylesheet rule:

```css
.bot-username-rtl { direction: rtl; unicode-bidi: bidi-override; }
```

This rule **does not exist** in either CSS source or compiled output:

- `grep -l "bot-username-rtl" src/theme/static/theme/css/input.css` → no match
- `grep -l "bot-username-rtl" src/theme/static/theme/css/output.css` → **no match** (0 hits)
- `grep -rn "bot-username-rtl" src/**/*.css` across the repo → only doc/spec references

**Consequence:** The class is a dead/no-op selector. On the footer link (`footer.html:10`) it is applied to the translatable **label** "Contact us" (the visible text is NOT the bot username), so even if the rule existed it would have no obfuscation effect there. On any future privacy.html display-text use it would silently fail to reverse the text because the CSS is absent.

**Evidence:**
```
telegram_tags.py:131   class_attr = f"js-telegram-link bot-username-rtl {classes}".strip()
input.css: (only @import + @source — no custom rules, no .bot-username-rtl)
output.css: 0 occurrences of "bot-username-rtl"
```

**Recommendation:** Add the rule to `input.css` (the canonical Tailwind v4 source is `src/theme/static/theme/css/input.css`, which currently contains only an `@import` and two `@source` directives — no custom utilities). In Tailwind v4 the custom rule can be appended as a plain (non-`@layer`) rule or inside `@layer utilities`. Then **recompile** so it appears in `output.css`. Effort: trivial. Priority: mandatory — a no-op class is worse than no class (false sense of protection).

---

### F-BB-002: `privacy.html` still serves cleartext `{{ bot_username }}` — Task 3 display-text migration not applied

| Field | Value |
|---|---|
| **ID** | F-BB-002 |
| **Severity** | HIGH |
| **Type** | SPEC-DEVIATION |
| **Classification** | mandatory (security/scraper-extraction correctness) |
| **Affected Modules** | `src/backend/templates/privacy.html`, `src/backend/apps/core/views.py:37` |

**Description:** Spec Q2=A mandates **all** bot-username template locations be obfuscated. `privacy.html` is named explicitly in Task 3 (L267: "lines 30, 33, 111, 148"). None of the four locations were updated:

**Exact current code at the four target lines:**

- **Line 30** (clickable deep-link href — `t.me/<bot_username>`):
  ```html
  <a href="https://t.me/{{ bot_username }}"
  ```
- **Line 33** (display text `@{{ bot_username }}`):
  ```html
                rel="noopener noreferrer">@{{ bot_username }}</a>.
  ```
- **Line 111** (`<code>t.me/{{ bot_username }}</code>` legal disclosure):
  ```html
  <li><strong>{% trans "Telegram" %}</strong> — {% blocktrans %}authentication and seller-buyer contact relay via deep-links (<code>t.me/{{ bot_username }}</code>). No ad content is shared; only the identifiers needed for the action.{% endblocktrans %}
  ```
- **Line 148** (second clickable deep-link href):
  ```html
  <a href="https://t.me/{{ bot_username }}"
  ```
  (Its companion display text is line 151: `rel="noopener noreferrer">@{{ bot_username }}</a>.`)

**Two compounding defects:**

1. `privacy.html` loads **only** `{% load static %}` (L2) and `{% load i18n %}` (L3). It does **not** `{% load telegram_tags %}`, so neither the `telegram_deep_link` tag nor the `rtl_obfuscate` filter is even available to this template.
2. `privacy_policy()` in `apps/core/views.py:34-38` still passes the env-var-backed value:
   ```python
   return render(
       request,
       "privacy.html",
       {"bot_username": settings.BOT_USERNAME},
   )
   ```
   This is the residual F-BU-001 consumer (Block 1) — `settings.BOT_USERNAME` instead of `get_bot_username()`. Even after a template-level rewrite, the context variable would still carry the wrong source.

**Evidence:**
- `privacy.html:2-3` — `{% load static %}` / `{% load i18n %}` only; no `{% load telegram_tags %}`
- `privacy.html:30,33,111,148,151` — all contain `{{ bot_username }}` in cleartext
- `views.py:37` — `{"bot_username": settings.BOT_USERNAME}`

**Recommendation (two-part):**
1. **Display text** (L33, L111, L151): wrap with `<span class="bot-username-rtl">...</span>` around the *reversed* username, paired with a visually-hidden `<span class="sr-only">@{{ bot_username }}</span>` for screen readers (spec §5.1, Task 3). Use the `rtl_obfuscate` filter once it is corrected (see F-BB-003) to reverse the string server-side, or reverse via template logic.
2. **Click h refs** (L30, L148): replace the cleartext `<a href="https://t.me/{{ bot_username }}">` with `{% telegram_deep_link "contact_us" %}` (the tag already emits base64 `data-bot-encoded` + IIFE), which requires `{% load telegram_tags %}`.
3. Migrate `views.py:37` from `settings.BOT_USERNAME` → `get_bot_username()` (F-BU-001, Block 1) so the reversed/display value resolves from SiteConfig.

Effort: medium (template rewrite + i18n `makemessages`/`compilemessages` needed for any new translatable strings; constraint #7). Priority: mandatory.

---

### F-BB-003: `rtl_obfuscate` filter uses RTL-mark insertion, not string reversal — diverges from spec §5.1 / Task 3

| Field | Value |
|---|---|
| **ID** | F-BB-003 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Classification** | mandatory (correctness — the filter cannot satisfy the declared CSS technique) |
| **Affected Modules** | `src/backend/apps/core/templatetags/telegram_tags.py:154-172` (filter) and its docstring (L12-14) |

**Description:** The spec's declared technique (§5.1 matrix row "CSS `direction: rtl` + `unicode-bidi: bidi-override`") pairs a **reversed** string in the HTML text node with CSS that flips it back visually:

> Medium (defeats `textContent`/regex scrapers) · No JS required · High (with `sr-only` pairing)
> — "The reversed string is in the HTML text node, flipped visually by CSS."

Task 3 (L261-262) confirms: "`.bot-username-rtl { direction: rtl; unicode-bidi: bidi-override; }` applied to **reversed** display text".

**The implemented `rtl_obfuscate` filter does neither reversal nor CSS pairing.** It inserts a Unicode Right-to-Left Mark (U+200F) between each character:

```python
# telegram_tags.py:36-39, 154-172
_RTL_MARK: Final[str] = "\u200f"

@register.filter(name="rtl_obfuscate")
def rtl_obfuscate(value: str) -> str:
    """Insert RTL marks between characters to resist scraper extraction.
    …
    Returns:
        A string with ``_RTL_MARK`` inserted between each character.
    """
    if not value:
        return ""
    return _RTL_MARK.join(value)
```

`"\u200f".join("bazuna_bot")` yields `b\u200f a\u200f z\u200f u\u200f n\u200f a\u200f _\u200f b\u200f o\u200f t` — the visible character order is unchanged; only invisible directional-formatting marks are inserted. This is a **different obfuscation strategy** from the spec's reverse-string + `direction: rtl` + `unicode-bidi: bidi-override` approach. Because no string is reversed, applying a would-be `direction: rtl; unicode-bidi: bidi-override` CSS class to this output would visually scramble the letters (the marks do not, by themselves, reorder the visible run into reversed order the way a reversed source string + bidi-override would).

**The module docstring (L12-14) documents the implemented (RTL-mark) technique**, so the code is internally consistent with its own docstring — but it is **inconsistent with the spec** (§5.1, §6.4, Task 3 L261-263), which explicitly names reversal + `direction: rtl; unicode-bidi: bidi-override`.

**Evidence:** `grep "bot-username-rtl|rtl_obfuscate|direction: rtl|bidi-override|reversed" telegram_tags.py` → the string "reversed" appears only in the spec/task docstrings, never in a code comment matching the reversal approach; `"\u200f".join(value)` is the sole transform at `telegram_tags.py:172`.

**Recommendation:** Reconcile the mismatch. Either:

- **(A) Align implementation to spec (preferred):** change `rtl_obfuscate` to reverse the string (`value[::-1]`) so it pairs correctly with the `direction: rtl; unicode-bidi: bidi-override` class on the display element, and update the module docstring (L12-14) + filter docstring (L156-168) to describe reversal, not mark insertion; **or**
- **(B) Align spec to implementation:** document that Block B uses the U+200F-insertion technique instead of reversal+CSS, and adjust Task 3 / §5.1 accordingly — but note R1 (spec §5.14) rates the CSS-RTL technique as "Medium" scraper resistance; the pure RTL-mark technique is weaker (`textContent`/regex scrapers still find the clean contiguous run once marks are stripped) and loses the `sr-only` pairing rationale.

Effort: small (A) / trivial (B). Priority: mandatory to resolve before the class is relied upon; if (A) is chosen, do it together with F-BB-001 (the CSS rule) and F-BB-002 (privacy.html wiring) so the three are consistent.

---

### F-BB-004: Spec references `templates/theme/css/input.css`; actual source is `src/theme/static/theme/css/input.css`

| Field | Value |
|---|---|
| **ID** | F-BB-004 |
| **Severity** | LOW |
| **Type** | DOC-UPDATE |
| **Classification** | advisory |
| **Affected Modules** | `.ai/problems/18_contact-us_spec.md` (L266), `.ai/problems/18_contact-us_spec.md` (L604) |

**Description:** Spec Task 3 (L266) and the Key-Files reference (L604) cite the CSS source as `templates/theme/css/input.css` / `templates/theme/css/input.css`. The actual file on disk is:

```
src/theme/static/theme/css/input.css
```

The current source contents (verbatim):
```css
/* Tailwind input stylesheet */
@import "tailwindcss";
@source "../../../backend/templates/**/*.html";
@source "../../../theme/static/theme/js/**/*.js";
```

It contains **no custom CSS rules**, no `@config`, and there is **no `tailwind.config.js`** / `tailwind.config.ts` anywhere in the repo (Tailwind v4 uses the `@import "tailwindcss"` + `@source` directives as its configuration). Custom utilities like `.bot-username-rtl` must be appended directly in this `input.css`.

**Evidence:** `glob **/tailwind.config.*` → no matches; `glob **/.postcssrc*` / `**/postcss.config.*` → no matches; `input.css` is 4 lines as shown above.

**Recommendation:** Correct the spec paths (L266, L604) to `src/theme/static/theme/css/input.css`. Add the `.bot-username-rtl` rule there (see F-BB-001). Note there is no separate PostCSS config; Tailwind v4 compiles `input.css` → `output.css` via the `@import`/`@source` directives, so any new rule requires a recompile to appear in the served `output.css`.

Effort: trivial. Priority: recommended (prevents implementor editing a phantom path).

---

### F-BB-005: `sr-only` is available in compiled output but is unused by every template

| Field | Value |
|---|---|
| **ID** | F-BB-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Classification** | advisory |
| **Affected Modules** | `src/theme/static/theme/css/output.css`, all templates |

**Description:** The spec (Task 3 L263-264) states "the `sr-only` Tailwind utility is already available." Verification:

- A literal search for `sr-only` in `output.css` returns **1 match** (within the minified compiled blob, L2). This is the `sr-only` core utility selector emitted by Tailwind v4 (the counterpart `not-sr-only` is also typically present). It is a default-on core utility, so it is emitted even though **no template currently references `sr-only`**.
- A repo-wide search for `sr-only` across `src/backend/templates/**/*.html` returns **0 matches** — the utility is available but never used.

**Implication for Block B:** The `sr-only` pairing the spec calls for ("a visually-hidden `sr-only` element containing the clean text for accessibility") is technically available today. Once F-BB-002 is implemented, the implementor can use `<span class="sr-only">@{{ bot_username }}</span>` (or a `rtl_obfuscate`-produced clean counterpart) without any CSS changes.

**Evidence:** `grep literal "sr-only" src/theme/static/theme/css/output.css` → 1 match; `grep -rn "sr-only" src/backend/templates/` → 0 matches.

**Recommendation:** No action required to "make available." Track as a reminder: when implementing the `sr-only` pairing in F-BB-002, keep in mind the spec's pairing intent (clean text for AT, reversed/obfuscated text for visual). Effort: trivial (consumes, not implements). Priority: informational.

---

### F-BB-006: `bot-username-rtl` is already in the `telegram_deep_link` tag's `class_attr`

| Field | Value |
|---|---|
| **ID** | F-BB-006 |
| **Severity** | INFORMATIONAL |
| **Type** | SPEC-DEVIATION (partial) |
| **Classification** | advisory |
| **Affected Modules** | `src/backend/apps/core/templatetags/telegram_tags.py:131` |

**Description:** The partial implementation **did** add `bot-username-rtl` to the rendered class list:

```python
# telegram_tags.py:130-131
# Always include bot-username-rtl for visual obfuscation of the link text.
class_attr = f"js-telegram-link bot-username-rtl {classes}".strip()
```

This satisfies the spec's intent (CR-6: "Visible display text … protected with CSS `direction: rtl`") at the **class-emission** level. However, as F-BB-001 notes, the backing CSS rule does not exist, so the class has no effect. Additionally, on the footer link (`footer.html:10` → `{% telegram_deep_link "contact_us" %}`) the tag's visible text is the translatable label "Contact us", **not** the bot username — so `bot-username-rtl` is present but superfluous there (it would only matter for links whose visible text is the username, which the tag does not emit).

**Evidence:** `footer.html:10` renders `{% telegram_deep_link "contact_us" classes="underline hover:text-gray-800" %}` whose visible text comes from `_LABELS[CONTACT_US]` = `_("Contact us")` (`telegram_tags.py:54`), not from `bot_username`.

**Recommendation:** Keep the class in `class_attr` (it is correct for any future link whose text is the username; it is harmless on label-only links). Define the CSS rule (F-BB-001) so the class is not dead. Effort: trivial (follows F-BB-001). Priority: recommended.

---

## 2. Consent-handling pattern at top of `privacy.html` (L1-25)

The page gates **analytics** (not contact) via two mechanisms, neither of which is a consent gate around contact links:

```html
<!-- privacy.html L1-3: only static + i18n are loaded -->
{% load static %}
{% load i18n %}

<!-- privacy.html L11-15: analytics consent gate (Plausible) -->
{% if consent_analytics and PLAUSIBLE_HOST %}
    <script defer
          data-domain="{{ PLAUSIBLE_HOST }}"
          src="https://{{ PLAUSIBLE_HOST }}/js/script.js"></script>
{% endif %}

<!-- privacy.html L17: body has no dir= attribute (defaults to ltr) -->
<body class="bg-gray-50 min-h-screen">
```

- `consent_analytics` is a context variable (the analytics-consent state). Plausible is loaded **only** when analytics consent is granted **and** `PLAUSIBLE_HOST` is set.
- `PLAUSIBLE_HOST` is a setting (`config/settings/base.py`).
- The document direction is **LTR** (`<html lang="en">` L5; `<body>` L17 has no `dir` attribute). Block B's `direction: rtl` is therefore intended as a **per-element class** (`.bot-username-rtl`), not a document-level `dir="rtl"` — consistent with the spec's "one CSS class" phrasing and Constraint #4.
- The consent banner itself renders at L155-157 (`{% include "components/consent_banner.html" %}`) gated on `not request.user.is_authenticated or not request.user.is_deleted`.
- The JS-execution cookie (`js=true`) is set by the **footer** include (`footer.html:13`), so privacy.html receives it because it includes the footer (L158) — but it is not set *within* privacy.html itself.

---

## 3. Answers to the seven investigation questions

1. **Exact current code at `privacy.html` lines 30, 33, 111, 148?**
   - **L30** — `<a href="https://t.me/{{ bot_username }}"` (cleartext deep-link `href`)
   - **L33** — `rel="noopener noreferrer">@{{ bot_username }}</a>.` (cleartext display text, with `@` prefix, and `@noopener/@noreferrer` link-rel)
   - **L111** — `… via deep-links (<code>t.me/{{ bot_username }}</code>). No ad content is shared…` (cleartext `<code>` legal disclosure, inside a `{% blocktrans %}`)
   - **L148** — `<a href="https://t.me/{{ bot_username }}"` (second cleartext deep-link `href`; its display text is on L151: `rel="noopener noreferrer">@{{ bot_username }}</a>.`)

2. **What does `rtl_obfuscate` do — reverse the string or insert RTL marks?**
   - **Inserts RTL marks.** `rtl_obfuscate` (`telegram_tags.py:154-172`) returns `"\u200f".join(value)` — it joins each character with a Unicode Right-to-Left Mark (U+200F, `_RTL_MARK`, L39). It does **not** reverse the string (`value[::-1]` is never used).

3. **Where is the Tailwind CSS source file? What does it contain?**
   - **Location:** `src/theme/static/theme/css/input.css` (the spec's stated `templates/theme/css/input.css` is a stale path — see F-BB-004).
   - **Contents (4 lines, verbatim):**
     ```css
     /* Tailwind input stylesheet */
     @import "tailwindcss";
     @source "../../../backend/templates/**/*.html";
     @source "../../../theme/static/theme/js/**/*.js";
     ```
     No custom rules, no `@config`, no `tailwind.config.{js,ts}` exists.
   - Compiled output: `src/theme/static/theme/css/output.css` (Tailwind v4.3.3, minified to 2 lines).

4. **Does `.bot-username-rtl` CSS rule exist anywhere?**
   - **No.** Literal `grep "bot-username-rtl"` in `output.css` → 0 matches; in `input.css` → 0 matches. The class name appears only in `telegram_tags.py:130-131` (comment + `class_attr`) and in the spec/doc text. **F-BB-001.**

5. **Is `sr-only` available?**
   - **Yes.** Literal `grep "sr-only" output.css` → 1 match (the core `sr-only` utility, emitted by Tailwind v4). It is a default-on core utility. However, no template currently uses it (F-BB-005).

6. **Is the `bot-username-rtl` class already in the tag's `class_attr`?**
   - **Yes.** `telegram_tags.py:131`: `class_attr = f"js-telegram-link bot-username-rtl {classes}".strip()`. F-BB-006.

7. **Does `privacy.html` load `telegram_tags`?**
   - **No.** `privacy.html` loads only `{% load static %}` (L2) and `{% load i18n %}` (L3). It does **not** `{% load telegram_tags %}`, so the `telegram_deep_link` tag and `rtl_obfuscate` filter are unavailable to it. F-BB-002.

---

## 4. Cross-template context (out of Block-B scope but required for completeness)

The spec Q2=A requires obfuscating **all** bot-username locations. The partial implementation (Block A) only migrated the **footer** (`footer.html:10` now uses `{% telegram_deep_link "contact_us" %}`). The other consumer templates are still cleartext — these belong to Blocks C/E but are recorded here because they share the same missing CSS class:

| Template | Line | Current code | Loads `telegram_tags`? |
|---|---|---|---|
| `components/header_catalog.html` | 33 | `href="https://t.me/{{ bot_username }}?start=create_ad"` (L33) | No (L8-11: i18n/localized_content/static/dict_tags) |
| `ads/detail.html` | 167 | `href="https://t.me/{{ bot_username }}?start=contact_{{ ad.id }}"` (L167) | No |
| `users/login_issue.html` | 21 | `href="{{ deep_link }}"` (L21; pre-built URL from `consent.py:306-307` using `settings.BOT_USERNAME`) | No |
| `privacy.html` | 30/33/111/148/151 | cleartext `{{ bot_username }}` | No |

`footer.html` is the **only** template that migrated (loads `{% load telegram_tags %}` at L3; uses the tag at L10). `header_catalog.html`, `detail.html`, `login_issue.html`, and `privacy.html` still carry cleartext/empty usernames — the residual F-BU-001/F-BU-002 consumers from Block 1.

---

## 5. Summary

| Severity | Count | Findings |
|----------|-------|----------|
| CRITICAL | 0 | — |
| HIGH | 2 | F-BB-001 (CSS rule missing), F-BB-002 (privacy.html not migrated) |
| MEDIUM | 1 | F-BB-003 (filter technique diverges from spec) |
| LOW | 2 | F-BB-004 (spec path mismatch), F-BB-005 (sr-only unused) |
| INFORMATIONAL | 1 | F-BB-006 (bot-username-rtl already in class_attr) |

## Mandatory Fixes

- **F-BB-001** — Define `.bot-username-rtl { direction: rtl; unicode-bidi: bidi-override; }` in `src/theme/static/theme/css/input.css`; recompile to `output.css`.
- **F-BB-002** — Migrate `privacy.html` display-text (L33/L111/L151) to the RTL-reversal + `sr-only` pairing; migrate hrefs (L30/L148) to `{% telegram_deep_link %}` (requires `{% load telegram_tags %}`); migrate `views.py:37` from `settings.BOT_USERNAME` → `get_bot_username()`.
- **F-BB-003** — Reconcile the `rtl_obfuscate` filter: either make it reverse the string (to pair with the CSS class, preferred) or update the spec/§5.1 to document the U+200F-insertion technique. Cannot leave the two approaches inconsistent.

## Advisory Recommendations

- **F-BB-004** — Correct the spec CSS-source path (`templates/theme/css/input.css` → `src/theme/static/theme/css/input.css`).
- **F-BB-005** — `sr-only` is available but unused; ensure the F-BB-002 rewrite actually pairs a visually-hidden `sr-only` element for screen-reader correctness.
- **F-BB-006** — Keep `bot-username-rtl` in `class_attr`; pair it (F-BB-001) so it is not a dead class.
- Cross-block: complete F-BU-001/F-BU-002 (Block 1) consumer migration in `header_catalog.html`, `detail.html`, `login_issue.html` — these still read `settings.BOT_USERNAME` / cleartext `{{ bot_username }}` and would silently bypass any per-view obfuscation fix.

## Doc Updates Needed

- F-BB-003 — Reconcile `telegram_tags.py` module docstring (L12-14) and filter docstring (L156-168) with whichever technique is standardized.
- F-BB-004 — Fix spec paths in `.ai/problems/18_contact-us_spec.md` (L266, L604).

---

## Template Field Reference

| Field | Value |
|---|---|
| id | F-BB-001 … F-BB-006 |
| severity | HIGH / MEDIUM / LOW / INFORMATIONAL |
| type | SPEC-DEVIATION / BEST-PRACTICE / DOC-UPDATE |
| classification | mandatory (F-BB-001/002/003) / advisory (F-BB-004/005/006) |
| affected_modules | `src/theme/static/theme/css/*`, `src/backend/templates/privacy.html`, `src/backend/apps/core/templatetags/telegram_tags.py`, `src/backend/templates/components/footer.html`, `src/backend/apps/core/views.py` |

## Files read in full for this block (audit trail)

| File | Purpose |
|---|---|
| `src/backend/templates/privacy.html` (160 lines) | The 4 target lines + consent gate (§2) |
| `src/backend/apps/core/templatetags/telegram_tags.py` (172 lines) | `rtl_obfuscate` filter + `telegram_deep_link` tag + `class_attr` |
| `src/theme/static/theme/css/input.css` (4 lines) | Tailwind v4 source — confirms no custom rules |
| `src/theme/static/theme/css/output.css` (2 lines, minified) | Compiled output — confirms `.bot-username-rtl` absent, `sr-only` present |
| `src/backend/templates/components/footer.html` (14 lines) | Block A reference: only template migrated; loads `telegram_tags`, uses tag |
| `src/backend/apps/core/tests/test_footer_contact_link.py` (155 lines) | Establishes "Spec 18 Block A" naming convention |
| `src/backend/apps/core/views.py` (75 lines) | `privacy_policy()` still passes `settings.BOT_USERNAME` (L37) |
| `src/backend/apps/core/context_processors.py` (139 lines) | `header_context` still returns `settings.BOT_USERNAME` (L91) |
| `src/backend/apps/core/services/site_config.py` (71 lines) | `get_bot_username()`/`get_bot_username_async()` exist (Task 1, Block 1) |
| `src/backend/apps/core/templatetags/dict_tags.py` (81 lines) | Reference tag-registration style |
| `src/backend/templates/components/header_catalog.html` (674 lines) | Still cleartext `{{ bot_username }}` (L33) |
| `src/backend/templates/ads/detail.html` (grep) | Still cleartext `{{ bot_username }}` (L167) |
| `src/backend/templates/users/login_issue.html` (grep) | Still cleartext `{{ deep_link }}` (L21) |
| `.ai/problems/18_contact-us_spec.md` (645 lines) | Spec §5.1, Task 3, CR-6/CR-9, Constraint #4, A2 |
| `.ai/audit/11-bot-username-migration/findings.md` (656 lines) | Block 1 context: F-BU-001/002 consumers + `telegram_deep_link` was previously absent |
| `.ai/audit/11-bot-username-migration/block-03-web-rate-limit-pattern.md` (504 lines) | Block 3 reference for block-file naming convention |
