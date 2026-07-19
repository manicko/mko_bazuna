# Docker Environment Research: PostgreSQL 18 + Python 3.14 Baseline Verification

**Status:** Research complete — decision guidance for owner's request  
**Date:** 2026-07-18  
**Scope:** Verify whether PostgreSQL 18 + Python 3.14 is a correct, production-appropriate baseline for the mko_bazuna classified ads MVP (Russian FTS, plpgsql triggers, pg_trgm).

---

## Evidence Table (Claims → Sources → Verdict)

| # | Claim / Question | Source / Evidence | Verdict |
|---|------------------|-------------------|---------|
| Q1 | **Python 3.14 status in 2026** | Python.org: Python 3.14.0 released Oct 7, 2025 (PEP 745). Version 3.14.6 released June 10, 2026. Stable GA release. | ✅ **VERIFIED** — Python 3.14.6 is current stable (July 2026). Fully production-appropriate. |
| Q2 | **Django support for Python 3.14** | Django FAQ (5.2): Django 5.1 supports Python 3.10–3.13 only (3.14 NOT supported). Django 5.2 supports Python 3.10–3.14 **as of 5.2.8**. Django 6.0 supports Python 3.12–3.14. Django download page: 5.2 LTS mainstream support ended Dec 2025, extended support to April 2028. | ✅ **VERIFIED** — Django 5.1 *does NOT* support Python 3.14. Use **Django 5.2.8+** or **Django 6.0** for Python 3.14. |
| Q3 | **psycopg3 support for Python 3.14** | psycopg.org docs: "Python: from version 3.10 to 3.14" (Psycopg 3.2+). PyPI shows `psycopg_binary-3.2.10-cp314-cp314-win_amd64.whl` and `cp314` wheel variants available. psycopg-binary 3.2.x has Python 3.14 wheels for Linux, macOS, Windows. | ✅ **VERIFIED** — psycopg[binary]>=3.2 provides Python 3.14 wheels. No known compatibility issues. |
| Q4 | **PostgreSQL 18 GA status / Docker image** | PostgreSQL.org: "PostgreSQL 18 Released! (2025-09-25)". Docker Hub: `postgres:18` and `postgres:18-alpine` images available. PostgreSQL 19 Beta 2 released July 16, 2026 confirms PG18 is stable. | ✅ **VERIFIED** — PostgreSQL 18 GA released Sep 25, 2025. Both `postgres:18` and `postgres:18-alpine` Docker images available. Production-ready. |
| Q5 | **Russian locale / collation fixes in PG18** | PG18 release notes: "Change full text search to use the default collation provider of the cluster to read configuration files and dictionaries, rather than always using libc." Also: "Change full text search to use the default collation provider of the cluster... for characters processed by LC_CTYPE" and "pg_trgm extension behavior may change." PG_UNICODE_FAST collation added. Docker Hub postgres README: "Alpine-based variants starting with Postgres 15 support ICU locales." | ⚠️ **PARTIALLY CORRECT** — PG18 improves locale handling but FTS vs collation relationship is nuanced. See detailed analysis below. |
| Q5b | **PG18 Russian FTS locale dependency** | PG18 release notes: FTS uses text-search *dictionaries/configurations* (snowball stemmer for 'russian'), not directly LC_COLLATE/LC_CTYPE. However, the stemmer's lowercasing behavior now respects the cluster's default collation provider. The Russian snowball dictionary is part of PostgreSQL's text search system and is largely independent of OS locale. | ⚠️ **CLARIFIED** — `to_tsvector('russian', ...)` uses the Russian text search configuration/snowball stemmer, which is predefined in PostgreSQL and NOT dependent on OS locale. HOWEVER, case-folding in FTS tokens now respects the cluster's collation provider (ICU/builtin/libc) in PG18. |

---

## Recommendation

### Final Coherent Version Tuple

| Layer | Recommended Version | Rationale |
|-------|---------------------|-----------|
| **Python** | `3.14` (latest stable, `python:3.14-slim`) | GA since Oct 2025 (3.14.6 current in mid-2026). Well-supported wheels for all key packages. |
| **Django** | `>=5.2.8,<6.0` (i.e. the **Django 5.2.x LTS** series) | Python 3.14 support was added in **Django 5.2.8**; staying in the 5.2.x LTS series keeps the LTS guarantee (extended support until **April 2028**). Do NOT pin a single patch (`5.2.16`) — pin the LTS series `>=5.2.8,<6.0` so bugfix/security patches flow in. Contains all required features (native psycopg pool, LoginRequiredMiddleware, STORAGES, {% querystring %}). Django 6.0 also supports 3.14 but is NOT LTS — avoid for MVP. |
| **psycopg** | `psycopg[binary]>=3.2.0` | Full Python 3.14 (cp314) wheel support, native Django 5.2+ pool integration via OPTIONS. |
| **PostgreSQL image** | `postgres:18` (Debian-based, NOT alpine) | For Russian content, use Debian-based image with ICU support. See locale recommendations below. |

### Recommended initdb Locale Settings for Russian FTS MVP

```yaml
# docker-compose.yml db service
environment:
  POSTGRES_INITDB_ARGS: "--locale-provider=icu --icu-locale=ru-RU"
# OR, safer cross-platform alternative:
# POSTGRES_INITDB_ARGS: "--locale-provider=icu --icu-locale=ru"
```

**Why ICU for Russian:**

1. **ICU is independent of OS locale** — Works identically on Alpine and Debian, no musl/libc dependency.
2. **Russian ICU locale (`ru-RU` or `ru`) is available** in PostgreSQL 15+ alpine images (per Docker Hub docs).
3. **PG18+ supports ICU as default collation provider** at cluster level (PG15 added this capability).
4. **PG18 FTS/collation behavior change** — PG18 changes full-text search to use the **cluster's default collation provider** (ICU/builtin/libc) for reading configuration files/dictionaries and for `LC_CTYPE`-driven character processing, rather than always using libc. Extensions that depend on collation (including `pg_trgm`) **may change behavior** and their indexes should be **reindexed after upgrade** (per PG18 release notes). NOTE: this is a *behavioral change requiring reindex*, not a targeted "pg_trgm respects column-collation OID" fix — that separate enhancement is NOT part of PG18 GA.
5. **Future-proof** — ICU ensures consistent sorting across platforms, solving the `ru_RU.UTF-8` glibc collation-version mismatch warnings.

**Important caveat on alpine:** While PostgreSQL 15+ alpine builds include `--with-icu` (per the official PostgreSQL 18 alpine Dockerfile), **musl libc still has known limitations** for non-C locales. Using `--locale-provider=icu` sidesteps musl entirely, but for MVP simplicity and to avoid any edge-case issues, the **Debian-based `postgres:18` image is recommended** over `postgres:18-alpine`.

---

## Russian FTS vs Locale Clarification (The Crux)

### What `to_tsvector('russian', ...)` Actually Depends On

| Feature | Locale Dependency | PG18 Change | Notes |
|---------|------------------|-------------|-------|
| `to_tsvector('russian', text)` | **None for stemming** | No change | Russian snowball stemmer is built-in; `russian` text search config is predefined. Lowercasing uses Unicode rules in PG18 (better for Cyrillic). |
| `pg_trgm` similarity/GIN indexes | **Tied to collation** | **Behavior may change in PG18** | PG18 changes FTS/collation-dependent processing to use the cluster's default collation provider; `pg_trgm` behavior may change and its indexes should be reindexed after upgrade. (This is NOT a "respect column-collation-OID" fix — that separate enhancement is not in PG18 GA.) |
| `ORDER BY name` (Russian strings) | **Direct dependency on LC_COLLATE / collation provider** | No change | Sorting relies on collation provider. ICU `ru-RU` (or libc `ru_RU.UTF-8`) required for correct Russian sort order. |
| LIKE pattern matching with non-ASCII | **Depends on LC_CTYPE** | No change | ICU or proper libc locale needed for correct character class handling (`[а-я]` etc). |

**Key insight:** The owner's premise is **partially correct**:

- **FTS stemming itself** (`to_tsvector('russian', ...)`) is **NOT dependent on DB locale** — it uses PostgreSQL's built-in Russian snowball dictionary.
- **Collation-dependent features** (sorting, pg_trgm similarity, LIKE character classes) **DO benefit from PG18 + ICU**:
  - PG18 changes FTS/collation-dependent processing to use the cluster's default collation provider; `pg_trgm` behavior may change and indexes should be reindexed after upgrade.
  - ICU provides consistent Russian collation without glibc version mismatch warnings.
  - `--locale-provider=icu --icu-locale=ru-RU` is the safest configuration for Russian content.

---

## Risks Section

### 1. Alpine / musl Locale Limitations (MED)
- **Risk**: musl libc historically lacks full locale support. Per Docker Hub README: "Previous Postgres versions based on alpine do *not* support locales; see musl documentation."
- **Mitigation**: PostgreSQL 15+ alpine images include `--with-icu` build flag. Setting `--locale-provider=icu` sidesteps musl, but Debian-based `postgres:18` remains the safer choice for production.

### 2. Collation-Version Mismatch Warnings (LOW)
- **Risk**: libc `ru_RU.UTF-8` locale can trigger "collation version mismatch" warnings when glibc is updated.
- **Mitigation**: ICU provider eliminates this — ICU data is bundled with PostgreSQL and versioned independently.

### 3. Python 3.14 Wheel Availability (LOW → RESOLVED)
- **Risk**: Some third-party packages may lack Python 3.14 wheels at MVP time.
- **Verification**: As of psycopg 3.2, wheels for Python 3.14 (cp314) exist. aiogram requires only Python >=3.9 and has no compiled extensions. Pillow and other pure-Python deps are unaffected.

### 4. Migration Complexity (LOW)
- **Risk**: Reindexing required when upgrading to PG18 with non-libc collation provider (per release notes).
- **Mitigation**: Fresh DB for MVP; document reindex step for future upgrades (`REINDEX DATABASE dbname;`).

### 5. PG18 Data Checksums Enabled by Default (LOW for greenfield / MED for future upgrades)
- **Change**: Databases initialized with PostgreSQL 18 `initdb` have **data page checksums enabled by default** (previously off). This is not a problem for a fresh MVP cluster, but it IS a consideration when restoring/upgrading from an older (checksum-disabled) cluster: `pg_upgrade` requires matching checksum settings (use `--copy`/`pg_checksums` or enable checksums on old cluster first).
- **Mitigation**: Greenfield MVP starts on PG18 with checksums on (a positive — silent-corruption detection at ~small overhead). Document that any future in-place upgrade or `pg_dump`/restore across checksum boundaries must account for this.

---

## Required Document Changes (Concrete Checklist)

### 1. `pyproject.toml` Changes

```toml
# BEFORE (current pyproject.toml):
requires-python = ">=3.14"
dependencies = [
    "django>=6.0.1",
    "psycopg2-binary>=2.9.11",
]

# AFTER (recommended — pin the Django 5.2.x LTS series, NOT a single patch, NOT 6.0):
requires-python = ">=3.14"
dependencies = [
    "django>=5.2.8,<6.0",     # Django 5.2.x LTS: first 3.14-capable series (5.2.8), LTS to Apr 2028
    "psycopg[binary]>=3.2.0",
]
```

### 2. `docker/Dockerfile` Base Image

```dockerfile
# BEFORE:
FROM python:3.14-slim

# AFTER (recommended):
FROM python:3.14-slim  # or python:3.14-alpine if using ICU
# No change needed to Python version, but ensure psycopg[binary]>=3.2 in uv.lock
```

### 3. `docker-compose.yml` DB Image

```yaml
# BEFORE (per docs/wiki/architecture-structure.md line 84):
db:
  image: postgres:17-alpine

# AFTER (for PG18 + Russian locale):
db:
  image: postgres:18  # Debian-based, more reliable ICU (NOT alpine/musl)
  environment:
    POSTGRES_INITDB_ARGS: "--locale-provider=icu --icu-locale=ru-RU"
  # Note: PG18 initdb enables data page checksums by default (fresh MVP cluster = fine).
```

### 4. `docs/wiki/packages.md` Updates

- Line 14: Change `django==5.1.2` to `django>=5.2.8,<6.0` (Django 5.2.x LTS — first series supporting Python 3.14; LTS to April 2028).
- Line 17: `psycopg[binary]>=3.2.0` is already the intended dependency in the wiki; ensure `pyproject.toml` matches it (current `pyproject.toml` has the conflicting `psycopg2-binary` — must be swapped).
- Add note: "Django 5.2.8+ (5.2.x LTS) required for Python 3.14. Django 6.0 also supports 3.14 but is not LTS; MVP stays on 5.2 LTS."

### 5. `docs/wiki/architecture-structure.md` Updates

- Line 96: `python:3.14-slim` — acceptable; keep.
- Line 84: `postgres:17-alpine` — change to `postgres:18` with `POSTGRES_INITDB_ARGS: "--locale-provider=icu --icu-locale=ru-RU"`.
- Line 104: PgBouncer note remains optional; psycopg3 native pool via OPTIONS supports both.

### 6. `docs/wiki/db-structure.md` Updates

- No structural changes needed; the plpgsql triggers and FTS logic remain valid.
- Add note in search_vector section: "On PostgreSQL 18, FTS/collation-dependent processing uses the cluster's default collation provider; reindex `ads` GIN and `pg_trgm` indexes after any PG18 collation-provider change/upgrade (per PG18 release notes). Fresh MVP cluster initialized on PG18 with ICU needs no reindex."

### 7. `docker_env_decision_00_prioritized.md` Updates (C1 Resolution)

- **Decision C1** (lines 77-81): Revise to acknowledge Python 3.14 is GA and acceptable.
- Change recommendation from "Django 5.2 LTS + Python 3.13" to "Django 5.2.x LTS (>=5.2.8) + Python 3.14".
- Update PostgreSQL version references from 17 to 18 throughout, and add the ICU initdb locale (`--locale-provider=icu --icu-locale=ru-RU`) + PG18 default page-checksums note.

---

## Verdict Summary

| Aspect | Owner's Claim | Evidence Verdict | Recommendation |
|--------|---------------|------------------|----------------|
| PostgreSQL 18 availability | Implied "latest" | ✅ GA since Sep 2025, Docker images available | **ACCEPT** — use `postgres:18` |
| Python 3.14 availability | Implied "latest" | ✅ GA since Oct 2025, 6 patch releases | **ACCEPT** — use 3.14.6 |
| Django 5.1 + Python 3.14 | Implicit in current pyproject.toml | ❌ Incompatible | **FIX** — use Django 5.2.x LTS (`>=5.2.8,<6.0`); 6.0 also works but is not LTS |
| Russian FTS locale issues | "earlier versions have problems" | ⚠️ Partially correct — FTS stemmer is locale-independent, but **sorting and pg_trgm benefit from PG18 ICU** | **ACCEPT with clarification** — ICU fixes real issues (sorting, pg_trgm), FTS stemmer is unaffected but consistently uses Unicode rules in PG18 |
| Alpine safety for Russian | Unmentioned | ⚠️ ICU sidesteps musl, but Debian recommended | **MITIGATE** — use `postgres:18` (Debian) or ICU initdb args if alpine |

---