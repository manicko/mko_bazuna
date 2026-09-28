---
name: 10-code-quality
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 10 — Code Quality

## Purpose

Audits whether the code holds to the conventions the project has adopted, and whether the properties the codebase and its documentation claim are the properties that actually hold. The lens is the gap between a rule and its enforcement: where each fixed value lives, which input boundaries validate, what a type checker is
configured to catch, how much one unit does, whether a rule has one implementation, and what the automation would notice if any of it stopped being true. This file names what to examine and under which angle; the executing auditor
discovers the concrete artifacts.

Scope boundary — other phases own: settings values and environment policy (02); transaction, lock, and pooler semantics (03); lifecycle correctness (05); the event-loop bridge mechanism (09); test adequacy (11); pipeline and container
posture (12); measurable performance consequences (13); authorization (15). This phase owns convention and consistency inside the code, and asks of every claimed property whether anything checks it — not what a lifecycle decision
should be, what a request is allowed to do, or how the service is run and deployed.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Every block carries its own evidence. Evidence is a class, not a check list: an inventory with a stated absence, a static proof that a claimed
property does not hold, or a reproduced divergence between two sites; the method is the auditor's. A passing check is methodology, never a finding, and any sound evidence is admissible — nothing here gates a finding on this
phase's own checks.

### 1. Fixed values: one named home per value

*Establish, for every fixed value the system branches on, whether it has exactly one named home. Look for a value written as a raw literal at a second site: compared or defaulted as a bare string where a named
vocabulary exists, or repeated inside a framework-facing surface — configuration, a template, a route, a form field, a translation key, a persisted column default. A named home that exists and is bypassed is the finding;
the literal itself is only the evidence. Also establish which of these values the type system could catch being wrong, and which are indistinguishable from a plain string at the point of use, so that a value the
project has already decided to constrain carries nothing that constrains it. Where two project rules pull against each other and the code resolves the tension, ask whether the resolution is recorded anywhere or
survives only in the one file that happened to resolve it.*
Evidence: the fixed-value inventory with its named home or its absence; the raw-literal sites grouped by framework-facing surface; the values the type system cannot distinguish from a bare string.

### 2. The constant surface as a maintained artifact

*Treat the constant modules as a maintained artifact, not a registry. Is an identifier family's numbering and ordering documented and evidently deliberate, or is it a sequence whose only explanation is the sequence
itself? Is membership derived outside the vocabulary it belongs to, in a structure the vocabulary's own consumers must know about? Is a private name published in a public export list? Is a mapping stored inside the
vocabulary it belongs to, so reading the vocabulary requires understanding a second structure? Is a value table constructed inside the function that consumes it, so no second component can consult it and every
caller re-derives legality independently? Is a named vocabulary exported, documented, and offered in a surface — a choice list, a schema constraint, a form field — while no code path enforces it? And is a value's required
type enforced where it is declared, or merely assumed at the sites that read it back?*
Evidence: per constant family — numbering convention, membership provenance, export-list contents; one value table with no reader but its own consumer; one vocabulary offered in a surface with no enforcing path.

### 3. Boundary validation coverage

*Establish which input boundaries validate and which do not: the transport, the parse, the validation model or its absence, and what reaches persistence. A boundary is a place where untrusted data becomes a row, and
the uncovered ones are the finding, not an exception to be noted. Treat the strictness of a shared validation base as a claim to verify, not a precondition — a model that does not inherit it, or that sets a
permissive unknown-key policy, is a boundary whose contract differs from the one the base describes, and whether the difference is deliberate must be established from the code and from whatever records it.
Where a boundary validates, ask what it validates against: a vocabulary that is narrower than the column it guards accepts every value the column would have rejected. Then ask what a field default means when the
key is absent: a default that is a legal value for "empty" silently overwrites stored content rather than leaving it.*
Evidence: the boundary inventory with a per-boundary validation verdict; every model departing from the shared base and the reason recorded for it, or the absence of one; one boundary where an absent key overwrites
existing content.

### 4. Type width and the sanctioned-suppression surface

*Establish what the type checker is actually configured to enforce and what it is configured not to: the checking mode, the disabled diagnostic classes, and any framework stubs deliberately declined, together
with the reason the project recorded for each. Never assume a strictness bar the project did not set, and never treat a non-zero diagnostic count as the finding. The accepted noise is a sanctioned-suppression
population, not a zero-error population — establish its size, its cause, whether any whole cluster could be retired by fixing one root cause, and whether each suppression is still warranted at its own site or
has outlived the construct it silences. Then classify every widened annotation as load-bearing or accidental: a parameter typed as a plain string defaulted with a vocabulary member, a container return with no
element type, a variable declared only to satisfy the checker, a return type that is broader than every value the function can actually produce. Production code only — a project may legitimately hold its own tests
to a different bar, and a diagnostic in a test file is not this phase's finding.*
Evidence: the checker's configured mode and disabled classes with the project's stated reason; the suppression population by cause; the widened annotations with a load-bearing/accidental verdict.

### 5. Responsibility inside a unit

*Within one view, handler, service, or helper, establish how many distinct responsibilities it performs — authorization, locking, validation, business decisions, formatting, persistence — and whether any of
them is reachable from anywhere else. A unit reported only as a line count has not been analysed: report the responsibilities, and ask whether extracting one would change what the tests can reach. Size is the
prompt; the multiplicity is the finding. Include a unit whose bulk is one long literal, one generated block, or one wide data mapping rather than several responsibilities: a size signal with nothing behind it is not
this block's finding, and saying so is as much a result as listing the responsibilities. The entry-layer boundary and the direction of dependency between layers are another phase's; what is examined here is
only what happens inside one unit — and a second copy of one rule inside the same layer is still in scope, however small the layer is.*
Evidence: per oversized unit, the responsibility list; one responsibility with no reachable caller, and where the test suite can reach it; one large unit with a single responsibility.

### 6. One rule, one home

*For each rule more than one component must obey, establish whether exactly one implementation exists. A byte-identical copy is a second site the next change must be made in; a near-copy is one the two have already
begun to disagree on; a second implementation with a different threshold, ordering, or tolerance is a live divergence. Where a site deliberately does not share the common implementation — a re-export package that
exists to keep an import direction, a shared helper kept free of an error-handling or dependency contract a specific caller cannot take — establish that the reason is recorded where a reader of that site will
find it, and that the reason still holds against the code as it is now. A site that does not share the common implementation is a claim to establish, not a duplication to file. Apply the same test to a shared seam's
own stated reason for existing — a seam whose stated purpose is to preserve the semantics of the call sites it was extracted from is a seam to examine, not a success, because preserving those semantics is a
contract it now owes everyone who adopts it.*
Evidence: the rule-to-implementation-count map; one rule whose implementations disagree; every deliberate exclusion with its recorded reason and a holds/does-not-hold verdict.

### 7. Convention compliance: the cheap high-volume rules

*One pass over the mechanical rules that are cheap to check and cheap to violate: standard-output writes on a production path, including a debug-gated one and one reached only at startup; the language of
comments, log records, docstrings, and error text that is not user-facing; naming; import ordering, an import deferred into a function body to dodge a cycle that no longer exists, and an import-time side effect
whose correctness depends on some other module having been imported first; packaging that makes an import resolve differently from its neighbours — a missing package marker, a directory present but
unregistered, a shim beside the thing it shims. Include code that is present, reachable, and referenced by nothing, where the question is what it was for rather than whether to delete it; the answer may be a
feature that is not switched on yet, and that too is a fact to establish. User-facing text is another phase's.*
Evidence: the convention sweep with per-rule counts and the corpus behind each; the unreferenced-definition list with the intent of each.

### 8. Declared contracts and their enforcement point

*For every property the code or its documentation asserts — in a docstring, a comment, a named guard, a validation hook, a checklist — establish whether anything checks it and whether anything reaches it.
A declared invariant no reachable caller enforces is documentation; a documented rule the code contradicts misleads every later reader, including a claim of universal coverage that a handful of deliberate
exceptions already falsify. A comment that describes a condition differently from the condition the executing path actually applies is itself a finding here, not a source: the answer to "what does this gate
check" comes from the path that runs, never from the prose above it. Also ask whether the project's own guidance is written where the code is being changed, or only in a rules file no contributor opens at the
moment they are making the change.*
Evidence: the declared-property inventory with an enforcement point or its absence; one documented rule the code contradicts; one validation hook no caller reaches.

### 9. Migration discipline and schema drift

*Establish, for every model change, whether the schema history records it — and then, separately, whether anything would notice if it did not. The claim to test is not "a migration exists" but "a gate fails when
one is missing": establish whether the automation runs a drift check at all, over which paths, and whether a check present in configuration is actually executed on every change, or is declared and never wired
in. Do not assume a gate exists until one is found running; its absence is the finding, not a failure of the block. A check that exists but that no contributor can run locally is a different absence, and a
narrower one. Separately, establish whether schema or reference data is mutated from a code path rather than from a migration, and whether such a path is idempotent if it is run twice — a sweep, a backfill, a
repair run, or a data fixture that writes to the database as a side effect of being imported.*
Evidence: the gate inventory — which drift checks exist, where they run, and what they cover; one model change with no recorded migration, or the confirmation that none exists; every non-migration schema
mutation with an idempotency verdict.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed list of mechanisms, so a defect whose
mechanism is not named here still lands by the consequence it is producing.

- **CRITICAL** — a wrong or lost value is in storage now, or the only thing that kept a rule true for everyone is gone: a stored value that no rule ever constrained, a field default that
  overwrites stored content when the key is absent, two implementations of one rule whose copies already disagree on a value the system acts on.
- **HIGH** — silent today, and the next change is guaranteed to be made wrongly in the same place: a value with two homes, a declared invariant nothing enforces, a shared helper whose stated reason has
  stopped holding, a rule that must be changed in several places with no single discoverable one, schema drift no gate would notice.
- **MEDIUM** — a bounded correctness or operability gap with a specific, limited audience: an unvalidated boundary on a non-critical path, a widened type on a value nothing branches on, a
  duplicated helper with no divergence yet, a constant surface whose conventions are undocumented, a convention rule broken in a narrow surface only.
- **LOW** — documentation, reachability, and hygiene drift with no runtime consequence today: a declared rule no caller reaches, a private name in a public export list, a comment restating the code, an
  unreferenced definition nobody has explained.

## Report Output

- Findings path: `.ai/audit/10-code-quality/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `QLT-` — **already in use** in shipped source from a prior cycle, with at least one identifier already resolving to two different findings; check for a collision before minting an ID
  and report it rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- If a shipped test asserts the current behaviour as intended, still file the finding and record the test as a remediation blocker.
