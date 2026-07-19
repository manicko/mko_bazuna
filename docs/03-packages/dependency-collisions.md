---
id: dependency-collisions
domain: packages
tags:
  - stack
  - dependencies
  - versions
  - compatibility
related:
  - packages-list
  - db-schema
  - architecture-structure
---

## Purpose

Documents version-coupling and collision risk across the Mko Bazuna dependency set. This is the
single source of truth explaining **why individual packages cannot be bumped in isolation** — a
change to one package forces a coordinated change to one or more others, or breaks the build/run.

Evidence is drawn from [packages-list](packages-list.md) and `pyproject.toml`. Each row names the constraint,
what it depends on, why it cannot be bumped alone, and where the evidence lives.

## Version-Coupling Matrix

| Package | Version Constraint | Depends-On | Why Can't Bump Alone | Evidence |
|---------|--------------------|------------|----------------------|----------|
| django | `>=5.2.16,<6.0` | django-mptt, django-filter, django-tailwind, django-htmx, django-environ, pytest-django | django-mptt is unmaintained and **not validated against Django 6.0**. Bumping django to `6.0` breaks django-mptt and cascades into categories (mptt tree). The upper bound `<6.0` is a hard guard, not a preference. | `packages-list.md` lines 21-22, 40, 43, 81, 83; Residual Risks (django-mptt abandonment, MEDIUM) |
| django-mptt | `>=0.18.0` | django (`<6.0`) | First Django 5.2-compatible release; unmaintained. A Django 6.0 bump invalidates it. Must be replaced (recursive CTE / django-tree-queries) **before** any Django 6.0 move. | `packages-list.md` lines 43, 83, 95; `db-schema.md` lines 20, 119 |
| psycopg (v3) | `psycopg[binary]>=3.2.0` | PostgreSQL 18, PgBouncer | psycopg3 is the Django 5.2 native driver. Under PgBouncer **transaction pooling mode** you MUST set `OPTIONS={"prepare_threshold": None}`, otherwise prepared-statement reuse across transactions fails. Bumping psycopg without re-checking the PgBouncer `prepare_threshold` config breaks pooled connections. | `packages-list.md` lines 41, 82, 74; `spec-index.md` line 41; `db-schema.md` line 87 (trigger-maintained column, no `GENERATED ALWAYS`) |
| pytest-asyncio | `>=1.4.0` | pytest (`minversion="8.4"`), aiogram async tests | Major jump from 0.24; requires `asyncio_mode="strict"` and a pytest `minversion` of `8.4`. Bumping pytest-asyncio alone without setting strict mode and the minversion breaks bot (aiogram) async tests. | `packages-list.md` lines 57, 87, 98; Residual Risks (pytest-asyncio strict-mode surprises, LOW) |
| deep-translator | `>=1.11.0` | (none, but wraps Google scrape) | Fragile backend (scrapes Google translate). Requires a hard timeout (~500ms) + mandatory fallback to the original query. Bumping the package can shift the scrape endpoint/behavior and silently change translation reliability; the wrapper contract (timeout + fallback) must be re-validated. | `packages-list.md` lines 34, 49, 86, 93; `spec-index.md` line 32 (Bosnian→Russian query translation) |
| django-filter | `>=26.1` | django (`>=5.2`) | Requires Django 5.2+. Bumping django below the LTS line, or jumping django to 6.0 without re-validating django-filter, breaks list filters. | `packages-list.md` lines 44, 84 |
| django-tailwind | `>=4.4.0` | Tailwind standalone CLI (no Node.js); django (`>=5.2`) | daisyUI is EXCLUDED by project choice (standalone CLI has no plugin support). Bumping without keeping the standalone-CLI/no-Node constraint reintroduces a Node dependency. | `packages-list.md` lines 45, 85, 96 |
| django-htmx | `>=1.19.0` | django (`>=5.2`) | HTMX MPA layer; tied to the Django version line. | `packages-list.md` lines 46, 31 |
| django-environ | `>=0.11.0` | python-dotenv (TRANSITIVE) | python-dotenv must NOT be declared directly — it is pulled transitively. Bumping django-environ can shift the transitive python-dotenv version; declaring python-dotenv explicitly would create a duplicate/conflicting pin. | `packages-list.md` lines 42, 37 |
| aiogram | `>=3.15.0` | Django ORM via `sync_to_async`; pytest-asyncio for tests | No built-in PG FSM storage; the ad dialog persists as an `Ad.DRAFT` row in the shared ORM. Bumping aiogram can change the Bot API surface and async semantics; async tests depend on pytest-asyncio strict mode. | `packages-list.md` lines 48, 84, 94; `spec-index.md` lines 39, 43 |
| gunicorn | `>=26.0` | Django 5.2 + Python 3.14 (sync WSGI) | Sync WSGI server; ASGI deferred. Bumping django to 6.0 or Python must keep gunicorn sync-mode compatibility. | `packages-list.md` lines 62, 72; `spec-index.md` line 38 |

## Cross-Cutting Rule: Validate as a Set

A dependency bump must be evaluated against the **whole set**, not the single package:

1. **Django is the anchor.** Its upper bound `<6.0` protects django-mptt. Any Django bump is a
   coordinated change requiring a django-mptt replacement plan first.
2. **Driver ↔ pooler coupling.** psycopg3 + PgBouncer require `prepare_threshold=None` in
   transaction mode. The driver version and the PgBouncer config are one contract.
3. **Test-stack coupling.** pytest + pytest-asyncio + pytest-django + pytest `minversion` must move
   together; strict mode is mandatory for aiogram async tests.
4. **Transitive pins are intentional.** python-dotenv is purposely undeclared (transitive via
   django-environ). Do not add direct pins that can drift from the transitive one.

## Residual Risks (cross-reference)

The full risk register lives in [packages-list](packages-list.md#residual-risks). Key items that interact with
the couplings above:

| Risk | Level | Mitigation |
|------|-------|------------|
| deep-translator Google-scrape fragility | HIGH | Hard timeout ~500ms + mandatory fallback to original query. |
| aiogram FSM "PostgreSQL storage" misconception | HIGH | Use `Ad.DRAFT` in shared Django ORM; no DB-backed FSM. |
| django-mptt abandonment | MEDIUM | Plan replacement (recursive CTE / django-tree-queries) before Django 6.0; keep `<6.0`. |
| django-tailwind without daisyUI | MEDIUM | Plain Tailwind suffices for MVP. |
| django-storages maintenance-at-risk | LOW | Re-validate at S3/R2 swap. |
| pytest-asyncio strict-mode surprises | LOW | `asyncio_mode="strict"`, `minversion="8.4"` when writing bot tests. |
