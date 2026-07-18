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

> **Таблица `login_tokens` (решение H / US-S1, зона C1):** отдельная таблица для атомарного входа через Telegram.
> Бот и веб — ДВА отдельных процесса; токен должен быть заявлен ровно один раз под общим блокированием.
> ```
> login_tokens
> ├── id (PK)
> ├── token_hash (CHAR(64) UNIQUE, indexed)   # SHA-256 от сырого 32-символьного URL-safe токена; сырой токен НИКОГДА не хранится
> ├── telegram_id (BIGINT, nullable)          # заполняет БОТ при /start login_<token>
> ├── created_at (TIMESTAMP)
> ├── expires_at (TIMESTAMP)                  # +5 минут от создания
> └── consumed_at (TIMESTAMP, nullable)       # заполняет ВЕБ при завершении входа
> ```
> **Двухфазный атомарный claim (каждый — один UPDATE под транзакцией):**
> 1. Бот: `UPDATE login_tokens SET telegram_id=<tg> WHERE token_hash=? AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now()`
> 2. Веб: `UPDATE login_tokens SET consumed_at=now() WHERE token_hash=? AND telegram_id IS NOT NULL AND consumed_at IS NULL AND expires_at > now()`
> Оба проверяют `expires_at > now()`; сравнение токена — `hmac.compare_digest` (константное время). Сырой токен передаётся только в QR/deep-link.
> Фоновая задача удаляет просроченные/потреблённые токены. Сессионные cookie: `SECURE` + `HTTPONLY` + `SAMESITE=Lax`.
> SQL-формы выше гарантируют, что ровно один claim побеждает (условие `telegram_id IS NULL` / `IS NOT NULL`).

> Поля `phone` и `is_verified` из ранней версии — УДАЛЕНЫ: собираем минимум
> (`telegram_id`, опц. `username`) по решению F. `is_verified` в спеке не используется.

### ads — объявления (ЕДИНАЯ таблица)

```
ads
├── id (PK)
├── user_id (FK → users.id)
├── title (VARCHAR)
├── description (TEXT)
├── price (INT, nullable)                 # BAM whole units; multi-currency deferred to post-MVP (D11: столбец `currency` УДАЛЁН — YAGNI, единая валюта BAM в фазе 1)
├── category_id (FK → categories.id)
├── city_id (FK → cities.id)
├── category_name (VARCHAR, editable=False)  # зона D1 (hybrid C, O5 RESOLVED): денормализованное РУССКОЕ имя категории (из categories.name на момент назначения); синхронизируется триггером; входит в search_vector (вес 'C')
├── status (TextChoices, см. AdStatus ниже)
├── source (TextChoices: TELEGRAM)         # фаза 1 — только бот (решение B); web-источника нет
├── created_at
├── updated_at
├── published_at (TIMESTAMP, nullable)     # базовая линия таймеров архива/удаления; ОБНОВЛЯЕТСЯ при каждом переходе PUBLISHED (сброс таймера, решение J / зона C3)
├── original_published_at (TIMESTAMP, nullable)  # фиксируется один раз при ПЕРВОЙ публикации; ИММУТАБЕЛЬНО, только для аудита (НЕ драйвит sweep)
├── archived_at (TIMESTAMP, nullable)
├── deleted_at (TIMESTAMP, nullable)
├── moderation_failed_at (TIMESTAMP, nullable)   # зона C4/D12: заполняется при переходе ON_MODERATION → ON_MODERATION_FAILED; НЕ-NULL драйвит 7-дневный purge. Взаимоисключающе с rejected_at
├── rejected_at (TIMESTAMP, nullable)            # зона D4: заполняется при ручном переходе в REJECTED; драйвит очистку REJECTED через 90 дней. Взаимоисключающе с moderation_failed_at
├── search_vector (TSVECTOR)                 # НЕ GENERATED ALWAYS — обслуживается триггером (нужен FK-lookup category_name). См. «Триггеры search_vector» ниже
├── published_by (FK → users.id, nullable, SET_NULL)  # модератор, вручную перевёл в PUBLISHED (NULL = авто-публикация/бот)
└── moderated_by (FK → users.id, nullable, SET_NULL)  # модератор, вручную перевёл в REJECTED (NULL = авто-отклонение)
```

> **`search_vector` (зона D1, hybrid C):** `setweight(to_tsvector('russian', title),'A') || setweight(to_tsvector('russian', description),'B') || setweight(to_tsvector('russian', category_name),'C')`. Колонка `category_name` денормализована с `categories.name` (русский, базовый язык) и синхронизируется триггерами (см. ниже) — поэтому НЕ может быть `GENERATED ALWAYS` (нужен FK-lookup в момент записи). GIN-индекс `IX_ads_search_gin` поверх. Код пишет title/description/category_id, триггер заполняет `category_name` + `search_vector`. Боснийский запрос переводится в русский ДО поиска (решение G), поэтому матчит русское имя категории.
> Поиск по категории работает ДВУМЯ путями: (1) FTS матчит слово-категорию через `category_name` в `search_vector`; (2) на уровне приложения fuzzy-детект (difflib, как для городов) применяет явный фильтр `category_id`, когда запрос — одно слово, похожее на имя категории. Оба пути покрывают требование «ввод 'телефоны' → матчит категорию Телефоны».
> `published_at` — **драйвит** таймеры архива (2 мес) и удаления (4 мес) из решения J: обновляется при КАЖДОМ переходе в `PUBLISHED` (вкл. реактивацию и правки цены/фото).
> `original_published_at` — иммутабельная АУДИТ-метка (фиксируется один раз при первой публикации), нигде не читается sweep'ом.
> `moderation_failed_at` и `rejected_at` взаимоисключающие: авто-сбой заполняет первое (оно же драйвит 7-дневный purge), ручной REJECT — второе (90 дней).
> Имя категории входит в `search_vector` через денормализованную колонку `category_name` (см. выше, зона D1).
>
> `published_by` / `moderated_by` — дополняют `ModeratorActionLog` (который хранит причины/историю по US-A11),
> давая быстрый указатель «кто последним модерировал». `updated_at` покрывает время действия.

AdStatus (Django TextChoices / StrEnum, rule 10):
- `DRAFT` — черновик бота, не отправлен
- `ON_MODERATION` — ожидает автопроверку (скрыто)
- `PUBLISHED` — опубликовано (единственный видимый покупателю статус)
- `REJECTED` — отклонено модератором вручную (хранится до 90 дней, затем purge; зона D4)
- `ON_MODERATION_FAILED` — не прошло автопроверку (очистка через 7 дней по `moderation_failed_at`, решение A / зона C4)
- `ARCHIVED` — авто-архив (2 мес) / ручной архив
- `DELETED` — мягкое удаление

Переходы:
- DRAFT → ON_MODERATION
- ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED
- PUBLISHED → ARCHIVED → PUBLISHED (реактивация, повторная модерация текста)
- PUBLISHED → ON_MODERATION (зона C2: только текстовые правки заголовка/описания; объявление НЕМЕДЛЕННО скрывается с публичного сайта; цена/фото правятся сразу без этой ветки; смешанная правка следует правилу текста)
- любой → DELETED

### categories — категории (дерево)
```
categories
├── id (PK)
├── name (VARCHAR)                       # русское имя (базовый язык хранения)
├── name_i18n (JSONB, nullable)         # зона D2: {"ru": <str>, "bs": <str>}; боснийское имя для UI; NULL → fallback на `name` (русский)
├── slug (VARCHAR)
├── parent_id (FK → categories.id, NULL)
└── is_active (BOOL)
```
Реализация — **django-mptt** (единственный источник истины: `lft`/`rght`/`tree_id`/`level`).
Денормализованные `path` / `level` колонки НЕ храним (риск рассинхрона, решение — mptt).
Фильтрация по поддереву — через `get_descendants()`. Имя для UI берётся `get_name(locale)` с русским fallback (боснийский — только в UI-оболочке). Русское `name` денормализуется в `ads.category_name` и индексируется в `search_vector` (зона D1, hybrid C) — поиск по слову-категории работает.

### cities — города
```
cities
├── id (PK)
├── country_code
├── name (VARCHAR)                       # русское имя (базовый язык хранения)
├── name_i18n (JSONB, nullable)         # зона D2: {"ru": <str>, "bs": <str>}; боснийское имя для UI; NULL → fallback на `name`
├── region (VARCHAR)
└── slug (VARCHAR)
```

Структура EAV (`category_attributes`, `ad_attribute_values`) отложена до появления
реального требования (атрибутивного фильтра) в спеке. В фазе 1 объявление использует
только плоские поля (title, description, price, category, city, images).

### tags / ad_tags — DEFERRED (вне scope фазы 1)

Теги (`tags`, `ad_tags`) отложены: в спеке нет источника их генерации (авто-тегирование
не описано), поиск ограничен title + description (US-B2). Добавляются в post-MVP при
появлении кейса.


### ad_images
├── id (PK)
├── ad_id (FK → ads.id)
├── image (VARCHAR / storage key)   # отдаваемый URL фото (наш storage: MEDIA_ROOT или S3/R2 через django-storages). Ключ НЕ содержит user_id/telegram_id/username — только ad_id + UUID v4 (зона R6: анонимность по URL)
├── telegram_file_id (VARCHAR, nullable)  # метаданные для дедупа/повторной выкачки, НЕ используется в <img src>
└── position (INT)
```

> Принимаются только сжатые Telegram-фото (`message.photo`); `message.document` отклоняется.
> Бот скачивает байты фото (getFile/download) и сохраняет в НАШ storage; в `image` хранится отдаваемый URL/ключ.
> `file_id` НЕ является URL и НЕ помещается в `<img src>` — храним только как метаданные (`telegram_file_id`).
> **Зона R8 (валидация на границе storage):** формат JPEG проверяется СТРОГО (magic bytes / PIL) при сохранении; не-JPEG отклоняется с 415. Ключ генерируется как UUID v4 (неугадываемый, не sequential). nginx `/media/` ставит `X-Content-Type-Options: nosniff`, whitelist `image/jpeg`, default `application/octet-stream`, `Content-Disposition: inline` (см. 03_structure.md).

### analytics_events — события аналитики (решение L)
```
analytics_events
├── id (PK)
├── event_type (TextChoices/StrEnum: REGISTRATION_CREATED, AD_PUBLISHED, SEARCH_PERFORMED, CONTACT_INITIATED)
├── timestamp (TIMESTAMP, default now)
├── user_id (FK → users.id, nullable)   # только для авторизованных действий (telegram_id уже собран по решению F). При отзове согласия/мягком удалении → SET NULL (сохраняем агрегаты, зона R1/R5)
```
> Считаются агрегацией ORM (`.filter(event_type=..., timestamp__date=...).count()`). Доступ — админ/CLI `show_metrics`.
> PII не добавляется сверх уже собранного `telegram_id`.

### Поиск (логика, не таблица)
Используется:
- `search_vector` в `ads` (обслуживается триггером, см. ниже; включает title + description + category_name)
- `GIN index` на `search_vector` (`IX_ads_search_gin`)
- `pg_trgm` для опечаток (опционально)
- на уровне приложения — fuzzy-детект категории (difflib) → фильтр `category_id` (зона D1)

Поисковое наполнение (search_vector, `to_tsvector('russian', ...)`):
**title (вес A) + description (вес B) + category_name (вес C)**. Имя категории денормализовано в `ads.category_name` (русский, из `categories.name`), поэтому входит в FTS-вектор без JOIN. Боснийский запрос переводится в русский ДО поиска (решение G) — матчит русское имя категории. При необходимости результаты помечаются «переведено с русского».

### Триггеры `search_vector` (зона D1, sync-safety)
Поскольку `search_vector` теперь включает имя категории (другая таблица), колонка НЕ может быть `GENERATED ALWAYS` — её наполняет plpgsql-триггер. Вся логика вычисления вынесена в ОДНУ функцию, чтобы INSERT и UPDATE пути не расходились.
```sql
-- 1. Единая функция пересчёта (используется обоими триггерами)
CREATE OR REPLACE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
DECLARE v_cat TEXT;
BEGIN
  SELECT name INTO v_cat FROM categories WHERE id = NEW.category_id;
  NEW.category_name := v_cat;
  NEW.search_vector :=
    setweight(to_tsvector('russian', coalesce(NEW.title,'')), 'A') ||
    setweight(to_tsvector('russian', coalesce(NEW.description,'')), 'B') ||
    setweight(to_tsvector('russian', coalesce(v_cat,'')), 'C');
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

-- 2. На ads: пересчёт при INSERT/UPDATE (вкл. смену category_id)
CREATE TRIGGER ads_search_vector_update
  BEFORE INSERT OR UPDATE ON ads
  FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn();

-- 3. На categories: при переименовании категории пропагируем в ads
CREATE OR REPLACE FUNCTION categories_name_propagate() RETURNS TRIGGER AS $$
BEGIN
  UPDATE ads SET category_id = ads.category_id  -- триггер #2 пересчитает category_name+search_vector
  WHERE category_id = NEW.id;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER on_category_name_update
  AFTER UPDATE OF name ON categories
  FOR EACH ROW EXECUTE FUNCTION categories_name_propagate();
```
> Миграция: одноразовый `UPDATE ads SET category_id = category_id` (или backfill-скрипт) для заполнения `category_name`+`search_vector` у существующих строк; O(n_ads) на переименование категории — приемлемо для ~30-50 категорий. mptt-дерево не затрагивается (только чтение `name`).

### Индексы `ads`
```python
# Django indexes (в Meta.indexes модели Ad):
models.Index(
    name='IX_ads_pub_listing',
    fields=['status', 'category_id', 'city_id', '-published_at'],
    condition=Q(status=AdStatus.PUBLISHED),   # partial: покрывает ~99% публичных чтений
)
models.Index(name='IX_ads_user_status', fields=['user_id', 'status'])   # объявления продавца / фильтр админа
GinIndex(name='IX_ads_search_gin', fields=['search_vector'])           # зона D12: НАСТОЯЩИЙ GIN на TSVECTOR (НЕ models.Index — тот создал бы BTREE)
# Таймеры жизненного цикла — три частичных индекса (зона C4):
models.Index(name='IX_ads_archive_sweep', fields=['status', 'published_at'],
             condition=Q(status=AdStatus.PUBLISHED))                    # архив @2мес
models.Index(name='IX_ads_delete_sweep', fields=['status', 'published_at'],
             condition=Q(status=AdStatus.ARCHIVED))                     # удаление @4мес
models.Index(name='IX_ads_purge_failed', fields=['status', 'moderation_failed_at'],
             condition=Q(status=AdStatus.ON_MODERATION_FAILED))         # 7-дневный purge авто-сбоя
models.Index(name='IX_ads_rejected_sweep', fields=['status', 'rejected_at'],
             condition=Q(status=AdStatus.REJECTED))                     # очистка REJECTED @90дней (зона D4)
```
> Стендэлон-индексы на `status` / `category_id` / `city_id` не нужны — покрываются композитными.
> `price` без отдельного индекса (редкий фильтр в фазе 1; добавить ТОЛЬКО после EXPLAIN ANALYZE на 500k, зона C7).
> `IX_ads_sweep` (единый) УДАЛЁН — заменён тремя частичными выше. `IX_ads_consent_sweep` перенесён на users (см. ниже).

### Индексы `users`
```python
models.Index(name='IX_users_erasure_sweep', fields=['consent_revoked_at'])  # зона R1: idempotent sweep hard-delete через 30 дней после отзыва согласия
```

> Теги исключены (DEFERRED). Город — точное совпадение по списку; did-you-mean через
> `difflib.get_close_matches` (решение G, только города — НЕ категории, зона D1), `pg_trgm` — опционально для общей нечёткости.

---

### moderation_criteria — критерии модерации (зона D3/D4, US-A11, O4 RESOLVED)
Singleton-таблица (ровно одна активная строка), редактируется админом в рантайме. Применяется к НОВЫМ объявлениям (читаем текущую строку в момент submit; пер-объявленного `criteria_version` НЕ нужно).

**Слой 1 — АВТОМАТИЧЕСКАЯ проверка (бот/API, синхронно при submit, решение A / US-A10):**
```
moderation_criteria
├── id (PK)
├── title_min_length (INT, default 5)          # мин. длина заголовка
├── title_max_length (INT, default 100)        # макс. длина заголовка (против спама)
├── description_min_length (INT, default 10)   # мин. длина описания
├── description_max_length (INT, default 2000) # макс. длина описания (против спама)
├── price_required (BOOL, default TRUE)        # цена ОБЯЗАТЕЛЬНА (отсутствие обязательных полей блокирует публикацию)
├── min_images (INT, default 1)                # мин. кол-во фото (≥1 обязательно)
├── max_images (INT, default 5)                # макс. кол-во фото (1..5)
├── banned_words (JSONB, default [])          # запрещённые слова/фразы (case-insensitive)
├── max_ads_per_user (INT, default 10)        # макс. активных объявлений на пользователя
├── duplicate_title_threshold (INT, default 85) # % схожести заголовка для детекта дублей-спама (0..100)
├── updated_at (TIMESTAMP)
└── updated_by (FK → users.id, nullable, SET_NULL)  # кто последним менял
```
> Поле `min_text_length` (старое суммарное) **УДАЛЕНО** — дублируется отдельными `title_min_length`/`description_min_length`.
> Хранится в БД (НЕ settings.py) — иначе не редактируется в рантайме по US-A11.

**Слой 2 — РУЧНАЯ модерация администратором (фото и запрещённый контент, US-A11):**
Админ проверяет **картинки** на запрещённый контент (в будущем — ML/OCR автоматизация). Это чек-лист админа + основа будущего ML, НЕ поля таблицы `moderation_criteria`. Категории запрещённого контента:
- `adult_content` — обнажённые, сексуальный контент
- `violence_gore` — оружие, кровь, насилие
- `drugs_weapons` — наркотики, огнестрельное
- `hate_speech` — ненавистническая символика/речь
- `counterfeit_goods` — подделки брендов
- `illegal_goods` — запрещённые товары
- `spam_scam` — мошеннические паттерны, подозрительные цены
- `off_topic` — не та категория, не по теме
> Результат ручной модерации фиксируется в `ModeratorActionLog` (причина — одна из категорий выше; НЕ показывается продавцу) + статус `REJECTED` / `ON_MODERATION_FAILED`.

### ModeratorActionLog — журнал действий модератора (зона D8, US-A11)
```
ModeratorActionLog
├── id (PK)
├── ad_id (FK → ads.id, nullable, SET_NULL)     # объявление, к которому относится действие
├── user_id (FK → users.id, nullable, SET_NULL) # модератор/админ (NULL после erasure, зона R1 — сохраняем reason/admin/timestamp)
├── action_type (StrEnum: REJECT, BAN_ACCOUNT, SOFT_DELETE, CRITERIA_CHANGE, OTHER)
├── reason (TEXT)                               # причина отклонения; НИКОГДА не показывается продавцу (US-A11)
└── created_at (TIMESTAMP, default now)
```
> `published_by` / `moderated_by` в `ads` дублируют «кто последним»; NULL означает авто-действие (бот/автопроверка). Лог — постоянный, не purge'ится вместе с объявлением (хранится для аудита; при erasure пользователя — `user_id` SET NULL, текст причины сохраняется).