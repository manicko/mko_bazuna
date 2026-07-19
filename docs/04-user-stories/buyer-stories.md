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
  - db-schema
---

## Purpose

Buyer-role user stories. Buyers browse, search, and filter the website **without registration**.
Domain rules referenced as "decision X" live in
[technical-specification.md](../01-spec/technical-specification.md).

## Stories

### US-B1 — Browse without registration
Anyone browses ads with status `PUBLISHED`; no login required.

### US-B2 — Search
Keyword search over title + description (`PUBLISHED` only), response ≤2s. Sort by date (newest
first) or price. A Bosnian query is translated to Russian before FTS (results optionally tagged
"translated from Russian"). Friendly empty state on no results. See decision G.

### US-B3 — Filter
Filter by category/subcategory, city, and price range; filters combinable with no full page
reload (HTMX). Exact city match + "did you mean" on typos. See decision G.

### US-B4 — Ad card
Card shows full ad details and a "Contact seller" button only — **no seller identity** shown. See
decision C.

### US-B5 — Contact seller
Contact via deep-link to our bot (`t.me/<bot_username>?start=contact_<ad_id>`); the bot relays
without revealing seller PII. No login required. Button renders only when the ad is `PUBLISHED`,
seller `telegram_id` is set, and the seller is not deleted/banned/withdrawn. See decision C / zone R2.

### US-B6 — Browse by category
Browse ads by category with hierarchy support (django-mptt subtree).

### US-B7 — Browse by city
Browse by city; exact match against the closed preset list; "did you mean" on typos; selected city
saved in session. See decision D.

### US-B8 — Responsive UI
Responsive layout across mobile, tablet, and desktop.

### US-B9 — Multilingual UI
UI language switch (Russian / Bosnian-latin), persisted across sessions. Switch translates the site
shell only; ad content is stored in Russian and translated on display. See decision G.
