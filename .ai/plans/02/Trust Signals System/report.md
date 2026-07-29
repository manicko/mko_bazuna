# Trust Signals System — Implementation Verification Report

**Plan:** `.ai/plans/02/Trust Signals System/plan.md`
**Date:** 2026-07-29
**Scope:** Verify implementation of all 14 plan tasks (T0–T13) against actual codebase.
**Verdict:** Partially implemented. 9 of 14 tasks complete; 5 not done. Several deviations from the plan's specified design.

---

## Summary Table

| Task | Symbol | Plan Status | Actual Status | Verdict |
|------|--------|-------------|---------------|---------|
| T0 | `apps.trust` module | Create directory structure | ✅ Complete | PASS |
| T1 | `TrustLevel` StrEnum | Add to `core/enums.py` | ✅ Complete | PASS |
| T2 | `User.telegram_premium` | Add field after `ads_auto_publish` | ✅ Complete | PASS |
| T3 | `SellerTrustScore` model | Create in `trust/models.py` | ✅ Complete (deviations) | DEVIATION |
| T4 | `SellerVerification` model | Create in `trust/models.py` | ✅ Complete | PASS |
| T5 | `TrustCalculator` service | Create in `trust/services/` | ✅ Complete (deviations) | DEVIATION |
| T6 | `AnalyticsEventType.CONTACT_RESPONSE` | Add enum member | ✅ Complete | PASS |
| T7 | `record_contact_response` | Add to `core/services/contact.py` | ❌ Not implemented | FAIL |
| T8 | Badge templates | Create 3 HTML templates | ✅ Complete | PASS |
| T9 | `trust_tags` template tags | Create `trust_badge` tag | ✅ Complete (deviations) | DEVIATION |
| T10 | Register `apps.trust` in settings | Add to `INSTALLED_APPS` | ✅ Complete | PASS |
| T11 | Update `ad_list.html` | Add badge after title | ❌ Not implemented | FAIL |
| T12 | Update `detail.html` | Add badge inline with title | ❌ Not implemented | FAIL |
| T13 | Hook score updates to publish | Add call in `_pass_moderation()` | ✅ Complete | PASS |

---

## Detailed Findings

### T0: Create apps/trust Module Structure — PASS

**Plan:** Create `apps/trust/` with `__init__.py`, `apps.py`, `models.py`, `services/`, `templatetags/`.

**Actual:** Full directory structure exists at `src/backend/apps/trust/`. All required files present:
- `__init__.py` — contains module docstring (plan specified `default_app_config`, which is unnecessary in Django 5.2)
- `apps.py` — `TrustConfig` with `name = "apps.trust"`, `verbose_name = "Trust"` (matches plan)
- `models.py` — both models present
- `services/trust_calculator.py` — `TrustCalculator` class present
- `templatetags/trust_tags.py` — `trust_badge` tag present
- `migrations/0001_initial.py` — migration created (not in plan, but required)
- `tests/test_trust_calculator.py` — test suite present (not in plan, but required)

**No issues.**

---

### T1: Add TrustLevel StrEnum — PASS

**Plan:** Add `TrustLevel` StrEnum to `apps/core/enums.py` with members `UNVERIFIED`, `VERIFIED`, `TRUSTED`, `PRO`. Add to `__all__`.

**Actual:** `TrustLevel` StrEnum exists at `src/backend/apps/core/enums.py` (lines 91–97) with exactly the four specified members. It is included in `__all__` (line 173).

**No issues.**

---

### T2: Add telegram_premium to User — PASS

**Plan:** Add `telegram_premium = models.BooleanField(default=False, ...)` after `ads_auto_publish` field in `apps/users/models.py`.

**Actual:** Field exists at `src/backend/apps/users/models.py` (lines 63–66), placed immediately after `ads_auto_publish` (lines 59–62). Matches plan specification.

**No issues.**

---

### T3: Create SellerTrustScore Model — DEVIATION

**Plan specification:**
```python
trust_level = models.CharField(
    max_length=20,
    choices=[(l.value, l.label) for l in TrustLevel],
    default=TrustLevel.UNVERIFIED,
)
```

**Actual implementation** (`src/backend/apps/trust/models.py`, lines 19–22):
```python
trust_level = models.CharField(
    max_length=20,
    choices=[(level.value, level.value) for level in TrustLevel],
)
```

**Deviations:**
1. **Missing `default=TrustLevel.UNVERIFIED`** — The plan specifies a default value. The actual code has no default. This means creating a `SellerTrustScore` without explicitly setting `trust_level` will raise an `IntegrityError`. In practice this is mitigated because `TrustCalculator.calculate_and_save()` always sets `trust_level` explicitly, but it is a deviation from the plan and a latent risk if other code paths create `SellerTrustScore` rows.
2. **Choices use `level.value` for both value and label** — The plan uses `l.label` for the display label (which would produce human-readable labels like "Unverified"). The actual code uses `level.value` for both, so the admin dropdown would show "unverified", "verified", etc. (lowercase values) instead of "Unverified", "Verified". This is a minor UX deviation in the Django admin.

**Other fields** (score, ad_count_lifetime, ad_count_active, rejection_rate, contact_response_rate, last_calculated, Meta.db_table) all match the plan.

---

### T4: Create SellerVerification Model — PASS

**Plan:** Create `SellerVerification` model with `user` (OneToOne), `phone_number`, `verified_by_admin`, `verified_at`.

**Actual:** Model exists at `src/backend/apps/trust/models.py` (lines 36–49) with all specified fields and `db_table = "seller_verifications"`. Matches plan.

**No issues.**

---

### T5: Create TrustCalculator Service — DEVIATION

The `TrustCalculator` class exists at `src/backend/apps/trust/services/trust_calculator.py` and is functionally complete, but the scoring algorithm **deviates significantly** from the plan's specified weights, thresholds, and logic.

#### 5.1 Scoring Weights

| Component | Plan | Actual |
|-----------|------|--------|
| Activity max | 15 (5 pts/ad, capped at 3 ads) | 40 (5 pts/ad, capped at 8 ads) |
| Quality max | 40 | 30 |
| Response max | 30 | 30 |
| **Total max** | **85** | **100** |

The plan specifies `Activity Score (0-15)` with `published * 5, capped at 15`. The actual code uses `_ACTIVITY_MAX = 40` with `_ACTIVITY_POINTS_PER_AD = 5`, capping at 8 ads.

The plan specifies `Quality Score (0-40)` with `(1 - rejected/total) * 40`. The actual code uses `_QUALITY_MAX = 30` with `(1 - rejected/total) * 30`.

#### 5.2 Trust Level Thresholds

| Level | Plan | Actual |
|-------|------|--------|
| PRO | score >= 90 | score >= 86 (`_PRO_THRESHOLD`) |
| TRUSTED | score >= 50 | score >= 61 (`_TRUSTED_THRESHOLD`) |
| VERIFIED | has_verification (floor only) | score >= 31 (`_VERIFIED_THRESHOLD`) |
| UNVERIFIED | else | else |

The plan has **no VERIFIED threshold** — it only checks `has_verification` as a floor below the TRUSTED threshold. The actual implementation adds `_VERIFIED_THRESHOLD = 31`, meaning a user with score 31–59 gets VERIFIED even without admin verification or Telegram Premium. This is a behavioral deviation.

#### 5.3 Verification Check Logic

**Plan:**
```python
has_verification = (
    hasattr(user, "verification") and user.verification.verified_by_admin
) or getattr(user, "telegram_premium", False)
```

**Actual** (lines 237–243): Separates the two checks:
```python
has_verification = hasattr(user, "verification") and bool(
    user.verification.verified_by_admin
)
has_premium = getattr(user, "telegram_premium", False)
if has_verification or has_premium:
    return TrustLevel.VERIFIED
```

Functionally equivalent (both use OR), but structurally different. The plan combines them into one expression; the actual code separates them. Not a behavioral deviation.

#### 5.4 Response Score Calculation

**Plan:** Returns `(responses / total_contacts) * 30` (unrounded float).

**Actual** (line 157): Returns `round((responses / total_contacts) * self._RESPONSE_MAX, 2)` — rounds to 2 decimal places. Minor deviation.

#### 5.5 Total Score Aggregation

**Plan:** `total = activity_score + quality_score + response_score` (response_score is a float, so total is a float).

**Actual** (line 53): `total = activity_score + quality_score + int(response_score)` — converts response_score to int before adding. This means fractional response scores are truncated. For example, a response score of 20.7 becomes 20 in the total. This is a behavioral deviation that affects threshold crossing.

#### 5.6 Return Type of `_get_trust_level`

**Plan:** Returns `str`.
**Actual:** Returns `TrustLevel` (the enum member itself). This is actually an improvement — the plan's `-> str` annotation is less type-safe.

#### 5.7 `save()` Call

**Plan:** `trust_score.save()` (no `update_fields`).
**Actual:** `trust_score.save(update_fields=[...])` with explicit field list. This is an improvement — more efficient and avoids overwriting `last_calculated` unnecessarily (though `auto_now=True` would update it anyway).

#### 5.8 Logging

**Plan:** Uses f-strings: `f"Created trust score for user {user.id}"`.
**Actual:** Uses lazy `%s` formatting: `"Created trust score for user %s", user.id`. This is an improvement per Python logging best practices (avoids string formatting when log level is disabled).

#### 5.9 Summary

The `TrustCalculator` is structurally complete and functional, but the **scoring weights, thresholds, and aggregation logic differ from the plan**. The actual implementation uses a 100-point scale (40+30+30) with thresholds at 86/61/31, while the plan specifies an 85-point scale (15+40+30) with thresholds at 90/50. The actual implementation also adds a VERIFIED_THRESHOLD (31) that the plan does not have, and truncates the response score via `int()` before aggregation.

---

### T6: Add CONTACT_RESPONSE Event — PASS

**Plan:** Add `CONTACT_RESPONSE = "contact_response"` to `AnalyticsEventType` in `apps/core/enums.py`.

**Actual:** Member exists at `src/backend/apps/core/enums.py` (line 62). The enum also contains many additional members beyond the plan's specification (SELLER_VERIFIED, TRUST_LEVEL_UPDATED, MODERATION_APPROVED, etc.), but `CONTACT_RESPONSE` is present.

**No issues.**

---

### T7: Add record_contact_response Method — FAIL (NOT IMPLEMENTED)

**Plan:** Add `record_contact_response(seller_telegram_id: int) -> None` to `apps/core/services/contact.py`. Export from `apps/core/services/__init__.py`. Hook into bot contact flow.

**Actual:**
- `src/backend/apps/core/services/contact.py` does **not** contain `record_contact_response`. The file has `can_contact_seller`, `get_seller_for_contact`, and `record_contact_initiated` only.
- `src/backend/apps/core/services/__init__.py` does **not** export `record_contact_response`. It exports only `can_contact_seller`, `record_contact_initiated`, `get_seller_for_contact`.
- `src/telegram_bot/handlers/contact.py` does **not** call `record_contact_response`. The bot contact handler (`handle_contact_orm`) only calls `record_contact_initiated`.

**This task is completely unimplemented.** The `CONTACT_RESPONSE` event type exists in the enum (T6), but there is no service function to record it, no export, and no bot integration.

**Impact:** The `TrustCalculator._calculate_response_score()` method depends on `CONTACT_RESPONSE` events to compute the response score. Without `record_contact_response`, no `CONTACT_RESPONSE` events will ever be created, so the response score component will always be 0.

---

### T8: Create Badge Templates — PASS

**Plan:** Create three badge templates in `templates/components/badges/`: `verified_badge.html`, `trusted_badge.html`, `pro_badge.html`.

**Actual:** All three templates exist at `src/backend/templates/components/badges/`. Each contains:
- Tailwind CSS classes matching the plan's color scheme (blue for verified, green for trusted, purple for pro)
- SVG icons matching the plan's SVG paths
- Accessibility attributes (`aria-label`, `role="status"`, `aria-hidden="true"`)
- HTML comments documenting usage and dependencies

The templates are more polished than the plan's minimal versions (they include `aria-label`, `role`, and `<span>` wrappers around text), but the visual output matches the plan.

**No issues.**

---

### T9: Create Trust Template Tags — DEVIATION

**Plan:** Create `trust_badge` inclusion tag in `apps/trust/templatetags/trust_tags.py`. The plan describes two approaches:
1. Inclusion tag with `BADGE_TEMPLATES` dict mapping levels to templates, returning `{"show_badge": True, "template": template_path, "trust_level": score.trust_level}`
2. Simple tag using `render_to_string` for dynamic template selection

**Actual implementation** (`src/backend/apps/trust/templatetags/trust_tags.py`):

The actual code uses an `@register.inclusion_tag` but **does not implement dynamic template selection**. Key deviations:

#### 9.1 No `BADGE_TEMPLATES` dict

The plan specifies a `BADGE_TEMPLATES` dict mapping `TrustLevel` members to template paths. The actual code does **not** have this dict. The `inclusion_tag` is registered with a hardcoded template:

```python
@register.inclusion_tag("components/badges/verified_badge.html", takes_context=False)
```

This means **all non-UNVERIFIED trust levels (VERIFIED, TRUSTED, PRO) will render the `verified_badge.html` template**. A TRUSTED seller will see a "Verified" badge, and a PRO seller will also see a "Verified" badge. The `trusted_badge.html` and `pro_badge.html` templates are never rendered.

The plan explicitly acknowledges this limitation (line 447: "Template tags in Django require a wrapper since `inclusion_tag` does not support dynamic template paths") and provides an alternative `simple_tag` approach using `render_to_string`. The actual implementation does **not** use either the `BADGE_TEMPLATES` dict + `{% include %}` pattern or the `simple_tag` + `render_to_string` approach.

#### 9.2 Different return context

**Plan:** Returns `{"show_badge": True, "template": template_path, "trust_level": score.trust_level}` (or `{"show_badge": False}` for no badge).

**Actual:** Returns `{"trust_level": trust_score.trust_level}` (or `{}` for no badge / UNVERIFIED level). The `show_badge` and `template` keys are absent.

#### 9.3 Different data access pattern

**Plan:** Uses `user.trust_score` (Django reverse relation access via `OneToOneField`).

**Actual:** Uses `SellerTrustScore.objects.get(user=user)` (explicit query). This is actually more robust — it avoids `AttributeError` if the `trust_score` relation is not loaded, and it works with `AnonymousUser` (which would raise `DoesNotExist` and return `{}` rather than crashing).

#### 9.4 No anonymous user check

**Plan:** Checks `user.is_anonymous` first and returns `{"show_badge": False}`.

**Actual:** Does not check `user.is_anonymous`. Instead, it attempts `SellerTrustScore.objects.get(user=user)`. For an `AnonymousUser`, this would raise `SellerTrustScore.DoesNotExist` (caught by the `except` block), so it returns `{}`. Functionally this works, but it performs a database query for anonymous users that the plan's approach would avoid.

#### 9.5 UNVERIFIED filtering

**Plan:** Does not explicitly filter UNVERIFIED level (would return `{"show_badge": True, "template": None, "trust_level": "unverified"}`).

**Actual:** Explicitly returns `{}` for `TrustLevel.UNVERIFIED` (line 53–54). This is an improvement — UNVERIFIED sellers don't get a badge.

#### 9.6 Summary

The template tag is functional but **the badge rendering is broken for TRUSTED and PRO levels** — they will always render the "Verified" badge. The plan's design for dynamic template selection (via `BADGE_TEMPLATES` dict + `{% include %}`, or `simple_tag` + `render_to_string`) was not implemented.

---

### T10: Register apps.trust in Settings — PASS

**Plan:** Add `"apps.trust"` to `INSTALLED_APPS` in `config/settings/base.py` after `"apps.search"`.

**Actual:** `"apps.trust"` is in `INSTALLED_APPS` at `src/backend/config/settings/base.py` (line 101). It appears after `"apps.search"` (line 99) and `"apps.media"` (line 100). The plan says "after `apps.search`" but the actual order has `apps.media` between them. This is a minor ordering difference that does not affect functionality.

**No issues.**

---

### T11: Update ad_list Template — FAIL (NOT IMPLEMENTED)

**Plan:** Add trust badge after ad title in `templates/ads/partials/ad_list.html` (line ~39). The plan provides two template approaches:
```html
{% if ad.user.trust_score %}
    {% render_trust_badge ad.user %}
{% endif %}
```
or:
```html
{% if ad.user.trust_score %}
    {% trust_badge ad.user as badge_ctx %}
    {% if badge_ctx.show_badge and badge_ctx.template %}
        {% include badge_ctx.template %}
    {% endif %}
{% endif %}
```

**Actual:** The template at `src/backend/templates/ads/partials/ad_list.html` does **not** load `trust_tags` and does **not** render any trust badge. The ad title is rendered as:
```html
<h2 class="font-semibold text-lg mb-2 line-clamp-2">{{ ad|get_title:LANGUAGE_CODE }}</h2>
```
There is no badge integration. The template only loads `localized_content` and `i18n` tags.

**This task is completely unimplemented.**

---

### T12: Update Detail Template — FAIL (NOT IMPLEMENTED)

**Plan:** Add trust badge inline with title in `templates/ads/detail.html` (line ~41):
```html
<h1 class="text-3xl font-bold mb-4">
    {{ ad.title }}
    {% if ad.user.trust_score %}
        {% render_trust_badge ad.user %}
    {% endif %}
</h1>
```

**Actual:** The template at `src/backend/templates/ads/detail.html` does **not** load `trust_tags` and does **not** render any trust badge. The ad title is rendered as:
```html
<h1 class="text-3xl font-bold mb-4">{{ ad|get_title:LANGUAGE_CODE }}</h1>
```
There is no badge integration. The template loads `static`, `contact_tags`, `localized_content`, and `i18n` tags, but not `trust_tags`.

**This task is completely unimplemented.**

---

### T13: Hook Score Updates to Publish — PASS

**Plan:** In `_pass_moderation()` in `apps/moderation/services/auto_moderation.py`, after creating analytics events, add:
```python
TrustCalculator().calculate_and_save(ad.user)
```
Also add the import at the top of the file.

**Actual:** Both the import and the call are present:
- Import at line 21: `from apps.trust.services.trust_calculator import TrustCalculator`
- Call at line 249: `TrustCalculator().calculate_and_save(ad.user)` — placed after the `AnalyticsEvent` creation for `AD_PUBLISHED` and `MODERATION_APPROVED` (lines 237–247), before the `logger.info` call (line 251).

The actual `_pass_moderation` also creates a `MODERATION_APPROVED` analytics event (lines 243–247) that the plan does not mention, but this is an addition, not a deviation.

**No issues.**

---

## Additional Observations

### A. Tests Exist Beyond Plan Scope

The file `src/backend/apps/trust/tests/test_trust_calculator.py` contains a comprehensive test suite (613 lines, 15 test methods) covering:
- Zero-ads scoring
- Published ads scoring
- Activity score cap
- Verification bonuses (admin and Telegram Premium)
- Rejection penalties
- Rejection rate persistence
- Trust level mapping (UNVERIFIED, VERIFIED, TRUSTED, PRO thresholds)
- Response score calculation
- Idempotency of `calculate_and_save`

The tests use the **actual implementation's thresholds** (86/61/31), not the plan's thresholds (90/50). This confirms the tests were written against the actual code, not the plan. The tests would need updating if the scoring algorithm is changed to match the plan.

### B. `__init__.py` Exports

The `templatetags/__init__.py` exports `trust_badge` (line 5), which is an improvement over the plan's empty `__init__.py`. This allows `from apps.trust.templatetags import trust_badge` if needed.

### C. Migration

The migration `0001_initial.py` exists and matches the model definitions. The `trust_level` field in the migration has no default (matching the actual model code, which also has no default). The `choices` in the migration use `[("unverified", "unverified"), ("verified", "verified"), ("trusted", "trusted"), ("pro", "pro")]` — matching the actual model code's `[(level.value, level.value) for level in TrustLevel]`.

### D. Bot Contact Handler

The bot contact handler (`src/telegram_bot/handlers/contact.py`) calls `record_contact_initiated` but does **not** call `record_contact_response`. This is the integration point that T7 would require. Without it, the response score component of the trust calculator will always be 0.

### E. Documentation References

The technical specification at `docs/01-spec/technical-specification.md` (line 138) references trust badges rendered via the `trust_badge` template tag on ad detail and list pages. This documentation is **ahead of the implementation** — the templates (T11, T12) do not yet integrate the badge.

---

## Rollout Analysis

### Risks

| Risk | Level | Description |
|------|-------|-------------|
| Broken badge rendering | High | TRUSTED and PRO sellers will display "Verified" badge due to hardcoded `verified_badge.html` in inclusion_tag (T9) |
| Response score always 0 | High | `record_contact_response` (T7) is not implemented, so response score component is always 0 |
| Missing badge display | High | Badges are not rendered on ad list (T11) or detail (T12) pages |
| Scoring algorithm mismatch | Medium | Actual weights (40/30/30, thresholds 86/61/31) differ from plan (15/40/30, thresholds 90/50) |
| Missing model default | Low | `trust_level` field has no default; relies on `TrustCalculator` always setting it explicitly |

### Dependencies

- T7 (`record_contact_response`) depends on T6 (`CONTACT_RESPONSE` event type) — T6 is done, T7 is not
- T9 (`trust_tags`) depends on T1 (`TrustLevel`) and T3 (`SellerTrustScore`) — both done
- T11 and T12 (template integration) depend on T9 (`trust_tags`) — T9 is done but broken
- T13 (score hook) depends on T5 (`TrustCalculator`) — both done

### Sequencing Concerns

The implementation order appears to have been: T0 → T1 → T2 → T3 → T4 → T5 → T6 → T8 → T9 → T10 → T13 (9 tasks), skipping T7, T11, and T12 entirely. The scoring algorithm was also redesigned from the plan's specification during implementation.

---

## Required Fixes

1. **T7 — Implement `record_contact_response`:** Add the function to `apps/core/services/contact.py`, export from `__init__.py`, and call it from the bot contact handler when the seller responds to a buyer's contact message.

2. **T11 — Integrate badge into `ad_list.html`:** Load `trust_tags` and render the badge after the ad title.

3. **T12 — Integrate badge into `detail.html`:** Load `trust_tags` and render the badge inline with the ad title.

4. **T9 — Fix dynamic template selection:** Implement the `BADGE_TEMPLATES` dict and either the `{% include %}` pattern or the `simple_tag` + `render_to_string` approach so that TRUSTED and PRO sellers render the correct badge templates.

5. **T3 — Add `default=TrustLevel.UNVERIFIED`:** Add the missing default to the `trust_level` field to match the plan and prevent `IntegrityError` from non-`TrustCalculator` code paths.

---

## Advisory Recommendations

1. **Align scoring algorithm with plan:** Consider whether the actual weights (40/30/30, thresholds 86/61/31) or the plan's weights (15/40/30, thresholds 90/50) are correct. The tests are written for the actual implementation. If the plan's weights are preferred, update both the `TrustCalculator` and the test suite.

2. **Consider `select_related` for badge rendering:** The `trust_badge` template tag performs a separate `SellerTrustScore.objects.get(user=user)` query per ad. For ad lists with many ads, this causes N+1 queries. Consider using `select_related("trust_score")` in the ad list view.

3. **Update documentation:** The technical specification references badge rendering on ad list and detail pages. Once T11 and T12 are implemented, verify the documentation matches the actual template integration.
