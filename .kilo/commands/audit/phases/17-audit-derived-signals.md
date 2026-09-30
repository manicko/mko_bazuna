---
name: 17-derived-signals
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 17 — Derived Signals & Aggregates

## Purpose

Whether a quantity the system derives from its own recorded events, persists, and then displays or acts on is the quantity those events support: the scope of the numerator against the
denominator, the counting semantics, the window the value claims to cover, the range and rounding applied, and whether a consumer and the producer of one ledger mean the same thing by it.
This is a question about arithmetic, and an arithmetic defect is invisible to every other angle — it raises no exception, fails no write, costs no latency, and passes every check that asks
whether the code ran. This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — other phases own: recompute *coverage*, meaning every row value maintained away from the write that changes its input — whether a mutation that invalidates a derived
value re-derives it, the read-modify-write discipline on derived rows, the identifier and reference namespaces behind them, and lock and window discipline for background and one-shot
execution (03). That is the whole difference between the two phases, and it is the boundary that matters most here: coverage asks whether a value is re-derived when its input moves, while
this phase asks whether the derivation was right the first time. The moment a block turns into a statement that an input changed and nothing recomputed, it is 03's, and is recorded as a
deferral with 03 named — an arithmetically wrong aggregate has no transaction boundary to violate and cannot honestly be graded on one. Also owned elsewhere: the cost of a rollup or a
recompute — statement count, write amplification, transaction width, lock hold (13); lifecycle transitions on a domain record and the timestamps they write, this phase owning what a
derived quantity becomes when such state moves and recording the lifecycle side as 05's (05); residual personal data and the consequences of erasure, a stored aggregate outliving the subject
it describes being 06's (06); a value with two homes, two live implementations of one fixed quantity being 10's high-band finding, recorded here as a deferral with 10 named rather than
re-filed (10); whether the job that produces aggregates is dispatched at all, 01 having already scoped itself away from the aggregate the job produces (01); the authority a given account state
carries on a given surface in a given process, and the identity and session binding an attribute is read through — where such an attribute is altered by the subject, this phase owning only the
effect the alteration has on the derived outcome and that authority being (15) and (04); egress and outbound failure (09); whether a decision is exercised by a test (11). A mechanism another
phase owns is recorded as a deferral with its owner named, and the block still covers the decision this phase makes.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others, and each carries its own evidence. Evidence is a class, not a check list: an enumeration of the events that
feed a value, a constructed case with a hand-computed expected result, an observed value at two moments, or a static proof that a stated property does not hold; the method is the
auditor's. A passing check is methodology, never a finding, and any sound evidence is admissible: nothing here gates a finding on this phase's own list. A correct value is not
evidence that the derivation is correct, and a plausible intent is not evidence that the number means what a reader will take it to mean — where the intent cannot be recovered from the
code, the value, record it and say what it makes the number. A block that drifts into recompute coverage has crossed into 03 and is deferred there with the arithmetic question it
opened still answered here.

### 1. Numerator and denominator scope agreement

*For every ratio the system derives, establish whether the numerator and the denominator are scoped to the same subject, over the same population, across the same interval. A component
computed against a population its subject does not belong to is a finding however well the intent reads, and so is a ratio whose two sides are drawn from different populations that happen
to coincide today. Establish whether the result is bounded by the subject's own recorded activity or by system-wide activity, and whether it moves as the system grows — a value that
decays toward zero merely because the site is busier is a function of traffic, not of the subject. Establish whether the value reaches anything a person other than the subject reads.*
Evidence: per derived ratio — the scope of each side, the population each draws from, and whether the result is a function of the subject's own records alone; a case where the two scopes
diverge.

### 2. Counting semantics: what counts as one occurrence

*Establish which recorded events denote one real-world occurrence and which denote a stage of it, and whether a stage and its completion both land in the same aggregate — an event pair
satisfying two conditions at once contributes two to a bucket that means occurrences, and nothing downstream can tell. Where two consumers answer the same question from the same ledger,
establish whether they agree by construction or by coincidence, and treat agreement that holds only because the two cases chosen so far happen to be disjoint as a construction failure. A
consumer counting a strict subset of what another counts, or a superset, is a finding wherever both answers are shown or acted on.*
Evidence: per aggregate — the event classes summed into it and which of them denote the same real-world occurrence; the two consumers of one ledger with the case their answers diverge
on; the counted rows behind a single displayed value.

### 3. The window a value claims to cover

*Establish where each aggregate's interval boundary is computed and where it is applied, whether the two are resolved in the same timezone, and how a boundary day is attributed — a window
whose bound is defined in one zone and filtered in another is not a rounding question. Establish whether an occurrence arriving after its window closed is attributed anywhere at all, or
dropped, and whether anything repairs it. State the window the value is documented to cover next to the window the code computes, and where they differ, that difference is the finding.
Whether the re-derivation is itself safe — locked, idempotent, restartable — is another phase's question; this block is about what the window means, not about how the run is guarded.*
Evidence: per aggregate — where the boundary is computed, where it is applied, the zone each resolves in; an occurrence landing on the boundary; an occurrence arriving after its window
closed and where it ends up.

### 4. Range, clamping, and two definitions of one quantity

*Establish whether a derived value is bounded by its declared range and where the bound is applied — before or after the computation, once or on every path. Establish how rounding is applied
and whether a rounded value can cross a threshold its unrounded form does not, so that the band a reader sees is one the computed value does not support. Where two implementations of one
quantity are both live, establish whether they agree and on what input they part — the agreement is the arithmetic, and it is this phase's; that one quantity has two live implementations at
all, and an implementation no caller reaches, is the fixed-value discipline another phase grades, so establish the divergence here and record the duplication itself as a deferral with that phase
named rather than filing it twice. Establish where a threshold mapping can return a band the value never qualified for, and whether the qualifying condition is the one actually tested.*
Evidence: per derived value — the bound and where it is applied; a value whose rounding moves it across a threshold; two definitions of one quantity with the input on which they diverge, the
duplication itself deferred.

### 5. Provenance, and what a stored value means to its consumer

*Establish whether an aggregate's records are drawn from the population it claims to describe, and whether an origin excluded from production is still admitted into a count — an event type
persisted for a purpose other than production contributing to a production figure is a provenance defect whatever the intent. Where an association carries a target whose type varies by
row, establish whether the surfaces reading it agree on what the reference denotes, since the row cannot say so. Establish whether a stored value carries the scope of the computation
that produced it — subject, population, window, and the moment it was true — or whether a later reader must reconstruct all four from the schema and the code, and record the
reconstruction burden where the value is displayed as a fact.*
Evidence: per aggregate — the event origins admitted and the ones the production population excludes; a value displayed with no recorded scope; the surfaces reading one varying-target
association and what each takes the reference to denote.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name.

- **CRITICAL** — a value is shown to a person other than the subject it describes — a public trust, rating or standing signal — and the recorded events do not support it; or a persisted
  aggregate is false at the scale and the population it is displayed over.
- **HIGH** — two consumers of one ledger returning different answers to the same question with no construction forcing agreement; a component whose denominator lies outside its
  subject's population; a band returned for a computed value the band does not qualify for.
- **MEDIUM** — a window resolved in a different timezone than it was defined in; a boundary occurrence attributed to no window with no repair path; a subject-controlled account
  attribute altering a computed outcome regardless of the computed value; rounding that shifts a value across a threshold.
- **LOW** — a cache lifetime that can serve a stale value with no version token, where the staleness is bounded and named; a stored value whose scope a reader must reconstruct
  where the reconstruction is currently unambiguous.

Anchored to **present state**: rate what is true now, not the worst consequence a defect would have if it were triggered. An empty band is a valid outcome — do not populate it with a
hypothetical.

## Report Output

- Findings path: `.ai/audit/17-derived-signals/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `DRV-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
