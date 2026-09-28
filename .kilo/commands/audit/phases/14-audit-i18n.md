---
name: 14-i18n
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 14 — Internationalization & Localization Correctness

## Purpose

Audits the two chains that decide what language a person reads in, and everything downstream of them: where a request's language comes from and how far it is validated, which consumer decides what a person is
seeing, where a locale is activated and restored, how localized data is stored and falls back, what format localization renders, what each cache tier keys on, what a translation pipeline leaves behind, whether the
catalogs are whole, what the automated controls actually examine, and what the declared language set can express.

Scope boundaries — other phases own: settings values, secrets and the environment-variant decision, including cookie attribute policy (02); identity binding and the account-state gate, this phase owning only the
locale the account record carries (04); the cross-backend behavioural difference between the two processes (03); fixed-value and enum discipline (10); the basis on which content may leave the system, and the translation client's transport,
retry and egress (06, 09); pipeline job gating and container locale availability (12); test-suite adequacy (11).

Cache-key ownership is split three ways. Phase 13 owns the key's composition and lifetime: what a cache key encodes and omits, and a freshness/version token's lifetime against the lifetime of the data
it retires, and the key's behaviour under concurrent access. Phase 08 owns the cached result-set itself: staleness, whether a stored entry may still serve a buyer-facing result set, and whether a content
change propagates to every stored form. Phase 14 owns whether the language component of a key is correct and where that component's value comes from.

This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others, and each carries its own evidence. Evidence is a class, not a check list: observed behaviour, a static proof that a stated property does
not hold, or a reproduced divergence between two paths. A passing check is methodology, never a finding, and any sound evidence is admissible — nothing here gates a finding on this phase's own list.

### 1. Where a request's language comes from, and what each source is normalized against

*Take every input that can select the language for a request — an explicit request parameter, a stored preference carried by the client, a client-declared language header, a configured default, and any further tier
the code maintains. Per source, establish whether the value is canonicalised and checked against the configured set before it takes effect, or passed through, and what an unrecognized value does to every consumer
downstream. A tier written and never read is a finding in its own right: the code believes it has a source it does not have.*
Evidence: the input inventory with a normalized / passed-through verdict each; one unrecognized value and what each consumer renders with it.

### 2. Every consumer that decides what language a person is seeing

*Inventory every place that answers what language this person wants — the request path, each interactive command, each notification path. Per consumer: which key identifies the person, which tier it falls back to,
how long that tier lives, and whether the key is the platform identity, the account's own identifier, or a value carried out of conversational state. Establish whether they agree on the key and on what a person is,
and reproduce any two that disagree — across a restart, or across an anonymous-to-registered transition.*
Evidence: the consumer inventory with key, fallback tier and lifetime each; one person two consumers resolve differently, and the transition that produces it.

### 3. Locale activation scope and restoration

*Establish where the language is activated, how wide that scope is, and what puts it back. Include every path that renders text for a person outside the request or update pipeline, and any work handed to another
thread, pool or worker, which would render under whatever locale that worker happens to carry. Establish whether an activation is scoped to one unit of work or leaks past it, whether an error path restores it, and
what a leaked locale would look like to the next caller.*
Evidence: the activation sites with their scope and their restoration; the render paths that run outside the pipeline; one path that renders without a locale of its own.

### 4. Localized data: the storage shape and the whole fallback chain

*For each entity that stores a value per language, establish the storage shape — a keyed map, one column per language, a constructed attribute name — and the entire chain, layer by layer, not only the first two
layers. At each layer ask whether the fallback exists at all or the code merely assumes one is there; a last layer naming a field the entity does not carry is a wrong assumption, not a defect. Then take a value that
is not one of the configured languages: what does it produce on each chain, and can a client supply one?*
Evidence: per entity the storage shape, the full chain, and a per-layer verdict on whether the fallback exists; one non-configured value and what each chain renders.

### 5. Format localization: numbers, currency, dates, times, plural counts

*Treat every formatted value a reader sees as locale-dependent output that no message catalog governs. Establish what produces it; whether the type handed to a formatting helper is the type it actually localises, or
a pre-rendered string that bypasses it; whether the pattern comes from the configured locale or is written into the template; and whether the time base the site computes in is the one it operates in. Include a value
correct in one language and wrong in another, and a value interpolated raw into an otherwise translated sentence.*
Evidence: the formatted-output inventory with producer, input type and locale source each; one value correct under one language and wrong under another; one raw value inside a translated string.

### 6. Cache tiers: what is cached, and whether the language is part of its identity

*For each cache tier, establish what the payload is — rendered output, a domain object, a number, a language value — and therefore whether the key must carry the language. Read the one-sided cells in both
directions: a key that omits a component its payload depends on, and a key that carries one it does not. Establish where each key component comes from and whether it is validated before it becomes part of the key; a
component taken straight from a client-supplied value makes the key space unbounded and the entry unreachable by a legitimate client.*
Evidence: the tier inventory with payload, key components and their provenance each; one key missing a component its payload depends on; one key carrying a component it does not, and the value that feeds it.

### 7. The translation pipeline's stored result

*Establish what text exists in each language for a piece of content and what produces the non-source translations. Then establish what is written when that production degrades — whether the original, a partial
result, or nothing — and what a reader in the affected language subsequently sees, given that chain's fallbacks. Establish whether the degradation is detectable afterwards, by an operator or by any reader. Establish
also which tier records a person's own language choice and which identity that writer reads, since a choice persisted to a tier the request path does not read is a stored result no reader of the chain will find. The
client's transport, retry and egress belong to another phase.*
Evidence: the storage shape and its chain; the degraded result that is persisted, and what each language's reader sees; whether anything distinguishes a degraded entry from a translated one; the writer of a stored language choice and the identity it reads.

### 8. Catalogue integrity in both directions, and which locale is exempt

*Establish the extraction → catalog → compiled-catalog chain and where it can break in each direction: a string the source uses that no catalog carries, a catalog entry no source produces, a compiled artifact
missing or older than its source. Establish which language is the source and that the completeness assertion is correctly waived for it and only for it. Compiled catalogs are build outputs rather than tracked
sources, so a missing or skipped compile step cannot be seen from the source tree alone.*
Evidence: the chain with a break identified in each direction; the exempt locale and the scope of its exemption; the step that produces the compiled artifact and the paths it runs on.

### 9. The localization controls: what each one actually enumerates

*Take every automated control over localization — a shipped test, a collector behind it, a pipeline job — and separate three questions per control: does it exist, what scope does it declare, what did it actually
examine. Establish what a green result does and does not license. A control whose declared and actual scope differ is a finding however green it is: ask whether the scope it declares matches what it
actually examines, whether the items it enumerates are the ones its framework resolves, and whether its assertion exercises the page that includes the artifact. Then take each declared exemption one at a time — including the
surface exempt because its text comes from the database — and establish what covers it instead, and whether the list is as narrow as the documentation claims.*
Evidence: per control — existence, declared scope, the file, item and series count it actually examined; each exemption with the mechanism that covers it, or the absence of one.

### 10. Script representability: what the declared language set can express

*Establish end to end whether a reader whose language requires a different script can be served that script: in the declared language configuration, in the message catalogs, in the per-language stored content, and
in the per-language columns. A configuration that names languages without naming scripts cannot express a script-tagged request, and per-language columns have no script dimension at all — establish where that stops
and what the reader receives. Establish what the direction attribute is derived from, and whether that derivation can be wrong for content the system itself stores.*
Evidence: the declared language set against the scripts in use; one script-tagged request and where it is reduced; the direction attribute's source and one stored value it cannot describe.

### 11. The language preference's round trip: what is written, when, and what the response declares

*Establish who persists a chosen language, under what condition, and whether the client-side and server-side writers agree on that condition — one ungated and one gated is a contract stated twice and implemented
once. Establish what the response declares about which inputs vary its body, whether that declaration covers every source that can change the language, and whether it still holds for a partial response that renders
none of the tokens a full page renders. Where a stated contract does not hold, report the contract and the behaviour, not only the gap between them.*
Evidence: the writers with their conditions and the attribute each emits; the response declaration against the sources that can change the body; a partial response and whether the declaration survives it.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed list of mechanisms, so a defect whose
mechanism is not named here still lands by the consequence it is producing.

- **CRITICAL** — a reader acts on a value that is wrong for their language and cannot tell: a monetary, temporal or numeric quantity rendered so the reader would read a
different quantity from the one stored, on a surface the reader is expected to act on. An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.
- **HIGH** — a reader is shown content in a language they did not select, or two consumers of one stored value disagree about which value applies, so a whole surface is wrong
before anyone notices; a quantity, a time base or a date pattern whose rendering is wrong for every reader regardless of the language selected; an automated control that reports clean over a surface it never
examined, on a path where an unexamined change would ship.
- **MEDIUM** — degraded correctness with a workaround: a fallback that lands on a value from another language or another identity than intended, where the reader can still
act; a formatting defect confined to one surface; a control that examines a subset of the surface it declares.
- **LOW** — documentation and hygiene drift with no reader-visible consequence today: a comment, docstring, specification line or exemption list describing a contract the code
beside it does not implement; a declared exemption wider than the surface it was granted for.

## Report Output

- Findings path: `.ai/audit/14-i18n/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `I18N-` — **already in use** in the specification and project-rules documents from a prior cycle, with several identifiers already resolving to two
different findings; report the collision rather than minting a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
