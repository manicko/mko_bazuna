---
name: 07-media
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 07 — Media Handling & Security

## Purpose

Audits the media path end to end: what an incoming image is admitted against, where its bytes are written and under what key, what is derived from them, what the serving path hands out and on whose word, what removes them, what reconciles the store against the records, and how several long-lived processes share one store while they do it. This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

Scope Boundaries — other phases own: sweep execution safety, meaning bounded, interruptible, locked and repeatable (03); what a retention operation selects and which clock it reads (05); the erasure cascade into physical file removal (06); search visibility (08); the platform download client and transport (09); enum and boundary-DTO discipline (10); test adequacy (11); probes and storage operations (12); authorization (15).

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed behaviour, a static proof that a stated property does not hold, or a reproduced divergence between two paths; the method is the auditor's. A passing check is methodology, never a finding, and any sound evidence is admissible — nothing gates a finding on this phase's own checks.

### 1. Storage-key ownership and what a removal actually guarantees

*Derive the key classes, then establish per class what it must guarantee about the bytes it names: some are deliberately shared
between live records, some deliberately predictable, so demanding unguessability or uniqueness across all of them tests a decision
the system made on purpose. How many live records may name one key, which mechanism shares deliberately and which by accident, and
what duplicating a listing or removing one referrer does to the others — including a removal that leaves a live record naming bytes
that are gone. Then establish what actually holds between a record's removal and its bytes', given no referential relationship to
the store: what waits for the commit, what is retried, what a failure leaves behind, and where that guarantee is broken.*
Evidence: per key class, the property it must hold and whether it does; the ownership rule actually enforced on removal; one shared-key state and what removing one referrer did to it.

### 2. Ingestion admission: which limits exist and where each is actually applied

*For every admission control on an incoming image — payload size, pixel dimensions, decode budget, per-ad item count, arrival rate —
establish which layer enforces it, in which long-lived process, at what point relative to transfer and decode, and how many places
declare its value; derive the site count rather than assuming it. Ask whether the declarations can disagree, whether a control
enforced by one process is absent from another that writes the same store, whether a limit exists that no path consults, and whether
a limit is a property of a code path or of a running process: a ceiling installed by mutating a library-wide setting during start-up
holds only where that start-up ran. Where no live external service can be reached, establish each control from a constructed payload
and a direct call into the admission path, and record what that evidence does not cover.*
Evidence: per control, the enforcing layer and process, its declaration sites, and any divergence between them.

### 3. Metadata removal: which layer strips, which processes reach it, and what the re-encode changes

*Establish where hidden metadata is actually removed: which component performs it, which long-lived processes reach it, and whether
any write path stores bytes without passing through it. Then establish what the removal costs — a full re-encode changes pixels,
compression and colour handling — and whether its parameters are a stated contract or an inherited default that two independent
pipelines need not share. Where no external inspection tool exists, establish absence with the decoder's own reader plus a raw
container-segment walk, and record that the check was library-only.*
Evidence: the removal call sites and the processes that make them; the re-encode parameters and where they are stated.

### 4. Derived-file generation: atomicity, partial sets, and whether repair reaches them

*Establish whether a derived set is materialised as a unit: whether members are written one at a time, what an interrupted
generation leaves behind, whether records naming the set can be written while it is incomplete, and whether the guard that makes
regeneration safe distinguishes a stale leftover from a concurrent writer. Include the reverse case — a record naming a derived file
that was never written — and whether the repair path can reach the broken state it exists to fix. Resource bounds on the transform
are part of the question, not the whole of it.*
Evidence: per derived set, one interrupted generation and what remains; the repair path's verdict on that residue.

### 5. The serving gate: which predicates it consults, and both directions of failure

*Establish what the request-time access decision consults and what it does not. Ask both directions explicitly: what it refuses, and
— the one that is easy to miss — whether it authorises anything it should not. Establish whether it rests on the existence of a
record or of the resource behind it, whether a second serving branch with different rules is reachable in another environment, and
whether a crafted key is refused by the request path, the storage layer, or the schema alone. This block owns the decision; whether
anything detects the state that follows is block 7's. The visibility predicate is 05's and 08's, the audience predicate 06's; the
enforcement mechanism is this phase's.*
Evidence: the predicates consulted and the branches they live on; one request authorised for a resource that is not there.

### 6. Exposure of this path relative to the paths served beside it

*Compare this path's own rating, hardening and failure responses against the other public paths the same front door serves, and
establish whether a control a document claims for it exists in the shipped configuration. Establish what the application hands to
the proxy tier in front of it, and whether a response the proxy cannot fulfil is ever produced; a control appearing on only one of
two environment-dependent serving branches is an asymmetry in the design, not a difference between deployments. Where no live proxy
tier can be exercised, the shipped configuration is the authority and the residual is recorded as unverified rather than passed.
Transport and header policy are another phase's.*
Evidence: this path's controls measured against a sibling path's; any documented control absent from the shipped configuration.

### 7. Reconciliation between the store and the records, in both directions, and what is exempt

*Establish the difference between what the store holds and what the records name, and compute it in both directions: a file no
record names, and — state this one explicitly, because difference-based tooling is one-sided by default — a record naming a file
that is not there. Per direction, establish whether anything detects it, whether anything repairs what it detects, and every part of
the store excluded from the comparison and why. Establish who may mutate the shared store while it is taken, and which of those
mutations it does not exclude. This block owns detection and repair; whether the access decision itself should notice the missing
resource is block 5's. Locking and repeat-run safety are another phase's.*
Evidence: both directions with a per-direction detector verdict and repair verdict; the excluded subtrees and their stated reason.

### 8. Capacity of the in-flight area: arrival rate against residence time

*Establish what bounds the in-flight area: what limits arrival, what reclaims what has been abandoned, and whether each bound is on
time, on count, or on bytes — a time bound does not bound a rate, and a count per flow does not bound bytes. Establish whether
reclaiming an entry converges whatever still points at it, and whether the area shares storage whose exhaustion stops something
wider than one upload.*
Evidence: the controls on the in-flight area, each classified by what it actually bounds; the shared-storage consequence of exhausting it.

### 9. Removal granularity, and the record of a removal that failed

*Establish whether a single item can be removed without destroying the record that holds it, which audiences can reach that
operation, and whether the collection is append-only by construction. Then establish what happens when a removal fails: is the
failure recorded, what reads that record, how long it is kept, and whether an operator can see it or act on it. What triggers an
erasure, and what an account's state means, is 06's — this block is the physical removal mechanics and the failure record only.*
Evidence: per audience, the removal operations that exist; the failure record's readers, retention and alerting.

### 10. Declared media contracts against what the code does

*Establish every statement the repository makes about this domain — the structure of a stored resource's name, who owns the bytes,
what a removal removes, what a maintenance operation selects, which controls the serving path carries — and check each against the
code. A statement nothing enforces is a finding in its own right, and an operation whose documented selection rule contradicts its
own predicate is another. Record which source is authoritative when two disagree, without picking a winner in the report.*
Evidence: the statement inventory with a true/false verdict each; one operation whose documented rule and its own predicate differ.

### 11. Cross-process coordination over the shared store

*Establish which long-lived processes read and mutate the shared store, and per operation whether it is mutually excluded and by
what. Ask what happens when a producer moves a stored object from one namespace to another that carries different rules and finds
its source already absent: is the failure silent, and is the destination recorded regardless. Establish whether the process that
removes metadata is the one that later publishes the bytes, and whether that separation is deliberate. Where a race cannot be
staged, establish the exclusion or its absence from the code together with the reachable interleaving, and record what the evidence
does not cover. Locking mechanics and repeat-run safety are another phase's; the storage contract is this phase's.*
Evidence: process × operation matrix with a mutual-exclusion verdict per operation; one operation whose failure is silent.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — bytes or content destroyed, overwritten, or exposed irreversibly while a live record still names them: a stored file removed or replaced with nothing that detects, repairs, or reverses the loss; a file handed to a caller the access decision is meant to refuse; hidden personal data still recoverable from a stored or served file after its removal obligation has completed.
- **HIGH** — a silent correctness failure with no self-healing path: an operation reports success while leaving the state it claims to have prevented or repaired; a record naming a resource that is not there, or a resource no record names, with nothing detecting it in that direction; two paths to the same state disagreeing about which is correct; a declared guard not consulted on the path it is meant to bound; a public path materially weaker than the paths beside it.
- **MEDIUM** — a bounded resource or operability gap: an area reclaimed by age but unbounded in count or bytes, or limited by events rather than by the resource consumed; an operation available only at a coarser granularity than the task it serves; a recorded failure with no reader, retention, or alert; a stored artefact whose production parameters are unstated; a part of the store exempt from a comparison that otherwise runs.
- **LOW** — documentation and observability drift with no runtime consequence today: a stated key structure, control, or selection rule the code does not implement; a comment or docstring asserting an invariant nothing enforces; one limit declared in more than one place with no divergence yet; a status line or counter reporting attempts as confirmations.

## Report Output

- Findings path: `.ai/audit/07-media/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `MED-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting current behaviour is a remediation blocker, not a gate
