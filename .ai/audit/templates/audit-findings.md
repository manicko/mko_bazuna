---
# Report metadata — fill once per phase report.
phase: "{PHASE_NUMBER}"
phase_name: "{PHASE_NAME}"
date: "{YYYY-MM-DD}"
auditor: "Executor (subagent)"
validator: "{Validator name}"  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
id_prefix: "{PREFIX}"
# report_status = lifecycle of the report document (draft → validated)
# per-finding Status (in Findings Summary + field table below) = lifecycle of the individual finding (Open → Validated/Rejected/Merged/Reclassified/Deferred)
report_status: "draft"  # "draft" for raw phases; Phase 99 sets to "validated"
severity_taxonomy: ".kilo/commands/audit/phases/{NN}-{phase-name}.md#severity-taxonomy"  # pointer to phase rubric, NOT hardcoded
# Structural enforcement (replaces the buried ID-preservation comment):
phase_99_invariant: "Finding IDs ({PREFIX}-NNN) MUST be preserved through Phase 99 validation. Phase 99 validators MUST NOT renumber to F-NN."
---

<!-- WRITE-HYGIENE: Append findings one at a time. Keep each append <=100 lines. Offload long evidence (>3 blocks) to Section: Appendices. -->
<!-- MODE: problems-only. If this phase finds zero problems, write ONLY "No problems found in this phase." (Section: Empty State) and STOP. Do NOT list "passed checks" or "correct configurations" as findings. -->
<!-- ID SEQUENCE: Finding IDs must be sequential and unique within the phase: {PREFIX}-001, {PREFIX}-002, ... — no duplicates, no gaps. -->

# Audit Findings — {PHASE_NAME}

## Executive Summary

2-3 non-technical sentences communicating overall risk posture for non-technical stakeholders. State how many findings, the highest severity, and the broadest business impact — no technical detail.

<!-- Phase 99 NOTE: Phase 99 does NOT simply replace this section inline. -->
<!-- It produces a different document type: change the title to "# Audit Findings — Validation Report", -->
<!-- preserve this Summary section verbatim, and add a separate ## Validation Summary section (see scaffolding at end of template). -->

## Scope & Methodology

**Scope:** {Concise statement of which files, modules, and behaviors this phase covered. One-to-two sentences.}

### Runtime Verification

Each claim in a finding must be reproducible. Record the verification checks below.

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | {assertion being verified} | {grep command / read / tool run} | PASS / FAIL |
| R-02 | {assertion being verified} | {method} | PASS / FAIL |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** {e.g., `ruff`, `basedpyright`, `grep -rn`, `uv run pytest`, `psql`, aiogram source inspection}

**Assumptions:** {e.g., "Production uses Redis-backed cache, not LocMemCache"; "PostgreSQL 18"; "Django 5.2"; "bot runs under CPython, no PyPy"}

<!-- Phase 99 ADDS a Methodology Cross-Check here (see scaffolding at end of template): -->
<!-- re-run each R# check against the live source and mark Confirmed/Unchanged where the original finding's claim holds. -->

## Findings Summary

Single source of truth for all counts below. Add one row per finding, ordered by severity (see `severity_taxonomy` in front-matter).

<!-- If this table is empty (zero rows), emit ONLY the line "No problems found in this phase." in the Empty State section below and STOP. -->
<!-- Skip all subsequent sections: Distribution, Findings by Severity, Cross-Finding Analysis, Remediation Roadmap, Rollout Safety, Appendices, and Phase 99 scaffolding. -->

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| {PREFIX}-001 | {one-line title} | {severity} | Open | {category} |
| {PREFIX}-002 | {one-line title} | {severity} | Open | {category} |

<!-- Phase 99 ADDS a Type column to this table (insert after Category): -->
<!-- | ID | Title | Severity | Status | Category | Type | -->
<!-- Phase 99 Type values: SPEC-DEVIATION (code deviates from established pattern) | BEST-PRACTICE (missing convention) | DOC-UPDATE (documentation-only) -->

## Empty State

No problems found in this phase.

<!-- IF ZERO findings: emit ONLY the line above and STOP. -->
<!-- This early-exit check precedes Distribution, Findings by Severity, and all remaining sections. -->

## Distribution

<!-- DERIVED from the Findings Summary table above. Never hand-maintained — update the summary first, then copy counts here. -->

**Severity counts**

| {severity-band-1 (see rubric)} | {n} |
| {severity-band-2} | {n} |
| {severity-band-3} | {n} |

**Status counts**

| Status | Count |
|--------|-------|
| Open | {n} |

> Note: Status is `Open` for all findings in raw phase reports. Phase 99 validation mutates Status to `Validated` / `Reclassified` / `Merged` / `Rejected` / `Deferred`. Values `Fixed` / `Verified` are forbidden here — they belong to a remediation tracker, not the audit report.

## Findings by Severity

Group findings under one band heading per severity tier **used by this phase's rubric**. Omit bands that have zero findings. Use the example block below as the structural template for every finding.

<!-- Use the EXACT severity band names from your phase's "Severity Taxonomy" section (see front-matter `severity_taxonomy`). -->
<!-- Include only bands with ≥1 finding. -->
<!-- For phases without a CRITICAL tier (e.g. Phase 10 — Code Quality), omit the CRITICAL heading entirely. -->

### {SEVERITY-BAND}

#### {PREFIX}-001: [{SEVERITY-BAND}] — {TITLE}

<!-- Core fields — always present and filled for every finding across all 14 phases. -->

| Field | Value |
|---|---|
| **ID** | {PREFIX}-001 |
| **Title** | {one-line title — must match the heading above exactly} |
| **Severity** | {phase-defined — see `severity_taxonomy` in front-matter} |
| **Category** | {domain or ISO 25010 quality characteristic — phase-defined} |
| **File(s)** | `path/to/file.py:NN` (SARIF-style line reference) |
| **Status** | Open |
| **Problem** | {defect stated once, in full context — NOT a repeat of Title} |
| **Impact** | {who/what is harmed and how — consequence, not mechanism} |
| **Root Cause** | {code-level or process-level reason the defect exists} |
| **Recommendation** | {concrete, actionable fix} |
| **Effort** | {S / M / L or N person-days} |
| **Priority** | {P0 / P1 / P2 or numerical} |

> Effort (size) and Priority (ordering) are orthogonal sub-fields of Recommendation. They populate the Remediation Roadmap.

<!-- === Conditional / phase-specific fields — append ONLY the sub-tables relevant to this phase; omit the rest. === -->
<!-- Phase 99 ADDS Validation Type as a final field-table row (see Phase 99 scaffolding). -->

<!-- === SECURITY PHASES (02, 04, 06, 09) — append this sub-table ONLY === -->

| Field | Value |
|---|---|
| **CWE** | {CWE-NNN — MITRE CWE identifier} |
| **Likelihood** | {LOW / MEDIUM / HIGH — OWASP bands: LOW 0-3, MEDIUM 3-6, HIGH 6-9} |

<!-- === OPERATIONAL PHASES (12, 13) — append this sub-table ONLY === -->

| Field | Value |
|---|---|
| **Owner** | {risk/operational owner — team or role name} |
| **Target Date** | {YYYY-MM-DD — remediation target} |

<!-- === DEVELOPMENT PHASES (08, 10, 11) — append this sub-table ONLY === -->

| Field | Value |
|---|---|
| **Reproduction Steps** | {numbered, runnable steps — leave blank for architectural findings} |

<!-- === CROSS-CUTTING (all phases) — always append this sub-table === -->

| Field | Value |
|---|---|
| **Related Findings** | {PREFIX-NNN, PREFIX-MMM — IDs this finding depends on or duplicates} |

**Evidence:**

<!-- Each block MUST be a fenced snippet with an inline caption tied to a SPECIFIC claim above. No uncaptioned dumps. Overflow -> Appendices. -->

**Evidence — `path/to/file.py:NN`** *(supports: "{quote the exact Problem/Impact/Root Cause claim this snippet proves}")*:
```{LANGUAGE}
# {replace LANGUAGE; paste minimal reproducible snippet, <=30 lines}
```

**Evidence — `{COMMAND or grep output}`** *(supports: "{claim}")*:
```text
{command output, truncated to <=20 lines}
```

---

### {SEVERITY-BAND}

#### {PREFIX}-002: [{SEVERITY-BAND}] — {TITLE}

<!-- Repeat the full finding block (core field table + conditional sub-table(s) + captioned evidence) for every finding. -->

<!-- Bands with no findings: write the header and note "No findings in this band." OR omit the band entirely. -->

## Cross-Finding Analysis

Assess at authoring time whether findings overlap or depend on each other.

- **Merge candidates:** {IDs sharing one root cause that could be unified into a single finding — or "None"}
- **Conflicting evidence:** {findings whose evidence contradicts another — or "None"}
- **Dependency chains:** {finding X must be fixed before finding Y — or "None"}

## Remediation Roadmap

Ordered fixes by Severity × Priority (from each finding's Effort/Priority). One row per fix.

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | {PREFIX}-001 | {severity} | {S/M/L} | {P0/P1/P2} | {short fix description} |
| 2 | {PREFIX}-002 | {severity} | {S/M/L} | {P0/P1/P2} | {short fix description} |

<!-- Phase 99 ADDS Required Fixes: annotate each row with REQUIRED (blocks release) vs ADVISORY, and record the validator's acceptance decision next to the row. -->

## Rollout Safety

Per-fix rollout risk. Assess before the fix ships.

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| {PREFIX}-001 | {Low / Med / High} | Yes / No | {what test is missing that the fix changes} |

## Appendices

Offload long evidence here to keep each writing append <=100 lines. Number appendices A, B, C and cross-reference from the relevant Evidence block above.

### Appendix A — {label}

```{LANGUAGE}
{long snippet, full tool output, or multi-command reproduction session}
```

*(supports the claim: "{recap the claim this appendix proves}")*

<!-- ==================================================================== -->
<!-- ===== PHASE 99 (VALIDATION) — STRUCTURE GUIDE & SCAFFOLDING ===== -->
<!-- ==================================================================== -->
<!-- The following structural guidance applies ONLY to the Phase 99 -->
<!-- validation document ("Validation Report"), which is a derived copy -->
<!-- of this raw findings file. Do NOT emit these sections in raw phase -->
<!-- (01–14) reports. -->
<!-- -->
<!-- Phase 99 workflow: -->
<!--   1. Copy the raw findings file as the base document. -->
<!--   2. Set front-matter report_status: "validated". -->
<!--   3. Change title to: "# Audit Findings — Validation Report" -->
<!--   4. Preserve this report's ## Executive Summary (Summary) verbatim. -->
<!--   5. ADD the sections below, in order. -->
<!--   6. PRESERVE all finding IDs ({PREFIX}-NNN) — NEVER renumber to F-NN. -->
<!--      (Enforced by phase_99_invariant in front-matter above.) -->
<!-- ==================================================================== -->

<!-- ## Validation Summary -->
<!-- Insert immediately after the document metadata block (after the title). -->
<!-- Counts MUST be consistent with the Validated Findings table below. -->
<!-- -->
<!-- | Action | Count | Details | -->
<!-- |--------|-------|---------| -->
<!-- | Validated (unchanged) | {n} | {PREFIX}-001, {PREFIX}-002, ... | -->
<!-- | Reclassified | {n} | — | -->
<!-- | Merged | {n} | — | -->
<!-- | Rejected | {n} | — | -->

<!-- ### Validated Findings -->
<!-- Add a Type column to the Findings Summary table (insert after Category). -->
<!-- IDs are preserved — NOT renumbered. -->
<!-- -->
<!-- | ID | Severity | Type | Title | Status | -->
<!-- |----|----------|------|-------|--------| -->
<!-- | {PREFIX}-001 | {severity} | SPEC-DEVIATION | {title} | Validated | -->
<!-- | {PREFIX}-002 | {severity} | BEST-PRACTICE | {title} | Validated | -->

<!-- ### Rejected Findings -->
<!-- _None._ -->
<!-- Format per finding: -->
<!-- ### {PREFIX}-NNN: ~~{title}~~ [REJECTED] -->
<!-- **Reason:** {why the finding was rejected} -->

<!-- ### Merged Findings -->
<!-- _None._ -->
<!-- Format per finding: -->
<!-- ### {PREFIX}-NNN: ~~{title}~~ [MERGED] -->
<!-- Merged into: {PREFIX}-MMM -->
<!-- **Reason:** {why the findings were merged} -->

<!-- ### Reclassified Findings -->
<!-- _None._ -->
<!-- Format per finding: -->
<!-- ### {PREFIX}-NNN: {old-severity} → {new-severity} -->
<!-- **Reason:** {why the severity was reclassified} -->

<!-- ## Finding {PREFIX}-001 — [{SEVERITY-BAND}] — {TITLE} -->
<!-- Per-finding validation block. Repeat for each finding. IDs preserved. -->

<!-- **Type:** {SPEC-DEVIATION | BEST-PRACTICE | DOC-UPDATE — brief justification} -->
<!-- **Validation Result:** {VALIDATED | REJECTED | MERGED | RECLASSIFIED} -->

<!-- ### Evidence Verification -->
<!-- Re-verify each claim against live source. Mark Confirmed/Unchanged/Refuted on each. -->

<!-- ## Cross-Finding Analysis -->
<!-- Extend the raw Cross-Finding Analysis with validation-specific merge/reject rationale. -->

<!-- ## Rollout Safety Assessment -->
<!-- (Phase 99 re-titles this from "Rollout Safety".) -->
<!-- The Phase 01 output uses per-finding narrative subsections; -->
<!-- the Phase 02 output uses a compact table. Either is acceptable. -->
<!-- -->
<!-- | Finding | Risk | Dependencies | Backward compatibility | Notes | -->
<!-- |---------|------|--------------|------------------------|-------| -->
<!-- | {PREFIX}-001 | {Low/Med/High} | {finding dependencies} | Yes/No | {test gap or rollout concern} | -->

<!-- ### {PREFIX}-001 — {short finding title} -->
<!-- Phase 99 (per-finding narrative, optional — use when table is insufficient): -->
<!-- **Risk:** {risk assessment} -->
<!-- **Backward compatibility:** {Yes/No — explain} -->
<!-- **Test gap:** {what test is missing} -->

<!-- ## Warnings -->
<!-- Phase 99: surface systemic issues discovered during validation, not individual findings. -->

<!-- ### Architectural Risks -->
<!-- 1. {systemic architectural concern surfaced by validation} -->

<!-- ### Maintainability / Evolvability Risks -->
<!-- 1. {systemic maintainability concern surfaced by validation} -->

<!-- ### Rollout Risks -->
<!-- 1. {systemic rollout concern surfaced by validation} -->

<!-- ## Methodology Cross-Check -->
<!-- Phase 99: re-execute each R# verification method and confirm the original result still holds. -->
<!-- -->
<!-- | R# | Method | Status | Notes | -->
<!-- |----|--------|--------|-------| -->
<!-- | R-01 | {check description} | {Confirmed / Unchanged / Refuted} | {verification detail} | -->
<!-- | R-02 | {method} | {Confirmed / Unchanged / Refuted} | {detail} | -->

<!-- ### Assumptions Verified -->
<!-- Phase 99: confirm or refute each assumption stated in the raw report's Scope & Methodology. -->

<!-- 1. "{original assumption}" — VERIFIED / REFUTED — {brief evidence} -->
<!-- 2. "{original assumption}" — VERIFIED / REFUTED — {brief evidence} -->

<!-- ## Required Fixes (Phase 99 annotated) -->
<!-- Annotate each raw finding's fix with REQUIRED (blocks release) vs ADVISORY. -->
<!-- Reuse the raw Remediation Roadmap table; add a Decision column. -->
<!-- -->
<!-- | Order | ID | Severity | Effort | Priority | Recommendation (summary) | Decision | -->
<!-- |-------|----|----------|--------|----------|--------------------------|----------| -->
<!-- | 1 | {PREFIX}-001 | {severity} | {S/M/L} | {P0/P1/P2} | {short fix description} | {REQUIRED / ADVISORY} | -->

<!-- ## Advisory Recommendations -->
<!-- Phase 99: broader improvements beyond the individual fixes. -->

<!-- 1. **ADR-01:** {broader improvement recommendation} -->
<!-- 2. **ADR-02:** {broader improvement recommendation} -->
