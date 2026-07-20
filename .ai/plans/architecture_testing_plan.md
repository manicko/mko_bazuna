# Mko Bazuna — Architecture Testing Plan

> **Status:** Approved
> **Scope:** Phase-1 architecture (two processes, one DB) of the Mko Bazuna classifieds board.
> **Audience:** Backend engineers, QA, reviewers.
> **Source of truth:** `docs/01-spec/*`, `docs/02-database/*`, `docs/03-packages/*`, validated against the actual implementation under `src/`.
> **Test runner:** `uv run pytest <path>` (pytest + pytest-django + pytest-asyncio[strict] + model-bakery). Typecheck `uv run basedpyright <path>`. Lint `uv run ruff check <path>`.

---

## 0. How to read this plan

Each section follows a fixed template:

- **Architecture concern** — what subsystem/layer/integration is under test.
- **Objective** — what correctness we prove.
- **Architecture layers / zones** — the spec "zones" (C1–C8, D1–D12, R1–R9) and code paths involved.
- **Test strategy** — unit / integration / contract / chaos / security, and which DB (real PostgreSQL required for any trigger/FTS/advisory-lock test).
- **Key scenarios** — concrete, implementable test cases with the exact invariant under test.
- **Risks / gaps** — real risks found by reading the code, with severity.
- **Acceptance** — definition of done.

**Cross-cutting test axioms (apply to every section):**
1. Every test that touches triggers, GIN indexes, advisory locks, or FTS **must** run against real PostgreSQL (CI uses `docker-compose.test.yml`). SQLite cannot emulate `to_tsvector`, plpgsql triggers, or `pg_advisory_xact_lock`.
2. Tests must never distort production code (rule: "production code is king"). If a test needs a private hook, add it to production-visible API, not a test-only shim.
3. Time-dependent sweeps are tested by **injecting fixed timestamps**, not `time.sleep()`.
4. Async bot code is tested with `pytest-asyncio` `asyncio_mode="strict"`; all ORM calls are already wrapped in `sync_to_async` per `docs/03-packages/packages-list.md`.

---

## Part 1 — Process Isolation & Shared-ORM Correctness

### 1.1 Architecture concern
The web (gunicorn **sync** WSGI) and bot (aiogram **async**) processes share one Django project and one PostgreSQL database. The bot calls `django.setup()` and uses the shared ORM; blocking ORM calls and Telegram photo downloads are wrapped in `sync_to_async` (`src/telegram_bot/handlers/*`, `src/telegram_bot/services/media.py`).

### 1.2 Objective
Prove that concurrent writes from the two processes do not corrupt shared state (ads, `LoginToken`, users, `AnalyticsEvent`) and that the sync↔async boundary is safe.

### 1.3 Layers / zones
- Web: `src/backend/apps/ads/views/*`, `src/backend/apps/users/views/*`.
- Bot: `src/telegram_bot/handlers/*`, `src/telegram_bot/services/*`.
- Boundary: `asgiref.sync.sync_to_async` wrapping every ORM call in bot handlers.
- Zones: C5 (async/sync boundary), C7 (per-process pool).

### 1.4 Test strategy
- **Integration (real PG):** simulate concurrent ad-creation from bot + web.
- **Contract:** assert every ORM entrypoint in `telegram_bot/` is `sync_to_async`-wrapped (static check + runtime).
- **Concurrency:** use `threading`/`asyncio` to fire overlapping writes.

### 1.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P1.1 | Bot creates ad via `Ad.DRAFT` ORM row while web publishes another ad | Both rows persist; no lost update; `Ad.objects.count()` == 2 |
| P1.2 | Two processes concurrently increment `AnalyticsEvent` for same user | Row count exact; no duplicate/under-count (PG serializes the INSERT) |
| P1.3 | `sync_to_async` wrapping audit: static scan of `telegram_bot/**` for raw `*.objects.` outside `sync_to_async` | Zero unwrapped ORM calls in bot package |
| P1.4 | Bot downloads + stores a photo (`media.py`) while web reads ad detail | No `OperationalError` from pool exhaustion; `CONN_MAX_AGE=0` honored |
| P1.5 | `select_for_update()` on `LoginToken` claim invoked from both processes | Exactly one claim succeeds; second returns `None` |

### 1.6 Risks / gaps (found in code)
- **HIGH:** `src/telegram_bot/handlers/contact.py::check_seller_available` runs a `SELECT` inside `sync_to_async` but the contact flow does **two** round-trips (availability check + analytics insert) without a single transaction — a seller could be soft-deleted between the two, creating a window where analytics records a contact to a now-`is_deleted` user. Test must prove the gap is acceptable or recommend a single `select_for_update`/atomic path.
- **MEDIUM:** No explicit test that the bot process uses its **own** psycopg3 pool (`CONN_MAX_AGE=0`) distinct from web. Recommend a settings contract test asserting `CONN_MAX_AGE` in both `config/settings/prod.py` and the bot entrypoint.

### 1.7 Acceptance
All P1.x pass on real PG; static sync_to_async audit clean.

---

## Part 2 — Migration Idempotency & Cold-Start Safety

### 2.1 Architecture concern
Migrations run **exactly once** before web and bot start (`docs/01-spec/architecture-structure.md`, Migration rule C5/D7). A session-scoped advisory lock (`AdvisoryLockId.MIGRATE = 100`) guards the migrate step, which runs **before** PgBouncer attaches (`src/backend/apps/core/utils/migrate_locked.py`).

### 2.2 Objective
Prove the migrate step is idempotent and that concurrent web+bot startup cannot trigger double migration.

### 2.3 Layers / zones
- `src/backend/apps/core/utils/migrate_locked.py`, `advisory_lock.py` (session lock path).
- `docker-compose.yml` `depends_on: migrate`, `entrypoint.sh`.
- Zones: C5, D7.

### 2.4 Test strategy
- **Unit:** `advisory_lock(session=True)` acquires/releases a session lock.
- **Integration (real PG):** run migrate inside the lock twice; assert `django_migrations` row count unchanged and exit 0 both times.
- **Chaos:** launch two migrate processes simultaneously; assert only one performs DDL (the other blocks then finds schema current).

### 2.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P2.1 | `migrate_locked.main()` executed twice sequentially | Second run is a no-op; exit code 0; no duplicate migration rows |
| P2.2 | Two concurrent `main()` (threaded) | Exactly one subprocess runs `migrate`; the other acquires lock after and short-circuits |
| P2.3 | Session lock released on normal exit | `pg_locks` shows no held advisory lock for id 100 after process exit |
| P2.4 | Migrate fails mid-way (forced error) then re-runs | Lock released; re-run resumes from last applied migration (no partial DDL applied twice) |
| P2.5 | `entrypoint.sh` ordering: web/bot `depends_on` migrate completed | Container does not start web/bot until migrate service exits 0 |

### 2.6 Risks / gaps
- **MEDIUM:** `migrate_locked.py` hardcodes `cwd="/app"` and the manage.py path `src/backend/manage.py`. If the image layout changes, migration silently runs wrong path. Recommend asserting the path exists at startup.
- **LOW:** The lock is **session-scoped** and safe only because migrate runs pre-PgBouncer. A regression that routes migrate through PgBouncer tx-mode would deadlock. Add a contract test asserting the migrate connection does not use the PgBouncer DSN.

### 2.7 Acceptance
P2.1–P2.5 pass; migrate path assertion present.

---

## Part 3 — Ad Lifecycle State Machine

### 3.1 Architecture concern
`AdStatus` state machine (`src/backend/apps/core/enums.py`, `src/backend/apps/ads/models.py`):
`DRAFT → ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED`;
`PUBLISHED → ARCHIVED → PUBLISHED` (reactivation); `PUBLISHED → ON_MODERATION` (text edit, hidden); any → `DELETED`.

### 3.2 Objective
Prove every valid transition is reachable, every invalid transition is rejected, and timer semantics (`published_at` reset on every PUBLISHED; `original_published_at` immutable) hold.

### 3.3 Layers / zones
- `Ad` model fields + transitions; `published_at`, `original_published_at` (`db-schema.md` zone C2/C3).
- Views: `ads/views/edit.py`, `delete.py`, `dashboard.py`.
- Zones: C2, C3.

### 3.4 Test strategy
- **Unit:** pure transition-table tests (no DB) of a `transition(from, to)` helper if present, or document that transitions are implicit in views and add explicit guards.
- **Integration (real PG):** exercise transitions through the actual view/service call paths.

### 3.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P3.1 | `DRAFT→ON_MODERATION→PUBLISHED` happy path | Status chain valid; ad buyer-visible only at PUBLISHED |
| P3.2 | `PUBLISHED→ON_MODERATION` on title/description edit | Ad immediately hidden; `status != PUBLISHED` until re-check passes |
| P3.3 | `PUBLISHED→ARCHIVED→PUBLISHED` reactivation | Reactivation re-runs text re-check; `published_at` updated on re-publish |
| P3.4 | `any→DELETED` soft delete | `deleted_at` set; ad excluded from all public listings |
| P3.5 | Invalid transition `REJECTED→PUBLISHED` attempted | Rejected (no direct path); only via admin re-create or allowed flow |
| P3.6 | `published_at` reset semantics | Every `→PUBLISHED` sets `published_at=now`; `original_published_at` set once and never changes |
| P3.7 | Mixed edit (text + price) | Follows the text rule (hidden + re-moderation), not instant publish |
| P3.8 | `original_published_at` immutability | Direct UPDATE of `original_published_at` is rejected/ignored by business logic |

### 3.6 Risks / gaps
- **HIGH:** Transitions are **not centralized** — they are spread across `auto_moderation.py`, `views/edit.py`, `views/delete.py`, and sweep commands. There is no single `Ad.transition_to()` guard, so an invalid transition could slip in via a new code path. Recommend a single guarded transition method and tests that enumerate the full allowed matrix.
- **MEDIUM:** `PUBLISHED→ON_MODERATION` for text edits must hide the ad immediately; verify the listing query filters `status=PUBLISHED` (uses `IX_ads_pub_listing` partial index). A regression to `status__in=[...]` would leak hidden ads.

### 3.7 Acceptance
Full transition matrix enumerated and enforced; timer resets verified.

---

## Part 4 — Advisory-Lock Sweep Guarantees

### 4.1 Architecture concern
Seven management commands run on schedules (`archive_sweep`, `delete_sweep`, `consent_hard_delete`, `sweep_drafts`, `cleanup_login_tokens`, `purge_failed_ads`, `purge_rejected_ads`). Each wraps its work in `advisory_lock(AdvisoryLockId.X)` — transaction-scoped (`pg_advisory_xact_lock`) so it is safe under PgBouncer transaction mode (`src/backend/apps/core/utils/advisory_lock.py`, `enums.py`).

### 4.2 Objective
Prove each sweep (a) selects only the correct retention window, (b) is idempotent, (c) cannot double-process under concurrent execution, and (d) honors `--dry-run`.

### 4.3 Layers / zones
- `core/management/commands/*`, `core/utils/advisory_lock.py`.
- Partial indexes `IX_ads_archive_sweep`, `IX_ads_delete_sweep`, `IX_ads_purge_failed`, `IX_ads_rejected_sweep`, `IX_users_erasure_sweep` (`db-indexes.md`).
- Zones: C4, D4, D12, R1.

### 4.4 Test strategy
- **Integration (real PG):** `pytest.mark.django_db`, inject fixed timestamps.
- **Concurrency:** launch two `call_command` invocations in parallel threads; assert exactly-once processing.
- **Baseline:** existing `core/tests/test_sweep_commands.py` already covers retention windows + dry-run + idempotency + lock IDs — **extend, do not rewrite**.

### 4.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P4.1 | `archive_sweep` window = PUBLISHED & `published_at < now-60d` | Correct ads archived; fresh untouched; `--dry-run` no mutation |
| P4.2 | `delete_sweep` window = ARCHIVED & `published_at < now-120d` | Old archived deleted; cascades `ad_images` |
| P4.3 | `consent_hard_delete` window = `consent_revoked_at < now-30d` | User hard-deleted; `analytics_events.user_id` & `moderator_action_log.user_id` SET NULL (history kept) |
| P4.4 | `sweep_drafts` window = DRAFT & `created_at < now-30m` | Old drafts deleted; PUBLISHED untouched |
| P4.5 | `purge_failed_ads` (7d) / `purge_rejected_ads` (90d) | Correct windows; mutually exclusive with other statuses |
| P4.6 | Concurrent same-command execution | Advisory lock serializes; no double archive/delete; final count deterministic |
| P4.7 | `cleanup_login_tokens` keeps recently-consumed (≤24h) tokens, deletes expired | Branch logic correct |
| P4.8 | Lock ID uniqueness | All 7 `AdvisoryLockId` values distinct; matches `advisory_lock` usage |

### 4.6 Risks / gaps
- **HIGH:** `consent_hard_delete` nulls `AnalyticsEvent.user_id`/`ModeratorActionLog.user_id` **before** deleting the user, but does **two separate `UPDATE`s then `DELETE`** outside a single explicit transaction — if the process crashes between the UPDATEs and DELETE, a user could be left with nulled history but not deleted, then re-processed. Wrap in `transaction.atomic`. Test must assert atomicity (inject failure between steps).
- **MEDIUM:** `archive_sweep`/`delete_sweep` use `timedelta(days=60)`/`120` while the spec says "2 months"/"4 months". 60/120 days ≠ calendar months. Confirm with product owner; if calendar months are required, switch to `relativedelta` and add a test on month-boundary dates.
- **LOW:** No test that the lock is **transaction-scoped** (released on commit). Add a test asserting the lock is free after the command returns.

### 4.7 Acceptance
P4.1–P4.8 pass; `consent_hard_delete` wrapped in `transaction.atomic` with a crash-injection test.

---

## Part 5 — PostgreSQL Trigger Sync & FTS Correctness

### 5.1 Architecture concern
`search_vector` (TSVECTOR) + `category_name` (denormalized) are maintained by plpgsql triggers (`src/backend/apps/ads/migrations/0002_search_vector_triggers.py`), because `category_name` lives in another table. GIN index `IX_ads_search_gin`; weights A(title)/B(description)/C(category_name); russian config.

### 5.2 Objective
Prove triggers keep `search_vector`/`category_name` consistent on INSERT/UPDATE and on category rename, and that FTS returns correct, ranked, PUBLISHED-only results.

### 5.3 Layers / zones
- Triggers `ads_search_vector_fn`, `categories_name_propagate`.
- `search/views/search.py`, `search/services/query_translator.py`.
- Zones: D1, D5, D6, D9.

### 5.4 Test strategy
- **Integration (real PG):** raw SQL + ORM to verify trigger behavior; FTS via Django `SearchQuery`/`SearchRank`.
- **Contract:** assert GIN index exists and is used (`EXPLAIN`).

### 5.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P5.1 | INSERT ad → trigger fills `search_vector` & `category_name` | Both non-null and match title/desc/category |
| P5.2 | UPDATE title → `search_vector` recomputed | Old term not searchable; new term is |
| P5.3 | Rename category → `categories_name_propagate` updates all its ads' `category_name`+`search_vector` | Propagation complete; backfill idempotent |
| P5.4 | FTS by category word (e.g. "Electronics") | Ad returned via weight C even if title/desc lack the word |
| P5.5 | FTS only over PUBLISHED ads | Non-PUBLISHED ads excluded from results |
| P5.6 | Russian morphology: search "телефоны" matches "телефон" | `to_tsvector('russian')` stemming works |
| P5.7 | `EXPLAIN` on search query uses `IX_ads_search_gin` | No sequential scan on `ads` |
| P5.8 | Bosnian query translated → Russian before FTS | See Part 7; here assert the search layer receives Russian text |
| P5.9 | Empty result → friendly state (US-B2) | View returns empty list, not 500 |

### 5.6 Risks / gaps
- **HIGH:** `categories_name_propagate` does `UPDATE ads SET category_id = ads.category_id WHERE category_id = NEW.id`. This is O(n_ads) per rename and **re-fires trigger #1** for every row — under a large category rename with many ads this is a long-held write lock. Test must measure lock duration at scale (≥10k ads) and flag if it exceeds the 2s response SLO. Consider batching.
- **MEDIUM:** `search_vector` is `null=True`. A row inserted with a trigger failure could have NULL `search_vector` and silently vanish from search. Add a CHECK / not-null enforcement test and a backfill verification test (mirror `core/migrations/0001_verify_lifecycle_indexes.py`).

### 5.7 Acceptance
P5.1–P5.9 pass on real PG; rename-lock benchmark within SLO; search uses GIN.

---

## Part 6 — Photo Storage Anonymity & Integrity

### 6.1 Architecture concern
Photos: 1–5 **Telegram-compressed JPEG only**, stored as `FileSystemStorage` `MEDIA_ROOT` behind nginx (`src/telegram_bot/services/media.py`). Storage key = `ad_id`-scoped + UUID v4, **no PII** (`src/backend/apps/ads/models.py::AdImage.generate_storage_key`, `db-schema.md` zone R6/R8).

### 6.2 Objective
Prove only valid JPEGs are accepted, count limits are enforced, and storage keys never leak user/telegram identity.

### 6.3 Layers / zones
- `media.py::validate_photo`, `validate_jpeg_bytes`, `generate_storage_key`.
- nginx `/media/` hardening (`docker/nginx/nginx.conf` R8).
- Zones: E, R6, R8.

### 6.4 Test strategy
- **Unit:** `validate_photo` with crafted byte blobs (magic bytes, size, dimensions).
- **Security:** assert storage key format; assert nginx config blocks script execution and whitelists `image/jpeg`.

### 6.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P6.1 | Valid JPEG ≤2MB, ≤2560px accepted | `validate_photo` returns `(True, None)` |
| P6.2 | PNG / GIF / document rejected | `(False, msg)`; bot blocks `message.document` |
| P6.3 | JPEG with malformed header rejected | Magic-byte check catches it |
| P6.4 | >5 photos rejected at creation | Bot enforces `max_images`; auto-moderation enforces too |
| P6.5 | 0 photos rejected | `min_images=1` enforced before publish |
| P6.6 | Storage key = UUID v4 + `.jpg`, no `telegram_id`/`user_id` | Regex `^[0-9a-f-]{36}\.jpg$`; key contains only ad scope |
| P6.7 | nginx `/media/` blocks `*.php/*.py` | Returns 403 for script-like paths |
| P6.8 | nginx serves only `image/jpeg`, `Content-Disposition: inline`, `nosniff` | Response headers correct |

### 6.6 Risks / gaps
- **HIGH:** `validate_photo` checks `len(photo_bytes) > 2*1024*1024` **and** PIL dimensions, but Telegram "compressed" photos can still be maliciously crafted JPEGs that pass magic bytes yet exploit decoders. Recommend defense-in-depth: re-encode via Pillow on store (currently deferred per decision E — flagged as future risk).
- **MEDIUM:** `generate_storage_key()` returns `"{uuid4()}.jpg"` — the model field `image` is `max_length=64`, fine. But the key is **not** prefixed with `ad_id` in storage (only logically related via FK). If two ads generate the same UUID v4 (probabilistically ~0), collision overwrites. Acceptable; note for audit.
- **LOW:** nginx `alias /media_volume/;` with `location /media/` — missing trailing-slash normalization could expose paths. Verify with a request to `//media//x`.

### 6.7 Acceptance
P6.1–P6.8 pass; storage-key regex enforced by test.

---

## Part 7 — Query Translation Pipeline Resilience

### 7.1 Architecture concern
Bosnian→Russian query translation via `deep-translator` (`src/backend/apps/search/services/query_translator.py`). Spec mandates **hard timeout ~500ms + fallback to original query** (`docs/03-packages/packages-list.md` residual risk: HIGH).

### 7.2 Objective
Prove the pipeline never blocks the search SLO (<2s), caches correctly, and always falls back to the original query on failure.

### 7.3 Layers / zones
- `query_translator.translate_query_bs_to_ru`, `translate_cached` (`lru_cache`), `invalidate_translation_cache`.
- Zones: G, D5.

### 7.4 Test strategy
- **Unit (mock network):** patch `GoogleTranslator.translate` to raise/timeout; assert fallback.
- **Contract:** assert a real hard timeout exists (currently the code has **no actual timeout** — see gap).

### 7.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P7.1 | Translation succeeds | Returns Russian string; logged |
| P7.2 | Translator raises `RequestException` | Returns original (Bosnian) query; no 500 |
| P7.3 | Translator times out (>500ms) | Returns original query within SLO |
| P7.4 | Identical query cached (`lru_cache` maxsize=128) | Second call does not hit network |
| P7.5 | `invalidate_translation_cache()` clears cache | Next call re-translates |
| P7.6 | Empty/whitespace query | Returned unchanged, no network call |

### 7.6 Risks / gaps
- **CRITICAL:** The current `query_translator.py` has **no actual 500ms timeout**. `GoogleTranslator` from `deep-translator` does not honor a thread-level timeout by default; `lru_cache` + synchronous call can block the gunicorn worker indefinitely on a slow network. The doc's "hard timeout" requirement is **not implemented**. Test P7.3 must fail today → this is a mandatory finding: wrap the call in `asyncio.wait_for` / `concurrent.futures` with `timeout=0.5`, or use a transport with a socket timeout.
- **MEDIUM:** Translation runs **synchronously inside the request** (web is sync WSGI). Under burst, N workers each block on Google. Recommend moving translation off the request critical path or using a process-wide async pool. Test should measure p95 search latency with translation enabled vs disabled.

### 7.7 Acceptance
P7.1–P7.6 pass **after** a real timeout is implemented; search p95 < 2s with translation.

---

## Part 8 — Telegram Login Deep-Link Atomicity

### 8.1 Architecture concern
Login via QR deep-link `login_<32-char-token>`. `LoginToken` two-phase atomic claim: bot writes `telegram_id` (phase 1), web consumes `consumed_at` (phase 2). Raw token hashed SHA-256; constant-time compare (`hmac.compare_digest`) (`src/telegram_bot/handlers/login.py`, `docs/02-database/db-schema.md` zone C1).

### 8.2 Objective
Prove the token is claimed exactly once, expired/invalid tokens are rejected, and timing attacks are prevented.

### 8.3 Layers / zones
- `login.py::claim_login_token`, `LOGIN_PATTERN` (`^login_([A-Za-z0-9_-]{32})$`).
- `users/models.py::LoginToken`.
- Zones: C1, H.

### 8.4 Test strategy
- **Async unit (mock bot):** `@pytest.mark.asyncio` tests on `claim_login_token`.
- **Security:** assert `hmac.compare_digest` usage; assert token hash stored, raw never persisted.
- **Concurrency:** two simultaneous claims.

### 8.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P8.1 | Valid unused token → bot claims (sets `telegram_id`) | `updated == 1`; token now claimed |
| P8.2 | Already-claimed token → second claim returns `None` | Exactly-once; no double login |
| P8.3 | Expired token (`expires_at < now`) | Claim returns `None`; clear retry message |
| P8.4 | Malformed token (not 32-char URL-safe) | `LOGIN_PATTERN` rejects; no DB hit |
| P8.5 | Raw token never stored | `LoginToken.token_hash` is SHA-256; assert no raw column |
| P8.6 | Constant-time compare | `hmac.compare_digest` used for hash compare (static + runtime) |
| P8.7 | Concurrent claims (2 threads) on same token | Exactly one succeeds |
| P8.8 | Web consumes token → `consumed_at` set | Login completes; session cookie SECURE+HTTPONLY+SAMESITE=Lax |

### 8.6 Risks / gaps
- **MEDIUM:** The bot claim uses a plain `UPDATE ... WHERE telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now()`. This is atomic in PG, good. But the **web consumption** step is not visible in the reviewed code path (bot handler only claims). Verify the web side (`users/views` login completion) performs the second-phase `UPDATE consumed_at` under the same conditions. Add a contract test for the web side.
- **LOW:** `token_hash` is `unique=True` + `db_index=True` — good. But no test asserts the 32-char token is URL-safe (`A-Za-z0-9_-`) end-to-end from generation (site) to claim (bot). Add a generation-side test.

### 8.7 Acceptance
P8.1–P8.8 pass; web-phase claim contract test present.

---

## Part 9 — Anonymous Contact Deep-Link Security

### 9.1 Architecture concern
Contact via `contact_<ad_id>` deep-link. Bot relays without revealing seller PII. Render conditions (zone R2): ad `PUBLISHED` AND seller `telegram_id` NOT NULL AND NOT `is_deleted` AND NOT `is_banned` AND `consent_revoked_at` IS NULL (`src/backend/apps/core/services/contact.py`, `src/telegram_bot/handlers/contact.py`).

### 9.2 Objective
Prove the contact button renders only under all R2 conditions, and the bot never leaks seller identity.

### 9.3 Layers / zones
- `core/services/contact.py::can_contact_seller`, `get_seller_for_contact`.
- `telegram_bot/handlers/contact.py::check_seller_available`.
- Zones: C, R2.

### 9.4 Test strategy
- **Unit (mock):** `can_contact_seller` with all 5-condition permutations.
- **Integration (real PG):** `get_seller_for_contact` / bot handler with persisted users+ads.
- **Security:** assert no `telegram_id`/`username` appears in buyer-facing template/message.

### 9.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P9.1 | All 5 R2 conditions true | `can_contact_seller` → True; button renders |
| P9.2 | Any one condition false (6 permutations) | → False; button hidden |
| P9.3 | Ad not PUBLISHED (e.g. ARCHIVED) | Bot: "объявление больше недоступно" |
| P9.4 | Seller `is_deleted` / `is_banned` / consent revoked | Bot: "продавец больше недоступен для связи" |
| P9.5 | Seller `telegram_id` NULL | No contact; no PII leak |
| P9.6 | Buyer display name anonymized | Only first/last name used; `telegram_id`/`username` never sent to buyer |
| P9.7 | `record_contact_initiated` analytics | `CONTACT_INITIATED` event created; `user_id` nullable |
| P9.8 | Template `contact_tags` renders button only when `can_contact_seller` | HTML contains button iff True |

### 9.6 Risks / gaps
- **HIGH (test gap):** Existing `core/tests/test_contact.py` does **not** import or call the real `can_contact_seller`. It re-implements the logic inline with dicts and asserts Python `all()`. This gives **zero coverage** of the actual function and would not catch a regression in `contact.py`. Mandatory finding: replace with real calls to `can_contact_seller(ad)` using `model_bakery`/`User`+`Ad` fixtures.
- **MEDIUM:** `get_seller_for_contact` (web) and `check_seller_available` (bot) implement the **same R2 logic twice**. Divergence risk. Recommend a single shared predicate and tests asserting both return identical results for the same inputs.

### 9.7 Acceptance
P9.1–P9.8 pass against the **real** `can_contact_seller`; duplicated-predicate consolidated or covered by parity test.

---

## Part 10 — Moderation Criteria Singleton & Auto-Check

### 10.1 Architecture concern
`ModerationCriteria` singleton (exactly one row, `get_singleton()` pk=1), edited at runtime by admin (`src/backend/apps/moderation/models.py`, `services/auto_moderation.py`, `docs/02-database/db-schema.md` zone D3/D4, decision O4). Auto-check is the **only** gate before PUBLISHED (decision A). Seller sees **generic** errors only (reason never disclosed).

### 10.2 Objective
Prove singleton enforcement, runtime edit propagation (cache invalidation), correct validation rules, and seller-safe error messages.

### 10.3 Layers / zones
- `ModerationCriteria.get_singleton`, `auto_moderation.auto_moderate`, `auto_moderation.check`.
- `core/utils/cache.py` (5-min TTL), signal invalidation.
- Zones: A, D3, D4, O4.

### 10.4 Test strategy
- **Unit:** `auto_moderate`/`check` with crafted `Ad` + criteria.
- **Integration:** singleton creation; cache invalidation on admin edit.

### 10.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P10.1 | `get_singleton()` called twice | Same row (pk=1); exactly one row in table |
| P10.2 | Title length out of bounds | Fail → `ON_MODERATION_FAILED` + `moderation_failed_at` |
| P10.3 | Description length out of bounds | Fail |
| P10.4 | `price_required` & price None | Fail |
| P10.5 | Image count < `min_images` or > `max_images` | Fail |
| P10.6 | Banned word (case-insensitive) in title/desc | Fail |
| P10.7 | `max_ads_per_user` exceeded | Fail (counts PUBLISHED+ON_MODERATION+ON_MODERATION_FAILED) |
| P10.8 | Duplicate title (`difflib.ratio*100 >= threshold`) | Fail |
| P10.9 | All pass → PUBLISHED + `AnalyticsEvent.AD_PUBLISHED` | Status + event created |
| P10.10 | `check()` returns generic message on fail | No specific reason leaked to seller |
| P10.11 | Admin edits criteria → cache invalidated → next submit uses new values | `invalidate_criteria_cache` called by signal; `get_cached_criteria` refreshes |
| P10.12 | Criteria has no price-range fields | `ModerationCriteria` has no `min_price`/`max_price` (schema contract) |

### 10.6 Risks / gaps
- **MEDIUM:** `auto_moderate` and `check` both call `_fail_moderation` which **sets status to `ON_MODERATION_FAILED`** even in the pre-submit `check()` path. If `check()` is used for live preview before submit, it would prematurely fail the ad. Confirm `check()` is only used post-submit, or split the "validate-only" path. Add a test asserting `check()` does not mutate status when used for preview.
- **MEDIUM:** Cache TTL 5 min means an admin criteria change can take up to 5 min to affect new ads **if** the signal invalidation is missed (e.g. direct SQL edit). Test P10.11 must cover the signal path specifically.
- **LOW:** `_is_duplicate_title` compares only within the same user — cross-user spam not caught. Documented as acceptable for MVP; note for future.

### 10.7 Acceptance
P10.1–P10.12 pass; `check()` mutation semantics clarified by test.

---

## Part 11 — Consent State Machine & PII Erasure

### 11.1 Architecture concern
Two distinct consent states (decision F/K, zone R3): **DECLINE** (browse-only, sets `ads_auto_publish=False`, no erasure) ≠ **WITHDRAW** (sets `consent_revoked_at` + `is_deleted`, nulls PII immediately, 30-day hard-delete via sweep). Users maximally anonymous (`src/backend/apps/users/services/deletion.py`, `account_state.py`, `docs/02-database/db-schema.md` zone R1/R3/R4/R5/R9).

### 11.2 Objective
Prove DECLINE≠WITHDRAW, immediate PII nulling on withdraw, soft-delete cascade, and the 30-day hard-delete preserves audit history.

### 11.3 Layers / zones
- `deletion.decline_consent`, `withdraw_consent`, `soft_delete_user_ads`, `give_consent`.
- `account_state.can_publish_ad`, `can_login`, `get_account_state`.
- `consent_hard_delete` sweep (Part 4).
- Zones: F, K, O1, O2, O3, R1, R3, R4, R5, R9.

### 11.4 Test strategy
- **Unit/Integration (real PG):** exercise the four consent functions; assert field transitions.
- **Contract:** GDPR erasure completeness — every PII column nulled; foreign keys SET NULL.

### 11.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P11.1 | `decline_consent` | `ads_auto_publish=False`; `consent_revoked_at` NULL; PII retained; ads visible |
| P11.2 | `withdraw_consent` | `consent_revoked_at`+`is_deleted`+`deleted_at` set; `telegram_id`/`username` NULL immediately |
| P11.3 | `withdraw_consent` cascades ads | All user ads → `DELETED` + `deleted_at`; `ad_images` cascade-deleted |
| P11.4 | `give_consent` | `consent_given_at` set; covers bot too (no separate bot confirm) |
| P11.5 | `can_publish_ad` logic | False if banned/deleted/`ads_auto_publish=False`; True otherwise |
| P11.6 | `can_login` logic | False if banned; deleted users (telegram_id NULL) cannot login anyway |
| P11.7 | Re-registration blocked within 30 days | New user with same telegram_id impossible (NULLed); allowed after hard-delete |
| P11.8 | `consent_hard_delete` (30d) preserves audit | `ModeratorActionLog.reason` + `action_type` + timestamps retained; `user_id` SET NULL |
| P11.9 | `consent_hard_delete` keeps aggregates | `AnalyticsEvent` rows kept, `user_id` SET NULL |
| P11.10 | DECLINE ≠ WITHDRAW (banner behavior) | DECLINE keeps contact working; WITHDRAW hides contact (R2) |

### 11.6 Risks / gaps
- **HIGH:** `withdraw_consent` nulls PII in the **user** row and soft-deletes ads, but the **hard-delete sweep** (Part 4 P4.3) is the only thing that removes the user row. Between withdraw and day 30, the user row still exists with NULL `telegram_id`. The `LoginToken` for that user is **not** invalidated on withdraw — a still-valid consumed token could theoretically re-link. Recommend invalidating active login tokens on withdraw. Add a test.
- **MEDIUM:** `soft_delete_user_ads` uses `.update(status=DELETED)` — bulk, no per-ad `ModeratorActionLog`. That's acceptable (withdraw is not moderation) but ensure analytics `AD_PUBLISHED` events for those ads are **not** deleted (they reference `user_id` which gets nulled later). Verify with a test.
- **LOW:** `consent_revoked_at` is the sole trigger for hard-delete; if `withdraw_consent` is later extended to also set `hard_delete_at`, the sweep must use `hard_delete_at`, not recompute. Document the single-source rule.

### 11.7 Acceptance
P11.1–P11.10 pass; login-token invalidation on withdraw added and tested.

---

## Part 12 — Non-Functional, Operational & Security Hardening

### 12.1 Architecture concern
Cross-cutting NFRs: response SLO (<2s), TLS/headers (nginx R8), rate limiting, settings hardening (`USE_X_FORWARDED_HOST`, `SECURE_SSL_REDIRECT`), Docker topology, and CI quality gates.

### 12.2 Objective
Prove the deployment meets its security/performance contracts and that CI gates catch regressions.

### 12.3 Layers / zones
- `docker/nginx/nginx.conf`, `docker-compose*.yml`, `config/settings/*`, `.github/workflows/ci.yml`.
- Zones: R8, C5, C7.

### 12.4 Test strategy
- **Config/contract tests:** assert settings values; parse nginx config for required directives.
- **Performance:** seeded DB (≥100k ads) search p95 < 2s.
- **CI:** assert ruff/basedpyright/pytest gates present and non-skippable.

### 12.5 Key scenarios
| ID | Scenario | Invariant |
|----|----------|-----------|
| P12.1 | nginx security headers on all responses | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, CSP present |
| P12.2 | Rate limits active | `/login/` ≤10r/s burst 20; `/search/` ≤20r/s burst 40 |
| P12.3 | TLS redirect | HTTP → 301 HTTPS; `SECURE_SSL_REDIRECT=True` |
| P12.4 | Web not exposed publicly | `docker-compose.yml` web port not published; only nginx publishes 443 |
| P12.5 | Search p95 < 2s at 100k ads | Performance benchmark with GIN index |
| P12.6 | Settings contract | `USE_X_FORWARDED_HOST`, `SECURE_PROXY_SSL_HEADER` set in prod |
| P12.7 | `StrEnum` discipline | Static scan: no bare string literals for status/source/event/action enums |
| P12.8 | CI gates | `ruff`, `basedpyright`, `pytest` all run and fail build on error |
| P12.9 | `print()` absence | Static scan: no `print(` in `src/` (use `logging`) |
| P12.10 | PgBouncer tx-mode settings | `CONN_MAX_AGE=0` + `OPTIONS={"prepare_threshold": None}` when PgBouncer enabled |

### 12.6 Risks / gaps
- **MEDIUM:** No automated performance test exists. The <2s SLO is asserted only by spec. Recommend a seeded-benchmark CI job (or local gate) for search/listing at scale.
- **MEDIUM:** `docker-compose.yml` web service — verify `port 8000 NOT published` is actually the case (spec says so). Add a config test parsing the compose file.
- **LOW:** `nginx.conf` listens on 80 and 443 in the **same** `server_name _` block set; ensure the staging/test compose does not accidentally disable TLS.

### 12.7 Acceptance
P12.1–P12.10 verified; performance benchmark job established.

---

## Appendix A — Coverage Matrix (existing tests → plan)

| Existing test file | Covers | Gap vs plan |
|--------------------|--------|-------------|
| `core/tests/test_sweep_commands.py` | Part 4 (P4.1–P4.8) — strong | Missing crash-injection atomicity (P4.8 risk) |
| `core/tests/test_contact.py` | Part 9 intent | **Does NOT call real `can_contact_seller`** — must be rewritten (P9.6) |
| `moderation/tests/test_auto_moderation.py` | Part 10 (partial) | Verify covers P10.11 cache invalidation |
| `ads/tests/test_search_triggers.py` | Part 5 (triggers) | Verify covers P5.3 rename propagation + P5.7 EXPLAIN |

## Appendix B — Mandatory Findings (block approval until fixed)

1. **[P7 — CRITICAL]** `query_translator.py` has no real 500ms timeout; search can block indefinitely. Implement hard timeout.
2. **[P9 — HIGH]** `test_contact.py` does not test the real `can_contact_seller`; rewrite to use real function.
3. **[P3 — HIGH]** Ad transitions not centralized; add a single guarded `transition_to()` to prevent invalid transitions.
4. **[P4 — HIGH]** `consent_hard_delete` not wrapped in `transaction.atomic`; add crash-injection test.
5. **[P11 — HIGH]** Login tokens not invalidated on consent withdrawal; add invalidation + test.

## Appendix C — Test Infrastructure Requirements

### C.1 Test layout (convention — DO NOT relocate per-app tests)
Tests follow **Django's per-app convention**: `src/backend/apps/<app>/tests/` (verified: `core/tests/`, `ads/tests/`, `moderation/tests/`). This is correct and intentional — keep it.
- `pyproject.toml` already discovers them: `python_files = ["tests.py","test_*.py"]`, `addopts = ["--import-mode=importlib", ...]`. Run `uv run pytest` from repo root.
- **Do NOT move per-app tests to a top-level `tests/` folder** — it fights the `apps.*` package layout and gains nothing.
- A **separate** repo-root `tests/` MAY be added later **only** for cross-app integration/E2E scenarios (e.g. login→publish→search spanning bot+web+DB). Existing per-app suites stay put.

### C.2 Runtime & tooling
- Real PostgreSQL 18 in CI via `docker-compose.test.yml` (SQLite insufficient for Parts 4, 5).
- `pytest-asyncio` `asyncio_mode="strict"` for bot handler tests (Parts 1, 8, 9).
- `model_bakery` for fixtures; `freezegun` or injected `timezone.now` for time-based tests (Parts 3, 4, 11).
- Static scans (ruff custom rule or a small pytest) for Parts 1.3, 12.7, 12.9.
- Seeded performance DB (≥100k ads) for Part 12.5.
