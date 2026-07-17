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
│   │   │   ├── users/             # пользователи, allauth, telegram-binding
│   │   │   ├── ads/               # объявления, фото, статусы
│   │   │   ├── categories/        # mptt-дерево категорий
│   │   │   ├── locations/         # города / регионы
│   │   │   ├── moderation/        # логи модерации, правила, статусы
│   │   │   ├── search/            # haystack + whoosh индексация
│   │   │   └── api/               # DRF — общий API (v1), если нужен сразу
│   │   │       ├── serializers/
│   │   │       ├── views/
│   │   │       └── urls.py
│   │   │
│   │   └── manage.py
│   │
│   └── telegram_bot/              # отдельный entrypoint для бота (не django app)
│       ├── bot/                   # aiogram или telethon handlers, FSM, middlewares
│       │   ├── handlers/
│       │   ├── states/
│       │   ├── filters/
│       │   └── __init__.py
│       ├── parsers/               # парсинг сообщений из группы
│       ├── services/              # бизнес-логика (create_ad_from_message и т.д.)
│       ├── config.py              # настройки бота + django settings wrapper
│       └── main.py                # запуск бота
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
├── media/                         # uploaded files (ads photos и т.д.)
├── tests/                         # pytest, разделён по apps
├── docs/
├── docker/
├── .env.example
├── docker-compose.yml
├── pyproject.toml                 # или requirements.txt + uv/poetry lock
├── ruff.toml
└── README.md
```