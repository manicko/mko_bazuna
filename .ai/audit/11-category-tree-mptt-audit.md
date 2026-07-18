# Category Tree Architecture Audit — django-mptt vs Alternatives

**Auditor scope:** Is `django-mptt` required for the category tree, or can Django 6.0 / PostgreSQL 17 solve it natively? Forward-looking recommendation for the MVP.
**Date:** 2026-07-18
**Inputs:** `docs/wiki/01_technical_specification.md` (decision D), `04_db_structure.md` (zone D1), `02_packages.md`, `03_structure.md`; prior `10-stack-versioning-audit.md`; live PyPI/GitHub verification of mptt, treebeard, tree-queries, fast-treenode.

---

## 0. DISCOVERY — current state

- **No implementation exists yet.** There is no `apps/` or `src/` package, no `models.py` for `Category`. The project is currently **docs + lockfile only**. The mptt decision is therefore a *spec-level / pre-implementation* decision, not a refactor of existing code. This is the cheapest possible moment to change the choice.
- The lockfile (`10-stack-versioning-audit.md §0`) was on `django>=6.0.1` + psycopg2
  and missing every documented package, including mptt. **RESOLVED (2026-07-18):**
  owner chose to **keep Django <6.0** (pin `django>=5.2.16,<6.0`); pyproject corrected.
  The documented stack (incl. mptt) is still not actually installed — that is the
  remaining §0 reconciliation item, independent of the Django-major decision.
- Spec facts (authoritative):
  - Tree: ~**30-50 categories, 3 levels** (Товары/Услуги/Недвижимость → subgroups → leaf).
  - Requirement: **filter by subtree** ("Электроника" → all nested ads).
  - Constraint (04_db_structure.md line 3, 126-127): **django-mptt is the single source of truth (lft/rght/tree_id/level); NO denormalized `path`/`level` columns stored** — risk of desync is cited as the *reason* for choosing mptt.
  - `get_descendants()` is the documented subtree primitive.

---

## 1. ANSWER TO THE 6 QUESTIONS

### Q1 — Can Django 6.0 (no third-party package) solve the hierarchy + subtree filter?
**YES.** Django ORM core supports only the **Adjacency List** pattern (`parent_id` FK). A subtree query over an adjacency list is a **recursive CTE** (`WITH RECURSIVE`), which PostgreSQL 17 executes natively and efficiently. Django 6.0 can express a recursive CTE via `django.db.models.QuerySet` + `union()`/`RawSQL`, or more cleanly via the third-party `django-cte` helper (small, maintained). For a 30-50-node / 3-level tree, a recursive CTE resolves the entire subtree in **one query**, O(1) writes. No mptt needed.

Other patterns compared (all with trade-offs):
| Pattern | Write cost | Subtree read | Notes |
|---|---|---|---|
| Adjacency List + recursive CTE | O(1) | O(n) single query | **Best default for our size.** Simple schema, Django-native. |
| Materialized Path | O(1) | O(n) `LIKE`/prefix | Stores a `path` string — **violates spec's "no denormalized path" rule** unless computed at query time. |
| Nested Set (mptt) | O(n) on every insert/move (rebalance lft/rgt) | O(n) range scan | Optimized for *static read-heavy* trees; writes are expensive. |
| Closure Table | O(n) per write | O(n) join | Extra linkage table; overkill for 50 nodes. |
| `ltree` (PG extension) | O(1) | GiST-indexed `<@` descendant op | Native, very fast for read-heavy taxonomies; requires enabling the `ltree` extension + maintaining a `path` column. |

### Q2 — Can `get_descendants()` be replicated on plain ORM + PG17?
**YES, trivially.** Three equivalent approaches:
1. **Recursive CTE** (`WITH RECURSIVE`): anchor = the node, recurse on `parent_id`. Returns all descendant IDs in one query; join to `ads` with `ads.category_id IN (subquery)`.
2. **`ltree`** `<@` operator: `WHERE path <@ 'Electronics'` — one indexed predicate, sub-millisecond on tiny trees.
3. **`django-tree-queries`** `node.descendants()` — wraps the recursive CTE for you and returns a queryset.

All three satisfy the spec's subtree-filter requirement without mptt.

### Q3 — If we drop mptt, which pattern keeps "no denormalized path/level"?
The spec's constraint is about **not storing** derived columns (to avoid desync). The correct pattern that honors this is:
- **Adjacency List with query-time derivation**: store only `parent_id`. Compute `level` and `path` *at query time* via the recursive CTE (the CTE can `array_append` ancestor IDs into a `path` array and count depth — see the MVP Factory benchmark). Nothing is persisted, so there is nothing to desync. This is exactly the pattern the spec wanted mptt to provide, but without mptt's write-time rebalancing.
- `ltree` is the *one* exception: it **does** store a `path` column. If the spec's "no denormalized path" rule is taken literally and strictly, `ltree` technically violates it (the `path` is a stored derived value). For 50 mostly-static categories the desync risk is negligible and the `path` is maintained by the model's `save()`/manager, but it is a deviation from the letter of the spec. Flag for the owner.

### Q4 — Alternatives compatible with Django 5.2 LTS (owner-pinned baseline) and 6.0?
Verified live (2026-07-18):

| Package | Django 5.2 / 6.0? | Maintained? | Verdict |
|---|---|---|---|
| **django-mptt 0.18.0** | Yes (CHANGELOG "Added support for Django 6.0", 2025-08; validated on 5.2) | **NO — "currently unmaintained", best-effort only** | SPOF risk; see §3. |
| django-mptt 0.19rc1 | Pre-release 2026-06-02 | Still unmaintained | Not production. |
| **django-treebeard 5.x** | **Yes** (CHANGELOG 2026-01: "Added support for Django 6.0", `deps=["django>=5.2"]`, Python 3.14) | **YES — actively maintained, Production/Stable** | **Best drop-in alternative.** Supports MP/NS/AL node types. |
| **django-tree-queries 0.24** | **Yes** (2026-03: "Added Python 3.14 and Django 6.0 to CI") | Yes (feincms org) | Adjacency + recursive CTE; returns querysets; light. |
| django-fast-treenode 3.2.10 | Declares `Django>=5.0`; **not yet certified for 6.0** in docs | Yes, very active | Overkill — built for 50k–100k nodes / 1000 levels. Heavy dependency footprint (msgpack, openpyxl, pyyaml, PyJWT). |

### Q5 — For a 30-50 node / 3-level MVP, is mptt overkill?
**YES — strongly.** mptt's nested-set design optimizes for *read-heavy, write-rare* trees by paying a heavy write penalty (every insert/reparent rewrites `lft`/`rght` for a whole tree or subtree). For 50 nodes this penalty is invisible, but you inherit: (a) an unmaintained SPOF, (b) 4 extra columns (`lft/rght/tree_id/level`) that the spec itself admits exist only to avoid desync, and (c) mptt-specific save/rebuild complexity. A plain `parent_id` + recursive CTE gives identical read behavior with simpler writes and zero extra dependencies. **mptt is the heaviest possible choice for the smallest possible tree.**

### Q6 — If we KEEP mptt, what is the risk?
- **Maintenance SPOF:** Upstream explicitly states no guarantee of patches; "neither is guaranteed" (issue #833). A future Django 6.1/6.2 change (e.g. identifier quoting, as tree-queries 0.24 had to fix) could break mptt with no committed fix timeline.
- **Blast radius:** The category tree is the single source of truth feeding the `ads.category_name` denormalization trigger (04_db_structure.md). If mptt breaks, category reads/writes and the FTS pipeline that depends on `categories.name` break with it.
- **Remediation cost if it breaks later:** Migrating an *existing* mptt table (with `lft/rght` data) to another model is more work than choosing the model now, before any rows exist.

---

## 2. VERDICT

**НУЖЕН ЛИ django-mptt:** **НЕТ.** (Alternative recommended.)

**РЕКОМЕНДАЦИЯ:** **НЕ тащить django-mptt.** Replace with one of:

- **Option A (recommended, lowest risk):** Plain **Adjacency List (`parent_id`) + recursive CTE**, implemented with `django-cte` (tiny, maintained) or a hand-written `WITH RECURSIVE` in a manager method. Honors the spec's "no denormalized path/level" rule exactly (derive at query time). Zero heavy deps. Best fit for 50 nodes / 3 levels.
- **Option B (if you want a maintained package with a familiar API):** **`django-treebeard==5.x`** (MP_Node materialized-path variant). Actively maintained, Django 6.0 + Python 3.14 certified, `django>=5.2`. Caveat: it *does* store a `path` column → technically deviates from the spec's "no denormalized path" letter (though not in spirit, since treebeard maintains it atomically). Requires a DOC-UPDATE to 04_db_structure.md.
- **Option C (PG-native, read-optimized):** **`ltree` extension** + `django-ltree` or a custom `path` `ltree` field. Fastest subtree reads via `<@`. Same spec-deviation caveat as B (stored path). Adds an `ltree` extension dependency to the DB.

**Do NOT use** `django-fast-treenode` (over-engineered for our scale; not yet 6.0-certified) and **do NOT stay on** `django-mptt`.

---

## 3. RISKS BY OPTION

| Option | Risk (severity) | Why |
|---|---|---|
| Keep mptt 0.18.0 | **HIGH (SPOF)** | Unmaintained; future Django break unguaranteed; blocks whole FTS pipeline on a category-tree failure. |
| A: Adjacency + recursive CTE | **LOW** | Native PG feature, no extra dep, trivial at our scale. Only "risk" is writing the CTE once (small, testable). |
| B: treebeard 5.x | **LOW-MEDIUM** | Maintained, 6.0-certified. SPEC-DEVIATION: stores `path` (deviates from "no denormalized path" rule → needs doc update). |
| C: ltree | **LOW-MEDIUM** | Native, fast. SPEC-DEVIATION: stored `path`. Adds `ltree` extension to DB provisioning (Docker `postgres:17` already used — easy). |

---

## 4. ARCHITECTURAL IMPACT (03_structure.md / 04_db_structure.md)

**YES — the docs must change** if mptt is dropped. Specific edits required:

- **`04_db_structure.md` (line 3, 116-128):** Replace "django-mptt — единственный источник истины (lft/rght/tree_id/level)" with the chosen pattern:
  - Option A: `categories` keeps `parent_id` (FK, nullable) as the single source of truth; subtree via recursive CTE (manager method `descendants()`); `level`/`path` computed at query time, **not stored** — this *strengthens* the existing "no denormalized path/level" rule.
  - Option B/C: document the stored `path` column and explicitly relax the "no denormalized path" constraint (DOC-UPDATE, since it is a deliberate, atomically-maintained deviation).
- **`03_structure.md` (line 22):** Update the `categories/` comment from "mptt-дерево" to the chosen implementation.
- **`01_technical_specification.md` (line 77):** "django-mptt остаётся единственным источником истины дерева" → rephrase to the chosen mechanism.
- **`02_packages.md` (line 4, 29):** Remove `django-mptt`; add `django-cte` (Option A) OR `django-treebeard` (Option B) OR note `ltree` extension (Option C). Align with the pinned Django 5.2 LTS (`<6.0`) baseline.

The `ads.category_name` denormalization trigger (04_db_structure.md lines 186-219) is **unaffected** by this change — it only reads `categories.name`, which exists in every option. No FTS / search_vector rework needed.

---

## 5. FINDINGS SUMMARY

| Sev | ID | Finding | Type |
|-----|----|---------|------|
| HIGH | T1 | django-mptt is unmaintained (best-effort SPOF) yet is the single source of truth for the category tree feeding the FTS pipeline. | BEST-PRACTICE (advisory) |
| MEDIUM | T2 | For a 30-50 node / 3-level MVP, mptt (nested-set, expensive writes) is the heaviest possible choice; adjacency+CTE or treebeard suffice. | BEST-PRACTICE |
| MEDIUM | T3 | django-treebeard 5.x is actively maintained and Django 6.0 + Python 3.14 certified — viable drop-in alternative. | BEST-PRACTICE |
| LOW | T4 | Spec's "no denormalized path/level" rule is honored exactly by Option A (query-time derivation); Options B/C store a `path` and need a DOC-UPDATE to relax the rule. | DOC-UPDATE / SPEC-DEVIATION |
| LOW | T5 | `ads.category_name` / `search_vector` trigger is independent of the tree mechanism (reads only `categories.name`); no FTS change required. | BEST-PRACTICE (informational) |
| LOW | T6 | Decision is pre-implementation — no `Category` model exists yet, so switching now has zero migration cost. | BEST-PRACTICE (informational) |

---

## 6. RECOMMENDED ACTION (priority order)

1. **Drop `django-mptt`** from `02_packages.md` and the design.
2. **Adopt Option A** (Adjacency List `parent_id` + recursive CTE via `django-cte`, or a manager `descendants()` method). Effort: **small**. Priority: recommended.
3. If a package API is preferred over a hand-rolled CTE, **use `django-treebeard==5.x`** (MP_Node) and update `04_db_structure.md` to document the stored `path` (DOC-UPDATE). Effort: **small**. Priority: recommended alternative.
4. Update `01/03/04_db_structure.md` and `02_packages.md` wording to reflect the chosen mechanism (remove "django-mptt is the single source of truth"). Effort: **trivial**. Priority: recommended.
5. Keep `django-mptt` **only** if the owner explicitly accepts the unmaintained-SPOF risk for a 0.18.0 pin (and tracks treebeard as contingency per `10-stack-versioning-audit.md` §3.11). Not recommended.
