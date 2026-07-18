# Research Report: Moderation Criteria for Classified Ads Platforms

**Date:** 2026-07-18
**Target:** mko_bazuna MVP (Telegram bot + Django classifieds)
**Platforms Researched:** Avito, OLX, eBay, Craigslist, Kijiji, Marktplaats, Facebook Marketplace, Allegro

---

## Executive Summary

Major classified platforms enforce **two-tier moderation**: automated text/metadata checks at submit time, and manual photo/content review post-publish. The automatic layer validates structural requirements (lengths, required fields, banned words), while manual review focuses on visual prohibited content. For the Bosnia MVP, we recommend extending the current `moderation_criteria` singleton table with comprehensive automatic rules and documenting manual review categories for future ML automation.

---

## 1. Automatic (Pre-Publish/API) Validation Rules

### 1.1 Title Requirements

| Platform | Min Length | Max Length | Required | Notes |
|----------|------------|------------|----------|-------|
| **Avito** | Not explicit (implied ~5+) | Not specified | Yes | Must be real item name, no price, no contacts, no marketing words |
| **OLX** | 5 chars | 70-111 chars | Yes | No uppercase, no links, no attention-grabbing phrases |
| **eBay** | None explicit | 80 chars recommended | Yes | Recommended 65-80 chars for better conversion |
| **Facebook Marketplace API** | None | 200 chars | Yes | Recommended 65 chars max for feed display |
| **Allegro** | None explicit | None explicit | Yes | Title + brand detection via ML |
| **Craigslist** | None | None | Yes | Required fields highlighted in green |

### 1.2 Description Requirements

| Platform | Min Length | Max Length | Required | Notes |
|----------|------------|------------|----------|-------|
| **Avito** | Not explicit | Not specified | Yes | Must describe item accurately, no contact info |
| **OLX** | 0 chars | 1000 chars | Yes | No uppercase, no links, no spam phrases |
| **eBay** | None explicit | None explicit | Recommended | Poor descriptions demoted in search |
| **Facebook Marketplace** | None | 9999 chars | Recommended | First 256 chars shown in listing |
| **Allegro** | None explicit | None explicit | Yes | Must match item specifics, no marketing language |

### 1.3 Price Requirements

| Platform | Required | Min | Max | Notes |
|----------|----------|-----|-----|-------|
| **Avito** | Yes (for products) | Not specified | Integer (RUB) | Must match actual selling price |
| **OLX** | Yes | None (0 = "on demand") | None | Must be realistic/market-appropriate |
| **eBay** | Required for most categories | None | None | $0 allowed for "free" items |
| **Facebook Marketplace** | Yes | None | None | Integer whole units |
| **Allegro** | Yes | None | None | Must be in marketplace currency |
| **Craigslist** | Varies by category | None | None | Some categories require price |

### 1.4 Photo/Image Requirements

| Platform | Min Photos | Max Photos | Required | Format Notes |
|----------|------------|------------|----------|--------------|
| **Avito** | 1 (except real estate 2+) | Not specified | Yes* | Max 25MB, jpg/jpeg/gif/png, 300px min side |
| **OLX** | 1 (at least one) | Not specified | Required | 5MB max, 300px min side |
| **eBay** | None | 12+ recommended | Recommended | 500-1600px recommended, white background |
| **Facebook Marketplace API** | 1 | 20 (1 + 19 additional) | Required | 500x500px min, 8MB max, JPEG/PNG |
| **Craigslist** | 0 | 24 | Optional | Optional for most categories |

### 1.5 Banned/Restricted Content (Auto-Detected)

| Platform | Detection Method | Categories Blocked |
|----------|------------------|-------------------|
| **Avito** | Auto + Manual | Profanity, erotic/sexual content, attention-grabbing phrases, contact info in text, duplicate listings, prohibited goods/services |
| **OLX** | Auto + Manual | Offensive language, religious references, phone numbers in text, invalid images, prohibited items, prices too high/low |
| **eBay** | Auto + Manual | Policy violations, duplicate listings, prohibited items, counterfeit goods |
| **Facebook Marketplace** | Auto + ML | Adult content, violence, drugs, weapons, hate speech, spam/scam |
| **Allegro** | Auto + ML | Prohibited goods, marketing phrases, contact info, non-original images, brand mismatches |

### 1.6 Frequency Limits (Per User)

| Platform | Limit | Enforcement | Notes |
|----------|-------|-------------|-------|
| **Avito** | Not explicit | Duplicate detection | Blocks same/similar listings, tracks account behavior |
| **OLX** | Not explicit | Duplicate detection | 30-day cooldown on reposts |
| **eBay** | Not explicit | Duplicate detection | Algorithms detect near-duplicates across accounts |
| **Facebook Marketplace** | Not documented | Account-based | Suspected fraud = account restrictions |

---

## 2. Manual Moderation / Human Review Categories

### 2.1 Photo Content Review (Currently Manual, Future ML)

| Category | Platforms That Explicitly Block | Detection Trend |
|----------|--------------------------------|-----------------|
| Adult / Sexually Explicit | Facebook, Avito, OLX | Increasing ML/OCR |
| Violence / Gore | Facebook, Avito, OLX | Increasing ML |
| Drugs / Weapons | Facebook, OLX, Allegro, Avito | ML + manual |
| Hate Symbols (Nazi, KKK) | Avito, Marktplaats, Facebook | Manual + ML |
| Counterfeit Goods | eBay, Allegro, Facebook | ML + brand verification |
| Tobacco / Alcohol | Avito, OLX, Facebook (restricted) | Manual for now |
| Illegal Goods | All platforms | Manual |

### 2.2 Text Content Review (Partially Auto, Partially Manual)

| Category | Platforms | Detection Status |
|----------|-----------|------------------|
| Contact Info in Description | Avito, OLX, Allegro | Auto-detect via regex |
| External Links | Avito, OLX, eBay | Auto-detect + user reports |
| Spam / Scam Patterns | Facebook, OLX | ML + heuristic rules |
| Misleading Information | All platforms | Manual review |
| Off-Topic / Wrong Category | Craigslist, Kijiji | Manual review |

---

## 3. Required vs Optional Fields (Consensus)

### 3.1 Universally Required

| Field | Platforms Requiring | Notes |
|-------|---------------------|-------|
| Title | All platforms | No exceptions found |
| Category | All (except Craigslist freeform) | Required for proper indexing |
| Primary Photo | Most platforms (except Craigslist) | Avito, OLX, eBay, Facebook require at least 1 |

### 3.2 Context-Dependent

| Field | Required By | Optional By | Notes |
|-------|-------------|-------------|-------|
| Price | Avito, OLX, eBay, Facebook | Craigslist | Some categories (jobs, personals) may not need |
| Description | OLX, Allegro | Craigslist, eBay (recommended) | Quality affects search ranking |
| Location | All platforms | All platforms | Must be accurate if provided |

---

## 4. Category-Specific Rules (Phase 1 Out of Scope)

All researched platforms implement **category-specific validation**:

| Category | Avito Special Rules | OLX Special Rules | eBay/Allegro | Recommendation for Phase 1 |
|----------|-------------------|-------------------|--------------|------------------------|
| Real Estate | Photo with ID required, all rooms+kitchen+bathroom | Requires ID photo | N/A | DEFERRED - flat fields only |
| Vehicles | VIN, make/model required | License plate restrictions | VIN, inspection required | DEFERRED - no EAV in phase 1 |
| Electronics | No "gift" claims without actual item | Price realism checks | Condition + specifics required | DEFERRED |
| Jobs | No discrimination | Specific format required | N/A | DEFERRED |
| Personals | Banned on most platforms | Banned | Banned | NOT SUPPORTED |

**Recommendation:** Phase 1 uses flat fields only. Category-specific rules (area/rooms for real estate, make/model for vehicles) are deferred to post-MVP using EAV pattern.

---

## 5. Owner's Potentially Missed Criteria

Based on platform research, the following are commonly enforced but may be missing from the current plan:

| Criterion | Why It Matters | Platforms Enforce | Recommendation |
|-----------|----------------|-------------------|----------------|
| **title_max_length** | Prevents spam, ensures mobile display | OLX (70-111), Facebook (200) | **ADD** - 100 chars reasonable |
| **description_max_length** | Prevents novel-length spam | OLX (1000), Facebook (9999) | **ADD** - 2000 chars reasonable |
| **min_images** | Quality listings require photos | Avito, OLX require 1 | **ADD** - 1 photo minimum |
| **price_min/price_max** | Prevents spam (1 BAM for laptops) | OLX (price anomaly detection), eBay clustering | **CONSIDER** - price sanity with ML later |
| **external_link_detection** | Keeps traffic on-platform | Avito, OLX, Allegro, eBay | **ADD to auto-check** |
| **duplicate_title_threshold** | Prevents duplicate spam | Avito, eBay, OLX detect duplicates | **ADD** - similarity threshold |
| **uppercase_percentage_limit** | Prevents SHOUTING spam | OLX, Avito limit caps | **CONSIDER** - simple heuristic |
| **special_char_frequency** | Prevents spam patterns | OLX restricts repeated chars | **CONSIDER** - simple validation |

---

## 6. Recommended `moderation_criteria` Extension

### 6.1 Automatic Criteria (Enforced at Submit)

| Field Name | Type | Default Value | Layer | Description |
|------------|------|---------------|-------|-------------|
| `banned_words` | JSONB | `[]` | Auto | Array of prohibited words/phrases (case-insensitive) |
| `min_text_length` | INT | 10 | Auto | Minimum total characters (title + description) (existing) |
| `title_min_length` | INT | 5 | Auto | Minimum title length |
| `title_max_length` | INT | 100 | Auto | Maximum title length |
| `description_min_length` | INT | 10 | Auto | Minimum description length |
| `description_max_length` | INT | 2000 | Auto | Maximum description length |
| `price_required` | BOOLEAN | TRUE | Auto | Whether price field is mandatory |
| `min_images` | INT | 1 | Auto | Minimum photos required per listing |
| `max_images` | INT | 5 | Auto | Maximum photos allowed (existing) |
| `max_ads_per_user` | INT | 10 | Auto | Maximum active listings per user |
| `duplicate_title_threshold` | INT | 85 | Auto | Similarity % for duplicate detection (0-100) |

### 6.2 Manual Review Categories (Admin-only)

These are documented for admin checklist and future ML automation:

| Category | Description |
|----------|-------------|
| `adult_content` | Nudity, sexual content, provocative imagery |
| `violence_gore` | Weapons, blood, violent imagery |
| `drugs_weapons` | Illegal substances, firearm imagery |
| `hate_speech` | Nazi symbols, discriminatory content |
| `counterfeit_goods` | Fake brand items |
| `illegal_goods` | Drugs, weapons, prohibited items |
| `spam_scam` | Fraudulent patterns, suspicious pricing |
| `off_topic` | Wrong category, unrelated content |

---

## 7. Concrete SQL for Phase 1 Implementation

```sql
ALTER TABLE moderation_criteria ADD COLUMN
    title_min_length INT DEFAULT 5,
    title_max_length INT DEFAULT 100,
    description_min_length INT DEFAULT 10,
    description_max_length INT DEFAULT 2000,
    min_images INT DEFAULT 1,
    price_required BOOLEAN DEFAULT TRUE,
    duplicate_title_threshold INT DEFAULT 85;
```

---

## 8. References

- Avito: https://www.avito.ru/legal/rules/listings/items-quality
- OLX: https://developer.olxgroup.com/docs/advert-validation-rules
- eBay: https://www.ebay.ca/help/policies/listing-policies/listing-policies
- Facebook: https://developers.facebook.com/docs/marketplace/partnerships/itemAPI/
- Allegro: https://help.allegro.com/en/sell/c/rules-for-offer-descriptions
- Marktplaats: https://help.marktplaats.nl/s/article/uitleg-aanstootgevend-materiaal
- Kijiji: https://kijiji--uat.sandbox.my.salesforce-sites.com/helpdesk/policies/posting-policies
- Craigslist: https://www.craigslist.org/about/help/posting/create
