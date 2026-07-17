## Принципы
- Одна таблица объявлений
- Дерево категорий
- Атрибуты зависят от категории
- Теги — вспомогательные
- Поиск — отдельный слой
- Пользователь — единый, с Telegram
- Один пользователь = один Telegram-аккаунт

### Основные таблицы и связи (верхний уровень)

```
users
 └── ads
      ├── categories
      │     └── category_attributes
      │           └── ad_attribute_values
      ├── cities
      ├── ad_tags
      │     └── tags
      └── ad_images
```
---

### users — пользователи

```
users
├── id (PK)
├── telegram_id (BIGINT, UNIQUE)
├── phone (VARCHAR)
├── username (VARCHAR)
├── is_verified (BOOL)
├── created_at (TIMESTAMP)
```

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
├── status (draft | active | blocked | archived)
├── source (web | telegram)
├── created_at
├── updated_at
├── published_at
├── currency (VARCHAR(3) DEFAULT 'EUR')
├── search_vector (TSVECTOR)
```

### categories — категории (дерево)
```
categories
├── id (PK)
├── name (VARCHAR)
├── slug (VARCHAR)
├── parent_id (FK → categories.id, NULL)
├── path (VARCHAR) # electronics.phones.apple
├── level (INT) # 0 / 1 / 2 / 3
├── is_active (BOOL)
```
path — очень важно для фильтрации


### category_attributes — атрибуты категории, «какие поля должны быть у объявлений ЭТОЙ категории»
```
category_attributes
├── id (PK)
├── category_id (FK → categories.id)
├── name (VARCHAR) # площадь, год, пробег
├── slug (VARCHAR)
├── type (int | bool | str | choice)
├── is_required (BOOL)
├── choices (JSONB, nullable)
```

Примеры:
- квартира → площадь, этаж  
- авто → год, пробег  
- услуги → формат работы  


### ad_attribute_values
 — значения атрибутов объявления
```
ad_attribute_values
├── id (PK)
├── ad_id (FK → ads.id)
├── attribute_id (FK → category_attributes.id)
├── value_int (INT, nullable)
├── value_str (VARCHAR, nullable)
├── value_bool (BOOL, nullable)
```

### tags — теги (семантика)
```
tags
├── id (PK)
├── name (VARCHAR)
├── normalized (VARCHAR)
```

Примеры:
iphone, айфон, apple, ремонт, срочно



### ad_tags
 — связь объявлений и тегов
```
ad_tags
├── ad_id (FK → ads.id)
├── tag_id (FK → tags.id)
```

- Связь: Many-to-Many
- Чаще **автоматические**, не пользовательские


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
 — изображения

```
ad_images
├── id (PK)
├── ad_id (FK → ads.id)
├── image (FILE / URL)
├── position (INT)
```

### Поиск (логика, не таблица)
Используется:
- `search_vector` в `ads`
- `GIN index`
- `pg_trgm` для опечаток

Поисковое наполнение:
title + description + tags + category.namez