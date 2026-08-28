Сейчас у нас очень долго запускатся контейнер. 

docker compose --project-name mko-bazuna-test `
  -f docker-compose.yml `
  -f docker-compose.test.yml `
  run --rm `
  --env DJANGO_SETTINGS_MODULE=config.settings.test `
  -e DATABASE_URL="postgres://postgres:postgres@db:5432/mko_bazuna" `
  -e DJANGO_SECRET_KEY=test-secret-key-for-testing-only `
  -e BOT_TOKEN=test-bot-token-for-testing `
  test python -u -c "
import django
print('1. importing django', flush=True)
django.setup()
print('2. django.setup() done', flush=True)
from django.db import connection
print('3. got connection', flush=True)
print('4. vendor:', connection.vendor, flush=True)
print('5. settings NAME:', connection.settings_dict.get('NAME'), flush=True)
print('6. creating test db...', flush=True)
try:
    old_config = connection.creation.create_test_db(verbosity=2)
    print('TEST DB CREATED SUCCESSFULLY', flush=True)
except Exception as e:
    import traceback
    print(f'ERROR: {type(e).__name__}: {e}', flush=True)
    traceback.print_exc()
"


проблема с `Compiling translations...` выполняется очень долго. 

Это может быть связана с количеством локалей: в файле огромный список `.po`, причём Django-компоненты (`humanize`, `sites`, `admin`, `flatpages` и т. д.) содержат практически весь набор локалей. Например, уже в первых строках идут `is`, `udm`, `my`, `os`, `sk`, `hr`, `fr`, `af` и далее. 

Но есть **важная деталь**: судя по выводу, эти файлы находятся в:

```text
/app/.venv/Lib/site-packages/django/...
```

То есть это **локали самого Django**,
те наш скрипт , скорее всего, сканирует **весь `/app`**, включая `.venv`, потому что `.venv` лежит внутри `/app`.

Это плохая конфигурация для Docker.

Нужно запустить Researcher агентов, чтобы:
1) Изучить текущую архитектуру и определить точную причину, почему так долго отрбабатывает контейнер и повисает Compiling translations...
2) Изучить современные практики, как корректно прописывать, чтобы Compiling translations... проходил быстро
