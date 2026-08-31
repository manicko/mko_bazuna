# Trust Signals System Implementation Plan

## Overview

Phase 2 Plan 3 introduces a Trust Signals System to display seller credibility badges on the platform. This system tracks seller behavior and trustworthiness through calculated scores and verification status.

## Execution DAG (Dependency Graph)

```
┌─────────────────────────────────────────────────────────────────┐
│                        Phase 2: Trust Signals                      │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ Layer 0: Prerequisites (No Trust Dependencies)               │
        └──────────────────────────────────────────────────────────────┘
                                  │
        ┌──────────┬──────────┬──────────┬──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼
   [Task T1]  [Task T2]  [Task T3]  [Task T4]  [Task T5]
     TrustLevel   User      Seller     Seller     Trust
   StrEnum       Model     TrustScore   Verif.   Template
               Update     Model        Model      Tags
                                  │
                                  ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ Layer 1: Core Trust Infrastructure                            │
        └──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                         [Task T6]  [Task T7]
                       Trust Score  Badge HTML
                       Service      Templates
                         (sync)      (static)
                                  │
                                  ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ Layer 2: Integration Points                                  │
        └──────────────────────────────────────────────────────────────┘
                                  │
        ┌──────────┬──────────┬──────────┬──────────┐
        ▼          ▼          ▼          ▼
   [Task T8]  [Task T9]  [Task T10] [Task T11]
   Contact    Ad List    Ad Detail  Update
  Analytics    Badge      Badge   Scoring
                 (HTMX)     Badge    Hook
```

## Task Specifications

### Task T1: TrustLevel StrEnum
**Semantic Anchor:** `@enum.core.trust_level`
**Risk:** Low (new enum only, no schema changes)
**Dependencies:** None

Add `TrustLevel` StrEnum to `apps/core/enums.py` with values:
- `UNVERIFIED` - Default for all new users
- `VERIFIED` - Has SellerVerification record
- `TRUSTED` - Trust score >= 70
- `PRO` - Trust score >= 90 + premium features

Update `__all__` exports.

### Task T2: User Model telegram_premium Field
**Semantic Anchor:** `@model.users.telegram_premium`
**Risk:** Medium - Schema change (one field)
**Dependencies:** None

Add `telegram_premium = models.BooleanField(default=False, ...)` to User model.
This field indicates if user has Telegram Premium subscription (fetchable via Bot API).

### Task T3: SellerTrustScore Model
**Semantic Anchor:** `@model.trust.seller_trust_score`
**Risk:** High - New table with schema
**Dependencies:** T1 (TrustLevel enum)

Create in `apps/trust/models.py`:
```python
class SellerTrustScore(models.Model):
    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="trust_score"
    )
    trust_level = models.CharField(
        max_length=20, choices=[(l.value, l.value) for l in TrustLevel]
    )
    score = models.PositiveSmallIntegerField(default=0)
    ad_count_lifetime = models.PositiveIntegerField(default=0)
    ad_count_active = models.PositiveIntegerField(default=0)
    rejection_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    contact_response_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.0
    )
    last_calculated = models.DateTimeField(auto_now=True)
```

> **Status: Implemented.** Field set matches [db-schema.md §SellerTrustScore](../02-database/db-schema.md).
> The plan previously listed `avg_ad_quality_score` and `updated_at`; the implementation uses
> `score` (overall 0–100) + `rejection_rate` and renames the timestamp to `last_calculated`.

### Task T4: SellerVerification Model
**Semantic Anchor:** `@model.trust.seller_verification`
**Risk:** High - New table with schema
**Dependencies:** None (User model updated in T2)

Create in `apps/trust/models.py`:
```python
class SellerVerification(models.Model):
    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="verification"
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    verified_by_admin = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)
```

> **Note:** `telegram_premium` is a field on `User` (not `SellerVerification`); it is set from
> `user.is_premium` on bot `/start` and used as a trust auto-verification signal (the
> `VERIFIED` trust-level floor). See [db-schema.md > users](../02-database/db-schema.md) and Task T2 above.

### Task T5: Trust Calculation Service
**Semantic Anchor:** `@service.trust.calculate_scores`
**Risk:** Medium - New service logic
**Dependencies:** T1, T3, AnalyticsEvent model exists

Create `apps/trust/services/trust_calculator.py`:
- Counts published ads per user
- Calculates contact response rate from analytics events
- Computes quality score based on ad performance
- Updates SellerTrustScore records

### Task T6: Badge Template Tags
**Semantic Anchor:** `@template.tag.trust_badge`
**Risk:** Medium - New template tags
**Dependencies:** T1, T3

Create `apps/trust/templatetags/trust_tags.py`:
- `get_trust_badge(user)` - Returns appropriate badge context

### Task T7: Badge HTML Templates
**Semantic Anchor:** `@template.trust.verified_badge`
**Risk:** Low - Static HTML templates
**Dependencies:** T6

Create templates:
- `templates/components/badges/verified_badge.html`
- `templates/components/badges/trusted_badge.html`
- `templates/components/badges/pro_badge.html`
- `templates/components/badges/premium_badge.html`

### Task T8: Contact Analytics Integration
**Semantic Anchor:** `@service.trust.contact_response`
**Risk:** Medium - New AnalyticsEventType required
**Dependencies:** AnalyticsEvent model, TrustScore model (T3)

Update contact service to:
- Track `CONTACT_RESPONSE` event type (add to AnalyticsEventType enum)
- Link to seller for response rate calculation

### Task T9: Ad List Integration
**Semantic Anchor:** `@view.ads.list.trust_badges`
**Risk:** Medium - Template modification
**Dependencies:** T6, T7, ad_list.html

Modify `templates/ads/partials/ad_list.html` to include trust badges in ad cards.

### Task T10: Ad Detail Integration
**Semantic Anchor:** `@view.ads.detail.trust_badges`
**Risk:** Medium - Template modification
**Dependencies:** T6, T7, ad_detail.html

Add trust badges to `templates/ads/detail.html`.

### Task T11: Scoring Hook Integration
**Semantic Anchor:** `@hook.trust.on_ad_publish`
**Risk:** Medium - Signal integration
**Dependencies:** T5, auto_moderation.py

Connect trust score updates to:
- Ad publish event (auto_moderation.py `_pass_moderation`)
- Ad archive event
- Periodic scheduled job via Django management command

## Detailed Implementation Sequence

### Phase 1: Models & Enums (Schema Changes)

1. **T1:** Add `TrustLevel` enum to `apps/core/enums.py`
2. **T2:** Add `telegram_premium` field to `apps/users/models.py`
3. **T4:** Create `apps/trust/models.py` with `SellerVerification` model
4. **T3:** Add `SellerTrustScore` model to `apps/trust/models.py`
5. **Create Migration:** `apps/trust/migrations/0001_initial.py`

### Phase 2: Services & Logic

6. **T5:** Create trust calculation service
7. **T8:** Add `CONTACT_RESPONSE` to AnalyticsEventType enum
8. **T8:** Update contact handler to record response events

### Phase 3: Templates

9. **T6:** Create trust template tags
10. **T7:** Create badge HTML templates
11. **T9:** Integrate badges into ad list
12. **T10:** Integrate badges into ad detail

### Phase 4: Integration Hooks

13. **T11:** Add signals/management commands for periodic score updates
14. **T11:** Integrate score updates into ad lifecycle

## Risk Assessment

### Schema Changes (High Risk)
- **SellerTrustScore table:** New table, create-only migration
- **SellerVerification table:** New table, create-only migration
- **User.telegram_premium:** Adds nullable/False field, backward compatible

### Data Migration Strategy
- Initial scores: Set all users to `UNVERIFIED` with count=0
- Historical data: Rely on existing Ad records for lifetime counts
- Analytics: Use existing `CONTACT_INITIATED` events as baseline

### Rollback Strategy
- Migrations add no irreversible data transformations
- All enums use string values, easy to modify in future phases

## File Manifest

### New Files
```
src/backend/apps/trust/
    __init__.py
    apps.py
    models.py              # SellerTrustScore + SellerVerification
    services/
        __init__.py
        trust_calculator.py   # Score calculation logic
    templatetags/
        __init__.py
        trust_tags.py         # Badge context tags

    migrations/
        __init__.py
        0001_initial.py       # Initial schema

templates/components/badges/
    verified_badge.html
    trusted_badge.html
    pro_badge.html
    premium_badge.html
```

### Modified Files
```
src/backend/apps/core/enums.py          # Add TrustLevel
src/backend/apps/users/models.py        # Add telegram_premium field
src/backend/apps/analytics/models.py    # Add CONTACT_RESPONSE to enum (optional)
src/backend/templates/ads/partials/ad_list.html    # Integrate badges
src/backend/templates/ads/detail.html            # Integrate badges
src/telegram_bot/handlers/contact.py    # Record response events
src/backend/apps/moderation/services/auto_moderation.py  # Hook score updates
```

## Validation Criteria

1. **Model validation:** All models pass pyright type checking
2. **Service validation:** Trust scores update correctly on ad publish/archive
3. **Template validation:** Badges render only for eligible sellers
4. **Integration validation:** No performance impact on ad listing queries (<5% overhead)