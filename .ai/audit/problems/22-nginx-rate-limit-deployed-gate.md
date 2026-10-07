# Audit Report — Plan 22: nginx-rate-limit-deployed-gate

**Date:** 2026-10-07
**Plan:** `.ai/plans/done/22-nginx-rate-limit-deployed-gate_fix.md` (moved from `.ai/plans/`)
**Verdict:** NOT FULLY EXECUTED — code changes required → mark `_fix`

---

## 1. Execution summary

| Work Item | Status | Code changes needed? |
|---|---|---|
| WI-1 (aggregator script + tests + fixture) | PARTIALLY DONE | **YES** — `peak_seconds` dead code (AC1.2), missing tests (AC1.5, AC1.6) |
| WI-2 (runbook) | PARTIALLY DONE | Doc only — missing §6.2 fallback (AC2.2), §6.3 window selection (AC2.1), §6.4 plumbing probe (AC2.4) |
| WI-3 (correction of record for 77c1653) | **NOT DONE** | Doc only — `## Correction of record` absent from runbook (AC3.1) |
| WI-4 (docker-deployment.md cross-ref fix) | PARTIALLY DONE (over-scoped) | Doc only — anchor not removed (AC4.1), table changed (AC4.2), 4 hunks vs 2 (AC4.4) |

Files created (existence verified):
- `scripts/measure-nginx-rate-limit-keys.py` — exists
- `src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py` — exists (12 tests pass)
- `src/backend/apps/seed/tests/fixtures/nginx_media_capture.txt` — exists
- `docs/ops/ops-nginx-rate-limit-gate.md` — exists

Code checks: `uv run ruff check` — "All checks passed!" ✓; `basedpyright` — "0 errors, 0 warnings, 0 notes" ✓; 12 unit tests via Docker test service — "12 passed in 2.46s" ✓. Script runs on fixture with exit 0 ✓; output contains no `PASS`/`FAIL`/`VERDICT` token ✓ (AC1.3, verified by grep).

**Runtime commands used (Docker test service):**
- `\.\Makefile.ps1 test` equivalent: `docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm -e PYTEST_OPTS="src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py --tb=short -v" test` → **12 passed**
- Local script execution: `Get-Content fixtures/nginx_media_capture.txt | python3 scripts/measure-nginx-rate-limit-keys.py` → exit 0, correct metric values matching test expectations

---

## 2. Code problems (require code changes)

### 2.1 `peak_seconds` is dead code — CRITICAL

**File:** `scripts/measure-nginx-rate-limit-keys.py` (line 242)
**Function signature** (line 242): `def peak_seconds(key: str, events: Iterable[AccessEvent], width_seconds: int) -> dict[str, int]:`

The function `peak_seconds` is defined but **never called** from `compute_metrics` or `main`. The plan's §5.3 lists `peak_seconds(key, events, 1)` as a metric to compute (1-second sub-bucket). The function's return value is never included in the metrics dict emitted by `compute_metrics`.

**Violates:**
- AC1.2: "Output contains every metric named in §5" — `peak_seconds` is named in §5.3 but absent from output.
- AC1.6: "Unit tests cover ... `peak_seconds` at the 1-second sub-bucket" — no test possible since the function is never invoked.

**Fix:** Call `peak_seconds` from `compute_metrics` for each rejecting key and include the result in the metrics dict.

### 2.2 Missing direct unit tests — HIGH

**File:** `src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py`

AC1.6 requires unit tests covering: `parse_access_line`, `parse_error_line`, `histogram` bucket edges, `peak_seconds`, `attribute_media_429`, `keys_over_media_budget`, `burst_regime`.

Current coverage:
| Function | Direct test? | Indirect (via run_aggregate) |
|---|---|---|
| `parse_access_line` | YES (test 6) | — |
| `parse_error_line` | NO | YES (via summarize) |
| `histogram` | NO | YES (via compute_metrics) |
| `peak_seconds` | NO | NO (dead code) |
| `attribute_media_429` | YES (tests 1-4, 6) | — |
| `keys_over_media_budget` | YES (test 8) | — |
| `burst_regime` | NO | YES (via compute_metrics) |

Missing direct tests for `histogram` (bucket edge assertions: 1–5, 6–24, 25–48, >48), `peak_seconds`, `burst_regime`, and `parse_error_line` with specific assertions.

### 2.3 Missing test for AC1.3 — MEDIUM

No test asserts that the script's output contains no `PASS` / `FAIL` / `VERDICT` token (the tripwire requirement in AC1.3). The script's `render()` function does not emit these tokens, but there is no mechanical test guarding against regression.

### 2.4 Missing test for AC1.5 — MEDIUM

No test for determinism (two runs on the same fixture produce identical bytes). The only related test is `test_crlf_capture_parses_identically`, which checks CRLF vs LF equivalence — not same-input determinism.

---

## 3. Documentation problems (in `docs/ops/`)

### 3.1 Runbook missing §6.2 `awk`/`grep`/`sort`/`uniq` fallback — HIGH

**File:** `docs/ops/ops-nginx-rate-limit-gate.md` (lines 42–43)
**WI-2 AC2.2:** "The `python3` precheck is **step 1** and the `awk`/`grep`/`sort`/`uniq` fallback is present and complete enough to produce a verdict-eligible summary unaided."

Current state (lines 42–43):
> Also confirm `command -v python3` on the host. **This is still unverified** — if `python3` is absent,
> the aggregator cannot run and a complete enough fallback summary must be produced another way.

**Problems:**
1. The step is titled "Step 0 — environment precheck" (line 31), not "Step 1 — python3 precheck" as AC2.2 requires.
2. `command -v python3` is mentioned but **no `awk`/`grep`/`sort`/`uniq` fallback commands** are given, even though the runbook itself says "a complete enough fallback summary must be produced another way" — yet provides none.
3. The plan's §6.2 specifies the fallback must produce: key count, `/media/` request count, 429 count, empty-vs-non-empty-body split, error-line `/media/` count, `attribution_delta`, and `keys_over_media_budget` — none of which appear.

### 3.2 Runbook missing §6.3 (window selection) — HIGH

**File:** `docs/ops/ops-nginx-rate-limit-gate.md` (lines 60–61)
**WI-2 AC2.1, AC2.2:** The plan's §6.3 requires window selection guidance: ≥ 7 consecutive days, 2 weekends, diurnal audience, retrospective not scheduled, record timezone.

Current state (lines 60–61):
> Pick `<t0>` and `<t1>` to cover a window in which the expected traffic was actually driven. The
> window must be long enough for at least one client key to exceed the exposure precondition.

**Problems:** No mention of ≥7 days, weekend coverage, diurnal pattern, retrospective non-scheduling, or timezone recording. The attribution record at `docs/99-agent/nginx-rate-limit-attribution-record.md` §"Verify, do not assume" (item 9) confirms these are required checks.

### 3.3 Runbook missing §6.4 (plumbing probe) — HIGH

**File:** `docs/ops/ops-nginx-rate-limit-gate.md` (entire file — no such section)
**WI-2 AC2.4:** "The plumbing probe is **labelled** as measuring the operator and carries an explicit 'never enters the verdict' instruction."

**Problems:** No plumbing probe section exists anywhere in the 132-line runbook. The plan's §6.4 requires a labelled synthetic burst measuring the operator (single key), explicitly excluded from the VOID/PASS/FAIL criterion.

### 3.4 Runbook missing `## Correction of record` section — HIGH

**File:** `docs/ops/ops-nginx-rate-limit-gate.md` (entire file — no such section)
**WI-3 / AC3.1:** "The correction names both falsehoods and cites the evidence (the `use-nginx` profile block; the N = 1 argument)."

**Problems:** The plan's §4 WI-3 requires a `## Correction of record` section inside the runbook that:
1. Quotes 77c1653 body item 9 verbatim: "Deployed smoke check: NOT performed in this environment. There is no HTTP hop here — the dev project runs no nginx container (only dev-web on :8000)..."
2. States both falsehoods: (a) claims no dev nginx container exists (false — `docker-compose.dev.override.yml` has a `use-nginx` profile at line ~107); (b) the "24-thumbnail page, zero 429s" instruction cannot produce the demanded evidence (false — `NGINX_BURST=45` stays below the application limit of 60).
3. Points at `.ai/plans/22-nginx-rate-limit-deployed-gate.md` as the operative procedure.

This section is completely absent from the 132-line runbook.

### 3.5 `docker-deployment.md` anchor not removed — MEDIUM

**File:** `docs/ops/docker-deployment.md` (line 996)
**WI-4 / AC4.1:** "The `[Client IP Trust Model]` link is gone from the zone-key sentence, or is re-aimed at a heading that genuinely describes the nginx key."

Current state (lines 994–997):
```
> The zone key is the nginx-observed peer address (`$binary_remote_addr`). That is a
> **different** mechanism from the Django-side peer gate described in
> [Client IP Trust Model](#client-ip-trust-model), which governs how *Django* resolves a
> client IP from forwarding headers — see that section for the application-side rules.
```

**Problems:** The disambiguation blockquote is a step in the right direction, but the `[Client IP Trust Model](#client-ip-trust-model)` link still appears in the zone-key sentence, still pointing at the Django-side heading `### Client IP Trust Model` (line 1053). It has not been removed, nor re-aimed at a heading that genuinely describes the nginx key. Neither condition of AC4.1 is met.

### 3.6 `docker-deployment.md` rate-limiting table changed beyond WI-4 scope — LOW

**File:** `docs/ops/docker-deployment.md` (lines 989–1006)
**WI-4 AC4.2:** "The rate-limiting table, the N/N figures, and the 'one shared per-IP bucket' claim are byte-identical to their pre-edit state."
**WI-4 AC4.4:** "git diff --stat for this path shows one file, and its hunk count matches the two intended edits."

**Evidence from `git diff 4ecdd3b6^..4ecdd3b6 -- docs/ops/docker-deployment.md`:** 4 hunks, not the 2 intended for WI-4:

- **Hunk 1** (line ~210): Bind-mount scope correction — "Seven services" → "six services", added `load_cities`/`create_admin`, removed `nginx` — **completely unrelated to WI-4**.
- **Hunk 2** (line ~296): Added cross-link to `dev-nginx-media-gate.md` — **plan 21's deliverable, not WI-4**.
- **Hunk 3** (lines 989–1008): Rate Limiting section — changed "Three" → "Four" zones (line 989), changed `/csp-report/` row from `login_limit 10 req/s 10` to `csp_report_limit 1 req/s 5` (line 1002), added the disambiguation blockquote — **violates AC4.2** (table must be byte-identical).
- **Hunk 4** (line ~1009): Added cross-link to `ops-nginx-rate-limit-gate.md` + attribution record — **this is WI-4's intended cross-link**.

While the bind-mount and table corrections are factually correct, only hunk 4 is in WI-4's scope. AC4.2 and AC4.4 are both violated.

---

## 4. Files not created (still absent)

None of the WI-1/WI-2/WI-3/WI-4 deliverable files are absent — all four exist. The gaps are in test coverage, missing functions in the output, and missing doc sections/content.
