# HTMX 2.0 Migration — Consolidated Findings

> **Source:** Researcher audit report `.ai/audit/problems/full_htmx_report.md` (consolidates `1_htmx_report.md` + `2_htmx_report.md`), cross-checked against verbatim HTMX `1.9.12` and `2.0.10` library sources fetched from the same `unpkg.com/htmx.org` CDN the project uses, plus official docs (`htmx.org/api/`, the 1.x→2.x migration guide, 2.0 release notes).
> **Status:** Findings validated against source. This is a planning reference only — **no code was changed.**

---

## Summary

Mko Bazuna loads HTMX **1.9.12** from the **unpkg CDN** across **5 standalone page templates** (no package-manager dependency, no HTMX extensions, 7 distinct `hx-*` attributes). The upgrade to HTMX **2.0.x** is a **low-effort, low-risk** operation at the attribute layer: every attribute and event the project uses (`hx-get`, `hx-post`, `hx-target`, `hx-swap`, `hx-push-url`, `hx-headers`, `hx-trigger`, `htmx:afterRequest`, `htmx:afterSwap`) is preserved verbatim in 2.0.x.

**However**, the CDN version bump does **not** auto-resolve bug **B6**. The migration requires exactly **2 code changes** (1 version tag across 5 files + 1 call-site fix), plus correction of **3 stale comments**. The remaining 4 call-site/event references are **NO-CHANGE** under the migration.

| # | Change | Type | Location | Affected Block(s) |
|---|---|---|---|---|
| 1 | `htmx.org@1.9.12` → `htmx.org@2.0.x` (script `src`) | Bump (5 files) | `list.html:16`; `detail.html:20`; `cabinet/favorites.html:16`; `cabinet/hub.html:14`; `cabinet/saved_searches.html:15` | 1 (cross-cutting header runtime) |
| 2 | `htmx.get(url, {target, swap})` → `htmx.ajax('GET', url, {target, swap})` | **Fix (NOT auto-resolved by bump)** | `header_catalog.html:536` | 1 |
| 3 | `addEventListener('htmx:afterRequest', …)` | NO CHANGE | `header_catalog.html:244` | 1 |
| 4 | `addEventListener('htmx:afterSwap', …)` | NO CHANGE | `header_catalog.html:544` | 1 |
| 5 | `addEventListener('htmx:afterRequest', …)` | NO CHANGE | `favorite_heart.html:34` | 1, 5 |
| 6 | `htmx.ajax('GET', url, {target, swap})` (already 2.x-correct) | NO CHANGE (preserved in 2.x) | `cabinet/favorites.html:47` | 1, 5 |

---

## 1. Version tag bump — 5 templates

All 5 page templates load HTMX via a pinned CDN `<script>` tag. Bump `@1.9.12` → `@2.0.10` (the version the audit validated against). The audit recommends hardening with jsDelivr + SRI; that infra decision is out of scope for this findings doc — only the tag value matters here.

| Template | Line | Current | New |
|---|---|---|---|
| `templates/ads/list.html` | 16 | `htmx.org@1.9.12` | `htmx.org@2.0.10` |
| `templates/ads/detail.html` | 20 | `htmx.org@1.9.12` | `htmx.org@2.0.10` |
| `templates/cabinet/favorites.html` | 16 | `htmx.org@1.9.12` | `htmx.org@2.0.10` |
| `templates/cabinet/hub.html` | 14 | `htmx.org@1.9.12` | `htmx.org@2.0.10` |
| `templates/cabinet/saved_searches.html` | 15 | `htmx.org@1.9.12` | `htmx.org@2.0.10` |

**Affected blocks:** Block 1. The shared `header_catalog.html` is `{% include %}`-d on the listing (`list.html`) and ad-detail (`detail.html`) pages; its badge-refresh path (change #2) depends on whichever runtime each page loads. The cabinet templates (`favorites.html`, `hub.html`, `saved_searches.html`) load the same tag independently.

---

## 2. `htmx.get()` → `htmx.ajax('GET', …)` — `header_catalog.html:536` — **REQUIRED FIX**

`htmx.get()` is **not a real HTMX API in 1.9.12 or 2.0.x** (audit `full_htmx_report.md` §D1: zero matches in the public API object of either version, absent from `htmx.org/api/`). This is a **pre-existing latent `TypeError` bug**, not a 2.x breaking change. Current code at `header_catalog.html:536`:

```js
htmx.get('{% url "cabinet:favorites_count" %}', {
    target: badge,
    swap: 'outerHTML'
});
```

**Required code fix:**

```js
htmx.ajax('GET', '{% url "cabinet:favorites_count" %}', {
    target: badge,
    swap: 'outerHTML'
});
```

This is the **exact pattern already used** at `cabinet/favorites.html:47`. **This is NOT resolved by the CDN version bump** — it was already broken in production under 1.9.12 and stays broken under 2.0.x without the call-site fix.

**Affected blocks:** Block 1 (header favorites-badge auto-refresh on favorite toggle — fires `favorite:toggled` from `favorite_heart.html:34`).

> ⚠️ **B6 correction to planning docs:** `15_search_patterns_spec.md` (PO-5=B, T6) and `block_01.md` originally assumed the HTMX 2.x upgrade "resolves" B6. Research disproves this — `htmx.get()` is not a real HTMX API in *any* version. The implementor **must** apply this explicit one-line call-site fix regardless of the CDN bump. `block_01.md` (line 24) has already been corrected to reflect this.

---

## 3–5. `addEventListener` event-name references — **NO CHANGE**

The repo uses `addEventListener` with camelCase event names in three sites:

| # | Site | Line | Listener |
|---|---|---|---|
| 3 | `header_catalog.html` | 244 | `htmx:afterRequest` (renders autocomplete dropdown response) |
| 4 | `header_catalog.html` | 544 | `htmx:afterSwap` (re-parse injected submenu panels for accordion behavior) |
| 5 | `favorite_heart.html` | 34 | `htmx:afterRequest` (dispatch `favorite:toggled` after heart POST swap) |

**NO CHANGE NEEDED.** In HTMX 2.0.x, `addEventListener` still fires **both** the camelCase form (`htmx:afterRequest` / `htmx:afterSwap`) **and** the kebab-case form (`htmx:after-request` / `htmx:after-swap`) — HTMX 2.0 dispatches aliases for backward compatibility. **Only** the `hx-on:` *attribute* shorthand requires kebab-case in 2.0.x. The repo uses **neither** `hx-on:` attribute, so these `addEventListener` call sites are entirely unaffected by the migration.

**Affected blocks:** Block 1 (header_catalog.html:244 autocomplete after-request, :544 after-swap) and Block 1 + Block 5 (favorite_heart.html:34 — the heart toggle is rendered on listing cards via the ad-list partial).

---

## 6. `htmx.ajax()` in `cabinet/favorites.html:47` — **NO CHANGE**

```js
htmx.ajax('GET', url, { target: '#favorites-list', swap: 'innerHTML' });
```

**NO CHANGE NEEDED.** `htmx.ajax()` is **preserved** in HTMX 2.0.x — in the 2.0.10 source it is `htmx.ajax = ajaxHelper` (documented at `htmx.org/api/`), and its `(verb, path, context)` signature is unchanged. The planning docs' speculative note ("*If `htmx.ajax()` is removed/deprecated in 2.x, replace with…*") is **incorrect** — it was not removed and the call site is already 2.x-correct.

**Affected blocks:** Block 1, Block 5 (cabinet favorites-list management — removes a favorite card via innerHTML swap).

---

## Stale Comments / Docstrings to Correct

Three comments are factually wrong — `hx-on` **is** supported in HTMX 1.9.12 (audit §D3: 1.9.12 source L1953–1954, L1989, L2064 handle `hx-on`). These should be updated when the owning templates/tests are next touched; they are not blockers for the CDN bump but propagate the same misconceptions the audit corrects.

| # | File:Line | Current (WRONG) | Correction |
|---|---|---|---|
| S1 | `header_catalog.html:4` | "Vanilla JS behavior (HTMX 1.9.12 has no hx-on)." | `hx-on` IS supported in 1.9.12; this component uses none — rephrase to "Vanilla JS behavior; no `hx-on` inline-event attributes are used." |
| S2 | `favorite_heart.html:29-30` | "HTMX 1.9.12 does not support the inline event attribute that this component previously relied on; dispatch `favorite:toggled` natively so the header heart badge can refresh after a toggle." | `hx-on` IS supported in 1.9.12; the true mechanism is a native `htmx:afterRequest` listener that dispatches `favorite:toggled`. |
| S3 | `test_favorites.py:95` (docstring) | "HTMX 1.9.12 has no `hx-on`; the event dispatch was replaced with a native `htmx:afterRequest` listener, so a toggled heart must not carry the broken attribute." | `hx-on` IS supported in 1.9.12; restate the assertion as "the heart form does not carry a stale `hx-on` attribute — the dispatch is via a native `htmx:afterRequest` listener." |

---

## Cross-References — Affected Blocks & Plan Sections

The shared `header_catalog.html` is `{% include %}`-d on every listing/detail page, so B6 (favorites badge refresh) is cross-cutting in terms of *runtime* but anchors to **Block 1** in the plan.

| Change | Source location(s) | Plan block | Plan entry |
|---|---|---|---|
| Version tag bump (5 files) | `list.html:16`, `detail.html:20`, `cabinet/favorites.html:16`, `cabinet/hub.html:14`, `cabinet/saved_searches.html:15` | 1 | B6 (line 47), P3 roadmap (line 67) |
| `htmx.get` → `htmx.ajax` fix | `header_catalog.html:536` | 1 | B6 (line 47, P3 row line 67), block_01.md Line 24, D8 |
| `htmx:afterRequest` (NO CHANGE) | `header_catalog.html:244`; `favorite_heart.html:34` | 1, 5 | B6 |
| `htmx:afterSwap` (NO CHANGE) | `header_catalog.html:544` | 1 | — |
| `htmx.ajax` preserved (NO CHANGE) | `cabinet/favorites.html:47` | 1, 5 | B6 |
| Stale comment S1 | `header_catalog.html:4` | 1 | — |
| Stale comment S2 | `favorite_heart.html:29-30` | 1, 5 | — |
| Stale comment S3 | `test_favorites.py:95` | 1, 5 | — |

---

## Verification Baseline & Gap

The audit ran a **41-test baseline (green, no code changes)** against the current 1.9.12 state. Caveat (audit §D5): repo tests assert template *source strings* (`hx-get`, `hx-swap`, `htmx:afterRequest`, absence of `hx-on`), **not** browser JS — so they cannot catch the `htmx.get` `TypeError` at runtime. The call-site fix in change #2 closes a gap the existing test suite does **not** cover; a regression-guard test asserting "`header_catalog.html:536` uses `htmx.ajax('GET', …)` and not `htmx.get(…)`" is recommended downstream (block_01.md line 24 marks this N/A / implementor fix).

---

## References

- Audit report: `.ai/audit/problems/full_htmx_report.md` (consolidates `1_htmx_report.md` + `2_htmx_report.md`)
- B6 in live verification report: `.ai/problems/01_search_patterns_verification.md` (§B6)
- B6 / PO-5 / T6 in spec: `.ai/problems/15_search_patterns_spec.md` (lines 56, 146–160, 295–322, 384, 427–442, 520, 530–536, 686–689)
- Plan B6 entry + roadmap P3 row + deviations: `.ai/plans/01_search_patterns_test_verification_detailed_plan.md` (lines 47, 67, 108)
- Block 1 findings (B6): `.ai/plans/_blocks/block_01.md` (Line 24)
