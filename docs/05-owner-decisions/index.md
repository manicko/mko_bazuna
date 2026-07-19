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

This file is the **single source of truth for the product owner's decisions O1–O5**. It is written for
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
| **O5** | Finding ads by category | Buyers must be able to **find ads by category name** in phase 1. | Hybrid search: denormalized category name included in the search index (weight 'C') plus fuzzy category detection; a Bosnian query is translated to Russian before searching. | D1 / D2 |

## Cross-References

- Full zone-resolution evidence (C1–C8, R1–R9, D1–D12) lives inline across
  [`../01-spec/technical-specification.md`](../01-spec/technical-specification.md),
  [`../02-database/db-schema.md`](../02-database/db-schema.md), and
  [`../02-database/db-indexes.md`](../02-database/db-indexes.md).
- Audit zones referenced above: **R1** (erasure), **R3** (consent decline ≠ withdraw),
  **R4** (three account states), **D1/D2** (category search), **D3/D4** (moderation criteria).
