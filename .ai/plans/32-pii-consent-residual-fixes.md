---
# Plan metadata
id: 32
name: pii-consent-residual-fixes
source: .ai/audit/99-validation/06-pii-consent-validated-findings.md
findings: PII-001, PII-002
effort: S
priority: P2
severity: LOW
status: done
---

# Execution Plan 32 — PII-Consent Residual Fixes (PII-001 / PII-002)

## 0. Summary

**Status:** PII-001 (CRITICAL, MANDATORY) is **already fixed in code** (commit
`5b5bb0a`). The import (`login.py`), the `mask_telegram_id` wrap (`login.py`),
and the `caplog` regression test assertions (`test_login.py`) are all present.
The residual work for PII-001 is **documentation-only**:

1. Correct the stale findings-file status that still reads "Open".
2. Fix a mislabeled test comment that says `PII-002` but actually tests
   PII-001 (log masking of raw `telegram_id`).

PII-002 (LOW, advisory) is a docstring hardening recommendation on
`ads/admin.py` — also documentation-only, no behavior change.

**Out of scope (explicitly acknowledged, not implemented):**
- ADR-02 (cross-phase severity consistency) — policy/taxonomy difference, no
  code defect.
- ADR-03 (bot-side logging convention) — the PII-001 site already uses
  `mask_telegram_id` directly; a broader convention is a separate follow-up.

## 1. Code Context (inspection result)

Confirmed against live source on `2026-09-19`:

- `src/telegram_bot/handlers/login.py` —
  - Imports `mask_telegram_id` from `apps.core.utils.sanitize`.
  - The rate-limit-exceeded branch calls
    `logger.warning("Login rate limit exceeded for telegram_id=%s",
    mask_telegram_id(message.from_user.id))`.
  - PII-001 code defect: **RESOLVED** (commit `5b5bb0a`).

- `src/telegram_bot/tests/test_login.py` —
  - `TestLoginRateLimit::test_login_rate_limit_blocks_after_threshold`
    (class at line 430; method at line 469) uses `caplog` and asserts
    `str(blocked_msg.from_user.id) not in caplog.text` and
    `"tg_" in caplog.text`.
  - The comment above the assertion block reads `# PII-002:` but the
    assertions test **PII-001** (log masking). **Mislabeled comment — stale.**

- `src/backend/apps/ads/admin.py` —
  - `user_link` function (lines 25–32): docstring is
    `"""Display user telegram_id as link."""` — no INTERNAL-ONLY note.
    Behavior is correct by design: staff-only via `has_view_permission` /
    `has_change_permission`; `telegram_id` nulled on withdraw via
    `withdraw_consent` (`deletion.py`).
  - `AdAdmin` class (lines 62–68): docstring notes "INTERNAL ONLY" for
    rejection-reason display but does not document the `user_link` column
    exposure scope.
  - PII-002: **Open (advisory)** — docstring note needed.

- `.ai/audit/99-validation/06-pii-consent-validated-findings.md` —
  Still marks PII-001 as "Validated / Open" despite the code fix.
  **Stale.**

- Web-side reference pattern (for context only — not modified):
  `src/backend/apps/users/tests/test_consent.py`
  `TestLoginStatusNoPii::test_login_consume_no_raw_telegram_id` provides the
  assertion pattern the bot-side test already mirrors.

## 2. Risk Assessment

| Finding    | Change Type            | Risk   | Rollback                  |
|------------|------------------------|--------|---------------------------|
| PII-001    | Markdown + 1 comment   | None   | Revert the two edits      |
| PII-002    | Docstring additions    | None   | Revert the docstring edits|

All changes are non-behavioral: markdown status update, a single comment fix
in a test file, and docstring text additions. No production logic, schema,
or test logic is altered.

## 3. Block Summary Table

| Block | Finding    | Scope                                    | Agent       | Depends on |
|-------|------------|------------------------------------------|-------------|------------|
| B1    | PII-001    | Findings file status + test comment fix  | Implementor | None       |
| B2    | PII-002    | `ads/admin.py` docstring updates         | Implementor | None       |
| B3    | —          | Verification                             | Implementor | B1, B2     |

## 4. Execution Blocks

### B1 — PII-001: Close stale findings status + fix mislabeled test comment

**Agent:** Implementor — documentation/comment only; no behavior change.

PII-001's code is already fixed (commit `5b5bb0a`). The two residual items:

1. **Test comment fix** — `test_login.py`, inside
   `test_login_rate_limit_blocks_after_threshold`: the comment above the
   `caplog` assertion block says `# PII-002:` but the assertions test PII-001
   (raw `telegram_id` not in logs; `tg_` prefix present). Correct to `# PII-001:`.

2. **Findings file status** —
   `.ai/audit/99-validation/06-pii-consent-validated-findings.md`:
   update PII-001 status from "Open" to "Resolved" in:
   - The validation summary table row for PII-001.
   - The PII-001 Status field.
   - The Required Fixes table Decision column (note code already applied via
     commit `5b5bb0a`).
   - The cross-reference to Phase 04 AUT-001 (same commit resolves both).

#### task_description

```yaml
id: pii-001-close-finding-status
title: PII-001 — Mark finding Resolved in findings file + fix mislabeled test comment
priority: P1
source_reference: .ai/plans/32-pii-consent-residual-fixes.md
source_section: B1 — PII-001: Close stale findings status + fix mislabeled test comment
depends_on: []

description: >
  PII-001 (CRITICAL) is already fixed in code (commit 5b5bb0a): login.py
  imports and wraps mask_telegram_id, and test_login.py has caplog
  assertions. The residual work is documentation-only: (1) correct the stale
  validated-findings file status that still reads "Open", and (2) fix a
  mislabeled test comment that says PII-002 but actually tests PII-001 log
  masking. No production code or test logic change.

goals:
  - Findings file marks PII-001 as Resolved (code already applied)
  - Mislabeled test comment corrected PII-002 -> PII-001
  - Cross-phase AUT-001 reference noted as resolved by same commit
  - No production code or test behavior change

files:
  - path: .ai/audit/99-validation/06-pii-consent-validated-findings.md
    targets:
      - type: document
        name: PII-001 status fields
    changes:
      - action: replace_text
        description: >
          Update PII-001 Status from "Open" to "Resolved" in the findings
          summary table, the PII-001 Status field, and the Required Fixes
          Decision column. Note that code is already applied via commit
          5b5bb0a.
      - action: update_cross_reference
        description: >
          Note in the AUT-001 cross-reference table that the same commit
          (5b5bb0a) resolves Phase 04 AUT-001 as well.

  - path: src/telegram_bot/tests/test_login.py
    targets:
      - type: method
        name: test_login_rate_limit_blocks_after_threshold
        class: TestLoginRateLimit
    changes:
      - action: replace_in_body
        description: >
          Fix mislabeled comment PII-002 -> PII-001. The assertions
          (str(from_user.id) not in caplog.text; "tg_" in caplog.text) test
          PII-001 log-masking, not PII-002.
        old: '# PII-002: raw telegram_id must not leak in logs; masked value present'
        new: '# PII-001: raw telegram_id must not leak in logs; masked value present'

acceptance_criteria:
  - Findings file PII-001 status reads "Resolved"
  - Findings file summary table PII-001 row reads "Validated / Resolved"
  - test_login.py comment above caplog assertion reads "PII-001"
  - No production code or test logic changed — only markdown status + 1 comment
  - git diff shows only the two intended changes
```

### B2 — PII-002: Document staff-only/INTERNAL-ONLY exposure on `user_link` and `AdAdmin`

**Agent:** Implementor — docstring additions only; no behavior change.

PII-002 (LOW, advisory): `user_link` in `ads/admin.py` returns `telegram_id`
verbatim. The behavior is correct by design (staff-only via
`has_view_permission` / `has_change_permission`; `telegram_id` nulled on
withdraw), but the advisory recommendation is to document the INTERNAL-ONLY
exposure.

1. **`user_link` function docstring** — add note that the displayed `telegram_id`
   is staff/superuser-only (via `AdAdmin.has_view_permission` /
   `has_change_permission`) and INTERNAL ONLY; erased accounts already render
   blank because `withdraw_consent` nulls `telegram_id`.

2. **`AdAdmin` class docstring** — add note that the `user_link` column in
   `list_display` is staff-only INTERNAL ONLY.

#### task_description

```yaml
id: pii-002-docstring-note
title: PII-002 — Document INTERNAL-ONLY staff-only exposure on user_link and AdAdmin
priority: P2
source_reference: .ai/plans/32-pii-consent-residual-fixes.md
source_section: B2 — PII-002: Document staff-only/INTERNAL-ONLY exposure
depends_on: []

description: >
  PII-002 (LOW, advisory): user_link in ads/admin.py returns telegram_id
  verbatim. Behavior is correct by design (staff-only admin; telegram_id
  nulled on withdraw), but the advisory recommendation is to document the
  INTERNAL-ONLY exposure in the user_link and AdAdmin docstrings. No
  behavior or code-logic change.

goals:
  - user_link docstring documents staff-only INTERNAL-ONLY exposure
  - AdAdmin docstring notes the user_link column is INTERNAL ONLY
  - Document that withdraw_consent nulls telegram_id (erased accounts render blank)
  - No behavior or code-logic change

files:
  - path: src/backend/apps/ads/admin.py
    targets:
      - type: function
        name: user_link
      - type: class
        name: AdAdmin
    changes:
      - action: replace_docstring
        target: user_link
        description: >
          Add INTERNAL-ONLY / staff-only note to user_link docstring,
          referencing the has_view_permission / has_change_permission guard
          and withdraw_consent nulling telegram_id for erased accounts.
      - action: replace_docstring
        target: AdAdmin
        description: >
          Add note to AdAdmin class docstring that the user_link column in
          list_display is staff-only INTERNAL ONLY.

acceptance_criteria:
  - user_link docstring includes INTERNAL-ONLY / staff-only note
  - AdAdmin docstring includes note about user_link column exposure scope
  - No behavior change — docstring edits only
  - git diff shows only docstring additions
```

### B3 — Verification

**Agent:** Implementor

1. Verify B1 and B2 edits are in place (`git diff`).
2. Lint both modified files.
3. Re-run the PII-001 rate-limit test to confirm no logic regression
   (comment-only change cannot alter behavior, but the test must still pass).

#### task_description

```yaml
id: verify-pii-001-002
title: Verify — PII-001 finding status + PII-002 docstring + test comment
priority: P1
source_reference: .ai/plans/32-pii-consent-residual-fixes.md
source_section: B3 — Verification
depends_on:
  - pii-001-close-finding-status
  - pii-002-docstring-note
type: verification

verification_steps:
  - build: echo "No build required — documentation/comment only"
  - test: pytest src/telegram_bot/tests/test_login.py::TestLoginRateLimit::test_login_rate_limit_blocks_after_threshold -x
    note: run via docker compose test service (test DB required)
  - smoke_check: uv run ruff check src/telegram_bot/tests/test_login.py src/backend/apps/ads/admin.py

pass_criteria:
  - Findings file PII-001 status reads "Resolved"
  - test_login.py comment reads "PII-001"
  - user_link and AdAdmin docstrings contain INTERNAL-ONLY notes
  - ruff lint passes on both files
  - test_login_rate_limit_blocks_after_threshold passes

failure_action: Return failing task to rework

rollback_task: N/A — documentation/comment only, trivial revert
```

## 5. Dependency DAG

```
  B1 (PII-001: findings + comment)     B2 (PII-002: docstring)
        \                                     /
         \                                   /
          B3 (Verification)
```

B1 and B2 are independent — no code, schema, or import dependencies between
them. B3 verifies both. They may execute in parallel.

## 6. Advisory-Only Items (Not Implemented)

Per the task constraints, the following are acknowledged but **not** expanded
into code changes:

1. **ADR-02 (cross-phase severity consistency):** PII-001 is CRITICAL under
   Phase 06 but the same defect is AUT-001 (LOW) under Phase 04. This is a
   taxonomy-scope difference — both correct for their respective phase scope.
   The findings file cross-reference table documents this. No action needed.

2. **ADR-03 (bot-side logging convention):** Advisory that all bot identity-
   bearing logs should route through a helper applying `mask_telegram_id` by
   construction, eliminating the "forgot to mask" class. The PII-001 site
   already uses `mask_telegram_id` directly. A broader convention (e.g. a
   shared `logger.identity(...)` helper) would be a separate Phase-06
   follow-up — **out of scope** for these residual fixes.

## 7. Cross-Phase Note

Plan 31 (`.ai/plans/31-auth-login-pii-mask.md`) is still `status: executing`.
Since the Phase 06 PII-001 code fix (commit `5b5bb0a`) also resolves Phase 04
AUT-001, plan 31 may be marked `done` once this plan's findings-file status
update (B1) is applied. This is a status-bookkeeping observation, not a scope
expansion — the plan author should close plan 31 after B1 lands.
