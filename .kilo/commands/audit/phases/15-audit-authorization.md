---
name: 15-authorization
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 15 — Authorization & Access Control

## Purpose

Audit what an access decision returns: which surfaces an identity may reach, what each refuses, and where the two processes agree or do not. The access level, the owner
comparison, the gate standing before an action, the disclosure a refusal carries, and the request-forgery check covering a surface are all decisions. This file names what to
examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — other phases own: cookie, origin and backend policy per environment, this phase owning only what an access
decision *returns* and not the attributes of the transport carrying it (02); identity resolution and binding, and the session-layer consequences, this
phase owning the per-request gate, and neither phase filing the same middleware decision (04); lifecycle correctness and moderation-gate
correctness (05); the consent consequence of an access decision (06); media ownership, this phase owning only whether an account-owned object
can be reached by another (07); the inbound surface form (09); fixed-value discipline (10); the privileged surface's pipeline posture (12).
A client-settable value the server reads to choose what it renders is 16's; which surfaces a request-forgery check reaches, and what an access
decision returns, are this phase's. A derived definition with no production caller is 10's; the exported predicate this phase
already grades is its own, and the authority an account state carries on a surface is 15's where 17 owns only the effect on the derived value.
A mechanism another phase owns is recorded as a deferral with its owner named, and the block still covers the decision this phase makes.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others, and each carries its own evidence. Enumerate the surfaces, then ask whether each is gated; a gate that
holds is methodology, never a finding, and any sound evidence is admissible, with nothing here conditioning a finding on this phase's own list. Where a property cannot be settled
in the environment at hand, establish it from what is observable and say plainly what could not be verified. A proposed change that would make two decisions agree is judged
against whatever one of them deliberately refuses.

### 1. The access-level representation, and where it is actually decided

*Establish whether an access level is stored, granted or derived: which attributes decide it, which surfaces consult the representation, and which read those attributes
directly instead. Where two surfaces reach the same verdict, establish whether a construction forces the agreement or it only follows from the same attributes being read
twice. That one decision point exists, and that two are independent, are both questions.*
Evidence: the site the level is decided at; the attribute set each elevated surface reads, compared.

### 2. What the representation can and cannot distinguish

*Establish the granularity actually available: whether anything finer than authenticated-or-not can be expressed, whether the framework's own permission
machinery connects to that representation or bypasses it, and whether an assignment layer exists that the representation ignores. A control that returns a
constant where a decision is expected is a finding; a gate correct at the granularity it has is not, and neither is a class that overrides no permission at all.*
Evidence: the distinctions available; administrative classes overriding no permission method; overrides returning a constant; surfaces read-only by a stated policy.

### 3. The privileged surfaces, and the predicate each one evaluates

*Enumerate every surface reachable only by an elevated identity, in either process: the framework's own administrative interface, the per-model overrides inside
it, a privileged path that hands off to a second gate, and any surface listed as privileged only in intent. Establish which of them are reachable over a request
at all — a one-shot task has no caller to authorise, and a surface every identity may reach is not privileged merely by being listed. Record where each decision sits.*
Evidence: surface inventory with the predicate each evaluates, against what admits a caller; a decision reached after the first irreversible step it guards; two gates on one request path.

### 4. Ownership on every single-object path

*Enumerate the object types an identity owns — including the collections, saved items and history rows a user accrues without ever being told it owns them — then
every path that reads or mutates one of them by identifier, and judge each for an owner comparison. Record what the response discloses before the decision is
made. Do not presuppose the enumeration is complete: a path that resolves an object without consulting its caller is a path, not an exception to the rule.*
Evidence: owned-type inventory; path × owner-comparison matrix; the paths carrying no owner comparison.

### 5. Ownership on collection and multi-object paths

*Establish the surfaces where one call names many objects — bulk actions, batch endpoints, list and count surfaces — and whether the restriction is applied per object
or once per call, and whether each named item is re-resolved under it. For a list, establish whether the restriction is part of the query or applied row by row, and
whether a row that has since left the public surface is still returned to the identity that owns or collected it. A per-object judgement cannot express any of these.*
Evidence: multi-object surfaces with a per-object or per-call verdict; the scoping of each list query; a list still returning a row that is no longer public.

### 6. The seam that receives an identity it does not read

*For every service, helper or job that creates, updates or deletes a row, establish whether the caller supplies an acting identity alongside the target identifier and
whether the callee consults it — a creation path handed an owner value it never reads, a deletion path resolving its target by a bare identifier with no owner
constraint. Such a callee trusts its caller by construction. Where a decision precedes a write, establish whether both are evaluated in the same indivisible operation.*
Evidence: mutation entry points with the identity parameter they accept and whether it is read; the entry points carrying none; a decision separated from its write, and the in-module precedent.

### 7. Which account state is consulted, on which surface, in which process

*Establish which account states are consulted, on which surfaces, in which process, and whether a read surface consults the states a mutating one does. Then at the
event-driven process's pre-action gate: how events enter, and whether a sender is authenticated where they arrive over a network; and whether the acting party
can differ from the one whose payload carries the action; and what it permits on an unrecognised shape, an absent payload, an unresolvable identity, an absent record, or a raising check.*
Evidence: state × surface × process coverage matrix; decision-before-action ordering; the identity source per event type; a per-edge permit-or-refuse verdict.

### 8. Whether the two processes reach the same verdict

*The two processes do not offer the same operations, so compare them by decision and not by name: for one subject and one object, what each refuses, which
states each consults, and whether any state one refuses is admitted by the other. A predicate that is specified or exported but that neither process calls is part
of the answer, as is one re-derived inline where a shared one exists. Where a surface exists in one process and has no counterpart, say so rather than inferring symmetry. The post-linking
handshake's session-layer consequences are 04's; the comparison here is the per-request gate and every ownership and account-state surface.*
Evidence: state × process refusal table; the states one process consults and the other ignores; exported predicates with no production caller; one state admitted by one process and refused by the other.

### 9. The public/owner boundary in both directions

*Establish what an unauthenticated caller can reach, and separately what an owner-scoped surface renders for that owner: whether an object that has left the public
surface is still shown to the identity that owns or collected it, and whether derived or annotated data on a public object carries owner-private fields. Establish the unit
a media object is authorised against — its own parent, or a storage reference several records share. Media ownership is another phase's; only reach across accounts is this one.*
Evidence: public-reachability inventory; owner-scoped surfaces rendering non-public objects; the unit each media authorisation is evaluated against.

### 10. What each refusal discloses, and where the shapes disagree

*For each refusal class — unauthenticated, authenticated-but-not-permitted, not-found, not-yet — establish what the response discloses on each surface, and whether one
underlying decision is answered at a different disclosure level on a machine-readable surface than on a human-facing one. A deliberately reduced disclosure is a
decision to read, not a defect. The finding is one decision answered inconsistently across two surfaces, with no stated reason, or a refusal describing an unimplemented scheme.*
Evidence: refusal class × surface matrix; the pairs where the same decision is disclosed differently; the stated reason for each divergence, or its absence.

### 11. Cross-site request forgery: what covers which surface

*Establish which surfaces the cross-site request check covers, which are exempt, and whether each exemption is documented and load-bearing. Establish whether a surface
that mutates on a method the check does not cover is a deliberate choice or an omission, and whether the trust anchor deciding which origins are honoured is in
effect in each environment actually deployed. Which origins and which cookie attributes are honoured, per environment, is the policy half and belongs to 02; which surfaces a
request-forgery check reaches, and whether it runs on each, is the enforcement half and is this phase's.*
Evidence: the check inventory with its exempt set; surfaces that mutate on an uncovered method; the trust-anchor state per deployed environment.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name.

- **CRITICAL** — an identity reaches an object or a surface that is not its own, in the state the system is in now: through a shared or indirect reference, through a batch
  not re-checked per item, or through a path that resolves an object without consulting its caller.
- **HIGH** — a decision reached after the first irreversible step it should have preceded; an access level resolved differently by two surfaces with no construction forcing
  the agreement; an account state one process refuses and the other admits; a control that decides nothing where a decision is required.
- **MEDIUM** — one underlying refusal answered at different disclosure levels on two surfaces with no stated reason; a correctly granular gate that reads the wrong attribute,
  refusing a legitimate subject while admitting a stronger one; a real defect whose only entry point is not currently reachable; a comment or docstring describing a
  decision the code does not make.
- **LOW** — refusals that leave no operator-visible trace, or a trace carrying no stable reason code; refusals recorded under a different convention on each surface that
  produces them; documentation drift on a gate.

Anchored to **present state**: rate what is true now, not the worst consequence a defect would have if it were triggered. An empty band is a valid outcome — do not
populate it with a hypothetical.

## Report Output

- Findings path: `.ai/audit/15-authorization/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `AUTZ-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
