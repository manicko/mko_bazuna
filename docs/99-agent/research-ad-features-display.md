# Research: Displaying Ad Features as Tags/Chips on List Cards and Detail Page

> **Status:** Research complete
> **Confidence:** HIGH (codebase evidence) / MEDIUM (competitor patterns from web search)
> **Date:** 2026-08-23

---

## 1. Current-State Analysis

### 1.1 Storage (Confirmed: ✅ Features ARE Populated)

The `Ad` model (`apps/ads/models.py:133-139`) defines:

```python
features = models.ManyToManyField(
    "lookups.LookupItem",
    through="ads.AdFeature",
    through_fields=("ad", "feature"),
    blank=True,
    related_name="featured_ads",
)
```

**Through model `AdFeature`** (`models.py:602-635`):

| Field         | Type                  | Purpose                              |
|---------------|-----------------------|--------------------------------------|
| `ad`           | FK → `Ad`            | CASCADE, `related_name="ad_features"` |
| `feature`      | FK → `LookupItem`    | PROTECT, limited to `LISTING_FEATURE` group |
| `sort_order`   | `PositiveIntegerField` | Display ordering; `Meta.ordering = ["sort_order"]` |

**Population sources:**

- **Seed generator** (`seed_service.py:114-131`): Step 4b calls `CategoryLookupResolver.get_resolved_features(ad.category)`, samples 1–3 features via a seeded RNG, and calls `ad.features.set(sample)`.
- **Bot ad-creation flow** (`telegram_bot/handlers/ad_create.py:844`): Uses `ad.features.set(feature_ids)` after resolving features via the same `CategoryLookupResolver.get_resolved_features()`.
- **Tests confirm**: `test_seed_populates_features` asserts at least one seeded ad has features; `test_seed_filter_by_feature_returns_results` confirms `?features=<slug>` filtering works end-to-end.

### 1.2 LookupItem Model (Has Visual Fields)

`lookup_items` records carry:

| Field       | Type             | Purpose                                    |
|-------------|------------------|--------------------------------------------|
| `slug`      | `SlugField(unique)` | Machine identifier (e.g. `"new"`, `"delivery"`) |
| `name_i18n`| `JSONField`      | Localized names: `{ru, bs, en}`             |
| `icon`      | `CharField(50)`  | "Emoji or SVG icon name" — empty by default |
| `color`     | `CharField(7)`   | Hex color e.g. `#e74c3c` — empty by default |
| `sort_order`| `PositiveIntegerField` | Display ordering within group     |
| `is_active` | `BooleanField`   | Inactive items are hidden from UI           |

**No features are displayed anywhere** on the ad list cards or detail page:

- **`ad_list.html`** (list card, lines 69-109): renders image → title + trust badge → price → description → location/category/date footer row. **No feature tags.**
- **`detail.html`** (detail page, lines 27-100): renders gallery → title + trust badge → price → description → location/category/published row → contact button. **No feature tags.**

### 1.3 Views — N+1 Risk Confirmed (❌ No Feature Prefetch)

| View                  | File                                      | Current prefetch                          | Features prefetched? |
|-----------------------|-------------------------------------------|-------------------------------------------|----------------------|
| `listings()`          | `apps/ads/views/listings.py:255-258`      | `select_related("category", "city", "user")` + `prefetch_related("user__trust_score")` | **No** |
| `ad_detail()`         | `apps/ads/views/listings.py:64-68`        | `select_related("category", "city", "user")` + `prefetch_related("images", "user__trust_score")` | **No** |
| `search()`            | `apps/search/views/search.py:54`          | `select_related("category", "city", "user")` — **no `prefetch_related` at all** | **No** |
| `favorites_list()`    | `apps/cabinet/views/favorites.py:27-32`   | `select_related("category", "city", "user")` + `prefetch_related("images", "user__trust_score")` | **No** |

**If `ad.features.all()` is accessed in templates without adding the prefetch to these four views, each ad in a 24-item grid triggers a separate `SELECT` — classic N+1.**

### 1.4 Existing Patterns to Follow

- **Localization**: `{{ item|get_lookup_name:LANGUAGE_CODE }}` is already used in `filter_form.html:27,42` and `ad_list.html:40,51` for active filter chips. The `get_lookup_name` template filter delegates to `LookupItem.get_name(locale)` with fallback chain: `locale → ru → slug`.
- **Badge components**: `components/badges/verified_badge.html`, `trusted_badge.html`, `pro_badge.html` use `inline-flex items-center px-2 py-1 text-xs font-medium bg-XXX-100 text-XXX-800 rounded` with SVG icons (not `rounded-full`).
- **Filter chips** (already in `ad_list.html` lines 39, 50): use `inline-flex items-center px-3 py-1 bg-XXX-100 text-XXX-800 rounded-full text-sm`.
- **Trust badge N+1 pattern**: The `test_ad_detail_queries.py` test (lines 1-87) is an N+1 regression guard with `_QUERY_BOUND = 15`. The `render_trust_badge` template tag reads from the prefetched `user__trust_score` to avoid per-ad queries — exactly the pattern features should follow.
- **`--query` count is 15** in the current detail test; adding one prefetch SELECT would push it to 16.
- **Test constraint**: `test_detail_context.py:105-107` asserts `prefetch_related` is called with **exactly** `("images", "user__trust_score")`. This test must be updated if `features` is added.

### 1.5 Tailwind CSS Availability

The project uses **Tailwind CSS v4.3.3** (compiled to `output.css`). Available utilities relevant to this task:
- `line-clamp-2`, `line-clamp-3` (already used in `ad_list.html:91,98`)
- `rounded-full` (filter chips), `rounded` (trust badges), `rounded-lg`, `rounded-md`
- Full color palette: `bg-blue-100/600/700`, `bg-green-100/600/700`, `bg-gray-100/200/300`, `bg-purple-100/600`, `bg-red-100/500/600/700`, etc.
- `text-xs`, `text-sm`, `font-medium`, `font-semibold`, `inline-flex`, `items-center`, `gap-1`, `gap-2`

---

## 2. Best-Practice Findings from Competitor Research

### 2.1 Design-Terminology Clarity (Smart Interface Design Patterns)

| Term    | Interactive? | Purpose                                      |
|---------|-------------|----------------------------------------------|
| **Badge** | No          | Status / numeric updates (e.g. "Draft", "3 new") |
| **Tag / Static tag** | No | Topics/labels/keywords (e.g. "New", "Delivery") |
| **Chip** | Yes        | Action-oriented (filter, remove, select)    |
| **Pill** | Visual style of chip (rounded-full)          |

**Recommendation for Mko Bazuna**: Features are **static tags** — they describe product attributes and are not interactive. They should look like tags/badges, not like clickable chips. This matches the existing `verified_badge`, `trusted_badge`, `pro_badge` components which are static `inline-flex` spans.

### 2.2 List Card: Progressive Disclosure

| Source | Key Insight |
|--------|-------------|
| **LOW/CODE marketplace UX** | *"Listing cards should show image, title, price, rating, and **one key differentiator only**; detailed attributes live on the listing page, not the card."* |
| **igitems** | *"Attribute chips below the title describe what the listing offers... The card shows a **curated subset**. The full attribute set plus the seller's description lives on the product page."* |
| **Avito DesignShots** | Card-grid layout with image, title, price, and attribute tags — compact, scannable. |
| **Stan.Vision UI Card Design** | *"Every card gets one clear primary action; secondary actions should be visually quieter and limited."* Avoid inline links inside cards. |

**Consensus**: On list cards, show **2–4 key feature tags** (the most discriminating ones), truncating the rest. The full set appears on the detail page.

### 2.3 Detail Page: Full Attribute Set

| Source | Key Insight |
|--------|-------------|
| **OLX Product Page Redesign** | *"Low relevance to the ad attributes added by sellers"* was a pain point — solved by moving to **structured description and data** on the detail page. |
| **igitems** | *"The card shows a curated subset. The full attribute set plus the seller's description lives on the product page."* |
| **LOW/CODE** | Detail page hierarchy: photos → price → seller rating → description → CTA button. Attributes should sit **before** the CTA, in the information-dense section. |

### 2.4 Visual Design: Tag/Chip Styling

| Source | Key Insight |
|--------|-------------|
| **Avito Visual Boost** | *"Badges на каждой карточке"* (badges on every card) — compact, visual indicators directly on cards. Uses color-coded badges. |
| **Facebook Marketplace Redesign** | Badges indicate seller reputation; visible on home page (not hidden). |
| **Tag vs. Chip (setproduct.com)** | Chips are interactive (clickable to filter); static attribute display should use non-interactive badge/tag styling. |

**Key design principle**: When the `LookupItem` has a `color` field, use it to tint the tag background (e.g. `bg-red-100 text-red-800` if no custom color, or dynamically compute a light/dark variant). When an `icon` is present (emoji or SVG name), render it as a leading visual element.

### 2.5 Mobile Touch Targets

| Source | Requirement |
|--------|-------------|
| **Smart Interface Design Patterns** | *"Use 48×48px as a minimum touch target size on mobile. Ideally use at least 8px spacing between interactive elements."* |
| **SetProduct** | Hover and active states reinforce the clickable nature of interactive chips. |

Since features are **static** (non-interactive), touch target rules are less critical, but tag height should still be comfortable for mobile scannability (~24–28px tall).

---

## 3. Feasible Approaches (Top 2–3)

### Approach A: Inline Tags in Template Loop (Recommended)

Render features directly in the existing card and detail templates using a `{% for %}` loop over `ad.features.all()`, calling the `get_lookup_name` filter and applying color/icon via inline style or conditional classes.

**Pros:**
- Simplest to implement — no new template tags or partials needed
- Fully server-side rendered (HTMX-compatible, no JS)
- Reuses existing `get_lookup_name:LANGUAGE_CODE` pattern
- `AdFeature.sort_order` is respected by `ad.features.all()` (through model's `Meta.ordering = ["sort_order"]`)
- Can leverage `LookupItem.color` and `LookupItem.icon` fields

**Cons:**
- Color logic must live in the template (conditional class mapping or inline style)
- No shared component — must be duplicated across `ad_list.html` and `detail.html`

### Approach B: Reusable Feature-Tag Partial Component (Recommended)

Create a `components/feature_tag.html` partial (like the existing `components/badges/`) that renders a single feature as a styled tag. Include it via `{% include %}` in both `ad_list.html` and `detail.html`.

**Pros:**
- DRY — single component reused across list card and detail page
- Follows the existing `components/badges/*.html` pattern (file structure, comment header, HTMX-compatible)
- Easy to customize styling in one place
- Clean separation: the partial handles icon, color, name, and truncation logic
- Can accept `max_features` parameter for the list card truncation

**Cons:**
- Slightly more files to create (the partial + optional include tag)
- `{% include %}` has minor overhead (template lookup per call), but negligible for ≤4 tags per card

### Approach C: Template Tag `render_feature_tags` (Acceptable, Less Preferred)

Create a `render_feature_tags` template tag (modeled after `render_trust_badge` in `trust_tags.py`) that renders the full set of tags as an HTML string via `render_to_string`.

**Pros:**
- Encapsulates prefetch-awareness and ordering in Python
- Can return early for empty features
- Follows the `render_trust_badge` pattern already in the codebase

**Cons:**
- Over-engineered for a simple tag list — the data is already prefetched, not computed
- `render_to_string` per call adds overhead in a 24-item grid (24 × N tags)
- The `trust_tags.py` tag exists because it needs to query `SellerTrustScore` (DB access). Features need no DB access if prefetched — a template loop is simpler.
- Harder to test markup precisely (renders as a single HTML blob string)

---

## 4. Recommended Approach: **B (Reusable Partial) with Approach A's Template Loop**

**Rationale:** Approach B provides the best balance of DRY, maintainability, and consistency with the existing `components/badges/` pattern. The partial handles icon + color + name, and the loop lives directly in the templates. This avoids the over-engineering of Approach C while eliminating duplication of Approach A.

### 4.1 Prefetch Strategy

Add `"features"` to `prefetch_related` in **all four views** that render ad cards or the detail page:

| View | Current | Updated |
|------|---------|---------|
| `listings()` | `.prefetch_related("user__trust_score")` | `.prefetch_related("features", "user__trust_score")` |
| `ad_detail()` | `.prefetch_related("images", "user__trust_score")` | `.prefetch_related("images", "features", "user__trust_score")` |
| `search()` | (no prefetch_related) | `.prefetch_related("features")` *(add `user__trust_score` too? — current gap)* |
| `favorites_list()` | `.prefetch_related("images", "user__trust_score")` | `.prefetch_related("images", "features", "user__trust_score")` |

**Ordering:** `AdFeature.Meta.ordering = ["sort_order"]` is applied by Django when accessing `ad.features.all()` (both lazy and prefetched). To be **explicit and future-proof**, use a `Prefetch` object:

```python
from django.db.models import Prefetch

ads = ads.prefetch_related(
    Prefetch(
        "features",
        queryset=LookupItem.objects.order_by("adfeature__sort_order"),
    ),
)
```

However, the existing codebase uses plain string prefetches (`"images"`, `"user__trust_score"`). **For consistency**, use `prefetch_related("features", ...)` (simple string) — the through model's `Meta.ordering` will be respected. If explicit ordering is preferred later, switch to `Prefetch`.

> **Confidence: HIGH** — `ad.features.all()` with a through model that has `Meta.ordering` applies that ordering in both lazy access and `prefetch_related`. This is documented Django behavior.

### 4.2 Component: `components/feature_tag.html`

Create a single-file partial at `src/backend/templates/components/feature_tag.html`:

```django
{% comment %}
Feature Tag Component for Mko Bazuna.

Renders a single ad feature (LookupItem) as a static tag/chip with optional
icon and color from the lookup item. Used on both ad list cards and the detail
page.

Usage:
  {% include "components/feature_tag.html" with feature=f icon=True color=True %}

Variables:
  feature: A LookupItem instance (from ad.features.all())
  show_icon: (bool) render the icon field if non-empty (default True)
  show_color: (bool) apply the color field as bg tint (default True)

Dependencies:
  - localized_content (get_lookup_name filter)
  - Tailwind CSS
{% endcomment %}
{% load localized_content %}

{% with name=feature|get_lookup_name:LANGUAGE_CODE %}
  {% if feature.icon or feature.color %}
    {% if feature.color %}
      <span class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full"
            style="background-color: {{ feature.color }}20; color: {{ feature.color }};">
        {% if feature.icon %}<span>{{ feature.icon }}</span>{% endif %}
        <span>{{ name }}</span>
      </span>
    {% else %}
      <span class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded-full">
        {% if feature.icon %}<span>{{ feature.icon }}</span>{% endif %}
        <span>{{ name }}</span>
      </span>
    {% endif %}
  {% else %}
    <span class="inline-flex items-center px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded-full">
      <span>{{ name }}</span>
    </span>
  {% endif %}
{% endwith %}
```

**Color strategy:** The `LookupItem.color` is a hex code (e.g. `#e74c3c`). In the template, use `style="background-color: {{ feature.color }}20; color: {{ feature.color }};"` where the `20` suffix creates a ~12% opacity tint (alpha hex). This is a simple CSS color mixing trick — no JS or server-side color computation needed. When `color` is empty, fall back to `bg-gray-100 text-gray-700`.

> **Note on accessibility:** If `color` is used, the contrast ratio of the tinted background against the text color may fail WCAG AA. A production implementation should compute a lighter background and darker text variant server-side (e.g. via a `lighten()` utility). For the research phase, the `style` approach is a reasonable MVP.

### 4.3 List Card Insertion Point (`ad_list.html`)

Insert the feature tags **between the description and the footer row** (lines 98-100):

```django
{# After description, before footer row (line 98) #}
{% if ad.features.all %}
  <div class="flex flex-wrap gap-1 mt-2 mb-2">
    {% for f in ad.features.all %}
      {% include "components/feature_tag.html" with feature=f %}
      {% if forloop.first %}{# first #}{% endif %}
    {% endfor %}
  </div>
{% endif %}
```

**Truncation strategy for list cards:** Show a maximum of **3 tags** using `{% if not forloop.first %}` pattern or slice the queryset. Django template slicing works on querysets: `{% for f in ad.features.all|slice:":3" %}`. However, since features are prefetched, a cleaner approach is to limit in the template:

```django
{% for f in ad.features.all|slice:":3" %}
  {% include "components/feature_tag.html" with feature=f %}
{% endfor %}
{% if ad.features.count > 3 %}
  <span class="inline-flex items-center px-2 py-1 text-xs text-gray-500">
    +{{ ad.features.count|add:"-3" }} {% trans "more" %}
  </span>
{% endif %}
```

> Note: `ad.features.count` triggers no additional query if features are prefetched — Django's prefetch cache handles it. If not prefetched, it would hit the DB. **The prefetch in the views is critical.**

### 4.4 Detail Page Insertion Point (`detail.html`)

Insert the full feature list **below the description block** (lines 57-59), **above the location/category/published row**:

```django
{# After description div (line 59), before the metadata border-t row #}
{% if ad.features.all %}
  <div class="mb-6">
    <div class="flex flex-wrap gap-2">
      {% for f in ad.features.all %}
        {% include "components/feature_tag.html" with feature=f %}
      {% endfor %}
    </div>
  </div>
{% endif %}
```

On the detail page, show **all features** (no truncation) since horizontal space is ample.

### 4.5 Test Updates Required

The following existing tests will break and must be updated (per project rule: "If tests conflict with architecture or business logic — fix or remove the tests"):

1. **`test_detail_context.py:105-107`** — asserts `prefetch_related` called with exactly `("images", "user__trust_score")`. Add `"features"` to the expected call:
   ```python
   mock_ad.objects.select_related.return_value.prefetch_related.assert_called_once_with(
       "images", "features", "user__trust_score"
   )
   ```

2. **`test_ad_detail_queries.py:37`** — `_QUERY_BOUND = 15`. Adding one prefetch SELECT pushes the count to 16. Update to `_QUERY_BOUND = 16`.

3. **`test_listings_context.py`** — the mock prefetch chain (`prefetch_related` returns `_EmptyQuerySet`) should still pass since it's a mock, but verify.

4. **New test recommended:** Add a markup test (like `test_gallery_markup.py`) that creates an ad with features and asserts the feature tags render in the detail page and list card HTML.

### 4.6 Progressive Enhancement / No-JS

All rendering is server-side via Django templates. No JavaScript is needed. The `get_lookup_name` filter handles localization entirely on the server. HTMX partial swaps (in `ad_list.html`) will automatically re-render features when navigating/filtering, since the full template fragment is re-rendered server-side.

---

## 5. Summary of Implementation Steps

| # | Step | File(s) | Effort |
|---|------|---------|--------|
| 1 | Add `"features"` to `prefetch_related` | `listings.py:258`, `listings.py:66`, `search.py:54`, `favorites.py:30` | 4 line edits |
| 2 | Create `feature_tag.html` partial | `templates/components/feature_tag.html` | New file |
| 3 | Add feature tags to list card (max 3 + "more") | `templates/ads/partials/ad_list.html` (after line 98) | Insert ~10 lines |
| 4 | Add full feature list to detail page | `templates/ads/detail.html` (after line 59) | Insert ~8 lines |
| 5 | Update test assertions | `test_detail_context.py:105`, `test_ad_detail_queries.py:37` | 2 line edits |
| 6 | (Optional) Add markup test | New `test_feature_tags.py` | New file |
| 7 | (Optional) Add `get_ordered_features()` to `Ad` model | `ads/models.py` | 1 method |

**No migrations required** — the `features` M2M and `AdFeature` through model already exist with `sort_order`. Only views, templates, and tests change.
