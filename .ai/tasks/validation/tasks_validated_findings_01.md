# Task Specification Validation Report — `order_2.yaml` rollout

**Validator:** validator (per `.kilo/commands/validate/validate-tasks-plan.md`)
**Date:** 2026-07-20
**Plan under review:** `.ai/tasks/todo/order_2.yaml`
**Findings base:** `.ai/audit/99-validation/01-..-11-*.md` (11 validated-findings reports)
**Tasks reviewed:** 75 active task files (`TASK_001`..`TASK_075`) + 5 research gates

---

## 1. Executive Summary

**Verdict: APPROVED WITH CORRECTIONS (no blocking defects).**

The `order_2.yaml` plan correctly accounts for **every validated/mandatory finding** across all 11 audit phases. All `REJECTED` / `MERGED` findings are correctly excluded from the plan (no dedicated tasks), and all `DOC-UPDATE` (reclassified) findings are handled as documentation/config changes rather than inappropriate code rewrites. Dependency edges are acyclic, topologically sorted, and the research gates correctly block their dependent implementation tasks.

Two stale task files from the superseded `order.yaml` plan were found in the `todo` folder with ID collisions against the active `task_008` / `task_009`; they were renamed to `*_REJECTED.yaml` (history preserved, collision removed).

**Coverage:** 75/75 active tasks map to at least one validated finding. Zero mandatory validated finding is left without a task. Residual advisory gaps are documented in §6–§8.

---

## 2. Findings → Task Coverage Matrix

### Phase 01 — Entry / Process Architecture
| Finding | Status | Type | Task | Decision |
|---------|--------|------|------|----------|
| ENT-001 | VALIDATED | SPEC-DEVIATION | task_006 | ✅ covered |
| ENT-002 | VALIDATED | SPEC-DEVIATION | task_007 | ✅ covered |
| ENT-003 | VALIDATED | SPEC-DEVIATION | task_014 | ✅ covered |
| ENT-004 | VALIDATED | SPEC-DEVIATION | task_015 | ✅ covered |
| ENT-005 | **REJECTED** | — | — | ✅ correctly excluded |
| ENT-006 | **REJECTED** (merged→ENT-001) | — | — | ✅ covered by task_006 |
| ENT-007 | reclassified DOC→SPEC | SPEC-DEVIATION | task_006 | ✅ covered (boot/package) |

### Phase 02 — Config / Secrets
| CFG-001 | reclassified DOC-UPDATE | DOC-UPDATE | task_012 | ✅ covered (delete orphan) |
| CFG-002 | VALIDATED | SPEC-DEVIATION | task_009 | ✅ covered |
| CFG-003 | VALIDATED | SPEC-DEVIATION | task_008 | ✅ covered |
| CFG-004 | **REJECTED** | — | — | ✅ correctly excluded |
| CFG-005 | VALIDATED | BEST-PRACTICE (advisory) | — | ⚠️ **gap — see §6** |
| CFG-006 | VALIDATED | DOC-UPDATE | task_011 | ✅ covered |

### Phase 03 — DB / Concurrency
| DB-001 | VALIDATED | SPEC-DEVIATION | task_018 | ✅ covered |
| DB-002 | VALIDATED | CRITICAL SPEC-DEVIATION | task_017 | ✅ covered |
| DB-003 | VALIDATED | BEST-PRACTICE | task_020 | ✅ covered |
| DB-004 | VALIDATED | BEST-PRACTICE | task_019 | ✅ covered |
| DB-005 | **MERGED**→DB-002 | — | — | ✅ covered by task_017 |

### Phase 04 — Auth / Login
| AUT-001 | VALIDATED | CRITICAL SPEC-DEVIATION | task_025 | ✅ covered |
| AUT-002 | VALIDATED | SPEC-DEVIATION | task_026 | ✅ covered |
| AUT-003 | VALIDATED | SPEC-DEVIATION | task_027 | ✅ covered |
| AUT-004 | reclassified→DOC-UPDATE | DOC-UPDATE | task_029 | ✅ covered |
| AUT-005 | **REJECTED** (missing integration) | — | — | ✅ correctly excluded |
| AUT-006 | VALIDATED | SPEC-DEVIATION | task_026 | ✅ covered (consumed_at fix) |

### Phase 05 — Ad Lifecycle
| AD-001 | APPROVED | CRITICAL SPEC-DEVIATION | task_030 | ✅ covered |
| AD-002 | **REJECTED** (stale; method exists) | — | — | ✅ correctly excluded (residual wiring noted §7) |
| AD-003 | APPROVED | SPEC-DEVIATION | task_031 | ✅ covered |
| AD-004 | APPROVED | BEST-PRACTICE | task_024 | ✅ covered |
| AD-005 | **REJECTED** (negative ROI) | — | — | ✅ correctly excluded |

### Phase 06 — PII / Consent
| PII-001 | VALIDATED | CRITICAL SPEC-DEVIATION | task_034 | ✅ covered |
| PII-002 | VALIDATED | CRITICAL SPEC-DEVIATION | task_035 | ✅ covered |
| PII-003 | VALIDATED | SPEC-DEVIATION | task_036 | ✅ covered |
| PII-004 | VALIDATED | SPEC-DEVIATION | task_039 | ✅ covered |
| PII-005 | VALIDATED | BEST-PRACTICE | task_040 | ✅ covered |
| PII-006 | reclassified DOC-UPDATE | DOC-UPDATE | task_041 | ✅ covered |
| PII-007 | VALIDATED | BEST-PRACTICE | task_037 | ✅ covered |
| PII-008 | VALIDATED | BEST-PRACTICE | task_042 | ✅ covered |
| PII-009 | VALIDATED | BEST-PRACTICE | task_043 | ✅ covered |
| PII-010 | VALIDATED | BEST-PRACTICE | task_038 | ✅ covered |

### Phase 07 — Media
| MED-001 | VALIDATED | CRITICAL SPEC-DEVIATION | task_044 | ✅ covered |
| MED-002 | VALIDATED | CRITICAL SPEC-DEVIATION | task_016 | ✅ covered |
| MED-003 | VALIDATED | SPEC-DEVIATION | task_045 (+021,039,024) | ✅ covered |
| MED-004 | VALIDATED | SPEC-DEVIATION | task_024 (+021,045) | ✅ covered |
| MED-005 | VALIDATED | SPEC-DEVIATION | task_022 | ✅ covered |
| MED-006 | VALIDATED | BEST-PRACTICE | task_023 | ✅ covered |
| MED-007 | **REJECTED** | — | — | ✅ correctly excluded |
| MED-008 | VALIDATED | BEST-PRACTICE | task_046 | ✅ covered |

### Phase 08 — Search / FTS
| SRH-001 | VALIDATED | SPEC-DEVIATION | task_047 | ✅ covered |
| SRH-002 | VALIDATED | SPEC-DEVIATION | task_048 | ✅ covered |
| SRH-003 | VALIDATED | SPEC-DEVIATION | task_049 | ✅ covered |
| SRH-004 | reclassified DOC-UPDATE | DOC-UPDATE | task_050 | ✅ covered |
| SRH-005 | VALIDATED | BEST-PRACTICE | task_051 | ✅ covered |
| SRH-006 | VALIDATED | BEST-PRACTICE | task_052 | ✅ covered |
| SRH-007 | VALIDATED | BEST-PRACTICE | task_053 | ✅ covered |
| SRH-008 | reclassified DOC-UPDATE | DOC-UPDATE | task_050 | ✅ covered |
| SRH-009 | VALIDATED | SPEC-DEVIATION | task_049 | ✅ covered (HTMX partial) |

### Phase 09 — External Integrations
| EXT-001 | VALIDATED | SPEC-DEVIATION | task_025 (==AUT-001) | ✅ covered |
| EXT-002 | VALIDATED | RUNTIME-ERROR | task_028 | ✅ covered |
| EXT-003 | VALIDATED | RUNTIME-ERROR | task_015 (==ENT-004) | ✅ covered |
| EXT-004 | VALIDATED | SPEC-DEVIATION | task_056 | ✅ covered |
| EXT-005 | VALIDATED | BEST-PRACTICE | task_054 | ✅ covered |
| EXT-006 | VALIDATED | SPEC-DEVIATION | task_055 | ✅ covered |
| EXT-007 | VALIDATED | RUNTIME-ERROR | task_014 (==ENT-003) | ✅ covered |
| EXT-008 | VALIDATED | SPEC-DEVIATION | task_010 | ✅ covered (see §7 re ENT-005) |
| EXT-009 | VALIDATED | BEST-PRACTICE | task_057 | ✅ covered |
| EXT-010 | VALIDATED | BEST-PRACTICE | task_058 | ✅ covered |

### Phase 10 — Code Quality
| QLT-001 | VALIDATED | SPEC-DEVIATION | task_030 (==AD-001) | ✅ covered |
| QLT-002 | VALIDATED | SPEC-DEVIATION | task_032 | ✅ covered |
| QLT-003 | VALIDATED | SPEC-DEVIATION | task_030 (auto-resolved) | ✅ covered |
| QLT-004 | VALIDATED | BEST-PRACTICE | task_033 | ✅ covered |
| QLT-005 | VALIDATED | BEST-PRACTICE | task_037 (==PII-007) | ✅ covered |
| QLT-006 | VALIDATED | BEST-PRACTICE | task_013 | ✅ covered |

### Phase 11 — Test Coverage
| TST-001 | VALIDATED | BEST-PRACTICE | task_061 | ✅ covered |
| TST-002 | VALIDATED | BEST-PRACTICE | task_062 | ✅ covered |
| TST-003 | VALIDATED | BEST-PRACTICE | task_060 | ✅ covered |
| TST-004 | VALIDATED | BEST-PRACTICE | task_063 | ✅ covered |
| TST-005 | VALIDATED | BEST-PRACTICE | task_064 | ✅ covered |
| TST-006 | VALIDATED | BEST-PRACTICE | task_065 | ✅ covered |
| TST-007 | VALIDATED | BEST-PRACTICE | task_066 (+046) | ✅ covered |
| TST-008 | VALIDATED | BEST-PRACTICE | task_059 | ✅ covered |
| TST-009 | VALIDATED | BEST-PRACTICE | task_067 | ✅ covered |
| TST-010 | VALIDATED | BEST-PRACTICE | task_068 | ✅ covered |
| TST-011 | VALIDATED | BEST-PRACTICE | task_069 | ✅ covered |
| TST-012 | VALIDATED | BEST-PRACTICE | task_070 | ✅ covered |

**Cross-cutting de-duplication verified:** AUT-001/EXT-001 → task_025; ENT-004/EXT-003 → task_015; ENT-003/EXT-007 → task_014; AD-001/QLT-001/QLT-003 → task_030; PII-007/QLT-005 → task_037; SRH-004/SRH-008 → task_050; MED-003/MED-004 → task_021+045+024+039. No finding is double-implemented in conflicting ways.

---

## 3. Approved Tasks

All 75 active tasks are **APPROVED** for execution subject to the corrections/warnings below. They are:
- **YAML-valid** and consistently named (`TASK_<NNN>_<short_name>.yaml` with matching `id:`).
- **One coherent responsibility each** (per-task single concern; no broad rewrites).
- **Symbol/statement-level targeted** (function names, specific statements, docstrings, config tables) — no line-number-based targeting.

Research gates (task_001–task_005) and verification tasks (task_071–task_075) are correctly structured (go/no-go verdicts; multi-step verification with `failure_action` rework pointers).

---

## 4. Rejected Tasks

No active task in `order_2.yaml` is rejected. The plan correctly contains **no task for any REJECTED/MERGED finding** (ENT-005, ENT-006, CFG-004, AUT-005, AD-002, AD-005, MED-007; DB-005 merged into DB-002).

**Two stale files from the superseded `order.yaml` plan were renamed to `*_REJECTED.yaml`** (history preserved, ID collision removed):
- `TASK_008_invalidate_tokens_on_withdraw_REJECTED.yaml` — source is `.ai/plans/architecture_testing_plan.md`, not the audit store; no audit finding requires LoginToken invalidation on withdraw. Collided with active `task_008_bot_token_failfast`.
- `TASK_009_verify_rollout_REJECTED.yaml` — references obsolete task IDs not present in `order_2.yaml`; duplicates the active verification tasks (task_071–task_075). Collided with active `task_009_postgres_password_failfast`.

---

## 5. Dependency Integrity — PASSED

- **Topological order:** every `depends_on` entry has a strictly lower task number. No violations found.
- **No circular dependencies** (verified across all 75 edges).
- **No dangling references:** every `depends_on` target exists in the plan.
- **Research gates block correctly:** task_006←task_001, task_007←task_002, task_034←task_003, task_044←task_004, task_025/026/027/028←task_005 (marked `status: blocked` + `blocked_by`).
- **Shared-file serialization:** multi-task edits to the same file are ordered to avoid collisions — `ad_create.py` (14<15<16<17<24<30), `media.py` (16<21<23), `consent_hard_delete.py` (17<39<45), `deletion.py`/`contact.py` chains. Correct.

---

## 6. Required Corrections (recommended, non-blocking)

**C1 — CFG-005 advisory gap.** `CFG-005` (VALIDATED, BEST-PRACTICE) "no automated tests for config/secret loading surface" has **no dedicated task**. The new fail-fast secret loading in task_008 (BOT_TOKEN) and task_009 (POSTGRES_PASSWORD) is unguarded by tests. Recommended: add a small settings-loading test task (assert missing `BOT_TOKEN`/`POSTGRES_PASSWORD` raises `ImproperlyConfigured`) OR fold it into task_059/task_068. Advisory only (not mandatory), so not a blocker, but it closes a real regression risk.

**C2 — Clean up stale `todo` artifacts.** Done for the two `*_REJECTED.yaml` files. Confirm no other `order.yaml`-era files remain in `.ai/tasks/todo`.

---

## 7. Semantic Stability Warnings

**S1 — Exact-value anchors (minor).** A few anchors use exact literal values that would break if the source changes:
- task_009 `edit_line: "PASSWORD": os.getenv("POSTGRES_PASSWORD", "")` (base.py)
- task_011 `edit_line: POSTGRES_PASSWORD=111` (.env.dev.example)
- task_006 `insert_after: comment "uv sync --frozen --no-install-project"` (Dockerfile)

These are stable today (confirmed by the audit evidence) and are statement/value-level, not line-number-based, so they are **acceptable** — but implementers should treat them as guidance and fall back to the function/file context if the literal drifts.

**S2 — AD-002 residual wiring (architectural debt, not a plan defect).** AD-002 was rejected as stale (the `Ad.transition_to()` method exists), but the validation note acknowledged it is **unwired**: 13 direct `ad.status = AdStatus.X` assignments remain across `edit.py`, `delete.py`, `admin_actions.py`, `moderation_log.py`. task_030 wires only the bot publish path through the shared service. The remaining scattered assignments are a known debt the validator deferred. Recommend tracking it as a separate future task (outside this plan) — no active task must be added here.

---

## 8. Rollout / Audit-Store Warnings

**R1 — ENT-005 vs EXT-008 contradiction (audit store, not plan).** Phase-01 validator **rejected** the web-restart-policy finding (ENT-005: "production override provides it"), while Phase-09 validator **validated** the identical issue (EXT-008: "base `docker compose up` runs without the policy"). The plan follows EXT-008 (includes task_010). This is the **defensible and correct** choice — the base compose genuinely lacks the restart policy and the audit contradiction should be reconciled in `.ai/audit/99-validation` (recommend re-classifying ENT-005 to align with EXT-008). No plan change needed.

**R2 — `depends_on` used for serialization, not just true prerequisites (minor).** A few edges are conservative serialization conveniences rather than strict semantic prerequisites:
- task_017 (atomic domain writes) ← task_016 (exif strip): functionally independent; chained to avoid `ad_create.py` collisions.
- task_009 (postgres password) ← task_008 (bot token): independent; chained for wave grouping.

Both are harmless and conservative (no correctness risk, only minor serialization). Acceptable, but noted so reviewers do not mistake them for hard prerequisites.

**R3 — High-risk verification gating is sound.** The four domain verification tasks (task_071 boot, task_072 login, task_073 media, task_074 PII) and the final integration gate (task_075) correctly aggregate their prerequisites with `failure_action: return … to rework`. Multi-stage/high-risk areas (login flow, media gate, PII cascade) are gated behind explicit verification before `task_075_verify_final`.

---

## 9. Execution Readiness — PASSED

- **Actionable:** every task has concrete `files`, `targets`, `semantic_anchors`, `changes`, and `acceptance_criteria`.
- **Measurable:** acceptance criteria are testable (e.g., "missing BOT_TOKEN raises ImproperlyConfigured", "unpublished photo returns 403/404", "concurrent claims cannot both succeed").
- **Relevant:** no task implements already-implemented behavior; no speculative redesigns.
- **Assumptions still valid:** research gates (task_001–task_005) are the only `status: blocked` items and explicitly require a go/no-go verdict before dependent implementation — this is the correct pre-condition for the boot/bootstrap/PII/media/login gates given the Windows-only audit environment could not execute the Docker stack.

---

## 10. Final Verdict

**APPROVED WITH CORRECTIONS.**
- ✅ All 75 active tasks are valid, scoped, correctly targeted, and acyclic.
- ✅ Every mandatory/validated finding is covered; every rejected/merged finding is correctly excluded; every DOC-UPDATE finding is handled as docs/config.
- ✅ Research gates and verification tasks are correctly structured and gated.
- ⚠️ Apply C1 (CFG-005 test coverage) for completeness; C2 already done.
- ⚠️ Note S1/S2/R1/R2/R3 as advisory awareness items; none block execution.
