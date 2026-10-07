# Plan 21 — Dev nginx media gate (run the container so BLOCK 9's `/media/` hardening is exercisable end-to-end)

**Status:** ready to execute · **Numbering:** 21 · **Created:** 2026-10-04
**Purpose:** make BLOCK 9's `/media/` hardening *observable in development* — by running the nginx
container that already exists in the dev stack behind a repeatable, non-vacuous check — and by
correcting the three dev-topology statements that the existence of that container falsifies.
**Origin:** the phase-07 brief's BLOCK 9 DoD item *"one irreducible manual gate: a deployed-stack
real-key smoke check"*. An Auditor and a Researcher investigated the live tree empirically and found
that premise false in a specific, useful way (see §1).
**Dependency:** BLOCK 9 shipped as `77c1653` (`fix(nginx): deny script execution under /media and
rate-limit the media path`). This plan adds **no** behaviour to either nginx config and **no**
dependency on any application code. BLOCK 9 is a hard precondition only in the sense that the gate
has nothing to check until the two `location` blocks exist.
**Decision owner:** coordinator. D1–D7 below are settled and **must not be re-opened by the
Implementor**; they are recorded here so no one re-derives them.
**Precondition:** the user directed that this file is the only artefact this plan produces. No code,
no other plan, no compose file, no `.ai/audit/**`.

---

## 0. Provenance and drift control

| Source | Role |
|---|---|
| Auditor session (`Audit dev env for nginx service`) | **Primary input.** Live measurement of the dev stack, the gate run, the non-vacuity control, and the Windows pitfalls. |
| Researcher session (`Research nginx dev container design`) | **Primary input.** Settled decisions D1–D7, the client-process rate measurement, the config-outage taxonomy, the residuals. |
| `docker-compose.yml` / `docker-compose.dev.override.yml` | The service and the profile gate (read-only evidence). |
| `docker/nginx/nginx.conf` / `docker/nginx/nginx.dev.conf` | The subject under test. **Never edited by this plan.** |
| `src/backend/tests/test_nginx_config.py` / `test_compose_hardening.py` | The structural pins that constrain what may be written and where (§3). |
| `.ai/plans/20-media-remediation-execution.md` §BLOCK 9 | The shipped design this plan exercises. |
| `.kilo/rules/project.md`, `.kilo/rules/commands.md` | Repo rules. |

**Citation rule:** every task target in this plan is a **semantic anchor** — a file path, a module, a
class, a function, a settings symbol, a PowerShell target name, a doc section heading. `file:line`
appears **only** as evidence for a finding, never as a target. This repo has a documented history of
stale line citations.

**Measurement discipline:** every number in §1, §5 and §8 was measured on this host and is labelled
as measured. Nothing is projected, extrapolated, or asserted from documentation.

---

## 1. The reframing finding

> **BLOCK 9's "irreducible manual gate" was never impossible. It was never attempted.**

An `nginx` service already exists in the dev stack. It is dormant for exactly one reason: no
`up`-target passes `--profile use-nginx`.

### 1.1 What already works

| Component | State | Evidence |
|---|---|---|
| `services.nginx` in `docker-compose.yml` | Present. `image: nginx:alpine`; `ports: ["80:80","443:443"]`; `media_volume:/media_volume:ro`; `./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro`; `depends_on: [web]`; `cap_drop: ["ALL"]` + five `cap_add`; `read_only: true`; `tmpfs: [/var/cache/nginx, /var/run]`; `security_opt: no-new-privileges:true`; `mem_limit`/`cpus`; `restart: unless-stopped`. | `docker-compose.yml`, the `nginx:` service block. |
| Profile gate in `docker-compose.dev.override.yml` | `nginx.profiles: ["use-nginx"]` — added by `46ac97e`, the same commit that created the dev override. It was an **opt-in**, never an exclusion. The override additionally mounts `media_volume`, `nginx.dev.conf` and `./docker/nginx/certs`. | `docker-compose.dev.override.yml`, the `nginx:` block. |
| mkcert certificates | **Already on disk**: `docker/nginx/certs/fullchain.pem`, `privkey.pem`, `localhost+3*.pem`. `docker/nginx/certs/*.pem` is gitignored (`.gitkeep` excepted), so they are per-clone and must be regenerated after a fresh clone. | `.gitignore`, the mkcert entries. |
| BLOCK 9's gate | **The Auditor ran it and it passed.** `nginx -t` clean for `nginx.dev.conf`; 24 distinct `/media/` URLs → **24 × HTTP 200, zero 429s** on a listings page. Dev DB held 402 published ads / 1212 images, so the 24-thumbnail premise holds on this machine. | Auditor measurement. |
| Non-vacuity control | `curl --parallel --parallel-max 40`, 120 requests → **`200×10 429×32`**, all visible in `docker compose logs nginx`. The limiter is live and observable. | Auditor measurement. |

**Why it is dormant:** `Makefile.ps1::Invoke-Up` and `Makefile::up` pass no `--profile`. Nothing
else is missing. `docs/ops/docker-deployment.md` already documents the service as *"Optional; use
`profiles: ["use-nginx"]`"* and `docs/ops/local-https-mkcert.md` is a complete runbook for it.

### 1.2 The honest shape of the work

D1, D2, D4 and D5 require **zero** changes. There is no compose work to manufacture. The work is:

- **(a) document the existing procedure**, and
- **(b) add a repeatable script** that runs the gate non-vacuously, plus
- **(c) three comment/doc corrections** that the existence of the container falsifies.

---

## 2. Owner decisions in force

Each is settled by measurement. The Implementor records them; it does not re-open them.

**D1 — Keep the existing `use-nginx` profile gate. Zero compose changes.** Five precedents exist in
the project (`seed` in base compose; production `scheduler` / `backup` / `pgbouncer`; `test`). Adding
nginx to the default `up` would make a development-only observability affordance a hard dependency of
the whole dev loop and bind host 80/443 for every developer. `web` must keep publishing `:8000` as
the fast loop.

**D2 — Readiness: leave `depends_on: service_started` exactly as it is.** Do not add an nginx
healthcheck; do not add any `web → nginx` edge. `docker/entrypoint.sh`'s DB/Redis waits apply only to
the Django image, so they never protected nginx anyway. **But the script must poll** — ≈25 s of 502s
was measured while `runserver` booted. Never sleep-then-assert. Note for the runbook: `up -d nginx`
alone drags the whole `db → migrate → load_cities → load_catalog → seed → web` chain and exceeded
120 s; the fast path is `--profile use-nginx up -d --no-deps web bot nginx`.

**D3 — Observability design (the core deliverable).**

- **Do NOT add a dedicated media access log — no config edit.** Filter the shared log.
  `nginx:alpine` symlinks `/var/log/nginx/access.log → /dev/stdout`, so the log is read with
  **`docker compose logs nginx`**; `docker exec … cat` is impossible (there is no file inside the
  container, and an exec'd process reads its own stdout, not the master's). `log_format main` already
  emits `$status`, and `limit_req_status 429;` sits at `http{}` level. A `json` log_format is a
  **separate future BLOCK**, explicitly out of scope here.
- **The burst must be ONE client process issuing N URLs over keepalive — never N process spawns.**
  Measured on this host: a PowerShell loop with one `curl.exe` per request achieves **16.8 r/s**,
  which is *below* `rate=20r/s` and therefore **structurally incapable of tripping the limiter** —
  such a test can never fail, which is worse than no test. One `curl.exe` with N URLs reaches
  **242–520 r/s**. Measured knee: 40 URLs → 0 × 429 (sitting exactly on the `burst=40` edge);
  60 URLs → 16 × 429; 100 URLs → 90 × 429.
- **Headroom is ~1.6×, not an order of magnitude.** `ListingsQuery.PER_PAGE = 24` against
  `burst=40` is 40/24 ≈ 1.67. This must be stated in the plan, the script output and the runbook so
  nobody reads "24 ≪ 40" as a wide margin. The template renders exactly **one** `<img>` per card
  (`ad.images.first.thumbnail_small_url|default:ad.images.first.image_url`, `loading="lazy"`), so a
  single page load is exactly one burst of ≤ 24 tokens out of a 40-token bucket that refills at
  20/s. **A second page load inside 2 s exceeds the bucket.**
- **Every run needs a non-vacuity control that must yield ≥ 1 429**, and the script must **fail** if
  it yields zero. This doubles as the wrong-hop guard: a probe that accidentally targets `:8000`
  bypasses nginx and can never emit a 429.
- **Readiness polling consumes the same bucket.** `nginx.dev.conf` has **no unrated proxyable
  path** — `/login/`, `/search/`, `/moderation/`, `/media/` and `/` all carry `limit_req`, and there
  is no `/health/` location. So: bounded poll (≤ 10 attempts, ≥ 1 s apart), then **settle ≥ 2 s**
  after the last poll (a full `burst=40` drains in 2 s at 20 r/s). The runbook must warn that an open
  dev browser tab shares the bucket.
- **Discriminate the deny outcomes by path, not byte count.** Byte counts are locale- and
  nginx-version-dependent (Django's `403` is 29 bytes in `ru`, 13 in `en`, 15 in `bs`; nginx's is
  153 on 1.31.6). Use two probes: `/media/<realkey>.php` **must** be `403` (only the `~*` block can
  answer this) and `/media/<realkey>` **must not** be `403`. Keep body size as human-readable
  corroboration only.
- **The real catastrophic mode is not the one BLOCK 9 documented.** *Adding* a prefix
  `location /media/` alongside the existing one fails loudly (`[emerg] duplicate location`). The
  genuine outage is putting `deny all; return 403;` **inside** the proxying `location /media/`,
  replacing `proxy_pass` — that **passes `nginx -t` cleanly** and then 403s every photo. A third
  variant is a half-applied edit leaving the regex tail after a prefix header, which passes
  `nginx -t` and leaves the deny **silently inert**, letting scripts proxy through. Both probes
  catch these; the `.php` probe is what catches the inert variant.

**D4 — Do NOT extend the locust harness** (`src/benchmark/locustfile.py`). It has no `/media/` task,
it runs *inside* the `web` container against `:8000`, and repointing it at nginx would put all N
users in one `browse_limit` bucket at ≈17 r/s — so its p95 SLO assertion would be measuring 429s.

**D5 — This is NOT a pytest.** The suite runs under the `mko-bazuna-test` Compose project, which has
no nginx service, so a pytest would always skip. It is also **not** a compose probe service.

**D6 — Verified Windows pitfalls.** The repo's conf files are **CRLF** (189 and 157 CRLF lines;
`nginx.dev.conf` is mixed with 2 bare LF) and **nginx tolerates it** — both pass `nginx -t` with no
warning. **But CRLF silently breaks tooling:** a `$`-anchored `sed` / `awk` / `grep -E` over these
files is a **silent no-op** (the line ends `;\r`); this already bit the Researcher. Any script that
inspects a conf must strip CR first. Bind mounts of the conf and certs from the Windows host work
fine. Ports 80/443 are free and need **no elevation** (Docker Desktop's forwarder runs as a service);
the realistic failure is contention (`Bind for 0.0.0.0:80 failed: port is already allocated`), not
permission. `host.docker.internal` auto-resolves (no `extra_hosts` needed). No compose file declares
a `logging:` block, so logs are `json-file` with **no rotation** — unbounded growth, pre-existing
across all services; this plan does not claim rotation. Post-reboot forwarder flakiness is
**unverified** (no reboot was performed) and is stated as such.

**D7 — Boundary.** Out of scope: any semantic change to `nginx.conf` / `nginx.dev.conf`; TLS on the
application path; any production topology change; any application dependency (no Django setting,
middleware, model or app code change); making the default `up` slower or flakier; `/protected-media/`
coverage; changing `depends_on`.

**D8 — this plan (Planner).** The runbook is a **new** `docs/ops/` document, not a section appended
to `docs/ops/docker-deployment.md`. That file is **1496 lines**, past the `docs/00-overview/doc-maintenance-rules.md`
**hard threshold of 1000** (*"must split"*); adding to it worsens a live violation. The three
*corrections* still edit existing files in place. Rationale is recorded so the coordinator can
override; the override cost is one violation of the doc rule.

---

## 3. Negative constraints — what must NOT be touched, and why

This is the section that protects the plan from itself. Record it verbatim in the tasks.

| Constraint | Detail |
|---|---|
| **N1 — do not edit either conf file** | `docker/nginx/nginx.conf` and `docker/nginx/nginx.dev.conf` are **do-not-touch** for this plan. No value change, no comment, no whitespace. Rationale is a hard test hazard, not conservatism: `_location_block` in `src/backend/tests/test_nginx_config.py` matches the **first** line containing a given string, so **any comment** added to either conf containing `= /metrics`, `/protected-media/`, `/media/` or `limit_req_zone` can shadow a structural test and make it pass or fail for the wrong reason. |
| **N2 — do not change `services.nginx` in compose** | `test_compose_hardening.py::test_nginx_has_cap_add` pins `cap_add`, `cap_drop: ["ALL"]` and the five caps (`NET_BIND_SERVICE`, `CHOWN`, `SETGID`, `SETUID`, `DAC_OVERRIDE`) on that service block. D1 already forbids the change; N2 records why it is not merely inconvenient. |
| **N3 — a dev nginx red-lines nothing** | `src/backend/tests/test_compose_contract.py` has **no nginx assertions** and performs **no Compose merge**. `test_deploy_check_env_parity.py`, `check --deploy` and `test_deploy_workflow.py` are all nginx-agnostic. So enabling nginx in dev cannot break a red line — which also means **no test will ever tell you the gate stopped working** if it silently degrades. That is precisely what the non-vacuity control (S7) is for. |
| **N4 — no pytest, no compose probe service, no locust change** | D4 and D5. |
| **N5 — no new dependency, no new compose file, no new profile** | D1. The script reaches the running stack through the existing compose invocation only. |
| **N6 — the script never writes to `docker/nginx/**`** | It is a read-only observer of the config and a client of the running container. |

---

## 4. Increment 1 — `scripts/verify-nginx-media-limits.ps1` + `Makefile.ps1 verify-nginx`

### 4.1 Surface (semantic units only)

| Unit | Kind | Action |
|---|---|---|
| `scripts/verify-nginx-media-limits.ps1` | **new file** | Create. Precedent for a `.ps1` under `scripts/`: `scripts/github-actions-logs.ps1`. |
| `Makefile.ps1` → `Show-Help` | existing PowerShell function | Add one target line, adjacent to the `seed-photos-*` / `profile` group. |
| `Makefile.ps1` → new `Invoke-VerifyNginx` function | new function, placed beside `Invoke-Profile` / `Invoke-Load` | Follow the file's convention exactly: set `$env:COMPOSE_PROJECT_NAME = $DevProject`, read env overrides with `if ($env:X) { … } else { "default" }`, then invoke the script and propagate its exit code. |
| `Makefile.ps1` → `switch ($Target.ToLower())` | existing dispatch | Add `"verify-nginx" { Invoke-VerifyNginx }`, adjacent to the `"profile"` / `"load"` arms. |
| env overrides `NGINX_BURST`, `NGINX_SETTLE` | new, documented in `Show-Help` | Same shape as `ITERATIONS` / `TOP` / `SORT` for `profile` and `LOCUST_*` for `load`. |

**Not in the surface:** every file under `docker/`, every file under `src/`, `.gitignore`,
`pyproject.toml`, CI workflows, and the bash `Makefile` (see OQ-1).

### 4.2 Binding constraints

1. **Follow the existing pattern (project rule 7).** `Invoke-Profile`, `Invoke-Load` and
   `Invoke-SeedPhotosValidate` are the precedents: set the project name, resolve env overrides with
   defaults, one `docker compose` invocation, no logic. The script itself keeps small focused
   functions (rule 15), one per gate.
2. **Exit-code propagation must be verified on Windows PowerShell 5.1 as well as PowerShell 7+**,
   because `Makefile.ps1`'s own header states the file must run under 5.1. Record the working
   mechanism in the commit body. A target that always exits 0 is a silently broken gate.
3. **English only; `Write-Host` for output** (rule 12's intent). No `print()`-style bare output, and
   nothing written to a pipeline the Makefile has to parse.
4. **The probe origin is `https://localhost` — port 443.** Never `:8000` (bypasses nginx; see S7)
   and never `:80` (the port-80 server answers `301` to HTTPS and would confuse every status tally).
5. **`NGINX_SETTLE` below 2 s is a hard error, not a silent clamp.** The settle is load-bearing (D3).
6. **Never write to `docker/nginx/**`** (N6). The script does not read either conf in v1 (S10).
7. **No `print()` of the full discovered URL list at default verbosity.** Print the count plus the
   first and last key; 24 long URLs is noise that hides the numbers that matter.
8. **Explicit staging.** Other agents share this tree and the index has been swept by a concurrent
   commit before (`749bbfc`). Stage only the two named paths. Never `git add -A`, `.`, or a
   directory. Do not commit without instruction; no `reset` / `checkout` / `restore` / `stash` /
   `--amend` / force-push.

### 4.3 Acceptance criteria

| ID | Criterion |
|---|---|
| AC1.1 | `.\Makefile.ps1 verify-nginx` exists, dispatches through the `switch ($Target.ToLower())` block, and has a `Show-Help` line. |
| AC1.2 | Dev stack up **with** nginx running: **exit 0**; output contains the distinct-URL count, the `200`/`429` tally, **≥ 1 429** from the non-vacuity control, the observed request count and the observed rate. |
| AC1.3 | Dev stack up **without** nginx: **exit 2**; output contains the exact start command. Assert the code is neither 0 nor 1. |
| AC1.4 | nginx **crash-looping** (certs absent): **exit 1**; output contains the `docker compose logs nginx` excerpt, and the message is **textually distinguishable** from AC1.3. |
| AC1.5 | **Tripwire.** The same script pointed at `http://localhost:8000` must **FAIL (exit 1)** at the non-vacuity control. This is the wrong-hop proof and it must be demonstrated, not argued. |
| AC1.6 | The one-process rule is justified by a **recorded measurement**, not an in-code assertion: a per-URL `curl.exe` loop measures ≈16.8 r/s and can never observe a 429; one process with N URLs measures 242–520 r/s. Both figures go in the commit body. |
| AC1.7 | Exit-code propagation verified on 5.1 **and** 7+ (constraint 4.2.2). |
| AC1.8 | `git status --short` shows **only** `scripts/verify-nginx-media-limits.ps1` and `Makefile.ps1`. Nothing else, and no unrelated agent's file is staged. |
| AC1.9 | `git diff --stat -- docker/ src/` is empty. |
| AC1.10 | `.\Makefile.ps1 test` result recorded. If red, re-run **serially** and attribute: a pre-existing red set is acceptable, a new one is not. |

---

## 5. Required behaviour of `scripts/verify-nginx-media-limits.ps1` (enumerated spec)

Gate order is **load-bearing** and must be exactly this:

```
container state → readiness poll → settle → pass gate → deny probes → non-vacuity control
```

The non-vacuity control is **last** because it deliberately fills the bucket; anything after it would
read `429` instead of the intended outcome.

**S1 — Configuration resolution.**
Compose invocation mirrors `Invoke-Profile`: `$env:COMPOSE_PROJECT_NAME = "mko-bazuna-dev"` with
`--env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx`.
Env overrides, each echoed at start-up: `NGINX_BURST` (default `120`), `NGINX_SETTLE` (default `2`,
seconds, **minimum 2**), `NGINX_POLL_ATTEMPTS` (default `10`), `NGINX_POLL_INTERVAL` (default `1`,
seconds, minimum `1`). Probe origin `https://localhost`.

**S2 — Container state detection, before any HTTP.**
Distinguish three states and give the last two **different** messages:
- **absent** → print the start command and the certificate prerequisite, then **exit 2**.
- **present but not running** (created / exited / restarting) → print
  `docker compose … logs --tail 50 nginx`, then **exit 1**. This is the crash-loop signature and it
  is the realistic failure on a fresh clone, because the certs are gitignored.
- **running** → continue.

**S3 — Bounded readiness poll.**
Target `https://localhost/health/live/`; require **HTTP 200**. There is no unrated proxyable path, so
this resolves to `location /` and therefore does carry `limit_req zone=browse_limit burst=40 nodelay`
— the poll consumes at most 10 of 40 burst tokens. Any non-200, including the ≈25 s of 502s measured
while `runserver` booted, does **not** satisfy the gate: keep polling. Exhausted → **exit 1** with the
last observed status and a `docker compose … logs --tail 50 web` excerpt. **Never sleep-then-assert.**

**S4 — Settle.**
Sleep ≥ `NGINX_SETTLE` seconds **after the last poll request**. Reason: a full `burst=40` drains in
2 s at 20 r/s. `NGINX_SETTLE < 2` → **exit 1** with an explanatory message; do not clamp silently.

**S5 — Pass gate: the thumbnails page, zero 429.**
Fetch `https://localhost/` and extract the `src` values that begin with `/media/`. De-duplicate; let
the distinct count be **N**. Then re-issue **all N URLs in ONE client process** (a single `curl.exe`
invocation with N URL arguments) with keepalive and status-only output.
- **N ≥ 1**, else **exit 1** — "nothing to rate-limit; the run is vacuous".
- Gate: every status is `200` **and** the `429` count is `0`. Otherwise **exit 1**.
- Report: N, the per-status tally, requests ÷ elapsed (the observed rate).
- Report N alongside `ListingsQuery.PER_PAGE = 24` and `burst = 40`, and state the headroom as
  **~1.6×**. A count below 24 is a **data** condition (ads without an image render no `<img>`) and is
  **reported, not failed** — see OQ-2.
- **Never one process per URL.** A per-URL loop measures ≈16.8 r/s, sits below `rate=20r/s`, and can
  therefore never observe a 429: it cannot fail, which is worse than no check.

**S6 — Deny probes, discriminated by path.**
Take one real key **K** discovered in S5.
- **Probe A** — `https://localhost/media/<K>.php` → **must be `403`**. Only the `~*` regex location can
  answer this; a `200` means the deny block is missing or **inert** (the half-applied-edit variant).
- **Probe B** — `https://localhost/media/<K>` → **must not be `403`**. A `403` here is the
  prefix-replacement outage that passes `nginx -t` cleanly.
- Print the byte sizes as **human-readable corroboration only**. **Never assert on them** — Django's
  `403` is 29 bytes in `ru`, 13 in `en`, 15 in `bs`; nginx's is 153 on 1.31.6.
- **Two probes, not twenty-four.** A full burst would risk tripping the limiter and turn the outcome
  into a `429`, which is evidence of nothing.

**S7 — Non-vacuity control (last).**
Issue `NGINX_BURST` distinct `/media/` URLs as **one** client process (`--parallel --parallel-max 40`).
**Must yield ≥ 1 `429`.** Zero 429s → **exit 1** naming both likely causes: a wrong hop (targeting
`:8000`) or a removed / altered `limit_req`. Assert only **≥ 1**, never a specific count — the exact
split is rate-machine dependent (measured: 40 URLs → 0; 60 → 16; 100 → 90; the 120-request parallel
run produced `200×10 429×32`).

**S8 — Log corroboration.**
The control's 429s must be visible in `docker compose … logs nginx`, by filtering the shared
`log_format main` output for `$status 429` on a `/media/` request. **Never** `docker exec … cat
/var/log/nginx/access.log`: `nginx:alpine` symlinks that path to `/dev/stdout` and an exec'd process
reads its own stdout, not the master's. There is no file in the container to read.

**S9 — Output discipline.**
`Write-Host` only. One line per gate carrying `PASS` / `FAIL` / `SKIP`, the measured numbers, and the
eventual exit code. Print the discovered count plus the first and last key, not the whole list.

**S10 — CRLF warning (v1 does not inspect a conf; the warning is inherited forward).**
v1 **must not read** `docker/nginx/nginx.conf` or `docker/nginx/nginx.dev.conf`. If a future variant
inspects either, it **must strip `\r` before any regex match**: a `$`-anchored `sed` / `awk` /
`grep -E` over these CRLF files is a **silent no-op** because every directive line ends `;\r`. nginx
itself tolerates the CRLF (both files pass `nginx -t` with no warning), so the breakage is invisible
until the check silently passes. **Print this warning once at the end of every run** so the next
author inherits it. Record the measured CRLF counts: 189 and 157 CRLF lines; `nginx.dev.conf` is
mixed with 2 bare LF.

**S11 — No container lifecycle.**
The script never runs `up`, `down`, `restart`, `pull` or `build`. It detects and probes only.
Starting the stack is the runbook's job (§6.4) — because `up -d nginx` alone exceeds 120 s on the
full dependency chain.

**S12 — Exit-code contract.**

| Code | Meaning |
|---|---|
| `0` | **PASS** — readiness, pass gate, deny probes and non-vacuity control all green. |
| `1` | **FAIL** — any gate failed; **or** nginx present but never served (poll exhausted); **or** nginx present and not running (crash-loop). |
| `2` | **SKIP** — the nginx container is **absent**; the dev stack is running without `--profile use-nginx`. |

`2` is never a pass and never a failure. `0` is never a skip. The two absent-adjacent states —
**absent** (exit 2) and **crash-looping** (exit 1) — must produce **different** messages, so the
operator can tell *"you did not start it"* from *"it is broken"*. *Design note:* crash-looping is
given exit 1 rather than exit 2 deliberately — a container that is present and cannot serve is a
real failure, whereas exit 2 exists solely for the "this run was never applicable" case.

---

## 6. Increment 2 — three comment/doc corrections + the runbook

Increment 2 depends on Increment 1 only through **one string**: the runbook documents the exact
command, so it must be written after `.\Makefile.ps1 verify-nginx` exists and must quote it verbatim.

### 6.1 Surface (semantic units only)

| ID | Unit | Kind | Action |
|---|---|---|---|
| **C1** | `src/backend/config/settings/dev.py` → the comment block immediately preceding `TRUSTED_PROXY_NETWORKS` | existing comment | **Amend the prose. The value stays `tuple[str, ...] = ()`.** |
| **C2** | `src/backend/config/settings/dev.py` → the comment block immediately preceding `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX` | existing comment | **Amend the rationale. All three values above it stay unchanged.** |
| **C3** | `docs/ops/docker-deployment.md` → the `**Bind-mount scope in dev:**` paragraph under `### Development Services` | existing paragraph | Correct the service list. |
| **R1** | `docs/ops/dev-nginx-media-gate.md` | **new file** | The runbook (D8). `## Purpose` first — doc rule. Frontmatter shape mirrors `docs/ops/local-https-mkcert.md`. |
| **R2** | `docs/ops/docker-deployment.md` → `### Production-like Development` | existing section | One cross-link line to the new runbook. |
| **R3** | `docs/ops/local-https-mkcert.md` → `### nginx Fails to Start` | existing section | One cross-link line to the new runbook, next to the existing `docker compose logs nginx` advice. |

**Why C1 and C2 are comment-only.** Both stale rationales justify themselves with *"the default dev
stack publishes Django directly on :8000, so the peer is loopback"* and *"publishes Django directly on
:8000 with no proxy"*. Both remain **correct values** once nginx is in front; only their stated reason
was scoped to the default topology. Amending a rationale is honest; changing the value would be a
behaviour change to the dev stack and is out of scope under D7.

**Anchor note for C2 (important — do not edit the wrong block).** The stale *"no proxy"* claim is not
in the comment above `SESSION_COOKIE_SECURE` itself; it is in the block above
`LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX`, which sits directly beneath `SESSION_COOKIE_SECURE` and
`CSRF_COOKIE_SECURE` and whose opening sentence makes the proxy claim. `SESSION_COOKIE_SECURE` is
grouped with it in that block's rationale. Edit **that** block.

### 6.2 Binding constraints

1. **No value changes.** `TRUSTED_PROXY_NETWORKS` stays `()`; `SECURE_SSL_REDIRECT`,
   `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` and `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX` all keep
   their current values. `SESSION_COOKIE_SECURE = False` remains correct: you still want an insecure
   cookie while debugging over plain `:8000`.
2. **C1 must state why `()` is still correct.** `_is_trusted_peer` also accepts `peer.is_private`, so
   the bridge gateway peer is trusted without a `TRUSTED_PROXY_NETWORKS` entry. And it must state the
   operational consequence the current prose misses: `get_client_ip` returns the **real peer** through
   nginx but `127.0.0.1` on a direct `:8000` hit, so **application-level rate-limit bucketing differs
   between the two topologies**. Do not cite a bridge-gateway address — `base.py`'s comment already
   explains that no compose file declares `networks:`, so there is no correct in-repo value.
3. **Do not touch `src/backend/config/settings/test.py`.** Its `TRUSTED_PROXY_NETWORKS` comment says
   the test client peers from loopback — that is *true*, not stale.
4. **`config/settings/tests/test_settings_defaults.py::test_dev_and_test_share_the_transport_tuple`
   must stay green.** It asserts dev/test agreement on all seven transport settings, so prose may be
   edited and values may not.
5. **`docker-deployment.md` is a shared, previously-dirty file.** Re-read it **immediately** before
   editing; if the paragraph has changed since this plan was written, **stop and report** rather than
   clobber. Never a wholesale rewrite.
6. **The new runbook must satisfy `docs/00-overview/doc-maintenance-rules.md`**: `## Purpose` present,
   English only, frontmatter verified, tables for structured data.
7. **`local-https-mkcert.md` is the certificate prerequisite and is not rewritten here** — the new
   runbook links to it rather than duplicating its setup steps.
8. English only; no bare `print()`; `rg`-free tooling is irrelevant here but **CRLF stripping is
   mandatory** if any tooling inspects a conf (S10) — which is why the runbook's troubleshooting
   entries are written as commands a human runs, not as regex over the conf.
9. Explicit staging; nothing outside the six units above.

### 6.3 Acceptance criteria

| ID | Criterion |
|---|---|
| AC2.1 | **C1**: `TRUSTED_PROXY_NETWORKS` is still `()`; the comment cites the `peer.is_private` path as the reason that stays true, **and** states the `get_client_ip` topology difference. |
| AC2.2 | **C2**: the `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX` comment block no longer asserts *"no proxy"* unconditionally; it says the plain-HTTP premise holds **only for the default `:8000` topology**, and records that under `--profile use-nginx` there **is** a proxy and the forwarded scheme is `https`. All four values unchanged. |
| AC2.3 | **C2**: `test_settings_defaults.py` green; `config/settings/test.py` byte-identical. |
| AC2.4 | **C3**: the `**Bind-mount scope in dev:**` paragraph no longer claims `.:/app` is applied to `nginx`, and its service list **matches the dev override's actual `volumes:` blocks**. At plan-authoring time the paragraph was additionally wrong about `create_admin` (it **is** bound `.:/app`; the paragraph calls it env-only) and **omitted** `load_cities` (also bound). The Implementor re-reads and reconciles **every** name — see OQ-4. |
| AC2.5 | **R1**: the runbook exists, opens with `## Purpose`, is English only, has frontmatter consistent with `local-https-mkcert.md`, and carries **every** item in §6.4. |
| AC2.6 | **R2/R3**: both cross-links resolve to the new doc by its heading, and neither file's existing content is otherwise altered. |
| AC2.7 | `uv run ruff check src/backend/config/settings/dev.py` clean; `basedpyright` shows no new error on that file. |
| AC2.8 | `git status --short` shows only the six units in §6.1 (plus the Increment 1 files if still uncommitted). |
| AC2.9 | `.\Makefile.ps1 test` result recorded. **Proportional gate:** because no value changes, the full suite is *not* required — `test_settings_defaults.py` plus ruff is the gate, and the full suite becomes mandatory only if any value was in fact touched. |

### 6.4 Runbook content the new doc must carry

1. **What it is and what it proves.** BLOCK 9's dev-side gate: `limit_req` on the `/media/` path does
   not throttle a normal 24-thumbnail page, and the script-execution deny block is live and does not
   403 genuine photos. State plainly what it does **not** prove (the three residuals, §9).
2. **The exact command.** The `--profile use-nginx up -d --no-deps web bot nginx` fast path, then
   `.\Makefile.ps1 verify-nginx`. **Why `--no-deps`:** `up -d nginx` alone drags
   `db → migrate → load_cities → load_catalog → seed → web` and exceeded 120 s. Also give the full
   `up -d` form for a cold start.
3. **The mkcert prerequisite — first, because it is the failure nobody sees.** The certs are
   **gitignored**, so **a fresh clone cannot start nginx**. With `restart: unless-stopped` a missing
   cert is a **crash-loop**, not a visible failure. Link to `local-https-mkcert.md` for setup; state
   the symptom (`docker compose logs nginx` shows the `ssl_certificate` cannot be loaded) and the
   fix.
4. **The probe targets 443, not 8000.** `:8000` stays published as the fast dev loop, so a probe that
   targets it **bypasses nginx entirely**, can never emit a 429, and would pass vacuously. The
   non-vacuity control exists to catch exactly this.
5. **The shared `browse_limit` bucket caveat.** `/login/`, `/search/`, `/moderation/`, `/media/` and
   `/` all draw on `browse_limit` (except `/login/`, on its own `login_limit`). The readiness poll
   consumes from it and the script settles ≥ 2 s afterwards. **An open dev browser tab shares the
   bucket** and can push the pass gate over the edge. Close heavy tabs, or wait, before a run.
6. **The headroom is ~1.6×, not an order of magnitude.** 24 of a 40-token bucket refilling at 20/s.
   **A second page load inside 2 s exceeds it.** If a developer sees intermittent 429s on images while
   clicking through listings quickly, this — not a bug — is the cause.
7. **Reading the evidence.** `docker compose logs nginx` and filter for status 429 on a `/media/`
   request. State explicitly that `docker exec nginx cat /var/log/nginx/access.log` **cannot** work
   (the path is a symlink to `/dev/stdout`).
8. **Reading the exit codes.** 0 pass / 1 fail / 2 skip, and the absent-vs-crash-loop distinction.
9. **Troubleshooting table** — rows for: exit 2 (nginx not started); exit 1 with a log excerpt
   (crash-loop / missing certs); exit 1 at the non-vacuity control (wrong hop, or `limit_req` changed);
   exit 1 at the deny probes (the deny block is inert, or the prefix replacement outage);
   `Bind for 0.0.0.0:80 failed: port is already allocated` (host contention — **not** a permissions
   problem, and **no elevation is required**); intermittent 429s (shared bucket, item 5).
10. **What is not covered.** §9's three residuals, verbatim, plus `/protected-media/` — it is
    `internal`, and with `DEBUG=True` `media_gate` takes the `FileResponse` branch and never emits
    `X-Accel-Redirect`, so `alias`, the MIME whitelist and `Content-Disposition` stay unexercised in
    dev.
11. **Explicitly: do not add an access log.** Filtering the shared log is the design; a `json`
    `log_format` is a separate future BLOCK.
12. **The CRLF trap**, for whoever writes the next thing that inspects a conf: strip `\r` first, or
    a `$`-anchored match is a silent no-op.

---

## 7. Explicitly out of scope

- **Any semantic change to `docker/nginx/nginx.conf` or `docker/nginx/nginx.dev.conf`** — no value,
  no comment, no whitespace. Non-negotiable: N1's `_location_block` shadowing hazard and N2's cap
  pins.
- **Adding nginx to the default `up`**, adding an nginx healthcheck, or adding any `web → nginx`
  dependency edge. D1, D2.
- **Any new compose file, compose service, profile, or dependency.** D1, N5.
- **Any application change** — no Django setting value, no middleware, no model, no migration, no
  template, no app code. D7.
- **Any production topology change.** D7.
- **TLS on the application path.** D7.
- **`/protected-media/` coverage.** Unreachable in dev (residual 2).
- **A dedicated media access log or a `json` `log_format`.** A separate future BLOCK (D3).
- **A pytest for the gate.** D5.
- **A compose probe service.** D5.
- **Extending `src/benchmark/locustfile.py`.** D4.
- **Log rotation.** Pre-existing unbounded `json-file` on every service; not introduced here and not
  claimed to be fixed (residual 3).
- **A CGNAT / NAT-aggregation reproduction.** Structurally impossible on loopback (residual 1).
- **Bash `Makefile` parity for `verify-nginx`.** See OQ-1.
- **Claiming BLOCK 9's deployed-stack gate is now satisfied.** It is **not** (residual 1).

---

## 8. Risks

| ID | Risk | Class | Likelihood | Impact | Mitigation | Residual |
|---|---|---|---|---|---|---|
| **R1** | The zero-429 pass gate is **vacuous**: a per-request client loop measures 16.8 r/s, below `rate=20r/s`, so it can never trip the limiter and can never fail | Correctness | **High** if built naively | High — a green gate that proves nothing | S5 mandates **one** client process with N URLs; the measured 242–520 r/s figure is recorded in the commit body (AC1.6) | Very low |
| **R2** | **Wrong hop**: the probe targets `:8000`, bypassing nginx, so a 429 is impossible and the whole run passes vacuously | Correctness | Medium | High | The non-vacuity control (S7) **fails the run** on zero 429s; AC1.5 makes this an explicit tripwire; S1 and the runbook fix the origin at 443 | Very low |
| **R3** | **Shared bucket**: the readiness poll and an open dev browser tab draw on `browse_limit`, so the 24-thumbnail pass gate sees 429s that are not a defect | Flakiness | **High** | Medium | Bounded poll (≤ 10, of 40 tokens) then settle ≥ 2 s (S3, S4); runbook item 6 warns explicitly; `NGINX_SETTLE` is overridable | Med — accepted and documented |
| **R4** | Host ports 80/443 already allocated → `Bind for 0.0.0.0:80 failed: port is already allocated` | Environment | Medium | Medium | Exit 2 names the start command; the troubleshooting table states this is contention and **not** permissions, and that no elevation is needed (D6) | Low |
| **R5** | **Missing mkcert certs on a fresh clone** → nginx crash-loops under `restart: unless-stopped`, presenting as an invisible failure rather than an error | Environment | **High** on a fresh clone | Medium | S2 separates *absent* (exit 2) from *present-not-running* (exit 1) and prints `docker compose logs nginx`; runbook puts the certificate prerequisite first | Low |
| **R6** | Readiness asserted by a fixed sleep → ~25 s of measured 502s makes the run fail or, worse, a longer sleep masks a genuinely broken hop | Correctness | Medium if built naively | Medium | S3 forbids sleep-then-assert; bounded poll with an exhausted-poll failure and a `web` log excerpt; D2 forbids a compose-level fix | Very low |
| **R7** | Deny discrimination by **byte count** → locale- and version-dependent (29/13/15 bytes for Django's 403; 153 for nginx's on 1.31.6) gives locale-flaky, version-flaky results | Correctness | Medium if built naively | Medium | S6 discriminates **by path** (`.php` must be 403; the real key must not be); byte size is printed as corroboration and **never** asserted | Very low |
| **R8** | The genuine config catastrophe is not caught: `deny all; return 403;` placed **inside** the proxying `/media/` location passes `nginx -t` and 403s every photo; a half-applied edit leaves the regex tail **inert** and lets scripts proxy through | Regression | Low | **High** — a site-wide image outage, or an open script-execution hole | Probe B catches the replacement outage; **Probe A** catches the inert variant. N1 keeps the plan from *causing* either. This is exactly why BLOCK 9's deployed gate is not replaced | Med — accepted; the deployed gate still stands |
| **R9** | A conf edit (even a comment) containing `= /metrics`, `/protected-media/`, `/media/` or `limit_req_zone` shadows `_location_block`'s first-match lookup and silently re-points a structural test; a compose edit to `services.nginx` breaks `test_nginx_has_cap_add` | Regression | Low | **High** — a green suite asserting the wrong block | N1, N2, N6; AC1.9 requires `git diff --stat -- docker/ src/` to be empty; the script never writes under `docker/nginx/**` | Very low |
| **R10** | The check is run against the slow path: `up -d nginx` alone drags `db → migrate → load_cities → load_catalog → seed → web` and exceeded 120 s, so the operator gives up or times out | Usability | Medium | Low | S11 forbids the script from starting anything; runbook item 2 leads with the `--no-deps` fast path and explains why | Very low |

---

## 9. Irreducible residuals — state these, do not fix them

1. **CGNAT is unobservable in dev.** Every probe request came from a single `$remote_addr`. A loopback
   check has exactly **one** rate-limit key by construction and therefore **cannot** reproduce NAT
   aggregation — the exact scenario that makes `burst` matter in production. Only the deployed-stack
   check on a real host observes this. **BLOCK 9's original deployed gate is therefore NOT replaced
   by this plan; it remains mandatory and outstanding.**
2. **`/protected-media/` is unreachable in dev.** It is `internal`, and with `DEBUG=True` `media_gate`
   takes the `_serve_image` `FileResponse` branch and never emits `X-Accel-Redirect`. So `alias`, the
   MIME whitelist and `Content-Disposition` stay unexercised. Reaching it would require
   `DEBUG=False` in a dev-shaped stack — an application change, which D7 forbids.
3. **Unbounded log growth.** No compose file declares a `logging:` block, so every service — including
   nginx — uses `json-file` with **no rotation**. Pre-existing across the whole stack, not introduced
   here, and this plan makes **no** rotation claim.

---

## 10. Open questions

Stated, not invented away. Each needs a coordinator answer; none blocks starting Increment 1.

- **OQ-1 — bash `Makefile` parity.** Should `make verify-nginx` exist? It is deliberately out of scope:
   the 16.8 / 242–520 r/s figures are Windows `curl.exe` measurements, and a bash `make` path would
   need its own measurement before it could carry the same non-vacuity guarantee. Default: **no**.
- **OQ-2 — should the pass gate hard-require exactly 24?** `ListingsQuery.PER_PAGE = 24`, but the
   template renders no `<img>` for an ad without an image, so a real page can carry fewer. v1 accepts
   **N ≥ 1** and reports N. Alternative: fail below 24 with a *"seed data is thin"* message. Default:
   accept and report — a data condition is not a config defect.
- **OQ-3 — the stale rate-limit table.** `docs/ops/docker-deployment.md`'s rate-limiting table lists
   only `/login/` and `/search/`; the shipped confs also rate-limit `/media/`, `/moderation/` and `/`.
   BLOCK 9 deliberately touched only the two confs and its test, so this table is **unowned**. Widen
   C3 to reconcile it, or route it to a documentation owner?
- **OQ-4 — how wide is C3?** The `**Bind-mount scope in dev:**` paragraph has **two further**
   inaccuracies beyond nginx: it states `create_admin` receives only `.env.dev` when the dev override
   in fact binds `.:/app` to it, and it omits `load_cities`, which is also bound. §6.1 C3 and AC2.4
   instruct the Implementor to reconcile every name; the open question is whether the coordinator
   prefers that, or wants the nginx claim fixed and the other two **routed** as a written request.
- **OQ-5 — post-reboot port-forwarder flakiness.** Docker Desktop's forwarder on 80/443 after a host
   reboot is **unverified** — no reboot was performed (D6). If it reproduces, does it earn a runbook
   troubleshooting row, or a follow-up BLOCK?
- **OQ-6 — CI wiring.** `verify-nginx` needs a running dev stack, so it is developer-invoked only. If
   CI wiring is expected later, it belongs to a CI BLOCK, not here. Confirm none is wanted now.
- **OQ-7 — `--parallel-max 40` is a host measurement.** The non-vacuity control's default relies on a
   single-process client reaching ≫ 20 r/s. On a materially slower host the default may need raising.
   The control asserts only **≥ 1 429**, so it degrades to *inconclusive* rather than *wrong* — but
   should the script **warn** when the observed rate is below 40 r/s, so a slow host does not read as
   a passing gate forever?

---

## 11. Sequencing and dependency DAG

```
        BLOCK 9 (77c1653)  ─────────────────────────────►  Increment 1
        [hard precondition: the gate has nothing to check        │
         until the two location blocks exist]                    │
                                                                  ▼
                                                   scripts/verify-nginx-media-limits.ps1
                                                   Makefile.ps1: Show-Help + Invoke-VerifyNginx
                                                   + switch arm "verify-nginx"
                                                                  │
                                                                  │ soft edge: exactly one string —
                                                                  │ the runbook must quote the real command
                                                                  ▼
        Increment 2
        C1  config/settings/dev.py  ── TRUSTED_PROXY_NETWORKS comment   (value unchanged)
        C2  config/settings/dev.py  ── LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX comment (values unchanged)
        C3  docs/ops/docker-deployment.md ── "Bind-mount scope in dev" paragraph
        R1  docs/ops/dev-nginx-media-gate.md  (new runbook)
        R2  docs/ops/docker-deployment.md ── cross-link
        R3  docs/ops/local-https-mkcert.md  ── cross-link
```

- **Increment 1 first.** It is the substance, it is verifiable, and Increment 2's runbook documents
  its command.
- **The C1 / C2 / C3 / R1–R3 edits are mutually independent** — different files, no shared surface —
  so they may be done in any order or in parallel once Increment 1's command string is fixed.
- **No dependency on BLOCK 8, 10 or 11.** No shared files.
- **Do not start Increment 2's `docker-deployment.md` edits until Increment 1 has committed** —
  `docs/ops/docker-deployment.md` has a history of being edited by concurrent phases, and a second
  concurrent editor is the risk the append-only discipline exists to prevent.
- **BLOCK 10's constraint on `docs/ops/docker-deployment.md` still applies**: it was dirty with another
  phase's account-state edits when BLOCK 10 was planned. Re-read immediately before editing; on
  conflict, **stop and report**.