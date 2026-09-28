---
name: 09-external-api
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 09 — External Integrations & API

## Purpose

Audits every boundary between this system and the outside: what an outbound call to a third party puts on the wire, what bounds it, what happens when the far side
misbehaves, and what the system still believes afterwards; and what the public surface accepts, refuses and reveals. A dependency that is unavailable must degrade
one feature, not the whole site. This file names what to examine; the executing auditor finds the artifacts.

Scope Boundaries — other phases own: ORM-dispatch, transaction, lock and pooler semantics (03); settings values, secrets, environment and cookie policy (02); the basis on which personal data may leave the system (06); the media-specific admission, keying, serving and ownership questions, this phase owning only the outbound transport, retry, timeout and failure-isolation mechanics of a download client reached from an integration path (07); search recall (08); enum and boundary-model discipline (10); the edge proxy, transport security and probes (12); measurable latency (13); authorization decisions, and which surfaces a request-forgery check reaches and whether it runs on each (15).

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed behaviour, a static proof that a stated
property does not hold, or a reproduced divergence between two paths; the method is the auditor's. A passing check is methodology, never a finding, and any sound evidence
is admissible — nothing gates a finding on this phase's own checks.

### 1. The credential seam: where a secret enters a request, and what absent, empty or malformed does

*Derive the outbound call set, then per call establish where the credential enters — path, query, header or body — treating absent, empty and malformed as three distinct
states. Establish which processes hold the credential and what each does with it: one handed to a process that never needed it is a widened blast radius, not a leak. Confirm the
wire form cannot reach a log, an exception string or a referrer. Values are another phase's. Without a reachable far side, establish the property from a constructed request,
and record the residual unverified.*
Evidence: per call — where the credential enters, the three states, the holding processes; one path by which the wire form could be observed.

### 2. How a caller-supplied payload is encoded for the receiving parser

*Establish what an outbound body is made to look like to the far side: which markup or template dialect it declares, whether caller-supplied field content is escaped for that dialect, and what a value
carrying the dialect's own control characters does to the send. Include the size and character set a body may carry, and whether a field the far side rejects is retried, reported or silently dropped —
a send that fails on a character the caller typed is a correctness failure even though nothing errored.*
Evidence: per outbound call — the declared dialect, the escaping applied or absent, one caller-supplied value and what the receiving side did with it.

### 3. Retry contract: what is replayed, what bounds the total, and whether a replay is safe

*Establish per call whether the bound is on each attempt or on the whole operation — a wait the far side mandates is a bound the local code inherits, not one it sets. Establish which failure classes
are replay-eligible, since a guard matching one exception class silently drops its siblings, and whether the replayed operation is safe to repeat when the response was lost after the write. Then
establish what the caller is told when the bound is exhausted: a failure reported as handled is a silent loss.*
Evidence: per call — the per-attempt bound, the total bound, the replay-eligible failure classes, the caller-visible outcome at exhaustion.

### 4. The aggregate request budget one third party sees across processes

*Establish every bound on outbound volume — per process, per key, per window — and multiply it by the deployed topology: how many processes hold the credential, how many replicas each runs, and
whether any limiter is per-process or per-key rather than shared. A limit correct inside one process is an unbounded budget in the deployed system. Include the amplification a far side imposes in
turn, where a backoff that honours a wait the far side names turns an inbound signal into an outbound one. Counts not derivable from the repository come from the shipped configuration, and the
residual is recorded as unverified.*
Evidence: the bound inventory with the scope of each bound; the process and replica counts; one arithmetic path from an inbound signal to the aggregate outbound count.

### 5. The blocking-work bridge, in both directions

*Establish how synchronous persistence is reached from an event-driven process: what wraps the call, on which thread it runs, and whether the connection that thread owned is released on the exception
path as well as the normal one. Then the reverse direction the forward framing hides — blocking network work pushed out of a request thread onto a pool whose result nobody retrieves, with an unbounded
queue and workers joined at interpreter exit. Is a shutdown grace period shorter than the work still running, and what is lost? Serialisation granularity, pooler sizing and latency are 03's and 13's.*
Evidence: the forward wrapper and its release path; for the reverse direction, one unretrieved result and the shutdown ordering against the grace period.

### 6. Degradation: what each dependency's failure takes down, and how a guard fails

*Derive the dependency set yourself rather than inheriting it from documentation, and include shared state — a cache, a store, a queue, a filesystem the request path reads — not only named third
parties. Per dependency establish what its unavailability takes down, whether the blast radius is one feature or every page, and whether a guard built to bound abuse fails open, fails closed, or
raises: a guard that raises where it was meant to bound turns a dependency outage into a total one. Then ask whether one failure reaches the same outcome through more than one layer, with the same
root cause in each.*
Evidence: the derived dependency list with a per-dependency blast radius; one outage probe and what survived it.

### 7. A degraded result the consumer cannot tell from a real one

*Establish, for every fallback and every default, whether what it returns can be told apart from a real result by whatever stores it — the value that arrives, the row that is written, the query that
later reads it. A fallback that returns a value where the caller needed a status writes a plausible answer into a field thereafter read as authoritative, permanently, and nothing alerts because the
operation succeeded. Include the case where a breaker, a limiter or a circuit is open and nothing counts or logs it.*
Evidence: per fallback — the substituted value, its consumer, and one stored state a reader cannot distinguish from success.

### 8. Isolation of failure inside a fan-out, and the record's order against the effect

*Establish what happens when one item of a fan-out fails: does the batch abort, continue, or run the remainder, and can the caller tell which items were reached. Establish the order of a durable
record against the effect it describes — a row written before the send is a record of an intention and is read afterwards as a record of an outcome — and what a retry of the batch re-does. Establish
what a partially applied batch leaves behind for a later run to meet.*
Evidence: one failed item and the fate of the rest; the write/send ordering on the same path; the residue a re-run meets.

### 9. Inbound surface form: method guards, body bounds, and what a refusal discloses

*Derive the inbound surface — the machine-readable reads, the state-changing writes, the anonymous sinks, the monitoring endpoints, the probes — and per endpoint establish its method guard, whether
that guard is declared once or re-implemented per view, and the bound on a submitted body. The surface is mixed by design: some paths answer anonymous callers with success, so establish per refusal
class what is disclosed and whether the disclosure level differs between the machine-readable and the human-facing surface for the same underlying decision. Establish whether a version is negotiated
or only written into a path, and what a consumer meets when a response field changes without one. Which refusal class an endpoint should return, and how the edge implements the bound, are other
phases'.*
Evidence: the derived endpoint list with per-endpoint guard and body bound; a refusal-class × surface matrix of what each discloses; the consumer list and the change each would break.

### 10. Which inbound boundaries validate, and which documented exceptions are load-bearing

*Establish the validation convention at the request boundary: the strict-by-default base every client-input model is supposed to inherit, and how many boundaries actually inherit it. For each boundary
that does not, establish whether the exception is documented, whether it is load-bearing — the far side sends fields the model would otherwise reject, or the shape is an output rather than an input —
or accidental, and whether the boundary rejects, ignores or coerces what it does not recognise. A documented exception is a decision; an undocumented one is drift. Of which
boundaries validate, 10 owns the production-code boundary surface and this block owns the inbound integration boundary.*
Evidence: the boundary × model inventory with an inherits / does-not-inherit verdict; each exception's documented reason and its field-handling verdict.

### 11. Declared dependency and declared mechanism against the code

*Establish every statement the repository makes about its outside world — a capability it claims to have, a credential or role attribute a gate is documented to check, a source whose data it says it
fetches, a runbook instruction — and check each against the code. Treat a comment, a docstring and a specification line as claims to be tested rather than as the invariant: for every gate, which
predicate does the executing path actually evaluate, and does the documentation above it match? A comment that contradicts the code it documents is itself a finding.*
Evidence: the statement inventory with a true/false verdict each; one documented mechanism the code contradicts; one capability claimed and absent.

### 12. What the integration surface writes into logs, and whether failure state is measurable

*Establish both directions: what an outbound client writes about the text and values it sent, through which sanitiser and whether that sanitiser masks; and what an anonymous sink writes about a body
it accepted from anyone, including fields that carry a location or an identity. Then establish whether a dependency's failure state is measurable at all — an open breaker, an exhausted bound, a
dropped send, a permanently failed substitution — or whether it exists only as an unlogged exception. Where no counter exists, a quiet dependency is indistinguishable from a working one.*
Evidence: per direction, the fields logged and the sanitiser's masking verdict; the list of failure states with a counter, a log, or neither.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — a live capability reachable without any gate, or a credential made usable by a path the system does not control, where the exposure cannot be
  withdrawn without rotating it. An empty band is a valid outcome here: do not populate it with a hypothetical, and do not pull an item up because it sounds alarming.
- **HIGH** — a silent correctness failure with no self-healing path: an operation reports success while the far side never received it, or a substituted result is
  stored where a real one was required and nothing can tell them apart; a bound correct per process and unbounded once the topology multiplies it; one dependency's
  failure taking down a whole surface rather than a feature; a refusal disclosing more on one surface than the other discloses for the same decision.
- **MEDIUM** — a bounded resource or operability gap: a replay bounded per attempt but not across the operation; a per-item failure that stops or skips the remainder
  of a fan-out without recording which; a guard applied on one path and absent from a sibling reaching the same dependency; a failure state with a log but no counter.
- **LOW** — documentation and observability drift with no runtime consequence today: a declared dependency, capability or control the code does not implement; a
  comment or docstring naming a predicate the executing path does not evaluate; a log line reporting an attempt as a confirmation; a boundary accepting a rejected field.

## Report Output

- Findings path: `.ai/audit/09-external-api/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `EXT-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- Finding IDs use the declared bare prefix; a shipped test, configuration comment or runbook may already carry an ID from a prior cycle, so check for a collision before minting a new one
- A shipped test asserting current behaviour is a remediation blocker, not a gate
