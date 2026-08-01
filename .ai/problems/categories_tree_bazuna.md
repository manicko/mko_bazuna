# Canonical Category Tree for Mko Bazuna (Базуна)

Based on analysis of Avito category structures, market demand patterns, and the 8 agreed top-level sections.

## Top-level categories (8 fixed)

1. Недвижимость (Real Estate)
2. Транспорт (Transport)
3. Товары (Goods)
4. Животные (Animals)
5. Услуги, работа, вакансии (Jobs, Services)
6. Бизнес (Business)
7. Благотворительность (Charity / Free stuff) — NO MPTT children, auto-populated via CategoryPath when price=0

## Key principles

- Max depth: L1 → L2 → L3 → L4
- Categories answer only "Что является объектом объявления?" (What is the object?)
- Listing purposes and features are stored in LookupGroup tables, NOT in the category tree
- Categories marked [DEFERRED] are excluded from initial launch due to low demand

## Legend

- [DEFERRED] = Low-demand / niche category, deferred to future releases
- (alt path) = Available via CategoryPath (alternative parent route)
- (auto) = Auto-populated based on business rule (e.g., price=0)

---

## TREE STARTING BELOW

```
L0 [root] Все категории (8 subs)
  L1 [1] Недвижимость
    L2 [1] Квартиры (listing_purpose: Продажа, Долгосрочная аренда, Посуточная аренда, listing_feature: Вторичка,  Новостройки)
    L2 [2] Дома, дачи, коттеджи (listing_purpose: Продажа, Долгосрочная аренда, Посуточная аренда, listing_feature: Вторичка,  Новостройки)
    L2 [3] Комнаты (listing_purpose: Продажа, Долгосрочная аренда, Посуточная аренда, listing_feature: Вторичка,  Новостройки)
    L2 [4] Гаражи и машиноместа (listing_purpose: Продажа, Долгосрочная аренда)
    L2 [5] Земельные участки (listing_purpose: Продажа, Долгосрочная аренда)
    L2 [6] Прочая недвижимость (listing_purpose: Продажа, Аренда)
    L2 [7] Коммерческая недвижимость (listing_purpose: Продажа, Аренда)
      L3 [1] Офисы
      L3 [2] Свободного назначения
      L3 [3] Торговые площади
      L3 [4] Склады
      L3 [5] Земельные участки (commercial)
  L1 [2] Транспорт (listing_purpose: Продажа, Аренда)
    L2 [1] Автомобили
    L2 [2] Мотоциклы и мототехника
      L3 [1] Мотоциклы
      L3 [2] Мопеды и скутеры
      L3 [3] Велосипеды
      L3 [4] Самокаты
    L2 [3] Грузовики и спецтехника
      L3 [1] Грузовики
      L3 [2] Сельхозтехника
      L3 [3] Коммерческий транспорт
      L3 [4] Автодома
    L2 [4] Водный транспорт (listing_purpose: Продажа, Аренда)
      L3 [1] Катера и яхты
      L3 [2] Моторные лодки
      L3 [3] Вёсельные лодки
      L3 [4] Гидроциклы
    L2 [5] Запчасти и аксессуары (alt path from Товары.Запчасти, listing_purpose: Продажа)
      L3 [1] Запчасти
      L3 [2] Шины, диски и колёса
      L3 [3] Аксессуары
      L3 [4] Инструменты (alt path)
      L3 [5] Экипировка (alt path)
      L3 [6] Масла и автохимия
      L3 [7] Противоугонные устройства
      L3 [8] GPS-навигаторы
      L3 [9] Аудио- и видеотехника (alt path)
      L3 [10] Багажники и фаркопы
      L3 [11] Прицепы
  L1 [3] Товары  (listing_purpose: Продажа)
    L2 [1] Одежда, обувь, аксессуары
      L3 [1] Женская одежда
      L3 [2] Женская обувь
      L3 [3] Мужская одежда
      L3 [4] Мужская обувь
      L3 [5] Сумки, рюкзаки и чемоданы
      L3 [6] Аксессуары
    L2 [2] Детская одежда и обувь
      L3 [1] Для девочек
      L3 [2] Для мальчиков
    L2 [3] Товары для детей и игрушки
      L3 [1] Игрушки
      L3 [2] Детские коляски
      L3 [3] Автомобильные кресла
      L3 [4] Детская мебель
      L3 [5] Товары для кормления
      L3 [6] Товары для купания
      L3 [7] Товары для школы
      L3 [8] Постельные принадлежности
      L3 [9] Самокаты и велосипеды (детские)
      L3 [10] Детская гигиена
    L2 [4] Красота и здоровье
      L3 [1] Макияж и маникюр
      L3 [2] Парфюмерия
      L3 [3] Уход и гигиена
      L3 [4] Средства для волос
      L3 [5] Приборы и аксессуары
      L3 [6] Медицинские изделия
    L2 [5] Часы и украшения
      L3 [1] Ювелирные изделия
      L3 [2] Часы
      L3 [3] Бижутерия
    L2 [6] Для дома и дачи
      L3 [1] Мебель и интерьер
      L3 [2] Ремонт и строительство
      L3 [3] Бытовая техника
      L3 [4] Продукты питания
      L3 [5] Растения
      L3 [6] Посуда и товары для кухни
    L2 [7] Электроника
      L3 [1] Телефоны
      L3 [2] Аудио и видео
      L3 [3] Компьютеры
      L3 [4] Ноутбуки
      L3 [5] Планшеты
      L3 [6] Фототехника
      L3 [7] Игры, приставки, программы
      L3 [8] Другое
    L2 [8] Хобби и отдых
      L3 [1] Велосипеды (alt path from Транспорт)
      L3 [2] Самокаты (alt path from Транспорт)
      L3 [3] Книги и журналы
      L3 [4] Музыкальные инструменты
      L3 [5] Спорт и отдых
      L3 [6] Билеты и путешествия
      L3 [7] Охота и рыбалка
  L1 [4] Животные (listing_purpose: Продажа, Отдаю, Потеряные, Найденные)
    L2 [1] Собаки
    L2 [2] Кошки
    L2 [3] Птицы
    L2 [4] Рыбы и аквариумные животные
    L2 [5] Другие животные
    L2 [6] Товары для животных
      L3 [1] Корм и сухой корм
      L3 [2] Игрушки для животных
      L3 [3] Аксессуары для животных
      L3 [4] Для собак и кошек
      L3 [5] Для птиц
  L1 [5] Услуги, работа, вакансии (listing_purpose: Ищу работу, Предлагаю работу, Ищу услугу, Предлагаю услугу)
    L2 [1] Ремонт и сервис
      L3 [1] Ремонт телефонов
      L3 [2] Ремонт ноутбуков и ПК
      L3 [3] Ремонт бытовой техники
      L3 [4] Пошив и ремонт одежды
      L3 [5] Ремонт обуви
      L3 [6] Ремонт авто
    L2 [2] Строительство и ремонт помещений
      L3 [1] Монтаж напольных покрытий
      L3 [2] Штукатурка и шпаклёвка
      L3 [3] Сантехника
      L3 [4] Гидроизоляция
      L3 [5] Электрика
      L3 [6] Монтаж и обслуживание кондиционеров
      L3 [7] Терассы и балконы
      L3 [8] Строительство коммерческих помещений
      L3 [9] Строительство жилых помещений
    L2 [3] IT и компьютеры
      L3 [1] Настройка ПК и ноутбуков
      L3 [2] Программирование
      L3 [3] Создание сайтов и приложений
    L2 [4] Красота и здоровье
      L3 [1] Стрижка и укладка волос
      L3 [2] Маникюр
      L3 [3] Педикюр
      L3 [4] Уход за кожей
      L3 [5] Уход за волосами
      L3 [6] Массаж
      L3 [7] Спорт и фитнес
      L3 [8] Салоны красоты и SPA
      L3 [9] Психология
      L3 [10] Медицина
    L2 [5] Транспорт и перевозки
      L3 [1] Эвакуатор
      L3 [2] Такси
      L3 [3] Перевозки, курьерская доставка
      L3 [4] Грузоперевозки
    L2 [6] Уборка
      L3 [1] Уборка квартир
      L3 [2] Химчистка ковров и мебели
      L3 [3] Уборка офисов
      L3 [4] Клининг
    L2 [7] Мероприятия и развлечения
      L3 [1] Искусство
      L3 [2] Организация мероприятий
      L3 [3] Фотосессии
      L3 [4] Услуги флориста
    L2 [8] Репетиторство и обучение
      L3 [1] Репетиторы
      L3 [2] Курсы и тренинги
    L2 [9] Финансы и юридические услуги
      L3 [1] Бухгалтерия
      L3 [2] Юридические услуги
      L3 [3] Налоговое планирование
      L3 [4] Оценка недвижимости
      L3 [5] Переводы
    L2 [10] Охрана
    L2 [11] Домашние услуги
      L3 [1] Выгул собак
      L3 [2] Домашний персонал
      L3 [3] Пищевое обслуживание
    L2 [12] Без опыта, подработка, студенты
    L2 [13] Общественное питание
      L3 [1] Рестораны
      L3 [2] Общественное питание
    L2 [14] Сельское хозяйство
    L2 [15] Торговля
    L2 [16] Склады
    L2 [17] Прочие услуги
  L1 [7] Бизнес
    L2 [1] Готовый бизнес (listing_purpose: Продажа)
    L2 [2] Оборудование для бизнеса (listing_purpose: Продажа, Аренда)
      L3 [1] Торговое оборудование
      L3 [2] Пищевое оборудование
      L3 [3] Офисное оборудование
      L3 [4] Промышленное оборудование
      L3 [5] Логистика и склад
      L3 [6] Для салона красоты
      L3 [7] Для автобизнеса
      L3 [8] Медицинское оборудование
    L2 [3] Коммерческая недвижимость (alt path from недвижимость)
      L3 [1] Офисы
      L3 [2] Свободного назначения
      L3 [3] Торговые площади
      L3 [4] Склады
      L3 [5] Земельные участки (commercial)
    L2 [4] Услуги (alt path from Услуги)
      L3 [1] Бухгалтерия
      L3 [2] Юридические услуги
      L3 [3] Налоги
      L3 [4] Оценка недвижимости
      L3 [5] Переводы
  L1 [8] Благотворительность (auto-populated)
    (No MPTT children — populated via CategoryPath when Ad.price = 0 or NULL)
    System rule: When Ad.price = 0 or NULL → CategoryPath(category=<ad's category>, parent=Благотворительность, is_automatic=True)
    When price changes from 0 to positive → remove automatic CategoryPath
```

---

## GLOBAL LISTING PURPOSES (LookupGroup: listing_purpose)

Applied to ALL categories — each category picks a subset.

| Code | Slug | RU Name |
|------|------|---------|
| sell | sell | Продажа |
| give_away | give-away | Отдаю бесплатно |
| want_to_buy | want-to-buy | Ищу для покупки |
| rent_item | rent-item | Прокат |
| rent_long | rent-long | Долгосрочная аренда |
| rent_short | rent-short | Посуточная аренда |
| offer_service | offer-service | Предлагаю услугу |
| seek_service | seek-service | Ищу услугу |
| job_offer | job-offer | Предлагаю работу |
| job_seek | job-seek | Ищу работу |


---

## GLOBAL LISTING FEATURES (LookupGroup: listing_feature)

Applied to ALL categories — each category picks a subset.

| Code | Slug | RU Name |
|------|------|---------|
| new | new | Новый |
| used | used | Б/У |
| with_photo | with-photo | С фото |
| with_video | with-video | С видео |
| delivery_available | delivery | Доставка есть |
| pickup_available | pickup | Самовывоз |
| price_negotiable | negotiable | Торг уместен |
| credit_available | credit | В кредит |
| exchange_available | exchange | В обмен |
| installment_available | installment | Рассрочка |
| urgent | urgent | Срочно |
| luxury | luxury | Премиум |
| eco_friendly | eco | Экологично |
| handmade | handmade | Сделано вручную |
| branded | branded | Брендированный |
| custom_order | custom | Под заказ |
| warranty | warranty | С гарантией |
| no_warranty | no-warranty | Без гарантии |
| original_packaging | packaging | Оригинальная упаковка |
| import | import | Импорт |
| local_production | local | Местное производство |
| energy_efficient | efficient | Энергоэффективный |
| smart_home | smart-home | Умный дом |


---
## NOTES
2. **Listing purposes and features are NOT part of the category tree.**
   They are stored in LookupGroup tables (listing_purpose, listing_feature).
   Each category defines which purposes and features it supports via M2M through tables.

3. **Alternative paths (CategoryPath) are for navigation only** — they do not change the canonical MPTT parent. Ad.category always points to the canonical category.

4. **Slugs** are copied from old IDs or left empty. New IDs assigned during migration.
