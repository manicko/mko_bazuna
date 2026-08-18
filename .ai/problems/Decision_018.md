---
id: decision-018-preferred-city
domain: decisions
tags:
  - catalog-ui
  - search
  - user-profile
  - mvp
related:
  - 14_catalog-ui-avito_spec
  - 15_catalog-ui-avito_plan
  - db-schema
  - architecture-structure
---

## Decision 018 — Preferred-city persistence strategy (plan 15, T-100)

**Status:** Approved
**Date:** 2026-08-18
**Scope:** Resolves the storage strategy for a buyer's `preferred_city` (search/autocomplete
feature). Gates plan-15 task T-700.

## Context

The catalog header (spec_014) lets a buyer click a **city** suggestion, which should
remember the choice and filter results. Spec §8.3 originally stated the registered-user path
uses `UserProfile.preferred_city`, but **no `UserProfile` model exists** in `apps/users`
(the app has a single custom `User` model and `LoginToken`). A repository-wide grep confirms
zero consumers reference a non-existent `UserProfile`.

Three storage options were evaluated against the project rules (#5 avoid overengineering, #7
follow existing patterns, #13 migrations for schema changes, strict separation of concerns):

- **(a) New `UserProfile` model** with `preferred_city = FK("locations.City")` — adds a whole
  profile subsystem (model, migration, OneToOne wiring, auto-creation signal) for a single
  non-critical field.
- **(b) Add `preferred_city` FK directly to `User`** — simpler, but still a schema migration +
  a server write path for a minor UX preference; the `User` model currently carries no FK
  columns.
- **(c) Cookie-only** — set a `preferred_city` cookie (city slug, 30-day expiry) on city
  suggestion click; works for both guests and registered buyers on the public pages that
  render the shared header. No schema, no migration, no server write path.

## Decision

**Option (c) — cookie-only `preferred_city` for this plan.**

The Product Owner explicitly capped MVP at "preferred-city storage without complex
personalization" (spec §2 Out of Scope, PO Q1). The header is rendered on public
catalog/search/detail pages for all visitors; being authenticated does not change the header
behavior, so a cookie is a sufficient and uniform persistence mechanism for both guests and
registered buyers. This keeps the change purely additive (no new table/column, no migration,
no server persistence endpoint with schema implications — consistent with the plan's
low-risk, additive posture).

Registered-user profile persistence (FK on a future `UserProfile` / `User`) is **deferred** to
a dedicated task that will be designed together with the buyer-profile subsystem, when there
are real consumers.

## Consequences

- City-suggestion click sets the `preferred_city` cookie client-side and filters results via
  the existing URL-based city filter.
- No `apps/users` schema change; `makemigrations --check` remains clean.
- T-700 scope is reduced to the cookie write + the header's city-click filter navigation; the
  profile-storage dimension is out of scope for this plan.

## Verdict

**Go with changes** — T-700 proceeds with the cookie-only implementation.
