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

| Gate | Question | Decision (ratified 2026-10-03) | Rejected alternative | Implementation |
|---|---|---|---|---|
| **Q-D1** | Is a consent **DECLINE** reversible? | **(a) Reversible.** `is_declined` is dropped from `can_login()`; publishing and listing/search visibility stay restricted while the decline stands. See [DECLINE-1](#decline-1-q-d1--a-decline-is-reversible) | **(b) Intentionally one-way** — leave `can_login()` alone and correct `privacy.html` §7 to say the choice is final for seller features. Rejected because it keeps a silent, effectively irreversible takedown of a live seller's listings as the side effect of clicking a cookie banner, and leaves recoverability an open design item instead of a courtesy | `8dba351` |
| **Q-D4** | `ConsentRecord` retention: what bound, and which advisory-lock id? | **R1 — decision fields: 5 years, anonymise, never delete. R2 — fingerprint fields (`session_key`, `user_agent`, `ip_address`, plus the `user` link): 90 days.** A fresh id was taken (**14**) rather than reusing an existing lock | Reusing an existing lock id, and a retention knob (a `--older-than` flag, env var or setting) that would let the documented value and the command drift apart | `fd5201d` |
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

## Open work

| Item | Question | State |
|---|---|---|
| **`06-NEW-02` — `ConsentRecord` has no actor column** | Who performed a consent action is not recorded. A staff-initiated revocation in the admin is evidenced as *"the subject withdrew"*, with nothing recording that a staff member did it, and the admin-initiated row carries **no IP address and no user agent**. | **Open and unowned.** The retention sweep that shipped under Q-D4 does **not** close it: it bounds and anonymises the ledger, it does not add provenance. Recorded as a known limitation in [`db-schema.md`](../02-database/db-schema.md#consent_records-zone-f--plan-21) — it is **not** assigned to any block, and no block in this pass is still to come |
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
| `purge_consent_records`: 90-day fingerprint / 5-year decision, anonymise-never-delete, advisory lock 14 | [`db-retention.md`](../02-database/db-retention.md) |
| `consent_records` columns, `IX_consent_records_sweep`, and the missing-actor-column limitation | [`db-schema.md`](../02-database/db-schema.md#consent_records-zone-f--plan-21) |
| `LOG_MASK_KEY`: the env-var contract, the guard chain, and the rotation trade-off | [`docker-deployment.md`](../ops/docker-deployment.md#environment-variables) |
| `mask_telegram_id()` keyed-HMAC construction and why the value is pseudonymised, not anonymised | [`technical-specification.md` §F](../01-spec/technical-specification.md) |
| `ModeratorActionLog.reason` redaction at write time | [`technical-specification.md` §A](../01-spec/technical-specification.md) |
| `search_query_key()` — redact-then-lower, and why a keyed digest was rejected | [`db-schema.md`](../02-database/db-schema.md#popularsearch) |
| Support intake gated on storage consent; tickets erased on withdrawal | [`architecture.md` § Bot Support Intake Flow](../99-agent/architecture.md#bot-support-intake-flow), [`db-schema.md`](../02-database/db-schema.md#support_tickets) |