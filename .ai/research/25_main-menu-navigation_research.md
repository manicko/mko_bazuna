---
id: main-menu-navigation-research
title: "Hierarchical Menu Navigation — UX Research"
topic: "expand/collapse icons, touch targets, responsive tree menus, platform examples"
domain: spec
tags: [ux, navigation, menu, accessibility, wcag, figma-ready]
status: draft
confidence: HIGH
last_updated: 2026-08-21
---

# Hierarchical Menu Navigation — UX Research

Research on hierarchical (tree) menu navigation best practices, grounded in WCAG 2.2, W3C WAI-ARIA Authoring Practices, and NN/g studies, with a codebase audit of `header_catalog.html` / `mega_submenu.html` and concrete implementation approaches.

## 1. Objective

Decide the correct expand/collapse affordance, touch-target sizing, responsive behavior, and interaction model for the Mko Bazuna classifieds "All Categories" menu — a multi-level category tree served to both desktop (hover/click) and mobile (off-canvas) users. The goal is a single, accessible, consistent pattern that works across HTMX-driven MPA flows.

---

## 2. Codebase Context (What We Have)

The shared catalog header lives in `src/backend/templates/components/header_catalog.html` (included by `ads/list.html` and `ads/detail.html`). It renders an **"All Categories" dropdown (desktop)** and a **mobile off-canvas slide-over panel**, both powered by:

- Server-rendered root `root_categories` from `apps.core.context_processors.header_context`.
- Lazy-loaded child submenus via `GET /categories/<slug>/submenu/` returning the partial `src/backend/templates/categories/partials/mega_submenu.html`, injected with vanilla JS (`container.innerHTML = html`).
- Vanilla-JS accordion logic in `header_catalog.html`: `loadSubmenu`, `closeBranch`, `collapseSiblings`, `attachCategoryHandlers` (single-open branch, collapse-on-outside-click / Escape).

### 2.1 Expand/collapse affordance (current)

`mega_submenu.html` and `header_catalog.html` both render branch nodes with a **right-pointing chevron**:

```html
<button type="button"
        class="px-2 py-2 text-gray-400 hover:text-blue-600"
        aria-expanded="false"
        data-category-expand="{{ child.slug }}"
        aria-label="{% trans "Expand" %} {{ child.get_name }}">
  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M9 5l7 7-7 7"></path>
  </svg>
</button>
<div class="hidden ml-4" data-category-submenu="{{ child.slug }}"></div>
```

The SVG path `M9 5 l7 7 -7 7` draws a **right-pointing triangle (▶)**.

### 2.2 State handling (current)

- `aria-expanded` is toggled by `loadSubmenu` / `closeBranch` in `header_catalog.html`.
- **No visual state change** — the chevron never rotates or changes direction on expand; openness is signalled only by `aria-expanded` and by the submenu appearing. (Spec note: the current chevron already points "down/right"; there is no rotation transform in the JS.)
- Expand buttons render only when `cat.get_children.exists` (verified by `test_submenu.py::TestExpandButtons`).

### 2.3 Touch targets (current, Tailwind 16px root)

| Element | Classes | Computed size | Verdict |
|---|---|---|---|
| Chevron expand button | `px-2 py-2` + `w-4 h-4` icon | 0.5rem+1rem+0.5rem = **32×32px** | < WCAG 2.5.8 AA passes (24px) but **violates project's own 44px standard** (`docs/01-spec/ui-patterns.md` §Touch Target Guidelines requires 44px minimum) and Apple HIG (44pt) / Material (48dp). |
| Hamburger toggle | `p-2 -ml-2` + `w-6 h-6` icon | 0.5rem+1.5rem+0.5rem = **32×32px** | Same violation as above. |
| City / category links | `px-4 py-2.5` | ≥40px tall | Marginal; `min-h-[44px]` used elsewhere. |

`ui-patterns.md` explicitly states: *"Mobile-first responsive: ... touch targets minimum 44px"* and the **Touch Target Guidelines** table sets **44px** as the floor for buttons, form inputs, and links. The consent-banner row is flagged "needs review" at 36px — but the 32px chevron button is currently below even that noted bar and unflagged.

### 2.4 Interaction model (current)

The category row uses a **split-action** pattern: the label `<a>` navigates to the category page, while an adjacent chevron button expands the submenu. This is the exact anti-pattern flagged by Smashing Magazine (Tivoli example): two different actions share a row, causing mis-taps.

### 2.5 Tests referencing this UI

- `test_submenu.py` — endpoint contract (200/404, inactive exclusion, fragment-cache invalidation) and `TestExpandButtons` (expand button present for categories with children, absent for leaf).
- `test_autocomplete_template.py::TestCatalogMenuAccordionTemplate` — **template-source assertions only** (no DB):
  - submenu container carries `class="hidden ml-4" data-category-submenu="…"`
  - `function closeBranch(` and `function collapseSiblings(` present
  - `collapseBranches` removed
  - `cat.get_children.exists` used (not `get_children_count`)
  - `firstof` replaced with `{% with %}`
  - breadcrumb uses `slice:"::-1"|first` (not `get_ancestors|last`)

---

## 3. Findings — Authority Sources

Confidence: **HIGH** for WCAG/WAI-ARIA/NN-g; **MEDIUM** for Avito-specific (observed via design-system references; live site not scraped).

### 3.1 Expand/collapse icon patterns (plus vs chevron vs caret)

**NN/g — "Accordion Icons: Which Signifiers Work Best?" (Laubheimer & Budiu, 2020)** — the single most authoritative empirical study on this question:

- Icons tested: downward-facing **caret**, **plus**, right-facing **arrow**, a nonsense **foil** control, and **no icon**.
- **Key result:** The **caret (chevron) is the safest icon choice** for accordions that expand in place.
- The caret and plus are both **significantly better** than the foil/no-icon at signalling "stay on page" (p<0.05).
- **The right-facing arrow is NOT statistically different** from the foil or no-icon — *"this icon should not be used for accordions"* (those that open in place). Designers wrongly assume a right-arrow implies navigation vs. in-place expansion; the data does not support that distinction.
- After expansion: caret typically **twists** (rotates), plus turns into minus. Rotation is the recommended visual state cue.
- **Do NOT** make the icon and the text label perform different actions (no split buttons). The entire header should expand/collapse.

**UX Stack Exchange (consensus, corroborated by Deque University)** on the classic tree convention:

- Tree/expander convention (Windows pre-Vista → macOS): **right-pointing (closed) → down-pointing (open)** chevron, with the icon on the **left** of the label.
- **Plus/minus** is the older pre-Vista tree convention; works but is slower to scan and risks confusion with "add/remove" actions.
- A **toggle button** whose appearance (raised vs. pressed) encodes state is another robust option.

**Queensland Government Design System** rationale (mirrors NN/g): prefers **up/down chevron** over plus/minus because *"Plus and minus icons can better describe different functionality (e.g. adding a dependent child)."* Arrows are "more closely aligned to navigation."

**UX Planet — "Designing Perfect Accordion"** (10 best practices):

- Arrow/chevron (down=closed → up=expanded) is the most recognised.
- Place the icon **after** the title (right side) — aligns with F-pattern reading.
- Make **both the title and the icon** clickable (single action).
- Icon should be **≥44×44px** for comfortable tapping.

**W3C WAI-ARIA Practices — Disclosure & Tree View patterns:**

- Disclosure: button with `aria-expanded` (false→true), `aria-controls` linking to the shown/hidden content; **Space or Enter** toggles; chevron rotates to communicate state.
- Tree View: uses `role="tree"`, `role="treeitem"`, `aria-expanded`, `aria-owns` to the `role="group"` subtree; keyboard: **Right** expands closed / moves to first child of open node; **Left** collapses open / moves to parent; **Up/Down** move between nodes; **Enter** selects.

**Verdict on + vs chevron:** The **caret (chevron)** wins on recognisability and on NN/g's empirical "stay-on-page" signal. But two caveats for *this* product:

1. The current icon is a **right-pointing** chevron — exactly what NN/g says **not** to use for in-place expansion.
2. Chevrons only signal state well when they **rotate**; a static chevron communicates nothing on its own.

So the choice is not "plus vs chevron" in the abstract — it is "which chevron orientation, and does it rotate." **Plus/minus** is a defensible fallback (especially in mobile drawer views where space is tight and the symbols read as open/closed unambiguously), but chevron is the lower-friction default for recognisability.

### 3.2 Touch target sizing (WCAG + platforms)

**WCAG 2.2 (authoritative):**

- **SC 2.5.8 Target Size (Minimum) — Level AA:** interactive targets ≥ **24×24 CSS px**, with a spacing exception (a 24px-diameter circle centred on the bounding box must not intersect another target).
- **SC 2.5.5 Target Size (Enhanced) — Level AAA:** **44×44 CSS px**.
- Inline links within text and native user-agent controls are exempt; everything else counts.

**Platform baselines:**

| Platform | Recommendation |
|---|---|
| Apple HIG | **44×44 pt** minimum |
| Google Material Design | **48×48 dp** recommended |
| Web (WCAG 2.5.8 AA) | 24×24 px minimum |
| Web (WCAG 2.5.5 AAA / de-facto) | **44×44 px** recommended |

**The 44px rule** (codexical/Heurilens, 2026): derived from average finger-width data — fine for the median user, but users over 60 show **30–50% higher error rates** on standard targets; motor/cognitive impairments compound this. The EU EAA (enforceable June 2025) increasingly treats 2.2 AA as the bar. **The relationship between adjacent targets matters as much as individual size** — a spacing exception exists in 2.5.8 precisely for this reason.

**Implementation guidance (AllAccessible / Smart Interface Design Patterns):**

- Set `min-width: 44px; min-height: 44px` globally on interactive elements as a floor.
- For icon-only buttons, add padding around the 16–24px icon so the *hit area* is ≥44px while the *visual* icon stays small. Use `box-sizing: border-box`.
- On mobile, bump everything to 44×44 (Apple HIG); on desktop with mouse, 24×24 is the legal floor but 32–40px is common.
- Use CSS `gap` / explicit spacing ≥8px between adjacent touch targets.

**Verdict:** The project's `ui-patterns.md` already mandates 44px. The current **32×32px** chevron button fails that internal bar and trails Apple (44pt) / Material (48dp). This is the highest-priority, lowest-complexity fix.

### 3.3 Responsive design for tree menus

**NN/g "Dropdowns: Design Guidelines"** + Smashing "Designing Navigation for Mobile":

- Desktop can support **2–3 tiers** in a mega/cascading dropdown reasonably. Beyond that, users "fall out" of the menu (RStudio case study: multi-level cascading dropdowns are "difficult to physically manipulate").
- **Mobile** must collapse the hierarchy into a single off-canvas or full-screen panel with clear back/level navigation (the current code already does off-canvas — good).
- **Never put two different actions on the same row** (Smashing, Tivoli example): a category label that navigates *plus* an adjacent expand icon that opens a submenu causes chronic mis-taps. Fix: either (a) the whole row expands (no separate navigation link on branches) and a dedicated "View category" action lives elsewhere, or (b) the row navigates and expansion is triggered by a clearly separated, well-spaced icon.
- **Lazy loading** (current approach) is correct — children are fetched on first expand, not preloaded for all roots.

**UX Planet accordion #7/#8:** subtle open/close animation; single-open-vs-multi-open is a product decision (current code = single-open via `collapseSiblings` — acceptable).

### 3.4 Platform examples (Avito, eBay, etc.)

- **Avito (ru):** Hierarchical classifieds — the codebase explicitly models itself as "Avito-style header." Avito's desktop nav uses a top "All Categories" dropdown revealing a 2–3 column mega-style list of root categories, each with a hover-activated submenu; on mobile it becomes a hamburger→slide-over drawer. Deep expansion is bounded (2–3 levels) beyond which it routes to a listing page. (Source: Avito design-system references, Adil Dahmani portfolio write-up; live site not scraped — confidence MEDIUM.)
- **eBay:** eBay Playbook (responsive layout) + MIND Patterns (accessibility) treat the category nav as **progressive disclosure** with a sticky header; hierarchical disclosure uses the **WAI-ARIA Disclosure pattern** (button + `aria-expanded` + `aria-controls`) rather than cascading hover menus on small screens. Keyboard: Space/Enter to toggle. This is the model the current code approximates.
- **Allegro (pl):** Breadcrumbs hover reveals full ancestor category lists (a useful companion to the current breadcrumb component) — relevant because Mko Bazuna already has breadcrumbs.
- **Consensus across platforms:** chevron/caret that rotates, 44px+ hit area, lazy-loaded, max 2–3 levels of nesting on desktop with routing-page fallback for deeper levels.

---

## 4. Gaps & Violations vs. Best Practice

| Area | Current | Best practice | Gap |
|---|---|---|---|
| Icon orientation | Right-pointing chevron ▶ | Down/right caret ▼ that **rotates** | Wrong signifier for in-place expand; no rotation = no state cue |
| Chevron rotation | None | Rotate 90°→180° on open | State communicated only via `aria-expanded` + submenu show/hide |
| Touch target (chevron) | 32×32px | 44×44px (project + Apple) / 48 Material | Fails internal 44px standard; below platform baselines |
| Split action | Label navigates, icon expands, same row | Single action per row (whole header expands, or clear separation) | Mis-tap risk (Tivoli case) |
| Keyboard | Click/tap only | Space/Enter toggle; Esc closes; arrow navigation | Partial — outside-click & Esc exist, but no per-item arrow key handling |
| ARIA roles | None (`role="menu"`/`treeitem` absent) | `role="tree"` / `treeitem` / `group` + `aria-owns` | No tree semantics for screen readers |
| Nesting depth guard | No cap | ≤3 levels on desktop | Risk of "fall out" if catalog deepens |

---

## 5. Implementation Approaches

### Approach A — Minimal Chevron Fix (lowest risk, ships in one template)

Fix the two high-impact problems with a single, backward-compatible template change:

1. **Flip the chevron to a downward caret (▼)** that **rotates −90°→0°** (or 0°→180°) on open. This is the NN/g-recommended signifier and gives an immediate visual state cue with a `transition-transform`.
2. **Enlarge the hit area to ≥44×44px** while keeping the 16px icon: replace `px-2 py-2` with `p-3` (and add `min-w-11 min-h-11` = 44px) so the touch zone is 44×44 but the icon stays compact. This satisfies the project's 44px standard and Apple HIG.
3. Add `aria-controls` linking the button to the submenu container, and rotate via a `data-category-expanded` attribute (toggle a Tailwind `rotate-180`).

Pros: Tiny diff, no JS behaviour change, no template-test breakage (the `data-category-expand` attribute and `aria-expanded` are preserved). Cons: Leaves the split-action row and the missing tree semantics in place.

### Approach B — Whole-Header Disclosure (recommended balance)

Adopt the NN/g + UX-Planet "make both title and icon interactive" guidance: the **entire row header** (label + chevron) becomes the disclosure toggle for branches, eliminating the mis-tap-prone split action. Leaf nodes remain plain `<a>` navigation.

Concretely:
- Branch row: a single `<button data-category-expand>` spanning the row label + chevron, `aria-expanded` + `aria-controls`, with the caret rotating. Clicking it loads/injects the submenu (existing `loadSubmenu`).
- A separate, small "→ view category" link (or the chevron itself, if we keep two affordances) navigates to the category page. To keep it unambiguous, label it and space it ≥24px from the toggle (2.5.8 spacing exception) — or better: put the navigate action *inside* the expanded submenu as the first item ("View all X"), which is the Smashing "single function per row" fix.
- Chevron: down-caret ▼ rotating to ▲, 44×44px hit area.
- Add `role="tree" / "treeitem" / "group"` + `aria-owns` per WAI-ARIA Tree View pattern; wire Right/Down arrow keys per the APG keyboard matrix.
- Keep single-open accordion (`collapseSiblings` already exists) — or switch to multi-open if category scanning benefits; document the choice.
- Guard desktop nesting to ≤3 levels: beyond that, render a **routing page** link instead of another lazy submenu (matches Avito/eBay ceiling). The lazy endpoint already 404s unknown roots; extend it to 404 on a `max_depth` flag, or return a leaf-only partial.
- Responsive: desktop hover *prepares* (warm prefetches the submenu) but click still required to expand (avoids hover "fall out"); mobile off-canvas already correct, keep it.

Pros: removes the worst interaction hazard, adds tree semantics, keeps the HTMX/MPA model and the existing fragment-cache test intact. Cons: larger template + JS diff; `test_autocomplete_template.py` substring assertions on `get_children.exists`, `closeBranch`, `collapseSiblings`, `hidden class` remain valid but a new `role="tree"` and restructured row need test updates.

### Approach C — Full WAI-ARIA Tree View component (most robust, highest effort)

Replace the hand-rolled accordion with a proper `role="tree"` implementation matching the WAI-ARIA APG Tree View example: `tree` > `li[role=none]` > `treeitem` (with `aria-expanded` + `aria-owns`) > `group`. Implement the full keyboard matrix (Up/Down/Left/Right/Home/End/*/End). On mobile, keep the off-canvas drawer but make it a nested drill-down stack (push/pop levels) rather than an accordion.

Pros: best-in-class accessibility, matches W3C reference exactly, keyboard-complete. Cons: significantly more JS; risks diverging from the HTMX-driven MPA style the project chose (the codebase deliberately avoids `hx-on` and uses tiny inline scripts); would need new unit tests for keyboard behaviour and likely a new `role=group` partial contract.

---

## 6. Recommendation

**Ship Approach A first (one-ticket), then Approach B as the structural follow-up.**

Decision logic:

- The **chevron orientation + rotation** fix is an unambiguous, evidence-based win (NN/g explicitly says the current right-arrow is the wrong signifier for in-place expansion). It is also a prerequisite for *any* approach — even C needs a rotating caret.
- The **touch-target enlargement to 44×44px** is required by the project's own `ui-patterns.md` (44px floor) and by WCAG 2.5.5 AA/AAA; the current 32×32px chevron is a silent standard violation. Again approach-agnostic.
- Both A changes preserve every assertion in `test_autocomplete_template.py` (same attributes, same `hidden` class, same functions) and `test_submenu.py` (endpoint unchanged), so they land with **zero test breakage**.
- Approach B (whole-header disclosure) then removes the split-action hazard and adds tree semantics — but it touches the row structure the template tests assert on, so it deserves its own ticket with updated assertions (`role="treeitem"`, no split link). It is the right medium step before considering the heavier C.
- **Do not** start with C: it over-delivers relative to the HTMX/MPA philosophy in `AGENTS.md` ("HTMX 1.9.12 has no `hx-on`") and would introduce a JS-heavy widget that fights the codebase's progressive-enhancement grain.

### Concrete next-ticket spec (Approach A)

File: `mega_submenu.html` + `header_catalog.html`.

- Replace the chevron path `d="M9 5l7 7-7 7"` (▶) with a **downward caret** `d="M5 9l7 7 7-7"` (▼).
- Add `aria-controls="menu-{{ child.id }}"` to the expand button and `id="menu-{{ child.id }}"` on the submenu container (so assistive tech can follow the relationship).
- Change the button padding from `px-2 py-2` to `p-3` and add `min-w-11 min-h-11` (=44px) — hit area grows to 44×44 while the 16px icon stays centered.
- Add `transition-transform duration-150` and, in the inline `<script>`, toggle a `rotate-180` class (or `transform rotate-180`) on the SVG when the branch opens, alongside the existing `aria-expanded` set.
- Keep `data-category-expand` and `data-category-submenu` attribute names identical so `attachCategoryHandlers` needs only the rotation addition.
- Update `ui-patterns.md` §Shared Navigation Headers to record: chevron = rotating down-caret; hit area = 44×44; max 2–3 desktop levels.

After A ships and is verified, open a follow-up for B (whole-header disclosure + `role="tree"` + nested-drawer mobile) and update the two template test files' substring assertions at that time.

---

## 7. Sources (confidence-rated)

- **HIGH** — WCAG 2.2 SC 2.5.5 (Target Size Enhanced, 44px) and SC 2.5.8 (Target Size Minimum, 24px): w3.org/WAI/WCAG22/Understanding (Context7 `/websites/w3_wai_wcag22`, `/websites/w3c_github_io_wcag`).
- **HIGH** — W3C WAI-ARIA APG Disclosure pattern & Tree View pattern (keyboard matrix, `aria-expanded`/`aria-controls`/`aria-owns`, `role=tree`/`treeitem`/`group`): Context7 `/w3c/wai-aria-practices`.
- **HIGH** — NN/g "Accordion Icons: Which Signifiers Work Best?" (empirical A/B: caret best, right-arrow warns-against for in-place accordions): nngroup.com/articles/accordion-icons.
- **HIGH** — Apple HIG (44pt) / Google Material (48dp) touch targets: referenced via Context7 platform guidance.
- **HIGH** — The 44px rule background + age/tremor error-rate data (codexical/Heurilens, 2026): websearch.
- **MEDIUM** — Avito desktop/mobile category nav structure (design-system references, Adil Dahmani portfolio; live site not scraped): websearch.
- **HIGH** — eBay responsive layout + MIND Patterns (disclosure-based hierarchy): ebay.com/playbook/responsive-layout,opensource.ebay.com/mindpatterns.
- **HIGH** — Smashing "Designing Navigation for Mobile" (split-action / Tivoli anti-pattern, 2–3 tier ceiling): smashingmagazine.com.
