---
id: csp-phase2-enforcement
domain: tracking
status: planned
priority: medium
tags:
  - csp
  - content-security-policy
  - security-headers
  - phase-2
  - tracking
  - milestone
related:
  - docker/nginx/nginx.conf
  - src/backend/apps/core/views.py
  - src/backend/apps/core/urls.py
  - docs/01-spec/architecture-structure.md
  - .ai/audit/99-validation/09-external-api-validated-findings.md
  - .ai/plans/28-external-api-fixes.md
---

# CSP Phase 2 Enforcement Tracking Milestone

## Purpose

This document establishes the Phase 2 CSP enforcement plan as a tracked deliverable.
It records the current Report-Only state, the Phase 1 baseline, the Phase 2 goal with
sub-tasks, the success criteria that must gate enforcement, and the ownership /
priority / dependency matrix.

This is a **planning artifact only** — no code changes, no runtime impact. The exact
nonce/hash migration approach is **not** prescribed here; it is a Phase 2 decision
to be worked out when Phase 2 execution begins.

**Tracking context:** Resolving finding `09-EXT-02` from
`.ai/audit/99-validation/09-external-api-validated-findings.md:64`. This milestone
corresponds to **Block B5** in `.ai/plans/28-external-api-fixes.md:680`.

## Current State

The production nginx configuration applies a **Report-Only** Content-Security-Policy.
It is set at three locations in `docker/nginx/nginx.conf` (nginx `add_header`
inheritance drops inherited headers when a `location` block defines its own, so each
block re-declares the full policy):

| Location | Line | Directive |
|---|---|---|
| Server-level (all responses) | `nginx.conf:53` | `Content-Security-Policy-Report-Only` |
| Static assets | `nginx.conf:75` | `Content-Security-Policy-Report-Only` (re-declared) |
| Protected media (`/protected-media/`) | `nginx.conf:97` | `Content-Security-Policy-Report-Only` (re-declared) |

The current server-level policy (`nginx.conf:53`):

```
add_header Content-Security-Policy-Report-Only "default-src 'none'; script-src 'self' 'unsafe-inline' https://unpkg.com https://*.plausible.io; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; report-uri /csp-report/" always;
```

Key facts about the current state:

- **`report-uri /csp-report/`** — Violation reports are POSTed to the Django endpoint
  at `/csp-report/` (`src/backend/apps/core/views.py:93` — `csp_report()` view;
  `src/backend/apps/core/urls.py:14` — URL route).
- **`'unsafe-inline'` is present** in both `script-src` and `style_src`. Inline
  scripts and inline styles execute without restriction. No violations are **blocked**
  — the policy is purely observational.
- **Report-only = zero enforcement.** Browsers collect violations and report them but
  never block resources. This means the `unsafe-inline` allowances provide **no XSS
  protection via inline-script injection** until enforcement is switched on.
- **Documented baseline:** `docs/01-spec/architecture-structure.md:324` documents this
  as "Phase 1 (Report-Only)" and `:325` records Phase 2 as "deferred" with no
  follow-up tracking — which is the gap this milestone closes.

## Phase 1 Goal (Done)

**Goal:** Deploy a Report-Only CSP to collect violation data without blocking any
resources or risking site availability.

**Status:** COMPLETE. The Report-Only policy is deployed across all three nginx
locations. The `/csp-report/` endpoint is live and receiving reports.

This phase carries **zero rollout risk**: because the policy is Report-Only, no
content is blocked even if the policy were too restrictive. All inline scripts and
styles continue to execute normally via the `unsafe-inline` allowances.

## Phase 2 Goal (Tracked Here)

**Goal:** Migrate from Report-Only CSP to an **enforcing** `Content-Security-Policy`
that eliminates `unsafe-inline` and protects against inline-script/style injection.

Phase 2 is **not yet started**. The specific mechanism for replacing `unsafe-inline`
(nonce-based allow-lists, hash-based allow-lists, or a combination) and the per-template
audit details are **out of scope for this tracking document** — they are Phase 2
execution decisions. This section defines the goal and its sub-tasks only.

### Sub-tasks

| # | Sub-task | Scope | Notes |
|---|---|---|---|
| a | Audit all inline scripts and styles in templates | `templates/` | Identify every inline `<script>` and inline `style` that `unsafe-inline` currently accommodates. Output: an inventory of inline sources to be migrated. |
| b | Replace inline scripts with allow-list-based directives | `templates/` | Migrate inline `<script>` blocks away from `unsafe-inline`. Specific approach (nonce vs. hash) decided in Phase 2. |
| c | Replace inline styles with allow-list-based directives | `templates/` | Migrate inline `style` attributes / `<style>` blocks away from `unsafe-inline`. Specific approach (hash) decided in Phase 2. |
| d | Switch `Content-Security-Policy-Report-Only` → enforcing `Content-Security-Policy` | `docker/nginx/nginx.conf` | Update all three locations (server-level `:53`, `/static/` `:75`, `/protected-media/` `:97`) from the `-Report-Only` header to the enforcing header, with `unsafe-inline` removed. |
| e | Keep the report endpoint active for fallback monitoring | `docker/nginx/nginx.conf`, `src/backend/apps/core/` | Retain `report-uri /csp-report/` (and/or `report-to`) on the enforcing policy so violations continue to be collected for monitoring after enforcement activates. |

### Phase 2 Coordination Notes

- **Coordinated deployment with HSTS preload (Block B4, 09-EXT-03):** Both Phase 2
  CSP enforcement and the HSTS `preload` change touch nginx security headers. They
  should be deployed in the same window to avoid a transient state where CSP is
  enforced but HSTS preload is not yet submitted (or vice versa). See
  `.ai/plans/28-external-api-fixes.md:105-108` for the coordination note.
- **Exact migration approach is deferred to Phase 2** — this document does not
  prescribe nonce values, hash computation, or specific CSP directive syntax. Those
  decisions belong to the Phase 2 implementor(s).

## Success Criteria

**The Phase 2 enforcement switch (sub-task d) may not proceed until all of the
following are met:**

1. **Zero CSP violations in Report-Only mode for 7 consecutive days.** The
   `/csp-report/` endpoint must log no violations for a full 7-day window. This
   confirms that `unsafe-inline` can be safely removed without breaking any real
   traffic.
2. **Sub-task audit (a) complete.** An inventory of all inline scripts/styles exists
   and has been reviewed.
3. **All templates migrated (sub-tasks b, c).** No template relies on
   `unsafe-inline` after the migration. A structural grep confirms no inline
   `<script>` or inline `style` remains in `templates/`.
4. **`report-uri`/`report-to` endpoint active (sub-task e).** The enforcing policy
   still points to `/csp-report/` and the endpoint continues to receive reports.

> Violations are inspected via the `csp_report` view's logging. After **B7/B8**
> (schema validation + INFO log level) complete, the endpoint validates report
> structure and logs at `INFO` — making the collected data reliable enough to
> distinguish real violations from noise (see Dependencies below).

## Ownership, Priority, and Dependencies

| Field | Value |
|---|---|
| **Owner** | docs-specialist (author of this milestone) — Phase 2 execution ownership to be assigned when Phase 2 begins. |
| **Priority** | MEDIUM (matches finding 09-EXT-02 severity) |
| **Status** | Planned — Phase 2 not started. Phase 1 (Report-Only) is complete. |

### Dependencies

| Dependency | Block | Finding | Why it gates Phase 2 |
|---|---|---|---|
| **CSP report schema validation + INFO log** | B7 | 09-EXT-04b | Without schema validation, the `/csp-report/` endpoint accepts arbitrary JSON and logs at `WARNING` level. The Report-Only violation data cannot be trusted to distinguish real violations from noise. B7 validates report structure before logging. |
| **CSP report tests (validation + log level)** | B8 | 09-EXT-04c | Verifies B7's schema validation and INFO log-level change. Must pass before the 7-day zero-violation window is meaningful. |
| **Dedicated `/csp-report/` nginx location + tighter rate limit** | B6 | 09-EXT-04a | Ensures the reporting endpoint is not throttled under the loose `browse_limit` zone during the 7-day monitoring window. (Recommended, not a hard gate.) |

> **Gating rationale:** The 7-day zero-violation success criterion requires
> trustworthy violation data. B7/B8 (schema validation) is the **gating prerequisite** —
> until reports are structurally validated, noise (malformed payloads, adversarial
> flood) cannot be filtered out, and the "zero violations" signal is unreliable. This
> milestone must **not** advance to enforcement (sub-task d) until B7 and B8 are
> complete and their tests pass.

### Execution Order

```
Phase 1 (DONE):    Report-Only CSP deployed (nginx.conf:53/75/97)

Phase 1.5 (B5-B8): ────────────────────────────
  B5 (this doc)  Create tracking milestone    [done by docs-specialist]
  B6 (nginx)     Dedicated /csp-report/ loc    [Implementor]
  B7 (view)      Schema validation + INFO log  [Implementor]
  B8 (test)      ──> B7                        [Validator]

Phase 2 (gated):   ────────────────────────────
  0. Confirm 7-day zero-violation window (B7/B8 data trusted)
  1. (a) Audit inline scripts/styles in templates
  2. (b) Migrate inline scripts to allow-lists  [approach TBD]
  3. (c) Migrate inline styles to allow-lists   [approach TBD]
  4. (d) Switch to enforcing Content-Security-Policy
  5. (e) Keep report-uri/report-to endpoint active
```

## Audit Trail

| Date | Action | Author |
|---|---|---|
| 2026-09-21 | Created tracking milestone document | docs-specialist (Block B5) |

## References

- **Finding:** `.ai/audit/09-external-api/findings.md:52` — 09-EXT-02
- **Validated finding:** `.ai/audit/99-validation/09-external-api-validated-findings.md:64`
- **Plan block:** `.ai/plans/28-external-api-fixes.md:680` (Block B5)
- **Current policy:** `docker/nginx/nginx.conf:53`
- **Report endpoint:** `src/backend/apps/core/views.py:93` (`csp_report`),
  `src/backend/apps/core/urls.py:14`
- **Architecture doc:** `docs/01-spec/architecture-structure.md:324-325`
- **Gating:** B7 (`.ai/plans/28-external-api-fixes.md:894`) and B8 (`:1043`)
