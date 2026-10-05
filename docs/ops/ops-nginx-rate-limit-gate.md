---
id: ops-nginx-rate-limit-gate
domain: ops
tags:
  - nginx
  - rate-limit
  - media
  - measurement
  - operations
related:
  - docker-deployment
  - dev-nginx-media-gate
  - rollback
  - architecture
---

## Purpose

Runbook for the **deployed-stack** `/media/` rate-limit measurement gate (P22): capturing the
production nginx logs and aggregating them with `scripts/measure-nginx-rate-limit-keys.py` into a
count-only report. A **human** applies the criterion and rules.

The criterion is **not stated here**. It is authoritative and lives in
[`../99-agent/nginx-rate-limit-attribution-record.md`](../99-agent/nginx-rate-limit-attribution-record.md);
this runbook links to it and must never restate or vary it. The script **emits no verdict** — it
prints counts only, and a human applies the decision table.

The **dev** equivalent is a different, automated gate —
[`dev-nginx-media-gate.md`](dev-nginx-media-gate.md).

## Step 0 — environment precheck

Before capturing anything, record all three of the following. A wrong answer here invalidates the
whole run.

| Check | What it must be | Why |
|---|---|---|
| Compose project | The **production** project | The capture must be the production stack, not a dev or test stack. |
| nginx image tag | `nginx:1.30.5` | The pinned build's error-page body length is a property of the tag; the criterion depends on the pinned build. |
| `CACHES['default']['BACKEND']` | `django_redis.cache.RedisCache` | Dev's `LocMemCache` with `workers = 3` and `max_requests = 1000` **systematically under-reports** Django-origin rejections, which can **fabricate a false PASS**. If the cache backend is not Redis, the run is void. |

Also confirm `command -v python3` on the host. **This is still unverified** — if `python3` is absent,
the aggregator cannot run and a complete enough fallback summary must be produced another way.

## The harvest — one capture carrying both streams

Access and error logs are separate Docker streams but reach one capture together. Error blocks
arrive **detached** from their access lines, so count the two channels independently and sum them;
never zip or pair by adjacency.

```bash
# The prod override file name is held in a variable on purpose: the docs/ops
# compose-invocation parity guard keys on the literal `docker-compose.prod.yml`
# token in the same logical line as `docker compose`, and this runbook is not in
# its static manifest. Keep the flags correct whichever way the name is spelled.
PROD_COMPOSE=docker-compose.prod.yml
docker compose --env-file .env.prod -f docker-compose.yml -f "$PROD_COMPOSE" logs --no-color --since <t0> --until <t1> nginx > capture.log
```

Pick `<t0>` and `<t1>` to cover a window in which the expected traffic was actually driven. The
window must be long enough for at least one client key to exceed the exposure precondition.

## The aggregation — stdin only

The script reads the capture on **stdin** and writes a deterministic text + JSON report on
**stdout**. It takes no arguments and **emits no verdict**.

```bash
python3 scripts/measure-nginx-rate-limit-keys.py < capture.log
```

A human then applies the criterion C1–C6 to the printed counts.

## The criterion — C1–C6

The decision table is reproduced, **without variation**, from the authoritative record. If this
runbook and the record ever disagree, **the record wins**.

| ID | Condition | Outcome if true |
|---|---|---|
| **C1 — channel integrity** | `attribution_delta == 0` | **VOID** if false. Investigate; do not report a number. |
| **C2 — parse integrity** | `lines_unparsed == 0` **and** `requests_media_429_nonempty_body + requests_media_429_empty_body == requests_media_429` | **VOID** if false. |
| **C3 — the gate** | `requests_media_429 == 0` **and** `keys_over_media_budget ≥ 1` | **PASS** |
| **C3′ — too narrow** | `requests_media_429 == 0` **and** `keys_over_media_budget == 0` | **INCONCLUSIVE — not a pass.** Widen the window, never the verdict. |
| **C4** | `requests_media_429_empty_body > 0` | **FAIL (Django-origin)** — a reportable finding, explicitly NOT a VOID |
| **C5** | `requests_media_429_nonempty_body > 0` | **FAIL (nginx-origin)** if ≥1 fell in a same-key burst with `W ≤ 1 s`; otherwise report as isolated candidates |
| **C6** | `burst_regime` present and stated | A human must record it; a run is not reportable without the regime it sampled |

**Authoritative source — read it before ruling:**
[`../99-agent/nginx-rate-limit-attribution-record.md`](../99-agent/nginx-rate-limit-attribution-record.md).
That record defines every metric, the one-sided `$body_bytes_sent == 0` attribution rule, and the
worked examples. **Do not restate or vary the criterion from memory.**

## What a VOID is — and is not

A VOID is a **soundness failure of the measurement**, not a finding about the stack.

- It is caused by exactly two things: **C1** (`attribution_delta != 0`, the two channels cannot be
  reconciled) or **C2** (parse integrity failed).
- On a VOID: **investigate; do not report a number.**
- A VOID is **not** "the two channel counts differ" (they are expected to differ — one channel sees
  both 429 origins, the other sees nginx-origin only), **not** "some `/media/` 429s exist" (a
  Django-origin 429 is a C4 FAIL, a reportable finding), and **not** "the run looks odd".

## Escalation trigger — the deferred `$limit_req_status` successor

The criterion is measured across two channels. If the **error channel is ever lost**, or
`limit_req_log_level` / `error_log` level is ever changed such that `[error]` lines stop being
written, the delta check dies. At that point `log_format main` must gain `$limit_req_status` and the
criterion collapses to the single-channel exact form `429 AND $limit_req_status == REJECTED`, needing
no second channel. That successor is **DEFERRED** — it is a production nginx config change and is
**not** specified as in-pass work.

## 🔴 BLOCK 9 is a PERMANENT deferral

The **actual deployed-stack measurement** requires a human-run window on the VPS and a human ruling.
Plan 22 BLOCK 9 is a **PERMANENT DEFERRAL** — **no code can close it**. This runbook gives a human
the capture and aggregation procedure; it does not and cannot perform the measurement, and its
existence must not be read as though the production path is already covered.

## GDPR discipline

The aggregator emits **counts only**. A key, IP, referer, or user-agent value must **never** be
retained — not in the report, not in a saved file, not in a ticket. Aggregation happens in memory;
nothing is written to disk by the script. Delete the raw `capture.log` once counts are recorded.

## Log growth — no rotation is configured

`LogConfig=json-file map[]` carries **no `max-size` and no `max-file`**: there is **no log rotation
anywhere**. The capture grows unbounded until it is deleted, and the container's log can grow the
same way between captures. Bound the capture window deliberately and clean up promptly; do not
assume a rotation policy exists to cap it for you.
