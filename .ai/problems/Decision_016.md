# Мусор / пыль / битые файлы в src/

Аудит (Researcher-агенты по папкам + ручная проверка) выявил следующие файлы/директории,
которые не относятся к основному коду проекта (Django classifieds + aiogram bot) и
рекомендованы к удалению. Всё подтверждено фактом наличия в рабочем дереве.

## Уже удалено пользователем
- `src/backend/apps/users/edit_audit.py` — сломанный скрипт (invalid syntax, line 3:
  `pathlib.Path(rC:\py_dev\mko_bazuna\...`). Был одноразовой утилитой, созданной
  ИИ и закоммиченной в корень apps/users/. Удалён из рабочего дерева.

## Мусор — удалить
1. `src/backend/apps/urls.py.bak` — устаревший `.bak` корня `apps/`. Ссылается на
   `listings`/`ad_detail` без импорта (broken). Живой аналог — `apps/ads/urls.py`.
   *Отслеживается git: удалять via `git rm`.*
2. `src/backend/apps/seed/fixtures/_validate_transport.py.bak` — одноразовый debug-скрипт
   внутри директории fixtures; использует `print()` и жёстко захардкоженные Windows-пути.
   *Отслеживается git: удалять via `git rm`.*
3. `src/backend/apps/api/` — пустой скелет приложения (`serializers/` + `views/` только,
   без `__init__.py`/`apps.py`/`models.py`/`urls.py`). Не в `INSTALLED_APPS`, не
   используется ни `include()`, ни `from apps.api`. Либо удалить, либо реализовать.
4. `src/telegram_bot/bot/filters/`, `bot/handlers/`, `bot/states/` — пустые директории
   без `__init__.py`, без единой ссылки в коде. Заброшенная scaffolding-разметка.
5. `src/telegram_bot/parsers/` — пустая директория, без `__init__.py`, 0 ссылок.
6. `src/static/` — пустая директория; `STATICFILES_DIRS` указывает на корень `static/`.
   *Проверить, что ни одно tooling не ожидает `src/static` перед удалением.*
7. `src/templates/` — пустая директория; `TEMPLATES["DIRS"]` указывает на
   `src/backend/templates`, а не на `src/templates/`.
8. `src/backend/docker/entrypoint-test.sh` — пустая *директория* с именем `entrypoint-test.sh`
   (не файл!). Реальный скрипт живёт в корне `docker/entrypoint-test.sh` (1357 байт).
   Удалить пустую директорию.

## Сломан (orphaned+broken) — выковырять или удалить
9. `src/backend/templates/search/partials/save_search_modal.html` — не используется
   ни одним `{% include %}`, ни одним view. При этом ссылается на несуществующие URL
   `{% url 'search:list' %}` и `{% url 'search:save-search' %}` (в `search/urls.py` только
   `search:search` и `search:autocomplete`). Либо реализовать view+URL+include, либо удалить.

## Старые .pyc без .py источника (14 штук) — gitignored локальные артефакты, удалить
Это устаревшие байтокоды, ссылающиеся на переименованные/удалённые модули:
- `apps/ads/migrations/__pycache__/0002_initial.cpython-314.pyc`
  (перееименован → `0002_add_fks_and_search_triggers.py`)
- `apps/ads/migrations/__pycache__/0006_ad_ck_ads_published_at_if_published_and_more.cpython-314.pyc`
  (перееименован → `0006_ad_ix_ads_purge_deleted_and_more.py`)
- `apps/ads/tests/__pycache__/test_dbg_tmp.cpython-314-pytest-9.1.1.pyc`
  (`test_dbg_tmp.py` удалён — debug-тест)
- `apps/analytics/migrations/__pycache__/0002_initial.cpython-314.pyc`
  (перееименован → `0002_add_user_fks_and_metrics.py`)
- `apps/moderation/migrations/__pycache__/0002_initial.cpython-314.pyc`
  (перееименован → `0002_add_fks_and_priority_indexes.py`)
- `apps/moderation/tests/__pycache__/test_signals.cpython-314-pytest-9.1.1.pyc`
  (`test_signals.py` удалён — тестирует несуществующий модуль)
- `apps/moderation/tests/__pycache__/test_zzz_phase9_probe.cpython-314-pytest-9.1.1.pyc`
  (`test_zzz_phase9_probe.py` удалён — debug-stаб фазы/probe)
- `apps/search/migrations/__pycache__/0002_initial.cpython-314.pyc`
  (перееименован → `0002_add_fks_indexes_constraints.py`)
- `apps/search/services/__pycache__/query_translator.cpython-314.pyc`
  (`query_translator.py` удалён)
- `apps/search/tests/__pycache__/test_query_translator.cpython-314.pyc`
  (`test_query_translator.py` удалён)
- `apps/search/tests/__pycache__/test_query_translator.cpython-314-pytest-9.1.9.1.1.pyc`
  (та же)
- `apps/trust/migrations/__pycache__/0002_initial.cpython-314.pyc`
  (перееименован → `0002_add_user_fks.py`)
- `apps/trust/tests/__pycache__/test_debug_trust.cpython-314-pytest-9.1.1.pyc`
  (`test_debug_trust.py` удалён — debug-тест)
- `config/__pycache__/settings.cpython-314.pyc`
  (`settings.py` превращён в пакет `settings/` из base/dev/prod/test; одиночный
  `settings.pyc` устарел)

Очистка: `find src/backend src/telegram_bot -type d -name __pycache__ -prune -exec rm -rf {} +`

## Косметика (не критично)
10. `src/backend/apps/ads/migrations/0006_ad_ix_ads_purge_deleted_and_more.py` — содержит
    UTF-8 BOM (`\xef\xbb\xbf`). Python import machinery и `ruff` толерантны к BOM,
    миграция работает. Только naivные AST-парсеры (как build.bat) ругаются на U+FEFF.
    Можно удалить BOM при желании: `python -c "import pathlib; p=pathlib.Path(...); ..."`
    — не является синтаксической ошибкой интерпретатора.

## НЕ мусор (проверено, оставить на месте)
- `apps/moderation/tests.py` (562 строк) + `apps/search/tests.py` (413 строк) — полноценные
  view-level тест-сьюты (TST-004), корректно коллектятся pytest
  (`python_files = ["tests.py", "test_*.py"]`, `--import-mode=importlib`). Не orphaned.
- Русский текст в тест-фикстурах — намеренные локализованные данные (LANGUAGE_CODE="ru").
- `src/__init__.py` — пустой 0-байтовый маркер src-layout (`BASE_DIR = src/`).
- `src/.env` + `src/backend/.env` — gitignored локальная конфигурация.

## Итог
**Удалить:** пункты 1–8 + 14 .pyc-артефактов.
**Сломан/незавершён:** пункт 9 (save_search_modal.html — реализовать или удалить), пункт 10 (BOM — optional strip).
**Чисто:** apps/{ads,analytics,categories,core,locations,lookups,media,seed,trust,users,maps}, config/, manage.py, src/telegram_bot/, src/theme/, src/backend/templates/ (кроме \partials/orphan).
