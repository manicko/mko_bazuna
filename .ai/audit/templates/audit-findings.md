---
phase: "{NN}"
phase_name: "{phase-name}"
id_prefix: "{PREFIX}"  # from the phase file's Report Output; no prefix list lives here
mode: "problems-only"
report_status: "draft"  # phase 99 sets "validated"
severity_taxonomy: ".kilo/commands/audit/phases/{NN}-audit-{phase-name}.md#severity-taxonomy"
code_ref: "{git short sha}"  # the tree this report describes; written once, never per finding
---

# Audit Findings — {PHASE_NAME}

## Summary

{2–4 non-technical sentences: how many findings, the highest severity present, the broadest
business consequence. No mechanism, no file names.}

## Scope

**Examined:** {which modules, surfaces and behaviours this phase covered}
**Tools:** {`rg`, `ruff`, `basedpyright`, `psql`, `pytest`}
**Not verified:** {what was out of scope or could not be checked — an assumption is a claim}

<!-- FORBIDDEN
     - line numbers as locators; Effort / Owner / Target Date / Likelihood / CVSS / R# numbering
     - a field restating what the #### heading or index row carries: ID, Title, Severity, Status
     - a passing check dressed as a finding; "Fixed" or "Verified" as a report_status
     - renaming a shipped test so a finding goes away
     - a Fix that names no target symbol — "be more careful" is not a fix
-->

<!-- GATES — run these before appending; each one falsifies a fabricated finding:
     1. every cited path appears in `git ls-files`
     2. the symbol exists in that file, and the disambiguator token exists inside it
     3. no `:<digits>` appears in any locator field
     4. every "we ran X" claim has its output pasted in the fence below it -->

## Findings

<!-- Anchor rule: `path::Symbol` — the file plus the class/function/method carrying the defect. -->
<!-- Non-code targets: `path::"exact token"` (template block, settings/YAML key, .po msgid). -->
<!-- A nested or function-local definition is `path::enclosing_symbol.nested_name`. -->
<!-- A line number is never a locator; line numbers belong only inside pasted tool output. -->
<!-- Zero findings? Emit only `No problems found in this phase.` and stop. -->

| ID | Severity | Anchor | Title |
|---|---|---|---|
| QLT-001 | HIGH | `src/backend/apps/ads/models.py::Ad.transition_to` | {one line: component + impact} |
| QLT-002 | MEDIUM | `src/backend/apps/ads/services/submission.py::submit_ad` | {one line: component + impact} |

<!-- Repeat per finding, sorted by severity; the index order IS the work order. -->
<!-- Severity bands and the ID prefix: read the phase file, never invent one. -->

#### QLT-001 — [HIGH] {title}

<!-- **Anchor:** one per line, primary first; every site the defect touches gets one, no cap. -->
<!-- **Disambiguator:** a token from inside the PRIMARY anchor; gate 2 checks the primary. -->
<!-- **Checked:** ran | static | not-checked — the last states no observed result. -->
<!-- **Repro:** required for `ran`, permitted for `static`, omitted for `not-checked`. -->
<!-- **Verify:** never blank — `path::test_name` or `new test needed: <name>`. -->
<!-- A shipped test asserting the current behaviour blocks the fix; never drop the finding. -->
**Anchor:** `src/backend/apps/ads/models.py::Ad.transition_to`
**Disambiguator:** `"moderator_id"`
**Checked:** ran
**Why this band:** {band trigger + the adjacent band NOT graded as; text in the phase file}
**Problem:** {the defect stated once, in context — not the title again}
**Repro:** {numbered steps, exact input, exact observed result}
**Impact:** {consequence for a named audience: sellers, buyers, the on-call developer}
**Root cause:** {a code or process condition, never a person or a team}
**Fix:** {concrete change naming its target symbol — move `Ad.transition_to` into the service}
**Verify:** new test needed: test_transition_to_rejects_illegal_status_jump
**Related:** QLT-004, AUTZ-002

**Evidence — `rg -n 'def transition_to' src/backend/apps/ads/models.py`** *(supports: "one site")*:
```text
src/backend/apps/ads/models.py:363:    def transition_to(
```

<!-- 1–2 fences per claim; an identical-sites claim shows both, or cites the pair in Appendices. -->

#### QLT-002 — [MEDIUM] {title — repeat the block above unchanged in shape}

## Fix Order

- **Dependencies:** {B must land before A} or `None.`
- **Merge candidates:** {IDs sharing one root cause} or `None.`
- **Conflicting evidence:** {two findings whose evidence cannot both hold} or `None.`
- **Cross-phase conflicts:** {concern filed under a phase that does not own it} or `None.`
- **Rollout risk:** {per finding: what the fix breaks, and which test must stay green} or `None.`

## Appendices

<!-- Required: appends are capped at 100 lines per pass, so long evidence lands here. -->

### Appendix A — {label}

```text
{full command output}
```
*(supports: "{claim}")*

<!-- VALIDATION (phase 99) — copy this file, retitle the H1 "# Audit Findings — Validation Report",
     set report_status: "validated". IDs are preserved, never renumbered; one disposition per
     finding in scope, none withheld. Emit none of this block in a raw-phase report. -->
<!-- Vocabulary and rules are in .kilo/commands/audit/phases/99-audit-validate.md. Resolve each
     anchor mechanically before any verdict: one that does not resolve blocks confirmation. -->
<!-- `VAL-` findings take their own section and severity scale; one Severity column must never
     carry two scales, so they are never interleaved into the index. -->
