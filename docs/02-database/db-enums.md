---
id: db-enums
domain: database
tags:
  - database
  - enums
  - str-enum
related:
  - db-schema
  - db-indexes
  - technical-specification
---

## Purpose

Authoritative list of the `StrEnum` types referenced by the phase 1 schema. Every fixed value set
is modeled as a `StrEnum` (never plain strings/dicts). Table and column context lives in
[db-schema.md](db-schema.md); indexes and triggers live in [db-indexes.md](db-indexes.md).

## AdStatus
Ad lifecycle status. The only buyer-visible status is `PUBLISHED`.

| Value | Meaning |
|-------|---------|
| `DRAFT` | bot draft, not sent |
| `ON_MODERATION` | awaiting auto-check (hidden) |
| `PUBLISHED` | published (only buyer-visible status) |
| `REJECTED` | manually rejected by moderator (kept 90 days, then purge) |
| `ON_MODERATION_FAILED` | failed auto-check (purged after 7 days) |
| `ARCHIVED` | auto-archive (2mo) / manual archive |
| `DELETED` | soft delete |

Transitions are defined in [db-schema.md](db-schema.md).

## AdSource
Origin of an ad. Phase 1 accepts ads only via the Telegram bot (decision B).

| Value | Meaning |
|-------|---------|
| `TELEGRAM` | bot-only source in phase 1 |

## EventType
Analytics event kinds for `analytics_events.event_type` (see [db-schema.md](db-schema.md)).

| Value | Meaning |
|-------|---------|
| `REGISTRATION_CREATED` | user registered |
| `AD_PUBLISHED` | an ad was published |
| `SEARCH_PERFORMED` | a search query ran |
| `CONTACT_INITIATED` | a buyer initiated contact with a seller |

## ModeratorActionType
`ModeratorActionLog.action_type` values (see [db-schema.md](db-schema.md)).

| Value | Meaning |
|-------|---------|
| `REJECT` | ad manually rejected |
| `BAN_ACCOUNT` | seller account banned |
| `SOFT_DELETE` | ad soft-deleted |
| `CRITERIA_CHANGE` | moderation criteria edited at runtime |
| `OTHER` | other moderator action |

## CategoryRejectReason
UI/admin vocabulary enum for moderator reject dropdown. Used as guidance for
reason text in `ModeratorActionLog` (never shown to seller, US-A11).

| Value | Meaning |
|-------|---------|
| `ADULT_CONTENT` | adult/pornographic content |
| `VIOLENCE_GORE` | violence or gore |
| `DRUGS_WEAPONS` | drugs or weapons |
| `HATE_SPEECH` | hate speech |
| `COUNTERFEIT_GOODS` | counterfeit goods |
| `ILLEGAL_GOODS` | illegal goods |
| `SPAM_SCAM` | spam or scam |
| `OFF_TOPIC` | off-topic content |

## LanguageLocale
Supported locale codes for UI and ad content. Maps to PostgreSQL text search
configurations for language-aware search.

| Value | Meaning | FTS Config |
|-------|---------|----------|
| `RUSSIAN` | Russian (base UI/content language) | `russian` |
| `BOSNIAN` | Bosnian (Montenegrin Latin script) | `simple` |
| `ENGLISH` | English | `english` |

The `fts_config` property returns the appropriate PostgreSQL text search
configuration name for each locale. Used by the search service to select the
correct search configuration when queries are in different languages.
