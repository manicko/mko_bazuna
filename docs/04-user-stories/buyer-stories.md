---
id: buyer-stories
domain: user-stories
tags:
  - user-stories
  - buyer
  - search
related:
  - user-stories-index
  - technical-specification
  - ui-patterns
  - search-patterns
  - filter-ui
  - db-schema
---

## Purpose

Buyer-role user stories. Buyers browse, search, and filter the website **without registration**.
Domain rules referenced as "decision X" live in
[technical-specification.md](../01-spec/technical-specification.md). See also [ui-patterns.md](../01-spec/ui-patterns.md),
[search-patterns.md](../01-spec/search-patterns.md), and [filter-ui.md](../01-spec/filter-ui.md) for implementation patterns.

## Stories

### US-B1 � Browse without registration
Anyone browses ads with status \PUBLISHED\; no login required.

### US-B2 � Search
Keyword search over title + description (\PUBLISHED\ only), response =2s. Sort by date (newest
first) or price. A Montenegrin query is translated to Russian before FTS (results optionally tagged
"translated from Russian"). Friendly empty state on no results. See decision G and [search-patterns.md](../01-spec/search-patterns.md).

### US-B3 � Filter
Filter by category/subcategory, city, and price range; filters combinable with no full page
reload (HTMX). Exact city match + "did you mean" on typos. See decision G and [filter-ui.md](../01-spec/filter-ui.md).

### US-B4 � Ad card
Card shows full ad details and a "Contact seller" button only � **no seller identity** shown. See
decision C and [ui-patterns.md](../01-spec/ui-patterns.md).

### US-B5 � Contact seller
Contact via deep-link to our bot (\	.me/<bot_username>?start=contact_<ad_id>\); the bot relays
without revealing seller PII. No login required. Button renders only when the ad is \PUBLISHED\,
seller \	elegram_id\ is set, and the seller is not deleted/banned/withdrawn. See decision C / zone R2 and [ui-patterns.md](../01-spec/ui-patterns.md).

### US-B6 � Browse by category
Browse ads by category with hierarchy support (django-mptt subtree). See [filter-ui.md](../01-spec/filter-ui.md).

### US-B7 � Browse by city
Browse by city; exact match against the closed preset list; "did you mean" on typos; selected city
saved in session. See decision D and [filter-ui.md](../01-spec/filter-ui.md) and [search-patterns.md](../01-spec/search-patterns.md).

### US-B8 � Responsive UI
Responsive layout across mobile, tablet, and desktop. See [ui-patterns.md](../01-spec/ui-patterns.md).

### US-B9 � Multilingual UI
UI language switch (Russian / Montenegrin-latin), persisted across sessions. Switch translates the site
shell only; ad content is stored in Russian and translated on display. See decision G and [search-patterns.md](../01-spec/search-patterns.md).

### US-B10 — Search autocomplete
As the buyer types in the search bar, a dropdown shows hybrid suggestions from three sources: the buyer's own search history, popular searches across all users, and matching category/city names. Suggestions are rate-limited (30 requests per minute per IP). Results are deduplicated and capped at 10. See decision O.

### US-B11 — Saved search alerts
Buyer saves a search query with optional city, category, and price filters. When a new matching ad
is published, the buyer receives a notification delivered via Telegram (near-real-time at publish
time, gated by `IMMEDIATE_ALERTS_ENABLED`; a daily backfill command runs regardless). Each notification
includes the ad title, city, price, an absolute ad link, and an inline `[Turn off alerts]` button
(callback), with a `/start` deep-link fallback for unsubscribe. Notifications are deduplicated per
search-ad pair (`uq_saved_search_ad`) so the same ad does not trigger multiple alerts for the same
saved search. Buyers may also manage subscriptions from the User Cabinet under
`Saved searches`. See decision O and [search-patterns.md](../01-spec/search-patterns.md).

### US-B12 — Search history
The buyer's recent search queries are remembered and surfaced as autocomplete suggestions on return visits. History is deduplicated and capped at 50 entries per user. Anonymous users also receive search history suggestions (session-scoped). See decision O.
