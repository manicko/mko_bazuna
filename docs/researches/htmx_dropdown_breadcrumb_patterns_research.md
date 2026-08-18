# Research: HTMX Mega-Dropdown, Breadcrumb & UX Patterns

**Stack:** Django 5.2 LTS · Python 3.14 · django-mptt `>=0.18.0` · HTMX `1.9.12` (pinned CDN) · django-htmx `>=1.19.0` · django-tailwind · PostgreSQL 18

**Created:** 2026-08-18
**Status:** COMPLETE

---

## 1. Mega-Dropdown Category Menu — Three Approaches

### Context

- **Category model** (`apps/categories/models.py`): `MPTTModel` with fields `name`, `name_i18n` (JSONField, fallback `ru`→`name`), `slug`, `is_active`, `parent` (related_name `children`). Tree depth up to 4 levels. `CategoryPath` provides alternative parents (read-only concern for now — breadcrumbs use primary `parent` chain).
- **Listings view** (`apps/ads/views/listings.py`): `listings(request, category_slug=None)` resolves the category and uses `category.get_descendants(include_self=True)` to gather the active subtree.
- **Spec reference** (`docs/01-spec/filter-ui.md`): shows `{% recursetree %}` template tag for rendering the category tree.
- **No base template exists**: `list.html` and `detail.html` each inline their own `<header>`. Shared fragments are `{% include %}` of `components/language_switcher.html` and `components/consent_banner.html`.
- **HTMX version is `1.9.12`** (confirmed from `pyproject.toml` and the CDN `https://unpkg.com/htmx.org@1.9.12`). Important: `hx-on` (event attribute syntax) is a **2.0+** feature and is **NOT available** in 1.9.12. Outside-click and escape handling must use vanilla JS (matching the existing `language_switcher.html` pattern).

---

### Approach A — Pre-rendered Full Tree in Header

Render the entire category tree server-side into the header HTML on every page load using django-mptt's `{% cache_tree_children %}` or `{% recursetree %}`.

**Pros:**
- Instant menu open — no network round-trip.
- Full tree markup in HTML → ideal for SEO/fresh-indexable nav structure.
- Simplest JS — only toggle show/hide (matches existing `language_switcher.html` pattern).
- Works without JS; tree is always in the DOM.

**Cons:**
- Header payload grows with tree size. With ~150–300 categories at 4 levels this adds 8–20 KB of HTML per request.
- No lazy loading — all categories fetched & rendered even if user never opens the menu.
- Cache invalidation: changing `is_active` or tree structure requires fragment cache refresh.

**Feasibility:** HIGH. Direct match to the `filter-ui.md` spec (`{% recursetree %}` usage). django-mptt provides `Category.objects.root_nodes()` and `cache_tree_children()` which build the nested tree in one query (no N+1).

**Template snippet:**
```django
{% load mptt_tags %}
<ul class="mega-menu" data-mega-menu>
  {% cache_tree_children "categories_cache" %}
    {% recursetree nodes %}
      <li class="{% if not node.is_leaf %}has-children{% endif %}">
        <a href="{% url 'listings_category' node.slug %}"
           class="px-3 py-2 block hover:bg-gray-100">
          {{ node.name|default_if_none:node.name_i18n.ru }}
        </a>
        {% if children %}
          <ul class="submenu">
            {{ children }}
          </ul>
        {% endif %}
      </li>
    {% endrecursetree %}
  {% endcache_tree_children %}
</ul>
```

---

### Approach B — HTMX Lazy-Load Subtree on Demand

Header renders only top-level (`Category.objects.root_nodes()`); subcategories are fetched via HTMX when the user hovers/clicks a top-level node. Each submenu is an `<a>` with `hx-get` targeting the server fragment.

**Pros:**
- Minimal initial payload — only top-level (e.g. 12–20 nodes).
- Server renders only the opened branch — optimal for large catalogs.
- Keeps HTML out of DOM until needed.

**Cons:**
- Network latency on first open of each branch (mitigated by `delay:300ms` hover or caching).
- Requires a dedicated endpoint returning just the submenu `<ul>` fragment (no full-page wrapper).
- More complex: must manage per-branch cache (server Redis or client `localStorage`/session) to avoid re-fetching.
- Hover-triggered fetch can cause jank if network is slow.

**Feasibility:** HIGH. Well within HTMX 1.9.12 capabilities. Pattern: `hx-get="{% url 'category_submenu' slug %}"` + `hx-trigger="hover delay:300ms, click"`.

**Endpoint view:**
```python
# apps/categories/views.py (bot-side or web)
def category_submenu(request, category_slug):
    cat = get_object_or_404(Category, slug=category_slug)
    # descendants incl. self → active only, 2 levels for the panel
    children = cat.get_children() if cat.level == 0 else cat.get_descendants(
        include_self=False
    )[:2]
    # render partial fragment
    return render(request, "categories/partials/mega_submenu.html", {"cat": cat, "children": children})
```

**Fragment:**
```django
<ul class="mega-dropdown-panel">
  {% for child in children %}
    <li>
      <a href="{% url 'listings_category' child.slug %}" class="block px-3 py-2 hover:bg-gray-100">
        {{ child.name }}
      </a>
      {% if child.children.exists %}
        {# nested submenu could nest further, or a 2-level cap #}
      {% endif %}
    </li>
  {% endfor %}
</ul>
```

---

### Approach C — CSS-Only Hover (`:hover` / Tailwind)

Pure CSS mega-menu using `group-hover` to reveal submenus. No JS toggle, no HTMX fetch.

**Pros:**
- Zero JS bundle cost.
- No network request; instant.
- Simple markup.

**Cons:**
- **Mobile-incompatible**: hover cannot be relied upon on touch devices. Users must tap, and `:hover` triggers on tap-1 then content on tap-2 — poor UX on mobile.
- Cannot lazy-load — entire tree in DOM (same payload concern as Approach A).
- Accessibility is weaker (keyboard focus management needs extra care, submenu flyout timing is CSS-only).

**Feasibility:** MEDIUM. Works on desktop only. Given Mko Bazuna is a classifieds board accessed by mobile buyers, **mobile tap-to-open behavior is required**. CSS-only hover is not recommended as the sole mechanism.

**Tailwind pattern:**
```html
<div class="relative group" data-nav-item>
  <a href="#" class="px-3 py-2 block">Electronics</a>
  <div class="absolute left-0 mt-2 w-64 hidden group-hover:block bg-white shadow-lg">
    {# submenu content #}
  </div>
</div>
```

---

### Recommendation: Approach B (HTMX Lazy-Load) with Fallback Enhancements

**Rationale:**
- Mko Bazuna's catalog is expected to grow (4-level tree × Avito-style breadth). Approach B keeps header payload small and fetches only what the user explores.
- HTMX 1.9.12 is already pinned and integrated via `{% htmx_script_src %}` — no new dependency.
- The existing `language_switcher.html` establishes a `data-*` + vanilla JS pattern for toggles; HTMX slots into the same architecture cleanly.
- **Mobile concern**: hover does not work on touch. Use `hx-trigger="click"` as the primary trigger for the mega menu toggle on the button element, with an optional `hover delay:300ms` added for desktop enhancement. This matches Avito's mobile-first behavior (tap to open).
- **SEO**: top-level categories in initial HTML (always indexable); subcategories loaded on demand. Acceptable since the site is buyer-browse-driven, not SEO-crawl-driven for deep category pages (those have their own listing URLs).

**Implementation plan:**
1. Context processor returns `root_categories = Category.objects.root_nodes().filter(is_active=True)` so the header include can render top-level always.
2. Header include: `<button data-mega-toggle>` + empty `<div data-mega-panel>` placeholder.
3. Button gets `hx-get="{% url 'category_submenu' top.slug %}"`, `hx-target="closest [data-mega-panel]"`, `hx-trigger="click"` (with `hover delay:300ms` added for desktop via `hx-trigger` compound).
4. Reuse the `language_switcher.html` vanilla JS toggle pattern for `data-mega-toggle` / `data-mega-panel` show/hide + outside-click + Escape, since `hx-on` is unavailable in 1.9.12.
5. Cache submenu HTML fragment server-side (Redis, already configured via django-redis) keyed by category slug + tree version, so repeat opens are instant.

---

## 2. Breadcrumb Generation — Two Approaches

### Approach A — MPTT `get_ancestors()` in View

In the listings view (or a context processor for non-category pages), call `category.get_ancestors(include_self=True)` which returns root→leaf order by default.

**Pros:**
- Single query (MPTT uses `lft`/`rght` indexing). O(1) reads for ancestors.
- Simple, idiomatic MPTT — no recursive template logic.
- Full control over filtering (e.g. `is_active` only) in Python.

**Cons:**
- Requires the category object to be resolved in the view — must add breadcrumb logic to every view that shows the header (currently none have a shared context processor for this; `core/context_processors.py` only provides `plausible_host` + `language`).
- For detail pages (`ad_detail`), must traverse from the ad's category — minor extra code.

**Feasibility:** HIGH. The `listings` view already calls `category.get_descendants(include_self=True)`, so adding `category.get_ancestors(include_self=True)` is trivial and consistent.

**View snippet:**
```python
def listings(request, category_slug=None, city_slug=None):
    category = get_object_or_404(Category, slug=category_slug, is_active=True) if category_slug else None
    ...
    breadcrumbs = []
    if category:
        breadcrumbs = [
            {"label": "Home", "url": "/"},
            *category.get_ancestors(include_self=True).values("name", "slug"),
        ]
    return render(request, "ads/list.html", {..., "breadcrumbs": breadcrumbs})
```

**Template:**
```django
<nav aria-label="Breadcrumb" class="flex items-center space-x-2 text-sm">
  {% for crumb in breadcrumbs %}
    {% if not loop.last %}
      <a href="{% if crumb.url == '/' }}{{ crumb.url }}{% else %}{% url 'listings_category' crumb.slug %}{% endif %}"
         class="text-gray-600 hover:text-gray-900">{{ crumb.label }}</a>
      <span class="text-gray-400">/</span>
    {% else %}
      <span class="text-gray-900 font-medium">{{ crumb.label }}</span>
    {% endif %}
  {% endfor %}
</nav>
```

---

### Approach B — Recursive Template Tag (`{% recursetree %}` or custom)

Render breadcrumbs via a recursive template fragment that walks `category.parent` upward, or uses django-mptt's `{% recursetree %}` over `get_ancestors()`.

**Pros:**
- Keeps breadcrumb markup purely in templates — no view-side boilerplate.
- `{% recursetree %}` is already referenced in the `filter-ui.md` spec, suggesting intent to use it.

**Cons:**
- Harder to filter by `is_active` within the template tag iteration.
- Less control over ordering; custom recursive tag adds maintenance.
- The `filter-ui.md` reference to `{% recursetree %}` is specifically in the **filter sidebar** context (rendering the category tree for filtering), not the breadcrumb. Repurposing it for breadcrumbs conflates two visual patterns.

**Feasibility:** MEDIUM. Works but is less clean than MPTT's built-in ordered ancestor list.

---

### Recommendation: Approach A (`get_ancestors()`) + Context Processor

**Rationale:**
- MPTT already provides `get_ancestors(include_self=True)` in root→leaf order — no recursive template needed.
- Single query, easy to filter.
- The existing `core/context_processors.py` is the correct architectural hook: breadcrumbs appear on the header of **all pages** (Home, listing, detail, search). A shared context processor returning `breadcrumbs` list (empty `[{}]` for non-category pages) keeps every template DRY and removes the need to add logic to each view.
- For the ad detail page, resolve via `ad.category.get_ancestors(include_self=True)`.

**Implementation:**
1. Add `breadcrumbs` to a shared context processor in `apps/core/context_processors.py`.
2. Context processor inspects the request path / URL name (already have `LANGUAGE_CODE` pattern) and builds breadcrumbs:
   - URL name `listings_category` → resolve `category_slug` → `get_ancestors()`.
   - URL name `detail` → resolve ad → `ad.category.get_ancestors()`.
   - URL name `listings` (root) → `[{"label": "All ads", "url": "/"}]`.
3. Header include renders `breadcrumbs` from context.

**Context processor skeleton:**
```python
def breadcrumbs(request):
    from apps.categories.models import Category
    from apps.ads.models import Ad  # resolve import lazily

    crumbs = []
    if request.resolver_match:
        url_name = request.resolver_match.url_name
        if url_name == "listings_category":
            slug = request.resolver_match.kwargs.get("category_slug")
            cat = Category.objects.filter(slug=slug, is_active=True).first()
            if cat:
                crumbs = [{"label": c.name, "url_name": "listings_category", "slug": c.slug}
                          for c in cat.get_ancestors(include_self=True)]
        elif url_name == "detail":
            ad_id = request.resolver_match.kwargs.get("ad_id")
            ad = Ad.objects.filter(id=ad_id, status=AdStatus.PUBLISHED).first()
            if ad:
                crumbs = [{"label": c.name, ...}
                          for c in ad.category.get_ancestors(include_self=True)]
    return {"breadcrumbs": crumbs}
```

---

## 3. HTMX Dropdown — Positioning & UX Best Practices (HTMX 1.9.12)

**Critical constraint:** HTMX is **1.9.12**. `hx-on` (inline event handler attribute) is **not available** (that is 2.0+). All interactive logic must use the established vanilla-JS pattern from `language_switcher.html`: `data-*` attributes + a single toggler script.

### Positioning

- The mega menu panel must be positioned `absolute` relative to the trigger button's parent (`relative`). Use Tailwind: `absolute left-0 mt-2 w-[calc(100vw-2rem)]` (full-width minus header padding, capped at e.g. `max-w-7xl mx-auto`).
- For a multi-column panel (4–5 category groups side-by-side, Avito-style), use CSS Grid: `grid grid-cols-4 gap-4 p-4`.
- Avoid viewport-edge overflow: measure panel width vs. trigger offset; if overflow, flip to `right-0`. Simple heuristic: if trigger is in the right 1/3 of viewport, align panel right.

**CSS (Tailwind):**
```html
<div class="relative" data-nav-item>
  <button type="button" data-mega-toggle class="px-3 py-2 hover:bg-gray-100">
    Electronics
  </button>
  <div data-mega-panel
       class="absolute left-0 mt-2 hidden z-[90] bg-white shadow-xl border border-gray-200
              grid grid-cols-4 gap-4 p-4 min-w-[480px]">
    {# HTMX fills this via hx-target #}
  </div>
</div>
```

### Z-Index

- Header z-index must exceed page content. Use `z-50` on header; dropdown panel `z-[90]` (between header and modals). Avoid `z-index` values over `z-50` globally to prevent layer conflicts with the consent banner (`z-50` from `components/consent_banner.html` if present).

### Click-Outside & Escape (Vanilla JS — HTMX 1.9.12)

Mirror the existing `language_switcher.html` pattern. On document `click` and `keydown` (Escape), close all panels whose `data-mega-panel` is not contained by the clicked target.

```js
document.addEventListener('click', (e) => {
  if (!e.target.closest('[data-mega-toggle], [data-mega-panel]')) {
    document.querySelectorAll('[data-mega-panel]').forEach(p => p.classList.add('hidden'));
  }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('[data-mega-panel]').forEach(p => p.classList.add('hidden'));
  }
});
```

### Keyboard Navigation

- `data-mega-toggle` buttons should toggle via `button` element (native Enter/Space activation).
- Arrow keys between top-level triggers: track the open panel; on `ArrowRight`/`ArrowLeft`, move focus to the next/prev top-level button and toggle its panel.
- Focus management within the panel: keep focus in the first `<a>` of the panel, allowing Tab to leave naturally (no modal trapping needed for a non-modal dropdown).

### Trigger Strategy (HTMX)

- **Primary:** `hx-trigger="click"` — reliable on both mobile and desktop.
- **Enhancement for desktop:** `hx-trigger="click hover delay:300ms"` so hover still opens but a click is required (no accidental hover-on-touch; `delay:300ms` prevents flicker).
- Set `hx-swap="innerHTML"` (default) and `hx-target="closest [data-mega-panel]"`.
- Mark loaded panels with a `data-loaded="true"` attribute server-side so re-opening an already-cached branch doesn't re-fetch — instead the server fragment can include a small inline script or class that just removes `hidden`.

**Trigger attributes on the button:**
```html
<button type="button"
        data-mega-toggle
        hx-get="{% url 'category_submenu' node.slug %}"
        hx-target="closest [data-mega-panel]"
        hx-trigger="click hover delay:300ms"
        hx-swap="innerHTML">
  {{ node.name }} ▼
</button>
```

### Mobile Consideration

- On mobile, `hover delay:300ms` is a no-op (touch doesn't fire hover reliably). The `click` trigger opens/toggles reliably.
- Ensure tap targets are ≥ 44×44 px (`min-h-11 min-w-[44px]`).
- Consider a dedicated mobile "hamburger" category page rather than the mega-menu for submenus — but the lazy-load fragment can be reused there.

---

## 4. Confidence Levels

| Topic | Confidence | Notes |
|---|---|---|
| HTMX `1.9.12` version, `hx-on` absence | **HIGH** | Confirmed via `pyproject.toml`, CDN `htmx.org@1.9.12`, and HTMX changelog (hx-on introduced in 2.0.0). |
| django-mptt `get_ancestors()` / `get_descendants()` | **HIGH** | Verified by reading `apps/categories/models.py` and `listings.py` which calls `get_descendants(include_self=True)`. |
| `cache_tree_children` / `{% recursetree %}` availability | **HIGH** | django-mptt `>=0.18.0` ships `mptt.templatetags.mptt_tags` with `cache_tree_children` and `recursetree`. Confirmed version pin in `pyproject.toml`. |
| `get_ancestors(ascending=True)` ordering | **HIGH** | django-mptt default `ascending=True` yields root-first order. |
| Existing `language_switcher.html` toggle pattern | **HIGH** | Source file read; uses `data-lang-switcher-toggle` / `data-lang-switcher-menu` + vanilla JS (`document.querySelector`). |
| No shared `base.html` | **HIGH** | `list.html` and `detail.html` each inline `<header>`; only `consent_banner.html` and `language_switcher.html` are shared includes. |
| Context processor pattern for breadcrumbs | **HIGH** | `apps/core/context_processors.py` exists and is registered; extending it follows the established pattern. |
| Avito mega-menu reference (single parent, 12 top-level) | **MEDIUM** | From `docs/07-design-researches/Design_02/01-avito-design.md` (design research doc, may reflect competitor snapshot not final spec). |
| Recommended HTMX lazy-load + `click` primary trigger | **HIGH** | Aligns with HTMX 1.9.12 capabilities, pinned version, and mobile-first requirement stated in spec. |
| Redis cache for submenu fragments | **MEDIUM** | django-redis is configured (`CELERY_BROKER_URL` / Django cache framework present); fragment caching approach is standard Django but exact cache-key strategy is an implementation detail left to the implementer. |
