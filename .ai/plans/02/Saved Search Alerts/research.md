# Saved Search Alerts - Research Analysis

**Date:** July 26, 2026  
**Phase:** Phase 2 Implementation  
**Status:** Research Complete

---

## 1. Current State Analysis

### 1.1 Existing Infrastructure

| Component | Status | Location |
|-----------|--------|----------|
| Search View | ✅ Implemented | `apps/search/views/search.py` |
| Query Translation | ✅ Implemented | `apps/search/services/query_translator.py` |
| Ad Model with search_vector | ✅ Implemented | `apps/ads/models.py` |
| Analytics Events | ✅ Implemented | `apps/analytics/models.py` |
| Advisory Lock Utility | ✅ Implemented | `apps/core/utils/advisory_lock.py` |
| Telegram Bot Framework | ✅ Implemented | `src/telegram_bot/main.py` |
| Bot Handler Patterns | ✅ Implemented | `src/telegram_bot/handlers/` |
| Management Commands | ✅ Implemented | `apps/core/management/commands/` |

### 1.2 Key Architecture Patterns in Use

#### Search Implementation
- PostgreSQL native FTS with `search_vector` TSVECTOR field and GIN index
- Bosnian→Russian translation via `deep-translator` with circuit-breaker pattern
- Single-word queries trigger fuzzy category detection via `difflib.get_close_matches`
- Results paginated (24 per page) with HTMX partial support

#### Background Job Patterns
- PostgreSQL advisory locks for idempotent scheduled jobs (`AdvisoryLockId` enum)
- Transaction-scoped locks (`pg_advisory_xact_lock`) safe under PgBouncer
- Management commands with `--dry-run` support for safe testing

#### Bot Handler Patterns
- aiogram 3.x Router-based handlers (e.g., `login_router`, `ad_create_router`)
- `sync_to_async` for ORM calls (critical since bot uses async, Django ORM sync)
- FSM state management via aiogram FSMContext
- Pydantic v2 validation for input payloads (`telegram_bot/schemas/`)

#### Analytics Tracking
- `AnalyticsEvent` model with `event_type` (StrEnum) and nullable `user` FK
- Events recorded for SEARCH_PERFORMED, AD_PUBLISHED, CONTACT_INITIATED
- User field SET NULL on erasure (privacy compliance)

### 1.3 Enums Reference

```python
# apps/core/enums.py
class AnalyticsEventType(StrEnum):
    REGISTRATION_CREATED = "registration_created"
    AD_PUBLISHED = "ad_published"
    SEARCH_PERFORMED = "search_performed"
    CONTACT_INITIATED = "contact_initiated"
    # SEARCH_ALERT_MATCHED needs adding
```

---

## 2. Gap Analysis

### 2.1 Missing Components (Per saved-search-alerts-plan.yaml)

| Task ID | Component | Status | Notes |
|---------|-----------|--------|-------|
| T1 | SavedSearch model | ❌ Missing | New table `saved_searches` |
| T1 | SavedSearchNotification model | ❌ Missing | Intermediate dedup table |
| T2 | AdvisoryLockId.ALERT_DELIVERY_TASK | ❌ Missing | Need Enum value |
| T2 | SavedSearches app registration | ❌ Missing | Or add to existing `apps.search` |
| T3 | AlertQueryService | ❌ Missing | Must reuse search patterns |
| T4 | SEARCH_ALERT_MATCHED event type | ❌ Missing | Add to AnalyticsEventType |
| T5 | /alerts bot handler | ❌ Missing | Router + FSM states |
| T6 | AlertDeliveryCommand | ❌ Missing | Management command |
| T7 | Save search modal template | ❌ Missing | HTMX-compatible partial |
| T8 | Router registration | ❌ Missing | Wire in `main.py` |

### 2.2 Critical Missing Infrastructure

1. **SavedSearches Module** - Entire module doesn't exist
2. **Bot Schemas for Saved Search** - Pydantic models for validation
3. **Bot FSM States for Alerts** - `SavedSearchState` enum needed
4. **Notification Tracking** - No mechanism to track delivery history

---

## 3. Implementation Recommendations

### 3.1 Model Design

Per the plan's `model_specs`, implement:

#### SavedSearch Model
```python
# apps/saved_searches/models/saved_search.py (or apps/search/models/)
class SavedSearch(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_searches")
    query = models.TextField(blank=True, null=True)  # FTS query
    city = models.ForeignKey(City, on_delete=models.SET_NULL, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True)
    min_price = models.PositiveIntegerField(blank=True, null=True)
    max_price = models.PositiveIntegerField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

#### SavedSearchNotification Model
```python
# Intermediate table for deduplication
class SavedSearchNotification(models.Model):
    saved_search = models.ForeignKey(SavedSearch, on_delete=models.CASCADE, related_name="notifications")
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="saved_search_notifications")
    sent_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "saved_search_notifications"
        constraints = [
            models.UniqueConstraint(fields=["saved_search", "ad"], name="unique_saved_search_ad")
        ]
```

### 3.2 Query Matching Service

The `AlertQueryService` should:

1. **Reuse existing search infrastructure** - Use the same FTS patterns as `search.py`
2. **Apply price filters** - Range filtering is straightforward DB query
3. **Handle category subtree** - Follow `get_descendants(include_self=True)` pattern
4. **Exclude notified ads** - JOIN with `SavedSearchNotification` to prevent duplicates
5. **Translate queries** - Use `translate_query_bs_to_ru` for Bosnian input

### 3.3 Delivery Architecture

#### For MVP/Phase 2 (Per roadmap):
- Daily digest via Telegram bot (scheduled via cron)
- Single delivery channel (Telegram only)
- Advisory lock prevents concurrent runs

#### For Future Scaling (Per 2026 best practices):
- Consider WebPush for web-based alerts (deferred to post-MVP)
- Per-user rate limiting to prevent spam
- Quiet hours enforcement (not critical for classifieds)

### 3.4 Bot Handler Flow

Following `ad_create.py` pattern:

```
/alerts (no args) → List saved searches with toggle status
/alerts save → Enter save search flow
→ Store query parameters in FSM
→ Confirm and save SavedSearch
```

### 3.5 Template Integration

The plan mentions T7 for templates but notes API endpoints come in Phase 3. For Phase 2:
- Modal triggers a management command or deferred job
- Consider storing unsaved searches temporarily for logged-in users

---

## 4. Dependencies

### 4.1 Internal Dependencies

| Depends On | Reason |
|------------|--------|
| `apps.core.enums.AdvisoryLockId` | New lock ID for alert delivery |
| `apps.core.enums.AnalyticsEventType` | New event type |
| `apps.search.services.query_translator` | Query translation reuse |
| `apps.search.views.search` patterns | FTS search reuse |
| `apps.ads.models.Ad` | Matching ads, status filter |
| `apps.categories.models.Category` | Category filtering |
| `apps.locations.models.City` | City filtering |
| `apps.analytics.models.AnalyticsEvent` | Event tracking |

### 4.2 External Dependencies (Existing)

| Package | Version | Use |
|---------|---------|-----|
| aiogram | 3.x | Telegram bot framework |
| django-filter | - | (Deferred to Phase 3 per plan) |
| deep-translator | - | Query translation |

### 4.3 No New Package Dependencies Required

The plan intentionally uses:
- PostgreSQL native FTS (no Elasticsearch/Solr)
- Management commands + cron (no Celery/Redis - deferred per roadmap)
- Telegram-only delivery (no SMS/email providers)

---

## 5. Modern Practices (2026)

### 5.1 Notification System Design

**Key Principles from Industry (2026):**

| Practice | Application to Mko Bazuna |
|----------|---------------------------|
| **At-least-once delivery** | Use advisory locks + idempotent DB writes |
| **Deduplication** | SavedSearchNotification unique constraint |
| **Provider isolation** | Currently single provider (Telegram) - simplify |
| **Rate limiting** | Per-user quiet hours not critical for classifieds |
| **Observability** | Log counts of notifications sent per run |

### 5.2 Saved Search Patterns

**From classified/ecommerce platforms:**

1. **Digest vs Real-time** - Daily digest is appropriate for classifieds (listings aren't time-critical like stock prices)

2. **Query Storage** - Store canonical query representation, not rendered strings:
   - Separate fields for query, city_id, category_id, price_range
   - Allows schema evolution without migration

3. **Matching Optimization** - Batch evaluation over individual queries:
   - Single query over all active SavedSearch records
   - Use JOIN for deduplication check
   - Index on `(saved_search_id, ad_id)` for fast lookup

### 5.3 Anti-Patterns to Avoid

| Anti-Pattern | Mitigation |
|--------------|------------|
| Duplicate notifications | UniqueConstraint in SavedSearchNotification |
| User spam | is_active flag, per-user saved search limits |
| Query overload | Daily digest (not real-time) + limit per user |
| Missing bot users | Check telegram_id/chat_id before sending |

---

## 6. Risk Assessment

### 6.1 Critical Risks

| Risk | Mitigation | Confidence |
|------|------------|------------|
| **Database migrations** | Test on copy of production; use advisory lock pattern | HIGH |
| **Telegram delivery failures** | Check chat_id exists before sending; log failures | HIGH |
| **Duplicate alerts** | UniqueConstraint prevents DB-level duplicates | HIGH |
| **Missing user contact info** | Graceful handling (log, skip notification) | HIGH |

### 6.2 Medium Risks

| Risk | Mitigation | Confidence |
|------|------------|------------|
| **Query performance** | Use indexes; limit matching to PUBLISHED ads only | MEDIUM |
| **Language handling** | Use existing translation cache; fallback to original | MEDIUM |
| **Bot state loss** | FSM state is ephemeral; saved searches persist in DB | MEDIUM |

### 6.3 Low Risks

| Risk | Mitigation | Confidence |
|------|------------|------------|
| **UI template changes** | HTMX partials, backward compatible | LOW |
| **Router registration** | Follow existing pattern | LOW |

---

## 7. Implementation Sequence (Per Plan DAG)

```
T1 (Models) → T2 (App Registration)
      ↓
T3 (AlertQueryService) ──┐
      ↓                   │
T4 (Analytics Enum)    ←─┤
      ↓                   │
T5 (Bot Handler) ────────┼──→ T8 (Router Integration)
      ↓                   │
T6 (Delivery Command) ←──┘
      ↓
T7 (Templates) - Parallel, no code dependency
```

### 7.1 Suggested Order

1. **T4** - Add `SEARCH_ALERT_MATCHED` to enum (lowest risk)
2. **T2** - Add `ALERT_DELIVERY_TASK` to `AdvisoryLockId` + register app
3. **T1** - Create models + migration
4. **T3** - Implement `AlertQueryService`
5. **T6** - Implement `AlertDeliveryCommand` (uses T3, T1)
6. **T5** - Implement `/alerts` handler (uses T1, T4)
7. **T8** - Register router in main.py
8. **T7** - Templates (can be done anytime)

---

## 8. Technical Decisions Required

### 8.1 Module Placement
- **Option A:** Create new `apps/saved_searches/` module
- **Option B:** Extend existing `apps/search/` module
- **Recommendation:** Extend `apps/search/` - keeps search-related models together

### 8.2 Delivery Frequency
- **Current plan:** Daily digest
- **Alternative:** On-publish trigger (complex, requires webhook/listener)
- **Recommendation:** Stick to daily digest for MVP; match plan spec

### 8.3 Notification Format
- **Per plan:** Daily digest format
- **Message limit:** Telegram allows ~4096 chars
- **Recommendation:** Truncate to top N matching ads (5-10) per digest

---

## 9. Verification Checklist (From Plan)

- [ ] All migrations run successfully in test database
- [ ] SavedSearch with is_active=False does not receive notifications
- [ ] AlertQueryService excludes ads in SavedSearchNotification intermediate table
- [ ] Telegram handler fails gracefully if user has no chat_id
- [ ] Management command logs execution count
- [ ] Template modal includes query, city, category, price fields

---

## 10. Appendix: Key Code References

### 10.1 Search Query Pattern
```python
# apps/search/views/search.py:52-65
if query:
    translated_query = translate_query_bs_to_ru(query)
    if _is_single_word(query):
        category_filter = _fuzzy_category_match(translated_query)
        if category_filter:
            ads = ads.filter(category_id__in=descendant_ids)
    search_query = SearchQuery(translated_query, search_type="websearch", config="russian")
    ads = ads.annotate(rank=SearchRank("search_vector", search_query))
    ads = ads.filter(search_vector=search_query).order_by("-rank")
```

### 10.2 Management Command Pattern
```python
# apps/core/management/commands/archive_sweep.py:36-40
with advisory_lock(AdvisoryLockId.ARCHIVE_SWEEP):
    with transaction.atomic():
        # ... operations ...
```

### 10.3 Bot Handler Pattern
```python
# src/telegram_bot/handlers/ad_create.py:48-68
@router.message(Command("post"))
async def cmd_post(message: types.Message, state: FSMContext) -> None:
    @sync_to_async
    def _create() -> Ad:
        return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)
    return await _create()
```