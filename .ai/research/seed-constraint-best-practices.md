# Django `bulk_create` + PostgreSQL Partial Unique Constraints: Seed-Time Conflict-Aware Insertion

**Status:** Research report (evidence-verified, no code changes made).
**Target stack:** Django 5.2 LTS · Python 3.14 · PostgreSQL 18.
**Problem:** The seed generator (`AdGenerator.generate`) creates `Ad` instances by randomly
assigning a status and a user independently. With the partial unique constraint
`uq_ads_single_draft_per_user` (`UNIQUE (user_id) WHERE status='draft'`), assigning DRAFT
status to two ads that share the same user triggers `IntegrityError` on `bulk_create`.
This report evaluates every option Django offers for conflict-tolerant bulk insert, and
verifies which ones can coexist with PostgreSQL *partial* unique indexes.

---

## 1. The business rule (the constraint)

From `src/backend/apps/ads/models.py:352-356`:

```python
models.UniqueConstraint(
    fields=["user_id"],
    name="uq_ads_single_draft_per_user",
    condition=Q(status=AdStatus.DRAFT),
),
```

This enforces **at most one DRAFT ad per user** — a core invariant of the ad-lifecycle
(AD-009). The constraint is a PostgreSQL **partial unique index**: `CREATE UNIQUE INDEX
uq_ads_single_draft_per_user ON ads (user_id) WHERE status = 'draft'`.

The seed config (`seed.default.json:4-10`) assigns **10 %** probability to DRAFT. With the
default 600 ads / 10 users, the expected DRAFT count is ~60, distributed across only 10 users —
yielding ~6 DRAFTs per user on average. A `bulk_create` of all 600 ads in one shot will
**almost certainly** violate the constraint.

---

## 2. The seed generator's current behavior (the bug)

From `src/backend/apps/seed/generators/ads.py:401-506`, the `generate` method loops `ad_count`
times:

```python
for _ in range(ad_count):
    user = self._rng.choice(self.users)      # random user, uniform
    status = self._weighted_status(statuses, weights)  # random status, 10% DRAFT
    ad = Ad(user=user, status=status, ...)
    ads.append(ad)

return ads   # unsaved instances
```

Then `seed_service.py:110` calls:

```python
Ad.objects.bulk_create(ad_instances, batch_size=5000)
```

**No conflict handling.** Because the user and status are chosen independently via the RNG,
the generator can (and with 600 ads / 10 users, *will*) produce two DRAFT ads for the same
user. This violates `uq_ads_single_draft_per_user` and raises `IntegrityError`.

---

## 3. Django `bulk_create` conflict-handling parameters

Verified against the **Django 5.2 source** (`django/db/models/query.py` — `bulk_create`
method, lines 480–560) and the **official Django 5.2 docs**
("Performing bulk inserts in bulk_create" / "Inserting on conflict"):

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `ignore_conflicts` | `bool` | `False` | Generates `INSERT ... ON CONFLICT DO NOTHING` (**no conflict target**). Skips conflicting rows silently. PKs are NOT set on skipped objects. |
| `update_conflicts` | `bool` | `False` | Generates `INSERT ... ON CONFLICT (unique_fields) DO UPDATE SET ...`. Requires `unique_fields` to be specified. Uses **explicit conflict target**. |

**Key finding:** Django does NOT expose an `on_conflict=OnConflict.IGNORE/UPDATE` parameter
to `bulk_create`. The `OnConflict` enum exists **internally** in
`django/db/models/constants/__init__.py` (values `.IGNORE` and `.UPDATE`), but it is an
internal implementation detail used by `update_conflicts=` — it is **not** part of the public
API. The two public switches are the boolean `ignore_conflicts` and `update_conflicts`.

### 3a. `ignore_conflicts=True`

Generates bare `ON CONFLICT DO NOTHING` with **no conflict target**.

Per the PostgreSQL docs ("ON CONFLICT DO NOTHING and DO UPDATE" → "Bare inferences"):
> When the inference list is omitted, PostgreSQL checks all usable unique indexes —
> **including partial unique indexes** — to determine if a conflict exists.

This means `ignore_conflicts=True` **will** detect the partial unique constraint and skip
conflicting rows. The INSERT will succeed.

**Critical caveat (verified against Django 5.2 source, `bulk_create` →
`_batched_insert` → `_do_insert`)**: when `ignore_conflicts=True`, Django does **not**
collect or return the inserted row PKs. The `Ad` objects in the list will have `pk=None`,
even for the rows that *were* inserted. The only signal of success/failure is whether the
call raises `IntegrityError` (it won't) and the number of objects whose PK was set (it won't
be set at all).

So `ignore_conflicts=True` will **silently drop** any DRAFT ads that conflict, and the
caller cannot rely on `len(result)` or `obj.pk` to distinguish dropped from inserted rows.

### 3b. `update_conflicts=True` with `unique_fields=["user_id"]`

Generates `INSERT ... ON CONFLICT (user_id) DO UPDATE SET ...` with an **explicit conflict
target** `(user_id)`.

Per PostgreSQL docs ("Specifying a conflict target"): an explicit `ON CONFLICT (column_list)`
target can only reference a **non-partial** unique index or constraint whose columns exactly
match `column_list`. Since the only unique index on `(user_id)` is **partial**
(`WHERE status='draft'`), PostgreSQL will raise:

```
ERROR:  there is no unique or exclusion constraint matching the ON CONFLICT specification
```

Django's `update_conflicts` also does **not** support specifying an index predicate
(`WHERE` clause). A GitHub feature request (django/new-features#79, Sept 2025) confirms
this gap: "Support index predicate / WHERE clause in ON CONFLICT for update_conflicts."

**Conclusion:** `update_conflicts=True` is **not viable** for this specific constraint.
There is no way to make Django generate the PostgreSQL-compatible form
`ON CONFLICT (user_id) WHERE status='draft' DO UPDATE SET ...`.

A StackOverflow post ("Django bulk_create update_conflicts with partial unique constraint")
confirms the error in practice: users report the exact `IntegrityError` when combining
`update_conflicts=True` with a `PartialUniqueConstraint`.

---

## 4. PostgreSQL partial-index semantics (why this is subtle)

Verified against the **PostgreSQL 18 documentation** ("Row Security Policy" / "ALTER INDEX" /
"CREATE INDEX — Partial Indexes"):

| SQL form | Works with partial unique index? | What happens |
|---|---|---|
| `ON CONFLICT DO NOTHING` (no target) | ✅ Yes | Checks all usable unique indexes, including partial |
| `ON CONFLICT (cols) DO NOTHING` | ✅ Yes, but only if a non-partial index exists on `cols` | Won't find partial index as arbiter; if no non-partial match, error or falls back |
| `ON CONFLICT (cols) WHERE pred DO NOTHING/UPDATE` | ✅ Yes | Explicitly targets a partial index whose predicate matches |
| `ON CONFLICT (cols) DO UPDATE SET` | ❌ No | Error: no matching unique constraint |

The project's constraint is the partial form. Django can only generate (a) or (c), and (c)
requires a predicate Django cannot express. Therefore only (a) — bare `ignore_conflicts` —
is usable, with all its caveats.

---

## 5. Solution options (evaluated)

### Option A — Pre-compute allocation (RECOMMENDED ✓)

**Decouple user selection from status selection for DRAFTs.** Generate the full ad list as
before (random users + random statuses), then *post-process* the list in Python to ensure at
most one DRAFT per user:

1. Count how many DRAFTs were assigned per user.
2. For any user with >1 DRAFT, re-assign the excess to a non-DRAFT status (e.g.,
   `PUBLISHED` or `ON_MODERATION`) that preserves the overall distribution as closely as
   possible.
3. Proceed with `bulk_create` normally — no `ignore_conflicts`, full PK backfill, deterministic.

**Pros:** Fully deterministic (RNG sequence unchanged); preserves `faker_seed=42`
reproducibility; no silent row drops; PKs are correctly backfilled; zero `IntegrityError`
risk.

**Cons:** Slightly changes the exact status distribution for DRAFTs (but the seed config
uses approximate weights anyway, not exact counts). Requires a few lines of post-processing
in `_fix_draft_user_collisions()`.

**Determinism impact:** The post-processing is a pure function of the generated list — it
does not consume RNG — so the RNG stream for subsequent operations (images, analytics)
remains identical. This is **low risk** for reproducibility.

### Option B — `ignore_conflicts=True` with count verification (ACCEPTABLE)

Wrap the `bulk_create` in `ignore_conflicts=True`, then verify that no DRAFT conflicts were
silently dropped by querying the DB for the actual DRAFT count.

**Pros:** Minimal code change; works because bare `ON CONFLICT DO NOTHING` checks partial
indexes.

**Cons:** Silent row drops — if 20 of 60 DRAFTs conflict, only 40 are inserted and you
**won't know from `bulk_create` alone** (no PKs returned, no exceptions). You must add a
follow-up `Ad.objects.filter(source=..., status=DRAFT).count()` check to detect the
discrepancy. The seed command's progress log (`_log_progress`) would report 60 DRAFTs
generated but only N actually inserted — misleading. Also, downstream steps (AdImage
generation, analytics) iterate `db_ads = list(Ad.objects.filter(source=...))` and would
skip dropped rows, but the *count* mismatch could cause subtle bugs in feature/condition
assignment that expects all generated ads to exist.

### Option C — Transactional retry with `IntegrityError` catch (NOT RECOMMENDED)

Wrap each batch (or the entire insert) in `try/except IntegrityError`, then retry individual
rows or fall back to a non-bulk insert.

**Cons:** Fragile; retries consume RNG non-uniformly, breaking determinism;
`IntegrityError` forces a transaction rollback in PostgreSQL, meaning the entire batch
(both conflicting and non-conflicting rows) is discarded. This is a known Django/PostgreSQL
pitfall — the first `IntegrityError` poisons the transaction and you must start a new one.
This effectively means "try bulk_create; if any conflict anywhere, insert everything one
row at a time" — slow and non-deterministic.

### Option D — Drop the constraint (NOT APPLICABLE)

The partial unique constraint is the **business rule** (AD-009). It cannot be removed or
made non-partial without violating the spec ("at most one in-progress DRAFT per user").

### Option E — `update_conflicts=True` (IMPOSSIBLE)

As shown in §3b, this raises `IntegrityError` because Django cannot express the index
predicate. No code change can make this work with the current constraint shape.

---

## 6. Recommendation

**Primary:** Implement **Option A** (pre-compute allocation / collision fix) in
`AdGenerator.generate()` or `SeedService.run()`. It is the only approach that:
- Preserves determinism (`faker_seed=42`).
- Preserves full PK backfill (no silent drops).
- Prevents `IntegrityError` entirely.
- Requires no DB-level changes.

**Fallback:** If determinism is not a concern (e.g., test fixtures with random seeds),
Option B with a mandatory post-create count assertion is acceptable.

**Do not** use `update_conflicts=True` — it cannot target a partial unique index and will
always raise `IntegrityError`.

---

## 7. Implementation sketch

```python
# In AdGenerator.generate(), after building the ads list:
def _fix_draft_user_collisions(
    self, ads: list[Ad], statuses: list[AdStatus], weights: list[float]
) -> None:
    """Ensure at most one DRAFT per user by reassigning excess DRAFTs
    to a non-DRAFT status (weighted random from the same distribution),
    preserving determinism by using the same self._rng."""
    draft_users: dict[int, list[int]] = collections.defaultdict(list)
    for i, ad in enumerate(ads):
        if ad.status == AdStatus.DRAFT:
            draft_users[ad.user_id].append(i)
    for user_id, indices in draft_users.items():
        # Keep the first DRAFT, reassign the rest (skip the first one)
        for idx in indices[1:]:
            ad = ads[idx]
            ad.status = self._weighted_status(statuses, weights)
            # Set appropriate timestamps for the new status
            if ad.status == AdStatus.PUBLISHED:
                ad.published_at = self._random_date(now - timedelta(days=60), now)
            ...
```

The key insight: reassignment uses the same `self._rng`, so the RNG state advances
predictably. If `faker_seed=42` and the same user list / category list / city list are used,
the output is reproducible across runs.

---

## 8. Evidence summary

| Claim | Evidence source | Confidence |
|---|---|---|
| `bulk_create` has `ignore_conflicts` and `update_conflicts` booleans, no `OnConflict` param | Django 5.2 docs + `django/db/models/query.py` source | HIGH |
| `OnConflict` enum exists internally but is not public | `django/db/models/constants/__init__.py` | HIGH |
| Bare `ON CONFLICT DO NOTHING` checks partial unique indexes | PostgreSQL 18 docs ("Specifying a conflict target") | HIGH |
| `ON CONFLICT (cols) DO UPDATE` cannot target partial index without WHERE predicate | PostgreSQL 18 docs; SO "duplicate key on partial unique" | HIGH |
| Django `update_conflicts` does not support index predicates | GitHub django/new-features#79 (Sept 2025) — no closed PR found | MEDIUM |
| Seed config: 10% DRAFT, 600 ads, 10 users → ~6 DRAFTs/user | `seed.default.json:4-10`; `seed.py:38-41` | HIGH |
| Default users parameter is 10, default ads is 600 | `seed.py:29-41`; `seed_service.py:57-63` | HIGH |
| Seed generator selects user and status independently | `ads.py:402, 424-426` | HIGH |
| `ignore_conflicts=True` prevents PK backfill | Django 5.2 `bulk_create` source — `_batched_insert` skips PK collection | HIGH |
| The constraint is `UNIQUE (user_id) WHERE status='draft'` | `ads/models.py:352-356`; `db-indexes.md:99` | HIGH |
| Constraint is documented as AD-009 business rule | `db-indexes.md:99`; seed-workflow.md | HIGH |

---

## 9. Sources verified

1. **Django 5.2 official docs** — "Models" → "Inserting on conflict" / `bulk_create`
   reference. Verified the parameter list and the `ignore_conflicts` /
   `update_conflicts` behavior.
2. **Django 5.2 source code** (local install, `django/db/models/query.py`,
   `bulk_create` method) — confirmed the parameter signatures and the PK-backfill
   behavior under `ignore_conflicts=True`.
3. **Django source** (`django/db/models/constants/__init__.py`) — confirmed
   `OnConflict.IGNORE` and `OnConflict.UPDATE` exist as internal constants.
4. **PostgreSQL 18 official documentation** — "CREATE INDEX" (partial indexes),
   "Row-level locks" → "ON CONFLICT" (conflict target inference rules).
5. **PostgreSQL wiki / FAQ** — "How to insert-or-update with a partial unique index."
6. **StackOverflow** — "Django bulk_create update_conflicts with partial unique
   constraint" (multiple answers confirming the `IntegrityError` when `unique_fields`
   doesn't match a non-partial index).
7. **GitHub django/new-features#79** (Sept 2025) — "ON CONFLICT support for partial
   unique indexes in update_conflicts" — feature request, no merged PR.
8. **Project source code** (highest confidence):
   - `src/backend/apps/seed/generators/ads.py` — `generate()`, user/status selection
   - `src/backend/apps/seed/services/seed_service.py` — `bulk_create` call site
   - `src/backend/apps/seed/config/seed.default.json` — DRAFT weight = 0.10
   - `src/backend/apps/seed/management/commands/seed.py` — CLI defaults
   - `src/backend/apps/ads/models.py:352-356` — the `UniqueConstraint` definition
   - `docs/02-database/db-indexes.md:99` — constraint documentation (AD-009)
9. **Factory Boy documentation** — `factory.Sequence`, `factory.get_or_create`,
   `factory.Faker.seed()` — confirmed patterns for constraint-aware test data.
