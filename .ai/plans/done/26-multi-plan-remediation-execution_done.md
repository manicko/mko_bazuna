---
title: Multi-Plan Remediation Execution — P21 / P22 / P23 / P16 debt
slug: 26-multi-plan-remediation-execution
phase: 26
status: shipped
created: 2026-10-05
source_plan: multiple
verified_head: 302b5343
language: en
block_count: 12
---

# §A.0 Execution result (recorded 2026-10-06)

**All 12 blocks (B-01 … B-12) shipped.** Executed against a tree whose HEAD had advanced
past `verified_head`; the plan's §A.1 drift rule required each Implementor to stop-and-report
rather than adapt silently, and each did. Commit map:

| Block | Commit(s) | Block | Commit(s) |
|---|---|---|---|
| B-01 | `d6504e45` | B-07 | `c514a8ca` |
| B-02 | `2e4c6c05` | B-08 | `0a00f3a9`, `0efa6314` |
| B-03 | `51e84c50` | B-09 | `6de51f40` |
| B-04 | `b6fe7d87` | B-10 | `b28d9189` |
| B-05 | `4ecdd3b6` | B-11 | `52276d16` |
| B-06 | `3d908f3b` | B-12 | `23153055` |

**Corrections found by the post-ship audit (recorded, not applied to block text):**
- §A.2 is stale: `.ai/plans/20-media-remediation-execution.md` and
  `src/backend/apps/users/services/deactivation.py` are clean, and `.ai/plans/21…26` are
  tracked, not untracked.
- §A.4 row 16-7 nginx counts are wrong: 4 `limit_req_zone` per file and 15/13 `location`
  blocks (not 9/7 and 11/9).
- Paths: `test_compose_contract.py` is at `src/backend/tests/`;
  `test_prod_email_host_missing_warns_but_imports` is at
  `src/backend/config/settings/tests/test_settings_secrets.py`.

No block of this plan remains executable at `302b5343`.

# §A Provenance, drift control, and corrections

## A.1 Provenance

Four source plans were audited against the live tree at HEAD `8fb2c0bc`. This document is the
**execution plan for the remaining work only**. It does not re-plan anything that already shipped.

| Source plan | Path | State at HEAD | In scope here |
|---|---|---|---|
| P21 | `.ai/plans/21-nginx-dev-media-gate.md` | BLOCK 1–3 unimplemented, BLOCK 4 = permanent deferral | BLOCK 1–3 |
| P22 | `.ai/plans/22-nginx-rate-limit-deployed-gate.md` | BLOCK 1–8 unimplemented, BLOCK 9 = permanent deferral | BLOCK 1–8, minus the design defect in §A.4 (22-D1) |
| P23 | `.ai/plans/23-key-columns-ownership.md` | 4 phases, **nothing** converted | all 4 phases |
| P16 | `.ai/plans/16-auth-login-remediation-execution.md` | **all 11 blocks shipped** | documentation debt + plan currency only |

**Head of record:** `8fb2c0bc`. Any Implementor whose `git rev-parse HEAD` differs must stop and
report rather than adapt silently — every verified starting state in §B is HEAD-relative.

## A.2 Working-tree state owned by other agents

| Path | State | Rule for this plan |
|---|---|---|
| `.ai/plans/20-media-remediation-execution.md` | modified uncommitted (+1265/−27), another agent's BLOCK 8 task | **re-read immediately before editing**; stage only the single P23 Phase-3 hunk |
| `src/backend/apps/users/services/deactivation.py` | modified uncommitted | do not touch |
| `.kilo/commands/implement/implement-plan-multiagent.md` | modified uncommitted | do not touch |
| `.ai/audit/**` | 16 pre-existing ` D` deletions | do not touch, do not restore |
| `.ai/plans/21-…` … `.ai/plans/25-…` | untracked | editing these is in-scope only where a block says "record the correction" |
| `.ai/context/19-…`, `.ai/tmp/`, `staticfiles/` | untracked | do not touch |

**Hard git rule, binding on every Implementor in this plan:**

```
git add <explicit path> [<explicit path> ...]      # only
```

Never `git add -A`, `git add .`, `git add <dir>`. Never `git reset`, `git checkout`,
`git stash`. Stage only the paths a block names, and for `.ai/plans/20-…` stage only the one hunk.

## A.3 Ordering principle

One Implementor at a time. Serial execution. Contended files first (so a reservation is claimed
before a cheap block can touch it), then highest risk, then cheapest-confirmation-first.

## A.3.1 ⚠ Block-id disambiguation — READ THIS

**This document's blocks are `B-01` … `B-12`.** Plan 16 `.ai/plans/16-auth-login-remediation-execution.md`
**also** numbers its own execution blocks `B-01` … `B-11`. The two numbering schemes collide.

**Binding rule for every reader and Implementor:**

| Form | Meaning |
|---|---|
| A **bare** `B-nn` in this document | **always** a block of **this** document (§B) |
| `P16 §B-nn`, or `B-nn` next to a commit hash | **always** a block of **plan 16** |

Never resolve a bare `B-nn` by opening plan 16, and never resolve a `P16`-qualified one by opening
this document. Where plan 16's blocks are named in §A.4, §B-11, §B-12, §F or §E **without** the
`P16` qualifier, treat them as a defect in *that sentence* and re-read the sentence against the
`P16` rows in §A.4 before acting on them.

## A.4 CORRECTIONS table

Disposition values: `CORRECT THE PLAN` (block scope must use the tree truth, not the plan's claim) ·
`NARROW` (the plan's remedy is over-scoped; do less) · `CONFIRM` (the plan's claim is already right;
proceed) · `REJECT` (the plan's claim is false and following it would do harm) · `EXTERNAL GATE`
(a human/product decision this plan may not resolve).

### Plan 21

| # | Plan claim | Tree truth at `8fb2c0bc` | Disposition |
|---|---|---|---|
| 21-1 | §1.1 dev override sets `image: nginx:alpine` | `docker-compose.yml::nginx` pins `nginx:1.30.5` (09-API-016); `nginx:alpine` is the **rollback** value. All other nginx service attributes verified verbatim: `depends_on: [web]`, `cap_drop: ["ALL"]` + 5 `cap_add`, `read_only: true`, 2 tmpfs, `security_opt`, `mem_limit`, `cpus`, `restart: unless-stopped` | CORRECT THE PLAN — no conf/service edit is needed; the block must not "fix" the pin |
| 21-2 | "189 and 157 CRLF lines" | `nginx.conf` = 227 CRLF / 0 LF; `nginx.dev.conf` = 188 CRLF / **2 bare LF (mixed endings)**; `Makefile.ps1` = 430 CRLF / 0 LF; `docker-compose.dev.override.yml` = LF-only | NARROW — carry the **qualitative** hazard only ("CRLF silently no-ops `$`-anchored regexes"); **do not pin counts** — they drift on every conf edit. `nginx.dev.conf` mixed endings is the actionable part |
| 21-3 | N1 shadow analysis (wrong in 3 of 4 items) | In `src/backend/tests/test_nginx_config.py`: `_location_block` is first-match; `_iter_location_blocks` uses `re.match(r"\s*location\b", line)` — anchored, so a `#` comment can never match. Real shadowable anchors: **`= /metrics` (4 call sites)**, **`/protected-media/` (1)**, **`location /health/ {` (1)** — a third anchor neither plan names. **`/media/` shadows nothing.** `limit_req_zone` is load-bearing via `_limit_req_zones` `re.findall` census asserting `len(zones) == 4` | CORRECT THE PLAN — the do-not-touch conclusion stands; the stated mechanism is wrong and must not be reproduced in the block's rationale |
| 21-4 | N3: `test_compose_contract.py` "has no nginx assertions" | **Two**, not zero: a `user:` rationale-table row, and `test_docker_deployment_table_quotes_the_pinned_images`, which parses `docs/ops/docker-deployment.md`, asserts the nginx row quotes exactly `nginx:1.30.5`, **and sweeps every `docs/ops/*.md`** asserting none restates `postgres:18-alpine` | REJECT — **neither plan mentions this test**, and **both new runbooks land inside `docs/ops/`**, inside that sweep. Any block creating a `docs/ops/*.md` file must satisfy it |
| 21-5 | OQ-3: rate-limit table lists only `/login/` and `/search/` | `### Rate Limiting` lists **six** rows: `/login/`, `/csp-report/`, `/search/`, `/`, `/media/`, `/moderation/` | CORRECT THE PLAN — the doc block's census is six rows |
| 21-6 | OQ-4: C3 bind-mount scope paragraph is wrong | **CONFIRMED as predicted.** The `**Bind-mount scope in dev:**` paragraph wrongly lists `nginx` as `.:/app`-bound, wrongly excludes `create_admin`, wrongly omits `load_cities`. Truth: `web`, `bot`, `load_catalog`, `load_cities`, `create_admin`, `seed` all carry `.:/app`; `migrate` has **no** `volumes:` key; `nginx` carries `media_volume` + `nginx.dev.conf` + `certs` | CONFIRM — the doc block fixes this paragraph |
| 21-7 | All P21 surfaces absent | **Confirmed ABSENT:** `scripts/verify-nginx-media-limits.ps1`, `Makefile.ps1::Invoke-VerifyNginx`, its `switch` arm, its `Show-Help` line, the `NGINX_BURST`/`NGINX_SETTLE`/`NGINX_POLL_ATTEMPTS`/`NGINX_POLL_INTERVAL` overrides, `docs/ops/dev-nginx-media-gate.md`, all three doc cross-links. **Confirmed PRESENT:** the two stale comment blocks in `src/backend/config/settings/dev.py` (the one preceding `TRUSTED_PROXY_NETWORKS` and the one preceding `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX`) | CONFIRM — the stale comments are the *seed* of block B-04's comment scope |
| 21-8 | AC demonstrates exit-0 "present but not running", burst-limit, settle and script-deny paths | `mko-bazuna-dev-nginx-1` exists but is **`Exited (0)`**, 28 hours stale; certs **are** on disk. An **agent cannot** demonstrate any of the four runtime paths — they need an operator to run `up -d nginx`. Also: `nginx.dev.conf` has **no** `/health/` and **no** `= /metrics` block, so an HTTPS probe on :443 falls through to `location /`, which carries `browse_limit burst=40 nodelay`; `ALLOWED_HOSTS` in `.env.dev` includes `localhost` | EXTERNAL GATE — split AC into agent-verifiable (static parse, dry-run, deny path) and operator-run (live burst/settle/exit-0). Do not let an Implementor claim the live paths as verified |
| 21-9 | Makefile idioms | `Invoke-Profile` is the env-override idiom (`$x = if ($env:X) { $env:X } else { "default" }`); `Invoke-SeedPhotosValidate` is the host-side-script precedent (no compose project name, no container); `Show-Help` is `Write-Host "  <target>       <description>"`. **Exit-code propagation exists only on `Invoke-Test` / `Invoke-TestAll` / `Invoke-TestRecreate`** — P21 would be the first non-test target to propagate it | CONFIRM + risk flag — exit-code propagation is the one genuinely novel piece; see B-04's risk band |
| 21-10 | Doc edit target | `docs/ops/docker-deployment.md` is **1591 lines**; `docs/00-overview/doc-maintenance-rules.md` sets a **1000-line hard / 800-line soft** threshold. P20 BLOCK 10 **already claims that file** and declares itself in its own Surface as "append-only, file is dirty with another phase's edits" | CORRECT THE PLAN — one editor at a time; P20 BLOCK 10 has **prior claim**. Serialise behind it; see §C |
| 21-11 | §6.2 constraint 4: `test_dev_and_test_share_the_transport_tuple` pins the `TRUSTED_PROXY_NETWORKS` change | That test pins **7** settings; `TRUSTED_PROXY_NETWORKS` is **not** among them | NARROW — drop the constraint; it over-covers |
| 21-12 | Performance/regression context | `ListingsQuery.PER_PAGE = 24`; `ad_list.html` has exactly **1** `<img>` per card; `locustfile.py` has **no** `/media/` task and targets `http://localhost:8000`; `.pre-commit-config.yaml` runs **gitleaks only** (no lint, no EOL hook) | CONFIRM — bounds the blast radius of the burst-40 test pin and means there is **no EOL hook** to normalise `nginx.dev.conf` mixed endings automatically |

### Plan 22

| # | Plan claim | Tree truth at `8fb2c0bc` | Disposition |
|---|---|---|---|
| 22-D1 🔴 | §5.4 `crosscheck_delta`: access-derived `/media/` 429 count MUST EQUAL error-derived `limiting requests` `/media/` count; AC1.4 returns **VOID** on non-zero delta. §9.1: "`$limit_req_status` is redundant". Premise: "there is no 429 emitter under `/media/`" | **PREMISE FALSE.** Commit `5ffad37e` (09-API-005) added application-level limiting at `apps/ads/views/listings.py::media_gate`, emitting `rate_limited_response(json=False)` → HTTP **429** under `/media/<path:image_key>`. A Django-side 429 appears in the **access** log as `$status 429` on a `/media/` URI but produces **no** `limiting requests` **error** line. The delta is therefore **non-zero on a healthy stack**, so AC1.4 returns VOID on exactly the zero-rejection run it exists to confirm; and §9.1's "redundant" claim is inverted — the two channels are precisely what separates an nginx-side from a Django-side rejection. The aggregator still measures the right quantities; **the criterion is wrong** | REJECT + **REDESIGN GATE** — do not implement the criterion as written. **B-01 is a mandatory design block that precedes B-02** |
| 22-2 | 429 census: `listings.py` ×2 | **8** `rate_limited_response(...)` call sites in `src/`: `apps/ads/views/listings.py` ×**3** (`media_gate` under `/media/`, `ad_detail`, `listings`), `apps/core/views.py::privacy_policy`, `apps/users/views/consent.py::login_issue` ×2, `apps/search/views/search.py::search`, `apps/search/views/autocomplete.py::autocomplete`. `media_gate` returns 200 / 403 / 404 / **429**; under `settings.DEBUG=True` **both** success paths take `_serve_image(...)` → `FileResponse` and **never** set `X-Accel-Redirect` | CORRECT THE PLAN — the census underpins the B-01 options and the B-05 doc wording |
| 22-D5 | §9.1 remediation table cites `test_media_location_is_rate_limited` with `len(zones) == 3`; "raise burst 40 → 80/100, no test change" | Truth: **`== 4`** (09-API-015), and a second test `test_media_location_carries_browse_limit_burst_40` now asserts the byte-exact `"limit_req zone=browse_limit burst=40 nodelay;"` — its docstring **names P21 and P22 by path** as the reason the pin exists. The "no test change" row is doubly false | REJECT — the burst-40 pin is contractual; see B-01's option space and B-05's DoD |
| 22-D3 | §1 cites `docs/ops/rollback.md` §5 prescribing `--env-file .env.staging` | It now uses `--env-file .env.prod` and states verbatim *"There is no `.env.staging` file and no `docker-compose.staging.yml` in the repository"* + *"Do not invent an `.env.staging` file."* Conclusion (no staging) holds; citation is stale | CORRECT THE PLAN — the runbook must cite the current text, and the stale citation in the untracked P22 source plan is recorded in B-05 |
| 22-D10 | WI-4 constraint 1: keep the `### Rate Limiting` table "byte-identical" | The table says "**Three** `limit_req_zone`s" (truth: four) and its `/csp-report/` row reads `login_limit` 10 req/s (truth: `csp_report_limit`, 1r/s, burst=5, per 09-API-015) — **wrong in two of six rows** | REJECT — "byte-identical" would ratify known-wrong documentation. B-05 **corrects** the table rather than preserving it |
| 22-6 | Conf state assumptions | 4 `limit_req_zone` blocks per file, all `$binary_remote_addr`; `limit_req_status 429;` at `http{}`; `log_format main` present in **both** files; **zero** `set_real_ip_from` / `real_ip_header` / `real_ip` tree-wide | CONFIRM — the last fact matters for B-01: the access log's client address is already the nginx-observed address, so it **is** commensurable with `$binary_remote_addr` |
| 22-7 | All P22 surfaces absent | **Confirmed ABSENT:** `scripts/measure-nginx-rate-limit-keys.py`, `src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py` (+ its fixture), `docs/ops/ops-nginx-rate-limit-gate.md`, the anchor-fix line, both cross-links | CONFIRM |
| 22-8 | Sound and reusable | `docker/Dockerfile` does **not** copy `scripts/`; `src/backend/apps/seed/tests/test_download_seed_photos.py` is the exact `importlib.util.spec_from_file_location` + `Path(__file__).resolve().parents[5] / "scripts"` precedent, at the same directory depth, so `parents[5]` resolves to the repo root for the P22 path; all five named stdlib precedents exist; `.env.staging` and `docker-compose.staging.yml` do **not** exist; `deploy.yml` has one job and no staging | CONFIRM — B-02 copies the download-seed-photos test shape verbatim |

### Plan 23

| # | Plan claim | Tree truth at `8fb2c0bc` | Disposition |
|---|---|---|---|
| 23-1 | Refactor is partially converted | **Everything is ABSENT / unconverted.** `src/backend/apps/media/storage_keys.py` does **not** exist. `KEY_COLUMNS` still lives in `apps/media/services/references.py` as `Final[tuple[str, ...]] = ("image","thumbnail_small","thumbnail_medium","thumbnail_large")`, with `unreferenced_keys` building a four-literal-arm `Q` chain **inline** and projecting `.values_list(*KEY_COLUMNS)`. `AdImage.storage_keys()` in `apps/ads/models.py` is a hardcoded literal preserving `cast` and a truthy filter, ordered as `KEY_COLUMNS`. `media_gate`'s `key_q` in `apps/ads/views/listings.py` is four literal arms with **three** `# type: ignore[operator]` on the `thumbnail_*` arms and **two** `.exists()` calls; authorisation kwargs have **drifted** from P23 §2 to `account_state_q("ad__user__")` + `ad__status=AdStatus.PUBLISHED` | CORRECT THE PLAN — B-08/B-09 must start from the drifted state, not P23 §2 |
| 23-2 | §4: "the drift claim is backwards" | **CONFIRMED.** `TestKeyColumnsAntiDrift` in `apps/media/tests/test_references.py` has exactly **2** tests; the module has 6 test functions total. Adding a 5th column + enum member leaves the existing relational test **GREEN** | CONFIRM — this is why B-06 exists and why its stop gate is real |
| 23-3 | Assumption 2: derive the index census from `AdImage.Meta.indexes` | **CONFIRMED.** `AdImage.Meta.indexes` holds exactly **four** explicit `models.Index`, one per key column. `AdImage.sha256` carries `db_index=True` and its implicit index is **absent** from `_meta.indexes` | CONFIRM + pin the caveat — `_meta.indexes` does **not** enumerate every index; do not treat it as total |
| 23-4 | Assumption 6: `KEY_COLUMNS` importers are limited | **CONFIRMED** by whole-tree grep: the only importers are `references.py` itself and `test_references.py` | CONFIRM — B-08's blast radius is exactly these two plus `ads/models.py` |
| 23-5 | Assumption 5: `db-schema.md` / `db-retention.md` "all four key columns" wording | **CONFIRMED still accurate** | CONFIRM — Phase 3 **records the check and changes nothing** in those two files |
| 23-CORR A | Commit A: preserve the census-vs-probe comment on `_collect_referenced_keys` | **MIS-AIMED.** `_collect_referenced_keys` in `apps/media/management/commands/sweep_orphaned_media.py` has only a one-line docstring. The distinguishing text lives in `_collect_dangling_keys` (the probe — "The join is load-bearing… 100% false positive on every seeded key (VAL-005)") and `_collect_report_orphan_files` (the census), plus an inline comment in `Command.handle` above `orphans = on_disk - referenced`. The protection is **already intact** in the tree | CORRECT THE PLAN — preserve those three comments **untouched** and record the correction; do not "restore" a comment onto the wrong function |
| 23-CORR B | Removing three `# type: ignore[operator]` will be observed by the typechecker | `reportUnnecessaryTypeIgnoreComment` is **OFF**. `pyproject.toml` sets `typeCheckingMode = "standard"` plus explicit `"none"` for `reportOperatorIssue` (the rule the ignores target) and 5 others. Empirically: basedpyright on `listings.py` → 0 errors/warnings/notes on a file with 3 provably-unnecessary ignores; repo-wide 180 ignore comments, 14 for rules set to `"none"`, none flagged | CONFIRM + **warning** — removal is safe **and unobservable**. The B-09 Implementor must **not** wait for a typechecker signal and must not treat silence as failure |
| 23-CORR C | `test_ad_image_delete_signal.py` lives under `apps/media/tests/` | It is at `src/backend/apps/core/tests/` | CORRECT THE PLAN — do **not** create a second copy |
| 23-CORR D | Phase 3's rationale in `.ai/plans/20-…`: "BLOCKS 7, 8 and 10 have file edges on those modules" | The target clause is still present **verbatim**, but the rationale is **stale** — BLOCKS 7, 8 and 10 have all **shipped** | CORRECT THE PLAN — B-10 updates the clause **and** its rationale |

### Plan 16 — all 11 blocks shipped; debt only

Commits: `B-01` `a19a0ee`+`83622e0` · `B-02` `49e741f`+`65efb3a` · `B-03` `8c65548`+`818c4504`+`a0bd928` ·
`B-04` `97c86dc8` · `B-05` `e106e0b8` · `B-06` `259dcb4f` (partial) · `B-07` `3cef5b22` ·
P16 block ids below are shown **without** the `P16` qualifier only to match the source plan's own
commit listing; they refer to plan 16, not to this document's blocks (see §A.3.1).
`B-08` `c2e57f8`+`7edc966`+`5dcc7e8` · `B-09` `74848c69` (shipped **as the planned deferral**) ·
`B-10` `32e151d7`+`cc3af4f6` · `B-11` shipped in substance.

| # | Plan claim | Tree truth at `8fb2c0bc` | Disposition |
|---|---|---|---|
| 16-1 🔴 | `B-10` record the session-lifetime decision in `docs/99-agent/architecture.md` § *Session Lifetime Policy (04-AUT-006)* | That section still reads *"**No product decision has been taken on the value.** … Do not record the finding as fixed."* while `base.py` **ships** `SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 1209600 seconds (14 days)` + `SESSION_SAVE_EVERY_REQUEST = False` — a direct contradiction between shipped code and the record of the decision | ✅ **CORRECTED (2026-10-05, B-11 `52276d16`).** See the TL ruling immediately below — **the "open product gate" framing in this row was WRONG.** |

> ### 🔴 TL RULING (2026-10-05) — the product gate for `04-AUT-006` was **already closed**. B-11's
> "open gate" framing was wrong; it is corrected here, in §B-11, §D-14, §E-12 and §F.4.
>
> **The B-11 Implementor searched rather than assumed, and found the decision.** `.ai/plans/16-auth-login-remediation-execution.md`
> (tracked, added by `86d2f0ce`) records a **Product Owner ruling dated 2026-10-03** in at least four
> verified places:
>
> - `G-10a`: *"⚠ THE VALUE ITSELF IS NOW RULED — 2026-10-03, Product Owner: the session lifetime is
>   **14 DAYS**, DECLARED EXPLICITLY IN SETTINGS. The 'owed product decision with a named owner'
>   framing is **WITHDRAWN**; known-gap #1 is **CLOSED AS A DECISION**."*
> - `### 🚧 PROPAGATION OBLIGATION` (raised 2026-10-03): *"**That statement is now FALSE.** … replace
>   'no product decision has been taken on the value' with **a record of the 2026-10-03 Product Owner
>   decision and its date**."*
> - `known_gaps_shipped`: *"the value is now a Product Owner **DECISION** dated 2026-10-03; nothing is
>   outstanding, nothing blocks `B-10` or `B-11`, and **no coordinator action remains**."*
>
> **So the honest record of `architecture.md` is the 2026-10-03 decision — not "still outstanding".**
> Keeping the gate open, as this plan originally required, would have shipped a **second false record**:
> one denying a ratification that plan 16 documents. That is the same defect class B-11 exists to fix.
>
> **What shipped** (`52276d16`): the section now records the decision **with attribution to plan 16**
> rather than asserting it in the Implementor's own voice; preserves the code-shipped / record-denial
> distinction; states the write-triggered semantics and the `?lang=` exception; records the reversal
> cost (a single literal); and **does not** claim `04-AUT-002` closed. Debt 2's marker-sweep record
> was added in the same file.
>
> **Standing lesson for this plan:** an Externgate derived from *"the repository does not say"* is not
> an external gate. **Search the whole repository — including tracked plan files — before declaring a
> decision unmade.** Three separate agents in this pass inherited that claim from a single upstream
> assertion without re-searching.
| 16-2 | `B-11` DoD: a tracker decision record citing §D item 14 (the phase-03 `EXT-`/`AUT-`/`SRH-` marker-sweep reservation) | **No such record exists anywhere** | CONFIRM — B-11 |
| 16-3 🔴 | `B-06` mandates `test_prod_requires_email_host` asserting `ImproperlyConfigured` | That shape is **explicitly forbidden** by the 2026-10-03 Product Owner ruling (09-API-009). The shipped opposite is `test_prod_email_host_missing_warns_but_imports`, whose docstring states the inversion. P16 also names the wrong path (`config/settings/tests/test_password_recovery.py`; actual: `apps/users/tests/test_password_recovery.py`) | REJECT — following P16 as written would write a **forbidden** test. B-12 corrects the section; **no test is written in this pass** |
| 16-4 | `B-02` i18n obligation discharged | `create_admin_user.py` raises `_("Password does not meet the password policy: %(errors)s")` — a new **untranslated** msgid, deliberate, with a comment pointing at a deferral recorded in `docs/99-agent/architecture.md` | CONFIRM — B-11 confirms the deferral pointer resolves; nothing to translate |
| 16-5 | `B-08`/`B-10` prose: `_TRANSPORT_SETTINGS` has six members | Commit `a0bd928` made it **seven** | CORRECT THE PLAN — B-12 |
| 16-6 | `B-07` known-gap tests 3 and 4 | They were **INVERTED** by `06-PII-109` / plan 18 (`test_banned_seller_is_now_refused_the_dashboard`; `test_edit.py::TestBannedSellerRelistNowRefused`). `G-B` was **overturned** by phase 06 — `withdraw_consent_action` is now registered with `permissions=["delete"]`. `04-AUT-002` remains **not closed** | CORRECT THE PLAN — B-12 records the inversion; `04-AUT-002` stays open |
| 16-7 | nginx counts | 9 `limit_req_zone` in `nginx.conf` (match) but **7** in `nginx.dev.conf` (P16 says 6); **4** zones (P16 says 3); 11 / 9 `location` blocks (P16 says 10 / 7) | CORRECT THE PLAN — B-12 |

---

# §B Execution blocks

Twelve blocks, **B-01 … B-12**, executed strictly in the order given by §C.2. Every block is
independently reviewable; every block names a single Implementor. `AUD`/`RES`/`PLN`/`IMP`/`VAL`
columns below are repeated per block in §B.x.1.

---

## B-01 — P22 `crosscheck_delta` criterion redesign (design gate, no code)

| Field | Value |
|---|---|
| Source plan | P22 §5.4, §9.1, AC1.4 (defect **22-D1**) |
| Priority | **P0** — B-02 is blocked on it |
| Risk | **High** — the change redefines what counts as VOID for a deployed-stack safety gate |
| Depends on | — |
| Blocks | B-02, B-05, B-11 |
| Auditor | **yes** — the plan's premise is factually false; the fact base (which channel sees which 429) must be re-established from the tree, not from P22 |
| Researcher | **yes** — multiple viable criteria exist; this is exactly the multi-approach case |
| Planner | **yes** — produces the decision artifact the Implementor must execute against |
| Implementor | **no** — this block writes a decision record, not production code |
| Validator | **no** — nothing is implemented; B-02 carries the review |

### Objective

Replace the invalid `crosscheck_delta` invariant and the `AC1.4` VOID trigger with a criterion
that is **true on a healthy stack** and still catches the failure the gate exists to catch: nginx
stopping serving `/media/` (or nginx 429s being misattributed) on the deployed stack.

The old invariant — *access-derived `/media/` 429 count MUST EQUAL error-derived `limiting
requests` `/media/` 429 count* — is inverted, because `apps/ads/views/listings.py::media_gate`
(09-API-005, commit `5ffad37e`) emits a Django 429 under `/media/<path:image_key>` that lands in
the **access** log with no matching **error** line. The delta is non-zero on a healthy stack, so
`AC1.4` returns VOID on the very zero-rejection run it was designed to confirm.

### Verified starting state

- **8** `rate_limited_response(...)` call sites in `src/`; `media_gate` is the only one under
  `/media/` and it returns 200 / 403 / 404 / **429**.
- Under `settings.DEBUG=True` both `media_gate` success paths call `_serve_image(...)` →
  `FileResponse` and **never** set `X-Accel-Redirect`.
- 4 `limit_req_zone` blocks per nginx file, all `$binary_remote_addr`; `limit_req_status 429;` at
  `http{}`; `log_format main` present in **both** files.
- **Zero** `set_real_ip_from` / `real_ip_header` / `real_ip` tree-wide ⇒ the access log's client
  address is already the nginx-observed address and **is** commensurable with `$binary_remote_addr`.
- `test_media_location_carries_browse_limit_burst_40` pins the byte-exact
  `"limit_req zone=browse_limit burst=40 nodelay;"` and its docstring names P21/P22.

### Scope

| Semantic unit | Change |
|---|---|
| `.ai/plans/22-nginx-rate-limit-deployed-gate.md` §5.4 `crosscheck_delta` | replaced by the ratified criterion |
| `.ai/plans/22-nginx-rate-limit-deployed-gate.md` AC1.4 | VOID trigger redefined |
| `.ai/plans/22-nginx-rate-limit-deployed-gate.md` §9.1 | remediation table refreshed: `len(zones) == 4` (not 3), burst-40 pin is contractual, **`$limit_req_status` is NOT redundant** |
| `.ai/plans/22-nginx-rate-limit-deployed-gate.md` §1 staging citation | `docs/ops/rollback.md` now uses `--env-file .env.prod`; the stale `.env.staging` citation is struck |
| `.ai/plans/22-nginx-rate-limit-deployed-gate.md` §5.2 / aggregator contract | names the agreed channel semantics so B-02 and B-05 inherit one definition |
| new decision record | one short file, or a dated decision section — the Implementor of B-02 must be able to cite it |

### Binding constraints

1. **The fix is to the criterion, not the aggregator.** The aggregator already measures the right
   quantities. Do not re-architect the measurement; do not add a new log source in this block.
2. **No production code, no nginx conf edit, no schema change in this block.** In particular
   `nginx.conf`, `nginx.dev.conf`, `docker-compose*.yml` are **out of scope** here.
3. A change to `log_format main` or to `rate_limited_response` (a discriminator option) is a
   **shared-config / production-code change** and is **forbidden** without a separate plan. This
   block may *recommend* it; it may not specify it as in-pass work.
4. The burst-40 pin and `len(zones) == 4` are contractual (09-API-015). No criterion may be built
   that pressures either.
5. The record must state, per channel, exactly which emitter(s) it can see:
   access-log 429 ⇒ nginx **or** `media_gate`; error-log `limiting requests` ⇒ nginx only.
6. The record must be explicit about what VOID now means and must not leave a reader able to
   reconstruct the old equality.

### Options to enumerate (the record must rank these, not just list them)

| Option | Idea | Cost / consequence |
|---|---|---|
| **(a)** | Redefine the invariant to compare **like with like** — e.g. nginx-side 429 count vs nginx-side rejection count, never access-vs-error | **Not implementable on its own.** The two channels are not commensurable without a discriminator, because nothing in either channel marks a Django 429 as a Django 429. (a) is really (c) or (d) in disguise. Record this explicitly so nobody re-derives it. |
| **(b)** | **Demote the delta to a reported diagnostic.** VOID triggers become only assertions that are true on a healthy stack: nginx `up` and healthy, `/media/` served by nginx, the 4 `limit_req_zone` census intact, `X-Accel-Redirect`/`FileResponse` served, reachable TLS on :443. The access-vs-error 429 delta is still **computed and printed**, with a caption saying it is expected to be non-zero whenever `media_gate` is rejecting. | Smallest possible diff. Cannot detect nginx-side rejections *misattributed* to the app — but neither can the current criterion, and it does not claim to. Preserves the diagnostic value. |
| **(c)** | **Introduce an nginx-side discriminator** so the channels become separable: a distinguishing response header on the Django 429 path, or a `map $status …` / new field in `log_format main` | Only option that makes a strict cross-check *true*. Cost: touches shared config and/or production Python, both outside the "measurement script" scope of P22; changes what the deployed stack emits; interacts with the `docs/ops` pin sweep and the burst-40 test pin. **Belongs in its own plan, not here.** |
| **(d)** | **Scope the measurement to nginx-side evidence only** — the error-log `limiting requests` census is the *sole* pass/fail signal; access-log 429s are contextual telemetry with no threshold | Simplest to reason about, but discards information the aggregator already gathers and makes the access channel a dead branch. Strictly weaker than (b). |

> **✅ TL RULING (2026-10-05) — the Researcher's evaluation landed and INVERTED the earlier
> recommendation. The settled design is (a), not (b).**
>
> Earlier drafts of this block recommended **(b)** on the belief that (a) was "not implementable on its
> own". The Auditor then found the missing piece and the Researcher evaluated it:
>
> | # | Option | Disposition |
> |---|---|---|
> | **(a)** | compare like-with-like **after** attributing | ✅ **ADOPTED** |
> | **(b)** | demote the delta to a reported diagnostic | ✅ adopted **inside** (a) as the *interpretation rule*, not instead of it |
> | **(c)** | real discriminator (`$limit_req_status` / a 429 header) | ⏸ **DEFERRED** — named successor, with a trigger |
> | **(d)** | nginx-side evidence only | ❌ **REJECTED** — strictly weaker |
> | **(e)** | ordering / dominance / ratio invariant | ❌ **REJECTED as a gate** — falsified; keep the taxonomy as a diagnostic |
> | **(f)** | *(new)* restrict **both** channels to `GET` | ✅ **ADOPTED inside** (a) |
> | **(g)** | *(new)* config-derived exposure precondition (`> 60` per key per fixed 60 s window) | ✅ **ADOPTED**, replacing `at_risk_pairs` |
>
> **The three findings that drive this:**
>
> 1. **A free discriminator already exists.** `log_format main`'s `$body_bytes_sent` separates the
>    origins with **no config edit and no production-Python edit**. Use the **one-sided** rule
>    `Django-origin ⟺ $body_bytes_sent == 0` — **never a literal byte count.** The nginx body length
>    is a function of the pinned build's error page, so it drifts on upgrade, on `server_tokens off`,
>    and on `msie_padding on` (UA-dependent). `0` is contractual (an existing test pins it). The
>    one-sided rule's every failure mode is a loud **VOID**; a two-sided rule has a **silent
>    false-PASS** mode. One-sided strictly dominates.
> 2. **`at_risk_pairs` never established exposure.** It demanded "≥2 page loads of ≥13 tokens in 2 s"
>    ⇒ R=26 — and **26 requests in 2 s is rejected by neither limiter** under the shipped config.
>    Replaced by `keys_over_media_budget`: **⟺ `R > 60` per key per 60 s window, at least one limiter
>    rejects.** That `60` is `RateLimitBudget.MEDIA_GATE`, already shipped — no new constant.
> 3. **(e) is falsified because the split is a function of burst duration, not a stable ratio.** For
>    `W ≤ 1 s` Django is structurally incapable of rejecting (`f ≤ 60`); for `W > 1 s` every nginx
>    rejection is accompanied by ≥ `20·(W−1)` Django rejections. HTTP/2 multiplexing, thumbnail
>    count and CGNAT all move `W`, so any ratio gate is environment-dependent by construction.
>
> **The withdrawn criterion's worst property, which the record must state:** the raw delta is
> **zero precisely when the thing being measured is broken.** `crosscheck_delta` is
> `requests_media_429 − error_media_limit_rejected`, and both terms fall together whenever the nginx
> access line for a refusal is absent — a misrouted `location`, a bare `return 429`, or a
> `limit_req_log_level` raised above what the error log writes. Both sides go to 0, AC1.4 is
> satisfied, and **a deployed stack refusing every image is declared clean.** That is the single
> strongest argument against the withdrawn invariant.
>
> The ratified rule: count `/media/` `GET` 429s; those with `$body_bytes_sent == 0` are Django's, the
> rest are nginx's candidates; **`attribution_delta == 0` is a soundness precondition, not a verdict**;
> PASS requires zero rejections of either origin over a window where at least one key exceeded 60
> `/media/` requests in a fixed 60 s window.
>
> **Escalation trigger for the deferred (c), to be recorded verbatim:** if the error channel is ever
> lost, or `limit_req_log_level` / `error_log` level is ever changed such that `[error]` lines stop
> being written, the delta check dies. At that point `log_format main` must gain `$limit_req_status`
> and the criterion collapses to the single-channel exact form
> `429 AND $limit_req_status == REJECTED`, needing no second channel.
>
> **Decision-record home:** `docs/99-agent/nginx-rate-limit-attribution-record.md`, matching the two
> existing precedent records. Deliberately **not** `docs/ops/` —
> `test_compose_contract.py::_DOCS_OPS.glob("*.md")` and `test_docs_ci_parity.py::_docs_ops_markdown()`
> sweep `docs/ops/*.md` only, so a record there enters the pinned-image and doc-parity sweeps for no
> benefit. B-05 owns `docs/ops/ops-nginx-rate-limit-gate.md` and must link the record by relative path.

### Acceptance criteria

1. The ratified criterion is stated as an executable rule: **which counts, which channel, which
   comparison, and which outcome (PASS / VOID / FAIL)** for each.
2. The record proves the old equality is invalid by citing `media_gate` +
   `rate_limited_response(json=False)` → 429 and the absence of a matching error line.
3. The record shows, on a worked example, a **healthy zero-rejection run** returning **PASS**, and
   a **simulated nginx-stopped-serving** run returning **VOID** — the two cases the gate must get
   right, and the two the current criterion gets wrong.
4. The record states what the delta is allowed to be on a healthy stack and why.
5. The record names the follow-up that would allow a strict cross-check, and marks it
   **out-of-pass**.
6. P22 §5.4 / AC1.4 / §9.1 / §1 are mutually consistent after the edit — no stale `== 3`, no
   `.env.staging`, no "`$limit_req_status` is redundant".
7. The record lists, explicitly, the facts the B-02 Implementor must **re-verify at implementation
   time** rather than inherit (see the "verify, do not assume" list in DoD).

### Rollback

The source plan is untracked and the decision record is additive. Rollback = revert the P22 edits
and delete the record. No runtime state is touched, so no operational rollback exists.

### DoD

- [ ] P22 §5.4, AC1.4, §9.1, §1 updated and internally consistent.
- [ ] Decision record written and cited from §5.4.
- [ ] Options (a)–(d) ranked with rationale; (b) recommended; (c) deferred with a named follow-up.
- [ ] **Verify, do not assume** (handed to B-02): (i) whether `rate_limited_response` sets any
      response header today that a discriminator could key on; (ii) the exact `log_format main`
      field list in `nginx.conf` and `nginx.dev.conf`; (iii) whether `media_gate`'s limiter keys on
      client IP or on the authenticated user (changes whether its 429s are even countable by
      `$binary_remote_addr`-based parsing); (iv) whether the 200/403/404 paths can produce a 429
      under any settings combination not covered above; (v) whether the deployed stack logs the
      access and error streams to the same sink with the same field set.
- [ ] No file other than the P22 plan and the decision record was created or modified.

---

## B-02 — P22 aggregator script and unit tests

| Field | Value |
|---|---|
| Source plan | P22 BLOCK 1–6 (implementation), criterion from B-01 |
| Priority | **P0** |
| Risk | **High** — it is a safety gate's decision engine; a wrong PASS is worse than a wrong FAIL |
| Depends on | **B-01** |
| Blocks | B-05 |
| Auditor | no — the design uncertainty is resolved in B-01; re-auditing the same premise adds nothing |
| Researcher | no — approach is fixed by B-01's recommendation |
| Planner | no — no remaining multi-step design |
| Implementor | **yes** |
| Validator | **yes** — the VOID/PASS logic is the highest-consequence code in this plan; independent review against B-01's record |

### Objective

Create the deployed-stack measurement script `scripts/measure-nginx-rate-limit-keys.py` and its
unit tests, implementing the B-01 criterion.

### Verified starting state

- `scripts/measure-nginx-rate-limit-keys.py` — **ABSENT**.
- `src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py` (+ fixture) — **ABSENT**.
- `docker/Dockerfile` does **not** copy `scripts/`, so no image rebuild is required.
- `src/backend/apps/seed/tests/test_download_seed_photos.py` is the exact precedent:
  `importlib.util.spec_from_file_location` + `Path(__file__).resolve().parents[5] / "scripts"`.
  Same directory depth, so `parents[5]` resolves to the repo root for this path.
- All five stdlib precedents P22 names exist. `.env.staging` and `docker-compose.staging.yml` do
  not exist; `deploy.yml` has one job and no staging.
- Source access log location / format for the deployed stack is **not** established in this
  material — see the verify list.

### Scope

| Semantic unit | Change |
|---|---|
| `scripts/measure-nginx-rate-limit-keys.py` (new) | `main()`; the nginx-side rejection census; the access-side 429 tally; the **redefined** cross-check per B-01; the per-key / per-zone breakdown; the fixed exit codes |
| `src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py` (new) | unit tests over the parser and the decision function |
| its fixture module | synthetic log corpus in the shape of `test_download_seed_photos.py`'s fixture handling |
| `.ai/plans/22-…` (status header only) | mark the implementation blocks shipped, with the commit refs |

### Binding constraints

1. **The cross-check is B-01's, verbatim.** If the Implementor believes B-01's criterion is wrong,
   they must stop and post HOLD — not substitute their own.
2. Tests import the script the way `test_download_seed_photos.py` does
   (`importlib.util.spec_from_file_location`, `Path(__file__).resolve().parents[5] / "scripts"`).
   No new packaging, no `sys.path` mutation, no new dependency.
3. Python 3.14 / Django 5.2 conventions already in the repo; English-only comments and messages.
4. **No `print()`** — use `logging` for any diagnostic, and reserve stdout for the report the
   runbook tells the operator to read. Project rule 12.
5. `scripts/` is **not** in the Docker image; do not add a copy step.
6. Do **not** touch `nginx.conf`, `nginx.dev.conf`, or any `docker-compose*.yml` file.
7. Tests must cover the healthy-zero-rejection case explicitly — that is the regression B-01 exists
   to prevent, and it has no other automated guard.
8. Unit tests are required even though the script is dev/ops-only: B-01's rule table is logic, and
   logic that gates a safety decision gets tests.

### Acceptance criteria

1. Given a synthetic corpus with **no** rejections anywhere, the script returns **PASS** (not VOID).
2. Given a synthetic corpus with nginx `limiting requests` rejections under `/media/`, the script
   reports them on the nginx channel and reaches the outcome B-01 specifies.
3. Given a synthetic corpus containing **only** `media_gate` 429s (access `$status 429`, no error
   line), the script reports a non-zero delta, **does not** treat it as a failure, and its report
   text says so.
4. Given an nginx that is not serving `/media/`, the script returns the B-01 VOID outcome.
5. The script never reads `.env.staging` and never asserts the existence of
   `docker-compose.staging.yml`.
6. The script is importable-free-of-side-effects: importing it (as the tests do) runs nothing.
7. Unit tests pass under the Docker test service; `uv run ruff check` clean on both new files.

### Rollback

Both files are new. Rollback = delete `scripts/measure-nginx-rate-limit-keys.py`, the test module
and its fixture. No migration, no config, no data.

### DoD

- [ ] B-01's rule table implemented line for line.
- [ ] **Verify, do not assume:** (i) the real access/error log paths and field names for the
      deployed stack — this material does **not** establish them, so the Implementor must find them
      in the runbook/`deploy.yml`/`docker-compose` log config and record what they found; (ii) the
      actual `log_format main` field list (B-01 must confirm it independently); (iii) whether the
      deployed stack writes nginx logs to stdout (container) or to a mounted file — this changes
      the entire input contract.
- [ ] If (i) cannot be established from the repo, the block stops and reports rather than guessing.
- [ ] `git add scripts/measure-nginx-rate-limit-keys.py src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py …`
      — explicit paths only.
- [ ] Validator review signed off against B-01's record.
- [ ] `test_docker_deployment_table_quotes_the_pinned_images` is **not** affected (no `docs/ops`
      file was added here).

---

## B-03 — P21 dev nginx media-limits verification script

| Field | Value |
|---|---|
| Source plan | P21 BLOCK 1 |
| Priority | **P1** |
| Risk | **Medium** — dev-only tooling, but it is a gate that reports PASS/FAIL to a human |
| Depends on | — (independent of B-01/B-02 in substance) |
| Blocks | B-04, B-05 |
| Auditor | no — the plan's factual errors are already corrected in §A.4; re-auditing is redundant |
| Researcher | no — P21's approach is concrete and approved |
| Planner | no |
| Implementor | **yes** |
| Validator | **no** — medium-risk dev tooling; static parse + deny-path execution is proportionate. Use B-04's exit-code review as the practical check |

### Objective

Create `scripts/verify-nginx-media-limits.ps1`: a PowerShell gate that verifies the dev nginx
`/media/` limiting configuration and, when the container is running, exercises the burst and settle
behaviour against the documented limits.

### Verified starting state

- `scripts/verify-nginx-media-limits.ps1` — **ABSENT**.
- `mko-bazuna-dev-nginx-1` **exists** but is **`Exited (0)`**, ~28 hours stale. Certs **are** on
  disk. So the "present but not running" path is real and reachable — as a **negative** observation.
- `nginx.dev.conf` has **no** `/health/` and **no** `= /metrics` block, so an HTTPS probe on :443
  falls through to `location /`, which carries `browse_limit burst=40 nodelay`.
- `ALLOWED_HOSTS` in `.env.dev` includes `localhost`.
- Test-shadow hazard (§A.4 21-3): shadowable anchors are `= /metrics` (4 sites),
  `/protected-media/` (1), `location /health/ {` (1). **`/media/` shadows nothing.**
  `limit_req_zone` is load-bearing (`_limit_req_zones` census, `len(zones) == 4`).
- Line-ending reality: `nginx.conf` 227 CRLF / 0 LF; `nginx.dev.conf` 188 CRLF / **2 bare LF
  (mixed)**; `Makefile.ps1` 430 CRLF / 0 LF; `docker-compose.dev.override.yml` LF-only.
  `.pre-commit-config.yaml` runs **gitleaks only** — no lint, no EOL hook.
- `migrate` has **no** `volumes:` key in the dev override; `nginx` carries `media_volume` +
  `nginx.dev.conf` + `certs`; `web`, `bot`, `load_catalog`, `load_cities`, `create_admin`, `seed`
  all carry `.:/app`.

### Scope

| Semantic unit | Change |
|---|---|
| `scripts/verify-nginx-media-limits.ps1` (new) | the gate: static parse of the dev conf; container-state detection; live burst probe; settle probe; the four env overrides `NGINX_BURST` / `NGINX_SETTLE` / `NGINX_POLL_ATTEMPTS` / `NGINX_POLL_INTERVAL`; exit-code contract |
| `.ai/plans/21-…` (status header only) | mark BLOCK 1 shipped with the commit ref |

### Binding constraints

1. **Edit no nginx file.** `nginx.conf`, `nginx.dev.conf`, and both `docker-compose*.yml` files are
   out of scope. The gate *reports*; it does not remediate. If the conf fails the check, the gate
   exits non-zero and a human decides.
2. **Do not "fix" the image pin.** `nginx:1.30.5` is correct (09-API-016); `nginx:alpine` is the
   rollback value (§A.4 21-1).
3. **`/media/` must not be added to, moved, or renamed in any location block** — the do-not-touch
   conclusion stands even though P21's stated shadowing mechanism was wrong (§A.4 21-3). The
   correct rationale is that `/media/` shadows nothing and `limit_req_zone` is load-bearing via the
   `len(zones) == 4` census.
4. **Never pin line counts** in the script or its output — carry the qualitative CRLF hazard only
   (§A.4 21-2). A count assertion will drift on the next conf edit.
5. The script must be safe to run when the container is down: it reports and exits non-zero, it
   does **not** run `docker compose up`.
6. The script must never bring the container up. Bringing it up is an operator action (§A.4 21-8).
7. PowerShell 7+ syntax; English-only output; no `Write-Host` outside the deliberate report
   lines.
8. Reads only: no writes to conf, compose, `.env`, or the database.

### Acceptance criteria

1. Static parse of the dev conf succeeds and the script reports the 4 `limit_req_zone` census and
   the `/media/` `browse_limit` directive it found.
2. Run with the container **down** (the current reality): exits **non-zero** with a message that
   distinguishes "container present but not running" from "container absent" from "conf invalid".
   This path is agent-verifiable and must be demonstrated.
3. Run with the container **up** (operator action): burst probe exceeds the documented burst and is
   refused with 429; the settle probe then succeeds. **Operator-run — not agent-verifiable.**
4. The script's own deny path is agent-verifiable: an intentionally broken input (e.g. a bad
   `--conf` argument or an unreadable path) exits non-zero. Demonstrate it.
5. The four env overrides each demonstrably take effect (unset → documented default; set → the set
   value). Demonstrate with two of them; assert the mechanism for the other two.
6. Exit codes are distinct per outcome, and documented inside the script's help.
7. Running the script changes nothing: `git status` is byte-identical before and after.

### Rollback

Single new file. Rollback = delete it. Nothing else in the pass depends on its state at rest.

### DoD

- [ ] Script exists, is idempotent, and is read-only.
- [ ] **Verify, do not assume:** (i) the *actual* `browse_limit` rate and burst in
      `nginx.dev.conf` at this HEAD — this material establishes that `location /` carries
      `burst=40 nodelay` but does not enumerate every directive; (ii) whether `media_gate` in
      `apps/ads/views/listings.py` can serve 429 **before** nginx's `limit_req` is reached, which
      would make a 429 ambiguous on the dev stack too and force the script to say so; (iii) the
      container's exact stopped-state exit code and how `docker compose ps` reports it in this
      project name.
- [ ] Operator-only ACs (3) are **recorded as pending operator run**, not claimed.
- [ ] `git add scripts/verify-nginx-media-limits.ps1` — explicit path only.

---

## B-04 — P21 `Makefile.ps1` target, env overrides, help entry, settings comment refresh

| Field | Value |
|---|---|
| Source plan | P21 BLOCK 2, BLOCK 3 |
| Priority | **P1** |
| Risk | **Medium** — `Makefile.ps1` is a shared developer entry point, and this target introduces the **first** non-test exit-code propagation in the file |
| Depends on | **B-03** |
| Blocks | B-05 |
| Auditor | no |
| Researcher | no — all three idioms are established in the tree (`Invoke-Profile`, `Invoke-SeedPhotosValidate`, `Show-Help`) |
| Planner | no |
| Implementor | **yes** |
| Validator | **no** — the risk is bounded by copying two existing function shapes verbatim; a Validator adds latency without new information. Proportionality: the novel bit (exit propagation) is reviewed in B-05's Validator pass, which already covers the shared-entry-point surface |

### Objective

Add `Invoke-VerifyNginx` to `Makefile.ps1` with its `switch` arm, its `Show-Help` line and the four
env overrides; refresh the two stale comment blocks in `src/backend/config/settings/dev.py`.

### Verified starting state

- `Makefile.ps1::Invoke-VerifyNginx`, its `switch` arm, its `Show-Help` line and the
  `NGINX_BURST` / `NGINX_SETTLE` / `NGINX_POLL_ATTEMPTS` / `NGINX_POLL_INTERVAL` overrides —
  **all ABSENT**.
- `Invoke-Profile` is the env-override idiom: `$x = if ($env:X) { $env:X } else { "default" }`.
- `Invoke-SeedPhotosValidate` is the host-side-script precedent: **no compose project name, no
  container** — the same shape B-03's script has.
- `Show-Help` is `Write-Host "  <target>       <description>"`.
- Exit-code propagation exists **only** on `Invoke-Test` / `Invoke-TestAll` /
  `Invoke-TestRecreate`. `Invoke-VerifyNginx` would be the first non-test target to propagate it.
- Two stale comment blocks in `src/backend/config/settings/dev.py` **are present** — the one
  preceding `TRUSTED_PROXY_NETWORKS` and the one preceding `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX`.
- `test_dev_and_test_share_the_transport_tuple` pins **7** settings; `TRUSTED_PROXY_NETWORKS` is
  **not** among them (§A.4 21-11 — drop P21 §6.2 constraint 4).

### Scope

| Semantic unit | Change |
|---|---|
| `Makefile.ps1` — new `Invoke-VerifyNginx` function | env-override block, then host-side invocation of `scripts/verify-nginx-media-limits.ps1` |
| `Makefile.ps1` — `switch` block | new arm dispatching to `Invoke-VerifyNginx` |
| `Makefile.ps1` — `Show-Help` | one new line matching the existing `Write-Host "  <target>       <description>"` shape |
| `src/backend/config/settings/dev.py` — comment block preceding `TRUSTED_PROXY_NETWORKS` | comment text only |
| `src/backend/config/settings/dev.py` — comment block preceding `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX` | comment text only |
| `.ai/plans/21-…` (status header only) | mark BLOCK 2 and BLOCK 3 shipped |

### Binding constraints

1. **Comment-only in `settings/dev.py`.** No setting value, no `TRUSTED_PROXY_NETWORKS` content,
   no `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX` value change. If the comments are *wrong about
   behaviour*, the fix is wording, not config.
2. **Do not add a test** asserting `TRUSTED_PROXY_NETWORKS` in the transport tuple — P21 §6.2
   constraint 4 over-covers (§A.4 21-11).
3. `Invoke-VerifyNginx` must follow `Invoke-SeedPhotosValidate`: host-side, no compose project
   name, no container name. Do not introduce a compose invocation here.
4. The four overrides use the `Invoke-Profile` idiom verbatim; do not invent a second pattern.
5. `Show-Help` formatting is byte-compatible with the surrounding lines (same spacing, same
   quoting).
6. **Exit-code propagation is the novel element.** Copy the propagation idiom from
   `Invoke-Test` exactly, and record in the PR/DoD that a non-test target now propagates — future
   readers will look for the precedent.
7. Preserve `Makefile.ps1` line-ending reality (430 CRLF / 0 LF). The edit must not introduce bare
   LF; PowerShell tolerates both but a mixed file is a future diff hazard.
8. No other `Makefile.ps1` target may change behaviour.

### Acceptance criteria

1. `.\Makefile.ps1` with no argument lists the new target in `Show-Help`, formatted like its
   neighbours.
2. The `switch` arm dispatches to the new function, and the function is reachable.
3. With the container down, the target exits non-zero and propagates that exit code to the
   caller's `$LASTEXITCODE` — the first non-test target to do so.
4. Setting `NGINX_BURST` (and each of the other three in turn) changes the script's behaviour;
   unsetting falls back to the documented default.
5. `settings/dev.py`: `git diff` shows **only** comment lines changed; the module still imports
   and `test_dev_and_test_share_the_transport_tuple` still passes unchanged.
6. `git diff --stat Makefile.ps1` shows no whole-file rewrite (proves line endings preserved).

### Rollback

Revert the three files. No data, no schema, no container state. Because the target is additive and
unreferenced by any other target, revert is clean and total.

### DoD

- [ ] Target reachable, help line present, exit code propagated, overrides effective.
- [ ] `settings/dev.py` diff is comment-only — verified by inspecting the diff, not by asserting
      it.
- [ ] **Verify, do not assume:** (i) that no other `Makefile.ps1` arm shadows or intercepts the
      new target name; (ii) the exact `Invoke-Test` propagation idiom at this HEAD (do not copy
      from memory); (iii) whether `Show-Help` is generated or hand-written at this HEAD — if
      generated, the generated source must be edited instead.
- [ ] `git add Makefile.ps1 src/backend/config/settings/dev.py` — explicit paths only.

---

## B-05 — Documentation block: two runbooks + `docker-deployment.md` corrections (single doc owner)

| Field | Value |
|---|---|
| Source plan | P21 BLOCK 3 doc half, P22 BLOCK 7–8, P21 §OQ-4 (C3), P22 WI-4 |
| Priority | **P0** for the `docker-deployment.md` corrections (they are factually wrong today) |
| Risk | **Medium–High** — a 1591-line file already **over the 1000-line hard split threshold**, already **claimed by P20 BLOCK 10**, currently dirty in the working tree from another phase |
| Depends on | **B-01** (rate-limit wording), **B-02** (runbook accuracy), **B-03**, **B-04** (the two runbooks describe these surfaces) |
| Blocks | — |
| Auditor | no — every factual claim is already corrected in §A.4 |
| Researcher | no |
| Planner | **yes** — a 1591-line file past a hard threshold, with a fact-correction that must not become a rewrite; deciding *where* the correction lands (in place vs. a split section) is real design work |
| Implementor | **yes** |
| Validator | **yes** — the `docs/ops/*.md` sweep and the pinned-image test are automated but narrow; a Validator must confirm the sweep was actually exercised and that the P21/P22 content was not flattened into a lie about the deferrals |

### Objective

Land the documentation for the P21 and P22 gates and correct the two factually wrong passages in
`docs/ops/docker-deployment.md`, as a **single doc-owning block** so that one editor, one pass, one
reservation.

### Why one block rather than serialised P21 and P22 doc blocks

Both plans want `docs/ops/docker-deployment.md`, which is over the hard split threshold, already
claimed by P20 BLOCK 10, and dirty. Two doc blocks would mean two acquisitions of the same
reservation on a file that cannot absorb concurrent editors, and the two edits touch **adjacent**
regions (`### Rate Limiting` and the `**Bind-mount scope in dev:**` paragraph). Merging is chosen
because: (a) it collapses two file acquisitions into one, (b) the corrections are independent
prose fixes that share no semantics with either plan's gate, (c) the ordering constraint against
P20 BLOCK 10 is unchanged by merging, and (d) splitting would guarantee a second round-trip over
an already-expensive file for no isolation benefit. The risk this trades away — a larger single
review — is contained by the Validator pass and by the explicit scope table below.

### Verified starting state

- `docs/ops/dev-nginx-media-gate.md` — **ABSENT**.
- `docs/ops/ops-nginx-rate-limit-gate.md` — **ABSENT**.
- All three doc cross-links referenced by P21, and both by P22 — **ABSENT**.
- `docs/ops/docker-deployment.md` = **1591 lines**; `docs/00-overview/doc-maintenance-rules.md`
  threshold = **1000 hard / 800 soft**. P20 BLOCK 10 **already claims** it, append-only, and says so
  in its own Surface.
- Wrong today: `### Rate Limiting` says "**Three** `limit_req_zone`s" (truth: **four**) and its
  `/csp-report/` row reads `login_limit` 10 req/s (truth: `csp_report_limit`, 1r/s, burst=5, per
  09-API-015) — wrong in **two of six** rows. P22 WI-4's "keep byte-identical" would ratify this.
- Wrong today: the `**Bind-mount scope in dev:**` paragraph lists `nginx` as `.:/app`-bound, wrongly
  excludes `create_admin`, wrongly omits `load_cities`. Truth: `web`, `bot`, `load_catalog`,
  `load_cities`, `create_admin`, `seed` carry `.:/app`; `migrate` has **no** `volumes:` key; `nginx`
  carries `media_volume` + `nginx.dev.conf` + `certs`.
- `### Rate Limiting` lists **six** rows: `/login/`, `/csp-report/`, `/search/`, `/`, `/media/`,
  `/moderation/`.
- 🔴 `test_compose_contract.py::test_docker_deployment_table_quotes_the_pinned_images` parses this
  file, asserts the nginx row quotes exactly `nginx:1.30.5`, **and sweeps every `docs/ops/*.md`**
  asserting none restates `postgres:18-alpine`. Both new runbooks land inside that sweep.
  `test_compose_contract.py` also carries a `user:` rationale-table row.
- `docs/02-database/db-schema.md` and `docs/02-database/db-retention.md` "all four key columns"
  wording is **still accurate** — **this block must not touch them** (that check belongs to B-10).
- `docs/ops/rollback.md` uses `--env-file .env.prod` and states verbatim that no `.env.staging`
  exists and none should be invented.

### Scope

| Semantic unit | Change |
|---|---|
| `docs/ops/dev-nginx-media-gate.md` (new) | P21 gate runbook: what it verifies, the four env overrides, the exit-code contract, and an explicit **"operator must run `up -d nginx` first"** note |
| `docs/ops/ops-nginx-rate-limit-gate.md` (new) | P22 runbook: inputs, the B-01 criterion in plain language, PASS/VOID/FAIL meanings, the per-key/per-zone reading, and the **BLOCK 9 permanent deferral** stated as such |
| `docs/ops/docker-deployment.md` — `### Rate Limiting` | four zones, corrected `/csp-report/` row, six-row census, cross-link to the P22 runbook |
| `docs/ops/docker-deployment.md` — `**Bind-mount scope in dev:**` | corrected per 21-6 |
| `docs/ops/docker-deployment.md` — nginx row / pinned images | must quote exactly `nginx:1.30.5`; cross-link to the P21 runbook |
| the other two doc cross-links named by P21 | restore |
| `.ai/plans/21-…`, `.ai/plans/22-…` (status headers only) | mark the doc blocks shipped |

### Binding constraints

1. **One editor at a time.** This block acquires `docs/ops/docker-deployment.md`. P20 BLOCK 10 has
   **prior claim** — acquire only after it releases, and confirm the file is clean before starting
   (§C.3).
2. **Additive, in place.** The 1591-line file is past the hard threshold. This block **corrects
   existing passages in place** and adds cross-links; it **must not** start a split, a rewrite, or a
   reorganisation. A split is a separate plan with its own reservation.
3. **The two new runbooks must satisfy the `docs/ops/*.md` sweep** — no `postgres:18-alpine` string
   anywhere in them, and the nginx image quoted exactly as `nginx:1.30.5` where the pinned image is
   named at all.
4. **Do not ratify the wrong table.** P22 WI-4 constraint 1 ("byte-identical") is **rejected**
   (§A.4 22-D10). Correct the two wrong rows; keep the other four byte-stable.
5. **State both deferrals explicitly** — P21 BLOCK 4 (production config) and P22 BLOCK 9 (actual
   deployed measurement) are **permanent**, and the runbooks must not read as though the production
   path is covered.
6. **Do not claim the live paths are verified.** P21's runtime ACs need an operator to run
   `up -d nginx` (§A.4 21-8). The runbook says so.
7. `docs/ops/rollback.md` is **referenced, not edited** — it already carries the correct
   `.env.prod` guidance and the "do not invent `.env.staging`" instruction. Any new runbook that
   discusses staging must cite the current text.
8. Do not touch `docs/02-database/**` in this block.
9. English-only; no user-facing strings are added that need translations.

### Acceptance criteria

1. `test_docker_deployment_table_quotes_the_pinned_images` **passes**, and the Implementer has
   shown it exercised the sweep over both new files (not merely that it passed).
2. `### Rate Limiting` states four `limit_req_zone`s and its `/csp-report/` row names
   `csp_report_limit` at 1r/s burst=5. Six rows total.
3. The `**Bind-mount scope in dev:**` paragraph names exactly the six `.:/app` services, states that
   `migrate` has no `volumes:` key, and states that `nginx` carries `media_volume` +
   `nginx.dev.conf` + `certs` — and does **not** claim `nginx` is `.:/app`-bound.
4. The nginx row in the deployment table quotes exactly `nginx:1.30.5`; `nginx:alpine` appears, if
   at all, only as the rollback value.
5. Both new runbooks exist, are reachable from `docker-deployment.md`, and each states its
   deferral and its operator-run prerequisites.
6. File length after the edit is recorded; if it grew past the hard threshold it did **because** of
   the two cross-links, and that fact is stated in the DoD.
7. `docs/02-database/**` is byte-identical before and after.
8. `git status` shows no file outside the two new runbooks and the listed passages of
   `docker-deployment.md`.

### Rollback

Two new files (delete) plus prose corrections in one file (revert the passages). The block holds no
lock and leaves no partial state that other blocks depend on — B-02 and B-03 do not read these
docs at runtime. Rollback is safe and complete.

### DoD

- [ ] Corrections landed; both runbooks landed; sweep test green; deferrals stated.
- [ ] **Verify, do not assume:** (i) that P20 BLOCK 10 has released
      `docs/ops/docker-deployment.md` and the file is clean — **stop and report if not**;
      (ii) the actual current line count of `docker-deployment.md` (1591 is a point-in-time fact);
      (iii) that the `user:` rationale-table row in `test_compose_contract.py` is not contradicted
      by the bind-mount correction — the row and the paragraph must agree; (iv) that neither
      runbook accidentally restates `postgres:18-alpine`.
- [ ] Validator review confirms the deferrals are not overstated and the sweep was exercised.
- [ ] `git add docs/ops/dev-nginx-media-gate.md docs/ops/ops-nginx-rate-limit-gate.md
      docs/ops/docker-deployment.md` — explicit paths only, after confirming the file was clean
      before the edit.

---

## B-06 — P23 Phase 0: anti-drift guard with hard stop gate

| Field | Value |
|---|---|
| Source plan | P23 Phase 0 + §4 (confirmed by 23-2) |
| Priority | **P0** — everything P23 is gated on this |
| Risk | **High** — the block's purpose is to *prove a guard is load-bearing*; a passing result that should have failed is the worst outcome and the block has a STOP condition |
| Depends on | — |
| Blocks | B-07, B-08, B-09, B-10 |
| Auditor | **yes** — the STOP path needs diagnosis, not a retry: if the assertions do not go red, P23 §4's premise is wrong and the whole refactor's justification changes |
| Researcher | no |
| Planner | no |
| Implementor | **yes** |
| Validator | no — the scratch-mutation red/green cycle *is* the verification; a reviewer would be reviewing the experiment, not the result |

### Objective

Establish, **before** any production edit, that a new anti-drift guard actually goes red when the
key-column set drifts. Then leave the guard in place as the regression test the refactor will be
measured against.

### Verified starting state

- `TestKeyColumnsAntiDrift` in `apps/media/tests/test_references.py` has exactly **2** tests; the
  module has **6** test functions total.
- `KEY_COLUMNS` in `apps/media/services/references.py` is `Final[tuple[str, ...]]` of four literals.
- `src/backend/apps/media/storage_keys.py` does **not** exist.
- **Confirmed:** adding a 5th column + enum member leaves the existing relational test **GREEN** —
  i.e. the current guard is not load-bearing against the drift P23 is meant to prevent.

### Scope

| Semantic unit | Change |
|---|---|
| `apps/media/tests/test_references.py` — `TestKeyColumnsAntiDrift` | add the drift assertions that the current pair does not provide |
| `src/backend/conftest.py` or the test module — scratch-mutation harness | a **temporary, reverted** mutation used only to observe red; must not survive the block |
| `.ai/plans/23-key-columns-ownership.md` Phase 0 | record the guard design and the red/green observation |

### Hard stop gate

> Under the scratch mutation, **if the new assertions do not go red, STOP and report.** Do not
> proceed to B-07 … B-10. The guard would then not be load-bearing, §4's premise ("the drift claim
> is backwards") would be wrong, and the refactor's justification — that the guard protects the
> consolidation — collapses.

The scratch mutation must be applied to a **working copy** or reverted in the same step; the block
may not end with a mutated tree. Post the red/green transcript as evidence in the DoD.

### Binding constraints

1. **No production change in this block.** `references.py`, `ads/models.py`,
   `sweep_orphaned_media.py` and `listings.py` are untouched here. The guard must be written against
   the *current* inline literal, because the point is to show the current code drifts undetected.
2. The guard must assert against the **observable contract** (the set of key columns actually
   present on `AdImage`, and/or the index census), not against a copy of the tuple that a future
   edit could change in lockstep.
3. If the guard needs an enum member or a `storage_keys` symbol to be meaningful, express it as
   "absent until B-07 lands" rather than creating the symbol here — creating it here would make the
   guard pass for the wrong reason.
4. Do not create a second copy of `test_ad_image_delete_signal.py`; it lives under
   `apps/core/tests/` (§A.4 23-CORR C).
5. The scratch mutation is **not** a migration and must not touch the database.

### Acceptance criteria

1. With the tree unmutated, the new assertions are **GREEN**.
2. Under the scratch mutation (a 5th key column introduced at the source of truth), the new
   assertions are **RED**, and the failure message names the drift.
3. The tree is unmutated at block exit; `git status` shows only the intended test additions.
4. The pre-existing 6 test functions in the module still pass.
5. The red/green transcript is recorded in the DoD with the exact assertion names.
6. On the STOP path, the block reports which assumption failed and **does not** proceed.

### Rollback

Revert the test-module additions. The scratch mutation is reverted inside the block, so rollback is
a single-file revert. No data, no schema.

### DoD

- [ ] Red under mutation, green without, transcript recorded.
- [ ] **Verify, do not assume:** (i) that `TestKeyColumnsAntiDrift` still holds exactly 2 tests at
      the moment of editing — the count is a point-in-time fact; (ii) which of the module's 6 test
      functions is the "relational" one the material refers to — the Implementor must identify it
      by reading the module, not by name.
- [ ] `git add src/backend/apps/media/tests/test_references.py` — explicit path only.
- [ ] STOP condition stated as a possible, acceptable outcome of this block.

---

## B-07 — P23 Phase 1: create the single source of truth (`storage_keys`)

| Field | Value |
|---|---|
| Source plan | P23 Phase 1 |
| Priority | **P0** |
| Risk | **Medium** — additive module, two importers, no migration |
| Depends on | **B-06** |
| Blocks | B-08, B-09, B-10 |
| Auditor | no |
| Researcher | no |
| Planner | no |
| Implementor | **yes** |
| Validator | no — the guard from B-06 is the review mechanism |

### Objective

Move `KEY_COLUMNS` out of `apps/media/services/references.py` into a new leaf module
`src/backend/apps/media/storage_keys.py`, and **re-export** it from `references.py` so every
existing import path keeps working unedited.

**VOCABULARY ONLY. CONSTANT-ONLY. See binding constraint 1 — this is the block's whole risk.**

### Verified starting state

- `src/backend/apps/media/storage_keys.py` — does **not** exist.
- `KEY_COLUMNS` currently lives in `apps/media/services/references.py` as
  `Final[tuple[str, ...]] = ("image","thumbnail_small","thumbnail_medium","thumbnail_large")`.
- The only importers of `KEY_COLUMNS` tree-wide are `references.py` itself and
  `test_references.py` (whole-tree grep, confirmed).
- `AdImage.Meta.indexes` holds exactly **four** explicit `models.Index`, one per key column.
  `AdImage.sha256` has `db_index=True` and its implicit index is **absent** from `_meta.indexes` —
  `_meta.indexes` is **not** a total index enumeration.
- Precedent for a vocabulary leaf: `apps/media/schemas.py` declares itself a leaf that "imports
  only pydantic"; `apps/core/enums.py` imports Django and is still a cycle-free vocabulary leaf.

### Scope

| Semantic unit | Change |
|---|---|
| `src/backend/apps/media/storage_keys.py` (new) | `KEY_COLUMNS: Final[tuple[str, ...]]` and **nothing else**, plus the five-clause docstring contract P23 §6 specifies |
| `src/backend/apps/media/services/references.py` — `KEY_COLUMNS` declaration | **removed**; replaced by an import-and-re-export so `from apps.media.services.references import KEY_COLUMNS` keeps working |
| `src/backend/apps/media/services/references.py` — module docstring | update the duplication paragraph to name the new owner |
| `src/backend/apps/media/services/references.py` — `unreferenced_keys` body | **unchanged, byte-for-byte** — the inline four-arm `Q` chain and the `.values_list(*KEY_COLUMNS)` projection stay |
| `src/backend/apps/media/tests/test_references.py` | **must NOT be edited** — its unedited survival is the backwards-compatibility evidence |
| `.ai/plans/23-key-columns-ownership.md` Phase 1 | record shipped + commit ref |

### Binding constraints

1. **The leaf contains `KEY_COLUMNS: Final[tuple[str, ...]]` and NOTHING ELSE.** P23 §6
   *explicitly forbids* every one of the following, and this is an owner ruling, not an open design
   question — do **not** "improve" it:
   - **NO `StrEnum` of the column names.** P23 §6: *"any `StrEnum` of column names (rule 10 targets
     magic values and dicts; this is one ordered immutable tuple, and an enum would be the odd one
     out)."* Project rule 10 does **not** override this. An earlier draft of this plan proposed a
     StrEnum; that proposal is **REJECTED** and is recorded here so it is not re-proposed.
   - **NO helper function.** A `build_key_q()` is exactly the query-level unification P23's binding
     decision D1 rejects.
   - **NO `Q`, no queryset, no `AdImage` import, no `settings`/`MEDIA_ROOT`, no filesystem call.**
   - **NO `KEY_FORMAT_REGEX`** — that is a *different* vocabulary owned by
     `media/services/filesystem.py`; do not merge it.
   - **NO DTO field name** (`storage_key`) — that is `filesystem.key_fields`' vocabulary.
   - **NO size→column map** — deliberately excluded; one consumer, and the guard derives that
     relation from the model, not from a map.
2. **Zero `apps.*` imports in the leaf.** NOT zero imports — `django.*` and stdlib are permitted.
   Zero-imports would be the wrong invariant.
3. **No model access, no module-level side effects.**
4. **Re-export is mandatory.** Every current import path must keep working and the existing test
   must run **unmodified**. Do **not** update `test_references.py`'s import — its unedited survival
   is the evidence.
5. **Do not touch `services/__init__.py`** (its docstring scopes it to filesystem utilities; every
   call site imports by full path).
6. **Order must equal the current four-name order.** `unreferenced_keys` projects
   `.values_list(*KEY_COLUMNS)`; a reorder changes result-tuple semantics for existing callers, and
   `AdImage.storage_keys()` order is pinned by `apps/ads/tests/test_adimage_storage_keys.py` and by
   ordered-equality consumers in `apps/users/tests/test_deletion.py`.
7. **No migration, no dependency, no `AdImage.Meta` edit.**
8. No consumer conversion in this block — `references.py`'s inline `Q` chain,
   `AdImage.storage_keys()`, `sweep_orphaned_media.py`'s `fields` tuple and `media_gate`'s
   `key_q` are converted in B-08/B-09.

### Acceptance criteria

1. `storage_keys.py` contains **exactly one** module-level declaration — `KEY_COLUMNS` — and its
   values and order equal the current four literals. Nothing else is declared in it.
2. `apps/media/tests/test_references.py` runs **unmodified**: its existing import of `KEY_COLUMNS`
   from `apps.media.services.references` still resolves, and all 6 of its test functions pass.
3. `apps/core/tests/test_ad_image_delete_signal.py` (**NOT** `apps/media/tests/` — see §A.4 C) is
   green.
4. B-06's guard still passes.
5. `uv run ruff check` and `uv run basedpyright` clean on `storage_keys.py` and `references.py`.
6. **No consumer body was edited** — `unreferenced_keys` is byte-for-byte identical; only the
   constant's provenance changed.
7. A grep confirms **zero** `apps.*` imports in the new leaf.

### Rollback

Delete `storage_keys.py` and restore the `KEY_COLUMNS` declaration in `references.py`. The repo
returns to the pre-block state exactly; no data, no migration, no persisted artefacts.

### DoD

- [ ] Leaf holds `KEY_COLUMNS` and nothing else; zero `apps.*` imports.
- [ ] Five-clause docstring contract present per P23 §6: (1) owns the vocabulary, no predicate /
      no query / no filesystem / no model; (2) `references` owns the still-referenced predicate,
      `media_gate` owns its authorisation predicate, `sweep_orphaned_media` owns its census — **the
      three are semantically independent by design and must not be merged**, with both failure modes
      named (folding the authorisation filter makes unpublished/declined ads' images publicly
      readable; replacing the census with a candidate probe deletes every file outside the candidate
      list); (3) the tuple is deliberately duplicated from `AdImage` because the model carries no
      marker, and drift is guarded by named tests; (4) leaf invariants; (5) adding a key column is a
      multi-file change and **the tests are the tripwire**.
- [ ] **Verify, do not assume:** that `test_references.py` genuinely runs unmodified — read the
      diff, confirm the test module is not in it.
- [ ] `git add src/backend/apps/media/storage_keys.py src/backend/apps/media/services/references.py`
      — explicit paths only.

---

## B-08 — P23 Phase 2: convert the consumers (references, models, sweep command)

| Field | Value |
|---|---|
| Source plan | P23 Phase 2 — **Commit A (site 2) + Commit B (site 6)** |
| Priority | **P0** |
| Risk | **Medium** — two consumers; one is an operational sweep whose census/probe distinction is the block's real hazard |
| Depends on | **B-07** |
| Blocks | B-09, B-10 |
| Auditor | no — the facts are established; the risk is execution, not uncertainty |
| Researcher | no |
| Planner | no |
| Implementor | **yes** |
| Validator | **no** — B-06's guard plus the existing tests in the module, plus `test_ad_image_delete_signal.py` under `apps/core/tests/`, are the review surface |

### Objective

Make the **two** remaining non-`media_gate` consumers derive their column set from `KEY_COLUMNS`
instead of repeating four literals: `AdImage.storage_keys()` (site 6) and
`sweep_orphaned_media._collect_referenced_keys` (site 2).

> **TL CORRECTION — this block is TWO files, not three.** An earlier draft of this plan also listed
> `references.py::unreferenced_keys`'s inline `Q` chain. **That is wrong and must not be done.**
> P23 §5 Phase 1 says `unreferenced_keys`'s inline four-way `Q` *"stays inline, byte-for-byte
> unchanged"*; P23 §8 site 1 says the constant **moves** and the `Q` **stays inline**; P23 §9 lists
> *"no query unification at any level"* as a **non-goal**. Site 1 was completed by B-07 (the constant
> move). **Do not touch `unreferenced_keys` in this block.** See binding constraint 1.

### Verified starting state

- `apps/ads/models.py::AdImage.storage_keys()` — a **hardcoded literal**, preserving `cast` and a
  truthy filter, ordered as `KEY_COLUMNS`.
- `apps/media/management/commands/sweep_orphaned_media.py::_collect_referenced_keys` — local
  `fields = ("image","thumbnail_small","thumbnail_medium","thumbnail_large")` then
  `.values(*fields).iterator()`.
- `apps/media/services/references.py` — `KEY_COLUMNS` now imported-and-re-exported from
  `apps.media.storage_keys` (B-07). Its `unreferenced_keys` four-literal-arm `Q` chain and
  `.values_list(*KEY_COLUMNS)` projection are **untouched and stay that way**.
- 🔴 §A.4 23-CORR A: the census-vs-probe comment is **not** on `_collect_referenced_keys` (one-line
  docstring only). The load-bearing text lives in `_collect_dangling_keys` (the probe — "The join is
  load-bearing… 100% false positive on every seeded key (VAL-005)"), in `_collect_report_orphan_files`
  (the census), and in an inline comment in `Command.handle` above
  `orphans = on_disk - referenced`. **These three are the protection and they are already intact.**
- `media_gate` is **not** in this block — it is B-09.

### Scope

| Semantic unit | Change |
|---|---|
| `apps/ads/models.py::AdImage.storage_keys` | literal replaced by the derived column set; `cast` and the truthy filter **preserved**; order must equal `KEY_COLUMNS` |
| `apps/media/management/commands/sweep_orphaned_media.py::_collect_referenced_keys` | local `fields` tuple replaced by `KEY_COLUMNS`; `.values(*KEY_COLUMNS).iterator()` shape preserved |
| `apps/media/management/commands/sweep_orphaned_media.py::_collect_dangling_keys` | **comment text preserved byte-identical** — no edit |
| `apps/media/management/commands/sweep_orphaned_media.py::_collect_report_orphan_files` | **comment text preserved byte-identical** — no edit |
| `apps/media/management/commands/sweep_orphaned_media.py::Command.handle` | the inline comment above `orphans = on_disk - referenced` **preserved byte-identical** — no edit |
| `apps/media/services/references.py::unreferenced_keys` | **NO EDIT** — see the TL correction above and constraint 1 |
| `.ai/plans/23-key-columns-ownership.md` Phase 2 | record shipped + commit ref, and record Correction A |

### Binding constraints

1. **`references.py::unreferenced_keys` is NOT touched.** Its inline four-arm `Q` chain stays
   **byte-for-byte** as it is. P23's binding decision **D1** is CONSTANT-ONLY: share the vocabulary,
   let each site keep its own query shape verbatim. The residual visible four-way `Q` is
   *deliberately preferable* to an authorisation decision depending on a shared helper's default
   arguments. Do not "fix" this.
2. **Do not touch the three protective comments** in `sweep_orphaned_media.py`. They are the reason
   the sweep's census and probe are distinguishable, and they are the only thing preventing a
   **data-loss** mode (a candidate-filtered census would delete every file outside the candidate
   list). If the conversion cannot happen without disturbing them, the conversion moves; the comments
   do not.
3. **Do not "restore" a census-vs-probe comment onto `_collect_referenced_keys`** — P23's instruction
   was mis-aimed (§A.4 23-CORR A). Record the correction instead of acting on it.
4. **`AdImage.storage_keys` keeps `cast` and the truthy filter.** Two shipped tests pin both `None`
   and `""` as excluded; removing either changes behaviour at call sites outside this block.
5. **Order must equal `KEY_COLUMNS`.** It is pinned by `apps/ads/tests/test_adimage_storage_keys.py`
   (`test_fully_populated_row_storage_keys_matches_key_columns`) and by ordered-equality consumers in
   `apps/users/tests/test_deletion.py`.
6. **Verify the import direction.** `apps/ads/models.py` will import `apps.media.storage_keys`. The
   leaf has zero imports, so no cycle is possible — but confirm it rather than assume it, and confirm
   `apps.media` does not gain a dependency back on `apps.ads` through this path.
7. **No query-shape change.** `storage_keys()` keeps its list order; the sweep keeps `.values()`;
   nothing changes termination or row shape.
8. No change to the sweep's semantics, ordering, or `.iterator()` usage.
9. No new module — B-07 created the one that was needed.

### Acceptance criteria

1. A whole-tree grep for the four column literals finds no remaining repetition **outside**
   `apps/media/storage_keys.py` — **except** `media_gate` (B-09, still pending), `references.py`'s
   deliberate inline `Q` chain (D1, permanent), and test fixtures/assertions that intentionally pin
   values.
2. `AdImage.storage_keys()` returns the same sequence as before, with `cast` and the truthy filter
   intact.
3. `_collect_referenced_keys` yields the same keys; the sweep command's behaviour is unchanged.
4. `references.py` is **absent from the diff**.
5. The three protective comments are byte-identical — verify by inspection of `git diff`.
6. B-06's guard passes; `apps/media/tests/test_references.py` passes;
   `apps/core/tests/test_ad_image_delete_signal.py` passes;
   `apps/ads/tests/test_adimage_storage_keys.py` passes; `apps/users/tests/test_deletion.py` passes.
7. `uv run ruff check` and `uv run basedpyright` clean on all touched modules.

### Rollback

Revert three files. `storage_keys.py` stays (B-07 is a separate block and remains valid). No
migration, no data — the sweep is a read-only maintenance command.

### DoD

- [ ] Three consumers converted; three comments untouched; behaviour identical.
- [ ] **Verify, do not assume:** (i) the exact current body of `unreferenced_keys` and of
      `AdImage.storage_keys` — the material summarises them, not quotes them; (ii) that no fourth
      consumer exists (the grep in 23-4 is a point-in-time fact; re-run it);
      (iii) that the import of `apps.media.storage_keys` into `apps.ads.models` does not create a
      cycle; (iv) that the four-literal grep baseline in AC1 is stated in the DoD.
- [ ] `git add src/backend/apps/media/services/references.py src/backend/apps/ads/models.py
      src/backend/apps/media/management/commands/sweep_orphaned_media.py` — explicit paths only.

---

## B-09 — P23 Commit C: `media_gate` `key_q` conversion (ISOLATED commit, documented fallback)

| Field | Value |
|---|---|
| Source plan | P23 Phase 2 (Commit C) |
| Priority | **P1** — deliberately last of the P23 conversions so its fallout is isolated |
| Risk | **Medium–High** — it is the authorisation gate for media delivery; a conversion error is a security or availability defect |
| Depends on | **B-07** (needs `KEY_COLUMNS`); **B-08** (so the rest of the tree is already converted and this diff is the only one under review) |
| Blocks | — |
| Auditor | no |
| Researcher | no |
| Planner | no |
| Implementor | **yes** |
| Validator | **yes** — the only P23 block whose failure mode is "media stops serving" or "media serves without authorisation"; independent review of the query semantics is proportionate |

### Objective

Replace `media_gate`'s four literal `Q` arms in `apps/ads/views/listings.py` with a loop over
`KEY_COLUMNS`, remove the three now-unnecessary `# type: ignore[operator]` comments, and collapse
the two `.exists()` calls — **as an isolated commit**, with a documented fallback.

### Verified starting state

- `apps/ads/views/listings.py::media_gate` — `key_q` is four literal arms with **three**
  `# type: ignore[operator]` on the `thumbnail_*` arms, and **two** `.exists()` calls.
- Authorisation kwargs have **drifted** from P23 §2: they are now
  `account_state_q("ad__user__")` + `ad__status=AdStatus.PUBLISHED`, **not**
  `ad__user__is_declined=False`. P23 §2 is stale here (§A.4 23-1).
- 🔴 `reportUnnecessaryTypeIgnoreComment` is **OFF**; `reportOperatorIssue` is explicitly `"none"`
  in `pyproject.toml` alongside 5 others. basedpyright on `listings.py` today: 0
  errors/warnings/notes, despite 3 provably-unnecessary ignores. Repo-wide: 180 ignore comments,
  14 for `"none"` rules, none flagged. **Removal is safe and unobservable.**
- `media_gate` returns 200 / 403 / 404 / **429**; under `DEBUG=True` both success paths call
  `_serve_image(...)` → `FileResponse` and never set `X-Accel-Redirect` (from 22-2).
- B-01 and B-02 both reason about `media_gate`'s 429; B-05's runbook documents it.

### Isolated-commit requirement

This conversion is a **separate commit** from B-08. Reason: B-09 is the only P23 edit that can
break media delivery or media authorisation. A reviewer who must revert it must be able to do so
without reverting the harmless consolidation. If B-09 fails review, B-08 and B-07 stand on their
own.

### Documented fallback

> **If the loop conversion is judged unacceptable for readability**, leave the four literal arms
> exactly as they are and record an **explicit documented exclusion** naming
> `apps/ads/views/listings.py::media_gate` and the reason.

The fallback is a **success** for this block, not a failure. Sites 1, 2 and 6 still consolidate
(those are B-08's consumers plus the Phase 1 source of truth), and the plan does not fail. The
exclusion must be recorded in `.ai/plans/23-key-columns-ownership.md` and in B-06's guard, so that
the next reader knows `media_gate` is a **known, accepted** repetition rather than an oversight.

### Binding constraints

1. **Isolated commit.** No other file's change may be in it.
2. **The fallback is legitimate.** Do not force the loop. Do not mark the block failed for taking
   the fallback.
3. **The three `# type: ignore[operator]` removals produce no signal** — the rule is off
   (§A.4 23-CORR B). Do **not** wait for a typechecker to confirm; do **not** treat silence as a
   failure; do **not** enable `reportUnnecessaryTypeIgnoreComment` to get one.
4. Preserve the **current** authorisation kwargs verbatim: `account_state_q("ad__user__")` +
   `ad__status=AdStatus.PUBLISHED`. P23 §2's `ad__user__is_declined=False` is stale and must not
   be reintroduced.
5. Preserve the 200 / 403 / 404 / **429** response contract, including
   `rate_limited_response(json=False)` — B-01/B-02 depend on it.
6. The loop must not introduce an N+1. The two `.exists()` calls are called out for consolidation;
   collapsing them is in scope, un-collapsing them is not.
7. If the loop is used, the generated `Q` must be equivalent to the four literal `|`-ed arms, in
   the same column order.
8. No change to `_serve_image`, and no change to the `X-Accel-Redirect` decision.

### Acceptance criteria

1. With the loop: `media_gate`'s authorisation and existence semantics are unchanged — a declined
   user, a non-`PUBLISHED` ad, a missing key, and a throttled request each produce the same
   outcome as before.
2. The three `thumbnail_*` `# type: ignore[operator]` comments are gone and **no** ignore comment
   remains on the converted block.
3. The block's `git diff` touches only `apps/ads/views/listings.py`.
4. The existing `media_gate` tests pass, plus the 8-call-site behaviour is unchanged (B-01/B-02's
   model of the 429 path still holds).
5. If the fallback was taken: `media_gate` is byte-identical, and an explicit exclusion is recorded
   in P23 and referenced from B-06's guard.
6. `uv run basedpyright apps/ads/views/listings.py` reports 0 errors — and the Implementor records
   that this is **expected** rather than evidence of correctness.
7. Validator review signed off on query-semantics equivalence.

### Rollback

`git revert` the single commit. `media_gate` returns to the literal arms. Because the commit is
isolated, the revert is total and touches nothing else. No migration, no data, no persisted
artefact.

### DoD

- [ ] Isolated commit; semantics preserved; either loop-landed or exclusion documented.
- [ ] **Verify, do not assume:** (i) the current body of `key_q` and the two `.exists()` call sites
      at this HEAD; (ii) what `account_state_q` expands to, so equivalence can be argued rather than
      assumed; (iii) which `.exists()` the two calls correspond to and whether collapsing them
      changes the short-circuit order; (iv) that no **other** `# type: ignore` on `thumbnail_*` arms
      exists beyond the three named.
- [ ] The unobservable-removal point is stated in the commit message and the DoD.
- [ ] `git add src/backend/apps/ads/views/listings.py` — explicit path only, single commit.

---

## B-10 — P23 Phase 3: plan-20 target clause, and the db-schema/retention check

| Field | Value |
|---|---|
| Source plan | P23 Phase 3 |
| Priority | **P2** |
| Risk | **Low–Medium** — documentation and a plan-file clause; the only real hazard is staging another agent's uncommitted work |
| Depends on | **B-07**, **B-08**, **B-09** (or B-09's documented exclusion) |
| Blocks | — |
| Auditor | no |
| Researcher | no |
| Planner | no |
| Implementor | **yes** |
| Validator | no |

### Objective

Update the P23 target clause in `.ai/plans/20-media-remediation-execution.md` (clause **and** its
now-stale rationale), and **record** that `docs/02-database/db-schema.md` and
`docs/02-database/db-retention.md` were checked and need no change.

### Verified starting state

- The P23 Phase 3 target clause in `.ai/plans/20-media-remediation-execution.md` is **present
  verbatim**; its rationale — "BLOCKS 7, 8 and 10 have file edges on those modules" — is **stale**,
  because BLOCKS 7, 8 and 10 have all **shipped** (§A.4 23-CORR D).
- `.ai/plans/20-media-remediation-execution.md` is **modified uncommitted** (+1265/−27) by another
  agent's BLOCK 8 task, and is untracked-adjacent working-tree state that must be respected.
- `docs/02-database/db-schema.md` and `docs/02-database/db-retention.md` "all four key columns"
  wording is **still accurate** (confirmed).
- `AdImage.Meta.indexes` holds four explicit `models.Index`; `sha256`'s implicit index is absent
  from `_meta.indexes`.

### Scope

| Semantic unit | Change |
|---|---|
| `.ai/plans/20-media-remediation-execution.md` — the P23 Phase 3 target clause | clause retained or retired |
| `.ai/plans/20-media-remediation-execution.md` — the clause's rationale | **stale rationale corrected** — BLOCKS 7, 8, 10 have shipped |
| `docs/02-database/db-schema.md` | **no change** — the check is recorded, not applied |
| `docs/02-database/db-retention.md` | **no change** — the check is recorded, not applied |
| `.ai/plans/23-key-columns-ownership.md` Phase 3 | record: check performed, files unchanged, index census note |
| `src/backend/apps/media/tests/test_references.py` | only if the Phase 3 index-census assertion belongs with the guard |

### Binding constraints

1. 🔴 **Re-read `.ai/plans/20-media-remediation-execution.md` immediately before editing** — it is
   dirty with another agent's work. Then **stage only this one hunk**; never `git add` the file
   whole.
2. **Do not touch `src/backend/apps/users/services/deactivation.py` or
   `.kilo/commands/implement/implement-plan-multiagent.md`** — another agent owns them.
3. Do not add an index. The census is a fact to record, not a change to make. `sha256`'s implicit
   index is out of scope.
4. "Record the check" means: a dated line in P23 saying which two files were checked and that the
   wording is still accurate. Not a re-word, not a "clarification".
5. The `test_ad_image_delete_signal.py` correction is **already handled** — it lives under
   `apps/core/tests/`; do not create a second copy (§A.4 23-CORR C).
6. If B-09 took the documented fallback, this block records the exclusion's downstream effect on
   the Phase 3 wording.

### Acceptance criteria

1. The stale rationale no longer claims BLOCKS 7, 8 and 10 are pending.
2. Only the P23-related hunk of `.ai/plans/20-media-remediation-execution.md` is staged;
   `git diff --cached` shows no part of the other agent's BLOCK 8 work.
3. `git status` confirms the other agent's files remain modified-uncommitted and unstaged by this
   block.
4. `docs/02-database/db-schema.md` and `docs/02-database/db-retention.md` are byte-identical
   before and after.
5. P23's Phase 3 entry records the check, the outcome, and the index-census caveat.
6. No index, no column, and no migration is introduced.

### Rollback

Revert the plan-file hunk; nothing else changed. Because the file is dirty from another agent,
rollback must be a **hunk** revert, not a file revert — the Implementor must say so in the DoD or
the rollback will destroy someone else's work.

### DoD

- [ ] Clause and rationale updated; staged hunk is surgical; db docs untouched and recorded.
- [ ] **Verify, do not assume:** (i) the exact current text of the target clause and its rationale —
      the file is being actively edited by another agent, so "present verbatim" was true at
      `8fb2c0bc` and may no longer be; (ii) that the other agent's BLOCK 8 hunk is still unstaged
      when this block runs; (iii) whether B-09 landed the loop or the exclusion, since Phase 3's
      wording depends on it.
- [ ] `git add -p`-style hunk staging only. No `git add` of the whole file, no `-A`, no `.`.

---

## B-11 — P16 debt in `docs/99-agent/architecture.md` — ✅ **SHIPPED `52276d16`** (the "open product gate" framing below was WRONG)

> ### ⚠ TL CORRECTION (2026-10-05) — this block's central constraint was **inverted**
>
> This block originally required B-11 to record the ratification of `04-AUT-006` as **still
> outstanding**, and forbade recording the 2026-10-03 Product Owner decision. **That was wrong.**
> Plan 16 itself records that decision in at least four places (`G-10a`, the
> `### 🚧 PROPAGATION OBLIGATION` section, and `known_gaps_shipped`), and its propagation obligation
> *explicitly instructs* replacing the false sentence with **a record of the 2026-10-03 decision and
> its date**.
>
> Writing this block as originally specified would have shipped a **second false record** — one
> denying a ratification the repository documents. That is the same defect class the block exists to
> fix, and the Implementor correctly raised a HOLD on it, searched, and resolved it by following
> plan 16's own instruction **with attribution** rather than asserting the decision in its own voice.
>
> **What shipped:** the 2026-10-03 decision recorded **with attribution to plan 16**; the
> code-shipped / record-denial distinction preserved; write-triggered semantics and the `?lang=`
> exception stated; reversal cost recorded; `04-AUT-002` **not** claimed closed; and Debt 2's
> marker-sweep record added. **Constraints 1 and the AC2/AC6 language below are superseded by this
> ruling and were not applied.**

### (superseded — retained for provenance only) Objective

| Field | Value |
|---|---|
| Source plan | P16 `B-10` propagation obligation, `B-11` DoD, `B-02` i18n deferral |
| Priority | **P2** |
| Risk | **Medium** — a documentation block whose real risk is *silently resolving a product question* |
| Depends on | — |
| Blocks | — |
| Auditor | no — the facts are established; the open item is a product decision, which is not an audit finding |
| Researcher | no |
| Planner | **yes** — the constraint "record the contradiction, raise the gate, do not resolve it" needs precise phrasing so the document cannot be read as a decision |
| Implementor | **yes** |
| Validator | no — the failure mode (a resolved-looking gate) is checkable by reading the diff |

### Objective

Close the *documentable* parts of the P16 debt in `docs/99-agent/architecture.md`: record the
`B-11` tracker decision record, confirm the `B-02` i18n deferral pointer resolves, and — for
`B-10` — record the code-vs-document contradiction and raise the product-owner gate.

### Verified starting state

- `docs/99-agent/architecture.md` § *Session Lifetime Policy (04-AUT-006)* still reads
  *"**No product decision has been taken on the value.** … Do not record the finding as fixed."*
- `base.py` **ships** `SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 1209600 seconds (14 days)` +
  `SESSION_SAVE_EVERY_REQUEST = False`.
- This is a **direct contradiction** between shipped code and the record of the decision.
- `B-11`'s required tracker decision record citing §D item 14 (the phase-03 `EXT-`/`AUT-`/`SRH-`
  marker-sweep reservation) **does not exist anywhere**.
- **Plan 16's** `B-09` (`74848c69`) shipped **as the planned deferral** — it is closed, not outstanding.
- `create_admin_user.py` raises `_("Password does not meet the password policy: %(errors)s")` — a
  deliberate untranslated msgid with a comment pointing at a deferral recorded in
  `docs/99-agent/architecture.md`.

### Scope

| Semantic unit | Change |
|---|---|
| `docs/99-agent/architecture.md` § *Session Lifetime Policy (04-AUT-006)* | record that `base.py` ships 14 days; state explicitly that whether 14 days is the **ratified** value or must be **re-opened** is an **open product-owner gate**; name the owner and the decision required |
| `docs/99-agent/architecture.md` — `B-11` decision record | create the missing record citing §D item 14 |
| `docs/99-agent/architecture.md` — `B-02` i18n deferral | confirm the pointer resolves; add nothing if it already does |
| `.ai/plans/16-…` — status line for `B-10` | annotate as **gate open**, not shipped |

### Binding constraints

1. 🔴 **Do not resolve the product question.** Do not write "14 days is ratified". Do not write
   "the decision is 14 days". Do not remove the "no product decision has been taken" sentence —
   **replace it** with an accurate statement that the code ships a value while the ratification is
   outstanding. The §D item's instruction "Do not record the finding as fixed" is the reason.
2. The gate must be **nameable**: which owner, which question, what unblocks it.
3. `B-09` stays closed-as-deferral; do not reopen it.
4. Do not translate the `create_admin_user.py` msgid — the deferral is deliberate and recorded.
5. No change to `base.py` or any settings file. This block edits documentation only.
6. `04-AUT-002` remains **not closed** — do not touch it here (see B-12 for the record).

### Acceptance criteria

1. The architecture record and `base.py` no longer contradict each other **as documents**: the
   record states what the code ships and states that ratification is pending.
2. A reader cannot extract a product decision from the new text. The gate is stated as a question
   with a named owner.
3. The `B-11` decision record exists, cites §D item 14, and names the `EXT-`/`AUT-`/`SRH-`
   marker-sweep reservation.
4. The `B-02` deferral pointer resolves to an existing statement; if it already resolves, the block
   is a no-op on that passage and says so.
5. `git diff` shows documentation only — no `.py` file is touched.
6. The word "fixed" does not appear in connection with `04-AUT-006`.

### Rollback

Revert the documentation file. Nothing else depends on it at runtime.

### DoD

- [ ] Contradiction recorded, gate raised and nameable, `B-11` record created, i18n pointer checked.
- [ ] **Verify, do not assume:** (i) the current exact wording of the `04-AUT-006` passage — an
      Implementor must not paraphrase a prohibition into a permission; (ii) that the `B-02` deferral
      pointer actually resolves (if it does not, that is a finding, not an edit); (iii) whether a
      tracker record already exists under a different name before creating one.
- [ ] `git add docs/99-agent/architecture.md` — explicit path only.

---

## B-12 — P16 plan-currency corrections in `.ai/plans/16-…` (tracked file)

| Field | Value |
|---|---|
| Source plan | P16 §`B-06`, `B-07`, `B-08`, `B-10` prose |
| Priority | **P2** |
| Risk | **Low** mechanically, **Medium** in effect: the file is tracked, so the edit is a real reviewable change, and one of its current statements would authorise a **forbidden** test |
| Depends on | — |
| Blocks | — |
| Auditor | no |
| Researcher | no |
| Planner | no — the corrections are enumerated; no design remains |
| Implementor | **yes** |
| Validator | **yes** — a mis-stated correction here re-licenses writing a test the 2026-10-03 Product Owner ruling forbids, and a mis-stated count is indistinguishable from a guess. Independent read-back against the corrections table is proportionate. |

### Why this is a separate block from B-11

B-11 edits **`docs/99-agent/architecture.md`** — the *debt record*, the living system document, whose
change has downstream readers. B-12 edits **`.ai/plans/16-…`** — a *tracked historical plan file*,
whose change is a correction to a plan that is no longer being executed. Different files, different
audiences, different failure modes: B-11's risk is resolving a product question; B-12's risk is
re-authorising forbidden work. Merging them would put both risks in one unreviewable diff and give
B-11 a Validator it does not need. They are kept apart. Note the asymmetry: `docs/…/architecture.md`
is a system document whose debt persists, whereas `.ai/plans/21…25` are **untracked**, so editing
those is bookkeeping, not a reviewable change — which is why the P2x blocks in this plan touch their
source plans only for status lines.

### Objective

Correct the factually stale and actively misleading parts of P16 so the plan can no longer be
followed into harm.

### Verified starting state

- `B-06` section mandates `test_prod_requires_email_host` asserting `ImproperlyConfigured` — a shape
  **explicitly forbidden** by the 2026-10-03 Product Owner ruling (**09-API-009**). The shipped
  opposite is `test_prod_email_host_missing_warns_but_imports`, whose docstring states the
  inversion. P16 also names the **wrong path**: `config/settings/tests/test_password_recovery.py`;
  the actual path is `apps/users/tests/test_password_recovery.py`.
- `B-08`/`B-10` prose says `_TRANSPORT_SETTINGS` has **six** members; commit `a0bd928` made it
  **seven**.
- `B-07` known-gap tests 3 and 4 were **inverted** by `06-PII-109` / plan 18:
  `test_banned_seller_is_now_refused_the_dashboard` and
  `test_edit.py::TestBannedSellerRelistNowRefused`.
- `G-B` was **overturned** by phase 06 — `withdraw_consent_action` is now registered with
  `permissions=["delete"]`. `04-AUT-002` remains **not closed**.
- Stale nginx counts: 9 `limit_req_zone` in `nginx.conf` (match) but **7** in `nginx.dev.conf`
  (P16 says 6); **4** zones (P16 says 3); 11 / 9 `location` blocks (P16 says 10 / 7).
- `.ai/plans/16-auth-login-remediation-execution.md` is **tracked** — its edit is a real
  reviewable change, staged explicitly.

### Scope

| Semantic unit | Change |
|---|---|
| `.ai/plans/16-…` — the `B-06` section | replaced with a pointer to the 09-API-009 ruling, the shipped `test_prod_email_host_missing_warns_but_imports`, and the corrected path `apps/users/tests/test_password_recovery.py`; the forbidden-test mandate struck |
| `.ai/plans/16-…` — `B-07` known-gap tests 3 and 4 | corrected to the inverted, current test names |
| `.ai/plans/16-…` — `G-B` | marked overturned by phase 06, with `withdraw_consent_action`'s `permissions=["delete"]` noted; `04-AUT-002` marked still open |
| `.ai/plans/16-…` — `_TRANSPORT_SETTINGS` mentions in `B-08` / `B-10` | six → **seven** |
| `.ai/plans/16-…` — nginx counts | 6 → **7** (`nginx.dev.conf` zones); 3 → **4** (zones); 10/7 → **11/9** (`location` blocks) |

### Binding constraints

1. 🔴 **Write no test.** The block corrects the *plan*. Following P16 as written would write a
   **forbidden** test — that must become impossible to do by reading the file.
2. **Preserve the commit map** for all 11 blocks. The plan is a shipped record; the corrections are
   annotations, not a rewrite.
3. **Plan 16's** `B-09` shipped **as the planned deferral** — do not mark it as outstanding.
4. `04-AUT-002` stays open; it is not closed by this block.
5. Where a count is corrected, prefer citing the source (09-API-015 / the test that pins it) over
   restating a bare number — a bare corrected number drifts exactly like the original.
6. Edit only the plan file. No source, no test, no docs.

### Acceptance criteria

1. The file no longer mandates `test_prod_requires_email_host` or any `ImproperlyConfigured`
   assertion, and names the 09-API-009 ruling and the shipped opposite test.
2. The `B-06` path is `apps/users/tests/test_password_recovery.py`.
3. `_TRANSPORT_SETTINGS` is stated as **seven** everywhere it is mentioned.
4. The `B-07` known-gap entries name the current (inverted) tests; `G-B` is marked overturned;
   `04-AUT-002` is marked open.
5. The nginx counts read 9 / 7 `limit_req_zone`, 4 zones, 11 / 9 `location` blocks.
6. `git diff` on this block touches exactly one file and produces no test file.
7. A reader following the corrected plan end-to-end cannot be led into writing a forbidden test.

### Rollback

Revert one tracked file. No code, no data, no state.

### DoD

- [ ] All five corrections landed; no test written; commit map intact.
- [ ] **Verify, do not assume:** (i) that `test_prod_email_host_missing_warns_but_imports` still
      exists and still states the inversion at this HEAD; (ii) that `04-AUT-002` is still open;
      (iii) the current `_TRANSPORT_SETTINGS` member count from the file itself, not from this
      material; (iv) the current nginx counts, re-derived rather than copied from §A.4 — every
      count in this block is a point-in-time fact and re-deriving is the whole point of the
      correction.
- [ ] Validator read-back against the §A.4 corrections table.
- [ ] `git add .ai/plans/16-auth-login-remediation-execution.md` — explicit path only.

---

# §C Dependency graph, serial order, and shared-artefact reservations

## C.1 Dependency graph

```
                       B-01  P22 cross-check design (no Implementor)
                      /     \
                     v       v
                  B-02      |
                  P22 agg   |
                     |      |
   B-03  P21 script--+      |
     |              |      |
     v              |      |
   B-04  Makefile---+      |
     |                     |
     +----------+----------+
                v
              B-05  docs (single doc owner: 2 runbooks + docker-deployment.md)

   B-06  P23 guard  [HARD STOP GATE]
     |
     v
   B-07  storage_keys (source of truth)
     |
     v
   B-08  consumers: references / models / sweep
     |
     v
   B-09  media_gate  [ISOLATED commit, documented fallback]
     |
     v
   B-10  P23 Phase 3: plan-20 clause + db-docs check

   B-11  P16 debt in architecture.md        (independent)
   B-12  P16 plan-currency corrections     (independent)
```

Edges: `B-01 → B-02 → B-05`; `B-01 → B-05` (rate-limit wording must match the ratified criterion);
`B-03 → B-04 → B-05` (the runbooks describe surfaces that must exist); `B-06 → B-07 → B-08 → B-09 →
B-10`. `B-11` and `B-12` have no in-pass predecessor and no successor.

**Two disjoint chains.** The P21/P22 chain and the P23 chain do not share a file, a module, or a
risk. They are separated by the stop gate so that B-06's STOP does not block P21/P22 delivery, and so
that a P23 stall never delays a documentation correction.

## C.2 Serial order

| # | Block | Implementor | Why here |
|---|---|---|---|
| 1 | **B-01** | no | design gate; nothing else in P22 can be built without it |
| 2 | **B-02** | yes | high-risk decision engine, built immediately after its criterion |
| 3 | **B-03** | yes | medium-risk tooling; independent, so it absorbs the serial slot after the P22 risk peaks |
| 4 | **B-04** | yes | depends on B-03; the only shared-dev-entry-point edit |
| 5 | **B-05** | yes | **the most contended block** — placed after every P21/P22 surface it documents exists, and gated on the P20 BLOCK 10 release |
| 6 | **B-06** | yes | P23 gate; the STOP path must not delay the docs |
| 7 | **B-07** | yes | P23 source of truth |
| 8 | **B-08** | yes | three consumers, one reviewable diff |
| 9 | **B-09** | yes | isolated commit; last of the conversions so its diff is alone under review |
| 10 | **B-10** | yes | plan-file clause; depends on B-09's outcome (loop vs exclusion) |
| 11 | **B-11** | yes | independent debt record; runs late in case earlier blocks surfaced information bearing on it |
| 12 | **B-12** | yes | tracked-file correction; independent, Validator-gated |

**One Implementor at a time, no exceptions.** B-01 has no Implementor, which is why it does not
consume a slot.

## C.3 Shared-artefact reservation table

| File / artefact | Blocks touching it | Single owner | Ordering rule |
|---|---|---|---|
| `docs/ops/docker-deployment.md` | **B-05** (only, in-pass) · externally **P20 BLOCK 10** | **B-05** | B-05 acquires **only after P20 BLOCK 10 releases** and the file is clean. P20 has **prior claim** (declared in its own Surface as append-only). B-05 does not begin its edit while the file is dirty. 1591 lines vs a 1000-line hard threshold ⇒ in-place correction only, no split, no reorganisation. |
| `.ai/plans/20-media-remediation-execution.md` | **B-10** (only, in-pass) · externally **P20 BLOCK 8** | **B-10** | B-10 **re-reads immediately before editing** and stages **one hunk**. It never stages the file whole, so P20's uncommitted work stays unstaged and intact. Rollback is a **hunk** revert, not a file revert. |
| `apps/media/tests/test_references.py` | **B-06** (adds the guard), **B-07** (importer update if the export moves), **B-08** (guard re-verified), **B-10** (optional Phase 3 index-census assertion) | **B-06** (first write), then sequential hand-off | Strictly serial in the order B-06 → B-07 → B-08 → B-10. B-06 creates the guard; **every later block may only re-verify it or add to it** — none may weaken or rewrite B-06's assertions, because B-06's STOP condition depends on them staying load-bearing. B-10 is last because it needs B-09's outcome. |
| `Makefile.ps1` | **B-04** (only, in-pass) | **B-04** | No contention. The obligation is to preserve line endings (430 CRLF / 0 LF) and to add exactly one `switch` arm + one `Show-Help` line. |
| `docs/99-agent/architecture.md` | **B-11** (only, in-pass) | **B-11** | No contention. B-12 must **not** edit this file — if a correction appears to need it, that is a finding for B-11, not an edit. |
| `.ai/plans/16-auth-login-remediation-execution.md` | **B-12** (plan-currency) · **B-11** (one status annotation) | **B-12** | Contention is minimal but real: B-11 annotates the `B-10` status line, B-12 rewrites the `B-06`/`B-07`/`G-B` sections. **B-11 runs before B-12** so B-12 has the last word on the file's content. B-11's annotation must be phrased so B-12's edits cannot contradict it. |
| `docs/ops/rollback.md` | **B-05** (references only) · **B-01** (cites the corrected `.env.prod` text) | **none — read-only** | Neither block edits it. Both must cite its **current** text (`--env-file .env.prod`, and the verbatim "There is no `.env.staging` file…" + "Do not invent an `.env.staging` file."). If either finds it inconsistent, that is a **finding to report**, not an edit. |
| `.ai/plans/21-…` / `.ai/plans/22-…` / `.ai/plans/23-…` | B-01 … B-10 | the writing block, per §B | **Untracked.** Editing them is bookkeeping, not a reviewable change. Each block writes **only its own sections** plus a status line. No block rewrites another's section. |
| `.ai/plans/20-…` status, `deactivation.py`, `implement-plan-multiagent.md` | **nobody** | other agents | Explicitly out of bounds except for B-10's single hunk. |

---

# §D Risks, ranked, with containment

| Rank | Risk | Where | Containment |
|---|---|---|---|
| 1 | 🔴 **The P22 cross-check is implemented as written** — a VOID that fires on a healthy stack, i.e. a safety gate that teaches operators to ignore it | B-01, B-02 | B-01 is a **hard prerequisite**; B-02's constraint 1 makes substitution a **HOLD**, not a judgement call; B-02 AC1 tests the healthy-zero-rejection case explicitly; Validator reviews against the record |
| 2 | 🔴 **A doc block is started while `docs/ops/docker-deployment.md` is claimed/dirty by P20 BLOCK 10** → lost work or a conflicting merge | B-05 | Prior claim is respected; B-05 confirms the file is clean before editing and **stops and reports** if not; explicit-path staging only |
| 3 | 🔴 **B-10 stages another agent's uncommitted BLOCK 8 work** in `.ai/plans/20-…` | B-10 | Re-read immediately before edit; hunk staging only; `git diff --cached` verified to contain none of the other agent's work; rollback is a hunk revert |
| 4 | 🔴 **Someone follows P16 §`B-06` and writes the forbidden `ImproperlyConfigured` test** | B-12 | P16's mandate is struck; the 09-API-009 ruling and the shipped opposite test are named; the wrong path is corrected; constraint 1 forbids writing a test; Validator read-back |
| 5 | **B-06's guard does not go red** → the anti-drift test is decorative and P23's premise is wrong | B-06 | **HARD STOP GATE**; the block reports and the whole P23 chain halts; the stop is an accepted outcome, not a failure |
| 6 | **B-09's loop conversion regresses media authorisation or availability** | B-09 | **Isolated commit** so revert is total; authorisation kwargs pinned verbatim; response contract (200/403/404/429) pinned; **documented fallback** makes "leave it literal" a success; Validator review of query equivalence |
| 7 | **The `# type: ignore` removals are treated as unverified** and the Implementor enables `reportUnnecessaryTypeIgnoreComment` to get a signal, causing repo-wide noise | B-09 | Constraint 3 names all three failure modes; §A.4 23-CORR B records the empirical basis; AC6 requires recording that 0 errors is *expected* |
| 8 | **Line counts are pinned** in P21 material and drift on the next conf edit | B-03, B-12 | §A.4 21-2 narrows to the **qualitative** CRLF hazard; B-03 constraint 4 forbids count assertions; B-12 constraint 5 prefers citing the source over a bare number |
| 9 | **The two new runbooks break the `docs/ops/*.md` sweep** (`postgres:18-alpine` restated) or the pinned-nginx-image assertion | B-05 | AC1 requires the test green **and** evidence the sweep exercised the new files; constraint 3; Validator pass |
| 10 | **B-05's doc corrections become a ratifying edit** — documentation of the wrong rate-limit table and bind-mount scope would be written with authority and become new truth | B-05 | §A.4 22-D10 **rejects** P22's "byte-identical" constraint; AC2/AC3 state the corrected facts; the other four rows are held byte-stable so the correction stays auditable |
| 11 | **B-04's exit-code propagation is inconsistent** — the first non-test target to propagate sets a precedent future targets will guess at | B-04 | Constraint 6 requires copying `Invoke-Test`'s idiom exactly and **recording the precedent**; AC3/AC6 verify; covered by B-05's Validator pass |
| 12 | **Line endings mixed into `Makefile.ps1`** by an editing tool | B-04 | Constraint 7; AC6 checks `git diff --stat` for a whole-file rewrite. Note `nginx.dev.conf`'s 2 bare LF lines are **not** fixed in this pass — there is no EOL hook, and the fix would be a conf edit that B-03 forbids (§F.9) |
| 13 | **B-02's input contract is guessed** — log paths/fields for the deployed stack are not established in this material | B-02 | The block **stops and reports** if the contract cannot be established from the repo; no invented defaults |
| 14 | ~~**B-11 is read as having ratified the 14-day session lifetime**~~ | B-11 | **SUPERSEDED — the risk was inverted, not present.** The ratification **already existed** (plan 16, 2026-10-03); the real risk was a *false* record denying it. B-11 shipped the decision **with attribution to plan 16** in `52276d16`. |
| 15 | **Scope creep in P23** — an index is added, a column is added, or a shared `Q` helper is created | B-07, B-08, B-10 | B-07 constraints 3 and 7; B-08 constraint 5 (and the reason: `media_gate` has different authorisation kwargs); B-10 constraint 3; `sha256`'s implicit index explicitly out of scope in all three |
| 16 | **B-06's scratch mutation is left in the tree** | B-06 | Constraint: applied to a working copy or reverted in the same step; AC3 checks `git status` |
| 17 | **A stale count from §A.4 is copied verbatim into a source plan**, converting a point-in-time fact into new documentation | B-05, B-10, B-12 | Every DoD carries a "verify, do not assume" list naming the counts to re-derive; B-12 constraint 5 |
| 18 | **Over-agenting** — research or planning cycles spent on blocks whose uncertainty was already resolved in §A.4 | all | §B marks Auditor/Researcher/Planner "no" with a one-line reason in 9 of 12 blocks; agents are reserved for B-01 (A+R+P), B-05 (P), B-06 (A), B-11 (P) |

---

# §E Whole-set Definition of done

Applies to the pass as a whole, not to any single block.

1. **All 12 blocks are B-01 … B-12, executed in §C.2 order, one Implementor at a time.**
2. **No B-06 STOP occurred**, or the STOP was reported and the P23 chain (B-07 … B-10) was
   deliberately abandoned — in which case this DoD is met for B-01 … B-05, B-11, B-12 and the
   P23 omission is recorded in §F.
3. **No forbidden test was written.** `test_prod_requires_email_host` / `ImproperlyConfigured` does
   not exist, and P16 no longer mandates it.
4. **No nginx configuration file was modified.** `nginx.conf` and `nginx.dev.conf` are byte-identical
   to `8fb2c0bc`.
5. **No `docker-compose*.yml` image pin was changed.** `nginx:1.30.5` stands; `nginx:alpine` remains
   the rollback value only.
6. **`docs/ops/docker-deployment.md` states the truth** on the rate-limit table (four zones, six
   rows, corrected `/csp-report/` row) and the dev bind-mount scope (six `.:/app` services, `migrate`
   with no `volumes:`, `nginx` with `media_volume` + `nginx.dev.conf` + `certs`).
7. **The `docs/ops/*.md` sweep passes**, and both new runbooks are inside it.
8. **Both permanent deferrals are stated as permanent** in the runbooks: P21 BLOCK 4 (production
   config) and P22 BLOCK 9 (actual deployed measurement).
9. **`KEY_COLUMNS` has exactly one source of truth** (`apps/media/storage_keys.py`, which holds the
   `Final[tuple[str, ...]]` and nothing else — no `StrEnum`, no helper), and the whole-tree grep finds
   no remaining four-literal repetition outside it, except any B-09
   documented exclusion, which is recorded as an accepted exclusion.
10. **The three protective comments in `sweep_orphaned_media.py` are byte-identical** to `8fb2c0bc`.
11. **B-06's guard is proven load-bearing** — the red/green transcript exists.
12. **The session-lifetime record is no longer false.** `docs/99-agent/architecture.md` now carries the
    **2026-10-03 Product Owner decision** (attributed to plan 16) instead of the false "no product
    decision has been taken / do not record as fixed" text. `04-AUT-002` remains **NOT closed**.
13. **Every deferral in §F is recorded** with its re-entry condition, and nothing was silently
    dropped.
14. **Git hygiene:** every commit in this pass used `git add <explicit paths>`. No `-A`, no `.`, no
    `<dir>`, no `git reset`, `git checkout` or `git stash`. The other agents' modified-uncommitted
    files remain modified-uncommitted and unstaged.
15. **Every "verify, do not assume" item** in every block's DoD was either verified or reported as
    unverified. An Implementor who could not verify must have said so — silence is not verification.
16. **Fast test gate green** (`.\Makefile.ps1 test`) for any block touching Python; lint clean on every
    touched Python path; typecheck clean where the plan requires it — with B-09's "0 errors is
    expected" note explicitly understood as not being evidence of correctness.
17. **No file was created or modified other than those named in §B scope tables**, plus this plan.

---

# §F Deferred / not executable in this pass

Each entry names the reason and the **re-entry condition**. Nothing here is silently dropped; each
is a deliberate, recorded deferral.

## F.1 P21 BLOCK 4 — production nginx config

| Field | Value |
|---|---|
| Item | P21 BLOCK 4 — production nginx configuration |
| Status | **Permanent deferral** (as declared by P21) |
| Reason | The dev-override verification gate (B-03/B-04) and the production configuration are different targets with different blast radii. Applying the gate to production config from a dev-tooling pass would conflate a read-only dev check with a production change. Production config changes are not authorised by this pass. |
| Re-entry condition | A separate, explicitly authorised production-config plan whose scope is `nginx.conf` (not the dev override), that states who may change production limiting, and that begins by re-deriving the 4 `limit_req_zone` census and the `len(zones) == 4` pin (09-API-015) against the then-current `nginx.conf`. |
| Note | B-05's runbook states this deferral explicitly so the dev gate is not read as covering production. |

## F.2 P22 BLOCK 9 — actual deployed-stack measurement

| Field | Value |
|---|---|
| Item | P22 BLOCK 9 — a real run against the deployed stack |
| Status | **Permanent deferral** (as declared by P22) |
| Reason | The aggregator (B-02) needs log access to a deployed environment. No staging environment exists (`.env.staging` and `docker-compose.staging.yml` do not exist; `deploy.yml` has one job and no staging), and this pass has no production access. B-01's record additionally notes that the deployed stack's log sink and field set are **not established in the repository**, so the input contract cannot be asserted here. |
| Re-entry condition | A deployed environment with retrievable nginx access **and** error logs, plus a written statement of where those logs live and their field set. At that point B-01's option (c) — an nginx-side discriminator — can be evaluated properly, because only a real run can confirm whether the two channels are commensurable in practice. |
| Note | B-05's runbook states this deferral explicitly. |

## F.3 P21 runtime acceptance criteria — burst, settle, exit-0, script-deny

| Field | Value |
|---|---|
| Item | P21's live ACs: burst-limit path, settle path, the exit-0 "present but not running" path, and the script-deny path **as live demonstrations** |
| Status | **Operator-gated, not permanently deferred** |
| Reason | `mko-bazuna-dev-nginx-1` is `Exited (0)`, ~28 hours stale. An agent will not start it (that would change shared dev state and mask the exit-0 detection path). The exit-0 detection and the deny path **are** agent-verifiable; the burst and settle paths are not. |
| Re-entry condition | An operator runs `up -d nginx` in the `mko-bazuna-dev` project, then re-runs the target. Note that an HTTPS probe on :443 falls through to `location /` (there is no `/health/` and no `= /metrics` block in `nginx.dev.conf`) and therefore meets `browse_limit burst=40 nodelay` — the probe target must account for this. `ALLOWED_HOSTS` in `.env.dev` includes `localhost`. |

## F.4 P16 — the `04-AUT-006` session-lifetime product decision

| Field | Value |
|---|---|
| Item | ~~Whether 14 days is the ratified `SESSION_COOKIE_AGE`, or the value must be re-opened~~ |
| Status | ✅ **NOT a product-owner gate — the decision already existed. Resolved 2026-10-05.** |
| Reason | **This entry was wrong and is withdrawn.** Plan 16 (tracked, `86d2f0ce`) records a **Product Owner ruling dated 2026-10-03** that the lifetime is **14 days**, states the "owed product decision with a named owner" framing is **WITHDRAWN**, and instructs that `architecture.md` carry that decision and its date. It shipped in `52276d16`. **Decision:** `SESSION_COOKIE_AGE` = 14 days (`1209600` s), `SESSION_SAVE_EVERY_REQUEST = False`. |
| Re-entry condition | **None.** `04-AUT-006` is discharged. `04-AUT-002` (session *revocation*) is a **separate** item — see F.5 — and remains **NOT closed**. |
| Why the mistake happened | The gate was inferred from *"`docs/` does not contain a ratification"* — not from *the decision does not exist*. **Nothing in `docs/` carried it; a tracked plan file did.** **Rule: any future external gate must be established by searching the whole repository, including `.ai/plans/**`, not by searching the docs tree.** |

## F.5 P16 — `04-AUT-002`

| Field | Value |
|---|---|
| Item | `04-AUT-002` |
| Status | **Open, out of scope** |
| Reason | B-12 records that it remains not closed; B-11 explicitly does not touch it. `G-B` was overturned by phase 06 and the known-gap tests 3 and 4 were inverted by `06-PII-109` / plan 18, so the plan's original framing no longer describes reality — but closing `04-AUT-002` is a separate piece of work. |
| Re-entry condition | A re-statement of `04-AUT-002` against the post-phase-06 tree, with the `withdraw_consent_action` `permissions=["delete"]` registration taken into account. |

## F.6 P16 — every block's shipped implementation

| Field | Value |
|---|---|
| Item | All 11 P16 blocks' code work |
| Status | **Shipped — not re-planned** |
| Reason | **Plan 16's** `B-01`…`B-11` all have commits (§A.4). Its `B-09` shipped *as the planned deferral*. Nothing in this pass re-does, re-verifies, or re-opens shipped implementation work. |
| Re-entry condition | None for the code. Only the documentation debt (B-11) and plan currency (B-12) remain, and both are in-pass. |

## F.7 P23 — a 5th key column, an index for `sha256`, and any schema change

| Field | Value |
|---|---|
| Item | Adding a key column; adding an index for `AdImage.sha256`; any migration |
| Status | **Out of scope** |
| Reason | P23 is an **ownership** refactor of the existing four columns. The index census (`AdImage.Meta.indexes` holds exactly four explicit `models.Index`, one per key column, while `sha256`'s `db_index=True` index is absent from `_meta.indexes`) is a **fact to record**, not a defect to fix. No column is added, renamed, or reordered in any block. |
| Re-entry condition | A schema plan that states the new column's purpose, its index, the `KEY_COLUMNS` update, and the migration — with B-06's guard expected to go red first, which is precisely what B-06 establishes. |

## F.8 P22 option (c) — an nginx-side discriminator

| Field | Value |
|---|---|
| Item | Making the access and error channels separable, so a strict cross-check becomes true |
| Status | **Deferred to its own plan** |
| Reason | It requires changing shared config (`log_format main` in two nginx files) or production Python (`rate_limited_response`), and it interacts with the `docs/ops` pin sweep and the byte-exact burst-40 test pin. Smuggling it into a measurement-script plan would be a scope violation. |
| Re-entry condition | B-01's decision record names the concrete discriminator. It is evaluated only when a deployed measurement is possible (F.2) — because whether a discriminator *suffices* is an empirical question. |

## F.9 `nginx.dev.conf` mixed line endings (2 bare LF among 188 CRLF)

| Field | Value |
|---|---|
| Item | Normalising `nginx.dev.conf`'s line endings |
| Status | **Out of scope, recorded as a hazard** |
| Reason | Fixing it is a conf edit, which B-03 forbids, and it is not needed for either gate to work. `.pre-commit-config.yaml` runs **gitleaks only** — there is no EOL hook and no lint hook to catch it. |
| Re-entry condition | A conf-change pass that already has authority to edit `nginx.dev.conf`. Until then the **qualitative** hazard is carried in B-03's rationale only (§A.4 21-2) and no count is pinned anywhere. |

## F.10 The B-06 STOP path

| Field | Value |
|---|---|
| Item | P23 Phase 1–3 (B-07 … B-10) if the anti-drift guard does not go red under the scratch mutation |
| Status | **Conditional deferral** |
| Reason | If the guard is not load-bearing, P23 §4's premise is wrong and the consolidation's justification — that a single source of truth is protected against drift — collapses. Proceeding would be refactoring on a false premise. |
| Re-entry condition | Either the guard is made load-bearing and B-07 restarts from a clean tree, or P23 is re-audited to establish what *does* protect the four columns today. The STOP is a first-class outcome of B-06, not a block failure. |

---

**End of plan.** 12 blocks · one Implementor at a time · two disjoint dependency chains · 6 external
owners and deferrals recorded in §F · 1 unconditional hard stop (B-06) · 1 product-owner gate left
open on purpose (B-11) · 1 design decision left to B-01's research (the P22 cross-check criterion).
