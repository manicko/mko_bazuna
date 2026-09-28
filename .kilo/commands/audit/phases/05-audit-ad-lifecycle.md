---
name: 05-ad-lifecycle
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 05 — Ad Lifecycle, Categories & Moderation

## Purpose

Audits the lifecycle of the ad and everything that decides whether it is public: its state model and the boundary meant to enforce it, parity between the many routes that write it, the timestamps and the clocks later decisions read, the publish gate as both a visibility contract and a policy, the privileged surface that moves it, the classification tree and the values copied onto ads from it, the photo collection as an invariant carrier, and the cleanup operations that expire rows by age. This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

Scope boundary — other phases own: transaction, lock, and repeat-run execution safety (03); consent, erasure and publishing-ban policy (06); file-handling mechanics (07); search-index behaviour (08); fixed-value enum discipline and boundary DTOs (10); test adequacy (11); probes (12); authorization, and which surfaces a request-forgery check reaches and whether it runs on each (15). This phase owns lifecycle correctness — what a cleanup operation selects and which clock it reads, and the lifecycle meaning of a derived currency value: whether the decision a transaction carries is the right one, not how its transaction is bounded.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed behaviour, a static proof that a stated property does not hold, or a reproduced divergence between two paths; the method is the auditor's. A passing check is methodology, never a finding, and any sound evidence is admissible — nothing here gates a finding on this phase's own checks.

### 1. Lifecycle state model and its enforcement boundary

*Establish the lifecycle's vocabulary from the code, not from documentation: the state set, the legal transitions, which states admit an exit, and the side effects each transition is meant to carry.
Which state values are actually observable in a committed row outside the transaction that set them — a state no committed row ever holds, while features branch on it, is a finding. Map every surface that can write a state:
application code, declarative admin surfaces, set-based and bulk updates, raw SQL, imported automation. Which are guarded by the transition contract, and which write a state without its lifecycle consequence?
Confirm or refute that a state claimed as terminal is terminal on every path, not only the one that declares it.*
Evidence: the derived state set and transition matrix with the source of each; state values observable in a committed row; the state-writing surface inventory with a guarded/un-guarded verdict each.

### 2. Write-path parity for the same entity

*Enumerate every route that creates or materially changes the persisted ad — the full submission pipeline, the status-preserving edit, duplication, reactivation, archiving, deletion, the privileged routes —
and for each establish its lifecycle effect, and whether the absence of that effect is intentional. Separate routes that deliberately skip the pipeline but must not skip the state contract from routes that skip both.
Include a route that bypasses the dialogue layer and creates a partially populated entity directly; a route reachable more than once for one user intent; a lifecycle effect attached to the
persistence event rather than to the state change, so a set-based write skips it; and a derived value, consulted by more than one writer, whose freshness is a property of a route, not of the row.*
Evidence: route inventory with per-route lifecycle effects; one reproduced divergence from the pipeline; each effect carried by a persistence event, and which write surfaces never raise it.

### 3. Lifecycle timestamps and the clocks derived from them

*For every lifecycle timestamp, establish which transition sets it, which clears it, and which later decision reads it. Test everywhere for the general form: a timer set on one path and left stale
on another — a publish or activity clock that a later write to the row does not restart, a timestamp that survives a state which no longer justifies it, a clock meant to measure activity that
measures a fixed instant because no activity is recorded. Ask always what the duration is measured FROM: is the anchor the clock the writing operation intended, and does a state reachable by
more than one route carry one anchor per route? Include a stored instant compared against a wall-clock window.*
Evidence: timestamp × (writers, clearers, readers) matrix; one row where a write path leaves a clock stale; the anchor chosen per state per route.

### 4. Publish gate as a visibility contract

*Establish every path that makes an ad publicly visible, including paths outside the gate's own domain — declarative admin surfaces, set-based updates, raw SQL, external automation, privileged
interfaces — and for each whether it passes through the gate and whether its absence is an intentional privilege or an oversight. Then establish every reader that gates visibility: listings,
search, the index maintained at the database layer, seller-facing dashboards. Does a state change propagate to all of them? A visibility rule carried by a database row trigger covers row
writes only, so ask which of these surfaces it actually reaches.*
Evidence: the path inventory with a gated/un-gated verdict each; the visibility-gating reader inventory with one reader that does not receive a state change.

### 5. The gate's inputs, policy and decision record

*Establish where the gate's decision data comes from and how a change to it takes effect. A mutable configuration row, a cached read, or a process-local cache invalidated by a save event
is a policy surface: a change that does not take effect, or takes effect for some requests and not others, is a finding. Establish whether every cap, threshold and per-seller limit the
decision depends on is consulted on the path it is meant to guard, including guards written into the same expression but never evaluated. Then establish what is written when the gate
decides — an attributable record of who decided what on what basis — and what the same decision surfaces to the seller, which may be deliberately coarser than what is stored. Can the
policy as configured refuse an ad that satisfies every stated rule?*
Evidence: the decision-data inventory with its read path and invalidation trigger; every consulted guard and every declared-but-unconsulted one; the decision record and the seller-facing message for one decision.

### 6. Privileged action surface

*For every privileged operation on ads and on sellers, establish the authorization it requires (its presence only — the policy belongs to another phase), the per-entity record it writes, its
interaction with bulk and set-based execution, and whether it re-implements the state contract without the contract's guarantees. A second entry point to the same transition, written
independently, is a divergence waiting to happen: establish whether the two agree on legality, on side effects, and on failure behaviour. Include what a partially applied bulk run
leaves behind, and whether an error raised by the state contract is surfaced or swallowed.*
Evidence: privileged-action inventory with authorization, record written, and bulk behaviour; two entry points to one transition compared; the residue of a partial bulk run.

### 7. Classification tree and its denormalised dependents

*Establish the tree's own structure: how it is loaded and changed, and which surfaces may write it. Then establish every copy of a tree value denormalised onto an ad, and whether a rename, a
move, an activation, or a deactivation path repairs it. A repair attached to a row event fires only for the row it names: a node moved under a new parent, or a whole subtree deactivated
one level above the ads, repairs nothing. Establish whether listing and search agree about a node's visibility, and whether a tree invariant is enforced by the model or only by the loader
and the importer.*
Evidence: the denormalised-copy inventory; the mutation operations that repair each copy and the ones that do not; one node change with its un-repaired dependent.

### 8. Photo collection as an invariant carrier

*Treat the collection as an invariant carrier rather than as a count. Establish uniqueness of each entry, contiguity and determinism of the ordering, and ownership of the rows and of the
resources the rows name: can two entries claim one position, can a position exist with no entry, and where a row is duplicated, is ownership tracked so that removing one copy does not
destroy what another still references. Establish that the same cardinality limit is enforced by more than one unrelated mechanism, and where those mechanisms can disagree. Resource-handling
mechanics belong to another phase; the row-level invariant does not.*
Evidence: the collection's declared constraints against the ordering actually stored; one reproduced ordering or ownership divergence; the enforcement points for the cardinality limit and their divergence.

### 9. Retention and cleanup operations as a family

*Establish the cleanup family as a family — including operations that do not act on this entity at all, which a status-keyed list would hide. For each: what it selects, which clock it reads,
what it removes, and whether it can reach a row it was not meant to. Test the general forms: a selection predicate that can match a live or in-progress row; a clock that differs between the
operation that wrote the timestamp and the one that reads it, so two routes into the same state expire on different schedules; a state transition presented as a cleanup. Include a window
stated in one unit in the code and another in the specification, and an operation present in one deployment tier and absent from another.*
Evidence: the operation inventory with select-predicate, clock column, and target entity; one row each that a sweep can reach and should not, and one whose clock diverges from its writer.

### 10. Declared lifecycle contract and its reachability

*Establish reachability of the domain's declared lifecycle machinery: a registry, a helper, a guard, or a cleanup routine that no caller reaches — including a legal-transition table
constructed inside the function that consumes it, so no other component can consult it and every caller re-derives legality independently. Then establish the declarations as contracts: a
comment, docstring, or named constant stating an invariant the code does not implement, and a constant duplicated as a literal elsewhere. A contract nothing can reach is documentation; a
documented rule the code contradicts misleads every later reader. Constant discipline in general is another phase's — this is reachability and statement-truth in this domain only.*
Evidence: the declared-machinery inventory with a reached/un-reached verdict; one duplicated constant with its two enforcement points; one stated rule the code contradicts.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — the public-visibility or data-loss boundary is broken: content reaching the public without the gate, a state reachable that the contract must forbid, or a live listed row destroyed or expired by an operation that selected it wrongly.
- **HIGH** — a lifecycle decision silently wrong for everyone who takes that path: a publish clock that no longer matches its own policy, so a live ad is expired or a seller loses visibility; a gate that refuses an ad meeting every rule or admits one breaking a rule; a timestamp carried into a state that no longer justifies it; a whole route that triggers none of the side effects the normal path does.
- **MEDIUM** — a bounded correctness or operability gap: one route's lifecycle effect differing from the pipeline's; a denormalised value left stale by a node move or deactivation; a cached policy value served after the row changes; a derived value stale relative to the state it belongs to.
- **LOW** — documentation and reachability drift with no runtime consequence today: a declared helper no caller reaches; a stated rule the code contradicts; a constant duplicated where no divergence exists yet.

## Report Output

- Findings path: `.ai/audit/05-ad-lifecycle/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `AD-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
