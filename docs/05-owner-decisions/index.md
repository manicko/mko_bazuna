---
id: owner-decisions-index
domain: owner-decisions
tags:
  - owner-decisions
  - product-owner
  - user-behavior
  - governance
related:
  - technical-specification
---

## Purpose

This file is the **single source of truth for the product owner's decisions O1–O8**. It is written for
the **product owner** — the person who owns user-facing behavior, not architecture or implementation.

Each decision records, in plain language, what the owner actually said about how the system should
behave for users. The "Technical consequence" column is kept brief and is for developers only: it
explains what the decision implies for the implementation. Do not duplicate the decision text
anywhere else.

## Main Concepts

- **Owner-readable:** Every decision is stated so the owner can confirm "yes, I said that".
- **No duplication:** The technical-specification.md only links here; it does not repeat this text.
- **Audit traceability:** Each decision lists its audit zone (e.g. R4) so developers can trace back to
  the full zone-resolution evidence in the spec and database docs.

## Owner Decisions

| ID | Topic | Decision (what the owner said) | Technical consequence | Audit zone |
|----|-------|-------------------------------|-----------------------|------------|
| **O1** | Turning off posting, deleting an ad, and banning a user | There are **three separate things**, and they must not be confused: <br>1. **Turning off auto-publish** — reversible; the seller's old ads are simply hidden, nothing is erased. <br>2. **Deleting an ad** — soft removal; the seller's personal data is wiped 30 days later. <br>3. **Banning the user** — blocks all of that user's ads, but their account/contact info is kept so the block stays in force. | Three independent states. A ban keeps `telegram_id`/`username` and purges the user's ads; a delete nulls personal data after 30 days. | R4 |
| **O2** | Refusing the consent banner vs. deleting the account | Refusing (declining) the consent banner is **NOT the same as deleting the account**. Refusal only blocks the seller from posting; it does **not** erase anything and does **not** hide the "Contact seller" button. Deleting/withdrawing erases everything. | Decline ≠ withdraw. Withdraw sets `consent_revoked_at` and triggers full erasure. | R3 |
| **O3** | What happens when a user deletes their account | When a user deletes their account, **all their personal data and ads must be fully erased 30 days later**. | Delete ads and images, clear `telegram_id`/`username`, and clear user references in analytics/moderator logs after 30 days. | R1 |
| **O4** | How ads are checked before they are published | Ads are checked **automatically before publishing** using text rules (minimum lengths, required fields, duplicate detection). A **human moderator** reviews the photos and content, and can **edit the rules at any time** while the system is running. The rules are not versioned. | Two layers: automatic checks (`moderation_criteria`) plus manual admin review of photos/content. Minimum-text-length rule removed. | D3 / D4 |
| **O5** | Finding ads by category | Buyers must be able to **find ads by category name** in phase 1. | Hybrid search: denormalized category name included in the search index (weight 'C') plus fuzzy category detection; buyers search in their own language against per-language FTS vectors (no query-time translation — decision G). | D1 / D2 |
| **O6** | Does a ban hide the banned seller's inventory? (Q7) | **A ban hides inventory.** A banned seller's ads are excluded from every public surface — search results, category listings, the ad detail page and the media gate. This is a **moderation** sanction, not a consent matter: banning is a seller-relationship sanction, and removing the inventory is part of that sanction. | Add the `is_banned=False` term to the shared public ad-visibility predicate on all four read surfaces (search, category listings, ad detail, media gate). Argue and record it as **ban enforcement**; never as a consent/`is_declined`/`consent_version` fix — those are different concepts and conflating them mislabels the change. | R4 |
| **O7** | Does a ban also stop the seller creating or publishing? (Q7′) | **Yes.** A banned seller **cannot create or publish** a new ad. Ban enforcement covers **relisting**, not only login. | The write path (create/publish) refuses a banned seller. This is a **phase-06 follow-on** on the `SRCH-008` write boundary. Anywhere in the plan set that "a banned seller can still relist" is recorded as an accepted known gap, that gap is **closed** and the documenting test becomes a positive control asserting the block. | R4 |
| **O8** | The single-word category narrowing: may the buyer undo the guess? (Q8) | **Yes — as a user-initiated opt-out, not as default behaviour.** The narrowing stays a **hard filter** for every request that does not ask otherwise, and the results page signals it. The buyer may undo the guess for their own query by following a control that **keeps their search term** and re-runs it across the **whole tree**. This is the ruling that discharges Q8's *"an undo, not merely a notice"* condition. | `search()` reads `?all_categories=1` and threads it into the narrowing step and the search cache key, suppressing the single-word category narrow **for that request only**. With the parameter absent, `_apply_fts_filtering` / `_is_single_word` behave exactly as before and the default predicate is **byte-identical**, so option (a)'s disjunctive branch is never adopted as default behaviour. The control's link carries `q` **and** the flag (plus the other seven filters). `SRCH-009` is now fully discharged. | D1 / D2 |

## Cross-References

- Full zone-resolution evidence (C1–C8, R1–R9, D1–D12) lives inline across
  [`../01-spec/technical-specification.md`](../01-spec/technical-specification.md),
  [`../02-database/db-schema.md`](../02-database/db-schema.md), and
  [`../02-database/db-indexes.md`](../02-database/db-indexes.md).
- Audit zones referenced above: **R1** (erasure), **R3** (consent decline ≠ withdraw),
  **R4** (three account states), **D1/D2** (category search), **D3/D4** (moderation criteria).
- The operator **ban target scope** (a moderator may ban ordinary sellers only; a superuser is
  unrestricted) is **not** an O1–O5 owner decision and is deliberately not restated here. It is
  stated once in
  [`../01-spec/technical-specification.md` §H](../01-spec/technical-specification.md) (the
  `is_banned` operator contract) and in the `apps/moderation/admin_actions.py` docstrings. Do not
  duplicate it into this table — a second copy becomes a second source of truth.

## Ban enforcement — ad visibility (phase-08 handoff)

The **Q7** and **Q7′** rulings above were taken by the Product Owner on **2026-10-03** and are
recorded here so the moderation decision has one findable home. They are **moderation** decisions:
a ban is a seller-relationship sanction, and hiding inventory and refusing new listings are part of
that sanction. They are **not** consent rulings — `is_declined` and `consent_version` are separate
concepts with separate semantics, and a change that implements Q7/Q7′ must be argued and recorded
as ban enforcement, never as fixing a consent violation.

**Handoff to phase 06 (`SRCH-004` / `06-PII-104`).** Phase 06 landed `account_state_q()` and applied
it to the **alert** path. `SRCH-004` is absorbed by `06-PII-104` verbatim and phase 08 does not edit
`apps/search/services/alert_query.py`. Two obligations remain with phase 06:

1. **Read boundary (Q7).** Exclude a banned seller's ads from the **public** ad-visibility
   predicate on all four surfaces. Phase 08 implemented this read-boundary predicate using the
   existing `account_state_q()` helper on `apps/ads/services/listings_query.py` and
   `apps/ads/views/listings.py` because the ruling had no owning phase and the exposure was live.
2. **Write boundary (Q7′), OPEN — owner: phase 06.** The write path must refuse a banned seller
   from creating or publishing an ad. This is a phase-06 follow-on and is **not** implemented by
   phase 08; it is recorded here as an open obligation.

Also: any `TRUSTED_PROXY_NETWORKS`-style "known gap" language recording that a banned seller can
still relist is **closed** by Q7′ — do not record it as accepted.

### O6 breadth — the predicate's five conjuncts (recorded, not hidden)

The read-boundary fix for Q7 replaced the lone `user__is_declined=False` term with the shared
`account_state_q("user__")` declaration. That predicate carries **five** conjuncts, so the change
newly excludes more than the ban alone. Recorded here so the breadth is not hidden:

1. `is_banned=False` — the **intended** term; Q7's ban enforcement.
2. `is_deleted=True` — newly excluded. A deleted account is a GDPR-withdrawal state; hiding its
   inventory is strictly more privacy-protective.
3. `consent_revoked_at IS NOT NULL` — newly excluded.
4. `is_declined=False` — the pre-existing term, now carried by the shared predicate.
5. `is_active=False` — newly excluded. No owner has ruled on hiding a **deactivated** seller's
   inventory; the exclusion self-heals on reactivation, but it is a behaviour change beyond the
   ban.

Two of the newly-excluded terms (2 and 3) **are consent concepts**, which sits awkwardly against
the instruction that the change must never be argued as a consent fix. They are present as a **side
effect of reusing one shared predicate** (the plan's Q6 answer explicitly asked for one named
predicate, not two), not as a consent justification. The change is still recorded as **ban
enforcement**; the enumeration is here so no reader mistakes it for ban-only.

### The favourites list — the fifth public surface (O6)

O6's original wording claimed exclusion from "every public surface" while the four named surfaces
were search, category listings, ad detail and the media gate. The authenticated favourites list
(`apps/cabinet/views/favorites.py`) renders through the same `ads/partials/ad_list.html` card and
originally filtered neither by status nor by account state, so a banned seller's PUBLISHED ad
stayed visible there with its title, price, thumbnail and contact affordance. That over-claim is
closed: the favourites list now applies the **same** `account_state_q("user__")` predicate (and a
PUBLISHED status filter), with a positive control proving an active seller's favourited ad is
unchanged.
