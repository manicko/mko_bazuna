---
id: cache-strategy
domain: architecture
tags:
  - cache
  - swr
  - stale-while-revalidate
  - single-flight
  - cache-key
  - invalidation
related:
  - rules
  - architecture
  - search-patterns
source_reference: .ai/plans/14-performance-fixes.md
finding: 13-PERF-006
---

# Cache Strategy & Key Naming Convention

## Purpose

This document defines the cache-key naming convention and invalidation strategy
decision matrix for Mko Bazuna. It exists to eliminate the three divergent
invalidation strategies that previously coexisted without a documented convention
(13-PERF-006).

The core principle: **invalidation method is determined by access pattern**.
Buyer-facing hot-path caches use version-bump embedded in the key (never a global
prefix wipe, which causes thundering-herd). Cold reference-data caches may use
prefix-wipe because a stampede on cheap reads is acceptable.

## Key Format

All cache keys follow the format:

```
<namespace>:v<N>:<segments...>
```

- **`<namespace>`** — dot-free identifier matching the domain owning the cache
  (e.g. `search`, `category`, `lookup`).
- **`v<N>`** — version segment immediately after the namespace. Bumped via
  `cache.incr` (atomic on Redis, thread-safe on LocMemCache) with a fallback
  to `cache.set` when the key does not yet exist.
- **`<segments...>`** — the remaining key components: version counters, locale,
  hashed query/fILTER data, slugs, IDs, etc.

The version segment is **never** a prefix-wipe trigger for hot-path caches.
Instead, incrementing the version changes the key itself, making old entries
unreachable. They expire via TTL in the background.

## Invalidation Strategy Decision Matrix

| Access pattern | Strategy | Locale segment | SWR | Mechanism | Rationale |
|---|---|---|---|---|---|
| Buyer-facing / hot render path (search results, category submenu) | Version-bump | Required | Recommended | `cache.incr` on a version key; old keys expire via TTL | A prefix wipe on the hot path causes a thundering-herd: the first N concurrent requests all miss and recompute simultaneously. Version-bump makes old keys unreachable without a global delete, so only the first request after the bump recomputes (single-flight) while others serve stale-then-fresh. |
| Cold / cheap reference data (lookup groups, lookup items, resolved purposes) | Prefix-wipe acceptable | Not required | Recommended (prevent stampede) | `invalidate_by_prefix()` (Redis-only) or per-key `cache.delete` | Cold reference data is read infrequently and is cheap to recompute. A prefix wipe is safe here because the stampede risk is low — but SWR is still recommended to prevent even a brief stampede on the single recompute. |

### When to add a new cache

1. Determine whether the cache sits on a **buyer-facing hot render path**
   (loaded on every listings/search page render). If yes → version-bump.
2. If the recompute is expensive (FTS query, MPTT walk, join-heavy) → wrap in
   `get_with_stale_revalidate` (SWR + single-flight).
3. If the cache key is locale-sensitive (different buyer content per language)
   → include the locale segment.
4. If the cache is cold / cheap reference data → a prefix-wipe is acceptable,
   but SWR is still recommended to prevent a stampede on invalidation.

## SWR Parameters

Expensive cache recomputes (any cache that runs a DB query, FTS search, or
MPTT traversal) must use
`apps/core/utils/swr_cache.py:get_with_stale_revalidate(key, producer, *, ttl, stale_ttl, lock_ttl, default=None, max_size_bytes=None)`.

The function implements a three-state machine:

1. **Fresh hit** (`age < ttl`) — return cached value immediately.
2. **Stale hit** (`ttl <= age < ttl + stale_ttl`) — serve stale value to the
   caller immediately; the single "winner" worker (first to win `cache.add`
   on the lock key) recomputes via `producer` and overwrites the entry. Losers
   simply return the stale value they already served.
3. **Cold miss** (no entry, or past the stale window) — first worker to win
   `cache.add(lock_key)` runs `producer` synchronously and stores the result.
   Concurrent losers with no stale value receive `default`.

### TTL tuning

| Parameter | Role | Requirement | Reference values |
|---|---|---|---|
| `ttl` | Fresh lifetime (seconds) | — | Search: 300 (5 min) |
| `stale_ttl` | Stale-serve window after TTL (seconds) | — | Search: 60 (1 min) |
| `lock_ttl` | Single-flight lock TTL (seconds) | **Must be < `stale_ttl`** | Search: 30 |

**Critical invariant:** `lock_ttl < stale_ttl`. This ensures a crashed or
slow worker releases the single-flight lock (via TTL expiry) **before** stale
data expires. If `lock_ttl >= stale_ttl`, a stuck worker could hold the lock
permanently, preventing revalidation and leaving stale data unserved past its
window.

The search cache (`apps/search/services/cache.py:44-46`) is the proven
reference: `ttl=300`, `stale_ttl=60`, `lock_ttl=30`.

### Single-flight cross-process note

- **Redis (production):** `cache.add` is a true distributed lock — single-flight
  coordinates across all 3 gunicorn workers + the bot process.
- **LocMemCache (dev/test):** `cache.add` is per-process only — single-flight is
  intra-process. The stale-serve path is still exercised by tests. This is an
  inherent limitation of `LocMemCache`, not a bug in the SWR utility.

## Locale Segmentation

Buyer-facing cache keys **must** include the `LanguageLocale` segment for the
current buyer. Two buyers with different language preferences must never read
the same cache entry — a Russian-rendered search result set must not be served
to a Bosnian visitor.

The locale segment is placed after the version segment and before any
query/content hashes:

```
<namespace>:v<N>:<version_counter>:<locale>:<...segments>
```

## Version-Bump Mechanism

Version-bump invalidation uses `cache.incr` with a `ValueError` fallback to
`cache.set`:

```python
try:
    cache.incr(VERSION_KEY)
except ValueError:
    cache.set(VERSION_KEY, 1)
```

- **`cache.incr` is atomic on Redis** (production) — true cross-process
  increment with no race window.
- **`cache.incr` is thread-safe on LocMemCache** (dev/test) — Django's
  LocMemCache acquires a per-key lock around the increment operation.
- The `ValueError` fallback handles the first increment when the key does not
  yet exist (Redis `INCR` returns `NOTINT` which Django surfaces as `ValueError`).

This mechanism **does not depend on `delete_pattern`** and works on both cache
backends. It is the pattern used by:

- `apps/search/services/cache.py` — `bump_search_version()` /
  `get_search_version()` (content version)
- `apps/categories/cache.py` — `bump_tree_version()` / `get_tree_version()`
  (tree structure version)

## Pattern-Based Invalidation (`invalidate_by_prefix`)

For caches that use a prefix-based key structure (e.g.
`category:submenu:{tree_version}:{slug}:{locale}`), use
`apps/core/utils/swr_cache.py:invalidate_by_prefix(prefix)` to invalidate all
entries whose key starts with `prefix`.

**Redis-only:** `invalidate_by_prefix` calls `cache.delete_pattern(f"{prefix}*")`,
which is a Redis-only API. Under `LocMemCache` (dev/test), `delete_pattern`
does not exist and the function logs a debug message and returns without
invalidating — it is a **no-op**.

Do not write unit tests that assert cache state after `invalidate_by_prefix`
under `LocMemCache` — the autouse `_clear_cache_between_tests` fixture handles
isolation instead.

## Existing Patterns

### 1. Search results cache (reference — version-bump + SWR + locale)

| Attribute | Value |
|---|---|
| Module | `apps/search/services/cache.py` |
| Key format | `search:v1:{content_version}:{locale}:{query_hash}:{filters_hash}` |
| Version key | `search:content_version` |
| Bump function | `bump_search_version()` (calls `bump_search_version`) |
| Read function | `get_search_version()` |
| SWR wrapper | `get_cached_search_ids()` → `get_with_stale_revalidate()` |
| `ttl` | 300 s (`SEARCH_CACHE_TTL`) |
| `stale_ttl` | 60 s (`SEARCH_CACHE_STALE_TTL`) |
| `lock_ttl` | 30 s (`SEARCH_CACHE_LOCK_TTL`) |
| Invalidation trigger | `apps/search/signals.py` on `Ad` publish/status transition |

**Key segments:**

- `search:v1` — namespace + version (version-bump via content version).
- `{content_version}` — monotonically incremented counter; bumped on every
  buyer-visible ad change (status transition, content edit, feature M2M change).
- `{locale}` — `LanguageLocale` enum value; per-language FTS query isolation.
- `{query_hash}` — SHA-256 of the query string, truncated to 16 hex chars.
- `{filters_hash}` — SHA-256 of JSON-serialized filter params (category, city,
  price range, purpose, condition, features, sort, per_page) with sorted keys.

> `page` is intentionally excluded — the cache stores the complete ordered
> result set (up to `SEARCH_CACHE_MAX_HITS=1000`); pagination is handled by
> Django's `Paginator` on the re-fetched queryset.

### 2. Category submenu cache (reference — tree-version bump + locale)

| Attribute | Value |
|---|---|
| Module | `apps/categories/cache.py` |
| Key format | `category:submenu:{tree_version}:{slug}:{locale}` |
| Version key | `category:tree_version` |
| Bump function | `bump_tree_version()` |
| Read function | `get_tree_version()` |
| TTL | 300 s (`SUBMENU_CACHE_TTL`) |
| Invalidation trigger | Category / CategoryPath structural changes |

**Key segments:**

- `category:submenu` — namespace prefix (no `v<N>` version segment; the
  tree version serves the same purpose).
- `{tree_version}` — monotonically incremented counter; bumped on any
  structural Category / CategoryPath change.
- `{slug}` — category slug identifying which submenu fragment.
- `{locale}` — `LanguageLocale` enum value; prevents cross-language fragment
  bleed (a Russian-rendered submenu must not serve a Bosnian visitor).

### 3. Lookup caches (v1 — SWR + version-bump, aligned to convention)

These caches now conform to the documented convention. All reads route
through ``get_with_stale_revalidate`` (single-flight + stale-serve) and
invalidation uses version-bump (``cache.incr``) — no prefix wipe.

#### Lookup groups & active items

| Attribute | Value |
|---|---|
| Module | `apps/lookups/services/cache_service.py` |
| Class | `LookupCacheService` |
| Key format | `lookup:v1:{content_version}:all_groups`, `lookup:v1:{content_version}:items:{group_code}` |
| Version key | `lookup:content_version` |
| Bump function | `bump_lookup_version()` |
| Read function | `get_lookup_version()` |
| SWR wrapper | `get_with_stale_revalidate()` |
| `ttl` | 3600 s |
| `stale_ttl` | 600 s |
| `lock_ttl` | 30 s |
| Invalidation trigger | `apps/lookups/signals.py` on `LookupGroup`/`LookupItem` save/delete |

```
LookupCacheKey.V1 = "lookup:v1"
LOOKUP_CONTENT_VERSION_KEY = "lookup:content_version"
```

#### Resolved category lookups

| Attribute | Value |
|---|---|
| Module | `apps/categories/services/lookup_resolution.py` |
| Class | `CategoryLookupResolver` |
| Key format | `lookup:v1:resolve:{content_version}:{segment}:{category_id}` where `segment` ∈ `purposes`, `features`, `conditions` |
| Version key | `lookup:resolve_version` |
| Bump function | `bump_lookup_resolve_version()` |
| Read function | `get_lookup_resolve_version()` |
| SWR wrapper | `get_with_stale_revalidate()` |
| `ttl` | 300 s |
| `stale_ttl` | 60 s |
| `lock_ttl` | 30 s |
| Invalidation trigger | `apps/categories/signals.py` on `LookupItem` save, through-model save/delete, `Category` structural change |

```
LookupResolveCacheKey.V1 = "lookup:v1:resolve"
LOOKUP_RESOLVE_VERSION_KEY = "lookup:resolve_version"
```

## Summary of Correct SWR API Names

| Function | Module | Purpose |
|---|---|---|
| `get_with_stale_revalidate` | `apps/core/utils/swr_cache.py:67` | SWR + single-flight cache read |
| `invalidate_by_prefix` | `apps/core/utils/swr_cache.py:208` | Pattern-based invalidation (Redis-only, no-op under LocMemCache) |

These are the only public entry points in `swr_cache.py`. Older references to
`swr_get` / `swr_set` in `rules.md` are **obsolete** — no such functions exist
in the module.
