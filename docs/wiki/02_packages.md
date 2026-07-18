
*  Django + PostgreSQL
*  Django Admin 
*  Filtration: django-filter, django-mptt
*  Search: PostgreSQL native FTS (search_vector TSVECTOR + GIN + pg_trgm, russian config)
*  API: Django Templates + HTMX + Alpine.js MPA for phase 1
*  Telegram bot (phase 1): aiogram 3.x — Bot API bot for login/contact/publish (needs @bot_username + t.me deep links; free built-in FSM for the US-S2 dialog). Telethon is NOT used in phase 1.
*  Background jobs: Django management commands + systemd timer / cron (Celery + Redis deferred)
*  **Асинхронный бот + синхронный Django ORM (зона C5):** бот запускает `django.setup()` и использует общий ORM. Блокирующие ORM-вызовы и скачивание фото Telegram оборачиваются в `sync_to_async` (thread-sensitivity по умолчанию для ORM). Каждый процесс держит СВОЙ пул psycopg3 (`CONN_MAX_AGE=0`); рекомендуется общий PgBouncer (transaction mode) как внешний пул. Миграции запускаются один раз до старта обоих процессов (см. 03_structure.md).
*  Query translation: deep-translator (Bosnian -> Russian at search time; твёрдый timeout ~500ms + fallback на оригинальный запрос против GIN `search_vector`, зона C7/D5)

```
# Core / Web
django==5.1.2                    

# Database / Drivers
psycopg[binary]>=3.2.0            # psycopg 3 (Django 5.1+ native support; connection pooling requires psycopg 3). Replaces psycopg2-binary.

# Authentication
# Login by Telegram: site issues LoginToken (random, TTL 5min), bot sets telegram_id via shared ORM
# on /start login_<token>. See docs/wiki/01_technical_specification.md decision H / US-S1.
# django-allauth is intentionally NOT used (no OAuth/social flow in phase 1).

# Environment handling
django-environ>=0.11.0            # Typed .env casting (env.bool, env.db, env.int) — prevents "False"→True string bugs.
                                 # python-dotenv becomes a transitive dependency.

# Models / Utils
django-mptt==0.16.0               # Древовидные категории
django-filter==24.3               # Фильтры в списках / API


# Search
# Native PostgreSQL full-text search (no external engine). No django-haystack / Whoosh.

# API 
# djangorestframework==3.15.2  # DEFERRED to post-MVP (HTMX MPA in phase 1)


# Telegram integration (phase 1)
aiogram>=3.15.0                  # Bot API bot: login (decision H/Z25), contact (decision C), seller publish dialog (US-S2).
                                 # Free built-in FSM + PostgreSQL SQLStorage (validated Z05/Z09) keeps the US-S2 step-by-step
                                 # dialog simple. Telethon CAN also run a bot account (bot-token login, serves deep links),
                                 # but it has NO built-in FSM — implementing our dialog would be custom ORM code. Per owner
                                 # rule, if the bot is harder in Telethon we use aiogram. => aiogram for phase 1.
                                 # Group-scraping userbot (Telethon) is a SEPARATE future phase-2 service (decision B).

# Query translation (decision G: Bosnian query -> Russian)
deep-translator>=1.11.0


# Tasks 
# celery==5.4.0 / redis==5.1.1  # DEFERRED to post-MVP.
# Phase-1 scheduled jobs (archive@2mo, delete@4mo, 7-day purge, 30-day consent hard-delete,
# 30-min draft sweep) run as Django management commands via systemd timer / cron.


# Frontend / Styling 
django-tailwind==4.4.2            # Tailwind CSS + daisyUI; standalone CLI mode needs NO Node.js (npm mode needs Node only at CSS build time; runtime needs NO Node)
django-htmx==1.19.0               


# Images / Media
django-storages==1.14.4            # storage abstraction: local MEDIA_ROOT (phase 1) -> S3/R2/MinIO later via DEFAULT_FILE_STORAGE
boto3==1.35.0                     # for later S3/R2 swap (not used in phase 1)
pillow>=10.4.0                    # image handling (download from Telegram, later thumbnails)                    

# Analytics
# Web analytics: Plausible (cookieless, EU-hosted SaaS, ~$9/mo for 10k pageviews) — JS snippet only, NO Python dep.
# Fallback: self-host Plausible CE / Umami via Docker. Product metrics = internal AnalyticsEvent model (see spec decision L).

# Testing / Dev tools
pytest==8.3.3                     # Тесты
pytest-django==4.9.0              # Django fixtures / client для pytest
pytest-factoryboy==2.7.0          # Фабрики моделей


# Linting / Formatting 
ruff==0.9.0                       

```

