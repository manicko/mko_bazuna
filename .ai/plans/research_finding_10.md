# Research: Finding 10 — CSP Scope Too Narrow

**Finding ID:** 10 (MEDIUM)
**Researcher:** task `ses_ff011c81fffe9XYZ3IHwbAO9Hc`
**Date:** 2026-08-17

---

## Current State

### Two nginx configs
- `docker/nginx/nginx.conf` (production): server-level HSTS, nosniff, X-Frame-Options (NO CSP)
- `docker/nginx/nginx.dev.conf` (dev): same minus HSTS

### `add_header` inheritance analysis
nginx rule: any `add_header` in a location block overrides ALL inherited `add_header` from parent blocks.

| Location | Has add_header? | Headers applied | CSP? |
|----------|-----------------|-----------------|------|
| `/static/` | Yes — Cache-Control | Cache-Control only; drops all inherited | No |
| `/media/` | No | Inherits server-level | No |
| `/protected-media/` | Yes — 4 headers | Full set incl. CSP | Yes |
| `/login/` | No | Inherits server-level | No |
| `/search/` | No | Inherits server-level | No |
| `/health/` | No | Inherits server-level | No |
| `/` | No | Inherits server-level | No |

CSP applied to 1 of 8 location blocks. Spec claims CSP on "all responses."

### Template audit (inline content that breaks strict CSP)
The strict policy `default-src 'none'; img-src 'self' data:; object-src 'none'` would block ALL scripts (falls back to `default-src 'none'` for `script-src`).

**External scripts:**
- `https://unpkg.com/htmx.org@1.9.12` — `ads/list.html`
- `https://{{ PLAUSIBLE_HOST }}/js/script.js` — 7 templates (runtime-resolved host)

**Inline `<script>` blocks:**
- `ads/list.html` (autocomplete dropdown)
- `components/language_switcher.html`
- `admin/moderation/review.html`
- `users/login_issue.html` (login polling via fetch)

**Inline event handlers (`onclick=`):**
- `ads/dashboard.html`, `admin/moderation/review.html` (7 handlers)

**`javascript:` URI:**
- `ads/detail.html` (`href="javascript:history.back()"`)

**Inline styles (`style=`):**
- `analytics/moderation_dashboard.html`, `admin/moderation/queue.html`

**Django admin at `/admin/`:** ships with extensive inline scripts, inline event handlers, `eval()` calls — strict CSP breaks it entirely.

All templates load `{% static 'theme/css/output.css' %}` → needs `style-src 'self'`.

---

## Alternatives

| Alt | Description | Verdict |
|-----|-------------|---------|
| A | Server-level strict CSP (enforce) | Breaks all inline scripts, external CDNs, onclick, javascript: URIs, Django admin. Site non-functional. |
| B | Per-location strict CSP (7 blocks) | Same breakage + verbose duplication. |
| C | `include` snippet for headers | Same breakage; only solves DRY, not policy compatibility. |
| **D** | **Server-level CSP-Report-Only + content-appropriate policy** | Zero rollout risk (Report-Only doesn't enforce). Collect violations, then tighten. |
| E | Content-type `map` differentiation | Adds map complexity for staging phase. |
| F | django-csp middleware | Shifts from nginx to Django; adds dependency; deviated from spec. |
| G | Server-level relaxed (enforce) + strict override | Live `'unsafe-inline'` is false security. |
| H | Map: enforce for images, Report-Only for HTML | Overly complex; CSP on image responses is meaningless. |

## Evaluation Matrix

| Alt | Correctness | nginx Fit | Maintainability | Rollout Risk | Rollback |
|-----|-------------|-----------|-----------------|-------------|----------|
| A | High scope, FAILS policy | Excellent | Excellent | CRITICAL | Trivial |
| B | High scope, FAILS policy | Poor | Poor | CRITICAL | Medium |
| C | High scope, FAILS policy | Good | Medium | CRITICAL | Medium |
| **D** | **High scope, SAFE (Report-Only)** | **Excellent** | **Excellent** | **LOW** | **Trivial** |
| E | High | Good | Medium | Medium | Medium |
| F | High | Poor | Medium | Medium | Medium |
| G | High | Good | High | Medium | Medium |
| H | High | Fair | Poor | Low | Poor |

## Selected Solution: Alternative D — Server-level CSP-Report-Only

### Policy (content-appropriate, Report-Only)
```
default-src 'none';
script-src 'self' 'unsafe-inline' https://unpkg.com https://*.plausible.io;
style-src 'self' 'unsafe-inline';
img-src 'self' data:;
object-src 'none';
base-uri 'none';
frame-ancestors 'none';
report-uri /csp-report/
```

### Rationale
1. Fixes Finding 10 scope: CSP now at server level, covering all responses.
2. Zero rollout risk: Report-Only sends violation reports but doesn't enforce.
3. Content-appropriate: accommodates existing inline scripts/styles/external CDNs.
4. Clear Phase 2 path: once templates refactored (extract inline JS, replace onclick, localize htmx), switch to enforcing `Content-Security-Policy`.
5. Idiomatic nginx: single `add_header` at server level.

### Dependency on Finding 09
Must be applied concurrently with Finding 09 (nginx `/static/` header inheritance). Since `/static/` has its own `add_header` directives, it drops server-level CSP-Report-Only unless re-declared in the `/static/` block.

### Files changed
- `docker/nginx/nginx.conf` — server-level CSP-Report-Only; re-declare in `/static/`; `/protected-media/` → Report-Only
- `docker/nginx/nginx.dev.conf` — identical (no HSTS)
- NEW: `src/backend/apps/core/views.py` — `csp_report` view
- `src/backend/apps/core/urls.py` — `/csp-report/` route
- NEW: `src/backend/apps/core/tests/test_csp_report.py` — 3 tests
- `docs/01-spec/architecture-structure.md` — staged rollout documentation

### Phase 2 (deferred)
Refactor templates to eliminate `'unsafe-inline'`, then switch to enforcing `Content-Security-Policy`.
