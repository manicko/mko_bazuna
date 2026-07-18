# Phase 5: Scraping Service + Internationalization - Implementation Plan

## Overview
This is Phase 5 of the development roadmap for the Django Telegram classifieds MVP. Phase 5 implements the deferred scraping service and adds Bosnian interface support to complement the existing Russian-language system.

**Scope:** Independence from Phase 1, strict separation of concerns, minimal coupling.

---

## Task 1: Scraping Schema Migration
**Goal:** Add Telegram message tracking for third-party source ads with unique identifiers.

**Acceptance Criteria:**
- Add `telegram_message_id` (BIGINT, nullable, UNIQUE, indexed) column to `ads` model
- Extend `AdSource` enum to include `TELEGRAM_SCRAPED` value
- Create Phase 5 migration that adds column without downtime
- Ensure migration handles existing ads gracefully (null values allowed)

**Artifacts:**
- `apps/ads/migrations/000X_add_scraping_fields.py` (Phase 5 migration)
- Updated `apps/ads/models.py` with new field and enum
- Updated `apps/ads/management/commands/migrate_scraping_schema.py` (if needed)

**Risks:**
- Column name collisions with existing Telegram-related columns
- Unique constraint impact on existing data integrity
- Migration performance on large tables (~500k rows)
- Potential conflict with future Phase 2 monitoring (separate API)

**Dependencies:**
- Phase 1 Task 2 (shared ORM setup)
- Database schema frozen until after Phase 1 data migration
- Requires PostgreSQL unique constraint optimization

---

## Task 2: Telethon Scraping Service Implementation
**Goal:** Standalone service that monitors third-party Telegram groups and imports ads via shared ORM.

**Acceptance Criteria:**
- Create `scraping_service/` as independent process separate from aiogram bot
- Implement Telethon MTProto userbot with phone login authentication
- Configure group/channel monitoring from external config
- Parse incoming messages extracting: title, description, price, photos, source info
- Create new ads via shared Django ORM with `source=TELEGRAM_SCRAPED`
- Implement deduplication using `telegram_message_id` unique constraint
- Run as separate systemd service with persistent storage for Telethon sessions
- Log all scraping activities with error handling and retry logic

**Artifacts:**
- `scraping_service/` directory with `__init__.py`, `config.py`, `main.py`, `parser.py`, `handlers.py`
- `systemd/unit/scraping.service` file
- `scraping_service/sessions/` directory for Telethon session storage
- `requirements_scraping.txt` (Telethon dependency)
- Docker configuration for persistent scraping service

**Risks:**
- Telegram Terms of Service violations leading to account ban
- Parsing reliability with diverse ad formats
- Session persistence and authentication complexity (phone codes)
- Network reliability and rate limiting
- Memory usage with high-volume message processing
- Data quality of third-party source ads vs. Phase 1 quality
- Sync issues between separate processes (scraping vs. bot)

**Dependencies:**
- Task 1 (schema migration completed)
- Telethon>=1.44.0 dependency installed
- Phase 1 shared ORM and database connectivity
- External group/channel configuration

---

## Task 3: UI Language Switcher (RU/BOS)
**Goal:** Add Bosnian (latiničina) interface language support while maintaining Russian content storage.

**Acceptance Criteria:**
- Implement `/set-lang/bosnian` and `/set-lang/russian` endpoints for session locale management
- Create Django middleware for language session handling
- Update all templates to use `{% trans "key" %}` with Russian default
- Implement `get_name(locale)` utility for categories and cities using `name_i18n` JSONB
- When locale=BOS, prioritize `name_i18n.bs` over `name.ru` for display
- When locale=RU, use `name.ru` for all UI elements
- Maintain Russian content invariant (ad titles/descriptions always Russian)
- Add UI content translation for common interface elements
- Ensure backward compatibility with Phase 1 (RU-only) behavior

**Artifacts:**
- `core/utils/i18n.py` with language utilities
- `core/middleware/language_middleware.py`
- Updated `apps/categories/models.py` and `apps/locations/models.py` `get_name()` methods
- `templates/i18n/` directory with extracted translation strings
- Updated `templates/base.html` with language switcher
- `apps/core/context_processors/i18n_context.py` for template context

**Risks:**
- Translation file synchronization complexity
- Maintenance burden of duplicated interface text
- UI language caching and session management issues
- JavaScript frontend localization (if any)
- Performance impact of JSONB lookups
- Context confusion between interface language and search language

**Dependencies:**
- Phase 1 Task 3 (core structure setup)
- Django translation framework configured
- `name_i18n` fields populated for categories and cities
- Database migrations for language fields

---

## Task 4: Query Translation Integration
**Goal:** Enable Bosnian search queries with automatic Russian translation for compatible search.

**Acceptance Criteria:**
- Implement Bosnian-to-Russian query translation using `deep-translator` library
- Add translation cache with 5-minute TTL to reduce API calls
- Implement translation timeout protection (~500ms)
- Fallback to original query if translation fails
- Integrate translation into search view before FTS query
- Preserve translated query for result marking (e.g., "translated from Bosnian")
- Monitor translation accuracy and performance
- Graceful degradation when translation service unavailable
- Ensure Bosnian queries work even when translation disabled

**Artifacts:**
- `core/services/translation.py` with translation caching
- Updated `core/middleware/search_translation_middleware.py`
- Updated `apps/search/utils.py` to handle pre-translation
- Cache configuration and monitoring
- Error handling and fallback logic

**Risks:**
- Translation API key management and security
- Translation accuracy and false positives
- Performance impact during high search load
- Rate limiting from translation service
- Cache invalidation and consistency issues
- API key rotation complexity

**Dependencies:**
- `deep-translator>=1.11.0` dependency installed
- Phase 1 Task 11 (search functionality)
- Caching infrastructure (Redis/memcached)
- External API key management

---

## Task 5: Content Language Invariant Check
**Goal:** Verify and maintain that all content is stored in Russian for FTS compatibility.

**Acceptance Criteria:**
- Verify Phase 1 bot implementation translates seller input to Russian on creation
- Confirm `search_vector` FTS works exclusively on Russian content
- Implement content validation to ensure no Bosnian text in searchable fields
- Add automated tests for content normalization
- Display translated back to Bosnian for BOS locale users
- Create content compliance monitoring
- Update documentation with clear language policies
- Ensure all Phase 1 processes follow Russian storage invariant

**Artifacts:**
- `core/validation/content_language_validator.py`
- Updated `apps/ads/services/content_translate.py` with validation
- Migration data cleanup for existing non-Russian content (if any)
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
- Phase 1 Task 9 (content translation implementation)
- Database migration for data cleanup
- Content validation infrastructure
- Automated test framework setup

---

## Task 6: Documentation Updates
**Goal:** Update technical specifications and architectural documentation for scraping and i18n features.

**Acceptance Criteria:**
- Update `docs/wiki/01_technical_specification.md` with Decision B (separate scraping) and Decision G (translation) details
- Update `docs/wiki/02_packages.md` with Telethon dependency and deep-translator integration
- Update `docs/wiki/03_structure.md` with scraping_service entry and i18n implementation
- Update `docs/wiki/04_db_structure.md` with `telegram_message_id` column documentation
- Add migration documentation and service deployment instructions
- Update architectural decision logs (ADRs) for new components
- Create runbooks for troubleshooting scraping and translation issues
- Add performance and scaling considerations documentation

**Artifacts:**
- Updated section in all wiki files
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
- Task 3: Basic language switcher (week 2)
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

- Scraping service processes 100+ messages per hour with 99.9% uptime
- Language switcher works for all UI elements with 95% translation accuracy
- Search translation handles 80% of Bosnian queries successfully
- Zero Russian content leakage in searchable fields
- Documentation completeness score > 90%
- System maintains Phase 1 compatibility throughout implementation