---
id: user-stories-index
domain: user-stories
tags:
  - user-stories
  - requirements
related:
  - technical-specification
  - seller-stories
  - buyer-stories
  - admin-stories
---

## Purpose

Index of all phase-1 user stories, grouped by role. Each story is the authoritative,
implementable requirement for a single behavior. Domain rules referenced as "decision X"
live in [technical-specification.md](../01-spec/technical-specification.md).

## Main Concepts

- **Roles:** Seller (posts ads via bot), Buyer (browses site, no login), Admin (moderates).
- **ID scheme:** `US-<role><n>` — e.g. `US-S2`, `US-B4`, `US-A10`. IDs are stable references
  used across the DB schema and spec.
- **Single source of truth:** story acceptance behavior lives here; product decisions live in the spec.

## Story Files

| Role | File | Stories |
|------|------|---------|
| Seller | [seller-stories.md](seller-stories.md) | US-S1, S2, S5, S6, S7, S8, S9 |
| Buyer | [buyer-stories.md](buyer-stories.md) | US-B1–B9 |
| Admin | [admin-stories.md](admin-stories.md) | US-A1–A11 |

> Story numbering has intentional gaps (e.g. no US-S3/S4) preserved from the original backlog.
