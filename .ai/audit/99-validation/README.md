# 99 — Validation Store

This directory holds the **validated findings report for each phase**, produced by
the validator (Phase 99) as it reviews every audit phase individually.

Process (per phase):
- The validator copies the auditor's per-phase findings file here as
  `{phase_number}-{phase_name}-validated.md`.
- It cross-checks findings, reclassifies or rejects them, and appends a
  Validation Summary.
- The original findings file is never modified.

See `.kilo/commands\audit\phases\99-audit-validate.md` for the validator
instruction. See the findings-template specification for the report structure.
