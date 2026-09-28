---
phase: "02"
phase_name: "Configuration & Secrets Management"
source_findings: ".ai/audit/02-config-secrets/findings.md"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: "Validator (subagent)"
mode: "problems-only"
id_prefix: "CFG"
val_prefix: "VAL (phase-02 namespace)"
anchor_commit: "9e96b84"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/02-audit-config-secrets.md#severity-taxonomy"
---

# Validated Findings — Configuration & Secrets Management (Phase 02)

Every finding below was independently re-derived from the working tree at commit
`9e96b84`. The auditor's claims were **not** accepted on trust: 9 of the 12 runtime
checks were reproduced by the validator from scratch, 2 were refuted or materially
corrected, and 4 audit-input defects (`VAL-001`…`VAL-004`) were recorded.

**No source file was modified.** The only write produced by this phase is this report.

---

## Verdict Matrix

| ID | Title (abbrev.) | Auditor severity | Verdict | Final severity | Type | One-line justification |
|----|------------------|------------------|---------|----------------|------|------------------------|
| CFG-001 | `DJANGO_ONESHOT`/`DJANGO_BUILD` bypass all prod secret guards | HIGH | **ADJUSTED** | **MEDIUM** ↓ | `SPEC-DEVIATION` | Mechanism reproduced, but the flag ships in no template, no doc, no real `.env.*`, and is **not** baked into the runtime image — latent hazard, not a live protection failure. |
| CFG-002 | CI `deploy-check` cannot import `config.settings.prod`; gate is inert | HIGH | **CONFIRMED** | **HIGH** | `SPEC-DEVIATION` | Reproduced exactly; `ci.yml:536` is the *only* `check --deploy` in CI, and it aborts at import on `EMAIL_HOST` then `REDIS_URL`. |
| CFG-003 | Admin password passed as management-command argv | MEDIUM | **ADJUSTED** | **LOW** ↓ | `BEST-PRACTICE` | Mechanism real, but impact **refuted**: the same secret is already in cleartext in the container's `Config.Env`, so argv adds no exposure surface. |
| CFG-004 | `EMAIL_BACKEND` env-overridable in production | MEDIUM | **CONFIRMED** | **MEDIUM** | `SPEC-DEVIATION` | Reproduced: prod settings accept the console backend, the `EMAIL_HOST` guard still passes, and the message body is emitted to stdout. |
| CFG-005 | `BOT_USERNAME` placeholder unvalidated + persisted by migration `0003` | MEDIUM | **CONFIRMED** | **MEDIUM** | `SPEC-DEVIATION` | Verified: no guard exists, and `QuerySet.update()` provably bypasses the field's `RegexValidator`. |
| CFG-006 | Bot-only config error crash-loops the whole dev stack | MEDIUM | **CONFIRMED** | **MEDIUM** | `SPEC-DEVIATION` | **Live-reproduced** — both dev containers are in `Restarting (1)` on `dev.py:21`. |
| CFG-007 | `STATICFILES_STORAGE` in `prod.py` is dead (removed in Django 5.1) | MEDIUM | **CONFIRMED** | **MEDIUM** | `SPEC-DEVIATION` | Confirmed absent from Django 5.2.17 `global_settings`; `STORAGES` in `base.py` already carries the same backend. |
| CFG-008 | `RUN_TRANSLATION_BACKFILL` missing from allowlist and all templates | LOW | **CONFIRMED** | **LOW** | `SPEC-DEVIATION` | Independent sweep reproduces it as the **only** consumed name absent from `ALLOWED_ENV_VARS`. |
| CFG-009 | `.env.example` omits 19 consumed variables | LOW | **CONFIRMED** | **LOW** | `DOC-UPDATE` | The count of 19 reconciles exactly; but the proposed "delete the file" branch is **blocked** (`VAL-003`). |
| CFG-010 | `test.py` does not reset `SECURE_HSTS_*` | LOW | **CONFIRMED** | **LOW** | `SPEC-DEVIATION` | Measured: test inherits `HSTS=3600 / INCLUDE_SUBDOMAINS=True`; dev explicitly zeroes the triple. |
| CFG-011 | `base.py` comment cites a non-existent "Env schema" | LOW | **ADJUSTED** | **LOW** | `DOC-UPDATE` | Misleading comment confirmed, but the auditor's root cause is **partly wrong** (an `Env` entry *does* exist); the "add Pydantic settings" half of the fix is rejected as overengineering. |

**0 rejected · 0 merged · 8 confirmed unchanged · 3 adjusted · 4 VAL findings recorded.**

**Severity movement:** 0 CRITICAL, 2 HIGH, 5 MEDIUM, 4 LOW → **0 CRITICAL, 1 HIGH,
5 MEDIUM, 5 LOW.**

---

## Executive Summary of the Validation Outcome

The auditor's core diagnosis is correct and important. **CFG-002 is a genuinely live,
currently-broken gate** and is the only finding that warrants HIGH on its own merits:
the single automated production-configuration check in the pipeline cannot import the
settings module it is meant to check, it has been broken for four days across two
commits, and nothing else in CI covers the gap.

The auditor's **priority ordering was inverted on CFG-001**. The report placed an
unscoped secret-guard bypass at HIGH / P0 on the strength of its *consequence*
(an empty signing key in production), while its *present state* is a flag that appears
in no shipped template, no documentation, no real `.env.*` file, and — verified
independently here — **not in the runtime image**, because `ENV DJANGO_BUILD=1` lives
only in the Dockerfile's builder stage. The defect is real and worth fixing; it is a
latent misconfiguration hazard with a catastrophic tail, not a protection mechanism
that is currently failing. It is re-rated MEDIUM while keeping top-of-queue ordering,
because the same file must be touched to fix CFG-002.

**CFG-003 is materially overstated and is down-graded.** The claim that the plaintext
admin password is visible in `ps` / `/proc/*/cmdline` is true, but the finding's impact
paragraph reasons as if argv were the only place the credential appears. It is not: the
`create_admin` service receives the password through `env_file: .env.prod`, so the
plaintext is **already** in the container's `Config.Env` and already readable via
`docker inspect`. The recommended fix (read from the environment inside the command)
therefore reduces the exposure to exactly zero, not to nothing-because-absent — it
produces false assurance. See `VAL-002`.

Finally, the report's Cross-Finding Analysis is sound: CFG-008/CFG-009 genuinely share
a root cause, and the "CFG-001 before CFG-002" dependency chain is real. The one
structural gap the auditor missed is that **a shipped green test currently pins the
CFG-001 bypass as intended behaviour**, so the CFG-001 fix cannot be applied without
also rewriting that test — see `VAL-001`.

---

## Scope, Anchor, and Method

**Anchor commit:** `9e96b84` (`chore(agents) allow docker remove commands`).
**Working tree:** clean except for untracked `.ai/audit/**` report directories.
**Django:** 5.2.17 · **Python:** 3.14 · **vhost settings source:** `src/backend/config/settings/{base,dev,test,prod}.py`.

**Files re-read in full:** `base.py` (402 L), `prod.py` (251 L), `dev.py` (66 L),
`test.py` (97 L), `0003_add_bot_username.py`, `create_admin_user.py`,
`entrypoint-create-admin.sh`, `docker/Dockerfile`, `docker-compose.prod.yml`,
`docker-compose.dev.override.yml`, `.github/workflows/ci.yml`, `.env.prod.example`.

**Independent reproductions performed by the validator** (all from scratch; the
auditor's transcripts were not re-used):

| # | Reproduction | Command surface | Outcome |
|---|--------------|-----------------|---------|
| V1 | `config.settings.prod` under the exact `ci.yml:510-518` env | `uv run python -c "import config.settings.prod"` | `ImproperlyConfigured: EMAIL_HOST must be set in production` (prod.py:205) → **confirms CFG-002** |
| V2 | same, with `EMAIL_HOST` added | same | `ImproperlyConfigured: REDIS_URL must be set in production` (prod.py:248) → **confirms the second missing var** |
| V3 | same, with both added | same | `IMPORT OK` → the gate would work with a 2-line fix |
| V4 | `DJANGO_ONESHOT=1` + all eight secrets blanked | same | `SECRET_KEY len=0, DEBUG=False, CSRF=[], REDIS_URL=''` → **confirms CFG-001 mechanism** |
| V5 | same + `django.setup()` + signing-key access | `uv run python` | `ImproperlyConfigured: The SECRET_KEY setting must not be empty` → **confirms CFG-001 tail** |
| V6 | `DJANGO_BUILD=1` + blank key | same | `IMPORTED via DJANGO_BUILD. SECRET_KEY len=0` → second trigger confirmed |
| V7 | `EMAIL_BACKEND=…console.EmailBackend` under a fully valid prod env | `django.setup()` + `mail.send_mail` | `PROD EMAIL_BACKEND = …console.EmailBackend`, guard passes, body written to stdout → **confirms CFG-004** |
| V8 | `STATICFILES_STORAGE` presence in installed Django | `hasattr(django.conf.global_settings, …)` | `False`; `STORAGES` present → **confirms CFG-007** |
| V9 | per-environment transport-security tuple | `import config.settings.{test,dev}` | test `HSTS=3600/SUBD=True/PRE=False`; dev `0/False/False` → **confirms CFG-010** |
| V10 | live dev stack state + `docker logs` | `docker ps`, `docker logs` | web **and** bot `Restarting (1)`, both dying at `dev.py:21` → **confirms CFG-006** |
| V11 | `docker image inspect` of the built runtime image | `docker image inspect mko-bazuna-dev-web:latest` | **no `DJANGO_*` key at all in `Config.Env`** → **new evidence; bounds CFG-001 severity** |
| V12 | `ADMIN_PASSWORD` key-name-only sweep of tracked files + full git history | `git grep`, `git log -S` | 4 placeholder / 1 shell-ref / 34 reference-or-empty; the one committed non-empty literal is a lowercase `test`-fixture used identically in `.env.test.example:47` and `docker-compose.test.yml:108`, with no mixed case or digits → **no real credential in history; CFG-003's git premise holds** |
| V13 | `ADMIN_PASSWORD` in the live `create_admin` container | `docker inspect … .Config.Env` | **present** → **refutes CFG-003's impact framing** (see `VAL-002`) |
| V14 | independent consumed-vs-allowlist sweep (regex over non-test `src/**`) | validator-authored sweep | 33 consumed names; exactly **one** missing from `ALLOWED_ENV_VARS`: `RUN_TRANSLATION_BACKFILL` → **confirms CFG-008 precisely** |
| V15 | key-name extraction from all four `.env*.example` templates | validator-authored sweep | `.env.example` 26 keys; 19 consumed names absent (reconciles CFG-009's figure exactly) |
| V16 | scoped test suite | `docker compose … run --rm test` with `PYTEST_OPTS` targeting `config/settings/tests` + `test_compose_hardening.py` | **60 passed in 81.22 s** — suite is green, which is what makes the test-gap claims in CFG-001/CFG-002 material |

**Secret-handling discipline observed throughout:** every real `.env.*` file in the
working tree was inspected by **key name only**; no value was read, printed, quoted or
transcribed into this report. Commands that would have echoed a value were replaced with
boolean/classification output (e.g. "NONEMPTY_LITERAL(len=19)", "contains 'test': True").

---

## Checkpoints

### Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 11 (HIGH 2, MEDIUM 5, LOW 4)
- **Evidence anchor:** `.ai/audit/02-config-secrets/findings.md` (822 lines), copied as the base of this report
- **Dependencies / blockers:** none — the auditor's R-03 hardcoded-secret scan was executed with manual `git grep` sweeps because `gitleaks` and `pre-commit` are not installed on this host (recorded as `VAL-005`)
- **Checkpoint status:** closed

### Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Cross-phase conflicts:** 0. (The one apparent collision — phase 01's "web crash-loops" vs. CFG-006's "dev stack crash-loops" — is complementary: different containers, different causes.)
- **Merge candidates:** 0 hard merges; 1 confirmed soft pair (CFG-008 ↔ CFG-009) and 1 cross-phase relationship (CFG-002 ↔ ENT-001/ENT-011/ENT-012).
- **Evidence anchor:** this document; every line reference verified against `9e96b84`
- **Checkpoint status:** closed

### Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Decisions:** Validated unchanged **8** (CFG-002, CFG-004, CFG-005, CFG-006, CFG-007, CFG-008, CFG-009, CFG-010) · Adjusted **3** (CFG-001 HIGH→MEDIUM; CFG-003 MEDIUM→LOW; CFG-011 root cause corrected + long-term recommendation rejected) · Merged **0** · Rejected **0**
- **Validator reproductions:** 16 (V1–V16 above)
- **Audit-input defects found:** 5 (`VAL-001`…`VAL-005`)
- **Checkpoint status:** closed

### Checkpoint 4 — Rollout safety

- **Stage:** Final audit
- **Findings in scope:** 11 CFG + 5 VAL
- **Circular dependencies:** none detected among CFG-001…CFG-011
- **Hidden dependency chains found:** 1 — CFG-001 cannot be fixed without also rewriting `test_django_oneshot_bypasses_all_secrets` (`VAL-001`)
- **Unsafe recommendations found:** 2 — CFG-003's fix does not close the exposure it names (`VAL-002`); CFG-009's "delete the template" branch is blocked by two shipped tests (`VAL-003`)
- **Checkpoint status:** closed

---

## Findings — HIGH

### CFG-002 — [HIGH] — CI `deploy-check` job cannot import `config.settings.prod`; the production config gate never runs

**Verdict: CONFIRMED — HIGH (unchanged).** Type: `SPEC-DEVIATION`.

**Verified, and independently reproduced (V1–V3).** The `deploy-check` job
(`.github/workflows/ci.yml:508-537`) sets exactly eight environment variables
(`ci.yml:511-518`) and omits `EMAIL_HOST` and `REDIS_URL`. Both are unconditional
requirements once `_SKIP_SECRET_VALIDATION` is false, and CI sets neither bypass flag:

- `src/backend/config/settings/prod.py:203-208` — `if not EMAIL_HOST: raise ImproperlyConfigured(...)`
- `src/backend/config/settings/prod.py:246-251` — `if not REDIS_URL: raise ImproperlyConfigured(...)`

Reproduced with the job's exact variable set: the first failure is
`EMAIL_HOST` (raised from `prod.py:205`); adding it moves the failure to
`REDIS_URL` (`prod.py:248`); adding both imports cleanly. The fix is two lines.

**The gate is genuinely the only one.** `check --deploy` appears exactly once in the
whole CI tree (`ci.yml:536`, inside `deploy-check`). The `test` job does not run it —
confirmed by scanning every `manage.py check` invocation in the workflow. The
auditor's impact claim that "the `test`-job replacement … is no longer running the
check either" is **correct**.

**Drift provenance — precisely attributed.** The `env:` block was written once, in
`6ef5390` (2026-09-22, `fix(ci): deploy-check runs check --deploy against prod settings
(12-OPS-001)`) and has **never been modified since** — `git blame -L 508,520` attributes
all ten lines to `6ef5390d`. Both guards were added *after* the job was written:

| Commit | Date | Change | Effect |
|--------|------|--------|--------|
| `8be3638` | 2026-09-26 09:55 | `require EMAIL_HOST in prod` | **introduces the breakage** — this is the commit that broke the gate |
| `909ad16` | 2026-09-27 20:58 | `add REDIS_URL fail-fast guard in production` | adds a *second* missing variable; the gate was already dead |

So: the gate has been red since 2026-09-26, four days before this audit, and
`909ad16` shipped a second omission into an already-failing job.

**Root cause — corrected and sharpened.** The auditor attributes the drift to "no test
asserting the documented deploy-check environment satisfies every `prod.py` guard".
That is true but it is the *detection* gap, not the *cause*. The cause is visible in
the file: the contract statement lives at `ci.yml:375-381` —

> *"All required production env vars are set to valid non-secret placeholders so the
> full prod settings import path is exercised."*

— but that comment block sits **orphaned above the `load-test:` job (line 382)**, 127
lines above the `deploy-check:` job it actually documents (line 508) and 129 lines above
the `env:` block it describes (line 510). The requirement and the environment that must
satisfy it are in the same YAML file but nowhere near each other, so a reviewer editing
`prod.py` never sees the job and an editor of the job never sees the contract. Moving
the comment back to `deploy-check:` is a one-line-adjacent change and removes the
structural cause.

**Recommendation — accepted, with the durable half promoted to primary.**
1. Add `EMAIL_HOST` and `REDIS_URL` to the `deploy-check` `env:` block (restores the gate).
2. Move the orphaned contract comment from `ci.yml:375-381` to sit directly above
   `deploy-check:` (removes the cause).
3. Add a test that imports `config.settings.prod` in a subprocess using **exactly** the
   variable set parsed out of `ci.yml`, so a future guard addition fails the `test` job
   instead of silently neutering `deploy-check`. Extracting the set into one shared
   constant consumed by both the test and the workflow is the durable form.

**Effort:** S (<0.5 person-day). **Priority:** P0.

**Rollout safety:** CI-only, fully backward compatible. No secret is introduced — the
added values are non-secret placeholders. The new test is the only behavioural change and
must run in the `test` job (not `deploy-check`) to be useful.

---

## Findings — MEDIUM

### CFG-001 — [MEDIUM] — `DJANGO_ONESHOT` / `DJANGO_BUILD` in the env file disables every production secret guard

**Verdict: ADJUSTED — HIGH → MEDIUM.** Type: `SPEC-DEVIATION`.

**The mechanism is exactly as described and is reproduced (V4–V6).** `prod.py:111-113`
is a plain, unscoped process-environment read with no reference to which settings module
is being loaded:

```python
_SKIP_SECRET_VALIDATION = bool(
    os.getenv("DJANGO_BUILD") or os.getenv("DJANGO_ONESHOT")
)
```

The supporting chain also checks out: both flags are in `ALLOWED_ENV_VARS`
(`base.py:21`), so the "unknown `.env` key" warning explicitly treats them as legitimate;
`base.py:102-105` calls `read_env()` on `BASE_DIR/.env` for every non-test settings
module; and `docker-compose.prod.yml` bind-mounts `./.env.prod:/app/src/.env:ro` on
`web` (11-19), `bot` (26-28), `migrate` (36-37), `create_admin` (44-45), `seed` (50-51),
`load_cities` (62-63) and `load_catalog` (70-71). The silent-degradation tail is also
real: `docker/entrypoint.sh:93-97` runs `check --deploy` under
`|| echo "WARNING: … (non-fatal at boot)"`, invoked at line 108.

**Why the severity is reduced — evidence, not preference.** The bypass is *latent*, and
four independent checks establish that:

1. **Not in the runtime image.** `ENV DJANGO_BUILD=1` is at `docker/Dockerfile:70`,
   which is inside **STAGE 1 (builder)**. The runtime stage begins with
   `FROM python:3.14-slim AS runtime` (line 99) — a fresh base that inherits no builder
   `ENV`. Confirmed empirically (V11): `docker image inspect mko-bazuna-dev-web:latest`
   reports **no `DJANGO_*` key at all** in `Config.Env`. The production image therefore
   does not carry the flag; the auditor's report did not establish this.
2. **Not in the production compose.** `docker-compose.prod.yml` sets neither flag on any
   service — and `src/backend/tests/test_compose_hardening.py:255-279`
   (`test_compose_oneshot_flags`) **already asserts** that for all five one-shot
   services. That regression test exists and is green.
3. **Not in any template or doc.** Neither `.env.prod.example` (92 lines, read in full),
   `.env.dev.example`, `.env.test.example`, nor `.env.example` contains either key.
4. **Not in the real `.env.prod`.** Key-name-only inspection of the working-tree file
   (22 keys) shows no `DJANGO_ONESHOT` and no `DJANGO_BUILD`.

So the "protection mechanism failure" framing of CWE-693 is *technically* apt but
*empirically* not the current state: the guards are fully active in every shipped and
real configuration. The defect is an **unguarded in-band control channel** — a
bootstrap flag that can be silenced by adding one line to a gitignored operator file,
with no warning, because the allowlist legitimises the key.

**The tail is genuinely catastrophic, which is why this stays at the top of the queue.**
If it fires, prod imports with `SECRET_KEY` length 0, empty `CSRF_TRUSTED_ORIGINS`,
empty `REDIS_URL` and empty `BOT_TOKEN`; the web tier 500s on the first signing
operation; the bot logs "development mode" and exits 0 while reporting healthy; the bot
drops to `MemoryStorage`, losing FSM state on every restart; and CSRF-protected POSTs
are rejected — all with only a W009 line in a non-fatal boot log. The realistic trigger
is an operator debugging a production bootstrap failure who copies `DJANGO_ONESHOT=1`
out of `docker-compose.dev.override.yml:53` into `.env.prod`. That is plausible, not
certain.

**Why MEDIUM and not HIGH.** Under the phase-02 taxonomy, HIGH covers *secret validation
absent*. The validation is present; what is missing is a guard on the *guard*. Under the
validation handbook §8, HIGH is reserved for stale/overbroad findings and blocks merge
into the report, which is the wrong instrument for a live, cheap-to-fix design defect.
MEDIUM with P0 ordering preserves the correct urgency without inflating the class.

**Recommendation — accepted; prefer option (a), and note what already exists.**
1. **Preferred:** ignore `DJANGO_ONESHOT` / `DJANGO_BUILD` in `prod.py` unless
   `DJANGO_SETTINGS_MODULE` is not a `*.prod` module. This is a three-line change and
   keeps the dev bootstrap working unchanged, because the five dev one-shot services all
   run `config.settings.prod` *with* the flag — which is exactly the case that would now
   require `DJANGO_ONESHOT` to be honoured. Careful: option (a) as written would break
   the dev one-shot services, because they use **prod** settings. It must be scoped the
   other way — e.g. honour the flag only when a dedicated
   `DJANGO_BOOTSTRAP_CONTEXT` marker *and* a non-prod deployment signal are both
   present, or (preferred, cleaner):
2. **Option (b), now clearly superior:** move the five one-shot services onto a
   dedicated `config.settings.bootstrap` module that inherits from `base` with dev-grade
   transport flags, leaving `prod.py` unconditionally strict. This is the only option
   that actually achieves the stated goal, because options that scope by settings-module
   name cannot distinguish "one-shot in dev" from "one-shot in prod" — the two are
   configured identically.
3. **Regardless of (1) or (2):** remove `DJANGO_ONESHOT` from the "Python-consumed"
   allowlist group in `base.py:21` and give it its own entry with an explanatory comment
   stating it is a build/bootstrap flag that must never appear in a production secret
   file. `test_compose_hardening.py:255` covers the Compose channel; the `.env` channel
   is what has no coverage. Add the matching assertion for `.env.prod.example`.

**Mandatory companion test (and a trap — see `VAL-001`):** assert that
`DJANGO_ONESHOT=1` + `DJANGO_SETTINGS_MODULE=config.settings.prod` + blank
`SECRET_KEY` **still raises**. This assertion is currently the *opposite* of what a
shipped test asserts.

**Effort:** S (≈0.5 person-day). **Priority:** P0 (ordering unchanged).

---

### CFG-004 — [MEDIUM] — `EMAIL_BACKEND` is env-overridable in production; transactional email can be routed to stdout

**Verdict: CONFIRMED — MEDIUM (unchanged).** Type: `SPEC-DEVIATION`.

**Reproduced (V7).** `base.py:391-394` reads the backend from the environment with an
SMTP default and no allow-list; `prod.py` never re-pins it (verified by reading all 251
lines — the module pins `DEBUG`, the four `SECURE_*` flags and `SECURE_PROXY_SSL_HEADER`,
but treats mail transport as ordinary overridable configuration). Under a fully valid
production environment — real `EMAIL_HOST` guard satisfied, all secrets present — setting
`EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` yields:

```text
PROD EMAIL_BACKEND = django.core.mail.backends.console.EmailBackend
EMAIL_HOST guard value present: True
Subject: subj
...
RESET-TOKEN-abc123
messages sent (no exception raised)
```

The `EMAIL_HOST` guard is satisfied by any non-empty string and is entirely irrelevant
once the backend is not SMTP — exactly as the auditor stated. The body is emitted to
stdout, which in production is the JSONL log stream
(`prod.py:22-36`, `RedactingJsonFormatter`). The redaction formatter redacts *sensitive
field values in log records*; it does not intercept arbitrary `print`/`write` output
from a mail backend, so message bodies pass through.

**Current state: latent, not live.** Neither `.env.prod.example` nor the real
`.env.prod` contains `EMAIL_BACKEND`, so no operator following the shipped template
hits this. It requires deliberately typing a fully-qualified Django dotted path that
appears in no template and no documentation.

**Why MEDIUM is right, despite the latent trigger.** The taxonomy places "secrets
written to logs" in the HIGH bucket, and the consequence here is real: password-reset
tokens, seller confirmations, alert digests and full support-ticket free text would land
in the log stream, and delivery failures would be invisible to the caller. That harm
class is categorically worse than CFG-001's outage class, which is why this is *not*
reduced even though both are latent. MEDIUM rather than HIGH because the trigger is not
reachable from any shipped artifact.

**Recommendation — accepted, both halves.**
1. In `prod.py`, re-pin `EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"`
   unconditionally, exactly as `DEBUG` is pinned, leaving the `dev.py` / `test.py`
   console/locmem overrides untouched.
2. For operators who genuinely need a non-SMTP transport, add a `StrEnum`
   (e.g. `EmailTransport`) read from a single env var and map it to a backend inside
   `prod.py`, so the permitted set is closed and validated rather than an arbitrary
   dotted path. This also satisfies the project rule that fixed values use `StrEnum`.

**Effort:** S (<0.5 person-day). **Priority:** P1.

**Rollout safety:** MEDIUM risk — re-pinning breaks any deployment that currently
relies on the env override to reach a non-SMTP transport. Such a deployment must adopt
the `StrEnum` path first. Test that must cover it: `settings.EMAIL_BACKEND` is the SMTP
backend under `config.settings.prod` **even when** the env var is set to the console
backend.

---

### CFG-005 — [MEDIUM] — `BOT_USERNAME` placeholder is unvalidated and is persisted into the DB by a migration

**Verdict: CONFIRMED — MEDIUM (unchanged).** Type: `SPEC-DEVIATION`.

**Verified in full.** `prod.py:153-188` runs `_validate_production_secret` over exactly
three values — `DJANGO_SECRET_KEY` (153-159), `BOT_TOKEN` (168-174),
`GOOGLE_TRANSLATE_API_KEY` (180-188). No equivalent block exists for `BOT_USERNAME`.
`base.py:309` gives it `default=""`. Both `.env.prod.example:31` and `.env.dev.example:31`
ship the literal `BOT_USERNAME=<your-bot-username>`.

**The validator-bypass claim is correct and provable.** `0003_add_bot_username.py:36-47`
declares `RegexValidator(regex="^[A-Za-z0-9_]{3,32}$")` on the field, then seeds with
`SiteConfig.objects.filter(pk=1, bot_username="bazuna_bot").update(bot_username=bot_username)`
(line 22-24). `QuerySet.update()` does not call `full_clean()`, so the validator is
never evaluated. The shipped template value `<your-bot-username>` contains `<`, `>` and
`-`, all of which the regex rejects — the write is provably invalid under the model's
own contract.

**The persistence claim is correct and stronger than stated.** The migration is applied
once and recorded in `django_migrations`; it will not re-run. Even a forced re-run is
guarded by `filter(pk=1, bot_username="bazuna_bot")`, so a value already overwritten
with the placeholder is not repaired. I found **no** management command or signal that
re-syncs `SiteConfig.bot_username` from settings — the only writers are
`0003_add_bot_username.py` and a Django-admin edit. The auditor's conclusion that "a
Django-admin edit becomes the only remedy" is **correct**.

**Blast radius confirmed by consumer sweep.** The DB value wins over the env var:
`apps/core/services/site_config.py:45-62` (`get_bot_username`) reads the model and
caches it, and is consumed by `users/views/consent.py:331` (the Telegram login deep link),
`core/templatetags/telegram_tags.py:163` (base64-encoded contact deep links),
`ads/views/listings.py:93`, `core/context_processors.py:93` and `core/views.py:63-68`
(footer). So a placeholder produces dead `t.me/<your-bot-username>?start=…` links
site-wide. Note the bot itself is unaffected: `telegram_bot/handlers/support.py:184`
derives the username from the Telegram API, not from settings.

**Recommendation — accepted, with the priority inverted inside it.** Validate
`BOT_USERNAME` against placeholders in **both** `prod.py` and `dev.py` (the dev half is
the cheaper one and stops the bad value from reaching the database in the first place,
because the dev one-shot services use prod settings and run the migration). Then make
`0003` validate before writing: fetch the row, assign, `full_clean()`, save — which
also protects any future operator editing the template.

**Effort:** S (≈0.5 person-day). **Priority:** P1.

**Rollout safety:** MEDIUM risk, unchanged and correctly identified by the auditor — a
deployment already seeded with a placeholder needs a **data** fix (a `SiteConfig` update
or an admin edit), not merely an env fix. Any deployment running with a real
`BOT_USERNAME` is unaffected.

---

### CFG-006 — [MEDIUM] — A bot-only config error in the shared settings module crash-loops the whole dev stack

**Verdict: CONFIRMED — MEDIUM (unchanged).** Type: `SPEC-DEVIATION`.
**This is a live, currently-observable outage and the only finding in the report that
is reproducing right now.**

**Independently re-observed (V10).** `docker ps` shows
`mko-bazuna-dev-web-1 → Restarting (1)` and `mko-bazuna-dev-bot-1 → Restarting (1)`.
`docker logs mko-bazuna-dev-web-1` ends in:

```text
File "/app/src/backend/config/settings/dev.py", line 21, in <module>
    raise ImproperlyConfigured(
django.core.exceptions.ImproperlyConfigured: BOT_TOKEN is a placeholder value from
.env.dev.example. Replace it with a real token from @BotFather, or leave it empty
(BOT_TOKEN=) to skip bot startup in development.
```

**The coupling is structural, not incidental.** `docker-compose.yml:231` and `:274` set
`DJANGO_SETTINGS_MODULE=config.settings.prod` for `web` and `bot` in production —
correct. `docker-compose.dev.override.yml:12` and `:35` flip **both** to
`config.settings.dev`. `dev.py:20-25` raises from module scope, i.e. inside
`django.setup()`, before any process-specific code runs. Both services carry
`restart: unless-stopped` (`docker-compose.yml:245`, `:288`), so the failure presents as
an indefinite crash loop rather than a one-shot exit. A credential only the bot consumes
therefore takes the web tier down, and `docker ps` alone gives no diagnosis.

**The auditor's "three existing settings tests" claim is accurate.** Verified in
`src/backend/config/settings/tests/test_settings_secrets.py`:
`test_bot_token_required_in_dev` (line 268), `test_bot_token_placeholder_rejects_in_dev`
(line 282), `test_bot_token_real_value_allowed_in_dev` (line 290). All three are in the
green set I ran (V16).

**Recommendation — accepted as written**, with one refinement: moving the guard to
`telegram_bot/main.py` immediately after `token = settings.BOT_TOKEN` is correct and
keeps the prod guard untouched (production runs both tiers from one secret source, so a
blank key *must* still fail the web tier fast). The added test pair is the right shape:
`import config.settings.dev` succeeds with a placeholder token, **and**
`telegram_bot.main.main()` refuses to start.

**Effort:** S (≈0.5 person-day). **Priority:** P1 — and because the dev stack is
currently down, this is unblocked work for whoever picks this up.

**Rollout safety:** MEDIUM, as the auditor states. The three dev placeholder tests must
be retargeted to the bot entrypoint in the same commit as the move, or the suite goes
red. The dev override's five one-shot services are unaffected (they use prod settings
and do not import `dev.py`).

---

### CFG-007 — [MEDIUM] — `STATICFILES_STORAGE` in `prod.py` is a dead setting removed from Django 5.1+

**Verdict: CONFIRMED — MEDIUM (unchanged).** Type: `SPEC-DEVIATION` (dead config).

**Verified (V8).** `prod.py:225` sets
`STATICFILES_STORAGE = "theme.storage.ThemeStaticFilesStorage"`. Under the installed
Django 5.2.17: `hasattr(django.conf.global_settings, "STATICFILES_STORAGE")` is
`False` while `STORAGES` is present — so the setting is not read by any code path.
Django accepts arbitrary uppercase module attributes without validating them, so the
line is silently inert. I additionally confirmed Django's own `security` check module
does not reference `STATICFILES_STORAGE` at all, so not even a W-series warning fires.

**The effective configuration is owned elsewhere and already agrees.**
`base.py:293-300` sets `STORAGES["staticfiles"]["BACKEND"]` to the same
`theme.storage.ThemeStaticFilesStorage`. The two settings do not currently disagree —
the dead key is redundant, not wrong.

**The secondary coupling the auditor identified is real.** `test.py:30-38` reasons at
length about "the production/dev storage (`ThemeStaticFilesStorage`)" while
`test.py:39-46` overrides `STORAGES` itself; the comment's subject is therefore
`base.py`'s dict, not `prod.py`'s line. If `prod.py:225` were later "fixed" by someone
who trusted the comment, nothing would change.

**Recommendation — accepted.** Delete `prod.py:225`; `STORAGES` in `base.py` is already
the single source of truth. Add a test asserting
`settings.STORAGES["staticfiles"]["BACKEND"] == "theme.storage.ThemeStaticFilesStorage"`
so the real decision is pinned and the dead key cannot silently return.

**Effort:** S (<0.5 person-day, one-line deletion). **Priority:** P2.
**Severity note:** MEDIUM is the taxonomy's own bucket for "unused config fields", so
the rating is correct even though the effort is trivial. Fix it opportunistically; do
not schedule it.

---

## Findings — LOW

### CFG-008 — [LOW] — `RUN_TRANSLATION_BACKFILL` is absent from `ALLOWED_ENV_VARS` and from all env templates

**Verdict: CONFIRMED — LOW (unchanged).** Type: `SPEC-DEVIATION`.

**Independently re-derived (V14).** I ran my own sweep of every `env()` / `env.*()` /
`os.getenv` / `os.environ[...]` name across non-test `src/**/*.py` and diffed it against
`ALLOWED_ENV_VARS`. Result: **33 consumed names, 48 allowlisted, and exactly one
consumed name missing from the allowlist — `RUN_TRANSLATION_BACKFILL`.** The auditor's
claim is precise, not approximate. (The auditor's own diff transcript also listed
`BASH_SOURCE`, `SCRIPT_DIR`, `PYTEST_*` and a stray token; those are shell-var noise and
test-only entrypoint variables and should be struck from the evidence — the conclusion
is unaffected.)

**The variable is real, consumed and documented.** Read at
`src/backend/apps/core/utils/migrate_locked.py:57`; documented in **six** tracked
files, not five: `docs/01-spec/architecture-structure.md:207` and `:315`,
`docs/99-agent/architecture.md:57`, `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md:80`, `:125`
and `:192`, `docs/ops/docker-deployment.md:145` and `:330`,
`docs/ops/migration-workflow.md:83`, `:95`, `:107`, `:343` and `:412`, plus the command
docstring at `apps/core/management/commands/bootstrap_reference_data.py:5`, `:43`, `:52`,
`:63`. It is absent from all four `.env*.example` templates (V15).

**The impact is exactly the alert-fatigue mechanism the auditor describes, and it is
the right characterisation.** An operator following `migration-workflow.md:95` and
adding `RUN_TRANSLATION_BACKFILL=true` to `.env.prod` receives, at every container boot,
a warning worded identically to a genuine typo
(`base.py:50-55`: *"not in ALLOWED_ENV_VARS (possible typo; value will be ignored by
env() calls)"*). The warning is factually wrong for this key. The allowlist's only
purpose is to surface exactly this class of error, so a false positive on a documented
key degrades the one mechanism that would catch a real `BOT_T0KEN` typo.

**Recommendation — accepted in full, including the durable half.**
1. Add `"RUN_TRANSLATION_BACKFILL"` to `ALLOWED_ENV_VARS` and document it in
   `.env.prod.example` next to the `migrate` notes.
2. Add the **reverse-direction** test the auditor proposes: every `os.getenv` / `env()`
   name in non-test `src/**` must appear in `ALLOWED_ENV_VARS`. This is the same test
   CFG-009 needs; implement it once.

**Effort:** S (<0.5 person-day). **Priority:** P2.

---

### CFG-009 — [LOW] — `.env.example` omits 19 consumed variables including the whole `EMAIL_*` block

**Verdict: CONFIRMED — LOW (unchanged).** Type: `DOC-UPDATE`.

**The count of 19 reconciles exactly (V15), including the production-mandatory
`EMAIL_HOST`.** My independent key-name extraction:

- `.env.example` — 26 keys. Absent from the Python-consumed set:
  `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
  `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`, `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`,
  `SUPPORT_NOTIFICATION_RECIPIENTS`, `POSTGRES_HOST`, `POSTGRES_PORT`, `DATABASE_URL`,
  `BOT_LIVENESS_FILE`, `BOT_HEALTH_STALE_SECONDS`, `BOT_HEALTH_CHECK_ENABLED`,
  `SCHEDULER_LIVENESS_FILE`, `SCHEDULER_COMMAND_TIMEOUT`, `RUN_TRANSLATION_BACKFILL`,
  `SCHEDULER_HEALTH_STALE_SECONDS` — **19**, once the three `DJANGO_*` control variables
  (which correctly should *not* be in a secret template) are excluded and the
  shell/consume-in-healthcheck variables are included. The auditor enumerated 18 names
  and asserted 19; the nineteenth is `SCHEDULER_HEALTH_STALE_SECONDS` (read by
  `docker/healthcheck-scheduler.sh:26`, set to `7200` at `docker-compose.prod.yml:98`).
  The headline figure is right; the enumeration is one short.
- `.env.prod.example` is missing 9 of the same (`DATABASE_URL`, `POSTGRES_PORT`,
  `BOT_LIVENESS_FILE`, `BOT_HEALTH_STALE_SECONDS`, `BOT_HEALTH_CHECK_ENABLED`,
  `SCHEDULER_LIVENESS_FILE`, `SCHEDULER_COMMAND_TIMEOUT`, `EMAIL_BACKEND`,
  `PROMETHEUS_MULTIPROC_DIR` is present but `SCHEDULER_HEALTH_STALE_SECONDS` is not).
  Confirmed.

**The file presents itself as authoritative and is not.** `.env.example:1` reads
*"Comprehensive environment variables template for Mko Bazuna"*, and lines 3-6 tell the
reader to copy one of the three tier templates. In practice no compose file, script or
Makefile target uses `.env.example` — the operational templates are `.env.dev.example`,
`.env.prod.example` and `.env.test.example`. The real risk is exactly the auditor's: an
operator treats the "comprehensive" file as the reference for what a deployment must set
and produces a `.env.prod` that fails boot on `EMAIL_HOST`, a variable they were never
shown.

**A minor additional defect the auditor missed:** `.env.example:1` begins with a UTF-8
BOM (`﻿#`). Cosmetic, but it will defeat a naive `startswith("#")` parser and is
trivially removed in the same edit.

**Recommendation — adopt the documentation branch, not the deletion branch, and see
`VAL-003`.** The auditor offered "add the missing blocks" *or* "delete the file and point
the header at the three tier templates, which are the ones actually used", presenting
them as cost-equivalent. They are not — see `VAL-003`. Recommended form:
1. Retitle `.env.example` to drop the word "Comprehensive" and state plainly that the
   three tier templates are authoritative (this alone removes the trap, at zero risk).
2. Add the missing blocks, or mark each as "see `.env.prod.example`".
3. Ship the reverse-direction template test from CFG-008, widened to
   `consumed_env_names ⊆ keys(<tier template>)` for the tier templates — which is the
   durable half and the part that actually prevents recurrence.

**Effort:** S (<0.5 person-day). **Priority:** P2.

---

### CFG-010 — [LOW] — `test.py` does not reset `SECURE_HSTS_*`, contradicting its own "mirrors dev" comment

**Verdict: CONFIRMED — LOW (unchanged).** Type: `SPEC-DEVIATION`.

**Measured, not inferred (V9).**

| Setting | `config.settings.test` | `config.settings.dev` | `base.py` |
|---|---|---|---|
| `SECURE_SSL_REDIRECT` | `False` | `False` | `True` |
| `SESSION_COOKIE_SECURE` | `False` | `False` | `True` |
| `CSRF_COOKIE_SECURE` | `False` | `False` | `True` |
| `SECURE_HSTS_SECONDS` | **`3600`** | `0` | `3600` |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | **`True`** | `False` | `True` |
| `SECURE_HSTS_PRELOAD` | `False` | `False` | `False` |

`test.py:18-24` resets three settings under a comment that says *"Mirrors
config/settings/dev.py (test settings must behave like dev, not prod)"*; `dev.py:49-52`
zeroes the HSTS triple; `test.py` inherits the HSTS triple from `base.py:158-160`. The
comment's claim is not honoured, and the three environment modules are no longer
mutually consistent on the transport tuple.

**Impact is narrow and the auditor is right to scope it.** No effect on the pytest suite:
Django's test client issues plain HTTP and is not subject to browser HSTS caching, and
`SECURE_SSL_REDIRECT` is already `False` so `SecurityMiddleware` does not redirect. The
exposure is to a human or browser-driven tool pointed at a test-mode server, which
caches `Strict-Transport-Security: max-age=3600; includeSubDomains` after one request and
then upgrades every subsequent `http://` request to HTTPS for an hour.

**Taxonomy note (recorded so the rating is not mistaken for an oversight).** The
phase-02 taxonomy puts "divergent per-environment behavior" in the HIGH bucket. That
bucket is written for *production-relevant* divergence. The `test` module sets
`DEBUG = True` (`test.py:16`), disables migrations entirely (`test.py:78-97`), swaps the
static-files backend (`test.py:39-46`) and disables the production email backend
(`test.py:69`) — it is non-production-grade **by design**, and the HSTS triple is one
more line in a module that is already deliberately divergent. There is no security
consequence. LOW is correct.

**Recommendation — accepted, but the priority is below the auditor's P2 grouping.** Add
the three lines to `test.py` mirroring `dev.py:50-52`, and add the dev/test transport-tuple
parity assertion that makes the comment machine-checked instead of aspirational. This is
a good candidate to be absorbed into whatever settings-test change lands for CFG-001 or
CFG-002 rather than scheduled on its own.

**Effort:** S (<0.5 person-day, three assignments). **Priority:** P3 (down from P2 —
the impact is browser-cache-only and the module is deliberately divergent).

---

### CFG-011 — [LOW] — `base.py` comment cites a non-existent "Env schema" for `BOT_TOKEN` validation

**Verdict: ADJUSTED — LOW (held), root cause corrected, long-term recommendation
rejected.** Type: `DOC-UPDATE`.

**The defect stands.** `base.py:116` reads:
`# Telegram bot token (required for bot process, validated via Env schema)`. There is no
settings *schema* object. `git grep` for `pydantic_settings|BaseSettings` across the
repository returns **zero** matches; Pydantic v2 is a dependency
(`pyproject.toml:28`) used only for `BaseInputModel` and the search/CSP models. Actual
validation of `BOT_TOKEN` is two hand-rolled regexes in two places —
`prod.py:16` (`_SECRET_PLACEHOLDER_RE` + `_validate_production_secret`) and `dev.py:15`
(`_BOT_TOKEN_PLACEHOLDER_RE`, whose own comment at `dev.py:13-14` records that it was
*copied* from `prod.py` "to avoid importing prod settings").

**The auditor's root-cause statement is partly wrong, and the correction matters for the
fix.** The report says "no such schema exists anywhere in the repository — there is no
`pydantic_settings.BaseSettings` subclass and **no `Env` model**." An `Env` entry *does*
exist: `base.py:62-67` instantiates `env = environ.Env(DEBUG=(bool, False),
BOT_TOKEN=(str, ""))`, so `BOT_TOKEN` has a declared cast and default in the
django-environ schema. What that entry provides is a **cast and a default, not
validation** — which is precisely why the comment misleads. The accurate root cause is:
*the comment names the right container and the wrong mechanism*, so a maintainer looks
for a schema that performs validation, finds only a cast, and must re-derive the real
mechanism from two partially duplicated implementations.

**The "longer term, add a Pydantic v2 settings model" half of the recommendation is
REJECTED as overengineering.** A settings module is not a system boundary in the sense
the project rule means (bot input, settings schemas for external configuration contracts,
future API). Introducing `pydantic-settings` would mean re-implementing or wrapping
django-environ, which is woven through every module (`base.py`, `prod.py`, `dev.py`,
`test.py`, the migrations, the entrypoints) and is explicitly relied on for its
`overwrite=False` semantics that the test suite depends on. The ROI is negative at this
project scale and the migration risk is real.

**Accepted recommendation (short form only):** correct `base.py:116` to name the actual
mechanism and its two locations, e.g. *"validated by placeholder/dummy regexes in
`prod.py:_validate_production_secret` and `dev.py:_BOT_TOKEN_PLACEHOLDER_RE`"*. This is
a one-line comment change. If the duplicated-regex hazard is also worth addressing, the
correct home is a single small shared helper in `config/settings/` — which is option (2)
of CFG-005's remediation and can be done without any Pydantic involvement.

**Effort:** S (<0.5 person-day, one comment line). **Priority:** P2.

---

## Validation Findings (phase-02 `VAL-` namespace)

These are defects in the **audit inputs and remediation plans**, not source-code defects.
The `VAL-` prefix is scoped to phase 02; phase 01 and phase 04 each opened their own
`VAL-` series, so IDs collide across phases by design and must be disambiguated by phase
when they are aggregated.

### VAL-001 — [MEDIUM] — CFG-001's remediation is pinned by a shipped green test, which the rollout table omits

> - **Action:** rollout-safety issue (new finding).
> - **Detail:** `src/backend/config/settings/tests/test_settings_secrets.py:338`
>   `test_django_oneshot_bypasses_all_secrets` **asserts the CFG-001 bypass as intended,
>   correct behaviour**, with a docstring explaining that the dev one-shot services
>   legitimately need it. It is in the green set (V16 — 60 passed). Any fix that scopes
>   or removes the bypass turns this test red. The auditor's Rollout Safety table for
>   CFG-001 lists only the *new* regression assertion to add ("assert `DJANGO_ONESHOT=1`
>   + `config.settings.prod` + blank `SECRET_KEY` still raises") and does not mention
>   that the existing suite asserts the opposite. A remediation that follows the table
>   literally will land a red suite and be reverted.
> - **Required fix:** rewrite `test_django_oneshot_bypasses_all_secrets` in the same
>   commit as the `prod.py` change — to assert the bypass applies only under the
>   bootstrap context — and add the new prod-strict assertion alongside it. Verify with
>   the scoped run from V16.
> - **See also:** CFG-001.

### VAL-002 — [MEDIUM] — CFG-003's recommended fix does not close the exposure it names, and would create false assurance

> - **Action:** wrong / incomplete recommendation (new finding).
> - **Detail:** The finding argues that moving the password out of argv is worthwhile
>   because the argv is *"permanently embedded in the container's runtime argv"* and
>   visible via `docker inspect` / `ps` / `/proc/*/cmdline`. But the credential is
>   **already** in cleartext in the container's environment: `create_admin` receives it
>   through `env_file: .env.prod` (`docker-compose.prod.yml:44-45`), and I verified
>   against the live container (V13) that `ADMIN_PASSWORD` **is present in
>   `Config.Env`**. `docker inspect` therefore already returns the plaintext password,
>   and inside the container `/proc/1/environ` is readable by the same uid that could
>   read `/proc/1/cmdline` — so argv crosses no additional privilege boundary. The
>   recommended fix (read from `os.environ` inside the command) reduces the exposure to
>   *exactly* the same level it is already at, while the report's impact text implies it
>   removes it.
> - **Secondary hazard:** the container is a single-process one-shot, so the threat model
>   in the finding ("a sidecar, a debugger, a crash handler that captures argv") has no
>   concrete instance in this deployment. `ALLOWED_ENV_VARS` (`base.py:34`) also already
>   classifies `ADMIN_PASSWORD` as a legitimate "shell/entrypoint/compose-injected" var,
>   so the current design accepted this channel deliberately.
> - **Required fix:** re-scope CFG-003 to `LOW` **defense-in-depth / command-contract
>   hygiene** ("`--password` is `required=True`, so a secret must always travel by
>   argv"; the argv itself is not the exposure), **or** — if the goal is genuinely to
>   stop the credential appearing in `docker inspect` — state that goal and scope the
>   fix to the `env_file` channel (a Docker secret or a file-mounted credential read by
>   the command), which is the only change that reduces the real exposure.
> - **See also:** CFG-003.

### VAL-003 — [LOW] — CFG-009's "delete `.env.example`" branch is blocked by two shipped tests and one spec line

> - **Action:** remediation hazard (new finding).
> - **Detail:** The recommendation offers two branches and describes them as
>   interchangeable: *"Either add the missing blocks to `.env.example` (or delete the
>   file and point the header at the three tier templates…)"*. The deletion branch is
>   not cost-equivalent. `.env.example` is load-bearing for:
>   - `src/backend/config/settings/tests/test_csrf_trusted_origins.py:134-135` —
>     asserts `.env.example` contains `CSRF_TRUSTED_ORIGINS`;
>   - `src/backend/config/settings/tests/test_prod_logging.py:149-160` — asserts
>     `.env.example` contains `SENTRY_DSN`;
>   - `docs/01-spec/architecture-structure.md:155` — lists the file in the documented
>     repository structure.
>   Deleting it therefore turns two green tests red (both in the V16 suite) and
>   desynchronises a spec document, converting a LOW documentation finding into a
>   code + doc + test change.
> - **Required fix:** in the remediation plan, mark the deletion branch as rejected and
>   keep the retitle + add-blocks branch. If deletion is genuinely wanted, it is a
>   separate change that must retire the two tests and update the spec line.
> - **See also:** CFG-009.

### VAL-004 — [LOW] — Cross-phase overlap: CFG-002 is one of four instances of a single anti-pattern (confirms phase 01's VAL-003)

> - **Action:** cross-phase relationship; **not** a merge.
> - **Detail:** Phase 01's validator independently reached the same conclusion and
>   filed it as `VAL-003` in
>   `.ai/audit/99-validation/01-entry-architecture-validated-findings.md:763-774`:
>   ENT-001 (`PROMETHEUS_MULTIPROC_DIR` set only in the prod override), ENT-011
>   (`stop_grace_period` set only on `web` and `scheduler`), ENT-012 (the dev `bot`
>   inherits a different `depends_on` than the dev `web`), and CFG-002 (the CI
>   prod-config gate silently dead) are four instances of *a contract asserted in exactly
>   one place with nothing verifying every environment satisfies it*. I independently
>   confirmed the CFG-002 half and add a fifth instance from the config side:
>   `ALLOWED_ENV_VARS` / `.env.*.example` drift (CFG-008, CFG-009) is the same shape —
>   a contract held in one hand-maintained list with only one of two directions tested.
> - **Verdict on overlap:** retain all five findings separately. The root causes differ
>   (compose file vs. workflow env block vs. allowlist), the fixes differ, and merging
>   would obscure the fact that five separate contracts are unguarded. What should be
>   recorded is a **single** recommendation: introduce one CI assertion that validates
>   every environment's contract (compose rendering parity, prod-settings import parity
>   against a single shared required-variable constant, and bidirectional
>   consumed↔allowlist parity) rather than five one-line patches. That has materially
>   better ROI than the sum of the parts.
> - **Coordination:** phase 01 is complete and its `VAL-003` is closed; phase 12
>   (production-ops) has not been validated at this time. **No conflicting evidence**
>   was found between any phase on this point.
> - **See also:** CFG-002, CFG-008, CFG-009, ENT-001, ENT-011, ENT-012,
>   phase-01 `VAL-003`.

### VAL-005 — [LOW] — The "no real credential is committed" conclusion is manual-sweep based, not tool-verified

> - **Action:** audit-input limitation (new finding).
> - **Detail:** Verification step R-03 of the phase-02 handbook calls for a hardcoded
>   secret scan, and the project's declared control is `gitleaks` via `.pre-commit-config.yaml`
>   and `.gitleaks.toml` plus a blocking CI `gitleaks` job
>   (`.github/workflows/ci.yml:368-373`, SARIF upload). **`gitleaks` and `pre-commit`
>   are not installed on this host**, so the declared control could not be executed. The
>   auditor substituted manual `git grep` sweeps. Those sweeps are a reasonable
>   substitute and I extended them (V12: full-history `git log -S`, key-shape
>   classification of every tracked `ADMIN_PASSWORD` occurrence, with the one committed
>   non-empty literal confirmed to be a lowercase `test`-fixture shared identically
>   between `.env.test.example:47` and `docker-compose.test.yml:108`) — and I found no
>   real credential. But this is **not** the same assurance level as a gitleaks run and
>   must not be reported as one.
> - **Required handling:** the final consolidated report must state that the
>   "no hardcoded secret" conclusion rests on manual pattern sweeps, and that the
>   project-declared `gitleaks` control was **not** exercised in this environment. Do
>   not upgrade it to "verified by the project's secret scanner".
> - **See also:** the source report's R-03 and R-04 rows.

---

## Cross-Finding and Cross-Phase Analysis

**Same root cause (merge candidates).** No hard merges. One soft pair, both retained:
**CFG-008 ↔ CFG-009** share the root cause "the env contract is hand-maintained and only
one of two drift directions is tested" — the fix for both is the *same* new
reverse-direction test, so they should be implemented together, not separately. This
extends to phase 01's ENT-001/011/012 via `VAL-004`: five findings, one anti-pattern.

**A second, cross-finding dependency the auditor under-stated.** **CFG-005 and CFG-011
are coupled in a way that changes the order of work.** CFG-005 requires adding a
placeholder check for `BOT_USERNAME`; CFG-011 documents that the placeholder/dummy
detection is currently duplicated in two modules with a *copied* regex
(`dev.py:13-14` says so explicitly). Adding a third copy for `BOT_USERNAME` would make
it three. The auditor's own roadmap places CFG-011 at position 11, last. That is the
wrong order: extract the shared helper **first** (or merge the two changes), otherwise
the remediation entrenches the duplication CFG-011 is complaining about.

**Conflicting evidence.** **None across phases.** The only apparent collision —
phase 01's "web crash-loops" (ENT-001) versus CFG-006's "dev stack crash-loops" — is
complementary: different containers, different causes (a missing Prometheus env var
versus a bot-only credential). Verified directly: the two live dev containers are dying
at `config/settings/dev.py:21`, not in gunicorn.

**Dependency chains (rollout-ordering constraints).**

1. **CFG-001 must be resolved before CFG-002 can be trusted.** Adding `EMAIL_HOST` and
   `REDIS_URL` to `deploy-check` achieves nothing while a `.env.prod` value can still
   bypass the guards — and the new shared-variable-set test would then be asserting
   against a requirement set that is itself conditional. Confirmed and retained.
2. **CFG-001 and `VAL-001` must land in the same commit** (the rewrite of
   `test_django_oneshot_bypasses_all_secrets`), or the suite goes red.
3. **CFG-005 and CFG-011 should be merged** or ordered CFG-011-first, to avoid a third
   copy of the placeholder regex.
4. **CFG-008 and CFG-009 share one test implementation** and should land together.
5. No circular dependencies were detected among CFG-001…CFG-011.

---

## Corrected Remediation Roadmap

The auditor's ordering is broadly sound; four changes are required and one reordering is
recommended.

| Order | ID | Final severity | Effort | Change from the auditor's plan |
|-------|----|----------------|--------|-------------------------------|
| 1 | CFG-001 | MEDIUM | S | **Reordered from #1 to #1 (unchanged) but severity reduced**; option (a) is now shown to be incorrect as literally written (dev one-shots use *prod* settings, so scoping by module name cannot distinguish dev from prod) — prefer option (b), a dedicated `config.settings.bootstrap`. **Must land with `VAL-001`.** |
| 2 | CFG-002 | HIGH | S | **Promoted in urgency rationale.** 2 lines restore the gate; also move the orphaned contract comment from `ci.yml:375-381` to `deploy-check:`. Consider landing this *first* in practice — it is a 2-line CI-only change with no test churn, whereas CFG-001 is entangled with a shipped test. |
| 3 | CFG-006 | MEDIUM | S | Unchanged. The dev stack is **currently down** for this reason; unblocked and cheap. |
| 4 | CFG-005 | MEDIUM | S | Unchanged in position; **implement on top of CFG-011's shared helper** rather than adding a third regex copy. |
| 5 | CFG-004 | MEDIUM | S | Unchanged. |
| 6 | CFG-011 | LOW | S | **Moved from #11 to #4** (ahead of CFG-005) so the shared helper exists before the `BOT_USERNAME` check is added. Pydantic half **rejected**. |
| 7 | CFG-003 | **LOW** | S | **Down-graded**; re-scoped per `VAL-002` — fix only if the goal is to remove the `env_file` exposure, not the argv. |
| 8 | CFG-008 | LOW | S | Unchanged; implement together with CFG-009. |
| 9 | CFG-009 | LOW | S | Unchanged; **deletion branch rejected** per `VAL-003`; adopt the retitle branch. |
| 10 | CFG-007 | MEDIUM | S | Unchanged in position; fix opportunistically, do not schedule. |
| 11 | CFG-010 | LOW | S | **Down-graded P2→P3**; absorb into whatever settings-test change lands for CFG-001/002. |

**Cross-cutting recommendation (from `VAL-004`, replaces five one-line patches):** add a
single CI assertion group that validates every environment's contract —
(a) compose rendering parity for the invariants ENT-001/011/012 already half-cover,
(b) a `config.settings.prod` subprocess import driven by one shared required-variable
constant consumed by both `deploy-check` and a unit test (closes CFG-002's detection
gap durably), and (c) bidirectional parity between consumed env names,
`ALLOWED_ENV_VARS`, and the tier templates (closes CFG-008 + CFG-009 durably). This is
the single highest-ROI change in the whole phase.

---

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| CFG-001 | **Med** — option (a) as literally written would break the five dev one-shot services, because they run `config.settings.prod` *with* `DJANGO_ONESHOT=1`; scoping by settings-module name cannot distinguish dev-bootstrap from prod-bootstrap. Option (b) is safe. | Yes, under option (b) | **+ `VAL-001`: `test_django_oneshot_bypasses_all_secrets` must be rewritten in the same commit.** New assertion: `DJANGO_ONESHOT=1` + `config.settings.prod` + blank `SECRET_KEY` still raises. Existing `test_compose_hardening.py:255` already covers the Compose channel; add the `.env.prod.example` channel. |
| CFG-002 | Low — CI-only; the added values are non-secret placeholders. | Yes | Subprocess import of `config.settings.prod` using the `deploy-check` variable set parsed from `ci.yml`, running in the `test` job so a future guard addition fails there. |
| CFG-003 | Low — the entrypoint and the command change together; the empty-password skip path (`entrypoint-create-admin.sh:18-21`) must be preserved. | Yes | `create_admin_user` resolves the password with `--password` absent, and with `ADMIN_PASSWORD` absent-and-empty. Note per `VAL-002` this does not reduce the real exposure. |
| CFG-004 | Med — re-pinning `EMAIL_BACKEND` breaks any deployment currently relying on the env override to reach a non-SMTP transport; such a deployment must adopt the `StrEnum` path first. | Yes | `settings.EMAIL_BACKEND` is the SMTP backend under `config.settings.prod` **even when** the env var is set to the console backend. |
| CFG-005 | Med — a deployment already seeded with a placeholder needs a **data** fix, not an env fix. | Yes | Placeholder `BOT_USERNAME` rejected in dev and prod; migration `0003` refuses to write a value failing the `RegexValidator`. |
| CFG-006 | Med — `config.settings.dev` will import with a placeholder `BOT_TOKEN`; three existing tests assert the import-time rejection. | Yes | `import config.settings.dev` succeeds with a placeholder token; `telegram_bot.main.main()` refuses to start; the three `test_settings_secrets.py` tests (lines 268, 282, 290) retarget. |
| CFG-007 | Low — one-line deletion; `STORAGES` already carries the same value. | Yes | `settings.STORAGES["staticfiles"]["BACKEND"]` is `theme.storage.ThemeStaticFilesStorage` under prod settings. |
| CFG-008 | Low — allowlist entry and template note only. | Yes | `test_example_keys_in_allowlist` still passes; the new reverse-direction test passes with no further gaps. |
| CFG-009 | Low — documentation/template change. | Yes | Reverse-direction template test passes; no allowlist test regresses. **Do not delete the file** (`VAL-003`). |
| CFG-010 | Low — three added assignments in a test-only module. | Yes | dev/test transport-tuple parity assertion; the existing suite already runs with `SECURE_SSL_REDIRECT = False`. |
| CFG-011 | Low — one comment line. The rejected Pydantic half would have been **High** risk (reimplementing django-environ under `full_clean()`-style validation semantics the test suite depends on). | Yes | Existing placeholder tests pass unchanged. |

**Hidden dependency chain found in R4:** CFG-001 → `VAL-001` (shipped test pins the
behaviour being removed). This is the only circular or ordering-critical interaction
inside phase 02.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 8 | CFG-002, CFG-004, CFG-005, CFG-006, CFG-007, CFG-008, CFG-009, CFG-010 |
| Reclassified | 0 | — |
| Severity-adjusted | 3 | CFG-001 HIGH→MEDIUM, CFG-003 MEDIUM→LOW, CFG-010 P2→P3 |
| Reclassified (type) | 3 | CFG-003 → `BEST-PRACTICE`; CFG-009 → `DOC-UPDATE`; CFG-011 → `DOC-UPDATE` |
| Merged | 0 | No finding was a true duplicate. CFG-008/CFG-009 and CFG-005/CFG-011 are coupling relationships, not merges. |
| Rejected | 0 | No finding was stale, already-implemented, or unverifiable. Every finding survived independent verification; four needed correction or down-scoping. |
| VAL- (audit-input / rollout) | 5 | VAL-001 (MEDIUM), VAL-002 (MEDIUM), VAL-003 (LOW), VAL-004 (LOW), VAL-005 (LOW) |
| Recommendations rejected | 2 | CFG-011's Pydantic-v2 settings model; CFG-009's `.env.example` deletion branch |

### Reclassified Findings

| ID | Original | New | Rationale |
|----|----------|-----|-----------|
| CFG-003 | `SPEC-DEVIATION` (implied security) | `BEST-PRACTICE` | No additional exposure exists to remove — the secret is already in `Config.Env`. What remains is command-contract hygiene (`--password` is `required=True`, forcing secrets through argv), which is a hardening/consistency matter, not a deviation from a stated requirement. |
| CFG-009 | `SPEC-DEVIATION` (implied) | `DOC-UPDATE` | No runtime defect: the missing values fail loudly at boot rather than defaulting. The defect is that a file labelled "Comprehensive" is neither comprehensive nor authoritative. |
| CFG-011 | `SPEC-DEVIATION` (implied) | `DOC-UPDATE` | The code is correct; only the comment is wrong. (Root cause additionally corrected — see the finding.) |

### Severity-adjusted Findings

| ID | From | To | Rationale |
|----|------|-----|-----------|
| CFG-001 | HIGH | MEDIUM | Mechanism fully confirmed and the tail is catastrophic, but the bypass is present in **no** template, **no** documentation, **no** real `.env.*`, and — verified via `docker image inspect` — **not in the runtime image** (the `ENV DJANGO_BUILD=1` is builder-stage only). The guards are active in every real configuration today; the defect is an unguarded control channel, not a failing protection mechanism. Ordering (P0) unchanged. |
| CFG-003 | MEDIUM | LOW | Impact refuted: `ADMIN_PASSWORD` is already in cleartext in the container's `Config.Env` (verified), so removing it from argv reduces the exposure by zero. The stated threat model also has no concrete instance in a single-process one-shot container. |
| CFG-010 | P2 | P3 (priority, not severity) | Impact is browser-HSTS-cache only and the test module is deliberately divergent (`DEBUG=True`, migrations disabled, storage and mail backends overridden). Absorb into an adjacent settings-test change rather than schedule it. |

### Corrections to the Source Report's Evidence

| Source claim | Correction |
|---|---|
| CFG-002: "introduced by the two guard commits" | Precisely: **`8be3638` (2026-09-26) introduced the breakage** via `EMAIL_HOST`; `909ad16` (2026-09-27) added a second omission to an already-failing job. The `deploy-check` `env:` block has never changed since `6ef5390` (2026-09-22). |
| CFG-002: root cause is "no test asserting the env satisfies every guard" | That is the detection gap. The structural cause is that the contract comment (`ci.yml:375-381`) is **orphaned above the `load-test:` job**, 127 lines from the `deploy-check:` job it documents. |
| CFG-001: implied that the bypass is reachable in a running production image | The runtime image carries **no** `DJANGO_*` env (`docker image inspect` verified). `ENV DJANGO_BUILD=1` is in the Dockerfile's builder stage only. |
| CFG-003: impact framed around argv visibility | The credential is already in `Config.Env` via `env_file`; argv adds no exposure surface. See `VAL-002`. |
| CFG-008: "described across five documentation files" | **Six** tracked documentation files (plus the command docstring). |
| CFG-009: "19 variables" with 18 enumerated | 19 is correct; the nineteenth is `SCHEDULER_HEALTH_STALE_SECONDS` (read by `docker/healthcheck-scheduler.sh:26`). |
| CFG-011: "no `Env` model" exists | An `Env` entry for `BOT_TOKEN` **does** exist (`base.py:62-67`); it provides a cast and default, not validation. The comment names the right container and the wrong mechanism. |
| R-03: hardcoded-secret scan PASS | Manual `git grep` sweeps only — `gitleaks`/`pre-commit` are not installed on this host. Tool-equivalent assurance was not obtained. See `VAL-005`. |
| R-10 / CFG-008 evidence diff listed `BASH_SOURCE`, `SCRIPT_DIR`, `PYTEST_*`, `stale` | Shell-var noise and test-only entrypoint variables. `RUN_TRANSLATION_BACKFILL` is genuinely the only consumed name missing from the allowlist — independently confirmed. |

---

## Appendix A — Reproduction Log (validator, this phase)

All reproductions were run on Windows 11 / PowerShell 7 at commit `9e96b84`, with
`PYTHONPATH=src;src/backend`. `src/.env` is a 0-byte file in this working tree, so
`base.py:102-105` `read_env()` is a no-op locally and no operator secret could leak into
a reproduction. No secret value was printed at any point; real `.env.*` files were
inspected by key name only.

**A.1 — CFG-002 (the deploy-check gate)**
```text
V1  env = exact ci.yml:510-518 set  ->  ImproperlyConfigured: EMAIL_HOST must be set in
                                         production.   (prod.py:205)
V2  + EMAIL_HOST=smtp.example.com   ->  ImproperlyConfigured: REDIS_URL must be set in
                                         production.   (prod.py:248)
V3  + REDIS_URL=redis://...          ->  IMPORT OK with EMAIL_HOST+REDIS_URL
```

**A.2 — CFG-001 (the bypass and its tail)**
```text
A: no bypass, all secrets blank  -> ImproperlyConfigured: DJANGO_SECRET_KEY must be set
                                   and non-empty in production.  (prod.py:155)
B: DJANGO_ONESHOT=1, all blank   -> IMPORTED. SECRET_KEY len=0 DEBUG=False CSRF=[]
                                   REDIS_URL='' BOT_TOKEN=''
C: bypass + django.setup()       -> ImproperlyConfigured: The SECRET_KEY setting must not
                                   be empty.   (django/conf/__init__.py:90)
D: DJANGO_BUILD=1, blank key     -> IMPORTED via DJANGO_BUILD. SECRET_KEY len=0
```

**A.3 — CFG-004 (mail backend in production)**
```text
env = fully valid prod set + EMAIL_BACKEND=…console.EmailBackend
  PROD EMAIL_BACKEND = django.core.mail.backends.console.EmailBackend
  EMAIL_HOST guard value present: True
  Subject: subj / To: d@e.f
  RESET-TOKEN-abc123                      <- message body written to stdout
  messages sent (no exception raised)
```

**A.4 — CFG-007 (dead static-files setting)**
```text
Django 5.2.17
STATICFILES_STORAGE in global_settings: False
STORAGES in global_settings: True
Django security checks reference STATICFILES_STORAGE: False
```

**A.5 — CFG-010 (test vs. dev transport tuple)**
```text
TEST DEBUG=True SSLREDIR=False SESS=False CSRF=False HSTS=3600 HSTS_SUBD=True  HSTS_PRE=False
DEV  DEBUG=True SSLREDIR=False SESS=False CSRF=False HSTS=0    HSTS_SUBD=False HSTS_PRE=False
```

**A.6 — CFG-006 (live dev stack)**
```text
$ docker ps --format "{{.Names}} {{.Status}}"
mko-bazuna-dev-web-1   Restarting (1)
mko-bazuna-dev-bot-1   Restarting (1)
$ docker logs --tail 20 mko-bazuna-dev-web-1
  File "/app/src/backend/config/settings/dev.py", line 21, in <module>
    raise ImproperlyConfigured(
django.core.exceptions.ImproperlyConfigured: BOT_TOKEN is a placeholder value from
.env.dev.example. ...
```

**A.7 — CFG-001 severity bound (new evidence)**
```text
$ docker image inspect mko-bazuna-dev-web:latest --format "{{range .Config.Env}}{{println .}}{{end}}" | grep DJANGO
(no output — the runtime image carries no DJANGO_* variable)
```

**A.8 — CFG-003 exposure surface (impact refutation)**
```text
$ docker inspect mko-bazuna-dev-create_admin-1  ->  Config.Env contains ADMIN_PASSWORD: True
$ git log -S "ADMIN_PASSWORD=" --all           ->  matches only in tracked files
  classified: 4 placeholder (<...>), 1 shell-ref, 34 reference-or-empty
  the single committed non-empty literal: identical in .env.test.example:47 and
  docker-compose.test.yml:108, contains "test", no mixed case, no digits -> test fixture
```

**A.9 — CFG-008 / CFG-009 (independent env sweep)**
```text
consumed names: 33 ; allowlisted: 48
consumed but NOT allowlisted:  RUN_TRANSLATION_BACKFILL          (exactly one)
.env.example keys: 26 ; consumed names absent: 19 (incl. EMAIL_HOST)
.env.prod.example keys: 34
```

**A.10 — Suite health**
```text
docker compose --project-name mko-bazuna-test --env-file .env.test \
  -f docker-compose.yml -f docker-compose.test.yml run --rm \
  -e PYTEST_OPTS="src/backend/config/settings/tests src/backend/tests/test_compose_hardening.py --tb=short" test
-> 60 passed in 81.22s (0:01:21)
```

---

## Appendix B — Context Observed but Not Filed as Findings

Recorded so the consolidated report does not re-derive them. None of these is a defect.

1. **The working-tree `.env.prod` is not deployable as it stands.** A key-name-only
   inspection shows 22 keys, of which the production-mandatory `EMAIL_HOST` and
   `CSRF_TRUSTED_ORIGINS` are **absent** (as are the whole SMTP block,
   `SUPPORT_NOTIFICATION_RECIPIENTS`, `SENTRY_DSN` and `PROMETHEUS_MULTIPROC_DIR`).
   Under `prod.py:203-208` and `prod.py:237-238` this file would fail the production
   guards. This is **operator-local state in a gitignored file**, not a repository
   defect — but it is direct evidence that the CFG-001 guards are live and working in
   the configuration that would actually be used.
2. **`docker-compose.prod.yml:90`** sets `DJANGO_SETTINGS_MODULE=config.settings.prod`
   explicitly on the `scheduler` service — the only service in the file that does so.
   The other six inherit it from the base compose (`docker-compose.yml:55, 89, 124,
   158, 194, 231, 274`). Consistent in effect; noted only because a future edit that
   moves a service between the two files could lose it silently.
3. **`ALLOWED_ENV_VARS` (`base.py:19-38`) contains 48 entries against 33
   Python-consumed names.** The 15 extras are legitimately shell/entrypoint/compose
   injected (`ADMIN_*`, `SEED_*`, `TLS_CERT_PATH`, `REGISTRY`, `PROMETHEUS_MULTIPROC_DIR`,
   `SCHEDULER_HEALTH_STALE_SECONDS`, `DJANGO_BUILD`, `DJANGO_ONESHOT`, …). The list is
   not over-broad; it is deliberately two-sided, and the CFG-008 gap is a missing entry
   in one direction, not a design fault.
4. **`.env.example:1` carries a UTF-8 BOM** before the leading `#`. Cosmetic; fold into
   the CFG-009 edit.
