# Research — end-to-end Telegram deep-link login flow integration (T005)

**Source task:** `task_005_research_login_flow` (research, `type: research`)
**Feeds:** `task_025_token_issuance` (AUT-001/EXT-001), `task_026_web_consumption` (AUT-002/AUT-006),
`task_027_web_session_poll` (AUT-003), `task_028_claim_toctou_fix` (EXT-002),
`task_029_claim_docstring_fix` (AUT-004)
**Verdict:** **GO WITH CHANGES** — the four-track contract below is sound and decoupled; two
required adjustments must be folded into the implementation tasks before coding (token length
vs. bot regex, and the cross-process user-creation race). See §7.

---

## 1. Current state (what exists vs. what is missing)

| Component | Status | Location |
|-----------|--------|----------|
| `LoginToken` model (two-phase: `telegram_id` then `consumed_at`) | Exists | `apps/users/models.py` |
| Raw token hashing (`sha256` hexdigest) | Exists (bot only) | `telegram_bot/handlers/login.py:66` |
| **Bot claim (phase 1)** — `UPDATE telegram_id WHERE telegram_id IS NULL` | Exists | `telegram_bot/handlers/login.py:69-124` |
| Bot `get_or_create_user` (writes profile fields) | Exists | `telegram_bot/handlers/login.py:129-157` |
| **Web issuance** — mint token + render deep-link | **MISSING** | — |
| **Web consumption (phase 2)** — `UPDATE consumed_at` | **MISSING** | — |
| **Web session** — `auth.login` + `cycle_key` | **MISSING** | — |
| `can_login()` ban gate | Exists but **never invoked** | `apps/users/services/account_state.py:80` |
| nginx `/login/` rate-limit zone | Exists, **guards a non-existent route** | `docker/nginx/nginx.conf:79-86` |
| `cleanup_login_tokens` consumed branch | Keys on `created_at` (bug) | `cleanup_login_tokens.py:48` |

Root cause is confirmed: the web side of the dual-process contract (web issues → bot claims →
web consumes) is entirely unimplemented. The bot claim already works in isolation, which is why
the flow "looks" complete but is end-to-end broken (the bot always answers *"invalid, expired,
or already used"* because no token is ever minted).

---

## 2. Integrated contract (the design)

Three tracks, one shared `login_tokens` table, zero bot→web callbacks:

### Phase 0 — Issuance (Web, `POST /login/issue/`)

```
raw_token  = secrets.token_urlsafe(24)          # 32 URL-safe chars, ~192 bits
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()   # 64 hex chars
LoginToken.objects.create(token_hash=token_hash, expires_at=now()+timedelta(minutes=5))
# telegram_id NULL, consumed_at NULL
deep_link  = f"https://t.me/{settings.BOT_USERNAME}?start=login_{raw_token}"
render(page, deep_link=deep_link, poll_token=raw_token)   # page polls /login/status/
```

- Raw token is **never stored** — only `token_hash`.
- Use **`POST`** to mint (CSRF-protected) so a page refresh does not exhaust tokens; `GET`
  shows the "Login via Telegram" button. (Mint-on-GET is acceptable but noisier.)
- `settings.BOT_USERNAME` is already exposed to templates via context processor
  (`templates/ads/detail.html:77`), so the view only needs `from django.conf import settings`.

### Phase 1 — Claim (Bot, `/start login_<token>`)

Already implemented. Hardening required by **T028**: replace the
`UPDATE` + separate `GET` with a single atomic `update(..., returning=True)` inside
`transaction.atomic()` so the claimed row is returned without a second read. The claim
predicate `telegram_id__isnull=True` already makes the *claim itself* concurrency-safe (see §4).
The bot then `get_or_create_user(...)` and replies. **This track is unchanged in behavior.**

### Phase 2 — Status-poll consumption + session (Web, `GET /login/status/?token=<raw>`)

```
token_hash = sha256(raw_token.encode()).hexdigest()
with transaction.atomic():
    claimed = LoginToken.objects.filter(
        token_hash=token_hash,
        telegram_id__isnull=False,   # bot already claimed
        consumed_at__isnull=True,    # not yet consumed (replay guard)
        expires_at__gt=now(),
    ).update(consumed_at=now(), returning=True)   # list[dict] (Django >=5.0)
if not claimed:
    # already consumed -> user already logged in this session
    if LoginToken.objects.filter(token_hash=token_hash, telegram_id__isnull=False,
                                 consumed_at__isnull=False).exists():
        return HttpResponse(status=200)          # already done, no re-auth
    return HttpResponse(status=410)              # expired / never claimed / invalid
row = claimed[0]
user = User.objects.get(telegram_id=row["telegram_id"])
if not can_login(user):                            # AUT-005 gate, finally wired
    return HttpResponse(status=403)
auth.login(request, user)
request.session.cycle_key()                        # defeat session fixation
return JsonResponse({"ok": True}, status=200)
```

**Response codes (per AUT-003):**
- `200` — claimed just now, session cookie set (or already logged in).
- `204` — pending: token valid, bot has **not** claimed yet (client keeps polling).
- `410` — expired / invalid / never issued.
- `403` — claimed but `can_login()` is `False` (banned).

The single `UPDATE ... WHERE consumed_at IS NULL` guarantees `consumed_at` is set
**exactly once** (consumed-once / replay protection). The `returning=True` read happens
inside the same atomic statement, so there is no re-read race.

---

## 3. Cross-process coupling analysis

Decoupling is achieved by the **status-poll pull** pattern (web pulls; bot never calls web).
Coupling surfaces only at the **shared contract**:

1. **Shared DB** — both processes read/write `login_tokens`. Migrations run once before both
   start (per architecture), so the schema is always consistent.
2. **Shared hashing** — issuance (web) and claim (bot) MUST use the identical
   `sha256(raw.encode()).hexdigest()`. Today only the bot has it. **Recommend a single
   source of truth** — e.g. `apps/users/services/tokens.py` exporting
   `hash_login_token(raw: str) -> str` (and optionally `issue_login_token()`), imported by
   both `telegram_bot/handlers/login.py` and the web views. This removes silent-drift risk.
3. **Shared token format** — see §7 conflict #1 (length must match the bot regex).
4. **Shared `expires_at` semantics** — both sides compare against `now()`; no drift risk as
   long as both use `django.utils.timezone.now()`.

No new configuration coupling is introduced (no web base-URL, no bot outbound HTTP). The bot
already imports `apps.users.models`, so importing a users-service helper is in-pattern.

---

## 4. Atomicity verdicts (honest findings for implementers)

- **Bot claim (T028):** The existing `UPDATE ... WHERE telegram_id__isnull=True` predicate is
  **already atomic** for the *claim* — a second concurrent claimant matches 0 rows and returns
  `None`. The TOCTOU risk EXT-002 describes is between the `UPDATE` and the *subsequent `GET`*
  (a re-read, not a double-claim). T028's `update(..., returning=True)` is therefore a
  **hardening/simplification** (removes the redundant `GET` and returns the row in one
  statement), **not** a fix of a live double-claim. Implement it as planned; just document it
  accurately. (T029 fixes the now-misleading "constant-time comparison" docstring — GO.)
- **Web consumption (T026/T027):** This is greenfield, so the single atomic `UPDATE ... WHERE
  consumed_at IS NULL` in §2 is the correct design and is required to avoid a real
  double-login under concurrent polls. GO.

---

## 5. nginx route wiring

Current config (`docker/nginx/nginx.conf:24,79-86`):

```
limit_req_zone $binary_remote_addr zone=login_limit:10m rate=10r/s;
...
location /login/ {                       # PREFIX match
    limit_req zone=login_limit burst=20 nodelay;
    proxy_pass http://web:8000;         # no trailing slash -> full path forwarded
}
```

- `location /login/` is a **prefix** match, so both `/login/issue/` and `/login/status/`
  fall under it automatically. **No new `location` block is required** — placing the new
  routes under the `/login/` prefix is sufficient, satisfying T025's "point the dead zone at
  the real route."
- `proxy_pass http://web:8000` (no URI) forwards the original path, so `/login/status/` hits
  `web:8000/login/status/`. Correct.
- Rate budget `10r/s burst=20` is generous for a single browser polling every 1–2 s; no change
  needed. (If polling is aggressive, raise the burst — non-blocking.)
- **Action:** ensure the new URLs are registered as `/login/issue/` and `/login/status/` (i.e.
  under the `""` include in `config/urls.py`, namespaced consistently). The existing
  `consent/accept/` + `consent/decline/` routes live at the root (not under `/login/`) and are
  **correctly NOT rate-limited** — leave them.

---

## 6. Downstream consumers map

Once the web session is established (`auth.login` + `cycle_key`), these become reachable /
affected:

| Consumer | Type | Effect of login flow |
|----------|------|----------------------|
| `consent_accept` / `consent_decline` | `@login_required` view | Now reachable post-login; sets `consent_given_at` / `ads_auto_publish=False`. |
| `ads:dashboard` (`dashboard`) | `@login_required` view | Seller dashboard; primary post-login destination (`LOGIN_REDIRECT_URL="/"` currently — consider redirecting to `ads:dashboard`). |
| `ads` edit / archive / reactivate / delete | `@login_required` views | Seller actions unlocked. |
| `is_consent_given(request)` | Used by `listings`/`dashboard` templates | After auth, banner logic keys off `consent_given_at` / `ads_auto_publish`. |
| `telegram_bot` `/post` etc. | Bot flows | Depend on a `User` with `telegram_id`; created by bot phase 1. |
| `cleanup_login_tokens` | Mgmt command | Consumed branch becomes live **only after** T026 sets `consumed_at`; T026 must fix the `created_at__lt` → `consumed_at__lt` bug. |
| `withdraw_consent` | Service | Deletes `LoginToken` rows by `telegram_id` — correct post-login (token invalidated on withdrawal). |
| `can_login(user)` | Service (was dead) | **Must be wired into phase 2** (§2) to refuse banned users — closes AUT-005. |

No consumer required schema changes; all depend only on the session/contract being established.

---

## 7. GO-WITH-CHANGES — required adjustments before coding

These two items **must** be folded into the implementation tasks; they are not optional and are
the difference between "compiles" and "works end-to-end."

### Change #1 — Token length MUST match the bot regex (blocks T025 if ignored)
The bot regex is `login_([A-Za-z0-9_-]{32})` (`telegram_bot/handlers/login.py:24`) —
**exactly 32 chars**. `secrets.token_urlsafe(32)` yields **43 chars** (32*4/3 = 42.67 → 43),
which will **never match** the regex, so every issued deep-link is unclaimable.
**Required:** issue with `secrets.token_urlsafe(24)` (→ exactly 32 chars, ~192 bits). Update
T025's description (`token_urlsafe(32)` → `token_urlsafe(24)`) and the view accordingly.
(Alternative: widen the bot regex to `{1,64}` — but the fixed-length form is fine and already
tested, so prefer the token-length fix.)

### Change #2 — Cross-process User-creation race (affects T027)
Phase 2 needs the `User` row (created by the bot in phase 1 via `get_or_create_user`, which
also writes `username`/`first_name`/`last_name`). Two hazards:
- If web polls **before** the bot created the `User`, a naive `User.objects.get(telegram_id=…)`
  raises `DoesNotExist`.
- If web `get_or_create`s the `User` first (empty profile), the bot's later `get_or_create`
  finds the row and **does not backfill** the Telegram profile fields — data loss.

**Required design:** the **bot remains the authoritative profile writer**. Web phase 2 must
`get` the `User` with a **short bounded retry** (e.g. up to ~2 s) for `DoesNotExist`, since the
bot creates it within the same deep-link tap round-trip (sub-second in practice). Do **not**
`get_or_create` from the web. (Cleaner alternative: a shared
`ensure_user(telegram_id, profile=None)` service using `update_or_create` defaults, so the
last writer with profile data wins — acceptable if adopted consistently by both processes.)

### Minor recommendation (non-blocking)
- Views placement: T025/T026/T027 list `apps/users/views/consent.py`. Functionally fine (it
  already aggregates auth-adjacent views), but for single-responsibility a dedicated
  `apps/users/views/login.py` is cleaner. Either is acceptable; keep the planned file to avoid
  rework, but prefer `login.py` if the implementer touches the module anyway.
- `LOGIN_REDIRECT_URL` is `"/"`; post-login users typically want `ads:dashboard`. Consider
  setting it (or redirecting from the issuance success page) — small, optional.
- `give_consent`/`withdraw_consent` use naive `datetime.now()` (T037 covers timezone); out of
  scope here but note the new phase-2 code should use `django.utils.timezone.now()`.

---

## 8. Verdict (explicit)

**GO WITH CHANGES** for tasks **025, 026, 027, 028, 029**.

- **T025 (issuance):** GO — implement §2 phase 0, but use `secrets.token_urlsafe(24)` (Change #1),
  not `token_urlsafe(32)`.
- **T026 (consumption + cleanup fix):** GO — atomic `UPDATE consumed_at` (§2 phase 2) and fix
  `cleanup_login_tokens.py:48` `created_at__lt` → `consumed_at__lt`.
- **T027 (status-poll session):** GO — `GET /login/status/` with `auth.login` + `cycle_key` +
  `can_login` gate + bounded-retry user `get` (Change #2).
- **T028 (TOCTOU hardening):** GO — `update(..., returning=True)` inside `transaction.atomic()`;
  document it as hardening (claim already atomic via predicate), not a live double-claim fix.
- **T029 (docstring):** GO — trivial, accurate docstring correction.

No architectural blockers. The only true integration risks are the two changes in §7; fold them
into the task descriptions and the four-track contract in §2 will assemble cleanly with
zero new cross-process configuration coupling.
