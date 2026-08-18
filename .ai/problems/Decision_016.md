# Мусор / пыль / битые файлы в src/

Аудит (Researcher-агенты по папкам + ручная проверка) выявил следующие файлы/директории,
которые не относятся к основному коду проекта (Django classifieds + aiogram bot) и
рекомендованы к удалению. 

## Мусор — удалить
1. `src/backend/apps/urls.py.bak` — устаревший `.bak` корня `apps/`. Ссылается на
   `listings`/`ad_detail` без импорта (broken). Живой аналог — `apps/ads/urls.py`.
   *Отслеживается git: удалять via `git rm`.*
2. `src/backend/apps/seed/fixtures/_validate_transport.py.bak` — одноразовый debug-скрипт
   внутри директории fixtures; использует `print()` и жёстко захардкоженные Windows-пути.
   *Отслеживается git: удалять via `git rm`.*
6. `src/static/` — пустая директория; `STATICFILES_DIRS` указывает на корень `static/`.
   *Проверить, что ни одно tooling не ожидает `src/static` перед удалением.*
7. `src/templates/` — пустая директория; `TEMPLATES["DIRS"]` указывает на
   `src/backend/templates`, а не на `src/templates/`.
8. `src/backend/docker/entrypoint-test.sh` — пустая *директория* с именем `entrypoint-test.sh`
   (не файл!). Реальный скрипт живёт в корне `docker/entrypoint-test.sh` (1357 байт).
   Удалить пустую директорию.


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
