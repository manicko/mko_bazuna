# Discrepancies: Plans 14-16 vs. Current Implementation

## Context

This report captures deviations between the development plans/specifications
(`14_seller-cabinet-ad-gallery`, `15_catalog-ui-avito`, `16_user-cabinet`) and the
**actual implemented code**, identified during the documentation-update task.
These affect how the implemented functionality must be documented.

All deviations below are **behaviorally mitigated** in the implementation and do
not represent security holes, but they diverge from the original written plan and
must be reflected accurately in the docs.

---

## 1. Preferred-city cookie lifetime: 30 days (planned) vs. 365 days (implemented)

- **Planned/spec:** `docs/07-design-researches/Design_03/city-selection-report.md`
  §11.2 (line 353) and §13.2 specify a **30-day** `preferred_city` cookie
  (`max_age = 2592000`).
- **Implemented:** `src/backend/apps/search/middleware/preferred_city.py`
  line 30 — `PREFERRED_CITY_COOKIE_MAX_AGE = 365 * 24 * 60 * 60` (**1 year**).
  The unit test `test_preferred_city.py:100-101` explicitly asserts
  `int(cookie["max-age"]) == PREFERRED_CITY_COOKIE_MAX_AGE` (1 year).
- **Assessment:** The preferred-city research report itself flagged the 30-day
  value as something to revisit; the implementation intentionally moved to 1 year
  for cross-session persistence. This is an intentional decision, not a defect.
- **Documentation impact:** When documenting preferred-city persistence, use the
  **1-year** value. The city-selection report's cookie spec table must be updated
  to avoid contradicting the implementation.

## 2. Preferred-city persistence model: `UserProfile` (considered) vs. direct FK (chosen)

- **Planned:** Plan 15 T-100 posed a Go/No-Go on whether to create a new
  `UserProfile` model or add the FK directly to `User`.
- **Implemented:** A **direct `ForeignKey`** placed on the existing `User` model
  (`apps/users/models.py` `preferred_city`), with migration
  `apps/users/migrations/0003_user_preferred_city.py`. No `UserProfile` model
  exists anywhere in the codebase (grep confirms zero references).
- **Assessment:** This is option (b) from T-100's acceptance criteria — the chosen
  path. No defect.
- **Documentation impact:** `db-schema.md` must add the `preferred_city_id` column
  to the `users` table and must NOT describe a `UserProfile` model.

## 3. Preferred-city consent gating: middleware-approach (recommended) vs. SET-gating (implemented)

- **Planned/recommended:** `docs/97-plans/consent-banner-gdpr-research-report.md`
  §5/Missing Components #4 (line 242) and §6 Post-Launch #1 (line 275) recommend a
  **cookie-consent middleware** that *intercepts/blocked* the `preferred_city`
  cookie before consent is given.
- **Implemented:** Instead of a blocking middleware, the cookie **write** is
  gated at the source — `set_preferred_city` (`apps/search/views/preferred_city.py`
  line 78) only sets the cookie when
  `request.COOKIES.get("consent_preferences") == "true"`. The authenticated DB
  preference persists regardless of cookie consent.
- **Assessment:** Different mechanism, same compliance outcome (no non-essential
  cookie set before consent). Both the research recommendation and the
  implementation prevent the cookie pre-consent.
- **Documentation impact:** Document the actual SET-gating behavior; note the
  research recommendation (blocking middleware) was satisfied by source-gating
  instead.

## 4. GLightbox loading: unconditional (spec GAL-001) vs. consent-gated (implemented)

- **Planned:** Plan 14 GAL-001 expected the GLightbox JS + inline init to load
  **unconditionally** on the ad-detail page (CSP is report-only; no settings
  change required).
- **Implemented:** `templates/ads/detail.html` line 15 loads the GLightbox
  **CSS `<link>` unconditionally** in `<head>`, but the GLightbox **JS `<script>`
  and inline `GLightbox({...})` init are gated behind
  `{% if consent_analytics %}` (line 112 `{% if %}` / line 126 `{% endif %}`).
  This gating was introduced by later consent-banner-compliance work (plan 21,
  items D7 / T-06b). Before consent, the gallery anchors + CSS exist but GLightbox
  JS is absent → plain-image navigation fallback (progressive enhancement).
- **Assessment:** A deliberate post-GAL-001 consent-compliance refinement, not a
  gap.
- **Documentation impact:** Document that GLightbox JS is consent-gated (loads only
  after `consent_analytics`); the CSS link is always present.

## 5. Publish-time alert signal trigger: transition (spec) vs. any PUBLISHED re-save (implemented)

- **Planned:** Plan 16 feature 3 / alert-delivery-research §(Approach 1) expected the
  `post_save` receiver to fire when an ad **transitions** to `PUBLISHED`
  (DRAFT → … → PUBLISHED).
- **Implemented:** `apps/moderation/signals.py:55`
  `deliver_immediate_alerts_on_publish` fires on **every** `Ad` `post_save` where
  `instance.status == AdStatus.PUBLISHED` — including a PUBLISHED→PUBLISHED
  re-save. Double delivery is prevented by the `SavedSearchNotification`
  idempotency (`uq_saved_search_ad` + `ignore_conflicts=True`).
- **Assessment:** Behaviorally safe (idempotent), but the trigger condition is
  broader than the strict "transition" wording.
- **Documentation impact:** Describe the actual condition (`status == PUBLISHED`
  on save) and note idempotency handles re-saves.

## 6. Per-ad alert message + unsubscribe: immediate path only (implemented), not daily digest

- **Planned:** Plan 16 feature 6 specifies the per-ad alert message (title/city/
  price + absolute ad link + inline `[Turn off alerts]` button) and the
  `/start unsub_<token>` deep-link fallback.
- **Implemented:** The per-ad message format + inline `unsub:<token>` button +
  ownership-validated callback handler (`telegram_bot/handlers/alerts.py`) +
  `/start unsub_<token>` deep-link are implemented **only on the publish-time
  (immediate) path** (`immediate_alerts.py:90 build_alert_message`).
  The **daily `send_alerts` digest** (`_format_digest`) sends a consolidated
  plain-text summary (title + price only, capped 10 ads) with **no absolute ad
  links and no unsubscribe inline button**.
- **Assessment:** The plan scoped feature 6 to per-ad publish-time messages (so
  the daily-digest omission is consistent with intent), but the behavioral
  difference (two alert shapes) is worth recording.
- **Documentation impact:** Document that inline unsubscribe applies to
  near-real-time per-ad alerts; the daily digest is a summary without an inline
  unsubscribe button.
