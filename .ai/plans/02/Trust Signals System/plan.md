# Trust Signals System — Implementation Plan

## Overview

Implement seller trust badges (Verified, Trusted, Pro) with score calculation based on ad history, moderation outcomes, and contact behavior.

**Research:** `.ai/plans/02/Trust Signals System/research.md`

---

## Task Execution Order

| Task | Description | Symbol | File | Dependencies |
|------|-------------|--------|------|--------------|
| T0 | Create apps/trust module structure | `apps.trust` module | `src/backend/apps/trust/` | None |
| T1 | Add TrustLevel StrEnum | `TrustLevel` | `apps/core/enums.py` | None |
| T2 | Add telegram_premium to User | `User.telegram_premium` | `apps/users/models.py` | None |
| T3 | Create SellerTrustScore model | `SellerTrustScore` | `apps/trust/models.py` | T1 |
| T4 | Create SellerVerification model | `SellerVerification` | `apps/trust/models.py` | T0 |
| T5 | Create TrustCalculator service | `TrustCalculator` | `apps/trust/services/trust_calculator.py` | T3, T4 |
| T6 | Add CONTACT_RESPONSE event | `AnalyticsEventType.CONTACT_RESPONSE` | `apps/core/enums.py` | None |
| T7 | Add record_contact_response method | `record_contact_response` | `apps/core/services/contact.py` | T6 |
| T8 | Create badge templates | `*.html` | `templates/components/badges/` | None |
| T9 | Create trust template tags | `trust_tags` | `apps/trust/templatetags/trust_tags.py` | T1, T3, T5 |
| T10 | Register apps.trust in settings | `INSTALLED_APPS` | `config/settings/base.py` | T0 |
| T11 | Update ad_list template | `ad_list.html` | `templates/ads/partials/ad_list.html` | T9 |
| T12 | Update detail template | `detail.html` | `templates/ads/detail.html` | T9 |
| T13 | Hook score updates to publish | `_pass_moderation()` | `apps/moderation/services/auto_moderation.py` | T5 |

---

## Task Details

### T0: Create apps/trust Module Structure

**Symbol:** `apps.trust` module  
**File:** `src/backend/apps/trust/` (new directory)  
**Priority:** Critical

Create the module directory structure:
```
apps/trust/
├── __init__.py
├── apps.py               # AppConfig for Django registration
├── models.py             # SellerTrustScore + SellerVerification
├── services/
│   ├── __init__.py
│   └── trust_calculator.py
└── templatetags/
    ├── __init__.py
    └── trust_tags.py
```

This must be created before any other trust-related tasks.

### T1: Add TrustLevel StrEnum

**Symbol:** `TrustLevel`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** High

```python
class TrustLevel(StrEnum):
    """Seller trust level for badge display."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    TRUSTED = "trusted"
    PRO = "pro"


# Add to __all__
__all__ = [
    "AdSort",
    "AdvisoryLockId",
    "AdStatus",
    "AdSource",
    "AnalyticsEventType",
    "ModeratorActionType",
    "CategoryRejectReason",
    "TrustLevel",  # ADD
]
```

### T2: Add telegram_premium to User

**Symbol:** `User.telegram_premium`  
**File:** `src/backend/apps/users/models.py`  
**Priority:** Medium

```python
telegram_premium = models.BooleanField(
    default=False,
    help_text="User has Telegram Premium subscription",
)
```

Place after `ads_auto_publish` field. This flag is set by the bot on `/start` from Telegram Bot API.

### T3: Create SellerTrustScore Model

**Symbol:** `SellerTrustScore`  
**File:** `src/backend/apps/trust/models.py`  
**Priority:** High

```python
from django.db import models
from apps.core.enums import TrustLevel


class SellerTrustScore(models.Model):
    """Persisted trust score for sellers, updated on ad publish."""

    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="trust_score",
    )
    trust_level = models.CharField(
        max_length=20,
        choices=[(l.value, l.label) for l in TrustLevel],
        default=TrustLevel.UNVERIFIED,
    )
    score = models.PositiveSmallIntegerField(default=0)  # 0-100
    ad_count_lifetime = models.PositiveIntegerField(default=0)
    ad_count_active = models.PositiveIntegerField(default=0)
    rejection_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    contact_response_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    last_calculated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seller_trust_scores"


class SellerVerification(models.Model):
    """Verification records for sellers (admin and phone verification)."""

    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="verification",
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
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
import logging
from typing import TYPE_CHECKING

from apps.ads.models import Ad
from apps.core.enums import AdStatus, TrustLevel
from apps.trust.models import SellerTrustScore

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


class TrustCalculator:
    """Calculate and persist trust scores for sellers."""

    def calculate_and_save(self, user: "User") -> SellerTrustScore:
        """Calculate trust score and persist to SellerTrustScore model."""
        activity_score = self._calculate_activity_score(user)
        quality_score = self._calculate_quality_score(user)
        response_score = self._calculate_response_score(user)

        total = activity_score + quality_score + response_score
        level = self._get_trust_level(total, user)

        # Persist to database
        trust_score, _ = SellerTrustScore.objects.get_or_create(
            user=user,
            defaults={
                "trust_level": level,
                "score": total,
                "ad_count_lifetime": self._count_lifetime_ads(user),
                "ad_count_active": self._count_active_ads(user),
                "rejection_rate": self._calculate_rejection_rate(user),
                "contact_response_rate": response_score,
            },
        )
        if _:
            logger.info(f"Created trust score for user {user.id}")
        else:
            trust_score.trust_level = level
            trust_score.score = total
            trust_score.ad_count_lifetime = self._count_lifetime_ads(user)
            trust_score.ad_count_active = self._count_active_ads(user)
            trust_score.rejection_rate = self._calculate_rejection_rate(user)
            trust_score.contact_response_rate = response_score
            trust_score.save()
            logger.info(f"Updated trust score for user {user.id}")

        return trust_score

    def _calculate_activity_score(self, user: "User") -> int:
        """Calculate activity score based on published ads."""
        published = Ad.objects.filter(
            user=user,
            status=AdStatus.PUBLISHED,
        ).count()
        return min(published * 5, 15)

    def _calculate_quality_score(self, user: "User") -> int:
        """Calculate quality score based on moderation outcomes."""
        total = Ad.objects.filter(user=user).exclude(status=AdStatus.DRAFT).count()
        rejected = Ad.objects.filter(
            user=user,
            status__in=[AdStatus.REJECTED, AdStatus.ON_MODERATION_FAILED],
        ).count()
        if total == 0:
            return 0
        return int((1 - rejected / total) * 40)

    def _calculate_response_score(self, user: "User") -> float:
        """Calculate response score based on CONTACT_RESPONSE events."""
        from apps.analytics.models import AnalyticsEvent
        from apps.core.enums import AnalyticsEventType

        total_contacts = AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.CONTACT_INITIATED,
        ).count()

        if total_contacts == 0:
            return 0.0

        responses = AnalyticsEvent.objects.filter(
            user_id=user.id,
            event_type=AnalyticsEventType.CONTACT_RESPONSE,
        ).count()

        return (responses / total_contacts) * 30

    def _calculate_rejection_rate(self, user: "User") -> float:
        """Calculate rejection rate for storage."""
        total = Ad.objects.filter(user=user).exclude(status=AdStatus.DRAFT).count()
        rejected = Ad.objects.filter(
            user=user,
            status__in=[AdStatus.REJECTED, AdStatus.ON_MODERATION_FAILED],
        ).count()
        if total == 0:
            return 0.0
        return round((rejected / total) * 100, 2)

    def _count_lifetime_ads(self, user: "User") -> int:
        """Count all non-draft ads."""
        return Ad.objects.filter(user=user).exclude(status=AdStatus.DRAFT).count()

    def _count_active_ads(self, user: "User") -> int:
        """Count currently published ads."""
        return Ad.objects.filter(
            user=user,
            status=AdStatus.PUBLISHED,
        ).count()

    def _get_trust_level(self, score: int, user: "User") -> str:
        """Determine trust level based on score and verification status."""
        has_verification = (
            hasattr(user, "verification") and user.verification.verified_by_admin
        ) or getattr(user, "telegram_premium", False)

        if score >= 90:
            return TrustLevel.PRO
        if score >= 50:
            return TrustLevel.TRUSTED
        if has_verification:
            return TrustLevel.VERIFIED
        return TrustLevel.UNVERIFIED
```

### T6: Add CONTACT_RESPONSE Event

**Symbol:** `AnalyticsEventType.CONTACT_RESPONSE`  
**File:** `src/backend/apps/core/enums.py`  
**Priority:** Medium

Add to `AnalyticsEventType` enum:

```python
class AnalyticsEventType(StrEnum):
    """Analytics event types for product metrics."""

    REGISTRATION_CREATED = "registration_created"
    AD_PUBLISHED = "ad_published"
    SEARCH_PERFORMED = "search_performed"
    CONTACT_INITIATED = "contact_initiated"
    CONTACT_RESPONSE = "contact_response"  # NEW
    AD_VIEWED = "ad_viewed"
```

### T7: Add record_contact_response Method

**Symbol:** `record_contact_response`  
**File:** `src/backend/apps/core/services/contact.py`  
**Priority:** Medium

Add new function after `record_contact_initiated`:

```python
def record_contact_response(seller_telegram_id: int) -> None:
    """
    Record CONTACT_RESPONSE analytics event.

    Called when seller confirms receiving a contact message.

    Args:
        seller_telegram_id: The seller's Telegram ID.
    """
    try:
        user = User.objects.get(telegram_id=seller_telegram_id)
        AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.CONTACT_RESPONSE,
            user_id=user.id,
        )
        logger.info(f"Contact response event recorded for seller {user.id}")
    except User.DoesNotExist:
        logger.warning(f"Seller not found for telegram_id {seller_telegram_id}")
```

Update `__init__.py` exports:

```python
from .contact import (
    can_contact_seller,
    get_seller_for_contact,
    record_contact_initiated,
    record_contact_response,  # NEW
)

__all__ = [
    "can_contact_seller",
    "record_contact_initiated",
    "get_seller_for_contact",
    "record_contact_response",
]
```

### T8: Create Badge Templates

**Symbol:** `*.html`  
**File:** `src/backend/templates/components/badges/` (new directory)  
**Priority:** Medium

Create template directory and three badge templates:

**`verified_badge.html`:**
```html
<span class="inline-flex items-center px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded">
    <svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
    </svg>
    Verified
</span>
```

**`trusted_badge.html`:**
```html
<span class="inline-flex items-center px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded">
    <svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
    </svg>
    Trusted
</span>
```

**`pro_badge.html`:**
```html
<span class="inline-flex items-center px-2 py-1 text-xs font-medium bg-purple-100 text-purple-800 rounded">
    <svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.507-.921 1.807 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81v.382a1 1 0 00-.293.536l-1.106 3.468a1 1 0 00-.293.536h-3.39c-.969 0-1.371 1.24-.588 1.81v.382a1 1 0 00-.293.536l-1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371-1.24.588-1.81v-.382a1 1 0 00.293-.536l1.106-3.468a1 1 0 00.293-.536h3.39c.969 0 1.371-1.24.588-1.81v-.382a1 1 0 00.293-.536l1.07-3.292a1 1 0 00-.95.69h-3.462a1 1 0 00-.95-.69l-1.106-3.468a1 1 0 00-.293-.536h-3.39z"/>
    </svg>
    Pro
</span>
```

### T9: Create Trust Template Tags

**Symbol:** `trust_tags`  
**File:** `src/backend/apps/trust/templatetags/trust_tags.py`  
**Priority:** Medium

```python
"""
Template tags for trust badge rendering.

Provides `trust_badge` inclusion tag that selects correct badge template
based on seller's trust level.
"""

from django import template
from apps.core.enums import TrustLevel
from apps.trust.models import SellerTrustScore

register = template.Library()


BADGE_TEMPLATES = {
    TrustLevel.VERIFIED: "components/badges/verified_badge.html",
    TrustLevel.TRUSTED: "components/badges/trusted_badge.html",
    TrustLevel.PRO: "components/badges/pro_badge.html",
}


@register.inclusion_tag("components/badges/verified_badge.html", takes_context=False)
def trust_badge(user) -> dict:
    """
    Render trust badge for seller.

    Selects correct badge template based on user's trust_level.
    Returns context dict with show_badge, template, and trust_level.

    Args:
        user: User object with trust_score relation.

    Returns:
        Dict with template name, show_badge flag, and trust_level.
    """
    if user.is_anonymous:
        return {"show_badge": False}

    try:
        score = user.trust_score
        template_path = BADGE_TEMPLATES.get(score.trust_level)

        return {
            "show_badge": True,
            "template": template_path,
            "trust_level": score.trust_level,
        }
    except SellerTrustScore.DoesNotExist:
        return {"show_badge": False}
```

**Note:** Template tags in Django require a wrapper since `inclusion_tag` does not support dynamic template paths. Use `trust_badge` as a filter returning context, then render in a wrapper template or use `{% include %}` with the returned template path.

**Alternative approach using simple tag:**

```python
@register.simple_tag(takes_context=True)
def render_trust_badge(context, user) -> str:
    """Render trust badge HTML directly."""
    if user.is_anonymous:
        return ""

    try:
        score = user.trust_score
        template_path = BADGE_TEMPLATES.get(score.trust_level)
        if template_path is None:
            return ""

        # Render template with context
        from django.template.loader import render_to_string
        return render_to_string(
            template_path,
            {"trust_level": score.trust_level},
            request=context.get("request"),
        )
    except SellerTrustScore.DoesNotExist:
        return ""
```

### T10: Register apps.trust in Settings

**Symbol:** `INSTALLED_APPS`  
**File:** `src/backend/config/settings/base.py`  
**Priority:** Critical

Add `"apps.trust"` to `INSTALLED_APPS` after `"apps.search"`:

```python
INSTALLED_APPS = [
    # ... existing apps ...
    "apps.search",
    "apps.analytics",
    "apps.trust",  # NEW
]
```

### T11: Update ad_list Template

**Symbol:** `ad_list.html`  
**File:** `src/backend/templates/ads/partials/ad_list.html`  
**Priority:** Medium

Add badge after ad title (line ~39):

```html
<h2 class="font-semibold text-lg mb-2 line-clamp-2">{{ ad.title }}
    {% if ad.user.trust_score %}
        {% render_trust_badge ad.user %}
    {% endif %}
</h2>
```

Or with inclusion tag approach:

```html
<h2 class="font-semibold text-lg mb-2 line-clamp-2">
    <a href="{% url 'ads:detail' ad.id %}" class="hover:text-blue-600">{{ ad.title }}</a>
    {% if ad.user.trust_score %}
        {% trust_badge ad.user as badge_ctx %}
        {% if badge_ctx.show_badge and badge_ctx.template %}
            {% include badge_ctx.template %}
        {% endif %}
    {% endif %}
</h2>
```

### T12: Update Detail Template

**Symbol:** `detail.html`  
**File:** `src/backend/templates/ads/detail.html`  
**Priority:** Medium

Add trust badge inline with title (line ~41):

```html
<h1 class="text-3xl font-bold mb-4">
    {{ ad.title }}
    {% if ad.user.trust_score %}
        {% render_trust_badge ad.user %}
    {% endif %}
</h1>
```

### T13: Hook Score Updates to Publish

**Symbol:** `_pass_moderation()`  
**File:** `src/backend/apps/moderation/services/auto_moderation.py`  
**Priority:** Medium

In `_pass_moderation()`, after creating analytics event:

```python
def _pass_moderation(ad: Ad) -> None:
    """Set ad to PUBLISHED with timestamp, log action, and create analytics event."""
    from apps.moderation.services.moderation_log import set_published
    from apps.trust.services.trust_calculator import TrustCalculator

    set_published(ad)

    AnalyticsEvent.objects.create(
        event_type=AnalyticsEventType.AD_PUBLISHED,
        user_id=ad.user_id,
    )

    # Update trust score after successful publish
    TrustCalculator().calculate_and_save(ad.user)

    logger.info(f"Auto-moderation passed for ad {ad.id}")
```

---

## App Module Structure

**`apps/trust/__init__.py`:**
```python
default_app_config = "apps.trust.apps.TrustConfig"
```

**`apps/trust/apps.py`:**
```python
from django.apps import AppConfig


class TrustConfig(AppConfig):
    name = "apps.trust"
    verbose_name = "Trust"
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
| Badge performance | Low | Use `select_related` on user queries in views |
| Privacy leakage | Low | Badges show level, not identity details |
| Score gaming | Medium | Rate limits on ad creation already exist |

---

## Notes

- Trust scores calculated on-publish, not real-time
- Badges show only trust level (not score number) to buyers
- Admin verification manually sets `verified_by_admin = True` in SellerVerification
- Telegram Premium flag comes from Bot API on `/start`
- CONTACT_RESPONSE events tracked via buyer follow-up pattern