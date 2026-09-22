---
name: 02-config-secrets
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 02 — Configuration & Secrets Management

## Purpose

Reusable handbook for auditing configuration and secrets management of a
**dual-process Django system**: a web process and an aiogram bot process that
share a single project and database.

Architectural givens for this system class:

- Secrets are injected per-deployment: Docker Compose bind-mounts a single
  `.env.*` file into both web and bot containers; CI sets all secrets as
  step-level `env:` variables with no `.env` file, relying on `base.py`
  defaults.
- The **configuration layer** is split per environment (development, production,
  test).
- Fixed values are modeled as `StrEnum` (or `IntEnum` for integer constants),
  distributed across per-app-domain `enums.py` modules and inline within
  feature modules — consumed via `.value` references, never inline string
  literals.
- External input is validated at boundaries through **Pydantic v2 DTO schemas**
  before it reaches persistence.

This phase does **not** cover: entry/bootstrap process (Phase 01), DB
concurrency (Phase 03), authentication (Phase 04), general code quality
(Phase 10), or test infrastructure (Phase 11). Reference those phases; do not
duplicate their checks here.

> **Scope boundary note:** connection *pooling* is a runtime/concurrency concern
> with **zero** matches in Phase 02 (`conn_max_age`/`pooler`); it belongs to
> Phase 03. DB connection *settings* (e.g. `CONN_MAX_AGE`) are Phase-02-owned
> config evidence — they appear as typed settings in `config/settings/base.py`.

## Output Mode — `problems-only: true`

- Report **only real deviations, bugs, or risks** backed by runtime evidence.
- Omit passing checks and healthy rows entirely.
- Every finding must carry: reproducible runtime evidence + the exact
  consequence.
- If nothing is wrong in this phase, write exactly one line:
  `No problems found in this phase.`

---

## Architectural Layers

| Layer | Zone of responsibility | Key risks |
|---|---|---|
| Settings / configuration layer | Typed settings; per-environment separation; single source of truth for config | Divergent web/bot config; hardcoded values in logic; untyped config dicts; leaked environment branches |
| Secret-loading mechanism | Flow from env source into settings; delivery of secrets to both processes | Missing secrets at boot; secret leakage in logs or tracebacks; silent defaults masking absence |
| Fixed-value enums (distributed) | All fixed constants modeled as `StrEnum`/`IntEnum` across per-domain `enums.py` modules and inline feature-module enums; single *usage* site, distributed *definition* | Inline string literals where an enum exists; enum members defined ad-hoc in non-enum modules; drift between migration `choices` and current enum |
| Boundary DTO schema | Pydantic v2 validation of all external input at boundaries | Invalid/unvalidated data reaching persistence; unknown keys silently accepted |
| Deployment / secret-injection zone | Container env_file → env source → settings wiring | Secrets committed to VCS; missing ignore coverage; real credentials in example/template config |

---

## Discovery Stage

Perform discovery before any verification. Record locations by role, not by name.

1. **Configuration-layer discovery** — Map the settings module(s), all
   environment variants, and the environment-variable flow into settings.
2. **Secret-loading discovery** — Locate the secret source and the loading
   mechanism. Determine how secrets reach **both** processes. Confirm
   ignore-file coverage for the secret source.
3. **Fixed-value enum discovery** — Enumerate all `StrEnum`/`IntEnum`
   definitions across `enums.py` modules and inline within feature modules
   (bot, services, benchmark). Trace usage. Identify raw-string constants
   bypassing an existing enum.
4. **Boundary DTO discovery** — Enumerate all input-validation schemas. Trace
   every external input to confirm it passes through a DTO before persistence.
5. **Config-to-consumer discovery** — For each configuration section/field,
   locate its consumer.

---

## Mandatory Runtime Verification

Run all checks below **before** the audit dimensions. Capture evidence
(commands, exit codes, output excerpts) for each.

| ID | Verification | Method | Evidence to capture |
|---|---|---|---|
| R1 | Import settings per environment | Import the settings module under each environment variant | Clean import; typed attributes present; no import-time side effects |
| R2 | Valid + invalid secret behavior | Instantiate config with a valid env, then with a missing/empty required secret | Valid load succeeds; missing secret raises a clear error with **no leaked value** in the message |
| R3 | Hardcoded-secret scan | Grep entire codebase + all compose/container-build files for tokens, passwords, keys | Each match classified: hardcoded → CRITICAL / env-reference → OK / placeholder → OK / test-fixture → verify it is fake |
| R4 | Ignore-file coverage | Verify every real secret/env file is ignored in VCS and container build contexts | All real secret files ignored; example/template files contain **only** placeholders |
| R5 | Linter + type-check | Run the linter and the type checker over the config/secret surface | Exit codes recorded |
| R6 | Test-suite run | Run tests focused on config/secret loading | Pass/fail recorded per test |

---

## Audit Dimensions

Evaluate each dimension. Report only failing checks with evidence.

### (a) Config model / typed-settings correctness

| Check | Description |
|---|---|
| Typed settings | All settings are typed and validated, not raw dicts |
| No raw dicts in logic | Business logic reads typed config, not ad-hoc dictionaries |
| Enum for fixed values | Fixed values come from `StrEnum` definitions (distributed per app-domain), not inline string literals |
| Unknown-key rejection | Unknown/unexpected config keys are rejected, not silently ignored |

**Evidence required:** import output showing typed attributes; references to raw
config dicts in logic; magic literals where an enum exists; proof of
unknown-key handling behavior.

### (b) Secret management

| Check | Description |
|---|---|
| No hardcoded secrets | No secrets embedded in code or build files |
| Protected source | Secrets loaded only from the protected env source |
| Reject empty/invalid | Validation rejects empty or malformed secrets |
| Placeholder-only templates | Example/template config contains placeholders only |
| Ignore coverage | Real secret files ignored in VCS and build contexts |

**Evidence required:** R3 scan classification; R2 rejection behavior; R4 ignore
proof; template contents.

### (c) Environment separation correctness

| Check | Description |
|---|---|
| DEBUG isolation | Debug behavior confined to the development environment |
| TLS / secure-cookie flags | Transport-security flags correct per environment |
| DB credential isolation | Database credentials distinct and isolated per environment |
| No process divergence | Web and bot processes share identical required config |

**Evidence required:** per-environment attribute values; comparison of required
config across both processes.

### (d) Secret load-at-boot safety

| Check | Description |
|---|---|
| Missing env source fails | Absent env source fails explicitly (non-zero exit, clear message) |
| Missing required token fails | Absent required token fails explicitly |
| No secret logging | Secrets never emitted to logs |
| No leakage in tracebacks | Secrets absent from error output/tracebacks |
| Actionable errors | Invalid secret yields an actionable, value-free error |

**Evidence required:** R2 output; boot behavior under missing source/token; log
and traceback excerpts confirming no leakage.

### (e) Config-to-consumer flow

| Check | Description |
|---|---|
| Every section consumed | Each config section reaches a real consumer |
| No unused fields | No defined-but-unread config fields |
| No hidden hardcoding | No hardcoded parameters that should be configuration |

**Evidence required:** trace from each config field to its consumer; list of
unread fields; hardcoded parameters that belong in config.

### (f) Dead-config detection

| Check | Description |
|---|---|
| Every var/enum/setting consumed | No orphaned env vars, enum members, or settings |
| Template names match | Template placeholders match real setting names |
| No dead branches | No unreachable environment branches |

**Evidence required:** static trace of each env var/enum member to a consumer;
template-vs-settings name diff; branch reachability notes.

---

## Cross-Cutting Concerns (this phase only)

- **Shared secret source** — Compose binds a single `.env.*` file to both web
  and bot containers; CI sets secrets as step-level `env:` with no `.env` file,
  relying on `base.py` defaults. The constraint of identical required variables
  across both processes still holds; only the delivery mechanism differs.
- **Placeholder-only templates** — Example/template config files contain only
  placeholders, never real-looking values.
- **Configured transport security** — TLS and secure-cookie behavior is enforced
  through configuration, not hardcoded literals.

---

## Severity Taxonomy

| Severity | Conditions |
|---|---|
| CRITICAL | Hardcoded real secret; committed secret in VCS; secret embedded in compose/container-build file; empty/blank signing key in production; debug mode enabled in production; divergent config between the two processes |
| HIGH | Secret validation absent (silent defaults); divergent per-environment behavior; secrets written to logs; no ignore coverage for secret files |
| MEDIUM | Untyped config dicts in logic; magic strings instead of enums; unused config fields; missing boundary validation |
| LOW | Placeholder/template gaps; missing documentation comments |

---

## Edge-Case Checklist

- Missing env source at boot.
- Missing required token.
- Missing or invalid database configuration.
- Missing TLS certificate.
- Empty signing key.
- Env source committed with real values.
- Template containing real credentials.
- Settings import side effects (no DB access or secret logging at import time).

---

## Dead-Config Detection

Identify config fields, enum members, and environment branches that are defined
but never consumed.

**How to evidence:** perform a static trace from each env var / enum member /
setting to at least one consumer. A field with no reachable consumer is
dead config. Confirm template placeholder names correspond to real setting
names, and that every environment branch is reachable under some environment
variant.

---

## Report Output

- Write findings to: `.ai/audit/02-config-secrets/findings.md`
- Use template: `.ai/audit/templates/audit-findings.md`
- **Incremental append**, ≤100 lines per pass.
- Prefix every finding ID with `CFG-`.

**Problems-only rules (restated):**

- Record findings only; omit passing rows.
- If no problems are found, write exactly: `No problems found in this phase.`
- Each finding must include reproducible **runtime evidence** and the exact
  **consequence**.
