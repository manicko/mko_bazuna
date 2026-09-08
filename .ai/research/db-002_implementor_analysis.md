# DB-002 Implementor Analysis — Why @implementor Sessions Keep Failing

## Status
**Investigation complete.** No code changes were made. Report written from session logs, source code, and plan spec analysis.

## Executive Summary

Both `@implementor` sessions assigned to implement the DB-002 fix hit the model's
output/reasoning limit and produced **zero code changes**. The root cause is **not**
model capability — it is a **flawed task formulation**: the plan's T2 test describes a
TOCTOU race condition that **cannot physically occur** given the project's existing count
criteria and transition matrix. The implementor, upon reaching that contradiction during
the reasoning phase, gets stuck in an ever-expanding loop of re-verification attempts
(reading the plan, re-reading source, checking settings, checking i18n, checking Docker,
etc.), consuming all output tokens before producing a single edit.

**Confidence: HIGH** — verified against source code (`auto_moderation.py:196-204`,
`moderation_log.py:208-224`, `enums.py:46-54`, `ads/models.py:349-369`).

---

## 1. Session History

### Session 1: `ses_f7e159a86ffeyr3WeqZOVhn4mc`
- **Task title:** "Implement DB-002 fix step by step"
- **Outcome:** Produced NO code changes. Session ended during investigation phase
  (grep searches + file reads) without reaching implementation.
- Available transcript shows the agent was still verifying file structure when the
  session terminated.

### Session 2: `ses_f7e219d4fffez5YPn6hHkmMm1`
- **Task title:** "Implement DB-002 max_ads fix"
- **Outcome:** Produced NO code changes. Model hit output limit while reasoning.
- The agent's final transcript line:
  > "The model hit its output limit while reasoning and produced no actionable output.
    Try disabling reasoning or increasing the output limit."
- **Investigation breadth:** The agent read 25+ files/resources including:
  - The 481-line plan spec (`.ai/plans/03_db-002_implementation_spec.md`)
  - 10+ source files (`moderation_log.py`, `auto_moderation.py`, `review.py`,
    `admin_actions.py`, `exceptions.py`, `enums.py`, `models.py`, `ad_create.py`,
    `api_bulk.py`, `base.py` settings)
  - 5+ test files (`test_admin_actions.py`, `test_auto_moderation.py`,
    `test_moderation_views.py`, `test_approve_ad_side_effects.py`,
    `test_i18n_completeness.py`)
  - Template (`review.html`) and locale files (`.po` files for ru/en)
  - Docker image capability checks (gettext tools, PG version)
  - Git status checks, import circularity checks, middleware config verification

**Pattern:** Both sessions follow the same trajectory — investigate extensively,
then exhaust output tokens without writing code. The second session's transcript
shows the agent systematically checking every open question and constraint in the 481-line
plan before hitting the wall.

---

## 2. The Core Problem: T2 Is Logically Impossible

### 2.1 The count criteria is invariant under ON_MODERATION → PUBLISHED

The max-ads count in **both** the advisory check and the proposed locked re-count uses:

```python
# _validate_max_ads_per_user (auto_moderation.py:196-204)
active_statuses = [AdStatus.PUBLISHED, AdStatus.ON_MODERATION]
count = Ad.objects.filter(
    user_id=user_id,
    status__in=active_statuses,
).count()
```

The plan's proposed `set_published` re-count (§2.2 of the spec, lines 165-168) uses the
**identical** criteria: `status__in=[AdStatus.PUBLISHED, AdStatus.ON_MODERATION]`.

When an ON_MODERATION ad is published, its status transitions:
```
ON_MODERATION → PUBLISHED
```

Both `ON_MODERATION` and `PUBLISHED` are in the counted set. Therefore:
- Before transition: the ad is counted (it is ON_MODERATION)
- After transition: the ad is still counted (it is now PUBLISHED)

**The count does not change.** It is mathematically invariant under this transition.

### 2.2 Consequences for the TOCTOU race

A classic TOCTOU race requires the protected resource to *change* between the check and
the commit. Here:

| Scenario | Count at check | Count at commit | TOCTOU race? |
|---|---|---|---|
| User at cap (count ≥ max_ads) | Advisory check rejects → never reaches `set_published` | — | No (blocked earlier) |
| User at cap-1 (count = max_ads - 1) | Advisory check passes | Publishing ON_MODERATION → PUBLISHED: count stays max_ads - 1 | No (invariant) |
| User under cap | Advisory check passes | `count >= max_ads` is False | No (legitimately passes) |

The locked re-count in `set_published` would **never** observe a count that differs from
the advisory check for the ON_MODERATION → PUBLISHED path. The `select_for_update` lock
prevents concurrent *increases*, but there are no concurrent increases to prevent for
this transition.

### 2.3 The only way count increases: ARCHIVED → PUBLISHED

From `ads/models.py:349-362`, the `transition_to` matrix permits:
```
ARCHIVED → PUBLISHED | ON_MODERATION
```

When an ARCHIVED ad is published:
- Before: ARCHIVED (NOT in counted set)
- After: PUBLISHED (in counted set)
- Count increases by 1 — **a genuine TOCTOU window exists here.**

However, **no caller currently publishes ARCHIVED ads through `set_published`**:
- Bot: `auto_moderate` is called on ON_MODERATION ads (set by `process_preview`)
- Web review: `approve_ad` view fetches `status=AdStatus.ON_MODERATION` (review.py:64)
- Bulk: calls `approve_ad` on ON_MODERATION ads

So while the `select_for_update` lock would *correctly protect* the ARCHIVED → PUBLISHED
path if it were ever used, the T2 test — which specifically uses ON_MODERATION ads —
cannot demonstrate the race it claims to test.

### 2.4 T2's scenario is self-contradictory

**T2 spec** (plan §3, line 349):
> `TestMaxAdsRaceCondition` — two concurrent `auto_moderate` calls (threads) with
> `max_ads=2`, user has 1 PUBLISHED + 2 ON_MODERATION drafts. Assert exactly 1
> PUBLISHED + 1 ON_MODERATION_FAILED after both complete.

**Trace:**
1. User state: 1 PUBLISHED + 2 ON_MODERATION = 3 active ads
2. `max_ads = 2`
3. Thread 1 calls `auto_moderate(ad_on_moderation_1)`:
   - `_validate_max_ads_per_user`: count=3, max=2 → `3 < 2` is `False` → advisory check **fails**
   - `_fail_moderation(ad)` → ON_MODERATION_FAILED
   - Returns `False` immediately — **never reaches `_pass_moderation` or `set_published`**
4. Thread 2: same outcome
5. Final state: 1 PUBLISHED + 0 ON_MODERATION + **2** ON_MODERATION_FAILED

**Expected by T2:** 1 PUBLISHED + 1 ON_MODERATION_FAILED (implying one ON_MODERATION
ad was successfully published).

**Actual with current code:** 1 PUBLISHED + 2 ON_MODERATION_FAILED.

The advisory check rejects both ads before `set_published` is ever called, so the locked
re-count in `set_published` — and thus the entire TOCTOU scenario — is unreachable.

---

## 3. Secondary Complexity Factors

Beyond the logical flaw, the plan's structure makes it nearly impossible for a single
agent pass to complete:

### 3.1 Overly long handoff document (481 lines)
The plan spec is 481 lines covering 6 file edits, 4 new tests, quality gates, risk
analysis, and rollout sequence. An implementor reading the entire spec + all source
files exhausts a significant fraction of context/output budget before writing a single
line of code.

### 3.2 Atomicity requirement across 6 files
The plan (§8, line 481) states:
> "All 6 source files must deploy together. A partial deploy where `set_published`
> raises but `auto_moderate`/view haven't been updated would cause an unhandled
> exception."

This forces the implementor to hold all 6 file edits in working context simultaneously,
making incremental verification impossible — they can't test after each step.

### 3.3 Thread-based concurrency test in Django
T2 requires Python threads with `select_for_update`. Django's `django_db` marker uses
transaction-wrapped tests by default. To test real row-level locking:
- Must use `@pytest.mark.django_db(transaction=True)` (bypasses per-test transaction
  rollback — much slower)
- Each thread needs its own DB connection (`connection.close()` + `close_old_connections()`)
- The pytest-xdist `--dist loadgroup` flag (enabled in the test entrypoint) can
  parallelize tests in ways that interfere with thread-based concurrency tests
- The plan's own quality gate (§7, line 446) explicitly warns: "ensure `--dist` is NOT
  `loadgroup` for the specific race test, or mark it `@pytest.mark.slow`"

This adds significant test infrastructure complexity beyond the business logic.

### 3.4 i18n overhead
OQ-2 requires adding `{% if messages %}` block to `review.html` and running
`makemessages`/`compilemessages` for ru, bs, en locales, then verifying with
`test_i18n_completeness.py`. This is a prerequisite step, not part of the core fix.

---

## 4. What Would Make This Task Solvable

### 4.1 Option A: Fix the test to match reality
Rewrite T2 to test the race on a path where the count actually changes:
- Use ARCHIVED → PUBLISHED (the reactivation path), not ON_MODERATION → PUBLISHED
- OR lower `max_ads` to 1 and have 1 PUBLISHED ad, with the second ad coming from DRAFT —
  but DRAFT → ON_MODERATION → PUBLISHED doesn't increase count either (DRAFT is not
  counted)

The fundamental issue: no automated path increases the PUBLISHED + ON_MODERATION count.
Only ARCHIVED → PUBLISHED does, and no caller does this.

### 4.2 Option B: Acknowledge the lock is defensive, not corrective
The `select_for_update` lock in `set_published` would still be *defensive good practice*
— it protects against future code paths that might publish ARCHIVED or DRAFT→ON_MODERATION
→ PUBLISHED ads concurrently. But T2 should not claim to demonstrate a TOCTOU race
that cannot occur on the current code paths. The test should verify the lock exists
(existence assertion) rather than attempting to trigger a race.

### 4.3 Option C: Break into smaller sub-tasks
Split the 481-line plan into 3 sub-tasks:
1. **T1 only:** Rewrite `exceptions.py` + `set_published` lock + `auto_moderate` catch
   (no web path, no tests beyond T1)
2. **T2 is impossible — re-design it** (per §4.1)
3. **T3-T4:** Web review view + bulk + T3/T4 tests

Each sub-task fits in a single agent pass with ~20% context budget for coding.

### 4.4 Option D: Simplify the contract
Instead of catching `MaxAdsExceeded` at each caller with different handling, consider
a single callback or result pattern that returns `(success: bool, reason: str|None)`.
This reduces the number of files to edit and the atomicity surface.

---

## 5. Evidence Checklist

| Claim | Evidence location | Confidence |
|---|---|---|
| Count criteria includes ON_MODERATION | `auto_moderation.py:199` | HIGH |
| Count criteria identical in plan's `set_published` | Plan §2.2, lines 165-168 | HIGH |
| ON_MODERATION → PUBLISHED is in transition matrix | `ads/models.py:359` | HIGH |
| Count is invariant under ON_MODERATION → PUBLISHED | Mathematical (both in set) | HIGH |
| Advisory check uses the same count | `auto_moderation.py:154, 196-204` | HIGH |
| T2 scenario: 1 PUBLISHED + 2 ON_MODERATION, max_ads=2 | Plan §3, line 349 | HIGH |
| Advisory check rejects count=3 vs max=2 | `auto_moderation.py:204`: `count < max_ads` | HIGH |
| Web view fetches only ON_MODERATION ads | `review.py:64`: `status=AdStatus.ON_MODERATION` | HIGH |
| No caller publishes ARCHIVED ads | Bot: `auto_moderate` on ON_MODERATION; Web: ON_MODERATION only | MEDIUM |
| ARCHIVED → PUBLISHED is the only count-increasing path | Transition matrix, `enums.py:46-54` | HIGH |
| Both sessions produced zero code changes | Session transcripts | HIGH |
| Second session hit model output limit | Session transcript final line | HIGH |
| 6-file atomicity requirement | Plan §8, line 481 | HIGH |
| Thread-based test requires `transaction=True` | Django docs convention + plan §7 warning | MEDIUM |

---

## 6. Relevant Files

### Source files (all unchanged — pre-DB-002 state)
| File | Lines | Role |
|---|---|---|
| `apps/moderation/services/exceptions.py` | 30 | `MaxAdsExceeded(user_id, limit)` — 2-arg, needs rewrite to 3-arg |
| `apps/moderation/services/moderation_log.py` | 224 | `set_published` — no lock, no raise (lines 208-224) |
| `apps/moderation/services/auto_moderation.py` | 352 | `auto_moderate`, `_validate_max_ads_per_user`, `_pass_moderation` |
| `apps/moderation/views/review.py` | 131 | `approve_ad` view — no try/except (lines 49-68) |
| `apps/moderation/admin_actions.py` | — | `approve_ad`, `bulk_approve` |
| `apps/core/enums.py` | 69 | `AdStatus` enum (PUBLISHED, ON_MODERATION, ARCHIVED, DRAFT...) |
| `apps/ads/models.py` | 349+ | `transition_to` method + matrix |

### Plan / research artifacts
| File | Lines | Contents |
|---|---|---|
| `.ai/plans/03_db-002_implementation_spec.md` | 481 | Full plan spec (D1-D5, §2 file requirements, §3 tests, §4 risks) |

### Test infrastructure
| File | Notes |
|---|---|
| `src/backend/conftest.py` | Shared fixtures: `seller`, `user`, `category`, `city`, `create_test_ad` |
| Docker Compose | `mko-bazuna-test` project, PostgreSQL 18, port 5433 |
| `base.py` settings | `django.contrib.messages` + `MessageMiddleware` confirmed present (R6 NOT triggered) |

### Session logs (via kilo_local_recall)
| Session ID | Title |
|---|---|
| `ses_f7e159a86ffeyr3WeqZOVhn4mc` | "Implement DB-002 fix step by step" |
| `ses_f7e219d4fffez5YPn6hHkmMm1` | "Implement DB-002 max_ads fix" |
