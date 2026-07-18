# Stack & Versioning Audit — Mko Bazuna (Phase 1 MVP)

**Auditor scope:** Cross-package version compatibility & architectural impact.
**Date:** 2026-07-18
**Inputs:** `docs/wiki/02_packages.md`, `03_structure.md`, `04_db_structure.md`, `05_audit_resolutions.md`; actual `pyproject.toml` + `uv.lock`; live PyPI/docs verification.

---

## 0. CRITICAL PRECONDITION — actual lockfile ≠ documented stack

The authoritative dependency declaration (`pyproject.toml` + `uv.lock`) is radically
behind `docs/wiki/02_packages.md`. The lockfile currently declares ONLY:

```
django>=5.2.16,<6.0            # Django 5.2 LTS (Python 3.14 supported since 5.2.8; LTS until Apr 2028).
                              # Upper bound <6.0 blocks the major bump: django-filter / django-mptt
                              # are not yet validated against Django 6.0 as a target baseline.
django-mptt>=0.18.0            # Hierarchical categories. 0.18.0 is the first version officially
                              # compatible with Django 5.2. (0.16.0 from the old doc is NOT validated.)
psycopg2-binary>=2.9.11        # psycopg2 (NOT psycopg3). psycopg2-binary has NO Python 3.14 wheel
                              # -> unusable on python:3.14-slim; must be replaced (see below).
python-dotenv>=1.2.1
```

**None** of the documented stack is actually pinned/installed:
- `psycopg[binary]>=3.2.0` → absent (only psycopg2-binary present)
- `django-environ`, `django-mptt`, `django-filter`, `aiogram`, `deep-translator`
- `django-tailwind`, `django-htmx`, `django-storages`, `boto3`, `pillow`

**Owner decision (2026-07-18): KEEP Django <6.0** — pin the LTS 5.2 line
(`django>=5.2.16,<6.0`). The Django 6.0.1 figure that previously appeared in
`pyproject.toml` was an unvalidated placeholder and has been corrected to match
`02_packages.md`. The docs and the lockfile now agree on the Django 5.2 LTS baseline.

**Consequence:** Every compatibility check below is currently *theoretical* — the
documented architecture cannot run until the lockfile is reconciled with `02_packages.md`.
This reconciliation (Step 0) is a hard prerequisite for the version checks in Step 3.

---

## 1. CRITICAL CROSS-DEPENDENCIES (pair/group → risk)

### C1. `django-filter` ⇄ `django` (HARD GATE)
- `django-filter==26.1` requires **`Django>=5.2`** (confirmed on PyPI:
  `dependencies = ["Django>=5.2"]`).
- This forces Django **off 5.1.2**. Two upgrade targets exist:
  - **5.2.16 LTS** (supported to 2028) — `django-filter 26.1` is explicitly
    tested against `django52` tox env → **compatible**.
  - **6.0.7** (latest) — `django-filter 26.1` tox adds `django61` env and states
    "Added testing for Django 6.1" → **6.0 also compatible**.
- **Risk:** `django-filter==24.3` (current doc target) supports only up to Django 5.1;
  it will refuse to install against Django 5.2+/6.0. You cannot keep 24.3.

### C2. `django-mptt` ⇄ `django` (HARD BLOCKER — verified)
- `django-mptt==0.18.0` CHANGELOG (PyPI/GitHub) explicitly states:
  *"Added support for Django 6.0."* and *"Fixed the way indexes are defined for
  Django 5."*
- Therefore **`django-mptt 0.18.0` supports BOTH Django 5.2 AND Django 6.0.**
- The older `0.16.0` (current doc target) predates the 5.2/6.0 index fixes and
  is **not** validated against 5.2/6.0. Must move to **`0.18.0`**.
- **Risk (maintenance):** `django-mptt` GitHub banner: *"This project is currently
  unmaintained … kept alive on a best-effort basis."* It is the single source of
  truth for the category tree (`04_db_structure.md`, zone D1). If mptt breaks on a
  future Django, the category tree — and the `ads.category_name` denormalization
  trigger that reads `categories.name` — breaks with it. **Recommend tracking
  `django-tree`/alternative as a contingency (advisory).**

### C3. `aiogram` FSM storage ⇄ `psycopg3` ⇄ shared-ORM architecture (CRITICAL FICTION)
- The doc (`02_packages.md`, `03_structure.md` zone D7/D9, `05` "validated Z05/Z09")
  claims: *"aiogram FSM PostgreSQL SQLStorage."*
- **VERIFIED FALSE:** aiogram's built-in FSM storages are **Memory, Redis, Mongo
  only** (confirmed in `docs.aiogram.dev/.../storages.html` and source modules
  `memory`, `redis`, `pymongo`, `mongo`). The SQLite storage added in 2025
  (`SqliteStorage`, PR #1718) uses **`aiosqlite`** and is SQLite-only.
- **There is NO native aiogram PostgreSQL `SQLStorage`.**
- For PostgreSQL-backed FSM you must use a 3rd-party package (`AiogramStorages` /
  `SQLAlchemyStorage`), which drives the DB via **`asyncpg`**, NOT psycopg3.
- **Architectural conflict:** `02_packages.md` zone C5 states the bot shares ONE
  psycopg3 driver/pool with the web process. An asyncpg-based FSM storage would
  introduce a **second, separate PostgreSQL driver** into the bot process, defeating
  the "single driver, single pool, PgBouncer in transaction mode" design.
- **Risk:** The documented FSM design cannot be implemented as written. Decision
  required before Step 3:
  (a) Use `MemoryStorage` (loses FSM on bot restart — unacceptable for the
      US-S2 multi-step publish dialog per zone D9),
  (b) Use Redis storage (adds Redis dependency, contradicts "Celery+Redis deferred"),
  (c) Use SQLite `SqliteStorage` (separate DB file, not the shared Postgres —
      breaks "FSM separate migration owner but one database" assumption),
  (d) Use `AiogramStorages`/asyncpg (second driver in bot process — conflicts C5).
  **This is the single most consequential open architectural question.**

### C4. `psycopg3` ⇄ `django` ⇄ `sync_to_async` runtime model
- Django 6.0 native async ORM requires psycopg3 (Django docs: psycopg 3.1.12+
  recommended; psycopg2 falls back to `sync_to_async` threads).
- `02_packages.md` zone C5 runs the **web as sync WSGI gunicorn** and the **bot via
  `django.setup()` + `sync_to_async`** over a per-process psycopg3 pool
  (`CONN_MAX_AGE=0`) + PgBouncer transaction mode.
- This is internally consistent for Django **5.2** (psycopg3 sync path + pooling
  available) and **6.0** (same, plus native async if ever needed). psycopg 3.3.4
  supports Python 3.14 and PG17 libpq. **No hard conflict** — but see C5.

### C5. `psycopg3` + `PgBouncer transaction mode` ⇄ `search_vector` plpgsql triggers
- The FTS design (`04_db_structure.md`) uses **plpgsql `BEFORE INSERT/UPDATE`
  triggers** that do `SELECT name FROM categories` and mutate `NEW.category_name`
 /`NEW.search_vector`.
- PgBouncer **transaction mode** is documented as recommended. In transaction mode,
  a trigger that issues its own `SELECT` inside the same statement is fine (same
  backend, same transaction). **However**, any session-level state (e.g. `SET`
  LOCAL, advisory locks, `pg_trgm` config per-session) does NOT survive across
  PgBouncer transaction boundaries.
- **Risk (medium):** The `to_tsvector('russian', …)` calls embed the config name
  literally (safe), but if future triggers rely on session `SET` (e.g. `search_path`
  for the FTS functions) they will break under transaction-mode PgBouncer. Verify all
  trigger functions are self-contained (schema-qualified names, no `SET`).

---

## 2. VERSION-CONFLICT POINTS (where `>=` is NOT enough — a `=` may be required)

| ID | Package(s) | Issue | Needed pin |
|----|-----------|-------|------------|
| V1 | `django-filter` | Hard `Django>=5.2`; caps lower bound, not upper. With `>=` it may pull a version needing Django 6.2+ later. | Pin `django-filter==26.1` (or `<27`) and pair with an explicit Django pin. |
| V2 | `django` | Choosing 6.0.7 vs 5.2.16 is a product decision (LTS vs latest). `>=` alone is unsafe — 6.1/6.2 may break mptt/tailwind before they catch up. | Pin Django explicitly: `django==5.2.16` **or** `django==6.0.7`. Do **not** use bare `>=`. |
| V3 | `django-mptt` | `0.16.0` (doc) unvalidated on 5.2/6.0. Must be `0.18.0`. | `django-mptt==0.18.0`. |
| V4 | `psycopg[binary]` | The `[binary]` extra must match the core `psycopg` version exactly (Django imports `psycopg`, not `psycopg3`). Mismatched `psycopg` + `psycopg-binary` causes import errors. | Pin both to 3.3.4: `psycopg[binary]==3.3.4`. |
| V5 | `django-tailwind` + daisyUI | Standalone binary mode has **NO plugin support** (see S1). If daisyUI is required, npm mode is mandatory. | If daisyUI: `django-tailwind==4.5.0` in **npm mode** + `package.json` with daisyui. If standalone: drop daisyUI. |
| V6 | `Pillow` | `12.3.0` needs Python 3.14 wheels (available) but some transitive image libs (e.g. `imagehash`, future `django-imagekit`) may lag on 3.14. | `pillow==12.3.0` OK; keep an upper bound if adding image-processing deps. |
| V7 | `aiogram` | `>=3.15.0` could resolve to a version whose `SqliteStorage`/Redis API changed. No Postgres native storage exists at any version. | Pin `aiogram==3.30.0`; resolve C3 storage choice separately. |

**Rule reminder:** per project rule, use `>=` for everything except where a CRITICAL
incompatibility demands `=`. V2/V3/V4 are the only places a hard `=` is currently
justified (exact Django/mptt/psycopg alignment).

---

## 3. PRIORITIZED COMPATIBILITY CHECKLIST (Step 3)

1. **[BLOCKER] Reconcile `pyproject.toml`/`uv.lock` with `02_packages.md`.**
   The lockfile is missing every documented package and is on Django 6.0.1 + psycopg2.
   Action: add all documented deps; remove psycopg2-binary; add `psycopg[binary]`.
   (Addresses §0.)

2. **[BLOCKER] Resolve the aiogram FSM storage question (C3).**
   Confirm there is no native PostgreSQL `SQLStorage` in aiogram; pick Memory/Redis/
   SQLite/asyncpg and document the chosen driver's relationship to the shared psycopg3
   pool + PgBouncer. This determines whether the bot process gets a 2nd DB driver.

3. **[DECISION — RESOLVED] Django target: `5.2.16` LTS (`<6.0`).**
   RESOLVED by owner (2026-07-18): **keep Django <6.0**, pin `django>=5.2.16,<6.0`.
   Both `django-filter 26.1` and `django-mptt 0.18.0` are validated against 5.2
   (verified). LTS = longer support window (until Apr 2028), lower churn; psycopg3
   sync path + per-process pool + PgBouncer transaction mode all hold on 5.2.
   Do NOT use bare `>=` (V2) — the explicit `<6.0` upper bound is now in pyproject.

4. **[PIN] Lock `django-filter==26.1`, `django-mptt==0.18.0`,
   `psycopg[binary]==3.3.4` together** (V1/V3/V4). Re-run `uv lock` and verify
   resolution does not pull Django 6.1+/6.2+ implicitly.

5. **[VERIFY] daisyUI vs django-tailwind standalone mode (S1).**
   Confirm `docs/wiki` claim that 4.4.2 "supports daisyUI" contradicts the
   standalone-binary "❌ Not available for plugins" limitation. Decide: npm mode
   (keeps daisyUI, adds Node at build) or drop daisyUI (keeps zero-Node standalone).
   Update `02_packages.md` to match reality (DOC-UPDATE).

6. **[VERIFY] `Pillow 12.3.0` + `Python 3.14` image pipeline.**
   Confirm Pillow 12.x ships 3.14 wheels (yes) and that `ad_images` JPEG
   magic-byte validation works under 3.14. Check no transitive image dep lags on 3.14.

7. **[VERIFY] PostgreSQL 17 + psycopg 3.3.4 + Django 5.2/6.0.**
   Django 6.0 docs: psycopg 3.1.12+ required/recommended — 3.3.4 satisfies.
   Confirm `postgres:17-alpine` libpq ≥ needed by psycopg 3.3.4 binary (it bundles
   its own libpq, so OK). Confirm `GinIndex`/`GistIndex` Django ORM mapping works
   on 17 for `search_vector` + `pg_trgm`.

8. **[VERIFY] plpgsql trigger safety under PgBouncer transaction mode (C5).**
   Inspect `ads_search_vector_fn()` and `categories_name_propagate()` for any
   session-state dependence (`SET`, advisory locks, non-schema-qualified funcs).
   Transaction mode must not break trigger execution.

9. **[VERIFY] `deep-translator 1.11.4` + `Python 3.14`** for the Bosnian→Russian
   query translation (zone D5/C7). Confirm the package imports under 3.14 and the
   ~500ms timeout + fallback path is implemented at the boundary (not blocking the
   GIN `search_vector` query).

10. **[VERIFY] `django-environ` (≥0.14.0) replaces raw `python-dotenv`**
    typing (`env.bool/int/db`). The lockfile currently uses only `python-dotenv`
    (a transitive dep of environ). Add `django-environ` explicitly.

11. **[ADVISORY] Contingency plan for unmaintained `django-mptt`.**
    The category tree is the single source of truth feeding the `ads.category_name`
    denormalization. Track an alternative (e.g. `django-tree`) so a future Django
    break does not block the whole FTS pipeline. No code change now.

12. **[ADVISORY] Django 6.0 native async ORM vs sync WSGI decision.**
    Project runs **sync WSGI** in phase 1 (zone D10). Django 6.0's native async
    path is unused. If the bot later uses `aget()`/`afilter()` it must run under
    ASGI, but the web stays sync. Confirm this split is intentional and documented;
    native pooling (`psycopg_pool.AsyncConnectionPool`) only applies on the async
    path — under sync WSGI + PgBouncer the documented pooling model holds.

---

## 4. ANSWERS TO THE KEY QUESTIONS (from the brief)

**Q1 — django-filter 26.1 requires Django ≥5.2; which Django to pick?**
→ Both 5.2.16 LTS and 6.0.7 satisfy django-filter 26.1 (verified tox matrices).
django-mptt 0.18.0 also supports both. Pick on support-window vs native-async
criteria; pin explicitly. Do NOT stay on 5.1.2 (filter 26.1 will refuse).

**Q2 — Is django-mptt 0.18.0 compatible with Django 5.2 AND 6.0?**
→ **YES for both** (CHANGELOG: "Added support for Django 6.0" + Django-5 index fix).
This removes mptt as a blocker for either Django choice. `0.16.0` is NOT validated.
**Owner has chosen Django 5.2 LTS (`<6.0`)**, so mptt 0.18.0 on 5.2 is the target.

**Q3 — aiogram 3.30 + Django ORM via sync_to_async + psycopg3 pool + SQLStorage?**
→ The Django-ORM-via-`sync_to_async` part is fine (C4). But **aiogram has NO
PostgreSQL `SQLStorage`** — only Memory/Redis/Mongo, plus a SQLite-only
`SqliteStorage`. The documented "FSM SQLStorage on PostgreSQL" cannot be built with
aiogram alone; a 3rd-party asyncpg-backed storage would add a 2nd driver,
conflicting with the shared-psycopg3 design (C3).

**Q4 — django-tailwind 4.5.0 standalone + daisyUI?**
→ **CONFLICT confirmed.** Standalone binary mode explicitly does NOT support plugins
(DaisyUI). The `02_packages.md` note "standalone needs NO Node (npm mode needs Node
only at build)" is technically true, but daisyUI is unavailable in standalone
regardless. To keep daisyUI → npm mode (Node at build). To keep zero-Node → drop
daisyUI. Requires a DOC-UPDATE to `02_packages.md`.

**Q5 — Pillow 12.3.0 + Python 3.14?**
→ OK. Pillow 12.x officially supports Python 3.14 (wheels built against 3.14 final
2025-10-07). Verify the `ad_images` JPEG magic-byte check path imports cleanly.

**Q6 — PostgreSQL 17 + psycopg 3.3.4 + Django 5.2/6.0?**
→ OK. psycopg 3.3.4 bundles its own libpq and supports PG17 + Python 3.14;
Django 6.0 requires psycopg ≥3.1.12 (satisfied). Confirm Django ORM
`GinIndex` mapping for `search_vector` on PG17.

---

## 5. FINDINGS SUMMARY

| Sev | ID | Finding | Type |
|-----|----|---------|------|
| CRITICAL | §0 | Lockfile missing all documented packages; was on `django>=6.0.1` + psycopg2, contradicting `02_packages.md` (Django 5.2 LTS `<6.0` + psycopg3). **RESOLVED**: pyproject corrected to `django>=5.2.16,<6.0`; still missing the documented stack (psycopg3, mptt, etc.). | SPEC-DEVIATION |
| CRITICAL | C3 | "aiogram FSM PostgreSQL SQLStorage" does not exist; blocks the documented bot persistence design. | SPEC-DEVIATION |
| HIGH | C1/V1 | django-filter 26.1 forces Django ≥5.2; 5.1.2 (and 24.3) incompatible. | SPEC-DEVIATION |
| HIGH | C2/V3 | django-mptt 0.16.0 unvalidated on 5.2/6.0; must be 0.18.0. | SPEC-DEVIATION |
| HIGH | Q4/S1 | daisyUI unavailable in django-tailwind standalone mode; doc claims otherwise. | DOC-UPDATE / SPEC-DEVIATION |
| MEDIUM | V2 | Django version must be explicitly pinned, not `>=`. | BEST-PRACTICE |
| MEDIUM | V4 | `psycopg` + `psycopg-binary` must match exactly. | BEST-PRACTICE |
| MEDIUM | C5 | plpgsql trigger session-state risk under PgBouncer transaction mode. | BEST-PRACTICE |
| LOW | C2-maint | django-mptt unmaintained; category-tree SPOF. | BEST-PRACTICE (advisory) |
| LOW | §3.12 | Sync WSGI vs Django 6.0 native async split must be intentional. | BEST-PRACTICE |
