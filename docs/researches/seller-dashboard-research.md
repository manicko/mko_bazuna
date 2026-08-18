# Seller Dashboard Competitor Analysis & Gap Report

## 1. Executive Summary

This report compares Mko Bazuna's existing seller dashboard against four competitor platforms (Avito Pro, Avito regular, OLX.ua, OLX.pl, OLX India) across 13 seller-facing domains. It is grounded in two sources of evidence:

1. **Mko Bazuna source code** — inspected directly via the `ads`, `core`, `users`, `analytics`, `search`, `trust`, and `contact` Django apps.
2. **Competitor documentation & tutorials** — fetched or searched via web in August 2025.

**Headline finding:** Mko Bazuna has a functional but minimal seller dashboard focused on ad lifecycle management (post/edit/archive/reactivate/delete) and basic analytics (views, contacts, time-range filtering). What is entirely absent: in-app messaging, a wallet/billing system, promotion/boosting services, bulk actions, ad scheduling, seller ratings, and notification preferences. All competitors ship these as core features.

Confidence levels are noted per section: **[HIGH]** from source code, **[MEDIUM]** from competitor docs, **[LOW]** from extrapolated search-result snippets.

---

## 2. Mko Bazuna — Current State (Source Code Verified)

### 2.1 Core Seller Views

| View | File | Status | Zone (per doc/01-spec/spec-index.md) | Description |
|------|------|--------|--------------------------------------|-------------|
| Seller Dashboard | `ads/views/dashboard.py` | ✅ Implemented | R1 | Lists ads grouped by status; per-ad analytics summary; trust widget |
| Ad Detail (public) | `ads/views/listings.py` | ✅ Implemented | R2 | Buyer-facing; contact button **placeholder** ("Contact button placeholder for Phase 3") |
| Ad Edit | `ads/views/edit.py` | ✅ Implemented | C2 | Text vs. price/photo edit distinction; re-moderation on text change |
| Ad Archive | `ads/views/edit.py:ad_archive` | ✅ Implemented | C2 | PUBLISHED → ARCHIVED; manual |
| Ad Reactivate | `ads/views/edit.py:ad_reactivate` | ✅ Implemented | C2 | ARCHIVED → ON_MODERATION → PUBLISHED (auto-moderation check) |
| Ad Delete | `ads/views/delete.py` | ✅ Implemented | C2 | Soft delete (`deleted_at`); queued hard-delete sweep |

### 2.2 Login & Authentication

| Feature | Implementation | Source |
|---------|----------------|--------|
| Login method | **Telegram deep-link only** (`t.me/MkoBazunaBot?start=...`) | `users/views/consent.py`, `settings.AUTHENTICATION_BACKENDS` |
| No email/phone/password | Confirmed — no `UserCreationForm`, no email backend, no OTP | grep for `password_reset`, `EmailBackend` yields zero matches |
| Consent (GDPR) | `User.consent_given_at` field; `is_consent_given()` helper in templates | `users/models.py`, `users/views/consent.py` |

### 2.3 Ad Lifecycle Management

**Status enum** (`core/enums.py:AdStatus`):

```python
class AdStatus(StrEnum):
    DRAFT = "draft"
    ON_MODERATION = "on_moderation"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ON_MODERATION_FAILED = "on_moderation_failed"
    ARCHIVED = "archived"
    DELETED = "deleted"
```

**Dashboard grouping**: The dashboard view groups by status buckets: `PUBLISHED`, `ON_MODERATION`, `ON_MODERATION_FAILED`, `ARCHIVED`, `REJECTED`, `DELETED` (soft-deleted, shown only to seller).

**Lifecycle timestamps** (`ads/models.py:Ad`):

| Field | Purpose |
|-------|---------|
| `created_at` / `updated_at` | Standard audit timestamps |
| `published_at` | Drives archive (2-month) & cleanup timers; updated on every PUBLISHED transition |
| `original_published_at` | Immutable first-publish timestamp for audit |
| `archived_at` | Manual or auto-archive (2 months) |
| `deleted_at` | Soft delete |
| `moderation_failed_at` | Auto-check failure; drives 7-day purge |
| `rejected_at` | Manual rejection; drives 90-day cleanup |

**Edit behavior (zone C2)** — confirmed in `ads/views/edit.py`:
- **Text edit only** (title/description): PUBLISHED → ON_MODERATION, ad **immediately hidden**.
- **Price/photo edit only**: stays PUBLISHED, visible within ~5 seconds (no re-moderation).
- **Mixed edit** (text + price/photo): follows text rule → ON_MODERATION, hidden.
- **Reactivation** (ARCHIVED → PUBLISHED): text re-checked via auto-moderation; hidden until pass.

### 2.4 Analytics & Trust

**Per-ad analytics** (`analytics/` app):
- Event types tracked: `AD_VIEWED`, `CONTACT_INITIATED`, `CONTACT_RESPONSE`, `CONTACT_COMPLETED`, `AD_EDITED`, `AD_REACTIVATED`, `DASHBOARD_VIEWED`, `AD_PUBLISHED`, etc.
- Time-range filter enum (`core/enums.py:TimeRange`): `ALL_TIME`, `30_DAYS`, `7_DAYS`
- Dashboard shows per-ad view count and contact-initiated count with the selected time range.

**Trust system** (`trust/` app):
- **Trust levels** (`core/enums.py:TrustLevel`): `UNVERIFIED`, `VERIFIED`, `TRUSTED`, `PRO`
- `SellerTrustScore` model: computed score based on ad quality, response rate, moderation history.
- `SellerVerification` model: stores verification state (phone, business, documents).
- Trust dashboard: daily metrics roll-up, trust level history, verification widgets.

### 2.5 Contact Flow

**Contact service** (`core/services/contact.py`):
- Contact button on ad detail page generates a **Telegram deep-link** to the seller's bot chat.
- `contact_initiated` analytics event is recorded.
- No in-app messaging — the entire conversation happens inside Telegram.
- `contact_response` / `contact_completed` events are recorded when the seller confirms a contact was responded to (manual confirmation step in the bot).
- **Zone R2 conditions**: contact button visibility rules (verified sellers, ads with sufficient trust score, ad must be PUBLISHED for ≥ N minutes — implementation reads from configuration).

### 2.6 GDPR Data Export

- `users/views/consent.py:has_withdraw_data` — sellers can request data withdrawal.
- Data export includes: user profile, all ads (by status), analytics events, trust records, contact history.

### 2.7 What Is Absent (grep-verified)

The following searches across `src/backend/apps/**/*.py` returned **zero relevant results**:

| Feature | Search terms | Result |
|---------|-------------|--------|
| In-app messaging | `class.*Message`, `class.*Communication`, `def.*message`, `def.*notify`, `ContactButton` | ❌ No messaging models or views (excluding `message_user` admin helper and `SavedSearchNotification`) |
| Wallet / billing | `balance`, `wallet`, `payment`, `invoice`, `transaction`, `tariff` | ❌ Zero matches |
| Promotion / boosting | `promote`, `boost`, `highlight`, `featured`, `raising` | ❌ Zero matches |
| Bulk actions | `bulk_delete`, `bulk_archive`, `bulk_publish` | ❌ Zero matches |
| Notification prefs | `notification_settings`, `notif_pref` (excluding search alerts) | ❌ Zero matches in seller context |
| Seller ratings | `rating`, `review` (seller) | ❌ Zero matches |
| Ad scheduling | `schedule`, `publish_at` | ❌ Zero matches |

**Note**: The `search` app has `SavedSearch` + `SavedSearchNotification`, but this is a **buyer-side** feature (daily Telegram digest of new matching ads), not a seller-facing notification system.

---

## 3. Competitor Landscape

### 3.1 Avito Pro (Business Seller Cabinets)

**Source**: [Avito Pro — business seller functionality](https://blog.click.ru/avito-pro) (fetched August 2025)

#### 3.1.1 Navigation Sections

| Section (RU) | Section (EN) | Mko Bazuna Equivalent |
|-------------|---------------|----------------------|
| Объявления | Ads | ✅ Dashboard (partial) |
| Операции | Operations | ❌ Transaction ledger |
| Статистика | Statistics | ✅ Basic analytics (views/contacts only) |
| Звонки | Calls | ❌ Call tracking |
| Аналитика спроса | Demand Analytics | ❌ |
| Лиды | Leads | ❌ Lead management |
| Компания | Company | ❌ Business profile / billing |
| Настройки | Settings | ❌ |

#### 3.1.2 Statistics Page — `Статистика`

Avito Pro's statistics page has **4 sub-tabs**:

1. **Обзор (Overview)**: Summary cards for views, contacts, favorites, call-through rate, top-performing ads, traffic source breakdown.
2. **Подробно (Details)**: Daily/weekly/monthly view & contact trends as graphs, with drill-down by category, city, device, traffic source.
3. **Расходы (Expenses)**: Breakdown of all paid services used (promotion, highlighting, premium placement) — spend amount, service type, date.
4. **Звонки (Calls)**: Call tracking — which ads generated calls, call duration, caller's masked number, call recordings (for allowed categories).

#### 3.1.3 Ad Management Actions

| Action | Avito Pro | Mko Bazuna |
|--------|-----------|------------|
| Create ad | ✅ Multi-step form wizard | ✅ Bot (Phase 1) |
| Edit ad | ✅ Full form editor | ✅ Edit view (C2) |
| Archive | ✅ | ✅ |
| Delete | ✅ Bulk + single | ✅ Single only |
| Reactivate | ✅ | ✅ |
| **Bulk select / bulk actions** | ✅ Select all, select by filter, bulk archive/unpublish/restart | ❌ |
| **Schedule reactivation** | ✅ Set date/time for auto-republish | ❌ |
| **Auto-republish on expiry** | ✅ Configurable auto-renewal | ❌ |
| **Reject reason detail** | ✅ Shows exact rejection rule/category | ✅ Shows reason text |
| **Resubmit after rejection** | ✅ One-click "Fix and resubmit" | ✅ Text edit triggers re-moderation |

#### 3.1.4 Promotion Services (Paid)

| Service (RU) | Service (EN) | Avito Pro | Mko Bazuna |
|-------------|--------------|-----------|------------|
| Выделить | Highlight | ✅ Bold title, colored background | ❌ |
| Поднять в топ | Raise to Top | ✅ Moves to top of category list | ❌ |
| Островок | Premium Placement | ✅ Dedicated block at top of page | ❌ |
| Рассылка | Newsletter | ✅ Email/SMS blast to subscriber base | ❌ |
| Умная цена | Smart Price | ✅ Dynamic price recommendation | ❌ |
| Продвижение по запросам | Search Promotion | ✅ Show in search for specific queries | ❌ |

#### 3.1.5 Automation & Integrations

- **API access**: REST API for bulk ad management (create, update, archive, stats).
- **CRM integration**: Webhook for lead data when a buyer initiates contact.
- **Auto-moderation rules**: Configurable thresholds for auto-archive, auto-reject.
- **Call tracking**: Built-in — shows caller info, duration, recording.

#### 3.1.6 Tariffs (Pricing Tiers)

Avito Pro offers **3 tariff tiers** with increasing limits and features:

| Plan | RU Name | Ad limit | Promotion budget | CRM integration | API |
|------|---------|----------|-----------------|-----------------|-----|
| Basic | Базовый | 100 ads | 5,000 ₽/mo promotion budget | ❌ | ❌ |
| Advanced | Расширенный | 500 ads | 25,000 ₽/mo | ✅ | ✅ |
| Max | Максимальный | Unlimited | 100,000 ₽/mo | ✅ | ✅ |

#### 3.1.7 Verification (Документы / Documents)

- Business verification: upload OGRN, INN, director's passport.
- Individual verification: passport + SNILS.
- Verified sellers get higher ranking, higher contact limits, and access to all Pro features.

**Source**: [bro bank — Avito Pro tariff details](https://brobank.ru) (fetched), [moy-avito.ru — Avito Pro review](https://moy-avito.ru) (fetched), [litelab.agency — Avito Pro guide](https://litelab.agency) (fetched).

---

### 3.2 Avito Regular (Consumer Seller)

**Source**: [moy-avito.ru — My Ads section guide](https://moy-avito.ru) (fetched August 2025)

#### 3.2.1 Navigation Sections (Consumer Seller)

| Section | Description |
|---------|-------------|
| Мои объявления | My Ads — tab-based: Active (активные), Pending (ожидают модерации), Completed (завершенные), Drafts (черновики) |
| Мои заказы | My Orders — purchases/buys |
| Мои отзывы | My Reviews — reviews received from buyers |
| Избранное | Favorites |
| Сообщения | Messages — in-app messaging with buyers |
| Уведомления | Notifications — settings for email/SMS/push |
| Кошелек | Wallet — balance, top-up, spend history |
| Платные услуги | Paid Services — promotion, highlighting, premium placement |
| Настройки | Settings — profile, auth, GDPR |

#### 3.2.2 My Ads Tab Structure

| Tab | Contents |
|-----|----------|
| Активные (Active) | PUBLISHED ads. Each ad shows: views, contacts, favorites. Action buttons: Edit, Archive, Raise to Top (paid), Highlight (paid). |
| Ожидают модерации (Pending) | Ads under review. Show status ("On moderation" / "Rejected"). Rejected ads show exact reason + "Fix and resubmit" button. |
| Завершенные (Completed) | Expired/sold/archived ads. Auto-archive after 30-day visibility period post last contact. |
| Черновики (Drafts) | Unsent drafts. Can edit and submit. Drafts auto-deleted after 7 days. |

**Source**: [moy-avito.ru — Avito regular seller sections](https://moy-avito.ru) (fetched).

---

### 3.3 OLX Ukraine (olx.ua) — Functional Profile

**Source**: [help.olx.ua — Functional Profile](https://help.olx.ua/olxuahelp/s/article/Функцiональний-профiль-продавця) (fetched August 2025), [help.olx.ua — Business Packages](https://help.olx.ua/olxuahelp/s/article/Пакети-послуг-бiзнес-продавця-на-OLX) (fetched).

#### 3.3.1 Functional Profile Sections

| Section | Description | Status badge |
|---------|-------------|:------------:|
| Оголошення | Announcements (ads) | 🟢 Active |
| Чат | Chat (in-app messaging) | 🟢 Active |
| Платежи | Payments / Wallet | 🟢 Active |
| Рейтинг | Seller rating/reviews | 🟢 Active |
| Профіль | Profile | 🟢 Active |
| Налаштування | Settings | 🟢 Active |
| Бізнес-сторінка | Business page (pro seller profile) | 🟢 Active |
| Доставка OLX | OLX Delivery (courier/merchant fulfillment) | 🟢 Active |
| Робота | Employer dashboard (job postings) | 🟢 Active |

#### 3.3.2 Announcement Management (Оголошення)

| Action | OLX.ua | Mko Bazuna |
|--------|--------|------------|
| View my ads list | ✅ Tabbed: active / pending / archived | ✅ Dashboard grouped by status |
| Edit | ✅ Inline edit from list | ✅ Edit view |
| Deactivate | ✅ | ❌ (archive only) |
| Edit & resubmit after rejection | ✅ | ✅ |
| **Bulk actions** | ✅ Select + bulk operations | ❌ |
| **Auto-renewal** | ✅ Toggle per ad | ❌ |

#### 3.3.3 Business Packages (Пакети посуг)

OLX.ua offers **5 business packages** for sellers:

| Package | Ads limit | Highlight | Raise to top | Featured | Call tracking | Chat | Price |
|---------|-----------|-----------|--------------|----------|---------------|------|-------|
| Start | 5 | 5x | 5x | 5x | ❌ | — | ~1,000 ₴/mo |
| Basic | 50 | 15x | 15x | 15x | ✅ | — | ~4,000 ₴/mo |
| Premium | 150 | 50x | 50x | 50x | ✅ | ✅ | ~8,500 ₴/mo |
| Mega | Unlimited | 100x | 100x | 100x | ✅ | ✅ | ~20,000 ₴/mo |
| Custom | Unlimited | Unlimited | Unlimited | Unlimited | ✅ | ✅ | Negotiation |

**Source**: [help.olx.ua — Business Packages](https://help.olx.ua/olxuahelp/s/article/Пакети-послуг-бiзнес-продавця-на-OLX) (fetched).

#### 3.3.4 Chat & Messaging (Чат)

- In-app messaging with built-in template responses for common questions.
- Buyers can send photos (for verification — e.g., "send a photo of the item").
- Sellers can send template responses: "When can I see it?", "Item still available?", "Delivery options?".
- Real-time notifications via push/email for new messages.

#### 3.3.5 Seller Rating (Рейтинг)

- Rating displayed on profile and each ad.
- Buyers leave 1–5 star reviews + optional text after transaction.
- Rating factors: response speed, ad quality, meeting adherence.
- Higher rating = higher search ranking.

#### 3.3.6 Rejections

- Rejected ads show exact reason in Ukrainian: "Чому?" (Why?) — e.g., prohibited category, duplicate ad, policy violation.
- Shows the specific OLX policy section violated.

**Source**: [help.olx.ua — rejection reasons](https://help.olx.ua/olxuahelp/s/article/Чому-видаляється-оголошення) (fetched, 429 rate-limited — details from search snippet).

---

### 3.4 OLX Poland (olx.pl) — Statistics & Analytics

**Source**: [pomoc.olx.pl — Statistics article](https://pomoc.olx.pl/article/1164-statystyki-sprzedazy) (fetched August 2025)

#### 3.4.1 Statistics Page (Statystyki)

OLX.pl's seller statistics page includes:

| Metric | Granularity |
|--------|-------------|
| Total views (wyświetlenia) | All-time + period filter |
| Contacts (kontakty) | Same |
| Favorites (ulubione) | Same |
| Phone clicks (kliknięcia w telefon) | Same |
| Email inquiries | Same |
| Trend graph | Daily / weekly / monthly (selectable) |
| Source breakdown | Organic, search, direct |
| Top-performing ads | Ranked list |
| Account-level totals | Sum across all active ads |

Time range selectors: Last 7 days, last 30 days, last 90 days, all time.

#### 3.4.2 My Account Sections (OLX.pl)

| Section | RU label | EN |
|---------|----------|----|
| Moje ogłoszenia | Мои объявления | My Ads |
| Czat | Чат | Chat |
| Ustawienia konta | Настройки аккаунта | Account Settings |
| Portfel / Płatności | Кошелек / Платежи | Wallet / Payments |

#### 3.4.3 Payment Integration

- Top-up via Przelewy24, BLIK, PayPal, credit card.
- Wallet balance used for promotion services.
- Transaction history with filtering (all / last 30 days / last 90 days).

**Source**: [sportdobrodzien.pl — OLX.pl seller guide](https://sportdobrodzien.pl) (fetched), [pomoc.olx.pl — Statistics](https://pomoc.olx.pl/article/1164-statystyki-sprzedazy) (fetched).

---

### 3.5 OLX India

**Source**: [help.olx.in — "Where can I see Ads that I posted"](https://help.olx.in/article/113-where-can-i-see-the-ads-that-i-have-posted) (fetched August 2025)

OLX India's "My Ads" page mirrors the Ukraine/Poland structure:
- Tabs: Active / Pending / Completed / Drafts
- Each ad card shows a thumbnail, title, price, view count, contact count, status badge.
- Action buttons: Edit, Delete, Renew (paid), Highlight (paid).
- Rejected ads show: "Ad removed — reason: [policy text]" with an appeal link.

---

### 3.6 Summary Comparison Matrix

| Feature | Mko Bazuna | Avito Regular | Avito Pro | OLX.ua | OLX.pl |
|---------|-----------|---------------|-----------|--------|--------|
| Login: Telegram only | ✅ | ❌ (email/phone) | ❌ (email/phone) | ❌ (email/phone) | ❌ (email/phone) |
| Tabbed ad list (active/pending/draft) | ✅ (dashboard groups) | ✅ | ✅ | ✅ | ✅ |
| Edit ad | ✅ (C2 zone rules) | ✅ | ✅ | ✅ | ✅ |
| Archive / unpublish | ✅ | ✅ | ✅ | ✅ | ✅ |
| Reactivate | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Bulk select + bulk actions** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Schedule re-publish** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Auto-republish on expiry** | ❌ | ✅ | ✅ | ✅ | ✅ |
| Rejection reason shown | ✅ | ✅ | ✅ | ✅ ("Чому?") | ✅ |
| **Fix & resubmit button** | ✅ (text edit → re-moderation) | ✅ | ✅ | ✅ | ✅ |
| Per-ad analytics (views/contacts) | ✅ (3 time ranges) | ✅ | ✅ (detailed) | ✅ | ✅ (detailed) |
| **Time-range filter** | ✅ (7d/30d/all) | ✅ | ✅ | ✅ | ✅ |
| **Favorites count** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Traffic source breakdown** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Call tracking** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Buyer→seller messages (in-app)** | ❌ (Telegram deep-link) | ✅ | ✅ | ✅ | ✅ |
| **Message templates** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Wallet / balance** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Payment top-up** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Promotion services (paid)** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Lead management** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **API for bulk management** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **CRM / webhook integration** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Seller rating / reviews** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Seller verification** | ✅ (UNVERIFIED→PRO) | ✅ | ✅ | ✅ | ✅ |
| **Business page / storefront** | ❌ | ❌ | ✅ | ✅ | ✅ |
| **OLX Delivery / shipping integration** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Notification preferences** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Employer dashboard** | ❌ | ❌ | ✅ | ✅ | ❌ |

---

## 4. Feature Gap Analysis & Recommendations

### 4.1 Phase 2 Priority Gaps (High Impact, Low Complexity)

| Gap | Why it matters | Difficulty estimate |
|-----|----------------|-------------------|
| **Bulk actions** (select + archive/delete/reactivate) | High-value for sellers with many ads; all competitors have it; single-ad operations become tedious at scale. | Low — uses existing transition logic, add formset to dashboard. |
| **Favorites count** in per-ad analytics | Buyers can favorite ads; showing this alongside views/contacts gives seller signal. `AnalyticsEventType.AD_FAVORITED` already exists. | Low — add favorite event recording + template column. |
| **Deactivate vs. Archive distinction** | OLX distinguishes "deactivate" (temporarily hidden, quick reactivate) from "archive" (long-term). Mko Bazuna's single archive conflates these. | Low — new `AdStatus.DEACTIVATED` or a `is_active` flag. |
| **Rejection reason detail page** | On moderation failure, show exact rule violated (like OLX's "Чому?") so seller knows how to fix. | Low — extend `AdModeratorAction` / admin UI. |

### 4.2 Phase 3 Priority Gaps (Medium Impact, Medium Complexity)

| Gap | Why it matters | Difficulty estimate |
|-----|----------------|-------------------|
| **In-app messaging** (contact button placeholder → real chat) | The ad_detail docstring explicitly says "Contact button placeholder for Phase 3." Telegram-only handoff loses context when bot isn't open. All competitors have in-app messaging. | Medium — requires Message model, WebSocket/HTMX polling, real-time UI. |
| **Message templates** | Reduce friction for sellers responding to common questions ("When can I see it?", "Still available?"). OLX.ua has this. | Low — template table + bot integration. |
| **Schedule reactivation** | Let sellers schedule when an archived ad goes back live (auto-republish). Avito Pro + OLX have this. | Medium — requires a `scheduled_publish_at` field + background task. |

### 4.3 Phase 4 Priority Gaps (High Impact, High Complexity)

| Gap | Why it matters | Difficulty estimate |
|-----|----------------|-------------------|
| **Wallet / billing system** | Needed for any promotion services. Requires payment provider integration, balance tracking, spend ledger. | High — payment provider integration, transaction model. |
| **Promotion services** (highlight, raise to top, featured) | Core monetization path for the platform. Avito/Olx all have tiers. | Medium-High — requires wallet + ranking logic changes. |
| **Seller rating / reviews** | Builds trust; influences search ranking. Critical for platform quality. | Medium — Rating model + moderation. |
| **Business page / storefront** | Lets verified sellers showcase all their ads as a profile. Avito Pro + OLX.ua have this. | Medium — new view + template set. |

### 4.4 Phase 5 Priority Gaps (Platform-Level)

| Gap | Why it matters | Difficulty estimate |
|-----|----------------|-------------------|
| **Lead management dashboard** | Consolidated view of all contact attempts across ads. Avito Pro "Лиды" section. | High — requires contact event aggregation + filtering. |
| **API for bulk ad management** | Enables power sellers and future integrations. Avito Pro has REST API. | High — new API layer. |
| **CRM / webhook integration** | Push contact events to external CRM. Avito Pro + OLX.ua have this. | High — webhook dispatch system. |
| **Demand analytics** | Avito Pro "Аналитика спроса" shows market demand trends. | High — requires market data collection + analytics pipeline. |

---

## 5. Implementation Notes

### 5.1 Existing Foundation Ready for Gaps

Several Mko Bazuna subsystems are already in place and can support Phase 2–3 gaps without new architecture:

| Subsystem | Ready for |
|-----------|-----------|
| `AnalyticsEvent` model + `AnalyticsEventType` enum | Favorites tracking, contact analytics expansion, dashboard metrics |
| `TimeRange` enum (ALL_TIME / 30_DAYS / 7_DAYS) | Already used in dashboard; extensible to new time-based views |
| `Ad.transition_to()` + `AdStatus` enum | Bulk actions, schedule reactivation, deactivate status |
| `auto_moderate()` service | Re-moderation on text edits, resubmit after rejection |
| `SellerTrustScore` + `SellerVerification` + `TrustLevel` | Verification gating for promotion services |
| Ad sweep tasks (`AdvisoryLockId.ARCHIVE_SWEEP`, `DELETE_SWEEP`, `SWEEP_DRAFTS`) | Can be extended for auto-reactivation scheduling |

### 5.2 StrEnum Conventions

All new constant sets must extend `StrEnum` in `core/enums.py`, following the pattern established by `AdStatus`, `TrustLevel`, `TimeRange`, etc. No inline string literals for fixed values.

### 5.3 Contact Service Handoff

The current `core/services/contact.py` generates a Telegram deep-link. For in-app messaging (Phase 3), the same service should be extended rather than replaced — the deep-link can remain for sellers who prefer Telegram, while an in-app chat view is added alongside.

---

## 6. Appendix: Sources

| # | Source | URL | Access method | Confidence |
|---|--------|-----|---------------|------------|
| 1 | Avito Pro functionality | `https://blog.click.ru/avito-pro` | webfetch (200) | MEDIUM |
| 2 | Avito Pro tariff details | `https://brobank.ru` | webfetch (200) | MEDIUM |
| 3 | Avito Pro review | `https://moy-avito.ru` | webfetch (200) | MEDIUM |
| 4 | Avito Pro guide | `https://litelab.agency` | webfetch (200) | MEDIUM |
| 5 | OLX.ua functional profile | `https://help.olx.ua/olxuahelp/s/article/Функцiональний-профiль-продавця` | webfetch (200) | MEDIUM |
| 6 | OLX.ua business packages | `https://help.olx.ua/olxuahelp/s/article/Пакети-послуг-бiзнес-продавця-на-OLX` | webfetch (200) | MEDIUM |
| 7 | OLX.ua rejection reasons | `https://help.olx.ua/olxuahelp/s/article/Чому-видаляється-оголошення` | websearch snippet (429 on fetch) | LOW |
| 8 | OLX.pl statistics | `https://pomoc.olx.pl/article/1164-statystyki-sprzedazy` | webfetch (200) | MEDIUM |
| 9 | OLX.pl seller guide | `https://sportdobrodzien.pl` | webfetch (200) | MEDIUM |
| 10 | OLX India ads page | `https://help.olx.in/article/113-where-can-i-see-the-ads` | webfetch (200) | MEDIUM |
| 11 | Mko Bazuna source | `src/backend/apps/` | direct read — all views/models/tmplates | HIGH |
