## Принципы
- Одна таблица объявлений
- Дерево категорий (django-mptt — единственный источник истины, без денормализованных path/level)
- Атрибуты зависят от категории — DEFERRED (EAV вне scope фазы 1, плоские поля объявления)
- Теги — DEFERRED (нет источника генерации в фазе 1)
- Поиск — нативный PostgreSQL FTS (search_vector TSVECTOR + GIN + pg_trgm, russian config)
- Пользователь — единый, с Telegram
- Один пользователь = один Telegram-аккаунт

### Основные таблицы и связи (верхний уровень)

```
users
 └── ads
      ├── categories
      ├── cities
      └── ad_images
```

> Примечание: `category_attributes` / `ad_attribute_values` и `tags` / `ad_tags` вынесены
> за пределы фазы 1 (см. ниже).
---

### users — пользователи

```
users
├── id (PK)
├── telegram_id (BIGINT, UNIQUE, nullable)  # nullable для аккаунтов, созданных админом
├── username (VARCHAR, nullable)            # публичный @username Telegram (ОПЦИОНАЛЬНО; НЕ используется для t.me-ссылки или публикации — см. решение C)
├── is_staff / is_superuser                 # роль администратора/модератора (решение A) — от AbstractUser
├── is_banned (BOOL)                        # блокировка аккаунта (US-A4)
├── is_deleted (BOOL)                       # мягкое удаление (US-S8)
├── ads_auto_publish (BOOL, default True)   # запрет размещения (US-S9)
├── deleted_at (TIMESTAMP, nullable)
├── consent_given_at (TIMESTAMP, nullable)  # US-A8 / решение F
├── consent_revoked_at (TIMESTAMP, nullable)
├── hard_delete_at (TIMESTAMP, nullable)    # obнуление telegram_id через 30 дней после отзыва согласия
└── created_at (TIMESTAMP)
```

> Поля `phone` и `is_verified` из ранней версии — УДАЛЕНЫ: собираем минимум
> (`telegram_id`, опц. `username`) по решению F. `is_verified` в спеке не используется.

### ads — объявления (ЕДИНАЯ таблица)

```
ads
├── id (PK)
├── user_id (FK → users.id)
├── title (VARCHAR)
├── description (TEXT)
├── price (INT, nullable)
├── category_id (FK → categories.id)
├── city_id (FK → cities.id)
├── status (TextChoices, см. AdStatus ниже)
├── source (TextChoices: TELEGRAM)         # фаза 1 — только бот (решение B); web-источника нет
├── created_at
├── updated_at
├── published_at
├── original_published_at (TIMESTAMP, nullable)  # фиксируется один раз при первой публикации
├── archived_at (TIMESTAMP, nullable)
├── deleted_at (TIMESTAMP, nullable)
├── currency (VARCHAR(3) DEFAULT 'BAM')     # Босния и Герцеговина (решение D/G); единая валюта в фазе 1
├── search_vector (TSVECTOR)
```

AdStatus (Django TextChoices / StrEnum, rule 10):
- `DRAFT` — черновик бота, не отправлен
- `ON_MODERATION` — ожидает автопроверку (скрыто)
- `PUBLISHED` — опубликовано (единственный видимый покупателю статус)
- `REJECTED` — отклонено модератором (дольше хранится)
- `ON_MODERATION_FAILED` — не прошло автопроверку (очистка через 7 дней, решение A)
- `ARCHIVED` — авто-архив (2 мес) / ручной архив
- `DELETED` — мягкое удаление

Переходы:
- DRAFT → ON_MODERATION
- ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED
- PUBLISHED → ARCHIVED → PUBLISHED (реактивация, повторная модерация текста)
- любой → DELETED

### categories — категории (дерево)
```
categories
├── id (PK)
├── name (VARCHAR)
├── slug (VARCHAR)
├── parent_id (FK → categories.id, NULL)
└── is_active (BOOL)
```
Реализация — **django-mptt** (единственный источник истины: `lft`/`rght`/`tree_id`/`level`).
Денормализованные `path` / `level` колонки НЕ храним (риск рассинхрона, решение — mptt).
Фильтрация по поддереву — через `get_descendants()`.


### category_attributes / ad_attribute_values — DEFERRED (вне scope фазы 1)

Структура EAV (`category_attributes`, `ad_attribute_values`) отложена до появления
реального требования (атрибутивного фильтра) в спеке. В фазе 1 объявление использует
только плоские поля (title, description, price, category, city, images).

### tags / ad_tags — DEFERRED (вне scope фазы 1)

Теги (`tags`, `ad_tags`) отложены: в спеке нет источника их генерации (авто-тегирование
не описано), поиск ограничен title + description (US-B2). Добавляются в post-MVP при
появлении кейса.


### cities
 — города
```
cities
├── id (PK)
├── country_code
├── name (VARCHAR)
├── region (VARCHAR)
├── slug (VARCHAR)
```

### ad_images
├── id (PK)
├── ad_id (FK → ads.id)
├── image (VARCHAR / storage key)   # отдаваемый URL фото (наш storage: MEDIA_ROOT или S3/R2 через django-storages)
├── telegram_file_id (VARCHAR, nullable)  # метаданные для дедупа/повторной выкачки, НЕ используется в <img src>
└── position (INT)
```

> Принимаются только сжатые Telegram-фото (`message.photo`); `message.document` отклоняется.
> Бот скачивает байты фото (getFile/download) и сохраняет в НАШ storage; в `image` хранится отдаваемый URL/ключ.
> `file_id` НЕ является URL и НЕ помещается в `<img src>` — храним только как метаданные (`telegram_file_id`).

### Поиск (логика, не таблица)
Используется:
- `search_vector` в `ads`
- `GIN index`
- `pg_trgm` для опечаток

Поисковое наполнение (search_vector, `to_tsvector('russian', ...)`):
title + description + category.name

> Теги исключены (DEFERRED). Город — точное совпадение по списку; did-you-mean через
> `difflib.get_close_matches` (решение G), `pg_trgm` — опционально для общей нечёткости.