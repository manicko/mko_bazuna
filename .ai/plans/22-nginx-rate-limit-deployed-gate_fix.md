# BLOCK 9 deployed-stack rate-limit gate — verification plan

**Status:** ready to execute (WI-1…WI-4); BLOCK 9 stays BLOCKED until a human runs the gate · **Numbering:** 22 · **Created:** 2026-10-04
**Criterion source:** the §5.4 attribution criterion is ruled in **B-01** of `.ai/plans/26-multi-plan-remediation-execution.md` and recorded in [`docs/99-agent/nginx-rate-limit-attribution-record.md`](../docs/99-agent/nginx-rate-limit-attribution-record.md). `crosscheck_delta` is **withdrawn**.
**Decision owner:** coordinator. D1–D5 and C-1/C-2 below are **settled and binding**; an Implementor records them and does not re-open them.
**Citation rule:** every task target is a **semantic unit** — a file, a module, a function, a heading, a directive. `file:line` appears **only** as evidence for a finding, never as a target.

---

## 1. Purpose and the owner's ruling

BLOCK 9 (`77c1653`, *fix(nginx): deny script execution under /media and rate-limit the media path*) shipped a `limit_req zone=browse_limit burst=40 nodelay` on `location /media/` in **both** `docker/nginx/nginx.conf` and `docker/nginx/nginx.dev.conf`.

**The owner's ruling: BLOCK 9 remains BLOCKED until verified on a deployed stack. It must not be closed on dev evidence.** Its outstanding step is recorded in exactly one place — commit `77c1653`, body item 9 — and that record is wrong (§4 WI-3).

**Dependency:** `77c1653` is a hard precondition in the only sense that matters: the gate has nothing to measure until the `/media/` `location` block exists. This plan adds **no** behaviour to either conf, **no** application change, and **no** dependency on any other block.

**Relationship to plan 21 (`.ai/plans/21-nginx-dev-media-gate.md`):** **not replaced, not superseded.** Plan 21 covers *dev observability* — running the dormant nginx container and asserting a zero-429 page load locally. Its §7 residual 1 states verbatim that *"BLOCK 9's original deployed gate is therefore NOT replaced by this plan; it remains mandatory and outstanding."* That sentence is binding on this plan and is not to be softened. Plan 21's non-vacuity figures **do not reproduce** (it recorded 242–520 r/s / `429×32`; a later measurement of 120 requests at 7.4 r/s produced **zero** 429s), so **no number from plan 21 is inherited here**.

**No staging exists.** `docs/ops/rollback.md` §5 documents a staging *procedure*, but there is **no** `.env.staging` and **no** `docker-compose.staging.yml` — that doc now uses `--env-file .env.prod` throughout and states there is no `.env.staging`, and `.github/workflows/deploy.yml` has one job with `environment: production`. Staging is *specified but unprovisioned* and would not help even if provisioned: CGNAT is a property of the audience's access network, occurring **before** the packet reaches the VPS, and nginx is the first hop. A staging box on the same VPS would see the same aggregation **if real users visited it** — and nobody does.

---

## 2. Why dev cannot close this

**A dev probe is a single key, so it can only ever produce N = 1 — which is the case dev already characterises.** That is the whole reason. Not "dev happens to observe one `$remote_addr`": that phrasing is an *accident of probe origin*, is falsifiable in five minutes (a second probe source inside the `web` container on the same bridge yields a second key), and would collapse the moment anyone tried. The irreducible fact is structural: **one probe origin is one key by construction**, and N = 1 is precisely the case already measured and characterised on dev.

Multi-source probing would make this *worse*, not better: it would demonstrate **per-key isolation** — the **opposite** property from the one under test.

**The repo cannot settle whether aggregation occurs.** There is no `set_real_ip_from` and no `real_ip_header` anywhere, so nginx is the **first hop** — no CDN, no upstream LB (`deploy.yml` uses `SERVER_HOST` / `SERVER_PORT` / `SERVER_USER` / `SERVER_SSH_KEY` / `SERVER_FINGERPRINT` straight to the VPS). Therefore whether distinct users share a `$binary_remote_addr` is decided by **the audience's ISP**, and the repo positively shows the **server side contributes none**.

**Consequently the gate's irreducible purpose is not "confirm the limiter fires."** Dev proves that (and plan 21 proves it non-vacuously). The purpose is to **measure production key cardinality (N) and per-key request rate** — quantities that exist only where real traffic does.

---

## 3. What the gate measures

Two quantities: **N** (distinct `$remote_addr` cardinality, reported as a distribution, never as a bare count) and **per-key request rate** (1-second sub-buckets).

### 3.1 Capacity is invariant in N; N multiplies DEMAND

Per-key capacity is fixed by the shipped config: **20 r/s sustained + a 40-token burst draining in 2 s**. N does not change capacity; it multiplies demand.

Demand per key `= N · p · T`, where `T = 1 + images` (the `1` is the page HTML — **same bucket**, `browse_limit` is shared with `location /`). Sustainable iff `N · p · T ≤ 20`, so:

> **N_max = 20 / (p · T)**

| Browsing style | `p` | `T` | `d` (r/s) | `N_max` |
|---|---|---|---|---|
| Casual desktop, above-the-fold | 1/8 s | 7 | 0.9 | ≈ 23 |
| Active desktop, full scroll | 1/4 s | 25 | 6.2 | ≈ 3.2 |
| Aggressive mobile, fast click | 1/2 s | 25 | 12.5 | ≈ 1.6 |

**`p` and `T` are [ASSUMPTION] A2.** `loading="lazy"` on the listings template (`src/backend/templates/ads/partials/ad_list.html`) makes `T` viewport- and scroll-dependent. **The structure is sourced; the magnitudes are illustrative.** No criterion may rest on these numbers.

### 3.2 Break-even N = 2

Measured single-key capacity from empty is **41–48** — report the **band**, never a point value (one measurement recorded 41, a later one ≈48; a criterion must not rest on a single figure). Break-even concurrent page views: `T=25` → ≈1.8 (**the 2nd view loses images**); `T=13` → ≈3.5; `T=7` → ≈6.5.

**Break-even N = 2** — two concurrent page views on one key inside the ~2 s burst-drain window. Precisely: the **first** view from a cold key never loses images (25 ≤ 40). **The failure unit is a PAIR, not a crowd.** N as a population count has **no threshold**; it only sets the *probability* that such a pair occurs.

### 3.3 The sharpest consequence — and it is NOT a CGNAT finding

At `d ≈ 12.5 r/s` a **single** aggressive user already consumes **62 % of the entire 20 r/s bucket**. **The shipped configuration has a latent burst-collision problem at N = 1.** CGNAT raises the probability that a collision occurs; **it does not create the mechanism.** Any report that attributes this finding to CGNAT has misread it.

### 3.4 N is an output, never an input

Realistic N is **[ASSUMPTION] A3 and NOT SOURCED. Do not invent a number.** This plan carries N as a **measured output with a stated bias** (see WI-1's bias note), never as an input assumption to any decision.

---

## 4. Work items

Each item lists semantic-unit surface only, then binding constraints, then acceptance criteria.

### WI-1 — aggregator script (the core deliverable)

**Surface**

| Unit | Kind | Action |
|---|---|---|
| `scripts/measure-nginx-rate-limit-keys.py` | **new file** | Create. Precedent: the stdlib-only scripts already in `scripts/` (`generate_po.py`, `consolidate_migrations.py`, `profile_search.py`, `download_seed_photos.py`, `run-profile.sh`). |
| `src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py` | **new file** | Unit tests against a committed fixture log. Precedent for loading a `scripts/` module by path: `test_download_seed_photos.py`, which uses `importlib.util.spec_from_file_location` on a repo-root script. |
| a fixture log under that test module | **new file** | A small, hand-written, **synthetic** capture: known key set, known `/media/` 429 count, matching error lines, and one deliberate **cross-check mismatch** case. Contains **no** real IP — RFC 5737 / RFC 3849 documentation addresses only. |

**Binding constraints**

1. **Python 3, stdlib only.** No `uv add`, no image rebuild, no venv sync on production.
2. **`.py`, never `.ps1`.** A `.ps1` is the precedent for *developer-workstation* tooling (`scripts/github-actions-logs.ps1`); this runs on a Linux VPS.
3. **Container-side is IMPOSSIBLE, not merely unchosen.** `docker/Dockerfile`'s runtime stage copies only `/app/src`, `pyproject.toml`, `uv.lock`, `staticfiles`, `gunicorn.conf.py` and `docker/entrypoint*.sh` — **`scripts/` is not in the production image** — and it cannot be piped in via `exec -T` because stdin already carries the log stream. **Host-side is forced.** The VPS has the repo checked out at `/app` (`deploy.yml`, the deploy script's `cd /app`).
4. **Input is STDIN.** The captured window is piped in. The script **never touches the filesystem**, which is also what makes it trivially testable.
5. **Output is deterministic text + JSON.** Same input → byte-identical output.
6. **The script emits NO pass/fail, and no branch word.** No `PASS`, `FAIL`, `OK`, `VERDICT`. It reports; a human rules (§6).
7. Small single-purpose functions, **no class** (project rule 15).
8. English only; no bare `print()` for anything but the report body (rule 12's intent is logging — here the script's stdout **is** its product, which the runbook records as the deliberate exception).

**Acceptance criteria**

| ID | Criterion |
|---|---|
| AC1.1 | Script exists, imports only stdlib, and runs to completion on a fixture piped to stdin with **exit 0**. |
| AC1.2 | Output contains every metric named in §5 and **no** raw IP, User-Agent or Referer string — assert this mechanically over the fixture. |
| AC1.3 | Output contains **no** `PASS` / `FAIL` / `VERDICT` token (tripwire: the string must be absent from both the text and the JSON). |
| AC1.4 | Feeding a fixture whose channels do not reconcile (`attribution_delta != 0`) yields the runbook's **VOID** wording — and the script still exits 0, because VOID is a human call. The fixture must also cover a `$body_bytes_sent == 0` Django-origin 429 (a **C4 FAIL**, not a VOID). |
| AC1.5 | Determinism: two runs on the same fixture produce identical bytes. |
| AC1.6 | Unit tests cover `parse_access_line`, `parse_error_line`, `histogram` bucket edges (1–5, 6–24, 25–48, >48), `peak_seconds` at the 1-second sub-bucket, `attribute_media_429` on empty vs non-empty bodies, `keys_over_media_budget` at the `R > 60` boundary, and `burst_regime`. |
| AC1.7 | `uv run ruff check scripts/measure-nginx-rate-limit-keys.py <test path>` clean; `basedpyright` reports no new error. |
| AC1.8 | `\.\Makefile.ps1 test` result recorded. Proportional gate: the targeted path is the gate; the full suite is mandatory only if a shared path was touched. |

### WI-2 — the runbook

**Surface:** `docs/ops/ops-nginx-rate-limit-gate.md` (**new file**). **Not** an appended section of `docs/ops/docker-deployment.md` — that file is 1524 lines, past the `docs/00-overview/doc-maintenance-rules.md` threshold of 1000, and adding to it worsens a live violation. Frontmatter and an opening `## Purpose` heading, mirroring `docs/ops/local-https-mkcert.md`.

**Binding constraints**

1. Carries **every** item in §6. The command in §6.2 is quoted **verbatim**.
2. English only; tables for structured data (doc rule).
3. States plainly what the gate **does not** prove (§9 residuals).
4. Must carry the **correction-of-record** for `77c1653` (WI-3), because git history is immutable and a written correction is the only durable form available.
5. Must state **why the two channels exist** (§7) — the access channel sees both origins and the error channel corroborates the nginx-origin subset only; attribution is what the gate needs, and a new status/origin under `/media/` is caught by C4/`requests_media_other_status` rather than silently voiding a premise.
6. Explicit-path staging only. Never `git add -A`, `.`, or a directory.

**Acceptance criteria**

| ID | Criterion |
|---|---|
| AC2.1 | File exists, opens with `## Purpose`, is English only, frontmatter consistent with `docs/ops/local-https-mkcert.md`, and carries every §6 item. |
| AC2.2 | The `python3` precheck is **step 1** and the `awk`/`grep`/`sort`/`uniq` fallback is present and complete enough to produce a verdict-eligible summary unaided. |
| AC2.3 | The four-branch criterion appears verbatim, with **INCONCLUSIVE explicitly labelled "not a pass."** |
| AC2.4 | The plumbing probe is **labelled** as measuring the operator and carries an explicit "never enters the verdict" instruction. |
| AC2.5 | `docs/ops/docker-deployment.md` and `docs/ops/rollback.md` each gain exactly one cross-link line, and neither file's other content is altered. |

### WI-3 — correct `77c1653` body item 9

Item 9 is **false on two counts**:
- it claims *"the dev project runs no nginx container"* — one exists in `docker-compose.yml`, gated by `profiles: ["use-nginx"]` in `docker-compose.dev.override.yml`. It is **dormant, not absent**;
- its instruction (*"serve a 24-thumbnail listing page in a deployed stack and assert zero 429s"*) **cannot produce the evidence it demands**, because a page served to the operator is a **single key** — the same category error, in the one place the outstanding step is recorded.

**Surface:** the `## Correction of record` section inside `docs/ops/ops-nginx-rate-limit-gate.md` (WI-2's file). **No git-history operation.** Amending or rewriting `77c1653` is forbidden and unsafe.

**Binding constraints**
1. Quote item 9, then state both falsehoods with evidence, then point at this plan as the operative procedure.
2. Do **not** restate the "24-thumbnail page, zero 429s" instruction as a *deployed* check — restate it as the **plumbing probe** it can legitimately be (§6.4).
3. Keep the correction short. Its purpose is to stop the next reader inheriting the error, not to re-litigate it.

**Acceptance criteria**

| ID | Criterion |
|---|---|
| AC3.1 | The correction names both falsehoods and cites the evidence (the `use-nginx` profile block; the N = 1 argument). |
| AC3.2 | The commit is **byte-identical** afterwards: `git show 77c1653 --stat` unchanged. |
| AC3.3 | No follow-up commit whose message implies `77c1653` was rewritten. |

### WI-4 — fix the `docs/ops/docker-deployment.md` cross-reference defect

**Defect:** the `### Rate Limiting` section points `[Client IP Trust Model](#client-ip-trust-model)` from a sentence describing nginx's `$binary_remote_addr` **zone key**. That anchor documents **Django's** `client_ip.py` peer-trust derivation — a gate that **cannot influence the nginx key**.

**Surface:** `docs/ops/docker-deployment.md` → the `### Rate Limiting` heading (the paragraph that begins *"Three `limit_req_zone`s are declared in `http{}`…"*), plus one added cross-link line to WI-2's runbook.

**Binding constraints**
1. **Prose only.** The rate-limiting table, the `N`/`N` figures, and the "**one shared per-IP bucket, not three separate budgets**" claim are all **currently true** and must remain byte-identical. §9's remediation table explains why that claim is a live constraint on a future change.
2. Remove or re-aim the misleading anchor; do not add a second anchor to a heading that already exists. A duplicated `#client-ip-trust-model` target would make the link ambiguous.
3. Add **one** line stating that a verification procedure now exists and naming the runbook. The repo currently documents the rate limit and **no verification procedure anywhere** — that absence is what this plan ends.
4. This file is shared and has a history of concurrent edits by other phases. **Re-read immediately before editing**; on conflict, **stop and report**. Never a wholesale rewrite. Never stage another agent's edits.

**Acceptance criteria**

| ID | Criterion |
|---|---|
| AC4.1 | The `[Client IP Trust Model]` link is gone from the zone-key sentence, or is re-aimed at a heading that genuinely describes the nginx key. |
| AC4.2 | The rate-limiting table and the shared-bucket sentence are byte-identical to their pre-edit state. |
| AC4.3 | The new cross-link resolves to the runbook by heading; exactly one line added, nothing else changed. |
| AC4.4 | `git diff --stat` for this path shows one file, and its hunk count matches the two intended edits. |

---

## 5. Aggregator spec

`scripts/measure-nginx-rate-limit-keys.py` — **Python 3, stdlib only**, reads **stdin**, writes deterministic **text + JSON** to stdout, **emits no verdict**.

### 5.1 Routine shape (small single-purpose functions, no class)

```
parse_access_line(line)   -> AccessEvent | None
parse_error_line(line)    -> LimitEvent  | None
bucket_by_key(events)     -> {key: [events]}
histogram(counts, edges)  -> {bucket: n}
peak_seconds(key, events, 1)      -> {second: count}
attribute_media_429(events)       -> (empty_body, nonempty_body)
keys_over_media_budget(events, window=60s, budget=60) -> count
render(text, json)        -> stdout
```

### 5.2 Channel parsing

- **Access channel** — `log_format main` in both confs emits `$remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent" "$http_x_forwarded_for"`. The script needs `$remote_addr` (the key), `$time_local` (timestamp), the request path (first token of `$request`), `$status`, `$body_bytes_sent` (the origin discriminator), and `$http_user_agent` (for the advisory co-occurrence figure).
- **Origin attribution** — a `/media/` 429 with `$body_bytes_sent == 0` is **Django-origin**; non-zero is an **nginx-origin candidate**. Both channels are restricted to **`GET`**.
- **Error channel** — `limiting requests, excess: <n> by zone "<zone>"` — **no `burst:` token** — at **`error`** level, e.g. `… request: "<METHOD> <URI> <PROTO>"`. `limit_req_log_level` defaults to `error` and is absent from both confs; `error` is more severe than the confs' `warn`, so the line **is** written (`error_log_level` is absent tree-wide and no `location`-level `error_log` override exists). The `request:` field carries the full URI, so the error log alone is a complete nginx-only rejection channel: key, URI, zone, excess, timestamp.
- **Two independent Docker streams.** Access and error go to different files symlinked to `/dev/stdout` and `/dev/stderr`, so ONE capture carries both — but they are **independent streams**. Error blocks arrive **detached** from their access lines and one connection emits many rejection lines: **count independently and sum; never zip, never pair by adjacency.**
- Lines that match neither shape are counted as `lines_unparsed` and surfaced — a non-zero value is a signal (C2), never silently dropped.
- **Strip `\r`** before any match. Captures taken through Windows tooling arrive CRLF; a `$`-anchored match over them is a silent no-op.
- **`$time_local` renders bracketed and space-separated**, so positional splitting is unsafe — parse fields, never split on whitespace by position.

### 5.3 Metrics to compute

| Metric | Meaning |
|---|---|
| `keys_total` | Distinct `$remote_addr` in the window. **Reported with its bias**: a low-traffic key is indistinguishable from an absent one, so `keys_total` is a **lower bound** on the audience. |
| `requests_total` | All access lines in the window. The denominator. |
| `requests_media` | Access lines whose request path begins `/media/`. |
| `requests_media_429` | `/media/` **GET** access lines with `$status == 429`. **A finding. NEVER a soundness input.** |
| `requests_media_429_empty_body` | of those, `$body_bytes_sent == 0` ⇒ **Django-origin**. |
| `requests_media_429_nonempty_body` | of those, `$body_bytes_sent != 0` ⇒ **nginx-origin candidate**. |
| `error_media_limit_rejected` | `limiting requests` `[error]` lines, zone `browse_limit`, `request:` path starts `/media/`, method `GET`. **nginx-only.** |
| `attribution_delta` | `requests_media_429_nonempty_body` − `error_media_limit_rejected`. **The ONLY soundness input** (§5.4 C1). |
| `requests_media_other_status` | `/media/` lines with a status outside {200, 403, 404, 429}. A finding. |
| `keys_rejected` | Distinct keys with ≥1 `/media/` 429. |
| key-size histogram | Distinct keys bucketed by their `/media/` request count: **1–5, 6–24, 25–48, >48**. The **upper tail** is the artefact, not a bare distinct-IP count. |
| `peak_seconds(key, events, 1)` | **1-second sub-bucket**, because `rate=20r/s` is defined per second, so the peak-second count is the comparable quantity. |
| `keys_over_media_budget` | distinct keys with **> 60** `/media/` requests in one **fixed** 60 s window. The exposure precondition (§5.4); derived from `RateLimitBudget.MEDIA_GATE`. |
| `burst_regime` | per rejecting key: share of rejections with burst width `W ≤ 1 s` vs `W > 1 s`. **Diagnostic only (C6).** |
| UA co-occurrence | `keys_total` **vs** the count of distinct (`$remote_addr`, User-Agent) pairs — an **upper bound on humans per key**. **Advisory only, never asserted**: a rotating UA and a shared household browser are indistinguishable here. |

### 5.4 The criterion — attribution, and what VOID means

The load-bearing mechanism is **attribution**, not equality. Count `/media/` **GET** 429s; those with
`$body_bytes_sent == 0` are **Django-origin**, the rest are **nginx-origin candidates**.
**`attribution_delta == 0` is a soundness precondition, not a verdict.**

| ID | Condition | Outcome if true |
|---|---|---|
| **C1 — channel integrity** | `attribution_delta == 0` | **VOID** if false. Investigate; do not report a number. |
| **C2 — parse integrity** | `lines_unparsed == 0` **and** `requests_media_429_nonempty_body + requests_media_429_empty_body == requests_media_429` | **VOID** if false. |
| **C3 — the gate** | `requests_media_429 == 0` **and** `keys_over_media_budget ≥ 1` | **PASS** |
| **C3′ — too narrow** | `requests_media_429 == 0` **and** `keys_over_media_budget == 0` | **INCONCLUSIVE — not a pass.** Widen the window, never the verdict. |
| **C4** | `requests_media_429_empty_body > 0` | **FAIL (Django-origin)** — a reportable finding, explicitly NOT a VOID |
| **C5** | `requests_media_429_nonempty_body > 0` | **FAIL (nginx-origin)** if ≥1 fell in a same-key burst with `W ≤ 1 s`; otherwise report as isolated candidates |
| **C6** | `burst_regime` present and stated | A human must record it; a run is not reportable without the regime it sampled |

**One sentence:** count `/media/` `GET` 429s; those with `$body_bytes_sent == 0` are Django's, the rest
are nginx's candidates; `attribution_delta == 0` is a **soundness precondition, not a verdict**; PASS
requires zero rejections of either origin over a window where at least one key exceeded 60 `/media/`
requests in a fixed 60 s window.

**`crosscheck_delta` is WITHDRAWN** — the access-vs-error equality is invalid and must not be
reconstructed. It compared a two-origin total against a one-origin count, and its raw delta is zero
precisely when the thing being measured is broken. Full rationale, the withdrawn reading, worked
examples and the deferred successor: **[`docs/99-agent/nginx-rate-limit-attribution-record.md`](../docs/99-agent/nginx-rate-limit-attribution-record.md)**
(the criterion's source of record, **B-01**).

**The one hard rule.** Use the ONE-SIDED test `Django-origin ⟺ $body_bytes_sent == 0`. Writing any
literal byte count anywhere is **PROHIBITED**; the only legal byte comparison is `== 0`. The nginx body
length is a property of the pinned build's error page and drifts on upgrade, `server_tokens off`, and
`msie_padding on`; `0` is contractual. One-sided strictly dominates: its every failure mode is a loud
VOID, whereas a two-sided literal has a silent false-PASS mode.

**Both channels are restricted to `GET`** (nginx returns headers only for a rejected `HEAD`, whose
`$body_bytes_sent == 0` would be misclassified as Django). **The exposure precondition is
config-derived** (replacing `at_risk_pairs`): `R > 60` per key per **fixed** 60 s window, which is
`⟺` at least one limiter rejects. The `60` is already `RateLimitBudget.MEDIA_GATE` — **no new
constant** — and the window is fixed disjoint 60 s buckets, never sliding.

**What `attribution_delta` is allowed to be on a healthy stack: exactly 0** — and `attribution_delta ==
0` does **not** imply health. That is why C1/C2 gate soundness and C3–C5 decide.

**First-run instruction:** verify that rejected requests actually appear in the access log at all
before the criterion leans on the channel counts. If they do not, the access log is not the primary
channel on this deployment and the run is **VOID** (C2), not PASS.

### 5.5 The hard rule

**The script emits no verdict.** It computes and renders. Which branch a run falls into is a human ruling (§6.5), because two of the four branches turn on judgements the script is not entitled to make: whether the window was long enough to have seen the tail, and whether a rejected image was above the fold.

---

## 6. Runbook

### 6.1 Harvest — one command, both streams

Nginx symlinks **both** logs to stdio (`/dev/stdout` and `/dev/stderr`), so a single host command returns access and error in one capture. They are **independent Docker streams**: error blocks arrive detached from their access lines, so count each independently and sum; never pair by adjacency. (The nginx image is pinned at `nginx:1.30.5`; `nginx:alpine` is the rollback value only.)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  logs --no-color --since <T-start> --until <T-end> nginx
```

**`docker exec … cat /var/log/nginx/access.log` cannot work** and must not be attempted: the path is a symlink to `/dev/stdout` and the container runs `read_only: true`. There is no file in the container to read.

### 6.2 Step 1 — `python3` precheck

```bash
command -v python3 || echo "NO python3 — use the awk fallback in step 1b"
```

**[ASSUMPTION] A1: `python3` on the VPS host is UNVERIFIED** — nothing in the repo invokes a host interpreter. This precheck is the mitigation. **1b — `awk`/`grep`/`sort`/`uniq` fallback:** documented in full, and complete enough to produce a verdict-eligible summary unaided (key count, `/media/` request count, `/media/` 429 count, empty- vs non-empty-body split, error-line `/media/` count, `attribution_delta`, `keys_over_media_budget`). `awk` is dpkg-required and marginally safer.

### 6.3 Window selection — explicitly HUMAN

- **≥ 7 consecutive days standing** — 2 weekends; a classifieds audience is strongly diurnal.
- **Retrospective, not scheduled.** No compose file declares a `logging:` block ⇒ `json-file` with **no rotation** ⇒ **any past window is recoverable**. The check is a **query over existing logs**: no coordination, no user impact, no maintenance window, and repeatable as a trend. This is the single largest operational simplification available.
- **Record the timezone in the artefact** [ASSUMPTION] A5. A diurnal peak measured against the wrong offset is a peak in the wrong hour.
- Ad-hoc windows for incident triage; the same script, a narrower `--since`/`--until`.

**Window selection is NOT automatable.** Which window is representative is a judgement about the business.

### 6.4 Plumbing probe — labelled, excluded from the verdict

A synthetic burst is **worthless as evidence for this gate**: an operator is a single key, so it reproduces N = 1 only — the very case §2 excludes.

**But it is not worthless as a plumbing check.** It answers two real questions: *is the production nginx config actually loaded, with the `/media/` `limit_req` present?* and *is 429 live?* Keep it. **Label it explicitly as measuring the operator.** **Never let its numbers enter the verdict.**

### 6.5 The criterion — behavioural, no magic numbers

| Branch | Condition |
|---|---|
| **PASS** | `requests_media_429 == 0` over a window where **`keys_over_media_budget ≥ 1`** (a key exceeded 60 `/media/` requests in a fixed 60 s window), with **`attribution_delta == 0`** (soundness, C1) and **`lines_unparsed == 0`** (C2). *Zero rejections of either origin over a provably exposed window is a positive finding.* |
| **INCONCLUSIVE — not a pass** | `requests_media_429 == 0` but **`keys_over_media_budget == 0`** (C3′). The window was too narrow to have seen the tail. **Remedy: widen the window, never the verdict.** |
| **FAIL** | Any `/media/` 429 (C4/C5). **Django-origin** (`$body_bytes_sent == 0`) is a reportable finding, explicitly NOT a VOID. **nginx-origin** is a FAIL if ≥1 fell inside a same-key burst of `W ≤ 1 s`; otherwise report as isolated candidates. |
| **VOID** | **C1** (`attribution_delta != 0`) or **C2** (`lines_unparsed != 0`, or the body buckets do not sum). **Investigate; do not report a number.** |

**RESERVED TO A HUMAN: whether the FAIL-branch rejections were VISIBLE above the fold.** A rejected visible thumbnail is a broken page; a rejected `loading="lazy"` image 3000 px down is **no user-visible harm at all**. The script reports **how many** rejections fell inside a ≥13-token burst versus how many were isolated or below-fold — and **does not choose between them**.

**Also not automatable:** whether a given 429 *rate* is a defect. 0.5 % versus 5 % is interpretable only against N, per-key rate, and decisively the above-fold distinction. **Zero `keys_over_media_budget` is inconclusive, and the remedy is a wider window, never a widened verdict.**

---

## 7. Evidence channel — attribution, not a cross-check equality

**Two channels, two origins — the access channel sees both; the error channel sees nginx only.** The
access log has the denominator and the full 429 population; `$body_bytes_sent` attributes each 429 to
its origin for free. The error log corroborates the nginx-origin subset alone and is empty when nothing
is rejected. `apps/ads/views/listings.py::media_gate` calls `rate_limited_response(json=False)` → a bare
`HttpResponse(status=429)` with an empty body under `/media/<path:image_key>`; it lands in the access
log with **no** matching `limiting requests` error line. A Django-origin **400** carrying a large HTML
body was also observed on `/media/` in the shipped dev stack — stated here **descriptively**, never as a
threshold or comparison.

**ACCESS log PRIMARY; error log corroborating.** The brief had this inverted, and the inversion is load-bearing: **the error log is empty when nothing is rejected.** On the healthy outcome — the one the owner most needs confirmed — it yields **zero data points and cannot produce a passing result**; it can only ever produce a failure. The access log has the denominator; via a `/media/` path filter it has an exact numerator.

**A 429 on a `/media/` URI is not provably nginx's.** `media_gate` is reachable at `/media/<key>` and returns **200 / 403 / 404 / 429** — its 429 is `rate_limited_response(json=False)`, a bare empty-body `HttpResponse(status=429)` that writes **no** error line. A Django-origin **400** with a large HTML body was also observed on `/media/` in the shipped dev stack, stated **descriptively** only. Every other Django-side 429 emitter is elsewhere: `apps/ads/views/listings.py` (×3 — `ad_detail`, `media_gate`, `listings`), `apps/core/views.py` (`/privacy/`), `apps/users/views/consent.py` (`/login/issue/`), `apps/search/views/search.py` (`/search/`), `apps/search/views/autocomplete.py` (`/api/search/autocomplete`) — **8 call sites in 5 files** tree-wide. `limit_req_status 429` sits at `http{}` level. **Therefore `$limit_req_status` is NOT redundant** — the two channels are precisely what distinguishes the origins (§5.4).

**Attribution replaces it for free** (§5.4): `$body_bytes_sent == 0` is already in `log_format main`.

### 7.1 The plan-21 conflict does NOT arise

D1 resolves to **no config edit**, so `log_format` is never touched and plan 21's N1 is never invoked. **Record why the question stays closed:**

- `_location_block` in `src/backend/tests/test_nginx_config.py` has exactly **three** anchors in the whole tree — `"= /metrics"` (×4), `"location /health/ {"` (×1) and `"/protected-media/"` (×1);
- the `/media/` assertions use `_iter_location_blocks`, which uses anchored `re.match(r"\s*location\b", line)`, so a `#` comment can never match and `/media/` is **not** shadowable;
- **no** test pins `log_format`;
- `test_nginx_config.py` is the only test file that reads either conf.

**If anyone later wants `$limit_req_status` anyway: a production redeploy of two confs for zero information gain — recommend refusing it.**

---

## 8. GDPR — the artefact must contain NO raw IPs

The access log holds client IPs, User-Agents and Referers — **personal data under GDPR**. Committing IPs makes them **permanent in git history**. **Truncating to `/24` is inadequate** (weak on IPv4, meaningless on IPv6).

**Aggregate on the host; bring back only the summary.** Per-key listings stay on-host and are discarded. **This is a second, independent reason the aggregator must be host-side** (§WI-1 constraint 3): the data never needs to leave the machine that already has it.

---

## 9. Out of scope, risks, residuals, assumptions

### 9.1 NO REMEDIATION IS PLANNED NOW

Every candidate changes shipped config, and §3 shows the right lever depends on **which regime binds** — which is exactly what the measurement determines. Recorded for later, each with its cost:

| Option | Verdict |
|---|---|
| Per-location `media_limit` zone for `/media/` | **The candidate** if the rate-bound regime binds. Breaks `test_media_location_is_rate_limited`'s `len(zones) == 4` positive equality and invalidates the currently-**true** "one shared per-IP bucket" doc claim. +10 MiB shared memory. **Separate BLOCK.** |
| Raise `burst` 40 → 80/100 | **REFUTED — blocked.** The byte-exact `test_media_location_carries_browse_limit_burst_40` pins `limit_req zone=browse_limit burst=40 nodelay;` in both confs, so the change cannot land without editing a contractual test. Even setting that aside, it widens the **shared** bucket's burst for `/` and `/moderation/` too — a **flood-mitigation regression** — and treats the symptom when `rate` may bind. |
| `limit_req_dry_run` | **REJECT, for a sourced reason:** `media_gate` runs an `AdImage.objects.filter(...).exists()` — **a DB query per image request**. Un-throttling converts 429s into **DB load**, not a fix. |
| Keyed zones (add `$http_user_agent`) | **REJECT:** UA is spoofable, so a client rotates it to multiply its own budget — **weakens a security control to help honest users**. More memory per state. |
| `$limit_req_status` in `log_format main` | **DEFERRED, not redundant.** The two channels are precisely what distinguishes the origins (§5.4); a single-channel status field is the named successor and needs a production redeploy (out of pass). See [`docs/99-agent/nginx-rate-limit-attribution-record.md`](../docs/99-agent/nginx-rate-limit-attribution-record.md). |

### 9.2 Risks

| ID | Risk | Class | Likelihood | Impact | Mitigation | Residual |
|---|---|---|---|---|---|---|
| R1 | `python3` absent on the VPS → the aggregator cannot run | Environment | **Unknown (A1)** | High — the gate stalls | `command -v python3` as runbook **step 1**; complete `awk`/`grep`/`sort`/`uniq` fallback (1b) | Low |
| R2 | Channel reconciliation fails (`attribution_delta != 0`) → a number is reported that does not describe reality | Correctness | Medium | High — a false PASS or a false FAIL | **VOID** branch (C1/C2); do not report a number | Very low |
| R3 | Rejected requests absent from the access log → the primary channel silently misses rejections | Correctness | Low (A4) | High — false PASS | Explicit first-run instruction (§5.4); a zero-429 access count with a non-zero error count is **VOID** | Very low |
| R4 | The plumbing probe's numbers leak into the verdict, reproducing the N = 1 category error in the one place it is forbidden | Correctness | Medium | High — a vacuous "deployed" PASS | §6.4 labels it and excludes it; the criterion requires an **at-risk pair**, which a single-key probe structurally cannot produce | Very low |
| R5 | A future Django view under `/media/` returns a **new** status or origin → the attribution argument fails **silently** | Correctness | Low | High — attribution becomes meaningless | `requests_media_other_status` and C4 **detect** it; §7 and WI-2 constraint 5 state *why* the channels exist | Low |
| R6 | An ad-hoc too-narrow window yields zero `keys_over_media_budget` and is read as a pass | Correctness | **High** if the criterion is read loosely | High | **INCONCLUSIVE is explicitly not a pass**; remedy is a wider window | Low |
| R7 | Raw IPs reach the artefact or git history | **Compliance** | Low | **High — personal data, irreversible** | §8; aggregate on host; AC1.2 asserts mechanically | Very low |
| R8 | A staging environment is provisioned to "fix" this | Scope | Low | Medium — cost with no evidentiary gain | §1: staging is *specified but unprovisioned* and **would not help even if it existed** (CGNAT precedes the VPS; nobody would visit it) | Very low |

### 9.3 Irreducible residuals — state these, do not fix them

1. **N is an audience property and cannot be sourced from the repo.** Whether users share a `$binary_remote_addr` is decided by their ISP.
2. **The access log cannot distinguish above-the-fold from below-the-fold rejections.** Browser-side data would be needed — a **separate BLOCK**.
3. **Unbounded log growth.** Pre-existing, no compose file declares `logging:`. It is also *what makes windows recoverable* (§6.3) — the residual and the mechanism are the same fact.
4. **The `/media/` attribution argument is NOT static — it has already failed once.** `5ffad37e` (09-API-005) added a Django 429 under `/media/`, which the withdrawn "no Django 429 under `/media/`" premise excluded. The current criterion is true on a healthy stack **because it attributes**, not because the premise holds. A future Django view under `/media/` returning a new status is caught by `requests_media_other_status` and by C4 — not by a silent voiding.
5. **Realistic N stays unknown until measured.** Carried as an output with a stated lower-bound bias (§5.3), never as an input.

### 9.4 Assumption table

| ID | Assumption | Status | Consequence if wrong |
|---|---|---|---|
| **A1** | `python3` exists on the VPS host | **UNVERIFIED** — nothing in the repo invokes a host interpreter | Runbook step 1 catches it; `awk` fallback (1b) is the mitigation |
| **A2** | Realistic `p` and `T` | **[ASSUMPTION]** — `loading="lazy"` makes `T` viewport-dependent; §3 table magnitudes are illustrative | The `N_max` *structure* holds; only the numbers move. **No criterion rests on them.** |
| **A3** | CGNAT prevalence in the audience's ISP mix | **NOT SOURCED — do not invent a number** | §3.3 stands regardless: the N = 1 collision is **not** a CGNAT finding |
| **A4** | Rejected requests appear in the access log | **[ASSUMPTION]** — verified only on dev | First-run instruction (§5.4); an absence is a **VOID** (C2), never a pass |
| **A5** | Timezone / diurnal alignment | **[ASSUMPTION]** — must be **recorded** in the artefact | A peak lands in the wrong hour; widening the window is the remedy |

### 9.5 Plan-21 items flagged, NOT actioned (its surface, not this plan's)

1. **Plan 21's S7 non-vacuity control does not reproduce** (recorded 242–520 r/s / `429×32`; a later 120-request run at 7.4 r/s produced **zero** 429s, so S7's "≥ 1 429 else exit 1" would **fail on a healthy stack**). The fix is **not** to tune `NGINX_BURST`: assert only "≥ 1 rejection observed", treat zero as **inconclusive-plumbing rather than hard-fail**, and assert on the **nginx-side log** rather than curl's exit codes (the `-o NUL` / `--parallel-max 100` non-determinism was **client-side** — the requests never arrived). **Listed for plan 21's owner; not actioned here.**
2. **`77c1653` item 9 is false on two counts** — WI-3 corrects it in writing. No history operation.
3. **The `docker-deployment.md` anchor defect** — WI-4 fixes it. Also flagged to plan 21, whose OQ-3 touches the same file's rate-limiting section; **coordinate before either edit lands.**

---

## 10. Sequencing

```
WI-1  scripts/measure-nginx-rate-limit-keys.py
      + fixture log + unit tests          ──┐  independent
WI-2  docs/ops/ops-nginx-rate-limit-gate.md ─┤  (WI-2 quotes WI-1's
        incl. WI-3 correction of record     │   interface, so WI-1 fixes
                                             │   the signature first)
WI-4  docs/ops/docker-deployment.md  ───────┘  ONE editor only — WI-2 and
                                                 WI-4 both touch ops docs;
                                                 WI-4's cross-link resolves to
                                                 WI-2, so WI-2 lands first
```

**Doable NOW — none of it touches production:**
1. **WI-1** — the aggregator plus unit tests against a synthetic fixture log. Includes the not-reconciling fixture that proves the C1 VOID path works, the Django-origin 429 fixture for C4, and the no-verdict tripwire (AC1.3).
2. **WI-2** — the runbook, quoting the command verbatim.
3. **WI-3** — the correction of record, inside WI-2's file.
4. **WI-4** — the doc fix, after WI-2 lands and coordinated with plan 21's OQ-3.

**IRREDUCIBLY WAITING:**
- **A production window** and the human who selects it (§6.3). Not a code dependency — a data dependency.
- **The `python3` precheck** outcome on the real VPS (A1), which decides aggregator vs `awk` fallback.
- **The human ruling**, by design. The script emits no verdict; the FAIL branch's above-the-fold judgement is reserved; "is this 429 rate a defect" is reserved; and INCONCLUSIVE must never be widened into a pass.

**Gate order:** WI-1 must be **proven against a fixture log** before anyone points it at production. A first production run is **VOID** until the first-run access-log check (§5.4) has been done on that deployment. The eight **verify, do not assume** items behind the criterion — `python3` on the host (A1); that the capture is production, not dev (`CACHES['default']['BACKEND']` must be `django_redis.cache.RedisCache`, or dev's `LocMemCache` fabricates a false PASS); that the log matches `log_format main` with `$body_bytes_sent` right after `$status`; that `[error]` lines are still written under the deployed `error_log` level; that `$time_local` renders bracketed and space-separated; that both streams reach one capture with the same field set; that the `/media/` limiter is IP-keyed; and that no discriminator header exists today — are enumerated with their cost-if-wrong in [`docs/99-agent/nginx-rate-limit-attribution-record.md`](../docs/99-agent/nginx-rate-limit-attribution-record.md).

**BLOCK 9 stays BLOCKED** until a human records PASS or FAIL against §6.5 for a real window. Nothing in this plan closes it.