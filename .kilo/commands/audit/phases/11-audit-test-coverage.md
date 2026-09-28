---
name: 11-test-coverage
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 11 — Test Coverage

## Purpose

Audits the test suite as what it is — a distributed system with its own bootstrap, its own process model, its own parallelism, and its own failure modes — and asks of it the one question: if the product made
the wrong decision, would anything notice? The lens is the gap between the assurance the suite appears to carry and the assurance it delivers: behaviour reached but never asserted, doubles that remove the
property under test, a helper layer whose defaults are a second contract with the product, boundaries covered from one side only, a harness whose own machinery decides what can and cannot be tested, failures
nobody can reproduce, and gates that are declared, loaded, green, or inert. This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

Scope boundaries — other phases own: production-code convention defects and dead code (10); pipeline and container posture (12); transaction, lock, and pooler semantics (03); lifecycle correctness (05);
settings values and environment policy (02); namespace rulings and cross-phase conflict resolution (99). This phase owns whether the suite would notice, and the fidelity of what it asserts once it does.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Every block carries its own evidence. Evidence is a class, not a check list: a derived inventory with a stated absence, a reproduced
divergence between two sites, or an observed pass against a decision the test purports to cover; the method is the auditor's. A passing check is methodology, never a finding, and any sound evidence is
admissible — nothing here gates a finding on this phase's own checks. Where the environment prevents the suite from being run at all, establish what is establishable by other means and state plainly, in the
report, what could not be verified and why; an unreachable suite is a limit on the report, never a finding.

### 1. Exercised, not merely reachable

*Derive from the code — never from a list carried in this or any other file — the set of decisions the system acts on: a value chosen, a transition permitted or refused, a record selected or excluded, a limit
 applied. For each, ask what value of the decision its assertions would reject. A branch whose effect nothing observes, a returned value nothing inspects, a refusal whose absence no test would notice, a
 rendered surface no test renders, an assertion that holds for every value the decision can take: each reads as coverage and is not. A table that enumerates inputs while asserting one shared postcondition
 discriminates no more than an empty assertion, and a chain of assertions in which any one would fail for a reason unrelated to the property it names proves the chain, not the property. Include a mechanism
 whose stated purpose is to fire on one path, and establish what tests the paths it must not fire on.*
Evidence: the derived decision set with a per-decision verdict; one decision whose effect no assertion can observe; one test whose assertions survive the decision being
inverted.

### 2. What the doubles remove

*For every boundary a test replaces — a patched collaborator, a stubbed deferral or scheduling primitive, an in-memory stand-in for real persistence, a source-text inspection standing in for a runtime
 observation, a reconstructed call chain — establish what property of the real thing can no longer be observed, and whether any test anywhere observes it. Replacing an external transport is correct, cheap, and
 is not this block's finding; replacing the mechanism under test removes the subject. A double standing in for a mechanism that exists to enforce an ordering leaves the ordering untested while making it look
 tested, and an assertion reduced to matching the shape of the source observes the source text rather than the behaviour. Build the inventory from what the tests actually replace, not from a declared convention
 about what ought to be replaced.*
Evidence: the double inventory with the property each removes; one property observed by no test; one stand-in standing in for a shared resource.

### 3. The fixture data contract

*Establish what states and values the helper layer manufactures by default, whether the product can produce each, and what stays green precisely because it cannot. A default that silently produces a surprising
 value turns every consumer into a test of a fiction; a helper that absorbs a database constraint means no test ever has to satisfy it. Also establish whether a fixed value the production vocabulary already
 names is restated as a bare literal by a helper — the test layer's instance of a value that now has two homes, where one copy drifts silently and every consumer is tested against the stale one. And establish
 whether the key space helper defaults must populate is ordered and non-overlapping by anything but the test's own convention, so two independently valid setups collide on an identity no constraint separates.
 Where more than one helper universe exists, establish that they agree on the contract, and where they do not, which one the assertions are actually testing. Whether helper data carries real identifiers or
 secrets, and whether any of it reaches outside the test run, is the same contract asked of hygiene. The project rule that production code is king is the frame here, not a prohibition on the finding.*
Evidence: the helper-default inventory with a producible/unproducible verdict and the call-site count per unproducible default; the restated fixed values; the constraints
the helper layer absorbs; the divergences between helper universes.

### 4. Both sides of every boundary

*Establish, for each boundary the architecture creates — process, transaction, storage, cache, clock, file system — what is asserted from each side and what from one side only. A behaviour that exists only
 because two components agree is covered only where both are exercised, and a boundary crossed in production but stubbed in every test is a boundary with no test. Establish first whether a stand-in for a shared
 resource is in use: presupposing one produces a false pass, and so does presupposing its absence. Cross-refer a defect another phase owns rather than re-filing it, and record the test that stands between that
 defect and its fix.*
Evidence: the boundary inventory with a per-side assertion verdict; the boundaries asserted from one side only; the cross-references to findings owned elsewhere, each with
the test that gates their remediation.

### 5. The harness as a system

*Establish how the test schema is built, how reference data is restored, how parallel execution partitions and isolates, what bounds a runaway query, and what each registered marker is wired to. Then establish
 the substitution semantics of the invocation: what a caller loses when the default options are overridden, and whether the two execution paths this project supports reach the same runtime configuration.
 Several arrangements here are deliberate and hard-won, and each is a claim to verify rather than a defect: a step excluded from the fast path, where nothing detects the failures running it would otherwise
 surface; two helper universes separated by an execution model neither can cross; an import-path shim retained so that existing patch targets still resolve after their module moved.
 Establish what each costs, what still holds it in place, and what a change would have to preserve. Finally: which tests the harness cannot currently host, and which missing coverage each explains. Establish
 what a data-level schema change does to the run — its effect, not only whether a migration applies cleanly and twice — since a schema built by a strategy other than the migration path cannot see it.*
Evidence: the schema, reference-data, isolation, and marker-wiring facts; the override-substitution delta; the deliberate arrangements with what holds each in place; the
tests the harness cannot host and the gap each names.

### 6. Reproducibility and debuggability

*Given a red run in automation, establish whether it can be reproduced: what varies per run and whether the variation is recorded where a reader of the log will find it, what is unbounded while a test runs,
 what a parallel run does that a serial run does not, and what a reused resource carries forward into the next run. Do not settle for running the suite twice and comparing. Order-independence is a per-test property
 and not a suite property: a shuffling plugin makes no individual test independent, so establish which tests depend on a resource another test left behind and which depend on being first. A test that reads the
 same clock, the same ambient environment, or the same process-wide state as the code it exercises is not isolated from the code it tests.*
Evidence: the per-run variable inventory with what is recorded and where; the unbounded resources and their owners; the process-wide state a test shares with production
code; what state a reused resource carries between runs; the recovery procedure for a red automated run.

### 7. What actually blocks a merge

*For each declared gate — static analysis, types, tests, coverage, translation completeness, security and dependency and secret scanning, deploy check, scheduled suites — establish whether it is loaded, whether
 it is green, and what its scope excludes. Four absences are distinct and must be told apart: a gate declared and never loaded, a gate loaded and red, a gate whose scope omits a whole process tree, and a gate
 whose configuration sits in the repository but is never read from the directory it runs in. Where the gate is a type checker, ask what it is configured to enforce, what its configured scope includes, and what
 noise class is sanctioned: assert no strictness bar the project did not set, and treat no diagnostic count as the finding. This phase owns only whether the test tree is inside that gate's scope and whether the
 gate is currently red — the population of diagnostics in production code and its sanctioned suppressions is another phase's. Where the gate produces a coverage measure, establish what the artefact it produced
 can actually see before its number is quoted: which configuration it read, from which working directory, what it omitted, and which process trees are absent from the report. That is a question about the
 effective scope of a measurement, not a bar to clear.*
Evidence: the gate inventory — loaded or not, green or not, scope; the gates whose scope excludes a process tree; the type checker's configured mode and sanctioned noise
class; the coverage artefact's effective source selection.

### 8. Declared test-layer contracts

*Establish whether each property the test layer asserts about itself — in a helper's docstring, a settings comment, an entry-point comment, a marker description, a test that asserts the text of a configuration
 file — is true of the code it describes, and whether anything checks it. A comment that describes the harness differently from how the harness behaves is a finding here, not a source. A test whose subject is
 the text of a configuration file passes when the text matches and fails when a line is reformatted, so establish what it can actually detect: which property of the running system a change to that text would
 have to break, and whether that is the property it is being relied on for. A registered marker is not evidence of use and a used marker is not evidence of justification; a helper nothing calls is a question of
 purpose, not of deletion. Scope here is the test layer; production-code convention and dead code are another phase's.*
Evidence: the declared-property inventory with a holds/does-not-hold verdict; one comment the code contradicts; one assertion about configuration whose failure modes are
not the ones it appears to guard.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed list of mechanisms, so a defect whose
mechanism is not named here still lands by the consequence it is producing. A band with no present occupant is left empty, not filled.

- **CRITICAL** — the suite's green is affirmatively false today: a shipped assertion the product cannot satisfy, or a decision the system acts on whose effect no assertion anywhere can observe, where the
  unobserved effect is one a user or a seller receives.
- **HIGH** — a gap that will be mistaken for coverage and is silent today: a decision exercised only through a stand-in for the thing it decides, a boundary asserted from one side only, a property the harness
  depends on that nothing holds it to, a gate declared and never loaded, a measurement whose effective scope is not the scope it is read for.
- **MEDIUM** — bounded and real, with a specific audience: a gate loaded and red over a known accepted-noise class, a resource left unbounded so that one test can take the run down, state carried forward
  between runs, a cost that makes a gate get disabled.
- **LOW** — self-description and hygiene with no runtime consequence today: a test-layer comment that misdescribes the harness, a duplicated helper with no divergence yet, a marker registered and inert, a test
  whose subject is configuration text it cannot actually detect a change in.

## Report Output

- Findings path: `.ai/audit/11-test-coverage/findings.md` — cumulative: a new run appends or supersedes, it does not restart
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `TST-` — **already in use** in shipped source and operations documentation from a prior cycle, with at least one identifier already resolving to two different findings; check for a
  collision before minting an ID and report it rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
- If a shipped test asserts the current behaviour as intended, still file the finding and record the test as a remediation blocker.
