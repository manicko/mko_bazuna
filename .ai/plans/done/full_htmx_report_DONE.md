# HTMX 1.9.12 → 2.x Compatibility Audit — Consolidated Report

**Project:** Mko Bazuna (Django 5.2 LTS / Python 3.14 / PostgreSQL 18 / HTMX MPA, gunicorn WSGI + HTMX-driven templates)
**Subject:** Upgrade feasibility, risk, and migration plan for the frontend HTMX library from **1.9.12** to **2.0.10**.
**Note:** Read-only analysis. No repository files were modified.

---

## 1. Executive summary (corrected facts)

Mko Bazuna loads HTMX **1.9.12** from the **unpkg CDN** across **5 standalone page templates**, with **zero** HTMX extensions and **7 distinct `hx-*` attributes**. The upgrade to HTMX **2.0.10** is **low effort / low risk at the attribute layer**: every attribute and event the project uses (`hx-get`, `hx-post`, `hx-target`, `hx-swap`, `hx-push-url`, `hx-headers`, `hx-trigger`, `htmx:afterRequest`, `htmx:afterSwap`) is preserved verbatim in 2.x.

The audit's decisive finding is a **pre-existing production bug the version bump does *not* repair**:

- **`components/header_catalog.html:536`** calls **`htmx.get(...)`**, which is **not a real HTMX API in 1.9.12 *or* 2.0.10**. On catalog (`ads/list.html`) and ad-detail (`ads/detail.html`) pages — the only pages including `header_catalog.html` — each favorite toggle dispatches `favorite:toggled`, reaches line 536, and throws `TypeError: htmx.get is not a function`; the header favorites-count badge never refreshes. It was already broken in production under 1.9.12; a naive CDN bump to 2.x leaves it broken.

The single required code change is one line: `htmx.get(url, { target, swap })` → **`htmx.ajax('GET', url, { target, swap })`** — the exact pattern already used at `cabinet/favorites.html:47`.

Two widespread misconceptions — one embedded in internal planning docs — are corrected by verbatim source inspection: (1) **`htmx.ajax()` was NOT removed in 2.x** (`htmx.ajax = ajaxHelper` in the 2.0.10 source, documented at `htmx.org/api/`); (2) **`htmx.get()`/`htmx.post()` were NOT introduced in 2.0`** — they do not exist in HTMX core in *any* version (likely confused with the `hx-get`/`hx-post` attributes or the `htmx.ajax('GET', …)` shorthand).

**Verdict:** One change bundles the upgrade and the fix — bump 5 CDN tags to `@2.0.10` (hardened with jsDelivr+SRI) and change line 536 to `htmx.ajax`. **Effort: S.** No dual-versioning, feature flag, or `htmx-1-compat` shim. PO-5=B stands, **but must be paired** with the call-site fix; the internal notes' premise that "the upgrade fixes `htmx.get`" is disproven.

---

## 2. Audit provenance & methodology

This report merges **two independent audits** (`1_htmx_report.md`, `2_htmx_report.md`), each performed against the **verbatim HTMX library sources** fetched from the same `unpkg.com/htmx.org` CDN the project uses, plus the **official documentation** (JS API reference, 1.x→2.x migration guide, 2.0 release notes). Where the two agree → independent corroboration; where they disagree → each claim was **re-checked against authoritative sources** (§16) and **resolved** (§3).

Both auditors used: (a) repo-wide inventory of every `<script>` load, `htmx.*` call site, `hx-*` attribute, and extension; (b) fetching `htmx.org@1.9.12/dist/htmx.js` and `htmx.org@2.0.10/dist/htmx.js` (`@latest`) and grepping their public-API object, `responseInfo` detail, config defaults, dispatched event literals, and attribute parsers; (c) cross-checking against `https://htmx.org/api/` and the migration guide; (d) a runtime baseline — **41 tests passed**, no code changes.

For this consolidation I added: live inspection of the repo templates and settings, a repo-wide `grep` of every attribute/API token, and a query of the official HTMX docs (Context7) for install/SRI/`htmx-1-compat`/`swap` guidance.

---

## 3. Discrepancy log (D1–D6, resolved)

| # | Discrepancy | Auditor #1 | Auditor #2 | Resolution (authoritative) | Confidence |
|---|---|---|---|---|---|
| D1 | `htmx.get`/`htmx.post` existence & classification | not-a-real-API; latent `TypeError` bug | not-a-real-API; latent `TypeError` bug | ✅ **Both right.** No `get/post/put/patch/delete` in the public API object of 1.9.12 or 2.0.10 (0 literals in source; absent from `htmx.org/api/`). `header_catalog.html:536` is a **pre-existing bug**, not a 2.x break. | Very High |
| D2 | `htmx.ajax` preserved in 2.x | ✅ preserved (`htmx.ajax = ajaxHelper`) | ✅ preserved (`ajaxHelper(verb, path, context)`) | ✅ **Both right.** `htmx.ajax` is the native 2.x API; `htmx.ajaxRemoved()` does not exist (0 matches). `favorites.html:47` needs no change. | Very High |
| D3 | `hx-on` in 1.9.12 | ❌ marks absent in matrix | ✅ present (1.9.12 source L1953–1954, L1989, L2064) | ✅ **Auditor #2 correct.** `hx-on` is a *handled* 1.9.12 attribute; 2.x renamed it to `hx-on:<event>`. Repo uses **neither** → no impact. In-repo comments `header_catalog.html:4`, `favorite_heart.html:29–30`, and `test_favorites.py:95` docstring ("HTMX 1.9.12 has no hx-on") are **factually wrong**. | Very High |
| D4 | `htmx.swap()` signature | `(target, content, swapSpec, swapOptions)` (4) | `(target, content, swapSpec)` (3) | ✅ **Auditor #2** matches the official 2.x API + migration guide: `htmx.swap(target, content, swapSpec)` (example: `api.swap(target, content, swapSpec)`). Not used by repo. | High |
| D5 | Test methodology | surveyed test files only | ran 41-test baseline (green) | ✅ **Complementary, not contradictory.** Tests assert template *source strings* (`hx-get`, `hx-swap="none"`, `htmx:afterRequest`, absence of `hx-on`), not browser JS; 41 pass; cannot catch the `htmx.get` `TypeError`. | Medium |
| D6 | SRI / CDN hardening | recommends jsDelivr+SRI | recommends jsDelivr+SRI | ✅ **Both right; verified.** Official install docs publish jsDelivr CDN tags **with** SRI for 2.0.10. Exact hashes: §14. | High |

**Attribute-count reconciliation (live grep, not a D-item):** Auditor #2's `hx-post` row labels "5×" while listing 4 locations — **over-count**; verified count = **4**. Auditor #1's `hx-target` row states 14 but lists 15 locations (line numbers offset −1; `hx-target` shares a line with `hx-push-url`/`hx-swap` *following* `hx-get`) — verified count = **15**. Verified total = **60** real instances (see §6).

---

## 4. HTMX version & loading mechanism

- **Version:** `1.9.12` (source `version: "1.9.12"`); `unpkg @latest` = **`2.0.10`** (`version: '2.0.10'`).
- **Loading:** 5 identical `<script src="https://unpkg.com/htmx.org@1.9.12">` tags — UMD/global, **no** `integrity`/`crossorigin`. HTMX is not a package dependency; `pyproject.toml:21` declares only the **server-side** `django-htmx>=1.19.0` (v1.28.0).
- **Templates:** `ads/list.html:16`, `ads/detail.html:20`, `cabinet/hub.html:14`, `cabinet/saved_searches.html:15`, `cabinet/favorites.html:16`.
- **Include graph:** `header_catalog.html` (the broken call-site file) is included **only** by `ads/list.html:20` and `ads/detail.html:24`; cabinet pages use `components/header.html` (a different header) and never render the bug.
- **CSRF:** `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` on `<body>` in `ads/list.html:19`, `ads/detail.html:23`, `cabinet/favorites.html:19`, `cabinet/hub.html:17`. `cabinet/saved_searches.html:17` omits it (pre-existing, unrelated to 2.x).
- **Transport:** Both versions use `XMLHttpRequest` internally; 2.x still sends `HX-Request: true` (L3315, L3699) → `django-htmx` is version-independent.

---

## 5. HTMX JavaScript API inventory

Repo-wide grep finds **exactly two `htmx.*` call sites** (all interaction is inline in templates; no static `.js` references HTMX).

### 5.1 Call sites (complete)

| # | File:line | API | Usage | 1.9.12 | 2.x | Migration? |
|---|---|---|---|---|---|---|
| 1 | `cabinet/favorites.html:47` | `htmx.ajax` | `htmx.ajax('GET', url, { target:'#favorites-list', swap:'innerHTML' })` | ✅ (`ajaxHelper`) | ✅ (`ajaxHelper(verb,path,context)`, L4059; `htmx.ajax=ajaxHelper` L307) | No |
| 2 | `components/header_catalog.html:536` | `htmx.get` | `htmx.get(url, { target:badge, swap:'outerHTML' })` | ❌ not an API | ❌ not an API | **Yes** — change to `htmx.ajax('GET', url, …)` |

Call site #2 context (`header_catalog.html:531–540`, verified):
```js
document.addEventListener('favorite:toggled', function () {
    if (typeof htmx === 'undefined') return;          // L533
    var badge = document.querySelector('[data-favorites-badge]');
    if (!badge) return;
    htmx.get('{% url "cabinet:favorites_count" %}', { // ← L536: NOT a valid HTMX API
        target: badge, swap: 'outerHTML'
    });
});
```
`[data-favorites-badge]` renders on catalog/detail pages via `header_favorites_badge.html:2` (included at `header_catalog.html:28`), so the handler body executes and throws.

### 5.2 Event listeners / guards (DOM `addEventListener` on HTMX CustomEvents — not `htmx.on()`)

| File:line | Listener | 1.9.12 dispatch | 2.x dispatch | Migration? |
|---|---|---|---|---|
| `header_catalog.html:244` | `htmx:afterRequest`; reads `e.detail.target`, `e.detail.xhr` | L3334 | L4581 (still has `xhr`+`target`) | No |
| `header_catalog.html:544` | `htmx:afterSwap`; reads `e.target` | L3652 | L1982 (bubbles, composed) | No |
| `favorite_heart.html:34` | `htmx:afterRequest` → dispatches repo `favorite:toggled` | same | same | No |
| `header_catalog.html:533` | `typeof htmx === 'undefined'` guard | — | — | No |

Event names are **camelCase in both versions** (a grep for kebab forms like `'htmx:after-request'` in the 2.0.10 source → 0 matches). The kebab-case rule applies **only** to the `hx-on:<event>` *attribute syntax*. The `responseInfo` still carries `xhr` + `target` and transport stays XHR, so `detail.xhr.status` remains valid.

### 5.3 APIs searched and **not used**

`htmx.get/post/put/patch/delete`, `htmx.extend` (pre-0.4 alias of `defineExtension`), `htmx.swap`/`htmx.location` (new 2.x), `htmx.trigger/process/find/findAll/closest/values/remove`, `htmx.addClass/removeClass/toggleClass/takeClass`, `htmx.on/off/onLoad`, `htmx.defineExtension/removeExtension`, `htmx.logger/logAll/logNone/parseInterval`, `htmx.config` (never *set*). All confirmed absent by repo-wide grep.

---

## 6. HTMX template attribute inventory (verified counts + lines)

7 attributes, **0 requiring migration**. Counts are exact occurrences (real attributes, excluding 2 comment-only mentions).

| Attribute | Count | Locations | 2.x |
|---|---|---|---|
| `hx-get` | 11 | `ad_list.html:42,54,65,72,143,147,157,165,169` (9) · `filter_form.html:6` · `header_catalog.html:121` | ✅ |
| `hx-post` | 4 | `favorite_heart.html:6` · `saved_search_row.html:33,48` · `save_search_modal.html:14` | ✅ |
| `hx-target` | 15 | `ad_list.html:43,55,66,73,144,148,158,166,170` (9) · `filter_form.html:7` · `header_catalog.html:123` · `favorite_heart.html:7`(`closest form`) · `save_search_modal.html:15` · `saved_search_row.html:34,49` | ✅ (`closest` preserved L1170) |
| `hx-swap` | 15 | `ad_list.html`×9(`innerHTML`) · `filter_form.html:8` · `header_catalog.html:124`(`none`) · `favorite_heart.html:8` · `saved_search_row.html:35,50` · `save_search_modal.html:16` | ✅ (`none` L1801) |
| `hx-push-url` | 10 | `ad_list.html`×9 · `filter_form.html:9` | ✅ |
| `hx-headers` | 4 | `list.html:19` · `detail.html:23` · `favorites.html:19` · `hub.html:17` | ✅ (L3705) |
| `hx-trigger` | 1 | `header_catalog.html:122` (`input delay:300ms`) | ✅ |
| **Real total** | **60** | + 2 comment-only (`header_catalog.html:4` "hx-on"; `save_search_modal.html:3` "hx-get") | |

Attributes **not used** (0 each): `hx-put/patch/delete/boost/confirm/sync/include/vals/select/select-oob/swap-oob/replace-url/indicator/disabled-elt/preserve/history/history-elt/disinherit/inherit/encoding/ext`, `data-hx-*` aliases, and `hx-on*`/`hx-on:`.

**Attribute compatibility verdict:** all 7 in use are 1:1 preserved; `hx-swap="none"`, `hx-target="closest form"`, `hx-target="#…"`, and `hx-trigger="input delay:300ms"` all behave identically in 2.x.

---

## 7. Extension inventory

| Extension | Present? | 1.9 | 2.x | Upgrade? | Evidence |
|---|---|---|---|---|---|
| `hx-ext` (any) | No | n/a | n/a | No | 0 matches |
| `htmx.defineExtension` (custom) | No | n/a | n/a | No | 0 matches |
| WebSocket (`hx-ws`) | No | removed 2.x | — | No | 0 matches |
| SSE (`hx-sse`) | No | n/a | n/a | No | 0 matches |
| `response-targets`/`morphing`/`alpine` | No | n/a | n/a | No | 0 matches |
| `htmx-1-compat` shim | Not installed | n/a | available | No (see §14) | — |

Only note: the **server-side** `django-htmx` v1.28.0 is in `INSTALLED_APPS` (`base.py:91`) but `HTMXMiddleware` is **not** in `MIDDLEWARE` (lines 113–124) and 0 tags/`request.htmx` usage exist — installed but unwired. HTMX 2.x still sends `HX-Request: true` → the frontend upgrade is independent of `django-htmx`.

---

## 8. HTMX 1.9 → 2.x compatibility matrix (corrected)

### 8.1 Public JavaScript API

| Member | 1.9.12 | 2.0.10 | Change? | Used? |
|---|---|---|---|---|
| `ajax` | ✅ (`ajaxHelper`) | ✅ (`htmx.ajax = ajaxHelper`, L307; `ajaxHelper(verb,path,context)` L4059) | No | ✅ `favorites.html:47` |
| `get/post/put/patch/delete` | ❌ (0 literals) | ❌ (0 literals) | never existed | ❌ `htmx.get` @ `header_catalog.html:536` (bug) |
| `swap` | ❌ (internal) | ✅ NEW (L316) | new | ❌ none |
| `location` | ❌ (internal) | ✅ NEW (2.x) | new | ❌ none |
| `on/off/onLoad/trigger/find/findAll/closest/values/remove` | ✅ | ✅ | No | ❌ none used |
| `addClass/removeClass/toggleClass/takeClass` | ✅ | ✅ | No | ❌ none |
| `defineExtension/removeExtension/logger/config/parseInterval/createEventSource/createWebSocket/_/version` | ✅ | ✅ | No (config defaults drift — see 8.2) | ❌ none set |

### 8.2 `htmx.config` defaults (repo never sets `htmx.config`)

| Key | 1.9.12 | 2.0.10 | Changed? | Impact on this repo |
|---|---|---|---|---|
| `scrollBehavior` | `'smooth'` (L72) | `'instant'` (L211) | ✅ | **None** — only the `show`/`transition` swap modifiers + `scrollIntoView`; repo uses neither. |
| `methodsThatUseUrlParams` | `["get"]` (L76) | `["get","delete"]` (L235) | ✅ | **None** — only changes DELETE body-vs-params; repo uses no `hx-delete`; GET→params/POST→body identical. |
| `selfRequestsOnly` | `false` (L77) | `true` (L241) | ✅ | **None** — only blocks cross-origin; all targets same-origin (`{% url %}`/`?page=…`). |
| NEW 2.x keys (`disableInheritance`, `responseHandling`, `allowNestedOobSwaps`, …) | absent | present | new | None — repo sets none. |
| `allowEval`/`allowScriptTags`/`defaultSwapStyle` | `true`/`true`/`innerHTML` | same | no | None |

**Bottom line:** the three migrated defaults are behaviorally inert for this app → **no `htmx.config` override and no `htmx-1-compat` shim required.**

### 8.3 Dispatched event names (kebab-case myth corrected)

The migration guide's kebab-case directive (`hx-on="event:"` → `hx-on:event`) applies **only** to the `hx-on:<event>` attribute syntax. The DOM `CustomEvent` types matched by `addEventListener` are **unchanged — still camelCase**. Verified: 1.9.12 fires `htmx:afterRequest` (L3334), `htmx:afterSwap` (L3652); 2.x fires the **same** (`htmx:afterRequest` L4581, `htmx:afterSwap` L1982); grep for kebab event literals in 2.x source → **0 matches**. The repo's 4 listeners keep firing identically; rewriting them to kebab would *break* them.

### 8.4 Attributes / behavior

| Concern | 1.9.12 | 2.0.10 | Repo impact |
|---|---|---|---|
| `hx-get/hx-post/hx-target/hx-swap/hx-push-url/hx-headers/hx-trigger` | supported | supported (no attribute removals) | None |
| `hx-target="closest form"` | supported | supported (L1170) | None |
| `hx-swap="none"` | supported | supported (L1801; typedef L5179) | None |
| Module/ESM build | UMD global only | ESM added; `/dist/htmx.js` still browser-loadable | None — repo uses `<script>` global |
| `makeFragment()` / `selectAndSwap` internals | — | DocumentFragment always / removed→`swap` | None (extension/internal only; repo has neither) |
| IE11 | supported | **dropped** | None — modern stack |

---

## 9. Breaking changes ranked High / Medium / Low

### HIGH — `htmx.get()` at `header_catalog.html:536` is a latent `TypeError` (not a 2.x break)

- **API:** `htmx.get` does **not exist** in any HTMX version.
- **Evidence:** (1) 1.9.12 public object (L25–92) has no `get/post/put/delete/patch`; 0 literals; (2) 2.0.10 API block (L300–318) lists `htmx.ajax = ajaxHelper` (L307) and no `htmx.get`; 0 literals; (3) `htmx.org/api/` method table has no `get/post`.
- **Failure mode:** On catalog/ad-detail pages (the only pages including `header_catalog.html`), each favorite toggle dispatches `favorite:toggled` → line 536 → `TypeError: htmx.get is not a function`. Badge **never refreshes**. The toggle itself succeeds (`favorite_heart.html` `outerHTML` swap). Already broken in 1.9.12 production (internal note `01_search_patterns_verification.md:431`: TypeError ×2 per toggle). The cabinet pages use `components/header.html` and never render this handler.
- **Why HIGH:** silent stale-count regression that **persists after a version bump**; the PO-5=B premise ("upgrade resolves B6") does **not** hold.
- **Fix:** line 536 → `htmx.ajax('GET', url, { target: badge, swap: 'outerHTML' })` (2.x `ajaxHelper(verb, path, context)`; identical `{target, swap}` shape to `favorites.html:47`). **Confidence: Very High.**

### HIGH (informational) — Misdiagnosis in planning notes

`15_search_patterns_spec.md:433,470,572` and `block_01.md:24` claim `htmx.get/post` were "introduced in 2.0" and the upgrade "makes `htmx.get()` available without code modification." **False.** T6 must be planned as upgrade **+** call-site edit — not "upgrade only". **Confidence: Very High.**

### MEDIUM — none

No medium-severity 2.x breaking change touches the repo. All attributes/events/surviving APIs are preserved; the 3 config-default drifts are no-ops (§8.2).

### LOW — documentation corrections due (no code impact)

- `htmx.config` default drifts — no-ops; no override needed.
- `htmx.swap()`/`htmx.location()` added in 2.x — not used.
- Module dist files added in 2.x — repo stays on UMD `<script>`.
- `htmx.makeFragment()` + `selectAndSwap` removal — extension/internal only; repo has neither.
- IE11 dropped — modern stack, no requirement.
- **Stale in-repo comments (factually wrong):** `header_catalog.html:4` ("HTMX 1.9.12 has no hx-on"), `favorite_heart.html:29–30` ("HTMX 1.9.12 does not support the inline event attribute"), `test_favorites.py:95` docstring ("HTMX 1.9.12 has no `hx-on`"). Per 1.9.12 source, `hx-on` *is* handled (L1953–1954, L1989, L2064). Correct these so future work isn't misled — `hx-on` is unused, so no migration impact.
- `django-htmx` (server-side) — independent of frontend version.

---

## 10. Affected files and call sites + totals

### Files requiring a behavioral edit — **1**

| Severity | File:line | Current | Change |
|---|---|---|---|
| HIGH | `components/header_catalog.html:536` | `htmx.get(url, { target: badge, swap: 'outerHTML' })` | `htmx.ajax('GET', url, { target: badge, swap: 'outerHTML' })` |

### Files requiring the CDN bump — **5** (no logic change)

`ads/list.html:16`, `ads/detail.html:20`, `cabinet/hub.html:14`, `cabinet/saved_searches.html:15`, `cabinet/favorites.html:16`.

### Files with zero semantic change (verified compatible)

`ads/partials/filter_form.html:6–9`, `ads/partials/ad_list.html` (9×), `components/favorite_heart.html:6–8`, `cabinet/partials/saved_search_row.html:33–35,48–50`, `search/partials/save_search_modal.html:14–16`, and the 4 event listeners (`header_catalog.html:244/544`, `favorite_heart.html:34`, guard `header_catalog.html:533`).

### Test surface (string-assertion only — cannot catch the `TypeError`)

| Test | Asserts |
|---|---|
| `test_autocomplete_template.py:57–63` | `hx-get`, `hx-trigger`, `hx-target`, `hx-swap="none"` present |
| `test_autocomplete_template.py:76` | literal `htmx:afterRequest` present |
| `test_catalog_filters.py:503–504` | `ad_list.html` has `hx-get=` ×9 and `hx-push-url="true"` ×9 |
| `test_favorites.py:90–105` (`test_heart_template_no_hx_on`) | `"hx-on" not in` fragment; docstring L95 stale |

### Totals (precise)

| Metric | Value |
|---|---|
| Files touched | **6** (1 behavioral fix + 5 CDN bumps) |
| `htmx.*` call sites in repo | **2** (`htmx.ajax` preserved; `htmx.get` to fix) |
| Call sites requiring migration | **1** (`header_catalog.html:536`) |
| Distinct HTMX attributes | **7** |
| Real attribute occurrences | **60** |
| Attributes requiring migration | **0** |
| Extensions used | **0** |
| Manual engineering changes | **1** fix + 5 CDN bumps |

---

## 11. Engineering effort estimate

| Scope | Size | Rationale |
|---|---|---|
| **(1) Version upgrade** | **S** | 5 identical `@1.9.12`→`@2.0.10` edits; CDN-only, no package step; no attribute changes. |
| **(2) Repo-specific incompatibilities** | **S** | 1 call site (`header_catalog.html:536`) → `htmx.ajax('GET', …)` with the identical `{target, swap}` shape already used at `favorites.html:47`; all 3 config drifts are no-ops. |
| **Overall** | **S** | Code change is trivial. Real cost is manual integration regression (§13 step 6) because no test drives the JS runtime — pushes *verification* toward M even though *code* effort is S. |

Baseline: 41 tests pass (`--reuse-db`). They assert template strings, not browser JS, so they stay green and cannot catch the `TypeError`. A pre-existing DB-bootstrap quirk (`relation "ads" does not exist` from `setup_search_triggers.py`, PostgreSQL 18 DDL) is unrelated to HTMX.

---

## 12. Recommended migration strategy

**Direct single-step upgrade 1.9.12 → 2.0.10, paired with the one-line `htmx.get` → `htmx.ajax` fix. No dual-versioning, no feature flag, no shim.**

- *Direct upgrade → chosen.* Only APIs that are preserved (verified by source); 1 call site + 5 mechanical bumps.
- *Dual-version → rejected.* Single canonical load; no benefit.
- *Feature flag → rejected.* No behavioral deltas divert between versions for this app's usage (3 drifts are no-ops); a flag is overengineering.
- *`htmx-1-compat` → rejected.* It reverts the 3 drifts, but they are already no-ops here; adding a dependency to neutralize correct behavior violates the project's anti-overengineering rule. See §14 for the precise add-only criterion.
- *Test-first → adopted.* Add a regression test asserting the badge call uses `htmx.ajax` (not `htmx.get`) and the script is `@2.0.10`.

**Target version:** pin **`@2.0.10`** (mirrors `@1.9.12`; official docs pin `@2.0.10`). `@2` auto-floats patches (less reproducible).

**Bug-fix scope:** **bundle** the fix with the upgrade in one PR. The badge is broken under *both* versions (not just 2.x), the two changes touch the same catalog header, and the fix can only be validated at runtime against 2.x; the existing suite is string-only so shipping them separately offers no safety gain.

---

## 13. Step-by-step migration plan

1. **Freeze / inventory.** ✅ Done (§3–§10).
2. **Verify extensions.** ✅ Done (§7): none in use.
3. **Add a regression test (test-first).** Assert the catalog-header script uses `htmx.ajax('GET', …)` and **not** `htmx.get`; still renders `htmx:afterRequest`; script src is `@2.0.10`. Mirror `test_autocomplete_template.py` style.
4. **Bump HTMX.** Replace the 5 unpkg tags with the hardened jsDelivr+SRI minified tag (§14) at `ads/list.html:16`, `ads/detail.html:20`, `cabinet/hub.html:14`, `cabinet/saved_searches.html:15`, `cabinet/favorites.html:16`.
5. **Apply the required API fix.** `header_catalog.html:536`:
   ```js
   htmx.ajax('GET', '{% url "cabinet:favorites_count" %}', { target: badge, swap: 'outerHTML' });
   ```
6. **Run tests.** `make test` — expect 41 + new test green; no string assertions need updating.
7. **Manually exercise every HTMX path** (tests can't drive the JS runtime): toggle a favorite on a catalog/ad-detail page — open DevTools, confirm **no** `TypeError: htmx.get is not a function` and the `[data-favorites-badge]` refreshes; verify autocomplete (`hx-get`/`hx-swap="none"`), pagination/filter (`hx-get`+`hx-push-url`+`hx-target=#ad-list` + Back/forward), saved-search toggle/delete, and save-search modal.
8. **Remove temporary compatibility code.** None used; step 5 is the permanent fix.
9. **Deploy.** Single change (CDN bump + 1-line fix + test), no migration. Revert criterion: console `TypeError` on favorite toggle, or badge/list refresh regression.

---

## 14. Modern-practice recommendations (researched, not opinion)

### 1. CDN vs. self-hosted bundle

**Current:** 5× `unpkg.com/htmx.org@1.9.12`, no SRI/`crossorigin`. **Authoritative guidance** (official install docs, Context7): HTMX recommends **jsDelivr CDN with SRI** as the primary install, providing exact tags with `integrity`+`crossorigin`. Switch unpkg→jsDelivr because jsDelivr publishes the **official SRI hashes** — the single highest-leverage supply-chain fix (current tags have *zero* integrity protection). For an internet-connected public classifieds board, **jsDelivr + SRI** is the lighter, officially-recommended path. **Self-host alternative:** if air-gapped, vendor `htmx.min.js` into `static/theme/js/` and reference via `{% static %}` with a self-computed SRI hash (see below) — trades global-cache hits for full control.

### 2. SRI (`integrity` + `crossorigin`)

**Official SRI hashes for 2.0.10 (from HTMX install docs):**
- Minified: `sha384-H5SrcfygHmAuTDZphMHqBJLc3FhssKjG7w/CeCpFReSfwBWDTKpkzPP8c+cLsK+V`
- Unminified: `sha384-Q+Dky3iHVJOr6wUjQ4ulh6uQ76an/t+ak1+PjMVaxRjbZamFLAG+u9InkfjbsEQf`
- Tag: `<script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js" integrity="sha384-…" crossorigin="anonymous"></script>`

**If self-hosting:** generate from the vendored file:
```sh
openssl dgst -sha384 -binary static/theme/js/htmx.min.js | openssl base64 -A
```
then `integrity="sha384-<output>"` + `crossorigin="anonymous"` (SRI requires `crossorigin` to match the fetch mode).

### 3. Consolidate 5 duplicate script tags (follow-up, out of scope)

Modern Django-HTMX convention puts a single, SRI-tagged `<script>` in the **base layout** (`base.html`) instead of repeating it per page. Collapses 5 maintenance points → 1 and makes SRI management trivial. Flag as a `LOW` operational follow-up, not a migration blocker.

### 4. `htmx-1-compat` — decision for *this* repo: **do not add**

**When recommended:** an app relies on the *exact* 1.x defaults that changed in 2.x, **or** must support **IE11**. The official `htmx-1-compat` extension reverts `scrollBehavior`→`'smooth'`, DELETE→form-encoded body, `selfRequestsOnly`→cross-domain-allowed; it **does not** cover IE11 (for IE11, stay on 1.x). **Verdict here:** add it **only if** the repo later relies on a pre-2.x `scrollBehavior`/`methodsThatUseUrlParams`/`selfRequestsOnly` default or on IE11. All three drifts are already no-ops for this app (no DELETE; all same-origin; no `show`/`scroll`/`transition` swaps) → adding the extension would be overengineering.

### 5. Pinning `@2.0.10` vs `@2`

Pin **exactly `@2.0.10`** — mirrors the `@1.9.12` discipline and matches the official docs' own SRI tag. `@2` auto-floats patches (less reproducible). Re-verify `@latest`→version before implementation; the no-`htmx.get` invariant holds across 2.x.

### 6. IE11

2.x **drops IE11** (migration guide + release notes). The repo's inline JS already uses ES6+ (`addEventListener`, `const`/`let` at `favorites.html:46`) and the stack is modern (Django 5.2, Python 3.14, Tailwind, PostgreSQL 18) — no IE11 requirement identifiable. **No impact.**

### 7. CSP

2.x still ships `/dist/htmx.js` as a browser-loadable UMD global (jsDelivr path `/dist/htmx.js` unchanged), so the existing `<script>` + inline-vanilla-JS pattern needs **no CSP change**. The repo uses no `eval`-style `hx-vars`/inline `hx-on` expressions, and `hx-trigger="input delay:300ms"` has no expression. 2.x still emits `HX-Request: true` → `django-htmx` server-side stays compatible. **No CSP regression.**

### 8. `django-htmx` (server-side) — unaffected

In `INSTALLED_APPS` (`base.py:91`) but `HTMXMiddleware` is absent from `MIDDLEWARE` (lines 113–124) and 0 tags/`request.htmx` usage exist — installed-but-unwired. HTMX 2.x still sends `HX-Request: true` → upgrade is independent. (Hygiene: prune or wire — separate from this audit.)

---

## 15. Open questions / uncertainties

1. **Intended feature or dead code?** `header_catalog.html:536` (`htmx.get`) is not a real API in 1.9.12, so the badge refresh has **never** worked in production — it is a genuine bug, not merely "at risk under 2.x." Engineering should confirm intent so the §12 fix is treated as a bug fix, not only a migration edit. **Confidence: High.**
2. **Why is `django-htmx` installed but unwired?** Not a 2.x concern, but worth pruning/wiring for hygiene.
3. **Latest 2.x patch.** `@latest`→`2.0.10` (verified). Re-fetch before implementation and re-grep for `htmx.get`/`htmx.swap` (expected invariant).
4. **CSRF gap on `cabinet/saved_searches.html`.** `<body>` has no `hx-headers` (line 17); pre-existing, **unrelated to 2.x**; flag for due diligence.

---

## 16. Source references (authoritative)

1. **HTMX 1.9.12 source** — `https://unpkg.com/htmx.org@1.9.12/dist/htmx.js` (`version:"1.9.12"` L92): public API object (L25–92, no `get/post/put/patch/delete`); `ajaxHelper(verb, path, context)` (L2985); `responseInfo` (`xhr`/`target`); `htmx:afterRequest` (L3334); `htmx:afterSwap` (L3652); config defaults (`scrollBehavior:'smooth'` L72, `methodsThatUseUrlParams:["get"]` L76, `selfRequestsOnly:false` L77); `hx-on` handling (L1953–1954, L1989, L2064).
2. **HTMX 2.0.10 source** — `https://unpkg.com/htmx.org/dist/htmx.js` (`@latest`→`version:'2.0.10'` L299): API block (L300–318: `htmx.ajax=ajaxHelper` L307, `htmx.swap=swap` L316; **no** `htmx.get/post/put/patch/delete`); `ajaxHelper(verb,path,context)` (L4059); `HtmxResponseInfo` (`xhr` L5271, `target` L5272); `HtmxAjaxHelperContext` (L5236); `responseInfo` (L4558); `htmx:afterRequest` (L4581); `htmx:afterSwap` (L1982); config defaults (`scrollBehavior:'instant'` L211, `methodsThatUseUrlParams:['get','delete']` L235, `selfRequestsOnly:true` L241); `case 'none':` (L1801); `HtmxSwapStyle` (`'none'` L5179); `closest ` (L1170–1171); `hx-headers` (L3705); `HX-Request:true` (L3315, L3699). Grep for kebab event literals in 2.0.10 source → 0 matches.
3. **HTMX JS API reference** — `https://htmx.org/api/` (Context7 `api.md`): documents `htmx.ajax(verb, path, context)` (3 forms; returns Promise); method table has **no `htmx.get/post/put/delete/patch`**; documents `htmx.swap(target, content, swapSpec)`; documents `htmx.on(eltOrSelector, type, listener, opts)`.
4. **HTMX 1.x→2.x Migration Guide** — `https://htmx.org/migration-guide-htmx-1/` (Context7 `migration-guide-htmx-1.md`): `/dist/htmx.js` stays browser-loadable; SSE extension must upgrade (N/A); the 3 config default changes; `hx-on="event:"`→`hx-on:event` (kebab rule is attribute-syntax only); `makeFragment` always `DocumentFragment`; `selectAndSwap`→`swap` (extension authors); IE11 dropped.
5. **HTMX 2.0.0 release notes** — `https://htmx.org/posts/2024-06-17-htmx-2-0-0-is-released/` (Context7): confirms the three default changes ship in 2.0.0.
6. **HTMX install docs (official CDN + SRI)** — `https://htmx.org/docs/` (Context7 `docs.md`): jsDelivr CDN with published SRI `integrity` + `crossorigin="anonymous"` for `@2.0.10`.
7. **htmx-1-compat extension** — `https://htmx.org/extensions/htmx-1-compat/` (Context7 `htmx-1-compat.md`): reverts `scrollBehavior`, `methodsThatUseUrlParams`, `selfRequestsOnly`; explicitly **not** IE11 (recommends staying on 1.x). CDN tag + SRI: `<script src="https://cdn.jsdelivr.net/npm/htmx-ext-htmx-1-compat@2.0.2" integrity="sha384-lcvVWaNjF5zPPUeeWmC0OkJ2MLqoWLlkAabuGm+EuMSTfGo5WRyHrNaAp0cJr9Pg" crossorigin="anonymous"></script>` with `<body hx-ext="htmx-1-compat">`.
8. **Project source (audited):** templates at `src/backend/templates/...` (5 HTMX-loading templates; `components/header_catalog.html` incl. line 536 + `header_favorites_badge.html` include at L28; `favorite_heart.html:34` listener + `:29–30` stale comment; `header_favorites_badge.html:2`; `ad_list.html:42–170`; `filter_form.html:6–9`; `saved_search_row.html:33–50`; `save_search_modal.html:14–16`); `pyproject.toml:21` (`django-htmx>=1.19.0`); `uv.lock` (resolves 1.28.0); `config/settings/base.py:91` (`django_htmx` in `INSTALLED_APPS`), `base.py:113–124` (no `HTMWiddleware`); `apps/ads/tests/test_catalog_filters.py:503–504`, `apps/search/tests/test_autocomplete_template.py:57–76`, `apps/ads/tests/test_favorites.py:90–105`.

*Prepared by a Researcher agent merging two independent source-level audits. No production or repository files were modified; this document is read-only analysis for planning the HTMX 2.x upgrade (PO-5 / T6, gated on this audit per the internal problem notes).*
