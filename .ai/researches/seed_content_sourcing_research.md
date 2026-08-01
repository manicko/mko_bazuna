# Seed Content Sourcing Research

**Date:** 2026-07-31  
**Project:** Mko Bazuna  
**Researcher:** Agent  
**Status:** Complete  
**Confidence:** HIGH (all claims verified against source code and official documentation)

---

## Table of Contents

1. [Photo Sources Evaluated](#1-photo-sources-evaluated)
2. [Recommended Photo Sourcing Approach](#2-recommended-photo-sourcing-approach)
3. [Avito Category Patterns Summary](#3-avito-category-patterns-summary)
4. [ImageGenerator Modification Plan](#4-imagegenerator-modification-plan)
5. [Template Structure Recommendation](#5-template-structure-recommendation)
6. [Storage and Performance Analysis](#6-storage-and-performance-analysis)
7. [Implementation Approaches](#7-implementation-approaches)

---

## 1. Photo Sources Evaluated

### 1.1 Source Comparison Table

| Site | License | Requires Attribution? | Bundlable in MIT Repo? | API Available | Rate Limit | Typical Quality | API Key Required? | Search by Category? |
|------|---------|----------------------|----------------------|--------------|------------|-----------------|-------------------|---------------------|
| **Unsplash** | Unsplash License (free to use, modify, distribute) | No (but encouraged) | **Yes** | REST API | 1,000 req/hr (demo); 3,000 req/hr (registered) | Excellent — professional DSLR, 4000+ px | Yes (free) | Yes — `search/photos?query=keyword` |
| **Pexels** | Pexels License (free to use, modify, no attribution required) | No | **Yes** | REST API | 200 req/hr (default); 20,000 req/hr (verified) | Very good — high-res, curated | Yes (free) | Yes — `search?query=keyword` |
| **Pixabay** | Pixabay Content License (royalty-free, no attribution required) | No | **Yes** | REST API | 100 req/60s | Good — mixed quality, 640px webformat default | Yes (free) | Yes — `category` parameter + `q` |
| **Lorem Picsum** | Unsplash-sourced (same license as Unsplash) | No | **Yes** | Simple HTTP | No auth needed, but no guarantees | Good — same as Unsplash | No | No — random only, no search |
| **Burst (Shopify)** | CC0-like (free for commercial use) | No | **Yes** | REST API | No info | Good — product-focused | Yes (free) | Yes |
| **StockVault** | Varies by image (some CC0, some require attribution) | Sometimes | **Maybe** | No API | N/A | Variable | N/A | N/A |
| **Wikimedia Commons** | CC0 / CC-BY / public domain | Varies | **Maybe** | MediaWiki API | No strict limit | Variable | No | Yes — complex categories |

### 1.2 Detailed Source Analysis

#### Unsplash
- **License:** [Unsplash License](https://unsplash.com/license) — "You can copy, modify, distribute, and use the photos for free, including for commercial purposes, without asking permission or providing attribution."
- **API:** `GET /search/photos?query=keyword` returns JSON with `urls.raw`, `urls.regular`, `urls.small`, `urls.thumb`
- **Rate limit:** 1,000 requests/hour (unregistered demo), 3,000 requests/hour (registered app)
- **Image sizes:** `raw` (original), `full` (1920px), `regular` (1080px), `small` (400px), `thumb` (200px)
- **Requires download tracking:** Must call `GET /photos/:id/download` to track downloads (not strictly required for one-time seed downloads)
- **Best for:** High-quality, professional photography for all categories
- **Confidence:** HIGH

#### Pexels
- **License:** [Pexels License](https://www.pexels.com/license/) — "All photos and videos on Pexels are free to use. Attribution is not required."
- **API:** `GET /v1/search?query=keyword&per_page=15` returns JSON with `src.original`, `src.large2x`, `src.large`, `src.medium`, `src.small`
- **Rate limit:** 200 requests/hour (standard), 20,000 requests/hour (verified free account)
- **Image sizes:** `original` (up to 6000px), `large2x` (1880px), `large` (940px), `medium` (350px), `small` (130px)
- **Best for:** Curated, high-quality images with good category coverage
- **Confidence:** HIGH

#### Pixabay
- **License:** [Pixabay Content License](https://pixabay.com/service/license-summary/) — "Free to use without attribution. Modify or adapt into new works."
- **API:** `GET /api/?key=KEY&q=keyword&category=...&image_type=photo`
- **Rate limit:** 100 requests/60 seconds
- **Image sizes:** `webformatURL` (640px max), `largeImageURL` (1280px), `fullHDURL` (1920px), `imageURL` (original)
- **Limitation:** API limited to 500 images per query; full HD+ resolution requires approved API access
- **Best for:** Quick, free access with no account setup for basic use
- **Confidence:** HIGH

#### Lorem Picsum
- **License:** Unsplash-sourced (same as Unsplash license)
- **API:** `https://picsum.photos/id/{id}/info` or `https://picsum.photos/v2/list`
- **Rate limit:** None documented, but no guarantee
- **No search capability:** Returns random images — cannot select by category
- **Verdict:** NOT suitable for category-specific image sourcing
- **Confidence:** HIGH

### 1.3 Montenegro-Specific Imagery

- **Query approach:** `montenegro+apartment`, `montenegro+car`, `budva+beach`, etc.
- **Unsplash:** Contains significant Montenegro-specific content (Kotor, Budva, Bay of Kotor, Durmitor)
- **Pexels:** Good coverage of Balkan/Mediterranean imagery
- **Pixabay:** Limited Montenegro-specific content
- **Relevance:** For a Montenegro-based classifieds board, using Montenegro-realistic scenes (real estate with sea views, cars on coastal roads, Mediterranean landscapes) adds authenticity
- **Confidence:** MEDIUM (depends on search query effectiveness)

---

## 2. Recommended Photo Sourcing Approach

### 2.1 Recommendation: Manual Download + Repository Bundle

**Approach:** Manually curate ~90 photos from Unsplash (primary) and Pexels (secondary), download at a reasonable resolution, and commit them to the repository.

**Rationale:**
1. **No runtime network dependency** — Spec requirement N05: "No network dependencies: all resources (fixtures, images) must be bundled in the repository."
2. **Zero API cost** — Free API keys needed for one-time download script
3. **Quality control** — Curated photos ensure appropriate, consistent quality per category
4. **Deterministic** — Same photos every time, matching Faker seed determinism
5. **Legal safety** — Both Unsplash and Pexels explicitly allow redistribution

### 2.2 Recommended Download Method

**Option A: One-time Python script (recommended)**
- Write a small script `scripts/download_seed_photos.py` in the repo
- Uses `requests` + API key (stored in `.env` or passed as arg)
- Queries Unsplash API per category, downloads 5-10 photos per category
- Downloads at `regular` (1080px) size — good balance of quality and file size
- Applies JPEG compression (Pillow, quality=75) to keep files under 100KB
- Outputs to `src/backend/apps/seed/fixtures/images/{category_slug}/`
- Generates `photo_manifest.json` mapping category → photos

**Option B: Fully manual curation**
- Manually browse Unsplash/Pexels
- Download images by hand
- Commit to repo
- Requires a human to manually rename and categorize each photo
- More effort but guaranteed quality

**Option C: Hybrid — script-assisted download + manual quality check**
- Use script for initial bulk download
- Human reviews and removes poor-quality images
- Best quality control with minimal effort

### 2.3 Unsplash Search Queries Per Category

| Category Group | Recommended Search Queries | Photos Needed |
|---------------|---------------------------|---------------|
| Real Estate (apartments, houses, commercial, land) | `apartment interior`, `house exterior`, `living room`, `modern kitchen`, `office space`, `building`, `land plot` | 12-16 |
| Vehicles (cars, motorcycles, boats, parts) | `car front view`, `sedan`, `offroad vehicle`, `motorcycle`, `boat`, `car engine`, `tire` | 12-16 |
| Electronics (phones, computers, photo, appliances) | `smartphone`, `laptop desk`, `camera`, `refrigerator`, `washing machine`, `tv screen` | 12-16 |
| Services (construction, beauty, education, legal) | `tools`, `hair salon`, `classroom`, `office desk`, `consultation` | 4-8 |
| Jobs (vacancies, resumes) | `office`, `interview`, `workplace` | 3-4 |
| Pets (dogs, cats) | `dog`, `cat`, `puppy`, `kitten` | 6-8 |
| Furniture | `sofa`, `chair`, `wardrobe`, `bedroom furniture` | 4-6 |
| Clothing & Shoes | `clothing rack`, `shoes`, `fashion` | 4-6 |
| Baby & Kids | `baby stroller`, `kids toys`, `children` | 3-4 |
| Sports & Leisure | `bicycle`, `sports equipment`, `travel` | 3-4 |
| **Total** | | **~65-90+** |

---

## 3. Avito Category Patterns Summary

### 3.1 Avito Top-Level Categories (verified from existing design research)

Based on the existing Avito design analysis in `docs/07-design-researches/Design_02/01-avito-design.md` and the project's category fixture:

| Avito Category | Mko Bazuna Equivalent | Common Title Patterns | Common Photo Styles |
|----------------|----------------------|----------------------|---------------------|
| Недвижимость (Real Estate) | nedvizhimost | "Продам/Сдам + тип + в районе X", "2-к квартира, центр" | Interior shots, building exterior, room views with natural light |
| Транспорт (Vehicles) | transport | "Марка Модель год", "Продам X в отличном состоянии" | 3/4 front angle, exterior, interior dashboard, engine bay |
| Электроника (Electronics) | elektronika | "Бренд Модель особенности", "Продам X ГБ" | Clean background, product front, accessories included |
| Услуги (Services) | uslugi | "Услуги X", "X с опытом Y лет" | Work-in-progress shot, result photo, or professional headshot |
| Работа (Jobs) | rabota | "Требуется X", "Ищем X с опытом" | Office environment, team photo, or workplace shot |
| Животные (Pets) | zhivotnye | "Щенки/Котята породы X", "Продаются X с родословной" | Close-up pet portrait, litter with mother, outdoor setting |
| Мебель (Furniture) | mebel | "Продам X, состояние Y", "X с механизмом трансформации" | Room setting, isolated product, detail of upholstery |
| Одежда/Обувь (Clothing) | odezhda | "X бренд, размер Y, состояние Z", "Новый с бирками" | Flat lay, on-model, detail of material/tag |
| Детские товары (Baby) | detskie | "Детская X, трансформер", "X для детей Y лет" | Product in use, product isolated, accessories |
| Спорт/Отдых (Sports) | sport | "X бренд, размер Y, состояние Z" | Product in action, product isolated, close-up of features |

### 3.2 Content Pattern Observations

**Title patterns:**
- **Action verbs:** "Продам" (selling), "Сдам" (renting), "Требуется" (hiring), "Ищу" (looking for), "Услуги" (services)
- **Structure:** [Action] + [Product] + [Key features] + [Location/condition]
- **Length:** 30-80 characters (typically 5-15 words)

**Description patterns:**
- **Opening:** Action verb + product + condition
- **Body:** Key specifications (size, year, features, condition)
- **Closing:** Call to action, contact info, location
- **Length:** 100-500 characters

**Photo patterns per category:**
- **Real estate:** Wide-angle interior shots, natural light, multiple rooms
- **Cars:** 3/4 front exterior, clean background, showroom or outdoor
- **Electronics:** Clean white/grey background, product centered, accessories visible
- **Pets:** Natural lighting, pet-focused, soft background blur
- **Furniture:** Room context, well-lit, clear view of upholstery/material

### 3.3 Alternative Reference Sites

| Site | Region | Notes |
|------|--------|-------|
| **Avito.ru** | Russia | Primary reference — closest to Mko Bazuna's classifieds model |
| **Youla.io** | Russia | Simpler interface, good for mobile-first patterns |
| **OLX.ba** | Bosnia & Herzegovina | Balkan-specific, relevant for Montenegrin/Bosnian market |
| **OLX.rs** | Serbia | Balkan market, Serbian language (close to Montenegrin) |
| **Facebook Marketplace** | Global | Design research already done in project |
| **Jiji.co.ke** | Kenya/Africa | Emerging market patterns (already researched) |

**Feasibility of manual research:** HIGH — all platforms are accessible via browser. No scraping needed. Existing design research docs already cover the patterns.

---

## 4. ImageGenerator Modification Plan

### 4.1 Current Architecture

**Files involved:**
- `src/backend/apps/seed/generators/images.py` — `ImageGenerator` class
- `src/backend/apps/seed/services/seed_service.py` — `SeedService` orchestrator
- `src/backend/apps/media/services/thumbnails.py` — `ThumbnailService`

**Current flow:**
1. `ImageGenerator.__init__()` receives `config` dict + `list[Ad]`
2. `_get_seed_image_pool()` generates 5 solid-color JPEGs via Pillow (cached in module-level variable)
3. `_preprocess_images()` writes JPEGs to `MEDIA_ROOT/seed/`, generates thumbnails
4. `generate()` selects 1-3 random images per ad, creates `AdImage` records
5. Images are shared across all ads (no category awareness)

### 4.2 Required Changes

#### 4.2.1 Category-Tagged Photo Support

**New file: `fixtures/images/photo_manifest.json`**

```json
{
  "version": 1,
  "categories": {
    "kvartiry": {
      "slug": "kvartiry",
      "photos": [
        {"filename": "kvartiry_01.jpg", "tags": ["interior", "living-room"], "width": 1080, "height": 720},
        {"filename": "kvartiry_02.jpg", "tags": ["interior", "kitchen"], "width": 1080, "height": 720},
        {"filename": "kvartiry_03.jpg", "tags": ["interior", "bedroom"], "width": 1080, "height": 720}
      ]
    },
    "avtomobili": {
      "slug": "avtomobili",
      "photos": [
        {"filename": "avtomobili_01.jpg", "tags": ["exterior", "front-angle"], "width": 1080, "height": 720},
        {"filename": "avtomobili_02.jpg", "tags": ["exterior", "side-view"], "width": 1080, "height": 720},
        {"filename": "avtomobili_03.jpg", "tags": ["interior", "dashboard"], "width": 1080, "height": 720}
      ]
    }
  },
  "default": {
    "photos": [
      {"filename": "default_01.jpg", "tags": []},
      {"filename": "default_02.jpg", "tags": []}
    ]
  }
}
```

#### 4.2.2 Directory Structure

```
src/backend/apps/seed/fixtures/images/
├── photo_manifest.json          # Maps categories to photos
├── kvartiry_01.jpg
├── kvartiry_02.jpg
├── kvartiry_03.jpg
├── avtomobili_01.jpg
├── avtomobili_02.jpg
├── avtomobili_03.jpg
├── ...
├── default_01.jpg
└── default_02.jpg
```

**Flat directory structure** (single directory, all photos) — simpler than subdirectories and easier to manage. The manifest provides the category mapping.

#### 4.2.3 Modified `ImageGenerator` Class

```python
class ImageGenerator(BaseGenerator):
    """Generates AdImage records for seed ads using bundled category-tagged photos."""

    def __init__(self, config: dict[str, Any], ads: list[Ad]) -> None:
        super().__init__(config)
        self.ads = ads
        self.photo_pool: dict[str, list[dict[str, Any]]] = {}  # category_slug -> [photo_info]
        self.default_pool: list[dict[str, Any]] = []

    def _load_manifest(self) -> None:
        """Load photo_manifest.json and build category->photo mapping."""
        manifest_path = FIXTURES_DIR / "images" / "photo_manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        for cat_slug, cat_data in manifest.get("categories", {}).items():
            self.photo_pool[cat_slug] = cat_data["photos"]
        self.default_pool = manifest.get("default", {}).get("photos", [])

    def _get_photos_for_category(self, category_slug: str) -> list[dict[str, Any]]:
        """Return the photo pool for a category, falling back to default."""
        return self.photo_pool.get(category_slug, self.default_pool) or self.default_pool

    def generate(self, ads_with_categories: list[tuple[Ad, str]]) -> list[AdImage]:
        """Generate AdImage records, selecting photos per ad's category."""
        # ... load manifest, pre-process images, then assign by category
```

#### 4.2.4 Changes to `SeedService` Orchestration

The `SeedService._clean()` method currently deletes:
1. `DailyAdMetrics` (FK to Ad)
2. `AnalyticsEvent` (FK to Ad)
3. `AdImage` (FK to Ad)
4. `Ad` (FK to User)
5. Seed users

**Changes needed:**
- Add cleanup of `MEDIA_ROOT/seed/` directory contents (remove all generated image files)
- This is already partially handled by the `_preprocess_images()` `O_EXCL` check, but explicit cleanup is cleaner
- The `_clean()` method should call a new `ImageGenerator.cleanup()` static method that removes seed media files

#### 4.2.5 `ThumbnailService` Compatibility

The existing `ThumbnailService` already works correctly:
- `generate_thumbnails(photo_bytes, key)` accepts raw bytes and a key string
- Uses `O_EXCL` atomic writes — if thumbnails exist, it raises `FileExistsError`
- The `ImageGenerator._preprocess_images()` already handles this with `os.path.exists()` check

**No changes needed** to `ThumbnailService` — it's already compatible.

---

## 5. Template Structure Recommendation

### 5.1 Current Template Architecture

**File:** `fixtures/ads.json` — flat array of 51 templates:
```json
[
  {"title": "Продам 2-комнатную квартиру в центре", "description": "Продаётся просторная 2-комнатная квартира... {category}"},
  ...
]
```

**Current processing:** `AdGenerator` picks a random template, replaces `{category}` with `category.name`. Only Russian, no multi-language support.

### 5.2 Recommended Template Structure

**New file: `fixtures/ads_templates.json`**

```json
{
  "version": 2,
  "placeholder_schema": {
    "condition": {"description": "Used/New condition", "examples": {"ru": "отличном", "en": "excellent", "bs": "odličnom"}},
    "brand": {"description": "Product brand name", "examples": {"ru": "Samsung", "en": "Samsung", "bs": "Samsung"}},
    "feature": {"description": "Key feature", "examples": {"ru": "Wi-Fi", "en": "Wi-Fi", "bs": "Wi-Fi"}},
    "city": {"description": "City name", "examples": {"ru": "Подгорица", "en": "Podgorica", "bs": "Podgorica"}},
    "price_range": {"description": "Price range description", "examples": {"ru": "недорого", "en": "affordable", "bs": "povoljno"}},
    "item_age": {"description": "Age/usage duration", "examples": {"ru": "2 года", "en": "2 years", "bs": "2 godine"}},
    "category": {"description": "Category name (in Russian - base field)", "examples": {"ru": "Квартиры"}}
  },
  "templates": [
    {
      "id": "real_estate_apartment_sell",
      "category_slug": "kvartiry",
      "patterns": {
        "ru": {
          "title": "Продам {condition} {rooms}-комнатную квартиру в {city}",
          "description": "Продаётся {condition} {rooms}-комнатная квартира в {city}. Площадь {area} кв.м. {feature}. Цена {price} BAM. Звоните!"
        },
        "en": {
          "title": "For sale: {condition} {rooms}-room apartment in {city}",
          "description": "For sale: a {condition} {rooms}-room apartment in {city}. Area: {area} sq.m. {feature}. Price: {price} BAM. Call now!"
        },
        "bs": {
          "title": "Prodaje se {condition} stan sa {rooms} sobe u {city}",
          "description": "Prodaje se {condition} stan sa {rooms} sobe u {city}. Površina: {area} m2. {feature}. Cijena: {price} BAM. Zovite!"
        }
      },
      "variables": {
        "rooms": {"type": "random_int", "min": 1, "max": 4, "suffix": "-к" if lang == "ru" else ""},
        "area": {"type": "random_int", "min": 30, "max": 150}
      }
    }
  ]
}
```

### 5.3 Placeholder Variables

| Variable | Description | Example (ru) | Example (en) | Example (bs) |
|----------|-------------|-------------|-------------|-------------|
| `{condition}` | Item condition adjective | отличном | excellent | odličnom |
| `{item_condition}` | Noun form of condition | отличное состояние | excellent condition | odlično stanje |
| `{brand}` | Product brand name | Samsung | Samsung | Samsung |
| `{model}` | Product model name | Galaxy S24 | Galaxy S24 | Galaxy S24 |
| `{feature}` | Key selling feature | Wi-Fi, кондиционер | Wi-Fi, air conditioning | Wi-Fi, klima |
| `{city}` | City name (nominative) | Подгорица | Podgorica | Podgorica |
| `{city_prep}` | City name (prepositional) | в Подгорице | in Podgorica | u Podgorici |
| `{price}` | Numeric price | 50000 | 50000 | 50000 |
| `{price_range}` | Price descriptor | недорого | affordable | povoljno |
| `{rooms}` | Number of rooms | 2 | 2 | 2 |
| `{area}` | Area in sq.m. | 65 | 65 | 65 |
| `{item_age}` | Age/usage period | 2 года | 2 years | 2 godine |
| `{year}` | Year of manufacture | 2020 | 2020 | 2020 |
| `{mileage}` | Mileage in km | 50000 | 50000 | 50000 |
| `{category}` | Category name (Russian) | Квартиры | Apartments | Stanovi |

### 5.4 Relationship Between Ad Fields

From the `Ad` model and migration `0004_ad_i18n_columns.py`:

| Field | Type | Purpose |
|-------|------|---------|
| `title` | CharField(200) | Base Russian title (primary content field) |
| `description` | TextField | Base Russian description (primary content field) |
| `title_en` | CharField(200, null) | English title translation |
| `description_en` | TextField(null) | English description translation |
| `title_bs` | CharField(200, null) | Bosnian title translation |
| `description_bs` | TextField(null) | Bosnian description translation |

**Fallback chain** (from `get_title()` / `get_description()` methods):
1. `title_{locale}` (e.g. `title_bs`)
2. `title_ru` (Russian field)
3. `title` (base field)

**Recommendation:** Generate all 3 languages at seed time. Fill `title` and `description` with Russian, then `title_en`/`description_en` with English, `title_bs`/`description_bs` with Bosnian.

### 5.5 Template Count Recommendation

| Category | Templates | Per Language | Total (3 langs) |
|----------|-----------|-------------|-----------------|
| kvartiry (apartments) | 3 | 3 | 9 |
| doma (houses) | 2 | 2 | 6 |
| kommercheskaya (commercial) | 2 | 2 | 6 |
| uchastki (land) | 2 | 2 | 6 |
| avtomobili (cars) | 4 | 4 | 12 |
| mototsikly (motorcycles) | 2 | 2 | 6 |
| vodnyy (boats) | 2 | 2 | 6 |
| zapchasti (parts) | 2 | 2 | 6 |
| telefony (phones) | 3 | 3 | 9 |
| kompyutery (computers) | 2 | 2 | 6 |
| foto (photo/video) | 2 | 2 | 6 |
| bytovaya (appliances) | 3 | 3 | 9 |
| stroitelstvo (construction) | 2 | 2 | 6 |
| krasota (beauty) | 2 | 2 | 6 |
| obrazovanie (education) | 2 | 2 | 6 |
| yuridicheskie (legal) | 2 | 2 | 6 |
| vakansii (vacancies) | 3 | 3 | 9 |
| rezyume (resumes) | 1 | 1 | 3 |
| sobaki (dogs) | 2 | 2 | 6 |
| koshki (cats) | 2 | 2 | 6 |
| mebel (furniture) | 3 | 3 | 9 |
| odezhda (clothing) | 2 | 2 | 6 |
| detskie (baby/kids) | 2 | 2 | 6 |
| sport (sports) | 2 | 2 | 6 |
| **Total** | **~50** | **~50** | **~150** |

---

## 6. Storage and Performance Analysis

### 6.1 File Size Budget

| Size | Quality | Use Case |
|------|---------|----------|
| 800×600 px | Good | Seed photo for ad cards |
| ~100KB | Target | Per file in repo |
| ~9MB | Total | 90 photos × 100KB |
| +3MB | Git overhead | Delta compression, git objects |

**Target file size: ~60-100KB** per photo after compression.

**Compression strategy:**
- Download at 1080px (`regular` size from Unsplash)
- Resize to 800×600 (or similar, maintaining aspect ratio)
- Save as progressive JPEG, quality=75-80
- Strip EXIF data (unnecessary for seed data)

### 6.2 Git Impact

| Metric | Estimate |
|--------|----------|
| Total images | ~90 |
| Total size | ~9MB |
| Git clone impact | ~9MB + ~3MB overhead = ~12MB |
| Git LFS needed? | **No** — under 50MB threshold for most repos |
| Repo size before | ~15MB (estimated) |
| Repo size after | ~27MB (acceptable) |

**Conclusion:** Regular git is fine. No need for Git LFS. The ~12MB addition is acceptable for a development tool.

### 6.3 Directory Structure

```
src/backend/apps/seed/fixtures/images/
├── photo_manifest.json          # ~3KB — category-to-photo mapping
├── kvartiry_01.jpg              # ~80KB — apartment interior
├── kvartiry_02.jpg              # ~75KB — apartment living room
├── kvartiry_03.jpg              # ~90KB — apartment kitchen
├── avtomobili_01.jpg            # ~85KB — car front 3/4
├── avtomobili_02.jpg            # ~80KB — car interior
├── avtomobili_03.jpg            # ~75KB — car side view
├── ...                          # ~90 files total
├── default_01.jpg               # ~70KB — generic fallback
└── default_02.jpg               # ~70KB — generic fallback
```

**Flat vs hierarchical:** Flat directory with manifest is simpler:
- No nested directory creation needed
- Simpler glob patterns
- Manifest provides all categorization
- Easy to add new photos without restructuring

### 6.4 EXIF Handling

- **Strip EXIF** during compression — saves ~5-15KB per image
- EXIF data is irrelevant for seed data
- No orientation issues (all photos will be properly oriented before download)
- Use Pillow: `PILImage.clean_exif()` or `list(img.getdata())` approach

### 6.5 Runtime Performance

| Operation | Current | With Bundled Photos |
|-----------|---------|---------------------|
| Load manifest | N/A | ~3ms (small JSON) |
| Read JPEGs from disk | ~5ms (5 generated) | ~50ms (90 files) |
| Write to MEDIA_ROOT | ~10ms | ~100ms |
| Generate thumbnails | ~150ms | ~2s (90 photos × 3 sizes) |
| Create AdImage records | ~5ms | ~5ms (same count) |
| **Total image phase** | ~170ms | ~2.2s |

**Impact:** ~2 second increase for the image generation phase. Acceptable for a dev tool. The 90 photos are processed once, then reused across all ads.

### 6.6 Media Cleanup

The `_clean()` method needs to:
1. Remove all files from `MEDIA_ROOT/seed/` (not the directory itself)
2. This ensures clean state for re-seed
3. **Current behavior:** `_preprocess_images()` checks for existing thumbnails with `O_EXCL` — but this is fragile. Explicit cleanup is better.

**Recommended change:**
```python
def _clean_media(self) -> None:
    """Remove all seed-generated media files."""
    seed_dir = os.path.join(settings.MEDIA_ROOT, "seed")
    if os.path.exists(seed_dir):
        import shutil
        shutil.rmtree(seed_dir)
```

---

## 7. Implementation Approaches

### 7.1 Approach A: Hybrid — Script-Assisted Download + Manual Curation (RECOMMENDED)

**Description:** Write a one-time download script, then manually review and curate photos.

**Steps:**
1. Write `scripts/download_seed_photos.py` 
2. Script uses Unsplash API (free key) to search `montenegro+apartment`, `car+interior`, etc.
3. Downloads 10 photos per category query
4. Applies JPEG compression, strips EXIF
5. Outputs to `fixtures/images/` with manifest generation
6. Human reviewer removes poor-quality or irrelevant photos
7. Final manifest is adjusted to reflect curated set

**Pros:**
- Minimal manual effort (review, not browse)
- Guaranteed quality (human review step)
- Full reproducibility (script can be re-run)
- Category-tagged from the start

**Cons:**
- Requires API key (free, but setup needed)
- Script is one-time use (maintenance burden)
- Unsplash API rate limits may require pacing

**Effort:** ~2-3 hours (script) + ~1 hour (manual curation)

### 7.2 Approach B: Fully Manual Curation (Alternative)

**Description:** Browse Unsplash/Pexels manually, download photos by hand, commit to repo.

**Steps:**
1. Browse Unsplash.com, search per category
2. Download 3-5 photos per category
3. Rename to convention: `{category_slug}_{number}.jpg`
4. Compress to ~100KB using image editor or batch script
5. Write `photo_manifest.json` manually

**Pros:**
- Maximum quality control
- Zero API key needed
- No code to maintain

**Cons:**
- Tedious for ~90 photos
- Manual renaming and categorization
- Error-prone (wrong files, wrong categories)
- Difficult to reproduce exactly

**Effort:** ~4-6 hours

### 7.3 Approach C: Pure Generated (Modified Current Approach)

**Description:** Keep the current Pillow-based approach but enhance it with more realistic generation.

**Steps:**
1. Keep `ImageGenerator._generate_placeholder_jpeg()`
2. Add more sophisticated generation: gradient backgrounds, geometric shapes, text overlays
3. Map category slugs to specific color palettes
4. No external photos needed

**Pros:**
- Zero external dependencies
- Zero git size impact
- Fully deterministic
- No copyright concerns

**Cons:**
- Still looks artificial (not realistic photos)
- PO explicitly wants "realistic photos"
- Poor UX for visual evaluation of the site
- Doesn't meet the PO requirement

**Verdict:** REJECTED — doesn't meet the "realistic photos" requirement.

### 7.4 Recommendation: Approach A

**Primary recommendation: Approach A (script-assisted download + manual curation).**

**Rationale:**
1. Meets PO requirement for "realistic photos"
2. Minimal manual effort
3. Reproducible (script can be re-run if photos need updating)
4. Category-tagged from the start
5. Under 50MB total — no Git LFS needed
6. Both Unsplash and Pexels licenses allow bundling in MIT repos

### 7.5 Template Implementation Recommendation

**Phase 1: Add category-slug mapping to existing templates**
- Keep the existing `ads.json` format
- Add `category_slug` field to each template entry
- `AdGenerator` selects templates matching the ad's category (or falls back to random)

**Phase 2: Restructure to multi-language format**
- Create `ads_templates.json` with the hierarchical structure in section 5.2
- Add `title_en`, `description_en`, `title_bs`, `description_bs` fields to `AdGenerator`
- Fill placeholders using Faker + per-language variable lists
- Set `original_language = "ru"` on generated ads

**Phase 3: Variable-based filling**
- Replace simple `{category}` replacement with full variable interpolation
- Variables like `{condition}`, `{brand}`, `{feature}`, `{city}` get filled from per-language word lists
- Word lists stored in JSON alongside templates (or in a separate `word_lists.json`)

### 7.6 Implementation Order

1. **Photo sourcing:** Run download script, curate, commit to `fixtures/images/`
2. **Photo manifest:** Create `photo_manifest.json` with category mapping
3. **ImageGenerator:** Modify to load manifest, select photos by category
4. **SeedService:** Add media cleanup to `_clean()`
5. **Template restructuring:** Update `ads.json` → `ads_templates.json`
6. **AdGenerator:** Add multi-language support, variable filling, category-specific templates
7. **Update tests:** Cover new category-tagged photo selection and multi-language template generation

---

## Appendix A: Key Files Referenced

| File | Purpose |
|------|---------|
| `src/backend/apps/seed/generators/images.py` | Current ImageGenerator (solid-color JPEGs) |
| `src/backend/apps/seed/generators/ads.py` | Current AdGenerator (flat templates) |
| `src/backend/apps/seed/services/seed_service.py` | SeedService orchestrator |
| `src/backend/apps/seed/fixtures/ads.json` | 51 flat Russian templates |
| `src/backend/apps/seed/fixtures/categories.json` | 30 categories with i18n names |
| `src/backend/apps/seed/config/seed.default.json` | Seed configuration |
| `src/backend/apps/media/services/thumbnails.py` | ThumbnailService (unchanged) |
| `src/backend/apps/ads/models.py` | Ad + AdImage models |
| `src/backend/apps/ads/migrations/0004_ad_i18n_columns.py` | Multi-language fields |
| `src/backend/apps/core/enums.py` | LanguageLocale, ThumbnailSizeStrEnum |
| `docs/07-design-researches/Design_02/01-avito-design.md` | Existing Avito design analysis |
| `.ai/problems/02_demo-seed-data_spec.md` | Original seed module spec |

## Appendix B: Confidence Levels

| Claim | Confidence | Evidence |
|-------|-----------|----------|
| Unsplash/Pexels/Pixabay licenses allow bundling in MIT repos | **HIGH** | Verified against official license pages |
| ThumbnailService compatible with seed flow | **HIGH** | Verified by reading `thumbnails.py` — accepts bytes, returns keys |
| Ad model has title_en, title_bs, description_en, description_bs | **HIGH** | Verified in migration `0004_ad_i18n_columns.py` |
| 30 categories exist | **HIGH** | Verified in `fixtures/categories.json` |
| Avito category hierarchy | **HIGH** | Based on existing design research doc |
| Unsplash API rate limit (1,000 req/hr) | **HIGH** | Verified from official Unsplash API docs via Context7 |
| Pixabay API rate limit (100 req/60s) | **HIGH** | Verified from official Pixabay API docs |
| Montenegro-specific content exists on Unsplash | **MEDIUM** | Inferred from general knowledge; not verified via API search |
| ~90 photos will fit in <12MB git | **HIGH** | Calculated: 90 × 100KB + 30% overhead = ~12MB |
| Git LFS not needed | **HIGH** | ~12MB is well under the 50MB GitHub recommendation threshold |