# Plan 23 — `KEY_COLUMNS` ownership: one vocabulary, three independent predicates

**Phase:** 07 media remediation · **Kind:** maintenance / ownership refactor · **Priority:** P3
**Status:** **shipped** (Phase 0–3) — all code committed, plan 20 deferral corrected, db docs checked. See §11.

---

## 1. Purpose, owner, ruling, origin

### Purpose

Give the `AdImage` key-column name list a single owner, so that adding a fifth key
column is a change to *one* constant instead of a silent divergence across nine
enumeration sites — **without** merging the predicates built on top of it.

### The owner's ruling

This is an **ownership / maintenance task**, explicitly **not** a correctness fix.

- It is **not** pulled toward `media_gate`, and it must not absorb any part of the
  deployed-media-gate work.
- The consolidation must leave the sites **semantically independent**.
- **Owner: storage / query schema.** `AdImage`'s key-column vocabulary is a
  storage-schema fact; the predicates layered on it belong to their sites.
- BLOCK 10 effectively skipped it — see §3.

### Origin — BLOCK 2b's orphaned deferral

`.ai/plans/done/20-media-remediation-execution_done.md` (BLOCK 2b, commit-body item 6) ships this
deferral verbatim:

> `sweep_orphaned_media._collect_referenced_keys` and `media_gate`'s `key_q` still
> duplicate the four column names and do **not** yet consume `KEY_COLUMNS`. They
> perform *different* predicates and BLOCKS 7, 8 and 10 have file edges on those
> modules, so consolidation is deferred to the **BLOCK 10 census**.

BLOCKS 7 and 8 shipped without touching the duplication. BLOCK 10 could not take it.
The deferral is therefore live, orphaned, and this plan retires it.

---

## 2. The framing correction (read this before touching any code)

**The deferral's clause "They perform *different* predicates" is half right, and the
half it gets wrong is what made this look like a predicate problem instead of a
vocabulary-ownership problem.**

The sites are **not** three semantically independent predicates. They are:

> **one shared key-membership predicate, expressed three times, plus two independent
> site-specific semantics.**

For a single non-empty key `k`, `not AdImage.objects.filter(key_q).exists()` and
`k not in unreferenced_keys([k])` enumerate the **identical** four columns:

- `Q(col__in=[k])` ≡ `Q(col=k)` for a singleton;
- the falsy-candidate filter is inert, because `media_gate`'s path converter requires
  a non-empty segment, so an empty key can never reach it.

So the key-membership half is a **tautology across sites**. What genuinely differs:

| Independent semantic | Site | What it is |
|---|---|---|
| **Authorisation** | `media_gate` | An *orthogonal* predicate: `ad__status=PUBLISHED`, `ad__user__is_declined=False`. Site 1 has no notion of it. |
| **Census vs probe** | `sweep_orphaned_media` | A *whole-table* projection consumed as a filesystem set-difference (`on_disk - referenced`), not a per-candidate answer. |

### Why this makes constant-only *correct*, not merely cautious

Because the predicates are tautologous in their key-membership half, there is nothing
to gain by unifying query construction and something specific to lose:

- `media_gate` must keep `SELECT 1 … LIMIT 1`. `unreferenced_keys` terminates in a
  per-key `.values_list(*4)` projection; on a shared seed key with many matching rows
  that is a material regression on a hot authorisation path.
- `sweep_orphaned_media`'s census must stay **textually distinct** from the candidate
  probe. That textual distinction is the only thing separating them — replacing the
  census with a candidate-filtered query would **delete every file outside the
  candidate list**.
- The authorisation filter must **never** be folded into a shared helper; collapsing
  them would make unpublished/declined ads' images publicly readable.

**Binding decision D1 — CONSTANT-ONLY.** Share the vocabulary; each site keeps its own
query shape verbatim. The residual ~12 lines of visible, greppable four-way `Q` chains
are **preferable** to an authorisation decision depending on a shared helper's default
arguments. Do not "fix" this.

---

## 3. Why BLOCK 10 skipped it — scope mismatch, evidenced

BLOCK 10 was a **documentation** census. Its declared surface
(`20-media-remediation-execution.md`, BLOCK 10 → *Surface*) contains exactly one code
file: `src/backend/apps/ads/views/edit.py`, restricted to **docstrings and comments
only, no behaviour**. None of the five code sites is in it. Its binding constraint 12
reads: **"No behavioural tests."** Its required tests: **None** — verification is a
Validator read-through against named symbols.

A code consolidation cannot be delivered by a documentation census that excludes
behavioural tests. This is a **scope mismatch, not an oversight**.

> **⚠ Homonym warning.** "Census" is used for two different things here: a **code**
> census (enumerate the sites that enumerate key columns) and a **documentation**
> census (enumerate stale doc sentences). BLOCK 2b's deferral pointed at a *code*
> census; BLOCK 10 was a *documentation* census. Anyone re-reading the deferral must
> not read BLOCK 10 as having discharged it.

---

## 4. Why this is maintenance, not urgency

The duplication is real and worth fixing. It is **not** on fire.

**The drift claim is backwards, and worse than assumed.** `AdImage.storage_keys()` is a
hardcoded four-name literal with **no reference to** `KEY_COLUMNS`. Adding a fifth key
column therefore changes **neither** side, and the suite **stays GREEN**.

Consequences if a fifth key column is added and the vocabulary is not updated:

| Site | Silent failure | Severity |
|---|---|---|
| `sweep_orphaned_media` | New size's files treated as orphans and **deleted** | 🔴 **DATA LOSS** |
| `media_gate` | New size's key **404s** — site-wide broken images | 🔴 High |
| `plan_staging_promotion` | Staged file never promoted — permanent orphan | 🟠 Medium |
| `backfill_thumbnails._SIZE_COLUMNS` | New size never backfilled | 🟠 Medium |
| `KEY_FORMAT_REGEX` | Not load-bearing: it does not encode size names, so `-xlarge.jpg` passes it | ℹ️ Informational |

**Why it is not urgent: a fifth size is not reachable today.** `ThumbnailSizeStrEnum`,
`ThumbnailService.SIZES`, `backfill_thumbnails._SIZE_COLUMNS` and `AdImage` all have
exactly three thumbnails. Introducing a fifth size is a **multi-file change with a
migration**, and whoever does it must touch all of them anyway. The failure table above
is the *cost of that change done carelessly*, not a live defect.

There is also a real chance the consolidation is **redundant**: if the Implementor's
loop conversion of `AdImage.storage_keys()` reads attribute names from `KEY_COLUMNS`,
the literal disappears, and the relational test — which populates live model
attributes from the constant via `AdImage.__new__(AdImage)` — then goes **RED** on
column add / reorder / typo. The gap is **one assertion, not a guard**.

---

## 5. Work items

Targets are semantic units only (files, modules, classes, functions, constants). No line
numbers are targets anywhere in this plan; `file:line` appears only as finding evidence.

### Phase 0 — Guard first, and prove it red (NO production code)

**Surface:** `src/backend/apps/media/tests/test_references.py` — the
`TestKeyColumnsAntiDrift` class.

- **Add** the two assertions specified in §7 (derivation set-equality; positive index +
  regex-constraint coverage).
- **Keep** `test_every_key_column_resolves_to_a_concrete_model_field` unchanged.
- Add the assertions **against the unconsolidated tree** — no leaf module, no consumer
  converted.
- **Demonstrate RED**: scratch-add a fifth key column **and** a
  `ThumbnailSizeStrEnum` member, run the assertions, observe failure, revert the scratch
  edits.
- **A guard never seen red is not a guard.** Capture the red output in the commit body.
- **Hard gate:** if the assertions do **not** go red under the scratch mutation, stop and
  report — the guard is not load-bearing and the plan's premise in §4 is wrong.

**Binding constraints**
1. No production file may change in Phase 0.
2. The scratch mutation must be reverted in the same change; the diff must contain only
   `test_references.py`.
3. **Phase 0's "these assertions go red" is a PREDICTION from reading code, not a
   measurement.** The Researcher did not run the suite. The Implementor must produce the
   evidence; the plan does not assert it.

**Acceptance criteria**
- `test_references.py` green on the unconsolidated tree.
- Recorded red output from the scratch mutation, in the commit body.
- `ruff` and `basedpyright` clean on the test file.

### Phase 1 — Create the leaf vocabulary module

**Surface:** new file `src/backend/apps/media/storage_keys.py` (§6);
`src/backend/apps/media/services/references.py` — the module docstring and the
`KEY_COLUMNS` declaration.

- Move `KEY_COLUMNS` into the new leaf.
- `references.py` **imports and re-exports** it, so every existing import path
  (`from apps.media.services.references import KEY_COLUMNS`) and every test keeps
  working **unedited**. Grep-verified consumers: `references.py` itself and
  `apps/media/tests/test_references.py` only.
- `unreferenced_keys`'s inline four-way `Q` **stays inline, byte-for-byte unchanged**
  (evidence: `references.py` `key_q` construction and the `.values_list(*KEY_COLUMNS)`
  projection). Only the constant's provenance changes.
- Update the `references.py` docstring's duplication paragraph so it names the new owner.

**Binding constraints**
1. **Zero `apps.*` imports in the leaf.** NOT zero imports — `django.*` and stdlib are
   permitted (`apps/core/enums.py` imports Django and is still a cycle-free vocabulary
   leaf). Zero imports would be the wrong invariant.
2. No model access, no module-level side effects.
3. Re-export preserves every current import path. Do **not** update the existing test's
   import — its unedited survival is the backwards-compatibility evidence.
4. Do **not** touch `services/__init__.py` (its docstring scopes it to filesystem
   utilities; every call site imports by full path).
5. The `unreferenced_keys` predicate body is **unchanged** — vocabulary only.

**Acceptance criteria**
- `test_references.py`, `test_ad_image_delete_signal.py` green **unmodified**.
- Leaf contains `KEY_COLUMNS` and nothing else (§6).
- No new dependency; no migration; `ruff`/`basedpyright` clean.

### Phase 2 — Convert consumers, ascending risk, site 3 isolated

Three separate commits, in this order, so a revert is surgical.

**Commit A — site 2, `sweep_orphaned_media._collect_referenced_keys`.**
`fields = KEY_COLUMNS`; the `.values(*fields)` / `.iterator()` loop is unchanged.
**Must preserve the census-vs-probe comment** — it is the only thing separating this
from `unreferenced_keys`, and it is what prevents the critical data-loss mode.

**Commit B — site 6, `AdImage.storage_keys()`.**
Iterate the tuple's attribute names via `getattr`. **Preserve the `cast`** and **preserve
the truthy filter** — two shipped tests in `apps/ads/tests/test_adimage_storage_keys.py`
pin both `None` and `""` as excluded. **Order must equal `KEY_COLUMNS`** (pinned by
`test_fully_populated_row_storage_keys_matches_key_columns` and by ordered-equality
consumers in `apps/users/tests/test_deletion.py`).

**Commit C — site 3, `media_gate`. ISOLATED.**
Build the four-way `Q` from `KEY_COLUMNS`; **keep both `.exists()` calls** and keep the
authorisation kwargs verbatim. In the same edit, remove the three
`# type: ignore[operator]` comments — they sit only on the `thumbnail_*` arms and are not
load-bearing after a loop build. **Isolated in its own commit** so a revert is surgical.

**Binding constraints (all three commits)**
1. **No query-shape change anywhere.** `media_gate` keeps `SELECT 1 … LIMIT 1`;
   `sweep_orphaned_media` keeps `.values()`; `storage_keys()` keeps its list order.
2. **`media_gate` stays free of filesystem access** in `key_q` construction. The shared
   constant adds none. `test_shared_seed_key_across_multiple_ads_returns_200` (two ads
   sharing a key, asserting 200 + `X-Accel-Redirect`) is the gate.
3. **The authorisation predicate is never folded into `KEY_COLUMNS`, into the leaf, or
   into any shared helper.** Folding it would make unpublished/declined ads' images
   publicly readable.
4. `sweep_orphaned_media` must never become candidate-filtered — it feeds
   `on_disk - referenced`; a filtered census deletes every file outside the candidate
   list.
5. `unreferenced_keys` keeps input-key order preservation (asserted by
   `apps/users/tests/test_deletion.py`).
6. Explicit-path staging only. No `git add -A` / `.` / `<dir>` — the tree carries other
   agents' uncommitted work and an untracked plan file.

**Acceptance criteria (per commit)**
- Target test file green; **plus** the site-3 files for Commit C.
- `ruff check --fix` clean; `basedpyright` clean on the touched files. Removing the
  stale ignores is safe either way — `reportUnnecessaryTypeIgnoreComment` at
  `typeCheckingMode = "standard"` is MEDIUM confidence, so treat its silence as
  unconfirmed, not as proof.
- Each commit body names the single site it converted.

### Phase 3 — Documentation

**Surface:** `.ai/plans/done/20-media-remediation-execution_done.md` (BLOCK 2b commit-body
deferral item 6); `docs/02-database/db-schema.md`; `docs/02-database/db-retention.md`.

- **Correct, do not delete,** BLOCK 2b's "They perform *different* predicates" clause.
  Replace with the §2 framing: the key-membership enumeration is identical; what differs
  is the **authorisation** predicate and the **census-vs-probe** consumption. Record that
  they must **not** be merged, and why. Correcting it stops a future reader re-attempting
  the merge.
- `db-schema.md` and `db-retention.md` both say "all four key columns". That is **still
  accurate** — this is a **wording check, not a correction**. Change nothing unless the
  Implementor finds the sentences have become wrong; record the check either way.

**Binding constraints**
1. The deferral correction is the only substantive doc edit.
2. English only. No `print()`. No user-visible strings → no i18n work.
3. Do not touch `.ai/audit/**`, other phases' plan files, or `edit.py`.

**Acceptance criteria**
- The corrected clause reads correctly on its own and states non-mergeability.
- Both doc locations confirmed still accurate (or corrected with the reason recorded).

### Gate

Targeted, then full:

```
.\Makefile.ps1 test   PYTEST_OPTS scoped to:
  src/backend/apps/media/tests/test_references.py
  src/backend/apps/ads/tests/test_adimage_storage_keys.py
  src/backend/apps/ads/tests/test_media_security.py            (site 3)
  src/backend/apps/media/tests/test_sweep_orphaned_media.py     (site 2)
  src/backend/apps/users/tests/test_deletion.py                (ordered storage_keys consumers)
```

Then the **full** `.\Makefile.ps1 test`. Re-read the result rather than asserting it — a
pre-existing `test_migrations.py::test_makemigrations_check` failure from another phase's
unmigrated `ModeratorActionLog.reason` change may still be red; attribute and prove, do
not fix.

---

## 6. Leaf module spec

**Path:** `src/backend/apps/media/storage_keys.py` (new, at the `media` package root).

**Invariant — zero `apps.*` imports.** Not zero imports: `django.*` and stdlib are
permitted. The precedent is the repo's own framing — `apps/media/schemas.py` calls
itself a leaf that "imports only pydantic", and `apps/core/enums.py` imports Django and
is still a cycle-free vocabulary leaf.

**Contents:** `KEY_COLUMNS: Final[tuple[str, ...]]` and **nothing else**.

**Must NOT contain:** any `Q` or queryset · any `AdImage` import · `settings` /
`MEDIA_ROOT` · any filesystem call · `KEY_FORMAT_REGEX` (a **different vocabulary** — do
not merge) · any DTO field name (`storage_key`) · any helper function — a
`build_key_q()` is exactly the query-level unification D1 rejects · any `StrEnum` of
column names (rule 10 targets magic values and dicts; this is one ordered immutable
tuple, and an enum would be the odd one out).

**Deliberately excluded:** the size→column map. One consumer, and the drift guard derives
that relation from the model, not from a map.

**Docstring contract — five clauses:**

1. This module owns the **vocabulary** of `AdImage` key column names. It owns **no**
   predicate, no query, no filesystem operation, and no model definition.
2. `references` remains **sole owner** of the still-referenced predicate;
   `media_gate` owns its authorisation predicate; `sweep_orphaned_media` owns its census.
   **Those three are semantically independent by design and must not be merged** —
   merging the authorisation filter would make unpublished/declined ads' images publicly
   readable; replacing the census with a candidate probe would delete every file outside
   the candidate list.
3. The tuple is **deliberately duplicated from `AdImage`** because the model carries no
   marker separating key columns from `telegram_file_id` / `sha256`, so derivation would
   require a model change. Drift is guarded by named tests (§7).
4. Leaf: no `apps.*` imports, no model access, no module-level side effects.
5. Adding a key column is a **multi-file change** — this tuple, the `AdImage` field, a
   migration, an index, the `KEY_FORMAT_REGEX` constraint, `ThumbnailSizeStrEnum`, and
   `ThumbnailService.SIZES`. **The tests are the tripwire.**

**Rejected placements** (each would create a false owner):

| Candidate | Rejected because |
|---|---|
| `references.py` | Two modules would depend on a module whose docstring claims **sole** ownership of a predicate they do not use. Curing that means rewriting a load-bearing contract shipped by BLOCK 2b. |
| `media/services/filesystem.py` | Already owns `KEY_FORMAT_REGEX` (vocabulary precedent is real), but imports `PIL`, `schemas`, `settings` — a pure tuple should not drag `PIL` in. |
| `apps/ads/models.py` | `ads.models` **already imports** `media.services.filesystem` at module level; putting it in `ads` **inverts** the established direction and makes `media` depend on `ads` — and `references.py` already imports `apps.ads.models`. |
| `apps/media/models.py` | That module is `MediaDeletionError`; unrelated concern. |
| `media/schemas.py` | **Forbidden by its own docstring.** |
| `apps/core/constants.py` | Does not exist anywhere in the repo; introduces a new concept. |

---

## 7. Drift-guard spec

All three assertions live in `src/backend/apps/media/tests/test_references.py`.

### Derivation rule (zero production change)

> **A key column is `image`, or `thumbnail_<size>` for some `size in
> `ThumbnailSizeStrEnum`.**

`ThumbnailSizeStrEnum` is **already** the canonical size vocabulary, and its member names
are exactly the three thumbnail column suffixes. The model is not imported in production
code; only the **test** derives the expected set.

### Assertion 1 — set-equality (NEW)

The derived set equals `set(KEY_COLUMNS)`. Catches: every row of §4's failure table via
set-equality, plus a new key column with **no index** (silent Seq Scan on the hot path)
and **no DB regex guard**.

**Misses:** a key column named outside the `thumbnail_<enum member>` convention.

### Assertion 2 — positive coverage (NEW, supersedes exact-count assertions)

Every `KEY_COLUMNS` name appears in some `AdImage._meta.indexes` field list **and** in
some constraint's condition.

**Deliberately positive, not exactness-based.** "Exactly four indexes / four
constraints" would be negative assertions pinning incidental detail (rule 15), even
though their intent is load-bearing. A legitimate future composite index must not break
this.

> **⚠ Pitfall that will bite.** `AdImage.sha256` carries `db_index=True`, so it has an
> **implicit** index that does **not** appear in `Meta.indexes`. Read `_meta.indexes`
> and derive from it; do **not** assume it enumerates every index the model has.

### Assertion 3 — keep unchanged

`test_every_key_column_resolves_to_a_concrete_model_field` stays. It catches a
`KEY_COLUMNS` name the model lacks (`FieldDoesNotExist`), which set-equality cannot.

### The three are non-overlapping

| Assertion | Relation |
|---|---|
| field-resolution | `KEY_COLUMNS ⊆ model fields` |
| set-equality | `KEY_COLUMNS = model fields` **under the derivation rule** |
| `storage_keys()` ordered equality | order |

**Correction to record:** the existing anti-drift test is **relational**, not
literal-vs-literal — it sets live model attributes from `KEY_COLUMNS` via
`AdImage.__new__`, then asserts `img.storage_keys() == list(KEY_COLUMNS)`. It is already
non-tautological. It goes **RED** if a column is added and *either* side is updated, and
on reorder or typo. It stays **GREEN** only in the actual failure scenario: **column
added, neither side updated.**

---

## 8. Scope table — nine enumeration sites

| # | Site | Decision | Reason |
|---|---|---|---|
| 1 | `references.py` — the constant + its inline `Q` | **INCLUDE** — constant **moves**; the `Q` **stays inline** | Predicate owner; function body otherwise unchanged. Re-export so every import path and test works unedited. |
| 2 | `sweep_orphaned_media._collect_referenced_keys` — local `fields` | **INCLUDE** | `fields = KEY_COLUMNS`; same tuple, same `.values(*fields)`. Must preserve the census-vs-probe comment. |
| 3 | `ads/views/listings.py::media_gate` — `key_q` | **INCLUDE (columns only)** | Build the four-way `Q` from `KEY_COLUMNS`; keep both `.exists()` calls; keep the authorisation kwargs verbatim. **Isolated commit.** |
| 4 | `AdImage.Meta.indexes` | **EXCLUDE** | Editing `Meta` **forces a migration** — that turns maintenance into a schema change. Covered defensively by Assertion 2. |
| 5 | `AdImage.Meta.constraints` | **EXCLUDE** | Same. |
| 6 | `AdImage.storage_keys()` | **INCLUDE** | Iterate the tuple's attribute names; **preserve the `cast`** and the truthy filter. Order must equal `KEY_COLUMNS`. |
| 7 | `filesystem.py` — `key_fields` | **EXCLUDE** | **DTO** vocabulary, not model columns (`"storage_key"`, not `image`). Wiring it needs a **rename** (ripples into bot FSM dicts, `SubmitAdInput`, ~30 test literals — past maintenance) **or a mapping** (a *new* duplication, worse than four literals). Omitting a field the constant does not name is the CRITICAL shape. |
| 8 | `backfill_thumbnails._SIZE_COLUMNS` | **EXCLUDE** | Single consumer; folding it in gives the leaf an `apps.core.enums` import for one caller. |
| 9 | `media/schemas.py` — fields + `storage_keys()` | **EXCLUDE** | Its docstring forbids the import explicitly. A Pydantic field declaration is the **boundary contract** — the one place a model-column mapping must not live. |

Also excluded: `apps/ads/migrations/*` — frozen history.

**Result: 4 files included. Zero model changes, zero migrations, zero new dependencies,
zero behaviour change.**

### Site-3 fallback path

The honest cost of including site 3: the `|` chain becomes a loop, so a reader can no
longer see the authorisation-relevant column set without executing Python, and the three
`# type: ignore[operator]` comments become unnecessary (harmless — remove them anyway in
the same edit).

> **Fallback:** if the Implementor judges the loop conversion of `media_gate` unacceptable
> for readability, leave site 3 as four literal arms and record it as an **explicit
> documented exclusion** in the commit body and in the §8 table. Sites 1, 2 and 6 still
> consolidate; the plan does not fail.

---

## 9. Out of scope, non-goals, and residuals

### Non-goals

No `AdImage.Meta` edit · no migration · no fifth-size enablement · no `storage_key`
rename · no `KEY_FORMAT_REGEX` relocation · no `services/__init__.py` re-export · **no
query unification at any level** · no change to `unreferenced_keys`' signature, order
preservation, or projection · no change to `media_gate`'s authorisation semantics ·
no edit to `.ai/audit/**`, other phases' plan files, or `edit.py`.

### Residuals to record

1. The **DTO sites** (`filesystem.key_fields`, `media/schemas.py`) and
   `_SIZE_COLUMNS` keep their own names. A fifth size would need hand-updates there with
   **no failing test** to signal it.
2. The D2 rule keys on the `thumbnail_<enum member>` convention, so a key column named
   **outside** that convention is invisible to the guard.
3. The coverage assertions are **positive**, not exactness assertions — a legitimate
   composite index will not break them, and neither will an accidental extra index.
4. The `.exists()` vs projection argument is **structural, not measured**. The seed pool
   is empty, so argue it from **documented Django behaviour** — `.exists()` is
   `SELECT 1 … LIMIT 1`; a projection returns matching rows — **never** as a benchmark.
5. Phase 0's red is a **prediction**, not a measurement (§5, §10).
6. `reportUnnecessaryTypeIgnoreComment` behaviour at `typeCheckingMode = "standard"` is
   **MEDIUM confidence** (inferred from `pyproject.toml` plus basedpyright defaults).
   Removing the stale ignores is safe either way.

---

## 10. Assumptions to verify

The Implementor must **verify** these, not assume them. Each names its verification.

| # | Assumption | Verification required |
|---|---|---|
| **1** | **Phase 0's new assertions go RED when a fifth key column + enum member are added.** | **A PREDICTION from reading code, not a measurement — the Researcher did not run the suite.** Produce the red output via the scratch mutation in Phase 0 and record it. **If it does not go red, STOP and report: the guard is not load-bearing and §4's premise is wrong.** |
| 2 | `AdImage.sha256`'s `db_index=True` index is absent from `_meta.indexes`. | Inspect `AdImage._meta.indexes` in-image before writing Assertion 2. Design the assertion against what `_meta.indexes` actually returns, not against this plan's reading. |
| 3 | `reportUnnecessaryTypeIgnoreComment` fires at `typeCheckingMode = "standard"`. | Run `basedpyright` before and after removing the three ignores in site 3. Treat silence as **unconfirmed**; removal is safe either way. |
| 4 | `.exists()` is materially cheaper than a per-key projection on a shared seed key. | **Structural argument only** — documented Django behaviour. Do **not** run or cite a benchmark; the seed pool is empty and BLOCK 2b's measured figures came from a synthetic schema. |
| 5 | `db-schema.md` / `db-retention.md` "all four key columns" is still accurate. | Wording check in Phase 3; record the result. It is **not** presumed accurate. |
| 6 | Re-exporting `KEY_COLUMNS` from `references.py` keeps every import path working. | Confirm by grep that the only importers are `references.py` and `test_references.py`, and that `test_references.py` runs **unmodified** in Phase 1. |
| 7 | Site 2's census textually stays distinct from the candidate probe after the change. | Read the commit diff and confirm the census comment survived verbatim. |

---

## 11. Shipped-state record (Phase 3)

This plan is **shipped**. The vocabulary leaf and three of the enumeration sites are
converted; nothing else changed.

### Commits

| Commit | Phase | What |
|---|---|---|
| `c514a8ca` | Phase 1 | `apps/media/storage_keys.py` leaf created; `KEY_COLUMNS` moved there and **re-exported** from `services/references.py` so every existing import path and test survives unedited. |
| `3d908f3b` | Phase 0 (B-06) | Two new proven-load-bearing assertions added to `TestKeyColumnsAntiDrift`. |
| `0a00f3a9` | Phase 2 Commit A (B-08) | `sweep_orphaned_media._collect_referenced_keys` derives `fields` from `KEY_COLUMNS`. |
| `0efa6314` | Phase 2 Commit B (B-08) | `AdImage.storage_keys()` derives its ordered attribute list from `KEY_COLUMNS`. |
| `6de51f40` | Phase 2 Commit C (B-09) | `media_gate`'s `key_q` built from `KEY_COLUMNS`; three stale `# type: ignore[operator]` removed; isolated commit. |

**Zero model changes, zero migrations, zero new dependencies, zero behaviour change.**
Four of the nine enumeration sites (§8 sites 1, 2, 3, 6) are converted;
`references.py`'s inline `Q` chain was deliberately left verbatim per binding decision
**D1** (CONSTANT-ONLY).

### Phase 3 task 1 — plan 20 deferral corrected, not deleted

The BLOCK 2b commit-body deferral in `.ai/plans/done/20-media-remediation-execution_done.md`
(item 6) was **corrected in place** (at the original path before it was moved to
`done/`). The corrected clause now: (a) states the
key-membership enumeration is **identical across sites** (`Q(col__in=[k])` ≡ `Q(col=k)`
for a singleton, and the falsy filter is inert), (b) names the two genuinely independent
semantics (**authorisation** at `media_gate`; **census-vs-probe** at
`sweep_orphaned_media`), (c) states **non-mergeability** with both failure modes
named — folding the authorisation filter in makes **unpublished/declined ads' images
publicly readable**, replacing the census with a candidate-filtered query **deletes every
file outside the candidate list** — and (d) records that the BLOCK 10 homonym is **not**
a discharge. The stale rationale "BLOCKS 7, 8 and 10 have file edges on those modules"
is recorded as shipped.

### Phase 3 task 2 — `docs/02-database/` wording check

| File | Check | Result |
|---|---|---|
| `docs/02-database/db-schema.md` | "single combined query over all four key columns (`image`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`)" | **Confirmed still accurate — no edit.** `KEY_COLUMNS` has four entries; `AdImage` has exactly four key columns; `ThumbnailSizeStrEnum` has exactly three members. |
| `docs/02-database/db-retention.md` | "The reference check covers **all four** key columns in `apps.media.services.references.unreferenced_keys`" | **Confirmed still accurate — no edit.** Same four-column fact. |

Both files are **byte-unchanged**. This was a wording check, not a correction.

### Corrections A–D (what actually happened)

**Correction A — the census-vs-probe comment was never on the target function.**
The plan (§5 Phase 2, Commit A) told the Implementor to preserve "the census-vs-probe
comment" on `sweep_orphaned_media._collect_referenced_keys`. That function carries only a
one-line docstring. The load-bearing text actually lives in three other places:
`_collect_dangling_keys` (the probe — "The join is load-bearing … 100% false positive on
every seeded key (VAL-005)"), `_collect_report_orphan_files` (the census — the report
walk is a read-only projection over the full store), and a comment in `Command.handle`
preceding `with transaction.atomic():` ("Snapshot referenced keys before deleting
anything …"). All three were **already intact and were preserved byte-identical**.
Nothing was "restored" onto the target function. Note also: there is **no** inline
comment directly above `orphans = on_disk - referenced` — the third protective text sits
above `with transaction.atomic():`.

**Correction B — `reportUnnecessaryTypeIgnoreComment` is OFF.**
The plan (§5 Phase 2, and §9 residual 6) recorded this as MEDIUM confidence and told the
Implementor to "treat silence as unconfirmed". Measured: `pyproject.toml` sets
`typeCheckingMode = "standard"` plus an explicit `"none"` for `reportOperatorIssue` (the
rule the three ignores targeted) and five others. basedpyright reports **0 diagnostics**
on `ads/views/listings.py` **with** the three comments present, so removal was safe
**and unobservable** — there is no signal either way, and the B-09 Implementor correctly
did not wait for one.

**Correction C — `test_ad_image_delete_signal.py` lives at
`src/backend/apps/core/tests/`,** not `apps/media/tests/`. The plan's Phase-1 acceptance
criterion named the wrong path. The file was located at
`src/backend/apps/core/tests/test_ad_image_delete_signal.py`; **no second copy was
created**.

**Correction D — the deferral's rationale is stale.** "BLOCKS 7, 8 and 10 have file
edges on those modules" no longer describes the tree: BLOCKS 7, 8 and 10 have all
**shipped**. The deferral was therefore retired by this work; it is kept in plan 20 as
the record of what was believed, not as live guidance.

### Residuals

1. The DTO sites (`filesystem.key_fields`, `media/schemas.py`) and
   `backfill_thumbnails._SIZE_COLUMNS` keep their own names (§8 sites 7–9). A fifth size
   would need hand-updates there with **no failing test** to signal it.
2. The drift guard keys on the `thumbnail_<enum member>` convention, so a key column
   named outside that convention is invisible to it (§7 Assertion 1 "misses").
3. The coverage assertions are **positive**, not exactness assertions — a legitimate
   composite index will not break them.
4. `_meta.indexes` does **not** enumerate every index: `AdImage.sha256`'s implicit
   `db_index=True` index is absent from it. Do not treat `_meta.indexes` as total.
5. Plan 20's corrected clause is a **documentation** record only; it changes no runtime
   behaviour.