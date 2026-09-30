---
name: 99-validate
status: draft
validated: no
executor: validator
problems-only: true
---

# Phase 99 — Audit Findings Validation

## Purpose

Validate another auditor's claims about the system — the reported defect, the support behind it, the band it was given, the recommendation attached to it — and produce a disposition record a
reader can act on without re-running the audit. This file names what to examine and under which angle; the executing validator discovers the concrete artifacts.

**Scope Boundaries** — 99 audits audit **output** and the audit tooling's own artefacts; the seventeen content phases audit the system, and no content phase's concern is 99's, except where a
finding's validity depends on a cross-phase claim. 99 never modifies source code, never renumbers an existing finding identifier, and never repairs a shared artefact from inside a
per-phase run; the only document it writes is its own validated report.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others, and each carries its own evidence, which here is a **disposition record**: what was re-derived, what
reproduced the claim, what refuted it, or what could not be settled and why.

**A PASS row in the input report's own verification table is methodology, never a verdict, and no adjudication is gated on the input's check list.**

The shared findings template instructs the validator to re-execute that list, which reinstates a gate removed deliberately, against reports themselves produced under it.

### 1. The claim re-derived from the executing path

*Ignore the quoted snippet, the comment and the line anchor. Does the path still do what the claim says, at the location it says, after the drift? Resolve every location reference
mechanically first — a reference into lines that do not exist is a wrong approval by default, not a formatting slip. A comment, docstring or runbook line that contradicts the
executing path is itself a finding, never a source of truth; so is the asserted cause, which can be false while the finding it supports survives.*
Evidence: per finding — the executing path, whether the anchor resolved, the claim tested on its own terms, and the asserted cause tested separately.

### 2. Support that is only a green control

*For every check, test, gate or shipped regression a claim leans on, separate three questions — does it exist, what scope does it declare, what did it actually examine — and then
separate a fourth: whether it ran at all is not whether it decided anything. A control that ran and reported clean substantiates nothing, however central it is to the argument. A
claim whose entire support is a green control is not confirmed — and a control that is present, configured and deciding nothing is a finding in the audit itself, not a pass.*
Evidence: per control — existence, declared scope, the item count actually examined, and the path by which a verdict would have reached a decision.

### 3. The grade against the audited phase's own rubric

*The source phase's severity section is the rubric of record; grade by effect and blast radius anchored to present state. A mechanism absent from an enumerated band is not thereby a
lower band, and a band left empty is a valid outcome rather than a gap. Grade the finding, not the mechanism: a real defect whose asserted cause is factually wrong is not thereby
mis-graded, and a claim that cannot fail is either vacuous or real and graded too low.*
Evidence: per finding — the band the audited rubric assigns, the band carried, and the mechanism it was downgraded on, if any.

### 4. Which side moves: code or documentation

*Decide from which artefact is load-bearing and which the rest of the corpus depends on. No verdict is reserved in advance for any finding class, and re-typing runs in both
directions. A dead-code label is not substantiated until the specification corpus has been asked whether the component is intended: a component no code path reaches, but that the
specification or a configuration surface expects, is a missing integration, not dead code.*
Evidence: per finding — which artefact is load-bearing, the specification-corpus answer, and the Type the finding carries after adjudication.

### 5. Whether the recommendation can be carried out

*Does the recommendation name a target that exists and is stable, does applying it remove the defect it claims to remove, what does it depend on, and what else breaks — and in which
order. A recommendation that is vague, offers alternatives, or names no implementation approach is substantiated but unusable: a distinct outcome from rejection, recorded as such
rather than passed over or counted as a failure.*
Evidence: per recommendation — target resolved, dependencies, what fixing it breaks, and its order in the roadmap.

### 6. Cross-phase conflict, ownership and merge

*Ownership decisions accumulate across the family, so a claim filed under a phase that does not own it — or two phases claiming the same concern — is a defect in the audit, and
detecting it is a first-class obligation, not an optional extra. Compare against whatever sibling reports exist, declare which are raw and which already validated, and record
rather than silently edit a merge whose target sits in a phase already written out. Same root cause is a merge; an adjacent concern is a cross-reference; two phases reaching
opposite conclusions about the same subject is a conflict.*
Evidence: per contested finding — the rival claim, the phase that owns the concern, the disposition, and the set of sibling reports compared against.

### 7. Namespace integrity — the ruling this phase owns

*Establish six shapes per prefix: the declared prefix; the identifiers past runs minted; provenance markers embedded in shipped code, configuration, tests and documentation; a
phase-qualified compound form that resolves to none of the others; a controlled template's own list of prefixes; and one namespace reused across phases. Then render a ruling
rather than only counting collisions — whether a new run reuses the declared namespace or mints a second one beside it, and whether the in-source markers are load-bearing
provenance to be migrated by a follow-up or drift to be retired. A validator that enumerates a collision and stops has not done this block.*
Evidence: per prefix — declared, minted, in-source marker count, the compound form where present, reuse across phases, and the ruling applied.

### 8. The report template as a controlled artefact

*The template this phase produces against is itself under validation. Establish whether the prefixes it enumerates cover every phase that exists; whether the severity-rubric
pointer pattern it declares matches the filenames phases actually carry, or whether it has ever resolved; how many reports carry that field at all under its declared name,
omitted, or renamed; whether the front-matter fields a validated report must set are present and honest; and whether every field the template mandates per finding survives
into the report. Record the defects — never repair the template from inside a per-phase run.*
Evidence: the template's prefix enumeration against the phase list; the declared pointer pattern resolved against a real filename; per field — present, omitted, or renamed; each
defect recorded, not edited.

### 9. Does the input rest on its own enumerated checks?

*Across this family the executed phases have shared one signature: their own named checks pass while their real findings arrive from an angle the phase never names — in some
phases the pre-pass states as expected the very mechanism that produced a finding, and in one the admissibility rule would have excluded every finding the run reported. Ask of
this input whether any substantive finding rests on its own phase's enumerated check list as its support, and whether the report contains at least one angle the list never
named. The answer is what it is; this block asks, it does not conclude.*
Evidence: per finding — whether its support is the input's own check list, an independent observation, or neither; and any finding arising from an angle the list does not name.

### 10. The validated report as an artefact, and what was not settled

*Every finding in scope carries a verdict, its own identifier and location, and the re-derivation behind it; the disposition tally agrees with the per-finding verdicts;
identifiers are preserved, never renumbered; the audited namespace and the validation namespace never share a table. The report is readable on its own, which requires the anchor
and the evidence rather than their removal. Every claim that could not be settled in this environment is listed with the reason and is never recorded as confirmed; where only a
stated sample could be re-derived, record the sample and the rate.*
Evidence: the disposition tally against the per-finding verdicts; each unresolvable or missing mandatory field; each claim left unsettled and why.

## Severity Taxonomy

These bands grade **defects in the audit**, never the audited finding: a finding keeps the band its own phase's rubric gave it, and a validator may re-grade it only against that rubric. Rate what is true now, not the worst consequence if triggered.

**A PASS row in the input report's own verification table is methodology, never a verdict, and no adjudication is gated on the input's check list.**

- **CRITICAL** — a wrong approval: a claim confirmed that the system does not support, or an absence recorded as established. A reader acts on it, remediation is built on it, and
  nothing downstream can distinguish it from a correct report. An empty band is a valid outcome.
- **HIGH** — a real defect released: a true finding rejected, merged away, or graded below what its own rubric implies, so work that must be done never reaches the roadmap.
- **MEDIUM** — a report the reader must repair before acting: a finding filed under a phase that does not own it, two claims about the same subject that disagree, a disposition
  tally that does not match the per-finding verdicts, an identifier resolving to more than one finding.
- **LOW** — drift with no remediation consequence today: template metadata that does not resolve, an unenumerated prefix, a naming or wording inconsistency.

## Report Output

- Findings path: `.ai/audit/99-validation/{NN}-{phase-name}-validated-findings.md` — one validated report per phase, carrying the audited phase's own prefix and identifiers
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: the audited phase's own prefix, preserved. Validation-level findings discovered *during* validation use `VAL-` and occupy a separate section — never
  interleaved into the findings table, because the two would share a `Severity` column carrying two different scales.
- Dispositions, one per finding in scope, and no verdict withheld: **confirmed** (kept as filed), **re-typed**, **re-graded**, **merged**, **not substantiated**, and **unsettled**
  where the environment cannot decide the claim either way. A claim that cannot be substantiated is **rejected** — never adjusted into vagueness, which releases a false positive
  into a validated report. Withhold approval and record why; never delete a true finding to avoid the decision. A finding confirmed unchanged still carries a disposition: that
  row is the deliverable, not a passing check.
- `problems-only: true` — suppress commentary about the validation itself, **not** dispositions
- Empty state, exactly: `No problems found in this phase.`
- Incremental append, ≤100 lines per pass — never write the entire report in a single call
