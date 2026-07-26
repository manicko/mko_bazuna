# Mko Bazuna — i18n Research

## Current State Analysis

### 1. Content Storage (Ads)

**Location:** `apps/ads/models.py`

**Current Implementation:**
- `title` (CharField) — stores only Russian text
- `description` (TextField) — stores only Russian text  
- Comments in model: "Ad title in Russian (translated from seller input)" and "Ad description in Russian (translated from seller input)"

**Translation Flow:** When seller creates an ad via bot, their input is translated to Russian via `deep-translator`:
- See `translate_to_russian()` in `telegram_bot/handlers/ad_create.py` (lines 508-521)
- Bot uses `GoogleTranslator(source="auto", target="ru")` 
- Translation happens synchronously during ad creation

**Search Vector Trigger:** `apps/ads/migrations/0002_search_vector_triggers.py`
```sql
NEW.search_vector :=
  setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
  setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
  setweight(to_tsvector('russian', coalesce(v_cat,'')), 'C');
```
- Only Russian content is indexed for FTS
- Uses `russian` text search config

### 2. Query Translation (Search)

**Location:** `apps/search/services/query_translator.py`

**Current Implementation:**
- `translate_query_bs_to_ru(query: str) -> str` — translates Bosnian queries to Russian
- Uses `deep-translator` with Google Translate
- Features: timeout (~500ms), LRU cache (128 entries), circuit-breaker pattern
- Source: `bs` (Bosnian), Target: `ru` (Russian)

**Search Flow:** `apps/search/views/search.py` (lines 45-62)
```python
query = (request.GET.get("q") or "").strip()
translated_query = translate_query_bs_to_ru(query)
search_query = SearchQuery(translated_query, search_type="websearch", config="russian")
ads = ads.annotate(
    rank=SearchRank("search_vector", search_query)
).filter(search_vector=search_query).order_by("-rank")
```

### 3. Localized Category/City Names

**Location:** `apps/categories/models.py`, `apps/locations/models.py`

**Current Implementation:**
```python
class Category(models.Model):
    name = models.CharField(max_length=200)  # Russian (base)
    name_i18n = models.JSONField(
        blank=True,
        null=True,
        help_text="i18n names: {'ru': <str>, 'bs': <str>}; NULL falls back to name"
    )

def get_name(self, locale: str = "ru") -> str:
    """Get localized name with Russian fallback."""
    name_i18n = getattr(self, "name_i18n", None)
    if name_i18n and locale in name_i18n:
        return name_i18n[locale]
    return str(self.name)
```

**Same pattern for City model.**

**Seed data example:** `categories/migrations/0002_seed_categories.py`
```python
["Товары", '{"ru": "Товары", "bs": "Proizvodi"}', "tovary"],
["Услуги", '{"ru": "Услуги", "bs": "Usluge"}', "uslugi"],
```

- Uses JSONB column for translations
- Russian (`ru`) is base language, Bosnian (`bs`) is secondary
- Templates use `{{ ad.category.get_name }}` and `{{ ad.city.get_name }}`

### 4. UI (Templates, Buttons, Static)

**Templates Location:** `src/backend/templates/ads/`

**Key Templates:**
- `list.html` — main listings page with search form
- `detail.html` — single ad display
- `edit.html` — ad editing form
- `partials/ad_list.html` — HTMX fragment for ad grid

**Current UI State:**
- All text is hardcoded in Russian/English
- Placeholder: "Search ads..."
- No language switcher UI
- No gettext/dngettext usage
- No language detection from request/session/cookies

**Template usage example:**
```html
<span>{{ ad.city.get_name|default:ad.city.name }}</span>
<span>{{ ad.category.get_name|default:ad.category.name }}</span>
```

**Static:** Tailwind CSS via `theme/static/theme/css/output.css`

---

## Required Changes for Multi-Language Support

### 1. Ad Content Translation Storage

**Problem:** Currently only Russian content is stored. Users viewing the site in Bosnian see Russian text.

**Options:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Separate columns per language** | `title_ru`, `title_bs`, `description_ru`, `description_bs` | Simple queries, fast reads, easy FTS per language | Schema changes for each new language, sparse data waste |
| **B. JSONB translations column** | `title_i18n: {"ru": "...", "bs": "..."}` | Flexible for adding languages, no schema changes | Complex queries, harder to index, need computed getters |
| **C. Separate translation table** | `ad_translations(ad_id, locale, title, description)` | Normalized, any number of languages | Joins required, more complex |

**Recommended: Option A (Separate columns)**

Rationale for this architecture:
- Search index needs to be per-language (different text configs)
- FTS queries need efficient filtering per language
- Adding languages is rare; migrations acceptable
- Follows existing pattern (`name_i18n` for reference data is different use case — no FTS)

### 2. Auto-Translation on Ad Creation

**Current flow:**
```
Seller input (any language) → GoogleTranslator(source="auto", target="ru") → Russian stored
```

**Required changes:**
1. Detect seller input language (could use `source="auto"` which auto-detects)
2. Store original language for reference
3. Translate to ALL active site languages (not just Russian)
4. Use atomic transaction for all translations

**Proposed flow:**
```
Seller input → Detect language → Translate to all site languages → Store in respective columns
```

**Languages to support (initially):**
- `ru` — Russian (base, always present)
- `bs` — Bosnian (for Montenegro market)
- `en` — English (international market)

### 3. Language Switching (Session/Cookie)

**Options:**

| Option | Description | Implementation |
|--------|-------------|----------------|
| **URL parameter** | `?lang=bs` | Simplest, explicit, no middleware |
| **Cookie** | `Accept-Language` or custom cookie | Persistent, no URL clutter |
| **Session** | Store in Django session | User-specific, works cross-request |
| **Header** | `Accept-Language` header detection | Automatic, no user action needed |

**Recommended: Cookie + URL fallback**

Implementation approach:
1. Middleware reads `lang` cookie, sets `request.LANGUAGE` 
2. URL parameter `?lang=bs` overrides cookie
3. Default to `ru` if no preference detected
4. Template context processor exposes current language

### 4. Search Impact

**Current search:**
- Query translated: Bosnian → Russian
- Search vector: Russian only
- FTS config: `russian`

**Required changes:**
1. Search must translate query to the language of the stored content being searched
2. Need language-specific search vectors: `search_vector_ru`, `search_vector_bs`, `search_vector_en`
3. Or: make search vector multi-language with weight per language

**Multi-language search vector approach:**
```sql
NEW.search_vector :=
  setweight(to_tsvector('russian', coalesce(NEW.title_ru,'')), 'A') ||
  setweight(to_tsvector('bosnian', coalesce(NEW.title_bs,'')), 'A') ||  -- PG18 supports 'bosnian'
  setweight(to_tsvector('english', coalesce(NEW.title_en,'')), 'A') ||
  setweight(to_tsvector('russian', coalesce(NEW.description_ru,'')), 'B') ||
  ...
```

**Or separate vectors:**
```sql
search_vector_ru = to_tsvector('russian', title_ru, description_ru, category_name)
search_vector_bs = to_tsvector('simple', title_bs, description_bs)  -- PG may not have 'bosnian'
search_vector_en = to_tsvector('english', title_en, description_en)
```

### 5. Extensibility for Other Languages

**Language model (recommended):**
```python
class Language(StrEnum):
    RUSSIAN = "ru"
    BOSNIAN = "bs"  
    ENGLISH = "en"
    
    @property
    def is_rtl(self) -> bool:
        return self in (Language.ARABIC,)  # future
    
    @property
    def fts_config(self) -> str:
        return {
            Language.RUSSIAN: "russian",
            Language.BOSNIAN: "simple",  # PG doesn't have native bosnian config
            Language.ENGLISH: "english",
        }[self]
```

---

## Technical Design Details (Third Pass)

### 1. Language Switcher Implementation

**Cookie-based language preference:**
```python
# apps/core/middleware/language.py
from django.utils.deprecation import MiddlewareMixin
from apps.core.enums import LanguageLocale

LANGUAGE_COOKIE_NAME = "lang_pref"
LANGUAGE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year

class LanguageMiddleware(MiddlewareMixin):
    """Detect and set user language preference."""
    
    def process_request(self, request):
        # Priority: ?lang=X > cookie > Accept-Language header > default
        lang = request.GET.get("lang")
        if lang and lang in LanguageLocale.values:
            request.LANGUAGE_CODE = lang
        else:
            lang = request.COOKIES.get(LANGUAGE_COOKIE_NAME)
            if lang and lang in LanguageLocale.values:
                request.LANGUAGE_CODE = lang
            else:
                # Parse Accept-Language header
                header_lang = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
                lang = self._parse_accept_language(header_lang)
                request.LANGUAGE_CODE = lang or LanguageLocale.RUSSIAN
        
        # Set on session for logged-in users
        if request.user.is_authenticated and not request.GET.get("lang"):
            request.session["language"] = request.LANGUAGE_CODE
    
    def _parse_accept_language(self, header: str) -> str | None:
        """Parse Accept-Language header, return best match."""
        if not header:
            return None
        for part in header.split(","):
            code = part.split(";")[0].strip().lower()
            if code in LanguageLocale.values:
                return code
        return None
```

**Language switcher UI (header dropdown):**
```html
<div class="relative inline-block" id="lang-switcher">
    <button type="button" class="flex items-center gap-1 px-3 py-1 text-sm rounded hover:bg-gray-100">
        <span>{{ current_lang|upper }}</span>
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
    </button>
    <div class="absolute right-0 mt-1 w-32 bg-white border rounded-md shadow-lg hidden">
        <a href="?lang=ru" class="block px-4 py-2 text-sm hover:bg-gray-100">Русский</a>
        <a href="?lang=bs" class="block px-4 py-2 text-sm hover:bg-gray-100">Боснийский</a>
        <a href="?lang=en" class="block px-4 py-2 text-sm hover:bg-gray-100">English</a>
    </div>
</div>
```

### 2. Ad Translation Storage Design

**Schema approach: Separate columns (Option A)**

```python
# apps/core/enums.py
class LanguageLocale(StrEnum):
    """Supported locale codes for UI and content."""
    RUSSIAN = "ru"
    BOSNIAN = "bs"
    ENGLISH = "en"
    
    @property
    def fts_config(self) -> str:
        """PostgreSQL text search config for this language."""
        return {
            LanguageLocale.RUSSIAN: "russian",
            LanguageLocale.BOSNIAN: "simple",  # PG18 no 'bosnian'
            LanguageLocale.ENGLISH: "english",
        }[self]

# Ad model additions
title_bs = models.CharField(max_length=200, blank=True, null=True)
description_bs = models.TextField(blank=True, null=True)
title_en = models.CharField(max_length=200, blank=True, null=True)
description_en = models.TextField(blank=True, null=True)
original_language = models.CharField(max_length=5, blank=True, null=True)

def get_title(self, locale: str = "ru") -> str:
    """Get localized title with fallback chain: locale → ru → first available."""
    # Implementation returns translated or fallback content
```

### 3. Multi-Language Search Vector Design

```sql
-- Migration 0003: Multi-language search vector
CREATE OR REPLACE FUNCTION ads_search_vector_update() RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
        setweight(to_tsvector('simple', coalesce(NEW.title_bs,'')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.description_bs,'')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.title_en,'')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.description_en,'')), 'B') ||
        setweight(to_tsvector('simple', coalesce(v_cat,'')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 4. Moderation with Multi-Language Content

Checks ALL localized versions against banned_words. Duplicate detection across languages.

### 5. Django i18n vs Custom Approach

**Hybrid: UI → gettext, Ad content → columns**

| Aspect | gettext | JSONB | Decision |
|--------|---------|-------|----------|
| UI strings | ✅ Standard | ❌ | gettext |
| Ad content | ❌ | ✅ FTS | Columns |
| Categories | ✅ | ✅ | JSONB (existing) |

---

## Final Architecture Decision

1. **UI localization:** Django gettext
2. **Ad content:** Separate columns per language
3. **Reference data:** JSONB `name_i18n` (existing)
4. **Search:** Multi-language GIN index
5. **Language switcher:** Cookie + URL param

### Phase 1: Foundation

1. **Add language columns to ads table:**
   ```python
   # Ad model additions
   title_en = models.CharField(max_length=200, blank=True, null=True)
   description_en = models.TextField(blank=True, null=True)
   title_bs = models.CharField(max_length=200, blank=True, null=True)  
   description_bs = models.TextField(blank=True, null=True)
   original_language = models.CharField(max_length=5, blank=True, null=True)
   ```

2. **Update search_vector trigger:**
   - Create separate search vectors per language OR
   - Create combined multi-language search vector

3. **Create language middleware:**
   - Detect/set `request.LANGUAGE`
   - Read from cookie or URL param

4. **Update bot translation service:**
   - Translate to all languages on ad creation
   - Store original language for reference

5. **Add language switcher UI:**
   - Simple dropdown in header
   - Sets cookie via JavaScript

### Phase 2: UI Localization

1. **Create message files:**
   - `locale/ru/LC_MESSAGES/django.po`
   - `locale/bs/LC_MESSAGES/django.po`  
   - `locale/en/LC_MESSAGES/django.po`

2. **Wrap UI strings:**
   - Use `{% trans "Search ads..." %}`
   - Use `{% trans "Contact Seller" %}`

3. **Update templates:**
   - Use `get_title(locale=request.LANGUAGE)` method on Ad model
   - Use `get_description(locale=request.LANGUAGE)` method

### Phase 3: Multi-Language Search

1. **Language-specific search:**
   - Detect query language (or use `request.LANGUAGE`)
   - Search in appropriate search_vector

2. **Cross-language search option:**
   - Search all languages simultaneously
   - Return results with language labels

---

## Implementation Priority

### HIGH Priority (Phase 1 required)

1. **Database schema changes** — add translated content columns
2. **Ad model methods** — `get_title(locale)`, `get_description(locale)`  
3. **Bot translation enhancement** — translate to all languages on creation
4. **Language middleware** — detect/set user preference
5. **Search vector migration** — update trigger for multi-language content

### MEDIUM Priority (Phase 2)

1. **Language switcher component** — dropdown in header
2. **UI string extraction** — wrap common strings
3. **Template updates** — use localized content

### LOW Priority (Future)

1. **Auto-detection of query language** — beyond Bosnian→Russian
2. **Cross-language search** — search all languages at once
3. **RTL language support** — Arabic, Hebrew

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Translation API failures | Circuit breaker already exists (reuse pattern) |
| PostgreSQL text search config for Bosnian | Use `simple` config or custom dictionary |
| Performance impact of multi-language search | Separate GIN indexes per language vector |
| Data migration for existing ads | Backfill via Google Translate API for `en`/`bs` |

---

## References

- PostgreSQL 18 text search configurations: `russian`, `english`, `simple` (built-in)
- `deep-translator` for API-based translation
- Existing `TranslationCircuitBreaker` pattern in `query_translator.py`
- JSONB `name_i18n` pattern in `categories/models.py` and `locations/models.py`