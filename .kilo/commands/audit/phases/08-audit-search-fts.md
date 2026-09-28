---
name: 08-search-fts
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 08 — Search & Full-Text Search

## Purpose

Audits the unauthenticated search path: what decides whether a row matches, what feeds and refreshes the indexed document, what it holds per language,
how input reaches the query, how filters compose, how results are ordered, paged, counted and recorded.

Scope boundaries — other phases own: whether a state change propagates to a visibility reader (05 — this phase owns only whether the reader's predicate is correct); personal-data containment and egress basis (06); measurable performance consequence (13 — this phase owns plan stability, unbounded scans and missing indexes on the search path); locale correctness (14); query execution concurrency (03); the external translation call (09); authorization (15).

This file names what to examine and under which angle; the executing auditor finds the artifacts.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a
check list: observed behaviour, reproduced output, or a static proof that a stated property does not
hold. A passing check is methodology; nothing gates a finding on this phase's own checks.

### 1. Predicate agreement across every reader of the indexed data

*Treat single-source-of-truth as a claim to test, not a precondition. Inventory every consumer deciding whether a
row matches — the interactive path, each direction of scheduled matching, any selection a stored set serves — and whether
each consults a shared definition or carries its own. Two readers disagreeing about one row are two implementations.*
Evidence: the consumer inventory with the definition each consults; one row two consumers treat differently.

### 2. Account-state consequence: where each source states it

*Establish which account states change what a result set contains, then inventory every source stating the
consequence — the specification, an owner decision, a recorded decision, the implemented filters. Where sources
disagree, report whether a correct implementation could pass against one and fail against another; pick no winner.*
Evidence: per state, the sources stating its effect on results; each disagreement, and whether an implementation could satisfy one while violating another.

### 3. Index maintenance: what feeds the document and what refreshes it

*Establish what enters the indexed document per language and what recomputes it: a row-level maintenance
mechanism, a recompute command, a schema bootstrap step. Which write surfaces reach it — ordinary saves,
set-based and bulk updates, raw statements, imports — and does its installation run on every schema-creating path?*
Evidence: the indexed-value inventory and what feeds each; the write-surface inventory with reached/un-reached verdicts; one schema-creation path installing no maintenance.

### 4. Side effects maintained at different layers: which writes skip them

*Take every side effect one user-visible change is meant to raise — document maintenance, an invalidation
token, a counter, an event — as one family. Establish the layer each sits at, map every write surface to which
effects it raises, and read the one-sided cells: a change reached by a layer the application never observes.*
Evidence: the effect × write-surface matrix; one user-visible change raising one effect and not the other.

### 5. The indexed document across languages

*Per language, establish what text enters the document, which parsing configuration is applied, and what a
value with no translation contributes — nothing, or another language's text by fallback. Does a change to one
language's content refresh the document for the others? Ask what a buyer in one language cannot find.*
Evidence: per language, the text that enters the document and the configuration applied; one absent value and what it contributes.

### 6. Untrusted input reaching the query engine

*Trace every path from a request-supplied string to the query — the text search itself, each filter value,
ordering choices, suggestion input, anything a stored record replays on a schedule. Is the statement
parameterised or composed, does a raw-expression escape hatch exist, and is an unrepresentable value rejected?*
Evidence: the input-to-statement path inventory with a parameterised/composed verdict each; one bound that alters rather than rejects.

### 7. Abuse control on the public search surface

*Establish the request bound on this path: what it charges against, whether the identity it uses is client-supplied
and overwritable, and what a refused request returns — a body a full-page navigation can render, or one it cannot.
Does the same bound exist on the suggestion path, on a directly addressable page, and on the replaying job?*
Evidence: the bound inventory per entry point with its charged identity; one bypass; the refusal surface each entry point receives.

### 8. Filter composition and the filters that are silently dropped

*Establish the combined predicate: which parent relation a subtree expansion follows in a tree carrying more than
one, and whether a row reachable through the other is returned. How do combined and repeated filters combine?
Then the value that no longer resolves — retired, renamed, deactivated — and whether it returns nothing or everything.*
Evidence: the filter inventory with the expansion each follows; the unresolvable-value behaviour and its response; the advertised-versus-applied comparison.

### 9. Implicit query rewriting

*Establish which inputs are re-scoped without the buyer asking — a single term matched by similarity against
a label set and narrowed to that subtree, with no indication in the response. What does a wrong match cost?
Is the narrowing disclosed in the response, in the address, in any stored set? Establish the candidate set's provenance.*
Evidence: the rewrite triggers and what each rewrites to; the disclosure points present and absent; the candidate set's provenance and version source.

### 10. Cached result sets: what a stored entry can still serve

*Phase 08 owns the cached result-set itself: staleness, whether a stored entry may still serve a buyer-facing result set, and whether a content change
propagates to every stored form. Establish each of those, and whether the entry can outlive what it represents. Phase 13 owns the key's composition and lifetime:
what a cache key encodes and omits, and a freshness/version token's lifetime against the lifetime of the data it retires, and the key's behaviour under
concurrent access. Phase 14 owns whether the language component of a key is correct and where that component's value comes from. Take any stated
objective here and establish what measures it.*
Evidence: the stored-entry inventory with the changes each does not reflect; one content change against the stored forms it reaches; one entry outliving what it represents; each stated objective with its emitter, or the absence of one.

### 11. Ordering, navigation stability and count agreement

*Establish the ordering keys and whether the order is total. A partial order leaves equally ranked rows in whatever
sequence the engine returns, so two identical requests can produce two different pages; equal display names and equal
timestamps are the ordinary sources. Establish whether the buyer can reorder, and whether the reordering is applied
before or after the set is stored.*
*Establish how a page is reached — an offset into a set that may change between two requests — and what a buyer sees when
it does: a row repeated across pages, a row never reachable, an empty page while later pages are not. Is the number shown
the number navigable, and do the total, the contents and the empty state come from one evaluation or several?*
Evidence: the ordering keys with a tie verdict; two identical requests and their sequences; the total, the page and the empty state with the evaluation behind each; one count/navigable divergence.

### 12. Search-derived user data and its matching directions

*Inventory the records this path creates about the people using it: per-user history including the anonymous
case, a shared query store feeding suggestions, saved criteria. Per record, what is stored processed against
raw, which key is derived from the unprocessed value, whether it is indexed, and whether a redaction leaves it reachable.*
Evidence: the record inventory with processed versus raw storage and the derived key; what deletion reaches; the two matching directions compared.

### 13. Personal data in what the query path logs and records

*Establish what this path hands to each sink — a log line, a recorded event, a persisted query, an
exception payload — and whether any of it is personal data. For each sink, what its helper actually does:
a control that masks a value, or one that only bounds length and strips characters. Add a redaction leaving a lookup value.*
Evidence: the sink inventory with what each receives and whether it is personal data; each helper's actual behaviour; every redaction and the value it left preserved.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed list of
mechanisms, so a defect whose mechanism is not named here still lands by the consequence it is producing.

- **CRITICAL** — a row reaching a buyer-facing result set that the system's own state makes it unfit to show; a caller's input deciding what the query engine returns, or failing to, in a way the system does not constrain.
- **HIGH** — two consumers that decide whether a row matches disagreeing about it, so one question has two answers; a bound that rewrites what a buyer asked for and answers a different question; one edit raising one of its side effects and not the other, leaving two layers disagreeing indefinitely.
- **MEDIUM** — a stored result set serving a selection that has since changed; a filter value that no longer resolves and silently applies nothing; a total, a page and an empty state that disagree with one another; a supported language returning nothing for a document that holds the text.
- **LOW** — a stated objective for this path with nothing that measures it; a documented rule, label or comment contradicting the behaviour beside it; a declared mechanism no path installs or no caller reaches.

## Report Output

- Findings path: `.ai/audit/08-search-fts/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `SRH-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting current behaviour is a remediation blocker, not a gate
