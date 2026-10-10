---
id: dev-nginx-media-gate
domain: ops
tags:
  - nginx
  - rate-limit
  - media
  - development
  - verification
  - operations
related:
  - docker-deployment
  - local-https-mkcert
  - rollback
  - ops-nginx-rate-limit-gate
---

## Purpose

Runbook for the **development** nginx `/media/` rate-limit verification gate:
`scripts/verify-nginx-media-limits.ps1`, invoked host-side as
`.\Makefile.ps1 verify-nginx`. The gate confirms that the dev nginx is
**present, running, and enforcing** the `/media/` limit documented in
[`docker-deployment.md`](docker-deployment.md#rate-limiting); it does not change anything and it
never starts the container.

The **deployed-stack** measurement is a different, human-run procedure — see
[`ops-nginx-rate-limit-gate.md`](ops-nginx-rate-limit-gate.md).

## What the gate is — and is not

| The gate **is** | The gate is **not** |
|---|---|
| A read-only PowerShell 7+ script that parses `docker/nginx/nginx.dev.conf` and, only when the container is already running, exercises the burst and settle behaviour against `https://localhost`. | A remediator. It edits no conf, compose file, `.env`, or database row. |
| A reporter. It exits with a distinct code per outcome and leaves the decision to a human. | A launcher. It **never** runs `docker compose up`, `start`, or `run`; bringing nginx up is an operator action. |
| Scoped to the `mko-bazuna-dev` compose project, so unrelated projects' containers are never observed. | A production check. It cannot see the production stack (see [When this gate is wrong](#when-this-gate-is-wrong)). |

## Prerequisite — starting nginx is an operator action

The dev `nginx` service is gated behind the opt-in `use-nginx` compose profile in
`docker-compose.dev.override.yml`. Without the profile, the gate reports the container as
**ABSENT** and exits `3`; it will not start it for you.

TLS certificates must exist before the container will serve on `:443`. Certificates are
gitignored (`docker/nginx/certs/*.pem`, with `.gitkeep` excepted), so they are generated locally —
follow [`local-https-mkcert.md`](local-https-mkcert.md).

## Commands

Start nginx (operator action; requires certificates and the `use-nginx` profile):

```powershell
docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx up -d nginx
```

Run the gate (host-side; no compose project name, no container):

```powershell
.\Makefile.ps1 verify-nginx
```

Teardown when finished:

```powershell
docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --profile use-nginx down
```

## Exit-code contract

`.\Makefile.ps1 verify-nginx` propagates the script's exit code verbatim.

| Code | Name | Meaning | What a human does |
|---|---|---|---|
| `0` | PASS | Container running; static parse consistent; both probes behaved as documented. | None. The dev `/media/` limit is enforcing. |
| `1` | CONFIG | The static parse failed, or the `/media/` block / four-zone census is not as documented. The conf is invalid. | Inspect `docker/nginx/nginx.dev.conf` against the `### Rate Limiting` table. Fix the conf, then re-run. |
| `2` | STOPPED | The nginx container exists in the dev project but is not running. Its stopped exit code is reported. | Start it (the `up -d nginx` command above), then re-run. The gate will not start it. |
| `3` | ABSENT | No nginx container exists in the dev project. | Bring the stack up with the `use-nginx` profile (operator action), then re-run. |
| `4` | PROBE FAIL | Container running and conf consistent, but a live probe did not behave as documented (limit not enforcing, or a probe could not be attributed). | Investigate before trusting the gate; see the 429 caveat below. |

## Environment overrides

Each override uses the project idiom `$x = if ($env:X) { $env:X } else { "default" }`; the effective
value is printed at the top of every run.

| Variable | Default | Effect |
|---|---|---|
  | `NGINX_BURST` | `45` | Concurrent `/media/` requests sent by the burst probe. Documented burst is `40`, so the extra 5 must overshoot it while the total stays under the application window of `240`. |
| `NGINX_SETTLE` | `15` | Seconds to wait for the nginx leaky bucket to drain before the settle probe. |
| `NGINX_POLL_ATTEMPTS` | `15` | Readiness poll attempts before giving up. |
| `NGINX_POLL_INTERVAL` | `1` | Seconds between readiness poll attempts. |

## 🔴 The 429-ambiguity caveat

On the dev stack `/media/` is limited **twice**, and **both limiters return HTTP 429**, so a bare
429 is ambiguous:

| Limiter | Where | Behaviour |
|---|---|---|
| nginx `browse_limit` | `location /media/` in `docker/nginx/nginx.dev.conf` | `burst=40 nodelay` at `20 r/s` |
| Application `RateLimitBudget.MEDIA_GATE` | `apps/ads/views/listings.py::media_gate` | `240 requests / 60 s` |

The burst probe keeps its total **strictly below `240`** for exactly this reason: any 429 it observes
is then attributable to nginx's `burst=40` rejection and not to the application limiter. **Do not
raise `NGINX_BURST` to or above `240`** — the probe loses its attribution and the gate becomes unable
to tell the two 429 sources apart.

## Scope limit — the production configuration is a permanent deferral

Plan 21 BLOCK 4 is a **PERMANENT DEFERRAL**: this gate changes nothing about the production `/media/`
configuration. Production limiting lives in `docker/nginx/nginx.conf`; this runbook and its script are
**dev-only** and make no claim about the deployed stack.

## When this gate is wrong

- It **cannot observe the production stack** — it parses the dev conf and probes `https://localhost`.
- It says **nothing** about the deployed rate-limit behaviour; that requires
  [`ops-nginx-rate-limit-gate.md`](ops-nginx-rate-limit-gate.md) and a human-run measurement window.
- It is **dev-only**: a PASS here is a statement about the local dev configuration, not about
  production.
- Its live burst/settle probes require an operator to have started the container; without that they
  are not exercised at all (the gate reports STOPPED or ABSENT instead).
