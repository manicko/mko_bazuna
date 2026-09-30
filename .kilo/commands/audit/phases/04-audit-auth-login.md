---
name: 04-auth-login
status: draft
validated: yes
executor: auditor
problems-only: true
---

# Phase 04 — Authentication & Login Token Security

## Purpose

Audit the deep-link login handshake end-to-end in a dual-process system — one
process mints the credential, a bot spends it, the web opens the session:
issuance, delivery, the single-use claim, account resolution and identity
binding, the consuming side, the post-linking account-state gate,
anonymous-to-authenticated state transfer, and abuse limiting. This file names
what to examine and from which angle; the auditor finds the artifacts.

Scope boundary — other phases own: process startup and configuration/secrets
values (01, 02), cookie/origin/backend policy per environment (02), row-lock
semantics in the async process (03), PII and consent (06), test adequacy (11),
TLS (12), object-level access control and staff/admin authorization (15). With
15: this phase owns identity resolution and binding and the session-layer
consequences, 15 owning the per-request gate, and neither phase files the same
middleware decision. What the server does with a value the client asserts is
16's; the identity that value binds to, and the session-layer consequences, are
this phase's. The authority a subject-controlled account attribute carries is
this phase's and 15's; the effect such an attribute has on a derived outcome is
17's. Which surfaces a request-forgery check reaches and whether it runs on
each is 15's; which origins and cookie attributes are honoured per environment
is 02's. The claim race and the login-token guarantee are this phase's
end-to-end.

## Audit Blocks

Each block is standalone; execute any one alone with only its own evidence.

### 1. Credential issuance and delivery boundary

*Establish where the one-time credential is minted, what constrains how often,
and which surfaces its cleartext must reach — the party entitled to spend it,
and no other. Map each surface it reaches (response body, inline script,
request lines, referrers, error paths, analytics, caches) and rule each inside
or outside its confidentiality boundary before calling it a leak.*
Evidence: per-surface in/out verdict; where the outbound link is built.

### 2. Credential strength and unguessability

*Judge the credential as an unguessable bearer value, not a bit count: is it
drawn from a cryptographic source, and is enumeration infeasible judged
against the delivery channel and its acceptance window? Judge its transport
representation separately — safe-to-carry is not the same property as
unpredictable.*
Evidence: generator, randomness budget, lifetime, enumeration cost, transport.

### 3. Claim guards — atomicity, single use, and lifetime

*Establish, for claiming and consuming alike, whether guards are evaluated in
the same indivisible operation as the state change, whether concurrent
claimants resolve to exactly one winner under real concurrency, and whether
every guard that must hold at the irreversible write holds. Include when it
expires, who reclaims retired records, and any guard defined but never
reached.*
Evidence: concurrent-claim and consume outcomes; guard list; cadence.

### 4. Account resolution and identity binding

*Establish whether the identity recorded when the credential is claimed and
the session's identity are one, resolved through the same key. Confirm or
refute that both processes resolve one account when a row's identity fields
disagree or is erased, whether claiming creates an account, and whether the
namespace real identities resolve into can be occupied by an
operator-provisioned privileged placeholder — so a seller's handshake binds a
privileged row.*
Evidence: resolution key per process, one divergence, placeholder collision.

### 5. Handshake completion on the consuming side

*Establish what consuming does once it is spent: whether every guard that can
refuse precedes the irreversible write, whether the visible failure is uniform
across its causes, whether a "not yet" response is distinguishable from a "no
such credential" response, and whether the credential is bound to the client
that obtained it. Record what a refused attempt leaves behind.*
Evidence: cause × response matrix; write-vs-guard order; requester binding.

### 6. Post-linking gate and eligibility agreement

*Establish, per process, what gates an identity after a link, and whether the
handshake can leave a session or a linked identity in a state that process's
eligibility predicate never admitted. Compare the two processes' eligibility
predicates over the same subject — by the flags consulted and the identity
resolved, not by name — and reproduce any state one refuses and the other
admits. The per-request gate itself — unknown event shape, absent payload,
unresolvable identity, absent record, a raising check — is 15's decision, not
filed here.*
Evidence: per-process predicate + flag set; one session or linked-identity
state one predicate refuses and the other admits.

### 7. Anonymous-to-authenticated state transfer

*Establish what pre-authentication state crosses into the authenticated
identity — a short-lived per-identity cache of a pre-login choice,
cookie-borne values, conversational state — how each is keyed, and its trust
level. Verify the cache cannot outlive its identity or leak across identities,
and that copy and invalidation cannot diverge. Also examine the abandoned
states: claim without a session, and the bot restarting mid-handshake.*
Evidence: transfer inventory, key and trust, copy-vs-invalidation, residue.

### 8. Abuse limiting on the login surfaces

*For every surface the handshake touches, establish which layers limit it —
application layer and edge proxy alike — what identifies the caller, and
whether it is observed or merely asserted by the caller: a proxy that appends
to a forwarded-address list lets a caller pick its own bucket. Also what a
limiter does when its store is unavailable or its key expires, and name the
unthrottled surfaces.*
Evidence: per-surface per-layer inventory, caller-identity source, bypasses.

## Severity Taxonomy

| Severity | Conditions |
|---|---|
| CRITICAL | A session established for an identity other than the one the handshake authenticated; a cleartext credential reaching a surface outside its delivery boundary; a credential still both retrievable and re-usable after a guard should have refused it |
| HIGH | An irreversible write or a spent credential preceding a guard that can refuse; one login gate admitting an account state the other process refuses; a claim binding an identity it never verified |
| MEDIUM | A "not yet" response distinguishable from a rejection; a bearer credential with no binding to the client that obtained it; a caller-identity source for limiting that is asserted rather than observed; pre-authentication state that can outlive or cross its identity boundary |
| LOW | Refusals, repeated attempts, and abandoned handshakes that leave no operator-visible trace; residue no reclamation path reaches; missing or unhelpful diagnostic text on a refusal path |

Severity is anchored to **present state**: rate what is true now, not the
worst consequence a defect would have if it were triggered.

## Report Output

- Write findings to: `.ai/audit/04-auth-login/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` (front matter, summary,
findings, distribution, cross-finding, roadmap, rollout safety, appendices)
- **Incremental append**, ≤100 lines per pass.
- Prefix every finding ID with `AUT-`.
- Record findings only and omit passing checks; every finding must carry
reproducible runtime evidence and the exact consequence. If nothing is wrong
in this phase, write exactly: `No problems found in this phase.`
