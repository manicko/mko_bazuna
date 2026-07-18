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
├── media/                         # Phase 1 storage: локальный MEDIA_ROOT (Docker volume) за nginx, завёрнут в django-storages
                                  #   (абстракция DEFAULT_FILE_STORAGE) для последующего переключения на S3/R2/MinIO без переписывания кода.
                                  #   Бот скачивает фото из Telegram и кладёт сюда; отдаём через свой <img src>. НЕ Telegram CDN
                                  #   (file_id/URL не помещаются в <img src> и содержат токен бота).
├── tests/                         # pytest, разделён по apps
├── docs/
├── docker/
├── .env.example
├── docker-compose.yml
├── pyproject.toml                 # или requirements.txt + uv/poetry lock
├── ruff.toml
└── README.md
```