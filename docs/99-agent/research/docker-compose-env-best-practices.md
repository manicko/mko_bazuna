# Docker Compose Environment Variable Management — Best Practices

> **Audience:** Engineers designing, operating, or CI/CD-ing containerized Compose apps.
> **Versions referenced:** Docker Compose v2.30+ (CLI `docker compose`). The Compose Specification (compose-spec) is the canonical source of truth; Docker Compose is its reference implementation.
> **Methodology:** Findings are derived from official Docker documentation, the Compose Specification, Context7-retrieved source code from the `docker/compose` repository, and verified GitHub issues. Each claim is tagged with a confidence level (HIGH/MEDIUM/LOW). Where the source code contradicts informal claims in issues, the source of truth wins.

## TL;DR — Key Takeaways

1. **Three distinct mechanisms, two phases.** There is a **parse-time** interpolation phase (`.env`, `--env-file`, shell) and a **container-environment** phase (`environment:`, `env_file:`, image `ENV`). Confusing them is the #1 source of bugs.
2. **`--env-file` does NOT override the service `env_file:` directive.** The CLI `--env-file` is consumed *only* for `${VAR}` interpolation; the service-level `env_file:` is injected *directly* into the container. This is a verified, frequently-misunderstood behavior ([docker/compose#12264](https://github.com/docker/compose/issues/12264)).
3. **Precedence for the *container's* environment** (highest→lowest): `docker compose run -e` → `environment:`/`env_file:` with interpolation → `environment:` literal → `env_file:` literal → image `ENV`.
4. **Use `.env` for interpolation + non-secrets; use Docker Compose `secrets` for anything sensitive.** Never put secrets in `.env` and commit it. (Docker docs, *Best practices*.)
5. **Base file holds the production contract; overrides hold environment ergonomics.** Secrets files (paths) and non-secret config can live in overrides; never duplicate full service blocks.
6. **Merge rules are asymmetric.** `environment`/`labels`/maps *merge* (local wins on conflict); `ports`/`expose` lists *concatenate*. You cannot "clear" a list with `ports: []` in an override.
7. **CI/CD should prefer native test execution over `docker compose up` for speed**, and inject credentials via GitHub Secrets → environment → `--secret`/build secrets or `--env` replication, never via committed `.env`.

---

## 1. `env_file` vs `environment` vs `.env` Interpolation

### 1.1 Three mechanisms, two phases

Docker Compose exposes environment-related configuration through **three** mechanisms that operate at **two different phases**:

| Mechanism | Phase | Purpose | Where the value lands |
|---|---|---|---|
| `.env` file (project directory) | Parse-time | Source of `${VAR}` substitutions in `compose.yaml` | **Not** injected into container directly; resolved into the Compose model |
| `--env-file` CLI flag | Parse-time | Alternate source of `${VAR}` substitutions (overrides default `.env`) | **Not** injected into container directly; resolved into the Compose model |
| `environment:` attribute (service) | Container-env phase | Explicit per-key container environment, may use `${VAR}` | `service.Environment` → container `Env` |
| `env_file:` attribute (service) | Container-env phase | Bulk injection of key-values from a file into the container | `service.Environment` (merged) → container `Env` |
| Image `ENV` (Dockerfile) | Container-env phase | Default baked into image | Lowest-priority container environment |

**Confidence: HIGH.** Source-code verification confirms the two-phase architecture:

- **Phase 1 — Parse/interpolation:** `cli.WithEnvFiles` + `cli.WithDotEnv` load the project `.env`/`--env-file` content into `project.Environment`. This is consumed *only* to resolve `${VAR}` tokens in the Compose YAML ([docker/compose `cmd/compose/compose.go`](https://github.com/docker/compose/blob/main/cmd/compose/compose.go)).
- **Phase 2 — Container environment:** `project.WithServicesEnvironmentResolved(true)` reads each service's `env_file:` entries and merges them into `service.Environment`, which then becomes the container's `Env` in `create.go` — proving `env_file:` content **is** injected into the running container, unlike project `.env` values ([docker/compose `pkg/compose/create.go`](https://github.com/docker/compose/blob/main/pkg/compose/create.go)).

> **CRITICAL DISTINCTION**
> The `.env` file and `--env-file` are **interpolation sources** for the Compose *file parsing*. They do **not** populate the container's environment by themselves. To get a value into the container, you must reference it through `environment:` (e.g., `DEBUG=${DEBUG}`) or via the service `env_file:` directive. This is repeatedly emphasized in the official docs: *"Be aware of Environment variables precedence when using variables in an .env file that as environment variables in your container's environment."* — [docs.docker.com](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation).

### 1.2 Interpolation precedence (parse-time)

When the **same** variable is referenced via `${VAR}` and comes from multiple sources, Compose resolves it using this order (highest → lowest):

1. Variables from your **shell environment**
2. Variables from a file set by **`--env-file`** (`--env-file` is repeatable; later files override earlier ones)
3. If `--env-file` is **not** set, variables from an **`.env` file in the project directory**

**Confidence: HIGH.** ([docs.docker.com/variable-interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation), Compose Spec).

The project directory resolution chain (when `--env-file` is unset):
- `--project-directory` if set, **else** the directory of the first `-f`/`--file` Compose file, **else** `$PWD`.

> **Note on two `.env` files:** When `--env-file` is *not* set, Compose may load up to **two** `.env` files — one from the project directory (higher precedence) and, if that file sets `COMPOSE_FILE=/path/to/compose.yaml` pointing elsewhere, a second `.env` from that directory with **lower** precedence. This is easy to trigger accidentally. — [docs.docker.com/envvars-precedence](https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence)

```yaml
# .env (project dir, higher precedence)
COMPOSE_FILE=../infra/compose.yaml
POSTGRES_VERSION=9.3

# ../.env (lower precedence, auto-loaded because COMPOSE_FILE points there)
POSTGRES_VERSION=9.2
```
Result: `postgres:9.3` wins — verified by `docker compose config`.

### 1.3 Interpolation syntax

Interpolation applies only to **unquoted** and **double-quoted** values; single-quoted is literal:

| Syntax | Meaning |
|---|---|
| `${VAR}` | value of `VAR` (empty string if unset) |
| `$VAR` | unbraced equivalent |
| `${VAR:-default}` | `VAR` if set & non-empty, else `default` |
| `${VAR-default}` | `VAR` if set, else `default` |
| `${VAR:?error}` | `VAR` if set & non-empty, else **exit with error** |
| `${VAR?error}` | `VAR` if set, else exit with error |
| `${VAR:+rep}` | `rep` if `VAR` set & non-empty, else empty |
| `${VAR+rep}` | `rep` if `VAR` set, else empty |

**Confidence: HIGH.** — [docs.docker.com/variable-interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation), Compose Spec.

`.env` file value-quoting rules (`.env` syntax differs from Compose YAML quoting):

```dotenv
VAR=VAL            # VAL
VAR="VAL"          # VAL (double-quoted → interpolation applied)
VAR='VAL'          # VAL (single-quoted → literal, no interpolation)
VAR='$OTHER'       # $OTHER (literal)
VAR="${OTHER}"     # ${OTHER} (literal)
VAR="some\tvalue"  # some<TAB>value (escape sequences honored)
VAR='some\tvalue'  # some\tvalue (literal)
VAR=VAL # comment  # VAL (inline comment needs leading space)
VAR="VAL" # comment # VAL
```

**Confidence: HIGH.** — [docs.docker.com/variable-interpolation#env-file-syntax](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation).

### 1.4 Container-environment precedence (runtime)

This is the precedence that decides the **final value inside the container**, independent of interpolation. Highest → lowest:

| Rank | Mechanism | Notes |
|---|---|---|
| 1 | `docker compose run -e VAR=...` (CLI) | Highest. Explicit CLI value beats everything. |
| 2 | `environment:` or `env_file:` **with interpolation** (`-e`, `${VAR}` resolved from shell/`.env`/`--env-file`) | Interpolated values fill in the attribute. |
| 3 | `environment:` **literal** (explicit `KEY=value` with no interpolation) | |
| 4 | `env_file:` **literal** (explicit values read from file, no interpolation) | |
| 5 | Image `ENV` (Dockerfile) | Only applies if no Compose entry exists. |

**Confidence: HIGH** — [docs.docker.com/envvars-precedence](https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence). Full numeric table (verified via direct fetch):

| # | `run -e` | `environment` | `env_file` | Image `ENV` | Host OS env | `.env` file | Result |
|---|---|---|---|---|---|---|---|
| 1 | — | — | — | — | `V=1.4` | `V=1.3` | — |
| 2 | — | — | `V=1.6` | `V=1.5` | `V=1.4` | — | `V=1.6` |
| 3 | — | `V=1.7` | — | `V=1.5` | `V=1.4` | — | `V=1.7` |
| 4 | — | — | — | `V=1.5` | `V=1.4` | `V=1.3` | `V=1.5` |
| 5 | `--env V=1.8` | — | — | `V=1.5` | `V=1.4` | `V=1.3` | `V=1.8` |
| 6 | `--env V` | — | — | `V=1.5` | `V=1.4` | `V=1.3` | `V=1.4` |
| 8 | — | — | `V` | `V=1.5` | `V=1.4` | `V=1.3` | `V=1.4` |
| 12 | `--env V` | `V=1.7` | — | `V=1.5` | `V=1.4` | `V=1.3` | `V=1.4` |

### 1.5 When to use which

**Recommendation:**

- Use **`.env` + interpolation** (`image: "webapp:${TAG}"`, `environment: - DEBUG=${DEBUG}`) for **non-secret configuration that varies per environment or developer machine** (image tags, feature flags, ports, paths). Keep `.env` in `.gitignore` or only commit a `.env.example`.
- Use **`env_file:`** for **bulk, mostly-non-secret environment injection** shared across services or to share a file with `docker run --env-file`. Good for things like a set of application config keys. Paths are **relative to the `compose.yaml`** location. Since Compose v2.24.0, files can be marked `required: false`.
- Use **`environment:`** (inline) for **small, explicit, documented** keys where you want the value visible in the Compose file or you want shell-pass-through (`- DEBUG`). Interpolated forms (`DEBUG=${DEBUG}`) emit a warning when the variable is unset, which aids debugging.
- Use **`docker compose run -e`** only for **one-off, ad-hoc overrides** (e.g., a temporary debug flag). Do **not** rely on it for persistent configuration.

**Avoid:** mixing literal values across `environment:` and `env_file:` for the *same* key without understanding precedence (#3 beats #4). Document the intended precedence at the top of the override file.

---

## 2. Multi-File Compose Patterns

### 2.1 Canonical layout: base + per-environment + per-tool overrides

The idiomatic Compose pattern is a **base file** describing the production contract, plus **override files** that layer environment-specific ergonomics on top, selected with `-f` (or `COMPOSE_FILE`).

```
.
├── compose.yaml              # base contract: image, env, secrets, networks
├── compose.local.yaml        # dev-only: bind mounts, source reloads (gitignored)
├── compose.test.yaml         # CI/test: overrides for test runner, coverage
├── compose.prod.yaml         # prod overrides: read-only, dropped caps, secrets
├── .env                     # default interpolation values (gitignored)
└── .env.example             # template with no secrets (committed)
```

> **Convention:** `compose.yaml` is the **base/production contract**. It should be runnable as `docker compose -f compose.yaml up` for a production-like deployment. The default `compose.override.yaml` is automatically merged for local dev convenience. — [docs.docker.com/multiple-compose-files/merge](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge)

### 2.2 What goes where

| Concern | Base `compose.yaml` | Override (`compose.override.yaml` / `.prod` / `.test`) |
|---|---|---|
| Image | ✅ define | ❌ don't change (build once, deploy everywhere) |
| Secrets (paths/names) | ✅ declare `secrets:` top-level + per-service `secrets:` | ✅ reference prod secret files (`required: false` locally) |
| Non-secret config (`environment:`) | ✅ literal defaults | ⚠️ only env-specific overrides |
| Bind mounts / source mounts | ❌ keep base clean | ✅ dev overrides (gitignored) |
| Capabilities / security opts | ✅ `read_only`, dropped caps, non-root | ❌ (dev may relax) |
| Volumes | ✅ data volume names | ⚠️ dev may add bind mounts |
| `env_file:` paths | ✅ shared non-secret files | ✅ env-specific env files |
| Ports | ✅ production ports | ✅ dev convenience ports (concatenated!) |

**Confidence: HIGH.** Pattern confirmed by the `docker-production-patterns` ADR ([github/markof88](https://github.com/markof88/docker-production-patterns/blob/main/docs/decisions/0003-compose-override-pattern.md)) and the official merge docs.

### 2.3 Merge rules — understand concatenation vs. merge

Compose merges files in the order given on the command line; **subsequent files override/extend predecessors**, but the behavior differs by type:

- **Scalars** (e.g., `image`, `command`, `container_name`): **replaced** by the later file.
- **Maps** (`environment`, `labels`, `build.args`): **merged**; keys from the later file override matching keys, new keys are added.
- **Lists** (`ports`, `expose`, `dns`, `dns_search`, `tmpfs`, `devices`): **concatenated** (appended), not replaced.
- **Maps-of-maps** (e.g., `env_file` entries): **merged** by key, later wins.

> **Pitfall:** You **cannot** clear a list like `ports` by setting `ports: []` in an override — Compose appends, so the base ports remain. To remove ports you must either not declare them in the base, or use named fragments/profiles. (Verified in [compose#config.go](https://github.com/docker/compose/blob/main/cmd/compose/config.go): *"sequences are appended when compose files are merged"*.)

```yaml
# compose.yaml (base)
services:
  webapp:
    ports:
      - "8000:8000"   # production

# compose.override.yaml (dev)
services:
  webapp:
    ports:
      - "9000:8000"   # dev debug UI  → BOTH 8000 and 9000 are exposed
```

**Confidence: HIGH.** — [docs.docker.com/multiple-compose-files/merge](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge)

### 2.4 Environment-specific `env_file` without full duplication

The core tension: you want the **same service block** but **different `env_file` paths** per environment. Solutions, in order of preference:

#### Option A — Interpolation resolves the path (cleanest)

```yaml
# compose.yaml
services:
  webapp:
    image: "myapp:${APP_TAG:-latest}"
    env_file:
      - "./config/${ENV_FILE:-default}.env"   # resolved at parse time
    environment:
      - DEBUG=${DEBUG}
```
```bash
# dev
docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml up

# test (CI)
ENV_FILE=test docker compose -f compose.yaml -f compose.test.yaml up

# prod
APP_TAG=v1.6 ENV_FILE=prod docker compose -f compose.yaml up
```

**Confidence: HIGH** for the mechanism (interpolation resolves `env_file` paths). **Caveat (LOW→MEDIUM confidence, evidenced by [compose#9980](https://github.com/docker/compose/issues/9980) and [compose#11741](https://github.com/docker/compose/issues/11741)):** interpolation *inside* an `env_file:` referenced file (i.e., `${VAR}` tokens *within* `default.env`) does **not** always resolve from `--env-file`/`include` sources — only the project `.env` reliably drives that. Therefore, **prefer interpolating the *path* in `compose.yaml` rather than the *contents* of a referenced env file.**

#### Option B — Override only `env_file` in the environment file

```yaml
# compose.yaml
services:
  webapp:
    env_file:
      - default.env                  # base non-secrets
    secrets:
      - db_password
    environment:
      - DEBUG=${DEBUG}

# compose.prod.yaml
services:
  webapp:
    env_file:
      - default.env
      - prod.env                     # added: prod overrides
```
Because `env_file` is a **map-merge by key**, and because multiple files are evaluated in order with later values overriding ([docs](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables#use-the-env_file-attribute)), layering works as expected — but **only when keys differ or are explicitly set to different values**. Duplicate keys across files are resolved by last-wins.

#### Option C — `secrets:` per environment (recommended for secrets)

```yaml
# compose.yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
secrets:
  db_password:
    file: ./secrets/db_password.dev   # dev default

# compose.prod.yaml
secrets:
  db_password:
    file: ./secrets/db_password.prod  # prod override
```

### 2.5 Use `profiles` for conditional service inclusion

For services that only exist in some environments (e.g., `mailhog`, `pgadmin`), use **profiles** rather than duplicating whole service blocks:

```yaml
services:
  mailhog:
    image: mailhog/mailhog:1.0.1
    profiles: ["dev", "test"]        # only started with --profile dev/test
    ports:
      - "8025:8025"
```
```bash
docker compose --profile dev up
```
This keeps the base clean and avoids shipping dev tooling to production. — [docs.docker.com/reference/cli/docker/compose](https://docs.docker.com/reference/cli/docker/compose)

### 2.6 File selection patterns

```bash
# Dev (auto-merges compose.yaml + compose.override.yaml):
docker compose up

# Test/CI (explicit, deterministic — do NOT rely on auto-merge in CI):
CI=1 docker compose -f compose.yaml -f compose.test.yaml up --abort-on-container-exit

# Prod (single base, environment injected):
docker compose -f compose.yaml -f compose.prod.yaml \
  --env-file .env.prod up -d
```
**Recommendation for CI: always pass `-f` explicitly** and avoid `COMPOSE_FILE` env var, so the assembled config is deterministic and reviewable. Use `docker compose config` as a CI lint step.

---

## 3. `--env-file` Flag vs `env_file:` Directive

### 3.1 They solve different problems (verified by source)

| Aspect | `--env-file` (CLI flag) | `env_file:` (service directive) |
|---|---|---|
| **Phase** | Parse-time (interpolation) | Container-env phase |
| **Scope** | Global to the Compose command | Per-service |
| **Default** | `.env` in project dir (if set) | none |
| **Repeatable** | ✅ yes (`--env-file a --env-file b`) | ✅ yes (list of files) |
| **Optional flag** | n/a (flag presence) | ✅ `required: false` (Compose v2.24+) |
| **Alternative format** | n/a | ✅ `format: raw` (Compose v2.30+) |
| **Injected into container?** | ❌ No — only feeds `${VAR}` | ✅ Yes — directly to container env |
| **Usable by `docker run`?** | ❌ No (Compose CLI only) | ✅ Yes (plain `docker run --env-file`) |

**Confidence: HIGH.** The source confirms the two-phase separation: `cli.WithEnvFiles`/`cli.WithDotEnv` populate `project.Environment` for interpolation; `WithServicesEnvironmentResolved` separately resolves per-service `env_file:` into `service.Environment`, which becomes the container's `Env`. — [compose `cmd/compose/compose.go`](https://github.com/docker/compose/blob/main/cmd/compose/compose.go), [compose `pkg/compose/create.go`](https://github.com/docker/compose/blob/main/pkg/compose/create.go)

### 3.2 The precedence table applied to `--env-file`

`--env-file` values participate in **interpolation precedence** (rank 2 below shell), **not** container environment by themselves. They only reach the container if a service attribute references them via `${VAR}`:

```yaml
# compose.yaml
services:
  webapp:
    environment:
      - DATABASE_URL=${DATABASE_URL}   # <-- interpolated; can come from --env-file
```
```bash
# .env.prod has DATABASE_URL=postgres://prod
docker compose --env-file .env.prod config   # resolves DATABASE_URL from .env.prod
```

### 3.3 The critical gotcha — `--env-file` does NOT replace `env_file:`

> **Verified behavior (not a bug, by design):** If a service declares `env_file: one.env` (with literal values), passing `--env-file two.env` on the CLI **does not** substitute those container values with values from `two.env`. The `--env-file` only resolves `${VAR}` tokens in the YAML; the `env_file:` directive injects its own file contents directly.

[docker/compose#12264](https://github.com/docker/compose/issues/12264) (closed as working-as-intended) documents this exact confusion:

```yaml
# compose.yaml
services:
  test:
    env_file: one.env     # ONE=1, VAR=one
    image: scratch
```
```bash
docker compose --env-file two.env config   # two.env has VAR=two, TWO=2
# Output environment: ONE=1, VAR=one  (VAR=two is NOT applied)
```

**Confidence: HIGH** (reproduced/acknowledged behavior).

**Recommendation:** Do **not** expect `--env-file` to override values already provided via the service `env_file:` directive. If you need CLI-driven per-environment container values, drive them through **interpolation** (`environment: - VAR=${VAR}`) or use **secrets** with per-environment files.

### 3.4 When to use each

- **`--env-file`**: to select a *set of interpolation defaults* (e.g., `.env.dev` vs `.env.prod`) for resolving `${VAR}` in the Compose model. Use when you want the **same Compose file** to resolve differently per environment.
- **`env_file:`**: to **bulk-inject** a file's key-values into a container's environment (and/or to share a file with `docker run`). Use when the file's contents should be present verbatim in the container.

A common, correct combination:
```bash
docker compose -f compose.yaml -f compose.prod.yaml --env-file .env.prod up
```
Here `.env.prod` drives interpolation (e.g., `image: "app:${APP_TAG}"`) while the service `env_file:` (declared in `compose.yaml`) still injects its own values directly into the container.

---

## 4. Secrets Management

### 4.1 Secrets definition (Compose Spec)

A top-level `secrets:` block declares secrets sourced from the host. Each source is mutually exclusive with `external`:

| Field | Meaning | Scope |
|---|---|---|
| `file:` | Secret created from the contents of the file at this path | Compose *and* Swarm (`docker stack deploy`) |
| `environment:` | Secret created from the value of this host environment variable | **Compose only** (v2.6+) — not supported with `docker stack deploy` |
| `external: true` | Secret already exists in the platform; Compose looks it up (does **not** create) | Compose *and* Swarm |
| `name:` | Distinct lookup key in the platform (used with `external`) | With `external` only |

**Confidence: HIGH** — [compose-spec/09-secrets.md](https://github.com/compose-spec/compose-spec/blob/main/09-secrets.md), [docs.docker.com/reference/compose-file/secrets](https://docs.docker.com/reference/compose-file/secrets).

When `external: true`, all other attributes (except `name`) are rejected as invalid.

### 4.2 How secrets reach the container

Secrets are mounted as a **file** at `/run/secrets/<secret_name>` inside the container (Linux only; Windows supports bind-mounting directories only). Services receive a secret only when explicitly granted via the service-level `secrets:` list. — [docs.docker.com/use-secrets](https://docs.docker.com/compose/how-tos/use-secrets)

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password   # *_FILE convention
    secrets:
      - db_password
secrets:
  db_password:
    file: ./secrets/db_password.txt
```

**Important nuances (verified at source level):**
- Docker Compose **rejects** `secrets:.*:driver` and `secrets:.*:template_driver` ("not supported"). It **warns** and ignores `uid`, `gid`, `mode` on the **file-backed** path ([compose `pkg/compose/create.go`](https://github.com/docker/compose/blob/main/pkg/compose/create.go)).
- **Environment-sourced secrets** (`environment:` under a secret) take a *different* code path (`copyFileToContainer` → tar with `createTar`) that **does** honor `uid`/`gid`/`mode`. So ownership *can* be set when sourcing a secret from a host env var, but not from a file. This is an asymmetry worth knowing.
- Before publishing an OCI artifact (`docker compose publish`), Compose **scans** compose files, env files, config files, and secret files for sensitive patterns via the DefangLabs secret-detector, prompting for confirmation. — [compose `pkg/compose/publish.go`](https://github.com/docker/compose/blob/main/pkg/compose/publish.go)

### 4.3 When to use `.env` vs Docker secrets

| Decision factor | `.env` / env vars | Docker Compose `secrets` |
|---|---|---|
| **Sensitivity** | Low / non-secret | **High** — passwords, tokens, keys, certs |
| **Exposure surface** | Visible to all processes, leakable in logs/`ps` | Mounted as a file under `/run/secrets/`, not in process env |
| **CI/CD injection** | Easy via shell-exported vars | Via `environment:` secret source, or `--secret`/build secrets |
| **Swarm (`stack deploy`)** | Works but insecure | `file:` / `external:` only (no `environment:` source) |
| **Complexity** | Simple | Slightly more (need `*_FILE` convention or app reads file) |

**Guideline (Docker docs):** *"Don't use environment variables to pass sensitive information ... Use secrets instead."* — [docs.docker.com/set-environment-variables](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables)

**Confidence: HIGH.** Recommendation: anything secret → Docker Compose `secrets` with `file:` pointing at a **gitignored** secret file, or `external: true` in production. Non-secret config → `.env` interpolation.

### 4.4 Production-grade secrets patterns

#### Pattern 1 — External secrets (Swarm/Cloud)
```yaml
secrets:
  db_password:
    external: true        # created via `docker secret create` or cloud secret store
services:
  db:
    secrets:
      - db_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
```

#### Pattern 2 — Local dev secrets (gitignored files)
```yaml
# compose.yaml (dev default)
secrets:
  db_password:
    file: ./secrets/db_password.dev        # gitignored
    required: false                        # tolerate missing locally (v2.24+)

# compose.prod.yaml
secrets:
  db_password:
    file: ./secrets/db_password.prod
```
> **Note:** The `required` field on `secrets:` is a separate concept from the `required` field on `env_file:`; both appeared in v2.24.0 for their respective directives.

#### Pattern 3 — Build-time secrets (Docker Buildx)
For building images, use BuildKit secret mounts sourced from host env vars — **not** the Compose `environment:` secret source for build (see [compose#13235](https://github.com/docker/compose/issues/13235), a regression fixed in v2.39.4 where env-sourced secrets stopped flowing to bake builds):

```dockerfile
# Dockerfile
FROM node:20-alpine
RUN --mount=type=secret,id=npm_token,env=NPM_TOKEN npm ci
```
```yaml
services:
  webapp:
    build:
      context: .
      secrets:
        - npm_token
secrets:
  npm_token:
    environment: NPM_TOKEN
```

**Confidence: HIGH** for the mechanism; **MEDIUM** for the v2.39.3 regression detail (issue #13235 is a real, recently-resolved bug — be aware env-sourced build secrets had a brief breakage).

### 4.5 Secrets precedence (Docker Agent / tooling level)

For tools that *consume* secrets (e.g., Docker Agent), a separate, documented precedence applies — but **this is not Compose container-env precedence**; it governs how a *tool* resolves a given secret key:

1. Environment variables (host)
2. Docker Compose secrets (`/run/secrets/…`)
3. Docker Agent env file (`~/.config/cagent/.env`)
4. Credential helper
5. Docker Desktop store

**Confidence: HIGH** — [docs.docker.com/ai/docker-agent/guides/secrets](https://docs.docker.com/ai/docker-agent/guides/secrets). This is tooling-level, not a substitute for the Compose container precedence in §1.4.

---

## 5. CI/CD Integration

### 5.1 General principle: native tests for speed, Compose for integration parity

For a Python/Django project (the reference context), the local `.env`/Compose workflow uses `PYTEST_OPTS` and a test DB service. In CI, the trade-off is:

- **Native test execution** (`pytest` directly on the runner with a service container for Postgres) is **faster** and uses the runner's own env for secrets. CI injects DB URLs/credentials via **GitHub Secrets → runner environment → `--env` or env-file**. No committed `.env`.
- **`docker compose run test`** is slower but guarantees the **exact** local stack parity (same images, same entrypoint). Appropriate for integration/e2e stages.

### 5.2 GitHub Actions — recommended shapes

#### A. Native tests with service container (fast gate)
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: mko_bazuna_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.14" }
      - run: pip install uv
      - run: uv sync --group dev
      - run: uv run pytest -m "not seed"
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/mko_bazuna_test
```

#### B. Compose-driven tests (parity)
```yaml
jobs:
  test-compose:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Start Compose stack
        run: |
          docker compose -f compose.yaml -f compose.test.yaml up -d --wait
        env:
          POSTGRES_PASSWORD: ${{ secrets.TEST_DB_PASSWORD }}
      - name: Run tests
        run: docker compose run --rm --env-file .env.test test
      - name: Tear down
        if: always()
        run: docker compose -f compose.yaml -f compose.test.yaml down -v
```

Key CI rules:
- **Never commit `.env` with secrets.** Ship `.env.example` (no real values) and `.env.test.example`.
- **Inject secrets via GitHub Secrets** into step `env:` or runner env, then into Compose via `--env`/`--env-file`/build `--secret`.
- Use **`docker/setup-compose-action`** (or `docker/setup-buildx-action`) rather than assuming a Compose version — see [docker/setup-compose-action](https://github.com/docker/setup-compose-action).
- Lint config: add `docker compose -f compose.yaml -f compose.test.yaml config` as a validation step.
- **Always tear down** (`down -v`) — CI runners are ephemeral, but explicit cleanup avoids port/owner leaks in self-hosted runners.

### 5.3 Build secrets in CI

For CI builds needing build-time credentials (npm tokens, private wheels):

```yaml
- name: Build image
  uses: docker/build-push-action@v6
  with:
    context: .
    push: ${{ github.ref == 'refs/heads/main' }}
    tags: user/app:${{ github.sha }}
    secrets: |
      NPM_TOKEN=${{ secrets.NPM_TOKEN }}
      SSH_PRIVATE_KEY=${{ secrets.SSH_PRIVATE_KEY }}
```

This uses **BuildKit** `--secret` mounts (not Compose service `environment:` secrets) — the appropriate mechanism for *build-time* secrets. — [docs.docker.com/build/ci/github-actions/secrets](https://docs.docker.com/build/ci/github-actions/secrets)

---

## 6. Common Pitfalls

### Pitfall 1 — `env_file:` in base, `--env-file` override doesn't replace it
**Symptom:** Passing `--env-file prod.env` at the CLI still yields values from the base `env_file: default.env` in the container.
**Cause:** `--env-file` feeds interpolation only; `env_file:` injects its file directly. (§3.3, [compose#12264](https://github.com/docker/compose/issues/12264).)
**Fix:** Make the `env_file:` path itself interpolated (`./config/${ENV_FILE}.env`), or override the entire `env_file:` list in the environment override.

### Pitfall 2 — Interpolation doesn't flow from `--env-file` into service `env_file:` contents
**Symptom:** `VAR=${OTHER}` inside `default.env` produces an empty `VAR` unless `OTHER` is in the project `.env` or shell.
**Cause:** Interpolation of tokens *inside* an `env_file:` is a Compose CLI feature tied to the project `.env`/`--env-file`/shell, but cross-file propagation through `include`/`--env-file` to service env-file contents is unreliable. — [compose#9980](https://github.com/docker/compose/issues/9980), [compose#11741](https://github.com/docker/compose/issues/11741).
**Fix:** Keep interpolated tokens in the Compose YAML (via `environment:` with `${VAR}`), not in referenced env-file contents; or put shared values in the project `.env`.

### Pitfall 3 — Lists concatenate, so you can't "unset" `ports` in an override
**Symptom:** Base declares `ports: ["8000:8000"]`; override sets `ports: []` — port 8000 is **still** published.
**Cause:** `ports`/`expose`/`tmpfs` are merged by **concatenation**, not replacement (verified in [compose `cmd/compose/config.go`](https://github.com/docker/compose/blob/main/cmd/compose/config.go)).
**Fix:** Don't declare dev-irrelevant ports in the base; use profiles for dev-only port mappings, or put all ports in the environment override.

### Pitfall 4 — `.env` committed to Git with real values
**Symptom:** Secrets/leaks in version control.
**Cause:** `.env` is the default interpolation file but is **not** auto-gitignored.
**Fix:** Add `.env` to `.gitignore`; commit `.env.example` with placeholders. Use `docker compose config` + `git-secrets`/secret scanning in CI to fail fast on leaked patterns. (Docker docs recommend this explicitly.)

### Pitfall 5 — Volume-mounting a host `.env` into a container
**Symptom:** Binding `./.env:/app/.env:ro` inside the container causes the container to read host env values, or `dotenv` auto-loads it, masking the intended container env. Worse, secrets in that file become part of the image's runtime filesystem.
**Cause:** `.env` is a **Compose CLI** concept (parse-time) for the host's `docker compose` process, *not* an application dotenv file — unless the app explicitly loads it. Mounting it conflates the two and can override `environment:`/`env_file:` values your app actually expects.
**Fix:** Do **not** mount the host `.env` into the container unless your application *intentionally* reads its own dotenv at runtime, and even then keep secrets out. Prefer `env_file:`/secrets for container configuration. — [docs.docker.com/env-file](https://docs.docker.com/compose/env-file)

### Pitfall 6 — Expecting two `.env` files to merge transparently
**Symptom:** A `.env` sets `COMPOSE_FILE=../infra/compose.yaml`; values in `../.env` silently override the project `.env`.
**Cause:** When `--env-file` is unset and `COMPOSE_FILE` points to a different directory, Compose auto-loads a **second** lower-precedence `.env`. — [docs.docker.com/envvars-precedence](https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence)
**Fix:** Prefer explicit `--env-file` in CI to disable the second-file auto-load behavior; document the dual-`.env` mechanism for developers.

### Pitfall 7 — Secrets via `environment:` (host) don't work with `docker stack deploy`
**Symptom:** A secret defined with `environment: VAR` works with `docker compose up` but fails under `docker stack deploy`.
**Cause:** The `environment:` source for secrets is **Compose-only** (v2.6+); Swarm requires `file:` or `external:`. — [docs.docker.com/reference/compose-file/secrets](https://docs.docker.com/reference/compose-file/secrets)
**Fix:** For deploy targets, use `file:` or `external: true`; reserve `environment:` secrets for local Compose only.

### Pitfall 8 — `env_file` `format: raw` quoted values differ from default
**Symptom:** With `format: raw`, `KEY='value'` stores the literal quotes; default `shell`-like format strips them.
**Cause:** Compose v2.30.0 added `format: raw` to pass values as-is (no interpolation/parsing). The default format applies Compose env-file parsing rules.
**Fix:** Choose `format: raw` deliberately when values must contain `$`, quotes, or shell specials that should not be re-parsed. — [compose-spec/spec.md](https://github.com/compose-spec/compose-spec/blob/main/spec.md)

---

## Quick Decision Table

| Need | Recommended mechanism |
|---|---|
| Image tag per environment | `.env` interpolation: `image: "app:${APP_TAG}"` |
| Feature flag per developer | `.env` (gitignored) + `environment: - DEBUG=${DEBUG}` |
| Bulk non-secret app config shared across services | `env_file:` (with `required: false` where optional) |
| A secret (password/token/cert) | Compose `secrets:` (`file:` gitignored, or `external: true` in prod) |
| Build-time secret (npm key) | BuildKit `--mount=type=secret` via `build.secrets` |
| CI override of a single value | `docker compose run -e VAR=x …` (rank-1 precedence) |
| Choose dev vs prod `.env` defaults | `--env-file .env.prod` (interpolation source) |
| Dev-only ports/services | `profiles: ["dev"]` + `-f compose.override.yaml` |

---

## Sources

1. **Docker — Environment variables precedence in Docker Compose.** Official precedence table and two-`.env`-file behavior. <https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence> (verified via direct fetch, Sept 2026).
2. **Docker — Set, use, and manage variables in a Compose file with interpolation.** Interpolation syntax, sources, precedence, `.env` syntax rules, `--env-file` behavior. <https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation> (verified via direct fetch).
3. **Docker — Set environment variables within your container's environment.** The `environment` vs `env_file` attributes, `required` (v2.24+), `format` (v2.30+), multi-file `env_file` ordering. <https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables> (verified via direct fetch).
4. **Docker — Best practices for working with environment variables in Docker Compose.** Non-exhaustive guidance (secrets, precedence, specific env files, interpolation). <https://docs.docker.com/compose/how-tos/environment-variables/best-practices> (verified via direct fetch).
5. **Docker — Manage secrets securely in Docker Compose.** Two-step secret injection, `/run/secrets/` mount, `*_FILE` convention, build secrets, Linux-only note. <https://docs.docker.com/compose/how-tos/use-secrets> (verified via direct fetch).
6. **Docker — Secrets (top-level element reference).** `file`, `environment` (Compose-only), `external`, `name`. <https://docs.docker.com/reference/compose-file/secrets> (verified via direct fetch).
7. **Docker — Use multiple Compose files / Merge Compose files.** Base + override merge rules (scalars replace, maps merge, sequences concatenate). <https://docs.docker.com/compose/how-tos/multiple-compose-files/merge> (verified via direct fetch).
8. **Compose Specification — `spec.md`.** Authoritative definition of `env_file` (`path`, `required`, `format`), env-file syntax, and the secrets element. <https://github.com/compose-spec/compose-spec/blob/main/spec.md> (verified via Context7).
9. **Compose Specification — `09-secrets.md`.** Secrets top-level element with `file`/`environment`/`external`/`name`. <https://github.com/compose-spec/compose-spec/blob/main/09-secrets.md> (verified via Context7).
10. **Docker Compose source — `cmd/compose/compose.go`.** Two-phase loading: `cli.WithEnvFiles`/`cli.WithDotEnv` into `project.Environment` (interpolation), then `WithoutEnvironmentResolution` before `WithServicesEnvironmentResolved(true)`. <https://github.com/docker/compose/blob/main/cmd/compose/compose.go> (verified via Context7).
11. **Docker Compose source — `pkg/compose/create.go`.** `env_file` content merged into `service.Environment` → `container.Config.Env`; secrets reject `driver`/`template_driver`/`external`. <https://github.com/docker/compose/blob/main/pkg/compose/create.go> (verified via Context7).
12. **Docker Compose source — `pkg/compose/publish.go` + `publish_test.go`.** Optional `env_file` (`required: false`) silently skipped on missing file; sensitive-data scanning before publish. <https://github.com/docker/compose/blob/main/pkg/compose/publish.go> (verified via Context7).
13. **Docker Compose source — `cmd/compose/config.go`.** Sequences (e.g. `ports`) are appended on merge, not replaced. <https://github.com/docker/compose/blob/main/cmd/compose/config.go> (verified via Context7).
14. **docker/compose#12264** — `--env-file` does not override service `env_file:` values (working-as-intended). <https://github.com/docker/compose/issues/12264>.
15. **docker/compose#9980** & **docker/compose#11741** — Interpolation of `${VAR}` *inside* service `env_file:` contents does not reliably resolve from `--env-file`/`include`-supplied sources. <https://github.com/docker/compose/issues/9980>, <https://github.com/docker/compose/issues/11741>.
16. **docker/compose#13235** — Env-sourced build secrets regression in v2.39.3 (fixed v2.39.4). <https://github.com/docker/compose/issues/13235>.
17. **Docker Docs — GitHub Actions secrets.** BuildKit `--secret`/`--secret-env`/SSH mounts in `docker/build-push-action`. <https://docs.docker.com/build/ci/github-actions/secrets> (verified via direct fetch).
18. **markof88/docker-production-patterns** — ADR for the base+override pattern (production contract vs dev ergonomics). <https://github.com/markof88/docker-production-patterns/blob/main/docs/decisions/0003-compose-override-pattern.md>.
