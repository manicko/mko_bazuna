Нужно добавить функционал кабинета продавца: 
  - правый верхний угол
  - Если не залогинен, на всех страницах нужно добавить работающую кнопку - вход/регистрация (перебрасывает на страницу логина, регистрации)
  
  - Если залогинен - кнопка входа в кабинет
  - Из кабинета можно управлять объявлениями 

Вот тут нужно запустить Researcher агента: посмотреть, по документации и по современным практикам на avito + olx какой функционал должен быть в кабинете и спросить у владельца продукта (у меня), что из этого берем

  - Также, нужно понять, как сделать вход для админа сайта - изучи современную практику, как разделить вход пользователей и кабинет пользователей от входа админа.

---

## PO Clarification (2026-08-20)

The auth/cabinet entry must appear in the catalog header (`header_catalog.html`) on
**all public pages** — including the homepage (listings) and ad-detail pages.
Spec_014 (R-05c) previously excluded the auth entry from the catalog header; this was
an error. The login/cabinet button should follow the Avito/OLX compact pattern:
icon-only user button (anonymous = outline, authenticated = filled avatar/initials)
with a dropdown menu, plus a heart icon with favorites count badge.
See `24_catalog-header-auth-entry_spec.md` for the full treatment.

