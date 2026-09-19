---
phase: "06"
phase_name: "pii-consent"
date: "2026-09-19"
auditor: "Phase 06 auditor (findings.md)"
validator: "Validator (Phase 99)"
mode: "problems-only"
id_prefix: "PII-"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/06-audit-pii-consent.md#8-severity-taxonomy"
---

# Phase 06 — PII Protection & Consent Compliance — Validation Report

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated | 2 | PII-001, PII-002 |
| Reclassified | 0 | — |
| Merged | 0 | (cross-reference to Phase 04 AUT-001 documented; not merged — see note) |
| Rejected | 0 | — |

### Validated Findings

| ID | Severity | Type | Title | Status |
|----|----------|------|-------|--------|
| PII-001 | CRITICAL | SPEC-DEVIATION | Raw Telegram identifier leaked into bot login rate-limit log | Validated / Resolved |
| PII-002 | LOW | BEST-PRACTICE | Admin list view displays raw `telegram_id` | Validated / Open (advisory) |

## Methodology

Read each cited source verbatim and grepped all `mask_telegram_id` consumers:
- `src/telegram_bot/handlers/login.py:94-102` (rate-limit warning)
- `src/backend/apps/core/utils/sanitize.py:51-67` (`mask_telegram_id`)
- `src/backend/apps/users/views/consent.py:36,415,424,432,447` (web-side masking)
- `src/backend/apps/ads/admin.py:24-32` (admin `user_link`)
- `src/backend/apps/users/services/deletion.py:72-163` (telegram_id nulling on withdraw)
- Cross-checked `.ai/audit/04-auth-login/findings.md` + `.../99-validation/04-auth-login-validated-findings.md` for the AUT-001 overlap.

## Findings by Severity

### CRITICAL

> **Validation Note — PII-001**
> - **Action:** validated
> - **Detail:** `src/telegram_bot/handlers/login.py:95-98` emits `logger.warning("Login rate limit exceeded for telegram_id=%s", message.from_user.id)` with the **raw** `message.from_user.id`. The handler (imports `apps.core.enums`, `apps.core.services.analytics`, `apps.core.services.site_config`, `apps.users.models`, `telegram_bot.*`) never imports or calls `mask_telegram_id`. `mask_telegram_id` is confirmed present at `apps/core/utils/sanitize.py:51` (`def mask_telegram_id(telegram_id: int | None) -> str`, returns `tg_<sha256[:8]>`, non-reversible, stable) and is already the established control in `consent.py` (4 call sites), `contact.py:134`, `create_admin_user.py`, `admin_actions.py:88`. `telegram_id` is the external auth identifier — "the only PII per §2 Identity+PII." Per Phase 06 §8, raw-identifier PII in logs is CRITICAL. Evidence matches verbatim; defect is real.
> - **Citation tidiness (advisory, non-fatal):** findings.md cites the web control at `consent.py:413,423,431,445`; the actual masking call sites are `415,424,432,447` (off by 2). The control is present and the import is at line 36 — substance unaffected.
> - **Cross-phase (see Cross-Reference section):** identical defect to Phase 04 AUT-001 on the **same code line**; AUT-001 validated LOW in the auth phase (no PII bucket in that taxonomy). Under Phase 06's PII taxonomy the same violation is CRITICAL — not a disagreement, a taxonomy-scope difference. Remediation is identical.

#### PII-001: [CRITICAL] — Raw Telegram identifier leaked into bot login logs

| Field | Value |
|---|---|
| **ID** | PII-001 |
| **Severity** | CRITICAL |
| **Type** | SPEC-DEVIATION (violates Phase 06 §5d "logs/tracebacks must contain no raw identity values" + technical spec "Raw telegram_id must never appear in logs") |
| **File(s)** | `src/telegram_bot/handlers/login.py:95-98` (emit); `src/backend/apps/core/utils/sanitize.py:51` (control exists, unused by bot) |
| **Status** | Resolved (code applied via commit `5b5bb0a`) |
| **Problem** | `handle_login_deep_link`'s rate-limit-exceeded branch logs the raw `message.from_user.id` (the external auth identifier / only PII) with no `mask_telegram_id` wrap and no import of it, while the matching web path (`consent.py:415/424/432/447`) consistently masks the same value. |
| **Evidence — `login.py:95-98`** | ```python\nlogger.warning(\n    "Login rate limit exceeded for telegram_id=%s",\n    message.from_user.id,\n)\n``` (verbatim match; no `sanitize` import in file header) |
| **Evidence — `sanitize.py:51`** | ```python\ndef mask_telegram_id(telegram_id: int | None) -> str:\n    ...\n    return f"tg_{hashlib.sha256(tid.encode()).hexdigest()[:8]}"\n``` (non-reversible, stable) |
| **Evidence — `consent.py:415,424,432,447`** | 4 call sites wrap `token.telegram_id` with `mask_telegram_id(...)`; import at line 36. (Audited citation said 413/423/431/445 — see tidiness note.) |
| **Impact** | Post-withdrawal, a rate-limited login attempt writes the raw external auth identifier into the bot's JSONL log stream. The production `RedactingJsonFormatter` only redacts sensitive *keys* (`password|token|secret|api[_-]?key|authorization`) — `telegram_id` interpolated via `%s` into the `message` field survives unmasked. Per Phase 06 §8 CRITICAL ("PII leaked into … logs (raw identifier)"). |
| **Root Cause** | The bot login handler is the sole auth/identity logging call site that does not adopt the project-wide `mask_telegram_id` convention; no bot-side test asserts log PII hygiene on this path. |
| **Recommendation** | (a) `from apps.core.utils.sanitize import mask_telegram_id`; (b) wrap: `logger.warning("Login rate limit exceeded for telegram_id=%s", mask_telegram_id(message.from_user.id))`. (c) Add `caplog` assertion to `test_login_rate_limit_blocks_after_threshold` mirroring web-side `TestLoginStatusNoPii` (`str(real_id) not in caplog.text`; `"tg_" in caplog.text`). |
| **Effort / Priority** | S (trivial) / mandatory |
| **Spec section** | §5d (PII containment), §8 (CRITICAL: raw identifier in logs) |

### LOW

> **Validation Note — PII-002**
> - **Action:** validated
> - **Detail:** `src/backend/apps/ads/admin.py:25-32` `user_link` returns `str(obj.user.telegram_id)` verbatim, surfaced in `AdAdmin.list_display` (line 77) with `short_description = "User (telegram_id)"`. Admin is staff/superuser-only (`has_view_permission`/`:113`, `has_change_permission`/`:117` → `is_staff or is_superuser`) and the `AdAdmin` docstring is INTERNAL ONLY. **Risk mitigation verified:** `withdraw_consent` nulls `telegram_id` (`deletion.py:132`) inside `transaction.atomic()`, so the column is already blank (`"None"`/`-`) for erased accounts — confirming the audit's "reducing risk" note. Classified LOW advisory ("no code change required for compliance as-is; document/narrow"). Evidence matches verbatim; classification as LOW/advisory is sound.
> - **Cross-phase:** no Phase 04 reference (Phase 04 = auth-login only, AUT-001 only). Standalone.

#### PII-002: [LOW (advisory)] — Admin list view displays raw `telegram_id`

| Field | Value |
|---|---|
| **ID** | PII-002 |
| **Severity** | LOW (advisory) |
| **Type** | BEST-PRACTICE (advisory hardening/documentation; no current spec violation — admin is staff-only INTERNAL ONLY and erased accounts already blank the column) |
| **File(s)** | `src/backend/apps/ads/admin.py:25-32` |
| **Status** | Open (advisory) |
| **Problem** | `user_link(obj)` returns `str(obj.user.telegram_id)` in the staff-only Django admin list. §5d notes the external identifier "should not be surfaced as a display value." |
| **Evidence — `ads/admin.py:25-32`** | ```python\ndef user_link(obj: Ad) -> str:\n    """Display user telegram_id as link."""\n    if obj.user:\n        return str(obj.user.telegram_id)\n    return "-"\n\nuser_link.short_description = "User (telegram_id)"\n``` (verbatim) |
| **Mitigation verified** | `withdraw_consent` sets `user.telegram_id = None` (`deletion.py:132`) atomically; erased accounts render `"None"`/`-"` → bounded exposure. `AdAdmin.has_view_permission`/`has_change_permission` (lines 113-119) restrict to `is_staff or is_superuser`. |
| **Recommendation** | Advisory only: (a) document the staff-only exposure in the `user_link` / `AdAdmin` docstring; (b) optionally gate the column behind a finer-grained staff permission if the admin surface ever widens; (c) if any public-buyer display ever reads `user.telegram_id`, fall back to name components, never the raw identifier. |
| **Effort / Priority** | Docstring note (trivial) / permission gate (small); recommended, not mandatory |
| **Spec section** | §5d (display-name guidance, advisory) |

## Rejected Findings

_None._ Both findings' evidence is verbatim-accurate and the defects are real.

## Merged Findings

_None within Phase 06._ PII-001 and AUT-001 (Phase 04) describe the **same root-cause defect on the same code line** (`login.py:95-98`). They are **not** merged because each phase's taxonomy correctly buckets the identical defect at its scope-appropriate severity (PII-001 = CRITICAL per §8; AUT-001 = LOW per auth "log verbosity around auth"). A single remediation resolves both — see Rollout Analysis. No Phase-06 pair shares a root cause (PII-001 = logs; PII-002 = admin display; distinct files, distinct defects).

## Cross-Reference: Phase 04 AUT-001 ↔ Phase 06 PII-001

| Aspect | Phase 04 AUT-001 | Phase 06 PII-001 | Verdict |
|--------|------------------|------------------|---------|
| Defect | Bot login rate-limit warning logs raw `message.from_user.id` | Identical | Same defect, same line (`login.py:95-98`) |
| Severity | LOW | CRITICAL | Taxonomy-scope difference (auth phase has no PII bucket; PII §8 rates raw-identifier-in-logs CRITICAL) — both correct for their phase |
| Status | Resolved (via commit `5b5bb0a`) | Resolved (via commit `5b5bb0a`) | Single remediation (commit `5b5bb0a`) resolves both Phase 04 AUT-001 and Phase 06 PII-001 |
| Fix | `mask_telegram_id` wrap + `caplog` regression | Identical | Single remediation resolves both findings |

**Validator note:** PII-001 is **not reclassified to LOW** to match AUT-001. The PII phase explicitly defines "PII leaked into … logs (raw identifier/handle)" as CRITICAL (§8) and §2 defines the external auth identifier (`telegram_id`) as the only PII. Downgrading would hide a CRITICAL- tier PII containment gap under the PII phase's own taxonomy. The cross-reference to AUT-001 (already carrying the exact fix) is documentary only.

## Rollout Analysis

| Finding | Risk | Dependencies | Backward compatibility | Sequencing |
|---------|------|--------------|------------------------|------------|
| PII-001 | Logging-only change; output text shifts from raw int to `tg_<8-hex>` (stable per input). | `apps.core.utils.sanitize.mask_telegram_id` (exists). No new dependency. | Yes — stable masking preserves correlation; verify no dashboard keys off the literal Telegram ID on the rate-limit path. | Resolve with Phase 04 AUT-001's single remediation: (1) add `from apps.core.utils.sanitize import mask_telegram_id` to `login.py`; (2) wrap `message.from_user.id` in the rate-limit `logger.warning`; (3) add `caplog` assertion to `test_login_rate_limit_blocks_after_threshold` mirroring `TestLoginStatusNoPii`. One commit resolves PII-001 + AUT-001. |
| PII-002 | Advisory; no behavior/PII-surface change by default. | None for the doc note. Permission gate (optional) needs a staff permission definition. | Fully backward-compatible. | Independent; no sequencing dependency. |

**Rollout safety — PII-001:** `mask_telegram_id` is already exercised in `test_sanitize.py` (non-reversible, stable) and 10 web-side call sites; no auth/DB/semantics change. The `caplog` regression prevents future drift. No migration.

**Rollout safety — PII-002:** documentation-only by default; staff-only admin surface unchanged. No rollout risk.

## Execution Validation

- **PII-001 applicability:** target `login.py:95-98` exists verbatim (`login.py:95-98`). `mask_telegram_id` import path `apps.core.utils.sanitize` is valid in the bot process (bot already imports sibling `apps.core.*` modules; `django.setup()` + shared ORM). ✅ Applicable.
- **PII-002 applicability:** target `ads/admin.py:25-32` (`user_link`) exists verbatim and is wired into `AdAdmin.list_display` at line 77. Staff-only guard `has_view_permission` confirmed (line 113). ✅ Applicable.

## Warnings

### Architectural / Maintainability Risks
1. **PII-001 (class-of-defect):** The bot login handler is the sole identity-bearing log site that bypasses `mask_telegram_id`. Without a shared bot-side logging convention, other bot handlers can reintroduce raw-identifier logging. Advisory: route all bot identity logs through a small helper that applies `mask_telegram_id` by construction (mirrors Phase 04 ADR-03).

### Documentation Inconsistencies
1. **PII-001 citation tidiness:** `findings.md` cites web control at `consent.py:413,423,431,445`; live masking call sites are `415,424,432,447` (import at line 36). Fix: update the citation lines to `415/424/432/447` when the findings file is finalized. Non-blocking — the control exists and is used.

## Required Fixes

| Order | ID | Severity | Type | Recommendation (summary) | Decision |
|-------|----|----------|------|--------------------------|----------|
| 1 | PII-001 | CRITICAL | SPEC-DEVIATION | Add `from apps.core.utils.sanitize import mask_telegram_id` to `login.py`; wrap rate-limit value: `logger.warning("Login rate limit exceeded for telegram_id=%s", mask_telegram_id(message.from_user.id))`; add `caplog` assertion to `test_login_rate_limit_blocks_after_threshold` (`str(real_id) not in caplog.text`, `"tg_" in caplog.text`). | Mandatory (code already applied via commit `5b5bb0a`; also resolves Phase 04 AUT-001) |

## Advisory Recommendations

1. **PII-002 (docstring + optional permission gate):** Note the staff-only/INTERNAL-ONLY exposure on `user_link`/`AdAdmin`; consider a finer-grained permission if the admin surface widens. Keep as-is for now (erased accounts already blank the column).
2. **Cross-phase PII severity consistency (ADR):** The same defect is CRITICAL under Phase 06 but LOW under Phase 04. If a unified PII severity policy is desired, confirm the canonical tier for "raw identifier in log on a defensive path, semi-public identifier, no secret leak" — currently CRITICAL (PII phase §8) vs LOW (auth phase). This is a policy call, not a code defect.
3. **Bot-side logging convention:** Route all bot identity-bearing logs through a helper applying `mask_telegram_id` by construction, eliminating the "forgot to mask" class — see Phase 04 ADR-03.
