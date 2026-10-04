---
id: pii-consent-remediation-record
domain: agent
tags:
  - pii
  - consent
  - gdpr
  - remediation
  - record
  - open-questions
related:
  - architecture
  - rules
  - db-schema
  - db-retention
  - technical-specification
---

## Purpose

Decision record for the **PII / consent remediation pass (phase 06)**: the owner-ratified
decisions that pass made, the option each one rejected, and the boundaries it deliberately left
untouched. It is the single source of truth for *"we know about X and we deliberately deferred
it"* on this pass. The durable behaviour itself lives in the linked specification, database and
operations docs, not here; those are linked from
[Where the shipped behaviour is documented](#where-the-shipped-behaviour-is-documented).

Conventions: a decision is **Ratified** (the owner has answered and the answer is implemented) or
**Open** (nobody has answered and nothing has shipped against it). An Open decision is not
approved, not partially approved and not scheduled for a named phase. Finding ids are
**cycle-scoped** — they belong to the phase-06 audit cycle and are reused by no other phase.

## Owner-ratified decisions

Three questions in this pass were the owner's to answer, not an agent's. All three were
recommended with the consequences enumerated and then ratified on **2026-10-03**. The gate ids
(`Q-D*`) are the plan's, and are the stable handle; a `Q-D` id may appear in only one row.
**One row was later re-grounded by a later owner ruling:** `Q-D4`'s consent-record retention
anchor was withdrawn and replaced on **2026-10-04**, and the actor-retention rule was added after
this table was written. Both are recorded in
[Retention framing correction](#retention-framing-correction-owner-ruling-2026-10-04), which
governs where the two disagree.

| Gate | Question | Decision (ratified 2026-10-03) | Rejected alternative | Implementation |
|---|---|---|---|---|
| **Q-D1** | Is a consent **DECLINE** reversible? | **(a) Reversible.** `is_declined` is dropped from `can_login()`; publishing and listing/search visibility stay restricted while the decline stands. See [DECLINE-1](#decline-1-q-d1--a-decline-is-reversible) | **(b) Intentionally one-way** — leave `can_login()` alone and correct `privacy.html` §7 to say the choice is final for seller features. Rejected because it keeps a silent, effectively irreversible takedown of a live seller's listings as the side effect of clicking a cookie banner, and leaves recoverability an open design item instead of a courtesy | `8dba351` |
| **Q-D4** | `ConsentRecord` retention: what bound, and which advisory-lock id? | **R2 — fingerprint fields (`session_key`, `user_agent`, `ip_address`, plus the `user` link): 90 days. Fresh lock id 14.** **R1 — event fields (`choice`, `categories`, `consent_version`, `consent_given_at`): retain while there is a necessity to prove consent/withdrawal and the lawfulness of the corresponding processing; after a justified period expires, delete or anonymise; anonymise, never delete.** The actor rule (`initiated_by`) was added later and is **not** part of this row — see [Retention framing correction](#retention-framing-correction-owner-ruling-2026-10-04). **R1's 2026-10-03 figure was re-grounded on 2026-10-04**: the limitation-period justification is withdrawn and the number survives only as a project decision | Reusing an existing lock id, and a retention knob (a `--older-than` flag, env var or setting) that would let the documented value and the command drift apart | `fd5201d` |
| **Q-D8** | `LOG_MASK_KEY` provenance, production requirement, rotation policy | **Independent secret** (never derived from `SECRET_KEY`), **required and fail-fast in `prod.py`**, rotated **only on compromise, never on a schedule** | Deriving the mask key from `SECRET_KEY`. Rejected: one leak would then have two blast radii and there would be no scoped revocation | `b7ba213` |

### DECLINE-1 (Q-D1) — a DECLINE is reversible

**Findings this decision closes.** `06-PII-105` (the reversible-decline finding — this record is
its **decision half**; the implementation half is `8dba351`) and `06-PII-113` (the DECLINE
documentation conflict, whose remaining contradictions were adjudicated in the same pass). Both ids
are **cycle-scoped**: they identify findings raised by the phase-06 audit cycle and are reused by
no other phase, so a reader outside this cycle should follow the linked document, not the id.

**Decision.** A `DECLINE` is a **reversible** state. Ratified **2026-10-03**; implemented in
`8dba351`. A declined account is **login-eligible again** while **publishing stays restricted**
for as long as the decline stands.

**What "reversible" means concretely.** Four separate effects hang off `is_declined`, and the
decision moved exactly one of them:

| Effect | Carried by | After the decline | After re-consent |
|---|---|---|---|
| **Login eligibility** | `can_login()` (`apps/users/services/account_state.py`) | **allowed** — this is the change | restored by `give_consent` clearing `is_declined` |
| **Publishing** | `ads_auto_publish=False`, read by `can_publish_ad()` | **refused** — unchanged | `give_consent` sets `ads_auto_publish=True` |
| **Listing / search / direct-URL / media-gate visibility** | `account_state_q()` (`is_declined` is one of its five conjuncts) | **hidden** — unchanged | `is_declined` clears and the ad returns, subject to the other four conjuncts |
| **Bot interaction** | `AccountStateMiddleware` | **browse-only** — unchanged | full bot interaction |

`can_publish_ad()` never read `is_declined` and was **not** edited behaviourally; only its
docstring was corrected (it had claimed a decline does not block publishing). Reading
`is_declined` there would leave a re-consented seller un-publishable while a cached queryset
still held the stale flag. A decline therefore blocks publishing *through the
publishing-restriction flag*, not through a decline conjunct.

**Why the middleware carve-out is load-bearing, not cosmetic.** Dropping `is_declined` from
`can_login()` alone would have been nearly a no-op. The only clearer of `is_declined` is the
**authenticated** `consent_accept`, and for a declined user the bot never reaches
`handle_login_deep_link` — `/start login_<token>` is not a contact deep-link, and the decline
branch refused it. Recovery would still have depended on the very session that recorded the
decline. `AccountStateMiddleware` (`src/telegram_bot/middlewares/permissions.py`) therefore
gained a `login_<token>`-pattern carve-out, `_is_login_deep_link(text)`, matching the **same**
`LOGIN_PATTERN` the handler uses (imported lazily, to avoid a middleware/handler import cycle),
sitting as a **peer** of the existing `is_contact_link` carve-out and inside the `is_declined`
branch — which stays ahead of the plan-19 `is_support_intake` carve-out.

- A bare `text.startswith("login_")` was **rejected**: it also swallows `login_start`,
  `login_email` and `login_help`, widening the carve-out well beyond the token handshake and
  letting a declined user reach arguments the handler then refuses anyway.
- The carve-out applies to **`is_declined` alone**. A deactivated, banned, deleted or withdrawn
  account is refused even a well-formed login deep-link, so the plan-19 `19-D6` support
  carve-out contract still holds.

**No new token, model, field, table, migration or URL route was introduced.** The recovery route
is the **existing** `LoginToken` handshake: `/login/issue/` → the bot's
`/start login_<token>` → `/login/status/`. The session the decline left behind is now the route
back rather than a residue (a decline does not flush the web session).

**One consequence that is easy to miss.** `give_consent()` bumps `bump_search_cache_version`
under `transaction.on_commit`, mirroring `decline_consent()`. Without it "reversible" would be
true of the row and false of the site: clearing `is_declined` restores eligibility, but cached
search result sets were computed while the seller was excluded and `build_search_cache_key`
embeds `get_search_version()`, so the ads would stay invisible for up to `SEARCH_CACHE_TTL`
plus the stale window.

**Documentation consistency (`06-PII-113`).** The DECLINE wording is stated **once**, in the
shipped behaviour, and mirrored in the three places a reader reaches:

| Document | What it now says |
|---|---|
| [`technical-specification.md` §F / §K](../01-spec/technical-specification.md) | A decline is reversible; login eligibility is restored by re-consent; publishing stays restricted via `ads_auto_publish`; a declined seller's ads stay hidden from listings and search |
| [`architecture.md` § Bot Support Intake Flow](../99-agent/architecture.md#bot-support-intake-flow) | The bot-tier behaviour, including which deep-links a declined user may use |
| `privacy.html` §7 (template, user-facing) | The data-subject's wording: a decline is reversible, accept again to restore posting |

## BLOCK 18 — the consent actor and mechanism (`06-NEW-02`)

**Finding this closes.** `06-NEW-02` — reopened as an owned phase-06 follow-up by **owner ruling
2026-10-04**. BLOCKS 12 and 15 were **not** reopened; the finding had been routed to "BLOCK 12/15"
and both closed without it, leaving it orphaned.

**Why it was a data-model and accountability defect, not cosmetics.** `ConsentRecord` could not
distinguish *subject withdrew / staff revoked / system revoked*, so the **audit meaning** of the
Art. 7(1) ledger was incomplete. A staff revocation in the admin was evidenced identically to a
self-service withdrawal — the row read *"the subject withdrew"*.

**What shipped.** Two columns on `ConsentRecord` (`users/models.py`, migration
`0005_consentrecord_initiated_by_action_source`): `initiated_by` (FK → `users.User`, `SET_NULL`,
`related_name="+"`) names the acting account, and `action_source` (closed
`ConsentActionSource` StrEnum, default `unknown`, indexed) states the mechanism.

**The actor definition.** The actor is the account that performed the action, recorded **only when
it is not the subject**. `user` already names the subject, so a self-action would store the same
account twice. Invariant: `initiated_by IS NOT NULL` only when it is a different row from `user`.
Read the pair, never one column alone — `action_source` is authoritative for which case the row
is, `initiated_by` names the account when one exists. A null `initiated_by` means "no acting
account distinct from the subject", covering a self-service action, an anonymous visitor and a
system action; `action_source` tells those three apart. Leaving the self-action null is
load-bearing: a subject-populated copy would survive BLOCK 15's 90-day `user_id` clear and become
the only remaining link from an anonymous decision to a live account.

**No data migration and no backfill.** The ledger never recorded the actor or the mechanism, so
nothing is derivable. `AddField` wrote the default, so every pre-existing row reads
`action_source = "unknown"` with `initiated_by = NULL`: *"written before the actor was recorded;
the mechanism was never captured and is not recoverable"*. A null `initiated_by` on such a row
carries **no inference** about who acted, including for rows that were in fact staff revocations.

**Retention — ruled 2026-10-04, replacing the "implement, do not settle" position this section
previously carried.** The acting account is retained **12 months after the consent action, then
irreversibly anonymised, subject to documented legal hold**. The earlier position — retain the actor
to the event bound — was recommended by BLOCK 18 and then declined by the owner without a separate
necessity and proportionality justification; it is withdrawn, and so is the sentence claiming the
counter-argument was "deliberately unresolved". The rationale the owner gave, which is the
justification of record:

- a year preserves **full accountability** across a complete operational and audit cycle;
- it is **substantially shorter than the contested 5 years**;
- **identifying a specific employee beyond that requires separate justification**;
- and the figure is **a chosen minimisation period, not a statutory term**.

**Legal hold.** If an investigation, claim or litigation arises **before** the 12 months elapse,
actor anonymisation is **suspended for the period of documented necessity**. The mechanism is a
`legal_hold` flag column on the record, and `purge_consent_records` honours it: a held row is
skipped by the actor stage. The column and the 12-month actor stage of the sweep land together as
the follow-up to BLOCK 18 — BLOCK 18 itself shipped only the two columns named above, and left the
actor's lifetime untouched. **Open owner/DPO question, unchanged in substance:** whether the
12-month window is itself sufficient for the audit cycle the controller actually runs, and who may
set a hold. Neither is answered here; both need the DPO.

**`ConsentActionSource.SYSTEM` has no production writer today, and that is expected.** It exists
because the owner named "system revoked" as one of the three cases, and a closed vocabulary is what
stops a future writer inventing a fourth spelling. It is proven storable and distinguishable by
driving the real recording service.

**Documented residuals (recorded, not fixed).** The admin-initiated row still carries **no
`ip_address` and no `user_agent`** (BLOCK 10's shipped behaviour and its test). And
`record_consent_action`'s `request is None` branch drops `consent_version` when delegating — a
pre-existing defect, out of scope, but the line was edited to forward `action_source`.

## Retention framing correction (owner ruling 2026-10-04)

**What is withdrawn.** This phase recommended a five-year retention period for the consent ledger
and anchored it to a **statutory limitation period**. **That inference is withdrawn.** A limitation
period governs the window in which a *claim* may be brought; it says nothing about how long a
controller must keep a record, and stating it as the reason for a retention period was the error
being undone. Every document that carried that anchor has been corrected. No document now asserts a
statutory, regulatory, guideline or limitation-period anchor for any retention window in this
project.

**The rule as ruled.** Retention is **per field**, not one blanket period:

| Field | Rule | Standing |
|---|---|---|
| `user` (subject) | the general record retention — the existing **90-day fingerprint bound** | project decision, unchanged |
| `choice`, `categories`, `consent_version`, `consent_given_at` (the consent/revocation event and its timestamp) | the **event retention period** — **policy-based and justified by purpose** | project decision, re-grounded |
| `initiated_by` (actor) | **12 months from the action, then irreversibly anonymised**, subject to documented legal hold | project decision, **new** |

The governing statement, in the form that replaces the figure:

> `ConsentRecord` retention is **policy-based and must be justified by purpose; no general
> five-year retention requirement for this record is imposed by law.** In need-based form:
> **retain while there is a necessity to prove consent/withdrawal and the lawfulness of the
> corresponding processing; after a justified period expires, delete or anonymise.**

The implemented event window is still the value the command carries. It is now a **project decision
defended on purpose** and revisitable by the rule above. No law requires it, and no document may
cite one that does.

**Two supporting facts, recorded so that no reader re-derives them by inference:**

- **GDPR Art. 5(1)(e) requires storage limitation** — that personal data is kept no longer than
  necessary — and **prescribes no number**. Any document reading it as prescribing a duration is
  wrong. Art. 7(1), cited elsewhere in this phase for demonstrability, likewise states no duration.
- **Montenegro's Personal Data Protection Law №133/2026** entered into force **19 September 2026**,
  applies from **20 March 2027**, and sets **no** universal five-year period for a consent record.
  It is a **neighbouring regime, not this project's applicable law** — see
  [Jurisdiction](#jurisdiction--a-documented-revisitable-assumption). It is recorded because it is
  the regime of the **launch market**, which is not the regime of the **data subject**, and a reader
  meeting the two in one document will otherwise conflate them.

**What did not change:** the 90-day fingerprint window, the anonymise-never-delete design, the
absence of any `DELETE` path in the sweep, and the existing 30-day post-withdrawal user erasure.
None of those was part of this ruling.

## Jurisdiction — a documented, revisitable assumption

**What the documents currently assume.** [`technical-specification.md` §F](../01-spec/technical-specification.md)
states *"Jurisdiction: Montenegro (GDPR-equivalent)"*, and the project is specified for a
Montenegrin launch market and a Bosnian UI language (`bs`). The two are not the same question, and
this section exists because the difference changes the retention analysis.

**The assumption of record.** The **data subject** this ledger records consent for is in **Bosnia
and Herzegovina**. The governing instrument is therefore **not** the GDPR directly, and this
project's documentation does **not** establish that Montenegrin data-protection law applies.
Documents in this repository cite GDPR article numbers — Art. 5(1)(e), Art. 7(1), Art. 21 — as
descriptive shorthand for storage limitation, demonstrability and withdrawal. Those citations are
read here as shorthand for the substantive standards they stand for, **not** as citations of directly
applicable EU law, and that reading is what the whole retention analysis rests on.

**This assumption must be confirmed with the DPO, and is revisitable.** It is recorded as an
assumption precisely because this pass could not close it. What depends on it:

| Depends on the assumption | If it is wrong |
|---|---|
| Every "GDPR Art. X" citation used as a substantive standard in this phase's documentation | each must be re-cited to the correct instrument, or dropped as unsupported |
| The need-based retention rule as the applicable test | must be re-derived against whatever instrument actually applies |
| **The retention windows themselves (90 d / 12 months / event)** | **not** — they are project decisions justified on purpose. A different instrument changes the *legal floor*, not the *justification*; a lower floor could require shortening a window, never lengthening one on legal grounds |
| `privacy.html`'s statement of the retention period to the data subject | the period stated must match the window actually enforced |

**What this pass did not do, deliberately.** It did **not** name a BiH statute, gazette reference or
article number as the governing instrument. That citation could not be supported from the
repository, and inventing one would be worse than recording the gap. It did not resolve the
entity-level question — a BiH framework and the FBiH / RS entity rules are not interchangeable, and
the applicable entity is not identified anywhere in this documentation. Where the guidance is
genuinely ambiguous, this record says so rather than choosing a figure and implying authority.

## Open work

| Item | Question | State |
|---|---|---|
| **Applicable jurisdiction (DPO)** | The data subject is in **Bosnia and Herzegovina**, so the governing instrument is not the GDPR directly and the spec's *"Jurisdiction: Montenegro (GDPR-equivalent)"* is an assumption, not a finding. Which instrument applies, and at which entity level (FBiH / RS / framework)? | **Open — DPO.** Recorded as a revisitable assumption in [Jurisdiction](#jurisdiction--a-documented-revisitable-assumption). No citation was invented and no entity was chosen |
| **Event-retention period (DPO)** | The implemented event window is a project decision. Is it the right figure for this controller, on the need-based rule? | **Open — DPO.** The number is now labelled a project decision with its rationale, not a legal requirement. Changing it is a constant change in `purge_consent_records` plus this record |
| **Actor window and legal hold (DPO)** | Is 12 months sufficient for the audit cycle actually run, and **who may set a `legal_hold`**? | **Open — DPO.** The window and the hold mechanism are ruled; the operational half — who may place a hold, and how it is documented and reviewed — is unanswered |
| **`06-NEW-02` (actor column)** | — | **CLOSED and owned by BLOCK 18.** The column exists; the retention decision and its open DPO question are recorded above and in [`db-schema.md`](../02-database/db-schema.md#consent_records-zone-f--plan-21) |
| **`06-PII-113` audit rubric (coordinator-owned)** | The phase-06 audit handbook's block 1 (*Consent states*) tells the auditor that "where sources disagree … **pick no winner**". That instruction is correct for an undecided question and **wrong for a decided one**: because DECLINE reversibility is now decided here, a future run would re-derive the same source disagreement and re-file it as a finding rather than recognise it as settled. | **Open, coordinator-owned.** `.ai/audit/**` and `.kilo/commands/audit/**` are audit inputs, not product documentation, and were **not** edited by this pass. Correcting the rubric is a coordinator deliverable, not this phase's |

## Boundaries deliberately left untouched

| Boundary | Why it is still absent |
|---|---|
| **No `is_declined` term in `can_publish_ad()`** | Publishing is restricted by `ads_auto_publish`, which `decline_consent` sets and `give_consent` restores. Adding a decline conjunct would re-block a re-consented seller behind a stale cached queryset |
| **No `__Host`-style new recovery token** | The existing `LoginToken` handshake was sufficient; a second credential for the same job would be a second revocation surface |
| **`MODERATOR` / ban-target-scope contract not restated here** | Stated once in [`technical-specification.md` §H](../01-spec/technical-specification.md) and in `apps/moderation/admin_actions.py`. A second copy is a second source of truth |
| **No data migration for a `LOG_MASK_KEY` rotation** | Nothing persists a masked value — no model field, session, cache key or Redis key. Rotating the key changes every masked value in the log history; that is a log-correlation cost, not a data migration |

## Where the shipped behaviour is documented

| Fact | Durable document |
|---|---|
| DECLINE = reversible; the four effects and which predicate carries each | [`technical-specification.md` §F / §K](../01-spec/technical-specification.md) |
| `account_state_q()` — the single five-conjunct account-state declaration, and its consumers | [`architecture.md`](../99-agent/architecture.md), [`technical-specification.md`](../01-spec/technical-specification.md) |
| `can_login` / `can_publish_ad` / `can_store_personal_data` / `can_create_ad` composition | [`architecture.md`](../99-agent/architecture.md) |
| Bot-tier carve-outs (`is_contact_link`, `login_<token>`, plan-19 support) | [`architecture.md` § Bot Support Intake Flow](../99-agent/architecture.md#bot-support-intake-flow) |
| `purge_consent_records`: 90-day fingerprint / 12-month actor / event window, anonymise-never-delete, `legal_hold`, advisory lock 14 | [`db-retention.md`](../02-database/db-retention.md#purge_consent_records-06-pii-116) |
| **The retention rule itself** (per-field windows; policy-based, justified by purpose; no statutory anchor; Art. 5(1)(e) prescribes no number; №133/2026 as a neighbouring regime) | this record, [Retention framing correction](#retention-framing-correction-owner-ruling-2026-10-04) |
| **The jurisdiction assumption and its dependents** | this record, [Jurisdiction](#jurisdiction--a-documented-revisitable-assumption) |
| `consent_records` columns, `IX_consent_records_sweep`, and the actor/mechanism definition and retention decision | [`db-schema.md`](../02-database/db-schema.md#consent_records-zone-f--plan-21) |
| `LOG_MASK_KEY`: the env-var contract, the guard chain, and the rotation trade-off | [`docker-deployment.md`](../ops/docker-deployment.md#environment-variables) |
| `mask_telegram_id()` keyed-HMAC construction and why the value is pseudonymised, not anonymised | [`technical-specification.md` §F](../01-spec/technical-specification.md) |
| `ModeratorActionLog.reason` redaction at write time | [`technical-specification.md` §A](../01-spec/technical-specification.md) |
| `search_query_key()` — redact-then-lower, and why a keyed digest was rejected | [`db-schema.md`](../02-database/db-schema.md#popularsearch) |
| Support intake gated on storage consent; tickets erased on withdrawal | [`architecture.md` § Bot Support Intake Flow](../99-agent/architecture.md#bot-support-intake-flow), [`db-schema.md`](../02-database/db-schema.md#support_tickets) |