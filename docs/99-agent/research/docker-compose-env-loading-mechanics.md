# Docker Compose Environment Variable Loading Mechanics

> **Research note.** This document records the *verified* technical mechanics of how Docker
> Compose resolves environment variables, `.env` files, interpolation, `.dockerignore` pattern
> matching, `COPY . .`, and volume-mounted env files. Findings combine **official Docker
> documentation** (cross-referenced with Compose source code) and **live empirical verification**
> run against the installed tooling.
>
> **Tested environment (where "exact outputs" were captured live):**
> - Docker Engine `29.8.0`
> - Docker Compose CLI `v5.5.1` (BuildKit backend `desktop-linux`, Docker Desktop on Windows host)
>
> **Confidence legend:** HIGH = verified by a live command run in this environment, or by an
> authoritative source-file in the `docker/compose` repository; MEDIUM = documented behavior
> cross-referenced with multiple trusted sources; LOW = inferred / not directly tested here.

---

## Two fundamentally different mechanisms (the #1 source of confusion)

There are **two distinct** uses of env files that are frequently conflated:

| Mechanism | Directive / flag | When it is read | What it does | Where its values go |
|---|---|---|---|---|
| **Project `.env` / `--env-file`** (interpolation source) | Auto-loaded `.env` in project dir, or `--env-file` CLI flag | During Compose *parse time* | Feeds `${VAR}` interpolation **in `compose.yaml`** | **Not** injected into the container. Used to substitute placeholders in `image:`, `environment:`, `env_file` *paths*, build args, etc. |
| **`env_file:` service directive** | `services:<svc>.env_file` in `compose.yaml` | At *load time* (after parse) | Reads file content → injects each `KEY=value` into the **container's runtime environment** | Merged into `service.Environment`, which becomes the container's `Config.Env`. |

> **Key fact (SOURCE /docker/compose `pkg/compose/create.go`):** `service.Environment` is the union
> of the compose-file `environment:` keys **and** the resolved `env_file:` entries. This merged map
> is what gets assigned to `containerConfig.Env`. The project `.env` / `--env-file` values are
> *not* part of this — they are consumed earlier, purely for interpolation.
>
> **Key fact (SOURCE /docker/compose `cmd/compose/compose.go`):** interpolation precedence is wired
> by applying `WithOsEnv` (shell) first, then `WithEnvFiles` / `WithDotEnv` (`.env` + `--env-file`).
> Shell env is applied first so it is *never overwritten* by env files.
>
> **Key fact (SOURCE /docker/compose `pkg/compose/loader.go`):** `WithEnvFiles` / `WithDotEnv` load
> `.env` / `--env-file` content into `project.Environment` — a *separate* field from any service's
> `env_file:`. `project.Environment` is used **only** to resolve `${VAR}` tokens; its values are
> never injected into containers directly, which is exactly why `--env-file` cannot replace the
> service `env_file:` directive (see §2).

A common trap: writing `env_file: ./app.env` and expecting `${VAR}` **inside `app.env`** to expand
against the same file or other env files. It does not — `env_file` content is injected verbatim
(except for the Compose env-file format's own quoting rules, see §1.6).

---

## 1. `env_file` directive behavior

### 1.1 Core mechanics

- `env_file` adds environment variables to the container **based on the file content**. Paths are
  relative to the `compose.yaml` location. (SOURCE: compose-spec `05-services.md`)
- It can be a single value or a **list**.

```yaml
env_file:
  - ./common.env
  - ./apps/web.env
```

### 1.2 Multiple files — duplicate keys (within an `env_file` list)

> "The `env_file` can also be a list. The files in the list are processed from the top down. For the
> same variable specified in two environment files, the value from the **last file in the list stands**."
> — compose-spec `05-services.md`

**Live-verified (Compose v5.5.1).** Fixture: `one.env` (`ONE=1`, `VAR=one`), `two.env` (`VAR=two`, `TWO=2`), both listed, plus an `environment:` entry to show the merge:

```yaml
services:
  webapp:
    image: nginx:alpine
    env_file:
      - ./one.env       # VAR=one
      - ./two.env       # VAR=two  -> last wins
    environment:
      ONLY_IN_ENV: from-environment
```

```console
$ docker compose -f compose-multifile.yaml config --format yaml
name: tmp-mechanics
services:
  webapp:
    environment:
      ONE: "1"                 # <- from one.env
      ONLY_IN_ENV: from-environment   # <- from environment:
      TWO: "2"                 # <- from two.env
      VAR: two                # <- last file in the list wins (over one.env's VAR=one)
    image: nginx:alpine
    networks:
      default: null
networks:
  default:
    name: tmp-mechanics_default
```

➡️ The **last file in the list wins** for duplicate keys, and `env_file` entries are **merged into
`environment`** (the `env_file:` directive itself is absent from the resolved output — see §3).

### 1.3 `environment:` vs `env_file:` — duplicate keys (the central precedence question)

> "Environment variables specified in `environment` override these values." — compose-spec `05-services.md`

i.e. **explicit `environment:` always wins over `env_file:` for the same key.**

**Live-verified.** Fixture: `app.env` contains `SHARED_VAR=from-file` and `RACK_ENV=development`; the compose file sets `SHARED_VAR` explicitly under `environment:`:

```yaml
services:
  webapp:
    image: nginx:alpine
    env_file: [./app.env]
    environment:
      SHARED_VAR: from-explicit-environment   # must win over app.env's "from-file"
      INTERP_VAR: ${SOME_INTERP:-default-val}
      PLAIN: plain-literal
```

```console
$ docker compose -f compose.yaml config --format yaml
name: tmp-mechanics
services:
  webapp:
    environment:
      INTERP_VAR: default-val
      PLAIN: plain-literal
      RACK_ENV: development                 # <- only in app.env -> preserved
      SHARED_VAR: from-explicit-environment # <- environment: beat env_file:
    image: nginx:alpine
    networks:
      default: null
networks:
  default:
    name: tmp-mechanics_default
```

➡️ For `SHARED_VAR`, the `environment:` value (`from-explicit-environment`) wins over the `env_file:`
value (`from-file`). For `RACK_ENV`, which exists *only* in `app.env`, the value is preserved.

### 1.4 Does it merge into `environment` in the resolved config?

**Yes.** The loader reads each `env_file`, parses `KEY=value` lines, and merges the resulting
mapping into `service.Environment`. At runtime this merged map is passed to the container
(`create.go`: `Env: ToMobyEnv(env)` where `env = proxyConfig.OverrideBy(service.Environment)`).
So `env_file` values and `environment:` values end up in the *same* `Environment` mapping, with
`environment:` taking priority per-key.

### 1.5 Optional env files (`required: false`, Compose ≥ 2.24.0)

```yaml
env_file:
  - path: ./default.env
    required: true   # default — error if missing
  - path: ./override.env
    required: false   # missing file is silently ignored
```

### 1.6 Alternative format (`format: raw`, Compose ≥ 2.30.0)

```yaml
env_file:
  - path: ./default.env
    format: raw   # passes values as-is; disables Compose interpolation/quoting
```

The default env-file format applies quoting/escape rules (single-quotes = literal, double-quotes =
interpolation enabled, `\` escapes, `\t\n\r` escapes, `#` inline comments need a leading space).
`format: raw` is the escape hatch when a value legitimately contains `$` or quotes.

### 1.7 What `env_file` is NOT

`env_file:` is **not** used for `${VAR}` interpolation of the `compose.yaml` itself. It is a 1:1
equivalent of `docker run --env-file ...` — it only populates the container's runtime environment.
Variables defined in `env_file` files are *not* available to interpolate `${VAR}` elsewhere in the
compose model (confirmed live: `docker compose config --variables` lists only interpolation
expressions found in `compose.yaml`; `env_file` keys never appear there — see §3.3).

---

## 2. The `--env-file` CLI flag vs the `env_file:` directive

### 2.1 What `--env-file` does (and does NOT do)

`--env-file` specifies the file Compose uses as the **interpolation source** (the set of variables
available to resolve `${VAR}` placeholders in `compose.yaml`). It is **not** an injection mechanism —
it never puts values directly into the container's environment. Its effect is purely on parse-time
substitution.

### 2.2 `--env-file` replaces the default `.env` pickup (live-verified)

The installed Compose loads `WithEnvFiles(o.EnvFiles...)` (the `--env-file` values) and
`WithDotEnv` (the auto `.env`). When `--env-file` *is* set, the automatic `.env` pickup is skipped,
so the explicit file **replaces** the default `.env`.

**Live-verified.** `.env` (project dir) contains `RACK_ENV=from-dot-env`; `root.env`
(`--env-file` target) contains `RACK_ENV=from-env-file`; neither file defines `DEBUG`:

```yaml
# compose-interp.yaml
services:
  webapp:
    image: nginx:alpine
    environment:
      DEBUG: ${DEBUG}
      RACK_ENV: ${RACK_ENV}
      INTERP_VAR: ${SOME_INTERP:-default-val}
```

Without `--env-file` → default `.env` is loaded:
```console
$ docker compose -f compose-interp.yaml config --format yaml
name: tmp-mechanics
services:
  webapp:
    environment:
      DEBUG: ""                       # <- unset -> blank + WARN (see §4)
      INTERP_VAR: default-val
      RACK_ENV: from-dot-env          # <- from the default .env
    image: nginx:alpine
...
time="..." level=warning msg="The \"DEBUG\" variable is not set. Defaulting to a blank string."
```

With `--env-file root.env` → default `.env` is **replaced** (not merged):
```console
$ docker compose --env-file root.env -f compose-interp.yaml config --format yaml
name: tmp-mechanics
services:
  webapp:
    environment:
      DEBUG: ""                       # <- still unset (root.env has no DEBUG)
      INTERP_VAR: default-val
      RACK_ENV: from-env-file        # <- now from root.env, NOT from-dot-env
    image: nginx:alpine
```

➡️ `RACK_ENV` switched **from-dot-env → from-env-file**, proving `--env-file` **replaces** (not
merges with) the default `.env`. *(Note: the trailing `EXITCODE=False` seen in the run is a
PowerShell artifact from capturing the unset-`DEBUG` warning on stderr; the `docker compose`
command itself exited 0 and printed full config.)*

### 2.3 Shell environment wins over `--env-file` (live-verified)

```console
$ $env:DEBUG="from-shell"
$ docker compose -f compose-interp.yaml config --format yaml
name: tmp-mechanics
services:
  webapp:
    environment:
      DEBUG: from-shell               # <- shell env beat both .env and --env-file
      INTERP_VAR: default-val
      RACK_ENV: from-dot-env          # <- .env (no --env-file set here)
```

➡️ Shell environment always wins. No `DEBUG` warning is emitted because the variable is now set.

### 2.4 Multiple `--env-file` flags

```console
$ docker compose --env-file .env --env-file .env.override up
```
Files are read in order; **later files override earlier ones**. (SOURCE: official variable-interpolation docs.)

### 2.5 Default behavior when `--env-file` is absent

When `--env-file` is **not** set, Compose auto-loads a `.env` from the **project directory**. The
project directory is, in order: `--project-directory` → directory of the first `-f`/`--file` → `PWD`.

> **NOTE (from compose-go `cmd/compose/compose.go`):** When `--env-file` is unset, Compose may load
> **up to two** `.env` files: first from the project directory, and — if that file sets
> `COMPOSE_FILE` to a path in a different directory — a second `.env` from *that* directory with
> *lower* precedence.

### 2.6 The critical gotcha — `--env-file` does NOT replace the service `env_file:` directive

> **Verified behavior (not a bug, by design):** If a service declares `env_file: one.env` (with
> literal values), passing `--env-file two.env` on the CLI **does not** substitute those container
> values with values from `two.env`. The `--env-file` only resolves `${VAR}` tokens in the YAML; the
> `env_file:` directive injects its own file contents directly.

**Live-verified** (this is the exact scenario behind [docker/compose#12264](https://github.com/docker/compose/issues/12264)):

```yaml
# compose-12264.yaml
services:
  test:
    image: scratch
    env_file: [./one.env]   # ONE=1, VAR=one
```
with `one.env` (`ONE=1`, `VAR=one`) and `two.env` (`VAR=two`, `TWO=2`):

```console
$ docker compose --env-file two.env -f compose-12264.yaml config --format yaml
name: tmp-mechanics
services:
  test:
    environment:
      ONE: "1"              # <- from one.env (env_file:), untouched
      VAR: one             # <- from one.env (env_file:); VAR=two from two.env is NOT applied
    image: scratch
```

➡️ `VAR` stays **`one`** (from the service `env_file:`), **not** `two` (from `--env-file`); `TWO`
does not appear at all. This is the source-level consequence of keeping *two separate phases*
(see the "two mechanisms" table above): `--env-file` populates `project.Environment` for
interpolation; `WithServicesEnvironmentResolved(true)` reads the service `env_file:` into
`service.Environment` independently.

**Recommendation:** Do **not** expect `--env-file` to override values already provided via the
service `env_file:` directive. To drive per-environment container values from the CLI, drive them
through **interpolation** (`environment: - VAR=${VAR}`) or use **secrets** with per-environment files.

### 2.7 `--env-file` vs `env_file:` — the decisive difference

| Aspect | `--env-file` (CLI flag) | `env_file:` (service directive) |
|---|---|---|
| Purpose | Interpolation source for `${VAR}` in `compose.yaml` | Container runtime environment |
| Injected into container? | **No** (consumed at parse time) | **Yes** (merged into `service.Environment`) |
| Multiple files | Yes (`--env-file a --env-file b`, later wins) | Yes (list, later wins) |
| Replaces default `.env`? | Yes (when set) | N/A — separate mechanism |
| Optional / `required: false` | n/a (flag presence) | Yes (Compose v2.24+) |
| Alternative `format: raw` | n/a | Yes (Compose v2.30+) |

> **Official maintainer statement** (docker/compose#3435): "`env_file` is used to declare the
> environment file used when creating container from, as a 1:1 mapping of the `docker run
> --env-file` parameter. It isn't involved when parsing the compose file to do any variable
> subscription."

---

## 3. `docker compose config` behavior with `env_file`

### 3.1 Default: `env_file` is resolved away

By default `docker compose config` **resolves** service env files: it reads them, merges their
values into the `environment` section, and **removes the `env_file` directive** from the output.
(LIVE-VERIFIED in §1.2/§1.3 — the `env_file:` key is absent and the file's keys appear under
`environment`.)

The resolution pipeline is `runConfigInterpolate` (`cmd/compose/config.go`):
`ToProject` → `WithServicesEnvironmentResolved(true)` (loads `env_file:` into `service.Environment`)
→ validate → marshal.

### 3.2 `--no-env-resolution` keeps the directive

With `--no-env-resolution`, `WithServicesEnvironmentResolved` is skipped, so `env_file:` content is
**not** read into `environment` and the `env_file:` directive is **retained**:

```console
$ docker compose -f compose.yaml config --no-env-resolution --format yaml
name: tmp-mechanics
services:
  webapp:
    environment:
      INTERP_VAR: default-val
      PLAIN: plain-literal
      SHARED_VAR: from-explicit-environment   # <- env-file-only RACK_ENV is GONE here
    env_file:
      - path: C:\py_dev\mko_bazuna\docs\99-agent\research\_tmp-mechanics\app.env   # <- retained
    image: nginx:alpine
    networks:
      default: null
networks:
  default:
    name: tmp-mechanics_default
```

➡️ With `--no-env-resolution`, env-file-only variables (`RACK_ENV`) disappear from `environment`,
and the `env_file:` path is preserved. This is the authoritative way to inspect *which* `env_file`
was declared.

### 3.3 Debugging which `env_file` was used / the interpolation environment

| Flag | Purpose |
|---|---|
| `docker compose config --environment` | Print the **full environment used for interpolation** (shell env + `.env`/`--env-file` values, shell env winning). |
| `docker compose config --variables` | List every `${VAR}` interpolation expression found in the model, with `REQUIRED` (from `:?`), `DEFAULT VALUE` (from `:-`), and `ALTERNATE VALUE` (from `:+`). |
| `docker compose config --no-env-resolution` | Inspect declared `env_file:` paths without merging their contents. |

**Live-verified — `--variables`** (on `compose-interp.yaml`, which references `${DEBUG}`, `${RACK_ENV}`, `${SOME_INTERP:-default-val}`):

```console
$ docker compose -f compose-interp.yaml config --variables
NAME                REQUIRED            DEFAULT VALUE       ALTERNATE VALUE
SOME_INTERP         false               default-val
DEBUG               false
RACK_ENV            false
```

➡️ Only `${VAR}` tokens **in the compose model** are listed. The keys that come from an `env_file:`
(`SHARED_VAR`, `RACK_ENV` as injected vars) **never** appear — confirming `env_file:` contents are
not an interpolation source.

**Live-verified — `--environment`** (excerpt, filtered to relevant keys + the DEBUG warning):

```console
$ docker compose -f compose-interp.yaml config --environment
...
time="..." level=warning msg="The \"DEBUG\" variable is not set. Defaulting to a blank string."
RACK_ENV=from-dot-env
GODEBUG=x509negativeserial=1     # unrelated OS env var that matches the "DEBUG" substring filter
...
```

➡️ `--environment` shows the *resolved interpolation environment* (`RACK_ENV=from-dot-env` from the
default `.env`), with shell env vars winning over file values.

### 3.4 Important caveat: `config` re-escapes `$` for shell safety

A subtle source of confusion: `docker compose config` (YAML output) **re-escapes** any `$` that
remains after interpolation back to `$$`, so the rendered YAML may show `$$VAR` even though the
container actually receives a single `$VAR`. (SOURCE /docker/compose `cmd/compose/config.go`:
`bytes.ReplaceAll(content, []byte{'$'}, []byte{'$', '$'})` when `!opts.noInterpolate`.) The container
always sees the fully-interpolated, single-`$` value. (Confidence: MEDIUM — source-derived; not
exercised empirically here.)

---

## 4. Variable interpolation — the `:?` required (fail) syntax

Compose supports shell-style interpolation variants. The relevant syntaxes:

| Syntax | Behavior |
|---|---|
| `${VAR}` | Substitute; if unset, substitute empty string **and warn**. |
| `${VAR:-default}` | Use `default` if `VAR` is unset or empty. |
| `${VAR:+alt}` | Use `alt` if `VAR` **is** set (presence check). |
| `${VAR:?msg}` | If `VAR` is unset/empty → **hard error and abort.** |

### 4.1 `${VAR:?msg}` is a hard failure, not a warning (live-verified)

```yaml
# compose-required.yaml
services:
  test:
    image: ${ID:?ID variable must be set}
    command: echo hi
```

With `ID` **unset**:
```console
$ docker compose -f compose-required.yaml config --format yaml
docker : error while interpolating services.test.image: required variable
ID is missing a value: ID variable must be set
EXITCODE: 1   (non-zero — genuine failure, no config produced)
```

➡️ This is a **hard error** (the command aborts, exit code `1`, no config is produced). It is **not**
a warning, and it does **not** fall back to a blank string — unlike bare `${VAR}`.

When the variable *is* resolvable (here, provided via `--env-file`):
```console
$ docker compose -f compose-required.yaml --env-file id.env config --format yaml
name: tmp-mechanics
services:
  test:
    command:
      - echo
      - hi
    image: alpine          # <- ID=alpine from id.env, resolved successfully
    networks:
      default: null
networks:
  default:
    name: tmp-mechanics_default
```

### 4.2 Source-level corroboration

- E2E testdata `pkg/e2e/testdata/TestUpImageID/compose.yaml` uses `image: ${ID:?ID variable must be set}`
  to assert a missing required var aborts image resolution.
- `config --variables` parses each expression into `{Required, DefaultValue, PresenceValue}` fields
  driven by `:?` / `:-` / `:+`, respectively (SOURCE `cmd/compose/config.go` `ExtractVariables` /
  `template.DefaultPattern`).

---

## 5. Precedence chains (two chains, because interpolation ≠ container env)

### 5.1 Chain A — Interpolation (resolving `${VAR}` in `compose.yaml`)

Highest → lowest:

1. **Shell environment variables** — applied first via `WithOsEnv`; never overwritten by files.
   (LIVE-VERIFIED §2.3: `DEBUG=from-shell` beat `.env`.)
2. **`--env-file` values** — replaces default `.env` when set.
   (LIVE-VERIFIED §2.2: `RACK_ENV` went `from-dot-env`→`from-env-file`.)
3. **Default `.env`** (project dir) — loaded only when `--env-file` is *not* set.
   (LIVE-VERIFIED §2.2: `RACK_ENV=from-dot-env` when no `--env-file`.)
4. *(secondary)* A second project-dir `.env` if `COMPOSE_FILE` points elsewhere — lowest.

> Within `--env-file`, multiple flags: later file overrides earlier file. (documented)

**Source:** `cmd/compose/compose.go` wires precedence as
`WithOsEnv` → `WithEnvFiles(...)` → `WithDotEnv` → `WithConfigFileEnv` → `WithDefaultConfigPath`
→ `WithEnvFiles(...)` → `WithDotEnv` (applied twice: once for `PWD`, once for the resolved project
dir). Shell is applied first so it is never overwritten by a file.

### 5.2 Chain B — Container environment (values injected into the running container)

Highest → lowest (SOURCE: docs.docker.com/compose/how-tos/environment-variables/envvars-precedence):

| Rank | Mechanism | Notes |
|---|---|---|
| 1 | `docker compose run -e VAR=...` / `docker run --env` | Highest. Explicit CLI value beats everything. |
| 2 | `environment:` **or** `env_file:` whose value was **interpolated** (`-e`, `${VAR}` resolved from shell/`.env`/`--env-file`) | Interpolated values fill in the attribute. |
| 3 | `environment:` **literal** (explicit `KEY=value` with no interpolation) | |
| 4 | `env_file:` **directive** (raw, non-interpolated file values) | |
| 5 | `Dockerfile` `ENV` directive (image-level default) | Only applies if no Compose entry exists. |

**Corollaries (verified/documented):**
- `environment:` (rank 3) beats `env_file:` (rank 4) per-key — LIVE-VERIFIED in §1.3
  (`SHARED_VAR=from-explicit-environment` overrode `from-file`).
- `env_file:` (rank 4) beats image `ENV` (rank 5) — an `env_file` value overrides a `Dockerfile ENV`
  of the same name (no Compose entrant present).
- A `Dockerfile` `ENV`/`ARG` only takes effect when there is **no** Compose `environment` /
  `env_file` / `run --env` entry for that variable.
- ⚠️ In Compose 2.25–2.29, a bare `VAR:` (null) in `environment:` stopped overriding
  `env_file`/`ENV` and instead *inherited* from the shell (docker/compose#11740, #12180); corrected
  around v2.29. Portable workaround: use `VAR: ""` (explicit empty) instead of bare `VAR:`.

---

## 6. `.dockerignore` path-matching semantics

### 6.1 Matching engine

- Patterns are newline-separated, `#` = comment, blank lines ignored.
- Matching uses Go's `filepath.Match` rules **plus** a special `**` wildcard that matches any number
  of path segments (including zero). (SOURCE: docs.docker.com/build/concepts/context/)
- "The root of the context is considered to be both the working and the root directory."
- `!` negates a pattern. Final state (include/exclude) is determined by the **last matching line**
  (order matters).

### 6.2 The recursive vs root-only distinction (critical for `.env`) — live-verified

A pattern **without** a path separator is anchored to the **root** of the context only. A pattern
with `**/` matches at **all** depths (including root, since `**` matches zero dirs).

**Live-verified (Docker 29.8.0).** Scratch build context contained a root-level `.env`-style file
set plus a nested `src/.env` (`SECRET=deeply-nested-secret`).

#### Pattern `.env*` — root only (FAILS to catch `src/.env`)

`.dockerignore`:
```
.env*
```
Resulting build:
```console
$ docker build -t mechanics-test-a .
...
#3 transferring context: 261B        # <- context sent to daemon
#6 [final 2/4] COPY . .
#9 [final 4/4] RUN ls -la /from-stage.txt /src/.env 2>&1 || true
#9 0.385 leaked.txt present?
#9 0.387 -rw-r--r-- 1 root root  18 ... /from-stage.txt       # <- COPY --from worked (see §7)
#9 0.387 -rwxr-xr-x 1 root root  28 ... /src/.env            # <- LEAKED: root-only .env* missed src/.env
```

➡️ With `.env*`, `src/.env` (28 bytes) is **still baked into the image** — `.env*` only matches
root-level filenames starting with `.env`; Go's `filepath.Match` `*` does **not** cross `/`.

#### Pattern `**/.env*` — all levels (catches `src/.env`)

`.dockerignore` (changed to):
```
**/.env*
```
Resulting build:
```console
$ docker build -t mechanics-test-b .
...
#3 transferring context: 95B          # <- smaller context (src/.env now excluded)
#5 transferring context: 427B
#7 [final 2/4] COPY . .
#9 [final 4/4] RUN ls -la /from-stage.txt /src/.env 2>&1 || true
#9 0.350 leaked.txt present?
#9 0.351 ls: /src/.env: No such file or directory   # <- EXCLUDED by **/.env*
#9 0.351 -rw-r--r-- 1 root root  18 ... /from-stage.txt  # <- still present (COPY --from, see §7)
```

➡️ With `**/.env*`, `src/.env` is **excluded** from the context (and thus from the image), while
`/from-stage.txt` (copied via `COPY --from=builder`) remains — proving the two mechanisms are
independent.

### 6.3 Recommended patterns for env-file exclusion

| Goal | Pattern | Scope |
|---|---|---|
| Exclude `.env` only, everywhere | `**/.env` | all dirs (exact name) |
| Exclude `.env`, `.env.local`, `.env.prod`, … everywhere | `**/.env*` | all dirs (prefix) |
| Exclude root `.env` only | `.env*` | root only |
| Exclude root `.env` only (exact) | `.env` | root only |

> **Note:** `node_modules`, `.git`, etc. follow the same rule — bare names are root-only; prefix with
> `**/` to recurse. The Java quickstart ships `**/.env` for this exact reason.

---

## 7. `Dockerfile` `COPY . .` and `.dockerignore` interaction across build stages

### 7.1 Build context = dir contents minus `.dockerignore` matches

- The **build context** is the set of files in the build's root directory **after** applying
  `.dockerignore`. The daemon only ever sees the filtered context.
- `.dockerignore` is applied **before** the context is transferred to the daemon, so ignored files
  are never sent (and never enter image layers). (LIVE-VERIFIED §6.2: context shrank
  `261B → 95B` after adding `**/.env*`.)
- You can verify what the daemon received from the `#<n> transferring context: <size>` progress line.

### 7.2 `COPY . .` draws from the (filtered) build context

- `COPY` (without `--from`) copies from the local build context. Therefore `.dockerignore` **does**
  protect `COPY . .` — any ignored file is absent and thus cannot be copied. (LIVE-VERIFIED: with
  `**/.env*`, `src/.env` was absent from the final layer; with `.env*` it leaked.)

### 7.3 `.dockerignore` does NOT apply to `COPY --from=<stage>` (multi-stage) — live-verified

> "`.dockerignore` filters the local files before they are sent to the daemon. It does **not**
> apply to individual `COPY` commands between stages." — maintainer tonistiigi, moby/moby#33923

**LIVE-VERIFIED.** The test `Dockerfile` (multi-stage) created `/build-artifacts/leaked.txt` *inside*
the `builder` stage, then `COPY --from=builder ... /from-stage.txt` in the final stage:

```dockerfile
FROM alpine:3.20 AS builder
RUN mkdir -p /build-artifacts && echo "FROM_STAGE_SECRET" > /build-artifacts/leaked.txt
FROM alpine:3.20 AS final
COPY . .                                  # subject to .dockerignore
COPY --from=builder /build-artifacts/leaked.txt /from-stage.txt   # NOT subject
```

Build output (with `**/.env*`, which excluded `src/.env`):
```console
#9 0.351 ls: /src/.env: No such file or directory   # <- COPY . . : .dockerignore applied
#9 0.351 -rw-r--r-- 1 root root  18 ... /from-stage.txt        # <- COPY --from=builder : NOT filtered
```

➡️ `COPY --from=builder` brought `leaked.txt` into the final image **despite** it being created inside
a build stage (invisible to `.dockerignore`). So `.dockerignore` protects only the **local context**
used by `COPY . .`, never stage-to-stage copies.

### 7.4 `Dockerfile` and `.dockerignore` themselves

> "You can use the `.dockerignore` file to exclude the `Dockerfile` and `.dockerignore` files. These
> files are still sent to the builder as they're needed for running the build. But the `ADD` and `COPY`
> instructions do not copy them to the image." (SOURCE: docker builder reference)

So even `COPY . .` will **not** copy the `Dockerfile` into the image (the daemon keeps its own
copy for parsing).

### 7.5 Ensuring no env files leak into images

1. Add `**/.env*` (and `**/secrets.dev.yaml`, etc.) to `.dockerignore` — the primary guarantee,
   applied at context-transfer time.
2. Never write a `COPY` that targets env files explicitly.
3. For build-time secrets, use BuildKit `--mount=type=secret` (never `ARG`/`ENV` for secrets — ARGs
   leak into `docker history`).

---

## 8. Volume-mounted env files (runtime bind mounts) — live-verified

### 8.1 A bind mount overlays, it does not "create" or "replace" — live-verified

> "If you mount a volume or a bind-mounted directory into a directory in the container in which files
> or directories exist, the pre-existing files are **obscured** by the mount." — Docker volumes docs

A probe image (`env-mount-probe`) baked `/app/.env` = `BAKED_IN_IMAGE` and `/app/tag.txt` = `FROM_IMAGE`.

**Baseline (no mount):**
```console
$ docker run --rm env-mount-probe
--- /app/.env ---
BAKED_IN_IMAGE
--- /app/tag.txt ---
FROM_IMAGE
--- stat /app/.env ---
-rw-r--r-- 1 root root 15 Sep 16 10:20 /app/.env      # regular file
```

**Bind-mount host `root.env` (`RACK_ENV=from-env-file`) over `/app/.env:ro`:**
```console
$ docker run --rm -v "$PWD/root.env:/app/.env:ro" env-mount-probe
--- /app/.env ---
RACK_ENV=from-env-file            # <- host file OBSURSES the baked file
--- /app/tag.txt ---
FROM_IMAGE                        # <- untouched (not mounted)
--- stat /app/.env ---
-rwxrwxrwx 1 root root 23 Sep 16 09:56 /app/.env     # <- now a bind mount (host perms)
```

➡️ The host file **hides** the baked-in `.env` at `/app/.env`; it is **not deleted or overwritten on
disk** — `/app/tag.txt` (outside the mount) is unaffected. Once the container stops, the original
baked-in file is visible again (it never left the layer).

### 8.2 Build vs runtime — mounts do NOT affect `docker build`

- Volume mounts (including env-file bind mounts) are a **runtime** concept (`docker run` /
  `docker compose up`). They are **not** applied during `docker build`.
- `COPY . .` in the `Dockerfile` reads from the **build context** (the filtered local directory),
  *not* from any runtime volume mount. So `./root.env:/app/.env:ro` has **zero effect at build
  time** — whatever was `COPY`ed into the image at build time is what lives at `/app/.env` until a
  container is started with the mount.
- Consequently, even if a volume mount "fixes" a missing env at runtime, the **image still contains**
  whatever `COPY . .` baked in. If you `COPY . .` and `.env` was in the context (not ignored), the
  image is already leaked; the runtime mount just hides the baked copy.

### 8.3 Missing-source behavior: `-v` vs `--mount` — live-verified

Docker's two mount syntaxes differ on a **missing** source path:

- `-v` / `--volume`: if the source does not exist, Docker **attempts to auto-create it as a
  directory**. When the destination (`/app/.env`) is a *file* in the image, this yields a
  dir-over-file conflict:

```console
$ docker run --rm -v "$PWD/missing.env:/app/.env" env-mount-probe
docker: Error response from daemon: ... error mounting "...missing.env" to rootfs at
"/app/.env": ... flags=MS_BIND|MS_REC: not a directory:
Are you trying to mount a directory onto a file (or vice-versa)?
Check if the specified host path exists and is the expected type.
```

- `--mount type=bind`: does **not** auto-create; a missing source produces an outright error:

```console
$ docker run --rm --mount type=bind,source="$PWD/missing.env",target=/app/.env env-mount-probe
docker: Error response from daemon: ... error mounting "...missing.env" ... "not a directory:
Are you trying to mount a directory onto a file (or vice-versa)?..."
```

➡️ Both error here because the destination is a *file* in the image and the source is missing. The
documented distinction (auto-create dir for `-v` vs error for `--mount`) manifests fully only when
the destination is a *directory*. (Confidence: HIGH for the documented distinction; the live run
reproduces the error path.)

### 8.4 Practical pattern for dev

```yaml
services:
  webapp:
    image: myapp
    volumes:
      - ./.env.dev:/app/src/.env:ro   # hide baked .env, expose dev env at runtime
```
This works — but remember: (a) the baked `.env` is still in the image layer unless excluded by
`.dockerignore` + no `COPY` of it; (b) at runtime the *host* file is what the container sees.

---

## Appendix: Verified command reference

Environment for interpolation (resolve/verify which vars are referenced):
```
docker compose config --environment        # print the interpolation env (shell + .env/--env-file)
docker compose config --variables          # list ${VAR} expressions with required/default/alternate
docker compose config --no-env-resolution  # keep env_file: directive; don't merge into environment
docker compose config --no-interpolate     # don't substitute ${VAR} at all
```

Loading precedence (interpolation):
```
docker compose --env-file custom.env config          # custom.env REPLACES default .env
docker compose --env-file a.env --env-file b.env config  # b.env overrides a.env
```

Required-variable guard (hard fail, exit 1):
```
docker compose -f compose-required.yaml config        # fails if ID unset
docker compose -f compose-required.yaml --env-file id.env config  # succeeds (image: alpine)
```

---

## Sources (high confidence, cross-referenced)

- Official docs — Environment variable precedence: `docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/`
- Official docs — Set environment variables / `env_file` attribute: `docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/`
- Official docs — Variable interpolation / `--env-file`: `docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/`
- Official docs — `docker compose config`: `docs.docker.com/compose/reference/config/`
- Official docs — `.dockerignore` file / `**` wildcard: `docs.docker.com/reference/dockerfile/#dockerignore-file`, `docs.docker.com/build/concepts/context/`
- Official docs — bind mounts / volumes ("Mounting over existing data"): `docs.docker.com/manuals/engine/storage/bind-mounts.md`, `docs.docker.com/manuals/engine/storage/volumes.md`
- Official docs — Dockerfile reference / `COPY --from`: `docs.docker.com/reference/dockerfile/`, `docs.docker.com/reference/dockerfile/copy/`
- Compose spec — `env_file` / env-file format / secrets: `github.com/compose-spec/compose-spec/blob/main/05-services.md`, `spec.md`, `09-secrets.md`
- **Verified source code (docker/compose):**
  - `cmd/compose/compose.go` — two-phase loading: `WithOsEnv` → `WithEnvFiles` → `WithDotEnv`; shell applied first; `COMPOSE_FILE` resolution.
  - `pkg/compose/loader.go` — `WithEnvFiles`/`WithDotEnv` load `.env`/`--env-file` into `project.Environment` (interpolation only, separate from service `env_file:`).
  - `pkg/compose/create.go` — `env_file:` content merged into `service.Environment` → `containerConfig.Env`; secrets reject `driver`/`template_driver`/`external`.
  - `cmd/compose/config.go` — sequences appended on merge; `ExtractVariables` drives `--variables` (`Required`/`DefaultValue`/`PresenceValue`); `$`→`$$` re-escape.
  - `pkg/compose/run.go` + `cmd/compose/run.go` — `env_file` resolved before `-e` overrides; `NewMappingWithEquals` + `OverrideBy` merge for `docker compose run -e`.
  - `pkg/e2e/testdata/TestUpImageID/compose.yaml` — `image: ${ID:?ID variable must be set}` e2e fixture.
- Maintainer statements: docker/compose#3435 (`env_file` is not for interpolation); moby/moby#33923
  (`.dockerignore` does not apply to `COPY --from`); docker/compose#11740/#12180 (`environment:` null-entry
  precedence regression).
- **Live verification (this environment: Docker 29.8.0 / Compose v5.5.1):** §1.2, §1.3, §2.2, §2.3, §2.6
  (compose#12264), §3.2, §3.3, §4.1, §6.2, §7.3, §8.1, §8.3.
