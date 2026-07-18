# Phase 5: Scraping Service + Internationalization - Final Refined Implementation Plan

## Overview
This is Phase 5 of the development roadmap for the Django Telegram classifieds MVP. Phase 5 implements two components:

1. A **standalone Scraping Service** that implements Decision B: Third-party Telegram group monitoring as a separate future phase with its own API.

2. **Bosnian Interface Language** support to complement the existing Russian-language system.

**Key Architectural Decisions:**
- Decision B: Scraping is a SEPARATE future phase with its own API (NOT in Phase 1 bot)
- Decision D2: name_i18n JSONB for categories+cities with ru/bs keys
- Bosnian (bs) - target second interface language with Latin alphabet (Ukraine)
- Decision G: Content invariant - stored content is Russian (base language)
- Search in Phase 5 - by Russian content (queries on Russian search, Bosnian queries translated)

---

## Task 1: Scraping Service Schema (Decision B: Separate API)
**Goal:** Implement dedicated scraping API with independent data model and `telegram_message_id` tracking for third-party sources.

**Acceptance Criteria:**
- Create `scraping/` app with its own `AdSource.SCRAPING` enum value
- Add `telegram_message_id` (BIGINT, nullable, UNIQUE, indexed) to `ads` model (Phase 5 migration only)
- Implement separate ORM models for scraping-specific data and workflow
- Ensure scraping writes through dedicated API (NOT shared ORM from Phase 1)
- Migration adds columns without downtime

**Artifacts:**
- `src/scraping/migrations/0001_scraping_schema.py`
- `src/scraping/models.py` (dedicated scraping models)
- `src/scraping/api/` (independent Django REST Framework API)
- `src/scraping/admin.py` (scraping-specific admin)

**Risks:**
- Schema collision with core `ads` table
- Version drift between scraping and core systems
- Independent upgrade complexity without core coupling

**Dependencies:**
- Phase 1 core ORM and database connectivity
- Separate scraping API endpoints planned

---

## Task 2: Telethon Scraping Service Implementation
**Goal:** Standalone service implementing Decision B: Monitor third-party Telegram groups with Telethon MTProto (separate from aiogram bot).

**Acceptance Criteria:**
- Create `scraping_service/` as completely independent process 
- Implement Telethon MTProto userbot with phone login authentication
- Use Telethon>=1.44.0 for third-party group monitoring (Decision B)
- Parse messages from configured external groups/channels
- Extract ad structure (photos, text, price) via Telethon message parsing
- Write ads via SCRAPING API (NOT shared ORM from Phase 1)
- Dedup by `telegram_message_id` (unique constraint per Task 1)
- Run as separate systemd service with persistent sessions
- Log all scraping activities with error handling and retry logic
- Implement robust filtering based on Phase 1 moderation_criteria (Decision A)

**Artifacts:**
- `scraping_service/` root with `__init__.py`, `config.py`, `main.py`, `parser.py`, `handlers.py`
- Telethon session storage in `scraping_service/sessions/`
- `systemd/unit/scraping.service` file
- `scraping_service/requirements.txt` (Telethon>=1.44.0)
- Docker configuration with persistent storage
- Integration with Phase 1 moderation_criteria

**Risks:**
- Telegram ToS violations/bans
- Parsing failures with diverse message formats
- Authentication complexity (phone codes)
- Network reliability and rate limits
- High memory usage during processing
- Data quality from third-party sources
- Sync between independent scraping and core systems

**Dependencies:**
- Task 1 (schema migration)
- Telethon>=1.44.0 dependency
- Phase 1 moderation_criteria integration

---

## Task 3: Bosnian Interface Language (Decision D2)
**Goal:** Add Bosnian interface language support while maintaining Russian content storage.

**Acceptance Criteria:**
- Implement `/set-lang/bosnian` and `/set-lang/russian` endpoints for session locale
- Create `get_name(locale)` utility using `name_i18n` JSONB with ru/bs keys
- Prioritize `name_i18n.bs` when locale=bs; Russian fallback for other locales
- Maintain Russian content invariant (Decision G)
- Update all templates with `{% trans "key" %}` with Russian default fallback
- UI content translation for common interface elements
- Maintain backward compatibility with existing Phase 1 (RU-only) behavior

**Artifacts:**
- `core/utils/i18n.py` with language utilities
- `core/middleware/language_middleware.py`
- Updated `apps/categories/models.py`, `apps/locations/models.py` `get_name()` methods
- `templates/i18n/` with Bosnian translations
- `templates/base.html` with language switcher
- `apps/core/context_processors/i18n_context.py`

**Risks:**
- Translation file synchronization
- UI maintenance burden (Russian+Bosnian)
- Session management complexity
- JavaScript frontend localization (if any)
- JSONB lookup performance impact
- Context confusion between interface language and search language

**Dependencies:**
- Phase 1 core structure setup
- `name_i18n` fields populated for categories and cities (ru/bs keys)
- Database migrations for language fields

---

## Task 4: Query Translation Integration
**Goal:** Search-time Bosnian query translation to Russian for Russian search (Decision G compliance).

**Acceptance Criteria:**
- Translate Bosnian query to Russian before FTS (deep-translator) (Decision G)
- Cache translations with 5-minute TTL
- 500ms timeout with fallback to original query
- Integrate into search view before FTS query (Decision G)
- Mark translated results appropriately
- Monitor translation accuracy and performance
- Graceful degradation when translation service unavailable

**Artifacts:**
- `core/services/translation.py` with caching
- `core/middleware/search_translation_middleware.py`
- Updated `apps/search/utils.py`
- Configuration and monitoring
- Error handling and fallback logic

**Risks:**
- API key security and management
- Translation accuracy (Bosnian->Russian)
- Performance during high search load
- Rate limiting from translation service
- Cache invalidation and consistency issues
- API key rotation complexity

**Dependencies:**
- `deep-translator>=1.11.0` dependency
- Phase 1 search functionality
- Caching infrastructure (Redis/memcached)
- External API key management

---

## Task 5: Content Language Invariant Check (Decision G)
**Goal:** Ensure all content is stored in Russian for FTS compatibility.

**Acceptance Criteria:**
- Verify Phase 1 translates seller input to Russian on creation (Decision G: Russian content stored)
- Confirm `search_vector` FTS works exclusively on Russian content
- Implement content validation to ensure no Bosnian text in searchable fields
- Add automated tests for content normalization
- Display content in localized language based on UI locale (Decision G)
- Create content compliance monitoring
- Update language policy documentation
- Ensure all Phase 1 processes follow Russian storage invariant

**Artifacts:**
- `core/validation/content_language_validator.py`
- Updated `apps/ads/services/content_translate.py` with validation
- Migration cleanup for existing non-Russian content (if any)
- Automated testing suite for language compliance
- Documentation in `docs/wiki/01_technical_specification.md` (Decision G)
- Logging middleware for language violation detection

**Risks:**
- Existing non-Russian content in database from testing/development
- Content loss during cleanup/migration processes
- Complex edge cases with mixed-language content
- Performance impact of validation checks
- Backwards compatibility with Phase 1 ad creation

**Dependencies:**
- Phase 1 content translation implementation
- Database migration for data cleanup
- Content validation infrastructure
- Automated test framework setup

---

## Task 6: Documentation Updates
**Goal:** Update technical specifications for scraping and i18n implementation.

**Acceptance Criteria:**
- Update `docs/wiki/01_technical_specification.md` with Decision B (separate scraping) and Decision G (translation) details
- Update `docs/wiki/02_packages.md` with Telethon dependency and deep-translator integration
- Update `docs/wiki/03_structure.md` with `scraping_service/` entry and i18n implementation
- Update `docs/wiki/04_db_structure.md` with `telegram_message_id` column documentation
- Add migration documentation and service deployment instructions
- Update architectural decision logs (ADRs) for new components
- Create runbooks for troubleshooting scraping and translation issues
- Add performance and scaling considerations documentation

**Artifacts:**
- Updated sections in all wiki files
- New ADR documents for scraping service and i18n implementation
- Operation and maintenance documentation
- Troubleshooting guides

**Risks:**
- Documentation drift between implementation and documentation
- Inconsistent documentation across files
- Missing details for future developers
- Documentation quality and completeness

**Dependencies:**
- Updated implementation files from all tasks above
- Technical review and approval from stakeholders
- Language and translation expertise for Bosnian terminology

---

## Implementation Timeline

### Phase 5.1 (Weeks 1-4): Schema and Infrastructure
- Task 1: Schema migration (week 1)
- Task 3: Basic Bosnian language switcher (week 2)
- Task 4: Query translation setup (week 3)
- Task 5: Content validation framework (week 4)

### Phase 5.2 (Weeks 5-8): Service Implementation
- Task 2: Telethon scraping service (weeks 5-7)
- Task 6: Documentation and deployment (week 8)

## Risk Mitigation Strategies

1. **Technical Risks:** Incremental development with thorough testing at each milestone
2. **Data Risks:** Comprehensive backups and validation before production deployment
3. **Performance Risks:** Load testing and optimization before full deployment
4. **Operational Risks:** Detailed runbooks and monitoring setup
5. **Documentation Risks:** Regular documentation reviews alongside implementation

## Success Metrics

- Scraping service processes 100+ messages per hour with 99.9% uptime (separate API working)
- Language switcher works for all UI elements with 95% translation accuracy
- Search translation handles 80% of Bosnian queries successfully
- Zero Russian content leakage in searchable fields (Decision G compliance)
- Documentation completeness score > 90%
- System maintains Phase 1 compatibility throughout implementation