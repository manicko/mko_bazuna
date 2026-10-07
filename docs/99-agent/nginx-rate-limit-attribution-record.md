---
id: nginx-rate-limit-attribution-record
domain: agent
tags:
  - nginx
  - rate-limit
  - media
  - remediation
  - record
  - decision
related:
  - rules
  - technical-specification
  - db-enums
---

## Purpose

Decision record for **B-01 of the multi-plan remediation pass**: the owner-ratified criterion that
replaces the withdrawn `crosscheck_delta` invariant in
[`.ai/plans/22-nginx-rate-limit-deployed-gate.md`](../../.ai/plans/22-nginx-rate-limit-deployed-gate.md)
(P22). It is the single citable source of truth for *what a deployed-stack `/media/` 429 measurement is
allowed to conclude*, and for *why the earlier access-vs-error equality was wrong*. The durable
behaviour itself — the script, its tests and the runbook — lives in the linked operations docs, not
here; those are named in [Where the durable behaviour is documented](#where-the-durable-behaviour-is-documented).

Conventions: a clause is **Ratified** (a human has ruled and the ruling binds), **Withdrawn** (a
previously settled clause that is no longer valid and must not be used), or **Deferred** (nobody has
ruled in this pass and nothing ships against it). A **Withdrawn** clause is not deprecated, not an
alias, and not a "legacy" reading — it does not exist.

This record is deliberately placed in `docs/99-agent/`, matching the two precedent records
[`pii-consent-remediation-record.md`](pii-consent-remediation-record.md) and
[`ad-lifecycle-remediation-record.md`](ad-lifecycle-remediation-record.md). It is **not** in
`docs/ops/`: `test_compose_contract.py::_DOCS_OPS.glob("*.md")` and
`test_docs_ci_parity.py::_docs_ops_markdown()` sweep `docs/ops/*.md` only, so a record placed there
would enter the pinned-image and doc-parity sweeps for no benefit.

## Main Concepts

| Concept | Meaning in this gate |
|---|---|
| **Django-origin 429** | A 429 emitted by `apps/ads/views/listings.py::media_gate`, which calls `rate_limited_response(json=False)` → a bare `HttpResponse(status=429)` with an **empty body**. It lands in nginx's **access** log with **no** matching `limiting requests` **error** line. |
| **nginx-origin 429** | A 429 emitted by `limit_req zone=browse_limit` on `location /media/`. It writes **both** an access line and a `limiting requests` `[error]` line. |
| **Access channel** | nginx `log_format main` lines. Sees **both** origins. `$body_bytes_sent` is the free discriminator: `0` ⇒ Django-origin, non-zero ⇒ nginx-origin candidate. |
| **Error channel** | nginx `limiting requests` `[error]` lines. Sees **nginx-origin only**. |
| **Attribution** | Splitting the access-channel `/media/` `GET` 429s into the two origins by `$body_bytes_sent`. |
| **Exposure precondition** | A key that issued **> 60** `/media/` requests in one **fixed** 60 s window. Derived from config (`RateLimitBudget.MEDIA_GATE`), not measured from traffic. |

## The criterion

The measurement counts `/media/` **`GET`** `429`s and attributes each by `$body_bytes_sent`. The
**only** soundness input is `attribution_delta`.

| Metric | Definition |
|---|---|
| `requests_media_429` | `/media/` **GET** access lines with `$status == 429`. **A finding. NEVER a soundness input.** |
| `requests_media_429_empty_body` | of those, `$body_bytes_sent == 0` ⇒ **Django-origin** |
| `requests_media_429_nonempty_body` | of those, `$body_bytes_sent != 0` ⇒ **nginx-origin candidate** |
| `error_media_limit_rejected` | `limiting requests` `[error]` lines, zone `browse_limit`, `request:` path starts `/media/`, method `GET` |
| **`attribution_delta`** | **`requests_media_429_nonempty_body` − `error_media_limit_rejected`** |
| `requests_media_other_status` | `/media/` lines with a status outside {200, 403, 404, 429} |
| `keys_over_media_budget` | distinct keys with **> 60** `/media/` requests in one **fixed** 60 s window |
| `burst_regime` | per rejecting key: share of rejections with burst width `W ≤ 1 s` vs `W > 1 s` (**diagnostic only**) |

**Only `attribution_delta` participates in a soundness check.** Every other count is a finding.

The criterion is human-ruled; the script emits **no** verdict.

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

**The one hard rule.** Use the **ONE-SIDED** test `Django-origin ⟺ $body_bytes_sent == 0`.
**PROHIBITED: writing any literal byte count anywhere** — not in the record, not in a code hint, not in
a comment, not as an "informational" note, not in a test name. The only legal byte comparison is
`== 0`. The nginx 429 body length is a property of the **pinned build's error page**, not a constant:
it changes on an nginx patch bump, on `server_tokens off`, and on `msie_padding on` (making it
User-Agent-dependent). `0`, by contrast, **is** contractual — the Django 429 has an empty body, pinned
by an existing test.

**Why one-sided strictly dominates.** Every failure mode of the one-sided rule is a **VOID** — loud and
non-reportable. A two-sided `== <literal>` rule has a **silent false-PASS** mode: the day a Django 429
gains a body, it is reclassified as nginx-origin, the error channel does not corroborate, and the run
fails open into a number nobody checked. A measurement gate's worst outcome is a confident wrong
number.

**Both channels are restricted to `GET`** (P22 option (f)): nginx returns **headers only** for a
rejected `HEAD`, so its `$body_bytes_sent == 0` would be misclassified as Django-origin and produce a
spurious VOID.

**The exposure precondition** (P22 option (g)) is config-derived and replaces the withdrawn
`at_risk_pairs` proxy. Per key per fixed 60 s window, with `R` requests and burst width `W`, nginx at
`rate=20r/s burst=40 nodelay` forwards `f = min(R, 40 + 20·W)` and rejects `max(0, R − 40 − 20·W)`;
Django at `RateLimitBudget.MEDIA_GATE` (60 / 60 s) rejects `max(0, f − 60)`. Therefore:

> **⟺ `R > 60` per key per 60 s window, at least one limiter rejects.**

The precondition is **`> 60`, not `≥ 60`** — at exactly `R = 60` neither limiter rejects; rejection
begins at 61. The window is **fixed, disjoint 60 s buckets, not sliding**: a sliding window inflates
every key's count and manufactures a vacuous PASS. The `60` is already shipped as
`RateLimitBudget.MEDIA_GATE` in `src/backend/apps/core/enums.py` — **no new constant**.

**What `attribution_delta` is allowed to be on a healthy stack: exactly 0.** And
`attribution_delta == 0` does **not** imply health — that is precisely why C1/C2 gate soundness and
C3–C5 decide.

## What VOID means

VOID is a **soundness failure of the measurement**, not a finding about the stack.

**Exactly two causes:**

- **C1 — channel integrity.** `attribution_delta != 0`: the nginx-origin candidate count does not
  match the error channel, so the two channels cannot be reconciled.
- **C2 — parse integrity.** `lines_unparsed != 0`, or the two body-bucket counts do not sum to
  `requests_media_429`.

For both: **investigate; do not report a number.**

VOID is **not**:

- "the two channel counts differ" — they are expected to differ; the access channel is a two-origin
  total and the error channel is nginx-only;
- "some `/media/` 429s exist" — a Django-origin 429 is a **C4 FAIL**, a reportable finding, never a
  VOID;
- "the run looks odd" — an unexplained impression is not a cause; only C1 and C2 void.

## Prohibited readings

1. **`crosscheck_delta` is Withdrawn, not deprecated.** It does not appear as a metric, a field, an
   alias, or a "legacy" note. It must not be reconstructed from this record.
2. **`requests_media_429` is a total across both origins** and must **never** be differenced against
   `error_media_limit_rejected`.
3. The **only** legal subtraction is `requests_media_429_nonempty_body − error_media_limit_rejected`
   (that is `attribution_delta`).
4. A non-zero **raw** difference (`requests_media_429 − error_media_limit_rejected`) is **not** a VOID
   trigger. On a healthy stack with a Django-origin 429 the raw access count legitimately **exceeds**
   the error count. That is exactly why the raw delta was invalid: it compared a two-origin total
   against a one-origin count, and so reported a difference on nothing.
5. `error_media_limit_rejected` is **nginx-only** and is never expected to equal any access-derived
   total.

## Worked examples

### Example A — healthy stack

| Metric | Value |
|---|---|
| `requests_media_429` | **0** |
| `requests_media_429_empty_body` | 0 |
| `requests_media_429_nonempty_body` | 0 |
| `error_media_limit_rejected` | 0 |
| `attribution_delta` | **0** |
| `keys_over_media_budget` | **3** |

C1 holds (`attribution_delta == 0`); C2 holds (all lines parsed, buckets sum); C3 holds
(`requests_media_429 == 0` **and** `keys_over_media_budget ≥ 1`). ⇒ **PASS.** The window was provably
exposed — three keys each exceeded 60 `/media/` requests in a fixed 60 s bucket — so zero rejections is
a positive finding, not a truncated sample. `burst_regime` is "no rejections sampled" (C6) and must be
stated.

**What the withdrawn criterion returned here:** **INCONCLUSIVE** on a provably exposed window. It
computed `requests_media_429 − error_media_limit_rejected` and, with no rejections, obtained `0` —
but its PASS branch additionally required the withdrawn `at_risk_pairs` proxy ("≥ 2 page loads of ≥ 13
tokens in 2 s" ⇒ R=26), and 26 requests in 2 s is **rejected by neither limiter**, so the proxy could
never be established over a window that this criterion proves was exposed. The measurement was sound
and the old rule could not say so.

### Example B — nginx not serving `/media/` properly

| Metric | Value |
|---|---|
| `requests_media_429` | 500 |
| `requests_media_429_empty_body` | 0 |
| `requests_media_429_nonempty_body` | **500** |
| `error_media_limit_rejected` | **0** |
| `attribution_delta` | **500 − 0 ≠ 0** |
| `keys_over_media_budget` | ≥ 1 |

C1 fails (`attribution_delta != 0`). ⇒ **VOID.** Investigate; do not report a number. Something
refused every image — a misrouted `location`, a bare `return 429`, or an error level above
`limiting requests` — without writing the error channel it should have.

**What the withdrawn criterion returned here:** a clean **`0`**. Its delta was
`requests_media_429 − error_media_limit_rejected = 500 − 500 = 0`, so it satisfied its own equality,
returned VOID **only** on disagreement, and its PASS branch had no rejection condition once the delta
was zero. It thus **permitted a PASS on a stack refusing every image.** This is the single strongest
argument against the withdrawn invariant: the raw delta is zero precisely when the thing being
measured is broken, because both terms fall together when the nginx access line for a refusal is
absent.

**Distinguishing "nginx not running at all":** with nginx down there are **no** `/media/` access lines
of any kind, so `requests_media_429 == 0` **and** `keys_over_media_budget == 0`. That is **C3′
INCONCLUSIVE** — never VOID and never PASS. This case must not be collapsed into Example B: Example B
has 500 refusals from *something*, C3′ has none.

## Options considered

| # | Option | Disposition | Sourced reason |
|---|---|---|---|
| **(a)** | compare like-with-like **after** attributing | **ADOPTED** | The two channels are not commensurable until each 429 is attributed to its origin. Attribution is free: `$body_bytes_sent == 0` separates the origins with no config edit and no production-Python edit. |
| **(b)** | demote the delta to a reported diagnostic | adopted **inside** (a) as the interpretation rule | The delta is still printed, but it is the **soundness precondition** (C1), never the verdict. A diagnostic that is allowed to void is not demoted; a diagnostic that decides is not a diagnostic. |
| **(c)** | real discriminator (`$limit_req_status`, or a header on the Django 429) | **DEFERRED** | Only option that makes a strict cross-check exact, but it touches shared config or production Python. See [Deferred successor and its trigger](#deferred-successor-and-its-trigger). |
| **(d)** | nginx-side evidence only | **REJECTED** | Strictly weaker: it discards the access channel and cannot distinguish a Django-origin 429 from an nginx one — the exact attribution the gate needs. |
| **(e)** | ordering / dominance / ratio invariant | **REJECTED as a gate** — falsified | For `W ≤ 1 s` Django is **structurally incapable** of rejecting (`f ≤ 60`); for `W > 1 s` every nginx rejection is accompanied by ≥ `20·(W−1)` Django rejections. HTTP/2 multiplexing, thumbnail count and CGNAT all move `W`, so any ratio gate is environment-dependent **by construction**. Kept only as the `burst_regime` diagnostic annotation. |
| **(f)** | restrict **both** channels to `GET` | **ADOPTED inside (a)** | nginx returns **headers only** for a rejected `HEAD`, so `$body_bytes_sent == 0` ⇒ misclassified as Django ⇒ spurious VOID. |
| **(g)** | config-derived exposure precondition | **ADOPTED, replacing `at_risk_pairs`** | The old proxy demanded "≥ 2 page loads of ≥ 13 tokens in 2 s" ⇒ R=26, but 26 requests in 2 s is rejected by neither limiter — it never established exposure. `R > 60` per key per fixed 60 s window **⟺** at least one limiter rejects, and the `60` is already shipped as `RateLimitBudget.MEDIA_GATE`. |

## Deferred successor and its trigger

`$limit_req_status` is the successor: exact, contractual, no magic numbers, available since nginx
1.17.6, image pinned at `nginx:1.30.5`, and it breaks no test. It is a **production nginx config
change** overturning P22's settled D1 ("no config edit"), for a human-ruled measurement.
**DEFERRED — do not specify it as in-pass work.**

**Trigger:** if the error channel is ever lost, or `limit_req_log_level` / `error_log` level is ever
changed such that `[error]` lines stop being written, the delta check dies. At that point
`log_format main` must gain `$limit_req_status` and the criterion collapses to the single-channel
exact form `429 AND $limit_req_status == REJECTED`, needing no second channel.

## Corrected facts

Each correction replaces a P22 claim that is false against the tree. Anchors are headings and literal
strings, never line offsets.

| # | P22 anchor | Stale claim | Corrected fact |
|---|---|---|---|
| 1 | §7 (the `media_gate` "returns exclusively 200/403/404" sentence) | `media_gate` returns exclusively 200/403/404 | It **also** returns 429 — `rate_limited_response(json=False)` → a bare `HttpResponse(status=429)` with an empty body under `/media/<path:image_key>`. Separately, a Django-origin **400** carrying a large HTML body was observed on `/media/` in the shipped dev stack; stated **descriptively**, it is never a threshold or comparison. |
| 2 | §7 / §7.1 (`listings.py` ×2) | `listings.py` carries ×2 429 emitters | **×3**: `ad_detail`, `media_gate`, `listings`. Tree-wide there are **8 call sites in 5 files**. |
| 3 | §7.1 (`_location_block` "exactly two anchors") | `_location_block` has exactly **two** anchors | **Three**: `= /metrics` (×4), `location /health/ {` (×1), `/protected-media/` (×1). The correct mechanism is that `_iter_location_blocks` uses anchored `re.match(r"\s*location\b", line)`, so a `#` comment can never match — `/media/` is **not** shadowable. |
| 4 | §9.1 (`len(zones) == 3`) | `len(zones) == 3` | **`== 4`** — 09-API-015 added the `csp_report_limit` zone. |
| 5 | §9.1 ("raise burst 40 → 80/100, no test change") | Raising burst changes no test | **REFUTED** — blocked by the byte-exact `test_media_location_carries_browse_limit_burst_40`. |
| 6 | §9.1 ("`$limit_req_status` is redundant") | `$limit_req_status` is redundant | **REFUTED** — the two channels are precisely what distinguishes the origins; a single-channel status field is the deferred successor, not a redundancy. |
| 7 | §9.3 residual 4 / AC1.4 ("STATIC [and holds]") | The static attribution argument holds | **REFUTED** by `5ffad37e` (09-API-005): a Django 429 now lives under `/media/`, which the withdrawn argument's premise excluded. |
| 8 | §1 (`docs/ops/rollback.md` `--env-file .env.staging` citation) | Staging uses `.env.staging` | That file now uses `--env-file .env.prod` and states there is **no** `.env.staging` and **no** `docker-compose.staging.yml`. The stale citation is struck; §1's **conclusion** (staging would not help) stands. |
| 9 | §5.2 (the error-line shape) | The error line carries a `burst:` token | It is `limiting requests, excess: <n> by zone "<zone>"` — **no `burst:` token** — at `error` level. `limit_req_log_level` defaults to `error` and is absent from both confs; `error` is more severe than the configured `warn`, so the line **is** written. `error_log_level` is absent tree-wide and no `location`-level `error_log` override exists. |
| 10 | §5.2 / §6.1 (the stream model) | The two streams can be read together | Access and error go to different files symlinked to `/dev/stdout` and `/dev/stderr`, so ONE capture carries both — but they are **independent Docker streams**. Error blocks arrive **detached** from their access lines and one connection emits many rejection lines: **count independently and sum; never zip, never pair by adjacency.** |
| 11 | §5.3 / §6.3 (log growth) | Rotation may bound the capture | `LogConfig=json-file map[]` — no `max-size`, no `max-file`, no rotation anywhere. |

## Verify, do not assume

The B-02 Implementor must re-verify each item at implementation time; inheriting it is how a gate
fails silently.

| # | What to check | What a wrong answer costs |
|---|---|---|
| 1 | `python3` on the VPS host — **still UNVERIFIED** | If absent, the aggregator cannot run; the `awk` fallback (P22 §6.2 step 1b) is the mitigation, and it must be complete enough to produce a verdict-eligible summary unaided. |
| 2 | That the capture is **production, not dev** — `CACHES['default']['BACKEND']` must be `django_redis.cache.RedisCache` | Dev's `LocMemCache` with `workers = 3` and `max_requests = 1000` **systematically under-reports** Django rejections and can **fabricate a false PASS**. |
| 3 | That the captured log matches `log_format main` field-for-field, with `$body_bytes_sent` immediately after `$status` | If a field is missing or reordered, the body-bucket attribution silently mis-assigns every 429 and the delta becomes meaningless. |
| 4 | That `[error]` lines are still written under the **deployed** conf's `error_log` level | A wrong answer kills the whole delta check and fires the (c) trigger — the deferred successor must be specified instead. |
| 5 | That `$time_local` renders bracketed and space-separated | Positional splitting is **unsafe**; a whitespace split silently mis-assigns `$body_bytes_sent`. Use a field-aware parse. |
| 6 | That both streams reach one capture with the same field set | If the error stream is sourced differently, the two channels are not comparable and C1 is unfalsifiable. |
| 7 | That the `/media/` limiter is keyed on client IP (`$binary_remote_addr`), commensurable with the access log's `$remote_addr` | If it were keyed on the authenticated user, the access 429s would not be countable per nginx key and the attribution would be wrong. |
| 8 | That no response header exists today which a discriminator could key on | If one does, the deferred (c) is already partly free and should be re-evaluated rather than inherited as "forbidden". |

The same list is summarised in P22 §10's Gate order.

## Where the durable behaviour is documented

- **The criterion and its corrections:** `.ai/plans/22-nginx-rate-limit-deployed-gate.md` (this record
  is cited from §5.4).
- **The aggregator script and its tests:** `scripts/measure-nginx-rate-limit-keys.py` and its unit
  tests — **B-02** (shipped).
- **The measurement runbook:** `docs/ops/ops-nginx-rate-limit-gate.md` — **B-05** (shipped).
- **The shipped budget constant:** `RateLimitBudget.MEDIA_GATE` in `src/backend/apps/core/enums.py`.
- **The shipped 429 shapes:** `apps/core/utils/rate_limit_response.py`.
- **The pinned `/media/` directive:** `test_media_location_carries_browse_limit_burst_40` in
  `src/backend/tests/test_nginx_config.py`.
