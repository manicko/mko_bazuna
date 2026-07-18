---
id: audit-resolutions
domain: wiki
tags:
  - audit
  - architecture
  - decisions
related:
  - 01-technical-specification
  - 04-db-structure
---

## Purpose

Консолидированный итог архитектурного аудита MVP (зоны C1–C8, R1–R9, D1–D12). Каждая зона прошла 3x исследование + валидацию (ACCEPT). Все решения перенесены в основные доки и помечены ID зоны инлайн.

> Этот файл — единственный источник всех **решений владельца (O1–O5)** и итоговых резолюций.

## Главные решения владельца (O1–O5)

| ID | Тема | Решение владельца |
|----|------|-------------------|
| **O1** (R4) | Удаление/запрет/бан | Три НЕЗАВИСИМЫХ состояния: (1) запрет публикации `ads_auto_publish=False` — обратим, СТАРЫЕ скрыты; (2) удаление — мягкое + обнуление PII через 30д; (3) бан — `telegram_id`+`username` стоп-лист, PURGE объявлений, PII не стирается. |
| **O2** (R3) | Баннер «Отказаться» vs «Удалить» | РАЗНЫЕ состояния. «Отказаться» блокирует вход, НЕ стирает, НЕ скрывает контакт. «Удалить»/отзыв — `consent_revoked_at` + полное стирание. |
| **O3** (R1) | Полнота стирания | **Полное стирание**: через 30д — DELETE объявлений (+`ad_images`), NULL `telegram_id`+`username`, SET NULL `analytics_events.user_id` и `ModeratorActionLog.user_id`. |
| **O4** (D3/D4) | Критерии модерации | 2 слоя: авто (текст/длины/поля/дубли в `moderation_criteria`) + ручная админом (фото/контент, будущий ML). Без версионирования. `min_text_length` удалён. |
| **O5** (D1/D2) | Поиск по категории | ОБЯЗАТЕЛЕН (гибрид C): `ads.category_name` + `search_vector` (вес 'C') + fuzzy-детект `category_id`. |

## Сводка резолюций

| Зона | Решение |
|------|---------|
| **C1** | `login_tokens`: SHA-256 token_hash, двухфазный атомарный claim, `hmac.compare_digest`, cookie SECURE/HTTPONLY/SAMESITE=Lax. |
| **C2 / C3** | `PUBLISHED → ON_MODERATION` (текст, скрытие). Таймеры по `published_at`; `original_published_at` — аудит-метка. |
| **C4 / D12** | `moderation_failed_at` + 3 частичных sweep + `IX_ads_rejected_sweep` (90д) + `GinIndex`. |
| **C5 / C7** | `sync_to_async`, per-process pool, PgBouncer, миграции 1 раз. Цена: индекс после 500k EXPLAIN. deep-translator 500ms + fallback. |
| **R1** | Полное стирание (O3) + `IX_users_erasure_sweep`. |
| **R2 / R3** | Контакт только при PUBLISHED + telegram_id NOT NULL + не удалён/бан/отзыв. Decline≠Withdrawal. |
| **R4** | Три состояния (O1). |
| **R5** | `analytics_events.user_id` SET NULL при стирании. |
| **R6 / R8** | `ad_images.image` ad-scoped + UUID v4. JPEG-валидация. nginx nosniff/whitelist/inline. |
| **R7** | `API_ID`/`API_HASH` удалены из `.env`. |
| **R9** | BANNED сохраняет telegram_id; DELETED пост-30д переиспользует строку. |
| **D1 / D2** | O5. `name_i18n` JSONB ru/bs, `get_name(locale)`. |
| **D3 / D4** | O4. `moderation_criteria` 2 слоя. REJECTED 90д, `rejected_at` ⊥ `moderation_failed_at`. |
| **D5 / D6** | Бот переводит на русский при создании. GIN. |
| **D7 / D9 / D10** | FSM отдельный владелец миграций; кэш категорий; Web sync WSGI. |
| **D8** | `ModeratorActionLog`: ad_id, user_id SET NULL, action_type, reason, created_at. |
| **D11** | `currency` удалён; `price` INT whole BAM. |

## Удаление `.ai/`

`.ai/problems/AUDIT_ZONES_01.md` и `.ai/researches/*` — временные, удаляются ДО старта разработки. Всё значимое перенесено сюда + в `01`–`04`.
