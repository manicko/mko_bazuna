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
  - spec-index
---

## Purpose

Authoritative list of the `StrEnum` types referenced by the schema. Every fixed value set
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
Origin of an ad or event. Phase 1 accepts ads via the Telegram bot (TELEGRAM); SEED marks
auto-generated demo data. The `source` field is also on `users`, `analytics_events`, and
`PopularSearch` (added in Plan 11/12) to enable direct seed-data cleanup without reverse-FK traversal.

| Value | Meaning |
|-------|---------|
| `TELEGRAM` | bot-only source in phase 1 |
| `SEED` | generated demo/seed data |

## CurrencyCode
Supported ad listing currencies (project rule 10 — never plain strings). `EUR` is the
default display currency (project launches in Montenegro). Rates are stored relative to
EUR in the `exchange_rates` table; `Ad.price_currency` and `ExchangeRate.currency` store
this enum's value (see [db-schema.md](db-schema.md)).

| Value | Meaning |
|-------|---------|
| `EUR` | Euro (default) |
| `RSD` | Serbian Dinar |
| `BAM` | Bosnia and Herzegovina Convertible Mark |

## EventType
Analytics event kinds for `analytics_events.event_type` (see [db-schema.md](db-schema.md)).

| Value | Meaning |
|-------|---------|
| `REGISTRATION_CREATED` | user registered |
| `AD_PUBLISHED` | an ad was published |
| `SEARCH_PERFORMED` | a search query ran |
| `CONTACT_INITIATED` | a buyer initiated contact with a seller |
| `AD_VIEWED` | ad detail page viewed (seller-scoped) |
| `CONTACT_RESPONSE` | seller responded to a contact message |
| `AD_EDITED` | ad text/content modified |
| `AD_REACTIVATED` | archived ad republished |
| `DASHBOARD_VIEWED` | seller opened the dashboard |
| `SELLER_VERIFIED` | seller verification status changed |
| `TRUST_LEVEL_UPDATED` | trust score/level recalculated |
| `MODERATION_APPROVED` | ad passed moderation |
| `MODERATION_REJECTED` | ad failed moderation |
| `MODERATION_FLAGGED` | ad flagged for senior review |
| `AD_REPORTED` | ad reported by a buyer |
| `CONTACT_COMPLETED` | contact exchange completed |

## ModeratorActionType
`ModeratorActionLog.action_type` values (see [db-schema.md](db-schema.md)).

| Value | Meaning |
|-------|---------|
| `REJECT` | ad manually rejected |
| `BAN_ACCOUNT` | seller account banned |
| `SOFT_DELETE` | ad soft-deleted |
| `CRITERIA_CHANGE` | moderation criteria edited at runtime |
| `OTHER` | other moderator action |

## BulkModerationAction
Bulk moderation action types accepted by the moderation JSON API
(`bulk_moderation_action` view). This is an API-level vocabulary — it is **not**
stored as a database column (individual outcomes are persisted as ad status
transitions and `ModeratorActionLog` entries, see [db-schema.md](db-schema.md)).

| Value | Meaning |
|-------|---------|
| `APPROVE` | publish the selected ads |
| `REJECT` | reject the selected ads (requires a reason) |
| `FLAG` | recalculate moderation priority for the selected ads |

The API validates the action up front and returns `400` for any value outside
this set.

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
configuration name for each locale, and `fts_vector_field` returns the matching
per-language `ads.search_vector_*` column. Used by the search and alert services
to select the correct vector + config when queries are in different languages.

## TrustLevel
Seller trust level for badge display and trust scoring (see [db-schema.md](db-schema.md)).

| Value | Meaning |
|-------|---------|
| `UNVERIFIED` | no verification or activity history |
| `VERIFIED` | admin-verified or Telegram Premium |
| `TRUSTED` | established seller with good metrics |
| `PRO` | top-tier seller (score >= 90) |

## TimeRange
Time range options for seller statistics filtering.

| Value | Meaning |
|-------|---------|
| `ALL_TIME` | all historical data |
| `THIRTY_DAYS` | last 30 days |
| `SEVEN_DAYS` | last 7 days |

## ThumbnailSizeStrEnum
Standard thumbnail sizes for ad images.

| Value | Meaning | Dimensions |
|-------|---------|----------|
| `SMALL` | small thumbnail | 240x180 |
| `MEDIUM` | medium thumbnail | 640x480 |
| `LARGE` | large thumbnail | 1280x960 |

## AdPriorityLevel
Priority levels for moderation queue triage.

| Value | Meaning |
|-------|---------|
| `HIGH` | requires immediate review |
| `MEDIUM` | standard review priority |
| `LOW` | low-risk, standard review |

## SearchSuggestionSource
Source of an autocomplete suggestion.

| Value | Meaning |
|-------|---------|
| `USER_HISTORY` | from authenticated user's search history |
| `POPULAR_SEARCH` | from popular search queries |
| `CATEGORY` | from category name matching |
| `CITY` | from city name matching |

## LookupGroupCode
Machine-readable codes for built-in lookup groups. Used in model field `limit_choices_to`, builder, and resolver — never plain strings.

| Value | Meaning |
|-------|---------|
| `LISTING_PURPOSE` | `listing_purpose` — what the seller wants to do (sell, buy, rent, etc.) |
| `LISTING_CONDITION` | `listing_condition` — condition of the item (new, used, etc.); single-select per ad (Plan 12) |
| `LISTING_FEATURE` | `listing_feature` — characteristics of the listing (urgent, etc.); multi-select, AND-semantics |

## ConsentChoice
User's consent decision recorded in `consent_records.choice` (see [db-schema.md](db-schema.md)).
Backs the GDPR/ePrivacy accept/decline/withdraw flow (decision F, zone R3).

| Value | Meaning |
|-------|---------|
| `ACCEPTED` | user accepted all processing (cookie `consent_given=accepted`) |
| `DECLINED` | user declined non-essential cookies (browse-only; no erasure) |
| `WITHDRAWN` | user withdrew consent (sets `consent_revoked_at`; triggers soft-delete + 30-day PII erasure) |

## CookieCategory
Non-essential cookie categories offered by the consent banner (Plan 21 D-9). Used as the
vocabulary for the `consent_analytics` / `consent_preferences` cookies and the
`consent_records.categories` JSON payload. Only `Essential` cookies (sessionid, csrftoken)
are always on.

| Value | Meaning | Cookie |
|-------|---------|--------|
| `ESSENTIAL` | strictly necessary cookies (always on) | — |
| `ANALYTICS` | anonymized traffic analytics (Plausible) | `consent_analytics` |
| `PREFERENCES` | language + city settings | `consent_preferences` |

> `CookieCategory` is defined in `apps/core/enums.py` (exported via `__all__`), but the
> `categories` flags are still passed and stored as **plain string keys**
> (`"analytics"`, `"preferences"`) in `ConsentSubmission` and `record_consent_action`.
> The enum members are not referenced by runtime code.
