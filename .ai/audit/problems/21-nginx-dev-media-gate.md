# Audit Report — Plan 21: nginx-dev-media-gate

**Date:** 2026-10-07
**Plan:** `.ai/plans/21-nginx-dev-media-gate.md`
**Verdict:** NOT FULLY EXECUTED — code and doc changes required → mark `_fix`

---

## 1. Execution summary

| Work Item | Plan § | Status | Code changes needed? |
|---|---|---|---|
| WI-1: `scripts/verify-nginx-media-limits.ps1` | Increment 1, §4/§5 | **NOT DONE** — script exists but is a different design than the plan's enumeration spec (S1–S12). Substantive code changes required. | **YES** |
| WI-1: `Makefile.ps1` `verify-nginx` target | Increment 1, §4.1 | Partial — Show-Help line, function, switch arm, exit-code propagation all present. But `Invoke-VerifyNginx` does not set `$env:COMPOSE_PROJECT_NAME = $DevProject` as §4.1 constraint 1 requires, and defaults differ from the plan (45/15 vs 120/2). | **YES** (defaults, project-name) |
| WI-2: C1 — `TRUSTED_PROXY_NETWORKS` comment | §6.1 C1, AC2.1 | **NOT DONE** — comment does not cite the `peer.is_private` path, and does not state the `get_client_ip` topology difference (real peer via nginx vs `127.0.0.1` on direct :8000). | **NO** (doc-only) |
| WI-2: C2 — `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX` comment | §6.1 C2, AC2.2 | DONE — comment conditionally states the proxy exists under `use-nginx`, all four values unchanged. | — |
| WI-2: C3 — bind-mount paragraph | §6.1 C3, AC2.4 | DONE — verified against `docker-compose.dev.override.yml`: the six `.:/app`-bound services match; `migrate` has no `volumes:`; `nginx` is not `.:/app`-bound. | — |
| WI-2: R1 — runbook `docs/ops/dev-nginx-media-gate.md` | §6.1 R1, AC2.5 | **NOT DONE** — exists (121 lines, opens with `## Purpose`, English, frontmatter present) but carries **none** of §6.4 items 2, 4, 5, 6, 7, 9, 11, 12; item 1 and 10 are partial; describes a *different* implementation than the plan (static conf parsing, 5 exit codes, sequential burst). | **YES** (doc-only rewrite) |
| WI-2: R2 — cross-link in `docker-deployment.md` | §6.1 R2 | DONE — line 299–301 cross-links under `### Production-like Development`. | — |
| WI-2: R3 — cross-link in `local-https-mkcert.md` | §6.1 R3 | DONE — line 248–250 cross-links under `### nginx Fails to Start`. | — |

Files created by the implementation (exist, verified):
- `scripts/verify-nginx-media-limits.ps1` — 442 lines, committed as `51e84c50`
- `Makefile.ps1` — `verify-nginx` target added (`b6fe7d87`)
- `src/backend/config/settings/dev.py` — comment-only C2 change (`95ccf2ab`)
- `docs/ops/dev-nginx-media-gate.md` — runbook (`4ecdd3b6`)
- `docs/ops/ops-nginx-rate-limit-gate.md` — additional runbook (`4ecdd3b6`, not in plan scope)

Code checks: `uv run ruff check src/backend/config/settings/dev.py` should be clean (comment-only); `basedpyright` should show no new errors (comment-only). These could not be executed in this environment (no Docker test DB).

---

## 2. Code problems (require code changes)

### 2.1 Script exit-code contract does not match the plan — HIGH

**File:** `scripts/verify-nginx-media-limits.ps1` (lines 99–104, the `$ExitPass` through `$ExitProbeFail` block)
**Plan:** §5 S12, AC1.3, AC1.4

The plan defines exactly three exit codes (§5 S12):

| Code | Meaning |
|---|---|
| `0` | PASS |
| `1` | FAIL — any gate failed; or nginx present but not running (crash-loop) |
| `2` | SKIP — nginx container absent |

The plan further specifies:
- **AC1.3**: Dev stack up **without** nginx → **exit 2**; output contains the start command.
- **AC1.4**: nginx **crash-looping** (certs absent) → **exit 1**; output contains `docker compose logs nginx` excerpt, textually distinguishable from AC1.3.
- **AC1.15 (S12)**: "`2` is never a pass and never a failure. `0` is never a skip. The two absent-adjacent states — absent (exit 2) and crash-looping (exit 1) — must produce different messages."

The script instead defines **five** exit codes and inverts the mapping:

```
$ExitPass       = 0   # PASS
$ExitConfig      = 1   # CONFIG
$ExitStopped     = 2   # STOPPED (crash-loop)
$ExitAbsent      = 3   # ABSENT
$ExitProbeFail   = 4   # PROBE FAIL
```

This means:
- **Absent** → exit `3` (plan requires exit `2` per AC1.3)
- **Crash-looping** → exit `2` (plan requires exit `1` per AC1.4)

The two absent-adjacent states are assigned the plan's exact codes for the *other* state, violating AC1.15's distinguishability requirement: an operator cannot tell "you did not start it" (exit 2 in the plan) from "it is broken" (exit 1 in the plan), because the script swaps them.

**Fix:** Conform the exit code contract to §5 S12 / AC1.3 / AC1.4 / AC1.15: absent → exit 2 with the start command; crash-looping → exit 1 with a `docker compose logs nginx` excerpt; merge CONFIG and PROBE FAIL into exit 1.

---

### 2.2 Script reads the nginx conf — direct violation of S10 — CRITICAL

**File:** `scripts/verify-nginx-media-limits.ps1` (lines 167–304, the "Static parse" section)
**Plan:** §5 S10

The plan explicitly states:

> **S10.** v1 **must not read** `docker/nginx/nginx.conf` or `docker/nginx/nginx.dev.conf`. [...] The warning is inherited forward. v1 **must not** read.

The script's entire opening section (lines 167–304) is a "Static parse" that:
- Reads `docker/nginx/nginx.dev.conf` via `[System.IO.File]::ReadAllText` (line 178)
- Regex-matches `limit_req_zone` directives (line 193)
- Extracts the `location /media/` block by brace-depth tracking (lines 207–226)
- Asserts `zoneNames.Count -eq 4`, `browse_limit` present, `burst=40`, `nodelay`, `limit_req_status 429` (lines 274–294)

This is a direct contradiction of S10 and also of N6 ("the script never writes to `docker/nginx/**`" — note the plan forbids *reading* in v1, and the script reads while not writing).

The runbook (R1) line 34 reinforces the wrong behaviour: it describes the gate as "a read-only PowerShell 7+ script that **parses** `docker/nginx/nginx.dev.conf`."

**Fix:** Remove the static parse section. Per S10, v1 must not read either conf file. The CRLF warning (S10) must be printed unconditionally at the end of every run as an inherited caution for the *next* author.

---

### 2.3 Burst probe uses sequential per-URL curl — the exact vacuous pattern R1 forbids — CRITICAL

**File:** `scripts/verify-nginx-media-limits.ps1` (lines 400–406)
**Plan:** §5 S5/S7, Risk R1, AC1.6

The plan's core methodology requirement (§5 S5, S7) is that **all N URLs must be issued as ONE client process** — a single `curl.exe` invocation with N URL arguments. The plan records the empirical justification (§5 S6, §1) and makes it a binding constraint:

> **D3 (S5/S7):** "The burst must be ONE client process issuing N URLs over keepalive — never N process spawns." Measured on this host: a PowerShell loop with one `curl.exe` per request achieves **16.8 r/s**, which is *below* `rate=20r/s` and therefore **structurally incapable of tripping the limiter** — such a test can never fail, which is worse than no test.

> **AC1.6:** "The one-process rule is justified by a **recorded measurement**... a per-URL `curl.exe` loop measures ≈16.8 r/s and can never observe a 429; one process with N URLs measures 242–520 r/s. Both figures go in the commit body."

> **R1:** The zero-429 pass gate is **vacuous**: a per-URL curl.exe loop measures 16.8 r/s, below `rate=20r/s`, so it can never trip the limiter and can never fail.

The script's "Burst probe" (lines 400–406) does the exact opposite:

```powershell
for ($i = 1; $i -le $Burst; $i++) {
    $uri = "$Url/media/seed/verify-nginx-media-limits-gate-$i.jpg"
    $burstCodes.Add((& curl.exe -k -s -o NUL -m 5 -w "%{http_code}" $uri)) | Out-Null
}
```

This is **one `curl.exe` process per URL in a sequential loop** — the pattern the plan explicitly classifies as structurally vacuous. At `NGINX_BURST=45` default (see §2.4 below), each request is a separate process spawn, so the effective rate is ~16.8 r/s (measured in the plan), which can never observe nginx `429`s. The burst probe will **always** report zero `429`s and exit `PROBE FAIL` — a gate that can never pass, not a gate that can never fail.

The "Settle probe" (lines 423–429) has the same defect: it loops 40 times with one `curl.exe` per URL.

**Fix:** Replace both probes with a single `curl.exe --parallel --parallel-max N` invocation carrying all URL arguments in one process, as the plan specifies in §1 (§5 S5/S7). Record the 16.8 / 242–520 r/s measurements in the commit body per AC1.6.

---

### 2.4 NGINX_BURST and NGINX_SETTLE defaults do not match the plan — MEDIUM

**File:** `scripts/verify-nginx-media-limits.ps1` (line 118–119, 444–447)
**Plan:** §5 S1, S5, S7

| Variable | Plan default | Script default |
|---|---|---|
| `NGINX_BURST` | `120` (§5 S1, S7: "Issue NGINX_BURST distinct /media/ URLs") | `45` |
| `NGINX_SETTLE` | `2` seconds (§5 S1, S4: "NGINX_SETTLE (default 2, seconds, minimum 2)") | `15` |
| `NGINX_POLL_ATTEMPTS` | `10` (§5 S1) | `15` |
| `NGINX_POLL_INTERVAL` | `1` (§5 S1) | `1` ✓ |

NGINX_SETTLE=15 also silently contradicts §5 S4: "NGINX_SETTLE below 2 s is a hard error, not a silent clamp." The script's `ConvertTo-PositiveInt` allows 0 (line 138: `-Minimum 0`), so `NGINX_SETTLE=1` would not be rejected. The plan requires the minimum to be **2** and a hard error below that.

The Makefile.ps1 `Invoke-VerifyNginx` function (lines 444–445) propagates the same wrong defaults (`"45"`, `"15"`).

**Fix:** NGINX_BURST → 120; NGINX_SETTLE → 2 with `-Minimum 2`; NGINX_POLL_ATTEMPTS → 10. Propagate the corrected defaults through Makefile.ps1.

---

### 2.5 Pass gate (S5) not implemented — CRITICAL

**File:** `scripts/verify-nginx-media-limits.ps1`
**Plan:** §5 S5

The plan's S5 "Pass gate" requires:
1. Fetch `https://localhost/`
2. Extract `src="/media/..."` values from the rendered HTML
3. De-duplicate → N
4. Re-issue **all N URLs in ONE client process** (single `curl.exe` with N URL arguments)
5. Assert every status is `200` and the `429` count is `0`
6. Report N alongside `ListingsQuery.PER_PAGE = 24` and `burst = 40`, headroom as ~1.6×

The script contains **no** thumbnails-page fetch, **no** `src` extraction, and **no** one-process re-issue. It generates synthetic URLs (`/media/seed/verify-nginx-media-limits-gate-$i.jpg`) that may not correspond to real media files.

**Fix:** Implement S5 as specified — fetch the listings page, parse media `src` URLs, re-issue in one `curl.exe` process, assert 200/N0 split.

---

### 2.6 Deny probes (S6) not implemented — CRITICAL

**File:** `scripts/verify-nginx-media-limits.ps1`
**Plan:** §5 S6

The plan's S6 requires two probes on one real key K discovered in S5:
- **Probe A** — `/media/<K>.php` → **must be `403`** (catches the inert-deny or missing-block variant)
- **Probe B** — `/media/<K>` → **must not be `403`** (catches the prefix-replacement outage that passes `nginx -t`)

Neither probe exists in the script. The script has no path-based discrimination at all.

**Fix:** Implement S6 as specified, using a real key discovered during S5.

---

### 2.7 Non-vacuity control (S7) not implemented — CRITICAL

**File:** `scripts/verify-nginx-media-limits.ps1`
**Plan:** §5 S7, AC1.2, AC1.5

The plan's S7 "Non-vacuity control" (last gate, per §5 gate order) requires:
- Issue NGINX_BURST distinct `/media/` URLs as **one client process** (`--parallel --parallel-max 40`)
- **Must yield ≥ 1 `429`**; zero 429s → **exit 1**
- Naming both likely causes: wrong hop (targeting `:8000`) or removed/altered `limit_req`

The script's "Burst probe" (lines 400–412) is nominally the non-vacuity control, but:
- It uses sequential per-URL curl (see §2.3), not one process
- It runs **before** any settle or pass-gate, violating the gate order in §5: "container state → readiness poll → settle → pass gate → deny probes → non-vacuity control"
- The non-vacuity control must be **last** because it deliberately fills the bucket

Additionally, **AC1.5** (the tripwire) requires that pointing the same script at `http://localhost:8000` must **FAIL** at the non-vacuity control. The script has no explicit wrong-hop detection — it would silently probe `:8000` if `-Url` were changed and simply report whatever 429s (or lack thereof) result.

**Fix:** Implement S7 as a distinct, last gate with one-process parallelism. Add an explicit origin check that fails fast if the URL resolves to `:8000`.

---

### 2.8 Readiness poll targets the wrong URL — MEDIUM

**File:** `scripts/verify-nginx-media-limits.ps1` (line 365, 369)
**Plan:** §5 S3

The plan S3 states the readiness poll must target `https://localhost/health/live/` and require HTTP 200. There is no unrated proxyable path, so this resolves to `location /` which carries `limit_req zone=browse_limit burst=40 nodelay`.

The script polls `$Url/media/seed/verify-nginx-media-limits-gate.jpg` (line 365) — a `/media/` URL with a synthetic key. This hits the **deny** side of the `/media/` block (not a real file, so Django returns 404, not 200), and the readiness check at line 369-371 only checks `$LASTEXITCODE -eq 0` (curl exit code), not the HTTP status code. A 404 would still satisfy `$LASTEXITCODE -eq 0`.

**Fix:** Poll `https://localhost/health/live/` and assert HTTP 200, per S3.

---

### 2.9 Log corroboration (S8) not implemented — MEDIUM

**File:** `scripts/verify-nginx-media-limits.ps1`
**Plan:** §5 S8

S8 requires that the non-vacuity control's 429s be visible in `docker compose logs nginx` by filtering `log_format main` output for `$status 429` on a `/media/` request. The script does not run `docker compose logs nginx` or filter for 429s at all.

**Fix:** Add S8 log corroboration after the non-vacuity control.

---

### 2.10 Makefile.ps1 `Invoke-VerifyNginx` does not set COMPOSE_PROJECT_NAME — LOW

**File:** `Makefile.ps1` (lines 443–456)
**Plan:** §4.1 constraint 1

The plan §4.1 states: "Follow the file's convention exactly: set `$env:COMPOSE_PROJECT_NAME = $DevProject`, read env overrides with `if ($env:X) { … } else { "default" }`, then invoke the script and propagate its exit code."

The `Invoke-Profile` function (line 236) follows this: `$env:COMPOSE_PROJECT_NAME = $DevProject`. The `Invoke-VerifyNginx` function does **not** set it. The commit message for `b6fe7d87` explains this is intentional ("no compose project name, no container") — but that is a deviation from the plan's explicit instruction.

**Fix:** Set `$env:COMPOSE_PROJECT_NAME = $DevProject` in `Invoke-VerifyNginx` per §4.1.

---

### 2.11 Commit body missing the one-process measurement — LOW

**Plan:** AC1.6, §1

The plan AC1.6 requires that the commit body contain the recorded measurements: "a per-URL `curl.exe` loop measures ≈16.8 r/s... one process with N URLs measures 242–520 r/s." The commit `51e84c50` body contains neither figure.

**Fix:** Include the measurements in a commit message, or document them in the script output.

---

## 3. Documentation problems (in `docs/ops/`)

### 3.1 Runbook (R1) missing §6.4 items — HIGH

**File:** `docs/ops/dev-nginx-media-gate.md`
**Plan:** §6.4 (12 numbered items), AC2.5

The runbook exists, opens with `## Purpose`, is English-only, and has frontmatter in the same shape as `local-https-mkcert.md`. However, it carries **none** of the following §6.4 items:

| §6.4 Item | Required content | Present in runbook? |
|---|---|---|
| **2** | Exact command with `--no-deps` fast path, explaining why `up -d nginx` alone exceeds 120s | **NO** — line 53 shows `up -d nginx` without `--no-deps`, no explanation |
| **4** | Probe targets 443, not 8000; `:8000` bypasses nginx | **NO** — no mention of port 443 vs 8000 |
| **5** | Shared `browse_limit` bucket caveat; an open dev browser tab shares the bucket | **NO** — not mentioned |
| **6** | Headroom is ~1.6×, not an order of magnitude; a second page load inside 2s exceeds it | **NO** — "headroom" absent |
| **7** | Reading evidence: `docker compose logs nginx`, NOT `docker exec … cat` (symlink to /dev/stdout) | **NO** — not mentioned |
| **9** | Troubleshooting table (exit 2, exit 1 log excerpt, 429 at control, 429 at probes, port contention, intermittent 429s) | **NO** — no troubleshooting table |
| **11** | Explicitly: do not add a dedicated access log; filter the shared log | **NO** — not mentioned |
| **12** | The CRLF trap: strip `\r` before regex | **NO** — not mentioned |

Item 1 ("What it is and what it proves... the three residuals, §9") is **partial** — the runbook's "What the gate is — and is not" table covers the gist but does not state the three residuals from §9 (CGNAT unobservable, /protected-media/ unreachable, unbounded log growth). Search for `CGNAT`, `protected-media`, `log growth`, `rotation` in the runbook returns zero matches.

Item 10 ("What is not covered... §9's three residuals, verbatim") is **NOT DONE** — the runbook has no residuals section.

**Fix:** Expand the runbook to carry all 12 §6.4 items verbatim.

---

### 3.2 Runbook describes a different implementation than the plan — HIGH

**File:** `docs/ops/dev-nginx-media-gate.md`
**Plan:** §5 (S1–S12), §5 S10

The runbook's §"Commands" and §"Exit-code contract" describe a **five-code** contract (0/1/2/3/4) and a **static conf parse** approach. This directly contradicts the plan's §5 S12 (three codes: 0/1/2) and §5 S10 (v1 must not read the conf). The runbook line 34 says the script "parses `docker/nginx/nginx.dev.conf`" — the plan forbids this in v1.

The plan's §5 gate order is: "container state → readiness poll → settle → pass gate → deny probes → non-vacuity control." The runbook has no pass gate, no deny probes, and no separate non-vacuity control.

**Fix:** Rewrite the runbook to match the plan's §5 spec, not the other way around.

---

### 3.3 C1 — `TRUSTED_PROXY_NETWORKS` comment incomplete — MEDIUM

**File:** `src/backend/config/settings/dev.py` (lines 50–56)
**Plan:** §6.1 C1, AC2.1

The plan AC2.1 requires the comment to:
1. Cite the `peer.is_private` path as the reason `()` stays correct
2. State the `get_client_ip` topology difference (real peer through nginx, `127.0.0.1` on direct :8000)

The current comment (commit `95ccf2ab`):

```python
# No extra trusted proxy networks in dev: the default dev stack publishes Django
# directly on :8000, so the peer is loopback and the gate in
# apps/core/utils/client_ip.py is already open. nginx is gated behind the opt-in
# `use-nginx` compose profile (docker-compose.dev.override.yml), so it is absent
# unless that profile is enabled; when it is, requests arrive via a proxy, but
# the value stays empty and is left to the operator to widen deliberately.
TRUSTED_PROXY_NETWORKS: tuple[str, ...] = ()
```

This does **not** cite `peer.is_private` (the `_is_trusted_peer` function at `client_ip.py:48-58` returns True when `peer.is_loopback or peer.is_private` — line 50). It does **not** state the topology difference: through nginx, `get_client_ip` returns the real client (from `X-Real-IP`/`X-Forwarded-For`); on a direct `:8000` hit, it returns `127.0.0.1` (the loopback peer, since no forwarding headers exist).

**Fix:** Amend the comment to cite `peer.is_private` explicitly and state the `get_client_ip` topology difference, per AC2.1. **Comment-only; no value change.**

---

### 3.4 Runbook references non-plan documents — LOW

**File:** `docs/ops/dev-nginx-media-gate.md` (lines 15, 28, 117)

The runbook's frontmatter `related:` list (line 15) includes `rollback` and `ops-nginx-rate-limit-gate`, and its body (lines 28, 117) links to `ops-nginx-rate-limit-gate.md`. These documents were created by the same commit (`4ecdd3b6`) but are **not** part of this plan's deliverables (§4.1 surface, §6.1). The plan's R1 deliverable is "the new runbook" — it does not mention `ops-nginx-rate-limit-gate.md` or `rollback.md`. This is not a correctness problem (the documents exist and the links resolve), but it represents scope expansion beyond the plan.

---

## 4. Acceptance criteria status

### Increment 1 (§4.3)

| AC | Status | Notes |
|---|---|---|
| AC1.1 | **PASS** | Show-Help line (line 71), `Invoke-VerifyNginx` function (line 443), switch arm (line 486) all present |
| AC1.2 | **FAIL** | Script does not fetch the thumbnails page, extract media URLs, or report a distinct-URL count or observed rate; burst probe is sequential (vacuous) |
| AC1.3 | **FAIL** | Absent → exit `3`, not `2` |
| AC1.4 | **FAIL** | Crash-loop → exit `2` (STOPPED), not `1` |
| AC1.5 | **FAIL** | No tripwire; no explicit `:8000` origin check |
| AC1.6 | **FAIL** | No recorded measurement of 16.8 / 242–520 r/s in commit body; script uses the per-URL loop the plan forbids |
| AC1.7 | **UNVERIFIED** | Exit-code propagation on PowerShell 5.1 cannot be verified in this environment |
| AC1.8 | **UNVERIFIED** | Requires git status check at commit time; all files are committed |
| AC1.9 | **PASS** (technically) | `git diff --stat -- docker/ src/` is empty for Increment 1 — the script is in `scripts/`, Makefile.ps1 in root |
| AC1.10 | **UNVERIFIED** | `.\Makefile.ps1 test` not run |

### Increment 2 (§6.3)

| AC | Status | Notes |
|---|---|---|
| AC2.1 | **FAIL** | C1 doesn't cite `peer.is_private` or state `get_client_ip` topology |
| AC2.2 | **PASS** | C2 comment conditionally states proxy under `use-nginx`, all values unchanged |
| AC2.3 | **UNVERIFIED** | Test suite not run |
| AC2.4 | **PASS** | C3 paragraph verified against `docker-compose.dev.override.yml` |
| AC2.5 | **FAIL** | Runbook missing 8 of 12 §6.4 items; residual 1 partial, residual 10 absent |
| AC2.6 | **PASS** | R2 and R3 cross-links present and resolving |
| AC2.7 | **UNVERIFIED** | ruff/basedpyright not run (comment-only changes; expected clean) |
| AC2.8 | **UNVERIFIED** | git status at commit time not re-verified |
| AC2.9 | **UNVERIFIED** | `.\Makefile.ps1 test` not run |

---

## 5. Plan spec internal consistency (no code changes needed)

The plan §6.4 item 2 states the fast path command as `up -d --no-deps web bot nginx`. This is internally consistent: `--no-deps` skips the `db → migrate → load_cities → load_catalog → seed → web` chain, and the named services `web bot nginx` are exactly what's needed for the gate. The plan's §1 claims `image: nginx:alpine` in docker-compose.yml (line 341 of the plan), but the actual file has `image: nginx:1.30.5` (pinned by `09-API-016`). This is a doc-code drift in the plan's §1 evidence, not a deliverable defect.
