# Multi-Parent Category Research Report

**Date:** 2026-08-01
**Confidence:** HIGH (codebase analysis + documented platform research + Django/PostgreSQL patterns)

---

## Table of Contents

1. [How Classifieds Platforms Handle Multi-Parent Categories](#1-how-classifieds-platforms-handle-multi-parent-categories)
2. [Impact Analysis: Current Codebase Dependencies on MPTT](#2-impact-analysis-current-codebase-dependencies-on-mptt)
3. [Django Approaches for Multi-Parent Polyhierarchy](#3-django-approaches-for-multi-parent-polyhierarchy)
4. [Cross-Cutting Considerations](#4-cross-cutting-considerations)
5. [Recommendation](#5-recommendation)

---

## 1. How Classifieds Platforms Handle Multi-Parent Categories

### 1.1 Summary Finding

**None of the major classifieds platforms (Avito, OLX, Jiji, Facebook Marketplace) use true multi-parent categories (polyhierarchy).** Every platform analyzed uses a strict single-parent tree hierarchy. Cross-listing is achieved through alternative mechanisms — never through a category belonging to multiple parents simultaneously.

### 1.2 Avito

**Source:** `docs/07-design-researches/Design_02/01-avito-design.md` (live CSS analysis, 2026-07-25)

Avito uses a flat list of ~12 top-level categories with subcategories in a strict tree:
- `/fr/maroc/autos_et_vehicules` — a category lives at exactly one URL path
- Breadcrumb navigation: `Home > Category > Subcategory` (single path)
- A bicycle listing lives under **either** "Sport & Loisirs" **or** "Véhicules", not both
- **No evidence** of polyhierarchy or cross-listing in the category system

Avito solves the "dual parent" need via:
- **Search/FTS**: A "bicycle" search finds listings regardless of which category tree the seller chose
- **Keyword-based category suggestion**: The bot suggests 3-5 categories based on ad text, but the seller chooses exactly one

### 1.3 OLX

**Source:** `docs/07-design-researches/Design_02/02-jiji-olx-design.md`

OLX uses a grid-based category system with:
- Dedicated category pages with iconography
- Breadcrumb: single path per category
- Progressive disclosure filters (category → subcategory → attributes)
- **No multi-parent category support**

### 1.4 Facebook Marketplace

**Source:** `docs/07-design-researches/Design_02/03-facebook-marketplace.md`

Facebook Marketplace uses:
- H-scroll category chips on mobile, left sidebar on desktop
- URL structure: `/marketplace/{category}/near/{location}` (single path)
- **Strict one-category-per-listing model** — a listing cannot appear under two category trees
- Cross-discovery is purely via search, not category browsing

### 1.5 Why Classifieds Avoid True Polyhierarchy

| Reason | Explanation |
|---|---|
| **URL ambiguity** | A category with two parents needs two URLs (e.g., `/transport/bicycles` and `/sports/bicycles`), which splits SEO value and creates canonicalization problems |
| **Buyer confusion** | Seeing the same category under two parents in navigation creates cognitive load: "Which one do I click?" |
| **Breadcrumb ambiguity** | "Bicycles > Mountain Bikes" — what breadcrumb path to show if the category has two parents? |
| **Ad placement ambiguity** | An ad in "Bicycles" appears under both "Transport" and "Sports" — is that intended by the seller? |
| **Analytics skew** | Category-level metrics become ambiguous |

### 1.6 What Classifieds Do Instead

The industry-standard solution for "Bicycles should appear under both Transport and Sports" is **not** multi-parent categories — it is one of:

1. **Search/FTS as discovery**: The buyer searches "bicycle" and finds it regardless of category
2. **Featured/Carousel cross-promotion**: "Also available in" sections on category pages
3. **Synonym/Alias routing**: The URL `/sports/bicycles` redirects or is an alias for the canonical `/transport/bicycles`
4. **Tagging**: Items tagged with "bicycle" appear in multiple browsing contexts through flat tag associations

**Confidence: HIGH** — Based on live platform analysis, design docs, and consistent pattern across 4 major platforms.

---

## 2. Impact Analysis: Current Codebase Dependencies on MPTT

Before evaluating approaches, the MPTT dependency footprint must be understood. Every approach will need to replace or supplement these.

### 2.1 Direct MPTT API Usage

| Location | Usage | Line |
|---|---|---|
| `categories/models.py` | `MPTTModel`, `TreeForeignKey('self')` | 12, 36 |
| `categories/admin.py` | `MPTTModelAdmin` | 9, 13 |
| `ads/views/listings.py` | `category.get_descendants(include_self=True)` | 227 |
| `search/views/search.py` | `category_filter.get_descendants(include_self=True)` | 62 |
| `search/services/alert_query.py` | `Category.objects.get(pk=category.pk).get_descendants(include_self=True)` | 73 |
| `categories/migrations/0001_initial.py` | MPTT fields: `lft`, `rght`, `tree_id`, `level` | 22-25 |
| `categories/migrations/0002_seed_categories.py` | Raw SQL with `lft`, `rght`, `tree_id`, `level` for tree insertion | entire file |

### 2.2 Indirect Dependencies

| Artifact | How it depends on single-parent tree |
|---|---|
| `ads.category` (FK) | Single category per ad. With polyhierarchy, an ad could theoretically have multiple categories, but the current schema is `ForeignKey` |
| `ads.category_name` (denormalized) | Trigger copies `categories.name` — assumes one canonical name |
| `search_vector` (trigger-maintained) | Includes `category_name` at weight C — a polyhierarchy would need to decide which category name(s) go in the vector |
| `IX_ads_pub_listing` index | Includes `category_id` — composite index for published ad listing |
| `SavedSearch.category_id` | FK to categories — saved searches filter by category |
| Seed fixtures (`fixtures/categories.json`) | MPTT tree with `lft`/`rght`/`tree_id`/`level` |
| Bot code (`ad_create.py`) | `Category.objects.get(id=category_id)` — single FK |

---

## 3. Django Approaches for Multi-Parent Polyhierarchy

### 3.1 Approach A: M2M to Self (DAG Pattern)

**Replace `parent = TreeForeignKey('self')` with `parents = ManyToManyField('self', symmetrical=False, blank=True)`**

#### Model Structure
```python
class Category(models.Model):  # No longer MPTTModel
    name = models.CharField(...)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(...)
    parents = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="children",
    )
```

#### Implementation Complexity: **HIGH**

| Aspect | Detail |
|---|---|
| **Ancestry queries** | No built-in `get_ancestors()` / `get_descendants()`. Must implement recursive queries (CTE) or materialized caches |
| **Admin UI** | Loses `MPTTModelAdmin` tree rendering. M2M widget is a multi-select — no tree visualization |
| **Cycle detection** | Must guard against cycles in application code (e.g., `validate_parents()` on save) |
| **Query performance** | Subtree queries require recursive CTEs (`WITH RECURSIVE`) or multiple queries. Slow for deep trees |
| **Slug uniqueness** | Already unique — no change needed. But URLs become ambiguous (which path to use?) |

#### Query Examples (Recursive CTE)
```sql
-- Get all descendants of category id=5
WITH RECURSIVE descendants AS (
    SELECT id FROM categories WHERE id = 5
    UNION ALL
    SELECT c.id FROM categories c
    JOIN descendants d ON c.id IN (
        SELECT category_id FROM categories_parents WHERE parent_id = d.id
    )
)
SELECT * FROM descendants;
```

#### Evaluation

| Criterion | Rating |
|---|---|
| Implementation complexity | HIGH |
| Query performance (breadcrumbs) | LOW (recursive CTE per query) |
| Query performance (subtree listing) | LOW (recursive CTE per query) |
| Query performance (root-level nav) | MEDIUM (`parents=None` equivalent needs `~exists` subquery) |
| Admin UI impact | SEVERE — loses tree UI entirely |
| Migration complexity | HIGH — data migration to populate M2M from existing parent FK |
| Compatibility with existing code | LOW — breaks every `get_descendants()` / `get_ancestors()` call |

**Verdict: Not recommended.** The loss of the MPTT admin tree and the need to reimplement tree operations manually makes this a poor trade-off. No closed-source Django library exists for this pattern.

---

### 3.2 Approach B: Keep MPTT + Add CategoryPath/CategoryAlias Model

**Keep the existing MPTT `Category` model untouched. Add a separate `CategoryPath` model for alternative navigation routes.**

#### Model Structure
```python
class Category(MPTTModel):
    # Existing model UNCHANGED
    name = ...
    slug = ...
    parent = TreeForeignKey("self", ...)  # CANONICAL single parent
    is_active = ...


class CategoryPath(models.Model):
    """Alternative navigation paths for multi-parent browsing."""

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="alt_paths",
    )
    parent = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="alt_children",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]
        unique_together = ["category", "parent"]
```

#### Semantics
- **Primary parent** (`Category.parent`): The canonical tree location. Used for breadcrumbs, the default URL slug path, and the single source for the denormalized `ads.category_name`.
- **Alternative paths** (`CategoryPath`): Additional browsing routes. "Bicycles" still has `parent=Transport` (canonical), but gets a `CategoryPath` entry with `parent=Sports & Hobbies`.
- **Navigation rendering**: The category tree renders showing both the canonical children (via MPTT) AND alternative children (via `CategoryPath`).

#### Implementation Complexity: **MEDIUM**

| Aspect | Detail |
|---|---|
| **Admin UI** | Keep `MPTTModelAdmin` for primary tree. Add TabularInline for `CategoryPath`. No third-party admin changes needed |
| **Navigation queries** | Union the MPTT children with CategoryPath entries for tree rendering |
| **Subtree queries** | For "all ads in this category or its children", need to UNION both primary descendants (MPTT) and alternative descendants (CategoryPath chain). This is the trickiest part |
| **URL structure** | Primary path uses existing slug logic. Alternative paths get their own URL pattern: `/sports/bicycles/` via a route that first checks CategoryPath, then falls back to MPTT |
| **Get descendants** | `get_descendants()` currently returns MPTT descendants. For polyhierarchy browsing, need a helper that also walks CategoryPath |

#### Evaluation

| Criterion | Rating |
|---|---|
| Implementation complexity | MEDIUM |
| Query performance (breadcrumbs) | HIGH (primary: MPTT `get_ancestors()`, alt: join through CategoryPath) |
| Query performance (subtree listing) | MEDIUM (requires UNION of MPTT subtree + CategoryPath walk) |
| Query performance (root-level nav) | HIGH (MPTT roots unchanged; CategoryPath roots join for alt entries) |
| Admin UI impact | LOW (inline added; primary tree preserved) |
| Migration complexity | LOW (existing Category table unchanged; new table added) |
| Compatibility with existing code | HIGH (`category.parent`, `get_ancestors()`, `get_descendants()` all continue to work for the canonical tree) |

#### Key Challenge
The biggest engineering challenge is the **subtree expansion** in listings and search. Currently:
```python
descendant_ids = category.get_descendants(include_self=True).values_list(
    "id", flat=True
)
ads = ads.filter(category_id__in=descendant_ids)
```

With Approach B, this must become:
```python
# MPTT descendants (existing behavior)
primary_ids = list(
    category.get_descendants(include_self=True).values_list("id", flat=True)
)
# Alternative paths (walk CategoryPath recursively or use a helper)
alt_ids = _get_alt_subtree_ids(category)
all_ids = primary_ids + alt_ids
ads = ads.filter(category_id__in=all_ids)
```

This is manageable but adds complexity to every query that previously used `get_descendants()`.

---

### 3.3 Approach C: Closure Table

**Replace MPTT entirely with a closure table (ancestor/descendant pairs with depth).**

#### Model Structure
```python
class Category(models.Model):  # No longer MPTTModel
    name = models.CharField(...)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(...)


class CategoryClosure(models.Model):
    ancestor = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="+")
    descendant = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="+")
    depth = models.PositiveIntegerField()

    class Meta:
        unique_together = ["ancestor", "descendant"]
        indexes = [
            models.Index(fields=["descendant"]),  # For ancestor lookups
            models.Index(fields=["ancestor"]),  # For descendant lookups
        ]
```

A closure table row `(ancestor=A, descendant=D, depth=N)` means "A is an N-level ancestor of D". With M2M parents:
- Root categories have no parent but still appear in closure as `(self, self, 0)`
- "Bicycles" under both "Transport" and "Sports" = closure rows for both lineages

#### Implementation Complexity: **HIGH**

| Aspect | Detail |
|---|---|
| **Ancestry queries** | `SELECT ancestor FROM closure WHERE descendant=X ORDER BY depth` — simple and fast |
| **Descendant queries** | `SELECT descendant FROM closure WHERE ancestor=X` — simple and fast |
| **Insert/delete operations** | Must maintain closure table integrity. On insert, need to insert closure rows for ALL ancestors in ALL lineages. On delete, need to clean up all closure rows for the deleted node |
| **Django packages** | No mature, maintained Django closure table package. `django-closure-tree` exists but is unmaintained (last update ~2015). Would need custom implementation |
| **Admin UI** | Loses MPTT admin. Need custom Tree admin or django-js-tree |

#### Evaluation

| Criterion | Rating |
|---|---|
| Implementation complexity | HIGH (need custom admin widget, custom tree maintenance code) |
| Query performance (breadcrumbs) | HIGH (single SELECT on indexed closure table) |
| Query performance (subtree listing) | HIGH (single SELECT on indexed closure table) |
| Query performance (root-level nav) | HIGH (SELECT ancestor=NULL or depth=0 rows) |
| Admin UI impact | SEVERE — no existing admin widget for closure table trees |
| Migration complexity | HIGH — must generate closure rows for all existing MPTT nodes, then replace all `get_descendants()` calls |
| Compatibility with existing code | LOW — requires rewriting all tree operations |

**Closure tables are the architecturally pure solution for polyhierarchy.** They handle it natively and perform well. The problem is the **absence of a maintained Django library** and the **complete loss of MPTT admin UI**. Building this from scratch for a single use case (category navigation) is disproportionate unless the polyhierarchy is very deep and traversal-heavy.

---

### 3.4 Approach D: Materialized Path + M2M Hybrid

**Keep `parent = M2M('self')` for the parent relationship, but store a materialized path string for fast ancestry/descendant lookups.**

#### Model Structure
```python
class Category(models.Model):
    name = models.CharField(...)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(...)
    parents = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="children",
    )
    # Materialized path: a string encoding all ancestor lineages
    # e.g., "/1/5/" for category 5 with ancestor chain 1→5
    # For multi-parent: "/1/5/ &3/7/" where & separates lineages
    path = models.CharField(max_length=500, db_index=True, editable=False)
```

#### How Materialized Path Works for Multi-Parent
- Single parent: `path = "/1/5/"` (category 1 is parent of 5)
- Two parents: `path = "/1/5/&/3/7/"` (category 5 is under both 1 and 7)
- Ancestry query: `path LIKE "%/5/%"` — finds all descendants of category 5
- Breadcrumbs: Split path by `/` and look up IDs

#### Evaluation

| Criterion | Rating |
|---|---|
| Implementation complexity | HIGH (path maintenance on every create/move/delete; multi-parent path encoding is non-trivial) |
| Query performance (breadcrumbs) | MEDIUM (split path string then N queries or single prefetch) |
| Query performance (subtree listing) | MEDIUM (`LIKE` queries on indexed char field — decent but not GIN-level) |
| Query performance (root-level nav) | LOW (need to find categories without parents — M2M makes this expensive) |
| Admin UI impact | SEVERE — same M2M widget issue as Approach A |
| Migration complexity | HIGH — compute paths for all existing nodes |
| Compatibility with existing code | LOW |

**Verdict: Not recommended.** Materialized paths are fragile with multi-parent, have no Django admin support, and the `LIKE "%/5/%"` pattern doesn't scale well. This approach was popular in the MongoDB era but is inferior to closure tables or MPTT + aliases for this use case.

---

### 3.5 Comparison Matrix

| Criterion | A: M2M DAG | B: MPTT + Path | C: Closure | D: Mat Path |
|---|---|---|---|---|
| **Total complexity** | HIGH | MEDIUM | HIGH | HIGH |
| **Admin UI quality** | POOR | GOOD | POOR | POOR |
| **Ancestor query perf** | LOW (CTE) | HIGH (MPTT) | HIGH (indexed) | MEDIUM |
| **Descendant query perf** | LOW (CTE) | HIGH (MPTT) | HIGH (indexed) | MEDIUM |
| **Move category cost** | LOW | MEDIUM (MPTT rebuild) | HIGH (closure rebuild) | HIGH (path rebuild) |
| **Cycle safety** | MANUAL | BUILT-IN (MPTT) | MANUAL | MANUAL |
| **Migration from MPTT** | HIGH | LOW | HIGH | HIGH |
| **Existing code compat** | LOW | HIGH | LOW | LOW |
| **Polyhierarchy support** | NATIVE | SUPPLEMENTAL | NATIVE | NATIVE |
| **Django ecosystem support** | Native M2M only | MPTT maintained | None | None |

---

## 4. Cross-Cutting Considerations

### 4.1 URL Structure

**Current:** `/category/<slug>/` (one path per category).

**With multi-parent, each category has multiple valid paths:**
- `/transport/bicycles/` — canonical
- `/sports/bicycles/` — alternative

**Recommendations:**

| Decision | Rationale |
|---|---|
| **Canonical URL** | Choose one parent as canonical (the primary MPTT parent in Approach B). Set `<link rel="canonical">` on alternative-path pages |
| **URL pattern** | Keep the existing `/category/<slug>/` pattern regardless of path. The breadcrumb context (not the URL structure) conveys which parent tree the user is in |
| **Slug uniqueness** | Already enforced via `unique=True`. A category has exactly one slug, so `/transport/bicycles` and `/sports/bicycles` both resolve to the same page — the difference is the navigation context |
| **HTMX fragment** | Alternative-path views should render the breadcrumb differently (showing the alternative parent chain) but the same ad grid |

### 4.2 Admin UI

| Approach | Admin Impact |
|---|---|
| **A (M2M DAG)** | Loses `MPTTModelAdmin` — no drag-drop tree, no indented list. Replaced by flat list with M2M multi-select widget. This is a significant operational regression for category management |
| **B (MPTT + Path)** | Keep `MPTTModelAdmin` for the canonical tree. Add `TabularInline` for `CategoryPath` — simple, effective, no third-party dep. Admin can manage alternative paths inline on the category edit page |
| **C (Closure)** | Same as A — no suitable admin widget. Would need a custom Django admin tree or use `django-mptt-admin`-style JavaScript tree with manual closure management |
| **D (Mat Path)** | Same as A |

**Recommendation for Admin:** Approach B is the clear winner. The admin needs a tree visualization to manage categories efficiently. Losing it (A, C, D) creates operational friction that grows with the category tree depth.

### 4.3 Search Indexing

**Current:** `ads.search_vector` includes `category_name` (denormalized Russian name from the canonical category). The search trigger reads `categories.name WHERE id = NEW.category_id`.

**With multi-parent:**
- The ad still has exactly one category (FK to Category)
- `category_name` remains denormalized from the canonical category
- **The search_vector does not need to change** — search is over the ad's category, not over the alternative browsing paths
- Alternative paths are navigation-only, not search semantics

**Implication:** No change needed to the search trigger, `search_vector`, GIN index, or `category_name` propagation.

### 4.4 Ad-to-Category Relationship

**Current:** `Ad.category = ForeignKey(Category, on_delete=PROTECT)`. Single category per ad.

**Should this stay a FK or become M2M?**

**Analysis:**
- **Industry standard:** Every classifieds platform surveyed uses one category per listing. The seller chooses exactly one category during ad creation.
- **Seller UX:** The bot already forces a single category choice (from top 3-5 suggestions + full tree). Forcing a seller to pick multiple categories adds friction.
- **Analytics:** One category = clean attribution for category-level metrics.
- **Complexity:** M2M ads-to-categories would require changes to the trigger (multi-valued `category_name`), the search vector, the composite index, the bot dialog, and all listing views.

**Recommendation: Keep `ForeignKey`.** The ad stays in one canonical category. Multi-parent navigation only affects where the category appears in the browse tree, not how ads are attached to it.

### 4.5 Migration Path for Existing Data

**Current data:** 30 seed categories in a single MPTT tree (3 root nodes, each with 4-5 children). No production data yet since the project is in development.

**Migration steps for Approach B (recommended):**
1. Create the `CategoryPath` model and migration
2. Add `CategoryPath` inline to existing `CategoryAdmin`
3. Optionally seed `CategoryPath` entries for existing categories that should appear under multiple parents
4. Modify the three `get_descendants()` call sites to optionally include alternative paths
5. Update navigation rendering to include alternative paths
6. No changes to `Ad`, `Category`, or any existing data — **zero-downtime migration**

---

## 5. Recommendation

### 5.1 Preferred Approach: **B — Keep MPTT + CategoryPath Model**

**Rationale:**

1. **Lowest migration risk.** The existing MPTT model, admin, seed data, and all tree operations remain unchanged. No data migration needed.

2. **Preserves admin UX.** The `MPTTModelAdmin` tree visualization is essential for efficient category management by the admin team. Losing it (Approaches A, C, D) is a significant operational cost.

3. **No external dependencies.** MPTT is already in the project and is maintained. No unmaintained closure-table packages needed.

4. **Compatible with existing code.** All current `category.parent`, `category.get_ancestors()`, `category.get_descendants()` calls continue to work for the canonical tree. The `CategoryPath` model adds supplemental navigation without breaking anything.

5. **Matches classifieds industry pattern.** No major classifieds platform implements true polyhierarchy. Alternative browsing paths (what Approach B provides) are how the industry solves "Bicycles should appear under both Transport and Sports."

6. **Search and ads unchanged.** The ad-to-category FK, the search trigger, the `category_name` denormalization — none of these need to change.

### 5.2 Implementation Plan (Ordered)

| Step | Effort | Description |
|---|---|---|
| 1. Create `CategoryPath` model | 1 day | Model with FK to category + FK to parent + sort_order |
| 2. Add admin inline | 0.5 day | TabularInline on CategoryAdmin for managing alt paths |
| 3. Update navigation queries | 2 days | Modify tree rendering to UNION MPTT children + CategoryPath entries |
| 4. Update `get_descendants()` call sites | 1 day | Modify 3 locations (listings, search, alert_query) to include alt path descendants |
| 5. URL routing | 1 day | Canonical URL stays the same. Alternative paths render with different breadcrumb context |
| 6. Seed alternative paths | 0.5 day | Add CategoryPath entries for categories that should appear in multiple trees |
| 7. Testing | 1 day | Test listings/search/navigation with both primary and alternative paths |

**Total effort:** 6-7 days.

### 5.3 Alternative Worth Considering: Approach C (Closure Table)

If the project foresees **very deep polyhierarchy** (categories with 3+ parents, or categories that frequently change parents), the closure table is architecturally superior. However:

- The project currently has **max 2 levels of depth** (root → child)
- The seed data has **30 categories** — not a scale where MPTT limitations matter
- No maintained Django closure table library exists
- The admin UI cost is severe

**Recommendation:** Do NOT choose Closure Table unless polyhierarchy depth regularly exceeds 3+ levels.

### 5.4 Potential Concerns with Approach B

| Concern | Mitigation |
|---|---|
| Navigation rendering needs to UNION two sources | A helper method `get_browsable_children()` on Category that combines MPTT children + CategoryPath entries |
| Descendant expansion query needs alt paths | Create a `get_all_descendants()` method that walks both MPTT and CategoryPath, caching results for the request |
| Admin inline could lead to orphaned CategoryPath entries | Use CASCADE on both FKs |
| CategoryPath depth limited (no recursion) | For current 2-level tree, CategoryPath entries are direct parent pointers only. No recursive walking needed |

---

## 6. Summary

| Question | Answer |
|---|---|
| Do Avito/OLX/Jiji use true polyhierarchy? | **No** — all use strict single-parent trees |
| How do they solve cross-listing? | **Search/FTS** and **alias routing**, not multi-parent categories |
| Recommended Django approach | **Approach B**: Keep MPTT + CategoryPath model |
| Second choice | **Approach C**: Closure table (only if deep polyhierarchy is needed) |
| Ad-to-category relationship | **Keep ForeignKey** — one category per ad |
| URL structure | **Keep `/category/<slug>/`** — canonical URL same; alternative paths render different breadcrumbs |
| Search indexing | **No changes needed** — search is over the ad's canonical category |
| Migration complexity | **LOW** — new table only, no data migration |
| Admin UI impact | **None for primary tree** — add inline for alternative paths |