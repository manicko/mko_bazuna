# Validated Audit Findings — Config & Secrets Management

**Phase:** 02 — Config & Secrets
**Date:** 2026-09-12
**Auditor:** Executor (subagent)
**Validator:** Kilo (read-validation agent)
**Status:** problems-only · validated: yes

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

## Cross-Finding Analysis

### Same root cause → merge candidates

None. The three findings have distinct root causes:
- **Finding 1:** Test author copy-pasted real key material into test data.
- **Finding 2:** Compose `:?` interpolation guard added without reconciling with the entrypoint's skip-on-empty design.
- **Finding 3:** `${VAR:?}` shell guard cannot validate secret strength; Django's W025 deploy check was never wired into CI or boot.

### Conflicting evidence

None. All findings are mutually consistent and independently verifiable.

### Dependency chains

- **Finding 1 (rotate key)** is independent. Rotating `DJANGO_SECRET_KEY` does not
  depend on Finding 2 or 3, but the **test fix** (Finding 1's recommendation #2)
  must be done first so the committed test no longer carries real key material
  before the key is rotated — otherwise the new key would also leak into the test
  if the same copy-paste pattern is reused.
- **Finding 2 (ADMIN_PASSWORD guard)** is independent of Finding 1 and 3.
  Its fix has an internal dependency: changing the compose `:?` to `:-` makes the
  entrypoint skip branch reachable, which then means the management command's
  empty-password `CommandError` (create_admin_user.py:67–71) becomes defensive
  backstop only (never reached in the empty case, since the entrypoint exits
  0 before invoking the command). The recommendation already notes this.
- **Finding 3 (add `check --deploy`)** is independent. It is a non-blocking CI
  addition with no dependency on other findings.

### Cross-phase overlap

- **Phase 12 (`12-audit-production-ops.md`)** Section 4 Check 5 and Section 5(d)
  both intend to flag the *absence* of `manage.py check --deploy` in CI as a
  CRITICAL pipeline-security finding. Phase 12 has **not yet been executed**
  (its findings directory is empty). Finding 3 here overlaps with what Phase 12
  would surface, but from a config-layer perspective (weak key accepted at boot
  vs. CI not running deploy checks). **No conflict** — complementary perspectives
  on the same gap. If Phase 12 is executed, its `OPS-*` finding should merge
  Finding 3's `check --deploy` absence into the Phase 12 finding, keeping the
  W025-weak-placeholder aspect in Phase 02.
- **Phase 01 (`01-entry-architecture/`) findings** cover async/sync boundaries,
  LOGGING config, and Gunicorn CLI flags — unrelated to config/secrets. No
  overlap or conflict.

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

**Evidence** (verified on-disk):

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
```

```
# Runtime files (gitignored, but identical to the committed value):
# .env:6            DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'
# .env.docker:6     DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'
# .env.local:7      DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'
```

**Validation result: VALIDATED — CRITICAL**

- `grep -rn "0y-)6rzn_dfoe"` across the entire repo returns **exactly 2 matches**, both in the committed test file (line 139 input, line 145 assertion). No other files in VCS contain this substring.
- `git ls-files --error-unmatch src/backend/config/settings/tests/test_settings_secrets.py` succeeds ⇒ the file (and thus the key) is **tracked/committed**.
- All three runtime env files are confirmed on disk and contain the **identical** key value:
  - `.env` line 6: `DJANGO_SECRET_KEY='=0y-)6rzn_dfoe+u$xp)u#*3yn&h!@9d+t=1va0r+#mg1hj+k+'`
  - `.env.docker` line 6: same
  - `.env.local` line 7: same
- `git log --oneline bae31ac` confirms the commit message: `fix(config): escape DJANGO_SECRET_KEY to prevent Docker Compose interpolation`.
- All three env files are correctly git-ignored (`.gitignore` lines 145–148) and docker-ignored (`.dockerignore` line 5: `.env*`). The **only** breach of the "protected source" boundary is the test file.
- The test's assertions do not depend on the specific key material — it only exercises `$`-preservation in single-quoted `.env` values. A dummy test string would suffice.

**Rollout note (CRITICAL):** Secret rotation is a coordinated, cross-environment operation: rotate the key in all local `.env*` files and the VPS `secrets/.env.docker`; invalidate all signed tokens; restart web and bot containers. The test-file fix (part 2 of the recommendation) is isolated and safe — replace the value with an obviously-fake dummy and verify with `pytest -k test_secret_key_with_dollar_sign_preserved`.

---

### Finding 2 — [HIGH] — `ADMIN_PASSWORD` compose `:?` guard contradicts the graceful-skip design and breaks `make up`

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Category** | Operational reliability / correctness (deployment-blocking) |
| **File(s)** | `docker-compose.yml:126` (`:?` guard); `docker-compose.yml:133` ("Skipped if…" comment); `docker/entrypoint-create-admin.sh:17-21` (skip-on-empty); `src/backend/.../create_admin_user.py:67-71` (rejects empty); `.env.docker.example:69` (ships empty) |
| **Problem** | Three layers of the `create_admin` one-shot contradict each other on the empty-`ADMIN_PASSWORD` policy: compose uses `${ADMIN_PASSWORD:?…}` (hard-fails on empty), the entrypoint + compose comment say "skip if empty", and the management command rejects empty passwords. Because compose evaluation happens before any container starts, the `:?` wins and the graceful-skip code is unreachable dead code. |
| **Impact** | With `ADMIN_PASSWORD` empty — which is exactly what is shipped by `.env.docker.example` (line 69: `ADMIN_PASSWORD=`) and present in the local `.env.docker` (line 41) — `docker compose config` (and therefore `make up` / `docker compose up`) **fails before any container starts**, with a cryptic interpolation error. The documented "Skipped if ADMIN_PASSWORD not set" behaviour cannot be exercised; there is no way to opt out of admin creation via an empty value. The primary dev startup path is blocked. |
| **Root Cause** | The `:?` form was chosen to "fail fast", but `create_admin` is a one-shot whose entrypoint was explicitly written to tolerate a missing password (skip + `exit 0`). The `:?` guard makes the skip branch unreachable. The intent was never reconciled with the compose interpolation guard. |

**Evidence** (verified on-disk):

```bash
# Reproduced (default empty ADMIN_PASSWORD in .env.docker):
$ docker compose --env-file .env.docker \
    -f docker-compose.yml -f docker-compose.dev.override.yml config
error while interpolating services.create_admin.environment.[
]: required variable ADMIN_PASSWORD is missing a value: ADMIN_PASSWORD must be set
```

```yaml
# docker-compose.yml:125-133  (contradiction in consecutive lines)
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

```python
# src/backend/apps/core/management/commands/create_admin_user.py:67-71  (defensive rejection)
if not password or not password.strip():
    raise CommandError(
        "Password cannot be empty. Please provide a valid password."
    )
```

**Validation result: VALIDATED — HIGH**

- `docker-compose.yml:126` confirmed: `ADMIN_PASSWORD=${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}` — the `:?` shell parameter expansion form **hard-fails** when `ADMIN_PASSWORD` is empty or unset, evaluated at compose config-resolution time (before any container starts).
- `docker-compose.yml:133` confirmed: comment `# Skipped if ADMIN_PASSWORD not set (empty string)` — directly contradicts the `:?` guard above it.
- `docker/entrypoint-create-admin.sh:18-20` confirmed: `if [ -z "${ADMIN_PASSWORD}" ]; then … exit 0` — skip logic that is **unreachable** because compose config fails first.
- `create_admin_user.py:67-71` confirmed: management command rejects empty passwords with `CommandError` — also unreachable in the empty case (entrypoint would exit before calling the command, and compose fails before the entrypoint runs).
- `.env.docker.example:69` confirmed: `ADMIN_PASSWORD=` — ships empty in the template.
- `.env.docker` on disk line 41 confirmed: `ADMIN_PASSWORD=` — local runtime file also ships empty.
- `.env.docker.example:67` has an **internal contradiction** of its own: the comment says "ADMIN_PASSWORD is REQUIRED … Must be non-empty or `docker compose config` fails (fail-fast via ${ADMIN_PASSWORD:?})" but the value on the next line (69) is empty.
- `docker-compose.dev.override.yml:15` — **additional occurrence**: the `web` service in the dev override *also* has `ADMIN_PASSWORD=${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set}`. This means even if `create_admin` were removed from the compose stack, the `web` service's environment resolution would also fail. This amplifies the finding beyond what the original report states (the original report only cited `docker-compose.yml:126`).
- `Makefile:9` confirmed: `ENV_FILE := --env-file .env.docker` — `make up` loads `.env.docker` which has empty `ADMIN_PASSWORD`, so `make up` is blocked.
- `Makefile:79-81` confirmed: the `up` target runs `docker compose $(COMPOSE_FILES) up -d --wait` which resolves all service configs including `create_admin` (which has the `:?` guard) and `web` (which also has it in the dev override).

**Rollout note (HIGH):** The recommended fix (change `:?` to `:-`, i.e. `ADMIN_PASSWORD=${ADMIN_PASSWORD:-}`) is a low-risk, compose-level change. However, removing the `:?` guard means the entrypoint skip branch becomes reachable, so operators must be aware that an empty `ADMIN_PASSWORD` will silently skip admin creation. The management command's defensive `CommandError` for empty passwords can remain as a backstop. Consider also removing the erroneous `ADMIN_PASSWORD=${ADMIN_PASSWORD:?…}` from the `web` service in `docker-compose.dev.override.yml:15` (it serves no purpose — the web process never reads `ADMIN_PASSWORD`).

---

### Finding 3 — [LOW] — No `check --deploy` backstop; weak/placeholder `SECRET_KEY` accepted at boot

| Field | Value |
|---|---|
| **Severity** | LOW |
| **Category** | Security / observability (missing boundary validation) |
| **File(s)** | `.env.docker.example:14` & `.env.example:13` (placeholder key, 43 chars); `docker-compose.yml:46` (`${DJANGO_SECRET_KEY:?…}` accepts non-empty placeholder); entrypoints + Dockerfile + `.github/workflows/ci.yml` (no `check --deploy`) |
| **Problem** | The `DJANGO_SECRET_KEY` guard is `${…:?}` which rejects only **empty/unset** values, not **weak/placeholder** values. The templates ship `DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>` — a non-empty 43-character string — which passes the `:?` guard and boots Django with a known, weak signing key. Django's own deploy check `security.W025` (firing on keys < 50 chars) would catch this, but `manage.py check --deploy` is never invoked at boot or in CI. |
| **Impact** | An operator who deploys the template verbatim (forgetting to generate a real key) silently boots production with a publicly-known signing key, enabling session/CSRF/password-reset token forgery. The project's hardening research (`docs/96-researches/security-config-hardening-research.md`, `admin-auth-separation-research.md`) already flagged the placeholder/weak-key concern; the `:?` fix closed the *empty* gap but not the *weak-placeholder* gap. |
| **Root Cause** | `${VAR:?}` cannot validate secret strength — it only checks presence. Django's strength validation lives in the `W025` deploy check, which requires an explicit `check --deploy` invocation that the project never performs. |

**Evidence** (verified on-disk):

```bash
# Django 5.2 W025 fires on the template placeholder (len=43 < SECRET_KEY_MIN_LENGTH=50):
$ python manage.py check --deploy -t security
?: (security.W025) Your SECRET_KEY has less than 50 characters, less than 5 unique
characters, or it's prefixed with 'django-insecure-' ...    System check identified 1 issue.
# But no entrypoint/Dockerfile/CI step runs this:
$ git grep -nE -- 'manage\.py check|check --deploy|--deploy' \
    -- docker/entrypoint*.sh docker/Dockerfile .github/workflows/*.yml
# (no matches in any source file — confirmed below)
```

**Validation result: VALIDATED — LOW (with minor correction)**

- `.env.docker.example:14` confirmed: `DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>` — placeholder, non-empty.
- `.env.example:13` confirmed: `DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>` — placeholder, non-empty.
- The placeholder string `<generate-with-django-secret-key-generator>` is **43 characters** (verified via `python -c "s='<generate-with-django-secret-key-generator>'; print(len(s))"` → 43), not 44 as stated in the findings. This is a minor numerical discrepancy. It does **not** affect the finding's validity: Django's `SECRET_KEY_MIN_LENGTH = 50`, so a 43-char placeholder still triggers W025. The substantive claim stands.
- `docker-compose.yml:46` confirmed: `DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY:?DJANGO_SECRET_KEY must be set}` — the `:?` form accepts any non-empty value, including the placeholder.
- `grep` for `manage\.py check|check --deploy|--deploy` across `docker/entrypoint*.sh`, `docker/Dockerfile`, and `.github/workflows/*.yml` returns **zero matches** in any actual source/deployment file. The `.env`, `.env.docker`, `.env.local` files do not contain this pattern (they are env files, not Python/compose).
- CI workflow (`.github/workflows/ci.yml`) confirmed: jobs are `build`, `test`, `lint`, `typecheck`, `lint-templates`, `i18n`. None invoke `manage.py check --deploy`. CI runs only ruff / basedpyright / djlint / pytest.
- `docker/entrypoint.sh` confirmed (full file read): no `check --deploy` call. It runs `check_env_file`, `fix_volume_permissions`, `wait_for_db`, `wait_for_redis`, `compile_messages`, then `exec "$@"`.
- `docker/Dockerfile` confirmed (full file read): no `check --deploy` call.
- The `docs/96-researches/security-config-hardening-research.md` and `docs/99-agent/i18n-definition-of-done-research.md` files *reference* `check --deploy` in research/discussion context, but none of the runtime/CI artifacts invoke it.

**Rollout note (LOW):** Adding a non-blocking `manage.py check --deploy` step to CI (or as a non-fatal call in `entrypoint.sh` after migrations) is low-risk and does not block boot. Per `.kilo/commands/audit/phases/12-audit-production-ops.md` Section 4 Check 5, Phase 12 also expects to find the absence of `check --deploy` in CI as a CRITICAL pipeline-security finding — the Phase 12 audit has not yet been executed, so this overlap should be reconciled when Phase 12 runs.

---

## Runtime Verification (R1–R6)

Evidence gathered during this validation pass (local venv at `.venv`, Python 3.14 /
Django 5.2.16; test DB via `docker compose --project-name mko-bazuna-test`).

| ID | Check | Command / method | Result |
|---|---|---|---|
| R1 | Settings import per environment, no import-time side effects | `DJANGO_SETTINGS_MODULE=config.settings.{test\|dev\|prod}` → `django.setup()` with `PYTHONPATH=src;src/backend` and controlled env | **PASS** — test (DEBUG=True, LocMemCache, `BOT_LIVENESS_FILE=''`), dev (DEBUG=True, no SSL redirect), prod (DEBUG=False, HSTS=31536000, HSTS_PRELOAD=True, secure cookies) all import cleanly. Import configures `DATABASES`/`CACHES` lazily (no DB access), no secret logging. |
| R2 | Missing/empty required secret fails fast, no leaked value | prod settings with `DJANGO_SECRET_KEY`/`BOT_TOKEN`/`GOOGLE_TRANSLATE_API_KEY`/`SITE_URL`/`ALLOWED_HOSTS` removed or empty | **PASS** — missing `DJANGO_SECRET_KEY` → `ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable` (value-free); missing `BOT_TOKEN` (prod) → `ImproperlyConfigured: BOT_TOKEN must be set in production. Provide it via the .env.docker runtime file.` (value-free). Empty-but-set also rejected (`django-environ` treats empty as missing). |
| R3 | Hardcoded-secret scan | `grep -rn "0y-)6rzn_dfoe"` across committed files; `git ls-files --error-unmatch` on env/test files | **FAIL (1)** — real `DJANGO_SECRET_KEY` found committed in `test_settings_secrets.py` (Finding 1). No other real secrets: CI uses `test-secret-key-for-testing-only`; test compose uses `postgres:postgres` (fake fixture); `seed-images-config.json` is gitignored + untracked (API keys empty in the committed `.example.json`). |
| R4 | Ignore-file coverage | `git check-ignore .env .env.docker .env.local .env.dev src/.env`; `git ls-files \| grep env`; `.dockerignore` | **PASS** — all real env files are git-ignored (`.gitignore` lines 145–148) and docker-ignored (`.dockerignore: .env*`); only `.example` templates are tracked. (Finding 1 is the single breach of "protected source".) |
| R5 | Lint + type-check over config/secret surface | `uv run ruff check src/backend/config/`; `uv run basedpyright src/backend/config/` | **PASS** — `ruff`: All checks passed. `basedpyright`: 0 errors, 0 warnings, 0 notes. |
| R6 | Settings secret tests | `docker compose ... run --rm -e PYTEST_OPTS="-k test_settings_secrets" test` (test DB already up) | **PASS** — `5 passed, 1473 deselected`. (Note: `test_secret_key_with_dollar_sign_preserved` passes *and* carries the leaked key — see Finding 1.) |

> R2 edge-case note: `DJANGO_SECRET_KEY=""` (empty-but-set) is rejected by `django-environ` (raises), so both "unset" and "empty" are covered for the signing key; BOT_TOKEN/GOOGLE_TRANSLATE_API_KEY/SITE_URL use explicit `if not X and not DJANGO_BUILD: raise`. The `DJANGO_BUILD` escape hatch correctly defers guards during image build (collectstatic) and re-fires at runtime.

---

## Cross-cutting observations (no deviation — validated for completeness)

- **Two-process secret parity:** `web` and `bot` services share identical required config — same `env_file: .env.docker` plus the same explicit `environment` block (`DJANGO_SETTINGS_MODULE=config.settings.prod`, `POSTGRES_*`, `DATABASE_URL`, `DJANGO_SECRET_KEY`, `REDIS_URL`). No process-specific secret divergence. `BOT_TOKEN` reaches both via `env_file` (not duplicated in `environment`), so there is no drift vector.
- **Enum registry (dimension a):** fixed-value constants are centralized as `StrEnum` — `apps.core.enums` (`AdStatus`, `AdSource`, `ModeratorActionType`, `ThumbnailSizeStrEnum`, `TrustLevel`, `AdSort`, `AnalyticsEventType`, `TimeRange`, `AdvisoryLockId`), `apps.currencies.enums`, `apps.lookups.enums`. Sampled ad/views import `AdStatus`/`AdSort` from the registry; no raw status-string literals found in ad views. Config-to-consumer flow: every env var in `.env.docker.example` is consumed (BOT_TOKEN → `main.py` + `immediate_alerts.py` + `send_alerts.py`; GOOGLE_TRANSLATE_API_KEY → `core/services/translation.py`; SITE_URL → `ads/models.py`; IMMEDIATE_ALERTS_ENABLED → `moderation/signals.py`; BOT_LIVENESS_FILE → `lifecycle.py` + `healthcheck-bot.sh`; TLS_CERT_PATH → nginx volume mount only) — no unused fields.
- **`.env.example` vs `.env.docker.example`:** `.env.example` omits `GOOGLE_TRANSLATE_API_KEY`. This is intentional scoping for the standalone-local template (local runs use `config.settings.dev`, where the key is optional via `default=""` and the prod guard is skipped) — not a defect.

---

## Rollout Safety Assessment

| Finding | Risk | Dependencies | Backward compatibility | Notes |
|---|---|---|---|---|
| 1 (rotate key) | **HIGH** — invalidates all signed tokens (sessions, CSRF, password resets) across all environments simultaneously | None | Breaking for active sessions; requires coordinated restart of web + bot containers | Fix order: (1) replace test value with dummy, (2) rotate key in all `.env*` + VPS `secrets/.env.docker`, (3) restart containers. The test fix must precede rotation so the new key is not also leaked. |
| 2 (ADMIN_PASSWORD guard) | **LOW** — compose-only change | None | None — current state already blocks `make up`; the change restores the documented dev startup path | Removing `:?` from `create_admin` AND from `web` (dev override line 15) makes the entrypoint skip reachable. Consider whether `web` should carry `ADMIN_PASSWORD` at all (it doesn't consume it). |
| 3 (`check --deploy`) | **NONE** — non-blocking CI step | None | None | Additive only. Recommend non-fatal invocation in CI (warnings-only). |

### Risks detected during validation

- **Finding 2 hidden dependency:** The dev override `docker-compose.dev.override.yml:15` adds `ADMIN_PASSWORD=${ADMIN_PASSWORD:?…}` to the **`web`** service — a service that never reads `ADMIN_PASSWORD`. This is likely a copy-paste error from the `create_admin` block. It means fixing only `create_admin`'s `:?` is insufficient; `make up` would still fail on the `web` service. This hidden occurrence should be removed entirely (not converted to `:-`).
- **Finding 2 design ambiguity:** Even after fixing the `:?` guard, the three-layer policy (compose `:-` empty-default → entrypoint skip → management command reject-empty) is internally inconsistent. The cleanest design is: compose passes empty string through, entrypoint skips and exits 0 (does not call the command), and the management command's empty-rejection is a defensive backstop that should be documented as such (or removed to avoid confusion).
- **Finding 2 `.env.docker.example` internal contradiction:** Line 67 says "Must be non-empty" but line 69 ships empty. If the preferred fix (drop `:?` to `:-`) is adopted, the `.env.docker.example` comment must be updated to reflect the opt-out behaviour.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 3 | Finding 1 (CRITICAL), Finding 2 (HIGH), Finding 3 (LOW) |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Reclassified Findings

None.

### Merged Findings

None within Phase 02. Finding 3 overlaps with Phase 12's intended `check --deploy` CI finding (Section 4 Check 5 / Section 5(d)) — Phase 12 has not been executed yet. When Phase 12 runs, the `check --deploy`-absence aspect should be consolidated into the Phase 12 `OPS-*` finding; the W025 weak-placeholder aspect remains a Phase 02 concern.

### Rejected Findings

None.

---

## Required Fixes

1. **[CRITICAL] Finding 1(a):** Replace the real `DJANGO_SECRET_KEY` value in `test_settings_secrets.py` lines 139 and 145 with an obviously-fake test-only dummy (e.g. `=t$test-key-with-$dollar$ign$chars`) that still exercises `$`-preservation. The test's assertions are value-agnostic.
2. **[CRITICAL] Finding 1(b):** Rotate `DJANGO_SECRET_KEY` across `.env`, `.env.docker`, `.env.local`, and the VPS `secrets/.env.docker` (verify before assuming prod differs). Treat the committed value as compromised.
3. **[HIGH] Finding 2:** Reconcile the `ADMIN_PASSWORD` policy. **Recommended:** change `${ADMIN_PASSWORD:?…}` to `${ADMIN_PASSWORD:-}` at `docker-compose.yml:126` AND remove the erroneous `ADMIN_PASSWORD=${ADMIN_PASSWORD:?…}` from `docker-compose.dev.override.yml:15` (web service doesn't use it). Update `.env.docker.example:67-69` to reflect the opt-out design.
4. **[LOW] Finding 3:** Add a non-blocking `manage.py check --deploy` step to the CI workflow (warnings-only, non-blocking) or as a non-fatal post-migration call in `entrypoint.sh`.

---

## Advisory Recommendations

- **Finding 2:** Remove `ADMIN_PASSWORD=${ADMIN_PASSWORD:?…}` from the `web` service in `docker-compose.dev.override.yml:15` entirely — it serves no purpose and is a likely copy-paste from the `create_admin` block.
- **Finding 2:** Consolidate the three-layer empty-password policy into a single source of truth. Either the entrypoint skips (and the management command's empty-rejection is documented as defensive-only backstop), or the management command's rejection is the only enforcement and the entrypoint's skip branch is removed. Currently both exist, creating ambiguity.
- **Finding 3:** Consider replacing `<generate-with-django-secret-key-generator>` in `.env.docker.example:14` and `.env.example:13` with a note that instructs operators to verify the key length and entropy, or add a runtime assertion in `prod.py` that `len(SECRET_KEY) >= 50` (complementing, not replacing, `check --deploy`).
