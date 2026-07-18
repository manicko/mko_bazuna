# Phase 5: Scraping Service + Internationalization - Refined Implementation Plan

## Overview
This is Phase 5 of the development roadmap for the Django Telegram classifieds MVP. Phase 5 implements two separate components:

1. A **standalone Scraping Service** that implements Decision B from Phase 1: Third-party Telegram group monitoring as a separate future phase with its own API and completely independent from the core system.

2. **Ukrainian Interface Language Support** to complement the existing Russian-language system.

**Key Architectural Decisions:**
- Decision B: Scraping is a SEPARATE future phase with its own API (NOT in Phase 1 bot)
- Decision D2: name_i18n JSONB for categories+cities with ru/uk keys  
- Ukrainian (Ukr.) - new target second language with Latin alphabet (geography: Ukraine)
- Decision G: Content invariant - stored content is Ukrainian (new base language)
- Search in Phase 5 - by Ukrainian content (queries on Ukrainian search)

---

## Task 1: Scraping Service Schema (Decision B: Separate API)
**Goal:** Implement dedicated scraping API with independent data model and `telegram_message_id` tracking for third-party sources.

**Acceptance Criteria:**
- Create `scraping/` app with its own `AdSource.SCRAPING` enum value
- Add `telegram_message_id` (BIGINT, nullable, UNIQUE, indexed) to `ads` model (Phase 5 migration only)
- Implement separate ORM models for scraping-specific data and workflow
- Ensure scraping writes through dedicated API (not shared core ORM)
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
**Goal:** Standalone service implementing Decision B: Monitor third-party Telegram groups with Telethon MTProto.

**Acceptance Criteria:**
- Create `scraping_service/` as completely independent process 
- Implement Telethon MTProto userbot with phone login authentication
- Use Telethon>=1.44.0 for third-party group monitoring
- Parse messages from configured external groups/channels
- Extract ad structure (photos, text, price) via Telethon message parsing
- Write ads via SCRAPING API (NOT shared ORM from Phase 1)
- Dedup by `telegram_message_id` (unique constraint per Task 1)
- Run as separate systemd service with persistent sessions
- Log all scraping activities with error handling and retry logic
- Implement robust filtering based on Phase 1 moderation_criteria

**Artifacts:**
- `scraping_service/` root with `__init__.py`, `config.py`, `main.py`
- Telethon session storage in `scraping_service/sessions/`
- `systemd/unit/scraping.service` file
- `scraping_service/requirements.txt` (Telethon>=1.44.0)
- Docker configuration with persistent storage
- Integrated moderation filtering

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

## Task 3: Ukrainian Interface Language (Decision D2)
**Goal:** Add Ukrainian interface language support while maintaining Ukrainian content storage.

**Acceptance Criteria:**
- Implement `/set-lang/ukrainian` and `/set-lang/russian` endpoints for session locale
- Create `get_name(locale)` utility using `name_i18n` JSONB
- Ukrainian `name_i18n.bs` priority when locale=Ukr.
- Ukrainian storage as base language (replacement for Russian)
- Update all templates with `{% trans "key" %}` Ukrainian default
- UI content translation for common interface elements
- Maintain backward compatibility with existing Phase 1

**Artifacts:**
- `core/utils/i18n.py` with language utilities
- `core/middleware/language_middleware.py`
- Updated `core/categories/models.py`, `core/locations/models.py` `get_name()` methods
- `templates/i18n/` with Ukrainian translations
- `templates/base.html` with language switcher
- `core/context_processors/i18n_context.py`

**Risks:**
- Translation file synchronization
- UI maintenance burden (Russian+Ukrainian)
- Session management complexity
- JavaScript frontend localization
- JSONB lookup performance

**Dependencies:**
- Phase 1 core structure setup
- `name_i18n` fields populated
- Database migrations for language fields

---

## Task 4: Query Translation Integration
**Goal:** Search-time query translation for Ukrainian- to-Ukrainian search.

**Acceptance Criteria:**
- Translate Ukrainian query to Ukrainian before FTS (deep-translator)
- Cache translations with 5-minute TTL
- 500ms timeout with fallback to original query
- Integrate into search view before FTS query
- Mark translated results appropriately
- Monitor translation accuracy and performance
- Graceful degradation when service unavailable

**Artifacts:**
- `core/services/translation.py` with caching
- `core/middleware/search_translation_middleware.py`
- Updated `core/search/utils.py`
- Configuration and monitoring
- Error handling and fallbacks

**Risks:**
- API key security and management
- Translation accuracy
- Performance during load
- Rate limiting
- Cache consistency

**Dependencies:**
- `deep-translator>=1.11.0` dependency
- Phase 1 search functionality
- Caching infrastructure
- External API key management

---

## Task 5: Content Language Invariant Check (Decision G)
**Goal:** Ensure all content is stored in Ukrainian for FTS compatibility (replacement for Russian invariant).

**Acceptance Criteria:**
- Verify Phase 1 translates seller input to Ukrainian on creation
- Confirm `search_vector` works on Ukrainian content only
- Implement content validation for Ukrainian text only
- Add automated tests for normalization
- Display translations back to Ukrainian for Ukr. locale
- Create compliance monitoring
- Update language policy documentation

**Artifacts:**
- `core/validation/content_language_validator.py`
- Updated `core/ads/services/content_translate.py`
- Migration cleanup for non-Ukrainian content
- Automated testing suite
- Documentation in specs (Decision G)
- Logging for violations

**Risks:**
- Non-Ukrainian test content
- Content loss during cleanup
- Complex edge cases
- Validation performance
- Backward compatibility

**Dependencies:**
- Phase 1 content translation
- Database migration for cleanup
- Validation infrastructure
- Test framework

---

## Task 6: Documentation Updates
**Goal:** Update technical specifications for scraping and i18n implementation.

**Acceptance Criteria:**
- Update specs with Decision B (separate scraping) and Decision G (translation)
- Update packages.md with Telethon>=1.44.0 and deep-translator
- Update structure.md with `scraping_service/` and i18n
- Update db_structure.md with `telegram_message_id` column
- Add migration and deployment documentation
- Create runbooks for troubleshooting
- Update architectural logs (ADRs)

**Artifacts:**
- Updated sections in all wiki files
- ADR documents for scraping and i18n
- Operation/maintenance documentation
- Troubleshooting guides

**Risks:**
- Documentation drift
- Inconsistency across files
- Missing details
- Quality issues

**Dependencies:**
- Updated implementation files
- Technical review
- Language expertise for translations

---

## Implementation Timeline

### Phase 5.1 (Weeks 1-4): Schema and Infrastructure
- Task 1: Schema migration (week 1)
- Task 3: Basic Ukrainian language switcher (week 2)
- Task 4: Query translation setup (week 3)
- Task 5: Content validation framework (week 4)

### Phase 5.2 (Weeks 5-8): Service Implementation
- Task 2: Telethon scraping service (weeks 5-7)
- Task 6: Documentation and deployment (week 8)

## Risk Mitigation

1. **Technical:** Incremental development with testing
2. **Data:** Backups before deployment
3. **Performance:** Load testing before full deployment
4. **Operational:** Runbooks and monitoring
5. **Documentation:** Regular reviews alongside implementation

## Success Metrics

- Scraping: 100+ messages/hour, 99.9% uptime
- Language: UI working with 95% translation accuracy
- Translation: 80% Ukrainian query handling
- Language: Zero non-Ukrainian content in searchable fields
- Documentation: >90% completeness
- Compatibility: Phase 1 compatibility maintained
