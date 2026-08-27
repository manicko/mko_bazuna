# Mko Bazuna

> Documents the target specification/architecture (source of truth: `docs/01-spec/`). Implementation is in progress.

Telegram-driven classifieds board (Avito-like) with a Django website. Sellers post ads through a
Telegram bot; published ads appear on the site. Buyers browse, search, and filter without login.

**Launch market:** Montenegro
**Content language:** Russian (base)
**UI:** Russian + Montenegrin (latin)

## Stack
Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · aiogram 3.x (Telegram bot) · PostgreSQL native FTS ·
django-mptt (categories) · django-tailwind + django-htmx (MPA) · Docker (db + web + bot + nginx)

## Architecture
Two long-lived processes share one Django project + one DB:
- **web:** sync WSGI (gunicorn), server-rendered HTMX MPA
- **bot:** aiogram, runs `django.setup()`, shares the ORM. The step-by-step ad dialog is persisted as an `Ad` row (`DRAFT`) via the shared ORM.

**Migrations run exactly once** before web+bot start. **Search:** native PostgreSQL full-text search (`search_vector` TSVECTOR + GIN, russian config).

## Quick start
```bash
# Configure .env.docker with your values (BOT_TOKEN, DJANGO_SECRET_KEY, POSTGRES_PASSWORD)
make build                  # build Docker images (one-time)
make up                     # start dev environment on :8000; runs db → migrate → load_catalog → create_admin → seed → web, bot
```

> **Project isolation:** `make` sets `COMPOSE_PROJECT_NAME` automatically (`mko-bazuna-dev` for dev,
> `mko-bazuna-test` for test) so `make up` and `make test` never collide. See
> [Docker deployment & operations](docs/ops/docker-deployment.md#compose-project-isolation) for the
> exact invocation forms and manual (non-`make`) setup.

### Tailwind CSS Development

Tailwind CSS is built during Docker image creation and regenerated on container start in development. CSS changes are detected automatically when running with the dev override.

```bash
# Development with hot-reload
make up
```

To rebuild CSS manually after editing templates:
```bash
make shell
# then inside the container:
uv run tailwindcss -i src/theme/static/theme/css/input.css -o src/theme/static/theme/css/output.css --minify
```

### Local HTTPS Development

Mko Bazuna uses nginx with TLS in both development and production for production parity. HTTPS is required to test secure cookies, OAuth, webhooks, and HTTP/2 features. See [Local HTTPS with mkcert](docs/ops/local-https-mkcert.md) for complete setup instructions.

```bash
# Install mkcert (once per machine)
choco install mkcert        # Windows (Chocolatey)

# One-time CA install (requires admin on Windows)
mkcert -install

# Generate development certificates
mkdir -p docker/nginx/certs
cd docker/nginx/certs
mkcert localhost 127.0.0.1 ::1 mkobazuna.local
# Rename for nginx compatibility (filenames may vary, e.g. localhost+2.pem)
cp localhost+2.pem fullchain.pem
cp localhost+2-key.pem privkey.pem
```

Then run with nginx profile for HTTPS:
```bash
COMPOSE_PROJECT_NAME=mko-bazuna-dev docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx up -d
```

Access at `https://localhost`. Certificates are valid for ~2 years; re-run mkcert to renew.

Web is served behind nginx (ports 80/443); the web container is not exposed directly.

### PgBouncer (optional connection pooling)
PgBouncer service is available for connection pooling via profile:
```bash
COMPOSE_PROJECT_NAME=mko-bazuna-dev docker compose --env-file .env.docker \
  -f docker-compose.yml -f docker-compose.dev.override.yml --profile pgbouncer up -d
```
Uses transaction-mode pooling with `edoburu/pgbouncer:1.25.2`. Enable in production when:
- High database connection count from multiple app instances
- Need to reduce PostgreSQL memory usage
- CONN_MAX_AGE=0 is already set in Django settings for async safety

## Documentation
| Doc | Purpose |
|-----|---------|
| `docs/01-spec/spec-index.md` | Concise technical summary for agents/developers |
| `docs/01-spec/technical-specification.md` | Product & domain spec (decisions A–L) |
| `docs/05-owner-decisions/index.md` | Owner decisions O1–O5 (plain, owner-readable) |
| `docs/01-spec/architecture-structure.md` | Source layout & Docker deployment |
| `docs/02-database/db-schema.md` | Tables, columns, relationships, enums reference |
| `docs/02-database/db-indexes.md` | Indexes & `search_vector` trigger SQL |
| `docs/02-database/db-enums.md` | `StrEnum` types (AdStatus, EventType, etc.) |
| `docs/03-packages/packages-list.md` | Dependency set & versions |
| `docs/03-packages/dependency-collisions.md` | Package version-coupling & collision risks |
| `docs/04-user-stories/index.md` | User stories by role (seller/buyer/admin) |
  | `docs/ops/docker-deployment.md` | Docker deployment & operations guide (Makefile, project isolation, test env, recovery) |
  | `docs/ops/migration-workflow.md` | Development migration workflow, consolidation, advisory locks |
  | `docs/ops/seed-workflow.md` | Seed data generation, fixtures, and photo pipeline |
| `docs/ops/restore.md` | Database restore runbook |
| `docs/ops/local-https-mkcert.md` | Local HTTPS setup with mkcert |
| `docs/99-agent/architecture.md` · `rules.md` · `references.md` | Agent guidelines & references |
| `docs/00-overview/doc-maintenance-rules.md` | Documentation governance rules |

### Docs structure
```
docs/
├── 00-overview/            doc-maintenance-rules.md
├── 01-spec/                spec-index.md · technical-specification.md · architecture-structure.md · design-system.md · filter-ui.md · search-patterns.md · ui-patterns.md
├── 02-database/            db-schema.md · db-indexes.md · db-enums.md
├── 03-packages/            packages-list.md · dependency-collisions.md
├── 04-user-stories/        index.md · seller-stories.md · buyer-stories.md · admin-stories.md
├── 05-owner-decisions/     index.md
├── 06-design-system/       index.md · tokens.md · tokens-research.md · layout.md · instruction.md · components.md · accessibility.md
├── 07-design-researches/   migration_patterns.md · Design_1/ · Design_2/
├── 97-plans/               01-phase-plan-highlevel.md · phase-01-detailed.md · phase-01-detailed-deployment.md · phase-01-detailed-testing.md · phase-02-detailed-plan-1.md · phase-02-detailed-plan-2.md · phase-02-detailed-plan-3.md
├── 98-reference/           ast-editor.md
├── 99-agent/               architecture.md · rules.md · references.md · trust-signals-plan.md
└── ops/                    docker-deployment.md · migration-workflow.md · seed-workflow.md · restore.md · local-https-mkcert.md · postgres-18-docker-volume-migration.md · research/
```

## Commands
| Task | Command |
|------|---------|
| Run tests | `make test` |
| Lint | `uv run ruff check <path>` |
| Type check | `uv run basedpyright <path>` |
| Add dependency | `uv add <package>` |

## Notes
**Phase 1 scope:** ads only via our Telegram bot.

**Deferred (post-MVP):** DRF API, Celery/Redis, S3/R2 storage, Telethon scraping, EAV attributes, tags, multi-currency.