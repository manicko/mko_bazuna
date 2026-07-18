Structure:

```
mko_bazuna/                        # корень репозитория
├── src/                           # всё исходники здесь (современный подход, удобно с uv/poetry)
│   ├── backend/                   # основной Django-проект
│   │   ├── config/                # проектные настройки
│   │   │   ├── settings.py
│   │   │   ├── urls.py
│   │   │   ├── asgi.py
│   │   │   └── wsgi.py
│   │   │
│   │   ├── apps/                  # все приложения (INSTALLED_APPS = ['apps.xxx'])
│   │   │   ├── core/              # общие утилиты, абстрактные модели, миксины, сигналы
│   │   │   │   ├── models.py
│   │   │   │   ├── managers.py
│   │   │   │   ├── utils/
│   │   │   │   └── __init__.py
│   │   │   │
│   │   │   ├── users/             # пользователи, OTP-авторизация (telegram_id), telegram-binding
│   │   │   ├── ads/               # объявления, фото, статусы
│   │   │   ├── categories/        # mptt-дерево категорий (django-mptt — единственный источник истины; без отдельных path/level колонок)
│   │   │   ├── locations/         # города / регионы
│   │   │   ├── moderation/        # логи модерации, правила, статусы
│   │   │   ├── search/            # PostgreSQL FTS (search_vector, GIN, russian config) — haystack/whoosh НЕ используется
│   │   │   └── api/               # DRF API — DEFERRED to post-MVP (phase 1 = HTMX MPA, см. decision B)
│   │   │       ├── serializers/
│   │   │       ├── views/
│   │   │       └── urls.py
│   │   │
│   │   └── manage.py
│   │
│   └── telegram_bot/              # отдельный entrypoint; запускает django.setup() и использует общие Django-модели/ORM (см. 05_integration)
│       ├── bot/                   # aiogram 3.x handlers, FSM, middlewares — Bot API бот (login/contact/publish).
│       │                         #   НЕ userbot. Telethon мог бы вести бота (bot-token login, deep-link работают), но у
│       │                         #   Telethon НЕТ встроенного FSM — диалог US-S2 пришлось бы писать вручную. По правилу
│       │                         #   владельца (если бот в Telethon сложнее -> aiogram) выбран aiogram.
│       │   ├── handlers/
│       │   ├── states/
│       │   ├── filters/
│       │   └── __init__.py
│       ├── parsers/               # DEFERRED to phase 2 (мониторинг групп вне scope фазы 1, решение B).
│       │                         #   В фазе 2 реализуется КАК ОТДЕЛЬНЫЙ Telethon userbot-сервис (см. ниже scraping_service),
│       │                         #   не внутри этого Bot API бота. Telethon здесь обязателен (userbot = phone-login), и его
│       │                         #   отсутствие FSM не мешает скрапингу.
│       ├── services/              # бизнес-логика (create_ad_from_message и т.д.)
│       ├── config.py              # настройки бота + django settings wrapper
│       └── main.py                # запуск бота
│
└── scraping_service/             # DEFERRED to phase 2 (решение B). Отдельный процесс: Telethon userbot (MTProto,
                                  #   phone-login), сидит в чужих группах, собирает объявления и пишет через django.setup()+ORM.
                                  #   Telethon выбран потому что скрапинг требует userbot (бот-аккаунт не может читать чужие группы),
                                  #   а не потому что он лучше для бота — для бота (фаза 1) оставлен aiogram (см. правило владельца).
│
├── templates/                     # глобальные шаблоны (если нужно)
│   ├── base.html
│   └── includes/
│
├── static/                        # глобальные статики (если не в apps)
│   ├── css/
│   ├── js/
│   └── img/
│
├── media/                         # Phase 1 storage: локальный MEDIA_ROOT (Docker volume `media_volume`) за nginx, завёрнут в django-storages
                                  #   (абстракция DEFAULT_FILE_STORAGE) для последующего переключения на S3/R2/MinIO без переписывания кода.
                                  #   Бот скачивает фото из Telegram и кладёт сюда; отдаём через свой <img src>. НЕ Telegram CDN
                                  #   (file_id/URL не помещаются в <img src> и содержат токен бота). nginx отдаёт /media/ напрямую (whitenoise — только /static/).
├── tests/                         # pytest, разделён по apps
├── docs/
├── docker/                        # docker/Dockerfile (python:3.14-slim + uv; non-root USER, RUN collectstatic)
├── .env.example
├── docker-compose.yml             # сервисы: db + web + bot + nginx (см. ниже "Deployment")
├── pyproject.toml                 # или requirements.txt + uv/poetry lock
├── ruff.toml
└── README.md
```

---

## Deployment (Docker, phase 1)

```
docker-compose.yml (root) сервисы:
  db      postgres:17-alpine  + volume postgres_data  + healthcheck (pg_isready)
  web     Django + gunicorn (sync WSGI) из docker/Dockerfile; команда `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers N`  # зона D10: фаза 1 = СИНХРОННЫЙ WSGI (HTMX MPA сервер-рендерится синхронно). `[+UvicornWorker]`/`asgi:application` — НЕ используется в фазе 1 (ASGI зарезервирован для будущего).
          монтирует media_volume:/app/media; env_file: .env; depends_on db (healthy); порт 8000 НЕ публикуется наружу
  bot     тот же образ, команда `python -m telegram_bot.main`; монтирует media_volume; depends_on db; restart: unless-stopped
  nginx   nginx:alpine; порты 80/443; монтирует static_volume (ro) + media_volume (ro); proxy_pass → web:8000;
          отдаёт /static/ и /media/ напрямую; TLS (Certbot или host-терминация)

volumes: postgres_data, media_volume, static_volume
```

- **nginx ОБЯЗАТЕЛЕН в фазе 1**: whitenoise НЕ отдаёт user-uploaded media; локальный MEDIA_ROOT требует nginx (или S3).
  Плюс TLS-терминация (HTTPS обязателен: токены входа в deep-link, Secure-куки). web-сервис не торчит наружу.
- **Dockerfile** (`docker/Dockerfile`): `python:3.14-slim` + `uv`; создать non-root пользователя; `RUN uv run python manage.py collectstatic --noinput`.
- **Статические файлы**: whitenoise (в образе) ИЛИ nginx (static_volume). Для медиа — только nginx.
- **Настройки Django**: `USE_X_FORWARDED_HOST = True`, `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')`, `SECURE_SSL_REDIRECT = True`.
- **Безопасность /media/ (зона R8):** в nginx блокировать исполнение скриптов (`location ~* /media/.*\.(php|py|cgi)$ { deny all; }`); плюс:
  - `X-Content-Type-Options: nosniff`;
  - whitelist `image/jpeg`, default `application/octet-stream`;
  - `Content-Disposition: inline`;
  - ключи медиа — UUID v4 (неугадываемые, см. 04_db_structure.md `ad_images`).
- **PgBouncer (рекомендуется, зона C5):** общий внешний пул в transaction mode между web+bot и Postgres; каждый процесс держит `CONN_MAX_AGE=0`.
- **Миграции (зона C5/D7):** запускаются ровно один раз ДО старта web и bot (dedicated step / ordering guard в entrypoint), чтобы два процесса не мигрировали конкурентно. aiogram FSM-таблицы (SQLStorage) — отдельный владелец миграций; доменные записи (ads/LoginToken) пишутся в ОДНУ Django-транзакцию, FSM очищается после успеха (без 2PC).
- **Секреты**: `.env` (BOT_TOKEN, DB, SECRET_KEY) через `env_file: .env`; позже — Docker secrets при оркестрации. `API_ID`/`API_HASH` (MTProto/userbot) в фазе 1 НЕ нужны и из `.env` УДАЛЕНЫ (только aiogram Bot API, см. 02_packages.md, зона R7).