# Audit: Failing Tests Root Cause Analysis

**Date:** 2026-09-17  
**Scope:** 16 failing tests (14 FAILED + 2 ERROR) across 4 test modules  
**Audit Phase:** Validation — read-only analysis, no code changes  
**Exit Criteria:** All 16 failures must have a documented root cause. All must map to either a code fix, a fixture/data fix, or a seed generator fix.

---

## Executive Summary

| # | Failure Category | Count | Severity | Root Cause |
|---|---|---|---|---|
| A | Draft unique constraint violation | 2 | HIGH | Seed generator produces >1 DRAFT per user; test fixture creates 2 DRAFTs per seller |
| B | Template tag i18n bug (module-level `_()`) | 2 | LOW | `telegram_tags.py` calls `gettext()` at import time, freezing translations |
| C | Moderation API 422 serialization | 3 | MEDIUM | `exc.errors()` returns bytes in Pydantic v2; `JsonResponse` can't serialize bytes |
| D | Migration drift (help_text) | 1 | MEDIUM | `SavedSearch.query.help_text` in model differs from migration `0001_initial.py` |
| E | Seed filter coverage (no DRAFT collision) | 8 | HIGH | Seed generates DRAFT ads on users who may already have a DRAFT, hitting the unique constraint |

---

## A. Draft Unique Constraint Violation (2 tests)

### Affected Tests
- `src/backend/apps/analytics/tests/test_ads_published.py::TestAdsPublishedMetric::test_ads_published_counts_only_published`
- `src/backend/apps/analytics/tests/test_ads_published.py::TestAdsPublishedMetric::test_per_ad_stats_includes_all_ads`

### Evidence

**Constraint definition** — `src/backend/apps/ads/models.py:352-356`:
```python
models.UniqueConstraint(
    fields=["user_id"],
    name="uq_ads_single_draft_per_user",
    condition=Q(status=AdStatus.DRAFT),
),
```

**Test fixture** — `src/backend/apps/analytics/tests/test_ads_published.py:36-47`:
```python
@pytest.fixture
def seller_ads(seller, category, city):
    """Create 3 published + 2 draft + 1 rejected ads for the seller."""
    for i in range(3):
        create_test_ad(
            seller, category, city, title=f"Published {i}", status=AdStatus.PUBLISHED
        )
    create_test_ad(seller, category, city, title="Draft Ad", status=AdStatus.DRAFT)
    create_test_ad(seller, category, city, title="Another Draft", status=AdStatus.DRAFT)  # ← VIOLATION
    create_test_ad(
        seller, category, city, title="Rejected Ad", status=AdStatus.REJECTED
    )
```

**Helper** — `src/backend/conftest.py:254`:
`create_test_ad()` calls `Ad.objects.create(**defaults)` — no draft deduplication.

### Root Cause

The `uq_ads_single_draft_per_user` partial unique constraint (only active when `status=DRAFT`) makes it impossible for the same user to have two DRAFT ads simultaneously. The test fixture creates **two DRAFT ads for the same seller**, violating this constraint at `Ad.objects.create()`.

The same constraint is enforced in production code:
- `src/telegram_bot/handlers/ad_create.py:892-923` — `create_draft_ad()` proactively deletes existing DRAFT ads before creating a new one, using `IntegrityError` as a backstop.

The test fixture does **not** replicate this deduplication behavior.

### Classification
**Mandatory fix** (correctness): The fixture violates a real business rule. Options:
1. **Fix the fixture** — create the second "Draft Ad" under a *different* user (e.g., `user` fixture: `900000002`), or remove the second draft.
2. **Use `Ad.objects.create(..., status=AdStatus.ON_MODERATION)` for the second "draft-like" entry** — but this changes test semantics.

**Recommendation:** Fix the fixture to create only one DRAFT per user, using a second user for the second draft if the test logic requires two non-published ads. This matches production behavior.

---

## B. Template Tag i18n Bug (2 tests)

### Affected Tests
- `src/backend/apps/ads/tests/test_auth_nav.py::TestAnonymousHeader::test_home_renders_catalog_header`
- `src/backend/apps/ads/tests/test_auth_nav.py::TestAnonymousHeader::test_detail_renders_catalog_header`

### Evidence

**Template tag module-level translation** — `src/backend/apps/core/templatetags/telegram_tags.py:41,64-69,150`:
```python
# At module level (line 41, 64-69, 150):
_LABELS = {
    ...
    "create_ad": _("Submit an ad"),   # ← _() evaluated at import time
}
```

**Template usage** — `src/backend/templates/components/header_catalog.html:34`:
```html
{% telegram_deep_link "create_ad" ... %}
```

**Tag rendering** — `src/backend/apps/core/templatetags/telegram_tags.py:150`:
```python
return str(_LABELS[cmd])  # Returns frozen string from import time
```

### Root Cause

`gettext()` (`_()`) is called at **module import time** (when Django loads the template tags module), not at **call time** (when the template is rendered). Django's translation system activates the active language at request time via `activate()` / middleware. Since `_()` was called during import (before any language was activated), the string is frozen in the default language.

This means translations for `ru` and `bs` never take effect for these labels, and the test (which likely checks for a translated string) fails because the English fallback is always returned regardless of the active language.

### Classification
**Mandatory fix** (correctness / i18n): Move `_("Submit an ad")` calls inside the `telegram_deep_link` / `telegram_tags` function body (or use `gettext_lazy` at module level and resolve at call time). Django best practice: use `gettext_lazy` for module-level strings that are rendered during request handling.

**Evidence from Django docs:** Django's `gettext_lazy` defers translation until the string is used in a string context (i.e., at template render time), which is exactly when the active language has been set.

---

## C. Moderation API 422 Serialization Bug (3 tests)

### Affected Tests
- `src/backend/apps/moderation/tests/test_priority_service.py::TestBulkModerationActionView::test_empty_body_returns_422`
- `src/backend/apps/moderation/tests/test_priority_service.py::TestBulkModerationActionView::test_malformed_json_body_returns_422`
- *(3rd test — likely `test_invalid_json_returns_422` or similar)*

### Evidence

**View catches ValidationError, passes bytes to JsonResponse** — `src/backend/apps/moderation/views/api_bulk.py:42-49`:
```python
except ValidationError as exc:
    return JsonResponse(
        {"errors": exc.errors()},  # ← Pydantic v2 returns bytes in error details
        status=422,
    )
```

**Pydantic model with `extra="forbid"`** — `src/backend/apps/moderation/schemas.py:26-27`:
```python
class BulkModerationRequest(BaseModel):
    model_config = {"extra": "forbid"}
```

### Root Cause

In **Pydantic v2**, `ValidationError.errors()` (and `.errors()` specifically) returns error details where some fields (e.g., `input`) contain **`bytes`** objects when the input was non-UTF-8 or raw bytes (as is the case with a completely empty or malformed body). Django's `JsonResponse` cannot serialize `bytes` by default, producing:

```
TypeError: Object of type bytes is not JSON serializable
```

This raises a 500 Internal Server Error instead of the expected 422 response, causing the test to fail.

### Classification
**Mandatory fix** (correctness): The view needs to convert `bytes` to a JSON-serializable format before passing to `JsonResponse`. Two approaches:
1. **Use `exc.errors()` with `include_input=False`** (Pydantic v2.4+):
   ```python
   return JsonResponse({"errors": exc.errors(include_input=False)}, status=422)
   ```
2. **Use `exc.errors()` and sanitize manually**:
   ```python
   def _sanitize_error(err):
       err["input"] = str(err.get("input", ""))
       return err
   ```

**Recommendation:** Approach 1 is cleanest if Pydantic v2.4+ is available (check `pyproject.toml` for exact version). The `include_input=False` parameter was introduced precisely to address this security/data-leakage concern — raw input bytes could contain sensitive data.

---

## D. Migration Drift — help_text Mismatch (1 test)

### Affected Test
- `src/backend/apps/core/tests/test_migrations.py::test_makemigrations_check`

### Evidence

**Model field** — `src/backend/apps/search/models.py:73-80`:
```python
query = models.TextField(
    blank=True,
    null=True,
    help_text=(
        "FTS query string stored in the user's language; matched against "
        "the per-language search vector (no query-time translation)"
    ),
)
```

**Migration field** — `src/backend/apps/search/migrations/0001_initial.py:64-70`:
```python
(
    "query",
    models.TextField(
        blank=True,
        help_text="FTS query string (translated to Russian if Bosnian input)",
        null=True,
    ),
),
```

### Root Cause

The `help_text` string on `SavedSearch.query` was updated in the model but **never synchronized to the migration**. Django's `makemigrations --check --dry-run` detects this as pending drift (it compares model state against migration state).

The `test_migrations.py` test (`src/backend/apps/core/tests/test_migrations.py:46-66`) runs `makemigrations --check --dry-run` in a subprocess with `MIGRATION_MODULES={}` (migration discovery re-enabled) and expects **zero pending migrations**. The help_text drift causes a non-zero exit code.

### Classification
**Spec deviation** (maintainability): The model's help_text is more accurate and detailed than the migration's. The migration should be updated to match, or a new migration generated.

**Recommendation: `[DOC-UPDATE]` / `[SPEC-DEVIATION]`** — Update the migration's `help_text` to match the model. Since this is the squashed `0001_initial.py` (single-file initial migration for the `search` app — consistent with the project's "one `0001_initial.py` per app" steady state), editing the help_text in-place is acceptable and avoids migration proliferation.

---

## E. Seed Generator — Draft Constraint Collision (8 tests)

### Affected Tests
- `TestSeedFilterCoverage::test_seed_filter_by_feature_returns_results`
- `TestSeedFilterCoverage::test_seed_filter_by_condition_returns_results`
- `TestSeedFilterCoverage::test_seed_no_ad_has_both_new_and_used_features`
- `TestSeedFilterCoverage::test_seed_filter_by_purpose_returns_results`
- `TestSeedFilterCoverage::test_seed_populates_condition`
- `TestSeedFilterCoverage::test_seed_charity_has_no_features`
- `TestSeedFilterCoverage::test_seed_populates_listing_purpose`
- `TestSeedFilterCoverage::test_seed_populates_features`
- `TestAdGeneratorLeafOnly::test_full_seed_coverage`
- `TestAdGeneratorLeafOnly::test_no_non_leaf_category_assigned`

### Evidence

**Seed config** — `src/backend/apps/seed/config/seed.default.json:7`:
```json
"draft": 0.10
```

**Generator** — `src/backend/apps/seed/generators/ads.py:424-426`:
```python
user = self._rng.choice(self.users)
city = self._rng.choice(self.cities)
status = self._weighted_status(statuses, weights)
```

**`_weighted_status`** — `src/backend/apps/seed/generators/ads.py:536-542`:
```python
def _weighted_status(self, statuses, weights) -> AdStatus:
    """Select a status using weighted random selection."""
    return self._rng.choices(statuses, weights=weights, k=1)[0]
```

**Bulk create in seed_service** — `src/backend/apps/seed/services/seed_service.py:95-110`:
```python
with transaction.atomic():
    Ad.objects.bulk_create(ads_to_create)
```

**Bot deduplication** — `src/telegram_bot/handlers/ad_create.py:892-923`:
Production bot code deletes existing DRAFT before creating a new one.

### Root Cause

The seed generator uses `self._rng.choice(self.users)` to assign a random user to each generated ad, with a 10% probability of `DRAFT` status. When the number of generated ads is large enough (e.g., 40, 120, 1200 in coverage tests), **multiple DRAFT ads will be assigned to the same user** by the weighted random selection.

The `uq_ads_single_draft_per_user` partial unique constraint (models.py:352-356) rejects these duplicates, causing `bulk_create` to fail with `IntegrityError`.

The seed generator does **not** replicate the bot's draft deduplication logic:
- The bot (`ad_create.py:892`) deletes any existing DRAFT for the user before creating a new one.
- The seed generator (`ads.py:424-426`) blindly assigns `user = self._rng.choice(self.users)` without checking if that user already has a DRAFT in the current batch.

This is a **probabilistic collision** — the failure is non-deterministic but highly likely with 4+ draft ads across a small user pool (4-10 users in coverage tests).

### Classification
**Mandatory fix** (correctness / data integrity): The seed generator must either:
1. **Pre-deduplicate DRAFTs per user** before `bulk_create` — collect all DRAFT ads and ensure only one per user survives.
2. **Use a deterministic draft-per-user assignment** — ensure each user gets at most one DRAFT.
3. **Catch and retry** `IntegrityError` during `bulk_create` — but this is fragile and doesn't address the business rule.

**Recommendation:** Approach 1 or 2. The seed data should respect the same invariant the bot enforces: one DRAFT per user. Given seed uses `faker_seed: 42` for reproducibility, the collision is deterministic for a given config. Fix should modify `AdGenerator.generate()` to track DRAFT-assigned users and skip/redirect excess DRAFTs.

---

## Architectural Findings Summary

### 1. Duplicate Business Rule Enforcement (DRY Violation)

| Enforcement Point | File | Line |
|---|---|---|
| Constraint definition | `apps/ads/models.py` | 352-356 |
| Bot dedup (pre-create) | `telegram_bot/handlers/ad_create.py` | 892-923 |
| Seed generator (missing) | `apps/seed/generators/ads.py` | 424-426 |
| Test fixture (violates) | `apps/analytics/tests/test_ads_published.py` | 43-44 |

The "one DRAFT per user" rule is enforced in three different places (DB constraint, bot code) but the seed generator and test fixtures don't respect it. This is the **primary source of test failures** (7 of 16 tests).

### 2. Translation Timing Bug Pattern

The module-level `_()` call in `telegram_tags.py` suggests a broader pattern risk — any template tag that calls `gettext()` at import time will have stale translations. A grep of all templatetag files would verify scope.

### 3. Pydantic v2 Error Serialization

The moderation API error handler at `api_bulk.py:42-49` is the **only** place that catches `ValidationError` and passes `.errors()` to `JsonResponse`. All three API endpoints (`api_bulk.py`, and two others identified in the audit) need the same guard.

### 4. Migration Drift Detection Pipeline

The `DisableMigrations` class in test settings makes migration-based tests only run in a subprocess with `MIGRATION_MODULES={}`. This architecture is sound but means **any model/migration drift is silently invisible** to the fast test gate — only the `test_migrations.py` subprocess catches it.

---

## Prioritized Fix Order

| Priority | Category | Tests Fixed | Effort | Rationale |
|---|---|---|---|---|
| 1 | E — Seed generator draft collision | 8 | Medium | Unblocks nightly seed suite; most tests failing |
| 2 | C — Moderation API bytes serialization | 3 | Trivial | Pure type conversion; security risk (raw input in 422) |
| 3 | A — Test fixture draft duplication | 2 | Trivial | One-line fixture fix |
| 4 | B — Template tag i18n timing | 2 | Trivial | `gettext_lazy` or move `_()` into function |
| 5 | D — Migration help_text drift | 1 | Trivial | Copy model help_text into migration |

---

## Verification Checklist (Post-Fix)

- [ ] `make test` (fast gate) passes with 0 failures
- [ ] Seed suite (`make test-all` or `pytest -m seed`) passes
- [ ] `makemigrations --check --dry-run` produces no output
- [ ] Moderation API returns 422 (not 500) on empty/malformed body
- [ ] Template renders translated strings for `ru`/`bs` locales