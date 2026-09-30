---
name: 06-pii-consent
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 06 — PII Protection & Consent Compliance

## Purpose

Audit consent semantics and versioning, what withdrawal and erasure reach, personal
data containment inside the system and on its way out, content hiding on state
change, and contact-surface parity in a dual-process system over shared state.

Scope Boundaries — this phase owns consent semantics, erasure completeness, PII containment,
and egress basis. Other phases own: identity binding and the account-state gate mechanism
(04); transaction and lock execution safety, and retention-operation execution safety
(03, 05); media file-handling mechanics (07 — this phase owns only the erasure cascade into
physical removal); whether a stored aggregate outliving its subject is arithmetically
supported is 17's; the residue and the erasure cascade are this phase's; authorization
(15); settings and secrets values (02); what executes in the client is 16's; a consent
gate a third-party widget enforces server-side is this phase's.

This file names what to examine and under which angle; the auditor finds the artifacts.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class,
not a check list: observed behaviour, reproduced output, or a static proof that a stated property
does not hold. A passing check is methodology; nothing gates a finding on this phase's own checks.

### 1. Consent states: where each consequence is defined

*Establish the states an account can hold and, per state, every source stating its consequences
— the text shown, the written policy, an owner decision, the recorded decision, the query and
template filters deciding visibility. Where sources disagree, report whether a correct
implementation could pass against one and fail against another; pick no winner. Also whether a
later choice reverses an earlier recorded state.*
Evidence: per state, the sources stating its consequences; each disagreement.

### 2. Consent provenance: what is recorded and whether it stays interpretable

*Establish whether each consent action leaves a durable, attributable record, and whether the
version recorded ties back to the text the person saw. Judge any normalisation, fallback, or
default that can relabel a record without failing — including whether a lenient acceptance at
the input boundary decouples the recorded version from the displayed one. Treat a
single-valued version identifier as a claim to test. Include the visitor with no account.*
Evidence: per action, what is recorded; version definition sites and fallback paths.

### 3. The personal-data set, what erasure reaches, and which clock it reads

*Derive, do not assume: inventory every column, table, file, and derived value that holds or can
re-identify a person, including stores unrelated to the account row. Measure the withdrawal path
and the deferred sweep against it — erased, hidden, detached by a nulling reference, or surviving
with no stated purpose. Of the retention window: defined once or duplicated, tunable by an
operator, and does the clock the sweep reads start where the obligation does?*
Evidence: inventory; per item, the erasure verdict; the window's sources and the timestamp read.

### 4. Identifier fields after erasure: which cease to identify

*Establish every field the system treats as an identifier, then whether the erasure paths agree on
which cease to identify — cleared on one path and retained on another, emptied where absent was
required, a sentinel left standing where absence was meant. Judge whether the two processes agree
on when each field stops identifying, and whether a returning person resolves to the old record
or to a second one beside it. Derive the field set; do not assume its size.*
Evidence: identifier set; per path, fields cleared and retained; one timing disagreement.

### 5. Residual artifacts after a completed erasure

*After a full erasure completes, establish what personal data still exists: rows surviving by a nulling
reference and the columns they carry, consent and audit records, files and their derivatives, cache
entries and their lifetime, derived copies and rollups, anything already handed outside. For each,
whether anything purges it; treat a surviving session handle or network identifier as personal data.*
Evidence: residue inventory; per item, retention and reclamation path.

### 6. Content hiding across every public surface

*For each account state, establish what a public surface is required to withhold and what it
actually withholds — list and detail views, search results and their cached copies, feeds,
directly-addressed media, the owner's own view. Ask which predicate each surface consults, and
whether a cached copy can serve what the live query would exclude.*
Evidence: per state × surface, the predicate consulted; one cached-vs-live divergence.

### 7. Contact surface: parity between deciding and delivering

*Establish the condition set the contact surface actually requires, then compare the point where
it is decided with the point where delivery happens — by the fields consulted, including duplicate
implementations; and what the outbound artefact carries to a non-owner of the record.*
Evidence: decision-side and delivery-side predicate; one state change between the two.

### 8. Personal data in internal telemetry

*Establish what a stored event, a log line, an exception payload, a cache entry, and an operator
screen each retain about a person, judged against the purpose it is kept for, and whether a masked
value is masked at the source, at the sink, or only in the display layer. Identity data here;
credentials are another phase's.*
Evidence: per store, the fields retained and their stated purpose; the masking point.

### 9. Personal data leaving the system under a stated basis

*Inventory every destination outside this system that receives personal data. For each: what is
sent, to which recipient, under what stated basis, whether that basis is a control or only a comment
or a policy page, and whether the send is gated by the consent state held at the time. A claim that
a transfer carries no personal data is a finding unless something enforces it. Name the recipient,
not the transport.*
Evidence: recipient inventory; per recipient, payload, basis, and the enforcement — or the comment.

### 10. Cross-process consent consistency

*Establish what a consent change must take effect on and when: other live sessions, in-flight work,
queued jobs, the eligibility decision in each process. Confirm or refute that the process which did
not record the change observes it, that the two consent predicates agree over the same state, and
that no cached consent decision outlives the state it encodes.*
Evidence: per consumer, the source of the consent state; one stale-decision case.

### 11. Soft delete and hard delete

*Establish what soft delete and hard delete are each meant to make different, and whether each is
correct: what each hides, for how long, reversibly by whom, what a hard delete is meant to leave
behind, and whether a partial or repeated operation converges. Locking mechanics are another's.*
Evidence: per content state, the visibility verdict; one interrupted and one repeated operation.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

| Severity | Conditions |
|---|---|
| CRITICAL | Personal data of a person who asked for it to be erased still identifiable or machine-reachable after the erasure operation has completed; a public surface serving content a person has withdrawn or erased; a consent or audit record readable as proof of a choice the person did not make |
| HIGH | An identifier one process retains after another has scrubbed it, leaving a withdrawn person addressable; personal data sent outside the system on a basis asserted only in a comment or a policy page; the two processes' consent predicates disagreeing over the same state; a contact surface reaching delivery without the check its decision point applies |
| MEDIUM | Personal data retained past the point it serves a purpose with no reclamation path; a cached result or client-held decision outliving the state it encodes; a retention window or erasure clock defined in more than one place or not adjustable by an operator; free text a person authored still readable after erasure |
| LOW | Documentation stating a different consequence from the one implemented; residue no reclamation path reaches; refusal and erasure paths that leave no operator-visible trace |

## Report Output

- Findings path: `.ai/audit/06-pii-consent/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `PII-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting current behaviour is a remediation blocker, not a gate
