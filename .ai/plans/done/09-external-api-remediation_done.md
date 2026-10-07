---
plan_id: "09-external-api-remediation"
phase: "09"
phase_name: "External Integrations & API"
source_report: ".ai/audit/99-validation/09-external-api-validated-findings.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "6413df5"
report_anchor_commit: "aa2a6b0"
status: "planned"
findings_in_scope: 26
blocks: 16
---

# Execution Plan — Phase 09 Remediation (External Integrations & API)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/09-external-api-validated-findings.md` (validated, 1735 lines) — the **only** surviving phase-09 source |
| Source findings file | `.ai/audit/09-external-api/findings.md` — **deleted from the working tree** (tracked deletion). Recorded for traceability only; **not** an input |
| Report anchor commit | `aa2a6b0` |
| Code-context document | `.ai/tmp/code-context-phase09.md` (729 lines, Auditor) |
| **Working anchor commit for this plan** | **`6413df5`** (`git rev-parse --short HEAD`, taken before writing). HEAD drifts because other agents commit concurrently; it was `aa2a6b0` when the code context was produced. **The tree is the authority** |
| Date | 2026-09-29 |
| Items in scope | 26 — **17 `API-` + 6 `VAL-` (validated) + 3 `VAL-` (this Planner)** |
| Validated severity split (17 `API-`) | 0 CRITICAL · 4 HIGH (`API-001`, `API-002`, `API-003`, `API-004`) · 8 MEDIUM · 5 LOW |
| State at `6413df5` | **0 already fixed · 15 still open · 2 partial** (`API-002` — under-scoped; `API-007` — part (b) rejected) · **0 rejected** |
| State of the 6 `VAL-` findings | **5 still valid** as process constraints · **1 (`VAL-002`) is an unowned open product defect** needing a destination |
| Execution blocks | 16 — **15 implementation, 1 decision/handoff** (BLOCK 13 ships no production behaviour) |
| Implementor concurrency | 1, strictly sequential (project rule: only one implementor at a time) |

**Naming convention.** This plan cites its own items with the **cycle-scoped prefix
`09-API-nnn` / `09-VAL-nnn`**, following the convention phase 03 established
(`.ai/plans/03-db-concurrency-remediation.md` §0.5) and phase 08 adopted. The bare IDs
`API-`, `VAL-`, `EXT-`, `AUT-` and `SRH-` all collide with **hard-coded in-source markers**
from prior audit cycles (§5.3). **Any tracker must key on `09-API-nnn`, never on the bare ID.**

**Anchor discipline (`09-VAL-003`).** Every line-number anchor in the source report and in
the code context is **advisory**. Re-resolve every target by **symbol name** at
implementation time. This plan never cites a line number as a task target.

### 0.2 Evidence basis — read this before executing any block

Two inputs plus this Planner's own tree read. They do not fully agree. **Where the report
or the code context disagrees with the tree, the tree wins and the correction is listed
here.** Four of these corrections send an Implementor working from the report's file or
symbol list to **code that does not exist** or to **a wrong mental model of the exposure**.

#### 0.2.1 Corrections — statements the **tree contradicts**

| # | Report / code-context statement | **Tree at `6413df5` says** | Consequence for this plan |
|---|---|---|---|
| **C-1** | The only `send_mail` consumer is `support_delivery_email.deliver_support_ticket_email` | **That symbol does not exist.** The function is **`send_support_notification_email`** (`src/telegram_bot/services/support_delivery_email.py`), with `_send_mail` as the `@sync_to_async` wrapper. It is the **authority** on the correct name (`src/telegram_bot/tests/test_support_delivery_email.py`) | BLOCK 9's file surface names the real symbol. An Implementor grepping for `deliver_support_ticket_email` finds nothing and must not "create" it |
| **C-2** | The consumer logs `"Support email delivery failed (continuing)"` | **That string is absent.** The real line is `logger.exception("Failed to send support email for ticket %s", ticket.ticket_ref)`. The behaviour the report describes (fail-open) is real; the quote is from an older revision | No test may assert the quoted string. BLOCK 9 asserts **behaviour** (the call does not raise) |
| **C-3** | `docker-compose.yml:240-243,283-286` carry explicit `BOT_TOKEN:` lines on `web` / `bot` | **No such lines exist.** `docker-compose.yml` has exactly **three** explicit `BOT_TOKEN: ${BOT_TOKEN}` lines (one-shots); `docker-compose.prod.yml` has **none at all**. The real distribution is `env_file:` plus the `./.env.*:/app/src/.env:ro` bind mount on **eight** Django services, and `settings/base.py::read_env` loads that file into `os.environ` at import | **Removing the three explicit lines is a no-op.** BLOCK 14 attacks the `env_file` pattern and the `prod.py` guard, not the compose lines |
| **C-4** | `/metrics` is "reachable from every sibling container on the Docker network" because only nginx's `allow 127.0.0.1; deny all;` protects it | **Probably inverted.** A Docker-bridge peer has a `172.x` source address, which `allow 127.0.0.1` does not match, so `deny all` **rejects** it. The **real, confirmed** exposure is dev: `docker-compose.dev.override.yml` publishes `"8000:8000"` on `web`, and `config/urls.py` mounts `django_prometheus.urls` at the **root**, so `/metrics` is unauthenticated in Django | The hardening item stands; the **impact model in any runbook must be re-derived** (Q3). BLOCK 11 gates the Django-side gate on a verification step, not on the report's sentence |
| **C-5** | `backfill_translations.py:97-102,163-180,221-231`; `asyncio.run(run_backfill(qs))`; no `--limit`/batching/progress | The file is **124 lines**, is **synchronous**, and declares `--batch-size` (default 100) driving `iterator(chunk_size=…)`. Selection is `Ad.objects.filter(title_en__isnull=True) \| Ad.objects.filter(title_bs__isnull=True)`. Only `--batch-size` exists; there is **no** `--limit` | The validator's split is upheld. BLOCK 8 adds `--limit` as a **pure addition** and touches no `asyncio` machinery |
| **C-6** | The false ECB claim is at `docs/ops/migration-workflow.md:353-354` | The sentence now spans **`:367-368`**: *"`load_cities` reads `cities.json`; `load_exchange_rates` makes HTTP calls to ECB."* | BLOCK 5 corrects by **anchor phrase**, not by line |
| **C-7** | `gunicorn.conf.py:18,27` are `timeout` / `graceful_timeout` | Confirmed by name: `timeout = 60` (`:22`), `graceful_timeout = 30` (`:31`). **The report missed `preload_app = True` (`:44`)**, which is decisive for API-013: with preloading, an import-time shutdown hook lands in the **gunicorn master**, not in the forked workers that hold the in-flight sends | BLOCK 7's hook design is **gated on Q7** and must be registered worker-side |
| **C-8** | `IMMEDIATE_ALERTS_ENABLED=false` appears in "all three `.env.*.example` files" | **Four**: `.env.example`, `.env.dev.example`, `.env.prod.example`, `.env.test.example` | No action; recorded so a coverage check does not miss one |
| **C-9** | The alert `Bot` in `immediate_alerts.py` is an active web-tier use | **Latent**: `deliver_immediate_alerts` is gated by `IMMEDIATE_ALERTS_ENABLED`, default `False`, `false` in all four templates. The scheduler-tier `Bot` in `send_alerts.py::_send_user_digests` **is** live and unconditional | Two of three `Bot` construction sites are active, not three. BLOCK 14's blast-radius argument uses the corrected count |
| **C-10** | `except ConnectionInterrupted, redis.RedisError:` in `apps/categories/signals.py` is a defect | **Valid Python 3.14** (PEP 758 unparenthesised except groups) — the file parses cleanly and `uv run ruff check src/` is **green** at `6413df5` | **Do not "fix" it.** Recorded so an Implementor working through the cache-failure policy does not introduce a SyntaxError |

#### 0.2.2 Load-bearing claims this Planner re-verified directly in the tree at `6413df5`

| Claim | Verification (symbol-anchored) |
|---|---|
| **API-001** open, and wider than filed | `apps/core/services/site_config.py::get_site_name` / `::get_bot_username` still execute `get_cached_site_config()` / `get_cached_bot_username()` **before** the `try`. Both docstrings still promise a fallback *"if the DB **or cache** is unavailable"*. `apps/core/utils/cache.py::get_cached_site_config` / `::get_cached_bot_username` are bare `return cache.get(key)` with **no** exception handling. `CACHES` in `config/settings/base.py` sets **no** `IGNORE_EXCEPTIONS` |
| **`09-VAL-007` (Planner)** — the write half is also unguarded | `set_cached_site_config(name)` / `set_cached_bot_username(username)` are **inside** the same `try`. A Redis **write** failure therefore returns `"Bazuna"` / `"bazuna_bot"` even though the ORM read **succeeded**, and the `logger.warning` says *"SiteConfig unavailable"* — a false diagnostic. **Unreported by the Auditor and the validator** |
| **API-002** open, and **seven** request-path guards, not four | Four in `telegram_bot/services/rate_limit.py` (`check_login_rate_limit`, `check_contact_start_rate_limit`, `check_support_message_rate_limit`, `check_upload_rate_limit`) and **three more on the web tier**: `apps/core/services/contact_rate_limit.py::check_deep_link_render_rate_limit` (used by `apps/ads/views/listings.py::listings`), `apps/search/services/rate_limit.py::rate_limit_check`, `apps/users/services/login_rate_limit.py::login_rate_limit_check` (used by `POST /login/issue/`). All seven wrap `cache.add` + `cache.incr` in **`except ValueError` only** |
| **`09-VAL-008` (Planner)** — the version-bump class is **four**, not three, and two of its callers are unguarded | `except ValueError`-only bump helpers: `apps/categories/cache.py::bump_tree_version`, `apps/categories/services/lookup_resolution.py::bump_lookup_resolve_version`, `apps/lookups/services/cache_service.py::bump_lookup_version`, `apps/search/services/cache.py::bump_search_version`. Of their receivers, only `apps/categories/signals.py::invalidate_on_lookup_item_change` catches `(ConnectionInterrupted, redis.RedisError)`; `bump_tree_version_on_structure_change` and `invalidate_category_lookup_cache` do **not**. These are the **invalidation** path, not the **guard** path — recorded, and **deliberately not** in `09-API-002`'s scope (§6.3) |
| **`09-VAL-008` (Planner)** — `apps/core/utils/cache.py` has **fifteen** call-shaped helpers, not ten | Five getter/setter/invalidate triads: `criteria`, `site_config`, `bot_username`, `support_contacts`, `anon_language`. The shared home for the cache-failure contract is a **real** home, not a new module |
| **API-003** open | `telegram_bot/handlers/contact.py::handle_contact_start` routes `contact_us` → `::handle_contact_us_start` (which calls `check_contact_start_rate_limit`) and `contact_<ad_id>` → `::handle_contact`, which contains **no limiter call of any kind**. `CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")` is a dense integer space |
| **API-004** open, all three sub-defects verbatim | `telegram_bot/retry.py::retry_transient`: `delay = float(exc.retry_after) if getattr(exc, "retry_after", None) else _BACKOFF_BASE` with **no ceiling**, slept before every one of `_MAX_RETRIES = 3` attempts; body opens `if not isinstance(exc, TelegramRetryAfter): return False`; ends `return True`. `telegram_bot/main.py::configure_dispatcher` registers `dp.errors(ExceptionTypeFilter(TelegramRetryAfter))(retry_transient)` and `main()` calls `dp.run_polling(bot)` with no arguments |
| **API-005** open, and the dev config is thinner | `docker/nginx/nginx.conf` declares exactly three zones (`login_limit` 10r/s, `search_limit` 20r/s, `browse_limit` 20r/s) and `location /media/` carries **no** `limit_req`. `docker/nginx/nginx.dev.conf` declares the same three and additionally has **no** `/health/`, **no** `/csp-report/` and **no** `= /metrics` block. Zones are per-`http`-context, so a new zone must be declared in **each** file |
| **API-006** open, both senders | `apps/search/services/immediate_alerts.py::build_alert_message` (`f"<b>{title}</b>"`, `f"📍 {city_name}"`, `f'<a href="…">{label}</a>'`) and `::Command._format_digest` in `apps/search/management/commands/send_alerts.py` (`f"• {ad.get_title(locale)[:50}…"`). `parse_mode="HTML"` appears at `immediate_alerts.py` (two sends: initial and retry) and at `send_alerts.py` (two sends). Neither module imports an escaping helper |
| **API-007(a)** open | `apps/core/services/translation.py::translate_text` returns the unmodified source on every failure path; `apps/ads/management/commands/backfill_translations.py::_translate_for_backfill` returns it verbatim; `::Command.handle` writes it into `title_en` / `title_bs` unconditionally; the selection query is nullability-derived. The row therefore never matches again |
| **API-008** open, plus a second false claim | `apps/currencies/management/commands/load_exchange_rates.py::Command.handle` still calls `ExchangeRate.objects.update_or_create(currency=…, defaults={…})` in a loop over `INITIAL_RATES`; the module docstring says *"Idempotent via `update_or_create` keyed on `currency`"*. `apps/currencies/services/price_normalizer.py::invalidate_rate_cache` is implemented and has **zero call sites**, and the **same module's docstring** claims *"The cache is invalidated when a rate is updated (admin/recompute path)"* — a **second** false capability claim next to the runbook's |
| **API-009** open | `config/settings/prod.py` carries the `EMAIL_HOST` fail-fast guard with the comment *"transactional emails (password resets, alert notifications, seller confirmations) are deliverable"*. `send_mail` has exactly one call site (`send_support_notification_email`); `set_password` has exactly one (`create_admin_user`); there is no `PasswordResetView`, `PasswordResetForm`, `token_generator` or password-reset URL/template anywhere under `src/` |
| **API-010** / **API-014** / **API-015** open in both configs | `nginx.conf`: the `:80` block is `listen 80;` + `return 301 https://$host$request_uri;` with **no** `server_name`; the `:443` block **does** declare `server_name _;`. No `ssl_protocols`, `ssl_ciphers`, `ssl_session_cache` or `ssl_session_tickets` in either file. No proxied location sets `X-Forwarded-Host`. `location = /metrics` carries `allow 127.0.0.1; deny all;`. `location /csp-report/` uses `login_limit` (10r/s). `apps/moderation/views/decorators.py::staff_required_api` sends 401 with `headers={"WWW-Authenticate": "Bearer"}`. `config/urls.py` mounts `path("", include("django_prometheus.urls"))` at the **root** |
| **API-011** open | `docker-compose.prod.yml` binds `./.env.prod:/app/src/.env:ro` and sets `env_file` on eight app services; `config/settings/prod.py` has an unconditional `if not BOT_TOKEN: raise ImproperlyConfigured(...)` inside `if not _SKIP_SECRET_VALIDATION:`; `config/settings/base.py::read_env` loads the bind-mounted file into `os.environ` at import. Two `Bot` construction sites outside the bot process: `immediate_alerts.py::_send_payloads` (latent) and `send_alerts.py::Command._send_user_digests` (live) |
| **API-012** open | `apps/search/views/save_search.py::save_search` reads `query = (request.POST.get("query") or "").strip()` and passes `query=query or None` straight into `SavedSearch.objects.create(...)`. No `redact_free_text` import | **RESOLVED (BLOCK 13, 2026-10-03):** `redact_free_text` was applied at the write boundary (commit `a8eeecbd`). **Deviation from plan (P1):** the plan prescribed `redact_search_query()`, but the code uses `redact_free_text` — the same PII masks with **no 100-char truncation**, chosen because `SavedSearch.query` is `VARCHAR(200)` and truncating to 100 would silently change what the saved search matches. The never-lengthen invariant of both functions is preserved |
| **API-013** open, all three weaknesses | `immediate_alerts.py`: module-level `_executor: ThreadPoolExecutor` with `_MAX_DELIVERY_THREADS = 5`; `::deliver_immediate_alerts` calls `_executor.submit(_run_send, payloads)` and **discards** the `Future`; `::_run_send` catches `AiogramError` only. **`09-VAL-009`:** `::_send_payloads` has its **own** uncapped `float(exc.retry_after)` sleep on the retry path — a second instance of API-004's defect (1) that the report does not list |
| **API-015** open | `apps/core/views.py::csp_report` validates with `CSPReportPayload(**report["csp-report"])` (422 on schema failure) then logs the **whole, unfiltered** report dict at INFO. The method guard is a **hand-written** `if request.method != "POST"` returning 405 — the validator's correction confirmed |
| **API-016** open | `docker-compose.yml`: `postgres:18-alpine`, `redis:7-alpine`, `nginx:alpine`. `docker-compose.prod.yml`: **eight** services at `${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}`, plus `${TLS_CERT_PATH:-/etc/nginx/certs}:/etc/nginx/certs:ro` and `edoburu/pgbouncer:1.25.2` (the **only** pinned tag) |
| **API-017** open | `apps/core/services/translation.py::translate_text` routes ad text through `sanitize_query_for_log` at five log sites (control-character strip + `_MAX_QUERY_LENGTH` truncation, **no** PII masking). The DEBUG success line logs **both** input and output. `TranslationCircuitBreaker` emits one WARNING on the transition into open and nothing else. **Credit upheld:** the HTTP-failure lines log `e.request.url.copy_with(params={})`, stripping the `key` parameter, so `GOOGLE_TRANSLATE_API_KEY` cannot leak through them |
| **`09-VAL-002`** open, unowned | `apps/search/services/search_history.py::record_search_history` and `apps/search/services/popular_search.py` both write `normalized = query.strip().lower()` (raw) into `query_normalized` and `redact_search_query(query)` into `query`. `query_normalized` is a persisted indexed `CharField(max_length=200)`. `apps/search/migrations/0002_redact_search_queries` rewrote only the `query` column and says `query_normalized` is *preserved intact* |
| **Migration numbering** | `ads` → next free `0008_*`; `search` → next free `0003_*`. **Re-check the directory immediately before generating.** Phase 05 plans `ads/0008_*`; phases 03/06/08 all claim `apps/search` |
| **Baseline static gates** | `uv run ruff check src/` → **All checks passed** at `6413df5`. No test suite was run for this plan; no database was started; no outbound network call was made |

#### 0.2.3 Claims this plan does **not** treat as proven

Fifteen runtime-only claims survive from the validated report — all HTTP-layer
reproductions, aiogram / gunicorn defaults, Telegram's flood-control ceilings, and the
sibling-container `/metrics` reachability. **None was re-run for this plan.** Each is
carried into §0.2.4 with its verification step; each verification is an **Auditor pre-step**
of the named block, never something the Implementor discovers mid-edit.

#### 0.2.4 Runtime re-verification required before a block relies on a claim

All commands are Docker-only (§1.1). **Never** make a real outbound call to Telegram,
Google Translate or ECB.

| # | Claim to re-verify | Block | How |
|---|---|---|---|
| U1 | A patched-raising cache makes `/`, `/search/` and `/privacy/` return **500** and `/health/` return 503 with `cache: fail` | 1 | Targeted pytest that monkeypatches `site_config`'s cache getters to raise `ConnectionInterrupted(None)`, then asserts the status codes. **Assert red before the fix** |
| U2 | `retry_after=300` through `retry_transient` yields `sleeps=[300.0, 300.0, 300.0]`, total 900 s, `handled=True` | 4 | `test_error_handler.py` already fakes `asyncio.sleep`; add the 300 s case there as part of BLOCK 4's test change |
| U3 | A `TelegramServerError` yields `sleeps=[]`, `replays=0`, `handled=False` (the transient set is unreachable) | 4 | Add the case to `test_error_handler.py` **after** moving `_make_dispatcher` to `_TRANSIENT_EXCEPTIONS`; demonstrate it is red against the current wiring first |
| U4 | All four bot guards **raise** on a patched-raising cache; none fails open | 2, 3 | Copy `src/telegram_bot/tests/test_update_id_dedup.py::test_redis_unavailable_fail_open`'s `MagicMock` shape into one test per guard |
| U5 | The three web-tier guards also raise on the same patched cache | 2 | Same shape against `apps.core.services.contact_rate_limit`, `apps.search.services.rate_limit`, `apps.users.services.login_rate_limit`. **Assert red before the fix** |
| U6 | Seller markup survives verbatim into the alert body | 6 | Build a message from a title containing `<b>`, `&` and `<a href>`; assert the raw markup is present. **No network needed** |
| U7 | A warm-DB test-container bootstrap prints `Exchange rates loaded: 0 created, 3 updated` | 5 | Call `load_exchange_rates` twice in a targeted test; assert the second run reports 3 updated and the first-created row is untouched afterwards |
| U8 | `retry_after` sleeps can sit on aiogram's **60 s** socket timeout | 4, 6 | Read the pinned aiogram version's session-timeout default; consider pinning it explicitly in the commit body |
| U9 | `dp.run_polling(bot)` with no args ⇒ `handle_as_tasks=True`, `tasks_concurrency_limit=None` | 4 | Inspect the installed aiogram `Dispatcher.run_polling` signature. This is what makes a 900 s sleep an amplification problem rather than a delay |
| U10 | `ThreadPoolExecutor` joins its workers at interpreter exit, and the interaction with `preload_app = True` | 7 | **Deferred by design** — BLOCK 7 must be designed so the question does not need answering first (Q7) |
| U11 | Telegram's actual flood-control ceiling for `retry_after`, and the real 5xx mix | 4 | Not verifiable here by design. The deliverable is the **shape** of the fix (a bounded budget), not a specific number |
| U12 | The `GOOGLE_TRANSLATE_API_KEY` call latency profile (0.5 s timeout, 2 attempts, 100 ms base) | 8 | The breaker and malformed-200 tests already simulate every failure branch; only real latency is unmeasured |
| U13 | Whether `/metrics` is reachable from a sibling container (C-4, Q3) | 11 | `docker compose --project-name mko-bazuna-dev … exec bot sh -c "curl -s -o /dev/null -w '%{http_code}' http://nginx/metrics"` — one command settles it. **Do not write the report's sentence into a runbook before this runs** |
| U14 | gunicorn's SIGTERM drain behaviour with an in-flight `_run_send` | 7 | Deferred; gated on Q7 |
| U15 | That `IMAGE_TAG:-latest` actually moved two hosts to different code | 15 | Historical. `docker image inspect` on each host, compare digests. The **fix** is not gated on it |

### 0.3 Scope statement (explicit)

**In scope — 15 open `API-` findings, both partials' live halves, 5 `VAL-` process
constraints, and 3 Planner findings. 26 items.**

`09-API-001`, `002` (widened), `003`, `004`, `005`, `006`, `007` (part (a) only),
`008`, `009`, `010`, `011`, `013`, `014`, `015`, `016`, `017`; `09-VAL-001`
(respected as a boundary), `09-VAL-003` (symbol-anchor discipline), `09-VAL-004`
(the API-004 test atomicity), `09-VAL-005` (the corrected Wave-1 ordering),
`09-VAL-006` (the API-001/API-008 coupling); plus `09-VAL-007`, `09-VAL-008`,
`09-VAL-009` (§0.4).

**Handled, no implementation work inside phase 09's production commits:**

- **`09-VAL-002`** — an **unowned open product defect**. Phase 09 **routes** it; BLOCK 13
  publishes the finding, the two candidate fixes and the acceptance criteria. Phase 09
  does **not** edit `apps/search/services/search_history.py`, `popular_search.py` or
  `apps/search/migrations/` — all three are three-way reserved (§5.3).
- **`09-API-012`** — **routed, not implemented.** Phase 08 has explicitly parked
  `SavedSearch.query` redaction as its Q5, a **forward dependency on phase 06**, and
  phase 06 owns `06-PII-108` (`SearchHistory.query_normalized`). BLOCK 13 is a
  **decision/handoff block** and ships **zero** production behaviour.
- **`09-API-007` part (b)** — **rejected on evidence** (C-5) and not actioned.
- **`09-VAL-001`** — respected as a boundary: API-008 ↔ `03-DB-008` and API-009 ↔
  `02-CFG-004` are cross-referenced, **never merged**. §5 records both.

**Two systemic commitments this plan makes, because treating the findings as seventeen
independent patches leaves the *class* intact:**

1. **One cache-failure policy, written down once**, in `apps/core/utils/cache.py`, with
   one shared read helper and one shared window-bump helper. BLOCK 1 and BLOCK 2 together
   cover **seven** request-path guards plus the site-config getters, in both tiers.
2. **Every fix that a green test contradicts changes the test in the same commit**, with
   the test named and the justification stated in the commit body. This plan slates
   **four** unconditional test rewrites (BLOCKS 4, 6, 7, 8) and **constrains** several
   more.

### 0.4 Severity corrections

The report's own movements are **upheld in full** and not re-litigated:

| ID | Movement | This plan's position |
|---|---|---|
| `09-API-005` | HIGH → **MEDIUM**, P0 → P1 | **Upheld.** A missing capacity control on one endpoint whose worst case is DB pressure, not a lost guarantee. One incident from HIGH — §7 records the re-grade trigger |
| `09-API-010` | MEDIUM → **LOW**, P1 → P2 | **Upheld.** The reflected `$host` is by construction the host the client used to address the server. **The fix still ships** (BLOCK 11): the missing `server_name` is a real misconfiguration trap |
| `09-API-007` | split; part (b) REJECTED | **Upheld.** Half (a) survives and is the whole of the real finding; half (b) is refused against the tree (C-5) |
| `09-API-008` | DOC-UPDATE → **SPEC-DEVIATION** | **Upheld.** The false claim lives in the ops runbook *and* in two code docstrings; code or policy must change |
| `09-API-009` | DOC-UPDATE → **SPEC-DEVIATION**, scope 1 → 5 sites | **Upheld.** Four runbook sentences plus the settings comment; two of the runbook sentences are inside the compromise-response procedure |
| `09-API-011` | evidence corrected | **Upheld** — with the Planner's C-3: the exposure is `env_file` + bind mount on **eight** services, and the three explicit compose lines are not the mechanism |

**Corrections and additions this Planner makes (none re-open a finding's status):**

- **C-1 … C-10** (§0.2.1) — nine of these send an Implementor to a symbol, line or
  exposure model that does not hold. Read them before BLOCK 9, 11, 14 or 15 starts.
- **`09-VAL-007` [MEDIUM, rollout] — a fourth half of API-001 the report does not name.**
  `set_cached_site_config` / `set_cached_bot_username` sit **inside** the same `try` as
  the ORM read, so a Redis **write** failure returns the fallback string after a
  **successful** database read, and the warning line claims *"SiteConfig unavailable"* —
  a wrong diagnostic that will mislead the next responder. BLOCK 1, gate **Q12**.
- **`09-VAL-008` [LOW, evidence] — two counts in the code context are wrong.** The
  `except ValueError`-only **version-bump** helpers number **four**, not three, and **two
  of their signal receivers are unguarded**; `apps/core/utils/cache.py` has **fifteen**
  call-shaped helpers, not ten. Neither changes a disposition; both are recorded so the
  de-scoping in §6.3 is precise and so the "shared home" is not mistaken for a new module.
- **`09-VAL-009` [MEDIUM, availability] — the alert path has its own uncapped backoff.**
  `immediate_alerts.py::_send_payloads` sleeps `float(exc.retry_after)` verbatim on its
  retry path — a **second, independent** instance of `09-API-004`'s defect (1) — and
  `test_immediate_alerts.py::TestRetryAfterBackoff::test_429_retry_after_honored` pins the
  exact sleep value, so the ceiling interacts with a live assertion. BLOCK 6 / BLOCK 7,
  gate **Q8**. **Neither the report nor the validated findings name this.**
- **`09-API-002` is widened from four guards to seven** (three of them web-tier). A helper
  scoped to `telegram_bot/services/rate_limit.py` leaves three web-tier 500s in place,
  **and an `apps.*` → `telegram_bot.*` import is forbidden** by the project rule. BLOCK 2.
- **`09-API-015`'s severity stays LOW but its blast radius is real**: the endpoint is
  unauthenticated, nginx allows it 10 r/s, and page URLs routinely carry buyer search
  text. The **log-hygiene policy** half belongs to phase 06 (`06-PII-102`); phase 09 owns
  the ingress field selection and the zone. BLOCK 12.

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**This plan does not choose where technical uncertainty exists.** Each question produces
either a pre-block step (Auditor / Researcher / Planner) or a labelled **decision required
before implementation** gate inside the named block, with the options and their
consequences. **Silence is not an acceptable outcome for any of them.**

| ID | Question | Block | Who decides | Status |
|---|---|---|---|---|
| **Q1** | **Mandatory or warning for `EMAIL_HOST` in production?** The single real consumer (`send_support_notification_email`) already fails **open**, so a warning matches the code's own behaviour — but a compliance or support-SLA requirement would make mandatory correct. The report calls this *"a human call, not a code call"* | **9** | **Owner / Coordinator (human).** Not an engineering decision | **RESOLVED 2026-10-03 (Product Owner) — LOUD WARNING at startup, NOT a hard boot gate.** The settings guard **must NOT raise `ImproperlyConfigured`**, and **no test may assert that it fires**. All **six** comment sites — and the compromise-response procedure — that describe it as a boot gate must be corrected to match. This **supersedes** §0.6.2's *"the guard is CODE"* reading with the owner's chosen severity. See §0.7 |
| **Q2** | **By what mechanism is `/metrics` restricted in Django as well as nginx?** A middleware, a `config/urls.py`-level wrapper, or `django_prometheus`'s own hook. Adjacent to phase 15's authorization territory | **11** | Researcher (mechanism) + **phase 15 boundary check** before building | **GATED.** The hardening is defence in depth; the *shape* is a design choice with a cross-phase boundary | **RESOLVED 2026-10-01 — a `urls.py` gate view keyed on loopback `REMOTE_ADDR`.** The decisive constraint is INVERTED: Django's `RequestFactory` hard-codes `127.0.0.1`, so `test_metrics_endpoint` stays green. See §0.6 |
| **Q3** | **Is the `/metrics` "reachable from every sibling container" impact model correct?** The tree says `allow 127.0.0.1; deny all;` **denies** Docker-bridge `172.x` peers (C-4) | **11** | **Researcher — one `curl` from a sibling container (U13)** | **Pre-block step, not a gate.** An inverted impact model produces a runbook that warns about the wrong thing |
| **Q4** | **What is the shape of the translation-failure signal?** *Minimal* (compare the result to the source, leave the column `NULL`, count a `fallback` total) keeps `translate_text`'s `str` signature and the whole `test_translation.py` suite green. *Status object* + a `translation_failed_at` column changes the return type, breaks every test in that file, and needs a migration whose number must be checked against phase 05's `ads/0008_*` | **8** | **Planner, with phase 05 / 06 migration coordination** | **GATED.** Effort S vs M **plus** a schema change. BLOCK 8 carries both options | **RESOLVED 2026-10-01 — option (a): NULL column + an `int` fallback count, SCOPED to the backfill command.** `translate_text`'s signature is unchanged; the signal is a side-channel. See §0.6 |
| **Q5** | **Is redacting `SavedSearch.query` on write the right product call?** The report itself calls the raw form for a buyer's *own* saved search a legitimate alternative, conditional on a documented retention rule and no third-party rendering | **13** | **Product Owner** (answered 2026-10-03) | **RESOLVED 2026-10-03 (Product Owner) — YES: redact at write.** `SavedSearch.query` is stored **REDACTED** via `redact_free_text()` (commit `a8eeecbd`). **Deviation from plan (P1):** the plan prescribed `redact_search_query()`, which truncates to `_MAX_QUERY_LENGTH=100`. The code uses `redact_free_text` — the same PII masks without truncation — because `SavedSearch.query` is `VARCHAR(200)` and truncating to 100 would silently change what the saved search matches against. Phase 09 now **implements** the `save_search` call plus a test in BLOCK 13; the *"unless the owner rules…"* clause in `09-API-012` is **removed**. See §0.7 |
| **Q6** | **Should `query_normalized` be keyed on redacted or raw text (`09-VAL-002`)?** It is the persisted, indexed dedup/lookup key that migration `0002_redact_search_queries` deliberately preserved. Redacting it changes dedup semantics (two users searching different phone numbers collapse) and needs a follow-up **data** migration | **13** | **Product Owner** (answered 2026-10-03) | **RESOLVED 2026-10-03 (Product Owner) — key it on the REDACTED form.** One rule for all query-persistence paths. The **follow-up data migration** for existing rows is a **propagation obligation on phase 06** (PII policy owner), because `apps/search/migrations/` is three-way reserved. See §0.7 |
| **Q7** | **Where does the API-013 shutdown hook actually run?** `gunicorn.conf.py` sets `preload_app = True`, so a module-import-time registration lands in the **master**, not in the forked workers that hold the in-flight sends (C-7) | **7** | **Researcher** (confirm against the pinned gunicorn version and the actual signal path) + **Planner** (choose the registration point) | **GATED.** A hook in the wrong process is a no-op that *looks* like a fix | **RESOLVED 2026-10-01 — `gunicorn.conf.py::worker_exit`, the worker-side hook.** The fork/executor defect is **NOT present** (the import is lazy); worker-side-ness must be pinned by a test. See §0.6 |
| **Q8** | **What ceiling for the alert-path retry (`09-VAL-009`)?** `_send_payloads` sleeps `float(exc.retry_after)` uncapped, separately from `retry_transient`, and `test_429_retry_after_honored` pins an exact sleep value | **6** (and **7**) | **Researcher (read the fixture) + Planner (set the ceiling)** | **GATED.** A cap above the pinned fixture is untested; below it, the test must change **in the same commit** | **RESOLVED 2026-10-01 — a per-module `RETRY_AFTER_CEILING = 30.0` clamping ONE retry.** There is no loop, so this is a single-sleep ceiling, not a budget. See §0.6 |
| **Q9** | **Are the seven cache guards fixed in one change or per module?** One shared helper is the right architecture; per-module changes are safer to land. Phases 02 / 03 / 06 / 08 all have claims on `apps/*` files | **2** | **Coordinator** (sequencing across four plans) + **Planner** (commit shape) | **GATED.** BLOCK 2 carries both shapes and their contention costs | **RESOLVED 2026-10-01 — TWO commits, bot half first.** The guards do not exist yet; the web half must wait for phase 16's uncommitted work. See §0.6 |
| **Q10** | **Is the "one outbound gateway" consolidation in scope for phase 09 at all?** It would collapse `09-API-004`, `09-API-011` and `09-API-013` into one owner, but it breaks the `{module}.Bot` patch targets in **two** test files and crosses the backend/bot boundary | §4.5, **6**, **7**, **11**, **14** | **Coordinator + Owner** | **GATED as a scope question. This plan does NOT assume it.** BLOCK 6, 7 and 14 each ship the local fix; the consolidation is recorded as a follow-on (§6.2) | **RESOLVED 2026-10-01 — the "outbound gateway" consolidation is NOT in scope.** It would collapse `09-API-004`, `-011` and `-013` into a new capability. See §0.6 |
| **Q11** | **Does the rate-provider question survive at all?** Nothing in `apps/currencies` makes a network call. A live ECB feed is a **new capability** (HTTP client, scheduler entry, rate-history model, migration), not a doc fix | **5** | **Owner / product** | **GATED.** BLOCK 5 ships `get_or_create` + wired invalidation + the doc correction, which are correct **whichever way** Q11 goes. A live feed is routed, not built | **RESOLVED 2026-10-01 — NO network call exists in `apps/currencies`.** Verified exhaustively: no `httpx`/`requests`/`aiohttp` import. A live ECB feed is a NEW capability. See §0.6 |
| **Q12** | **Does the cache *write* move out of the `try` in `get_site_name` / `get_bot_username` (`09-VAL-007`)?** | **1** | **Researcher (shape) + Planner** | **GATED.** Moving it out changes when the cache is primed and stops a successful DB read from being masked; leaving it in keeps one `try` and a wrong diagnostic | **RESOLVED 2026-10-01 — option (b): narrow the `try`.** Option (a) is not viable; a shared `cache_set_best_effort` has one consumer and the WRONG VERB for BLOCK 5. See §0.6 |
| **Q13** | **At what point is `PriceNormalizer.invalidate_rate_cache()` wired?** The helper is implemented and has **zero** call sites. The candidates are an admin save hook, a `post_save` signal on `ExchangeRate`, or the `recompute_normalized_prices` command — and a signal on a **rate** row is a new receiver in a new app | **5** | **Researcher (is there an existing admin / command surface?) + Planner** | **GATED.** The report's own maintainability warning applies: a helper that is implemented, documented and never called is *worse* than an absent one | **RESOLVED 2026-10-01 — a new `apps/currencies/signals.py` receiver.** Option (b) is MOOT: `admin.py` does not exist. An in-seed call would be unreachable dead code. See §0.6 |
| **Q14** | **What is the `:80` redirect shape, given that it requires the operator to set a real `server_name`?** | **11** | **Researcher (what does a fresh clone / dev do?) + Owner (what does production need?)** | **GATED.** This is the **only** change in the phase that can break a *working* deployment. Both shapes are argued in BLOCK 11 | **RESOLVED 2026-10-01 — ship `server_name _;` (one line); ROUTE the domain mechanism.** Option (c) is foreclosed; the catch-all is deliberate. See §0.6 |

---

### 0.6 Gate resolutions — 2026-10-01 (Auditor → Researcher pass)

**Scope.** The Auditor refuted several of the plan's file paths and one of its central
premises; the Researcher then closed Q2, Q4, Q7, Q8, Q9, Q12, Q13 and Q14, and closed Q10
and Q11 as scope rulings. The Researcher also **refuted the Auditor's own flagged fork
defect** after verifying the import graph.

**Still open after the 2026-10-03 Product Owner rulings:** **none.** **Q1**, **Q5** and **Q6**
were all answered by the Product Owner on `2026-10-03` (§0.7). **Q3** remains the pre-block
`curl` verification step it was, and **Q1's §0.6.2 "the guard is CODE" reading is superseded**:
the owner chose the **warning**, so the guard's *shape* — not its existence — is the change.

#### 0.6.1 Resolved decisions

| Gate | Decision | Why the alternatives lost |
|---|---|---|
| **Q2** | **A gate view in `config/urls.py` in front of the metrics route, keyed on `request.META["REMOTE_ADDR"]` ∈ loopback, returning 403 otherwise.** | **The plan's decisive constraint is inverted.** Django's test `RequestFactory` hard-codes `REMOTE_ADDR="127.0.0.1"`, so `test_metrics_endpoint`'s unconditional 200 stays **green unchanged** — the constraint that looked decisive does not bind. A `urls.py` gate also leaves the **15-entry `MIDDLEWARE` count** phase 16 pins untouched, and reads raw `META` rather than adding a **fourth** private `_get_client_ip` (phase 16 `B-08` owns that collapse). It closes both real exposures: a sibling container reaching `web:8000/metrics` across the bridge (source `172.x` → 403) and dev's published `8000:8000` (host traffic arrives as the Docker gateway → 403), so `nginx.dev.conf` needs no `= /metrics` block. Rejected: middleware (a per-request tax on every request to protect one route, plus the count change); the library hook (**moot** — `django_prometheus==2.5.0`'s `ExportToDjangoView` is a bare function view with zero auth seam); nginx-only (leaves the bridge bypass open, which *is* the finding); moving the route to an internal path (closes the bridge but not dev's published port). **New coupling to record:** a scrape *through nginx* now 403s at Django — which is already true at the nginx layer today, so nothing that works stops working, but an operator centralising Prometheus must widen this deliberately. |
| **Q4** | **Option (a) — NULL column plus an `int` fallback count — confined to `backfill_translations.py`. `translate_text`'s `-> str` signature is unchanged; the signal is an observable side-channel** (the absent `updates` key leaves the column NULL, plus a `fallbacks` list). | **The publish-path constraint the plan worried about does not bind.** `Ad.get_title(locale)` returns the first truthy value of `[f"title_{locale}", "title"]`, so a NULL `title_en` renders **identically** to today's source-in-column state. Search is not at risk either: `search_vector_en`/`_bs` are built from `coalesce(title_en,'')`, so NULL gives that language's vector no title weight — **honest and repairable** — whereas source-in-column feeds `to_tsvector('english', <Russian>)`, which is noise. **An `int` counter, not a new `TranslationOutcome` StrEnum**: `fallback` is a count, not a named vocabulary, and the collocated precedents (`DeliveryOutcome`, `ConsumeOutcome`) each exist because a *multi-way* mapping was needed — here there is one comparison, so a vocabulary would have one consumer and no second discriminator (rule 5). The metric option is **moot for this block**: the command runs in the `migrate` one-shot, which has no `PROMETHEUS_MULTIPROC_DIR` and no tmpfs. Rejected: the status column (migration, a full `test_translation.py` rewrite, an `apps/ads/` number contended with phase 05's planned migration, and **no added capability** — the re-run is already driven by the existing nullability-derived selection query). Extending (a) to the bot publish path is **routed as a follow-on**: `translate_all_languages` builds a dict with every locale key present, so `submit.py`'s `.get("en", original_title)` never falls through; making NULL reach publication means editing two bot files the plan never lists and rewiring `SubmitAdInput`'s `""` sentinel. |
| **Q7** | **`worker_exit(server, worker)` added to `gunicorn.conf.py`**, beside the existing `child_exit`, calling `_executor.shutdown(wait=False, cancel_futures=True)` behind a guarded lazy import. | **There is exactly one viable registration family**, not a menu: `atexit` appears **zero** times tree-wide, `signal.signal` only in the scheduler subprocess, and the four `transaction.on_commit` sites are commit-deferred work. `worker_exit` is invoked at `gunicorn/arbiter.py:734` inside the **child's own `finally:`** after `worker.init_process()` — the worker, on the normal path. `on_exit` (`arbiter.py:387`, inside `Arbiter.stop`) and `worker_int` are **master-side**. Rejected: the module-level shutdown registry (**moot by its own rationale** — it concedes the state is a post-`fork()` clone); a `ready()`-based hook (**there is no worker-local `ready()`** — under `preload_app = True` `ready()` runs in the master). |
| **Q8** | **A per-module `RETRY_AFTER_CEILING: Final[float] = 30.0` clamping the single retry**, landing in both modules inside BLOCK 6's existing commit. | **There is exactly one retry and no loop** in either path (`sleep → one retry → except AiogramError`), so this is a **single-sleep ceiling, not a total budget** — `09-VAL-009`'s existence stands but its magnitude is overstated. **Per-module, not a shared helper:** both modules live in `apps/search`, so there is no import-direction problem to solve, and a helper for a `min()` is a one-line abstraction over a one-line call site (rule 5). A shared constant in `apps/core/` would be a **third** home for Telegram backoff policy that BLOCK 4's `retry.py` also needs — **and BLOCK 4 lands first**; if anyone consolidates it should be BLOCK 4, not BLOCK 6, and not into a three-way-reserved file. `30.0` is chosen so **both pinned fixtures stay green unchanged** (both use `retry_after=2` → `assert_awaited_once_with(2.0)`); the ceiling gets its own new case at `retry_after=300`. **The plan's §0.5 note is backwards**: a cap *above* the fixture leaves the pinned test surviving; a cap *below* it requires rewriting two pinned assertions. |
| **Q9** | **Two commits, bot half first.** Commit A: the new helper in `apps/core/utils/cache.py` **+** all four `telegram_bot/services/rate_limit.py` guards together. Commit B: the three web guards, only after phase 16's working-tree changes land. Helper shape: `bump_rate_limit_window(key: str, limit: int, period: int) -> bool`. | **The guards do not exist yet** — `apps/core/utils/cache.py` has **zero** guards and **zero** documented fail-open windows, so BLOCK 2 is *creating* the contract, and there is no half-migrated prior state to respect, only a half-adopted new one. The **bot half has zero contention** (one file, no `apps/*` claim); the **web half collides on `apps/users/tests/test_login.py`**, which phase 16 has already modified in the working tree — and BLOCK 3 consumes the helper, so Commit A must land first regardless. Rejected: the plan's three-commit option (puts the contract in a commit with no consumer and leaves two intermediate commits with the policy half-adopted); one commit across six files and four apps (a blast radius that buys nothing and collides with live uncommitted work). **Signature non-uniformity forces the helper's shape**: three guards take `HttpRequest` and derive their own IP, one also takes `*, namespace`, four are `@sync_to_async` while three are sync — so the helper takes the **already-computed `key`, never `request`**, and must be a plain `def`. The `ValueError` branch stays **byte-identical**. |
| **Q12** | **Option (b): narrow the `try`.** Read via BLOCK 1's never-raising helper, DB read + `return` inside the existing `try`, and the `set_cached_*` write in **its own** `try/except (ConnectionInterrupted, redis.RedisError)` logging at **DEBUG**. | Option (a) is **not viable** — it closes only the read half and leaves `09-VAL-007` open. The finding's content is precisely *"a successful DB read is masked and the log line lies"*; (b) makes the log line true and returns the database's answer whenever the database answered. **Two inline guards, not a shared helper** — and the plan's cost analysis for (c) is wrong in a direction that *strengthens* the rejection: **BLOCK 5's second consumer needs a guard on `cache.delete`, not `cache.set`**, so a `cache_set_best_effort` would serve BLOCK 5's neighbour, not BLOCK 5. One consumer, wrong verb → rule 5. **Do not wait for BLOCK 5** — `09-VAL-006` already orders BLOCKS 1 and 5 in one wave, and (b) is complete on its own. Both `test_get_site_name_reads_from_cache` and its `test_site_config_bot_username.py` mirror stay green unchanged, because (b) keeps the read first — only a naive reorder (DB first) would break them. Fallback strings stay byte-identical. |
| **Q13** | **A new `apps/currencies/signals.py` with `post_save` + `post_delete` receivers on `ExchangeRate`, registered from a new `CurrenciesConfig.ready()`.** | Option (b) is **moot** — `apps/currencies/admin.py` **does not exist**; the app has neither `admin.py` nor `signals.py`. **A call inside `load_exchange_rates` is strictly worse**: there is **one** production writer, and after BLOCK 5's switch to `get_or_create` the seed **never writes an existing row**, so an in-seed invalidation would be **unreachable dead code**. A receiver covers every write path by construction, including a future admin or a `shell`. Rejected: a `save()` override (couples the model to the cache backend — rule 3). The `(ConnectionInterrupted, redis.RedisError)` guard is **mandatory** — without it `cache.delete` raising inside a signal **rolls back the saving transaction** — and must copy `apps/categories/signals.py::invalidate_on_lookup_item_change` verbatim. Phase 03 reserves none of this surface. |
| **Q14** | **Ship `server_name _;` in the `:80` block — one line. Route the domain mechanism.** | The missing `server_name` is a **deliberate catch-all, not a defect**: a `listen 80` block with no `server_name` *is* nginx's default server for that port, and `return 301 https://$host$request_uri` is the standard same-host HTTPS idiom; there is exactly one TLS vhost, so there is nothing to select between. The only genuine defect is the **asymmetry** — the TLS block declares its catch-all, the `:80` block relies on the implicit default — and the one line closes exactly that. Option (b) alone yields `return 301 https://$request_uri;`, an **empty host** nginx treats as malformed, so it is unusable without (a) — and (a) has **no delivery mechanism**. Option (c) is **foreclosed** by BLOCK 11's own constraint 7. Inventing an `NGINX_SERVER_NAME` env var is speculative and would fail `test_deploy_check_env_parity.py` until the name is added to `.github/workflows/ci.yml` — which **no phase in this plan claims**. Route the cost with the decision; do not pre-pay it. |

#### 0.6.2 Two rulings that were scope questions, not technical ones

- **Q10 — the "one outbound gateway" consolidation is NOT in scope.** It would collapse
  `09-API-004`, `-011` and `-013` into a single new capability, which is the definition of
  the speculative redesign the project rules forbid. Each is remediated on its own surface.
- **Q11 — no network call exists in `apps/currencies`.** Verified exhaustively: the module
  inventory is `__init__`, `apps`, `enums`, `models`, `migrations/0001_initial`,
  `services/{__init__,exceptions,price_normalizer}`,
  `management/commands/{load_exchange_rates,recompute_normalized_prices}`, `tests/` — with
  **no `httpx`/`requests`/`aiohttp` import anywhere**. The only outbound HTTP client in the
  Django backend is `translation.py`'s `httpx.Client`. **A live ECB feed is a new
  capability, not a remediation.**
- **Q1 — superseded on 2026-10-03 by the Product Owner.** The finding above — that the guard
  is code, not a decision — remains **accurate evidence** (all three named email flows are
  fictional; no test asserts the guard fires; there are **six** correction sites in three
  files). What is superseded is the **conclusion**: §0.6.2 treated the existing raising guard
  as the shape to keep and priced demotion as the option. **The Product Owner chose the
  warning.** The six-site correction cost, the `test_deploy_check_env_parity.py` taxonomy
  update and the "no test asserts it fires" test-safety finding **all still apply in full** —
  they are now the price of a *decided* change rather than a gated one. See §0.7.

#### 0.6.3 The Auditor's fork defect does not exist — and the real risk is narrower

The Auditor flagged that under `preload_app = True` gunicorn calls `django.setup()` before
`fork()`, which would construct `immediate_alerts._executor` in the master and leave a
worker-side `submit()` enqueueing into a clone no thread drains. **Verified false:**
`django.setup()` does **not** import `apps.search.services.immediate_alerts`.
`apps/moderation/signals.py::deliver_immediate_alerts_on_publish` imports it **lazily
inside `_deliver()`**, which runs inside `transaction.on_commit` — worker-side, post-fork.
The executor is built in the worker with live threads, and Q7's "which process owns the
sends" is answered by the tree rather than by a design choice.

**The residual risk is the inverse and smaller, and BLOCK 7 must convert the accident into
a constraint:** worker-side-ness holds only because that import is lazy. Hoisting it to
module level in `moderation/signals.py`, or adding `immediate_alerts` to
`apps/search/services/__init__.py`, would move the executor into the master and reproduce
exactly the "rows written, `delivered_at` NULL, no send, no log" symptom — which is
indistinguishable from the documented backlog. **BLOCK 7 therefore owes a test pinning
that the module is absent from `django.setup()`'s import graph.**

Two further implementation traps the implementor must not hit: `worker_exit` must **not** be
tested by executing it against the real module, because `test_observability.py::_load_gunicorn_conf()`
execs `gunicorn.conf.py` inside the pytest process and would `shutdown()` the global
executor for the rest of the session — the test must `monkeypatch` it with a `Mock`. And
BLOCK 5's test must **not** hold a long-lived `PriceNormalizer` across an invalidation:
`invalidate_rate_cache` is a `@staticmethod` deleting only the shared key and cannot reach
any live instance's `_rate_cache`. That is unreachable today because
`normalize_price_to_eur` builds a fresh instance per call (its docstring says long-lived
instances were deliberately avoided), so a test asserting the opposite would pin behaviour
the helper cannot deliver.

#### 0.6.4 Corrections to this plan's prose (tree wins)

| # | Correction |
|---|---|
| 1 | **`_send_payloads` is in `apps/search/services/immediate_alerts.py`**, not `notification_delivery.py` — which has **no retry loop at all**. `DeliveryOutcome` is a `mark_delivered` log vocabulary. |
| 2 | **`09-VAL-009` is a THIRD uncapped instance**, not the second: `send_alerts.py::Command._send_user_digests` has the identical `float(exc.retry_after)` shape **and its own independent `_BACKOFF_BASE: Final[float] = 0.5`**. |
| 3 | **The translation module is `apps/core/services/translation.py`**, not `translate.py`. |
| 4 | **`apps/core/utils/cache.py` has ZERO guards and ZERO documented fail-open windows** — no `try`, no `except`, no `logger`, no `redis`/`ConnectionInterrupted` import; 15 helpers across 5 bare triads; the docstring claims only "cached singleton access for ModerationCriteria". The contract BLOCK 1/2 mandates **does not exist yet; it is being created.** |
| 5 | **`apps/currencies/admin.py` does not exist** — the app has neither `admin.py` nor `signals.py`, so **Q13 option (b) is moot.** `apps/currencies/apps.py::CurrenciesConfig` also has **no `ready()`**, which BLOCK 5 must add. |
| 6 | **`test_nginx_config.py` has FOUR tests** (the plan says three), plus `_location_block(text, location_match) -> str`; it parses `nginx.conf` only. |
| 7 | **`on_exit`, `worker_exit` and `worker_int` are ALL ABSENT** from `gunicorn.conf.py`; only `child_exit` exists. |
| 8 | **`apps/search/tests/test_send_alerts.py::TestTransientErrorHandling::test_429_retry_after_honored` is missing from BLOCK 6's `tests_to_run`** — a second pinned fixture (`retry_after=2` → `assert_awaited_once_with(2.0)`). |
| 9 | **Unrecorded phase-16 contention:** `apps/users/tests/test_login.py` — BLOCK 2's named tripwire — is **already modified in the working tree**, along with `apps/users/{models.py,services/login_token.py,views/consent.py,tests/test_consent.py,tests/test_login_token.py}` and an untracked `migrations/0003_logintoken_browser_binding.py`. The two service files BLOCK 2 also edits are **not** dirty; the collision is the one test file. |
| 10 | **`EMAIL_HOST` has six correction sites in three files**, not five — `test_prod_logging.py`, `test_csrf_trusted_origins.py` and `config/settings/base.py` each carry a comment asserting the guard exists. |
| 11 | **The `preload_app` + fork executor defect is NOT present** (§0.6.3). The real risk is worker-side-ness being an accident of a lazy import; BLOCK 7 must pin it with a test. |
| 12 | **Q8's "a cap above the pinned fixture is untested" is backwards** — above leaves both pinned tests green and needs one new case per module; below rewrites two pinned assertions. |
| 13 | **There is exactly one retry in each alert path — no loop.** The exposure is a single sleep; `09-VAL-009`'s existence stands but its magnitude does not. |
| 14 | **`notification_delivery.py` is in `apps/search/services/`**, not `apps/core/services/`. |
| 15 | **The `prometheus-django-metrics` URL name is never reversed anywhere**, so the route may move without breaking a reverse. |
| 16 | **`IMMEDIATE_ALERTS_ENABLED=false` is in THREE `.env*.example` files, not four** — `.env.test.example` exists but does not carry it, so BLOCK 7's acceptance criterion "remains false in all four" is not literally checkable as written. |
| 17 | **BLOCK 5's second guard candidate is `cache.delete`, not `cache.set`** — which further weakens Q12 option (c). |
| 18 | **`docs/ops/docker-deployment.md:1176`** ("An external Prometheus instance scrapes it") and **`docs/ops/prometheus-slo-alerts.yaml:9`** are **wrong today** — the nginx-proxied path is already 403 and there is **no Prometheus service in either compose file**. Flag to phase 12; do not edit here. |

#### 0.6.5 New findings filed by this pass

- **`09-NEW-01`** — worker-side-ness of `immediate_alerts` is an **accident of a lazy import**,
  not an enforced invariant. Hoisting that import would reproduce the "rows written,
  `delivered_at` NULL, no send, no log" symptom while looking correct. Pinned by a test
  BLOCK 7 owes.
- **`09-NEW-02`** — `PriceNormalizer.invalidate_rate_cache` is a `@staticmethod` deleting only
  the shared key and **cannot reach any live instance's `_rate_cache`**. Unreachable today
  because `normalize_price_to_eur` builds a fresh instance per call, but it makes any future
  long-lived normalizer silently immune to invalidation.
- **`09-NEW-03`** — `load_exchange_rates` runs **once per deploy** as step 3 of
  `migrate_locked._build_steps`, and is in **neither** `HOURLY_COMMANDS` **nor**
  `DAILY_COMMANDS`. Exchange rates are therefore never refreshed on a schedule, and the
  rate cache's 300 s TTL is the only thing bounding staleness. Routed — refresh scheduling
  is a product/ops decision.
- **`09-NEW-04`** — `recompute_normalized_prices` is registered in
  `test_sweep_lock_structure.py::_LOCK_TARGET_MODULES` with a session-scoped advisory lock
  but is **not dispatched by any scheduler**. An orphaned command with a reserved lock.

---

### 0.7 Product Owner gate rulings — 2026-10-03

**Authority.** Product Owner decisions, dated `2026-10-03`, recorded here so that no Implementor
can re-derive a settled question. **Every `GATED` row in §0.5 that maps to a ruling below is
now closed.** Two of them change a block's *class* — a block that shipped no production code
now ships a bounded change, and a block that shipped a raising guard now ships a warning.

| Gate | Ruling (2026-10-03, Product Owner) | Chosen option | Block-level consequence |
|---|---|---|---|
| **Q1** — `EMAIL_HOST` in production | **A LOUD WARNING at startup, NOT a hard boot gate.** The settings guard **must NOT raise `ImproperlyConfigured`**, and **no test may assert that it fires** | **(b)**, on the owner's own severity | **BLOCK 9 is rewritten**: it ships a `logging.getLogger(__name__).warning` in place of the guard, plus the **six** comment-site corrections and the compromise-response procedure. **This supersedes §0.6.2's "the guard is CODE, not a decision" reading** — the evidence in that section stands (the three named flows are fictional; no test asserts the guard fires), but the conclusion is replaced by the owner's severity choice. Acceptance criteria and test expectations are restated: the new test asserts a **WARNING is emitted and the import succeeds**, and a test asserting the raise **must not exist**. `test_deploy_check_env_parity.py`'s "six guards raise `ImproperlyConfigured`" taxonomy must lose one entry in the same commit |
| **Q5** — redacting `SavedSearch.query` on write | **Yes — redact at write.** `SavedSearch.query` is stored **REDACTED** via `redact_free_text()` (commit `a8eeecbd`). **Deviation from plan (P1):** plan prescribed `redact_search_query()` (truncates to 100); code uses `redact_free_text` (no truncation) because `VARCHAR(200)` would lose matches. Both share the same PII masks and "never lengthen" invariant | **the product rule** | **`09-API-012` moves from "routed, not implemented" to IMPLEMENTED IN PHASE 09.** BLOCK 13 gains the `redact_free_text` call **plus a test**. The *"unless the owner rules that the buyer's own saved search keeps the raw form"* clause in `09-API-012` and in BLOCK 13's acceptance table is **removed**. BLOCK 13 is therefore **no longer a zero-production-code handoff block** — see §3 and §8.1 for the corrected block count |
| **Q6** — the `query_normalized` storage key (`09-VAL-002`) | **Key `query_normalized` on the REDACTED form.** One rule for **all** query-persistence paths | **the product rule** | **`09-VAL-002` is decided.** Two consequences phase 09 **does not** implement, and records as a **propagation obligation on phase 06** (the PII policy owner): the **follow-up data migration** that repairs existing `PopularSearch.query_normalized` and `SearchHistory.query_normalized` rows, and the **explicit statement of what happens to dedup semantics** when two users search different phone numbers and their keys now collapse. Both need `apps/search/migrations/`, which is **three-way reserved** (phase 06 BLOCK 7, phase 03 BLOCK 9 option B, phase 08 BLOCKS 5/8) |

**Rulings that do not change phase 09's work, recorded so they are not re-litigated.**

- **A native (preferably Montenegrin) reviewer must sign off the three `bs` strings.**
  Machine output and translation APIs are not acceptable, and until that sign-off exists the
  gate stays **OPEN-PENDING-REVIEWER**, not closed. **This is plan 14's BLOCK 9, which the
  second Planner owns — phase 09 records it only for consistency.** Phase 09 introduces **no**
  new `bs` string under any 2026-10-03 ruling: BLOCK 9's warning is a log line, not a
  user-visible message, and BLOCK 13 adds no string.
- **`TIME_ZONE = "Europe/Podgorica"` is hard-coded and NOT env-overridable** — therefore **no
  `ALLOWED_ENV_VARS` entry and no `.env*.example` lines**. Plan 14's file. Recorded here
  because BLOCK 9's and BLOCK 13's acceptance criteria both assert
  `test_env_allowlist.py` stays green, and this ruling is the reason no allowlist edit is
  needed anywhere in this programme.

**Technical gates that are NOT Product Owner decisions and therefore remain exactly as they
are.** Q2, Q3, Q4, Q7, Q8, Q9, Q10, Q11, Q12, Q13 and Q14 keep their 2026-10-01 resolutions
verbatim. **No module placement, commit sequencing, migration numbering or cache-TTL
arithmetic was changed by any 2026-10-03 ruling.**

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make; use
`.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test`
service of the `mko-bazuna-test` Compose project. `docker/entrypoint-test.sh` performs
**no** database setup: pytest-django provisions `test_mko_bazuna`, and the session-autouse
fixture in `src/backend/conftest.py` restores the reference data under advisory lock 111.

```powershell
# Alias, copied once per session
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

# Start the DB if it is not already up
docker ps --filter "name=mko-bazuna-test-db-"
$dc up -d db

# Fast gate (skips the nightly `seed` suite) - the default iteration command
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Targeted run
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k test_name" test
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_error_handler.py --tb=short" test

# Full suite (only when the change touches seeding or images)
$dc run --rm test

# Fresh schema - MANDATORY after BLOCK 8's migration, if Q4 option (b) is chosen
$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
```

**Three caveats that will silently produce a wrong result if ignored:**

- `--env-file .env.test` is **required**; without it compose aborts on `${POSTGRES_*?}`
  interpolation. **Never** substitute the `mko-bazuna-dev` project name for
  `mko-bazuna-test`.
- Setting `PYTEST_OPTS` **replaces** the defaults
  (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a
  targeted run loses xdist parallelism and DB reuse. `PYTEST_OPTS` is also **unquoted** in
  the entrypoint, so each token is word-split: `-k test_name` and bare paths work, quoted
  multi-token values do not. Never use `--override-ini=addopts=` — it strips
  `--import-mode=importlib`, which `pyproject.toml` requires.
- **Concurrent runs collide on the single `test_mko_bazuna` database.** If a gate goes red
  while other phase agents are running, **re-run it serially** before reporting it as a
  defect. Teardown races surface as `FATAL: database "test_mko_bazuna" does not exist`
  and `relation "..." does not exist`, not as product failures.

**Never make a real outbound network call** to Telegram, Google Translate, ECB or any
host. Every network interaction is faked at the module boundary — the patterns are listed
in §1.5.

### 1.2 Lint, typecheck, i18n

```powershell
uv run ruff check <path>            # lint
uv run ruff check --fix <path>      # auto-fix, including import sorting (I001)
uv run basedpyright <path>          # typecheck
uv run djlint src/backend/templates/   # only if a template changes
```

`uv run ruff check src/` is **green at `6413df5`**. Re-run it after **every** block, not
only at the end. Note that `except ConnectionInterrupted, redis.RedisError:` (the
unparenthesised form in `apps/categories/signals.py`) is **valid Python 3.14** under
PEP 758 — ruff accepts it, `ast.parse` accepts it, and **it must not be "fixed"** (C-10).

**i18n is part of DoD.** Every user-visible string is wrapped in `{% trans %}` /
`{% blocktrans %}` (templates) or `gettext` / `gettext_lazy` (Python). `msgstr` must be
**non-empty** for `ru` and `bs`; `en` may be empty (the msgid is English). `.mo` files are
gitignored and compiled at image build, at container start, and in the CI `i18n` job.

**No block in this plan introduces a user-visible string.** The only new text is
operator-facing log output (BLOCK 9's optional boot warning, BLOCK 1/2/5's warnings) and
documentation. An operator log line is not a translated string — confirm against
`apps/ads/tests/test_i18n_completeness.py` rather than assuming, and **do not** run a
wholesale `makemessages` (the locale files are shared with phases 03 and 14).

### 1.3 Git contract — one implementor, sequential, one commit per block

- **One Implementor at a time.** Never two. Never a background implementor.
- If a block is stopped mid-way, **resume the existing session**; do not launch a new agent.
- Each block is committed separately, explicitly staged: `git add <specific files>` —
  never `git add -A`, never `git add .`.
- Message form, matching the repo style: `"{type}({scope}): {description}"`, e.g.
  `fix(core): declare one cache-failure contract (09-API-001)`,
  `fix(telegram): fail open when the cache is unavailable (09-API-002)`,
  `fix(telegram): bound the transient replay budget (09-API-004)`.
  Every new citation is **cycle-scoped** (`09-API-nnn`, `09-VAL-nnn`), never a bare
  `API-nnn` / `EXT-nnn` / `SRH-nnn`.
- **Never** `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`,
  `--no-verify`, or any other history mutation. Never force-push.
- **Other agents are working in parallel and HEAD drifts.** Files you did not change
  appearing in `git status` is normal. **Never** revert, stash or `git checkout` a file
  you did not write. If a file you are about to edit already has uncommitted changes from
  another agent, **stop and report it** rather than clobbering it. This applies with extra
  force to `docs/ops/docker-deployment.md`, `docs/ops/rollback.md`,
  `config/settings/base.py`, `config/settings/prod.py`, `docker-compose*.yml` and
  `src/backend/apps/search/services/immediate_alerts.py` (§5.3).
- `.ai/audit/**` is **unmodifiable by mandate**. Nineteen tracked deletions exist in the
  working tree and are intentional. `git status --short .ai` must show **no new
  modifications** beyond those deletions, this plan's own file, and `.ai/tmp/`.
- Do not commit unless the block's instructions say to.

### 1.4 Standing project rules (restated for every block)

- **English only** — comments, logs, docstrings, error messages, docs.
- **No `print()`.** `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- Stack: Python 3.14 · Django 5.2 LTS (`>=5.2.16,<6.0`) · PostgreSQL 18 · aiogram 3.x ·
  native PostgreSQL FTS (no Elasticsearch). **Two processes, one DB:** web (gunicorn
  sync WSGI, HTMX MPA) and bot (aiogram, `django.setup()` + shared ORM).
  **Migrations run exactly once** before both start — a migration that must run in only
  one process is a defect.
- The bot FSM has no built-in PG storage: the ad dialog is persisted as an `Ad` row in
  `DRAFT` via the ORM.
- **Django ORM is the persistence layer.** Pydantic v2 is used **only** at system
  boundaries (bot input, settings schemas, `CSPReportPayload`, DTOs that already exist at
  a request edge). Business logic lives in `services/`; views stay thin adapters. A
  service-layer **result object** (Q4) is a `NamedTuple` / small dataclass, **not** a
  Pydantic model.
- **All schema changes via Django migrations**. Migration numbers are sequential **per
  app**; **never renumber or edit an existing migration**. `ads` → next free `0008_*`;
  `search` → next free `0003_*`. **Check the directory immediately before generating** —
  phases 03, 05, 06 and 08 are all landing migrations.
- **Fixed values via `StrEnum`** — never plain strings, dicts or lists. New backoff
  ceilings, window sizes and rate caps belong with the existing module-level `Final`
  constants. Phase 06 reserves new `AdvisoryLockId` members; **this phase allocates none.**
- i18n: every user-visible string wrapped; `ru` and `bs` `msgstr` non-empty.
- Small, focused modules and functions. **Composition over inheritance.** Follow existing
  patterns; **no new abstraction without strong justification**; no speculative redesign;
  no scope creep. Prefer the simple, obvious solution (project rule 5). **The one new
  module-level helper this plan sanctions is the cache read + window-bump pair in
  `apps/core/utils/cache.py`** — seven call sites, two tiers, is the justification.
- **`apps.*` must never import `telegram_bot.*`.** This is why BLOCK 2's helper lives in
  `apps/core/utils/cache.py` and not in `telegram_bot/services/rate_limit.py`. Three of
  the seven guards are web-tier and cannot import the bot's service.
- **Production code is king.** If a test conflicts with the architecture or the business
  logic, **fix the test** — and say which change and why in the commit body. This plan
  slates **four** unconditional test rewrites (§0.3) and constrains several more; each
  block names the test and the justification.
- **Docs in `docs/` stay in sync.** `docs/00-overview/doc-maintenance-rules.md`,
  `docs/99-agent/architecture.md`, `docs/99-agent/rules.md`, plus the ops runbooks BLOCKS
  5, 9, 11 and 15 must touch.
- **Secrets are governed by the phase-02 env allowlist and the `prod.py` deploy gate.**
  `config/settings/tests/test_env_allowlist.py` is the gate **any new secret must pass**,
  and it runs in **both** directions: every `.env` key must be allowlisted *and* every
  allowlisted key must be consumed. All nine email keys, `EMAIL_BACKEND`, `REDIS_URL` and
  `BOT_TOKEN` are **already** allowlisted — **no block in this plan requires a new env
  var**. If a block concludes otherwise (BLOCK 13's optional `_MAX_DELIVERY_THREADS`
  settings value does), the allowlist entry, the four `.env*.example` updates and the
  code land **in one commit** or that test fails in both directions.
- **Never use a line number as a task target** (`09-VAL-003`). Every target is a file plus
  a **semantic** anchor: a class, a method, a module-level constant, a named attribute, a
  function call, a URL route name, a config key, a compose service name, an nginx
  `location` block.

### 1.5 Test authoring standard for every block

Tests verify **logic and component interaction**, not implementation trivia. No test that
asserts a literal private name, a line number, a template-string substring, a column
count, or the mere presence of a symbol. Assert on **absence of danger** and on
**observable behaviour**.

**Never use the report's quoted log strings as assertions** (C-2). Assert behaviour: the
call does not raise, the value does not reach the log record, the request returns the
right status.

Good targets for this phase:

- a patched-raising cache leaves `/`, `/ads/<id>/` and `POST /login/issue/` returning their
  normal statuses, and each of the seven rate-limit guards returns "allowed";
- a rate-limited `contact_<ad_id>` trigger issues **no** `send_message`, and a burst from a
  single buyer against a single seller is refused at the per-seller cap **before** any
  `AnalyticsEvent` is written;
- a `retry_after=600` produces a **bounded total sleep**, and a `TelegramServerError` is
  replayed at all (demonstrated red against the current wiring first);
- an ad title containing `<b>`, `&` and `<a href="…">` produces an alert body in which
  **none** of the seller's markup is live — asserted on the rendered text, not on the
  absence of a helper;
- an edited exchange rate survives a second `load_exchange_rates` run, and editing a rate
  makes the very next `PriceNormalizer` read see the new value;
- a translation failure leaves `title_en` **NULL**, counts a `fallback` total, and a
  re-run of the command revisits the same row;
- a `/csp-report/` POST with a `document-uri` carrying a query string produces a log
  record containing neither the query string nor the referrer, while the full 200/400/405/
  422 response contract is unchanged;
- the nginx config test parses the **shipped** file and fails if a `location` block that
  reaches the database has no `limit_req` zone.

**Every block must copy one of these faking patterns** — never introduce a real socket
call, and never a new HTTP-faking dependency:

| What is being faked | The pattern to copy |
|---|---|
| **Cache outage** | monkeypatch the **module-level `cache` name** with a `MagicMock` whose method raises `django_redis.exceptions.ConnectionInterrupted(None)` — the exact shape of `src/telegram_bot/tests/test_update_id_dedup.py::test_redis_unavailable_fail_open` |
| **Telegram outbound (bot)** | the `_FakeBot` class with an async `__call__` in `src/telegram_bot/tests/test_error_handler.py`. **No `Bot` is ever constructed** |
| **Telegram outbound (backend)** | `patch("apps.search.services.immediate_alerts.Bot", return_value=mock_bot)` with `mock_bot.send_message = AsyncMock(...)` and `mock_bot.session.close = AsyncMock()`. **The patch target is the `Bot` symbol in each module** — any consolidation breaks both patch targets |
| **Translation upstream** | `patch` of the `translate_text` symbol **in the command's import path**, plus the `_reset_translation_state` fixture for breaker state |
| **Email** | the locmem backend forced by test settings; `django.core.mail.outbox`; `patch("telegram_bot.services.support_delivery_email._send_mail", side_effect=RuntimeError(...))` |
| **nginx / compose structure** | `Path.read_text()` + a brace-depth `_location_block` helper, as `src/backend/tests/test_nginx_config.py` already does |
| **Settings subprocess** | `_prod_env_overrides(...)` / `_dev_env_overrides(...)` + `python -c "from django.conf import settings; …"` in a subprocess. **The `config/settings/tests/` package must be run whole** — `test_settings_secrets.py` and `test_prod_logging.py` share a cross-module import |

Fixtures are canonical in `src/backend/conftest.py`: `seller` (900000001), `user`
(900000002), `category`, `city`, and
`create_test_ad(user, category, city, *, status=AdStatus.PUBLISHED, **kwargs)`.
`src/telegram_bot/tests/conftest.py` redefines these as an **async** `user`; bot tests
cannot import the backend conftest.

**Do not edit `src/backend/conftest.py`.** It is the most contended file in the repository.
If a block appears to need a new fixture, that is a signal the test is over-fitted.

### 1.6 Task shape for every block

Each block's implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic
`targets` with `type` / `name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section` / `source_blocks`, and an `extra_context` block
carrying the block's binding constraints and its open gate verbatim. Verification is
**inline** for low/medium-risk blocks (the Implementor runs `tests_to_run` and checks
`acceptance_criteria`); a **separate Validator task is required for every HIGH block**,
for every block that ships a migration, and for every block whose acceptance depends on a
decision the Implementor was told not to make.

---

## 2. Scope decisions table (acceptance contract for execution)

| ID | Disposition | Block | Final severity | One-line reason |
|---|---|---|---|---|
| `09-API-001` + `09-VAL-007` | **implement — gated on Q12.** One `cache_get_or_none()` in `apps/core/utils/cache.py`; the cache **read** moves inside the existing `try`; the cache **write** half is decided by Q12. Fallback strings unchanged | **1** | **HIGH** | Reproduced at the HTTP layer: `/`, `/search/`, `/privacy/` all return 500 while `/health/` correctly reports `cache: fail`. The docstrings promise a fallback *"if the DB **or cache** is unavailable"* and half of it is unimplemented. `09-VAL-007` is the unreported write half |
| `09-API-002` | **implement — widened from 4 to 7 guards. Gated on Q9.** One shared fail-open window helper in `apps/core/utils/cache.py`, adopted by **all four** bot guards **and all three** web-tier guards. The `ValueError` reset path stays byte-identical | **2** | **HIGH** | A bot-only helper leaves three web-tier 500s live. `ConnectionInterrupted` derives from `Exception`, not `ValueError`, so it escapes. An `apps.*` → `telegram_bot.*` import is **forbidden** — the helper's home is forced |
| `09-API-003` | **implement as one unit with the per-seller cap.** Per-buyer (≈5 / 600 s) **and** per-seller (≈20 / 3600 s), both built on BLOCK 2's helper — not an eighth copy of the idiom | **3** | **HIGH** | The deep link is unrated, the identifier space is a dense integer, the link renders on the anonymously reachable ad detail page, and `AccountStateMiddleware` lets a browse-only account reach it. **The per-seller cap protects the expensive part** — the outbound message to the seller — and an attacker controls the buyer, not the seller. Per `09-VAL-005` the cap is a **prerequisite of shipping at all** |
| `09-API-004` + `09-VAL-004` | **implement atomically across `retry.py`, `main.py` and `test_error_handler.py`.** Cap the backoff and bound by **total budget**; register `ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS)`; delete the unreachable `isinstance` guard; return `False` on exhaustion with a drop counter. **Three** tests change, not one | **4** | **HIGH (highest execution risk in the phase)** | `sleeps=[300, 300, 300]` for one flood response, with `handle_as_tasks=True` and no concurrency limit, turns N concurrent 429s into 3N replayed calls — the opposite of what flood control asks. The drop is then reported as **success**. The fix is right and the suite will go red without its test change: that is the hazard |
| `09-API-005` | **implement.** `media_limit` zone in **both** nginx configs (each has its own `http{}`), an application-level limiter using the same client-IP policy `listings` already uses, and a structural test in `test_nginx_config.py`. The duplicated `AdImage` query is a **bonus, not a requirement** | **10** | **MEDIUM** | `/media/` is the only anonymous, DB-backed path with neither a proxy zone nor an app limiter. `/static/` is unrated and harmless (whitenoise). `nginx.dev.conf` is **thinner** than `nginx.conf` — a prod-only fix leaves dev uncovered |
| `09-API-006` | **implement — gated on the shape.** Exactly one shape applied to **both** modules and **all four** send sites (initial + retry in each). No new user-visible strings, so i18n is not engaged | **6** | **MEDIUM** | One seller's `<` in a title kills the whole digest for **every recipient batch** (≤10 ads each), `SavedSearchNotification` rows are written **before** the send, and `TelegramBadRequest` is permanent with no retry. Invisible to seller and buyer alike |
| `09-API-007` | **implement part (a) only — gated on Q4.** Minimal by default (compare result to source, leave the column `NULL`, count a `fallback` total, `logger.warning`, `--limit`). The status-object option changes `translate_text`'s return type, breaks the whole `test_translation.py` suite and needs a migration | **8** | **MEDIUM** | The degradation path returns a **value** where the caller needs a **status**. The nullability-derived selection query is why it is unrecoverable: once the source is written into `title_en`, the row never matches again. Part (b) is **rejected on evidence** (C-5) |
| `09-API-008` + `09-VAL-006` | **implement.** `get_or_create` instead of `update_or_create`; wire the already-correct `invalidate_rate_cache()` (gated on Q13); correct **three** false capability claims (`migration-workflow.md`, the command's docstring, `price_normalizer.py`'s docstring). No migration needed. **Must land in the same wave as BLOCK 1** | **5** | **MEDIUM** | Silent, recurring, operator-facing **data loss**: an admin correction is reverted at the next deploy with no log line and no record of the previous value, and `price_normalized_eur` is not recomputed, so the rate table and every derived price diverge. The false claim is in the runbook an operator follows *during an incident* |
| `09-API-009` | **implement — Q1 RESOLVED 2026-10-03: option (b), a LOUD WARNING, not a boot gate.** The reason must be corrected at **all six** comment sites either way, and the compromise-response procedure with them. The guard is **replaced by** the warning; it is **not** justified in place | **9** | **MEDIUM (P2 priority — but first in decision order)** | A fail-open, single-purpose, best-effort integration is a **hard boot gate for the entire system**, justified by a rationale the codebase does not support, and the fiction is repeated inside the compromise-response procedure. **The owner chose the warning**, so the finding's remedy is now decided: the cost of that choice is that a host which never noticed the warning loses support escalations, so the warning must be loud and the runbook must say what is lost |
| `09-API-010` + `09-API-014` | **implement as one nginx/config change — gated on Q14.** `:80` `server_name`; the unsatisfiable `Bearer` challenge dropped; `reject_ad` / `ban_user` → `@require_POST`; a Django-side `/metrics` gate (gated on Q2, boundary-checked against phase 15); `X-Forwarded-Host` on every proxied location; `ssl_protocols` / `ssl_session_cache` pinned | **11** | **LOW** | Five small contract observations that together are the maintenance tax of an API layer grown by accretion. `(4)` is one network-policy line from a public metrics scrape. **The LOW grade must not suppress the fix** — the missing `server_name` is a real misconfiguration trap |
| `09-API-011` | **implement the role-conditional guard + the `env_file` removal. Removing the three explicit `BOT_TOKEN:` compose lines alone is a NO-OP (C-3)** | **14** | **MEDIUM** | Eight Django containers hold the credential via `env_file` + the `.env` bind mount, and the root cause is a **settings guard**, not a compose line: any process importing `prod.py` must hold the token to satisfy a guard it never exercises. Two `Bot` sites are active (C-9). The report's "Effort S" does not price the `test_settings_secrets.py` rewrite |
| `09-API-012` | **CHANGED 2026-10-03 — now IMPLEMENTED here, not routed.** Q5 is resolved (redact at write), so BLOCK 13 applies `redact_free_text()` in `save_search` **and adds a test**. The *"unless the owner rules…"* clause is **removed**. Still **not** phase 09's: `apps/search/migrations/` and the PII policy statement. **Deviation from plan (P1):** code uses `redact_free_text` instead of `redact_search_query` — same masks, no truncation, chosen for the `VARCHAR(200)` column | **13** | MEDIUM (was "absorbed"; now partly implemented) | Fixing the view alone would let the tracker record *"search PII is handled"* while the indexed dedup key still holds the raw query. The **owner decided**, so the view fix is a bounded one-line-plus-test change — but `save_search.py` is **also phase 08 BLOCK 8's file** (§5.3) |
| `09-VAL-002` | **Q6 RESOLVED 2026-10-03 — key `query_normalized` on the REDACTED form.** The *decision* is closed; the **follow-up data migration** and the explicit dedup-semantics statement are **routed to phase 06** (PII policy owner) because `apps/search/migrations/` is three-way reserved | **13** (decision) · phase 06 (migration) | MEDIUM → **decision closed, migration outstanding** | `query_normalized` stores the raw query on **both** tables the project believes it redacts, and migration `0002_redact_search_queries` preserved it on purpose. The owner has now ruled; what remains is the data repair, and it is not this plan's file |
| `09-API-013` | **implement — gated on Q7.** A done-callback that retrieves `future.exception()`; a backpressure gate or a settings-tunable thread count; a **worker-side** shutdown hook; the `AiogramError`-only catch in `_run_send` raised to `Exception` with `logger.exception` | **7** | **MEDIUM** | The result is never inspected, the backlog is unbounded, and `preload_app = True` means an import-time hook lands in the gunicorn **master** (C-7). Latent today (`IMMEDIATE_ALERTS_ENABLED=false`); live the moment an operator opts in — **fix before flipping the flag** |
| `09-API-015` | **implement.** Log only the fields an operator acts on, drop `document-uri`'s query string and `referrer`, tighten the nginx zone. The full 200/400/405/422 response contract is unchanged | **12** | **LOW** | An unauthenticated caller can push 10 r/s of arbitrary JSON, each producing a full-dict INFO line, and page URLs routinely carry buyer search text. **The PII-minimisation policy half is phase 06's** (`06-PII-102`); phase 09 owns the ingress field selection and the zone. Do **not** add `@require_POST` to this view while BLOCK 11 standardises its siblings |
| `09-API-016` | **implement.** `IMAGE_TAG` fails loudly instead of defaulting to `latest`; third-party datastore tags pinned; **`TLS_CERT_PATH` DEFERRED (P4)** — `.env.prod.example` explicitly marks the decision deferral; `docker-compose.prod.yml:109` keeps `${TLS_CERT_PATH:-/etc/nginx/certs}`. The in-repo path is a candidate, not a default | **15** | **LOW (P4)** | `docker-compose pull` on two hosts running "the current compose file" can move **the entire application** to different code with no repository change — the higher-consequence half the auditor missed. The `${TLS_CERT_PATH:-…}` default mounts an empty directory rather than failing, so a missing export yields a crash-looping proxy whose compose output looks successful |
| `09-API-017` | **implement the counter half here; the sanitiser swap is reviewed against phase 06.** `translation_requests_total`, `translation_fallback_total`, `translation_circuit_open` on the existing `/metrics`; ad text redacted-then-truncated in `translate_text`'s log sites; a module-docstring note on which sanitiser applies to which text | **16** | **LOW** | The breaker being open means **every ad ships untranslated**, and that state has no counter, no gauge and no threshold. The DEBUG success line also logs the **translated output**, which survives masking the input alone. `django_prometheus` is already wired and multiprocess counters are already the established pattern |
| `09-VAL-001` | **respected as a boundary — no merge, no re-file** | §5 | MEDIUM (process) | API-008 ↔ `03-DB-008` and API-009 ↔ `02-CFG-004` are adjacent pairs with **different mechanisms and different fixes**. They compose; fixing either does not fix the other. Phase 02 owns the email *backend* selection, phase 09 owns the *existence-of-consumers* question — action both in one pass, report as two findings |
| `09-VAL-002` | **routed to phase 06 / phase 08 via BLOCK 13 — it has no owner today** | **13** | MEDIUM (product defect) | `query_normalized` stores the raw query on **both** tables the project believes it redacts, and migration `0002_redact_search_queries` preserved it on purpose. The correct owner is a **storage-layer decision**, not a missing call at a view |
| `09-VAL-003` | **honoured as a binding constraint — symbol anchors only** | §1.4 | MEDIUM (process) | Every line anchor in the source report is advisory and several are wrong. Remediation keyed to them lands in the wrong place |
| `09-VAL-004` | **honoured — BLOCK 4 is one atomic change** | **4** | MEDIUM (process) | One in-repo dependency asserts the wrong return contract, and the test helper hard-codes the too-narrow `ExceptionTypeFilter`, so the new sibling-replay test would otherwise pass **vacuously**. The report names one test; there are **three** |
| `09-VAL-005` | **honoured — this is the corrected Wave-1 ordering** | §4.1 | MEDIUM (process) | API-002 and API-003 ship in **separate** releases. The report's same-release coupling conflates a guard that fails *closed* with a guard that fails *open*: on `contact_<ad_id>` no limiter exists, so API-002 cannot "remove" a guard that was never there, and shipping API-003 alone is a pure tightening with no failure mode |
| `09-VAL-006` | **honoured — BLOCKS 1 and 5 land in one wave** | **1**, **5** | MEDIUM (process) | Both define "what a cache read does on failure". Split, the rate cache serves a pre-boot value for up to 5 minutes with no invalidation, and the next developer finds a `cache_get_or_none` that does not exist yet |
| `09-VAL-007` | **implement inside BLOCK 1** — gated on Q12 | **1** | MEDIUM (rollout) | A Redis **write** failure returns the fallback string after a **successful** database read, and the warning says *"SiteConfig unavailable"* |
| `09-VAL-008` | **recorded as evidence-basis corrections; no work item** | §0.4, §6.3 | LOW (evidence) | Four `except ValueError`-only bump helpers, not three, and **two of their receivers are unguarded**; `apps/core/utils/cache.py` has **fifteen** call-shaped helpers, not ten |
| `09-VAL-009` | **implement inside BLOCKS 6 / 7 — gated on Q8** | **6**, **7** | MEDIUM (availability) | The alert path has a **second, independent** uncapped `retry_after` sleep, and a live test pins its exact value |
| **`Q1` (`EMAIL_HOST` mandatory vs warning)** | **RESOLVED 2026-10-03 (Product Owner) — LOUD WARNING; no `ImproperlyConfigured`** | **9** | — | Decided on the owner's own severity. BLOCK 9 ships the warning plus all six comment-site corrections; `test_deploy_check_env_parity.py`'s guard taxonomy loses one entry in the same commit. See §0.7 |
| **`Q2` / `Q3` (the Django-side `/metrics` gate)** | **GATED + pre-block step** | **11** | — | The hardening is correct; the mechanism is a design choice adjacent to phase 15, and the report's impact model is **inverted** (C-4) |
| **`Q4` (translation-failure signal shape)** | **GATED** | **8** | — | S vs M, plus a migration whose number is contended with phase 05 |
| **`Q5` (`SavedSearch.query` redaction)** | **RESOLVED 2026-10-03 (Product Owner) — redact at write; phase 09 implements it** | **13** | — | Was "ROUTED, NOT DECIDED". Now a bounded production change in BLOCK 13 plus a test |
| **`Q6` (`query_normalized` storage key, `09-VAL-002`)** | **RESOLVED 2026-10-03 (Product Owner) — key on the redacted form** | **13** | — | Was "ROUTED, NOT DECIDED". The decision is closed; the follow-up **data migration** is **phase 06's** (PII policy owner), because `apps/search/migrations/` is three-way reserved |
| **`Q7` (where the shutdown hook runs)** | **GATED** | **7** | — | With `preload_app = True` a hook in the wrong process is a no-op that looks like a fix |
| **`Q8` (the alert-path retry ceiling)** | **GATED** | **6**, **7** | — | A cap above the pinned fixture is untested; below it, the test changes **in the same commit** |
| **`Q9` (one change or per module for the seven guards)** | **GATED** | **2** | — | One shared helper is the right architecture; per-module is safer to land, and four phases have claims on `apps/*` |
| **`Q10` (one outbound gateway)** | **GATED as a scope question; not assumed** | §4.5 | — | It would collapse three findings into one owner but breaks two test patch targets and crosses the backend/bot boundary. Recorded as a follow-on (§6.2) |
| **`Q11` (does a live rate feed exist?)** | **GATED — product** | **5** | — | A live ECB feed is a **new capability**, not a doc fix. BLOCK 5's fix is correct either way; the feed is routed, not built |
| **`Q12` (does the cache write leave the `try`?)** | **GATED** | **1** | — | Changes when the cache is primed and whether a successful DB read can be masked |
| **`Q13` (where is `invalidate_rate_cache()` wired?)** | **GATED** | **5** | — | An implemented, documented, never-called helper reads as done — worse than an absent one |
| **`Q14` (the `:80` redirect shape)** | **GATED** | **11** | — | The only change in the phase that can break a working deployment |
| **Advisory: "route every outbound integration through one gateway"** | **declined as a work item** | §6.2 | — | High value, wrong phase. It is a cross-tier architectural change with two test-patch-target breaks, and folding it into any single finding would misattribute a large change to a small defect. Q10 routes it |
| **Advisory: "one cache-failure policy for the whole project, written down once"** | **adopted** | **1**, **2**, **16** | — | The single highest-leverage structural change in the phase, and it is a **documentation convention plus two helpers**, not new machinery |

---

## 3. Execution blocks

Sixteen blocks: **fifteen implementation blocks and one block (13) that was a decision/handoff
block and became a bounded implementation on 2026-10-03** (the `09-API-012` view redaction, with
`09-VAL-002`'s data migration recorded as a phase-06 obligation). **One Implementor, strictly
sequential, one commit per
block** (§1.3).

**Eleven blocks carry a labelled decision required before implementation gate** —
BLOCKS 1, 2, 5, 6, 7, 8, 9, 10 (shape), 11, 13, 14. A gated block does not start until the
answer is written down; **the Implementor is forbidden from choosing an option** (§1.4,
§8.1). BLOCKS 3, 4, 12, 15 and 16 are ungated in-plan (BLOCK 4 carries a gate on the
budget shape and BLOCK 15 carries one on the pin policy, both stated inside the block).
**The Product Owner closed three of these on 2026-10-03** — Q1 (BLOCK 9), Q5 and Q6
(BLOCK 13). Those blocks now carry their resolved ruling; the remaining eight keep their
2026-10-01 resolutions verbatim.

BLOCKS 1, 2, 5, 9 and 13 are prepared in parallel by the Auditor / Researcher while other
blocks run, but the **serial execution order is 1 → 16** (§4.1): BLOCKS 1 and 5 are one
wave by `09-VAL-006`, and BLOCK 3 consumes BLOCK 2's helper.

### BLOCK 1 — One cache-failure contract, declared once (09-API-001, 09-VAL-007, 09-VAL-006 half)

| | |
|---|---|
| **Findings owned** | `09-API-001` (HIGH) · `09-VAL-007` (Planner, MEDIUM) · half of `09-VAL-006` |
| **Depends on** | **nothing in-plan** |
| **Blocks** | BLOCK 5 (same wave, `09-VAL-006`); the cache helper BLOCK 2 adds sits beside it; BLOCK 16's docstring note |
| **Priority** | **P0 — blocks rollout** |
| **Risk level** | **HIGH** — availability defect on every rendered page, in both tiers |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** The Researcher settles Q12's shape; the Planner records the option; the Validator confirms the HTTP-level 200s and the unchanged fallback strings |

**Why this is first.** A Redis blip currently returns **500** on `/`, `/search/` and
`/privacy/` while `/health/` correctly reports `cache: fail` — the probe fails *open* and
everything behind it fails *hard*. It is also the anchor BLOCK 5 must ship with.

**Decision required before implementation — Q12: what happens to the cache write?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Move only the **read** inside the existing `try`; leave `set_cached_*` inside it | **Gains:** the smallest diff; the fallback string is returned on any cache problem. **Costs:** a Redis **write** failure still masks a **successful** database read and still logs *"SiteConfig unavailable"* — a wrong diagnostic that misleads the next responder during exactly the incident the block is fixing |
| **(b)** | Move the read inside the `try`; move the **write** **out** of it, guarded by its own `except` that logs at DEBUG and returns the value it already has | **Gains:** the function returns the **database's** answer whenever the database answered; the warning line becomes true; a cache that is read-only degraded still serves correct content. **Costs:** slightly more code; the cache is not primed when the write fails (correct — it will be primed on the next successful read); the write's failure must be logged at a level that does not page anyone |
| **(c)** | Read through the shared helper, write through a shared `cache_set_best_effort`, both in `apps/core/utils/cache.py` | **Gains:** the contract is declared once and the other four triads in the module can adopt it later. **Costs:** a second helper with no second consumer today — the weakest justification in the plan, and close to a speculative abstraction (rule 5) |

**The Implementor may not choose.** Whatever is chosen, the commit body names it. **(b) is
the option the evidence supports**, but the diagnostic consequence of (a) is exactly the
kind of thing that costs an hour in an incident.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/utils/cache.py` | the new `cache_get_or_none` helper; the module docstring (it currently claims only *"cached singleton access for ModerationCriteria"*) | **The shared home.** Fifteen call-shaped helpers already live here across five triads. **State the fail-open policy in the module docstring** — that is advisory recommendation #1, and it is the only structural change in the phase |
| `src/backend/apps/core/services/site_config.py` | `get_site_name`, `get_bot_username` | Keep the fallback strings **`"Bazuna"`** and **`"bazuna_bot"`** byte-identical: the site header and every bot deep link depend on them. The two async wrappers are pass-throughs — no change needed |
| `src/backend/apps/core/tests/test_site_config.py` | `test_get_site_name_reads_from_cache` | **Must stay green unchanged.** It asserts `SiteConfig.get_singleton` is *not* called on a cache hit — a naive "always try the DB first" fix breaks it |
| `src/backend/apps/core/tests/test_site_config_bot_username.py` | the `get_bot_username` mirror | Same |
| `src/backend/apps/core/tests/` (new module if cleaner) | the HTTP-level regression | Do **not** add to `conftest.py` |

**Binding constraints**

1. **The cache read moves inside the `try`; the write's placement follows Q12.** Both
   halves must be decided — a read-only fix leaves `09-VAL-007` open.
2. **Do not change the fallback strings.** Do not change the readiness probe
   (`apps/core/views.py::readiness_check` already reports 503 with `cache: fail`
   correctly — it is the *control*, not the defect).
3. **Follow the existing fail-open precedent**: `telegram_bot/middlewares/update_id_dedup.py::UpdateIdDedupMiddleware.__call__`
   catches `(ConnectionInterrupted, redis.RedisError)` and logs a warning. Reuse that
   exception tuple; `django_redis` and `redis` are already imported directly elsewhere in
   the tree, so **no new dependency is introduced**.
4. **Do not set `IGNORE_EXCEPTIONS` in `CACHES` and do not pin
   `CACHES["default"]["TIMEOUT"]`.** The first silently changes every cache read's failure
   semantics across the whole project; the second would silently extend the lifetime of
   every cache entry in the system. Neither is this fix.
5. **The helper must be importable from both tiers** with no dependency reversal: it lives
   in `apps/core/utils/cache.py` precisely because `apps.*` may never import `telegram_bot.*`.
6. **Assert the red case first.** The HTTP-level regression is written against the
   *current* code and must be demonstrated **red** before the fix lands (U1).
7. **`set_cached_*` is called on the success path.** Whichever option Q12 selects, the
   cache-miss path must still prime the cache — otherwise the fix trades a 500 for a
   permanent cache miss and a per-request database read.

**Implementor task**

```yaml
id: task_09_b01_cache_contract
title: "Declare one cache-failure contract and route the site-config read through it (09-API-001)"
priority: high
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 1 - One cache-failure contract, declared once"
source_blocks: ["BLOCK 1"]
description: >
  apps/core/services/site_config.py::get_site_name and ::get_bot_username execute the
  cache read BEFORE the try block, and apps/core/utils/cache.py's getters are bare
  cache.get() calls with no exception handling - while both docstrings promise a fallback
  "if the DB or cache is unavailable". Under a Redis outage every rendered page returns
  500 while /health/ correctly reports cache: fail. A SECOND, unreported half: the
  set_cached_* writes sit INSIDE the same try, so a cache WRITE failure returns the
  fallback string after a successful database read and logs "SiteConfig unavailable",
  which is a false diagnostic.
goals:
  - "make a cache outage leave every rendered page serving, in both tiers"
  - "state the project's cache-failure policy once, in the shared module"
  - "keep the fallback strings and the cache-hit behaviour byte-identical"
  - "make the logged diagnostic true in both failure halves"
files:
  - path: "src/backend/apps/core/utils/cache.py"
    targets:
      - type: module
        name: cache
      - type: function
        name: cache_get_or_none
  - path: "src/backend/apps/core/services/site_config.py"
    targets:
      - type: function
        name: get_site_name
      - type: function
        name: get_bot_username
  - path: "src/backend/apps/core/tests/test_site_config.py"
    targets:
      - type: function
        name: test_get_site_name_reads_from_cache
  - path: "src/backend/apps/core/tests/test_site_config_bot_username.py"
    targets:
      - type: module
        name: test_site_config_bot_username
changes:
  - action: modify_code
    description: >
      Add cache_get_or_none(key) to apps/core/utils/cache.py. It swallows
      ConnectionInterrupted and redis.RedisError, logs at the level the
      UpdateIdDedupMiddleware precedent uses, and returns None. Update the module
      docstring to state the project's cache-failure policy in one place - this is
      advisory recommendation #1 and it is a documentation convention, not machinery.
      Move the cache read in get_site_name and get_bot_username inside the existing
      try. Apply the Q12 option to the set_cached_* write the Researcher recorded.
    code_hint: |
      def cache_get_or_none(key: str) -> object | None:
          """Read ``key`` from the shared cache, returning None when it is unreachable.

          The project-wide policy: a cache read never raises into a request path. A
          cache outage degrades to "no cached value", never to a 5xx. Same policy and
          same exception tuple as
          telegram_bot/middlewares/update_id_dedup.py::UpdateIdDedupMiddleware.
          """
          try:
              return cache.get(key)
          except (ConnectionInterrupted, redis.RedisError):
              logger.warning("Cache read failed for %s; treating as a cache miss", key)
              return None
  - action: add_test
    description: >
      An HTTP-level regression: with every cache operation patched to raise
      ConnectionInterrupted, GET / , an ad detail page and POST /login/issue/ all
      return their normal statuses, and /health/ still returns 503 with cache: fail.
      Assert it RED against the current code before applying the fix.
acceptance_criteria:
  - "with the cache patched to raise, GET / returns 200, an ad detail page returns 200, and POST /login/issue/ returns its normal status - not 500"
  - "GET /health/ still returns 503 with checks.cache == 'fail'"
  - "get_site_name() returns 'Bazuna' and get_bot_username() returns 'bazuna_bot' under a cache fault and under a database fault - byte-identical to today"
  - "a cache HIT still short-circuits: SiteConfig.get_singleton is not called (test_get_site_name_reads_from_cache passes UNCHANGED)"
  - "a cache MISS still primes the cache - the write still happens on the success path under the chosen Q12 option"
  - "test_site_config.py and test_site_config_bot_username.py pass UNCHANGED"
  - "the apps/core/utils/cache.py module docstring states the project-wide cache-failure policy in one place"
  - "the commit body names the Q12 option and, for option (b), states that the write's failure is logged at DEBUG"
  - "no IGNORE_EXCEPTIONS, no CACHES TIMEOUT change, no new dependency, no new user-visible string"
tests_to_run:
  - "src/backend/apps/core/tests/test_site_config.py"
  - "src/backend/apps/core/tests/test_site_config_bot_username.py"
  - "src/backend/apps/core/tests/test_context_processors.py"
  - "src/backend/apps/core/tests/test_health_contract.py"
```

**Tests required**

1. **The outage** — patched-raising cache → `/`, an ad detail page and
   `POST /login/issue/` all keep their statuses. Assert on the **response**, not on the
   helper's return value.
2. **The probe** — `/health/` still returns 503 with `cache: fail`. This is the control
   that proves the fix did not simply silence the outage.
3. **The fallback strings** — under a cache fault *and* under a database fault, both
   functions return their documented constants. A refactor that "improves" the default
   breaks the site header and every deep link.
4. **The cache-hit short circuit** — `test_get_site_name_reads_from_cache` unchanged. It is
   the tripwire against a "always hit the database first" fix.
5. **The cache-write half (Q12)** — a cache that raises on **write** but not **read**
   returns the **database's** value under option (b), or the fallback under option (a).
   Whichever the option is, the test asserts it, so the decision is enforced rather than
   assumed.

**Risk and rollback**

- *Implementation risk:* **changing the fallback strings**, which would break the site
  header and every bot deep link. Mitigation: binding constraint 2 and test 3.
- *Rollout risk:* **silencing the outage signal**. Mitigation: `/health/` is asserted
  unchanged; the helper logs at WARNING, never silently.
- *Regression risk:* a cache that is permanently unreachable turning every request into a
  database read. Mitigation: test 5 asserts the write still happens; the readiness probe
  reports the outage so the condition is visible.
- *Rollback:* a straight revert restores the 500s. State that plainly in the commit body.
- *Cross-phase:* BLOCK 5 ships in the **same wave** (`09-VAL-006`), and BLOCK 2 adds a
  second helper to the **same module**.

---

### BLOCK 2 — One fail-open window helper for all seven request-path guards (09-API-002)

| | |
|---|---|
| **Findings owned** | `09-API-002` (HIGH) — **widened from four guards to seven** |
| **Depends on** | **nothing in-plan** (shares the module with BLOCK 1; see §4.2 for the soft edge) |
| **Blocks** | BLOCK 3 (reuses this helper; must **not** add an eighth copy of the idiom) |
| **Priority** | **P0** |
| **Risk level** | **HIGH** — a behaviour change on seven guards across two tiers, with two pinned test suites |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** The Researcher re-derives the seven sites (U4, U5) and audits for any eighth; the Planner records the Q9 commit shape; the Validator confirms all seven fail open and that every `ValueError` reset path is unchanged |

**Why the widening matters more than the fix.** Three of the seven guards are **web-tier**
— `contact_rate_limit.py` (used by the listings page), `search/services/rate_limit.py`
(autocomplete) and `login_rate_limit.py` (`POST /login/issue/`). A helper scoped to
`telegram_bot/services/rate_limit.py` leaves three 500s live, and **`apps.*` may never
import `telegram_bot.*`** — so the helper's home is forced, not chosen.

**Decision required before implementation — Q9: one change or per module?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **One commit**: the helper plus all seven adoptions | **Gains:** no half-migrated contract; the policy is declared once and every caller is converted in the same change; the eight-copy duplication is removed in one review. **Costs:** one commit touches **six** files across **four** apps and two tiers — the largest blast radius in the phase; phases 02 / 03 / 06 / 08 have claims on three of the files (§5.3), so contention must be sequenced by the Coordinator |
| **(b)** | **Helper first**, then the four bot guards, then the three web guards as separate commits | **Gains:** each commit is independently reviewable and revertible; the web-tier half can wait for phase 08's client-IP trust item to settle. **Costs:** two or three commits where a policy is half-adopted; a reader of a single file cannot see the contract |
| **(c)** | **Per-module local `except` widening**, no shared helper | **Gains:** lowest risk, no cross-app import at all. **Costs:** the report rejects it explicitly — it is the "three patches leave the class intact" outcome, and it keeps the duplication that generated the defect |

**The Implementor may not choose.** The commit body names the option and the contention
sequence.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/utils/cache.py` | the new window-bump helper | **Beside `cache_get_or_none` from BLOCK 1.** Plain `def` — **not** `async def` — because the bot guards call it inside `sync_to_async` |
| `src/telegram_bot/services/rate_limit.py` | `check_login_rate_limit`, `check_contact_start_rate_limit`, `check_support_message_rate_limit`, `check_upload_rate_limit` | Keep the `(user_id, limit=…, period=…)` signatures and the `@sync_to_async` decorator — handlers `await` them and `test_rate_limit_functions_are_async_callable` pins the coroutine shape |
| `src/backend/apps/core/services/contact_rate_limit.py` | `check_deep_link_render_rate_limit` | **Web tier — not in the report.** 60 / 600 s |
| `src/backend/apps/search/services/rate_limit.py` | `rate_limit_check` | **Web tier — not in the report.** Search autocomplete |
| `src/backend/apps/users/services/login_rate_limit.py` | the function containing its `cache.incr` | **Web tier — not in the report.** `POST /login/issue/` |
| `src/telegram_bot/tests/test_rate_limit_service.py` | `TestContactStartRateLimit`, `TestSupportMessageRateLimit` | Threshold semantics (5 allowed, 6th `False`, per-user isolation, custom `limit`/`period` kwargs). A fail-open change keeps all green — none simulates a cache fault |
| `src/backend/apps/core/tests/test_contact_rate_limit.py` · `src/backend/apps/users/tests/test_login.py` | the `cache.incr` → `ValueError` reset tests | **Tripwires.** The `ValueError` branch must stay reachable **and** keep its reset behaviour **byte-identical** (`cache.set(key, 1, timeout=…)`, return `True`, counter back to 1) |

**Binding constraints**

1. **Keep the `ValueError` reset path byte-identical.** `cache.add` then `cache.incr` is
   the existing primitive; do **not** swap it for a different atomic operation. Two test
   files pin the reset semantics and the LocMemCache behaviour they rely on.
2. **The helper must be a plain `def`.** The four bot guards are `@sync_to_async`; the
   three web guards are sync. A single sync helper serves both without a dependency
   reversal.
3. **Fail open with a `logger.warning` naming the key**, never silently, and never
   `logger.exception` — an outage is not a stack trace.
4. **Do not add an eighth copy** of the idiom, and do not add it to BLOCK 3's new guards
   separately — BLOCK 3 reuses this helper.
5. **The `ValueError`-only version-bump helpers are OUT of scope** (§6.3). They are the
   invalidation path, not the guard path. `09-VAL-008` records that two of their signal
   receivers are unguarded; that is a separate finding, not this one.
6. **Do not change any key format, limit value or period value.** This block changes what
   happens when the cache is unreachable, not the budgets.
7. **Assert red first** for the three web-tier guards (U5) — the report never proved they
   raise.
8. **The helper's return contract is "allowed".** A caller cannot distinguish "under the
   limit" from "cannot tell", and that is the documented, intended fail-open policy — the
   same one `UpdateIdDedupMiddleware` already documents.

**Implementor task**

```yaml
id: task_09_b02_fail_open_window
title: "One fail-open rate-limit window helper, adopted by all seven request-path guards (09-API-002)"
priority: high
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 2 - One fail-open window helper for all seven request-path guards"
source_blocks: ["BLOCK 2"]
description: >
  Seven request-path rate-limit guards wrap cache.add + cache.incr in
  `except ValueError` only. django_redis.exceptions.ConnectionInterrupted derives
  from Exception, not ValueError, so a Redis outage escapes and every guard raises
  instead of failing open - the opposite of the policy
  telegram_bot/middlewares/update_id_dedup.py::UpdateIdDedupMiddleware documents.
  Four guards are in telegram_bot/services/rate_limit.py (reported); THREE MORE ARE
  WEB-TIER AND WERE NOT IN THE REPORT: apps/core/services/contact_rate_limit.py
  (used by the listings page), apps/search/services/rate_limit.py (autocomplete)
  and apps/users/services/login_rate_limit.py (POST /login/issue/). A helper scoped
  to telegram_bot would leave three web-tier 500s live, and apps.* must never import
  telegram_bot.*, so the helper belongs in apps/core/utils/cache.py.
goals:
  - "make every request-path rate-limit guard fail open on a cache outage"
  - "remove the four-copy (in fact seven-copy) duplication"
  - "leave the ValueError reset path byte-identical"
  - "leave every key format, limit and period unchanged"
files:
  - path: "src/backend/apps/core/utils/cache.py"
    targets:
      - type: module
        name: cache
  - path: "src/telegram_bot/services/rate_limit.py"
    targets:
      - type: function
        name: check_login_rate_limit
      - type: function
        name: check_contact_start_rate_limit
      - type: function
        name: check_support_message_rate_limit
      - type: function
        name: check_upload_rate_limit
  - path: "src/backend/apps/core/services/contact_rate_limit.py"
    targets:
      - type: function
        name: check_deep_link_render_rate_limit
  - path: "src/backend/apps/search/services/rate_limit.py"
    targets:
      - type: function
        name: rate_limit_check
  - path: "src/backend/apps/users/services/login_rate_limit.py"
    targets:
      - type: module
        name: login_rate_limit
  - path: "src/telegram_bot/tests/test_rate_limit_service.py"
    targets:
      - type: class
        name: TestContactStartRateLimit
      - type: class
        name: TestSupportMessageRateLimit
changes:
  - action: modify_code
    description: >
      Add a shared, sync-callable window-bump helper to apps/core/utils/cache.py that
      performs cache.add + cache.incr, catches (ConnectionInterrupted, redis.RedisError,
      ValueError), logs at WARNING naming the key, and returns True (allowed) when the
      cache is unreachable. Keep the ValueError branch's reset behaviour byte-identical.
      Route all seven request-path guards through it, deleting their duplicated bodies.
      Apply the Q9 option for the commit shape the Coordinator recorded.
    code_hint: |
      def bump_rate_limit_window(key: str, limit: int, period: int) -> bool:
          """Return True when the caller is within its window, fail-open on cache loss.

          Mirrors the policy documented in
          telegram_bot/middlewares/update_id_dedup.py::UpdateIdDedupMiddleware: a cache
          outage degrades to "no limit" rather than dropping legitimate traffic. Never
          raises into a request path.
          """
          try:
              if cache.add(key, 1, timeout=period):
                  return True
              current = cache.incr(key)
          except (ConnectionInterrupted, redis.RedisError):
              logger.warning("Cache unavailable; allowing request on key %s", key)
              return True
          except ValueError:
              # Key expired between the add and incr calls - treat as a fresh start.
              cache.set(key, 1, timeout=period)
              return True
          return current <= limit
  - action: add_test
    description: >
      One test per guard: monkeypatch the module-level cache name with a MagicMock whose
      add raises ConnectionInterrupted(None) - the shape of
      src/telegram_bot/tests/test_update_id_dedup.py::test_redis_unavailable_fail_open -
      and assert the guard returns True. Demonstrate the three web-tier cases RED
      against the current code first; the report never proved they raise.
acceptance_criteria:
  - "all four bot guards and all three web guards return True (allowed) when the cache raises ConnectionInterrupted"
  - "the ValueError reset path is unchanged: cache.set(key, 1, timeout=period) runs and the counter reads back as 1"
  - "threshold semantics are unchanged: 5 allowed, the 6th refused, per-user isolation intact, custom limit/period kwargs still honoured"
  - "inspect.iscoroutinefunction is still True for the four bot guards and the @sync_to_async decorator is retained"
  - "test_rate_limit_service.py, test_contact_rate_limit.py and test_login.py pass; any change to their assertions is named in the commit body"
  - "no new import of telegram_bot.* from any apps.* module"
  - "no key format, limit value or period value changed"
  - "the commit body names the Q9 option and the contention sequence used"
tests_to_run:
  - "src/telegram_bot/tests/test_rate_limit_service.py"
  - "src/telegram_bot/tests/test_update_id_dedup.py"
  - "src/backend/apps/core/tests/test_contact_rate_limit.py"
  - "src/backend/apps/users/tests/test_login.py"
```

**Tests required**

1. **Per-guard fail-open** — seven tests, one per guard, each patching the *module-level*
   `cache` name so the patch is genuinely scoped. A single shared test that only calls the
   helper proves the helper works and says nothing about the seven callers.
2. **The `ValueError` reset stays live** — the two existing tests are the tripwire. Do not
   widen the `except` tuple in a way that makes `ValueError` unreachable.
3. **Threshold semantics** — the existing suites must pass **unchanged**. A fail-open
   change should be invisible to them; if it is not, the block is wrong.
4. **The negative control** — with a healthy cache, the 6th call is still refused. A
   fail-open change that accidentally always returns `True` would pass tests 1–3 only if
   test 4 were missing.

**Risk and rollback**

- *Implementation risk:* **the `ValueError` branch becomes unreachable** because a broader
  tuple or a reordering swallows it. Mitigation: binding constraint 1, and two existing
  tests are the tripwire.
- *Rollout risk:* **an eighth guard nobody audited.** Mitigation: the Auditor's pre-step
  is a repo-wide search for the `cache.add` + `cache.incr` shape; any new hit is reported
  before the commit.
- *Availability risk — this is the intended behaviour change:* during a Redis outage, all
  seven guards stop limiting. That is the documented policy (the guards that fail **open**
  on the consume path and **closed** on the guard path is the inversion `09-API-002`
  exists to fix), but it must be stated in the commit body so nobody reads it as a
  regression. BLOCK 3's per-seller cap is what limits the residual exposure.
- *Contention risk:* three of the six production files have claims from other phases
  (§5.3). Re-read before editing; stop and report on a concurrent change.
- *Rollback:* a straight revert restores the raise-on-outage behaviour for whichever
  guards the block converted.

---

### BLOCK 3 — Rate the `contact_<ad_id>` deep link, per buyer **and** per seller (09-API-003)

| | |
|---|---|
| **Findings owned** | `09-API-003` (HIGH) |
| **Depends on** | **BLOCK 2** (hard — the guards reuse BLOCK 2's helper) |
| **Blocks** | nothing in-plan; composes with BLOCK 4 (an attacker who drives 429s currently gets *more* outbound calls, not fewer) |
| **Priority** | **P0** |
| **Risk level** | **HIGH** — a new guard on a previously unlimited path; a pure tightening, with no failure mode it can introduce |
| **Required agents** | **Auditor · Planner · Validator** (Researcher is *not* required — the design follows the report and BLOCK 2's precedent; the Auditor confirms no existing test asserts the *absence* of a limiter) |

**Why the corrected ordering (09-VAL-005).** The report's roadmap says API-003 "must land
together with API-002". **That claim does not hold**, and the validator ruled it: a guard
that fails **closed** is not a working guard either, and `contact_<ad_id>` has no limiter
at all today, so API-002 cannot "remove" a guard that was never there. Shipping API-003
alone is a **pure tightening** with no ordering constraint.

**What is a real prerequisite, and it belongs to this block:** the **per-seller cap must
ship inside API-003, not as a follow-up**. The expensive part of the flow is the outbound
message *to the seller*, and an attacker controls the buyer account, not the seller's —
so a per-buyer limit alone is trivially evaded by cycling accounts. This block therefore
lands **two** guards.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/telegram_bot/handlers/contact.py` | `handle_contact` (the `contact_<ad_id>` branch) | **Not** `handle_contact_start` unless the routing itself changes. **Do not change** `classify_contact_deep_link` or `ContactDeepLinkKind` — `test_account_state_middleware.py` pins them, including the DECLINE-widening contract |
| `src/telegram_bot/handlers/contact.py` | `handle_contact_us_start` | The model for the shape: it already calls `check_contact_start_rate_limit` and already sends plain text with no `parse_mode` — which is also `09-API-006`'s preferred shape |
| `src/telegram_bot/services/rate_limit.py` | the two new guards | **Both reuse BLOCK 2's helper.** Do **not** add a seventh copy of the `add`/`incr` idiom. Keep `@sync_to_async` |
| `src/backend/apps/core/services/contact.py` | `get_seller_for_contact` | Read-only reference. It already returns `(bool, User | None)`, so keying on `seller.telegram_id` (or `seller.pk`) is free on the hot path |
| `src/telegram_bot/tests/test_contact_us.py` | the `contact_us` path and its limiter | Must stay green; the two branches must not be conflated |

**Binding constraints**

1. **Two guards, one commit.** Per-buyer (≈5 / 600 s, mirroring `contact_us`) **and**
   per-seller (≈20 / 3600 s, keyed on the ad owner). The per-seller cap is a prerequisite
   of shipping at all.
2. **Reuse BLOCK 2's helper.** An eighth copy of the idiom re-creates the defect.
3. **Refuse before the side effects.** The limiter must be evaluated **before**
   `record_contact_initiated` (the `AnalyticsEvent` INSERT) and **before** the outbound
   `bot.send_message` to the seller. A refused trigger must write no analytics row and
   send no message.
4. **Do not change the classifier, the regex, or the `AccountStateMiddleware` DECLINE
   behaviour.** Narrowing who can reach the branch is a **different** finding (phase 15's
   territory); the defect here is that the branch is unrated for everyone who *can* reach it.
5. **Per-buyer limit and per-seller limit are independent counters** with distinct key
   namespaces. Namespace collision would let one buyer's traffic consume the seller's
   budget.
6. **Do not change the send's `parse_mode`** — that is BLOCK 6's decision, and making it
   here would smuggle a cross-block change into a HIGH abort-control commit.

**Implementor task**

```yaml
id: task_09_b03_contact_rate_limit
title: "Rate the contact_<ad_id> deep link per buyer and per seller (09-API-003)"
priority: high
depends_on: ["task_09_b02_fail_open_window"]
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 3 - Rate the contact_<ad_id> deep link"
source_blocks: ["BLOCK 3"]
description: >
  telegram_bot/handlers/contact.py::handle_contact_start routes contact_us to a
  rate-limited branch and contact_<ad_id> to ::handle_contact, which contains NO limiter
  of any kind. The ad id is a dense, trivially enumerable integer parsed by
  CONTACT_PATTERN, the deep link renders on the anonymously reachable ad detail page,
  and AccountStateMiddleware admits declined/browse-only accounts to this branch. Each
  hit performs a seller lookup, an AnalyticsEvent INSERT and an outbound Telegram
  send_message TO THE SELLER. Any account can iterate contact_1..contact_N to flood
  every seller and inflate analytics_events without bound.
goals:
  - "make the per-ad contact deep link rate-limited for everyone who can reach it"
  - "protect the seller, not only the buyer's account"
  - "refuse before any analytics row and before any outbound message"
  - "add no eighth copy of the cache window idiom"
files:
  - path: "src/telegram_bot/handlers/contact.py"
    targets:
      - type: function
        name: handle_contact
      - type: function
        name: handle_contact_start
  - path: "src/telegram_bot/services/rate_limit.py"
    targets:
      - type: module
        name: rate_limit
      - type: function
        name: check_contact_start_rate_limit
  - path: "src/telegram_bot/tests/test_contact_us.py"
    targets:
      - type: module
        name: test_contact_us
changes:
  - action: modify_code
    description: >
      Add two guards in telegram_bot/services/rate_limit.py, both built on the shared
      helper introduced by BLOCK 2: a per-buyer guard on message.from_user.id mirroring
      the contact_us budget, and a tighter per-seller guard keyed on the ad owner. The
      seller identity is already available from get_seller_for_contact, so the seller key
      costs no extra round trip. Call both at the top of handle_contact, BEFORE
      record_contact_initiated and BEFORE the outbound send, and refuse cleanly when
      either refuses.
    code_hint: |
      # Distinct key namespaces - a buyer's traffic must not consume the seller's budget.
      CONTACT_BUYER_LIMIT: Final[int] = 5
      CONTACT_BUYER_PERIOD: Final[int] = 600
      CONTACT_SELLER_LIMIT: Final[int] = 20
      CONTACT_SELLER_PERIOD: Final[int] = 3600
  - action: add_test
    description: >
      From one buyer, the 6th contact_<ad_id> trigger is refused AND no send_message is
      issued AND no AnalyticsEvent is written. Separately, N distinct buyers are refused
      at the per-seller cap - this is the case that proves the second guard exists and is
      not merely a different number on the first one.
acceptance_criteria:
  - "the 6th contact_<ad_id> trigger from one buyer is refused, no bot.send_message to the seller is issued, and no AnalyticsEvent row is created"
  - "a burst from distinct buyers is refused at the per-seller cap, with the same no-send and no-analytics guarantee"
  - "the contact_us branch's behaviour is byte-identical and test_contact_us.py passes UNCHANGED"
  - "classify_contact_deep_link and ContactDeepLinkKind are unchanged; test_account_state_middleware.py passes UNCHANGED"
  - "the two guards use distinct key namespaces; one buyer's traffic does not consume the seller's budget"
  - "both guards are @sync_to_async and both reuse BLOCK 2's shared helper - no new cache.add/incr copy exists in this module"
  - "the commit body states the per-seller cap's rationale: the expensive part of the flow is the outbound message to the seller"
  - "no change to any parse_mode, to the deep-link regex, or to AccountStateMiddleware"
tests_to_run:
  - "src/telegram_bot/tests/test_contact_us.py"
  - "src/telegram_bot/tests/test_rate_limit_service.py"
  - "src/telegram_bot/tests/test_account_state_middleware.py"
  - "src/backend/apps/core/tests/test_contact.py"
  - "src/backend/apps/core/tests/test_contact_response.py"
```

**Tests required**

1. **The buyer's sixth trigger** — refused, and the assertion is on the **absence of the
   side effects**, not on the limiter's return value. Assert `bot.send_message` was not
   called and no `AnalyticsEvent` exists. A test that only asserts `False` passes against
   the current, unrated code path if it is written against the wrong symbol.
2. **The seller's cap, from distinct buyers** — this is the test that distinguishes the two
   guards. Without it, a block that implemented only a per-buyer guard and set a different
   number would pass.
3. **The `contact_us` branch unchanged** — `test_contact_us.py` must pass untouched.
4. **The classifier unchanged** — `test_account_state_middleware.py` must pass untouched;
   it pins `classify_contact_deep_link` and the DECLINE-widening contract.
5. **Key independence** — a buyer exhausting their own budget does not affect the
   seller's remaining budget.

**Risk and rollback**

- *Implementation risk:* **the guard is placed after the side effects**, so a refused
  trigger still sends the message and writes the analytics row. Mitigation: binding
  constraint 3 and test 1's negative assertions.
- *Regression risk:* **an over-tight budget blocks legitimate buyers.** A first-party
  repeat buyer is exactly the pattern the limit constrains. Mitigation: the per-buyer
  budget mirrors the shipped `contact_us` budget, and the commit body states both numbers
  so they can be tuned deliberately rather than discovered.
- *Design risk:* **the per-seller key uses a seller identity that is not yet resolved** at
  the point of the check, forcing an extra database round trip. `get_seller_for_contact`
  already returns it — read the call order before adding a query, and measure if one is
  added.
- *Rollback:* a straight revert restores the unrated deep link, which is HIGH severity.
  State that plainly.

---

### BLOCK 4 — A bounded replay budget, a reachable transient set, an honest return contract (09-API-004, 09-VAL-004)

| | |
|---|---|
| **Findings owned** | `09-API-004` (HIGH) · `09-VAL-004` |
| **Depends on** | **nothing in-plan** (composes with BLOCK 3: an attacker who drives 429s currently gets *more* outbound calls, not fewer) |
| **Blocks** | BLOCK 6's shape (both are outbound-Telegram retry decisions and BLOCK 6 must not re-derive one) |
| **Priority** | **P0** |
| **Risk level** | **HIGH — the highest execution risk in the phase, precisely because the fix is right.** Shipping `retry.py` without its test change produces a red suite and invites a revert of a correct fix |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** The Researcher re-derives U2/U3/U8/U9 and states the budget shape; the Planner records it; the Validator must be able to reject a solution that still sleeps `retry_after` verbatim |

**This is one atomic change across three files.** `telegram_bot/retry.py`,
`telegram_bot/main.py` and `telegram_bot/tests/test_error_handler.py`. The report names
**one** test that must change; **three** do.

**Decision required before implementation — the budget shape (the Implementor may not choose)**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | `delay = min(float(exc.retry_after or 0), _MAX_BACKOFF_SECONDS)` with a small ceiling, **keeping** `_MAX_RETRIES` as the loop bound | **Gains:** the smallest change; the 900 s becomes `3 × ceiling`. **Costs:** still attempt-bounded rather than budget-bounded, so three consecutive ceilings exceed any stated budget. The report explicitly asks for a **total budget**, and attempt-counting is what produced the defect |
| **(b)** | A **total wall-clock budget** for one update task: loop while the elapsed budget remains, `delay = min(retry_after, remaining, _MAX_BACKOFF_SECONDS)` | **Gains:** the stated guarantee — *no* single flood response can pin an update task for more than the budget — is enforceable and testable as one number. **Costs:** needs a monotonic-clock read per attempt; the sleep can become very short near the end, which is intended |
| **(c)** | (b) **plus** an explicit `dp.run_polling` concurrency bound so N concurrent 429s cannot each pin a task | **Gains:** closes the amplification half — `handle_as_tasks=True` with `tasks_concurrency_limit=None` means N concurrent 429s become 3N replayed calls. **Costs:** changes the bot's update-processing behaviour globally, which is a **larger** decision than this finding and interacts with `09-API-003`'s traffic shape |

**(b) is the shape the evidence supports.** (c) is attractive but is a bot-wide throughput
decision — record it as a follow-on rather than smuggling it in here.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/telegram_bot/retry.py` | `retry_transient`, `_MAX_RETRIES`, `_BACKOFF_BASE`, `_TRANSIENT_EXCEPTIONS` | **The module docstring's "NO import-time side effects" contract must survive** — `retry.py` is imported lazily inside `main()` after `django.setup()`. Add a `prometheus_client.Counter` for dropped messages: `django_prometheus` is already mounted at `config/urls.py` root and multiprocess mode is already the established pattern, so **no new dependency and no new wiring** |
| `src/telegram_bot/main.py` | the `dp.errors(...)` registration inside `configure_dispatcher` | One line: `ExceptionTypeFilter(TelegramRetryAfter)` → `ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS)`. **Do not change the module's import structure** — the lazy import after `django.setup()` is load-bearing |
| `src/telegram_bot/tests/test_error_handler.py` | `_make_dispatcher`, `test_error_handler_marks_handled_after_exhausting_bound`, `test_error_handler_returns_false_for_unrelated_error`, plus the **new** `TelegramServerError` and `retry_after=600` cases | **The helper hard-codes `ExceptionTypeFilter(TelegramRetryAfter)`.** If it is not moved, the new sibling-replay test never reaches the handler and **passes vacuously** — the most dangerous outcome in this block |
| `src/telegram_bot/tests/test_error_handler.py` | `test_error_handler_backs_off_and_replays` | Asserts `result is True`, `sleeps == [2.0]`, `await_count == 1`. Compatible with a ceiling (2.0 s is under any sane cap) and with `True` on the success path — **leave it alone** |

**Binding constraints**

1. **Three tests change in this commit, not one.** `09-VAL-004` names
   `test_error_handler_marks_handled_after_exhausting_bound`; the tree shows
   `test_error_handler_returns_false_for_unrelated_error` **also becomes wrong** — with
   the filter widened and the `isinstance` guard deleted, `TelegramBadRequest` falls into
   `except AiogramError: break` and the handler returns `True`, failing its
   `assert result is False`. The report calls this test "unaffected". **It is affected.**
2. **Per the project rule, the tests change, not the handler.** Each rewrite must say in
   its docstring and in the commit body that the old assertion encoded the defect as
   intended behaviour.
3. **`_make_dispatcher` must move to `_TRANSIENT_EXCEPTIONS` in the same commit.**
   Otherwise the new `TelegramServerError` replay test is vacuous.
4. **Demonstrate U3 red first** — the sibling-replay test must fail against the current
   wiring before the fix, proving it actually reaches the handler.
5. **Keep the module docstring's no-import-side-effects contract.** No `ThreadPoolExecutor`,
   no network, no model loading at import.
6. **A drop counter, not a log line only.** `prometheus_client.Counter` on the existing
   `/metrics`; no new endpoint, no new dependency.
7. **Do not change `dp.run_polling(bot)`'s arguments** unless Q-shape option (c) was
   explicitly recorded. That is a bot-wide throughput decision (§6.2).

**Implementor task**

```yaml
id: task_09_b04_retry_budget
title: "Bound the transient replay budget and make the return contract honest (09-API-004)"
priority: critical
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 4 - A bounded replay budget"
source_blocks: ["BLOCK 4"]
description: >
  telegram_bot/retry.py::retry_transient sleeps the Telegram-mandated retry_after
  verbatim before each of _MAX_RETRIES = 3 attempts, so ONE flood response pins an
  update task for 900 s. The declared transient set is unreachable: main.py registers
  ExceptionTypeFilter(TelegramRetryAfter) and the body opens with
  `if not isinstance(exc, TelegramRetryAfter): return False`, so TelegramNetworkError
  and TelegramServerError can never enter the handler. After exhausting retries the
  handler returns True, which ErrorsMiddleware reads as "handled" - a lost message is
  reported as a success and nothing logs the drop. dp.run_polling is called with no
  arguments, so aiogram's defaults apply (handle_as_tasks=True,
  tasks_concurrency_limit=None) and N concurrent 429s become 3N replayed outbound calls.
files:
  - path: "src/telegram_bot/retry.py"
    targets:
      - type: function
        name: retry_transient
      - type: constant
        name: _TRANSIENT_EXCEPTIONS
      - type: constant
        name: _MAX_RETRIES
  - path: "src/telegram_bot/main.py"
    targets:
      - type: function
        name: configure_dispatcher
  - path: "src/telegram_bot/tests/test_error_handler.py"
    targets:
      - type: function
        name: _make_dispatcher
      - type: function
        name: test_error_handler_marks_handled_after_exhausting_bound
      - type: function
        name: test_error_handler_returns_false_for_unrelated_error
changes:
  - action: modify_code
    description: >
      Apply the recorded budget shape: bound the total wall-clock budget for one update
      task and cap each individual sleep at a module-level Final constant. Register
      ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS) in main.py and delete the now-redundant
      isinstance guard so the handler body matches the constant it already declares.
      Return False after exhaustion so ErrorsMiddleware re-raises, and increment a
      prometheus_client.Counter for dropped outbound messages.
    code_hint: |
      # Total wall-clock budget for ONE update task's replay loop.
      _MAX_REPLAY_BUDGET_SECONDS: Final[float] = 30.0
      # Per-attempt ceiling, so a single retry_after cannot consume the whole budget.
      _MAX_BACKOFF_SECONDS: Final[float] = 5.0

      _DROPPED_OUTBOUND_CALLS = Counter(
          "telegram_dropped_outbound_calls_total",
          "Outbound Telegram calls dropped after the replay budget was exhausted.",
      )
  - action: modify_test
    description: >
      In test_error_handler.py, in THIS SAME COMMIT: (1) move _make_dispatcher to
      ExceptionTypeFilter(_TRANSIENT_EXCEPTIONS); (2) rewrite
      test_error_handler_marks_handled_after_exhausting_bound to assert the handler
      returns False and the drop counter incremented - the old assertion encoded the
      defect; (3) rewrite test_error_handler_returns_false_for_unrelated_error for the
      widened filter; (4) add a TelegramServerError case that demonstrates RED against
      the current wiring first, then proves the replay; (5) add a retry_after=600 case
      asserting a BOUNDED total sleep. Leave test_error_handler_backs_off_and_replays
      untouched.
acceptance_criteria:
  - "a TelegramRetryAfter with retry_after=300 produces a total sleep bounded by _MAX_REPLAY_BUDGET_SECONDS, not 900 s"
  - "a TelegramServerError enters the handler and is replayed (asserted red against the current wiring first)"
  - "after exhaustion the handler returns False and the dropped-outbound counter increments"
  - "a non-transient TelegramBadRequest still returns False"
  - "test_error_handler_backs_off_and_replays passes UNCHANGED"
  - "retry.py's module docstring contract holds: no import-time side effects, no network, no model loading"
  - "the commit body names the budget shape option, states that THREE tests changed and why each old assertion encoded a defect, and states that retry.py was NOT shipped alone"
  - "no new dependency, no new endpoint, no new user-visible string"
tests_to_run:
  - "src/telegram_bot/tests/test_error_handler.py"
  - "src/telegram_bot/tests/test_main_lifecycle.py"
```

**Tests required**

1. **The bound** — `retry_after=300` and `retry_after=600` both yield a total sleep inside
   the budget. Assert the **total**, not the per-attempt value: an attempt-counting bound
   also reduces 900 s to `3 × ceiling` and still does not guarantee the budget.
2. **The reachable set** — a `TelegramServerError` enters the handler and replays.
   Demonstrate it **red** against the current wiring first; a test that passes without ever
   reaching the handler is worse than no test.
3. **The honest return** — after exhaustion the handler returns `False` and the drop
   counter increments. Both halves: the return value changes what `ErrorsMiddleware` does,
   and the counter is the only line anywhere that says "N messages were dropped".
4. **The unrelated error** — `TelegramBadRequest` still returns `False`. This is the test
   the report declared "unaffected" and it is **not**.
5. **The success path** — `test_error_handler_backs_off_and_replays` unchanged.

**Risk and rollback**

- *Correctness risk:* **the sibling-replay test passes vacuously** because
  `_make_dispatcher` still filters on `TelegramRetryAfter`. Mitigation: binding constraint
  3, plus red-first demonstration. This is the single most dangerous failure mode in the
  plan because it produces a **green** result that proves nothing.
- *Rollout risk:* **shipping `retry.py` alone** produces a red suite and invites a revert
  of a correct fix. Mitigation: the three files are one commit, and §8.2 checks the
  atomicity.
- *Availability risk:* a smaller budget drops more messages that a longer budget would
  have retried. That is the intended trade, but it must be recorded — and the drop counter
  is what makes it observable. State the budget and its rationale in the commit body.
- *Contract risk:* returning `False` re-raises into `ErrorsMiddleware`. The validator
  confirmed `retry_transient` has exactly one production caller and **no application code
  branches on its value**; the Auditor's pre-step is to re-confirm that at the block's
  commit, because a new caller would change the blast radius.
- *Rollback:* a straight revert restores the 900 s pin and the false success. State that.

---

### BLOCK 5 — Exchange rates: a bootstrap default, wired invalidation, honest docs (09-API-008, 09-VAL-006 half)

| | |
|---|---|
| **Findings owned** | `09-API-008` (MEDIUM) · the second half of `09-VAL-006` |
| **Depends on** | **BLOCK 1** (soft — same wave by `09-VAL-006`, same module for the cache contract) |
| **Blocks** | nothing in-plan. **Composes with** `03-DB-008` (a reverted rate causes a full-table recompute that holds locks) — cross-referenced, never merged (`09-VAL-001`) |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — no migration, small diff, but the docs it corrects are the ones an operator follows **during an incident** |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four). The Researcher settles Q13 (where the invalidation is wired) and reads the existing admin / command surface; the Planner records it; the Validator confirms an edited rate survives a second seed run and that the cache is actually invalidated |

**Why this is high-priority despite MEDIUM severity.** Two capability claims the project
believes about itself are false, and both are in the operator's runbook. An operator who
corrects a drifted rate in the admin **has it reverted at the next deploy**, with no log
line and no record of the previous value — and `price_normalized_eur` is not recomputed, so
the rate table and every derived price silently diverge. Every cross-currency filter and
sort on the site reads that column.

**Decision required before implementation — Q13: where is `invalidate_rate_cache()` wired?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | A `post_save` / `post_delete` receiver on `ExchangeRate` in a new `apps/currencies/signals.py` | **Gains:** every write path is covered by construction, including a future one; matches the pattern already used in `apps/categories/signals.py` and `apps/search/signals.py`. **Costs:** a **new** receiver module in a new app; a cache call inside a signal must not be able to roll back the saving transaction — so the receiver needs the same `(ConnectionInterrupted, redis.RedisError)` guard the category receiver already has |
| **(b)** | The Django admin's `ExchangeRateAdmin.save_model`, plus an explicit call in the `recompute_normalized_prices` command | **Gains:** no new receiver; the invalidation sits where an operator actually edits the rate. **Costs:** a rate changed by a management command, a data migration or a shell is **not** invalidated — the defect returns through a second door |
| **(c)** | Override `ExchangeRate.save()` so the instance invalidates its own cached rate | **Gains:** the narrowest correct seam; no admin dependency. **Costs:** a cache call inside `save()` couples the model to the cache backend, which the project's own layering rule discourages |

**(a) is the shape the codebase already uses**, and it is the only one that cannot be
bypassed. The Researcher must first establish whether `apps/currencies` already has an
admin or a signals module — the report does not say, and the answer changes the file
surface.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/currencies/management/commands/load_exchange_rates.py` | `Command.handle`, the module docstring | The docstring currently claims *"Idempotent via `update_or_create` keyed on `currency`"* — which is precisely the wrong property for a value operators are expected to correct. Switch to `get_or_create(currency=…, defaults={…})` and add a **new** log line stating the rate in use and whether it came from the seed or from a prior edit. The existing `"Exchange rates loaded: N created, M updated"` summary changes shape — that is expected, not a regression |
| `src/backend/apps/currencies/services/price_normalizer.py` | `PriceNormalizer.invalidate_rate_cache`, `PriceNormalizer._get_current_rate`, `normalize_price_to_eur`, the module docstring | The helper is implemented and correct with **zero** call sites. The module docstring's *"The cache is invalidated when a rate is updated"* is a **second** false capability claim |
| `src/backend/apps/currencies/admin.py` (read-only) | the `ExchangeRate` admin registration | Read before choosing Q13's option |
| `src/backend/apps/core/utils/migrate_locked.py` | `_build_steps` | **Reference only.** The tuple must keep `load_exchange_rates` — `test_migrate_locked.py` pins the order and the `RUN_TRANSLATION_BACKFILL` gate |
| `src/backend/apps/currencies/tests/test_price_normalizer.py` · `test_recompute_command.py` | the normalizer and the recompute sweep | Must stay green |
| `src/backend/apps/currencies/tests/conftest.py` | the exchange-rate fixtures | Read: a `get_or_create` switch changes which path a test that **pre-creates** a rate exercises |
| `docs/ops/migration-workflow.md` | the sentence asserting the command *"makes HTTP calls to ECB"* (anchor by **phrase**, not by line — C-6) | Phase 12's runbook surface, contended |

**Binding constraints**

1. **`get_or_create`, not `update_or_create`.** Idempotence for a value operators correct
   means *"create it if absent"*, not *"make the row equal the constant"*.
2. **No migration is needed** and none may be added.
3. **Do not add `recompute_normalized_prices` to the seed.** The rate table and the derived
   column already drift; silently recomputing every price on every boot would turn a
   correctness fix into a large write amplification on every deploy. Record the drift
   instead.
4. **Correct **three** false claims, not one:** `migration-workflow.md`, the command's
   docstring, and `price_normalizer.py`'s docstring. A doc-only fix that corrects the
   runbook leaves two code comments asserting a capability that does not exist.
5. **The cache guard must be present wherever `invalidate_rate_cache()` is called** —
   `cache.delete` raises `ConnectionInterrupted` under an outage, and a receiver that lets
   it escape rolls back the saving transaction. Copy the `(ConnectionInterrupted,
   redis.RedisError)` guard shape from `apps/categories/signals.py`.
6. **`apps/currencies` must not import `telegram_bot.*`** and must not gain a dependency on
   `apps/search`.
7. **Q11 is routed, not decided.** A live ECB feed is a **new capability** (HTTP client,
   scheduler entry, rate-history model, migration). BLOCK 5's fix is correct either way.
   Record the routing; do **not** build the feed.

**Implementor task**

```yaml
id: task_09_b05_exchange_rates
title: "Make the exchange-rate seed a bootstrap default and wire the rate-cache invalidation (09-API-008)"
priority: high
depends_on: ["task_09_b01_cache_contract"]
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 5 - Exchange rates: bootstrap default, wired invalidation, honest docs"
source_blocks: ["BLOCK 5"]
description: >
  apps/currencies/management/commands/load_exchange_rates.py::Command.handle runs
  ExchangeRate.objects.update_or_create(currency=..., defaults={...}) in a loop over
  INITIAL_RATES, and it is step 3 of migrate_locked._build_steps - which runs on every
  docker compose up and every deploy, under advisory lock MIGRATE. An operator who
  corrects a drifted rate in the admin has it silently reverted at the next deploy, with
  no log line and no record of the previous value. The seed also does not re-run
  recompute_normalized_prices, so exchange_rates and Ad.price_normalized_prices drift
  apart. Separately, PriceNormalizer.invalidate_rate_cache is implemented and correct
  with ZERO call sites, while its own module docstring claims the cache is invalidated
  on a rate update - a second false capability claim. And there is no external rate feed
  at all: apps/currencies contains no HTTP client and no network call.
goals:
  - "stop silently reverting an operator's corrected rate on every boot"
  - "make invalidate_rate_cache() actually reachable from a rate write"
  - "correct all three false capability claims"
  - "stay a small, migration-free fix - a live feed is routed, not built"
files:
  - path: "src/backend/apps/currencies/management/commands/load_exchange_rates.py"
    targets:
      - type: class
        name: Command
      - type: method
        name: handle
  - path: "src/backend/apps/currencies/services/price_normalizer.py"
    targets:
      - type: class
        name: PriceNormalizer
      - type: method
        name: invalidate_rate_cache
      - type: method
        name: _get_current_rate
  - path: "src/backend/apps/currencies/tests/test_price_normalizer.py"
    targets:
      - type: module
        name: test_price_normalizer
  - path: "docs/ops/migration-workflow.md"
    targets:
      - type: module
        name: migration_workflow
changes:
  - action: modify_code
    description: >
      Switch Command.handle from update_or_create to get_or_create so an existing row is
      never rewritten, and log the rate in use together with whether it came from the
      seed or from a prior edit. Apply the Q13 option to wire
      PriceNormalizer.invalidate_rate_cache() into the rate-change path, guarded against
      ConnectionInterrupted and redis.RedisError so a cache outage can never roll back
      the saving transaction. Correct the module docstring in
      load_exchange_rates.py and in price_normalizer.py.
    code_hint: |
      # The constant is a BOOTSTRAP DEFAULT, not the authority. Idempotence here means
      # "create if absent", never "make the row equal the constant".
      obj, was_created = ExchangeRate.objects.get_or_create(
          currency=currency_code,
          defaults={
              "rate_to_eur": rate_to_eur,
              "source": SOURCE,
              "effective_date": EFFECTIVE_DATE,
          },
      )
      self.stdout.write(
          f"Rate {currency_code}: rate_to_eur={obj.rate_to_eur} "
          f"({'seeded' if was_created else 'preserved existing'})"
      )
  - action: modify_doc
    description: >
      docs/ops/migration-workflow.md: the sentence asserting that load_exchange_rates
      "makes HTTP calls to ECB" is false - apps/currencies contains no HTTP client, no
      scheduler entry and no network call. Replace it with what the command actually
      does and why it is a separate one-shot. Anchor by phrase, not by line.
  - action: add_test
    description: >
      Seed the three rates, edit one in the database, run load_exchange_rates again, and
      assert the edited value SURVIVES and the log line reports it as preserved. Separately,
      edit a rate through the wired path and assert the very next PriceNormalizer read
      sees the new value rather than the cached one.
acceptance_criteria:
  - "an operator-edited exchange rate survives a second load_exchange_rates run, and the command's own output says the value was preserved rather than updated"
  - "a rate changed through the wired path is visible to the very next PriceNormalizer read - the cache is genuinely invalidated"
  - "a cache outage during invalidation does NOT roll back the saving transaction (the receiver's except tuple is exercised)"
  - "test_migrate_locked.py passes UNCHANGED - load_exchange_rates stays in _build_steps in the same position"
  - "no migration was added and makemigrations --check is clean"
  - "recompute_normalized_prices was NOT added to the boot path"
  - "the ECB sentence in docs/ops/migration-workflow.md no longer claims a network call, and the load_exchange_rates and price_normalizer docstrings no longer claim an automatic invalidation that did not exist"
  - "the commit body records that a live ECB feed (Q11) is routed to the owner and was NOT built here"
  - "no recompute sweep added, no new dependency, no new user-visible string"
tests_to_run:
  - "src/backend/apps/currencies/tests/test_price_normalizer.py"
  - "src/backend/apps/currencies/tests/test_recompute_command.py"
  - "src/backend/apps/core/tests/test_migrate_locked.py"
```

**Tests required**

1. **The seed no longer reverts** — edit a rate, run the command, assert the value
   survives. This is the finding, expressed as an assertion.
2. **The cache is genuinely invalidated** — warm the rate cache, change the rate through
   the wired path, read through `PriceNormalizer` and assert the new value is returned.
   A test that calls `invalidate_rate_cache()` directly proves nothing about the wiring; it
   must exercise the **production path** that a real rate change takes.
3. **The outage does not roll back** — patch the cache to raise during invalidation and
   assert the rate change still commits. This is the tripwire for binding constraint 5.
4. **The boot order is unchanged** — `test_migrate_locked.py` untouched.

**Risk and rollback**

- *Data risk:* `get_or_create` means a **fresh** deployment still seeds all three rates,
  and an existing deployment keeps whatever is there — including a wrong value that has
  been wrong for a long time. Mitigation: the new log line reports the rate in use and its
  provenance on every boot, so the value is no longer silent.
- *Implementation risk:* the invalidation is wired to the **wrong** write path and the
  helper's call-site count rises to one while the real path stays unwired. Mitigation:
  test 2 exercises the production path, not the helper.
- *Rollout risk:* a cache call inside a signal rolls back the transaction under an
  outage. Mitigation: binding constraint 5 and test 3.
- *Regression risk:* the command's stdout shape changes and a test asserts the old string.
  Mitigation: the change is expected; any test touching it is updated **in this commit**
  with the change named.
- *Cross-phase:* the same command participates in `03-DB-008`'s recompute sweep.
  **Cross-referenced, not merged** (`09-VAL-001`) — fixing either does not fix the other.

---

### BLOCK 6 — Alert bodies: one shape, both modules, all four send sites (09-API-006, 09-VAL-009)

| | |
|---|---|
| **Findings owned** | `09-API-006` (MEDIUM) · the backoff half of `09-VAL-009` |
| **Depends on** | BLOCK 4 (soft — do not re-derive a retry decision BLOCK 4 has already made) |
| **Blocks** | BLOCK 7's `_send_payloads` edit (same function, same file) |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — no user-visible string is added, but two test suites declare a `send_message` signature and will change |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four). The Researcher reads `test_send_alerts_daily.py`'s stub signatures and `test_immediate_alerts.py`'s pinned sleep fixture; the Planner records the shape and the Q8 ceiling; the Validator confirms no seller markup is live in either module |

**Decision required before implementation — the message shape (the Implementor may not choose)**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **Drop `parse_mode="HTML"` and send plain text** in both modules, at all four send sites (initial + retry in each) | **Gains:** removes the **entire class** of defect with no per-field auditing; consistent with `telegram_bot/handlers/contact.py::handle_contact`, which already sends plain text. **Costs:** loses the bold title, the location emoji's formatting and the "View ad" anchor — cosmetic only; the deep link is not actionable as a Telegram inline URL without the anchor, so **the UX consequence must be stated**. Changes two test stub signatures |
| **(b)** | Keep HTML and escape every interpolation with `django.utils.html.escape`, using unescaped values only for structural tags | **Gains:** formatting preserved. **Costs:** every field must be audited **and** re-audited on every future edit — which is how the defect happened; **and there is a real import trap**: `apps/core/services/translation.py` already imports the **stdlib** `html` and calls `html.unescape(...)`, which is decoding, not escaping. An Implementor reaching for `html` in the wrong module writes a real defect |

**(a) is the lower-risk shape and the report's stated preference.** Either way, the change
must cover **all four** send sites: dropping `parse_mode` at the initial send and leaving
it on the retry send is a defect that survives the fix.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/services/immediate_alerts.py` | `build_alert_message`, `_send_payloads` (both the initial send and the retry send) | `f"<b>{title}</b>"`, `f"📍 {city_name}"`, `f'<a href="{ad.get_absolute_url()}">{view_ad_label}</a>'`. The gettext-wrapped labels are the **only** safe values; `title`, `city_name` and the URL are seller-controlled |
| `src/backend/apps/search/management/commands/send_alerts.py` | `Command._format_digest`, `Command._send_user_digests` (both sends) | `f"• {ad.get_title(locale)[:50]}\n  {price_str}\n"`. Note the **50-character truncation** — a full raw-markup substring check on the digest returns `False` while unescaped `<b>` is still present in the prefix. The test must assert on the **truncated prefix** |
| `src/backend/apps/search/tests/test_immediate_alerts.py` | `TestBuildAlertMessageKeyboard::test_build_alert_message_unsubscribe_callback` | Discards the text and asserts only `callback_data` — survives either option |
| `src/backend/apps/search/tests/test_send_alerts_daily.py` | `TestDeliveryOutcome` (`async def always_fail(chat_id, text, parse_mode)`), `TestPerUserDigestCap` | **Dropping `parse_mode` changes the stub signature and raises `TypeError`** — the test friction the report did not name |
| `src/backend/apps/search/tests/test_immediate_alerts.py` | `TestRetryAfterBackoff::test_429_retry_after_honored` | Pins an exact `asyncio.sleep` value — the Q8 tripwire |

**Binding constraints**

1. **All four send sites**, or the fix does not land. Initial and retry, in both modules.
2. **`parse_mode` must not be dropped from one send and kept on the other.**
3. **Under option (b), use `django.utils.html.escape` and not the stdlib `html`.** The
   translation service's `html.unescape` is the decoy. If option (b) is chosen, the commit
   body names the import path explicitly.
4. **Do not change the message text beyond escaping or mode.** No new user-visible string,
   so **i18n is not engaged** — confirm against
   `apps/ads/tests/test_i18n_completeness.py` rather than assuming.
5. **Assert red first** (U6): build a message from a title containing `<b>`, `&` and
   `<a href="…">` and assert the raw markup is present in the current output.
6. **`09-VAL-009`:** `_send_payloads`'s own retry sleep is `float(exc.retry_after)`
   **verbatim** — a second, independent uncapped backoff. Apply the Q8 ceiling **in this
   block** so BLOCK 7 does not have to re-derive it. If the ceiling lands below the value
   pinned by `test_429_retry_after_honored`, that test changes **in this commit** and the
   commit body says why.
7. **Do not change the `Bot` construction or the module-level patch targets.** Consolidating
   the outbound path is Q10 and is **not** in this block (§6.2).

**Implementor task**

```yaml
id: task_09_b06_alert_escaping
title: "Make both alert builders safe for seller-controlled text (09-API-006)"
priority: high
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 6 - Alert bodies: one shape, both modules, all four send sites"
source_blocks: ["BLOCK 6"]
description: >
  apps/search/services/immediate_alerts.py::build_alert_message and
  apps/search/management/commands/send_alerts.py::Command._format_digest interpolate
  seller-authored text straight into HTML-parse-mode Telegram messages. Neither module
  imports an escaping helper. Telegram rejects an unparseable entity set as a permanent
  TelegramBadRequest with no retry, and SavedSearchNotification rows are written BEFORE the
  send - so the system reports the alert as delivered and neither seller nor buyer sees a
  symptom. The digest is per RECIPIENT BATCH, not per seller: one seller's bad title kills
  the whole digest for every user whose 10-ad window included that ad. The mirror risk is
  confirmed too - a title containing <a href="..."> becomes a clickable link a seller
  injected into every subscriber's chat.
goals:
  - "make no seller-controlled value live markup in any outbound alert"
  - "cover all four send sites, initial and retry, in both modules"
  - "bound the alert path's own uncapped retry_after sleep (09-VAL-009)"
  - "introduce no new user-visible string"
files:
  - path: "src/backend/apps/search/services/immediate_alerts.py"
    targets:
      - type: function
        name: build_alert_message
      - type: function
        name: _send_payloads
  - path: "src/backend/apps/search/management/commands/send_alerts.py"
    targets:
      - type: class
        name: Command
      - type: method
        name: _format_digest
      - type: method
        name: _send_user_digests
  - path: "src/backend/apps/search/tests/test_send_alerts_daily.py"
    targets:
      - type: class
        name: TestDeliveryOutcome
  - path: "src/backend/apps/search/tests/test_immediate_alerts.py"
    targets:
      - type: class
        name: TestRetryAfterBackoff
changes:
  - action: modify_code
    description: >
      Apply the recorded shape to BOTH modules at ALL FOUR send sites. Under option (a)
      drop parse_mode="HTML" and send plain text; under option (b) escape every
      interpolation with django.utils.html.escape - NOT the stdlib html module that
      apps/core/services/translation.py already imports for UNESCAPING - and leave only
      structural tags unescaped. Apply the Q8 ceiling to _send_payloads' own
      float(exc.retry_after) sleep.
    code_hint: |
      # Option (a) - plain text at every send site:
      await bot.send_message(chat_id=payload["chat_id"], text=text)

      # Option (b) - escape every seller-controlled interpolation:
      from django.utils.html import escape   # NOT stdlib html: translation.py's
                                            # html.unescape() DECODES, it does not escape
      title = escape(ad.get_title(locale))
  - action: modify_test
    description: >
      TestDeliveryOutcome's send_message stubs declare (chat_id, text, parse_mode).
      Under option (a) update the stub signature and every call site in this commit and
      name the change in the commit body. Add a regression built from a title containing
      <b>, & and <a href="http://evil.example">x</a> asserting none of the seller's markup
      is live. For the digest, assert on the 50-character truncated prefix - a full
      substring check returns False against the current code for a reason that has nothing
      to do with escaping. If the Q8 ceiling lands below the value pinned by
      test_429_retry_after_honored, update that assertion in this commit.
acceptance_criteria:
  - "an alert body built from a title containing <b>, & and <a href=...> contains no live seller markup, in BOTH modules"
  - "the digest path is asserted on the truncated prefix, so the check can actually fail against the current code"
  - "all four send sites are covered - initial and retry, in immediate_alerts and send_alerts"
  - "test_build_alert_message_unsubscribe_callback passes UNCHANGED (it asserts only callback_data)"
  - "the send_message stub signatures in test_send_alerts_daily.py match what the production call sites now pass"
  - "_send_payloads' retry sleep is bounded; test_429_retry_after_honored passes, or its expectation is updated in this commit with the reason stated"
  - "no new user-visible string and no locale file change; test_i18n_completeness.py is green"
  - "the Bot construction sites and the module-level patch targets are unchanged"
  - "the commit body names the shape option, states the plain-text UX consequence under option (a), and records the Q8 ceiling"
tests_to_run:
  - "src/backend/apps/search/tests/test_immediate_alerts.py"
  - "src/backend/apps/search/tests/test_send_alerts_daily.py"
  - "src/backend/apps/search/tests/test_alert_query.py"
```

**Tests required**

1. **The markup does not survive** — build from a hostile title in **both** modules and
   assert none of the seller's markup is live. This is the finding, as an assertion.
2. **The digest's truncation** — assert on the 50-character prefix. A test written against
   the untruncated string will pass against the defective code, which is exactly the false
   refutation the report itself recorded.
3. **A control** — an ordinary title with no markup produces the same visible text as
   before. A blanket "strip everything" passes test 1 and destroys the message.
4. **The stub signatures** — `TestDeliveryOutcome` and `TestPerUserDigestCap` pass with
   signatures matching what production now sends.
5. **The bounded sleep** — the alert retry path's total sleep is bounded. Demonstrated red
   first if the current fixture's value exceeds the chosen ceiling.

**Risk and rollback**

- *Correctness risk:* **one of the four send sites is missed**, so the retry path still
  sends unescaped HTML and the defect survives the fix with a plausible green suite.
  Mitigation: binding constraints 1 and 2, and the test must exercise the retry send.
- *Regression risk:* **a `TypeError` from an unchanged test stub.** This is a **known**
  consequence of option (a), budgeted in the same commit. It is not a regression to be
  triaged as one.
- *UX risk:* dropping HTML removes the anchor and the bold title. Mitigation: cosmetic
  only, and the commit body states it. Do not add a replacement formatting scheme "while
  you are there".
- *Design risk:* the wrong `html` import (C: stdlib `html` vs `django.utils.html`). Under
  option (b) this is the realistic failure and it produces a **silently wrong** message.
  Mitigation: binding constraint 3 and the explicit import in the code hint.
- *Rollback:* a straight revert restores the unescaped bodies. State plainly.

---

### BLOCK 7 — Make the immediate-alert dispatch observable and bounded (09-API-013, 09-VAL-009)

| | |
|---|---|
| **Findings owned** | `09-API-013` (MEDIUM) · the dispatch half of `09-VAL-009` |
| **Depends on** | **BLOCK 6** (hard — same module and same functions; BLOCK 6 must land first so the two commits do not collide) |
| **Blocks** | **the rollout gate on `IMMEDIATE_ALERTS_ENABLED`** — this block must land before any operator enables the flag |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM–HIGH** — the shutdown hook's registration point is genuinely uncertain (Q7), and a hook in the wrong process is a no-op that *looks* like a fix |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** The Researcher settles Q7 against the pinned gunicorn version; the Planner records the registration point and the backpressure shape; the Validator must be able to reject a hook that runs in the master |

**Decision required before implementation — Q7: where does the shutdown hook run?**

`gunicorn.conf.py` sets `preload_app = True` (C-7). The Django app — and therefore
`immediate_alerts` and its module-level `ThreadPoolExecutor` — is constructed in the
**master** before the workers fork. An `atexit`-style or `AppConfig.ready()`-style hook
registered at import time therefore belongs to the master's copy, not to the forked
children that actually hold in-flight sends.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Register the hook from a **worker-side** lifecycle point (a Django `AppConfig` `ready()` that is worker-local, or a gunicorn `worker_int`/signal hook in `gunicorn.conf.py`) | **Gains:** the hook runs where the sends are, which is the whole point. **Costs:** touches `gunicorn.conf.py` — a **production runtime** file — and adds an app-level registration whose correctness depends on the preload model staying as it is |
| **(b)** | Keep registration in the module, but make the shutdown cooperative: track in-flight batches in a module-level registry and have each `_run_send` check a shutdown flag **before** starting | **Gains:** no `gunicorn.conf.py` change; works regardless of which process owns the registry, because after `fork()` each child has its **own copy** and its own flag. **Costs:** does not cancel *already-queued* work the way `cancel_futures=True` does, so it reduces but does not eliminate the force-kill window |
| **(c)** | (a) **and** (b) together | **Gains:** the flag stops new work and the hook cancels the queue. **Costs:** two mechanisms for one outcome; the most code in the block |

**The Researcher must answer (a)'s feasibility against the pinned gunicorn version before
the block starts.** The block must be designed so that U10/U14 do not need answering
first — if the design cannot be validated without a production-like stack and a real
Telegram outage, that is a gate, not an obstacle.

**Decision required before implementation — the backpressure shape**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Track in-flight batches; above a threshold log a WARNING and **skip the send** | **Gains:** bounds the backlog; safe from a duplicate standpoint because `SavedSearchNotification` rows are written **before** the dispatch and the daily `send_alerts` digest is an unconditional safety net. **Costs:** alerts are genuinely dropped under sustained load — that is the intended shedding, and the counter must say so |
| **(b)** | Make `_MAX_DELIVERY_THREADS` a settings value so it can be tuned per environment | **Gains:** operator-tunable without a deploy. **Costs:** a **new env var** — its `ALLOWED_ENV_VARS` entry, four `.env*.example` updates and the code must land in **one commit** or `config/settings/tests/test_env_allowlist.py` fails in both directions. Phase 02 owns those files |
| **(c)** | Bounded submission only — reject `submit()` when the queue exceeds a threshold, without changing the alert semantics | **Gains:** the smallest change that bounds the buffer. **Costs:** the drop is invisible unless instrumented, which is test 1's job anyway |

**(a) is the report's recommendation and (b) is phase 02's file surface.** They are not
mutually exclusive, but (b) alone does not bound the backlog.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/services/immediate_alerts.py` | `deliver_immediate_alerts`, `_run_send`, `_send_payloads`, the module-level `_executor` and `_MAX_DELIVERY_THREADS` | The `Future` returned by `_executor.submit(...)` is **discarded** today. The module docstring's "daemon thread" description is stale |
| `gunicorn.conf.py` | `preload_app`, `graceful_timeout`, `timeout` | **Read before designing the hook.** `timeout = 60` and `graceful_timeout = 30` are confirmed by name |
| `config/settings/base.py` + four `.env*.example` | `_MAX_DELIVERY_THREADS` as a setting, **only** if option (b) is chosen | Phase 02's surface. Gated by `test_env_allowlist.py` in both directions |
| `src/backend/apps/search/tests/test_immediate_alerts.py` | `TestRunSendExceptionNarrowing`, `TestBotReuse`, `TestGatherIsolation`, `TestRetryAfterBackoff` | See below |
| `src/backend/apps/core/tests/test_observability.py` | the `/metrics` surface a counter lands on | Multiprocess counters are already the established pattern |

**Binding constraints**

1. **`test_non_aiogram_error_propagates` changes in this commit.** It asserts that a
   `RuntimeError` **propagates** out of `_run_send`, and the class docstring states
   *"`_run_send` catches AiogramError, not bare Exception"*. Raising the catch to
   `Exception` with `logger.exception` — which the report recommends — makes that test
   fail. **It encodes the defect as intended behaviour.** Same ruling as `09-VAL-004`:
   production code is king, the test changes, and it changes **here**.
2. **Never retrieve nothing.** Every submitted `Future` gets a done-callback that calls
   `future.exception()` and logs at ERROR with the payload count. A future nobody
   retrieves is a lost alert with no trace.
3. **Do not remove `return_exceptions=True` from the gather.** `TestGatherIsolation` pins
   it: a permanent failure must not cancel its siblings.
4. **Do not change the one-`Bot`-per-batch contract or the `finally: close session`
   behaviour.** `TestBotReuse` pins both.
5. **`deliver_immediate_alerts` must not block.** It is called from
   `transaction.on_commit` via `Ad.post_save`, where blocking is not an option. Any
   backpressure gate must be a **decision**, not a wait.
6. **`IMMEDIATE_ALERTS_ENABLED` must stay `False` in every environment until this block
   lands.** Phase 08 independently reinforces this. Phase 09 **does not change the flag**
   — it records the gate.
7. **The done-callback and any counter must work under multiprocess mode.**
   `gunicorn.conf.py` already sets up `PROMETHEUS_MULTIPROC_DIR` with a `child_exit` hook;
   follow the existing pattern rather than inventing one.

**Implementor task**

```yaml
id: task_09_b07_alert_dispatch
title: "Make the immediate-alert dispatch observable, bounded and shut down in the worker (09-API-013)"
priority: high
depends_on: ["task_09_b06_alert_escaping"]
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 7 - Make the immediate-alert dispatch observable and bounded"
source_blocks: ["BLOCK 7"]
description: >
  apps/search/services/immediate_alerts.py::deliver_immediate_alerts discards the Future
  returned by _executor.submit(_run_send, payloads), and _run_send catches only AiogramError
  - so any other exception is stored in a Future nobody retrieves and the alert is lost with
  no application log. The ThreadPoolExecutor's work queue is unbounded, so the 5-worker cap
  throttles concurrency without bounding backlog, and during a Telegram outage work
  accumulates with nothing to shed load. ThreadPoolExecutor joins its workers at
  interpreter exit, which can outlast gunicorn's graceful_timeout of 30 seconds.
  CRITICALLY: gunicorn.conf.py sets preload_app = True, so the module and its executor are
  constructed in the MASTER before the workers fork - an import-time shutdown hook lands in
  the master, not in the forked children holding the in-flight sends.
goals:
  - "make every submitted dispatch either complete or leave a retrievable trace"
  - "bound the backlog rather than only the concurrency"
  - "put the shutdown where the sends actually run"
  - "keep the flag off until all of the above is true"
files:
  - path: "src/backend/apps/search/services/immediate_alerts.py"
    targets:
      - type: function
        name: deliver_immediate_alerts
      - type: function
        name: _run_send
      - type: constant
        name: _executor
      - type: constant
        name: _MAX_DELIVERY_THREADS
  - path: "gunicorn.conf.py"
    targets:
      - type: constant
        name: preload_app
      - type: constant
        name: graceful_timeout
  - path: "src/backend/apps/search/tests/test_immediate_alerts.py"
    targets:
      - type: class
        name: TestRunSendExceptionNarrowing
changes:
  - action: modify_code
    description: >
      Attach a done-callback to every submitted Future that calls future.exception() and
      logs at ERROR with the payload count, so nothing is ever unretrieved. Raise _run_send's
      catch from AiogramError to Exception with logger.exception. Apply the recorded
      backpressure shape - track in-flight batches and, above a threshold, log a WARNING and
      skip the send. Register the shutdown hook at the Q7 registration point the
      Researcher confirmed, so it runs in the WORKER that owns the in-flight sends, and
      have it call _executor.shutdown(wait=False, cancel_futures=True).
    code_hint: |
      def _on_send_done(future: Future[None]) -> None:
          """Never leave a dispatch unretrieved.

          deliver_immediate_alerts is called from transaction.on_commit, so nothing above
          this submission will ever see an exception. Retrieving it here is the only place
          the failure becomes visible.
          """
          exc = future.exception()
          if exc is not None:
              logger.exception(
                  "Immediate-alert dispatch failed: %s", exc, exc_info=exc
              )
  - action: modify_test
    description: >
      In THIS SAME COMMIT: rewrite
      TestRunSendExceptionNarrowing::test_non_aiogram_error_propagates. It currently
      asserts a RuntimeError PROPAGATES and the class docstring states the AiogramError-only
      contract - both encode the defect. The test must instead assert the exception is
      logged and no longer escapes into a Future nobody reads. Leave TestBotReuse,
      TestGatherIsolation and TestRetryAfterBackoff unchanged.
  - action: add_test
    description: >
      A dispatch that raises a non-AiogramError leaves a retrievable ERROR log carrying
      the payload count. A backlog above the threshold logs a WARNING and issues no
      outbound call. And - the load-bearing one - the shutdown hook must be shown to run in
      the process that owns the sends: assert the registration point is worker-side, not at
      module import under preload_app = True.
acceptance_criteria:
  - "a dispatch raising a non-AiogramError produces a retrievable ERROR log with the payload count; nothing is lost silently"
  - "a backlog above the threshold produces a WARNING and issues no outbound send, and does not block the request thread"
  - "the shutdown hook runs in the worker that owns the in-flight sends, not only in the gunicorn master"
  - "TestBotReuse passes UNCHANGED: exactly one Bot per _send_payloads call, session closed in finally"
  - "TestGatherIsolation passes UNCHANGED: return_exceptions=True retained, a permanent failure does not cancel siblings"
  - "TestRunSendExceptionNarrowing now asserts the logged-and-contained contract, and the commit body says the old assertion encoded the defect"
  - "deliver_immediate_alerts still does not block and is still safe to call from transaction.on_commit"
  - "IMMEDIATE_ALERTS_ENABLED remains false in all four .env*.example templates - this block does not change the flag"
  - "if a new env var was introduced, its ALLOWED_ENV_VARS entry and all four template updates are in THIS commit"
tests_to_run:
  - "src/backend/apps/search/tests/test_immediate_alerts.py"
  - "src/backend/apps/core/tests/test_observability.py"
  - "src/backend/apps/search/tests/test_send_alerts_daily.py"
```

**Tests required**

1. **The failure is visible** — a dispatch raising a `RuntimeError` leaves a log record an
   operator can find. This is the assertion that distinguishes "caught and logged" from
   "stored in a Future nobody reads".
2. **The backlog is bounded** — above the threshold, the send is skipped with a WARNING
   and no outbound call. It must be a **decision**, not a wait: the caller is inside
   `on_commit`.
3. **The hook is in the right process** — the load-bearing test. A shutdown test that
   passes against a hook registered at import time proves nothing under `preload_app =
   True`. Assert the registration point, and assert it survives a fork.
4. **The existing contracts survive** — one `Bot` per batch, session closed in `finally`,
   `return_exceptions=True` on the gather, the pinned retry sleep values.

**Risk and rollback**

- *Correctness risk:* **the hook lands in the gunicorn master and does nothing in the
  workers**, while every test passes. This is the single highest-consequence failure in
  the block and it is invisible. Mitigation: Q7 is gated on a Researcher answer, and
  test 3 asserts the registration point rather than the outcome alone.
- *Correctness risk:* **raising `_run_send`'s catch to `Exception` hides a programming
  error** in the payload builder behind a log line. Mitigation: `logger.exception`, not
  `logger.warning` — the stack trace is preserved.
- *Availability risk:* the backpressure gate **drops real alerts** under sustained load.
  That is intended shedding, and it is safe from a duplicate standpoint only because
  `SavedSearchNotification` rows are written first and the daily digest is
  unconditional. Both facts must be stated in the commit body.
- *Contention risk:* `immediate_alerts.py` is claimed by **phase 03** (delivery state) and
  this is the module's third edit in this plan (BLOCKS 6, 7 and, for the docstring,
  16). Re-read before editing; stop and report on a concurrent change.
- *Rollback:* a straight revert restores the fire-and-forget contract. **Do not roll back
  and then enable the flag** — state that in the commit body.

---

### BLOCK 8 — Make a failed translation distinguishable from a real one (09-API-007)

| | |
|---|---|
| **Findings owned** | `09-API-007` (MEDIUM), **part (a) only** — part (b) is **rejected on evidence** (C-5) |
| **Depends on** | **nothing in-plan** |
| **Blocks** | nothing. Pairs with BLOCK 16 (same service, same signal) |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — the minimal option is small and keeps the whole `test_translation.py` suite green; the "better" option changes a service-layer return type and adds a contended migration |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four). The Researcher confirms the migration number is still free **immediately before** generating; the Planner records Q4; the Validator confirms a failed row stays re-runnable |

**Decision required before implementation — Q4: what is the shape of the failure signal?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** — **minimal** | In `_translate_for_backfill`, compare the result to the source; on equality leave the column `NULL`, count the row into a `fallback` total reported by the summary line **and** a `logger.warning`; add `--limit` to `add_arguments` | **Gains:** `translate_text`'s `str` signature is untouched, so **every test in `test_translation.py` stays green unchanged**; the row stays `NULL`, so the nullability-derived selection query matches it again and the backfill is **re-runnable** — which is the actual defect. Effort S, no migration. **Costs:** a *legitimate* translation that happens to equal the source is counted as a fallback — rare for `ru`→`en`/`bs`, but it is a false positive in the counter, and the `logger.warning` will name it |
| **(b)** — **status object** | Return a result object from `translate_text` (a `NamedTuple` / small dataclass, **not** Pydantic — this is a service layer, not a boundary) carrying the text and an explicit status, plus a `translation_failed_at` column so the backfill can target retries | **Gains:** the distinction is explicit at the source, so *no* caller can repeat the original mistake; a timestamp makes retry targeting possible. **Costs:** changes `translate_text`'s return type and **breaks every test in `test_translation.py`**; needs a migration in `apps/ads/` where phase 05 plans `0008_*`; effort M. **Every one of those costs is real** |
| **(c)** | (a) now, (b) later | **Gains:** closes the unrecoverable-data defect this cycle and keeps the migration out of a contended app. **Costs:** two changes to the same service; the second must not be forgotten |

**The Implementor may not choose.** (a) is what the evidence supports for this cycle; if
(b) is chosen, `test_translation.py` is rewritten **in this commit** and the migration
number is re-checked in the same breath.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/ads/management/commands/backfill_translations.py` | `_translate_for_backfill`, `Command.handle`, `Command.add_arguments` | 124 lines, **synchronous**, `--batch-size` (default 100) drives `iterator(chunk_size=…)`; there is **no** `--limit`. Selection is `Ad.objects.filter(title_en__isnull=True) \| Ad.objects.filter(title_bs__isnull=True)` |
| `src/backend/apps/core/services/translation.py` | `translate_text` | Read-only under option (a). Holds a module-level `httpx.Client`, a module-level `ThreadPoolExecutor(max_workers=4)` and an `@lru_cache(maxsize=256)` on `translate_cached_generic` — this is why option (b) is expensive |
| `src/backend/apps/ads/models.py` | `Ad.title_en`, `Ad.title_bs`, `Ad.original_language` | The columns whose nullability **is** the selection criterion |
| `src/backend/apps/ads/tests/test_backfill_translations.py` | `test_translation_failure_skips_gracefully`, `test_idempotent_when_all_translations_present`, `test_uses_translate_text_not_raw_api` | See below |
| `src/backend/apps/core/tests/test_translation.py` | the whole file | **Must stay green unchanged under option (a).** Under option (b) it is rewritten. `test_translation_error_log_does_not_leak_api_key` is a **security** guard — do not weaken it under either option |
| `apps/ads/migrations/` | the next free number | **Re-check immediately before generating.** Phase 05 plans `ads/0008_*` |

**Binding constraints**

1. **A failed translation must leave the column `NULL`.** Anything else re-creates the
   unrecoverable state: the row stops matching the selection query and the backfill never
   revisits it. This is the whole of the confirmed defect.
2. **The summary line and a `logger.warning` must both report the `fallback` total**, so a
   partially-degraded run is visible *and* re-runnable.
3. **`test_translation_failure_skips_gracefully` changes in this commit.** It currently
   asserts the untranslated Russian **is** written into `title_en`, `title_bs` and both
   description columns, with `original_language == "ru"`, and its docstring calls this
   *"Path A consistency"*. **That is the defect stated as intended behaviour.** Production
   code is king; the test changes, and the commit body says the old assertion documented
   the defect.
4. **Do not skip the `translate_text` call for an already-populated field**, and do not
   change the source locale. `test_uses_translate_text_not_raw_api` asserts
   `call_count == 4` and the `"ru"` source — the fix must not "optimise" around it.
5. **`--limit` is a pure addition** to `add_arguments`. Do **not** add batching, an event
   loop or `asyncio.run` — part (b) of this finding is **rejected on evidence** (C-5) and
   re-implementing it would be acting on a claim the tree contradicts.
6. **Under option (a), do not change `translate_text`'s return type.** Under option (b),
   a `NamedTuple` or small dataclass matches this codebase's style; **Pydantic is for
   boundaries**, and a service-layer return value is not one.
7. **Check the migration number in the same breath as generating it.** Phases 05 and 06 are
   both landing `apps/ads` / `apps/users` migrations. Never renumber an applied migration.

**Implementor task**

```yaml
id: task_09_b08_translation_signal
title: "Make a failed translation distinguishable from a real one (09-API-007)"
priority: high
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 8 - Make a failed translation distinguishable from a real one"
source_blocks: ["BLOCK 8"]
description: >
  apps/core/services/translation.py::translate_text returns the UNMODIFIED SOURCE on every
  failure path - open breaker, empty body, non-2xx, invalid key, timeout. The caller cannot
  tell that from a translation. backfill_translations.py::_translate_for_backfill returns
  that value verbatim and Command.handle writes it into title_en / title_bs
  unconditionally, so the row no longer matches the command's nullability-derived selection
  query
  (Ad.objects.filter(title_en__isnull=True) | Ad.objects.filter(title_bs__isnull=True))
  and the backfill NEVER revisits it. The damage is permanent and the command reports
  success.
goals:
  - "leave a failed translation NULL so the backfill can retry it"
  - "make a partially-degraded run visible in the summary and in the log"
  - "bound the command with --limit"
  - "keep the whole test_translation.py suite green under option (a)"
files:
  - path: "src/backend/apps/ads/management/commands/backfill_translations.py"
    targets:
      - type: function
        name: _translate_for_backfill
      - type: class
        name: Command
      - type: method
        name: handle
      - type: method
        name: add_arguments
  - path: "src/backend/apps/ads/tests/test_backfill_translations.py"
    targets:
      - type: class
        name: TestBackfillTranslations
      - type: function
        name: test_translation_failure_skips_gracefully
  - path: "src/backend/apps/core/services/translation.py"
    targets:
      - type: function
        name: translate_text
changes:
  - action: modify_code
    description: >
      Apply the Q4 option. Under option (a): _translate_for_backfill compares the result to
      the source and signals "this is the original" so Command.handle leaves the column
      NULL, counts the row into a fallback total reported by the summary line and by a
      logger.warning naming the ad and the field. Add --limit to add_arguments as a pure
      addition. Under option (b): change translate_text to return an explicit status (a
      NamedTuple or small dataclass - NOT Pydantic), add the translation_failed_at column
      via a NEW migration, and rewrite the consumers in the SAME commit.
    code_hint: |
      # Option (a) - the degradation path returns a VALUE where the caller needs a STATUS.
      # Compare, and leave the column NULL so the nullability-derived selection query
      # matches the row again on the next run.
      translated = _translate_for_backfill(text, target)
      if translated == text:
          fallbacks.append((ad_id, field))
          continue  # updates[field] stays absent -> the column remains NULL
      updates[field] = translated
  - action: modify_test
    description: >
      Rewrite test_translation_failure_skips_gracefully in THIS SAME COMMIT. It currently
      asserts ad.title_en == the untranslated Russian text, ad.title_bs likewise, both
      description fields likewise, and original_language == "ru", with a docstring calling
      it "Path A consistency" - that is the defect as intended behaviour. The replacement
      asserts the columns stay NULL, the row is counted in the fallback total, and a
      SECOND run of the command revisits the same row. Leave
      test_idempotent_when_all_translations_present and
      test_uses_translate_text_not_raw_api unchanged. Under option (b), test_translation.py
      is rewritten in the same commit and
      test_translation_error_log_does_not_leak_api_key must not be weakened.
acceptance_criteria:
  - "a translation failure leaves title_en and title_bs NULL, so the row still matches the command's selection query on a second run"
  - "the summary line AND a logger.warning both report the fallback count, naming the ad and the field"
  - "a second run of the command revisits the same failed row - this is the assertion that distinguishes the fix from the defect"
  - "a successful translation is still written and the row is still marked processed"
  - "test_uses_translate_text_not_raw_api passes UNCHANGED: the call is not skipped for a populated field and the source locale stays 'ru'"
  - "test_translation.py passes unchanged under option (a); under option (b) its rewrite is in this commit and the API-key non-leakage test is not weakened"
  - "--limit exists and bounds the run"
  - "no asyncio.run, no batching and no event loop were introduced - part (b) of this finding is rejected on evidence"
  - "no user-visible string added; --limit appears in the command's help, which is operator-facing, not translated"
  - "under option (b) only: a NEW migration exists, its number was checked against apps/ads/migrations/ immediately before generation, and no applied migration was renumbered"
  - "the commit body names the Q4 option and states that the old test assertion documented the defect"
tests_to_run:
  - "src/backend/apps/ads/tests/test_backfill_translations.py"
  - "src/backend/apps/core/tests/test_translation.py"
  - "src/backend/apps/search/tests/test_search_translation_outage.py"
```

**Tests required**

1. **The row survives the failure** — the columns stay `NULL`. This is the finding,
   expressed as an assertion.
2. **The re-run finds it again** — the command runs twice and the second run revisits the
   same row. **This is the test that distinguishes the fix from the defect**: without it,
   a command that writes `NULL` but filters on something else would pass test 1 and remain
   unrecoverable.
3. **The degradation is visible** — the summary line and a WARNING both carry the count.
4. **The success path is unchanged** — a successful translation is written, the row is
   marked processed, and an already-populated field is not re-translated.
5. **Search stays up** — `test_search_translation_outage.py` must pass unchanged.

**Risk and rollback**

- *Data risk:* option (a) leaves `NULL` rows that a consumer might not expect. Mitigation:
  the column was already nullable and `NULL` is the command's own definition of "missing";
  the selection query proves it.
- *Implementation risk:* **the equality comparison misfires** on a legitimate translation
  identical to the source, producing a false `fallback` count. Mitigation: the counter is
  a signal, not a gate; the `logger.warning` names the ad and field so the case is
  recognisable. State it in the commit body.
- *Regression risk:* the command **silently does nothing** on a run where every translation
  fails, and the operator reads the new summary line as success. Mitigation: the fallback
  total is on the summary line and at WARNING — this is the improvement over the current
  behaviour, where the same run reports 0 failures and exit 0.
- *Migration risk (option (b) only):* the migration number is contended with phase 05.
  Mitigation: binding constraint 7 and a `--create-db` run after the migration.
- *Rollback:* reverting restores the unrecoverable write. State plainly.

---

### BLOCK 9 — `EMAIL_HOST`: replace the boot gate with a loud warning, and correct the reason at six sites (09-API-009)

| | |
|---|---|
| **Findings owned** | `09-API-009` (MEDIUM, **P2 priority — first in decision order**) |
| **Depends on** | **nothing in-plan.** Q1 was the gate; it is **answered** (2026-10-03) |
| **Blocks** | nothing in-plan. **Adjacent to and actioned in one pass with** `02-CFG-004` (`09-VAL-001`) |
| **Priority** | **P2 by severity, first by decision order — now no longer blocked** |
| **Risk level** | **MEDIUM** — the doc half is trivial; the settings half changes **whether a container starts**, and `prod.py` is the most contended settings file in the repository. Under the chosen option the change is **strictly less** dangerous than option (a): a warning cannot stop a deploy |
| **Required agents** | **Auditor · Planner · Validator.** Q1 was answered by the **Product Owner** (2026-10-03) — the Implementor is forbidden from choosing, and equally forbidden from shipping the raising guard. **Researcher** is no longer required: there is no runtime consequence to reproduce |

**Q1 RESOLVED 2026-10-03 (Product Owner) — a LOUD WARNING, not a boot gate**

**The ruling: option (b), on the owner's own severity.** In production with `EMAIL_HOST` unset,
`config/settings/prod.py` emits a **loud warning** and the import **succeeds**. It **must not
raise `ImproperlyConfigured`**, and **no test may assert that it fires**. The six comment sites
— and the compromise-response procedure — that describe it as a boot gate **must be corrected
to match**. The options are retained below for traceability; the Implementor may **not**
re-choose.

**What this supersedes.** §0.6.2's *"the guard is code, not a decision"* reading priced demotion
as the **option** and treated the existing raising guard as the shape to keep. **The owner has
chosen the warning.** Everything §0.6.2 established as *evidence* still stands and is still the
reason this block is worth doing — the three named flows are fictional, no test asserts the
guard fires, and there are **six** correction sites in three files. What changed is the
conclusion, not the facts.

| Option | What it is | Consequences |
|---|---|---|
| ~~**(a)**~~ | Keep `EMAIL_HOST` **mandatory** and justify it correctly at all sites | **NOT CHOSEN.** It would leave a staging or DR host unable to boot for an integration that fails open by design. Recorded so the reasoning is not re-derived |
| **(b) — CHOSEN 2026-10-03** | **A loud `logging.getLogger(__name__).warning` at settings import**, matching the delivery path's own fail-open behaviour | **Adopted.** The site boots; only the support-desk e-mail degrades, which is **exactly what the code already does**. **The cost the owner accepted:** a support escalation can be lost on a host that never noticed the warning — so the warning must be loud, must name the setting **and** the consequence, and `docs/ops/docker-deployment.md` must say what is lost |

**Whichever option had been chosen, the reason had to be corrected at all six sites** —
`config/settings/prod.py`'s guard comment (which becomes the warning's comment),
`docs/ops/docker-deployment.md` (three sentences: the secret-table row, secret-rotation step 4,
the guard-description bullet) and `docs/ops/rollback.md` (one table row), **plus the two
correction sites §0.6.2 found beyond the plan's own count** — `test_prod_logging.py`,
`test_csrf_trusted_origins.py` and the third comment in `config/settings/base.py`.
Correcting only the settings comment leaves **five** statements asserting a feature that does
not exist, **two of them inside the compromise-response procedure**. **A partial correction is
a defect.**

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/config/settings/prod.py` | the `EMAIL_HOST` fail-fast guard and its comment | **Four-block contended file** — phase 02 (BLOCKS 3/5/7/9) and phase 06 (BLOCK 4) both edit it. `config/settings/prod.py` also holds the `BOT_TOKEN` guard, which is BLOCK 14's surface. **Per the 2026-10-03 ruling the guard is replaced, not justified** |
| `docs/ops/docker-deployment.md` | three sentences asserting password-reset token behaviour; plus the guard-description bullet | **Contended** — phase 01, 02 and 08 all touch it. Two of the three are in the secret-rotation procedure. The same bullet mis-attributes the `REDIS_URL` fail-fast guard to **`CFG-001`**, which in the current phase-02 numbering is `DJANGO_ONESHOT=1` disabling the prod secret guards — a different defect (`09-VAL-003`) |
| `docs/ops/rollback.md` | the `DJANGO_SECRET_KEY` table row | The rollback counterpart |
| `src/telegram_bot/services/support_delivery_email.py` | `send_support_notification_email` | **Read-only.** Its fail-open behaviour is the **reference** the ruling is argued from. **Not** `deliver_support_ticket_email` — that symbol does not exist (C-1) |
| `src/backend/config/settings/tests/test_settings_secrets.py` | `test_django_oneshot_does_not_bypass_prod_secrets` and the tests that set `EMAIL_HOST` to get past the guard | ✔ Confirmed by the ruling's own premise: **no test asserts that a missing `EMAIL_HOST` alone raises**, so demotion is test-safe. The `config/settings/tests/` package must be run **whole** |
| `src/backend/config/settings/tests/test_deploy_check_env_parity.py` | the guard-count taxonomy in its docstring | **New in this block.** Demoting `EMAIL_HOST` makes "six guards raise `ImproperlyConfigured`" false; the docstring must be corrected in the same commit |
| `src/backend/config/settings/tests/test_prod_logging.py`, `test_csrf_trusted_origins.py` | the comments asserting the guard exists | **Two of the six correction sites**, found by §0.6.2 beyond the plan's own count of five |
| `src/backend/config/settings/tests/test_env_allowlist.py` | the allowlist gate | All nine email keys are already allowlisted, and **no new env var is introduced** — so this gate is not engaged. It is listed so its "green in both directions" status is an explicit acceptance criterion |

**Binding constraints**

1. **Q1 is answered — the guard becomes a WARNING.** This is a Product Owner ruling
   (2026-10-03), not a Planner's. **The settings guard must NOT raise
   `ImproperlyConfigured`**, and **no test may be added that asserts it raises**. Silence is
   not an acceptable outcome for any *other* gate in this plan; there is no gate left here.
2. **All six comment sites are corrected**, in the same commit as the warning. Under the
   chosen option the comment *becomes* the warning's rationale, and it must state the real
   consequence — seller escalations to the admin inbox are silently lost.
3. **The warning must use `logging.getLogger(__name__)`** — `prod.py` already imports
   `logging` for exactly this. **No `print()`**, lazy `%s` formatting, and the message must
   name the setting and the consequence, not just "unset".
4. **`test_deploy_check_env_parity.py`'s taxonomy loses one entry in the same commit.** Its
   docstring counts the guards that raise `ImproperlyConfigured`; demoting one makes that
   count wrong, and a docstring that lies about the guard set is the same defect as the
   comments this block exists to fix.
5. **Correct the `CFG-001` mis-attribution in the same pass.** It is a stale cross-phase
   citation in the same bullet, and `docs/ops/docker-deployment.md` is being edited by
   several agents; a second edit pass is a second clobber risk.
6. **Do not touch `EMAIL_BACKEND`.** That is `02-CFG-004` — the *backend-selection*
   problem (a prod operator can point mail at stdout). Phase 02 owns it. Phase 09 owns the
   *existence-of-consumers* question. **Action both in one pass; report them as two
   findings** (`09-VAL-001`).
7. **Do not weaken any other guard in `prod.py`.** `DJANGO_SECRET_KEY`, `BOT_TOKEN`,
   `GOOGLE_TRANSLATE_API_KEY`, `SITE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
   `REDIS_URL` and `BOT_USERNAME` are all guarded, and the same bullet's list of three is
   stale against those nine.
8. **Do not assert the report's quoted log string** (C-2). `"Support email delivery failed
   (continuing)"` does not exist. Assert **behaviour**.
9. **No new environment variable and no new secret surface.** The warning reads a setting that
   already exists in `ALLOWED_ENV_VARS`; nothing is added, so `test_env_allowlist.py` is
   unaffected in either direction.

**Implementor task**

```yaml
id: task_09_b09_email_host
title: "Replace the EMAIL_HOST boot gate with a loud warning and correct the reason at six sites (09-API-009)"
priority: medium
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 9 - EMAIL_HOST: correct the reason at five sites"
source_blocks: ["BLOCK 9"]
description: >
  config/settings/prod.py makes EMAIL_HOST a hard boot gate for the entire system, and
  justifies it with "transactional emails (password resets, alert notifications, seller
  confirmations) are deliverable". NONE of those flows exist: there is no password-reset
  view, URL, template, token_generator, PasswordResetView or PasswordResetForm anywhere
  under src/; alerts are Telegram; publishing is a Telegram reply. The only real e-mail
  consumer is telegram_bot/services/support_delivery_email.py::send_support_notification_email
  - note the name; the report's deliver_support_ticket_email does not exist - and it is
  explicitly fail-open. The fiction is repeated at SIX sites, two of them inside the
  secret-rotation and compromise-response procedure. The Product Owner ruled on 2026-10-03:
  a LOUD WARNING, not a boot gate.
goals:
  - "make every stated reason match the flows that actually exist"
  - "make the guard match the real blast radius, per the Q1 decision"
  - "correct the stale CFG-001 attribution in the same bullet"
  - "leave every other prod.py guard untouched"
files:
  - path: "src/backend/config/settings/prod.py"
    targets:
      - type: module
        name: prod
      - type: constant
        name: EMAIL_HOST
  - path: "docs/ops/docker-deployment.md"
    targets:
      - type: module
        name: docker_deployment
  - path: "docs/ops/rollback.md"
    targets:
      - type: module
        name: rollback
  - path: "src/backend/config/settings/tests/test_settings_secrets.py"
    targets:
      - type: module
        name: test_settings_secrets
changes:
  - action: modify_code
    description: >
      Q1 is RESOLVED 2026-10-03 as option (b): REPLACE the raising guard with a
      logging.getLogger(__name__).warning that names the setting AND the consequence - seller
      escalations to the admin inbox will be silently lost, while the site otherwise serves
      normally - using lazy %s formatting. The import must NOT raise ImproperlyConfigured. Do
      NOT add a test asserting that it raises. Update the reason at all SIX sites (prod.py's
      comment, docker-deployment.md's three sentences, rollback.md's table row, and the
      comments in test_prod_logging.py and test_csrf_trusted_origins.py), and correct the
      CFG-001 mis-attribution in the docker-deployment guard bullet in the same pass.
    code_hint: |
      # Q1 option (b) - RESOLVED 2026-10-03 by the Product Owner.
      # This REPLACES the guard. It must not raise, and the message must name
      # the setting and the consequence.
      if not EMAIL_HOST:  # noqa: F405
          logger.warning(
              "EMAIL_HOST is not set. The support-desk notification is the only "
              "transactional e-mail this system sends; without it, seller escalations "
              "to the admin inbox are silently lost. The site otherwise serves normally."
          )
  - action: modify_doc
    description: >
      docs/ops/docker-deployment.md: three sentences claim password-reset token
      invalidation on DJANGO_SECRET_KEY rotation. Two are in the compromise-response
      procedure. Replace each with what actually happens - sessions and CSRF tokens are
      invalidated; no password-reset flow exists. docs/ops/rollback.md: the same
      correction in the DJANGO_SECRET_KEY row. Do NOT add a new feature description.
  - action: modify_test
    description: >
      Add a test that a prod settings import with EMAIL_HOST unset SUCCEEDS and logs a
      WARNING naming the setting and the consequence. Do NOT add a test asserting the guard
      raises - that is now forbidden by the ruling. Update test_deploy_check_env_parity.py's
      guard-count docstring so it no longer counts EMAIL_HOST among the raising guards, and
      correct the two stale comments in test_prod_logging.py and test_csrf_trusted_origins.py.
      Run the WHOLE config/settings/tests/ package: test_settings_secrets.py and
      test_prod_logging.py share a cross-module import.
acceptance_criteria:
  - "a prod settings import with EMAIL_HOST unset SUCCEEDS and emits a WARNING naming the setting and the consequence"
  - "no shipped file asserts that a missing EMAIL_HOST raises ImproperlyConfigured, and no test asserts it fires"
  - "no shipped file asserts a password-reset, e-mail-alert or seller-confirmation flow - grep for 'password-reset' across docs/ and src/backend/config/settings/ returns only corrected statements"
  - "the guard-description bullet no longer attributes the REDIS_URL fail-fast guard to CFG-001"
  - "test_deploy_check_env_parity.py's guard taxonomy no longer counts EMAIL_HOST, and its docstring is corrected in the same commit"
  - "the comments in test_prod_logging.py and test_csrf_trusted_origins.py no longer assert that the guard exists"
  - "test_django_oneshot_does_not_bypass_prod_secrets passes unchanged"
  - "the whole config/settings/tests/ package passes"
  - "no other prod.py guard changed; EMAIL_BACKEND was not touched (that is 02-CFG-004)"
  - "test_env_allowlist.py is green in both directions - no new env key was added"
  - "the report's quoted log string 'Support email delivery failed (continuing)' appears nowhere - it does not exist in the tree"
  - "the commit body names the Q1 ruling, its date (2026-10-03) and who made it"
tests_to_run:
  - "src/backend/config/settings/tests/"
  - "src/telegram_bot/tests/test_support_delivery_email.py"
  - "src/backend/tests/test_docs_ci_parity.py"
  - "src/backend/apps/core/tests/test_deploy_workflow.py"
```

**Tests required**

1. **The warning's behaviour** — a prod settings import with `EMAIL_HOST` unset **succeeds**
   and emits a **WARNING** naming the setting **and** the consequence. Assert the
   **behaviour**, not the comment. **No test asserts that it raises** — that shape is
   forbidden by the ruling.
2. **No other guard moved** — the `DJANGO_SECRET_KEY`, `BOT_TOKEN`,
   `GOOGLE_TRANSLATE_API_KEY`, `SITE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
   `REDIS_URL` and `BOT_USERNAME` guards are unchanged. A structural assertion over the
   settings module is better here than a prose check, because this is exactly the class of
   change that silences a second guard "while you are there".
3. **The docs** — a text assertion that the password-reset claims are gone from **all six**
   sites, that `CFG-001` is no longer mis-attributed, and that the guard-count taxonomy in
   `test_deploy_check_env_parity.py` matches reality. `test_docs_ci_parity.py` and
   `test_deploy_workflow.py` already parse these files; extend rather than duplicate.

**Risk and rollback**

- *Availability risk:* **removed by the ruling.** Option (a)'s residual — a staging or DR host
  that cannot boot without SMTP — no longer exists. What replaces it is the accepted cost:
  a host that never noticed the warning loses support escalations. The warning names the
  consequence; phase 12 owns the runbook line that says what to do about it.
- *Regression risk:* the demotion is applied a second time elsewhere, or the
  `test_deploy_check_env_parity.py` count is left stale. Both are acceptance criteria and both
  fail the block.
- *Contention risk — the highest in this block:* `config/settings/prod.py` is edited by
  phase 02 **and** phase 06, and `docs/ops/docker-deployment.md` has been touched by phase
  01, 02 and 08. Re-read immediately before editing; **stop and report** on a concurrent
  change rather than clobbering it.
- *Documentation risk:* correcting only `prod.py` leaves five runbook statements asserting a
  feature that does not exist — two of them telling an operator, mid-incident, that
  rotating a key expires links that never existed. That is the most likely phase-09 finding
  to cause a **wrong operational decision**, which is why it outranks its severity in the
  ordering.
- *Rollback:* a straight revert restores the fiction **and** the boot gate. State plainly that
  the revert reintroduces an availability dependency for a capability that does not exist.

---

### BLOCK 10 — Rate `/media/` at the proxy and in the view (09-API-005)

| | |
|---|---|
| **Findings owned** | `09-API-005` (MEDIUM) |
| **Depends on** | **nothing in-plan.** Shares `docker/nginx/nginx.conf` with BLOCKS 11 and 12 — see §4.2 for the serial edges |
| **Blocks** | nothing in-plan. **Phase 13 must assume this landed** before re-measuring the duplicated query |
| **Priority** | **P1** |
| **Risk level** | **LOW–MEDIUM** — a small config change, but `nginx.dev.conf` is the *thinner* file and a prod-only fix silently leaves dev uncovered |
| **Required agents** | **Auditor · Planner · Validator.** No Researcher is required — the defect is statically confirmed and the mitigation is one nginx directive per file |

**What is confirmed.** `location /media/` is the **only** anonymous, DB-backed path with
**neither** a `limit_req` zone nor an application-level limiter. nginx resolves the
**longest** matching prefix, so a `/media/…` request never falls through to `location /`
and the catch-all `browse_limit` zone does not cover it. Its sibling on the same module,
`listings`, *does* have an app-level limiter. `/static/` is also unrated and is whitenoise
with no DB work — correctly harmless.

**Decision required before implementation — the zone shape**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | A **tighter, separate** `media_limit` zone declared in **each** file's own `http{}`, applied to `location /media/`, plus the same application-level limiter `listings` uses | **Gains:** the point is to protect the **database**, not the user, so a tighter budget than `browse_limit` is right; the app-level half means the control survives the proxy being removed. **Costs:** two files, four edits, plus a new guard on the hot path |
| **(b)** | The nginx zone only | **Gains:** the minimum that closes the reported gap. **Costs:** the control lives in **one file only**, which is the same single-point-of-failure pattern `09-API-014` flags for `/metrics` |
| **(c)** | The app-level limiter only | **Gains:** reaches the view even if the proxy is bypassed. **Costs:** the DB sees the request first — the zone is the whole point of the finding |

**(a) is the report's recommendation.** Note that zones are per-`http`-context and are
**not** inherited across files, so the declaration must appear in both.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `docker/nginx/nginx.conf` | the `http{}` `limit_req_zone` declarations; `location /media/` | Currently three zones: `login_limit` 10r/s, `search_limit` 20r/s, `browse_limit` 20r/s |
| `docker/nginx/nginx.dev.conf` | the same two targets | **Thinner**: no `/health/`, no `/csp-report/`, no `= /metrics`. **Same three zones** |
| `src/backend/apps/ads/views/listings.py` | `media_gate` | No app-level limiter; also runs the **same** `AdImage.objects.filter(key_q)` query **twice** on a valid request (the first result is not reused). De-duplication is a **bonus, not a requirement** |
| `src/backend/apps/ads/views/listings.py` | `listings` | The sibling that **does** call `check_deep_link_render_rate_limit` — copy its shape |
| `src/backend/tests/test_nginx_config.py` | the `_location_block` helper and the existing `/metrics` tests | **The established home for structural nginx assertions.** It parses **`nginx.conf` only** — extend it to `nginx.dev.conf` as part of this block |
| `src/backend/apps/ads/tests/test_media_security.py` | the `media_gate` access-control assertions | A de-duplication must change **no** status code it asserts |

**Binding constraints**

1. **Keep `$binary_remote_addr`.** Do **not** switch to `$proxy_add_x_forwarded_for`; the
   XFF-first form is bypassable (`04-AUT-003`). If an app-level limiter is added, note that
   `contact_rate_limit._get_client_ip` **does** read `HTTP_X_FORWARDED_FOR` and therefore
   inherits that trust assumption — **which is phase 08's / phase 04's item, not this
   phase's**. Do not change the trust model here.
2. **Both config files.** A zone declared in one file does not exist in the other.
3. **De-duplicating the `AdImage` query is optional.** If it is done, no status code in
   `test_media_security.py` may change, and phase 13 must be told so it does not
   re-measure a phase-09-owned defect.
4. **Do not touch `location /static/`.** Its lack of a zone is correct.
5. **The structural test must parse the shipped file**, so the next `location` block added
   cannot silently miss a zone — that is the report's actual ask, and it is worth more than
   the one directive.

**Implementor task**

```yaml
id: task_09_b10_media_limit
title: "Rate /media/ at the proxy and in the view, and make the assignment structural (09-API-005)"
priority: medium
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 10 - Rate /media/ at the proxy and in the view"
source_blocks: ["BLOCK 10"]
description: >
  Every public path in both nginx configs declares a limit_req zone EXCEPT
  location /media/. Because nginx resolves the longest matching prefix, a /media/ request
  never falls through to location /, so the catch-all browse_limit zone does not cover it
  - the zone is simply absent. The Django view behind it has no application-level limiter
  either, and its sibling on the same module (listings) does. /media/ is therefore the only
  anonymous, DB-backed path with neither control. media_gate also runs the same
  AdImage.objects.filter(key_q) query twice on a valid request.
goals:
  - "give /media/ a tighter, separate zone in BOTH shipped configs"
  - "add the same application-level limiter listings already uses"
  - "make the zone assignment a structural assertion, not a convention"
  - "leave the client-IP trust model untouched"
files:
  - path: "docker/nginx/nginx.conf"
    targets:
      - type: module
        name: nginx_conf
  - path: "docker/nginx/nginx.dev.conf"
    targets:
      - type: module
        name: nginx_dev_conf
  - path: "src/backend/apps/ads/views/listings.py"
    targets:
      - type: function
        name: media_gate
      - type: function
        name: listings
  - path: "src/backend/tests/test_nginx_config.py"
    targets:
      - type: function
        name: _location_block
changes:
  - action: modify_code
    description: >
      Declare a tighter media_limit zone in EACH file's own http{} block (zones are
      per-http-context and are not inherited across files) and apply it to
      location /media/. Keep $binary_remote_addr - do NOT switch to
      $proxy_add_x_forwarded_for; the XFF-first form is bypassable (04-AUT-003). Add the
      same application-level limiter to media_gate that listings already uses. Optionally
      de-duplicate the repeated AdImage existence query; this is a bonus, not a
      requirement, and must not change any status code test_media_security.py asserts.
    code_hint: |
      limit_req_zone $binary_remote_addr zone=media_limit:10m rate=30r/s;
      # ...
      location /media/ {
          limit_req zone=media_limit burst=60 nodelay;
          # ...
      }
  - action: modify_test
    description: >
      Extend test_nginx_config.py: parse BOTH docker/nginx/nginx.conf and
      docker/nginx/nginx.dev.conf and assert that location /media/ carries a limit_req
      zone, that the zone is declared in that file's own http{} block, and that the key is
      $binary_remote_addr rather than an XFF-derived variable. Add a view-level test that a
      burst on media_gate is refused at the application limiter.
acceptance_criteria:
  - "both nginx configs declare media_limit in their own http{} and apply it to location /media/"
  - "the zone key is $binary_remote_addr - no XFF-derived key anywhere in this block's diff"
  - "a burst on media_gate is refused by the application-level limiter"
  - "test_nginx_config.py's existing /metrics assertions still pass (proxy_pass, four proxy headers, allow 127.0.0.1 + deny all)"
  - "no status code asserted by test_media_security.py changed"
  - "the structural test parses both shipped files, so a location block added next year without a zone fails the suite"
  - "location /static/ untouched"
  - "the commit body states whether the AdImage de-duplication was done, and tells phase 13 not to re-measure it"
tests_to_run:
  - "src/backend/tests/test_nginx_config.py"
  - "src/backend/apps/ads/tests/test_media_security.py"
  - "src/backend/apps/ads/tests/test_ad_detail_queries.py"
```

**Tests required**

1. **The structural assertion** — parsing the shipped config, `location /media/` carries a
   `limit_req`, the zone is declared in that file's own `http{}`, and the key is
   `$binary_remote_addr`. This is the test with lasting value: it fails when the *next*
   block is added without a zone.
2. **Both files** — the dev config is a separate file with its own `http{}`; a test that
   only reads `nginx.conf` passes while dev stays uncovered.
3. **The view limiter** — a burst is refused. Assert on the response, not on the helper's
   return value.
4. **No access-control regression** — `test_media_security.py` unchanged.

**Risk and rollback**

- *Availability risk:* **the zone is too tight for a real burst**, e.g. a page loading many
  thumbnails at once with `nodelay` discarding the excess. Mitigation: `burst` and `nodelay`
  are part of the shipped shape; the commit body states the numbers so they can be tuned
  deliberately.
- *Configuration risk:* **a zone declared in the wrong `http{}` context, or in one file
  only**, silently does nothing. Mitigation: the structural test parses the shipped file.
  **Run `nginx -t` before rolling** — this is a proxy change and a syntax error takes the
  site down.
- *Regression risk:* the app-level limiter uses a client-IP helper that trusts
  `HTTP_X_FORWARDED_FOR`. That trust assumption is **phase 08's / phase 04's item** — do not
  change it here, and record it.
- *Re-grade trigger:* if a scraper is ever observed against `/media/`, this must be
  re-graded **immediately** upward — the MEDIUM grade rests on the absence of observed
  traffic.
- *Rollback:* removing the directive and the guard restores the unrated path.

---

### BLOCK 11 — The API-surface and nginx contract bundle (09-API-010, 09-API-014)

| | |
|---|---|
| **Findings owned** | `09-API-010` (LOW) · `09-API-014` (LOW) |
| **Depends on** | **BLOCK 10** (soft — same files; see §4.2) |
| **Blocks** | nothing in-plan. **Phase 15 owns the authorization boundary** — check before building the `/metrics` gate |
| **Priority** | **P2** |
| **Risk level** | **MEDIUM — this is the only block that can break a *working* deployment.** `09-API-010` requires the operator to set a real `server_name` |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** Q3 is a Researcher pre-step (one `curl`, U13) and Q14 is gated |

**Two LOW findings, one config file, one coherent bundle.** Individually small; together
they are the maintenance tax of an API layer grown by accretion.

**Decision required before implementation — Q14: the `:80` redirect shape**

The `:80` listener has **no `server_name`** and **no `default_server`**, and its sole job
is `return 301 https://$host$request_uri;`. The `:443` block **does** declare
`server_name _;` — the asymmetry is specific to the plaintext listener.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Give the `:80` block an explicit `server_name <site-domain>;` **and** add a second `listen 80 default_server;` block that `return 444;` (nginx closes the connection with no response at all), keeping the 301 only inside the named block | **Gains:** correct, and the default server drops an unmatched `Host` instead of reflecting it. **Costs:** **requires the operator to set a real domain.** A fresh clone with a self-signed mkcert cert in dev would then redirect to a name that does not resolve. This is the option the report recommends |
| **(b)** | Use `$server_name` instead of `$host` in the single existing block | **Gains:** one line; **fails closed** — with no name configured it resolves to the literal empty string rather than the client's header. **Costs:** the redirect target becomes empty in exactly the configuration the project ships, so it must be paired with option (a) for production |
| **(c)** | Leave the `:80` block alone and fix only the other items | **Gains:** zero deployment risk. **Costs:** the missing `server_name` remains a real misconfiguration trap — an operator who adds a second vhost to this file gets surprising behaviour. **The LOW grade must not suppress the fix** |

**Rollout rule, binding:** `nginx -t` before rolling. Coordinate with the domain/TLS work
in the deployment runbook. **Phase 12 owns the runbook.**

**Decision required before implementation — Q2: by what mechanism is `/metrics` restricted in Django?**

`config/urls.py` mounts `path("", include("django_prometheus.urls"))` at the **root**, so
`/metrics` is unauthenticated in Django. nginx's `allow 127.0.0.1; deny all;` is the only
other control, and it lives in **one file**.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | A `config/urls.py`-level wrapper view in front of the metrics routes | **Gains:** the smallest honest option; one file; the control mirrors nginx's rather than inventing a new mechanism. **Costs:** must keep `/metrics` working for the Prometheus scrape from inside the container |
| **(b)** | A middleware | **Gains:** uniform, and applies to any future path. **Costs:** middleware runs on **every** request to evaluate a condition that is true for exactly one path — that is a cost paid by the whole site to protect one route |
| **(c)** | `django_prometheus`'s own auth hook | **Gains:** uses the library's intended seam. **Costs:** the library's supported surface must be verified against the pinned version before relying on it |

**Check the phase-15 boundary before building any of them** — phase 15 owns permission
predicates and per-request gates, and two adjacent mechanisms is worse than one.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `docker/nginx/nginx.conf` · `nginx.dev.conf` | the `:80` `server {}` block; the `listen 443 ssl` block; every proxied `location`'s `proxy_set_header` set | No `ssl_protocols`, `ssl_ciphers`, `ssl_session_cache` or `ssl_session_tickets` in either file. **No proxied location sets `X-Forwarded-Host`** — including `location /static/`, which re-declares the whole security-header set. `USE_X_FORWARDED_HOST = True` is therefore trusted against a header nobody sets or clears |
| `src/backend/config/urls.py` | `path("", include("django_prometheus.urls"))` | The root mount. A Django-side gate lands here |
| `src/backend/apps/moderation/views/decorators.py` | `staff_required_api` | 401 with `headers={"WWW-Authenticate": "Bearer"}` while the only accepted credential is the **session cookie** |
| `src/backend/apps/moderation/views/review.py` | `reject_ad`, `ban_user` | Hand-written `if request.method != "POST": return redirect(...)` where `approve_ad` uses `@require_POST`. **No `csrf_exempt` exists anywhere**, so this is consistency, not a hole. **Converting changes the non-POST response from a 302 to a 405** — check the HTMX template's non-HTMX fallback |
| `docs/01-spec/architecture-structure.md` | a new section stating the surface's contract | `/api/v1/` is the **only** versioned prefix. Documenting that versioning is a **deliberate non-goal** for a single-consumer frontend is defensible — but it needs writing down |
| `src/backend/tests/test_nginx_config.py` | the three `/metrics` tests | `test_nginx_metrics_restricted_to_localhost` asserts `allow 127.0.0.1` **and** `deny all` are **retained** — any change must keep it green |
| `src/backend/apps/core/tests/test_observability.py` · `test_health_contract.py` | the `/metrics` and `/health/` contracts | **The Django-side `/metrics` restriction is the one change here most likely to need a test update — check both first** |

**Binding constraints**

1. **`nginx -t` before rolling.** This block changes a production proxy.
2. **The `/metrics` nginx block keeps `allow 127.0.0.1; deny all;`, `proxy_pass` and the
   four `proxy_set_header` lines.** `test_nginx_config.py` pins all of them.
3. **Do not change the alert audience or the moderation CSRF posture.** No `csrf_exempt`
   exists and none may be added.
4. **The `reject_ad` / `ban_user` 302 → 405 change must be checked against the templates**
   before it ships. This is the one item here with a user-visible response change.
5. **`X-Forwarded-Host` must be set on every proxied location, including `location
   /static/`.** The validator's correction stands: the report's inference that it applies
   only to the catch-all is wrong.
6. **Pinning `ssl_protocols` / `ssl_session_cache` changes the accepted cipher set for every
   production deployment.** Coordinate with the deployment runbook; do not pin
   `ssl_ciphers` to an explicit list "for safety" — pinning the **protocols** and the
   session cache is reviewable; an explicit cipher string is a maintenance burden that
   silently rots.
7. **Q3 must be answered (U13) before any runbook sentence about `/metrics` is written.**
   The report's impact model is probably inverted (C-4) and a runbook that warns about the
   wrong thing is worse than none.

**Implementor task**

```yaml
id: task_09_b11_api_contract
title: "Close the API-surface and nginx contract gaps (09-API-010, 09-API-014)"
priority: medium
depends_on: ["task_09_b10_media_limit"]
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 11 - The API-surface and nginx contract bundle"
source_blocks: ["BLOCK 11"]
description: >
  Five contract gaps plus one hardening gap. (1) staff_required_api answers 401 with
  WWW-Authenticate: Bearer while the only accepted credential is a session cookie, so a
  generic client retries with a Bearer token forever. (2) approve_ad uses @require_POST
  while reject_ad and ban_user hand-roll the method check - CSRF is still enforced on all
  three, so this is consistency, not a hole. (3) /api/v1/ is the only versioned prefix.
  (4) django_prometheus.urls is mounted at the root, so /metrics is unauthenticated in
  Django and nginx's allow 127.0.0.1 / deny all is the only other control. (5)
  USE_X_FORWARDED_HOST is trusted but nginx never sets or clears X-Forwarded-Host, and
  no TLS parameter is pinned in either config. Separately, the :80 listener has no
  server_name and reflects $host into its redirect.
goals:
  - "make every advertised challenge and documented contract match reality"
  - "make /metrics controlled in Django as well as nginx, without a per-request tax on the whole site"
  - "stop reflecting the client-supplied host, failing closed"
  - "make the TLS posture reviewable rather than inherited"
files:
  - path: "src/backend/apps/moderation/views/decorators.py"
    targets:
      - type: function
        name: staff_required_api
  - path: "src/backend/apps/moderation/views/review.py"
    targets:
      - type: function
        name: reject_ad
      - type: function
        name: ban_user
  - path: "src/backend/config/urls.py"
    targets:
      - type: module
        name: urls
  - path: "docker/nginx/nginx.conf"
    targets:
      - type: module
        name: nginx_conf
  - path: "docker/nginx/nginx.dev.conf"
    targets:
      - type: module
        name: nginx_dev_conf
changes:
  - action: modify_code
    description: >
      Drop the unsatisfiable WWW-Authenticate header (or change it to a scheme the
      decorator actually accepts, with a comment). Convert reject_ad and ban_user to
      @require_POST to match approve_ad, after checking the moderation templates'
      non-HTMX fallback for the 302 -> 405 change. Add proxy_set_header
      X-Forwarded-Host $host; to EVERY proxied location in both configs, including
      location /static/. Pin ssl_protocols TLSv1.2 TLSv1.3 and ssl_session_cache in the
      TLS block; do NOT pin an explicit ssl_ciphers string. Apply the Q14 option to the :80
      listener. Apply the Q2 option to add the Django-side /metrics gate, after the
      phase-15 boundary check.
  - action: modify_test
    description: >
      No test currently asserts the WWW-Authenticate header, the require_POST consistency,
      or the presence of ssl_protocols - items (1), (2) and (5) are unpinned and free to
      change. Check test_observability.py and test_health_contract.py BEFORE the
      Django-side /metrics change; that is the one item most likely to need an update.
      test_nginx_config.py's three /metrics tests must stay green unchanged.
  - action: modify_doc
    description: >
      docs/01-spec/architecture-structure.md: state that the API surface is an internal
      HTMX/JSON surface, that /api/v1/ is the only versioned prefix, and that versioning
      is a deliberate non-goal for a single-consumer frontend. This is the report's own
      recommendation and it needs writing down.
acceptance_criteria:
  - "a 401 from staff_required_api no longer advertises a Bearer challenge the server cannot satisfy"
  - "reject_ad and ban_user use @require_POST and their non-POST response was checked against the moderation template's non-HTMX fallback"
  - "no csrf_exempt was added anywhere"
  - "/metrics is restricted in Django as well as nginx, and the nginx block keeps allow 127.0.0.1, deny all, proxy_pass and the four proxy headers"
  - "every proxied location in both configs sets X-Forwarded-Host, including location /static/"
  - "ssl_protocols and ssl_session_cache are pinned in the TLS block; no explicit ssl_ciphers string was added"
  - "the :80 listener applies the Q14 option and fails closed when no server_name is configured"
  - "nginx -t passes against both configs before the commit is proposed"
  - "test_nginx_config.py's three /metrics tests pass UNCHANGED"
  - "test_observability.py and test_health_contract.py pass; any change to their assertions is named in the commit body"
  - "the commit body records the phase-15 boundary check result and the Q3 verification result"
tests_to_run:
  - "src/backend/tests/test_nginx_config.py"
  - "src/backend/apps/core/tests/test_observability.py"
  - "src/backend/apps/core/tests/test_health_contract.py"
  - "src/backend/apps/moderation/tests/"
```

**Tests required**

1. **The honest challenge** — a 401 from `staff_required_api` does not advertise a scheme
   the server cannot accept. Assert on the **response headers**.
2. **Method consistency** — all three state-changing endpoints refuse a non-POST, and the
   refusal shape is uniform. Assert on the response, and record that the moderation
   templates were checked for the 302 → 405 change.
3. **`/metrics` is controlled twice** — the nginx block keeps its three pinned properties,
   and the Django side rejects a request that did not come from the expected source. **The
   Django test must fail if the gate is removed** — otherwise it is a no-op assertion.
4. **TLS posture** — `ssl_protocols` and `ssl_session_cache` are present in the shipped
   file; `X-Forwarded-Host` is set on **every** proxied location. These are the assertions
   that make the posture reviewable rather than inherited.
5. **The fail-closed redirect** — with no `server_name` configured, the `:80` behaviour
   resolves to the configured value, not the client's header.

**Risk and rollback**

- *Rollout risk — the only one in the phase that can break a working deployment:*
  `09-API-010`'s fix requires the operator to set a real `server_name`. Mitigation: Q14 is
  gated, `nginx -t` is binding, and the commit body states the operator action. **Do not
  ship option (a) without the runbook line.**
- *Availability risk:* pinning `ssl_protocols` changes what every existing client can
  negotiate. Mitigation: pin `TLSv1.2 TLSv1.3` — do not drop TLS 1.2 in a change that is
  about reviewability, not about deprecating TLS 1.2.
- *Regression risk:* the `reject_ad` / `ban_user` 302 → 405 change is user-visible. Check
  the template's non-HTMX fallback **before** converting; if it depends on the redirect,
  stop and report.
- *Boundary risk:* a Django-side `/metrics` gate adjacent to phase 15's authorization
  framework produces two mechanisms. Mitigation: the phase-15 boundary check is in the
  acceptance criteria.
- *Documentation risk:* writing the `/metrics` exposure into a runbook from the report's
  inverted impact model (C-4). Mitigation: Q3/U13 first.
- *Rollback:* the TLS pinning and the redirect change are the two items that would need a
  deliberate un-push, not a silent revert.

---

### BLOCK 12 — Log only what `/csp-report/` needs to log (09-API-015)

| | |
|---|---|
| **Findings owned** | `09-API-015` (LOW) |
| **Depends on** | **BLOCK 10** (soft — same nginx files; see §4.2) |
| **Blocks** | nothing |
| **Priority** | **P2** |
| **Risk level** | **LOW** — the response contract is well-pinned, and the log test pins the **level** rather than the payload |
| **Required agents** | **Auditor · Planner · Validator.** The sanitiser it composes with is **phase 08's** file — coordinate, do not edit blind |

**What is confirmed.** `apps/core/views.py::csp_report` validates the payload with
`CSPReportPayload` (Pydantic, 422 on schema failure) and then logs the **entire,
unfiltered** report dict at INFO. The CSP report schema browsers send includes
`document-uri` — the full URL **including its query string** — and `referrer`. The endpoint
is unauthenticated, and nginx allows it 10 r/s with `burst=10 nodelay`, an order of
magnitude looser than a violation-report sink would ever need.

**Decision required before implementation — the zone shape**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Tighten `location /csp-report/` to a dedicated `rate=1r/s burst=5 nodelay` zone in `nginx.conf`, **and add a `/csp-report/` location to `nginx.dev.conf`** | **Gains:** matches what a sink actually needs in both environments. **Costs:** `nginx.dev.conf` currently has **no** `/csp-report/` location at all, so the dev path goes through the catch-all `location /` at 20 r/s — **looser** than production. Adding one means adding a block, not just editing one |
| **(b)** | Tighten `nginx.conf` only | **Gains:** production is what faces the internet. **Costs:** dev stays *looser* than production, which inverts the usual relationship and hides the problem from anyone testing locally |
| **(c)** | Leave the zone and fix only the logged fields | **Gains:** removes the PII sink, which is the higher-value half. **Costs:** leaves the cheapest form of log DoS available |

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/views.py` | `csp_report` | Hand-written `if request.method != "POST": return JsonResponse(..., status=405)` — **there is no `@require_POST` decorator**, and that is exactly the pattern `09-API-014` flags for inconsistency. **Do not add `@require_POST` here** while BLOCK 11 standardises its siblings; the report's warning is the right sequencing note |
| `src/backend/apps/core/schemas` | `CSPReportPayload` | The Pydantic v2 boundary model. **Read-only.** It is the model's precedent for this project |
| `src/backend/apps/core/utils/sanitize.py` | `sanitize_query_for_log` | **Phase 08's file** (its BLOCKS 3/4 reshape this neighbourhood). Route `document-uri`'s query string through it rather than building a second sanitiser |
| `docker/nginx/nginx.conf` | `location /csp-report/` | Currently `limit_req zone=login_limit burst=10 nodelay` — the **login** zone, 10 r/s |
| `docker/nginx/nginx.dev.conf` | `location /csp-report/` | **Does not exist.** The catch-all serves it at 20 r/s |
| `src/backend/apps/core/tests/test_csp_report.py` | `test_post_valid_report_logs_at_info_level` | Sets `caplog` at INFO and asserts `len(info_records) >= 1` and `len(warning_records) == 0`. **It pins the level, not the payload** — field narrowing keeps it green as long as an INFO record is still emitted. Better news than for `09-API-007` / `09-API-013` |
| `src/backend/apps/core/tests/test_csp_report.py` | the six response-contract tests | 200 / 400 / 405 / 422 — all must survive unchanged |

**Binding constraints**

1. **The full response contract survives**: 200, 400 (three shapes), 405, 422. Only the
   *logged fields* change.
2. **An INFO record is still emitted.** The existing test pins the level; do not "fix" the
   volume problem by downgrading to DEBUG or dropping the line.
3. **Reuse `sanitize_query_for_log`; do not build a second sanitiser.** It strips control
   characters and truncates — it does **not** mask PII, and it must not be asked to. If
   masking is also wanted, that is **phase 06's** `06-PII-102` policy and phase 08's file;
   do not grow `sanitize.py` here.
4. **Drop `document-uri`'s query string and `referrer` entirely**, or reduce `document-uri`
   to host + path. `blocked-uri` reduced to host + path is the shape an operator acts on.
5. **Do not add `@require_POST`.** BLOCK 11 standardises the siblings; a lone decorator here
   is the inconsistency in the other direction.
6. **`nginx.dev.conf` must be considered explicitly** under Q-shape option (a) or (b).

**Implementor task**

```yaml
id: task_09_b12_csp_log
title: "Log only the fields an operator acts on at /csp-report/ (09-API-015)"
priority: medium
depends_on: ["task_09_b10_media_limit"]
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 12 - Log only what /csp-report/ needs to log"
source_blocks: ["BLOCK 12"]
description: >
  apps/core/views.py::csp_report validates the payload with CSPReportPayload and then
  logs the entire, unfiltered report dict at INFO. The CSP report schema browsers send
  includes document-uri - the full URL including its query string - and referrer. Page
  URLs routinely carry buyer search text, so a violation on a search-results page writes
  the buyer's own query into the log stream in clear. The endpoint is unauthenticated and
  nginx allows it 10 r/s via the login_limit zone, an order of magnitude looser than a
  violation-report sink would ever need.
goals:
  - "keep the buyer's search text out of the log stream"
  - "keep the response contract byte-identical"
  - "keep an INFO record, because that is what an operator alerts on"
  - "build no second sanitiser"
files:
  - path: "src/backend/apps/core/views.py"
    targets:
      - type: function
        name: csp_report
  - path: "docker/nginx/nginx.conf"
    targets:
      - type: module
        name: nginx_conf
  - path: "docker/nginx/nginx.dev.conf"
    targets:
      - type: module
        name: nginx_dev_conf
changes:
  - action: modify_code
    description: >
      Replace the whole-dict log statement with an explicit field selection: violated-
      directive, effective-directive, disposition, blocked-uri reduced to host + path, and
      the script sample. Reduce document-uri to host + path and drop its query string and
      the referrer entirely. Route anything that still needs truncation through
      sanitize_query_for_log - it strips control characters and truncates, it does NOT
      mask PII, and it must not be extended here. Apply the recorded zone shape.
    code_hint: |
      logger.info(
          "CSP violation: violated=%s effective=%s disposition=%s blocked_uri=%s sample=%s",
          report["violated-directive"],
          report.get("effective-directive", ""),
          report.get("disposition", ""),
          _host_and_path(report.get("blocked-uri", "")),
          report.get("sample", ""),
      )
      # document-uri's query string and referrer are deliberately NOT logged: they carry
      # the buyer's own search text.
  - action: modify_test
    description: >
      test_csp_report.py's existing tests pin the level (INFO, no WARNING) and the full
      response contract; both must survive. ADD a case where document-uri carries a query
      string and a referrer is present, asserting neither reaches the log record.
  - action: modify_doc
    description: >
      Note in the module docstring that the PII-minimisation policy for log fields is
      phase 06's (06-PII-102) and that sanitize.py is phase 08's, so the next reader does
      not extend either file from here.
acceptance_criteria:
  - "a POST whose document-uri contains a query string and whose referrer is set produces a log record containing neither"
  - "an INFO record is still emitted and no WARNING record is emitted - test_post_valid_report_logs_at_info_level passes UNCHANGED"
  - "the 200 / 400 / 405 / 422 response contract is unchanged - all six existing tests pass UNCHANGED"
  - "@require_POST was NOT added to this view"
  - "sanitize_query_for_log was reused, not extended, and no second sanitiser exists"
  - "the nginx zone shape was applied per the recorded option, including the dev config's missing /csp-report/ block under option (a)"
  - "the commit body states that the PII-policy half is phase 06's and the sanitiser is phase 08's"
tests_to_run:
  - "src/backend/apps/core/tests/test_csp_report.py"
  - "src/backend/tests/test_nginx_config.py"
  - "src/backend/tests/test_docs_ci_parity.py"
```

**Tests required**

1. **The sink is closed** — a report whose `document-uri` carries a query string and which
   sets `referrer` produces a log record containing **neither**. This is the PII
   assertion.
2. **The level survives** — an INFO record is still emitted and no WARNING is. The existing
   test already pins this; it must not be changed.
3. **The response contract survives** — all six existing tests unchanged.
4. **The operator still has what they act on** — `violated-directive`, `effective-directive`,
   `disposition`, `blocked-uri` host + path, and `sample` are all still present. A blanket
   "log nothing" passes test 1 and destroys triage capability — this test is the control.

**Risk and rollback**

- *Triage risk:* a blanket reduction destroys the information an operator needs. Mitigation:
  test 4 is the control.
- *Regression risk:* the log level changes. Mitigation: test 2 pins it, and the reduction
  is a **field** change, not a level change.
- *Configuration risk:* adding a `/csp-report/` location to `nginx.dev.conf` that the dev
  config did not previously have is a structural change to a file other agents may also be
  editing. Re-read; `nginx -t` both configs.
- *Cross-phase:* `sanitize.py` is **phase 08's** file and the PII policy is **phase 06's**.
  Composing with an existing helper is the correct move; growing it is not.
- *Rollback:* restoring the whole-dict log restores the PII sink. State plainly.

---

### BLOCK 13 — `redact_free_text` at the `save_search` boundary + route `09-VAL-002` (production code + handoff)

| | |
|---|---|
| **Findings owned** | `09-API-012` (MEDIUM — **now implemented here**) · `09-VAL-002` (MEDIUM — **decision closed; data migration routed**) |
| **Depends on** | **nothing in-plan.** **New soft edge to phase 08 BLOCK 8** — both edit `save_search.py` (§5.3). The Coordinator sequences it |
| **Blocks** | nothing in this plan. **Phase 06 is the consumer** of the `query_normalized` migration obligation |
| **Priority** | **P1** — cheap, and it now closes `09-API-012` outright rather than publishing a handoff |
| **Risk level** | **MEDIUM** (was: *process*) — it now ships production code. The risk is no longer a false completion signal; it is the **contended file** and the fact that a view-only fix would still let the tracker record *"search PII is handled"* while the indexed key holds the raw query |
| **Required agents** | **Auditor · Planner · Validator.** A Validator confirms the call, the test, the named migration obligation and the coordinator handoff. **Researcher** is no longer required — the storage-layer semantics were argued in §0.6 and are now decided |

**This block changed class on 2026-10-03. It previously shipped no production code.**

**The ruling that changed it.** Q5 is **resolved**: `SavedSearch.query` is stored **REDACTED**
via `redact_free_text()` (commit `a8eeecbd`). **Deviation from plan (P1):** the plan prescribed
`redact_search_query()`, which truncates to `_MAX_QUERY_LENGTH=100`; the code uses
`redact_free_text` — the same PII masks without truncation — because
`SavedSearch.query` is `VARCHAR(200)` and truncating to 100 would silently change what the
saved search matches against. Both functions share the "never lengthen" invariant. An
Implementor can therefore be told *what* to do, and the *"unless the owner rules…"* conditional
that used to sit in this block's acceptance table is **removed**. BLOCK 13 now delivers the
**call plus a test**, and records the one thing it still cannot deliver: the **follow-up
data migration** for `query_normalized`.

**Why phase 09 implements the view fix but not the storage migration.** Phase 08's plan has
**already parked** `SavedSearch.query` redaction as its **Q5, a forward dependency on phase 06**
— and that dependency is now discharged. Phase 06 owns `06-PII-108`
(`SearchHistory.query_normalized`). `apps/search/services/search_history.py`,
`popular_search.py` and `apps/search/migrations/` are **three-way reserved** — phase 06
BLOCK 7, phase 03 BLOCK 9 option B, phase 08 BLOCKS 5/8. A phase-09 **migration** would be a
fourth editor on a contested file for a decision that is now made but whose *data repair* is
not this plan's to schedule.

**What the two findings are**

| Finding | The defect | The disposition | Who owns what now |
|---|---|---|---|
| `09-API-012` | `apps/search/views/save_search.py::save_search` takes raw `request.POST["query"]` and writes it straight into `SavedSearch.query`. Two of the three query-persistence write paths use `redact_search_query()`; the third, the view, does not | **IMPLEMENTED HERE (2026-10-03):** one `redact_free_text()` call at the boundary (**deviation from plan P1:** code uses `redact_free_text` instead of `redact_search_query` — same masks, no truncation, chosen for the `VARCHAR(200)` column — **plus a test**). The raw-form alternative is **closed** — the owner chose redaction | **Phase 09, BLOCK 13** |
| `09-VAL-002` | `SearchHistory.query_normalized` and `PopularSearch.query_normalized` are written with the **raw** query in both paths that *do* redact. `query_normalized` is a persisted, **indexed** `CharField(max_length=200)` — the dedup/lookup key. Migration `0002_redact_search_queries` rewrote **only** the `query` column and states that `query_normalized` is preserved intact | **DECIDED (Q6, 2026-10-03): key it on the redacted form.** The **follow-up data migration** repairing existing rows is **routed to phase 06**, with the dedup-semantics consequence stated in writing | **Phase 06** (PII policy owner) — propagation obligation, §5.5 |

**Why `09-VAL-002` is not merged into `09-API-012`:** they have **different files and different
mechanisms** — a missing call at a view versus a storage decision plus a data migration — and
redacting `query_normalized` **changes dedup semantics** (two users searching different phone
numbers now collapse into one row). They are **sequenced** and **reported as one remediation
item**, not implemented separately. BLOCK 13 still ships the explicit statement that
**implementing `09-API-012` alone does not close the search-PII gap**, because the indexed
dedup key keeps the raw query until phase 06's migration lands.

**Deliverable of this block**

1. `redact_free_text()` applied in `save_search` before `SavedSearch.objects.create`, **and
   a test** asserting that a `SavedSearch` created from `"+382 69 000 123"` stores no raw
   digits. **Deviation from plan (P1):** code uses `redact_free_text` (no truncation) instead
   of `redact_search_query` (truncates to 100) — correct for `VARCHAR(200)`.
2. A written record — in this plan's §2 and §5, and in a single commit's message — naming the
   `09-VAL-002` ruling, the **dedup-semantics** consequence, and the phase-06 obligation.
3. The explicit statement that **fixing `09-API-012` alone does not close the search-PII
   gap**, so a tracker cannot record a false completion.
4. **No** edit to `apps/search/services/`, `apps/search/migrations/`,
   `apps/core/utils/sanitize.py`, or any locale file.

**Acceptance criteria (published so the owner's criteria cannot drift)**

| Item | Must satisfy |
|---|---|
| **`09-API-012` — phase 09, BLOCK 13** | `redact_free_text()` is applied in `save_search` before `SavedSearch.objects.create`, **with a test** asserting a `SavedSearch` created from `"+382 69 000 123"` stores no raw digits. **Deviation from plan (P1):** code uses `redact_free_text` instead of `redact_search_query` — same PII masks, no 100-char truncation, chosen because `SavedSearch.query` is `VARCHAR(200)` and truncating would silently change match semantics. The **one rule for all query-persistence paths** is stated in the commit body: redact at write. **Do not rename the view function or the URL name.** `test_saved_search_create.py::test_create_saved_search_with_filters_and_language` posts `"велосипед"` and asserts `ss.query == "велосипед"` — `redact_free_text` is a no-op on that string, so it stays green unchanged. If the privacy page documents search-history retention, its search-history paragraph is amended **in the same change** |
| **`09-VAL-002` — phase 06, PII policy owner** | A **follow-up data migration** repairing existing `PopularSearch.query_normalized` and `SearchHistory.query_normalized` rows onto the redacted form, with an **explicit statement of what happens to dedup semantics** when two users search different phone numbers and their keys collapse into one row. Its number is checked against `apps/search/migrations/` **immediately before** generation (next free `0003_*`, subject to phase 06 BLOCK 7 and phase 08 BLOCKS 5/8). The session path — `search_history.py::_record_session_history` for anonymous users — is the **same raw/redacted split** and must be part of the same migration, not a third door |

**Implementor task**

```yaml
id: task_09_b13_saved_search_redaction
title: "Redact SavedSearch.query at write and record the query_normalized migration obligation (09-API-012, 09-VAL-002)"
priority: medium
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 13 - Route 09-API-012 and 09-VAL-002 to their owners"
source_blocks: ["BLOCK 13"]
description: >
  save_search reads request.POST["query"] and writes it straight into SavedSearch.query. Two of
  the three query-persistence write paths call redact_search_query(); this one does not. The
  Product Owner ruled on 2026-10-03 that SavedSearch.query is stored REDACTED and that
  query_normalized is keyed on the redacted form - one rule for all query-persistence paths.
  **Deviation from plan (P1):** the code applies `redact_free_text` (same masks, no truncation)
  rather than `redact_search_query` (truncates to 100) — correct for the VARCHAR(200) column.
  Apply the call at the view boundary and add a test. The follow-up data migration that repairs
  existing query_normalized rows belongs to phase 06 and must only be recorded here.
goals:
  - "close 09-API-012 by redacting at write, with a test"
  - "record the one-rule policy statement in the commit body"
  - "record phase 06's follow-up data migration obligation, including the dedup-semantics consequence"
files:
  - path: "src/backend/apps/search/views/save_search.py"
    targets:
      - type: function
        name: save_search
  - path: "src/backend/apps/search/tests/test_saved_search_create.py"
    targets: []
changes:
  - action: modify_code
    description: >
      Apply redact_free_text() to the query read before SavedSearch.objects.create. Do NOT
      rename the view function or the URL name. Do NOT touch apps/search/services/**,
      apps/search/migrations/**, apps/core/utils/sanitize.py, or any locale file.
      **Deviation from plan (P1):** code uses redact_free_text (no truncation) instead of
      redact_search_query (truncates to 100) — correct for the VARCHAR(200) column.
  - action: modify_test
    description: >
      Add a test asserting a SavedSearch created from "+382 69 000 123" stores no raw digits.
      test_create_saved_search_with_filters_and_language posts "велосипед" and must stay green
      unchanged - redact_free_text is a no-op on that string.
  - action: modify_doc
    description: >
      If the privacy page documents search-history retention, amend its search-history paragraph
      in the same change.
acceptance_criteria:
  - "a SavedSearch created from '+382 69 000 123' stores no raw digits"
  - "test_create_saved_search_with_filters_and_language is green UNCHANGED"
  - "the view function name and the URL name are unchanged"
  - "the commit body states the one rule for all query-persistence paths - redact at write - and names the 2026-10-03 ruling"
  - "the commit body records that query_normalized is keyed on the redacted form, that two users searching different phone numbers now collapse into one dedup row, and that the follow-up data migration is PHASE 06's"
  - "no file under apps/search/services/ or apps/search/migrations/ was edited"
  - "no locale file was edited and no new user-visible string was introduced"
  - "the fast Docker gate is green"
tests_to_run:
  - "src/backend/apps/search/tests/test_saved_search_create.py"
  - "src/backend/apps/search/tests/test_alert_query.py"
  - "src/backend/apps/core/tests/test_redact_search_query.py"
```

**Risk and rollback**

- *Contention risk:* `save_search.py` is **phase 08 BLOCK 8's file** as well (§5.3). Re-read
  immediately before editing; stop and report on a concurrent change. Phase 08's block bounds
  the field; this block redacts the value. **Both edits are one-line-shaped and must not be
  conflated.**
- *Process risk:* a tracker records "search PII handled" after the view fix. The acceptance
  criteria above, and this block's explicit statement, are the mitigation.
- *Product risk:* a redacted saved-search query matches differently than the seller typed, so
  an existing seller could stop receiving alerts for a query containing a digit run. **The
  owner accepted this on 2026-10-03**; the commit body must name that acceptance so it is a
  decision on record rather than a surprise.
- *Scope risk:* an Implementor "helpfully" writes the `query_normalized` migration. It is
  phase 06's, and `apps/search/migrations/` is three-way reserved. §6.1 records the
  de-scoping and this block's acceptance criteria exclude it.
- *Rollback:* a straight revert restores the raw write and the failing test. Rows already
  written redacted stay redacted; that is not undone by a revert and must be stated in the
  commit body.

---

### BLOCK 14 — Least-privilege `BOT_TOKEN` (09-API-011)

| | |
|---|---|
| **Findings owned** | `09-API-011` (MEDIUM) |
| **Depends on** | **nothing in-plan.** Shares `docker-compose.yml` / `docker-compose.prod.yml` with BLOCK 15 — serialise |
| **Blocks** | nothing in-plan |
| **Priority** | **P2** |
| **Risk level** | **HIGH** — the finding is MEDIUM but the change touches the production settings module, the compose env plumbing and a test suite that pins the guard being changed. The report's "Effort S" does not price this |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** The Researcher establishes the existing `DJANGO_ONESHOT` precedent and the exact role matrix; the Planner records it; the Validator must confirm both the boot behaviour and that no one-shot lost a secret it needs |

**The correction that changes the work (C-3).** `docker-compose.prod.yml` has **no** explicit
`BOT_TOKEN:` lines at all, and `docker-compose.yml` has exactly **three** — on the one-shots.
**Removing those three lines is a no-op.** The real distribution mechanism is `env_file:`
plus the `./.env.*:/app/src/.env:ro` bind mount on **eight** Django services, which
`config/settings/base.py::read_env` loads into `os.environ` at import.

**Decision required before implementation — the role matrix**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **Compose-only.** Remove `env_file` and the `.env` bind mount from the services that need no whole-file access, keeping it only on `web`, `bot`, `scheduler` | **Gains:** the smallest change; no Python, no test surgery on the settings suite; immediately reduces the exposure from eight containers to three. **Costs:** `prod.py` still *requires* `BOT_TOKEN` at import, so any process importing it must still have it in its environment — the compose change alone leaves the guard as the reason they need it. The finding's stated root cause ("a monolithic settings module") is untouched |
| **(b)** | **Guard-only.** Make the `BOT_TOKEN` requirement conditional on process role, and use the existing `DJANGO_ONESHOT=1` + `config.settings.oneshot` mechanism as the model — the project's own sanctioned "this process does not need the real secrets" pattern | **Gains:** attacks the **root cause**. **Costs:** `test_settings_secrets.py` has **six** assertions pinning the guard in `prod.py` and their dev mirrors (`test_bot_token_required_in_production`, `test_prod_bot_token_rejects_placeholder`, `test_prod_bot_token_rejects_dev_only_dummy`, `test_prod_bot_token_accepts_real_token`, `test_bot_token_required_in_dev`, `test_bot_token_placeholder_rejects_in_dev`) — they must be rewritten **and** re-targeted, which is a real cost the report does not price. `prod.py` is the most contended file in the repository |
| **(c)** | **(a) and (b) together** | **Gains:** the exposure and its cause both go. **Costs:** the largest commit in the phase — compose × 2, `prod.py`, `base.py`, the one-shot matrix, and a rewritten settings suite — for a MEDIUM finding. This is the option Q10's "one outbound gateway" argument is really about, and it is a **separate decision** |

**(a) is the minimum that changes the exposure; (b) is the minimum that changes the cause.**
Which combination lands is a Coordinator sequencing decision, because `prod.py`,
`docker-compose.dev.override.yml` and the `.env*.example` files are all **phase 02's**
surface.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `docker-compose.prod.yml` | `env_file:` and the `./.env.prod:/app/src/.env:ro` volume on `web`, `bot`, `migrate`, `create_admin`, `seed`, `load_cities`, `load_catalog`, `scheduler` | **Eight** Django services. `backup` correctly has neither and must keep it that way |
| `docker-compose.yml` | the same two keys across `migrate`, `load_cities`, `load_catalog`, `create_admin`, `seed`, `web`, `bot`, plus the three explicit `BOT_TOKEN: ${BOT_TOKEN}` lines | Seven services |
| `src/backend/config/settings/prod.py` | the `BOT_TOKEN` fail-fast guard | **Phase 02's and phase 06's file.** Also BLOCK 9's |
| `src/backend/config/settings/base.py` | `read_env` (loads the bind-mounted file into `os.environ` at import) | The actual mechanism. **Read-only reference** — do not change how the file is loaded |
| `src/backend/apps/search/services/immediate_alerts.py` · `apps/search/management/commands/send_alerts.py` | the two `Bot(token=…)` constructions outside the bot process | **Read-only.** `immediate_alerts` is **latent** (`IMMEDIATE_ALERTS_ENABLED=false`); `send_alerts` is **live and unconditional** (C-9). Consolidating them is Q10 and is **not** this block |
| `src/backend/config/settings/tests/test_settings_secrets.py` | the six `BOT_TOKEN` assertions | **The cost.** Rewriting them is a behaviour change, not a chore |
| `src/backend/tests/test_compose_contract.py` | `test_base_web_environment_uses_sequence_form`, `test_base_web_declares_prometheus_contract_as_pair`, `test_prod_long_lived_services_have_30s_stop_grace`, `test_dev_bot_has_no_depends_on_and_dev_web_depends_on_seed` | **Phase 01's file.** Phase 02's plan explicitly forbids re-asserting compose parity from another phase. Any `env_file` restructuring must keep all four green |
| `docs/ops/docker-deployment.md` | the compromise-response guidance | Add "rotate `BOT_TOKEN`, not only `DJANGO_SECRET_KEY`, when the web tier is suspected" and note the multi-process flood-control consequence. **Phase 12 owns the runbook; the file is contended** |

**Binding constraints**

1. **Removing the three explicit `BOT_TOKEN:` compose lines alone changes nothing.** If the
   commit does only that, it is a **no-op dressed as a fix** and must not be made.
2. **`backup` keeps no `env_file` and no mount.** The report named it as an exposure; it is
   not one. Do not "fix" it.
3. **Do not change `read_env`'s behaviour.** It is the mechanism being worked *around*, not
   the defect.
4. **Under option (b), reuse the existing `DJANGO_ONESHOT=1` + `config.settings.oneshot`
   mechanism.** Do not invent a new role flag; the project already has one, and phase 02
   owns it.
5. **Do not break any one-shot's actual secret needs.** The one-shots read
   `DJANGO_SECRET_KEY` and `DATABASE_URL` at minimum. The role matrix must be derived from
   what each service **actually reads**, not from what it is named.
6. **The six `test_settings_secrets.py` assertions must be rewritten in the same commit**
   with the reason stated. They are not incidental: they pin the guard that is the root
   cause, and rewriting them silently would make the change look like a test-hack.
7. **`immediate_alerts.py` and `send_alerts.py` are read-only here.** Their `Bot`
   construction sites stay; consolidating them is Q10 (§6.2).

**Implementor task**

```yaml
id: task_09_b14_bot_token
title: "Stop distributing the bot credential to containers that never use it (09-API-011)"
priority: medium
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 14 - Least-privilege BOT_TOKEN"
source_blocks: ["BLOCK 14"]
description: >
  BOT_TOKEN is env-sourced (correct) but distributed to eight Django containers in
  production - web, bot, migrate, create_admin, seed, load_cities, load_catalog,
  scheduler - via env_file plus a ./.env.prod:/app/src/.env:ro bind mount that
  config/settings/base.py::read_env loads into os.environ at import. The web and scheduler
  tiers construct their own Bot: send_alerts.py (the scheduler, daily at 08:00 UTC) is live
  and unconditional; immediate_alerts.py (the web tier) is behind IMMEDIATE_ALERTS_ENABLED,
  which is false in all four env templates. The root cause is config/settings/prod.py,
  which requires BOT_TOKEN unconditionally so ANY process importing it must hold it to
  satisfy a guard it never exercises.
goals:
  - "reduce the number of containers holding the bot credential to the ones that use it"
  - "attack the root cause - the unconditional settings guard - rather than the compose lines"
  - "keep every one-shot bootable with the secrets it actually reads"
  - "leave the Bot construction sites and their test patch targets untouched"
files:
  - path: "docker-compose.prod.yml"
    targets:
      - type: service
        name: web
      - type: service
        name: bot
      - type: service
        name: migrate
      - type: service
        name: create_admin
      - type: service
        name: seed
      - type: service
        name: load_cities
      - type: service
        name: load_catalog
      - type: service
        name: scheduler
      - type: service
        name: backup
  - path: "docker-compose.yml"
    targets:
      - type: service
        name: web
      - type: service
        name: bot
  - path: "src/backend/config/settings/prod.py"
    targets:
      - type: constant
        name: BOT_TOKEN
  - path: "src/backend/config/settings/tests/test_settings_secrets.py"
    targets:
      - type: module
        name: test_settings_secrets
  - path: "src/backend/tests/test_compose_contract.py"
    targets:
      - type: module
        name: test_compose_contract
changes:
  - action: modify_code
    description: >
      Apply the recorded role matrix. Remove env_file and the .env bind mount from the
      services that need no whole-file access, keeping them only where the process actually
      reads the file. Under option (b), make the BOT_TOKEN requirement in prod.py
      conditional on process role, reusing the existing DJANGO_ONESHOT=1 +
      config.settings.oneshot mechanism rather than inventing a new flag. Derive the matrix
      from what each service READS, not from its name.
    code_hint: |
      # The three explicit BOT_TOKEN lines are NOT the distribution mechanism - removing
      # them is a no-op. The env_file plus the ./.env.prod:/app/src/.env:ro bind mount is,
      # and read_env() loads that file into os.environ at import.
  - action: modify_test
    description: >
      test_settings_secrets.py pins SIX BOT_TOKEN assertions - in production and their dev
      mirrors - against the guard that is the root cause. Rewrite them in THIS SAME COMMIT
      under option (b), re-targeted at the role-conditional behaviour, and name the change
      and its reason in the commit body. test_compose_contract.py must pass UNCHANGED -
      it is phase 01's file and phase 02's plan forbids re-asserting compose parity here.
  - action: modify_doc
    description: >
      docs/ops/docker-deployment.md: in the compromise-response procedure, state that
      BOT_TOKEN must be rotated - not only DJANGO_SECRET_KEY - when the web tier is
      suspected, and note the multi-process flood-control consequence: each process has its
      own rate-limit budget, so flood control is enforced against the token in aggregate.
      Phase 12 owns this runbook; the file is contended - re-read before editing.
acceptance_criteria:
  - "the set of containers receiving BOT_TOKEN in production is the set that actually constructs a Bot, plus nothing more"
  - "backup still has no env_file and no .env mount"
  - "every one-shot service still boots: the whole docker-compose.test.yml service list starts without an ImproperlyConfigured"
  - "under option (b), a process importing config.settings.prod without a role that needs the token does not require it, while a bot or scheduler process still does"
  - "the six BOT_TOKEN assertions in test_settings_secrets.py were rewritten in this commit, with the change and its reason named; none was deleted to make a run green"
  - "test_compose_contract.py passes UNCHANGED"
  - "the immediate_alerts.py and send_alerts.py Bot construction sites and their module-level patch targets are unchanged"
  - "read_env's behaviour is unchanged"
  - "the commit body states the role matrix as a table of service -> secrets actually read, and names the Q10 boundary (no gateway consolidation here)"
  - "docs/ops/docker-deployment.md states the BOT_TOKEN rotation obligation in the compromise-response procedure"
tests_to_run:
  - "src/backend/config/settings/tests/"
  - "src/backend/tests/test_compose_contract.py"
  - "src/backend/tests/test_compose_hardening.py"
  - "src/backend/apps/search/tests/test_immediate_alerts.py"
  - "src/backend/apps/search/tests/test_send_alerts_daily.py"
```

**Tests required**

1. **The role matrix** — a structural test over the shipped compose files asserting which
   services carry `env_file` and the bind mount. Assert on the **file**, not on the count.
2. **Every one-shot still boots.** The whole service list must start against
   `docker-compose.test.yml`. This is the test that catches a role matrix derived from
   service *names* instead of from what each service reads.
3. **The guard, under option (b)** — a process without a role needing the token does not
   require it; a bot or scheduler process still does. Both directions; a guard that is
   merely *removed* fails the second.
4. **Compose contract unchanged** — `test_compose_contract.py` passes untouched.
5. **The alert paths unchanged** — both `Bot` patch targets still resolve.

**Risk and rollback**

- *Availability risk — the highest in this block:* **a one-shot loses a secret it
  actually reads** and fails to boot. The one-shots read `DJANGO_SECRET_KEY` and
  `DATABASE_URL` at minimum. Mitigation: test 2, and binding constraint 5.
- *Correctness risk:* **the commit removes only the three explicit compose lines** and is
  reported as a fix. It changes nothing. Mitigation: binding constraint 1, and test 1
  asserts the whole-file mechanism, not the explicit lines.
- *Review risk:* **six settings tests are rewritten**, which looks like test-hacking unless
  the reason is stated. Mitigation: binding constraint 6, and the commit body must name
  each one.
- *Contention risk:* `prod.py`, `docker-compose.dev.override.yml` and the `.env*.example`
  files are **phase 02's**; `docker-compose*.yml` is also BLOCK 15's. Re-read; stop and
  report on a concurrent change.
- *Rollback:* restoring the `env_file` lines restores the exposure. State plainly.

---

### BLOCK 15 — Reproducible deploys: pin the application image and the certificate path (09-API-016)

| | |
|---|---|
| **Findings owned** | `09-API-016` (LOW) |
| **Depends on** | **BLOCK 14** (hard in practice — same files; serialise) |
| **Blocks** | nothing in-plan. **Phase 12 owns the runbook text; phase 02 explicitly excludes `docker-compose.prod.yml`** |
| **Priority** | **P2** |
| **Risk level** | **MEDIUM** — the `IMAGE_TAG` change is **breaking for every deployment that relies on the default**, which is a real operational risk on a LOW finding |
| **Required agents** | **Auditor · Planner · Validator.** No Researcher is required — nothing here is measured |

**Two halves, and the auditor missed the consequential one.**

1. Every third-party datastore image floats: `postgres:18-alpine`, `redis:7-alpine`,
   `nginx:alpine`. `edoburu/pgbouncer:1.25.2` is the **only** pinned tag and is the model
   to follow.
2. **The application image floats too** — eight production services at
   `${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}`. This is
   the higher-consequence half: `docker-compose pull` on two hosts running "the current
   compose file" can move **the entire application** to different code with no repository
   change.

Separately, `${TLS_CERT_PATH:-/etc/nginx/certs}` is an **absolute host path**, not the
repository's own `./docker/nginx/certs` — which is where the `certs/` directory that ships
with the project actually lives. Docker auto-creates a missing bind-mount source as an
empty directory, so a deployment that forgets to export `TLS_CERT_PATH` **does not fail at
mount time**: it starts, mounts an empty directory, and nginx then aborts with `cannot load
certificate`. `${VAR:-default}` produces no warning.

**Decision required before implementation — the image-tag policy**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Require `IMAGE_TAG` — remove the default, or change it to `${IMAGE_TAG:?…}` so compose **fails loudly** | **Gains:** the half that actually prevents two hosts running different code. **Costs:** **breaking for every existing deployment** that relies on `latest`. An operator who upgrades the compose file without setting `IMAGE_TAG` gets a hard failure — which is the point, and is still an outage in the middle of a deploy |
| **(b)** | Change the default to something non-`latest` (e.g. a dated tag) | **Gains:** no hard failure; two hosts still converge if the operator updates the file. **Costs:** **silently pins the deploy to whatever the file says**, and a forgotten default is a deploy to stale code. It trades an outage for a silent wrong version — usually the worse trade |
| **(c)** | Leave the default and add a runbook requirement | **Gains:** zero risk. **Costs:** the defect is unchanged; a runbook line is not an enforcement mechanism, and this is the class of thing the phase's own evidence says recurs |

**(a) with the `${VAR:?…}` form is the right shape** — a loud failure at `docker compose
up` is strictly better than a crash-looping proxy with compose output that looks
successful. It must be paired with the runbook line, which is **phase 12's**.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `docker-compose.yml` | the `db`, `redis` and `nginx` service image references | Floating tags |
| `docker-compose.prod.yml` | the eight application-service `image:` references; the `backup` service image; the TLS volume | `${IMAGE_TAG:-latest}` × 8; `${TLS_CERT_PATH:-/etc/nginx/certs}` |
| `docker/nginx/certs/` | the directory that ships with the project | Contains only `.gitkeep` |
| `src/backend/tests/test_compose_contract.py` · `test_compose_hardening.py` · `test_deploy_workflow.py` · `apps/core/tests/test_ci_security.py` | — | **Searched for `IMAGE_TAG`, `TLS_CERT_PATH`, `postgres:18`, `nginx:alpine` and `redis:7`: no assertion exists.** This finding is **completely unpinned** and can ship without test surgery — which also means it is the finding most likely to be lost |
| `docs/ops/docker-deployment.md` | the certificate path and tag-pinning guidance | Phase 12's file; contended |

**Binding constraints**

1. **`TLS_CERT_PATH` DEFERRED (P4)** — the binding constraint is **not** satisfied by phase 09.
    `${TLS_CERT_PATH:-/etc/nginx/certs}` in `docker-compose.prod.yml:109` is **unchanged**;
    `.env.prod.example` marks the decision as deferred ("DEFERRED DECISION (09-API-016)"). The
    in-repo path is a candidate; the owner has not yet ruled on the host filesystem layout. The
    runbook must state that the path resolves on the **host** once the owner names it.
2. **Pin the third-party datastores to a patch version or a digest.** Follow
   `edoburu/pgbouncer:1.25.2`. **Never** repin across a PostgreSQL major-version boundary
   as part of this change — that is its own operation with its own runbook.
3. **Add a structural test in the same style as `test_nginx_config.py`** asserting that no
   production service uses a floating tag and that `IMAGE_TAG` has no `latest` default.
   This is the highest-value part of the block, because the finding is otherwise unpinned.
4. **Do not edit a digest or a tag that a deployment depends on without recording the
   rollback.** A digest pin is not revertible by editing the file alone — the previous
   digest must be recorded.
5. **`docker-compose.prod.yml` is explicitly out of scope for phase 02** and is not claimed
   by any plan read for this pass. It is **BLOCK 14's** file too — sequence.
6. **Coordinate the tag bumps with phase 12's runbooks.** A scheduled monthly "pull and
   test" job keeps them current without making every deploy a coin flip; that job is
   **phase 12's**, not this block's.

**Implementor task**

```yaml
id: task_09_b15_image_pins
title: "Pin the runtime images and default the certificate path to the repository's own (09-API-016)"
priority: low
depends_on: ["task_09_b14_bot_token"]
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 15 - Reproducible deploys"
source_blocks: ["BLOCK 15"]
description: >
  Every third-party image in the production topology floats - postgres:18-alpine,
  redis:7-alpine, nginx:alpine - and edoburu/pgbouncer:1.25.2 is the only pinned tag.
  Higher-consequence and missed by the auditor: eight production services reference
  ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}, so
  `docker-compose pull` on two hosts running the current compose file can move the ENTIRE
  APPLICATION to different code with no repository change. Separately, the production TLS
  mount defaults to the absolute host path /etc/nginx/certs rather than the repository's own
  ./docker/nginx/certs; Docker auto-creates a missing bind-mount source as an empty
  directory, so a deployment that forgets to export TLS_CERT_PATH starts, mounts nothing,
  and nginx then aborts with "cannot load certificate" while compose output looks
  successful.
goals:
  - "make the application image tag explicit rather than defaulted to latest"
  - "pin every third-party runtime image to a patch version or a digest"
  - "make a fresh clone work with no TLS_CERT_PATH export"
  - "assert the pinning structurally so it cannot silently regress"
files:
  - path: "docker-compose.yml"
    targets:
      - type: service
        name: db
      - type: service
        name: redis
      - type: service
        name: nginx
  - path: "docker-compose.prod.yml"
    targets:
      - type: service
        name: web
      - type: service
        name: scheduler
      - type: service
        name: backup
      - type: volume
        name: certs
  - path: "src/backend/tests/test_compose_hardening.py"
    targets:
      - type: module
        name: test_compose_hardening
changes:
  - action: modify_code
    description: >
      Apply the recorded image-tag policy - require IMAGE_TAG with the ${IMAGE_TAG:?...}
      form so compose fails loudly rather than defaulting to latest. Pin postgres,
      redis and nginx to a patch version or a digest, following edoburu/pgbouncer:1.25.2
      as the model. Change the TLS volume default to the repository's own
      ./docker/nginx/certs so a fresh clone works with no export.
    code_hint: |
      # ${VAR:-default} produces NO warning when the operator forgets to export it.
      # ${VAR:?message} fails loudly at `docker compose up`.
      image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:?IMAGE_TAG must be set; a floating :latest makes two hosts run different code}
      volumes:
        - ${TLS_CERT_PATH:-./docker/nginx/certs}:/etc/nginx/certs:ro
  - action: add_test
    description: >
      Extend the structural compose test, in the same style as test_nginx_config.py: assert
      no production service resolves to a floating tag, that IMAGE_TAG has no latest
      default, and that the TLS volume default is the repository's own certs path. This
      finding is completely unpinned today, which is why it is the one most likely to be
      silently undone by the next compose edit.
  - action: modify_doc
    description: >
      docs/ops/docker-deployment.md: state that IMAGE_TAG must be set before `docker compose
      up`, that TLS_CERT_PATH resolves on the HOST, and that the previous digest of every
      repinned image is recorded for rollback. Phase 12 owns the runbook; re-read before
      editing.
acceptance_criteria:
  - "no production service resolves to a floating tag, and no IMAGE_TAG default of latest remains"
  - "the TLS volume default is the repository's own ./docker/nginx/certs"
  - "every repinned image's PREVIOUS digest is recorded in the commit body - a digest pin is not revertible by editing the file alone"
  - "the structural compose test asserts both the pinning and the IMAGE_TAG policy, and fails if either is undone"
  - "test_compose_contract.py and test_deploy_workflow.py pass UNCHANGED"
  - "no image was repinned across a PostgreSQL major-version boundary"
  - "the commit body states the BREAKING nature of requiring IMAGE_TAG and names the operator action"
  - "the runbook line about host-side path resolution is present or explicitly handed to phase 12"
tests_to_run:
  - "src/backend/tests/test_compose_contract.py"
  - "src/backend/tests/test_compose_hardening.py"
  - "src/backend/apps/core/tests/test_deploy_workflow.py"
  - "src/backend/tests/test_docs_ci_parity.py"
```

**Tests required**

1. **No floating tag** — a structural test over the shipped compose files. This is the
   assertion that stops the next compose edit from undoing the fix silently.
2. **`IMAGE_TAG` is required** — the compose file contains no `latest` default.
3. **The certificate path default** — the shipped value is the repository's own path, so a
   fresh clone works with no export.
4. **Everything else unchanged** — `test_compose_contract.py` and `test_deploy_workflow.py`
   pass untouched.

**Risk and rollback**

- *Operational risk:* **requiring `IMAGE_TAG` breaks every deployment that relies on the
  default.** That is the intent, and it is still an outage mid-deploy. Mitigation: the
  commit body names it; the runbook line is the mitigation, and it is **phase 12's**.
- *Rollback risk:* **a digest pin cannot be reverted by editing the file** — the previous
  digest must be known. Mitigation: binding constraint 4; the commit body records them.
- *Dependency-version risk:* **repinning `postgres` across a major-version boundary** is an
  operation, not a version bump. Mitigation: binding constraint 2.
- *Regression risk:* the `certs/` path change means a deployment that **was** relying on
  `/etc/nginx/certs` silently starts using the repo's empty directory. Mitigation: the
  runbook states the host-side resolution; nginx's `cannot load certificate` is a loud,
  obvious failure — which is why the change is an improvement.
- *Rollback:* a straight revert restores the floating tags and the misleading default.

---

### BLOCK 16 — Translation observability: redacted log fields and a measurable breaker (09-API-017)

| | |
|---|---|
| **Findings owned** | `09-API-017` (LOW) |
| **Depends on** | **nothing in-plan.** Shares `apps/core/services/translation.py` with BLOCK 8 — see §4.3 for why there is deliberately no hard edge |
| **Blocks** | nothing |
| **Priority** | **P2** |
| **Risk level** | **LOW** — three log-site changes plus three counters; the tripwires are existing tests |
| **Required agents** | **Auditor · Planner · Validator.** The sanitiser swap is **phase 06's and phase 08's** — this is a coordination obligation, not a code one |

**Two halves with different owners, stated plainly.**

- **The counter half is unambiguously this phase's.** The breaker being open means
  **every ad ships untranslated**, and that state is visible only as one INFO line per
  call. `django_prometheus` is already wired at `config/urls.py` root and
  `gunicorn.conf.py` already sets up `PROMETHEUS_MULTIPROC_DIR` with a `child_exit` hook,
  so multiprocess counters are the **established pattern** — no new dependency, no new
  endpoint, no new wiring.
- **The sanitiser swap must be reviewed against phase 06's existing redaction tests** so
  the new assertions land in one place. `06-PII-102` is the same class of defect — raw
  identifiers logged on send failure — and phase 06 owns the log-hygiene policy.
  **Do not action the log-field-selection change twice.**

**Credit where due, and it is verified:** the HTTP-failure lines already strip the
credential — `str(e.request.url.copy_with(params={}))` removes the `key` query parameter,
so `GOOGLE_TRANSLATE_API_KEY` cannot leak through them. **Do not weaken that.**

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/services/translation.py` | `translate_text` (five log sites that include ad text) · `TranslationCircuitBreaker` | The **cleanest ownership in the whole phase** — no plan claims this module. The sites are the open-circuit INFO line, the DEBUG success line (**input and output**), the transport-failure WARNING and two HTTP 4xx/5xx WARNINGs |
| `src/backend/apps/core/utils/sanitize.py` | `sanitize_query_for_log` vs `redact_free_text` | **Phase 08's file.** Two sanitisers exist for two different audiences: `redact_search_query` (masks + truncates to 100, for stored search queries) and `redact_free_text` (masks only, no truncation, for staff-authored free text in unbounded fields). **Deviation from plan (P6):** the plan prescribed `redact_search_query` for ad text, but the code correctly uses `redact_free_text` — ad text lands in an unbounded `TextField` where a 100-char cap would silently discard the operator's words. **Compose redact-then-truncate**; do not modify either function |
| `src/backend/apps/core/tests/test_translation.py` | `TestTranslateTextFallback::test_translation_error_log_does_not_leak_api_key`, `TestTranslationCircuitBreaker::*` | The first is a **security** regression guard — do not weaken it |
| `src/backend/apps/core/tests/test_sanitize.py` · `apps/search/tests/test_redact_search_query.py` | the two sanitisers' contracts | `redact_search_query` has a **"never lengthen"** invariant. Phase 08's plan explicitly forbids changing it |
| `src/backend/apps/core/tests/test_observability.py` | the `/metrics` surface the counters land on | No new wiring needed |

**Binding constraints**

1. **Compose, do not replace.** Redact with `redact_free_text` (**deviation from plan P6:**
   code uses `redact_free_text` instead of `redact_search_query` — ad text is staff-authored
   free text in an unbounded `TextField`, so a 100-char truncation cap would silently discard
   the operator's words), **then** truncate with `sanitize_query_for_log`, respecting the
   "never lengthen" invariant. Do not modify either function — `sanitize.py` is phase 08's.
2. **The DEBUG success line logs the translated output as well as the input.** Masking the
   input alone is insufficient: a phone number survives translation into the recipient
   language. **The report does not name this second sink.**
3. **Do not weaken `test_translation_error_log_does_not_leak_api_key`.** The URL-stripping
   practice is the model; keep it.
4. **Counters follow the existing multiprocess pattern.** `django_prometheus` is already
   mounted at the root and `PROMETHEUS_MULTIPROC_DIR` already exists. **No new dependency,
   no new endpoint.**
5. **Naming:** the three counters are `translation_requests_total`,
   `translation_fallback_total` and `translation_circuit_open`, so the API-007 fallback
   count becomes **measured** rather than inferred.
6. **No new user-visible string.** The module docstring note about which sanitiser applies
   to which kind of text is documentation.

**Implementor task**

```yaml
id: task_09_b16_translation_observability
title: "Redact translation log fields and make the breaker measurable (09-API-017)"
priority: low
depends_on: []
source_reference: ".ai/plans/09-external-api-remediation.md"
source_section: "BLOCK 16 - Translation observability"
source_blocks: ["BLOCK 16"]
description: >
  Every log line in apps/core/services/translation.py that includes ad text routes it
  through sanitize_query_for_log, which strips control characters and truncates to 100 but
  does NOT mask PII. The project ships both redact_search_query (masks + truncates to 100,
  for stored search queries) and redact_free_text (masks only, no truncation, for
  staff-authored free text in unbounded fields) for exactly this. A seller who
  writes a phone number into a title therefore has it written to production logs at INFO and
  WARNING by the translator's own diagnostics - and the DEBUG success line logs the
  TRANSLATED OUTPUT as well as the input, so a number survives into the recipient language.
  Separately, the circuit breaker is observable only as one INFO line per call, so "how
  many ads were published untranslated in the last hour" requires a log grep: there is no
  counter, gauge or threshold to alert on.
goals:
  - "keep buyer-typed identifiers out of the translator's own log lines"
  - "make 'the translator is down' alertable rather than greppable"
  - "reuse the existing multiprocess metrics pattern - no new dependency, no new wiring"
  - "leave the credential-stripping practice intact"
files:
  - path: "src/backend/apps/core/services/translation.py"
    targets:
      - type: function
        name: translate_text
      - type: class
        name: TranslationCircuitBreaker
      - type: method
        name: is_open
      - type: method
        name: record_failure
  - path: "src/backend/apps/core/tests/test_translation.py"
    targets:
      - type: class
        name: TestTranslateTextFallback
      - type: class
        name: TestTranslationCircuitBreaker
changes:
  - action: modify_code
    description: >
      Route ad text in every translate_text log site through redact_free_text FIRST
      (**deviation from plan P6:** code uses `redact_free_text` instead of
      `redact_search_query` — ad text is staff-authored free text in an unbounded
      `TextField`, where a 100-char truncation cap would silently discard the
      operator's words) and sanitize_query_for_log SECOND, respecting
      redact_free_text's "never lengthen" invariant. Cover the DEBUG success line's
      OUTPUT as well as its input - a phone number survives translation. Add three
      prometheus_client.Counters following the existing multiprocess pattern:
      translation_requests_total, translation_fallback_total and
      translation_circuit_open. Note in the module docstring which sanitiser applies to
      which kind of text, so the next caller picks correctly. Do NOT change
      apps/core/utils/sanitize.py - it is phase 08's file.
    code_hint: |
      # Two sanitisers, two audiences. Compose them; do not pick one by name similarity.
      def _safe_log_text(text: str) -> str:
          """Redact first, then truncate - redact_free_text never lengthens."""
          return sanitize_query_for_log(redact_free_text(text))

      TRANSLATION_REQUESTS = Counter("translation_requests_total", "...")
      TRANSLATION_FALLBACKS = Counter("translation_fallback_total", "...")
      TRANSLATION_CIRCUIT_OPEN = Gauge("translation_circuit_open", "...")
  - action: add_test
    description: >
      A seller title containing a phone number and an e-mail address produces NO log
      record containing either - for the open-circuit line, the DEBUG success line's
      INPUT and its OUTPUT, and the transport and HTTP failure lines. A control case: a
      title with no identifiers still logs its text. The three counters are exposed on
      /metrics and the breaker gauge tracks is_open.
acceptance_criteria:
  - "a seller title containing a phone number and an e-mail produces no log record containing either, on the open-circuit line, the DEBUG success line's input, the DEBUG success line's OUTPUT, and the failure lines"
  - "the HTTP-failure lines still strip the GOOGLE_TRANSLATE_API_KEY query parameter - test_translation_error_log_does_not_leak_api_key passes UNCHANGED"
  - "a title with no identifiers still logs its text (the control that stops a blanket log-nothing change)"
  - "translation_requests_total, translation_fallback_total and translation_circuit_open are exposed on /metrics and the breaker gauge tracks is_open"
  - "apps/core/utils/sanitize.py was NOT modified; redact_free_text's never-lengthen invariant is respected"
  - "no new dependency, no new endpoint, no new env var, no new user-visible string"
  - "test_translation.py passes; the commit body records that the log-field-selection half was reviewed against phase 06's 06-PII-102 redaction tests so the assertions land in one place"
tests_to_run:
  - "src/backend/apps/core/tests/test_translation.py"
  - "src/backend/apps/core/tests/test_sanitize.py"
  - "src/backend/apps/core/tests/test_json_logging.py"
  - "src/backend/apps/core/tests/test_observability.py"
  - "src/backend/apps/search/tests/test_redact_search_query.py"
```

**Tests required**

1. **The log sink is closed** — a title with a phone number and an e-mail reaches no log
   record, on **every** log site including the DEBUG output line. Naming the output line
   explicitly is the difference between closing the defect and closing most of it.
2. **The credential guard is intact** — the existing API-key non-leakage test passes
   unchanged. This is the tripwire for a change that touches the same log statements.
3. **The control** — an ordinary title still logs its text. A blanket "log nothing" passes
   test 1 and destroys triage capability.
4. **The metrics exist** — the three counters are on `/metrics` and the breaker gauge
   tracks the open state.

**Risk and rollback**

- *Triage risk:* over-redaction destroys the ability to debug a translation failure.
  Mitigation: test 3.
- *Security risk:* a sanitiser change that accidentally **widens** what is logged.
  Mitigation: test 1 asserts absence, test 2 asserts the credential guard.
- *Contention risk:* `sanitize.py` is **phase 08's** and `translation.py`'s log lines may be
  touched by phase 06's `06-PII-102` work. Mitigation: compose with the existing helpers;
  modify neither; re-read before editing.
- *Rollback:* a straight revert restores the unredacted log lines. State plainly.

---

## 4. Dependency graph

### 4.1 Execution order (the safe serial order)

One Implementor, strictly sequential. Every block is one commit (§1.3).

| # | Block | Findings | Depends on (in-plan) | External gate | Risk |
|---|---|---|---|---|---|
| 1 | One cache-failure contract | `09-API-001`, `09-VAL-007`, half `09-VAL-006` | — | **Q12** | **HIGH** |
| 2 | One fail-open window helper (7 guards) | `09-API-002` | — (soft: 1) | **Q9** (Coordinator) | **HIGH** |
| 3 | Rate the `contact_<ad_id>` deep link | `09-API-003` | **2** (hard) | — (per-seller cap is in-block) | **HIGH** |
| 4 | Bounded replay budget, honest return | `09-API-004`, `09-VAL-004` | — | budget shape (in-block); U2/U3/U9 | **HIGH** |
| 5 | Exchange rates + wired invalidation | `09-API-008`, half `09-VAL-006` | 1 (**same wave**, `09-VAL-006`) | **Q11** (product), **Q13** | MEDIUM |
| 6 | Alert bodies: one shape, four sends | `09-API-006`, half `09-VAL-009` | 4 (soft) | shape (in-block), **Q8** | MEDIUM |
| 7 | Observable, bounded alert dispatch | `09-API-013`, half `09-VAL-009` | **6** (hard) | **Q7** | MEDIUM–HIGH |
| 8 | Distinguishable translation failure | `09-API-007` | — | **Q4** | MEDIUM |
| 9 | `EMAIL_HOST` reason + guard | `09-API-009` | — | **Q1** (human) | MEDIUM (contended files) |
| 10 | Rate `/media/` | `09-API-005` | — | zone shape (in-block) | LOW–MEDIUM |
| 11 | API-surface + nginx contract | `09-API-010`, `09-API-014` | 10 (soft) | **Q14**, **Q2**, Q3 pre-step | MEDIUM |
| 12 | `/csp-report/` log hygiene | `09-API-015` | 10 (soft) | zone shape (in-block) | LOW |
| 13 | Route `09-API-012` + `09-VAL-002` | `09-API-012`, `09-VAL-002` | — | **Q5 / Q6 routed to phase 06/08** | process |
| 14 | Least-privilege `BOT_TOKEN` | `09-API-011` | — | role matrix (Coordinator); **Q10 boundary** | **HIGH** |
| 15 | Pin images + certificate path | `09-API-016` | **14** (hard in practice) | tag policy (in-block) | MEDIUM |
| 16 | Translation observability | `09-API-017` | — | — | LOW |

### 4.2 The DAG and why each edge exists

```
     (none)                        (none)                       (none)
        |                             |                            |
        v                             v                            v
 [1 cache contract]  <-- Q12   [2 fail-open window]  <-- Q9   [4 retry budget]
        |                             |                            |
        |    (soft, same module)      v                            |
        +--------------------------->[3 rate contact_<ad_id>]       |
        |                                                          |
        v                                                          v
 [5 exchange rates]  <-- Q11,Q13                        [6 alert bodies] <-- Q8
                                                              |
                                                              v
 [8 translation signal] <-- Q4                     [7 alert dispatch] <-- Q7
                                                          |
   (none) -> [9 EMAIL_HOST] <-- Q1                       |
                                                          |
   (none) -> [10 rate /media/]                          |
                |                                        |
                v                                        |
 [11 API + nginx contract] <-- Q14, Q2                   |
                |                                        |
                v                                        |
 [12 /csp-report/ logs]                                 |
                                                          |
 [13 route API-012 + VAL-002] <-- Q5,Q6 routed            |
                                                          |
   (none) -> [14 BOT_TOKEN] <-- role matrix, Q10 boundary  |
                |                                        |
                v                                        |
 [15 pin images + certs]                                 |
                                                          |
   (none) -> [16 translation observability] ---------------+
```

**Each edge, with the reason it exists:**

| Edge | Why it exists |
|---|---|
| **2 → 3** (hard) | BLOCK 3's two guards must **reuse** BLOCK 2's helper. Landing 3 first means writing a seventh and eighth copy of the `add`/`incr` idiom, then deleting two of them — and the copy that BLOCK 2 then consolidates is a *newer, differently-shaped* copy. The edge is a shape dependency, not just a correctness one |
| **1 → 5** (hard, by `09-VAL-006`) | The report's own rule: *"Land API-001 and API-008 in the same release, or land API-001 first and treat API-008 as 'in progress, do not close'."* Both define **what a cache read does on failure**, and the rate cache is one of the readers. Split, the rate cache serves a pre-boot value for up to 5 minutes with no invalidation while a `cache_get_or_none` helper sits half-adopted next to it. The Validator's risk #1: *"A helper that is implemented, documented and never called is worse than an absent one"* |
| **4 → 6** (soft) | Both are outbound-Telegram retry decisions and both touch a `retry_after` sleep. BLOCK 4 fixes the bot's handler; BLOCK 6 fixes the backend's alert path (`09-VAL-009`), which the report does not even list as the same defect. If BLOCK 6 lands first and BLOCK 4 then sets the ceiling, there are briefly two different ceilings for the same Telegram response. Soft because neither fails to compile without the other |
| **6 → 7** (hard) | **The same three functions in the same file.** BLOCK 6 changes `_send_payloads`'s send calls and its retry sleep; BLOCK 7 changes `_send_payloads`'s failure handling and `_run_send`'s catch. Landing them apart means two commits editing overlapping bodies in one module, and the second silently re-reverts the first's escaping if the author works from a stale read. Also: BLOCK 6's stub-signature change and BLOCK 7's `test_non_aiogram_error_propagates` rewrite are in the **same test file** |
| **10 → 11** (soft) | Both edit `docker/nginx/nginx.conf` and `nginx.dev.conf`. With one Implementor they are serialised by §1.3 anyway, but BLOCK 11's `nginx -t` gate means a half-applied config from BLOCK 10 would be validated twice. The edge exists so BLOCK 11's verification is meaningful |
| **10 → 12** (soft) | Same reason, plus both add or tighten an `http{}` zone. A zone declared in one commit and applied in another is the configuration mistake BLOCK 10's structural test exists to catch — the two blocks should not create the situation the test is designed to catch |
| **14 → 15** (hard in practice) | **Same two compose files.** BLOCK 14 restructures `env_file` and volumes across eight services; BLOCK 15 changes `image:` on those same services and one volume. Sequentialising them means each commit is reviewable against one coherent diff of one concern. The edge is not logical but it is the only way both commits stay reviewable |
| **4 → 2** | There is **no** edge. They are independent — bot handler retry policy versus a cache-failure helper in the backend's shared utils. The one-Implementor rule serialises them without a dependency |
| **8 ↔ 16** | **Deliberately no edge** — see §4.3 |
| **1 → 2** (soft, not a hard edge) | Same module (`apps/core/utils/cache.py`), different helpers, different reasons. Serialised by §1.3. BLOCK 2's commit will show BLOCK 1's helper in its diff context, which is fine |
| **Any block → 13** | **No edge.** BLOCK 13 now ships a bounded production change and can run at any point —
  it is *encouraged* to run early so the routing is on the record before any other phase
  touches `apps/search/**`. Its only consumer is `save_search.py`, which is **also
  phase 08 BLOCK 8's file** (§5.3); the Coordinator sequences the two |
| **13 → phase 06 / phase 08** (external) | The handoff is the edge. It is **published**, not consumed — no block in this plan depends on phase 06 or phase 08 answering Q5/Q6 |

### 4.3 Where there is deliberately no edge, and why

| Pair with no edge | Why |
|---|---|
| **8 ↔ 16** | Both touch `apps/core/services/translation.py`, which is why they would *look* ordered. They share no symbol: BLOCK 8 changes what the **backfill command** does with `translate_text`'s **return value**; BLOCK 16 changes what `translate_text` **logs** and adds **counters**. BLOCK 8's preferred (minimal) option does not touch `translate_text` at all — it changes `_translate_for_backfill` in a management command. If BLOCK 8 chose the status-object option they would couple through the return type, and the edge becomes real. Recording the coupling condition here so it is not discovered late |
| **2 ↔ 4** | Different layers, different mechanisms. A rate-limit window and a Telegram replay budget share the word "retry" and nothing else |
| **1 ↔ 5** beyond the wave rule | BLOCK 5's *cache* half is `invalidate_rate_cache()` — a **write-path** helper, not a read-path guard. BLOCK 1's contract is about what a **read** does when the cache is unreachable. The `09-VAL-006` coupling is about the **rate-cache read** and the half-migrated contract, not about `invalidate_rate_cache`. They belong in the same *wave*; they do not need each other to compile |
| **4 ↔ 6, 6 ↔ 7** beyond the file overlap | The edges above exist for **file overlap and test-file conflict**, not for logical dependency. None of the three needs the other's *behaviour*. This is stated so nobody reads BLOCK 4's shape as constraining BLOCK 6's |
| **9 ↔ 14** | Both edit `config/settings/prod.py` — different guards (`EMAIL_HOST` vs `BOT_TOKEN`), ~30 lines apart, different blocks. Serialised by §1.3 and by §5.3's reservation. Coupling them would put an unresolved human decision (Q1) in front of a change that needs none |
| **11 ↔ 14** | BLOCK 11 touches compose/urls/nginx/settings-adjacent files; BLOCK 14 touches compose × 2, `prod.py` and the settings suite. The overlap is `docker-compose*.yml` in BLOCK 15's case, not BLOCK 11's. There is no shared symbol |
| **12 ↔ 16** | Two log-hygiene findings in two different apps and two different tiers. They share a **policy**, not a file. The policy is phase 06's; each block ships its own field selection |
| **10, 11, 12 ↔ 15** | BLOCK 15 touches `docker-compose*.yml`; BLOCKS 10–12 touch `docker/nginx/*.conf`. The certificate path in BLOCK 15 and the TLS block in BLOCK 11 are **related** but in different files, and BLOCK 11's `nginx -t` gate does not validate a compose volume default |
| **Any block → the legacy in-source marker sweep** | There is no edge because phase 09 **must not start it**. Phase 03's plan §5.2 reserves the `EXT-` / `AUT-` / `SRH-` marker sweep and forbids other phases from beginning it. Phase 09's `EXT-002` markers sit inside `retry.py` and `main.py` — files BLOCK 4 edits — and are left exactly as they are |

### 4.4 The orders that are unsafe, and the rollout gates

1. **BLOCK 3 before BLOCK 2** — a seventh and eighth copy of the `cache.add` / `cache.incr`
   idiom are written, and the consolidation that follows has to delete two of them. The
   `09-VAL-005` analysis is about *policy*, not about this; it does not make the
   duplication acceptable.
2. **BLOCK 5 before BLOCK 1** — `09-VAL-006`'s explicit constraint. With API-008 landed and
   API-001 not, the rate cache serves a pre-boot value for up to 5 minutes with no
   invalidation, and the next developer finds a `cache_get_or_none` that does not exist.
   **BLOCK 5 must not be closed while BLOCK 1 is open.**
3. **BLOCK 7 before BLOCK 6** — two commits editing the same three functions in one module.
   The second, written from a stale read, silently re-reverts the first's escaping.
4. **BLOCK 15 before BLOCK 14** — two large diffs against `docker-compose.prod.yml` in
   sequence, each mixing a different concern. Neither is reviewable.
5. **BLOCK 9 without Q1 answered** — a settings guard changes with no recorded human
   decision behind it. This is the block where the absence of a decision is most damaging:
   the change looks like a comment fix and ships without anyone knowing the boot policy was
   chosen.
6. **Any block enabling `IMMEDIATE_ALERTS_ENABLED`** — **forbidden in every environment
   until BLOCK 7 lands.** Phase 08 independently reinforces this: the alert audience
   predicates do not exist yet. The publish-time path is currently *latent* (C-9); turning it
   on with an unretrieved-future dispatch and an unvalidated body would ship three defects
   at once. **Phase 09 does not change the flag** — it records the gate.
7. **ROLLOUT GATE: BLOCK 11's `:80` change must not reach a production proxy before the
   domain is set.** This is a **rollout** gate, not a code gate: the commit may merge; the
   deployment may not, until `server_name` is configured and `nginx -t` passes against the
   operator's real certificate. §8.4 records it as satisfied or open.
8. **ROLLOUT GATE: BLOCK 15's `IMAGE_TAG` requirement must not reach a host that has not
   exported it.** Same shape: the commit may merge; the rollout waits for the runbook line,
   which is **phase 12's**.

### 4.5 What the DAG does *not* decide

The DAG orders blocks. It does **not** resolve Q1 … Q14, and it does **not** answer Q10.

**Q10 — whether the outbound-Telegram consolidation is in scope for phase 09 — is a scope
question the DAG deliberately leaves open.** This plan does **not** assume it. BLOCK 6,
BLOCK 7 and BLOCK 14 each ship the local fix; the consolidation is recorded as a follow-on
(§6.2) with its costs already stated — it breaks the `{module}.Bot` patch targets in **two**
test files and it crosses the backend/bot boundary. If Q10 is answered "yes", the work is a
**separate plan**, not a commit inside BLOCK 6, 7 or 14: folding it into any single finding
would misattribute a cross-tier architectural change to a small defect, which is exactly
what the project's "no speculative redesign" rule forbids.

Each remaining question is a **gate inside a block**, recorded in that block's
`extra_context` and in §0.5, and §8.1 checks that a written answer exists for each.
**A block whose gate is unanswered does not start.**

---

## 5. Cross-phase coordination

Plans `.ai/plans/01-entry-architecture-remediation.md` through
`.ai/plans/08-search-fts-remediation.md` exist; phases 10–15 are being planned in parallel
right now by other Planner agents. This section is the boundary contract. It is
deliberately **one-directional**: phase 09 states what it owns, what it will not touch, and
where its boundaries lie. It does **not** attempt to contact or negotiate with the other
agents.

### 5.1 What phase 09 already owns and must not re-ship

| Phase 09 artefact | What phase 09 must not do | Boundary |
|---|---|---|
| **The cache-failure contract** — `cache_get_or_none` and the shared window helper in `apps/core/utils/cache.py` | Phase 09 must not create a **second** cache-failure helper in any other module, and must not route any request-path cached read through anything else | `apps/core/utils/cache.py` is the **shared home**, chosen because three of the seven guards are web-tier and `apps.*` may never import `telegram_bot.*`. No other phase may add a competing helper beside it. **Phase 13** grades cache effectiveness at legitimate volume; the *failure policy* is phase 09's |
| **The fail-open policy, stated once** | Phase 09 must not write it in seven places. It is one docstring paragraph in `apps/core/utils/cache.py` plus one helper | This is the phase's adopted advisory recommendation. Phase 08's cache-version work is a **different** contract (key lifetime, not failure behaviour) and the two must not be conflated |
| **`normalize_price_to_eur` and the exchange-rate path** | Phase 09 must not touch `03-DB-008`'s `recompute_normalized_prices` sweep, its lock duration or its transaction shape | **Adjacent, not overlapping** (`09-VAL-001`). A reverted rate produces a full-table recompute that then locks for its whole sweep — but fixing either does not fix the other. **No merge. Cross-reference only** |
| **The `EMAIL_HOST` existence-of-consumers question** | Phase 09 must not touch `EMAIL_BACKEND`. That is `02-CFG-004` — the *backend-selection* problem (a prod operator can point mail at stdout) | **Different defects, same settings block** (`09-VAL-001`). Phase 02 owns CFG-001/002/004; phase 09 owns whether the consumers exist. **Action both in one pass; report them as two findings** |
| **The `BOT_TOKEN` role matrix** | Phase 09 must not invent a new role flag. The project already has `DJANGO_ONESHOT=1` + `config.settings.oneshot` as its sanctioned "this process does not need the real secrets" mechanism | Phase 02 owns `DJANGO_ONESHOT`; phase 09's BLOCK 14 reuses it. Reusing is a constraint, not an optional style |
| **`docker-compose.prod.yml`** | Phase 09 must not touch it outside BLOCKS 14 and 15 | **Explicitly out of scope for phase 02** and claimed by no plan read for this pass. BLOCK 15 coordinates tag bumps with **phase 12**'s runbooks |

### 5.2 What phase 09 must not do, for other phases' sake

| Other phase | What phase 09 must not do | Boundary |
|---|---|---|
| **Phase 02 — the env allowlist, `EMAIL_BACKEND`, bot-token guards, the `prod.py` deploy gate** | Phase 09 must not edit `ALLOWED_ENV_VARS`, must not add an env var without its allowlist entry **and** all four `.env*.example` updates in one commit, must not change `EMAIL_BACKEND`, and must not change the `_validate_production_secret` strength rules for any variable other than the one its block names | `config/settings/tests/test_env_allowlist.py` is the gate **any new secret must pass**, and it runs in **both** directions. The `prod.py` deploy gate is phase 02's: phase 09's BLOCK 9 changes the *policy* of one guard and BLOCK 14 the *scope* of another, never the gate's machinery. **`prod.py` is four-block contended** (phase 02 BLOCKS 3/5/7/9, phase 06 BLOCK 4) — the Coordinator sequences |
| **Phase 03 — `alert_query.py`, `immediate_alerts.py`, `DB-004`, `DB-008`** | Phase 09 must not edit `apps/search/services/alert_query.py`, and must not redo the delivery-state or notification-contract work | **Three-way reservation**: phase 06 BLOCKS 5/7 (eligibility), phase 03 BLOCK 9 (delivery state), phase 09 BLOCKS 6/7 (body and dispatch). `DB-004` (`statement_timeout`) **complements** `09-API-001`/`002` as an *instance* of the same untested-failure-posture class — record it in phase 03's roll-up, do not re-file it |
| **Phase 06 — `LOG_MASK_KEY`, the settings base, `06-PII-102`, `06-PII-108`, `06-PII-104`** | Phase 09 must not implement `LOG_MASK_KEY` (**it does not exist in the tree yet** — phase 06 has not landed), must not build the logging-policy `Filter`, must not touch the alert-audience predicate, and must not edit `apps/search/services/search_history.py`, `popular_search.py` or `apps/search/migrations/` | `LOG_MASK_KEY`'s absence is load-bearing for BLOCK 16: the redaction must go through `redact_free_text`, not through a phase-06 mechanism that does not exist. `06-PII-102` owns log-hygiene policy and already has regression tests — **BLOCK 16's log-field selection must be reviewed against them so the assertions land in one place, not two**. `06-PII-108` owns `SearchHistory.query_normalized` — which is why `09-VAL-002` is **routed** (BLOCK 13) and not implemented |
| **Phase 08 — the `SavedSearch.query` / `query_normalized` parking, the client-IP trust item, `sanitize.py`, `IMMEDIATE_ALERTS_ENABLED`** | Phase 09 was instructed **not to decide Q5 or Q6** and **not to edit `apps/search/services/**` or `apps/search/migrations/`**. **Q5 is now resolved by the Product Owner (2026-10-03): BLOCK 13 implements `redact_free_text` in `views/save_search.py` only.** Phase 09 must still **not** edit `apps/search/services/**`, `apps/search/models.py`, `apps/search/migrations/`, or extend `redact_search_query`/`redact_free_text` or change either function's "never lengthen" invariant, and must not change `IMMEDIATE_ALERTS_ENABLED` | **This is the explicit instruction in the brief and it matches phase 08's own plan.** Phase 08's §5.5 lists *"06 — Q5: whether `SavedSearch.query` needs redaction, not just a bound"* as an **open forward dependency** that is now **resolved**. Phase 08's BLOCK 8 owns the **bound** on the same read as `save_search.py`; the two are **sequenced** (§5.3). Phase 09 publishes the view fix (BLOCK 13) and edits nothing else in `apps/search/**`. On the client-IP trust item: BLOCK 10's optional app-level limiter **inherits** `contact_rate_limit._get_client_ip`'s `HTTP_X_FORWARDED_FOR` trust — phase 09 must not change that trust model, and phase 08 must know a phase-09 guard now sits behind it |
| **Phase 10 — code quality** | Phase 09 must not fold BLOCKS 2 and 16's helper work into a general "consolidate the cache layer" or "consolidate the outbound layer" change | `09-API-002`'s seven-copy consolidation **is** a code-quality-shaped change, but it is triggered by a HIGH availability defect and its blast radius is the finding. Phase 10 must not claim it |
| **Phase 11 — test coverage** | Phase 09 must not grow the four required test rewrites into new coverage | BLOCKS 4, 6, 7 and 8 rewrite tests that **encode defects**. Those are *incidental rewrites required by a behaviour change*, the convention phases 03/06/08 all adopted. Phase 11 must not claim them, and phase 09 must not expand them while rewriting |
| **Phase 12 — production ops** | Phase 09 must not write a runbook | BLOCKS 5, 9, 11, 14 and 15 all state a parameter; phase 12 writes the procedure — the ECB sentence, the password-reset corrections, the `server_name` rollout, the `BOT_TOKEN` rotation obligation, the `IMAGE_TAG` requirement. **Adding a fifth editor to `docs/ops/docker-deployment.md` needs the Coordinator** |
| **Phase 13 — performance** | Phase 09 must not make latency claims or `EXPLAIN` anything | Phase 13 grades cache and query effectiveness at **legitimate** volume; phase 09 owns **failure-mode** behaviour. Phase 13 **must assume BLOCK 10 landed**, or it re-measures `media_gate`'s duplicated query as a phase-13 finding. If BLOCK 10 did not de-duplicate it, phase 13 owns that question |
| **Phase 14 — i18n** | Phase 09 must not regenerate locale files | `sanitize_query_for_log`'s `isalpha()` handling degrades the triage BLOCK 16 improves; that classification is **phase 14's**. Recorded and routed. Phase 09 adds no user-visible string in any block (§1.2) |
| **Phase 15 — authorization** | Phase 09 must not build a permission predicate, and must not build a per-request authorization gate | BLOCK 11's Django-side `/metrics` restriction is **adjacent** to phase 15's framework. The phase-15 boundary check is in BLOCK 11's acceptance criteria. Q2's option (b) — a middleware — is a per-request gate and is phase 15's shape, not phase 09's |
| **Any phase — the audit input** | Phase 09 must not edit another phase's audit handbook or **any** `.ai/audit/**` file | Nineteen tracked deletions exist in the working tree and are intentional. `git status --short .ai` must show no new modifications beyond those deletions, this plan's file, and `.ai/tmp/` |

### 5.3 Shared-artefact reservations (the Coordinator must sequence these)

| Artefact | Phase 09 claim | Conflict and rule |
|---|---|---|
| **`src/backend/apps/core/utils/cache.py`** | **Phase 09: BLOCKS 1, 2** (two helpers + the policy docstring) | No other phase claims it today. It becomes the **shared home** for the cache-failure contract by phase 09's decision. If any other phase adds a cache helper, it goes here |
| **`src/backend/apps/core/services/site_config.py`** | **Phase 09: BLOCK 1** | No other phase claims it. Its async wrappers are used by the bot |
| **`src/telegram_bot/services/rate_limit.py`** | **Phase 09: BLOCKS 2, 3** | No other phase claims it. Phase 04 holds `apps/users/services/login_rate_limit.py` — **different file**, see below |
| **`src/backend/apps/core/services/contact_rate_limit.py`**, **`apps/search/services/rate_limit.py`**, **`apps/users/services/login_rate_limit.py`** | **Phase 09: BLOCK 2** (all three, the web tier) | Phase 04 holds `login_rate_limit.py` for `04-AUT-003`; phase 02 holds the **edge** limits (env plumbing); **phase 08 claims `apps/search/services/rate_limit.py`** in its BLOCK 9. Compatible in principle — phase 09 changes the *failure mode*, phase 08 changes the *trust and budget* — but they edit the **same three files**. **Re-read before editing; stop and report on a concurrent change.** BLOCK 10's optional app-level limiter also inherits `contact_rate_limit`'s IP helper |
| **`src/backend/apps/currencies/**`** | **Phase 09: BLOCK 5** | No other plan claims it. `03-DB-008` claims the *recompute sweep's* locking, not this app's seed |
| **`src/backend/apps/search/services/immediate_alerts.py`** | **Phase 09: BLOCKS 6, 7** | **Three-way.** Phase 06 BLOCKS 5/7 (eligibility), phase 03 BLOCK 9 (delivery state), phase 09 (body + dispatch). It is the module's third and fourth edits in this plan. **If either has landed, re-read — do not assume** |
| **`src/backend/apps/search/management/commands/send_alerts.py`** | **Phase 09: BLOCKS 6, 14** (read-only for 14) | Phase 01 owns the daily-run idempotency. **Phase 09 must not redo it** |
| **`src/backend/apps/core/services/translation.py`** | **Phase 09: BLOCKS 8, 16** | **The cleanest ownership in the phase** — no plan read for this pass claims it. BLOCK 8's minimal option does not touch it |
| **`src/backend/apps/core/utils/sanitize.py`** | **Phase 09: BLOCK 16 — compose only, never modify** | **Phase 08's** (its BLOCKS 3/4 reshape this neighbourhood). `redact_search_query`'s never-lengthen invariant is **shared** and phase 08 explicitly forbids changing it. BLOCK 16 reuses both functions and modifies neither |
| **`src/backend/config/settings/prod.py`** | **Phase 09: BLOCKS 9, 14** (one guard each) | **The most contended settings file in the repository.** Phase 02 BLOCKS 3/5/7/9; phase 06 BLOCK 4. Sequential, never parallel |
| **`src/backend/config/settings/base.py`** | **Phase 09: read-only** | Phase 02 owns `ALLOWED_ENV_VARS`; phase 06 owns `LOG_MASK_KEY`. Phase 09 reads `CACHES`, `read_env`, `IMMEDIATE_ALERTS_ENABLED` and `USE_X_FORWARDED_HOST` and **changes none of them**. BLOCK 7 *may* touch it under the Q-shape (b) option — and then the allowlist entry and four template updates land in the same commit |
| **`.env.example`, `.env.dev.example`, `.env.prod.example`, `.env.test.example`** | **Phase 09: BLOCKS 14 (maybe), 15 (no)** | Phase 02 BLOCK 6 and phase 06 BLOCK 4 own these files. Gated in **both** directions by `test_env_allowlist.py`. **`IMMEDIATE_ALERTS_ENABLED` must stay `false` in all four** — phase 09 does not change the flag |
| **`docker-compose.yml`, `docker-compose.prod.yml`** | **Phase 09: BLOCKS 14, 15** | **Phase 02's** `docker-compose.dev.override.yml` is a *different* file. `test_compose_contract.py` is **phase 01's** and phase 02's plan explicitly forbids re-asserting compose parity from another phase. BLOCK 14 before BLOCK 15 (§4.2) |
| **`docker/nginx/nginx.conf`, `nginx.dev.conf`** | **Phase 09: BLOCKS 10, 11, 12** | No other phase claims them. Three blocks edit both files; **BLOCK 10 first** so the `nginx -t` gate in BLOCK 11 validates a coherent config. Phase 13 has no claim |
| **`src/backend/tests/test_nginx_config.py`** | **Phase 09: BLOCKS 10, 11, 12** | The established structural-test home; it parses `nginx.conf` only today, and BLOCK 10 extends it to the dev config |
| **`docs/ops/docker-deployment.md`, `docs/ops/rollback.md`, `docs/ops/migration-workflow.md`** | **Phase 09: BLOCKS 5, 9, 11, 14, 15** | **Phase 12 owns the runbooks.** Phase 01, 02 and 08 have all touched `docker-deployment.md`. **Re-read immediately before editing; stop and report on a concurrent change.** No phase-09 block rewrites a runbook — it corrects a false claim or states a parameter |
| **`docs/01-spec/architecture-structure.md`** | **Phase 09: BLOCK 11** (one new section) | No other phase claims it. Phase 06 holds `docs/01-spec/technical-specification.md` — a **different** file |
| **`src/backend/apps/search/views/save_search.py`** | **Phase 09: BLOCK 13** (Q5 ruled 2026-10-03: implement `redact_free_text` at the view boundary). The **view function** and **URL name** are unchanged; only the `redact_free_text` call + bounded-length guard + test are added. Phase 08 BLOCK 8 still owns the `max_length=200` **model** bound (§5.3 contention row) | **Three-way reserved** (phase 06 BLOCK 7, phase 03 BLOCK 9 option B, phase 08 BLOCKS 5/8) for **`services/search_history.py`, `services/popular_search.py`, `apps/search/models.py`, `apps/search/migrations/`** only. BLOCK 13 edits **`save_search.py`** — a one-line-plus-guard change, not a handoff |
| **`src/backend/apps/search/services/search_history.py`, `services/popular_search.py`, `apps/search/models.py`, `apps/search/migrations/`** | **Phase 09: NONE** | **Three-way reserved** (phase 06 BLOCK 7, phase 03 BLOCK 9 option B, phase 08 BLOCKS 5/8). These files are **not** touched by BLOCK 13 — only `views/save_search.py` is |
| **`apps/ads/migrations/`** | **Phase 09: BLOCK 8 only, under Q4 option (b)** | Phase 05 plans `ads/0008_*`; phase 06 also touches `apps/users/models.py` migrations. **Re-check the directory immediately before generating**; never renumber |
| **`src/backend/conftest.py`** | **Nobody in this plan** | The most contended file in the repository. **No phase-09 block may edit it.** If a block appears to need a new fixture, that is a signal the test is over-fitted |
| **`.ai/audit/**`** | **Nobody.** Unmodifiable by mandate | Nineteen tracked deletions. `git status --short .ai` must show no new modifications |
| **The in-source `EXT-` / `AUT-` / `SRH-` marker sweep** | **Phase 09: NONE** | **Phase 03's plan §5.2 reserves this sweep and forbids other phases from starting it.** `EXT-002` markers sit inside `retry.py` and `main.py` — files BLOCK 4 edits — and `EXT-003` / `EXT-04` inside the nginx configs — files BLOCKS 10/11/12 edit. Phase 09 leaves them exactly as they are and keys its own citations on `09-API-nnn` |

### 5.4 The `09-API-012` → phase 06 / phase 08 handoff (BLOCK 13)

**Recorded here so it is not lost, and so no one implements it twice.**

1. **`09-VAL-002` was an unowned open product defect; the DECISION is now taken (2026-10-03).**
   `query_normalized` stores the raw query on **both** tables the project believes it redacts,
   and `apps/search/migrations/0002_redact_search_queries.py` preserved it **on purpose**, with
   a docstring saying so. It is not the same defect as `09-API-012` — that one is a missing
   call at a view, this one is a storage decision plus a data migration — and the two must be
   **sequenced and reported as one remediation item**. **The Product Owner ruled: key
   `query_normalized` on the redacted form.** The *data repair* is still outstanding and still
   unowned by implementation; see item 2.
2. **Phase 09 implements `09-API-012` and records `09-VAL-002`'s migration.** The Q5 question
   phase 08 parked as its **Q5** was answered on 2026-10-03, so the view call plus a test is
   **no longer a routed dependency — it is this plan's work** (BLOCK 13). What phase 09 still
   does **not** do is the **data migration**: `apps/search/services/search_history.py`,
   `popular_search.py` and `apps/search/migrations/` are **three-way reserved** (phase 06
   BLOCK 7, phase 03 BLOCK 9 option B, phase 08 BLOCKS 5/8), and a phase-09 migration would be
   a fourth editor. **Phase 06 owns `06-PII-108` and the migration.**
3. **What each owner must satisfy** is published in BLOCK 13, so the acceptance criteria
   cannot drift between this plan and theirs.
4. **The third door.** The same raw/redacted split reaches the **session** through
   `search_history.py::_record_session_history` for anonymous users. Whoever writes the
   migration must include it — a fix that covers the two tables and not the session closes
   two of three paths.
5. **The gate, restated under the ruling.** Phase 09 records that implementing the view fix
   is **necessary and not sufficient**, and that the dedup-semantics consequence of redacting
   `query_normalized` (two users searching different phone numbers collapse into one row) was
   **decided, by the owner, on 2026-10-03** — it is no longer an open question, and the
   commit body must present it as a decision rather than a side effect.

### 5.5 What phase 09 needs from other phases (forward dependencies)

| Phase | Phase 09 depends on it for | Risk if phase 09 is silent |
|---|---|---|
| **02 — the env allowlist and `prod.py` sequencing** | Clearance to touch `prod.py` twice (BLOCKS 9, 14) and possibly `base.py` (BLOCK 7) | Two phase-09 commits and two phase-02 commits interleave in one settings module, and one clobbers the other |
| **02 — CFG-004 (`EMAIL_BACKEND`)** | A single pass over the email block of `prod.py` | Two commits fix half the email settings question and the tracker records it twice |
| **06 — the log-hygiene policy** | Confirmation that BLOCK 16's redaction lands in phase 06's test suite rather than a second one | Two regression suites for the same class, one of which will drift |
| **06 — `06-PII-108` — PROPAGATION OBLIGATION, 2026-10-03** | The **follow-up data migration** rewriting existing `query_normalized` rows onto the redacted form, and the **written statement of the "one rule for all query-persistence paths"** policy (routed from phase 08's Q5 as well) | `query_normalized` keeps holding raw queries **forever** while the tracker shows `09-VAL-002` decided. The decision exists; the data does not follow it |
| **08 — BLOCK 8 (`save_search` bound)** | Sequencing on the shared `save_search.py` read | Two phases edit one read; the bound and the redaction get conflated or one clobbers the other (§5.3) |
| **08 — the client-IP trust item** | A ruling on `HTTP_X_FORWARDED_FOR` trust before BLOCK 10's optional app-level limiter inherits it | Phase 09 ships a guard on phase 08's undecided trust assumption |
| **12 — the runbooks** | The ECB correction, the password-reset corrections, the `server_name` rollout, `BOT_TOKEN` rotation, the `IMAGE_TAG` requirement | An operator's first encounter with each is unguided, and two of them are inside the compromise-response procedure |
| **13 — the performance baseline** | A grading that assumes BLOCK 10 landed, and that does not re-measure `media_gate`'s duplicated query | Phase 13 re-measures a phase-09-owned defect as its own |
| **15 — the authorization framework boundary** | Confirmation that BLOCK 11's Django-side `/metrics` gate does not fork a per-request gate | Two mechanisms for one control |
| **Coordinator — `09-VAL-001`, `09-VAL-005`, Q9, Q10, Q11** | The cross-phase reconciliations, the rollout order, the commit shape, the consolidation scope question, and whether a live rate feed is wanted | The phase either double-files a defect, couples two independent changes for no safety gain, or silently commits the product to a capability it does not have |

### 5.6 Audit-pipeline artefacts — recorded, routed, not actioned

Three items in this plan are defects in the **audit input**, not in the product:

- **`09-VAL-003` — the evidence anchors.** Every line-numbered anchor in the source report
  is advisory and several are wrong (C-1, C-2, C-5, C-6, C-7, C-8). The **wider** note
  matters more: this project hard-codes finding IDs from **prior audit cycles** as in-source
  markers, so `EXT-`, `AUT-`, `API-` and `SRH-` all collide. **Any remediation tracker must
  key on `<phase>-<prefix>-<NNN>` (`09-API-007`), never on the bare ID.** Phase 09 applies
  this to itself: every citation in this plan is cycle-scoped. **The in-source marker sweep
  is phase 03's** (§5.3) — phase 09 does not start it.
- **`09-VAL-005` — the rejected rollout claim.** The report's roadmap said API-003 "must
  land together with API-002". It does not hold: a guard that fails **closed** is not a
  working guard either, and `contact_<ad_id>` has no limiter today, so API-002 cannot
  "remove" a guard that was never there. The corrected order — and the real prerequisite,
  that API-003's per-seller cap ships **inside** API-003 — is in §4.1 and BLOCK 3. Recorded
  so the rejection is not re-litigated.
- **`09-VAL-001` — the cross-phase double-ownership.** Four pairs are adjacent, not
  mergeable: API-008 ↔ `03-DB-008`, API-009 ↔ `02-CFG-004`, API-001/002 ↔ `03-DB-004`, and
  `09-VAL-002` ↔ `06-PII-108`. **No merge in any case.** §5.1 and §5.2 state the ownership;
  the Coordinator sequences, not the agents.

**A fourth observation, for the Coordinator rather than for any phase's code:** three of
this phase's findings are, at root, *"the documentation asserts a capability the code does
not have"* — the ECB feed, the password-reset flow, and (per phase 02) a live prod-config
CI gate. A short **verified-capabilities** section in the deployment runbook — each line
with the command that proves it — would prevent the next cycle re-deriving the same class.
That is **phase 12's** file and **phase 12's** decision.

---

## 6. Out of scope for this plan

Every de-scoping below is **routed**, not dropped. A de-scoped item with no destination is
a re-filed finding.

### 6.1 De-scoped by ownership (routed, not dropped)

| Item | Where it went | Why |
|---|---|---|
| **`09-VAL-002` — the follow-up DATA MIGRATION** repairing `query_normalized` rows onto the redacted form | **Phase 06 (PII policy owner).** BLOCK 13 records the obligation and its acceptance criteria | The **decision** was taken by the Product Owner on 2026-10-03; the **data repair** was not, because `apps/search/services/` and `apps/search/migrations/` are three-way reserved and a phase-09 migration would be a fourth editor. Phase 06 owns `06-PII-108` |
| ~~**`09-API-012`** — `save_search` skips `redact_search_query()`~~ | **NO LONGER DE-SCOPED — implemented by phase 09, BLOCK 13, since 2026-10-03** | Q5 was answered (redact at write), so the view fix became a bounded one-line-plus-test change instead of a routed dependency. Phase 08's BLOCK 8 still owns the **bound** on the same read, so the two are **sequenced** (§5.3). The *policy statement* remains phase 06's |
| **The alert-audience predicate** — whether alert recipients respect consent / DECLINE state | **Phase 06** (`06-PII-104`) | Phase 09 must not fork it. `apps/search/services/alert_query.py` is a **three-way** reservation (phase 06 BLOCKS 5/7, phase 03 BLOCK 9, phase 09 **none**) |
| **`EMAIL_BACKEND` env-overridable in production** (`02-CFG-004`) | **Phase 02** | Different defect, same settings block. **Action both in one pass; report as two findings** (`09-VAL-001`) |
| **`03-DB-004`** (`statement_timeout` / `lock_timeout`) | **Phase 03** | It **complements** `09-API-001`/`002` as an instance of the same untested-failure-posture class. Record it in phase 03's roll-up; do not re-file |
| **`03-DB-008`** (`recompute_normalized_prices` lock duration) | **Phase 03** | Adjacent, not overlapping. A reverted rate causes a full-table recompute that then locks — but fixing either does not fix the other |
| **`04-AUT-003`** (XFF-first `$proxy_add_x_forwarded_for`) | **Phase 04** | BLOCK 10's new zone **must** keep `$binary_remote_addr` precisely because of this finding. Phase 09 must not ship the bypassable form |
| **The PII-minimisation policy for log fields** | **Phase 06** (`06-PII-102`) | BLOCK 16 ships the field selection and the counters; the **policy** and its regression tests are phase 06's |
| **`sanitize_query_for_log`'s `isalpha()` character handling** (the Cyrillic collapse) | **Phase 14** | It degrades the triage BLOCK 16 improves. Recorded inside `09-API-017` and routed; classification is phase 14's |
| **`sanitize.py`'s shape** | **Phase 08** (BLOCKS 3/4) | BLOCK 16 composes with its two functions and **modifies neither** |
| **Runbook authoring** | **Phase 12** | Phase 09 corrects a false claim or states a parameter; phase 12 writes the procedure. Adding a fifth editor to `docs/ops/docker-deployment.md` needs the Coordinator |
| **The legacy in-source `EXT-` / `AUT-` / `SRH-` marker sweep** | **Phase 03** | Phase 03's plan §5.2 reserves it and **forbids** other phases from starting it. Phase 09's `EXT-002` markers sit inside BLOCK 4's files and are left untouched |
| **Re-grading `09-API-005` upward if a scraper is observed** | **The next cycle, on observation** | The MEDIUM grade rests on the *absence of observed traffic*. §7 records the trigger |

### 6.2 De-scoped by design (deliberately not done here)

| Item | Why not | Where it is recorded |
|---|---|---|
| **Consolidating all outbound Telegram through one gateway** (the report's advisory #2) | It would collapse `09-API-004`, `09-API-011` and `09-API-013` into one owner with one retry policy and one drop counter — genuinely the highest-value structural change available. But it breaks the `{module}.Bot` patch targets in **two** test files, crosses the backend/bot boundary, and is a cross-tier architectural change. Folding it into any single finding would **misattribute a large change to a small defect** — exactly what the project's "no speculative redesign" and "production code is king" rules forbid | **Q10** is gated as a scope question in §0.5 and §4.5. BLOCKS 6, 7 and 14 each ship the **local** fix and record the boundary. If Q10 is answered "yes", it is a **separate plan** |
| **Implementing a live ECB rate feed** | A **new capability**: an HTTP client, a scheduler entry in `HOURLY_COMMANDS`, a rate-history model, a migration, and a failure-mode design. BLOCK 5's `get_or_create` + wired invalidation + doc correction is the small correct fix and is **correct whichever way Q11 goes** | **Q11** is routed to the owner. §2 records that BLOCK 5 must not build it |
| **Making the rate table read-only in the admin** | A **product** decision, offered by the report as "the other coherent reading". Not a code fix | Recorded in BLOCK 5's binding constraints and §2 |
| **Re-pinning PostgreSQL across a major-version boundary** | An **operation** with its own runbook, not a version bump | BLOCK 15's binding constraint 2 |
| **A scheduled monthly image-bump job** | Deployment hygiene, not a defect fix, and it belongs with whoever owns the CI/CD surface | BLOCK 15's binding constraint 6 routes it to phase 12 |
| **A bot-wide update-concurrency bound** (`dp.run_polling(tasks_concurrency_limit=…)`) | It closes API-004's amplification half, but it changes the bot's **throughput behaviour globally** — a larger decision than a 40-line retry handler, and one whose right value depends on the deployment's worker count | BLOCK 4's Q-shape option (c) is recorded with its cost and **not taken** |
| **An explicit nginx `ssl_ciphers` string** | Pinning `ssl_protocols` and `ssl_session_cache` makes the posture **reviewable**; an explicit cipher list is a maintenance burden that silently rots on the next nginx upgrade | BLOCK 11's binding constraint 6 |
| **Re-running `recompute_normalized_prices` from the boot seed** | The rate table and the derived column already drift; recomputing every price on every deploy turns a correctness fix into a large write amplification | BLOCK 5's binding constraint 3 |
| **Narrowing who may reach the `contact_<ad_id>` branch** | The defect is that the branch is unrated for everyone who *can* reach it. Access predicates are **phase 15's** | BLOCK 3's binding constraint 4 |
| **A "documented capabilities" section in the deployment runbook** | Phase 12's file, phase 12's decision | §5.6, last paragraph |
| **Fixing the report's own evidence defects in place** | `.ai/audit/**` is **unmodifiable by mandate** | C-1 … C-10 in §0.2.1 are recorded here instead |

### 6.3 Explicitly forbidden while implementing

These are the specific wrong moves this phase invites. Each is the shape of a plausible,
confident mistake rather than an arbitrary restriction.

1. **Never use a line number as a task target.** Semantic anchors only (§1.4). C-1 and C-6
   are what happens when the report's numbers are used.
2. **Never import `telegram_bot.*` from an `apps.*` module.** BLOCK 2's helper's location is
   forced by this, not chosen.
3. **Never create a second cache-failure helper**, and never widen the block to the
   `except ValueError`-only **version-bump** helpers — they are the *invalidation* path, not
   the *guard* path (`09-VAL-008`: four of them, two of whose receivers are unguarded).
   That is a separate finding.
4. **Never remove the `ValueError` branch** from a widened `except` tuple. Two test files
   pin its reset semantics and the LocMemCache behaviour they rely on.
5. **Never flip `IMMEDIATE_ALERTS_ENABLED`** in any environment, in any block. It stays
   `false` in all four templates until BLOCK 7 lands **and** phase 06's predicates exist.
6. **Never add `csrf_exempt`.** None exists anywhere; CSRF is enforced on all three
   moderation endpoints, and `09-API-014`'s item (2) is consistency, not a hole.
7. **Never drop the `ValueError` reset, the `return_exceptions=True` gather, the
   one-`Bot`-per-batch contract, or the `finally: close session`** in `immediate_alerts`.
   Four test classes pin them.
8. **Never edit `src/backend/conftest.py`.** No phase-09 block may.
9. **Never edit `.ai/audit/**`.** Never modify another phase's audit handbook.
10. **Never set `IGNORE_EXCEPTIONS` on `CACHES`, and never pin
    `CACHES["default"]["TIMEOUT"]`.** The first silently changes every cache read's failure
    semantics across the project; the second would silently extend the lifetime of every
    cache entry in the system. Neither is this phase's fix.
11. **Never add a `statement_timeout`, a `lock_timeout`, or any `DATABASES` key** — that is
    `03-DB-004`.
12. **Never add `@require_POST` to `csp_report`** while BLOCK 11 standardises its siblings.
    Do not write the stdlib `html` module where `django.utils.html.escape` is meant; the
    translation service's `html.unescape` is the decoy.
13. **Never make an outbound network call** to Telegram, Google Translate, ECB or any host
    during a test or a verification step.
14. **Never renumber or edit an applied migration**, and never generate one without
    re-checking the directory in the same breath.
15. **Never rewrite a test to keep a defect.** The four unconditional rewrites (BLOCKS 4, 6,
    7, 8) each require the test to be named and the reason stated in the commit body. Any
    *other* test change is a red flag and must be reported, not absorbed.
16. **Never let a block's gate be answered implicitly** by whoever implements first. Silence
    is not an acceptable outcome for any of Q1 … Q14.

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Migration" covers DDL, data movement and rollback. "Contention" covers
shared files. "Contraction" covers behaviour changes to existing consumers. "Correctness"
covers defects that survive a green suite. "Security" covers trust boundaries, credentials
and rate limits. "Availability" covers degraded modes and outage behaviour.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An Implementor works from the report's symbol list and blocks on `deliver_support_ticket_email`, on the `"…(continuing)"` log string, or on `docker-compose.yml:240-243` as `BOT_TOKEN:` lines — **none of which exist** | Process | **High** | Med | C-1, C-2 and C-3 are stated in §0.2.1, in §1.4 and in each affected block's file surface. The Validator re-reads before each block | Very low |
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled block in §3 and a row in §0.5, repeated in the task YAML's `extra_context`; §8.1 checks a written answer exists for each | Low |
| **All** | A block's tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its exact Docker gate command; tests run **only** through the `test` service (§1.1) | Low |
| **All** | A red gate is captured while another phase's validator runs, and a teardown race is reported as a product defect | Process | **High** | Med | Concurrent runs collide on one `test_mko_bazuna`. Re-run serially before reporting. The symptoms to recognise are `test_mko_bazuna does not exist` and `relation "..." does not exist` | Low |
| **All** | A green test that **encodes a defect** is "fixed" by changing production code instead | Correctness | Med | **High** | Project rule 2 restated in §1.4. **Four** unconditional rewrites are named per block; each commit body must name the test and state that the old assertion documented the defect | Low |
| **All** | A concurrency change is justified by an unverified aiogram/gunicorn default (U8–U11) | Process | Med | Med | All fifteen runtime claims are carried in §0.2.4 with their verification steps. The **shape** of each fix is the deliverable, not a number copied from the report | Low |
| **All** | A new env var is added without its `ALLOWED_ENV_VARS` entry and four template updates, failing the allowlist gate in both directions | Security | Low | Med | No block requires a new env var. If BLOCK 7's backpressure option (b) does, the entry and all four templates land **in the same commit** (§1.4) | Very low |
| **1** | The fallback strings change, breaking the site header and every bot deep link | Regression | Low | **High** | Binding constraint 2 and the fallback-string test; the strings are asserted byte-identical under both a cache fault and a database fault | Very low |
| **1** | `set_cached_site_config` moves **outside** the `try` and a cache that is permanently read-only turns every request into a database read | Performance | Med | Med | The cache-write test asserts the write still happens on the success path, and `/health/` still reports the outage so the condition stays visible | Low |
| **1** | `IGNORE_EXCEPTIONS` or a pinned `CACHES["default"]["TIMEOUT"]` is added as a "cleaner" fix | Regression | Low | **High** | Binding constraint 4, stated explicitly in §1.4 and §6.3. **This is the one wrong fix that looks obviously right** | Very low |
| **1** | Q12 is answered implicitly by moving the write out "because it is obviously better" | Process | Med | Med | The block is gated; the commit body names the option and the consequence | Low |
| **2** | The helper is scoped to `telegram_bot/services/rate_limit.py` and **three web-tier 500s survive** | Correctness | Med | **High** | Binding constraint: the helper lives in `apps/core/utils/cache.py`; an `apps.*` → `telegram_bot.*` import is forbidden. Test 1 is **one per guard**, seven in total | Low |
| **2** | The `ValueError` branch becomes unreachable because a broader tuple swallows it | Regression | Med | Med | Two existing test files pin the reset path; `test_login.py` asserts `cache.get("login_rl:127.0.0.1") == 1` after the reset | Low |
| **2** | An **eighth** guard nobody audited keeps the `except ValueError`-only idiom | Correctness | Med | Med | The Auditor's pre-step is a repo-wide search for the `cache.add` + `cache.incr` shape; any new hit is reported before the commit | Low |
| **2** | The three web-tier files are edited on a stale read and phase 08's or phase 04's work is clobbered | Contention | **High** | Med | §5.3 names all three reservations. Re-read before editing; stop and report on a concurrent change. `test_compose_contract.py`-style parity assertions are not re-asserted from another phase | Med — accepted |
| **2** | Fail-open is read as a regression and "fixed" by re-tightening | Review | Med | **High** | The commit body states that failing open is the **documented, intended** policy — the same one `UpdateIdDedupMiddleware` already states — and that BLOCK 3's per-seller cap is what bounds the residual exposure | Low |
| **3** | The guard is placed **after** `record_contact_initiated` and the outbound send, so a refused trigger still sends and still writes analytics | Correctness | Med | **High** | Binding constraint 3; the test asserts the **absence** of both side effects, not the limiter's return value | Very low |
| **3** | Only the per-buyer guard is implemented and the seller is still floodable from cycling accounts | Correctness | Med | **High** | Test 2 uses **distinct buyers** against one seller — the case that distinguishes the two guards. Per `09-VAL-005` the per-seller cap is a prerequisite of shipping at all | Very low |
| **3** | The seller key needs an extra database round trip because the seller identity is resolved after the check | Performance | Med | Med | `get_seller_for_contact` already returns `(bool, User | None)`; read the call order and measure if a query is added | Low |
| **3** | An over-tight buyer budget blocks legitimate repeat buyers | Product | Med | Med | The per-buyer budget mirrors the shipped `contact_us` budget; both numbers are stated in the commit body so they are tuned deliberately | Low |
| **4** | `_make_dispatcher` keeps `ExceptionTypeFilter(TelegramRetryAfter)` and the new sibling-replay test **passes vacuously** | Correctness | **High** | **High** | Binding constraint 3. The new case is demonstrated **red** against the current wiring first. A green result that proves nothing is the worst outcome in this block | Low |
| **4** | `retry.py` ships without its test change, the suite goes red, and someone reverts a correct fix | Rollout | **High** | **High** | Three files, one commit; §8.2 checks the atomicity; the commit body names all three tests | Low |
| **4** | The budget is set too low and real messages are dropped that a longer budget would have retried | Availability | Med | Med | The drop counter is the observability that makes it measurable, and the budget and its rationale are stated in the commit body | Low |
| **4** | The handler's contract change breaks a **new** caller that branches on its return value | Correctness | Low | Med | The Validator confirmed exactly one production caller and no branching code; the Auditor re-confirms at commit time | Very low |
| **5** | `get_or_create` preserves a value that has been wrong for months, and the fix is read as "the rate is now correct" | Data | Med | Med | The new log line reports the rate in use **and its provenance** on every boot, so the value is no longer silent. State this in the commit body | Low |
| **5** | The invalidation is wired but the **real** write path is a different one, so the call-site count rises to one and the defect survives | Correctness | Med | Med | The cache-invalidation test exercises the **production path**, not the helper directly. `09-VAL-008`'s warning — a helper that is implemented, documented and never called is *worse* than an absent one — is quoted in the block | Low |
| **5** | A cache call inside a signal rolls back the saving transaction under an outage | Availability | Med | Med | Binding constraint 5; the outage-does-not-roll-back test is explicit | Low |
| **5** | A live ECB feed is quietly built "while we are here", committing the product to a new capability | Scope | Low | **High** | Q11 is routed; binding constraint 7; the commit body must record that the feed was NOT built | Very low |
| **6** | One of the **four** send sites is missed and the retry path still sends unescaped HTML | Correctness | Med | **High** | Binding constraints 1 and 2; the test must exercise the retry send, not only the initial one | Low |
| **6** | The wrong `html` import — the stdlib module the translation service already imports for **unescaping** | Correctness | Med | **High** | Binding constraint 3; the code hint names the import path; under option (b) the test asserts absence of live markup, which fails against a decode | Low |
| **6** | `TypeError` from an unchanged `send_message` stub is triaged as a regression | Process | **High** | Low | A **known** consequence of option (a), budgeted in the same commit and named in the commit body. Not a regression | Very low |
| **6** | A full-substring markup check on the digest **passes against the defective code** because of the 50-character truncation | Correctness | **High** | Med | The test asserts on the truncated prefix. This is the exact false refutation the report itself recorded — a naive test here would be worse than no test | Very low |
| **7** | The shutdown hook lands in the gunicorn **master** and does nothing in the workers, while every test passes | Correctness | Med | **High** | `preload_app = True` (C-7) is the whole reason Q7 is gated. Test 3 asserts the **registration point** and its survival across a fork — not the outcome alone | Low |
| **7** | Raising `_run_send`'s catch to `Exception` hides a programming error behind a log line | Correctness | Med | Med | `logger.exception`, not `logger.warning` — the stack trace is preserved | Low |
| **7** | The backpressure gate drops real alerts and is discovered only by a user | Availability | Med | Med | It is safe from a duplicate standpoint **only** because `SavedSearchNotification` rows are written first and the daily digest is unconditional. Both facts go in the commit body | Low |
| **7** | `immediate_alerts.py` is edited on a stale read and phase 03's or phase 06's work is clobbered | Contention | Med | **High** | Three-way reservation (§5.3); the file is the plan's third and fourth edit. Re-read; stop and report | Low |
| **8** | The equality comparison misfires on a legitimate translation identical to the source and inflates the fallback counter | Correctness | Med | Low | The counter is a signal, not a gate; the WARNING names the ad and the field; stated in the commit body | Low |
| **8** | Option (b) is chosen and the migration number collides with phase 05's `ads/0008_*` | Migration | Med | Med | Re-check `apps/ads/migrations/` in the same breath as generating; never renumber; run `--create-db` afterwards | Low |
| **8** | The **whole** `test_translation.py` suite is rewritten and the API-key non-leakage guard is weakened "to make the suite pass" | Security | Low | **High** | Binding constraints: under option (a) the suite must pass **unchanged**; under option (b) the rewrite is explicit and the security guard is named as untouchable | Low |
| **8** | Part (b) of the finding is re-implemented — `asyncio.run`, batching, a `LISTEN/NOTIFY` sweep — on the report's rejected claim | Scope | Med | Med | C-5 records that the file is 124 lines, synchronous, and already has `--batch-size`. Binding constraint 5: `--limit` only | Very low |
| **9** | ~~The guard changes with no recorded human decision behind it~~ — **CLOSED 2026-10-03**: the Product Owner chose the warning | — | — | — | Replaced by the two rows below | Closed |
| **9** | The warning is shipped as a raise, or a test is added asserting the raise fires | Correctness | Med | **High** | The ruling forbids both. Acceptance criteria: the import **succeeds** and warns; **no test may assert it raises**. The commit body names the ruling and its date | Very low |
| **9** | A support escalation is lost on a host that never noticed the warning | Product | Med | Med | **The accepted cost of the owner's decision**, not a defect to fix. The warning names the consequence; phase 12 owns the runbook line | Med — accepted, by decision |
| **9** | `test_deploy_check_env_parity.py`'s guard-count docstring is left stale after the demotion | Documentation | Med | Med | Binding constraint 4 and an acceptance criterion. A docstring that miscounts the raising guards is the same defect class as the comments this block fixes | Very low |
| **9** | Only `prod.py`'s comment is corrected and **five runbook sentences** keep asserting password-reset behaviour — two inside the compromise-response procedure | Documentation | Med | **High** | Binding constraint 2, restated to **six** sites including `test_prod_logging.py` and `test_csrf_trusted_origins.py`. This is the finding most likely to cause a **wrong decision under pressure**: an operator rotates a key believing links expired | Low |
| **9** | `prod.py` or `docker-deployment.md` is edited on a stale read and phase 02's, 06's, 01's or 08's work is clobbered | Contention | **High** | Med | §5.3 names both reservations. Re-read immediately before editing; stop and report | Med — accepted |
| **9** | `EMAIL_BACKEND` is "tidied" at the same time and phase 02's `CFG-004` is half-fixed | Process | Med | Med | Binding constraint 5; `09-VAL-001`'s ruling is actioned-in-one-pass, reported-as-two | Low |
| **10** | The zone is declared in **one** file, or in the wrong `http{}` context, and silently does nothing | Configuration | Med | Med | The structural test parses the **shipped** files and asserts the declaration and the application. `nginx -t` before rolling | Low |
| **10** | The zone is too tight for a real thumbnail burst and legitimate requests are discarded | Availability | Med | Med | `burst` + `nodelay` are part of the shipped shape; the numbers are in the commit body | Low |
| **10** | The app-level limiter inherits `contact_rate_limit`'s `HTTP_X_FORWARDED_FOR` trust and the trust model is changed here | Security | Low | **High** | Binding constraint 1: keep `$binary_remote_addr`; the app-level trust assumption is **phase 08's / phase 04's**. Recorded, not fixed | Low |
| **10** | Phase 13 re-measures `media_gate`'s duplicated query as its own finding | Process | Low | Low | The commit body tells phase 13 whether the de-duplication was done | Very low |
| **11** | The `:80` change reaches production before a real `server_name` is set | **Rollout** | Med | **High** | **The only change in the phase that can break a working deployment.** Q14 is gated; `nginx -t` is binding; §4.4 item 7 is a rollout gate and §8.4 records it | Low |
| **11** | Pinning `ssl_protocols` negotiates away from an existing client | Availability | Low | Med | Pin `TLSv1.2 TLSv1.3` — do **not** drop TLS 1.2 in a change about reviewability | Low |
| **11** | `reject_ad` / `ban_user` change a 302 to a 405 and a moderation template depends on the redirect | Regression | Med | Med | The template's non-HTMX fallback is checked **before** converting; stop and report if it depends on the redirect | Low |
| **11** | A Django-side `/metrics` gate forks phase 15's authorization framework | Design | Med | Med | The phase-15 boundary check is in the acceptance criteria; option (b) — a middleware — is explicitly phase 15's shape | Low |
| **11** | The report's inverted `/metrics` impact model is written into a runbook | Documentation | Med | Med | Q3 / U13: one `curl` from a sibling container settles it. **Do not write the sentence before it runs** | Low |
| **12** | The reduction is a blanket "log nothing" and triage capability is destroyed | Observability | Low | Med | The control test asserts the operator fields — `violated-directive`, `effective-directive`, `disposition`, `blocked-uri` host+path, `sample` — are still present | Very low |
| **12** | `@require_POST` is added to `csp_report` while BLOCK 11 standardises its siblings | Scope | Low | Low | Binding constraint 5; the report's own warning is the right sequencing note | Very low |
| **12** | `sanitize.py` is extended with a masking helper instead of composed | Scope | Med | Med | Binding constraint 3: compose redact-then-truncate; do not modify either function. `sanitize.py` is phase 08's | Very low |
| **13** | A tracker records "search PII handled" after only the view-level fix | Process | Med | **High** | BLOCK 13's acceptance criteria are published for both owners, and the block states explicitly that fixing `09-API-012` alone is **not sufficient** | Very low |
| **13** | ~~The handoff is dropped and `09-VAL-002` — which has **no owner today** — is lost until the next audit cycle~~ | — | — | — | **Replaced below**: `09-VAL-002` now has a named owner for its migration (phase 06) and a decided policy | Closed |
| **13** | The `query_normalized` **data migration** is never written, so the decided policy exists with raw data behind it | Process | **Med** | **High** | The obligation is a **named propagation obligation on phase 06** in §5.5 with published acceptance criteria, and BLOCK 13's commit body must record it. The decision is not the fix; say so in the tracker | Med — accepted |
| **13** | Phase 08 BLOCK 8 and phase 09 BLOCK 13 collide on `save_search.py` — the bound and the redaction get conflated | Contention | Med | Med | §5.3 names the shared read; the two are sequenced; re-read immediately before editing | Low |
| **13** | An Implementor "helpfully" writes the `query_normalized` migration into phase 09 | Scope | Med | Med | Acceptance criteria exclude `apps/search/migrations/**`; §6.1 records the de-scoping and names phase 06 | Very low |
| **14** | The commit removes only the three explicit `BOT_TOKEN:` compose lines and is reported as a fix — **it changes nothing** | Correctness | Med | **High** | C-3 states the mechanism is `env_file` + bind mount. Test 1 asserts the **whole-file** distribution, not the explicit lines | Low |
| **14** | A one-shot loses a secret it actually reads and fails to boot | **Availability** | Med | **High** | The role matrix is derived from what each service **reads**; the whole service list is started in the test; binding constraint 5 | Low |
| **14** | Six settings tests are rewritten and the commit looks like test-hacking | Review | Med | Med | Binding constraint 6: each must be named with its reason; none may be deleted to make a run green | Low |
| **14** | `prod.py`, `docker-compose.dev.override.yml` or the `.env*.example` files are edited on a stale read | Contention | **High** | Med | §5.3 names all three reservations | Med — accepted |
| **15** | Requiring `IMAGE_TAG` reaches a host that has not exported it — a hard failure mid-deploy | **Rollout** | **High** | Med | §4.4 item 8 is a rollout gate; §8.4 records it. The `${VAR:?}` form fails **loudly** at `docker compose up`, which is strictly better than a crash-looping proxy whose output looks successful | Low |
| **15** | A digest pin cannot be reverted by editing the file | Rollback | Med | Med | Binding constraint 4: every repinned image's **previous digest** is recorded in the commit body | Low |
| **15** | `postgres` is repinned across a major-version boundary | Dependency | Low | **High** | Binding constraint 2. It is an operation with its own runbook, not a version bump | Very low |
| **15** | The finding is undone by the next compose edit because nothing pins it structurally | Correctness | Med | Med | The structural test is the highest-value part of the block — the finding is **completely unpinned** today | Low |
| **16** | Only the DEBUG **input** is redacted and the translated **output** — which still carries the number — is logged | Security | Med | **High** | Binding constraint 2 names the output line; the test asserts absence on that line explicitly | Low |
| **16** | The sanitiser change accidentally **widens** what is logged, or weakens the credential guard | Security | Low | **High** | Test 1 asserts absence; test 2 is the existing API-key non-leakage test, unchanged | Very low |
| **16** | `sanitize.py` or `redact_search_query`'s invariant is modified | Scope | Med | Med | Binding constraints 1 and 4; `sanitize.py` is phase 08's and phase 08 explicitly forbids changing the never-lengthen invariant | Very low |
| **16** | The log-field assertions are written a second time alongside phase 06's `06-PII-102` suite | Process | Med | Med | BLOCK 16's commit body records that the change was reviewed against phase 06's redaction tests so the assertions land in one place | Low |

---

## 8. Definition of done for the whole plan

Phase 09 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All **26** items have a recorded disposition: **21 implemented** (`09-API-001`, `002`,
      `003`, `004`, `005`, `006`, `007` (part (a)), `008`, `009`, `010`, `011`, **`012`**,
      `013`, `014`, `015`, `016`, `017`, `09-VAL-004`, `09-VAL-005` (as the ordering),
      `09-VAL-006`, `09-VAL-007`, `09-VAL-009`); **1 decision closed with its migration
      outstanding** (`09-VAL-002` → phase 06, via BLOCK 13); **3 recorded as
      process constraints** (`09-VAL-001` as a boundary, `09-VAL-003` as anchor discipline,
      `09-VAL-008` as evidence corrections); **1 rejected on evidence** (`09-API-007` part
      (b)); **0 already fixed**; **0 otherwise dropped**.
      **`09-API-012` moved from *routed* to *implemented* on 2026-10-03** when the Product
      Owner answered Q5.
- [ ] Every gated block (**1, 2, 5, 6, 7, 8, 9, 10, 11, 13, 14**) has a **written** decision
      for its open question, naming the option chosen and the consequences accepted.
      **Silence is not an acceptable outcome for any of them.** **Q1, Q5 and Q6 were answered
      by the Product Owner on 2026-10-03** (§0.7); the rest carry their 2026-10-01
      resolutions.
- [ ] Each of **Q1 … Q14** is either answered with a record, or explicitly re-routed with a
      named destination. **Q1**, **Q5** and **Q6** are **Product Owner decisions, all taken on
      2026-10-03** (§0.7) — Q1 is a **warning, not a boot gate**; Q5 is **redact at write**;
      Q6 is **key `query_normalized` on the redacted form**. **Q4**, **Q7**, **Q8**, **Q12**,
      **Q13** and **Q14** are Planner decisions with Researcher input; **Q2** and **Q9** touch
      the phase-15 and cross-plan boundaries; **Q3**, **Q10** and **Q11** are a verification
      step, a scope ruling and a product question respectively. **No gate remains unanswered.**
- [ ] **Q1 is recorded with a named decider.** The **Product Owner**, on **2026-10-03** — not
      an agent, and not implicitly.
- [ ] The `09-API-012` implementation **and** the `09-VAL-002` phase-06 obligation (BLOCK 13,
      §5.4) were communicated to the coordinator, including the phase-06 acceptance criteria
      for the data migration and the "the view fix alone is **not sufficient**" statement.
- [ ] The `09-VAL-001` boundary rulings were communicated: API-008 ↔ `03-DB-008`,
      API-009 ↔ `02-CFG-004`, API-001/002 ↔ `03-DB-004`, `09-VAL-002` ↔ `06-PII-108` —
      **no merge in any case**, action-together / report-separately where they share a file.
- [ ] **Q10 was answered** — whether the outbound-Telegram consolidation is in scope. If it
      was answered "yes", it is a **separate plan**, not a commit inside BLOCKS 6, 7 or 14.
- [ ] Every de-scoping in §6 has a named destination.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0 (it is green at `6413df5`; it must still be green at
      the end).
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `.\Makefile.ps1 test` → full suite green (seed marker skipped).
- [ ] `.\Makefile.ps1 test-recreate` executed **once after BLOCK 8's migration**, if Q4
      option (b) was chosen.
- [ ] `makemigrations --check` clean after BLOCK 8 (and BLOCK 5 must have added **none**).
- [ ] `config/settings/tests/test_env_allowlist.py` green after BLOCKS 7 and 14 — **in both
      directions**.
- [ ] `apps/ads/tests/test_i18n_completeness.py` green (no block adds a user-visible string,
      but the gate is run to prove it).
- [ ] Every block's exact gate command from §3 was run and green, **not** the full suite
      alone; `ruff` re-run after **every** block, not only at the end.
- [ ] `nginx -t` passes against **both** configs after BLOCKS 10, 11 and 12.
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions, this plan's own file, and `.ai/tmp/`.
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect
      (§1.1).
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git restore` or `git stash` was run at any point; no history was rewritten.
- [ ] **No real outbound network call** was made to Telegram, Google Translate, ECB or any
      host during implementation or verification.

### 8.3 Per-item behavioural confirmation

- [ ] **`09-API-001` / `09-VAL-007`** — with the cache patched to raise, `/`, an ad detail
      page and `POST /login/issue/` keep their statuses; `/health/` still returns 503 with
      `cache: fail`; both fallback strings are byte-identical; a cache hit still
      short-circuits (`test_get_site_name_reads_from_cache` unchanged); a cache **write**
      failure follows the Q12 option and the logged diagnostic is true.
- [ ] **`09-API-002`** — **all seven** guards (four bot, three web) return "allowed" when the
      cache raises; the `ValueError` reset is byte-identical; threshold semantics are
      unchanged; the bot guards are still coroutines; **no `apps.*` module imports
      `telegram_bot.*`**.
- [ ] **`09-API-003`** — the 6th `contact_<ad_id>` trigger from one buyer is refused with
      **no** `send_message` and **no** `AnalyticsEvent`; a burst from **distinct buyers** is
      refused at the per-seller cap; the `contact_us` branch and
      `classify_contact_deep_link` are unchanged; the two counters have distinct key
      namespaces.
- [ ] **`09-API-004` / `09-VAL-004`** — `retry_after=300` and `retry_after=600` both yield a
      **total** sleep inside the budget; a `TelegramServerError` enters the handler and
      replays (demonstrated red first); after exhaustion the handler returns `False` and the
      drop counter increments; `TelegramBadRequest` still returns `False`;
      `test_error_handler_backs_off_and_replays` unchanged.
- [ ] **`09-API-005`** — both nginx configs declare and apply `media_limit`; the key is
      `$binary_remote_addr`; the view refuses a burst; `test_nginx_config.py`'s `/metrics`
      assertions and `test_media_security.py` pass unchanged; `location /static/` untouched.
- [ ] **`09-API-006`** — a hostile title produces no live seller markup in **either** module,
      asserted on the digest's **truncated prefix**; all four send sites are covered; the
      stub signatures match what production sends; the alert retry sleep is bounded.
- [ ] **`09-API-007`** — a translation failure leaves the columns `NULL`; the summary line and
      a WARNING both carry the fallback count; a **second run revisits the same row**;
      `test_uses_translate_text_not_raw_api` unchanged; `test_translation.py` unchanged under
      option (a); `--limit` exists.
- [ ] **`09-API-008` / `09-VAL-006`** — an edited rate survives a second
      `load_exchange_rates` run and the output says "preserved"; a rate changed through the
      wired path is visible to the very next read; a cache outage during invalidation does
      not roll back the saving transaction; **no migration**; **no recompute added to the
      boot path**; all three false capability claims corrected.
- [ ] **`09-API-009`** — no shipped file asserts a password-reset, e-mail-alert or
      seller-confirmation flow; the `CFG-001` mis-attribution is gone; the guard behaves per
      the Q1 decision; no other `prod.py` guard moved; `EMAIL_BACKEND` untouched; the whole
      `config/settings/tests/` package passes.
- [ ] **`09-API-010` / `09-API-014`** — no unsatisfiable `Bearer` challenge; the three
      moderation endpoints refuse non-POST uniformly with no `csrf_exempt`; `/metrics` is
      controlled in Django **and** nginx and the nginx block keeps all four pinned
      properties; every proxied location sets `X-Forwarded-Host` including `/static/`;
      `ssl_protocols` and `ssl_session_cache` pinned and **no** explicit cipher string added;
      the `:80` listener fails closed.
- [ ] **`09-API-011`** — the set of containers receiving `BOT_TOKEN` equals the set that
      actually constructs a `Bot`, plus nothing more; `backup` still has neither `env_file`
      nor a mount; the whole service list starts; under option (b) the guard is role-scoped
      in **both** directions; the six rewritten settings assertions are named in their
      commit; `test_compose_contract.py` unchanged.
- [ ] **`09-API-012` / `09-VAL-002`** — BLOCK 13's record exists and names both owners, both
      candidate fixes, both acceptance-criteria sets, **and** that the view fix alone is not
      sufficient. BLOCK 13 changed **only** `apps/search/views/save_search.py` (one line + guard
      + test); no file under `apps/search/services/`, `apps/search/migrations/`,
      `apps/search/models.py` or `apps/search/tests/test_redact_search_query.py` was edited by
      phase 09.
- [ ] **`09-API-013`** — a non-`AiogramError` dispatch leaves a retrievable ERROR log with the
      payload count; a backlog above the threshold warns and sends nothing **without
      blocking**; the shutdown hook is shown to run in the **worker**, not only the master;
      `TestBotReuse` and `TestGatherIsolation` unchanged.
- [ ] **`09-API-015`** — a report whose `document-uri` carries a query string and which sets
      `referrer` produces a log record containing **neither**; an INFO record is still
      emitted and no WARNING is; the 200/400/405/422 contract is unchanged; `@require_POST`
      was **not** added.
- [ ] **`09-API-016`** — no production service resolves to a floating tag; no `IMAGE_TAG`
      `latest` default remains; **`TLS_CERT_PATH` is DEFERRED (P4, not decided here)** —
      `docker-compose.prod.yml:109` still uses `${TLS_CERT_PATH:-/etc/nginx/certs}`; every
      repinned image's **previous digest** is recorded; a structural test asserts both.
- [ ] **`09-API-017`** — a title with a phone number and an e-mail reaches no log record on
      **any** site including the DEBUG **output** line; the API-key non-leakage test is
      unchanged; a title with no identifiers still logs; the three counters are on
      `/metrics` and the breaker gauge tracks `is_open`; `sanitize.py` was **not** modified.

### 8.4 Cross-phase integrity

- [ ] **`09-VAL-006` held** — BLOCKS 1 and 5 landed in one wave. If BLOCK 5 was closed while
      BLOCK 1 was open, that is a failed wave and must be recorded as such.
- [ ] **`09-VAL-005` held** — API-002 and API-003 shipped in **separate** commits, and
      API-003's per-seller cap shipped **inside** API-003.
- [ ] **`09-VAL-004` held** — BLOCK 4 was one atomic change across `retry.py`, `main.py` and
      `test_error_handler.py`, with **three** test changes. A commit touching only
      `retry.py` is a failed block.
- [ ] **Rollout gate 1 (§4.4 item 7)** — BLOCK 11's `:80` change was **not** deployed before a
      real `server_name` was configured and `nginx -t` passed. **Satisfied / open.**
- [ ] **Rollout gate 2 (§4.4 item 8)** — BLOCK 15's `IMAGE_TAG` requirement was **not**
      deployed before the operator exported it and phase 12's runbook line existed.
      **Satisfied / open.**
- [ ] **Rollout gate 3 (§4.4 item 6)** — `IMMEDIATE_ALERTS_ENABLED` is `false` in **all four**
      `.env*.example` templates. **Phase 09 did not change the flag.**
- [ ] No phase-09 block edited `apps/search/services/alert_query.py`,
      `apps/search/**`'s query-persistence or migration surface,
      `apps/core/utils/sanitize.py`, `src/backend/conftest.py`, `apps/search/models.py`, the
      FTS DDL, the search trigger, or any `.ai/audit/**` file.
- [ ] No `apps.*` module imports `telegram_bot.*` as a result of this plan.
- [ ] No `statement_timeout`, `lock_timeout` or new `DATABASES` key was added.
- [ ] No legacy in-source `EXT-` / `AUT-` / `SRH-` marker sweep was started by a phase-09
      block.
- [ ] Every citation that survived into code, docstrings, commit messages or docs is
      **cycle-scoped** (`09-API-nnn`, `09-VAL-nnn`). No bare `API-nnn` / `EXT-nnn` was
      introduced.

### 8.5 Project conventions

- [ ] English only — every comment, log message, docstring and doc line added.
- [ ] No `print()` anywhere in the diff.
- [ ] Every new fixed value is a `StrEnum` member or a module-level `Final` constant. No new
      `AdvisoryLockId` member was allocated.
- [ ] Pydantic v2 appears only at a boundary. BLOCK 8's result object, if option (b) was
      chosen, is a `NamedTuple` or small dataclass — **not** a Pydantic model.
- [ ] Every new module and function is small and single-purpose; composition over
      inheritance; the only new helpers are the two in `apps/core/utils/cache.py`.
- [ ] Every user-visible string is wrapped in `gettext` / `{% trans %}`, with non-empty
      `ru` and `bs`. **No block in this plan introduces one** — the gate is run to prove it,
      not because a string was expected.
- [ ] Docs in `docs/` are in sync: the ECB sentence, the five password-reset sentences, the
      `CFG-001` attribution, the API-surface section in
      `docs/01-spec/architecture-structure.md`, and the `price_normalizer.py` /
      `load_exchange_rates.py` docstrings.
- [ ] Every fix that a green test contradicted changed **the test** in the **same commit**,
      with the test named and the justification in the commit body. **Production code was
      never bent to keep a test green** — project rule 2, and the reason this plan slates
      four rewrites.
- [ ] Tests verify **logic and component interaction**, not implementation trivia: no
      assertion on a private name, a line number, a quoted log string, a column count, or the
      mere presence of a symbol. **No line number is used as a task target.**

### 8.6 Deliverables

- [ ] **23 commits** shipped across the 16 blocks (15 implementation + 1 decision/handoff that became
      implementation on 2026-10-03). Seven blocks had correction, test-only or doc follow-up
      commits — each in the same `"{type}({scope}): {description}"` repo style with a body naming
      the option chosen, the tests changed, and any cross-phase note. The count exceeds 16
      because BLOCKS 4, 6, 8, 11, 13, 14, 16 each produced one or more follow-ups.
- [ ] `apps/core/utils/cache.py` carries **one** documented cache-failure policy, two
      helpers, and no second contract.
- [ ] Seven request-path guards share **one** helper; the `add`/`incr` duplication is gone
      from all of them.
- [ ] Three Prometheus counters make "the translator is down" alertable.
- [ ] The `09-API-012` / `09-VAL-002` handoff is on the record with both owners named.
- [ ] **Q10's answer is on the record**, so the next agent knows whether the outbound
      gateway is a pending plan or a declined advisory.
- [ ] This plan's §0.2.1 correction table is **carried into the phase report**, so the next
      cycle does not re-derive C-1 … C-10 or send an Implementor to a symbol that does not
      exist.
