# P-003 Rate-Limit Remediation — Validation Report

**Project:** Mko Bazuna (Django + Telegram bot + PostgreSQL 18)  
**Scope:** P-003 media_gate rate-limit blankout on HTMX sort  
**Commits reviewed:** `aa0a08ba`, `cb798afa`, `f949d554`, `410896fc`  
**Date:** 2026-10-10  
**Validator:** Automated read-only review  

---

## 1. Overall Verdict: **PASS**

The P-003 remediation is architecturally sound, implementationally correct, and well-tested. The four commits implement three independent work blocks (C, A, B) exactly as planned, with backward-compatible changes to the shared `rate_limited_response` helper. No production behavior regresses for the 7 non-media callers of the shared 429 builder. Remaining risks are documented as known limitations with deferred successors; one docstring inaccuracy is flagged (see §6).

---

## 2. Per-File Review

### Core implementation (4 files)

**1. `src/backend/apps/core/utils/rate_limit_response.py`** — `rate_limited_response` now accepts optional `retry_after: int | None = None` and `body: str | None = None`, both defaulting to `None`, and unconditionally sets `Cache-Control: no-store` on every 429. The two `@overload` signatures were updated to carry the new parameters, preserving type-safety for callers. All 8 production callers (commit aa0a08ba) pass neither new param except `media_gate`, so they receive identical behavior plus the `no-store` addition — a strict improvement. The `RETRY_AFTER_HEADER` constant is defined and used internally but not exported; callers pass an integer and it is stringified at the boundary. One issue: the docstring (line 47) claims `body` is "Ignored for the default JSON shape unless explicitly set," but the code applies `response.content = body` unconditionally when `body is not None`, regardless of the `json` flag — see §5/§6 for the latent footgun.

**2. `src/backend/apps/ads/views/listings.py`** — Three changes shipped across three commits:
- *commit cb798afa (Block C-2):* `_MEDIA_GATE_429_SVG` constant (lines 70–75) added; the 429 path (lines 211–217) now calls `rate_limited_response(json=False, retry_after=MEDIA_RATE_LIMIT_PERIOD, body=_MEDIA_GATE_429_SVG)` and then sets `response["Content-Type"] = "image/svg+xml"`. The Content-Type override works correctly on Django's `HttpResponse` (it is a plain header in the internal `HttpResponseHeaders` dict) — confirmed by the live verification guide (line 249) and the test assertion at `test_media_security.py:968`.
- *commit f949d554 (Block A):* `_MEDIA_CACHE_CONTROL_200` constant (line 84) replaces the four inline `Cache-Control` string assignments on 200 responses (lines 252, 256, 275, 280) — one per serving branch: staff+DEBUG, staff+prod, non-staff+DEBUG, non-staff+prod. All four branches now use the same constant, so drift is impossible.
- *Uncommitted (scope: comment-only):* The module comment at line 57 was updated from "60 requests / 60 s" to "240 requests / 60 s" to match the new budget. This is the only uncommitted change to `listings.py` and is correct.

**3. `src/backend/apps/core/enums.py`** — `RateLimitBudget.MEDIA_GATE.requests` changed from `60` to `240` (line 63); the `period` remains `60` (line 74); the docstring (line 45) was updated from "60 requests / 60 s" to "240 requests / 60 s". No structural change to the enum's dict-lookup pattern. All other budgets (SEARCH_PAGE=30, AUTOCOMPLETE=30, DEEP_LINK_RENDER=60, LOGIN_ISSUE=10) are unchanged.

**4. `.ai/plans/001-media-rate-limit-remediation.md`** — The execution plan. Sections 5–10 specify implementation order (C→A→B), per-block task specs, acceptance criteria, and test strategy. Three deviations from the plan were observed in the implementation:
- *SVG attributes:* §4.3 specifies an SVG with `role="img"`, `aria-label="Image unavailable"`, and `rx="8"` on the `<rect>`. The shipped SVG (listings.py:70–75) omits all three. This is a **sound** simplification — `aria-label="Image unavailable"` is an English string that would trigger the i18n completeness gate, and the `<img>` tag in `ad_list.html:127` already carries `alt="{{ ad|get_title:LANGUAGE_CODE }}"` for screen readers. `rx="8"` is irrelevant: the SVG is served as an `<img>` `src`, so the CSS `rounded-t-lg` class on the `<img>` element (line 128) handles visual rounding.
- *"19 callers" typo:* The plan (line 138) states "All 19 existing callers" but then (line 149) enumerates "8 call sites in 5 files" — the 19 is an error; 8 is correct (confirmed by grep and the attribution record at line 242).
- *Test file:* §4.3 acceptance criterion C4 and the §6 task list reference a new `test_rate_limit_response.py`, which was **never created** (see §2.6 below). The tests were placed in `test_rate_limit_budget.py` instead.

### Tests (3 files)

**5. `src/backend/apps/core/tests/test_rate_limit_budget.py`** — Commit aa0a08ba added 6 new test methods to `TestOneResponseShape` covering the new `no-store` header, `Retry-After` when specified / absent when omitted, `body` override, and backward compatibility. Commit 410896fc updated line 82 from `(60, 60)` to `(240, 60)`. The `TestNamespaceIsolation` and `TestForwardedForRegressionGuard` classes correctly use `RateLimitBudget.SEARCH_PAGE.requests` (30) for their loops, not the media budget. No stale assertions remain.

**6. `src/backend/apps/ads/tests/test_media_security.py`** — Commit cb798afa added 4 assertions to existing rate-limit tests (Retry-After, SVG in body, Content-Type, no-store) and added 3 new test methods: `test_429_has_retry_after_header`, `test_429_returns_svg_placeholder`, `test_429_has_no_store_cache_control`. Commit f949d554 updated all `TestMediaGateCacheControl` assertions from `no-store`/`no-cache` to `public, max-age=86400` (with `immutable`-absence and `no-store`-absence checks), and added `test_200_response_has_cache_control_max_age`. Commit 410896fc added `test_media_gate_budget_allows_ten_page_loads` (240 allowed, 241st is 429) and updated `test_period_constant_is_the_documented_window` from `(60, 60)` to `(240, 60)`. **Notable gap:** `test_429_returns_svg_placeholder` (line 1064) asserts `_MEDIA_GATE_429_SVG in body` — this imports the constant and checks it is a substring of the response body, which is a circular assertion (testing the constant against itself). The `<svg` and `Content-Type` assertions on lines 1077/1078 are the genuinely behavioral checks.

**7. `src/backend/apps/core/tests/test_rate_limit_response.py`** — **This file does not exist.** The plan (§4.3, §6 Task C-1, acceptance criterion C4) expected a new test file at this path, but the commit `aa0a08ba` placed the backward-compat + new-param tests inside `test_rate_limit_budget.py` (`TestOneResponseShape` class). The tests exist and cover the same behavior; the file-structure deviation is cosmetic and does not affect coverage.

### Docs and scripts (6 files — all uncommitted)

**8. `docs/01-spec/architecture-structure.md`** (line 220) — Updated the `media_gate` cache security paragraph: `Cache-Control: no-store` → `Cache-Control: public, max-age=86400` on 200 responses; expanded the stale-cache safety discussion to note server-side re-authorization on each request; added "(429 responses still use `Cache-Control: no-store`)". Directly related to Block A. ✓

**9. `docs/99-agent/nginx-rate-limit-attribution-record.md`** — Updated budget references from 60→240 throughout the concept table, criterion table, worked examples, and options-considered matrix. **Critical correction:** Corrected Fact #12 was added, documenting that `media_gate`'s 429 now carries a non-empty SVG body (~159 bytes), breaking the `$body_bytes_sent == 0` Django-origin discriminator. The Deferred successor (§6: add `$limit_req_status` to nginx `log_format`) trigger was expanded to include the non-empty-body case. This is not scope creep — the P-003 fix materially breaks the measurement gate's attribution, so the record must be corrected. ✓

**10. `docs/ops/dev-nginx-media-gate.md`** — Budget table updated from "60 requests / 60 s" to "240 requests / 60 s" (line 100); the 429-ambiguity caveat (line 102–105) updated to keep the burst probe total "strictly below" 240 instead of 60. Directly related to Block B. ✓

**11. `scripts/measure-nginx-rate-limit-keys.py`** (line 42) — `MEDIA_BUDGET` updated from `60` to `240`; the explanatory comment (lines 38–40) updated from `R > 60` to `R > 240`. The script's attribution logic is unchanged — it still uses the one-sided `$body_bytes_sent == 0` test (now documented as broken in the attribution record). ✓

**12. `scripts/verify-nginx-media-limits.ps1`** — All 9 budget references updated from 60→240 (the `.IMPORTANT` block at lines 30–38, the env-var help at lines 67–70, the burst-probe guard at lines 386–395, and the success message at line 393). **Minor formatting issue:** The burst-probe `if` block (lines 386–395) gained 4-space indentation relative to the surrounding top-level code — a cosmetic inconsistency in PowerShell (indentation is non-significant). This does not affect execution.

**13. `src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py`** — Added a known-stale annotation block (lines 14–23) explaining that the `$body_bytes_sent == 0` discriminator is broken after commit `cb798afa` because `media_gate` 429s now return a non-empty SVG body. The synthetic test lines still use `body_empty=True` for Django-origin by convention, with a comment clarifying they test the aggregator's attribution logic, not the live response shape. This is a known limitation with a deferred successor. ✓

---

## 3. Test Quality Assessment

**Strengths:**
- **Behavioral coverage, not just constant assertions.** `test_burst_over_budget_is_refused` (line 950) exhausts the real rate limiter through the HTTP layer and asserts the 429 shape (Retry-After, SVG body, Content-Type, no-store). `test_429_returns_svg_placeholder` (line 1064) asserts `<svg` in the body and `Content-Type == image/svg+xml` — genuine behavioral checks, not just constant comparison.
- **Budget boundary is exact.** `test_media_gate_budget_allows_ten_page_loads` (line 971) sends exactly `MEDIA_RATE_LIMIT_REQUESTS` (240) requests expecting all 200, then one more expecting 429. Verified against `bump_rate_limit_window` (cache.py:60–90): `cache.add` sets count=1 on the first request, `cache.incr` increments thereafter, and `current <= limit` returns `False` on the 241st (count=241 > 240). The boundary is at 241, matching the test. ✓
- **All 4 serving branches covered.** `TestMediaGateCacheControl` tests staff+DEBUG, staff+prod, non-staff+DEBUG, non-staff+prod, plus 403/404 no-cache-control and `_serve_image` itself.
- **Cross-cutting 429 shape tests.** `TestOneResponseShape` in `test_rate_limit_budget.py` tests the shared builder directly: JSON body, HTML body, no-store on both, Retry-After present/absent, body override, backward compatibility.
- **No stale assertions.** No tracked test file still asserts `60` for MEDIA_GATE, `no-cache`/`no-store` for 200 responses, or absent Retry-After on 429s. The search and autocomplete 429 tests (test_autocomplete.py:152, test_search_view.py:1829) only assert `status_code == 429` and `{"error": "rate_limit"}` — unaffected by the `no-store` addition. ✓

**Gaps:**
- **Circular SVG assertion.** `test_429_returns_svg_placeholder` (line 1079) asserts `_MEDIA_GATE_429_SVG in body` — since `_MEDIA_GATE_429_SVG` is imported from the module under test and is the exact string passed as the body, this is a tautology. The other assertions (`<svg` in body, `Content-Type == image/svg+xml`) are sound, but the constant-is-substring check adds no independent value.
- **No test for `body` param on JSON responses.** The docstring claims `body` is "Ignored for the default JSON shape," but no test verifies this — because the code does NOT actually ignore it (see §5). No caller exercises `json=True, body=...`, so this gap is latent, not active.
- **`test_rate_limit_response.py` was not created.** The plan's acceptance criterion C4 named this file; tests were placed in `test_rate_limit_budget.py` instead. Coverage is equivalent, but the file structure deviates from the plan.
- **`TestMediaGateCacheControl` lacks an autouse cache-clear.** This class has no `_clear_cache` fixture, unlike `TestMediaGateApplicationRateLimit`. Total requests across all tests in the class (~10) are well under the 240 budget, so this is not a practical risk today — but it is a latent test-isolation concern if the class grows.

---

## 4. Scope Creep Check

**All changes are directly related to P-003.** The 13 files fall into two groups:

| Group | Files | Justification |
|---|---|---|
| **Remediation code** (4 commits) | `rate_limit_response.py`, `listings.py`, `enums.py`, `test_rate_limit_budget.py`, `test_media_security.py` | The three work blocks (C, A, B) and their tests. |
| **Uncommitted docs/scripts** (6 files) | `architecture-structure.md:220`, `nginx-rate-limit-attribution-record.md`, `dev-nginx-media-gate.md`, `measure-nginx-rate-limit-keys.py`, `verify-nginx-media-limits.ps1`, `test_measure_nginx_rate_limit_keys.py` | Budget references (60→240) and the Corrected Fact #12 documenting that the SVG-body 429 breaks the `$body_bytes_sent == 0` attribution discriminator. Without these doc/script updates, the deployed-stack measurement gate would silently VOID on a healthy stack — a direct consequence of the P-003 fix. |
| **Uncommitted comment** (1 file) | `listings.py:57` | A single comment line updating "60 requests / 60 s" → "240 requests / 60 s" to match the code. |

No unrelated refactoring, no feature creep, no formatting churn beyond the one noted indentation inconsistency in the PowerShell script.

---

## 5. Known Limitations

### 5.1 — `$body_bytes_sent == 0` discriminator is broken (DOCUMENTED, DEFERRED)
Commit `cb798afa` made `media_gate` 429 responses return a non-empty SVG body (~140–159 bytes). The deployed-stack measurement gate (`scripts/measure-nginx-rate-limit-keys.py`, `docs/99-agent/nginx-rate-limit-attribution-record.md` §Corrected Fact #12) relies on `$body_bytes_sent == 0` to identify Django-origin 429s. Non-empty bodies are now misclassified as nginx-origin candidates, producing false `attribution_delta != 0` and **VOID** results on a healthy stack. This is documented as a known stale annotation in `test_measure_nginx_rate_limit_keys.py:14–23`. The deferred successor is to add `$limit_req_status` to nginx's `log_format main` (attribution record §6), collapsing attribution to the single-channel exact form `429 AND $limit_req_status == REJECTED`. **This is not a blocker for P-003** — it is a measurement-gate concern with an explicit successor and trigger.

### 5.2 — `body` parameter is a latent footgun for JSON callers (LOW)
The `rate_limited_response` docstring (line 47) states `body` is "Ignored for the default JSON shape unless explicitly set," but the code (line 62) applies `response.content = body` unconditionally — if a future caller invokes `rate_limited_response(json=True, body="<svg>")`, the JSON body `{"error": "rate_limit"}` is replaced with the SVG string while `Content-Type` remains `application/json`. No current caller does this (only `media_gate` passes `body`, and it passes `json=False`). The plan §6 acknowledges this risk. **Recommended fix:** either enforce the documented contract (guard `body` with `if not json`) or correct the docstring.

### 5.3 — SVG omits `role="img"` and `aria-label` (INTENTIONAL DEVIATION)
The plan §4.3 specified `role="img" aria-label="Image unavailable"` in the SVG. The implementation omits both. The `<img>` tag in `ad_list.html` already carries `alt="{{ ad|get_title:LANGUAGE_CODE }}"`, so screen readers have a semantic label. The `aria-label` was also an English string that would complicate the i18n gate. This is a sound trade-off, but it is not documented as a plan deviation in the audit trail.

### 5.4 — `immutable` omission on 200 responses is correct
The plan and implementation both correctly omit `Cache-Control: immutable` on 200 responses. Image keys are UUID v4 (uploads) or fixed `seed/<filename>.jpg` names — NOT content-addressed. Seed files are regenerated with `WriteMode.REPLACE` at the same URL (seed/generators/images.py:333), so `immutable` would cause stale cached bytes to be served. `public, max-age=86400` allows natural expiry. ✓

### 5.5 — Retry-After value is the full window period (60s), not a sub-window estimate
`media_gate` passes `retry_after=MEDIA_RATE_LIMIT_PERIOD` (60) as the `Retry-After` header value. This follows the `DbLockTimeoutMiddleware` precedent (db_lock_timeout.py:36: `_RETRY_AFTER_SECONDS = 30` for a 10s lock timeout). The value is a safe upper bound: the rate-limit counter TTL is set to `period` (60s) via `cache.add(key, 1, timeout=period)` (cache.py:80), so after 60 seconds the counter expires and a retry will be allowed. The client may wait longer than necessary in the common case (the counter may have been set by an earlier request), but never shorter than needed. This is standard practice for fixed-window rate limiters. ✓

---

## 6. Required Fixes

| # | File | Issue | Severity |
|---|---|---|---|
| 1 | `rate_limit_response.py:47` | Docstring says `body` is "Ignored for the default JSON shape unless explicitly set" but the code applies it unconditionally. **Correct the docstring** to state: "When given, overrides the response content. Note: for JSON responses, overriding the body while the Content-Type remains `application/json` will produce a non-JSON payload — callers should pass `json=False` with a `body`, or omit `body` when using the JSON shape." Alternatively, enforce the contract with `if body is not None and not json: response.content = body`. | BEST-PRACTICE |
| 2 | `test_media_security.py:1079` | `test_429_returns_svg_placeholder` asserts `_MEDIA_GATE_429_SVG in body` — a circular check (the constant is the exact string passed to the builder). Add an independent assertion on the SVG structure (e.g., `assert 'fill="#e5e7eb"' in body` or `assert '240" height="180"' in body`) so the test validates the content, not just its presence. | BEST-PRACTICE |

---

## 7. Advisory Recommendations

1. **Create `test_rate_limit_response.py` as planned.** The plan's file structure (C4 acceptance criterion) expected a dedicated test file for the shared builder. The tests currently live in `test_rate_limit_budget.py::TestOneResponseShape`. Splitting them out would improve test discoverability and match the plan's intent.

2. **Guard the `TestMediaGateCacheControl` class with an autouse cache-clear fixture.** Although the current 10-request-per-class total is far below the 240 budget, adding `@pytest.fixture(autouse=True)` to clear the cache would prevent a latent test-isolation bug if the class grows.

3. **Add `role="img"` to the SVG.** While `aria-label` was justifiably omitted (i18n concern), `role="img"` carries no translatable text and provides a semantic hint when the SVG is rendered standalone (e.g., in a developer tool or error page). Low effort, marginal benefit.

4. **Address the `$body_bytes_sent == 0` discriminator degradation (P-22 follow-up).** The deferred successor (`$limit_req_status` in nginx `log_format`) should be prioritized as a P-22 task, since the P-003 fix has already invalidated the current discriminator.

---

## 8. Recommendation: **ACCEPT AS-IS**

The P-003 remediation is correct, well-tested, architecturally consistent with existing patterns (`DbLockTimeoutMiddleware`, `RateLimitBudget` enum), and properly scoped. The four commits are atomic and follow the planned C→A→B ordering. The two required fixes (#1 docstring, #2 test assertion) are minor BEST-PRACTICE issues that do not affect correctness or safety. The known limitation in §5.1 is explicitly documented with a deferred successor and is not a blocker.
