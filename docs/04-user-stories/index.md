---
id: user-stories-index
domain: user-stories
tags:
  - user-stories
  - requirements
related:
  - technical-specification
  - ui-patterns
  - search-patterns
  - filter-ui
  - seller-stories
  - buyer-stories
  - admin-stories
---

## Purpose

Index of all phase-1 user stories, grouped by role. Each story is the authoritative,
implementable requirement for a single behavior. Domain rules referenced as "decision X"
live in [technical-specification.md](../01-spec/technical-specification.md).
UI patterns referenced as "pattern X" live in [ui-patterns.md](../01-spec/ui-patterns.md).

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

## UI Pattern References

Buyer stories US-B2–B4, US-B7–B8 reference patterns documented in [`../01-spec/ui-patterns.md`](../01-spec/ui-patterns.md):
- Responsive Grid Layout (US-B2, US-B8)
- Card-Based Ad Display (US-B4)
- Price Display (US-B4)

Search patterns for US-B2–B3 are in [`../01-spec/search-patterns.md`](../01-spec/search-patterns.md):
- Hero Search with Location
- Query Translation
- Did-You-Mean

Filter patterns for US-B3, US-B7 are in [`../01-spec/filter-ui.md`](../01-spec/filter-ui.md):
- Sticky Sidebar Filters
- Mobile Filter Drawer
- Filter Chips/Tags

> Story numbering has intentional gaps (e.g. no US-S3/S4) preserved from the original backlog.