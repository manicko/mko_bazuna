# Final Comprehensive Plan Audit — `mko_bazuna` MVP

**Scope:** All 6 plans in `.ai/plans/`
- `01_plan_development_phases.md` (roadmap)
- `01_detailed_plan_publish_discover.md` (Phase 1)
- `02_detailed_plan_moderation.md` (Phase 2)
- `03_detailed_plan_contact_dashboard.md` (Phase 3)
- `04_detailed_plan_analytics_harden.md` (Phase 4)
- `05_detailed_plan_scraping_i18n.md` (Phase 5)

**Method:** Cross-read of all plans against `docs/wiki/01_technical_specification.md`, `02_packages.md`, `03_structure.md`, `04_db_structure.md`, `05_audit_resolutions.md`, and the prior audit `AUDIT_ZONES_01.md` (28 zones C1–C8, R1–R9, D1–D12).

**Result:** ✅ **APPROVE (all plans as a set)** — with 2 LOW-severity advisory findings and spec-coverage gaps noted below. No blocking contradictions, no mandatory-issue regressions.

---

## 1. Prior Audit Mandatory Issues — Resolution Status

The "M1–M4 / A5–A6" mandatory items correspond to the validated zone resolutions in `AUDIT_ZONES_01.md` / `05_audit_resolutions.md`. Each is reflected in the consumed spec/DB docs and implemented by the plans:

| Prior zone (mandatory) | Resolved in spec/DB | Consumed by plan | Status |
|---|---|---|---|
| **C1** LoginToken atomicity | `04_db_structure.md` login_tokens standalone + 2-phase claim | P1 T2, T9 (`hmac.compare_digest`, `select_for_update`) | ✅ |
| **C2/C3** `PUBLISHED→ON_MODERATION` + timer on `published_at` | `04_db_structure.md` transitions + `published_at` reset | P3 T2 (text→re-moderation, hide), P4 T2 sweeps | ✅ |
| **C4/D12** 7-day purge + 3 partial indexes | `IX_ads_purge_failed`, `IX_ads_rejected_sweep`, `GinIndex` | P1 T6 indexes; P2 T4 purge | ✅ |
| **C5** async bot / sync ORM / migrations-once | `02_packages.md`, `03_structure.md` (PgBouncer, `CONN_MAX_AGE=0`, migrate-once) | P1 T8 docker-compose, T9 bot; P4 T3 | ⚠️ (see F2) |
| **C6** ≤5s auto-publish SLA | US-A10 synchronous auto-check | P1 T10 sync service, P2 T1 | ✅ |
| **C7** <2s search SLA / price index | `04_db_structure.md` (no price index, EXPLAIN gate) | P1 T11 FTS; P4 hardening | ✅ |
| **C8** draft lifecycle (FSM, no DRAFT row) | decision I | P1 T9 FSM `SQLStorage`, 30-min idle | ✅ |
| **R1** GDPR hard-delete completeness | `05_audit_resolutions.md` O3 erasure scope | P3 T4 `consent_hard_delete`; P1 T6 `IX_users_erasure_sweep` | ✅ |
| **R2/R3** contact + decline≠withdrawal | decision C/K, `05` O2 safe-default | P3 T1 (render only if PUBLISHED+telegram_id NOT NULL+not banned/deleted/revoked) | ✅ |
| **R4** (O1) three independent states | `05` O1 | P3 T3 account states | ✅ |
| **R5/R6/R8** FK nulling, anonymity, media security | `04_db_structure.md` + `03_structure.md` nosniff/UUIDv4/JPEG | P1 T2 (UUID v4), T8 (nginx nosniff), T9 (JPEG magic bytes) | ✅ |
| **R7** Telethon secrets removed | `03_structure.md` (API_ID/API_HASH deleted) | P5 T2 Telethon only in phase 5 (correctly scoped) | ✅ |
| **R9** re-registration uniqueness | `telegram_id UNIQUE` + 30-day null | P3 T3/T4 | ✅ |
| **D1/D2** category-name search + i18n | `category_name` denorm + `name_i18n` JSONB + `get_name()` | P1 T3, T5; P5 T3 | ✅ |
| **D3/D4** (O4) moderation_criteria + REJECTED 90d | `moderation_criteria` singleton, `IX_ads_rejected_sweep` | P1 T4, T10; P2 T1 | ✅ |
| **D5/D6** Russian-store invariant + true GIN | `GinIndex`, bot translates on create | P1 T9, T5; P5 T5 | ✅ |
| **D7/D9/D10** FSM ownership, category cache, sync WSGI | `03_structure.md` | P1 T8/T9 | ⚠️ (F2) |
| **D8** ModeratorActionLog | schema present | P1 T4, P2 T2 | ✅ |
| **D11** drop `currency` column | `04_db_structure.md` (YAGNI) | P1 T2 (`price INT`, no currency) | ✅ |

**Conclusion:** All prior mandatory findings are resolved or explicitly delegated to the resolved spec/DB docs. No regression.

---

## 2. Cross-Phase Contradiction Check

| Check | Result |
|---|---|
| Roadmap status names vs detailed enums | ⚠️ Roadmap (Phase 1, line 34) writes `ON_Moderation_FAILED` (mixed case); detailed plan P1 T1 defines `ON_MODERATION_FAILED`. Cosmetic mismatch only — same concept. **[LOW]** |
| 7-day purge ownership | ⚠️ P3 T4 restates "7-day purge job … belongs in Phase 2 Task 4" — correct attribution but P3 re-lists it as its own artifact, implying duplicate implementation. Should be marked cross-phase reference only. **[LOW]** |
| `delete_sweep` semantics (P4 T2) | P4 T2 says `delete_sweep: 4 months → DELETED (then hard-delete after 30 days consent revocation)`. The parenthetical conflates ad-lifecycle delete (4mo, US-A5) with consent hard-delete (30d, R1) — two distinct sweeps. Wording misleading, not a logic error. **[LOW / DOC]** |
| `AdSource` extension | P1 defines `AdSource: TELEGRAM` only; P5 T1 extends to `TELEGRAM_SCRAPED`. P5 explicitly notes "extend AdSource enum" — consistent. ✅ |
| Dependency graph | Roadmap: P1→P2→P3→P4→P5. Detailed plans: P3 `Depends_on: Phase 1` (not P2); P4 `Depends_on: Phases 1-3`; P5 `Depends_on: Phase 1 + Phase 2`. All consistent with roadmap ordering. ✅ |
| Logout / session-idle in spec decision H ("long idle") | No plan task implements session idle-timeout expiry. Minor — decision H says "until explicit logout or long idle"; not critical for MVP. |

No blocking cross-phase contradictions found.

---

## 3. Spec Coverage (US-S*, US-B*, US-A*)

> Note: the spec defines seller stories **S1, S2, S5, S6, S7, S8, S9** (no S3/S4/S10/S11 — the audit request's "S1..S11" over-enumerates; actual spec stops at S9). Audit maps against the real spec.

| Story | Coverage | Notes |
|---|---|---|
| US-S1 | ✅ | P1 T1/T2/T8/T9 |
| US-S2 | ✅ | P1 T9 |
| US-S5 | ✅ | P3 T2 |
| US-S6 (delete ad) | ⚠️ Partial | Soft-delete status exists (P1 T1 enum) + admin (P2 T3); no explicit seller "delete my ad" dashboard task. **Gap (advisory).** |
| US-S7 | ✅ | P4 T2 archive_sweep |
| US-S8 | ✅ | P3 T3/T4 |
| US-S9 | ✅ | P3 T3 |
| US-B1 | ✅ | P1 T11 |
| US-B2 | ✅ | P1 T11 (FTS + translation) |
| US-B3 | ✅ | P1 T11 |
| US-B4 | ✅ | P1 T11 templates |
| US-B5 | ✅ | P3 T1 |
| US-B6 | ✅ | P1 T3/T11 |
| US-B7 | ✅ | P1 T3/T11 |
| US-B8 (responsive) | ⚠️ Gap | No plan task mentions responsive/mobile layout. Rides on Tailwind/daisyUI defaults; should be an explicit acceptance criterion. **Advisory.** |
| US-B9 | ✅ | P5 T3 |
| US-A1 | ⚠️ Implicit | Django admin auth assumed; no explicit 2FA/Telegram-admin-role task. Acceptable for MVP. |
| US-A2 | ✅ | P2 T3 |
| US-A3 | ✅ | P2 T2/T3 (ban account) |
| US-A4 | ✅ | P3 T3 (ban/unban) |
| US-A5 | ✅ | P4 T2 |
| US-A6 (inactive users) | ⚠️ Gap | No plan implements inactive-user detection/deletion. **Advisory gap** (deferrable post-MVP). |
| US-A7 (cat/city mgmt) | ⚠️ Partial | Tree admin-editable via Django admin implied (P1 T3); no dedicated admin task. Acceptable. |
| US-A8 | ✅ | P3 T3/T4 |
| US-A9 (logs/events) | ⚠️ Partial | P4 T1 analytics dashboard covers product metrics; no explicit system-log/event admin view. **Advisory gap.** |
| US-A10 | ✅ | P1 T10, P2 T1 |
| US-A11 | ✅ | P2 T1/T2/T3 |

**Coverage verdict:** Core seller/buyer/moderation flows fully planned. Gaps are admin-side niceties (US-S6 seller ad-delete, US-B8 responsive, US-A6 inactive-users, US-A9 logs view, US-A7 explicit admin) — acceptable as MVP-scope deferrals but should be recorded as known out-of-scope so they aren't silently dropped.

---

## 4. Rule Compliance

| Rule | Status | Evidence |
|---|---|---|
| **StrEnum for all constants** (rule 10) | ✅ | P1 T1 defines `AdStatus`, `AdSource`, `AnalyticsEventType`, `ModeratorActionType` as enums in `apps/core/enums.py`; all models import from there. `ModeratorActionLog.action_type` is `StrEnum`. |
| **Small modules / functions** | ✅ | Tasks decompose into `services/moderation.py`, `services/contact.py`, `services/account_state.py`, `services/deletion.py`, `services/translation.py`, `bot/handlers/*`, `ads/views/dashboard.py`. Coherent SRP. |
| **English only** | ✅ | All plan prose, code identifiers, and acceptance criteria are English. |
| **Migrations for schema** (rule 13) | ✅ | Every model task includes "Model files with migrations"; P5 T1 "Phase 5 migration"; triggers via migration file. |
| **Custom errors / no silent swallow** | n/a in plans | Plans are at task level; enforcement belongs to implementation. No contradiction. |
| **Production code is king** | ✅ | Plans follow spec/DB docs (the agreed source of truth), not vice-versa. |

---

## 5. Findings

### F1 — [LOW] Roadmap status-name casing mismatch
- **Where:** `01_plan_development_phases.md` line 34 (`ON_Moderation_FAILED`) vs `01_detailed_plan_publish_discover.md` T1 (`ON_MODERATION_FAILED`).
- **Impact:** Cosmetic; could cause a copy-paste enum error during implementation.
- **Recommendation:** Normalize to `ON_MODERATION_FAILED` in the roadmap. Effort: trivial. Priority: advisory.

### F2 — [LOW] Migration-orchestration & async-binding acceptance criteria not restated in plans
- **Where:** C5/D7 resolutions (migrate-once, `sync_to_async`, `CONN_MAX_AGE=0`, PgBouncer, FSM ownership) live only in `02_packages.md` / `03_structure.md`. Plan tasks (P1 T8/T9, P4 T3) reference Docker/nginx but do **not** list these as explicit acceptance criteria.
- **Impact:** Implementer may miss the mandatory migration-ordering guard and `sync_to_async` wrapping, risking concurrent-migration races and bot-loop blocking — the exact C5 failure mode.
- **Recommendation:** Add to P1 T8 (or a new infra task) explicit acceptance criteria: (a) migrations run exactly once before web+bot via ordering guard; (b) bot ORM/Telegram-blocking I/O wrapped in `sync_to_async`; (c) per-process `CONN_MAX_AGE=0` + PgBouncer transaction mode. Effort: small. Priority: recommended (not blocking — docs already specify it, but plans should pin it).

### F3 — [LOW/DOC] P4 T2 `delete_sweep` wording conflates two sweeps
- **Where:** `04_detailed_plan_analytics_harden.md` Task 2: "delete_sweep: 4 months → DELETED (then hard-delete after 30 days consent revocation)".
- **Impact:** Could mislead an implementer into folding consent hard-delete into the ad-lifecycle sweep. They are independent (US-A5 4mo vs R1 30d).
- **Recommendation:** Split the sentence: ad-lifecycle `delete_sweep` (4mo→DELETED, US-A5) and `consent_hard_delete` (30d after `consent_revoked_at`, R1) as separate bullets. Effort: trivial. Priority: advisory.

### F4 — [ADVISORY] Known spec-coverage gaps (record as out-of-scope)
- **Where:** US-S6 (seller deletes own ad via dashboard), US-B8 (responsive layout AC), US-A6 (inactive-user purge), US-A9 (system-log/event admin view), US-A7 (explicit admin cat/city management task).
- **Impact:** None blocking for MVP; risk is silent scope creep/loss if not logged.
- **Recommendation:** Add a one-line "Deferred / implicit" note per gap in the relevant phase task, or a consolidated "Out of MVP scope" appendix in the roadmap. Effort: small. Priority: advisory.

---

## 6. Decision

**✅ APPROVE all 6 plans as a set.**

Rationale:
1. Every prior mandatory audit finding (C/R/D zone resolutions, incl. the M/A-class items) is resolved in the consumed spec/DB docs and implemented by the plans.
2. No blocking cross-phase contradictions; only 3 LOW-severity cosmetic/clarity issues (F1–F3).
3. Rule compliance confirmed: StrEnum constants, small modules, English docs, migrations-per-change.
4. Spec coverage is comprehensive for all core flows; residual gaps are admin-side MVP deferrals (F4) that do not block the roadmap.

**Conditions (now resolved):**
1. F1 — Fixed: Status name normalized to `ON_MODERATION_FAILED` in roadmap (line 34)
2. F2 — Fixed: Added explicit acceptance criteria in P1 T8 for migration orchestration guard, async safety, and connection pooling
3. F3 — Fixed: Split P4 T2 sweep definitions into separate bullets with spec references (US-A5, R1)
4. F4 — Recorded: Added "Deferred / Out-of-MVP Scope" appendix in roadmap documenting acknowledged gaps

All advisory findings addressed. Plans are ready for development handoff.

