# Test Suite Optimization Plan

## 1. Executive Summary

Suite: 4,396 tests / 270 files (Step 2); ~300s fast gate, ~2,100s Full CI (Step 2). Top bottlenecks: seed runs `call_command("seed")` 8× serial (~1,054s, Step 3 #1); ~47 settings subprocess spawns (10–25s, Step 3 #2); `slow`+migration 60–120s pollute fast gate (Step 3 #3); `PYTEST_OPTS` loses `--reuse-db` (Step 3 #6). 14 optimizations across 3 phases target PR gate ~220–250s, seed ~170s (−83%), Full CI ~900–1,200s (−50–57%); keep-green for search/SLO, submission, moderation, auth/PII, migrations (Step 4).

## 2. Bottlenecks & Evidence

| Rk | Bottleneck | Metric | Source |
|----|-----------|--------|--------|
| 1 | Seed: `call_command("seed")` 8× serial | ~1,054s | Step 3 #1, Step 5 F1 |
| 2 | 4,396 tests / 270 files | Import overhead | Step 2 |
| 3 | ~47 subprocess spawns (settings) | 10–25s | Step 3 #2, Step 5 C1/F2 |
| 4 | `slow` + migration in fast gate | Gate inflated | Step 3 #3, Step 5 S1 |
| 5 | Advisory lock 111 (schema setup) | Worker barrier | Step 3 #4 |
| 6 | 6 concurrent classes unpinned | Deadlock/flaky | Step 3 #5, Step 5 P3/P4 |
| 7 | `PYTEST_OPTS` loses `--reuse-db` | Re-build schema | Step 3 #6, Step 5 G3 |
| 8 | `--cov` always-on | Overhead | Step 3 #7, Step 5 G2 |

## 3. Test Taxonomy Summary

| Domain | Type | Risk | Speed | Gate |
|--------|------|------|-------|------|
| Ads search/SLO/filters | Integration | **Critical** | Slow | PR SLO gate |
| Ads submission/moderation/lifecycle | Integration | High | Slow (seed) | Keep-green |
| Auth/Consent/PII | Integration | **Critical** | Med | Keep-green |
| Migration reproducibility | Integration | High | Slow | Keep-green |
| Settings (subprocess) | Unit-marked | Med | Slow | Fast gate after fix |
| Bot↔Telegram contract | Integration | Low (intentional) | Med | Gap accepted |
| Payments/Fraud | N/A | — | — | Gap (no app) |
| Concurrency (6 cls) | TRUNCATE | High (deadlock) | Slow | Pin + rerun |

## 4. Recommended Optimizations

| Name | Risk | Effort | Impact | Phase |
|------|------|--------|--------|-------|
| S1: PR `not (seed or slow or real_images)` | Low | 1 | Excl. slow | 1 |
| G3: Merge `PYTEST_OPTS` w/ defaults | Low | 2 | Keep `--reuse-db` | 1 |
| P3: Pin 6 concurrent w/ `xdist_group` | Med | 2 | Deadlock fix | 1 |
| L2: Cap `--maxprocesses=4` | Low | 1 | Stability | 1 |
| C1: `no_cover` on 8 settings tests | Low | 1 | Branch off | 1 |
| P4: `reruns=1` on concurrent | Low | 1 | Flake ↓ | 1 |
| F3: Reclassify 3 + `test_session_policy` | Low | 2 | Correct | 1 |
| F1: Class-scoped seed fixture | Med | 3 | Seed −83% | 2 |
| F2: Shared subprocess-probe fixture | Low | 2 | Settings save | 2 |
| G2: `--cov` off PR gate | Low | 1 | PR ↓ | 2 |
| G4: Nightly (seed/slow/real_images) | Low | 3 | Off-peak | 2 |
| SLO gate: `-k TestSearchResponseSLORegression` job | Low | 2 | <3 min | 2 |
| Full CI: serial seed + parallel non-seed | Low | 2 | Parallel | 3 |
| G1: Strict branch coverage (Full+Nightly) | Low | 1 | Retention | 3 |

## 5. Target Suite Definitions

| Suite | Markers | xdist | Coverage | Target |
|-------|---------|-------|----------|--------|
| PR fast gate | `-m "not (seed or slow or real_images)" -k "not TestSearchResponseSLORegression"` | loadgroup max4 | None | ~220–250s |
| PR SLO gate | `-k TestSearchResponseSLORegression` | auto | None | <3 min |
| Full CI | `-m "not seed"` (par) + `-m seed` (ser) | loadgroup max4 | On | ~900–1,200s |
| Nightly | all incl. slow/real_images/seed | loadgroup max4 | Strict | ~1,050s |

## 6. Implementation Roadmap

**Phase 1 (immediate):** S1 filter; G3 merge `PYTEST_OPTS`; P3 `xdist_group`; L2 cap max4; C1 `no_cover`; P4 reruns; F3 reclassify. *Impact:* gate ~300s→~220–250s; concurrency stable.

**Phase 2 (structural):** F1 class-scoped seed → seed ~170s; F2 shared subprocess fixture; G2 drop `--cov` PR gate; G4 nightly; SLO gate job. *Impact:* seed −83%; Full CI ~900–1,200s.

**Phase 3 (hardening):** serial seed + parallel non-seed Full CI split; G1 strict coverage Full+Nightly; verify keep-green across suites.

## 7. Expected Impact Summary

| Suite | Before | After | Δ |
|-------|--------|-------|---|
| PR fast gate | ~300s | ~220–250s | −17–25% |
| PR SLO gate | embedded | <3 min | New |
| Seed | ~1,054s | ~170s | −83% (F1) |
| Full CI | ~2,100s | ~900–1,200s | −50–57% |
| Nightly | — | full+slow+strict | New |

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| `--dist worksteal` breaks `xdist_group` (Step 3 HIGH) | `loadgroup` + P3 pinning |
| Lock 111 serializes setup (Step 3 #4) | `--reuse-db` (G3) + `loadgroup` (P3) |
| TRUNCATE deadlocks (Step 3 #5) | P3 + P4 reruns |
| F1 scope change breaks seed coverage | Re-verify `TestSeedFilterCoverage` Full CI |
| `PYTEST_OPTS` merge regression | Validate `-e PYTEST_OPTS="-k foo" test` |
| PR `--cov` removal hides regressions | SLO gate + Full CI retain coverage |

## 9. Validation & Measurement Plan

- **Baseline:** 4,396 node IDs + per-suite wall times (Step 2).
- **Phase 1:** gate <250s; concurrent OK under `loadgroup`; `--reuse-db` preserved.
- **Phase 2:** seed ≤180s; settings spawns ≤1/file.
- **Phase 3:** Full CI <1,200s; nightly clean.
- **Keep-green:** search/SLO, submission, moderation, auth/PII, migrations green all suites (Step 4).
- **Flake tracking:** rerun logs + deterministic `loadgroup`.

## 10. Accepted Gaps & Marker Discipline

**Accepted gaps:** Payments/Fraud (no app, Step 4); Bot↔Telegram mocked contract not e2e (Step 4); DB i18n exempt (env instructions).

**Markers** (register in `pyproject.toml`, Step 1): `seed` serial-only; `slow`/`real_images` excluded PR gate; `no_cover` opt-out (Step 5 C1); `concurrent` pinned + `reruns=1` (Step 5 P3/P4); unmarked = fast keep-green.
