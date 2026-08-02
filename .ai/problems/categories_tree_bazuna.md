# Canonical Category Tree for Mko Bazuna (Базуна)

Based on analysis of Avito category structures, market demand patterns, and the 7 agreed top-level sections.

## Top-level categories (7 fixed)

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
L0 [root] Все категории (7 subs)
  L1 [1] Недвижимость (real-estate) (listing_purpose: sell, rent, rent-short) (listing_feature: negotiable, credit, installment, urgent, luxury, smart-home, eco, exchange)
    L2 [1] Квартиры (apartments)
    L2 [2] Дома, дачи, коттеджи (houses)
    L2 [3] Комнаты (rooms)
    L2 [4] Гаражи и машиноместа (garages) (listing_purpose: sell, rent)
    L2 [5] Земельные участки (land-plots) (listing_purpose: sell, rent)
    L2 [6] Прочая недвижимость (other-real-estate) (listing_purpose: sell, rent)
    L2 [7] Коммерческая недвижимость (commercial-real-estate) (listing_purpose: sell, rent)
      L3 [1] Офисы (offices)
      L3 [2] Свободного назначения (flex-space)
      L3 [3] Торговые площади (retail-spaces)
      L3 [4] Склады (warehouses)
      L3 [5] Земельные участки (commercial) (commercial-land)
  L1 [2] Транспорт (transport) (listing_purpose: sell, rent) (listing_feature: new, used, delivery, pickup, negotiable, credit, exchange, urgent, warranty)
    L2 [1] Автомобили (cars)
    L2 [2] Мотоциклы и мототехника (motorcycles)
      L3 [1] Мотоциклы (motorcycles)
      L3 [2] Мопеды и скутеры (scooters)
      L3 [3] Велосипеды (bicycles)
      L3 [4] Самокаты (scooters)
    L2 [3] Грузовики и спецтехника (trucks)
      L3 [1] Грузовики (trucks)
      L3 [2] Сельхозтехника (agricultural-machinery)
      L3 [3] Коммерческий транспорт (commercial-vehicles)
      L3 [4] Автодома (campers)
    L2 [4] Водный транспорт (water-transport)
      L3 [1] Катера и яхты (boats-yachts)
      L3 [2] Моторные лодки (motorboats)
      L3 [3] Вёсельные лодки (sailing-boats)
      L3 [4] Гидроциклы (personal-watercraft)
    L2 [5] Запчасти и аксессуары (auto-parts) (alt path from Товары.Запчасти, listing_purpose: sell) (listing_feature: new, used, delivery, pickup, negotiable, exchange, urgent, warranty, packaging, branded, import, local)
      L3 [1] Запчасти (parts)
      L3 [2] Шины, диски и колёса (tires-wheels)
      L3 [3] Аксессуары (accessories)
      L3 [4] Инструменты (tools) (alt path)
      L3 [5] Экипировка (equipment) (alt path)
      L3 [6] Масла и автохимия (oils-chemicals)
      L3 [7] Противоугонные устройства (anti-theft)
      L3 [8] GPS-навигаторы (gps-navigators)
      L3 [9] Аудио- и видеотехника (audio-video) (alt path)
      L3 [10] Багажники и фаркопы (roof-boxes-hitches)
      L3 [11] Прицепы (trailers)
  L1 [3] Товары (goods) (listing_purpose: sell) (listing_feature: new, used, delivery, pickup, negotiable, exchange, urgent, handmade, branded, custom, warranty, packaging, import, local, eco)
    L2 [1] Одежда, обувь, аксессуары (clothing-shoes-accessories)
      L3 [1] Женская одежда (women-clothing)
      L3 [2] Женская обувь (women-shoes)
      L3 [3] Мужская одежда (men-clothing)
      L3 [4] Мужская обувь (men-shoes)
      L3 [5] Сумки, рюкзаки и чемоданы (bags-luggage)
      L3 [6] Аксессуары (accessories)
    L2 [2] Детская одежда и обувь (kids-clothing-shoes)
      L3 [1] Для девочек (girls)
      L3 [2] Для мальчиков (boys)
    L2 [3] Товары для детей и игрушки (kids-products-toys)
      L3 [1] Игрушки (toys)
      L3 [2] Детские коляски (strollers)
      L3 [3] Автомобильные кресла (car-seats)
      L3 [4] Детская мебель (kids-furniture)
      L3 [5] Товары для кормления (feeding-products)
      L3 [6] Товары для купания (bath-products)
      L3 [7] Товары для школы (school-supplies)
      L3 [8] Постельные принадлежности (bed-linen)
      L3 [9] Самокаты и беговелы (детские) (kids-scooters-bikes)
      L3 [10] Детская гигиена (kids-hygiene)
    L2 [4] Красота и здоровье (beauty-health)
      L3 [1] Макияж и маникюр (makeup-manicure)
      L3 [2] Парфюмерия (perfumes)
      L3 [3] Уход и гигиена (care-hygiene)
      L3 [4] Средства для волос (hair-care)
      L3 [5] Приборы и аксессуары (appliances-accessories)
      L3 [6] Медицинские изделия (medical-products)
    L2 [5] Часы и украшения (watches-jewelry)
      L3 [1] Ювелирные изделия (jewelry)
      L3 [2] Часы (watches)
      L3 [3] Бижутерия (costume-jewelry)
    L2 [6] Для дома и дачи (home-garden)
      L3 [1] Мебель и интерьер (furniture-interior)
      L3 [2] Ремонт и строительство (repair-construction)
      L3 [3] Бытовая техника (appliances)
      L3 [4] Продукты питания (food-products) (listing_feature: delivery, pickup, negotiable, exchange, urgent, local, eco, import)
      L3 [5] Растения (plants) (listing_feature: delivery, pickup, negotiable, exchange, urgent, local, eco)
      L3 [6] Посуда и товары для кухни (kitchen-dining)
    L2 [7] Электроника (electronics)
      L3 [1] Телефоны (phones)
      L3 [2] Аудио и видео (audio-video)
      L3 [3] Компьютеры (computers)
      L3 [4] Ноутбуки (laptops)
      L3 [5] Планшеты (tablets)
      L3 [6] Фототехника (cameras)
      L3 [7] Игры, приставки, программы (games-consoles-software)
      L3 [8] Другое (other)
    L2 [8] Хобби и отдых (hobby-leisure)
      L3 [1] Велосипеды (bicycles) (alt path from Транспорт)
      L3 [2] Самокаты (scooters) (alt path from Транспорт)
      L3 [3] Книги и журналы (books-magazines)
      L3 [4] Музыкальные инструменты (musical-instruments)
      L3 [5] Спорт и отдых (sports-outdoors)
      L3 [6] Билеты и путешествия (tickets-travel)
      L3 [7] Охота и рыбалка (hunting-fishing)
  L1 [4] Животные (animals) (listing_purpose: sell, give-away, lost, found) (listing_feature: delivery, pickup, negotiable, urgent)
    L2 [1] Собаки (dogs)
    L2 [2] Кошки (cats)
    L2 [3] Птицы (birds)
    L2 [4] Рыбы и аквариумные животные (fish-aquarium)
    L2 [5] Другие животные (other-animals)
    L2 [6] Товары для животных (pet-supplies) (listing_feature: new, used, delivery, pickup, negotiable, exchange, urgent, warranty, branded, import, local)
      L3 [1] Корм и сухой корм (pet-food)
      L3 [2] Игрушки для животных (pet-toys)
      L3 [3] Аксессуары для животных (pet-accessories)
      L3 [4] Для собак и кошек (dogs-cats)
      L3 [5] Для птиц (birds)
  L1 [5] Услуги, работа, вакансии (services-jobs) (listing_purpose: job-seek, job-offer, seek-service, offer-service) (listing_feature: negotiable, urgent)
    L2 [1] Ремонт и сервис (repair-service)
      L3 [1] Ремонт телефонов (phone-repair)
      L3 [2] Ремонт ноутбуков и ПК (laptop-pc-repair)
      L3 [3] Ремонт бытовой техники (appliance-repair)
      L3 [4] Пошив и ремонт одежды (clothing-repair)
      L3 [5] Ремонт обуви (shoe-repair)
      L3 [6] Ремонт авто (car-repair)
    L2 [2] Строительство и ремонт помещений (construction-renovation)
      L3 [1] Монтаж напольных покрытий (flooring-installation)
      L3 [2] Штукатурка и шпаклёвка (plastering)
      L3 [3] Сантехника (plumbing)
      L3 [4] Гидроизоляция (waterproofing)
      L3 [5] Электрика (electrical)
      L3 [6] Монтаж и обслуживание кондиционеров (ac-installation)
      L3 [7] Терассы и балконы (terraces-balconies)
      L3 [8] Строительство коммерческих помещений (commercial-construction)
      L3 [9] Строительство жилых помещений (residential-construction)
    L2 [3] IT и компьютеры (it-computers)
      L3 [1] Настройка ПК и ноутбуков (pc-setup)
      L3 [2] Программирование (programming)
      L3 [3] Создание сайтов и приложений (web-development)
    L2 [4] Красота и здоровье (beauty-health)
      L3 [1] Стрижка и укладка волос (hair-styling)
      L3 [2] Маникюр (manicure)
      L3 [3] Педикюр (pedicure)
      L3 [4] Уход за кожей (skincare)
      L3 [5] Уход за волосами (hair-care)
      L3 [6] Массаж (massage)
      L3 [7] Спорт и фитнес (sport-fitness)
      L3 [8] Салоны красоты и SPA (beauty-salons-spa)
      L3 [9] Психология (psychology)
      L3 [10] Медицина (medicine)
    L2 [5] Транспорт и перевозки (transport-logistics)
      L3 [1] Эвакуатор (tow-truck)
      L3 [2] Такси (taxi)
      L3 [3] Перевозки, курьерская доставка (delivery-courier)
      L3 [4] Грузоперевозки (freight)
    L2 [6] Уборка (cleaning)
      L3 [1] Уборка квартир (apartment-cleaning)
      L3 [2] Химчистка ковров и мебели (carpet-cleaning)
      L3 [3] Уборка офисов (office-cleaning)
      L3 [4] Клининг (cleaning-service)
    L2 [7] Мероприятия и развлечения (events-entertainment)
      L3 [1] Искусство (arts)
      L3 [2] Организация мероприятий (event-planning)
      L3 [3] Фотосессии (photoshoots)
      L3 [4] Услуги флориста (florist)
    L2 [8] Репетиторство и обучение (tutoring-education)
      L3 [1] Репетиторы (tutors)
      L3 [2] Курсы и тренинги (courses-training)
    L2 [9] Финансы и юридические услуги (finance-legal)
      L3 [1] Бухгалтерия (accounting)
      L3 [2] Юридические услуги (legal-services)
      L3 [3] Налоговое планирование (tax-planning)
      L3 [4] Оценка недвижимости (property-valuation)
      L3 [5] Переводы (translations)
    L2 [10] Охрана (security)
    L2 [11] Домашние услуги (home-services)
      L3 [1] Выгул собак (dog-walking)
      L3 [2] Домашний персонал (housekeeping)
      L3 [3] Пищевое обслуживание (food-service)
    L2 [12] Без опыта, подработка, студенты (no-experience-jobs) (listing_purpose: job-seek) (listing_feature: negotiable)
    L2 [13] Общественное питание (food-service)
      L3 [1] Рестораны (restaurants)
      L3 [2] Общественное питание (catering)
    L2 [14] Сельское хозяйство (agriculture)
    L2 [15] Торговля (trading)
    L2 [16] Склады (warehousing)
    L2 [17] Прочие услуги (other-services)
  L1 [6] Бизнес (business) (listing_purpose: sell, rent) (listing_feature: new, used, delivery, pickup, negotiable, credit, installment, urgent, warranty, luxury)
    L2 [1] Готовый бизнес (ready-business) (listing_purpose: sell) (listing_feature: negotiable, urgent, credit, installment, luxury)
    L2 [2] Оборудование для бизнеса (business-equipment) (listing_feature: new, used, delivery, pickup, negotiable, exchange, urgent, warranty)
      L3 [1] Торговое оборудование (retail-equipment)
      L3 [2] Пищевое оборудование (food-equipment)
      L3 [3] Офисное оборудование (office-equipment)
      L3 [4] Промышленное оборудование (industrial-equipment)
      L3 [5] Логистика и склад (logistics-warehouse)
      L3 [6] Для салона красоты (beauty-equipment)
      L3 [7] Для автобизнеса (auto-business-equipment)
      L3 [8] Медицинское оборудование (medical-equipment)
    L2 [3] Коммерческая недвижимость (commercial-real-estate) (alt path from недвижимость)
      L3 Офисы (offices)
      L3 Свободного назначения (flex-space)
      L3 Торговые площади (retail-spaces)
      L3 Склады (warehouses)
      L3 Земельные участки (commercial) (commercial-land)
    L2 [4] Услуги (services) (alt path from Услуги)
      L3 Бухгалтерия (accounting)
      L3 Юридические услуги (legal-services)
      L3 Налоги (taxes)
      L3 Оценка недвижимости (property-valuation)
      L3 Переводы (translations)
  L1 [7] Благотворительность (charity) (auto-populated)
    (No MPTT children — populated via CategoryPath when Ad.price = 0 or NULL)
    System rule: When Ad.price = 0 or NULL → CategoryPath(category=<ad's category>, parent=Благотворительность, is_automatic=True)
    When price changes from 0 to positive → remove automatic CategoryPath
```

---

## GLOBAL LISTING PURPOSES (LookupGroup: listing_purpose)

Applied to ALL categories — each category picks a subset.

| Slug | RU Name |
|------|---------|
| sell | Продажа |
| give-away | Отдаю бесплатно |
| rent | Аренда |
| rent-short | Посуточная аренда |
| lost | Потерянные |
| found | Найденные |
| offer-service | Предлагаю услугу |
| seek-service | Ищу услугу |
| job-offer | Предлагаю работу |
| job-seek | Ищу работу |


---

## GLOBAL LISTING FEATURES (LookupGroup: listing_feature)

Applied to ALL categories — each category picks a subset.

| Slug | RU Name |
|------|---------|
| new | Новый |
| used | Б/У |
| delivery | Доставка есть |
| pickup | Самовывоз |
| negotiable | Торг уместен |
| credit | В кредит |
| exchange | В обмен |
| installment | Рассрочка |
| urgent | Срочно |
| luxury | Премиум |
| eco | Экологично |
| handmade | Сделано вручную |
| branded | Брендированный |
| custom | Под заказ |
| warranty | С гарантией |
| packaging | Оригинальная упаковка |
| import | Импорт |
| local | Местное производство |
| smart-home | Умный дом |


---
## NOTES
2. **Listing purposes and features are NOT part of the category tree.**
   They are stored in LookupGroup tables (listing_purpose, listing_feature).
   Each category defines which purposes and features it supports via M2M through tables.
3. **Inheritance model**:
   - L1 categories set the full `listing_feature` set for all descendants.
   - L2/L3 categories only override `listing_feature` if they need a **different** set
     (e.g., removing, adding, or replacing features from the inherited set).
   - Categories without an explicit `listing_feature` annotation **inherit** from their
     nearest L1 ancestor.
4. **Alternative paths (CategoryPath)** are for navigation only — they do not change the canonical MPTT parent. Ad.category always points to the canonical category.
