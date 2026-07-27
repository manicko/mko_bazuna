# Mko Bazuna Backup Architecture Research

## Executive Summary

Mko Bazuna — это Telegram-бот и веб-платформа для объявлений (аналог Avito), реализованная на Django. Система использует микросервисную архитектуру с двумя процессами (web + bot) и PostgreSQL 18 в качестве единственного источника данных. Настоящий документ описывает архитектуру проекта с фокусом на то, **что нужно бэкапить и почему**.

---

## 1. Technology Stack

### Core Components

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| **Backend** | Django | >=5.2.16, <6.0 | Веб-фреймворк, ORM, бизнес-логика |
| **Python** | Python | 3.14 | Язык программирования |
| **Database** | PostgreSQL | 18-alpine | Основное хранилище данных |
| **Telegram Bot** | aiogram | 3.x | Интерфейс продавца |
| **WSGI Server** | gunicorn | >=26.0 | Синхронный веб-сервер |
| **Static Files** | WhiteNoise | >=6.12.0 | Обслуживание статики в контейнере |
| **Containerization** | Docker + Docker Compose | - | Оркестрация сервисов |

### Supporting Technologies

| Technology | Purpose |
|------------|---------|
| django-mptt | Иерархическое дерево категорий |
| django-filter | Фильтрация объявлений на сайте |
| django-environ | Управление переменными окружения |
| deep-translator | Перевод Montenegrin → Russian для FTS |
| pillow | Обработка изображений (thumbnail'ы) |
| nginx:alpine | Обратный прокси, TLS termination |

### Infrastructure Services (Optional)

| Service | Profile | Purpose |
|---------|---------|---------|
| pgbouncer | `--profile pgbouncer` | Connection pooling |
| backup | `--profile backup` | Автоматические бэкапы |
| scheduler | `--profile scheduler` | Периодические задачи (часовые sweep'ы) |

---

## 2. Data Storage

### 2.1 Database (PostgreSQL)

База данных является **единственным источником правды** для всей бизнес-логики. Все данные хранятся в единой схеме.

#### Main Tables (from db-schema.md)

**users**
- `id` (PK) — внутренний идентификатор
- `telegram_id` (BIGINT, UNIQUE) — Telegram ID пользователя
- `chat_id` (BIGINT) — стабильный Telegram chat ID
- `username` (VARCHAR, nullable) — публичный @username
- `is_staff`, `is_superuser` — права администатора
- `is_banned`, `is_deleted` — состояния аккаунта
- `ads_auto_publish` (BOOL) — ограничение на публикацию
- `consent_given_at`, `consent_revoked_at` — GDPR согласие

**login_tokens**
- Токены для атомарного входа через Telegram
- `token_hash` — SHA-256 от токена (сырой токен НЕ хранится)
- `expires_at` (+5 минут от создания)

**ads** (single table)
- `id`, `user_id`, `title`, `description`, `price`
- `category_id`, `city_id`, `category_name` (денормализовано, синхронизируется триггером)
- `status` (AdStatus enum: DRAFT, ON_MODERATION, PUBLISHED, REJECTED, ON_MODERATION_FAILED, ARCHIVED, DELETED)
- `source` (AdSource enum: TELEGRAM)
- `published_at`, `original_published_at` — таймеры архива/удаления
- `archived_at`, `deleted_at`, `moderation_failed_at`, `rejected_at`
- `search_vector` (TSVECTOR) — полнотекстовый поиск

**ad_images**
- `ad_id` (FK) — родительское объявление
- `image` (storage key, UUID v4) — путь к файлу в MEDIA_ROOT
- `telegram_file_id` — метаданные для дедупликации
- `position` — порядок в галерее
- `thumbnail_small/medium/large` — пути к миниатюрам

**categories** (MPTT tree)
- `id`, `name` (Russian), `name_i18n` (JSONB)
- `slug`, `parent_id`, `is_active`

**cities**
- `id`, `country_code`, `name` (Russian), `name_i18n` (JSONB)
- `region`, `slug`

**analytics_events**
- `id`, `event_type`, `timestamp`
- `user_id` (SET NULL on erasure)

**moderation_criteria**
- Синглтон-таблица с правилами модерации
- `title_min/max_length`, `description_min/max_length`
- `price_required`, `min/max_images`
- `banned_words`, `max_ads_per_user`, `duplicate_title_threshold`

**moderation_action_logs**
- Аудит действий модератора
- `ad_id`, `user_id`, `action_type`, `reason`

### 2.2 Media Files (Volume)

**Location:** `/app/media` (внутри контейнера) → `media_volume` (Docker volume)

**Structure:**
```
/app/media/
├── <uuid>.jpg              # Original uploaded photos
```

**Characteristics:**
- Файлы именуются UUID v4 (непредсказуемые, анонимные)
- Путь в базе: только `image` поле (storage key)
- **НЕ содержит PII** в имени файла (telegram_id, user_id исключены)
- Только JPEG (строгая валидация magic bytes)
- Максимум 2MB, максимум 2560px по длинной стороне
- EXIF данные очищаются при сохранении

**Estimated Volume:**
- Прогноз: ~200x200px средний размер миниатюры
- Оригиналы: 1-3 MB каждое
- Прогнозируемое количество: 10,000+ фото к концу MVP
- Примерный объем: 50-100 GB (с ростом)

### 2.3 Static Files

**Location:** `/app/staticfiles` (внутри контейнера)

**Content:**
- Скомпилированный Tailwind CSS
- Собранные Django static files
- **Реконструируемы** из исходного кода (не критичны для бэкапа)

### 2.4 Configuration

**Environment Variables (.env.docker):**
- `DJANGO_SECRET_KEY` — критично для безопасности
- `BOT_TOKEN` — токен Telegram бота
- `POSTGRES_*` — параметры БД
- `ADMIN_*` — учётные данные админа
- `TLS_CERT_PATH` — путь к сертификатам

**Docker Compose Override Files:**
- `docker-compose.prod.yml` — production overrides
- `docker-compose.dev.override.yml` — development overrides

---

## 3. Deployment Architecture

### 3.1 Services

```
┌─────────────────────────────────────────────────────────────┐
│                      nginx:alpine                           │
│  Ports: 80 (→ HTTPS), 443                                 │
│  - TLS termination                                          │
│  - Rate limiting (/login/, /search/)                         │
│  - Proxy to web (port 8000)                                │
│  - Прокси /media/ → web (контроль доступа)                 │
└─────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        │                                 │
        ▼                                 ▼
┌─────────────────┐             ┌─────────────────┐
│   web           │             │   bot           │
│   gunicorn:8000 │             │   python -m     │
│                 │             │   telegram_bot  │
│ - Django WSGI   │             │                 │
│ - REST API      │   ◄──────── │ - Telegram bot  │
│ - HTMX MPA      │   SAME DB   │ - FSM dialogs   │
│ - media_write   │             │ - media_write   │
└─────────────────┘             └─────────────────┘
        │                                 │
        └─────────────────┬───────────────┘
                          ▼
              ┌─────────────────────┐
              │   postgres:18       │
              │   Volume:           │
              │   postgres_data     │
              │   media_volume      │
              └─────────────────────┘
```

### 3.2 Volumes

| Volume Name | Type | Purpose | Critical? |
|-------------|------|---------|-----------|
| `postgres_data` | Named volume | Данные БД | **YES** |
| `media_volume` | Named volume | Медиа файлы | **YES** |

### 3.3 Network Flow

1. **Внешний запрос** → nginx (80/443)
2. **Static files** → nginx → `/static/` → proxy → web:8000
3. **Media files** → nginx → `/protected-media/` → internal → web (access control)
4. **Dynamic requests** → nginx → proxy → web:8000
5. **Telegram webhook** → bot (внутренний polling/webhook)
6. **Оба процесса** → общая БД (postgres_data)

---

## 4. Failure Points and Critical Data

### 4.1 Critical Failure Scenarios

| Scenario | Impact | Recovery Priority | Data at Risk |
|----------|--------|-------------------|--------------|
| **PostgreSQL volume corruption** | Complete data loss | **HIGH** (immediate) | All database data |
| **Media volume loss** | Missing ad photos | HIGH | All uploaded images |
| **Secret key leak/expiry** | Security breach, session invalidation | HIGH | DJANGO_SECRET_KEY |
| **Bot token compromise** | Unauthorized bot control | HIGH | BOT_TOKEN |
| **Disk full on DB volume** | Write failures, DB crash | **HIGH** | All pending writes |
| **Corrupted backup** | Restore impossible | HIGH | Backup integrity |

### 4.2 Critical Data Classification

#### 🔴 CRITICAL (Must backup daily)

| Data | Reason | Backup Method |
|------|--------|-------------|
| **PostgreSQL database** | Бизнес-логика, пользователи, объявления | `pg_dump -F c` |
| **Media files** | Фотографии объявлений (основная ценность) | Volume snapshots |

#### 🟡 IMPORTANT (Secondary priority)

| Data | Reason | Backup Method |
|------|--------|-------------|
| **Django migrations** | Схема БД (можно реконструировать) | Git repository |
| **Source code** | Восстановление системы | Git repository |
| **Nginx config** | Routing rules | Git repository |
| **TLS certificates** | HTTPS (могут быть выписаны заново) | Let's Encrypt/ACME or external |

#### 🟢 RECONSTRUCTIBLE (Low priority)

| Data | Reason | Recovery Method |
|------|--------|-----------------|
| **Static files** | Собираются из кода | `collectstatic` |
| **Python dependencies** | Восстановятся из lock | `uv sync` |

### 4.3 Data Growth Projections

| Entity | Projected Volume (Year 1) | Storage Impact |
|--------|---------------------------|----------------|
| Users | 10,000-50,000 | ~10 MB |
| Ads | 30,000-100,000 | ~200 MB |
| Photos | 50,000-200,000 | **50-200 GB** |
| Thumbnails | 3x photos | ~150 GB additional |

**Conclusion:** Медиа файлы доминируют по объёму. Бэкап должен быть differential (snapshot-based) или использовать deduplicated storage.

---

## 5. Current Backup Implementation

### 5.1 Docker Compose Backup Service

```yaml
# docker-compose.prod.yml
services:
  backup:
    image: postgres:18-alpine
    environment:
      POSTGRES_HOST: db
      POSTGRES_PORT: 5432
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      PGPASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./backups:/backups
    command:
      - /bin/sh -c "... pg_dump -F c ..."
    profiles: ["backup"]
```

**Characteristics:**
- **NOT enabled by default** (requires `--profile backup`)
- Daily schedule (86400 seconds sleep)
- Custom format (`-F c`) — compressed
- Retention: 7 days
- **Output:** `./backups/dump_YYYYMMDD.dump`

### 5.2 Makefile Backup Targets

```makefile
backup:
    # Creates timestamped backup: dump_YYYYMMDD_HHMMSS.dump
    # Runs prune-backups after

restore:
    # Restores from specified file
    # Stops web/bot services first

prune-backups:
    # Deletes files older than 7 days
```

### 5.3 Gaps in Current Implementation

| Gap | Risk | Mitigation Needed |
|-----|------|-------------------|
| **No media backup** | 🔴 Photo loss = простои | media_volume snapshots |
| **No offsite storage** | 🔴 Single-point failure | rsync/AWS S3/GCS sync |
| **No backup verification** | 🔴 Corrupted backups undetected | pg_restore --list check |
| **No pre-restore safety** | 🟡 Accidental restore | Confirmation prompts |
| **No point-in-time recovery** | ��� Only latest day | WAL archiving |
| **No secret backup** | 🔴 Cannot restore config | .env + TLS cert backup |

---

## 6. What to Backup — Detailed Matrix

### 6.1 Database Backup Strategy

| Table/Data | Backup Method | RPO | RTO | Notes |
|------------|--------------|-----|-----|-------|
| **All tables** | Full dump (`pg_dump -F c`) | 24h | 1h | Daily, включая структуру |
| **ads + ad_images** | Critical subset | - | - | Largest tables |
| **users + login_tokens** | Include sensitive | - | - | GDPR considerations |
| **categories + cities** | Include seed data | - | - | Reference data, static |
| **Moderation tables** | Full dump | - | - | Compliance required |

**Command:**
```bash
pg_dump -h db -U $POSTGRES_USER -d $POSTGRES_DB -F c -f /backups/dump_YYYYMMDD.dump
```

### 6.2 Media Backup Strategy

| Content | Method | Frequency | Notes |
|---------|--------|-----------|-------|
| **Original photos** | Volume snapshot | Daily | Largest volume |
| **Thumbnails** | From originals | On-demand | Can be regenerated |
| **Upload queue** | Include in dump | - | Part of DB |

**Options:**
1. **Docker volume backup:**
   ```bash
   docker run --rm -v mko_bazuna_media_volume:/media \
     -v $(pwd)/backups:/backups \
     alpine tar -czf /backups/media_$(date +%Y%m%d).tar.gz /media
   ```

2. **File-level backup:**
   ```bash
   tar -czf media_backup_$(date +%Y%m%d).tar.gz \
     -C /var/lib/docker/volumes mko_bazuna_media_volume/_data
   ```

### 6.3 Configuration Backup

| Item | Critical | Backup Location |
|------|----------|---------------|
| `.env.docker` | 🔴 YES | Version control (NO secrets) или separate vault |
| TLS certificates | 🟡 Partial | ACME cache, можм быть выписаны заново |
| `nginx.conf` | 🟢 NO | Git repository |
| `docker-compose.*.yml` | 🟢 NO | Git repository |

**Требования к .env.docker:**
- DJANGO_SECRET_KEY — регенерируется с системы оффлайн невозможно
- BOT_TOKEN — можно запросить новый через BotFather, но потребуется обновить подписчиков
- POSTGRES_PASSWORD — если изменён, restore не сработает

---

## 7. Recovery Procedures

### 7.1 Database Restore

```bash
# 1. Stop write services
docker compose stop web bot

# 2. Verify backup exists
ls -la ./backups/dump_*.dump

# 3. Restore
docker compose exec -T db pg_restore \
    --clean --if-exists \
    -U $POSTGRES_USER \
    -d $POSTGRES_DB \
    ./backups/dump_YYYYMMDD.dump

# 4. Start services
docker compose start web bot
```

**Critical Considerations:**
- Все транзакции после времени бэкапа потеряны
- MEDIA_ROOT не трогается (файлы могут become orphan)
- После restore нужны новые миграции (если БД "старше" кода)

### 7.2 Media Restore

```bash
# 1. Stop services
docker compose stop web bot

# 2. Clear volume
docker volume rm mko_bazuna_media_volume

# 3. Restore volume
docker run --rm -v mko_bazuna_media_volume:/media \
    -v $(pwd)/backups:/backups \
    alpine sh -c "cd / && tar -xzf /backups/media_YYYYMMDD.tar.gz"

# 4. Fix permissions (uid 1000)
docker compose run --rm web chown -R 1000:1000 /app/media

# 5. Start services
docker compose start web bot
```

---

## 8. Recommendations

### 8.1 Immediate (MVP)

1. **Enable daily backup profile:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml \
     --profile backup up -d
   ```

2. **Add media volume backup:**
   - Daily tar gzip of media_volume
   - Store in `./backups/media/`

3. **Offsite sync (weekly):**
   - rsync to remote server
   - или S3/GCS sync

4. **Backup verification script:**
   - `pg_restore --list` на случайный backup
   - Проверка наличия media файлов

### 8.2 Future (Production-grade)

| Feature | Implementation |
|---------|---------------|
| **WAL archiving** | Continuous archiving для PITR |
| **S3/MinIO backend** | Для media (ELIMINATES volume backup) |
| **Encrypted backups** | GPG/SSE-C для конфиденциальности |
| **Backup monitoring** | Healthchecks + alerting |
| **Automated DR runbook** | GitOps recovery scripts |

---

## 9. Backup Storage Requirements (Estimation)

### 9.1 Daily Growth Estimates

| Component | Size per item | Projected items | Daily growth |
|-----------|--------------|-----------------|--------------|
| Database dump | ~10 MB (compressed) | +100-500 ads/day | +0.5-2 MB |
| Media files | ~1-3 MB avg | +50-200 photos/day | 50-600 MB |
| Thumbnails | ~200 KB | 3x photos | ~30 MB |

### 9.2 Storage Planning

| Retention | Database | Media | Total |
|-----------|----------|-------|-------|
| Daily (7 days) | 70 MB | 350 GB | ~350 GB |
| Weekly (4 weeks) | 40 MB | 1.4 TB | ~1.4 TB |
| Monthly (12 months) | 120 MB | 18 TB | **~18 TB** |

**Recommendation:** Использовать deduplicated backup storage или S3 lifecycle policies.

---

## 10. Security Considerations for Backup

| Risk | Mitigation |
|------|------------|
| **Plaintext DB dump contains user PII** | Encrypt at rest, secure access to backup location |
| **DJANGO_SECRET_KEY in backup environment** | Separate secrets management (HashiCorp Vault, Doppler) |
| **.env.docker in repository** | Use .env.docker.example + environment secrets |
| **Media files have no PII** | Only UUID-based keys, safe for cloud storage |

---

## Appendix: File References

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Main services definition |
| `docker-compose.prod.yml` | Production overrides + backup profile |
| `Dockerfile` | Build/runtime configuration |
| `Makefile` | Backup/restore targets |
| `docs/ops/restore.md` | Restore runbook |
| `docs/ops/docker-deployment.md` | Deployment documentation |
| `docs/02-database/db-schema.md` | Full schema reference |
| `src/backend/apps/*/models.py` | ORM model definitions |