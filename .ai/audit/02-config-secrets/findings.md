---
phase: "02"
phase_name: "Configuration & Secrets Management"
date: "2026-09-27"
auditor: "Executor (subagent)"
validator: ""
mode: "problems-only"
id_prefix: "CFG"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/02-audit-config-secrets.md#severity-taxonomy"
---

# Audit Findings — Configuration & Secrets Management

## Executive Summary

The system's secret plumbing is broadly sound: no real credentials are committed, the
configuration templates are placeholders only, and production boot fails loudly when a
required secret is missing. However, eleven defects were found that weaken this
protection. The most serious is a single environment flag that can silently switch off
*every* production secret check, and a second defect that means the automated
production-configuration check in the build pipeline can no longer run at all. A further
group of issues would let the site go live with a broken seller-contact address, with
customer email printed into server logs, or with the whole development environment
permanently offline from a single bot-only typo.

## Scope & Methodology

**Scope:** `src/backend/config/settings/{__init__,base,dev,prod,test}.py`, the four
tracked `.env*.example` templates, `.gitignore`/`.dockerignore`/`.gitleaks.toml`,
`docker-compose.{yml,dev.override.yml,test.yml,prod.yml}`, `docker/Dockerfile`, all
`docker/*.sh` entrypoints and healthchecks, `.github/workflows/ci.yml` + `deploy.yml`,
`src/backend/apps/core/utils/{migrate_locked,json_logging}.py`,
`src/telegram_bot/main.py`, and every `env()`/`os.getenv()` call site in `src/`.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Settings import cleanly per environment (test / dev / prod) | `uv run python -c "import config.settings.<env>"` with a controlled environment | PASS |
| R-02 | Valid prod env imports with hardened transport flags | subprocess import with all guards satisfied | PASS |
| R-02b | Missing/empty/invalid secret raises a clear, value-free error | `_prod_env_overrides` subprocesses + manual `DJANGO_SECRET_KEY=""` import | PASS — 12 guard tests green |
| R-02c | **Secret guards are unconditional** | subprocess import with `DJANGO_ONESHOT=1` and every secret blanked | **FAIL** → CFG-001 |
| R-03 | Hardcoded-secret scan (code, compose, Dockerfiles, workflows, docs) | `git grep -E` for Telegram-token shape, `AIza*`, `ghp_*`, `github_pat_*`, `sk-*`, `AKIA*`, `BEGIN … PRIVATE KEY`, plus a generic `key = "…"` sweep | PASS — only test fixtures and `github_pat_xxxx…` placeholders |
| R-04 | Ignore coverage for real secret files | `git check-ignore -v .env.dev .env.prod .env.test src/.env` + `git ls-files` + `.dockerignore` review | PASS — all four real files ignored, only `*.example` tracked, `.dockerignore` excludes `.env*` |
| R-05 | Linter + type checker over the config/secret surface | `uv run ruff check src/backend/config/`; `uv run basedpyright src/backend/config/` | PASS — exit 0 both (0 errors, 0 warnings) |
| R-06 | Config/secret test suite | `docker compose … run --rm test` with `PYTEST_OPTS=src/backend/config/settings/tests` | PASS — 41 passed (81.9 s) |
| R-07 | Compose renders for the test project | `docker compose … config --quiet` | PASS — exit 0 |
| R-08 | Live container boot behaviour (dev stack) | `docker ps` + `docker logs mko-bazuna-dev-{web,bot}-1` | **FAIL** → CFG-006 |
| R-09 | CI `deploy-check` prod-settings import path reproduced locally | subprocess import with the exact `ci.yml:510-518` environment | **FAIL** → CFG-002 |
| R-10 | Env-var consumption vs `ALLOWED_ENV_VARS` vs templates | static trace of every `env()`/`os.getenv()`/`${VAR}` against the allowlist and the 4 templates | **FAIL** → CFG-005, CFG-008, CFG-009 |
| R-11 | Every settings assignment recognised by the installed Django | `hasattr(django.conf.global_settings, …)` on Django 5.2.17 | **FAIL** → CFG-007 |
| R-12 | Production mail backend cannot be redirected | prod-settings import with `EMAIL_BACKEND=…console.EmailBackend`, then `mail.send_mail` | **FAIL** → CFG-004 |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `uv run python` (subprocess settings imports), `uv run ruff check`,
`uv run basedpyright`, `git grep`, `git check-ignore`, `git blame`,
`docker compose … run` (test service, project `mko-bazuna-test`), `docker ps`,
`docker logs`, `Select-String` static sweeps.

**Assumptions:** "Production" = `config.settings.prod` as wired by
`docker-compose.prod.yml` with `.env.prod` as the single secret source; the running
`.env.dev`/`.env.prod`/`.env.test` files in this working tree are operator-local and
were classified by key name and value *shape* only — no secret value was read, printed
or quoted. Django 5.2.17 / Python 3.14 as installed in `.venv`.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| CFG-001 | `DJANGO_ONESHOT` / `DJANGO_BUILD` in the env file disables every production secret guard | HIGH | Open | Security — secret validation |
| CFG-002 | CI `deploy-check` job cannot import `config.settings.prod`; the production config gate never runs | HIGH | Open | Reliability — validation pipeline |
| CFG-003 | Admin password passed as a management-command argument (visible in `ps`/`/proc/*/cmdline`) | MEDIUM | Open | Security — secret exposure |
| CFG-004 | `EMAIL_BACKEND` is env-overridable in production; transactional email can be routed to stdout | MEDIUM | Open | Security — configuration |
| CFG-005 | `BOT_USERNAME` placeholder is unvalidated and is persisted into the DB by a migration | MEDIUM | Open | Correctness — configuration |
| CFG-006 | A bot-only config error in the shared settings module crash-loops the whole dev stack | MEDIUM | Open | Availability — configuration coupling |
| CFG-007 | `STATICFILES_STORAGE` in `prod.py` is a dead setting removed from Django 5.1+ | MEDIUM | Open | Maintainability — dead config |
| CFG-008 | `RUN_TRANSLATION_BACKFILL` is absent from `ALLOWED_ENV_VARS` and from all env templates | LOW | Open | Observability — dead config |
| CFG-009 | `.env.example` omits 19 consumed variables including the whole `EMAIL_*` block | LOW | Open | Maintainability — template gap |
| CFG-010 | `test.py` does not reset `SECURE_HSTS_*`, contradicting its own "mirrors dev" comment | LOW | Open | Maintainability — environment separation |
| CFG-011 | `base.py` comment cites a non-existent "Env schema" for `BOT_TOKEN` validation | LOW | Open | Maintainability — stale documentation |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 0 | 2 | 5 | 4 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 11 |

## Findings by Severity

### HIGH

#### CFG-001: [HIGH] — `DJANGO_ONESHOT` / `DJANGO_BUILD` in the env file disables every production secret guard

| Field | Value |
|---|---|
| **ID** | CFG-001 |
| **Title** | `DJANGO_ONESHOT` / `DJANGO_BUILD` in the env file disables every production secret guard |
| **Severity** | HIGH |
| **Category** | Security — secret validation (protection mechanism failure) |
| **File(s)** | `src/backend/config/settings/prod.py:111-113`, `src/backend/config/settings/prod.py:153-251`, `src/backend/config/settings/base.py:19-38`, `src/backend/config/settings/base.py:102-105` |
| **Status** | Open |
| **Problem** | `prod.py` gates all eight production secret checks behind `_SKIP_SECRET_VALIDATION = bool(os.getenv("DJANGO_BUILD") or os.getenv("DJANGO_ONESHOT"))`, with no restriction on which settings module is being loaded. Both variables are listed in `ALLOWED_ENV_VARS` as "Python-consumed", i.e. they are explicitly accepted from a `.env` file. Because `base.py` calls `environ.Env.read_env()` on the bind-mounted `/app/src/.env` (= `.env.prod` in production) for every non-test settings module, a single `DJANGO_ONESHOT=1` line in `.env.prod` is loaded into `os.environ` inside the long-lived `web` and `bot` containers and silently turns the entire production secret-validation layer off. |
| **Impact** | With the bypass present, production boots with a blank signing key, no bot token, no translation key, no site URL, no SMTP host, no trusted origins and no Redis URL — all accepted without complaint. The concrete outcomes are: every web request that touches signing raises `ImproperlyConfigured: The SECRET_KEY setting must not be empty` (verified, Appendix A), the bot logs "BOT_TOKEN not set — skipping bot startup (development mode)" and exits 0 while reporting healthy, the bot silently drops to `MemoryStorage` so ad-creation FSM state is lost on every restart, and all CSRF-protected POSTs are rejected with HTTP 403. `check --deploy` at boot is non-fatal (`entrypoint.sh:95-96`), so the degradation is not caught. The configuration error is silent — no warning is emitted, and the only trace is a W009 line in the boot log. |
| **Root Cause** | A build/bootstrap escape hatch is expressed as a process-wide environment variable instead of being bound to the bootstrap context (settings module, or a dedicated `config.settings.bootstrap`). The allowlist then legitimises the variable as a legitimate `.env` key, so nothing warns an operator that a dev-only flag has entered a production secret file. |
| **Recommendation** | Stop honouring the bypass under `config.settings.prod`. Either (a) ignore `DJANGO_ONESHOT`/`DJANGO_BUILD` unless `DJANGO_SETTINGS_MODULE` is not a `*.prod` module, or (b) move the one-shot services onto a dedicated `config.settings.bootstrap` module that inherits from `base` with dev-grade transport flags, leaving `prod.py` unconditionally strict. Add a regression test asserting that `DJANGO_ONESHOT=1` combined with `DJANGO_SETTINGS_MODULE=config.settings.prod` still raises on a blank `SECRET_KEY`. |
| **Effort** | S (≈0.5 person-day) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-693 (Protection Mechanism Failure) |
| **Likelihood** | MEDIUM (4) |

| Field | Value |
|---|---|
| **Related Findings** | CFG-002, CFG-005 |

**Evidence — `src/backend/config/settings/prod.py:111-113`** *(supports: "the bypass is a plain environment read with no settings-module scoping")*:
```python
_SKIP_SECRET_VALIDATION = bool(
    os.getenv("DJANGO_BUILD") or os.getenv("DJANGO_ONESHOT")
)
```

**Evidence — `src/backend/config/settings/base.py:19-21`** *(supports: "both flags are explicitly allowlisted as legitimate `.env` keys")*:
```python
ALLOWED_ENV_VARS = frozenset({
    # --- Python-consumed (env()/env.*()/os.getenv in base.py & prod.py) ---
    "DJANGO_SECRET_KEY", "DJANGO_SETTINGS_MODULE", "DJANGO_BUILD", "DJANGO_ONESHOT",
```

**Evidence — `src/backend/config/settings/base.py:102-105`** *(supports: "a `.env` file entry is loaded into `os.environ` for the prod settings module, so the flag reaches web and bot")*:
```python
    if "test" not in os.getenv("DJANGO_SETTINGS_MODULE", ""):
        _env_keys_before = set(os.environ)
        environ.Env.read_env(env_path)
        _warn_unknown_env_vars(set(os.environ) - _env_keys_before)
```

**Evidence — controlled prod-settings import with the bypass set and every secret blanked** *(supports: "all eight guards are skipped; production settings import with an empty signing key")*:
```text
--- A: valid prod env ---
PROD OK DEBUG= False HSTS= 31536000 PRELOAD= True SSLREDIR= True
--- B: DJANGO_ONESHOT=1 with EMPTY signing key + missing CSRF/REDIS/EMAIL/SITE_URL ---
PROD IMPORTED WITH BYPASS: SECRET_KEY repr len= 0 DEBUG= False CSRF_TRUSTED_ORIGINS= [] REDIS_URL= ''
```

**Evidence — `docker-compose.prod.yml:11-19,25-28`** *(supports: "the same `.env.prod` file is both `env_file` and the bind-mounted `/app/src/.env` for web and bot, so a file-level flag reaches both processes")*:
```yaml
  web:
    env_file:
      - .env.prod
    volumes:
      - ./.env.prod:/app/src/.env:ro
  bot:
    env_file:
      - .env.prod
    volumes:
      - ./.env.prod:/app/src/.env:ro
```

---

#### CFG-002: [HIGH] — CI `deploy-check` job cannot import `config.settings.prod`; the production config gate never runs

| Field | Value |
|---|---|
| **ID** | CFG-002 |
| **Title** | CI `deploy-check` job cannot import `config.settings.prod`; the production config gate never runs |
| **Severity** | HIGH |
| **Category** | Reliability — validation pipeline |
| **File(s)** | `.github/workflows/ci.yml:508-537`, `src/backend/config/settings/prod.py:203-208`, `src/backend/config/settings/prod.py:246-251` |
| **Status** | Open |
| **Problem** | The `deploy-check` job declares itself as the sole automated verifier that production settings are deploy-clean, and its documentation (`docs/99-agent/rules.md:181`, `docs/ops/docker-deployment.md:427`) states that it sets "all required production env vars … so the full production settings import path is exercised". It sets nine of them but omits `EMAIL_HOST` and `REDIS_URL`, both of which `prod.py` requires whenever `_SKIP_SECRET_VALIDATION` is false. The job therefore aborts at `import django` and `manage.py check --deploy --fail-level WARNING` never executes. |
| **Impact** | The only automated control that would catch a production-configuration regression (weak or blank `SECRET_KEY` → W009, `DEBUG=True` in production → W018, missing HSTS preload → W021, secure-cookie regressions → W012/W016) is inert. Any future edit to `prod.py` that weakens transport security ships undetected, and the `test`-job replacement this gate was created for is no longer running the check either. Because the job fails with a plain `ImproperlyConfigured` rather than a security finding, it also reads as an infrastructure flake and is likely to be ignored or re-run. |
| **Root Cause** | The required-production-variable set lives only implicitly in `prod.py` guard bodies. When two new guards were added (`EMAIL_HOST` on 2026-09-26 in `8be3638`, `REDIS_URL` on 2026-09-27 in `909ad16`) nothing kept the CI environment in sync, because there is no test asserting "the documented deploy-check environment satisfies every `prod.py` guard". |
| **Recommendation** | Add `EMAIL_HOST` and `REDIS_URL` to the `deploy-check` job `env:` block, and add a unit test that imports `config.settings.prod` in a subprocess using exactly the `deploy-check` variable set parsed out of `ci.yml`, so a future guard addition fails loudly in the `unit` job instead of silently neutering the gate. Extracting the shared fixture into a single constant (e.g. `tests/settings_fixtures.py::PROD_ENV`) consumed by both the test and the workflow is the durable form. |
| **Effort** | S (≈0.5 person-day) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-16 (Configuration) |
| **Likelihood** | HIGH (8) |

| Field | Value |
|---|---|
| **Related Findings** | CFG-001 |

**Evidence — `src/backend/config/settings/prod.py:203-208,246-251`** *(supports: "`EMAIL_HOST` and `REDIS_URL` are unconditional requirements once the build/one-shot flags are absent")*:
```python
if not _SKIP_SECRET_VALIDATION:
    if not EMAIL_HOST:  # noqa: F405
        raise ImproperlyConfigured(
            "EMAIL_HOST must be set in production. "
            "Provide it via the .env.prod runtime file."
        )
...
if not _SKIP_SECRET_VALIDATION:
    if not REDIS_URL:  # noqa: F405
        raise ImproperlyConfigured(
            "REDIS_URL must be set in production. "
            "Provide it via the .env.prod runtime file."
        )
```

**Evidence — reproducing the `ci.yml` `deploy-check` environment locally** *(supports: "the job's declared production environment cannot import production settings")*:
```text
--- replicating ci.yml deploy-check env exactly ---
django.core.exceptions.ImproperlyConfigured: EMAIL_HOST must be set in production. Provide it via the .env.prod runtime file.
```

**Evidence — `git blame` on the guards vs. the workflow** *(supports: "the drift was introduced by the two guard commits, after the job was written")*:
```text
$ git blame -L 198,212 --date=short -- src/backend/config/settings/prod.py
8be36387 (2026-09-26 204)     if not EMAIL_HOST:  # noqa: F405
909ad16  (2026-09-27)     REDIS_URL must be set in production.   # via git log -- prod.py
$ git log --oneline -6 -- src/backend/config/settings/prod.py
909ad16 fix(config): add REDIS_URL fail-fast guard in production
8be3638 feat(settings): force console/locmem email backends in dev/test and require EMAIL_HOST in prod
6ef5390 fix(ci): deploy-check runs check --deploy against prod settings (12-OPS-001)
```

---

### MEDIUM

#### CFG-003: [MEDIUM] — Admin password passed as a management-command argument (visible in `ps`/`/proc/*/cmdline`)

| Field | Value |
|---|---|
| **ID** | CFG-003 |
| **Title** | Admin password passed as a management-command argument (visible in `ps`/`/proc/*/cmdline`) |
| **Severity** | MEDIUM |
| **Category** | Security — secret exposure |
| **File(s)** | `docker/entrypoint-create-admin.sh:24-27`, `src/backend/apps/core/management/commands/create_admin_user.py:34-39` |
| **Status** | Open |
| **Problem** | The bootstrap container creates the Django superuser by passing the plaintext admin password as the `--password` command-line argument. Process arguments are world-readable inside the container's PID namespace via `/proc/<pid>/cmdline` and appear verbatim in any `ps`, `top`, or crash-dump capture taken during the container's lifetime. The value is also permanently embedded in the container's runtime argv. |
| **Impact** | Any process that can reach the container's PID namespace — a sidecar, a debugger, an incident-response `docker exec`, or a crash handler that captures argv — can read the Django superuser password in cleartext. The password is a full `is_staff`/`is_superuser` credential for the Django admin, which is the highest-privilege account in the system. The exposure window is short (a one-shot service) which is what keeps this MEDIUM rather than HIGH, but the window is not zero and the blast radius is total. |
| **Root Cause** | The management command takes its credential from the CLI rather than from the process environment, so the natural fix is unavailable without changing the command's contract. |
| **Recommendation** | Read the credential from the environment inside the command: make `--password` optional and fall back to `os.environ.get("ADMIN_PASSWORD")`, then have `entrypoint-create-admin.sh` invoke the command without the flag. Add a `--dry-run` regression test asserting that the resolved password never appears in `sys.argv`. If the CLI form must be kept for local use, add a `manage.py help`-visible note that it must not be used in containers. |
| **Effort** | S (≈0.5 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-214 (Invocation of Process Using Visible Sensitive Information) |
| **Likelihood** | LOW (2) |

| Field | Value |
|---|---|
| **Related Findings** | None |

**Evidence — `docker/entrypoint-create-admin.sh:23-27`** *(supports: "the plaintext password becomes a process argument")*:
```bash
# Run the create_admin_user command with environment variables
exec /opt/venv/bin/python src/backend/manage.py create_admin_user \
    --username "${ADMIN_USERNAME:-admin}" \
    --password "${ADMIN_PASSWORD}" \
    --telegram-id "${ADMIN_TELEGRAM_ID:--1}"
```

**Evidence — `src/backend/apps/core/management/commands/create_admin_user.py:34-39`** *(supports: "the credential has no environment fallback — CLI is the only channel")*:
```python
        parser.add_argument(
            "--password",
            type=str,
            required=True,
            help="Admin password (must be non-empty)",
        )
```

---

#### CFG-004: [MEDIUM] — `EMAIL_BACKEND` is env-overridable in production; transactional email can be routed to stdout

| Field | Value |
|---|---|
| **ID** | CFG-004 |
| **Title** | `EMAIL_BACKEND` is env-overridable in production; transactional email can be routed to stdout |
| **Severity** | MEDIUM |
| **Category** | Security — configuration |
| **File(s)** | `src/backend/config/settings/base.py:391-394`, `src/backend/config/settings/prod.py:203-208`, `src/backend/config/settings/dev.py:66`, `src/backend/config/settings/test.py:69` |
| **Status** | Open |
| **Problem** | `EMAIL_BACKEND` is read from the environment in `base.py` with a permissive default, and `prod.py` never re-pins it. The only production-side mail guard is a non-empty `EMAIL_HOST`, which is satisfied by any string and is entirely irrelevant once the backend is not SMTP. Setting `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` in `.env.prod` therefore produces a fully-valid production configuration in which every transactional message body is written to container stdout. |
| **Impact** | Password-reset links, seller-confirmation messages, alert digests and full support-ticket bodies (user free-text plus identifiers) are written to the JSON log stream instead of being delivered. Anyone with log access — or with read access to `docker logs`, a log aggregator, or an error-reporting backend that captures stdout — can read account-recovery tokens and impersonate a user by completing a password reset, and can read support correspondence. Delivery failures are invisible: the send "succeeds" from the caller's point of view. |
| **Root Cause** | `prod.py` hard-pins `DEBUG` and the transport-security flags but treats the mail backend as ordinary overridable configuration, even though it is the switch that decides whether customer data leaves the system. |
| **Recommendation** | In `prod.py`, re-pin `EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"` unconditionally, exactly as `DEBUG` is pinned, and let `dev.py`/`test.py` keep their console/locmem overrides. If an operator genuinely needs a different production transport (SES, Mailgun), introduce a small `StrEnum` (e.g. `EmailTransport.SMTP`) read from one env var and map it to the backend inside `prod.py`, so the allowed set is closed and validated rather than an arbitrary dotted path. |
| **Effort** | S (≈0.5 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-16 (Configuration) |
| **Likelihood** | LOW (2) |

| Field | Value |
|---|---|
| **Related Findings** | CFG-001 |

**Evidence — `src/backend/config/settings/base.py:391-394`** *(supports: "`EMAIL_BACKEND` is environment-driven with a permissive default and no allow-list")*:
```python
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
```

**Evidence — controlled prod-settings import with the console backend** *(supports: "production settings accept the override, the EMAIL_HOST guard still passes, and the real message body is emitted to stdout")*:
```text
PROD imported OK. EMAIL_BACKEND = django.core.mail.backends.console.EmailBackend
EMAIL_HOST guard value still: smtp.example.com
Date: Sun, 27 Sep 2026 21:48:42 -0000
Message-ID: <179054572213.21316.9542154241472534977@DESKTOP-9NDDTM0>

reset-token-abc123
-------------------------------------------------------------------------------
backend class actually used: EmailBackend
```

---

#### CFG-005: [MEDIUM] — `BOT_USERNAME` placeholder is unvalidated and is persisted into the DB by a migration

| Field | Value |
|---|---|
| **ID** | CFG-005 |
| **Title** | `BOT_USERNAME` placeholder is unvalidated and is persisted into the DB by a migration |
| **Severity** | MEDIUM |
| **Category** | Correctness — configuration |
| **File(s)** | `.env.prod.example:31`, `.env.dev.example:31`, `src/backend/config/settings/base.py:307-309`, `src/backend/config/settings/prod.py:125-150`, `src/backend/apps/core/migrations/0003_add_bot_username.py:13-24,40-46` |
| **Status** | Open |
| **Problem** | `prod.py` runs `_validate_production_secret` over `DJANGO_SECRET_KEY`, `BOT_TOKEN` and `GOOGLE_TRANSLATE_API_KEY`, rejecting `<...>` placeholders and the `dev-only-dummy` sentinel. `BOT_USERNAME` is excluded from that set, yet both `.env.dev.example:31` and `.env.prod.example:31` ship the literal placeholder `<your-bot-username>`, and `base.py:309` gives it an empty-string default rather than making it required. The value is then read by migration `0003_add_bot_username` and written into the `SiteConfig` singleton. |
| **Impact** | A production deployment that fills in every other template value but leaves `BOT_USERNAME` as shipped boots cleanly, passes every secret guard, and passes `check --deploy` — then serves every "write to the seller" button as `https://t.me/<your-bot-username>?start=…`, a dead link. Buyers cannot contact sellers through the primary conversion path and nothing in the logs or health endpoints indicates a problem. The bad value is worse than transient: the migration writes it with `QuerySet.update()`, which bypasses the field's own `RegexValidator("^[A-Za-z0-9_]{3,32}$")`, and it only ever overwrites a row still at the factory default — so correcting `.env.prod` afterwards does **not** repair the stored value, and a Django-admin edit becomes the only remedy. The model validator gives false assurance that the value is well-formed when the write path never checks it. |
| **Root Cause** | Placeholder validation was extended value-by-value as secrets were added, and `BOT_USERNAME` was not added to the list even though it is template-populated and persisted. Separately, the seeding migration uses a bulk `update()` that skips `full_clean()`, so the field validator protects nothing on that path. |
| **Recommendation** | Apply `_validate_production_secret("BOT_USERNAME", BOT_USERNAME)` in `prod.py` alongside the other three, and mirror the dev-side placeholder check from `dev.py`. Change the seeding migration to fetch the row, assign, and `full_clean()` before saving (or call `SiteConfig.objects.filter(pk=1).update()` only with a value that has already passed a `RegexValidator` check), so the persisted value is provably valid. Add a settings test asserting `BOT_USERNAME="<your-bot-username>"` is rejected under both `config.settings.dev` and `config.settings.prod`. |
| **Effort** | S (≈0.5 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-20 (Improper Input Validation) |
| **Likelihood** | MEDIUM (4) |

| Field | Value |
|---|---|
| **Related Findings** | CFG-001, CFG-008 |

**Evidence — `.env.prod.example:30-34`** *(supports: "the template ships an unvalidated placeholder for the value that seeds the contact handle")*:
```dotenv
# Bot username for contact deep-links (without @)
BOT_USERNAME=<your-bot-username>

# Get your bot token from @BotFather. REQUIRED in production.
BOT_TOKEN=<your-bot-token-from-botfather>
```

**Evidence — `src/backend/config/settings/prod.py:153-174`** *(supports: "`BOT_TOKEN` is guarded; the loop that would guard `BOT_USERNAME` does not exist")*:
```python
if not _SKIP_SECRET_VALIDATION:
    if not SECRET_KEY:  # noqa: F405
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set and non-empty in production. ..."
        )
    _validate_production_secret("DJANGO_SECRET_KEY", SECRET_KEY)  # noqa: F405

if not _SKIP_SECRET_VALIDATION:
    if not BOT_TOKEN:  # noqa: F405
        raise ImproperlyConfigured("BOT_TOKEN must be set in production. ...")
    _validate_production_secret("BOT_TOKEN", BOT_TOKEN)  # noqa: F405
# no equivalent block for BOT_USERNAME
```

**Evidence — `src/backend/apps/core/migrations/0003_add_bot_username.py:13-24,40-46`** *(supports: "the value is written by a bulk update that bypasses the field's RegexValidator, and only overwrites the factory default")*:
```python
def seed_bot_username(apps, schema_editor):
    SiteConfig = apps.get_model("core", "SiteConfig")
    from django.conf import settings as dj_settings
    bot_username = getattr(dj_settings, "BOT_USERNAME", "") or "bazuna_bot"
    # Only seed rows that are still at the factory default ...
    SiteConfig.objects.filter(pk=1, bot_username="bazuna_bot").update(
        bot_username=bot_username
    )
...
    validators=[RegexValidator(regex="^[A-Za-z0-9_]{3,32}$", ...)]   # never runs on update()
```

**Evidence — `src/backend/apps/core/templatetags/telegram_tags.py:89`** *(supports: "the stored value is spliced directly into the buyer-facing Telegram deep link")*:
```javascript
var url = 'https://t.me/' + username + '?start=' + encodeURIComponent(el.dataset.start);
```

---

#### CFG-006: [MEDIUM] — A bot-only config error in the shared settings module crash-loops the whole dev stack

| Field | Value |
|---|---|
| **ID** | CFG-006 |
| **Title** | A bot-only config error in the shared settings module crash-loops the whole dev stack |
| **Severity** | MEDIUM |
| **Category** | Availability — configuration coupling |
| **File(s)** | `src/backend/config/settings/dev.py:20-25`, `docker-compose.yml:219-302`, `docker-compose.dev.override.yml:6-42` |
| **Status** | Open |
| **Problem** | The `BOT_TOKEN` placeholder guard lives in `config/settings/dev.py`, which is the settings module imported by **both** the web and the bot processes (both services set `DJANGO_SETTINGS_MODULE=config.settings.dev`). It raises `ImproperlyConfigured` from module scope, i.e. inside `django.setup()`, so a defect in a bot-only credential takes down the web tier as well. Both services carry `restart: unless-stopped`, so the failure presents as an indefinite crash loop rather than a one-shot error. |
| **Impact** | At the time of this audit the local development stack was fully offline for exactly this reason: `mko-bazuna-dev-web-1` and `mko-bazuna-dev-bot-1` were both in `Restarting (1)` state with the same `ImproperlyConfigured` from `dev.py:21`. Neither the website nor the bot is available, no diagnosis is possible from `docker ps` alone, and the developer must read a container log to discover that a bot token placeholder in a gitignored local file is the cause. Because the error is raised at settings-import time, the blast radius of a bot-scoped misconfiguration is the entire application tier — the exact opposite of the "separate what breaks" property that a dual-process design is supposed to provide. |
| **Root Cause** | A credential that only the bot consumes is validated at settings-import time in a settings module shared by both processes, rather than at the point of use (or in a bot-specific settings module), so the two processes cannot fail independently on bot configuration. |
| **Recommendation** | Move the `BOT_TOKEN` placeholder check out of `config/settings/dev.py` into `src/telegram_bot/main.py`, immediately after `token = settings.BOT_TOKEN`, where a bot-only misconfiguration degrades the bot alone and the web tier stays up. Keep the `prod.py` guard as-is (production should still fail fast for all processes, since production runs both tiers from one secret source and a blank key must never reach the web tier). Add a test asserting that importing `config.settings.dev` with a placeholder `BOT_TOKEN` succeeds while `telegram_bot.main` refuses to start. |
| **Effort** | S (≈0.5 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-16 (Configuration) |
| **Likelihood** | HIGH (7) |

| Field | Value |
|---|---|
| **Related Findings** | CFG-005 |

**Evidence — live dev stack state** *(supports: "both processes are crash-looping, not just the bot")*:
```text
$ docker ps --format "{{.Names}}\t{{.Status}}"
mko-bazuna-dev-web-1      mko-bazuna-dev-web    Restarting (1) 42 seconds ago
mko-bazuna-dev-bot-1      mko-bazuna-dev-bot    Restarting (1) 16 seconds ago
```

**Evidence — `docker logs mko-bazuna-dev-web-1`** *(supports: "the web process aborts during settings import on a bot credential")*:
```text
  File "/app/src/backend/manage.py", line 442, in execute_from_command_line
  File "/app/src/backend/config/settings/dev.py", line 21, in <module>
    raise ImproperlyConfigured(
django.core.exceptions.ImproperlyConfigured: BOT_TOKEN is a placeholder value from
.env.dev.example. Replace it with a real token from @BotFather, or leave it empty
(BOT_TOKEN=) to skip bot startup in development.
```

**Evidence — `src/backend/config/settings/dev.py:17-25`** *(supports: "a bot-only credential is validated at shared-module import time")*:
```python
# Fail fast: reject truthy-but-placeholder BOT_TOKEN values. Empty tokens are
# allowed (the bot's `if not token: return` guard skips startup gracefully).
# This is dev-only — prod has its own guard (prod.py:140-145).
if BOT_TOKEN and _BOT_TOKEN_PLACEHOLDER_RE.match(BOT_TOKEN):  # noqa: F405
    raise ImproperlyConfigured(
        "BOT_TOKEN is a placeholder value from .env.dev.example. ..."
    )
```

**Evidence — `docker-compose.dev.override.yml:10-12,34-36`** *(supports: "web and bot share the same dev settings module")*:
```yaml
  web:
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
  bot:
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
```

---

#### CFG-007: [MEDIUM] — `STATICFILES_STORAGE` in `prod.py` is a dead setting removed from Django 5.1+

| Field | Value |
|---|---|
| **ID** | CFG-007 |
| **Title** | `STATICFILES_STORAGE` in `prod.py` is a dead setting removed from Django 5.1+ |
| **Severity** | MEDIUM |
| **Category** | Maintainability — dead config |
| **File(s)** | `src/backend/config/settings/prod.py:224-225`, `src/backend/config/settings/base.py:293-300`, `src/backend/config/settings/test.py:30-46` |
| **Status** | Open |
| **Problem** | `prod.py:225` sets `STATICFILES_STORAGE = "theme.storage.ThemeStaticFilesStorage"`. `STATICFILES_STORAGE` was deprecated in Django 4.2 in favour of `STORAGES["staticfiles"]["BACKEND"]` and removed from `django.conf.global_settings` in Django 5.1. The project pins `Django >=5.2.16,<6.0` (5.2.17 installed), so the setting is never read by any code path. The effective configuration comes from `base.py:293-300`, which already sets `STORAGES["staticfiles"]["BACKEND"]` to the same class. Django accepts arbitrary uppercase module attributes without validating them, so the line is silently inert. |
| **Impact** | No runtime effect today, which is precisely the problem: the file asserts a production decision that is not the one actually in force. A maintainer changing the production static-files backend will edit a line that has no effect, deploy, and discover that hashed-filename behaviour is unchanged. It also misleads `test.py`, whose 30-46 comment reasons at length about "the production/dev storage (`ThemeStaticFilesStorage`)" when that decision is actually owned by `base.py`'s `STORAGES` dict — an indirect coupling that will break confusingly if `prod.py` is ever "fixed" to what it appears to say. |
| **Root Cause** | A Django 4.2-era setting was migrated to `STORAGES` in `base.py` but the legacy key was left behind in the production override during that migration. |
| **Recommendation** | Delete `prod.py:225`. `STORAGES` in `base.py` is already the single source of truth, and the diff is a one-line removal. Add a test that asserts `settings.STORAGES["staticfiles"]["BACKEND"] == "theme.storage.ThemeStaticFilesStorage"` for the prod settings module so the real decision is pinned and the dead key cannot silently return. |
| **Effort** | S (<0.5 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-16 (Configuration) |
| **Likelihood** | LOW (1) |

| Field | Value |
|---|---|
| **Related Findings** | None |

**Evidence — `src/backend/config/settings/prod.py:224-225`** *(supports: "the dead setting")*:
```python
# Static files via whitenoise (with input.css excluded from post-processing)
STATICFILES_STORAGE = "theme.storage.ThemeStaticFilesStorage"
```

**Evidence — `src/backend/config/settings/base.py:293-300`** *(supports: "the live configuration is owned by `STORAGES`, and already names the same class")*:
```python
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "theme.storage.ThemeStaticFilesStorage",
    },
}
```

**Evidence — the setting is absent from the installed Django** *(supports: "`STATICFILES_STORAGE` no longer exists in Django 5.2's global settings, so nothing reads `prod.py:225`")*:
```text
$ uv run python -c "import django; print('Django', django.get_version()); \
    from django.conf import global_settings; \
    print('global_settings has STATICFILES_STORAGE:', hasattr(global_settings,'STATICFILES_STORAGE'))"
Django 5.2.17
global_settings has STATICFILES_STORAGE: False
```

---

### LOW

#### CFG-008: [LOW] — `RUN_TRANSLATION_BACKFILL` is absent from `ALLOWED_ENV_VARS` and from all env templates

| Field | Value |
|---|---|
| **ID** | CFG-008 |
| **Title** | `RUN_TRANSLATION_BACKFILL` is absent from `ALLOWED_ENV_VARS` and from all env templates |
| **Severity** | LOW |
| **Category** | Observability — dead config |
| **File(s)** | `src/backend/apps/core/utils/migrate_locked.py:57`, `src/backend/config/settings/base.py:19-38`, `src/backend/config/settings/tests/test_env_allowlist.py:45-70` |
| **Status** | Open |
| **Problem** | `RUN_TRANSLATION_BACKFILL` is a documented, operator-facing switch read via `os.getenv` in `migrate_locked.py:57` and described across five documentation files, but it is not present in `ALLOWED_ENV_VARS` and not present in any of the four `.env*.example` templates. The allowlist's whole purpose is to warn on `.env` keys the code does not recognise, so the documented variable is indistinguishable from a typo. |
| **Impact** | An operator who follows the documented procedure — adding `RUN_TRANSLATION_BACKFILL=true` to `.env.prod` — gets an `Unknown env var … (possible typo; value will be ignored by env() calls)` WARNING at every container boot, worded exactly like a genuine mistake. The warning is factually wrong for this key. The damage is alert fatigue on the one mechanism that detects silently-ignored secret names, which is the mechanism's only purpose; after a few such warnings the boot log stops being read, and a real `BOT_T0KEN` typo would go unnoticed. |
| **Root Cause** | The allowlist is maintained by hand and validated in only one direction: `test_example_keys_in_allowlist` asserts `example_keys ⊆ ALLOWED_ENV_VARS`, so a variable that exists in code but not in any template is never detected. |
| **Recommendation** | Add `"RUN_TRANSLATION_BACKFILL"` to `ALLOWED_ENV_VARS` and document it in `.env.prod.example` next to the `migrate` service notes. Add a companion test that asserts the reverse direction too — every `os.getenv`/`env()` name in non-test `src/**` is in `ALLOWED_ENV_VARS` — so the next operator-facing flag is covered automatically instead of by recall. |
| **Effort** | S (<0.5 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-16 (Configuration) |
| **Likelihood** | HIGH (8) |

| Field | Value |
|---|---|
| **Related Findings** | CFG-005, CFG-009 |

**Evidence — `src/backend/apps/core/utils/migrate_locked.py:52-59`** *(supports: "the variable is a real, consumed, documented switch")*:
```python
    if os.getenv("RUN_TRANSLATION_BACKFILL") == "true":
        steps_list.append(("backfill_translations",))
        logger.info("Translation backfill enabled (RUN_TRANSLATION_BACKFILL=true)")
```

**Evidence — the warning the allowlist emits for it** *(supports: "a documented key is reported with the same wording as a typo, so the check is misleading rather than helpful")*:
```text
--- simulating an operator adding RUN_TRANSLATION_BACKFILL=true to .env.prod ---
WARNING config.settings.base: Unknown env var 'RUN_TRANSLATION_BACKFILL' loaded from .env
        - not in ALLOWED_ENV_VARS (possible typo; value will be ignored by env() calls).
--- simulating a typo (BOT_T0KEN) for contrast ---
WARNING config.settings.base: Unknown env var 'BOT_T0KEN' loaded from .env
        - not in ALLOWED_ENV_VARS (possible typo; value will be ignored by env() calls).
```

**Evidence — static diff of consumed vs. allowlisted env names** *(supports: "`RUN_TRANSLATION_BACKFILL` is the only genuinely consumed name missing from the allowlist")*:
```text
=== env() consumed in non-test Python (35 names) ===
... REDIS_URL, RUN_TRANSLATION_BACKFILL, SCHEDULER_COMMAND_TIMEOUT, SENTRY_DSN, SITE_URL
=== union minus allowlist ===
BASH_SOURCE  PYTEST_MARK_ARGS  PYTEST_OPTS  PYTEST_SKIP_MARKERS
RUN_TRANSLATION_BACKFILL  SCRIPT_DIR  stale
```

---

#### CFG-009: [LOW] — `.env.example` omits 19 consumed variables including the whole `EMAIL_*` block

| Field | Value |
|---|---|
| **ID** | CFG-009 |
| **Title** | `.env.example` omits 19 consumed variables including the whole `EMAIL_*` block |
| **Severity** | LOW |
| **Category** | Maintainability — template gap |
| **File(s)** | `.env.example:1-90`, `src/backend/config/settings/base.py:385-402`, `src/backend/config/settings/tests/test_env_allowlist.py:45-55` |
| **Status** | Open |
| **Problem** | `.env.example` is headed "Comprehensive environment variables template for Mko Bazuna" but is missing 19 variables the code actually reads, including `EMAIL_HOST` — which `prod.py:203-208` treats as mandatory in production — plus `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`, `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `SUPPORT_NOTIFICATION_RECIPIENTS`, `POSTGRES_HOST`, `POSTGRES_PORT`, `DATABASE_URL`, `BOT_LIVENESS_FILE`, `BOT_HEALTH_STALE_SECONDS`, `BOT_HEALTH_CHECK_ENABLED`, `SCHEDULER_LIVENESS_FILE`, `SCHEDULER_COMMAND_TIMEOUT` and `PROMETHEUS_MULTIPROC_DIR`. `.env.prod.example` is missing 9 more of the same (notably `EMAIL_BACKEND`). |
| **Impact** | Anyone treating the "comprehensive" template as the reference for what a deployment must set will produce a `.env.prod` that fails the production boot with an `ImproperlyConfigured` naming a variable they were never shown. Because the drift is one-directional and no test checks it, the gap persists silently and grows with every new env-backed setting. No runtime exposure — the missing values fail loudly at boot rather than defaulting. |
| **Root Cause** | The template was not updated when the email, Redis-health and liveness settings were added, and the only template/allowlist test asserts the wrong direction to catch it. |
| **Recommendation** | Either add the missing blocks to `.env.example` (or delete the file and point the header at the three tier templates, which are the ones actually used) and add a test asserting `consumed_env_names ⊆ keys(.env.example)`, or explicitly document `.env.example` as a non-authoritative overview and remove the word "Comprehensive". The test is the durable half of the fix and is shared with CFG-008. |
| **Effort** | S (<0.5 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-16 (Configuration) |
| **Likelihood** | MEDIUM (4) |

| Field | Value |
|---|---|
| **Related Findings** | CFG-008 |

**Evidence — `.env.example:1-9`** *(supports: "the file presents itself as the authoritative reference")*:
```dotenv
# .env.example — Comprehensive environment variables template for Mko Bazuna
#
# Copy the appropriate template to create your .env.<tier> file:
#   cp .env.dev.example .env.dev     # development (Docker)
#   cp .env.prod.example .env.prod   # production (Docker)
#   cp .env.test.example .env.test   # testing (Docker)
```

**Evidence — template-vs-code name diff** *(supports: "19 consumed variables are absent, including the production-mandatory `EMAIL_HOST`")*:
```text
=== consumed-by-code/env-file vars MISSING from .env.example ===
DATABASE_URL  POSTGRES_HOST  POSTGRES_PORT
BOT_LIVENESS_FILE  BOT_HEALTH_STALE_SECONDS  BOT_HEALTH_CHECK_ENABLED
SCHEDULER_LIVENESS_FILE  SCHEDULER_COMMAND_TIMEOUT
EMAIL_HOST  EMAIL_PORT  EMAIL_HOST_USER  EMAIL_HOST_PASSWORD  EMAIL_USE_TLS
EMAIL_TIMEOUT  EMAIL_BACKEND  DEFAULT_FROM_EMAIL  SUPPORT_NOTIFICATION_RECIPIENTS
PROMETHEUS_MULTIPROC_DIR
=== .env.prod.example missing (of consumed) ===
DATABASE_URL  POSTGRES_PORT  BOT_LIVENESS_FILE  BOT_HEALTH_STALE_SECONDS
BOT_HEALTH_CHECK_ENABLED  SCHEDULER_LIVENESS_FILE  SCHEDULER_COMMAND_TIMEOUT
EMAIL_BACKEND  SEED_USERS  SEED_ADS
```

**Evidence — `src/backend/config/settings/tests/test_env_allowlist.py:49-55`** *(supports: "only the reverse direction is gated, so this class of drift is invisible")*:
```python
def test_example_keys_in_allowlist(filename: str) -> None:
    """Every KEY= in a tracked .env.*.example template is allowlisted."""
    missing = _example_keys(filename) - ALLOWED_ENV_VARS
    assert not missing, (
        f"{filename} keys not in ALLOWED_ENV_VARS: {sorted(missing)}"
    )
```

---

#### CFG-010: [LOW] — `test.py` does not reset `SECURE_HSTS_*`, contradicting its own "mirrors dev" comment

| Field | Value |
|---|---|
| **ID** | CFG-010 |
| **Title** | `test.py` does not reset `SECURE_HSTS_*`, contradicting its own "mirrors dev" comment |
| **Severity** | LOW |
| **Category** | Maintainability — environment separation |
| **File(s)** | `src/backend/config/settings/test.py:18-24`, `src/backend/config/settings/dev.py:49-52`, `src/backend/config/settings/base.py:156-160` |
| **Status** | Open |
| **Problem** | `test.py:18-24` states that its TLS block "Mirrors config/settings/dev.py (test settings must behave like dev, not prod)" and resets `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` — but it omits the HSTS block that `dev.py:49-52` explicitly zeroes. The test environment therefore inherits `SECURE_HSTS_SECONDS = 3600` and `SECURE_HSTS_INCLUDE_SUBDOMAINS = True` from `base.py:158-159`. |
| **Impact** | No effect on the pytest suite, whose client is not subject to browser HSTS caching. The risk is to a human or browser-driven tool that points at a test-mode server: after one request the browser caches `Strict-Transport-Security: max-age=3600; includeSubDomains` for the test host, and every `http://<test-host>` request for the next hour is upgraded to HTTPS, which the test server does not serve. That is a confusing, self-inflicted failure that looks like an application bug. It also means the three environment modules are no longer consistent with each other, which is the invariant the comment asserts. |
| **Root Cause** | `test.py` was derived from `dev.py` field by field and the HSTS triple was missed; nothing in the test suite compares the three modules for transport-setting equality. |
| **Recommendation** | Add the three HSTS lines to `test.py`, mirroring `dev.py:50-52` (`SECURE_HSTS_SECONDS = 0`, `SECURE_HSTS_INCLUDE_SUBDOMAINS = False`, `SECURE_HSTS_PRELOAD = False`). Optionally add a small settings test that asserts the transport-security tuple (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`) is identical between `config.settings.dev` and `config.settings.test`, which makes the comment's claim machine-checked instead of aspirational. |
| **Effort** | S (<0.5 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-16 (Configuration) |
| **Likelihood** | LOW (2) |

| Field | Value |
|---|---|
| **Related Findings** | None |

**Evidence — `src/backend/config/settings/test.py:18-24`** *(supports: "the TLS block claims to mirror dev but stops before the HSTS block")*:
```python
# Disable SSL/TLS redirect and secure cookies for the test client, which issues
# plain HTTP requests. Without this, SecurityMiddleware 301-redirects every
# request to HTTPS and breaks all DB-backed view tests.
# Mirrors config/settings/dev.py (test settings must behave like dev, not prod).
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
# <no SECURE_HSTS_* overrides follow>
```

**Evidence — measured per-environment values** *(supports: "test inherits a 1-hour HSTS policy with includeSubDomains, dev does not")*:
```text
$ uv run python -c "import config.settings.test as s; print('TEST OK DEBUG=',s.DEBUG,'HSTS=',s.SECURE_HSTS_SECONDS,'SSLREDIR=',s.SECURE_SSL_REDIRECT)"
TEST OK DEBUG= True HSTS= 3600 SSLREDIR= False CACHE= ...locmem.LocMemCache
$ uv run python -c "import config.settings.dev as s; print('DEV OK DEBUG=',s.DEBUG,'HSTS=',s.SECURE_HSTS_SECONDS,'SSLREDIR=',s.SECURE_SSL_REDIRECT)"
DEV OK DEBUG= True HSTS= 0 SSLREDIR= False COOKIE= False EMAIL= ...console.EmailBackend
```

---

#### CFG-011: [LOW] — `base.py` comment cites a non-existent "Env schema" for `BOT_TOKEN` validation

| Field | Value |
|---|---|
| **ID** | CFG-011 |
| **Title** | `base.py` comment cites a non-existent "Env schema" for `BOT_TOKEN` validation |
| **Severity** | LOW |
| **Category** | Maintainability — stale documentation |
| **File(s)** | `src/backend/config/settings/base.py:116-118` |
| **Status** | Open |
| **Problem** | `base.py:116` comments the `BOT_TOKEN` setting as "required for bot process, validated via Env schema". No such schema exists anywhere in the repository — there is no `pydantic_settings.BaseSettings` subclass and no `Env` model. Validation is hand-rolled in two places with two different implementations: `_SECRET_PLACEHOLDER_RE` plus `_validate_production_secret` in `prod.py:16,125-150`, and `_BOT_TOKEN_PLACEHOLDER_RE` in `dev.py:15,20-25`. |
| **Impact** | A maintainer extending validation to another setting (exactly the change CFG-005 requires) will look for the schema the comment points at, find nothing, and has to re-derive the mechanism from two partially-duplicated implementations before making the edit. This is a small cost, but it is paid at precisely the moment a security control is being changed, and it is the kind of comment that leads a reviewer to believe the codebase is more centralised than it is. |
| **Root Cause** | The comment predates or anticipates a Pydantic-settings refactor that was never performed; the two regexes were then written separately in `dev.py` and `prod.py`, with `dev.py:14` explicitly noting the copy ("Copied from prod._SECRET_PLACEHOLDER_RE to avoid importing prod settings"). |
| **Recommendation** | Correct the comment to name the actual mechanism and its two locations. Longer term, extract the placeholder/dummy detection into one shared helper in `config/settings/` (or a small Pydantic v2 model, which would also satisfy the project's stated Pydantic-v2-at-boundaries rule) and have both `dev.py` and `prod.py` call it, eliminating the duplicated regex and the copied-constant maintenance hazard. |
| **Effort** | S (<0.5 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-16 (Configuration) |
| **Likelihood** | LOW (1) |

| Field | Value |
|---|---|
| **Related Findings** | CFG-005 |

**Evidence — `src/backend/config/settings/base.py:116-118`** *(supports: "the comment points at a validation mechanism that does not exist")*:
```python
# Telegram bot token (required for bot process, validated via Env schema)
# Allow empty string for development when bot is not needed
BOT_TOKEN = env("BOT_TOKEN", default="")
```

**Evidence — `src/backend/config/settings/dev.py:12-15`** *(supports: "validation is a duplicated local regex, not a shared schema")*:
```python
# Matches values shipped as templates in .env.*.example files, e.g.
# <your-bot-token-from-botfather>. Copied from prod._SECRET_PLACEHOLDER_RE
# to avoid importing prod settings (which carry logging/Sentry config).
_BOT_TOKEN_PLACEHOLDER_RE = re.compile(r"^<[^>]+>$")
```

**Evidence — repository-wide search for the claimed schema** *(supports: "no `BaseSettings` / settings-schema class exists")*:
```text
$ grep -rn "BaseSettings|pydantic_settings" --include=*.py src/
(no matches — the only Pydantic models in src/ are BaseInputModel (core/schemas.py:17),
AutocompleteSuggestion (search/schemas.py:17) and CSPReportPayload (core/views.py:21))
```

---

## Cross-Finding Analysis

- **Merge candidates:** CFG-008 and CFG-009 share one root cause — the env-var allowlist and
  the `.env` templates are maintained by hand and only validated in the
  `example_keys ⊆ ALLOWED_ENV_VARS` direction, so drift in the other direction is
  undetectable. They are kept separate because the fixes are different (a new test
  direction plus an allowlist entry, versus a template rewrite plus a scope decision),
  but they should be remediated together and the new test should cover both.
  CFG-005 and CFG-011 additionally overlap: CFG-011's shared-helper recommendation is
  the natural home for the `BOT_USERNAME` validation CFG-005 requires.
- **Conflicting evidence:** None. No two findings rest on contradictory observations.
  CFG-002 is the closest to a boundary case — it is reported as a *pipeline* defect
  rather than a settings defect because `prod.py` is behaving exactly as documented;
  the defect is that the environment validating it has drifted from the requirement set.
- **Dependency chains:** CFG-001 must be fixed before CFG-002 can be trusted, because
  adding `EMAIL_HOST`/`REDIS_URL` to the `deploy-check` job achieves nothing while a
  `DJANGO_ONESHOT` value could still bypass the guards. CFG-005 should be implemented on
  top of CFG-011's shared helper, or the regex will be duplicated a third time.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | CFG-001 | HIGH | S | P0 | Scope the `DJANGO_ONESHOT`/`DJANGO_BUILD` bypass out of `config.settings.prod` (or move one-shot services to a dedicated `bootstrap` settings module) |
| 2 | CFG-002 | HIGH | S | P0 | Add `EMAIL_HOST` and `REDIS_URL` to the `deploy-check` job and gate it with a test that imports `config.settings.prod` from the workflow's own variable set |
| 3 | CFG-006 | MEDIUM | S | P1 | Move the `BOT_TOKEN` placeholder check from `config/settings/dev.py` into `telegram_bot/main.py` so a bot-only misconfiguration cannot take the web tier down |
| 4 | CFG-005 | MEDIUM | S | P1 | Validate `BOT_USERNAME` against placeholders in dev and prod, and make migration `0003` validate before writing |
| 5 | CFG-004 | MEDIUM | S | P1 | Re-pin `EMAIL_BACKEND` in `prod.py` (or map a `StrEnum` transport choice to a closed set of backends) |
| 6 | CFG-003 | MEDIUM | S | P1 | Have `create_admin_user` read `ADMIN_PASSWORD` from the environment instead of `--password` argv |
| 7 | CFG-007 | MEDIUM | S | P2 | Delete the dead `STATICFILES_STORAGE` line from `prod.py` and pin the real `STORAGES` value with a test |
| 8 | CFG-008 | LOW | S | P2 | Allowlist `RUN_TRANSLATION_BACKFILL`, document it in `.env.prod.example`, and add the reverse-direction allowlist test |
| 9 | CFG-009 | LOW | S | P2 | Reconcile `.env.example` with the consumed variable set (or drop the "comprehensive" claim) under the same new test |
| 10 | CFG-010 | LOW | S | P2 | Add the `SECURE_HSTS_*` overrides to `test.py` and assert dev/test transport parity |
| 11 | CFG-011 | LOW | S | P2 | Fix the `base.py:116` comment and extract the duplicated placeholder regex into one shared helper |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| CFG-001 | Med — removing the bypass from `prod.py` will make the dev one-shot services fail if they are ever pointed at prod settings without `DJANGO_ONESHOT`; the dev override sets it on all five, but a local `docker compose -f base -f prod` mix-up would surface as a boot error rather than a silent one | Yes | Assert `DJANGO_ONESHOT=1` + `config.settings.prod` + blank `SECRET_KEY` still raises; assert all five one-shot services still import with the flag under a dev settings module |
| CFG-002 | Low — CI-only change; the added values are non-secret placeholders | Yes | A subprocess import of `config.settings.prod` using the `deploy-check` variable set, so a future guard addition fails the `unit` job |
| CFG-003 | Low — the entrypoint and the command change together; the empty-password skip path must be preserved | Yes | `create_admin_user` resolves the password with `--password` absent and with `ADMIN_PASSWORD` absent-and-empty |
| CFG-004 | Med — re-pinning `EMAIL_BACKEND` in prod will break any deployment that currently relies on the env override to reach a non-SMTP transport; such a deployment would need the `StrEnum` path instead | Yes | `settings.EMAIL_BACKEND` is the SMTP backend under `config.settings.prod` even when the env var is set to the console backend |
| CFG-005 | Med — a deployment currently running with a real `BOT_USERNAME` is unaffected, but any DB already seeded with a placeholder needs a data fix, not just an env fix | Yes | Placeholder `BOT_USERNAME` rejected in dev and prod; migration `0003` refuses to write a value failing the `RegexValidator` |
| CFG-006 | Med — moving the guard means `config.settings.dev` now imports with a placeholder `BOT_TOKEN`; anything that relied on the import-time rejection (including three existing settings tests) must be updated to assert on the bot entrypoint instead | Yes | `import config.settings.dev` succeeds with a placeholder token; `telegram_bot.main.main()` refuses to start; the three `test_settings_secrets.py` placeholder tests retarget |
| CFG-007 | Low — one-line deletion; `STORAGES` already carries the same value | Yes | `settings.STORAGES["staticfiles"]["BACKEND"]` is `theme.storage.ThemeStaticFilesStorage` under prod settings |
| CFG-008 | Low — allowlist and template additions only | Yes | `test_example_keys_in_allowlist` still passes; new reverse-direction test passes with no further gaps |
| CFG-009 | Low — documentation/template change | Yes | Reverse-direction template test passes; no allowlist test regresses |
| CFG-010 | Low — three added assignments in the test settings module | Yes | dev/test transport tuple parity assertion; the existing suite already runs with `SECURE_SSL_REDIRECT = False` |
| CFG-011 | Low — comment text plus a shared-helper extraction | Yes | Existing placeholder tests pass unchanged against the shared helper |

## Appendices

### Appendix A — Full reproduction of the CFG-001 bypass

Environment: `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DJANGO_ONESHOT=1`,
`DJANGO_SECRET_KEY=` (present but empty), `BOT_TOKEN=`,
`GOOGLE_TRANSLATE_API_KEY=`, `SITE_URL` unset, `CSRF_TRUSTED_ORIGINS=`,
`REDIS_URL=`, `EMAIL_HOST=`, `ALLOWED_HOSTS=example.com`, `POSTGRES_PASSWORD` set.

```text
$ uv run python -c "import config.settings.prod as s; \
    print('PROD IMPORTED WITH BYPASS: SECRET_KEY repr len=', len(s.SECRET_KEY), \
          'DEBUG=', s.DEBUG, 'CSRF_TRUSTED_ORIGINS=', s.CSRF_TRUSTED_ORIGINS, \
          'REDIS_URL=', repr(s.REDIS_URL))"
PROD IMPORTED WITH BYPASS: SECRET_KEY repr len= 0 DEBUG= False CSRF_TRUSTED_ORIGINS= [] REDIS_URL= ''

$ uv run python -c "import django; django.setup(); print(settings.SECRET_KEY == '')"
  File ".../django/conf/__init__.py", line 90, in __getattr__
    raise ImproperlyConfigured("The SECRET_KEY setting must not be empty.")
django.core.exceptions.ImproperlyConfigured: The SECRET_KEY setting must not be empty.
```

Both production settings import **succeed** and the first runtime access to the signing
key fails. Note that `check --deploy` would report W009 for the empty key, but
`docker/entrypoint.sh:93-97` runs it with `|| echo "WARNING: … (non-fatal at boot)"`, so
the container starts and serves 500s.

*(supports the claim: "a single `DJANGO_ONESHOT=1` line in `.env.prod` converts a
fail-fast boot into a runtime outage with no fatal signal")*
