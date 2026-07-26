# Trust Signals System Implementation Research

**Date:** 2026-07-26  
**Status:** Research Complete → Implementation Ready

## 1. Current Architecture Analysis

### 1.1 Existing Models

#### User Model (`apps/users/models.py`)
- **Core identity:** Telegram-native authentication with `telegram_id` as unique identifier
- **Account states (3 independent flags):**
  - `is_banned` — Admin action, blocks login/publish, PII retained
  - `is_deleted` — GDPR withdrawal, triggers 30-day erasure
  - `ads_auto_publish` — Publishing restriction (US-S9)
- **GDPR consent tracking:** `consent_given_at`, `consent_revoked_at`
- **Note:** No `telegram_premium` field exists yet (required for Trust PRO badge)

#### Ad Model (`apps/ads/models.py`)
- **Lifecycle status:** `AdStatus` enum (DRAFT, ON_MODERATION, PUBLISHED, REJECTED, ON_MODERATION_FAILED, ARCHIVED, DELETED)
- **Source tracking:** `AdSource` enum (currently only TELEGRAM)
- **Full-text search:** PostgreSQL TSVECTOR for efficient searching
- **Owner relationship:** `user` ForeignKey to User model
- **Moderator references:** `published_by`, `moderated_by` for audit trail

#### AnalyticsEvent Model (`apps/analytics/models.py`)
- **Event types tracked:** `REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`, `CONTACT_INITIATED`
- **User attribution:** Nullable FK to User (SET NULL on erasure for GDPR compliance)
- **Missing:** `CONTACT_RESPONSE` event type (required for trust score calculation)

### 1.2 Service Layer Patterns

#### Auto-moderation Service (`apps/moderation/services/auto_moderation.py`)
- Singleton pattern for `ModerationCriteria` with caching (5-minute TTL)
- Validates ads on publish: title/description length, banned words, image count, max ads per user
- Records `AnalyticsEvent` on successful publish (AD_PUBLISHED)
- **Hook point:** `_pass_moderation()` function for trust score updates

#### Contact Service (`apps/core/services/contact.py`)
- Zone R2 conditions already defined (same pattern for trust checks)
- `can_contact_seller()` checks availability before rendering contact button
- `record_contact_initiated()` creates analytics event
- **Hook point:** Need to add `CONTACT_RESPONSE` tracking

### 1.3 UI Patterns (from Design System)

#### Badge Component Pattern (Atomic Design)
- **Structure:** Inline-flex with icon + text
- **Variants:** Primary (blue), Success (green), Warning (yellow), Danger (red), Neutral (gray)
- **CSS tokens:** `bg-green-100 text-green-800` for verification badges

#### Contact Seller Card
- Anonymity-preserving via Telegram deep-link
- Button only renders for PUBLISHED ads with available sellers
- Trust badges should integrate alongside contact mechanism

---

## 2. Trust Signals Requirements Analysis

Based on the implementation plan (`trust-signals-plan.md`) and design docs:

### 2.1 Required Components

| Component | Type | Location | Purpose |
|-----------|------|----------|---------|
| `TrustLevel` | StrEnum | `apps/core/enums.py` | Trust level classification |
| `SellerTrustScore` | Model | `apps/trust/models.py` | Calculated trust metrics |
| `SellerVerification` | Model | `apps/trust/models.py` | Verification records |
| `telegram_premium` | Field | `apps/users/models.py` | Telegram Premium flag |
| `get_trust_badge()` | Template tag | `apps/trust/templatetags/` | Badge rendering context |
| Badge templates | HTML | `templates/components/badges/` | Visual badge components |

### 2.2 Trust Level Enum Values (planned)

```python
class TrustLevel(StrEnum):
    UNVERIFIED = "unverified"    # Default for all new users
    VERIFIED = "verified"        # Has SellerVerification record
    TRUSTED = "trusted"          # Trust score >= 70
    PRO = "pro"                  # Trust score >= 90 + premium features
```

**Risk Assessment:** The threshold values (70, 90) are arbitrary and need refinement based on actual user behavior.

---

## 3. Modern Trust/Verification Systems Analysis (2026)

### 3.1 eBay Top Rated Seller (eTRS) Model

**Key Findings from 2026 Research:**

| Metric | eBay Requirement | Applicability to Mko Bazuna |
|--------|-----------------|---------------------------|
| Transaction volume | 100+ transactions, $1,000+ sales | **NOT APPLICABLE** — No transaction system (P2P, no payments) |
| Defect rate | <0.5% | **ADAPT** — Rejection rate from moderation |
| Late shipment rate | <3% | **NOT APPLICABLE** — No shipping in classifieds |
| Tracking upload | ≥95% | **N/A** |
| Returns policy | 30-day required | **N/A** — Off-platform transactions |
| Account age | 90+ days | **RELEVANT** — Ad lifetime count |

**Key Insight:** eBay's model relies heavily on transaction-based metrics. For Mko Bazuna's P2P classifieds model, we must adapt to:
- Ad publication history instead of transactions
- Moderation outcomes instead of late shipments
- Contact response behavior instead of shipping metrics

### 3.2 Facebook Marketplace Trust Signals (2026)

**Key Metrics (from research):**
1. **Save rate** — User saves listing (proxy for quality)
2. **Message rate** — Views converting to contacts
3. **Response time** — Seller responsiveness (critical for ranking)
4. **Completion rate** — Transactions completed successfully

**Adaptation for Mko Bazuna:**
- Track contact initiation rate (equivalent to message rate)
- Measure seller response through follow-up events
- High-quality ads = fewer rejections + longer ad lifecycles

### 3.3 Modern Trust System Principles (2026)

From marketplace trust research:

#### Core Components:
1. **Identity signals** — Phone verification, Telegram Premium
2. **Performance metrics** — Rejection rate, ad quality score
3. **Recourse mechanisms** — Report/block, dispute path
4. **Badge visibility** — Must be in decision path (not hidden)

#### Critical Rules:
1. **Never show "verified" unless defensible** — Fake badges train users to ignore signals
2. **Simplicity matters** — Complex badges outside main flow are rarely used
3. **Regular updates** — Trust scores must reflect current behavior
4. **Transparency** — Users should understand what earns trust

---

## 4. Recommended Implementation Approach

### 4.1 Trust Level Refined Model

**Based on research, propose revised trust levels:**

| Level | Requirements | Rationale |
|-------|--------------|-----------|
| `UNVERIFIED` | Default | All new users start here |
| `VERIFIED` | `SellerVerification.verified_by_admin = True` OR `telegram_premium = True` | Identity confirmed via admin/Telegram |
| `TRUSTED` | Trust score 50-89 + active | Consistent seller behavior (see scoring below) |
| `PRO` | Trust score 90+ + verified | Elite status for top sellers |

### 4.2 Trust Score Calculation Algorithm

**Proposed formula (transparent, achievable):**

```
Trust Score = (
    Activity Score (0-30) +
    Quality Score (0-40) +
    Response Score (0-30)
)
```

**Activity Score (0-30):**
- Published ads: 5 points each, max 15
- Days active (30-day rolling): 1 point per 10 days, max 15
- *Cap prevents gaming via bulk posting*

**Quality Score (0-40):**
- Moderation passes: 8 points each (max 40)
- OR: 100% - (rejected ads / total submissions) * 40
- *Rewards clean publishing history*

**Response Score (0-30):**
- Contact responses tracked via analytics
- 20 points: At least 3 contacts recorded
- 10 points per response recorded (estimated via buyer follow-up)
- *Requires CONTACT_RESPONSE event type*

### 4.3 Integration Points

| Location | Integration | Method |
|----------|-------------|--------|
| Ad list (`ad_list.html`) | Seller badge in card | Template tag + badge component |
| Ad detail (`detail.html`) | Seller badge near title | Template tag + badge component |
| Auto-moderation | Score updates on publish | Signal/hook in `_pass_moderation()` |
| Contact flow | Response tracking | New `CONTACT_RESPONSE` event |
| Dashboard | Trust status display | Template tag in dashboard |

### 4.4 Database Schema (Refined)

#### SellerTrustScore Model
```python
class SellerTrustScore(models.Model):
    user = models.OneToOneField("users.User", on_delete=models.CASCADE, related_name="trust_score")
    trust_level = models.CharField(max_length=20, choices=[(l.value, l.value) for l in TrustLevel])
    score = models.PositiveSmallIntegerField(default=0)  # 0-100 for easy display
    ad_count_lifetime = models.PositiveIntegerField(default=0)
    ad_count_active = models.PositiveIntegerField(default=0)
    rejection_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    contact_response_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    last_calculated = models.DateTimeField(auto_now=True)
```

**Improvements over plan:**
- Added `score` field (0-100) for direct display
- Changed `rejection_rate` to be directly stored (no calculation on display)
- Added `last_calculated` for transparency/debugging

#### SellerVerification Model
```python
class SellerVerification(models.Model):
    user = models.OneToOneField("users.User", on_delete=models.CASCADE, related_name="verification")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    telegram_premium = models.BooleanField(default=False)
    verified_by_admin = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)
```

**Note:** This duplicates `telegram_premium` from User. Consider:
- **Option A:** Separate verification record (plan approach) — Cleaner audit trail
- **Option B:** Merge into User model — Simpler queries, less joins

### 4.5 Performance Considerations

From design system research:
- Badge visibility must be in main decision path (search results, ad cards)
- Trust data should be denormalized or cached to avoid N+1 queries
- Consider using `select_related` when loading ads with trust data

### 4.6 Privacy & Anonymity Alignment

The trust system must align with Mko Bazuna's core principle of seller anonymity:
- **Trust badges display behavior/score, NOT identity**
- No `@username`, phone, or other PII on trust display
- Verification status is binary (verified/unverified), not detailed
- Contact response tracking is anonymous (no message content stored)

---

## 5. Implementation Priority & Sequence

### Phase 1: Foundation (Tasks T1-T2)
1. **T1:** Add `TrustLevel` StrEnum to `apps/core/enums.py`
2. **T2:** Add `telegram_premium` to User model (Bot API provides this)

### Phase 2: Core Models (Task T3-T4)
3. **T4:** Create `apps/trust/models.py` with `SellerVerification`
4. **T3:** Add `SellerTrustScore` model
5. Create migration `apps/trust/migrations/0001_initial.py`

### Phase 3: Scoring Logic (Task T5-T7)
6. **T5:** Create trust calculator service
7. Add `CONTACT_RESPONSE` to `AnalyticsEventType`
8. **T7:** Create badge templates (verified, trusted, pro)

### Phase 4: Integration (Task T8-T11)
9. **T8:** Update contact handler to track responses
10. **T6:** Create trust template tags
11. **T9/T10:** Integrate badges into ad list/detail templates
12. **T11:** Hook score updates to ad publish events

---

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Schema migration | High | Create-only migration, reversible |
| Trust score gaming | Medium | Rate limits, anomaly detection |
| Badge performance overhead | Medium | Denormalize, cache, or use annotations |
| Fake verification abuse | High | Admin-only verification for now |
| CONTACT_RESPONSE tracking | Medium | Estimate via buyer follow-up pattern |

---

## 7. Success Metrics Alignment

From roadmap: **+25% seller verification rate within 30 days**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Trust scores updated on publish | 100% | Test coverage |
| Badge display performance | <5% overhead | Query profiling |
| Seller verification uptake | 25% increase | Analytics event count |
| Contact response correlation | >70% accuracy | Score vs. actual responses |

---

## 8. Files to Create/Modify

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
        0001_initial.py       # Schema

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
src/backend/apps/analytics/models.py    # Add CONTACT_RESPONSE to enum
src/backend/apps/moderation/services/auto_moderation.py  # Hook score updates
src/telegram_bot/handlers/contact.py    # Record response events
src/backend/templates/ads/partials/ad_list.html    # Integrate badges
src/backend/templates/ads/detail.html              # Integrate badges
```

---

## 9. Key Decisions Required

Before implementation:

1. **Duplicate telegram_premium field:** Keep in both User and SellerVerification, or remove from User?
2. **Trust score thresholds:** Are 50/90 the right cutoffs? Suggest: TRUSTED=50+, PRO=85+
3. **Response tracking method:** How to reliably detect seller contact responses?
4. **Badge visibility:** Show on all ads or only high-trust sellers? (Recommend: show on all)

---

## 10. References

- eBay Top Rated Seller research (2026): Transaction-defect-rate model, 8-12% conversion lift
- Facebook Marketplace trust signals: Save rate, message rate, response time metrics
- AMA Journal of Marketing Research: Trust badge redesign impact on seller behavior
- Mko Bazuna design system: Badge component patterns, trust signal HTML