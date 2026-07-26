# Trust Signals System — Implementation Plan

## Overview

Implement seller trust badges (Verified, Trusted, Pro) with score calculation based on ad history, moderation outcomes, and contact behavior.

**Research:** `.ai/plans/trust-signals/research.md`

---

## Task Execution Order

| Task | Description | Symbol | File | Dependencies |
|------|-------------|--------|------|--------------|
| T1 | Add TrustLevel StrEnum | `TrustLevel` | `apps/core/enums.py` | None |
| T2 | Add telegram_premium to User | `User.telegram_premium` | `apps/users/models.py` | None |
| T3 | Create SellerTrustScore model | `SellerTrustScore` | `apps/trust/models.py` | T1 |
| T4 | Create SellerVerification model | `SellerVerification` | `apps/trust/models.py` | None |
| T5 | Create TrustCalculator service | `TrustCalculator` | `apps/trust/services/trust_calculator.py` | T3, T4 |
| T6 | Add CONTACT_RESPONSE event | `AnalyticsEventType.CONTACT_RESPONSE` | `apps/core/enums.py` | None |
| T7 | Create badge templates | `*.html` | `templates/components/badges/` | None |
| T8 | Create trust template tags | `trust_tags` | `apps/trust/templatetags/trust_tags.py` | T1, T3, T5 |
| T9 | Update ad_list template | `ad_list.html` | `templates/ads/partials/ad_list.html` | T8 |
| T10 | Update detail template | `detail.html` | `templates/ads/detail.html` | T8 |
| T11 | Hook score updates to publish | `auto_moderation.py` | `apps/moderation/services/auto_moderation.py` | T5 |

---

## Task Details

### T1: Add TrustLevel StrEnum

**Symbol:** `TrustLevel`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** High

```python
class TrustLevel(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    TRUSTED = "trusted"
    PRO = "pro"
```

### T2: Add telegram_premium to User

**Symbol:** `User.telegram_premium`  
**File:** `src/backend/apps/users/models.py`  
**Priority:** Medium

```python
telegram_premium = models.BooleanField(
    default=False,
    help_text="User has Telegram Premium subscription"
)

class Meta:
    # Add to existing Meta
```

### T3: Create SellerTrustScore Model

**Symbol:** `SellerTrustScore`  
**File:** `src/backend/apps/trust/models.py`  
**Priority:** High

```python
class SellerTrustScore(models.Model):
    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="trust_score"
    )
    trust_level = models.CharField(
        max_length=20,
        choices=[(l.value, l.value) for l in TrustLevel]
    )
    score = models.PositiveSmallIntegerField(default=0)  # 0-100
    ad_count_lifetime = models.PositiveIntegerField(default=0)
    ad_count_active = models.PositiveIntegerField(default=0)
    rejection_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    contact_response_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    last_calculated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seller_trust_scores"
```

### T4: Create SellerVerification Model

**Symbol:** `SellerVerification`  
**File:** `src/backend/apps/trust/models.py`  
**Priority:** Medium

```python
class SellerVerification(models.Model):
    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="verification"
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    telegram_premium = models.BooleanField(default=False)
    verified_by_admin = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "seller_verifications"
```

### T5: Create TrustCalculator Service

**Symbol:** `TrustCalculator`  
**File:** `src/backend/apps/trust/services/trust_calculator.py`  
**Priority:** High

```python
from apps.core.enums import TrustLevel, AnalyticsEventType
from apps.ads.models import Ad
from apps.users.models import User

class TrustCalculator:
    """Calculate trust scores for sellers based on activity, quality, and response."""

    def calculate_score(self, user: User) -> dict:
        """Calculate comprehensive trust score."""
        activity_score = self._calculate_activity_score(user)
        quality_score = self._calculate_quality_score(user)
        response_score = self._calculate_response_score(user)

        total = activity_score + quality_score + response_score
        level = self._get_trust_level(total)

        return {
            "score": total,
            "trust_level": level,
            "ad_count_lifetime": Ad.objects.filter(user=user).count(),
            "ad_count_active": Ad.objects.filter(
                user=user, status=AdStatus.PUBLISHED
            ).count(),
        }

    def _calculate_activity_score(self, user: User) -> int:
        published = Ad.objects.filter(
            user=user, status=AdStatus.PUBLISHED
        ).count()
        return min(published * 5, 15)

    def _calculate_quality_score(self, user: User) -> int:
        total = Ad.objects.filter(user=user).exclude(status=AdStatus.DRAFT).count()
        rejected = Ad.objects.filter(
            user=user,
            status__in=[AdStatus.REJECTED, AdStatus.ON_MODERATION_FAILED]
        ).count()
        if total == 0:
            return 0
        return int((1 - rejected / total) * 40)

    def _calculate_response_score(self, user: User) -> int:
        # Based on CONTACT_RESPONSE events (deferred to Phase 3)
        return 0

    def _get_trust_level(self, score: int) -> str:
        if score >= 90:
            return TrustLevel.PRO
        if score >= 50:
            return TrustLevel.TRUSTED
        if score >= 10:
            return TrustLevel.VERIFIED
        return TrustLevel.UNVERIFIED
```

### T6: Add CONTACT_RESPONSE Event

**Symbol:** `AnalyticsEventType.CONTACT_RESPONSE`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** Low

```python
class AnalyticsEventType(StrEnum):
    REGISTRATION_CREATED = "registration_created"
    AD_PUFORMED = "ad_published"
    SEARCH_PERFORMED = "search_performed"
    CONTACT_INITIATED = "contact_initiated"
    CONTACT_RESPONSE = "contact_response"  # NEW
    AD_VIEWED = "ad_viewed"
```

### T7: Create Badge Templates

**Symbol:** `*.html`  
**File:** `src/backend/templates/components/badges/`  
**Priority:** Medium

`templates/components/badges/verified_badge.html`:
```html
<span class="inline-flex items-center px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded">
    <svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
    </svg>
    Verified
</span>
```

### T8: Create Trust Template Tags

**Symbol:** `trust_tags`  
**File:** `src/backend/apps/trust/templatetags/trust_tags.py`  
**Priority:** Medium

```python
from django import template
from apps.trust.models import SellerTrustScore

register = template.Library()

@register.inclusion_tag("components/badges/verified_badge.html")
def trust_badge(user):
    """Render trust badge for seller."""
    if user.is_anonymous:
        return {"show_badge": False}

    try:
        score = user.trust_score
        return {"show_badge": True, "trust_level": score.trust_level, "score": score.score}
    except SellerTrustScore.DoesNotExist:
        return {"show_badge": False}
```

### T9: Update ad_list Template

**Symbol:** `ad_list.html`  
**File:** `src/backend/templates/ads/partials/ad_list.html`  
**Priority:** Medium

Add badge after ad title:
```html
<h4 class="font-semibold text-lg mb-2 line-clamp-2">
    <a href="{% url 'ads:detail' ad.id %}" class="hover:text-blue-600">{{ ad.title }}</a>
</h4>
{% if ad.user.trust_score %}
    {% trust_badge ad.user trust_level=ad.user.trust_score.trust_level %}
{% endif %}
```

### T10: Update Detail Template

**Symbol:** `detail.html`  
**File:** `src/backend/templates/ads/detail.html`  
**Priority:** Medium

Add trust badge near title:
```html
<h1 class="text-2xl font-bold mb-4">{{ ad.title }}
    {% if ad.user.trust_score %}
        {% trust_badge ad.user trust_level=ad.user.trust_score.trust_level %}
    {% endif %}
</h1>
```

### T11: Hook Score Updates to Publish

**Symbol:** `auto_moderation.py`  
**File:** `src/backend/apps/moderation/services/auto_moderation.py`  
**Priority:** Medium

In `_pass_moderation()`:
```python
from apps.trust.services.trust_calculator import TrustCalculator

# After successful moderation
TrustCalculator().calculate_score(ad.user)
```

---

## Verification Commands

```bash
uv run basedpyright src/backend/apps/trust/
uv run ruff check src/backend/apps/trust/
uv run pytest src/backend/apps/trust/tests/ -v
```

---

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Schema migration | Medium | Trust models are separate from core ads/users |
| Badge performance | Low | Use `select_related` on user queries |
| Privacy leakage | Low | Badges show level, not identity details |
| Score gaming | Medium | Rate limits on ad creation already exist |

---

## Notes

- Trust scores calculated on-publish, not real-time
- Badges show only trust level (not score number) to buyers
- Admin verification manually sets `verified_by_admin = True`
- Telegram Premium flag comes from Bot API on `/start`