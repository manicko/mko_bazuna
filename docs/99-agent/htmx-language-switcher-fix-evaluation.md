# Evaluation — Fixing Language Switcher Staleness After HTMX Swaps

**Date:** 2026-09-03
**Prerequisite:** Read `htmx-swap-language-switcher-audit.md` first. This document evaluates remediation approaches against the confirmed architecture.

---

## 1. HTMX Lifecycle Hook — Which Event?

Per the HTMX 2.0 source and docs (verified via Context7), the relevant events, in firing order, are:

| Event | Fires when | Detail payload | Suitable here? |
|---|---|---|---|
| `htmx:pushedIntoHistory` | *after* `history.pushState()` (triggered by `hx-push-url="true"`), **before** the DOM swap | `{ path }` | **Most surgical** — fires only when the URL bar actually changes. |
| `htmx:afterSwap` | **after** new content is swapped into the target | `elt`, `xhr`, `target`, `requestConfig` | **Recommended** — fires after swap; URL already updated (pushState runs at `doSwap` start, before swap). |
| `htmx:afterSettle` | after swap + settle (CSS transitions done) | same as afterSwap | Overkill — no transitions in this swap (`innerHTML`). |
| `htmx:afterRequest` | after the XHR completes (before swap) | `elt`, `xhr`, `target`, `successful`, `failed` | **Not suitable** — too early; but `window.location.search` is *already* updated by the time afterRequest fires, because `pushUrlIntoHistory` runs at the start of `doSwap`. |
| `htmx:configRequest` | *before* the request is sent — mutates outgoing params/headers | `parameters`, `headers` | **Wrong layer** — this is for shaping the *outgoing* request, not reacting to the *response/URL*. Does not help. |
| Response headers (`HX-Push-Url` / `HX-Replace-Url`) | server can override push/replace URL | — | **Not applicable** — controls the URL bar only; cannot instruct the client to refresh a non-targeted fragment. |

### Ordering guarantee (verified from `htmx.js` `beforeSwapCallback`)

```
1. pushUrlIntoHistory(path)  -> history.pushState  -> URL bar UPDATED
2. trigger('htmx:pushedIntoHistory', { path })
3. ...content swapped into target...
4. trigger('htmx:afterSwap', { target, elt, xhr })
5. trigger('htmx:afterSettle', ...)
```

**Conclusion:** By the time `htmx:afterSwap` fires, **`window.location.search` already reflects the swapped URL** (pushState happened in step 1). This makes `htmx:afterSwap` the right hook to recompute the language-switcher links from the *live* URL. It is also the event the codebase already listens to (`header_catalog.html` L609 `window.addEventListener('htmx:afterSwap', …)`), so using it is consistent with existing conventions.

> `htmx:pushedIntoHistory` is a more surgical alternative (fires only on push, not on pure innerHTML swaps without `hx-push-url`). Since all 9 links in this project use `hx-push-url="true"` (asserted by `test_all_htmx_links_have_push_url`), both events co-fire. **`htmx:afterSwap` is recommended** for consistency; `htmx:pushedIntoHistory` is acceptable if you want to skip work on non-push swaps.

---

## 2. Approach A — Move `language_switcher.html` into the `#ad-list` swap target

**Verdict: REJECTED.** (Also rejected by the auditor for the same reasons.)

- **Structural incoherence:** The switcher lives in the header's top-right corner (brand | place-an-ad | lang). The `#ad-list` div is the ad-grid/filter region *inside* `<main>`. Moving the switcher into `#ad-list` would relocate a header UI element into the content stream — a visual/logical break on every catalog page.
- **Shared component / detail asymmetry:** `header_catalog.html` is included in *both* `list.html` (has `#ad-list` + HTMX swaps) and `detail.html` L28 (no `#ad-list`, no swaps). A "move switcher into swap target" change only makes sense on `list.html`, forcing the two templates to diverge.
- **Heavy re-render per swap:** Even moving *only the whole header* into the target would re-run the MPTT `root_categories` query, the `cities` query, and the favorites count on every filter/pagination change (all via context processors firing on every `render()`), plus re-execute the ~400-line inline IIFE in `header_catalog.html` (L216–L614) — wiping open dropdowns/accordions/mobile-panel state on every swap. The auditor flagged this (Finding 1, "Approach A — higher risk").
- **`cabinet/favorites.html` uses a different header (`header.html`) and target (`#favorites-list`)** — Approach A would need a parallel, inconsistent change there.

**Not viable.**

---

## 3. Approach B — Client-side `htmx:afterSwap` listener that recomputes switcher `href`s

**Verdict: RECOMMENDED primary fix.** (Lowest risk, comprehensive, idiomatic.)

### 3.1 How it works

Add a small listener inside the `language_switcher.html` IIFE (L43–L126 — which already runs once on full load and attaches the dropdown-toggle listeners). Because the header is never re-rendered on HTMX swaps, the listener is registered exactly once and persists across swaps (no duplicates). After each swap, it re-reads `window.location.search` (already current) and rewrites each `[data-lang-switcher-link]` href.

### 3.2 Reference implementation (~15 lines)

```javascript
// Inside the language_switcher.html IIFE.
// Recompute language links from the *live* URL after HTMX swaps, since
// the header is outside the #ad-list swap target and is never re-rendered.
document.body.addEventListener('htmx:afterSwap', function () {
    var links = document.querySelectorAll('[data-lang-switcher-link]');
    if (!links.length) return;              // not on a page with a switcher
    var params = new URLSearchParams(window.location.search);
    params.delete('page');                  // reset pagination when switching language
    var base = params.toString();
    links.forEach(function (link) {
        var rebuilt = new URLSearchParams(base);
        rebuilt.set('lang', link.getAttribute('data-lang'));
        link.setAttribute('href', '?' + rebuilt.toString());
    });
});
```

### 3.3 Why this is correct

| Concern | Resolution |
|---|---|
| **Frozen `request.GET` snapshot** | Solved — reads `window.location.search`, which `hx-push-url="true"` updates *before* `afterSwap` fires (verified from `htmx.js` push-state ordering). |
| **Multi-value params (`features=a&features=b`)** | `URLSearchParams` preserves duplicate entries through `.toString()`. |
| **Empty query (homepage `/`)** | `new URLSearchParams("")` → `""` → link = `?lang=en`. Matches `query_replace` on empty input. |
| **URL-encoding of `q` / special chars** | `URLSearchParams.toString()` percent-encodes identically to `QuerySet.urlencode()`. |
| **`page` leakage (the secondary issue)** | Explicit `params.delete('page')` resets pagination on language switch. |
| **No duplicate listeners** | Header (incl. the switcher script) is never re-rendered on swap → listener registered once. (This is the *same* property the staleness bug relies on; the fix exploits it, not fights it.) |
| **Progressive enhancement** | The switcher dropdown *already* requires JS (`language_switcher.html` L43–126 toggles the menu). Adding a post-swap hook does not introduce a new hard-JS dependency — the component is already JS-dependent. Server-rendered links are correct on load; they go stale only *between* swaps, which the hook corrects. |

### 3.4 What it fixes (and what it does not need to)

- **Primary bug (frozen non-`lang` params after swap):** FIXED — links recomputed from the live URL.
- **Secondary bug (`page` carried to language link):** FIXED — explicit `params.delete('page')`.
- **No server/DB changes, no view changes, no test changes** — the existing `query_replace` tests remain valid because the tag is left untouched.

**Risk: LOW.** ~15 lines of self-contained JS, idiomatic, no blast radius beyond the selector `[data-lang-switcher-link]`, no server-side changes.

---

## 4. Approach C — Strip `page` from `query_replace`

**Verdict: NOT a standalone fix. REJECTED as the primary mechanism, but the *intent* (drop `page`) is correct.**

- **Blast radius:** `query_replace` has exactly **one** production call-site — `language_switcher.html` L35, always invoked as `query_replace request lang=language.code`. So changing it would only affect the switcher. This is actually a point *in favor* of C being safe to use as a *complement*.
- **Why it's insufficient alone:** `query_replace` snapshots `request.GET` at *render time*. On the full page load, `request.GET` is current and correct — but the staleness arises *after* HTMX swaps, when `request.GET` is never re-snapshotted (the header isn't re-rendered). Stripping `page` in `query_replace` prevents page-leakage at **initial render**, but does nothing for the **post-swap frozen `features`/`sort`/`q`** staleness. C ≠ a staleness fix.
- **Why it would break tests:** `test_preserves_multiple_params` (`test_templates.py` L119–L125) explicitly asserts that `query_replace("q=phone&page=2&sort=price", lang="bs")` preserves `page=2`. Changing the tag to drop `page` breaks this test — and for no benefit, because `query_replace` is a *general-purpose* "copy + override" utility. Dropping `page` is a *switcher-specific* policy that does not belong in a generic tag.
- **Better home for the `page` policy:** Approach B's JS (§3.2) already handles `params.delete('page')` at the correct layer — the consumer that knows language should reset pagination.

**Conclusion:** Leave `query_replace` unchanged. Implement the `page` policy in the switcher (Approach B). If a server-side `page` policy is ever needed, add a dedicated tag (e.g. `switcher_url`) rather than overloading `query_replace`.

---

## 5. Approach D — Server-side OOB swap (`hx-swap-oob`)

**Verdict: VIABLE alternative, but higher friction than B. Consider only if server-side source-of-truth for links is a hard requirement.**

This is the idiomatic HTMX pattern for "update an element outside the primary swap target." HTMX 2.0 supports it via `hx-swap-oob="true"` (matches by ID) or `hx-swap-oob="<strategy>:<selector>"` (verified from `hx-swap-oob.md` and `hx-select-oob.md`).

### 5.1 How it would work here

The language switcher root div already has `id="lang-switcher"` (`language_switcher.html` L13). On HTMX swap requests, the served `ad_list.html` fragment would include an OOB payload that re-renders the switcher:

```html
<!-- trailing OOB payload inside ad_list.html -->
<div id="lang-switcher" hx-swap-oob="innerHTML">
    {% include "components/language_switcher.html" %}
</div>
```

HTMX would swap the *main* `ad_list.html` content into `#ad-list` (primary target) and the OOB div's content into the existing `#lang-switcher` — re-running `query_replace` against the *fresh* post-swap `request.GET`.

### 5.2 Friction / risks

| Issue | Explanation |
|---|---|
| **Nested `#lang-switcher` ID** | `language_switcher.html` itself wraps its content in `<div id="lang-switcher" …>` (L13). An OOB wrapper `<div id="lang-switcher" hx-swap-oob="innerHTML">` containing a *second* `#lang-switcher` is duplicate-ID HTML → ambiguous target matching. Would require splitting the switcher into an inner fragment (links + dropdown) and a separate script, or restructuring. |
| **Script re-execution per swap** | `language_switcher.html` ships its own `<script>` (L43–L126). An OOB `innerHTML` or `outerHTML` re-render would re-insert and re-run that script on every filter/pagination change — re-attaching toggle listeners each time. Wasteful, though not broken (listeners are on the fresh element). |
| **Context-processor cost** | Every `render()` re-runs context processors. The HTMX branch already renders `ad_list.html` (heavy: `header_context` runs `root_categories` MPTT + `cities` + `favorites`). Adding an OOB re-render of the switcher adds a *second* full context-processor pass per swap unless the OOB fragment is rendered as part of the same `ad_list.html` response (then the extra IDs/structure problem above remains). |
| **View changes** | Requires touching the HTMX branches of `listings.py`, `search.py`, and (for parity) `favorites.py`, plus editing `ad_list.html` to emit the OOB payload. |

### 5.3 When D is worth it

If the project adopts a strict "no client-side URL construction; the server is the only source of truth for query strings" rule, D is the correct pattern. But today the project already leans **client-side** for URL manipulation (e.g., the search-clear handler in `header_catalog.html` L246–260 builds `URLSearchParams` from `window.location.search`; the chip/pagination links are hand-built in templates). Approach B matches that existing posture.

**Net:** D is viable but strictly heavier than B. Document as the fallback if server-authoritative links are mandated.

---

## 6. Recommendation

| Rank | Approach | Verdict |
|---|---|---|
| **1 (primary)** | **B** — `htmx:afterSwap` listener recomputing `[data-lang-switcher-link]` hrefs from `window.location.search`, dropping `page` | **Recommended.** ~15 lines, no server/DB/view/test changes, matches existing client-side URL posture and the existing `htmx:afterSwap` convention (L609). Fixes both the primary staleness and the `page` leakage. |
| 2 (alternative) | D — OOB swap of `#lang-switcher` in the `ad_list.html` HTMX response | Viable if server-side query-string authority is required. Higher friction (nested IDs, script re-exec, context-processor cost, 3 view edits). |
| 3 (complement only) | C — strip `page` inside `query_replace` | **Do not** overload the general-purpose tag. The `page` policy belongs in the consumer (B's `params.delete('page')`). |
| — (out) | A — move switcher into `#ad-list` | Rejected: structurally incoherent, breaks `detail.html` symmetry, heavy re-render + state loss. |

### Final directive to the Implementor

Implement **Approach B**: add the `htmx:afterSwap` listener (§3.2) to the `language_switcher.html` script block. Do **not** touch `ad_list.html`, `header_catalog.html`, `query_replace`, or any view. The existing `test_all_htmx_links_have_push_url` and `test_lang_param_in_all_htmx_urls` static-template tests continue to pass unchanged (they assert on the server-rendered partial), and the staleness is corrected at runtime.

### Second verification pass required?

**Yes — flag for re-review.** Two standalone, viable approaches exist for the *primary* fix: **B (client-side recompute)** and **D (server-side OOB)**. They represent a genuine architectural fork (client-authored URLs vs. server-authoritative URLs). The choice affects whether any server template/view contracts change. A second pass should confirm which paradigm the maintainers prefer before committing to B, since retrofitting D later means removing the JS hook and adding view/OOB changes. If server-authority is non-negotiable, D must be built instead — and then Approach B's JS must be deleted.

---

## 7. Appendix — Hook placement and edge cases

- **Placement:** Inside the existing IIFE in `language_switcher.html` (L43–L126), after the dropdown/cookie listeners. It reads `[data-lang-switcher-link]` (already emitted by the template at L38), so no template attribute changes are needed.
- **`consent_preferences` gating (L102):** The cookie is only set when `consent_preferences` is truthy. This is orthogonal to the swap fix — language *switching* still works via `?lang=` (middleware priority #1) regardless of cookie state. The hook only fixes *link freshness*, not cookie consent.
- **Non-HTMX navigations:** On a full reload (e.g. clicking a language link), the server re-renders the header with correct links; the hook is a no-op until the next swap. No conflict.
- **Pages without `#ad-list` (detail, dashboards):** `htmx:afterSwap` fires, `querySelectorAll('[data-lang-switcher-link]')` returns matches only if the switcher is present; on pages with no active HTMX swap of `#ad-list` the handler is inert. Safe.

---

## Resolution Status (post-implementation)

**Implemented:** Approach **B** (chosen, not the open question this doc treated as pending).
`components/language_switcher.html` contains the `htmx:afterSwap` listener with selector
`[data-lang-switcher-link]` that recomputes `href`s from `window.location.search` and drops
`page` — the exact pattern recommended in §3.2 and §6. The header was **not** moved into
`#ad-list` (the `list.html` include remains outside the swap target). The §6 "Second
verification pass required?" (L164) is closed to **N/A — decision made**: Approach B is
deployed; Approach D was not built, so the JS hook needs no removal. This document is
retained as the pre-implementation rationale record.
