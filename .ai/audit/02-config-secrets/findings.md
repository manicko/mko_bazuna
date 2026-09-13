# Audit Findings — Config & Secrets Management

**Phase:** 02 — Config & Secrets
**Date:** 2026-09-12
**Auditor:** Executor (subagent)
**Status:** problems-only · validated: no (draft)

---

## Summary

This phase audited the configuration layer of the two-process Mko Bazuna system
(Django web + aiogram bot, one shared PostgreSQL DB) against the mandatory runtime
verification (R1–R6) and the audit dimensions (config-model correctness,
secret management, environment separation, boot-time secret validation,
config-to-consumer flow, dead-config/unknown-key rejection).

The configuration architecture is fundamentally sound: settings are split into
`base`/`dev`/`test`/`prod` (Django 5.2.16, `django-environ`), secrets are sourced
exclusively from a single bind-mounted `.env` (`/app/src/.env`, sourced from the
gitignored `.env.docker` via `--env-file`), real env files are correctly git-ignored
and docker-ignored, every env var is consumed (no dead config), the enum
registry (`apps.core.enums` / `apps.lookups.enums` — `StrEnum`, 70+ usages) is not
bypassed by magic strings in sampled views, and prod fail-fast guards reject
missing/empty `DJANGO_SECRET_KEY`, `BOT_TOKEN`, `GOOGLE_TRANSLATE_API_KEY`,
`SITE_URL`, and `ALLOWED_HOSTS` with value-free error messages.

Three deviations were found. **One is critical** (a real signing key committed to
VCS), **one is high** (a compose guard breaks the documented dev startup), and
**one is low** (missing Django deploy check backstop). All other R1–R6 checks
passed and are summarized in *Runtime Verification*.

---

## Findings

### Finding 1 — [CRITICAL] — Real `DJANGO_SECRET_KEY` committed in a test file

| Field | Value |
|---|---|
| **Severity** | CRITICAL |
| **Category** | Security (secret in VCS) |
| **File(s)** | `src/backend/config/settings/tests/test_settings_secrets.py:139,145` |
| **Problem** | The regression test `test_secret_key_with_dollar_sign_preserved` hardcodes the genuine `DJANGO_SECRET_KEY` value instead of a test-only dummy. |
| **Impact** | A Django secret signing key is committed to version control. The value is identical to the key currently configured in the gitignored runtime files (`.env`, `.env.docker`, `.env.local`). Anyone with repo access can forge Django-signed tokens (session cookies, CSRF tokens, password-reset tokens) for any environment that used this key. After rotation, all existing signed tokens for the rotated key are invalidated. |
| **Root Cause** | Commit `bae31ac` ("fix(config): escape DJANGO_SECRET_KEY to prevent Docker Compose interpolation") added a regression test for the `$xp` single-quote-preservation behavior. The author copy-pasted their real local key into the test data instead of using an obviously-fake test value. The test only needs a string containing `$` (and other interpolation-sensitive characters); the actual key material is irrelevant to what it asserts. |
| **Recommendation** | (1) **Mandatory:** treat the committed value as compromised and **rotate `DJANGO_SECRET_KEY`** across every environment that may have used it (local `.env`/`.env.docker`/`.env.local`, plus the VPS `secrets/.env.docker` if the same key was reused — check before assuming it differs from prod). (2) **Fix the test:** replace the hardcoded value with a test-only dummy that still exercises `$` preservation, e.g. `"DJANGO_SECRET_KEY='=t\$t-key-with-\$dollar\$ign\$chars'\n"` and assert against the matching unquoted form. Remove all real key material from the test module. |
| **Evidence** | `git grep "0y-)6rzn_dfoe"` returns exactly 2 matches, both in the committed test file: line 139 (`"DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'\n"`) and line 145 (the asserted value). The identical value appears in the gitignored runtime files `.env:6`, `.env.docker:6`, `.env.local:7`. `git ls-files --error-unmatch src/backend/config/settings/tests/test_settings_secrets.py` succeeds ⇒ the file (and thus the key) is tracked/committed. R3 scan (`git grep` for AKIA/ghp/sk-AIza/Telegram `id:token` patterns across all committed non-`.example` files) found no other real secrets — the leak is isolated to this one test. |

```python
# src/backend/config/settings/tests/test_settings_secrets.py:136-146  (excerpt)
def test_secret_key_with_dollar_sign_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'\n"
    )
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    environ.Env.read_env(env_file, overwrite=True)

    assert os.environ["DJANGO_SECRET_KEY"] == (
        "=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+"
    )

# Runtime files (gitignored, but identical to the committed value):
# .env:6            DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'
# .env.docker:6     DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'
# .env.local:7      DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'
```

---

### Finding 2 — [HIGH] — `ADMIN_PASSWORD` compose `:?` guard contradicts the graceful-skip design and breaks `make up`

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Category** | Operational reliability / correctness (deployment-blocking) |
| **File(s)** | `docker-compose.yml:126` (`:?` guard); `docker-compose.yml:133` ("Skipped if…" comment); `docker/entrypoint-create-admin.sh:17-21` (skip-on-empty); `src/backend/.../create_admin_user.py:67-71` (rejects empty); `.env.docker.example:69` (ships empty) |
| **Problem** | Three layers of the `create_admin` one-shot contradict each other on the empty-`ADMIN_PASSWORD` policy: compose uses `${ADMIN_PASSWORD:?…}` (hard-fails on empty), the entrypoint + compose comment say "skip if empty", and the management command rejects empty passwords. Because compose evaluation happens before any container starts, the `:?` wins and the graceful-skip code is unreachable dead code. |
| **Impact** | With `ADMIN_PASSWORD` empty — which is exactly what is shipped by `.env.docker.example` (`:69: ADMIN_PASSWORD=`) and present in the local `.env.docker` — `docker compose config` (and therefore `make up` / `docker compose up`) **fails before any container starts**, with a cryptic interpolation error. The documented "Skipped if ADMIN_PASSWORD not set" behaviour cannot be exercised; there is no way to opt out of admin creation via an empty value. The primary dev startup path is blocked. |
| **Root Cause** | The `:?` form was chosen to "fail fast", but `create_admin` is a one-shot whose entrypoint was explicitly written to tolerate a missing password (skip + `exit 0`). The `:?` guard makes the skip branch unreachable. The intent was never reconciled with the compose interpolation guard. |

```bash
# Reproduced (default empty ADMIN_PASSWORD in .env.docker):
$ docker compose --env-file .env.docker \
    -f docker-compose.yml -f docker-compose.dev.override.yml config
error while interpolating services.create_admin.environment.[
]: required variable ADMIN_PASSWORD is missing a value: ADMIN_PASSWORD must be set
```

```yaml
# docker-compose.yml:125-133  (contradiction in four consecutive lines)
      - ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}   # <-- hard-fails empty
      - ADMIN_TELEGRAM_ID=${ADMIN_TELEGRAM_ID:--1}
    # Skipped if ADMIN_PASSWORD not set (empty string)                    # <-- promises skip
```

```bash
# docker/entrypoint-create-admin.sh:17-21  (unreachable dead code)
if [ -z "${ADMIN_PASSWORD}" ]; then
    echo "ADMIN_PASSWORD not set, skipping admin user creation"
    exit 0          # never reached: compose config fails first
fi
```

| **Recommendation** | Reconcile the policy to one of two consistent states. **Preferred (matches the existing skip semantics):** drop the `:?` to `ADMIN_PASSWORD=${ADMIN_PASSWORD:-}` (empty-default, no fail) so compose resolves to `""` and `entrypoint-create-admin.sh` executes its documented skip branch; delete the misleading "Must be non-empty" comment in `.env.docker.example` and the "Password cannot be empty" `CommandError` stays as a defensive backstop in the command itself. **Alternative (if admin must always exist):** keep `:?`, but remove the skip-on-empty entrypoint branch + its comment, and ship `.env.docker.example` with a clearly-marked non-empty placeholder so `make up` works out of the box — at the cost of a default credential. Either way, the three layers must agree. |
| **Evidence** | Empirically reproduced above. Cross-file contradiction: `docker-compose.yml:126` vs `:133`, `entrypoint-create-admin.sh:18-20`, `create_admin_user.py:68-71`, `.env.docker.example:69`. |

---

### Finding 3 — [LOW] — No `check --deploy` backstop; weak/placeholder `SECRET_KEY` accepted at boot

| Field | Value |
|---|---|
| **Severity** | LOW |
| **Category** | Security / observability (missing boundary validation) |
| **File(s)** | `.env.docker.example:14` & `.env.example:13` (placeholder key, 44 chars); `docker-compose.yml:122` (`${DJANGO_SECRET_KEY:?…}` accepts non-empty placeholder); entrypoints + Dockerfile + `.github/workflows/ci.yml` (no `check --deploy`) |
| **Problem** | The `DJANGO_SECRET_KEY` guard is `${…:?}` which rejects only **empty/unset** values, not **weak/placeholder** values. The templates ship `DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>` — a non-empty 44-character string — which passes the `:?` guard and boots Django with a known, weak signing key. Django's own deploy check `security.W025` (firing on keys < 50 chars) would catch this, but `manage.py check --deploy` is never invoked at boot or in CI. |
| **Impact** | An operator who deploys the template verbatim (forgetting to generate a real key) silently boots production with a publicly-known signing key, enabling session/CSRF/password-reset token forgery. The project's hardening research (`docs/96-researches/security-config-hardening-research.md`, `admin-auth-separation-research.md`) already flagged the placeholder/weak-key concern; the `:?` fix closed the *empty* gap but not the *weak-placeholder* gap. |
| **Root Cause** | `${VAR:?}` cannot validate secret strength — it only checks presence. Django's strength validation lives in the `W025` deploy check, which requires an explicit `check --deploy` invocation that the project never performs. |

```bash
# Django 5.2 W025 fires on the template placeholder (len=44 < SECRET_KEY_MIN_LENGTH=50):
$ python manage.py check --deploy -t security
?: (security.W025) Your SECRET_KEY has less than 50 characters, less than 5 unique
characters, or it's prefixed with 'django-insecure-' ...    System check identified 1 issue.
# But no entrypoint/Dockerfile/CI step runs this:
$ git grep -nE -- 'manage\.py check|check --deploy|--deploy' \
    -- docker/entrypoint*.sh docker/Dockerfile .github/workflows/*.yml
(no matches)
```

| **Recommendation** | Add a non-fatal deploy check as a visibility backstop, not as startup-blocking validation (so it can't block boot for a deploy warning). **Recommended:** add a CI job step `uv run python manage.py check --deploy` (warnings-only, non-blocking) so weak config surfaces in PR checks; optionally run it in a non-fatal way inside `entrypoint.sh` after migrations. This complements — and does not replace — the `:?` guards and the operator instruction to `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`. |
| **Evidence** | Django source `.venv/.../django/core/checks/security/base.py:22-23` (`SECRET_KEY_MIN_LENGTH = 50`), `:207 def _check_secret_key`, `:216 def check_secret_key`, `:142 W025`. Empirically: `manage.py check --deploy -t security` emits W025 for the template placeholder; `git grep` for `check --deploy`/`manage.py check`/`--deploy` across `docker/entrypoint*.sh`, `docker/Dockerfile`, and `.github/workflows/*.yml` returns no matches. CI (`ci.yml`) runs only ruff / basedpyright / djlint / pytest. |

---

## Runtime Verification (R1–R6)

Evidence gathered during this audit run (local venv at `.venv`, Python 3.14 /
Django 5.2.16; test DB via `docker compose --project-name mko-bazuna-test`).

| ID | Check | Command / method | Result |
|---|---|---|---|
| R1 | Settings import per environment, no import-time side effects | `DJANGO_SETTINGS_MODULE=config.settings.{test\|dev\|prod}` → `django.setup()` with `PYTHONPATH=src;src/backend` and controlled env | **PASS** — test (DEBUG=True, LocMemCache, `BOT_LIVENESS_FILE=''`), dev (DEBUG=True, no SSL redirect), prod (DEBUG=False, HSTS=31536000, HSTS_PRELOAD=True, secure cookies) all import cleanly. Import configures `DATABASES`/`CACHES` lazily (no DB access), no secret logging. |
| R2 | Missing/empty required secret fails fast, no leaked value | prod settings with `DJANGO_SECRET_KEY`/`BOT_TOKEN`/`GOOGLE_TRANSLATE_API_KEY`/`SITE_URL`/`ALLOWED_HOSTS` removed or empty | **PASS** — missing `DJANGO_SECRET_KEY` → `ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable` (value-free); missing `BOT_TOKEN` (prod) → `ImproperlyConfigured: BOT_TOKEN must be set in production. Provide it via the .env.docker runtime file.` (value-free). Empty-but-set also rejected (`django-environ` treats empty as missing). |
| R3 | Hardcoded-secret scan | `git grep` for AKIA/ghp/sk-AIza/Telegram `id:token` patterns + `git grep "0y-)6rzn_dfoe"` across committed files; `git ls-files` for env files | **FAIL (1)** — real `DJANGO_SECRET_KEY` found committed in `test_settings_secrets.py` (Finding 1). No other real secrets: CI uses `test-secret-key-for-testing-only`; test compose uses `postgres:postgres` (fake fixture); `seed-images-config.json` is gitignored + untracked (API keys empty in the committed `.example.json`). |
| R4 | Ignore-file coverage | `git check-ignore .env .env.docker .env.local .env.dev src/.env`; `git ls-files | grep env`; `.dockerignore` | **PASS** — all real env files are git-ignored (`.gitignore` lines 144-148) and docker-ignored (`.dockerignore: .env*`); only `.example` templates are tracked. (Finding 1 is the single breach of "protected source".) |
| R5 | Lint + type-check over config/secret surface | `uv run ruff check src/backend/config/`; `uv run basedpyright src/backend/config/` | **PASS** — `ruff`: All checks passed. `basedpyright`: 0 errors, 0 warnings, 0 notes. |
| R6 | Settings secret tests | `docker compose ... run --rm -e PYTEST_OPTS="-k test_settings_secrets" test` (test DB already up) | **PASS** — `5 passed, 1473 deselected`. (Note: `test_secret_key_with_dollar_sign_preserved` passes *and* carries the leaked key — see Finding 1.) |

> R2 edge-case note: `DJANGO_SECRET_KEY=""` (empty-but-set) is rejected by `django-environ` (raises), so both "unset" and "empty" are covered for the signing key; BOT_TOKEN/GOOGLE_TRANSLATE_API_KEY/SITE_URL use explicit `if not X and not DJANGO_BUILD: raise`. The `DJANGO_BUILD` escape hatch correctly defers guards during image build (collectstatic) and re-fires at runtime.

---

## Cross-cutting observations (no deviation — documented for completeness)

- **Two-process secret parity:** `web` and `bot` services share identical required config — same `env_file: .env.docker` plus the same explicit `environment` block (`DJANGO_SETTINGS_MODULE=config.settings.prod`, `POSTGRES_*`, `DATABASE_URL`, `DJANGO_SECRET_KEY`, `REDIS_URL`). No process-specific secret divergence. `BOT_TOKEN` reaches both via `env_file` (not duplicated in `environment`), so there is no drift vector.
- **Enum registry (dimension a):** fixed-value constants are centralized as `StrEnum` — `apps.core.enums` (`AdStatus`, `AdSource`, `ModeratorActionType`, `ThumbnailSizeStrEnum`, `TrustLevel`, `AdSort`, `AnalyticsEventType`, `TimeRange`), `apps.currencies.enums`, `apps.lookups.enums`. Sampled ad/views import `AdStatus`/`AdSort` from the registry; no raw status-string literals found in ad views. Config-to-consumer flow: every env var in `.env.docker.example` is consumed (BOT_TOKEN → `main.py` + `immediate_alerts.py` + `send_alerts.py`; GOOGLE_TRANSLATE_API_KEY → `core/services/translation.py`; SITE_URL → `ads/models.py`; IMMEDIATE_ALERTS_ENABLED → `moderation/signals.py`; BOT_LIVENESS_FILE → `lifecycle.py` + `healthcheck-bot.sh`; TLS_CERT_PATH → nginx volume mount only) — no unused fields.
- **`.env.example` vs `.env.docker.example`:** `.env.example` omits `GOOGLE_TRANSLATE_API_KEY`. This is intentional scoping for the standalone-local template (local runs use `config.settings.dev`, where the key is optional via `default=""` and the prod guard is skipped) — not a defect.

---

## Severity Counts

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 1        | 1    | 0      | 1   |

---

## Methodology

- **Discovery:** read `src/backend/config/settings/{__init__,base,dev,prod,test}.py`, `docker-compose.yml` + `.dev.override.yml` + `.prod.yml` + `.test.yml`, `docker/entrypoint*.sh`, `docker/entrypoint-create-admin.sh`, `docker/Dockerfile`, `.gitignore`/`.dockerignore`, `Makefile`/`Makefile.ps1`, `AGENTS.md`, `pyproject.toml`, CI workflows, and the project's own hardening research (`docs/96-researches/`).
- **Runtime evidence:** settings import (R1), fail-fast (R2 + empty-but-set edge), `docker compose config` reproduction (Finding 2), Django deploy-check reproduction (Finding 3/W025), `uv run ruff` + `uv run basedpyright` on the config surface (R5), and the full `test_settings_secrets.py` suite via the documented Docker test path (R6).
- **Assurances (scope):** this phase is config & secrets only. Auth/authz (logout CSRF, `LOGIN_URL`, GET logout links), media, search/FTS, ad lifecycle, i18n, and PII consent are covered by other phases and were **not** re-audited here. The prior-audit findings referenced in `docs/96-researches/*` (e.g. `${VAR:-placeholder}`, scheduler `/app/.env` path) were re-verified against current code and found **already remediated**; this report reflects the **current** repository state, not those stale artifacts.
