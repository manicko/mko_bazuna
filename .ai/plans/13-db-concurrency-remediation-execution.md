---
plan_id: "13-db-concurrency-remediation-execution"
role: "execution plan"
source_plan: ".ai/plans/03-db-concurrency-remediation.md"
source_report: ".ai/audit/99-validation/03-db-concurrency-validated-findings.md"
code_context: ".ai/tmp/code-context-phase03-anchor-ba23277.md"
source_plan_anchor_commit: "4fd8bd0"
anchor_commit: "ba23277"
anchor_commit_at_write: "d14b9cc"
date: "2026-09-29"
planner: "Planner (subagent)"
status: "ready-for-execution"
blocks: 11
serial_order: "1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11"
implementor_concurrency: 1
---

# Execution Plan — Phase 03 Remediation (Database & Concurrency Consistency)

## 0. How to use this document

This is the **execution artifact** for
`.ai/plans/03-db-concurrency-remediation.md` (the *source plan*, 2674 lines, authored at
`4fd8bd0`). The source plan's analysis, options tables, gate definitions and risk register
are carried forward **corrected, not replaced**. This document adds what an execution plan
adds and the source plan does not contain:

1. the **anchor and drift section** (§1) — 18 documented plan-vs-tree disagreements plus 5
   further findings of this Planner's own, each with the correction an Implementor must apply;
2. the **11 execution blocks** (§2) in the serial order the source plan fixes, each with a
   roster decision re-confirmed against the tree, paste-ready agent briefs, a corrected
   Implementor task in `.ai/tasks/templates/task_template.yaml` shape, the corrected test
   surface, the exact Docker gate, and risk/rollback;
3. the **gate and escalation surface** (§3);
4. the **cross-block non-negotiables** (§4);
5. a **sequencing/status surface and a Definition of Done** (§5).

**Authority.** The tree at `ba23277` wins over the source plan and over the code context.
Where this document and the source plan disagree, this document is the execution instruction.

**PowerShell alias used throughout** (copy once per session):

```powershell
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
```

`--env-file .env.test` is required. Use `--project-name mko-bazuna-test`, never
`mko-bazuna-dev`. The test DB (`mko-bazuna-test-db-1`) is already up.

---

## 1. Anchor and drift

### 1.1 Anchor

| Item | Value |
|---|---|
| **Audit anchor commit** (the tree all of §1 was verified against) | **`ba23277`** — `fix(admin): make --password optional in create_admin_user with an ADMIN_PASSWORD fallback (CFG-003)` |
| **HEAD when this document was written** | **`d14b9cc`** — `docs(config-secrets): correct docs left stale by the phase 02 remediation blocks`. This landed **during** the authoring of this document; see **N-1**. Every symbol, test name, migration number and drift finding below was verified at `ba23277`, and `git diff ba23277 d14b9cc` touches **documentation only** — no phase-03 surface. |
| Source plan anchor | `4fd8bd0` |
| Commits landed since the source plan's anchor (`git log 4fd8bd0..HEAD`) | `ba23277`, `da399d7`, `d42f778`, `e57f8f8`, `6413df5` (all phase 02 code), `d14b9cc` (phase 02 docs) — 6 |
| `git diff --stat 4fd8bd0 ba23277` | 32 files, +1702/−117. No `.ai/`, no `submission.py`, no `login.py`, no `advisory_lock.py`, no `enums.py` except +1 line, no `DATABASES`. |
| Phase-03 work already landed | **None.** All 10 implemented findings are byte-for-byte where the source plan left them. |
| Working tree at `ba23277` | Dirty **by design**: 19 tracked `D` under `.ai/audit/**`; **5 tracked docs `M`** from an uncommitted phase-02 documentation pass (see **N-1**); untracked `.ai/plans/*`, `.ai/tmp/`, `staticfiles/`. Zero modified tracked **source** files. |
| Working tree at `d14b9cc` | 19 tracked `D` under `.ai/audit/**`; **docs now clean** (phase 02 committed them); untracked plans/temp. **A parallel phase moved HEAD while this document was being written** — re-read `git status --short` immediately before every commit, as §4 requires. |
| Static gates at the anchor | `uv run ruff check src/` → `All checks passed!`; `uv run basedpyright src/` → `0 errors, 0 warnings, 0 notes`. Both **green**; they must stay green. |
| Test DB | `mko-bazuna-test-db-1 Up (healthy) 0.0.0.0:5433->5432/tcp` |

### 1.2 Drift table — the 18 documented disagreements (`D-1` … `D-18`)

Every row below was **re-verified by this Planner against the tree at `ba23277`**, not
inherited on the code context's word. "Correction" is the instruction the Implementor applies.

| ID | What the source plan says | What the tree shows | **Correction Implementors must apply** |
|---|---|---|---|
| **D-1** | §0.2 / §5.3 / §6: *"18 members today; ID 10 reserved… IDs 13–99 are reserved for future scheduled jobs."* | `AdvisoryLockId` has **19** members. Phase 02 `6413df5` added **`REPAIR_BOT_USERNAME = 13`**. `advisory_lock.py`'s allocation table lists only **15** of the 19, and its closing sentence *"IDs 13-99 are reserved for future scheduled jobs"* is now **factually false**. New command `apps/core/management/commands/repair_bot_username.py` exists and is **not** in `test_sweep_lock_structure.py::SWEEP_COMMANDS` (still 13). `test_advisory_lock_ids.py::test_all_references_are_valid_members` is **one-way** (`referenced - valid_members`), so the drift is invisible to the suite. | **Never allocate ID 13.** Any new id starts at **14**. **BLOCK 2 additionally corrects** `advisory_lock.py`'s module docstring: add the missing transaction-scoped row `13 REPAIR_BOT_USERNAME  bot-username repair` and change the closing sentence to reserve **14–99**. BLOCK 7's `session is False` amendment stays constrained to `archive_sweep` and `recompute_normalized_prices`; the other **11** entries are untouched. Phase 03 allocates **no** new member. |
| **D-2** | BLOCK 9 `extra_context`: *"Do not revert phase 01's send_alerts idempotency work (**fbbb6cf**)."* Cited 4× in total. | `git show --stat fbbb6cf` → **`fix(scheduler): gate the daily set on a durable marker`**, touching `core/migrations/0005_scheduler_daily_state.py`, `core/models.py`, `core/services/scheduler_daily_state.py`, `core/utils/scheduler.py` + scheduler tests. It **never touched `send_alerts.py`**. The `send_alerts` artefacts are from `dc8aa8c` (`_DIGEST_AD_LIMIT` cap + the loss-window docstring) and `bddee42` (dry-run lock migration). | **Drop the hash from every task YAML and brief.** Re-anchor by **symbol**: `apps.core.utils.scheduler.SchedulerDailyMarker`, `apps.core.services.scheduler_daily_state`, `apps.search.management.commands.send_alerts.Command._DIGEST_AD_LIMIT`, and `send_alerts.Command.handle`'s loss-window docstring. **Never cite a commit hash as a task target or a constraint** — hash-anchored constraints survive nothing. |
| **D-3** | BLOCK 5: *"the **six** shipped concurrency tests"*; names 5 files + the invented placeholder *"the `test_ad_detail_queries`-adjacent locking guards"*. | The real set is **8 tests across 6 files** with `time.sleep(1.0)` row-lock holds: `ads/tests/test_edit_views_locking.py::TestEditViewsRowLockConcurrency` ×**3** (`:200`, `:256`, `:309`), `ads/tests/test_transition_concurrency.py` ×1, `core/tests/test_sweep_archive.py::TestArchiveSweepRowLockConcurrency`, `currencies/tests/test_recompute_command.py::TestRecomputeRowLockConcurrency`, `moderation/tests/test_admin_actions.py`, `telegram_bot/tests/test_unsubscribe.py`. `test_ad_detail_queries.py` has **no** locking test — it is a `CaptureQueriesContext` N+1 guard. | BLOCK 5's risk table, Researcher brief and Validator brief all say **eight tests / six files**. Add `test_edit_views_locking.py::TestEditViewsRowLockConcurrency` (the largest single contributor; `@pytest.mark.django_db(transaction=True) @slow @integration @concurrent`). **Delete the invented placeholder.** Exclude `core/tests/test_anon_lang_cache.py` (cache-TTL test, `time.sleep(1.1)`, not a row lock). |
| **D-4** | §1, §5.1, BLOCK 2, §8.4: `test_migrate_locked.py::TestSessionLockLogging::test_session_lock_logs_request_before_acquire`. | The class is **`TestSessionLockAcquisitionLog`**; the method name is **correct**. | Cite `src/backend/apps/core/tests/test_migrate_locked.py::TestSessionLockAcquisitionLog::test_session_lock_logs_request_before_acquire`. This is phase 01's hard regression guard for `ENT-006` — it must stay **green unchanged**. |
| **D-5** | BLOCK 9 file surface + YAML: *"src/backend/apps/ads/signals.py → the `post_save` receiver"*. | **`src/backend/apps/ads/signals.py` does not exist.** The gate is `src/backend/apps/moderation/signals.py::deliver_immediate_alerts_on_publish`, guarded by `getattr(settings, "IMMEDIATE_ALERTS_ENABLED", False)`, which calls `deliver_immediate_alerts(instance.id)`. Real gate test: `moderation/tests/test_approve_ad_side_effects.py` via `override_settings`. | BLOCK 9's file surface and YAML target `src/backend/apps/moderation/signals.py::deliver_immediate_alerts_on_publish`. The real BLOCK 9 gate test is `test_approve_ad_side_effects.py`. **Second half of D-5 is wrong — see N-2.** |
| **D-6** | §3.11 note 1 and BLOCK 11 `files:`: `src/telegram_bot/services/ad_data/orm.py` is a production citation holder. | That file has **zero** `DB-0\d\d` citations. Its only citation is in `src/telegram_bot/tests/test_create_draft_ad.py` (a test file). Two further test files the plan omits entirely: `src/telegram_bot/tests/test_ad_create.py`, `src/telegram_bot/tests/test_db_connection_middleware.py`. | **Remove `ad_data/orm.py` from BLOCK 11's `files:`.** Its citation, if in scope, lives in `test_create_draft_ad.py` — a test file. Add the two omitted test files to the test-file inventory (§1.3 N-5 defers the test sweep). |
| **D-7** | §3.11 / BLOCK 11: *"68 shipped citations across **26** files"*. | **68 matches / 27 files**: **8 production** (16 matches) + **19 test** (52 matches). Production set exactly: `apps/core/utils/advisory_lock.py` (3), `apps/moderation/admin_actions.py` (4), `apps/moderation/services/moderation_log.py` (4), `apps/ads/services/submission.py` (1), `apps/ads/views/edit.py` (1), `apps/ads/models.py` (1), `apps/core/management/commands/archive_sweep.py` (1), `apps/search/management/commands/send_alerts.py` (1). | BLOCK 11's scope numbers become **27 files**; its **production** target list is those **8**. The source plan's "worst case" claim is **confirmed verbatim**: `advisory_lock.py` cites this cycle's `DB-004`/`DB-010` three lines below a previous cycle's `DB-007` and beside a previous cycle's `DB-001`. See **N-5** for the scope shrink this drives. |
| **D-8** | BLOCK 6 + BLOCK 8 cite `test_orphan_file_deleted`, `test_ad_referenced_file_survives`, `test_seed_dir_is_excluded`, and name only one class. | Actual in `media/tests/test_sweep_orphaned_media.py`: `TestSweepOrphanedMedia::test_orphaned_file_is_deleted`, `::test_referenced_file_is_kept`, `::test_seed_subdir_excluded`; plus `TestSweepLockScope::test_delete_photo_called_within_lock_scope` in a **second class the BLOCK 8 YAML omits**. Also present and unnamed by the plan: `test_dry_run_is_nondestructive`, `test_delete_photo_routing`. | BLOCK 6 and BLOCK 8 use the **actual** names. BLOCK 8's `files:` gains `{ type: class, name: TestSweepLockScope }`. Unnamed tests listed above must stay green unchanged. |
| **D-9** | BLOCK 2 YAML: `replace_in_body` with `old: '"""Unit test for PII-002: transaction-scoped advisory lock release logging.'` anchored under the two **test functions**. | That string is the **module** docstring's first line, not any function body. Both tests exist, both `pytest.mark.unit`, **no DB marker**; both patch `apps.core.utils.advisory_lock.connection` and `...transaction.get_connection`. | Anchor the docstring rewrite at **module** scope (`{ type: module, name: test_advisory_lock_release_log }`), **not** under `replace_in_body`. The rewrite stays DB-free: the new rollback test raises a **real** exception inside the `with advisory_lock(...)` body (no mock) — the `try/finally` fires without a database. |
| **D-10** | BLOCK 5: *"an `ALLOWED_ENV_VARS` entry … `config/settings/tests/test_env_allowlist.py`"* — one parity test. | Phase 02 `e57f8f8` added a **second, larger** gate: `config/settings/tests/test_env_allowlist_reverse.py` (511 lines) — an AST scanner (`_EnvReadVisitor`, `_ScanResult`) that walks the tree for every `env(...)`/`env.*()`/`os.getenv` read and asserts each consumed name is allowlisted. 7 tests. | Any new `env("…")` in `base.py` must satisfy **both** files. The BLOCK 5 Option A gate command already runs `src/backend/config/settings/tests/` wholesale, so it is operationally covered — the *description* is what was wrong. Name both files in the Planner and Validator briefs. |
| **D-11** | §0.2 C-4 / BLOCK 3: 9 call expressions across 6 modules, *"of which 4 sit inside a caller-owned transaction"* … *"the other five are autocommit"*. | The 9/6 count is **exactly right**. The "five are autocommit" split is **not unconditionally true**: `apps/analytics/services/trust_analytics.py::record_trust_event` → its only production caller `apps/trust/services/trust_calculator.py::calculate_and_save`, which `auto_moderation._pass_moderation` calls **inside a nested `atomic()`** ⇒ a **savepoint** on the publish path, autocommit on seed / trust-recalculation paths. | BLOCK 3's call-graph table must mark `record_trust_event` as **conditional** (savepoint on the publish path). The fix in the same module therefore reaches the defect under **both** Q4 options. **Do not copy "five are autocommit" into a brief.** |
| **D-12** | §0.2 C-2 / C-3: `CONN_HEALTH_CHECKS` set nowhere; the discrete branch is dead in deployment; the first branch **replaces** `OPTIONS` wholesale. | **Exactly right, verbatim.** `base.py` `DATABASES`: branch 1 (`DATABASE_URL`) does `DATABASES["default"]["OPTIONS"] = {"prepare_threshold": None}`; branch 2 (discrete, dead in deployment) carries `CONN_MAX_AGE: 0` **and** `OPTIONS: {"prepare_threshold": None}`. `git diff 4fd8bd0 ba23277 -- base.py` does **not** touch `DATABASES`. `CONN_HEALTH_CHECKS` appears nowhere. | No correction to substance. Restate for BLOCK 5: **any new `OPTIONS` key goes in BOTH branches**, and a `?options=-c …` query parameter in `DATABASE_URL` is silently clobbered. Do **not** re-open `CONN_MAX_AGE` (phase 01 `ENT-010` Half B, rejected as intentional design). |
| **D-13** | §5.3: a new env var needs an `ALLOWED_ENV_VARS` entry + four template updates. | `ALLOWED_ENV_VARS` is a **grouped, commented `frozenset`**. Group "--- Python-consumed ---" contains `"IMMEDIATE_ALERTS_ENABLED"` and (new) `"RUN_TRANSLATION_BACKFILL"`. All four templates exist. `test_env_allowlist.py::test_bypass_flags_absent_from_env_templates` forbids `DJANGO_BUILD`/`DJANGO_ONESHOT` in `.env.example`/`.env.prod.example`. | BLOCK 5 Option A's new var goes in the **"Python-consumed"** group (read with `env.int(...)` in `base.py`) — the reverse AST test enforces that grouping. All four templates exist. **Never re-add the UTF-8 BOM** to `.env.example` (phase 02 removes it). |
| **D-14** | §0.2 / §5.3: model fields, `IX_ads_draft_sweep`, `uq_ads_single_draft_per_user`, migration numbering. | **Exactly right, re-derived.** `Ad.status` default `AdStatus.DRAFT`; `created_at` `auto_now_add=True`; `updated_at` `auto_now=True`; `IX_ads_draft_sweep` = `fields=["status","created_at"], condition=Q(status=DRAFT)`; `uq_ads_single_draft_per_user` is a **partial unique index** (`UniqueConstraint`), so `SET CONSTRAINTS` **cannot** defer it. Next numbers: `ads` → `0008_*`, `search` → `0003_*`, `core` → `0006_*` (phase 03 needs none), `media` → `0002_*`. | No correction to substance. Two Implementor-visible consequences: (a) BLOCK 3 must not attempt to defer `uq_ads_single_draft_per_user`; (b) **check each migration directory immediately before generating** — the numbers are correct *now* and may not be by BLOCK 9. |
| **D-15** | BLOCK 2 / BLOCK 7: `test_sweep_lock_structure.py` asserts `session is False` for all 13 lock-taking commands. | **Exactly right.** `SWEEP_COMMANDS` is a 13-tuple; `TestSweepLockOrdering::test_all_sweep_commands_lock_inside_transaction` is `django_db(transaction=True)`, asserts `len(lock_calls) == 13`, `in_atomic is True`, `session is False` ×13. `send_alerts` is driven **without** `--dry-run`. A second class `TestArchiveSweepPositivePath` follows. | No correction. BLOCK 2 leaves the assertion untouched. BLOCK 7's amendment is constrained to the **two** named entries; the other **11** must remain byte-identical. |
| **D-16** | BLOCK 1: remove `storage_keys` and `len(storage_keys)` from six commands. | In **five** of the six, `ad_ids = list(queryset.values_list("id", flat=True))` exists and feeds **only** the comprehension. `consent_hard_delete` uses `user_ids`, which additionally feeds two `UPDATE(...).update(user_id=None)` statements **and** the surviving log field. | BLOCK 1's `changes` must remove **`ad_ids` as well** from `sweep_drafts`, `delete_sweep`, `purge_failed_ads`, `purge_rejected_ads`, `purge_deleted_ads`. **`consent_hard_delete` keeps `user_ids`.** Verified per file at the anchor. |
| **D-17** | BLOCK 1: *"drop the `AdImage` import in each file where it becomes unused"*. | Per-file: five files carry `from apps.ads.models import Ad, AdImage` and must **narrow to `Ad`**. `consent_hard_delete.py` carries `from apps.ads.models import AdImage` **alone** (`Ad` is not imported at all) → **remove the whole line**; its scan uses `ad__user_id__in=user_ids`, a different field path. | Encode the per-file import outcome explicitly in BLOCK 1's YAML `changes` — five narrowings, one whole-line removal. Do not apply one mechanical edit to six files. |
| **D-18** | BLOCK 6 / BLOCK 8: `submit_ad` promotes media before `transaction.atomic()`; the bot error surface is in `ad_create`. | Confirmed verbatim. Ordered outline: (1) thumbnail generation **outside** any TX; (2) `move_staging_to_permanent(input.photos)`; (3) `with transaction.atomic():` → (a) `Ad.objects.select_for_update().get(id=input.ad_id)` with `except Ad.DoesNotExist: return False, ["Ad not found"]`; (h) `AdImageService.create_or_skip(...)`; (i) `ad.transition_to(ON_MODERATION)`; (j) deferred import of `auto_moderate`. Exactly **one** `select_for_update`, **no** advisory lock, never `SWEEP_ORPHANED_MEDIA`. The bot error surface is **`ad_create/submit.py::process_preview`**; `ad_create/preview.py::show_preview` is a **non-router render helper**. | BLOCK 8 targets step **2** relative to step **3**. BLOCK 6's error-surface target is **`submit.py::process_preview`** — **never** write `preview.py`. A BLOCK 5 Option B `SET LOCAL` must be placed **inside** the atomic and must not shift the atomic/`select_for_update` ordering that `test_edit_views_locking.py::TestEditViewsLocking` structurally pins (`source.count("select_for_update") == 1` in `ad_edit`; `submit_ad`'s `select_for_update` appears **after** `transaction.atomic`). |

### 1.3 Further findings of this Planner — beyond `D-1` … `D-18`

| ID | Finding | Evidence at `ba23277` | **Correction Implementors must apply** |
|---|---|---|---|
| **N-1** | **The working tree moved under this document's feet — proven, not theoretical.** At the audit anchor `ba23277`, five documentation files were modified in the working tree by an uncommitted phase-02 documentation pass: `docs/01-spec/architecture-structure.md`, `docs/02-database/db-schema.md`, `docs/99-agent/architecture.md`, `docs/99-agent/rules.md`, `docs/ops/docker-deployment.md`. **While this execution plan was being written, a parallel phase committed them in `d14b9cc`** (`docs(config-secrets): correct docs left stale by the phase 02 remediation blocks`), and HEAD moved `ba23277 → d14b9cc`. A new untracked plan (`15-authorization-remediation.md`) also appeared mid-authoring. | `git diff --stat -- docs` at `ba23277` → 5 files, +82/−17; `architecture.md`'s diff was entirely phase-02 content (the dual-direction allowlist gate, `config/settings/secret_validation.py`, the `EMAIL_BACKEND` pin). `git log` now shows `d14b9cc` on top of `ba23277`; `git status --short -- docs` is now empty. | The hazard is **confirmed to be live**, so the rule is not optional: **re-read `git status --short` immediately before every commit and stage explicit paths only** (§4.3). `d14b9cc` touches documentation only, so **no drift finding in §1.2 is invalidated** — but a block must never assume the tree it was planned against is the tree it will commit into. Combined with **N-3**, phase 03 no longer touches `docs/99-agent/architecture.md` at all, which removes the single worst instance of this hazard from BLOCK 6's surface. |
| **N-2** | **D-5's second claim is wrong.** `IMMEDIATE_ALERTS_ENABLED` is **present in all four** `.env.*.example` templates as `false` (`.env.example:77`, `.env.dev.example:68`, `.env.prod.example:62`, `.env.test.example:60`) and is in `ALLOWED_ENV_VARS` under the "Python-consumed" group. D-5 says it "appears in **no** `.env.*.example`". | Direct grep over the four templates + `base.py:367` and `base.py:33`. | The **conclusion** ("latent — the gate has never been enabled anywhere") **holds** and is in fact stronger: base default `False` + all four templates `false`. The **reason** in the source plan is wrong. BLOCK 9 must **not** add a template entry for this variable (it exists) and must **not** claim the flag is undocumented. |
| **N-3** | **BLOCK 6's DOC-UPDATE set is three files too wide.** `docs/01-spec/technical-specification.md:151` already says *"Abandoned draft auto-deleted on **idle** timeout (e.g. 30 min)"*; `docs/04-user-stories/seller-stories.md:39` already says *"idle timeout (~30 min)"*. **The code is the thing that deviates from the spec** — BLOCK 6 makes the code match those documents, so editing them is churn on shared files with no accuracy gain. `docs/99-agent/architecture.md` contains **no** draft-retention semantics section at all (its only hit is the `orm.py` helper table listing `create_draft_ad`). | `Select-String` over all three documents for `idle timeout`, `sweep_drafts`, `retention`, `DRAFT`. | **BLOCK 6's documentation surface is exactly two files:** `docs/02-database/db-retention.md` (the `sweep_drafts` row's *"Delete DRAFT ads **older than** 30 minutes"* is creation-age prose and **must** become inactivity prose) and `docs/02-database/db-indexes.md` (`fields=["status", "created_at"]` → `["status", "updated_at"]`). The `db-retention.md` sentence *"All retention values are hardcoded… no environment variables… are read for retention durations"* **stays true** (BLOCK 6 keeps 30 minutes) and is **not** an edit. Drop `technical-specification.md`, `seller-stories.md`, `architecture.md` from BLOCK 6. |
| **N-4** | **Plan number `13` is not free.** `.ai/plans/13-performance-remediation.md` already exists; the directory holds 01–14 with 13 present. | `Get-ChildItem .ai/plans`. | The instructed output path `13-db-concurrency-remediation-execution.md` does **not** collide (different slug) and has been honoured exactly as given. **The source plan is not renumbered.** If a future execution-plan series is produced for the same finding set, use a genuinely free number. |
| **N-5** | **BLOCK 11's scope should shrink from 27 files to 8.** | §5.2 of the source plan already assigns test-file concerns to phase 11 and states that phase 03 "must not expand them into new coverage". BLOCK 11 note 3 already ranks production files above test files. 19 of the 27 files are tests, and rewriting comments in files that **twelve other phases are writing against in parallel** is the block's largest process risk (§7's block-11 rows). | **BLOCK 11's default scope is the 8 production files** listed in D-7. The **19 test files are an explicitly optional second pass**, owned by phase 11. The **three this-cycle-polluted production citations remain non-negotiable under any option** — two are handled inside BLOCK 2, leaving `send_alerts.py` to BLOCK 11 or, on de-scope, to the coordinator. See §2.11. |

---

## 2. Execution blocks

**Standing rules (from §1 and §4, never re-derived per block).** Implementor is always
required, **exactly one at a time, strictly sequential**. Every block's gate runs through the
Docker `test` service — **never** `uv run pytest` locally (no DB on `localhost:5432`).
`PYTEST_SKIP_MARKERS=seed` is the default gate; no block touches seeding or image generation.
Never `git add -A` / `git add .` / `git commit -a` / `git reset` / `git checkout` / `git stash`
/ `git clean` — the tree is dirty by design (**N-1**). `.ai/audit/**` is unmodifiable by
mandate. No task target is ever a line number. One block = one commit, staged by explicit
path, re-reading `git status --short` immediately before staging.

---

### BLOCK 1 — Drop the redundant media-key pre-collection from six sweeps (`03-DB-011`)

| | |
|---|---|
| **Findings owned** | `03-DB-011` |
| **`depends_on`** | *(none)* — executes first |
| **Priority** | P0 |
| **Roster** | **Implementor, Validator** |

**Roster decision — CONFIRMED against the tree, unchanged from the source plan.**

- **Implementor — yes.** Always.
- **Auditor — no.** Re-checked at `ba23277`: all six `Command.handle` bodies are present and
  identical in shape, and **D-16/D-17 fully determine the per-file edit** (five `ad_ids`
  removals, five import narrowings, one whole-line import removal, `user_ids` retained). There
  is no investigative question left. Adding an Auditor here would be ceremony.
- **Researcher — no.** Pure removal of dead work; no external best-practice question.
- **Planner — no.** Six identical mechanical deletions plus six log-line edits. The plan's
  role here would be re-describing a list, not designing.
- **Validator — yes.** The claim being made is *"no behaviour change"*, and the absence of a
  regression is only established by an independent run of the six sweep suites **plus** the two
  media-deletion suites that pin "delete_photo runs exactly once".

**Grouping decision (carried forward).** `03-DB-011` is promoted from the report's rollout
position 10 to **first**: pure removal, no behaviour change, no test change, it **shortens**
the transaction every other sweep holds while its advisory lock is held (cheap risk reduction
for BLOCK 7), and it is the lowest-altitude change in the phase. BLOCK 6 then starts from a
shorter `sweep_drafts.Command.handle`.

**Agent briefs.** *Auditor / Researcher / Planner: not required.* **Implementor brief:**

> **Goal.** Remove, from each of six management commands, the `AdImage` storage-key
> pre-collection that runs inside the `transaction.atomic()` + `advisory_lock(...)` block, and
> drop its only consumer (`len(storage_keys)`) from the closing log line.
>
> **Hard constraints.** (1) `src/backend/conftest.py` is untouchable. (2) Physical media
> deletion stays exclusively `AdImage.pre_delete` → `transaction.on_commit()` →
> `delete_photo`; do **not** create a second deletion path. (3) `consent_hard_delete` **keeps**
> `user_ids` — it feeds two `UPDATE(...).update(user_id=None)` statements and its log field.
> (4) Do **not** replace `len(storage_keys)` with a live count query — that reintroduces the
> scan this block deletes. (5) Do **not** touch `sweep_drafts`'s *predicate*; that is BLOCK 6.
> (6) Stage explicit paths; never `git add -A`.
>
> **Exact files + symbols.**
> - `apps/core/management/commands/sweep_drafts.py::Command.handle` — delete `ad_ids` and
>   `storage_keys`; log becomes `"Deleted %d draft ads older than 30 minutes."`; import narrows
>   `from apps.ads.models import Ad, AdImage` → `from apps.ads.models import Ad`.
> - `…/delete_sweep.py::Command.handle` — same removals; log
>   `"Deleted %d ads with ARCHIVED status older than 60 days."` (two-line implicit concat).
> - `…/purge_failed_ads.py`, `…/purge_rejected_ads.py`, `…/purge_deleted_ads.py::Command.handle`
>   — same removals; keep their respective `ON_MODERATION_FAILED` / `REJECTED` / `DELETED`
>   windows verbatim; import narrows to `Ad`.
> - `…/consent_hard_delete.py::Command.handle` — delete `storage_keys` only; log becomes
>   `"Hard-deleted %d users (cascaded %d rows incl. ads/images) with consent revoked over 30 days ago."`
>   with args `len(user_ids), deleted_count`; **remove the whole import line**
>   `from apps.ads.models import AdImage` (`Ad` is not imported in this file).
> - Leave the *correct* explanatory comment ("Physical media deletion is handled by the
>   `AdImage` `pre_delete` signal via `transaction.on_commit()`") in place in every file.
>
> **Must return.** The changed file list; `git status --short` output taken immediately before
> staging; the six green suites named below; confirmation that no `storage_keys` or `ad_ids`
> reference survives in any of the six; the commit hash.

**Implementor task (`.ai/tasks/templates/task_template.yaml` shape).**

```yaml
id: task_03_b01_remove_storage_keys_precollection
title: Remove the redundant AdImage storage-key pre-collection from six sweep commands
priority: high
depends_on: []
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 1 — Drop the redundant media-key pre-collection from six sweeps (DB-011)"
extra_context: |
  CORRECTED AGAINST ba23277 (see execution plan 13 §1.2 D-16 and D-17).
  1. In FIVE of the six commands (sweep_drafts, delete_sweep, purge_failed_ads,
     purge_rejected_ads, purge_deleted_ads) a local `ad_ids = list(queryset.values_list("id",
     flat=True))` exists solely to feed the storage_keys comprehension and MUST be removed too.
  2. consent_hard_delete KEEPS `user_ids` — it feeds two UPDATE(...).update(user_id=None)
     statements and the surviving log field.
  3. Import handling is per-file, not mechanical: five files narrow
     `from apps.ads.models import Ad, AdImage` to `from apps.ads.models import Ad`;
     consent_hard_delete imports AdImage ALONE and the whole line is removed.
  Do NOT add a test. Do NOT edit src/backend/conftest.py. Do NOT change any predicate.

description: >
  In six management commands, delete the AdImage storage-key pre-collection that runs inside
  the transaction.atomic() + advisory_lock block before the cascade delete, together with the
  now-dead ad_ids local that only fed it, and drop len(storage_keys) from the closing log line.
  Physical media deletion is already handled by the AdImage pre_delete signal via
  transaction.on_commit() and must remain the only path.

goals:
  - remove six redundant full AdImage scans executed while the sweep lock and transaction are held
  - remove the five dead ad_ids locals that existed only to feed those scans
  - preserve the physical-deletion contract (AdImage pre_delete -> transaction.on_commit -> delete_photo)
  - preserve every other log field, including len(user_ids) in consent_hard_delete
  - no behaviour change and no test change

files:
  - path: src/backend/apps/core/management/commands/sweep_drafts.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: [{ type: assignment, value: "storage_keys = [" },
               { type: assignment, value: "ad_ids = list(queryset.values_list(\"id\", flat=True))" }]
  - path: src/backend/apps/core/management/commands/delete_sweep.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: [{ type: assignment, value: "storage_keys = [" },
               { type: assignment, value: "ad_ids = list(queryset.values_list(\"id\", flat=True))" }]
  - path: src/backend/apps/core/management/commands/purge_failed_ads.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: [{ type: assignment, value: "storage_keys = [" },
               { type: assignment, value: "ad_ids = list(queryset.values_list(\"id\", flat=True))" }]
  - path: src/backend/apps/core/management/commands/purge_rejected_ads.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: [{ type: assignment, value: "storage_keys = [" },
               { type: assignment, value: "ad_ids = list(queryset.values_list(\"id\", flat=True))" }]
  - path: src/backend/apps/core/management/commands/purge_deleted_ads.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: [{ type: assignment, value: "storage_keys = [" },
               { type: assignment, value: "ad_ids = list(queryset.values_list(\"id\", flat=True))" }]
  - path: src/backend/apps/core/management/commands/consent_hard_delete.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      delete: [{ type: assignment, value: "storage_keys = [" }]
      keep: [{ type: assignment, value: "user_ids = list(queryset.values_list(\"id\", flat=True))" }]

changes:
  - action: delete_code
    description: >
      Remove the storage_keys comprehension and its collection-site comment from each
      Command.handle, and remove the now-dead ad_ids local from the five commands that have
      one. Leave the correct "Physical media deletion is handled by the AdImage pre_delete
      signal via transaction.on_commit()" comment below the atomic block intact in all six.
  - action: edit_log_statement
    description: >
      Remove the " Removed %d media files." fragment and the len(storage_keys) argument from
      each closing logger.info. In consent_hard_delete keep len(user_ids) and deleted_count as
      the first two arguments.
    code_hint: |
      logger.info("Deleted %d draft ads older than 30 minutes.", deleted_count)
  - action: delete_import
    description: >
      Per file, not mechanically: narrow `from apps.ads.models import Ad, AdImage` to
      `from apps.ads.models import Ad` in sweep_drafts, delete_sweep, purge_failed_ads,
      purge_rejected_ads and purge_deleted_ads; remove the whole line
      `from apps.ads.models import AdImage` from consent_hard_delete (Ad is not imported
      there). Verify with `uv run ruff check src/` before committing.

acceptance_criteria:
  - no `storage_keys` reference remains in any of the six commands
  - no `ad_ids` local remains in the five commands that had one; `user_ids` still present in consent_hard_delete
  - the AdImage pre_delete -> transaction.on_commit -> delete_photo path is unchanged and
    delete_photo is still called exactly once per key
  - consent_hard_delete still logs len(user_ids) and deleted_count
  - no sweep predicate was modified (sweep_drafts keeps `created_at__lt`; BLOCK 6 owns it)
  - `uv run ruff check src/` exits 0 (no new F401) and `uv run basedpyright src/` reports 0 errors
  - the Docker gate below is green; no test file is modified; src/backend/conftest.py is unmodified
```

**Tests required.**

- *Must keep passing unchanged:* `src/backend/apps/core/tests/test_sweep_delete.py`,
  `test_sweep_drafts.py` (**all six**, including the three `created_at` back-dates that assert
  survival), `test_sweep_lock_structure.py`, `test_advisory_lock_ids.py`,
  `test_delete_photo_single_call.py`, `test_ad_image_delete_signal.py`, and the
  `purge_*` / `consent_hard_delete` suites.
- *Must be added:* **none.** This is the one block in the phase that needs no new test. A test
  asserting the *absence* of a variable tests trivia, not logic. Do **not** add one.
- *Must be changed:* **none.**

**Exact gate command (Docker only).**

```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/ src/backend/apps/ads/tests/" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk:* deleting an `AdImage` import that is still used (e.g. in a type annotation or a count).
  `ruff` catches it; read before deleting. **Risk:* applying one mechanical import edit to all
  six — `consent_hard_delete` needs the whole line gone.
- *Risk:* an Implementor "improves" the log line with a live count query, reintroducing the scan.
- *Risk:* touching `sweep_drafts`'s predicate here. That is BLOCK 6.
- *Rollback:* six independent, trivially revertible deletions. No schema, no contract, no
  persisted state.

---

### BLOCK 2 — Advisory-lock release log on the rollback path (`03-DB-010`)

| | |
|---|---|
| **Findings owned** | `03-DB-010`, plus this cycle's own ID re-citation in the same file, plus **the allocation-table correction from `D-1`** |
| **`depends_on`** | *(none)* |
| **Priority** | P1 |
| **Roster** | **Implementor, Validator** |

**Roster decision — CONFIRMED unchanged from the source plan, with one scope addition.**

- **Implementor — yes.** Always.
- **Auditor — no.** The function, the branch, the defect and the in-repo model to copy (the
  session branch's own `try/finally`) are all identified and were re-read at `ba23277`. The
  only consumer of the release-log message is the test file this block rewrites.
- **Researcher — no.** `try/finally` around a context-manager `yield` has no viable
  alternative here.
- **Planner — no.** Two edits in one function plus a test rewrite whose required shape is
  specified.
- **Validator — yes.** The block **rewrites two shipped green tests that currently pin the
  defective mechanism** and changes a primitive used by **13** commands.

**Scope addition (new, driven by `D-1`).** `advisory_lock.py`'s module-docstring lock
**allocation table** is now factually false: it lists 15 of 19 ids and its closing sentence
claims *"IDs 13-99 are reserved"* while `REPAIR_BOT_USERNAME = 13` exists. The source plan
defers this to BLOCK 11; this execution plan moves the **table row + reserved-range sentence**
into **BLOCK 2**, because (a) BLOCK 2 opens this file anyway, (b) the false sentence sits
three lines below a citation BLOCK 2 already edits, and (c) `test_advisory_lock_ids.py` is
one-way so nothing catches the drift. **The legacy `DB-001`/`DB-007` citation *text* remains
BLOCK 11's** and must not be rewritten here.

**Agent briefs.** *Auditor / Researcher / Planner: not required.* **Implementor brief:**

> **Goal.** Make the transaction-scoped branch log its release on **every** exit, not only on
> commit, and correct the file's now-false lock-allocation table.
>
> **Hard constraints.** (1) **Lock behaviour must not change** — `pg_advisory_xact_lock`
> releases on commit *and* rollback. (2) Copy **only** `try:` / `finally:` / the `logger.info`
> from the session branch — **never** `pg_advisory_unlock`, which would be a behaviour change
> and an extra round-trip for 13 commands. (3) **Do not touch the session branch** (phase 01
> `ENT-006` shipped it). (4) **Do not rewrite the legacy `DB-001` / `DB-007` citations** —
> that is BLOCK 11. (5) Cycle-scope only this cycle's own ids (`03-DB-00N` form).
> (6) Stage explicit paths.
>
> **Exact files + symbols.**
> - `src/backend/apps/core/utils/advisory_lock.py::advisory_lock` — replace the
>   `transaction.on_commit(lambda: logger.info("Released transaction advisory lock %s", …))`
>   registration + bare `yield` in the `session=False` branch with
>   `try: yield finally: logger.info("Released transaction advisory lock %s", lock_id)`.
> - same file, **module docstring** — add the transaction-scoped row
>   `13  REPAIR_BOT_USERNAME         bot-username repair`; change the closing sentence to
>   reserve **14-99**; keep `ID 10 is intentionally unused/reserved`.
> - same file, inline comment in the session branch — normalise this cycle's citations:
>   `# (see DB-010) and phase 03's DB-004 owns any timeout wording.` → cycle-scoped
>   `# (see a previous cycle's DB-010) and phase 03 DB-004 owns any timeout wording.`
> - `src/backend/apps/core/tests/test_advisory_lock_release_log.py` — **module** docstring plus
>   the two tests (see below).
> - `src/backend/apps/core/tests/test_sweep_lock_structure.py::TestSweepLockOrdering::
>   test_all_sweep_commands_lock_inside_transaction` — **do not edit**; it must keep passing.
>
> **Test rewrite (D-9 corrected — module docstring, not an in-body anchor).** Both tests are
> `pytest.mark.unit` with **no DB marker**; the rewrite stays DB-free.
> (a) Replace `test_transaction_scoped_lock_logs_release_on_commit` with a normal-exit test
> asserting both the "Acquired" and "Released" lines; **no `on_commit` patch** — the `finally`
> fires without a database.
> (b) Replace `test_transaction_scoped_lock_registers_on_commit_callback` with a **rollback**
> test: raise a **real** exception inside the `with advisory_lock(...)` body, assert the
> exception **propagates to the caller**, and assert the "Released transaction advisory lock"
> line is present in the log. This test must be demonstrated **RED against the pre-fix code**.
> A test that only asserts (a) reproduces the finding's blind spot and proves nothing.
> (c) Rewrite the module docstring — it currently states the defective contract as intended
> (*"The on_commit callback fires only on successful commit — matching when
> `pg_advisory_xact_lock` releases the lock."*).
>
> **Must return.** The changed file list; `git status --short` immediately before staging;
> proof that the rollback test was red before the fix; the green
> `TestSessionLockAcquisitionLog` result; the commit hash.

**Implementor task.**

```yaml
id: task_03_b02_advisory_lock_release_log
title: Log the transaction-scoped advisory-lock release from a finally block, not from on_commit
priority: high
depends_on: []
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 2 — Advisory-lock release log on the rollback path (DB-010)"
extra_context: |
  CORRECTED AGAINST ba23277 (execution plan 13 §1.2 D-1, D-2, D-4, D-9, D-15).
  1. The module-docstring lock-allocation table is FALSE: it lists 15 of 19 ids and its
     closing sentence claims "IDs 13-99 are reserved" while REPAIR_BOT_USERNAME = 13 exists.
     Correct it here — the file is open anyway. NEVER allocate id 13; any new id starts at 14.
  2. Phase 01's regression guard is test_migrate_locked.py::TestSessionLockAcquisitionLog
     (NOT TestSessionLockLogging). It must pass unchanged.
  3. The docstring to rewrite is the MODULE docstring, not a function body.
  4. Cycle-scope this cycle's own ids to the 03-DB-00N form. Do NOT rewrite the legacy
     DB-001 / DB-007 citations — that is BLOCK 11.

description: >
  In advisory_lock(), the session=False branch registers its release log via
  transaction.on_commit, so the line is emitted only when the sweep succeeded and is omitted
  precisely when an operator needs it. Wrap the body in try/finally and log the release from
  the finally, mirroring the session branch. Lock behaviour must not change. Separately,
  correct the module docstring's now-incomplete lock-allocation table.

goals:
  - emit the release log on both commit and rollback
  - leave pg_advisory_xact_lock acquisition and the RuntimeError guard untouched
  - leave the session branch untouched (phase 01 ENT-006 residual shipped there)
  - make the module docstring's lock-allocation table match AdvisoryLockId exactly
  - normalise this cycle's own ID citations in the same file to the 03-DB-00N form

files:
  - path: src/backend/apps/core/utils/advisory_lock.py
    targets:
      - { type: function, name: advisory_lock }
      - { type: module, name: advisory_lock }
    semantic_anchors:
      replace_in_body:
        old: |
          transaction.on_commit(
              lambda: logger.info("Released transaction advisory lock %s", lock_id)
          )
          yield
        new: |
          try:
              yield
          finally:
              logger.info("Released transaction advisory lock %s", lock_id)
      replace_in_body:
        old: "to prevent the autocommit-release bug (DB-001)."
        new: "to prevent the autocommit-release bug (a previous cycle's DB-001)."
      replace_in_body:
        old: "was removed in DB-007. IDs 13-99 are reserved for future scheduled jobs."
        new: "was removed in DB-007 (a previous cycle's). IDs 14-99 are reserved for future scheduled jobs."
      replace_in_body:
        old: "# (see DB-010) and phase 03's DB-004 owns any timeout wording."
        new: "# (see a previous cycle's DB-010) and phase 03 DB-004 owns any timeout wording."
  - path: src/backend/apps/core/tests/test_advisory_lock_release_log.py
    targets:
      - { type: module,   name: test_advisory_lock_release_log }
      - { type: function, name: test_transaction_scoped_lock_logs_release_on_commit }
      - { type: function, name: test_transaction_scoped_lock_registers_on_commit_callback }
    semantic_anchors:
      replace:
        old: |
          """
          Unit test for PII-002: transaction-scoped advisory lock release logging.
        new: |
          """
          Unit test for the transaction-scoped advisory-lock release log.
  - path: src/backend/apps/core/utils/advisory_lock.py
    targets: [{ type: module, name: advisory_lock }]
    semantic_anchors:
      insert_after:
        type: comment_line
        value: "12  RECOMPUTE_NORMALIZED_PRICES  price normalization"
  - path: src/backend/apps/core/tests/test_sweep_lock_structure.py
    targets: [{ type: function, name: test_all_sweep_commands_lock_inside_transaction }]
    semantic_anchors: {}   # assertion must keep passing unchanged; DO NOT EDIT

changes:
  - action: edit_code
    description: >
      Replace the on_commit release registration in the session=False branch with a
      try/finally around the yield, logging the release from the finally. Do NOT add
      pg_advisory_unlock — a transaction-scoped lock releases with the transaction.
  - action: add_code
    description: >
      Add the missing transaction-scoped row `13  REPAIR_BOT_USERNAME  bot-username repair`
      to the module docstring's lock-allocation table and change the closing reserved-range
      sentence from 13-99 to 14-99. Do not add any new AdvisoryLockId member.
  - action: edit_comment
    description: >
      Cycle-scope this cycle's own citations in this file to the 03-DB-00N form. Do NOT
      rewrite the legacy DB-001 / DB-007 citation text — BLOCK 11 owns that.
  - action: rewrite_test
    description: >
      Replace the two on_commit-shaped tests with (a) a release-logged-on-normal-exit test and
      (b) a release-logged-on-rollback test that raises a REAL exception inside the context
      manager, asserts the exception propagates, and asserts the release line is in the log.
      Neither test may patch transaction.on_commit any more. Rewrite the MODULE docstring,
      which today states the defective contract as intended.

acceptance_criteria:
  - the release line is emitted when the body raises (the case that is currently silent), and
    the exception still propagates to the caller
  - the release line is still emitted on the normal path
  - pg_advisory_xact_lock is still issued exactly once and NO pg_advisory_unlock is added to
    the transaction branch
  - advisory_lock still raises RuntimeError outside an atomic block (unchanged)
  - AdvisoryLockId gained no new member; the module docstring table lists all 19 ids
  - test_sweep_lock_structure.py passes unchanged, including its `session is False` assertion
    for all 13 commands
  - test_migrate_locked.py::TestSessionLockAcquisitionLog passes unchanged
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - the Docker gate below is green
```

**Tests required.**

- *Must keep passing unchanged:* all of `test_sweep_lock_structure.py`; `test_migrate_locked.py`;
  `test_advisory_lock_ids.py`; **all 13** lock-taking command suites.
- *Must be changed (rewritten, not deleted):* the two named tests in
  `test_advisory_lock_release_log.py`. The rollback case **must be demonstrated RED against
  the pre-fix code** while the current `on_commit` registration is in place.
- *Must be added:* none beyond the rewrite. The log message text itself needs no test.

**Exact gate command (Docker only).**

```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_advisory_lock_release_log.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/core/tests/test_migrate_locked.py src/backend/apps/core/tests/test_advisory_lock_ids.py" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk (highest):* adding `pg_advisory_unlock` to the transaction branch by copying the
  session branch too literally — a **behaviour** change and an extra round-trip for 13
  commands. Constrain the copy to `try:` / `finally:` / the `logger.info`.
- *Risk:* the rewrite keeps only the normal-exit assertion and drops the rollback case —
  reproducing the finding's blind spot. The rollback test is mandatory.
- *Risk:* an Implementer takes the opportunity to "fix" the legacy `DB-001`/`DB-007`
  citations. That is BLOCK 11.
- *Rollback:* one function, one docstring, one test file. Fully reversible; no schema, no
  contract, no lock-behaviour change.

---

### BLOCK 3 — `record_event` must not abort the caller's transaction (`03-DB-002`)

| | |
|---|---|
| **Findings owned** | `03-DB-002` |
| **`depends_on`** | *(none)* — but **gates BLOCK 5** (`03-VAL-002`) |
| **Priority** | P0 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Roster decision — CONFIRMED unchanged; all five, and the "high risk ⇒ all agents" rule
applies.**

- **Implementor — yes.** Always.
- **Auditor — yes.** Two things must be re-derived before code is written, not inherited:
  (1) the exact call graph at `ba23277`, because phase 01's `ENT-005` extraction rewrote
  `login.py` and moved the precedent; (2) whether any additional `record_event` caller
  appeared during phases 01/02. **`D-11` makes this harder, not easier**: `record_trust_event`
  is *conditionally* in a savepoint.
- **Researcher — yes.** **Q3** is a genuine PostgreSQL question, and the Researcher must also
  confirm the libpq/PgBouncer safety of whatever BLOCK 5 lands, so the two fixes compose.
- **Planner — yes.** **Q4** has real consequences against two shipped tests and must be made
  explicitly, not by an Implementor.
- **Validator — yes.** The load-bearing runtime premise is **not** re-derived in the source
  report. An independent reviewer must confirm it against the Docker test database *before*
  the fix is believed.

**Decision gate — Q3 + Q4: CLOSED. Options were tabulated in the source plan §3.3.1; the
choice, its consequences and the corrections below are binding. No Implementor may re-open or
re-litigate either question.**

| Gate | Decision |
|---|---|
| **Q3 — `SET CONSTRAINTS` scope** | **Option B: a named, comma-separated constraint list** — *not* `ALL`. |
| **Q4 — the encoding** | **Option A-hybrid** — inside a caller-owned transaction, a nested `transaction.atomic()` savepoint + `SET CONSTRAINTS <user_fk>, <ad_fk> IMMEDIATE` **inside that savepoint**, then the INSERT. In autocommit, today's bare INSERT, unchanged. Branch on `transaction.get_connection().in_atomic_block` (a Python attribute — zero query cost). **Zero call-site edits.** |

**Why A-hybrid and not Option B** (`on_commit` / call-after-the-block) — the decisive evidence
is not the plan's stated reason, which is false (see `C-2` below): `test_analytics_service.py`'s
module-level `pytestmark` is **non-transactional**, so `in_atomic_block` is `True` for every test
in `TestRecordEvent` and a deferred `on_commit` callback **never fires** (the test rolls back).
Option B would break **four of the six** shipped tests — `test_record_event_creates_row_with_all_fields`,
`test_record_event_minimal_call`, `test_record_event_anonymous_user` and
`test_record_event_failure_returns_none_and_logs` (no log record, so the caplog assertions fail) —
and would require the whole class to move to `django_db(transaction=True)`. It also makes the
return type dishonest (`None` on the in-transaction path). Option A-hybrid breaks **zero** shipped
tests, keeps the write synchronous, and still calls `AnalyticsEvent.objects.create`, so the
mocked-failure test still reaches the `except` branch and logs.

**Why named constraints and not `ALL`** — PostgreSQL 18 accepts `SET CONSTRAINTS { ALL | name [,
...] }`, so the comma-separated form is **one statement and costs exactly the same**. `ALL` is
strictly worse: the mode change is **retroactive**, so it re-validates *every* pending deferred
constraint in the caller's transaction, **including ones on other tables** (probes: `ALL` errored
on a pending `users.preferred_city_id` violation, the named list did not). Every FK in this schema
is `DEFERRABLE INITIALLY DEFERRED` (Django ≥ 3.1 default), so `submit_ad`'s transaction carries a
large pending deferred set and `ALL` could fail a publish for an unrelated dangling FK. Named
scope is precisely confined.

#### 1.4 The four load-bearing claims in the source plan that the Researcher **disproved**

All four are measured against live PostgreSQL 18.6 / Django 5.2.17. **They supersede the source
plan wherever they disagree.** An Implementor must not reintroduce them.

| ID | Source plan claims | **Disproof** | Correction to carry |
|---|---|---|---|
| **C-1** | Q4: Option B *"inverts"* `test_record_event_inside_commit_persisted` and `test_record_event_inside_rollback_not_persisted`. | **Wrong.** `on_commit` callbacks run during `Atomic.__exit__` (before the `with` body returns) and are **discarded on rollback**, so both tests pass under any correct encoding. | Neither shipped test is rewritten. **Zero shipped tests change meaning.** The Option-B call-site edit list never materialised. |
| **C-2** | Option B's defect: *"`on_commit` registered inside a **nested** `atomic()` fires at **savepoint** release, not the outer commit."* | **Wrong for Django 5.2.17.** It fires at the **outer** commit: `django/db/backends/base/base.py::savepoint_commit` calls `_savepoint_commit(sid)` and does **not** call `run_and_clear_commit_hooks()`. | This was the plan's **stated** reason to prefer A. It is false, and Option B still loses — for the four-broken-tests reason above. The risk row *"Option 2's `on_commit` placed inside a nested atomic"* is **withdrawn**. |
| **C-3** | Option A's premise: *"`SET CONSTRAINTS` is transactional, so the mode reverts on savepoint release."* | **Wrong for `RELEASE`.** True only for `ROLLBACK TO SAVEPOINT`. After a `RELEASE SAVEPOINT` the same violating INSERT still errored ⇒ the mode **stayed `IMMEDIATE`**. | After a *successful* `record_event` the two `analytics_events` FKs remain `IMMEDIATE` for the rest of the caller's transaction. **Benign** (only `record_event` writes `analytics_events`, and a second call in the same transaction being checked immediately is *desired*; it resets at commit) — but it **must be documented** in the function docstring. |
| **C-4** | Implicit: a fix keyed on `in_atomic_block` leaves `_QUERY_BOUND = 16` untouched. | **Wrong.** `pytest.mark.django_db` wraps every test in Django's atomic block, so `in_atomic_block` is `True` in-test (`baseline_count=16`, `in_atomic_block_seen=[True]`). | **`_QUERY_BOUND` moves 16 → 19** — see binding constraint 1, rewritten below. |

**Also recorded for `03-VAL-004`** (evidence quality): the load-bearing runtime premise was
**re-derived by the Researcher against the live test database**, so BLOCK 3 is the one block in
this phase whose central runtime claim is *not* on the "not re-derived" list.

**Binding constraints carried forward.**

1. **The ad-detail query budget — RESOLVED, and it moves: `16 → 19`.**
   `test_ad_detail_queries._QUERY_BOUND = 16` is an N+1 guard whose comment enumerates
   *"1 INSERT (AnalyticsEvent)"*, and `record_event`'s own docstring cites the constant. The
   before-number was **measured at exactly 16 — zero headroom** (`16 <= 16`), and
   `CaptureQueriesContext` demonstrably records transaction-control statements (the existing
   `SAVEPOINT`/`RELEASE SAVEPOINT` from `get_bot_username` appear in the capture).

   **Derivation: `16 + SAVEPOINT + SET CONSTRAINTS + RELEASE SAVEPOINT = 19`.** The Implementor
   **raises the bound to 19 and restates the enumerating comment**; it does **not** leave the
   budget untouched.

   **The bound is the WORST CASE — an in-transaction caller.** Production `ad_detail` is
   **autocommit** (no `ATOMIC_REQUESTS`, no `atomic()` in `listings.py`), so the `in_atomic_block`
   guard takes the cheap branch and pays **0** extra statements. The `+3` is observable **only
   inside the test**, because `pytest.mark.django_db` makes every test transactional (`C-4`). The
   comment must say this explicitly, so a future reader does not "re-tighten" the bound to 16 and
   re-break a correct fix. `ad_detail` and `_record_search_analytics` are the production paths
   that actually pay 0.
2. **The fix must land before BLOCK 5** (`03-VAL-002`).
3. **The load-bearing runtime premise must be reproduced first.** Write and run a throwaway
   probe inside the Docker test database: open an outer `atomic()`, insert an `AnalyticsEvent`
   for a user, hard-delete that user from a *second* connection, attempt the INSERT, assert
   the outer COMMIT succeeds under the chosen encoding. If it does not, **stop and escalate**.
   Delete the probe afterwards; **never commit it**.
4. **`submit_ad`'s transaction must not move.**
   `test_submit_ad_rolls_back_when_auto_moderate_raises` pins it.
5. **A bare mocked exception is not a regression test.**
   `test_record_event_failure_returns_none_and_logs` monkeypatches
   `AnalyticsEvent.objects.create` to raise `RuntimeError`, which leaves the transaction
   perfectly usable — it **structurally cannot reach** the failure mode. Keep it as a
   supplement; the new test must provoke a **real server-side** error.
6. **The docstrings are part of the defect.** The module docstring asserts "performs NO
   `transaction.atomic()`" and `record_event`'s asserts "never raising"; neither is currently
   true. Both must be rewritten to state what the code does.

**Agent briefs (paste-ready).**

> **Auditor.** *Goal:* re-derive the exact `record_event` call graph at `ba23277` and
> re-locate the in-repo savepoint precedent by **symbol**. *Hard constraints:* change no code;
> never cite a line number as a target. *Files + symbols:* `apps/core/services/analytics.py::
> record_event` + module docstring; the 6 importing modules
> (`apps/ads/views/listings.py::ad_detail`, `apps/search/views/search.py`,
> `apps/core/services/contact.py::record_contact_initiated` / `::record_contact_response`,
> `apps/analytics/services/trust_analytics.py::record_trust_event`,
> `apps/moderation/services/auto_moderation.py::_fail_moderation` / `._pass_moderation`,
> `src/telegram_bot/handlers/login.py::handle_login_orm` → nested `_handle`);
> `apps/trust/services/trust_calculator.py::calculate_and_save`. *Must return:* a per-call-site
> table of caller-transaction and savepoint status, explicitly flagging `record_trust_event`
> as **conditional** (savepoint on the publish path via `_pass_moderation`, autocommit on seed /
> trust-recalculation paths) — **D-11**; confirmation of whether any *new* caller appeared
> after the report's anchor; the symbol path of the savepoint precedent
> (`handle_login_orm._handle`'s inner `with transaction.atomic():` around
> `User.objects.get_or_create`, whose `except IntegrityError:` runs a plain query inside the
> outer transaction); and confirmation that `submit_ad` still has exactly one
> `select_for_update` and no advisory lock.

> **Researcher.** *Goal:* close **Q3** — `SET CONSTRAINTS ALL IMMEDIATE` inside the savepoint
> vs. a named constraint — with the actual semantics of each under a caller transaction that
> has pending deferred constraints. *Hard constraints:* do not choose Q4 (Planner's); do not
> assume generated constraint names (they embed a content hash and must be read from the live
> schema); confirm the libpq/PgBouncer safety of the mechanism BLOCK 5 will land. *Files +
> symbols:* `analytics_events` FK constraints; `Ad.Meta.constraints::
> uq_ads_single_draft_per_user` (a **partial unique index** — `SET CONSTRAINTS` cannot defer
> it); `advisory_lock`; `config/settings/base.py::DATABASES`. *Must return:* the chosen Q3
> option and why; the exact `SELECT` an Implementor must run against the test database to
> read the real constraint names; whether Q3-A's re-validation of the *caller's* other
> pending deferred constraints is acceptable; and whether BLOCK 5's chosen mechanism composes.

> **Planner.** *Goal:* close **Q4** — the fix encoding — explicitly, before coding. *Hard
> constraints:* neither option may be picked by an Implementor; both options' costs against
> shipped tests must be stated. *Files + symbols:* `record_event`; under Option B,
> `auto_moderation._fail_moderation` / `._pass_moderation` and
> `login.handle_login_orm._handle`. *Must return:* the chosen option, the accepted
> consequences, and — if Option B — the full call-site edit list with each site's
> `atomic()` nesting depth stated, because `on_commit` inside a *nested* atomic fires at
> **savepoint** release, not at the outer commit.
>
> **CLOSED.** The last clause is **false** for Django 5.2.17 (`C-2`); the call-site edit list was
> never produced because the decision is **Option A-hybrid**, which needs no call-site edits.

> **Validator.** *Goal:* independently confirm, **before the fix is believed**, that the
> chosen encoding actually rescues the caller's write, and that the new test provokes a **real
> server-side** error rather than a mocked Python exception. *Hard constraints:* change no code;
> run only through the Docker `test` service. *Must return:* the probe result (run twice —
> pre-fix, post-fix), the measured `len(captured_queries)` on the ad-detail path, and a
> statement of whether `_QUERY_BOUND` needed raising.

**Implementor task.**

```yaml
id: task_03_b03_record_event_transaction
title: Make record_event non-aborting for the caller's transaction
priority: high
depends_on: []
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 3 — record_event must not abort the caller's transaction (DB-002)"
extra_context: |
  Q3 AND Q4 ARE **CLOSED**. The decision is **Option A-hybrid** and is binding — an Implementor
  may NOT re-open it, may NOT substitute Option B, and may NOT ship the plain-savepoint variant.

  Q3 (SET CONSTRAINTS scope) = **named, comma-separated constraints. NOT `ALL`.**
  Q4 (encoding) = **Option A-hybrid.** Inside a caller-owned transaction: a nested
  `transaction.atomic()` savepoint, then `SET CONSTRAINTS <user_fk>, <ad_fk> IMMEDIATE` inside
  that savepoint, then the INSERT. In autocommit: today's bare INSERT, unchanged. Branch on
  `transaction.get_connection().in_atomic_block`. **ZERO call-site edits.**

  FOUR CLAIMS IN THE SOURCE PLAN ARE DISPROVED — do not reintroduce them:
  C-1  Option B does NOT invert the two inside-transaction tests. Neither shipped test is rewritten.
  C-2  A nested `on_commit` does NOT fire at savepoint release on Django 5.2.17. That was the
       plan's stated reason to prefer A; it is false, and A is chosen on other grounds.
  C-3  `SET CONSTRAINTS` is restored by `ROLLBACK TO SAVEPOINT` but NOT by `RELEASE SAVEPOINT`.
       After a SUCCESSFUL call the two analytics_events FKs stay IMMEDIATE for the rest of the
       caller's transaction. Benign, but MUST be documented in the function docstring.
  C-4  A guard on `in_atomic_block` does NOT leave `_QUERY_BOUND` at 16: `pytest.mark.django_db`
       makes every test transactional. The bound moves 16 -> 19.

  BINDING CONSTRAINTS:
  1. `_QUERY_BOUND` moves **16 -> 19**. Derivation: 16 + SAVEPOINT + SET CONSTRAINTS +
     RELEASE SAVEPOINT. The bound is the WORST CASE (in-transaction caller); production
     `ad_detail` is autocommit and pays 0. The enumerating comment must record all of this.
  2. BLOCK 5 depends on this block (03-VAL-002). Do not defer.
  3. The load-bearing runtime premise must be reproduced FIRST with a throwaway probe against
     the Docker test database. Delete the probe; never commit it. If it fails, STOP and escalate.
  4. submit_ad's transaction must not move (test_submit_ad_rolls_back_when_auto_moderate_raises).
  5. A monkeypatched RuntimeError is NOT a regression test — it leaves the transaction usable.
     The new test must provoke a real server-side error, and must be demonstrated RED pre-fix.
  6. The module docstring and the record_event docstring are part of the defect; both must be
     rewritten to state what the code actually does.
  D-11: record_trust_event is CONDITIONALLY inside a savepoint (via _pass_moderation), not
  unconditionally autocommit. A single static per-symbol label is unsound: `auto_moderate` is
  reached by five production call paths, one of which (moderation/views/api_bulk.py::
  bulk_moderation_action) has NO atomic() at all, so `_pass_moderation`'s block is a real commit
  boundary there. The fix must therefore be call-site-free — it can assume neither the presence
  nor the absence of a savepoint.

description: >
  record_event is documented as never raising and as transaction-transparent, and catches a
  bare Exception — but it executes inside callers' transactions. A server-side error during the
  INSERT aborts PostgreSQL's transaction; the exception is swallowed and the caller keeps
  issuing statements against a dead transaction, or (for a deferred constraint) sees success
  all the way to COMMIT and loses the entire business write. Apply the Q3/Q4 decision so
  record_event can never abort the transaction it was only observing.

goals:
  - a database error inside record_event never leaves the caller with an aborted transaction
  - keep the "analytics is an observer, not a participant" contract literally true in the code
  - do not move or weaken submit_ad's outer transaction
  - keep every call site unchanged — the fix is entirely inside record_event
  - keep the autocommit path (ad_detail, _record_search_analytics, handle_contact_orm) at one statement
  - bind _QUERY_BOUND to its measured worst case (19) with the derivation recorded in the comment

files:
  - path: src/backend/apps/core/services/analytics.py
    targets:
      - { type: function, name: record_event }
      - { type: module,   name: analytics }
    semantic_anchors:
      replace_in_body:
        target: record_event
        old: "try:"   # the create() try block — scope via the symbol, not a line number
  - path: src/backend/apps/core/tests/test_analytics_service.py
    targets: [{ type: class, name: TestRecordEvent }]
    semantic_anchors: {}
  - path: src/backend/apps/ads/tests/test_ad_detail_queries.py
    targets:
      - { type: constant, name: _QUERY_BOUND }
      - { type: module,   name: test_ad_detail_queries }   # the enumerating comment above it
    semantic_anchors: {}
  # NOT touched: the AnalyticsEvent model or its migration; record_trust_event; ANY call site of
  # record_event (ad_detail, _record_search_analytics, record_contact_initiated,
  # record_contact_response, record_trust_event, _fail_moderation, _pass_moderation,
  # handle_login_orm); auto_moderation.py; login.py; submit_ad.

changes:
  - action: add_code
    description: >
      Apply Option A-hybrid inside record_event. Read transaction.get_connection() once; if
      in_atomic_block is False, issue today's single bare INSERT. If True, open a nested
      transaction.atomic() savepoint, execute the NAMED, comma-separated
      `SET CONSTRAINTS <user_fk>, <ad_fk> IMMEDIATE` inside that savepoint, then the INSERT.
      The try must bracket the FAILING WORK, not the recovery — the login.py::handle_login_orm
      pattern: the savepoint is created before the work, and Atomic.__exit__ rolls back to it
      before the exception reaches the handler, so the handler runs on a healthy transaction.
    code_hint: |
      connection = transaction.get_connection()
      try:
          if not connection.in_atomic_block:
              return AnalyticsEvent.objects.create(...)
          with transaction.atomic():
              with connection.cursor() as cursor:
                  cursor.execute(_SET_CONSTRAINTS_SQL)
              return AnalyticsEvent.objects.create(...)
      except Exception:  # noqa: BLE001 — analytics must never break the request
          logger.exception("Failed to record analytics event %s (...)", ...)
          return None
  - action: add_code
    description: >
      Add the two module-level constants holding the generated FK constraint names read from the
      LIVE test database in step 1, plus the composed SQL string. Project rule 10 applies: named
      module-level constants, not inline literals.
  - action: edit_docstring
    description: >
      Rewrite the module docstring and record_event's docstring. The function docstring MUST state
      that removing the SET CONSTRAINTS line silently reintroduces COMMIT-time data loss, because a
      deferred violation is NOT raised at RELEASE SAVEPOINT. It MUST also record the named-vs-ALL
      rationale, the C-3 IMMEDIATE-persistence note, and the autocommit cost. The module docstring's
      false "performs NO transaction.atomic() so it remains transparent to the caller's transaction
      boundary" claim MUST be replaced with "observer, not a participant".
  - action: edit_constant
    description: >
      In test_ad_detail_queries.py, raise _QUERY_BOUND from 16 to 19 and restate the enumerating
      comment: 16 + SAVEPOINT + SET CONSTRAINTS + RELEASE SAVEPOINT, worst case = an in-transaction
      caller, and that production ad_detail is autocommit and pays 0 because pytest.mark.django_db
      makes the test transactional.
  - action: add_test
    description: >
      Add the real-server-side-error regression test (transactional, no mocking) and the
      constraint-name guard test. Demonstrate the regression test RED against the pre-fix code
      BEFORE the fix lands. Keep the existing mocked-failure test unchanged as a supplement.
  - action: not_do
    description: >
      Do NOT rewrite test_record_event_inside_commit_persisted or
      test_record_event_inside_rollback_not_persisted — C-1 proves Option A-hybrid leaves both
      passing and their meaning intact. Do NOT change AnalyticsEvent or its migration. Do NOT take
      advisory lock 3. Do NOT touch send_alerts.py or seed_service.py (reported, not fixed).

acceptance_criteria:
  - inside a caller-owned atomic(), a real server-side database error in record_event leaves
    the caller's business write committed; the caller's transaction is still usable afterwards
  - the regression test provokes a GENUINE server-side error (no monkeypatch, no mock exception)
    and was demonstrated RED against the pre-fix code before the fix landed
  - the constraint-name guard test asserts BOTH generated FK names exist in pg_constraint on the
    live test database with condeferrable AND condeferred
  - the runtime probe was executed against the Docker test database BEFORE the fix, its result
    recorded, and the probe deleted (not committed)
  - the plain-savepoint variant was NOT shipped; SET CONSTRAINTS is present in the transactional branch
  - the change is call-site-free: no call site of record_event was edited; the AnalyticsEvent model
    and its migration are unchanged; submit_ad's transaction did not move
  - test_submit_ad_rolls_back_when_auto_moderate_raises, its sibling
    test_submit_ad_commit_when_auto_moderate_passes, and all six TestRecordEvent cases pass unchanged
  - _QUERY_BOUND is 19, with the 16 + SAVEPOINT + SET CONSTRAINTS + RELEASE derivation, the
    worst-case (in-transaction caller) framing, and the "production ad_detail is autocommit and
    pays 0" note recorded in the enumerating comment
  - test_record_event_failure_returns_none_and_logs passes unchanged
  - the record_event docstring states that removing the SET CONSTRAINTS line silently reintroduces
    COMMIT-time data loss, and the module docstring no longer claims transaction transparency
  - the commit message records: Q3/Q4 as Option A-hybrid with named constraints; that only the
    record_event encoding changed; the _QUERY_BOUND 16 -> 19 move with its derivation; and that the
    consent_hard_delete push-down is PRE-EXISTING and out of scope
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - the Docker gate below is green
```

**Tests required.**

- *Must keep passing unchanged:* `apps/core/tests/test_analytics_service.py::TestRecordEvent`
  **all six** — including `test_record_event_inside_commit_persisted`,
  `test_record_event_inside_rollback_not_persisted`, and the mocked
  `test_record_event_failure_returns_none_and_logs` (`C-1`: the two inside-transaction tests are
  **not** rewritten). `apps/ads/tests/test_submission.py` — **both** siblings
  `test_submit_ad_rolls_back_when_auto_moderate_raises` and
  `test_submit_ad_commit_when_auto_moderate_passes`. `apps/moderation/tests/test_auto_moderation.py` —
  `test_auto_moderate_pass_sets_published_and_analytics`,
  `test_pass_moderation_survives_trust_calculator_failure` (the direct behavioural precedent for
  this fix) and `test_auto_moderate_fail_sets_failed_status_and_analytics` (asserts
  `len(event_types) == 1` — the fix emits **no** compensating event). `src/telegram_bot/tests/test_login.py`.
- *Must be added:* (a) the **real-server-side-error** regression test — **red against the pre-fix
  code**; (b) the **`pg_constraint` constraint-name guard**; (c) the autocommit-cost guard
  (optional — see below).
- *Must be changed:* **none.**

**Exact gate command (Docker only).**

```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_analytics_service.py src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_ad_detail_queries.py src/backend/apps/moderation/tests/ src/telegram_bot/tests/test_login.py" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk (highest):* shipping the **plain savepoint** variant. It resembles the real fix, passes the
  existing suite, and does **not** fix the defect — the COMMIT still fails and the business write
  is still lost (`probe2b_users_rows_survived = 0`). The regression test is the only control and
  it must have been red.
- *Risk:* the `SET CONSTRAINTS` subtlety being "simplified" away because it is undocumented.
  **A reviewer must treat the absence of the `SET CONSTRAINTS` rationale as a defect.**
- *Risk:* a generated FK constraint name copied from a report instead of re-read from the live
  schema. A wrong name raises `UndefinedObject` inside our own savepoint — the caller is unharmed
  and the failure is loud in the log, so it is **silent in production**. Mitigated by the
  `pg_constraint` guard test, which fails CI on a rename.
- **Accepted risk 1 — `_QUERY_BOUND` 16 → 19** (the guard loosens by 19%). The `+3` is a
  test-harness artifact of `pytest.mark.django_db`; production `ad_detail` pays 0. Documented.
- **Accepted risk 2 — constraint-name fragility.** Stable only for a given migration state.
  Mitigated as above; failure mode is safe.
- **Accepted risk 3 — `RELEASE SAVEPOINT` leaves the two FKs `IMMEDIATE`** for the rest of the
  caller's transaction (`C-3`). Benign, must be documented.
- **Accepted risk 4 — push-down to `consent_hard_delete` is PRE-EXISTING.** Today's bare
  `record_event` commits the same FK-bearing row and PostgreSQL takes `FOR KEY SHARE` on the
  parent either way; the fix neither creates nor worsens the push-down, and it **reduces** total
  exposure (an already-deleted user is now rejected at our savepoint, so neither side fails).
  **No design inside `record_event` avoids it** — serialising would require the publisher to take
  advisory lock 3, which would put analytics on the critical path of every publish. The residual
  race needs a **retry in `consent_hard_delete`**: **out of scope**, report to the Coordinator.
- **Accepted risk 5 — PostgreSQL-specific.** Accepted; the project is PostgreSQL-only (native FTS).
- **Reported, not fixed (out of scope):** `apps/search/management/commands/send_alerts.py::
  Command.handle` and `apps/seed/services/seed_service.py` write `AnalyticsEvent` rows via
  `bulk_create`, **bypassing `record_event`**, with the same deferred-FK exposure. **No
  `record_event` fix covers them.** Report to the Coordinator.
- *Withdrawn:* "Option B's `on_commit` placed inside a nested atomic" — `C-2` disproves it.
- *Risk:* landing after BLOCK 5, turning a latent defect live (`03-VAL-002`). Enforced by
  `depends_on`.
- *Rollback:* one function plus one docstring pair, one constant, and two test files. No schema,
  no call-site change, no contract change. Fully reversible.

---

### BLOCK 4 — Recoverable race backstop in `create_draft_ad` (`03-DB-001`)

| | |
|---|---|
| **Findings owned** | `03-DB-001` (`03-VAL-003` as an **advisory** gate) |
| **`depends_on`** | *(none)* — **advisory** gate on the coordinator's `03-VAL-003` acknowledgement |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Validator** |

**Roster decision — CONFIRMED unchanged.**

- **Implementor — yes.** Always.
- **Auditor — yes.** The fix copies an in-repo precedent whose line reference in the source
  report is **stale** (`C-5`); the Auditor must re-locate it **by symbol** and confirm the
  caller topology before the block relies on it. See **N-5**: a third non-test reference
  exists in prose.
- **Researcher — no.** The remedy is prescribed and has an in-repo model.
- **Planner — no.** One nested `atomic()` around one statement plus a regression test. The
  severity question (`03-VAL-003`) is a **coordinator** decision and does not change the code.
- **Validator — yes.** Hot bot path (`/post`); the fix changes a transaction boundary. A
  regression means `/post` breaks for every seller.

**Decision gate — `03-VAL-003` (coordinator, advisory).** `AD-005` (phase 05, HIGH) and
`03-DB-001` (this cycle, MEDIUM) are the same defect filed twice. This plan ships **one** work
item at **MEDIUM** and escalates the phase-05 re-rating (§3.2). **This gate is advisory and
must not block the phase** — see §3.2.

**Agent briefs (paste-ready).**

> **Auditor.** *Goal:* re-locate the savepoint precedent by symbol and confirm the caller
> topology at `ba23277`. *Hard constraints:* change no code; never target a line number.
> *Files + symbols:* `src/telegram_bot/services/ad_data/orm.py::create_draft_ad` → inner
> `_create()`; the precedent is **`src/telegram_bot/handlers/login.py::handle_login_orm` →
> nested `def _handle()`**, whose inner `with transaction.atomic():` wraps
> `User.objects.get_or_create(...)` and whose `except IntegrityError:` runs a plain
> `User.objects.get(chat_id=...)` query **inside the outer transaction** — this is the shape to
> copy; also `src/backend/apps/ads/models.py::Ad.Meta.constraints::
> uq_ads_single_draft_per_user`. *Must return:* (a) the confirmed symbol path of the
> precedent; (b) whether `cmd_post` is still the **only invocation** site — note that
> `src/telegram_bot/middlewares/update_id_dedup.py` contains a **prose** mention of
> `create_draft_ad` in its module docstring but **no import and no call**, so it is not a
> caller; (c) whether any second bot process exists in any deployment, since that is what
> makes the unique-index race reachable.

**Implementor brief.** *Goal:* wrap `Ad.objects.create(...)` in a nested
`transaction.atomic()` so the `except IntegrityError` recovery branch runs against a usable
transaction. *Hard constraints:* keep the existing delete-then-recreate (Option D pattern —
BLOCK 10 unifies it with `copy_ad`, do not remove it); keep the existing cleanup-then-retry;
the invariant to test is **"a draft is returned"**, **not** "the seller's draft survived" — the
rollback preserves the pre-existing DRAFT row and no `pre_delete`/`on_commit` deletion fires;
no `apps/*` → `telegram_bot/*` import. *Files + symbols:*
`src/telegram_bot/services/ad_data/orm.py::create_draft_ad` → inner `_create()`, the
`try`/`except IntegrityError` block, and the `create_draft_ad` docstring;
`src/backend/apps/ads/models.py::uq_ads_single_draft_per_user` (reference only, not modified);
**not** `ad_data/__init__.py`, **not** `entry.py`. *Must return:* the changed files, the red
demonstration of the new test, the green
`TestCreateDraftAdCrashRecovery`, and the commit hash.

**Implementor task.**

```yaml
id: task_03_b04_create_draft_savepoint
title: Add the missing savepoint so create_draft_ad's IntegrityError recovery is reachable
priority: high
depends_on: []
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 4 — Recoverable race backstop in create_draft_ad (DB-001)"
extra_context: |
  The 03-VAL-003 gate is ADVISORY and must not block this block (execution plan 13 §3.2).
  ONE work item ships, at MEDIUM. Phase 05 must not ship a second patch.
  THE CORRECT INVARIANT IS "a draft is returned", NOT "the seller's draft survived": the
  rollback PRESERVES the pre-existing DRAFT row and no pre_delete / on_commit file deletion
  fires. A test written against the report's "the seller's ad is destroyed" claim would FAIL
  against correct code.
  The in-repo precedent is src/telegram_bot/handlers/login.py::handle_login_orm -> nested
  def _handle(): the inner `with transaction.atomic():` around User.objects.get_or_create(...),
  whose `except IntegrityError:` runs a plain query inside the OUTER transaction. The source
  report's line reference is stale — locate it by SYMBOL.
  src/telegram_bot/middlewares/update_id_dedup.py mentions create_draft_ad in prose only; it
  neither imports nor calls it and is not a second caller.
  KEEP the existing delete-then-recreate. BLOCK 10 unifies this policy with copy_ad.

description: >
  create_draft_ad's inner _create() wraps Ad.objects.create(...) in the OUTERMOST
  transaction.atomic(), so Django creates no savepoint and the except IntegrityError handler's
  first statement runs against an already-aborted transaction. The branch is dead code, and
  the docstring's promise ("we retry once after cleaning up") is false. Add the missing nested
  atomic() so the documented backstop becomes reachable.

goals:
  - make the documented IntegrityError backstop reachable
  - keep the delete-then-recreate policy and the cleanup-then-retry sequence unchanged
  - keep uq_ads_single_draft_per_user as the backstop, not the primary mechanism
  - no data-loss framing in code, docstring or test

files:
  - path: src/telegram_bot/services/ad_data/orm.py
    targets:
      - { type: function, name: create_draft_ad }
      - { type: function, name: _create }
    semantic_anchors:
      insert_around:
        target_symbol: "Ad.objects.create("
        new: |
          with transaction.atomic():
              Ad.objects.create(...)
  - path: src/backend/apps/ads/models.py
    targets: [{ type: class, name: Ad }]
    semantic_anchors: {}   # uq_ads_single_draft_per_user — REFERENCE ONLY, do not modify
  - path: src/telegram_bot/tests/test_create_draft_ad.py
    targets: [{ type: class, name: TestCreateDraftAdCrashRecovery }]
    semantic_anchors: {}
  # NOT touched: src/telegram_bot/services/ad_data/__init__.py (no new export);
  #             src/telegram_bot/handlers/ad_create/entry.py (no call-site change).

changes:
  - action: edit_code
    description: >
      Wrap the Ad.objects.create(...) call in a nested transaction.atomic() so Django creates
      a savepoint and the except IntegrityError branch runs against a usable transaction. Keep
      the existing existing.delete() cleanup and the retry.
  - action: add_test
    description: >
      Add a regression test that forces uq_ads_single_draft_per_user to fire — make the
      delete-then-create race deterministic (e.g. create a second DRAFT from a separate
      connection between existing.delete() and create()) — and assert create_draft_ad still
      RETURNS A DRAFT rather than propagating the driver error. Demonstrate it RED against the
      pre-fix code.
  - action: edit_docstring
    description: >
      Keep the docstring's "retry once after cleaning up" promise and make the code honour it.
      Remove any wording that implies the seller's draft is destroyed — the rollback preserves it.

acceptance_criteria:
  - with uq_ads_single_draft_per_user forced to fire, create_draft_ad returns a draft and does
    not propagate an InternalError / driver exception
  - the new test was demonstrated RED against the pre-fix code
  - the delete-then-recreate policy and the cleanup-then-retry sequence are unchanged
  - TestCreateDraftAdCrashRecovery passes unchanged (rollback preserves the DB row;
    delete_photo is not called on rollback)
  - test_create_draft_second_call_does_not_duplicate passes unchanged
  - src/backend/apps/ads/tests/test_ad_constraints.py passes unchanged
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - the Docker gate below is green
```

**Tests required.**

- *Must keep passing unchanged:*
  `src/telegram_bot/tests/test_create_draft_ad.py::test_create_draft_second_call_does_not_duplicate`
  and `TestCreateDraftAdCrashRecovery::*`; `src/backend/apps/ads/tests/test_ad_constraints.py`.
- *Must be added:* the forced-constraint-fire test — **red against the pre-fix code**.
- *Must be changed:* none.

**Exact gate command (Docker only).**

```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_create_draft_ad.py src/backend/apps/ads/tests/test_ad_constraints.py" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk:* the nested savepoint changes what a rollback of the **outer** block restores — the
  cleanup `Ad.objects.filter(...).delete()` now runs inside the outer transaction and could be
  rolled back by a later failure. That is **correct** behaviour (one unit of work) and must be
  understood, not assumed.
- *Risk:* "fixing" it by removing the cleanup-then-retry — a dead net becomes no net.
- *Risk:* a test written against the report's wrong "the seller's ad is destroyed" claim.
- *Rollback:* one function. Trivially reversible.

---

### BLOCK 5 — Bound the lock wait and give both processes an `OperationalError` boundary (`03-DB-004`, timeout half)

> **Title corrected.** The source plan's *"Bound the lock wait and give both processes a
> **retry** boundary"* **over-promises**. There is no retry in this block: after the abort, a
> retry means leaving and re-entering the `atomic()`, which the shipped guard tests forbid
> (`test_ad_edit_get_path_not_locked` asserts `count("select_for_update") == 1`, plus two
> ordering assertions in `test_unsubscribe.py::TestResolveOwnedLocking`). The deliverable is a
> **bounded wait** plus a **handled** boundary. The only real retry in the system is
> `apps/core/utils/scheduler.py::run_one_cycle` re-dispatching `HOURLY_COMMANDS` on every
> tick, which already exists and needs no code.

| | |
|---|---|
| **Findings owned** | `03-DB-004` — **timeout half only** (the `ENT-006` addendum is already shipped) |
| **`depends_on`** | **BLOCK 3** (`03-VAL-002`) — **satisfied** (`549c58e`) |
| **Priority** | P0 — the phase's structural block |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |
| **Gate status** | **Q1 and Q2 CLOSED** (Auditor `context_a`, Researcher `context_r`, Planner). Implementor may not re-open either. |

**Roster decision — CONFIRMED unchanged; all five.** Re-verified against the tree: `D-3`
(eight concurrency tests, not six), `D-10` (a **second** env-parity gate) and `D-12`/`D-13`
(the exact `base.py` / `ALLOWED_ENV_VARS` shape) each independently reinforce the need for
Auditor (inventory), Researcher (Q1/Q2), Planner (shared settings + two-process error
boundary) and Validator (bounded-wait assertion). `CONN_MAX_AGE`/connection lifecycle stays
**closed** (phase 01 `ENT-010` Half B, rejected).

#### Decision gates — `Q1` and `Q2`: **CLOSED**. Binding; no re-litigation.

Both were measured by the Researcher against the live test database (PostgreSQL 18.6,
psycopg 3.3.4, Django 5.2.17). The source plan §3.5.1–§3.5.2 option tables are superseded
wherever they disagree.

| Gate | Decision |
|---|---|
| **Q1 — the mechanism** | **Connection-level `lock_timeout`, delivered as libpq's `options` startup parameter** in `DATABASES["default"]["OPTIONS"]`, via a new env var **`LOCK_TIMEOUT_SECONDS`** (`env.int`, seconds, **default `10`**), rendered as `f"-c lock_timeout={LOCK_TIMEOUT_SECONDS}s"`. **No `SET LOCAL`. No `statement_timeout`. No `idle_in_transaction_session_timeout`.** Both are explicit deferrals with triggers, not omissions — see below. |
| **Q2 — the boundary** | **Asymmetric "C", plus one shared predicate.** One `is_lock_timeout()` classifier in `apps/core/`; a **narrow, predicate-gated** `process_exception` web middleware (`if not is_lock_timeout(exc): raise`) for the six redirect-only views; **in-view** handling for `ad_edit`; **per-handler** handling for the three bot sites that own user state; **no code change** in management commands. **No retry loop anywhere.** |

**Q1 — value, unit, and margin.**

- **The source plan's Option A is not implementable as written.** `DATABASES["default"]["OPTIONS"]`
  is spread straight into `psycopg.connect()`, and libpq rejects any keyword outside its
  conninfo table. Measured: `psycopg.connect(DSN, lock_timeout=5000)` →
  `psycopg.ProgrammingError: invalid connection option "lock_timeout"`, raised out of
  `DatabaseWrapper.get_new_connection`. A bare GUC takes **every process down**. Only
  `options="-c …"` is valid. **The `options="-c …"` form is mandatory.**
- **Unit safety is structural, not documentary.** A bare GUC number is **milliseconds**
  (measured: `-c lock_timeout=2` → `SHOW lock_timeout` = `2ms`). The constant is named
  `LOCK_TIMEOUT_SECONDS` and the rendered string carries an explicit `s`, so the 1000×
  error is **inexpressible** through this API. A guard test asserts the rendered string, not
  the int.
- **`StrEnum` is REJECTED for this value** (source plan §1's "includes the DB-004 timeout
  value"). `base.py` already holds four sibling timeouts as plain `env.int` seconds
  (`BOT_HEALTH_STALE_SECONDS`, `SCHEDULER_COMMAND_TIMEOUT`, `SCHEDULER_HEALTH_STALE_SECONDS`,
  `EMAIL_TIMEOUT`); a `StrEnum` wrapping `"10s"` is strictly less safe and diverges from the
  file's own convention (project rule 7). Safety comes from the `_SECONDS` name + the `s`
  suffix + the guard test.
- **Value: `10` seconds.** Margin is **≈ 8.7 s of headroom** over the eight concurrency
  tests' `time.sleep(1.0)` holds (measured: a 1000 ms bound fires at 1.022 s), and it is
  **6× below** `gunicorn.conf.py::timeout = 60`, so a timed-out request yields a real error
  page rather than a SIGKILLed worker with a dropped connection. **Not 5 s:** BLOCK 7 has not
  landed and `archive_sweep.Command.handle` holds its `select_for_update()` for the whole
  sweep in one transaction. BLOCK 7 only shortens holds and needs **no change** to this value.
- **Exception shape.** `psycopg.errors.LockNotAvailable`, **SQLSTATE `55P03`**, surfacing as
  `django.db.utils.OperationalError` with the driver error on **`exc.__cause__`**
  (`exc.sqlstate` is `None` — Django does not re-export it). Match on `__cause__` only;
  matching `str(exc)` is locale- and version-fragile.
- **Deferred with a trigger** (not silently dropped): **`statement_timeout`** — revisit only
  with BLOCK 7 landed, and only with a value `> LOCK_TIMEOUT_SECONDS` derived and tested
  independently; **`idle_in_transaction_session_timeout`** — it bounds a transaction that
  *holds* a lock and then waits on Python, the opposite of what `lock_timeout` bounds.

**Q2 — the closed shape, per execution model.** No retry is available (§2.1 of `context_r`):
the outermost-`atomic()` path is unrecoverable after the abort, and the guard tests forbid
re-issuing the query.

| Tier | Boundary BLOCK 5 adds |
|---|---|
| **web** (`ad_edit`, `ad_archive`, `ad_reactivate`, `ad_delete`, `approve_ad`, `reject_ad`, `ban_user`, `bulk_approve`, `bulk_reject`, `bulk_delete`) | Predicate-gated `process_exception` middleware (**503** + `Retry-After`) for the **six** redirect-only views; **in-view** for `ad_edit` (the only view with a template to return to — a bare 503 discards the seller's typed form); catch-around-the-whole-`atomic()` + log + **re-raise** for the **three bulks**. |
| **bot** — one asgiref `thread_sensitive` worker | `lock_timeout` + **per-handler** handling, because aiogram's catch-all **logs without messaging** and would strand the FSM. |
| **commands** — scheduler subprocess / operator CLI | `lock_timeout` **only**. **No code change.** `archive_sweep`: a timeout is a failed tick — *not* a skipped batch, *not* an in-process retry (BLOCK 7 collides). `recompute_normalized_prices`: fail loudly; a silently partial recompute publishes wrong EUR-normalized prices to every buyer. |

**The `submit_ad` deception is the highest-value line in the block.** `process_preview`
currently **discards `errors`** and prints a hard-coded *"Ad failed moderation…"*, then
`state.clear()`. It must render `errors[0]` (as `ad_edit` already does), add the busy branch,
and **not clear state on a timeout** — clearing on a transient lock failure destroys hours of
typed work for a condition that resolves in 10 seconds. The genuine-moderation-failure branch
keeps its message *and* its `state.clear()`.

**Exactly two new msgids**, `ru` + `bs` non-empty, **appended** to the shared
`src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` (shared with phase 14 — **append, never
regenerate wholesale**):

1. `"The system is busy. Please try again in a moment."` — reused on the bot submit path
   (`process_preview`), the bot login path (`handle_login_deep_link`), the `ad_edit`
   re-render, and nowhere else.
2. The **503 body** — a distinct, more operational wording so the two are not conflated in the
   catalog.

**No new msgid for `alerts.py::_resolve_owned`.** It logs and returns `None`; `None` is
already the failure signal and both callers already answer *"Failed to disable/enable
notifications"*. That is an honest degradation and it **preserves the `59`/`60`-line count of
`test_unsubscribe.py`'s messages**.

#### Two corrections to the Auditor's `context_a` — both binding

| ID | `context_a` claims | **Correction (measured)** |
|---|---|---|
| **B-1** | §9 / §12b-E: *"`ROLLBACK TO SAVEPOINT` does **not** restore a `SET LOCAL` GUC."* | **Wrong for `lock_timeout`.** Measured: after `SET LOCAL 3s` inside a savepoint, `ROLLBACK TO SAVEPOINT` restores `0`; only **`RELEASE SAVEPOINT`** leaks the value for the rest of the enclosing transaction. (It is right for `SET CONSTRAINTS` *mode*, which is BLOCK 3's `record_event` docstring, and that docstring is unaffected.) The `set_published` hazard therefore **survives on the *successful* path** — a `SET LOCAL` there is `RELEASEd` on every normal call. This does **not** rescue Option B. |
| **B-2** | §12b-H: an `OperationalError` in `bulk_*` *"would abort the bulk and roll back already-processed rows."* | **Half wrong.** `QuerySet.__iter__` → `_fetch_all()` issues **one** `SELECT … FOR UPDATE` for the whole result set **before the first row body executes**, so the **primary** path has **nothing** to discard. A **secondary** path (a later in-loop statement, e.g. `transition_to()` → `refresh_from_db()`) does roll back earlier rows. **The commit message must use the corrected characterisation: hang → fail with nothing committed.** |

#### PgBouncer prerequisite (risk `R1`, **HIGH if unmitigated**)

`docker-compose.prod.yml::pgbouncer` is `edoburu/pgbouncer:1.25.2` with
`PGBOUNCER_POOL_MODE=transaction`. `.github/workflows/deploy.yml` uses **no `--profile`**, so
PgBouncer is **not in the deployed path today**. But `options` is a **startup-packet**
parameter and the edoburu entrypoint sets `ignore_startup_parameters=extra_float_digits`,
erroring on anything else. ⇒ **`PGBOUNCER_IGNORE_STARTUP_PARAMETERS=options,extra_float_digits`
ships in the same commit as the setting**, plus the prerequisite is recorded in
`docs/01-spec/architecture-structure.md` and in a `docs/ops/` runbook line. No-op today,
correct-by-construction the moment phase 12 enables the profile (phase-12 `OPS-007`/`OPS-015`).

#### Accepted risks

| # | Risk | Sev | Disposition |
|---|---|---|---|
| **R1** | PgBouncer rejects the client's `options` startup parameter → **every connection fails** if the profile is enabled without the prerequisite. | **HIGH if unmitigated** | **Accepted with mitigation** — the env var in the same commit + `architecture-structure.md` + a `docs/ops/` runbook line. Latent today. |
| **R2** | Legitimate `>10 s` waits now fail (a moderator action contending with `archive_sweep`'s whole-sweep transaction; a second `purge_deleted_ads` run queued behind the first). | MED | **Accepted** — this is the finding being fixed. BLOCK 7 shortens the holds; the value needs no change. |
| **R3** | Bulk moderation actions abort (nothing committed) instead of hanging — a behaviour change from the source plan's §12b-H (corrected by **B-2**). | LOW–MED | **Accepted and stated as such.** Strictly better than a silently partial bulk. |
| **R4** | `submit_ad`'s dialog state would be destroyed by the existing failure branch. | MED | **Accepted and mitigated** — do **not** `state.clear()` on a lock timeout. |
| **R5** | The eight concurrency tests run at the **production** value (connection-level setting; `config/settings/test.py` inherits `base.py`). | LOW | **Accepted** — ≈ 8.7 s of headroom; verified by running them unmodified. |
| **R6** | `transaction=True` teardown (`flush`/TRUNCATE) can itself block; the bound converts a teardown hang into a visible teardown error. | LOW | **Accepted** — arguably an improvement. It is a **different signature** from the known pre-existing teardown flakiness, so it must not be mis-filed as that. |
| **R7** | Concurrent-commit hazard on `base.py` / the four templates (phase 02) and on `docker-compose.prod.yml` (phase 12). | MED | **Mitigated** — re-read immediately before editing; three explicit commits; stage explicit paths. |

**Recorded, not fixed (do not "help"):** `CONN_HEALTH_CHECKS` is set **nowhere** in the
repository (phase 01 `ENT-010` Half B was rejected as intentional design). Raising the asgiref
worker count or relaxing `thread_sensitive` is **forbidden** — it exists so a transaction and
its connection stay on one thread. `SWEEP_COMMANDS` holds 13 entries and
`test_sweep_lock_structure.py::test_all_sweep_commands_lock_inside_transaction` asserts
`session is False` for each; **BLOCK 5 must not add `repair_bot_username`** (a 14th
transaction-scoped lock-taker is genuinely unlisted — a pre-existing gap, out of scope).

**Agent briefs (paste-ready) — HISTORICAL RECORD; the gates are now closed.** The
Researcher's and Planner's briefs below are preserved as issued; their outputs are the
`context_r` / this section's tables above. The Auditor's and Validator's briefs remain live.

**Agent briefs (paste-ready).**

> **Auditor.** *Goal:* re-derive the complete inventory of `select_for_update()` call sites
> that would **newly gain an `OperationalError` path**, split bot-side from web-side.
> *Hard constraints:* change no code; never target a line number; do not re-open
> `CONN_MAX_AGE`. *Files + symbols:* **15 production call expressions** — bot: (2)
> `apps/ads/services/submission.py::submit_ad`, `src/telegram_bot/handlers/alerts.py`
> (`SavedSearch`); web: (10) `apps/ads/views/edit.py::ad_edit` / `ad_archive` / `ad_reactivate`,
> `apps/ads/views/delete.py::ad_delete`, `apps/moderation/views/review.py` (approve / reject /
> ban), `apps/moderation/admin_actions.py` ×3 on `Ad` + ×1 on `User`; savepoint-nested: (1)
> `apps/moderation/services/moderation_log.py::set_moderation_failed` / `::set_published`;
> commands: (2) `archive_sweep.Command.handle`, `recompute_normalized_prices.Command._process_batch`.
> Also the scheduler paths `apps/core/utils/scheduler.py::run_one_cycle` /
> `HOURLY_COMMANDS` / `DAILY_COMMANDS`, and `gunicorn.conf.py`'s `timeout = 60`.
> *Must return:* the per-site retry-vs-error classification Q2 needs; confirmation that
> `handle_login_orm` takes **no** `select_for_update` (it waits on unique-index contention, not
> a row lock — the source plan's `C-1` is slightly off on that point); and the scheduler and
> `post_migrate`/`load_catalog`/`seed` paths that would surface a bounded error as a
> `CommandError`.

> **Researcher.** *Goal:* close **Q1** (global `DATABASES["default"]["OPTIONS"]` libpq timeout
> vs. per-transaction `SET LOCAL`) and survey the **Q2** error-boundary options. *Hard
> constraints:* do **not** "fix" this by raising the asgiref worker count — `thread_sensitive`
> exists so a transaction and its connection stay on one thread; **libpq units are
> milliseconds**, so a value written in seconds is a 1000× error; `SET LOCAL` inside a nested
> `atomic()` reverts at the **enclosing** transaction boundary, not the savepoint.
> *Files + symbols:* `config/settings/base.py::DATABASES` (both branches); `ALLOWED_ENV_VARS`;
> `config/settings/tests/test_env_allowlist.py` **and** `test_env_allowlist_reverse.py`
> (**D-10**); the eight `time.sleep(1.0)` row-lock concurrency tests (**D-3**);
> `apps/core/tests/test_sweep_lock_structure.py::TestSweepLockOrdering`.
> *Must return:* the chosen Q1 option with the chosen value **and its unit stated**, an
> explicit resolution of `test_sweep_archive.py::TestArchiveSweepRowLockConcurrency` (which
> exercises `archive_sweep` itself and holds a lock ~1 s), a statement of which deployment
> pooling mode is in use, and the Q2 recommendation with per-site retry-vs-error.

> **Planner.** *Goal:* close **Q2**'s design — where the bounded-retry `OperationalError`
> boundary lives and who owns the seller-facing message — and specify the whole change.
> *Hard constraints:* the boundary must work in **two** execution models (gunicorn sync views
> and aiogram async handlers); the scheduler's `CommandError` path is in scope;
> `test_edit_views_locking.py::TestEditViewsLocking` structurally pins `select_for_update`
> **inside** the view source, `source.count("select_for_update") == 1` in `ad_edit`, and that
> `submit_ad`'s `select_for_update` appears **after** `transaction.atomic` — a `SET LOCAL`
> inserted before the fetch must not shift that ordering. *Files + symbols:* the 15 call sites
> above; `config/settings/base.py`; `src/backend/apps/core/utils/` (a shared helper, Option A);
> `src/telegram_bot/middlewares/connection.py` (**only** if a per-update reset is genuinely
> required — `CONN_MAX_AGE = 0` already closes the connection per update). *Must return:* the
> ordered change list, the env-var + template + allowlist plan under Option A, and the
> doc-edit to `docs/02-database/db-retention.md`.

> **Validator.** *Goal:* confirm the wait is genuinely bounded and observable, and that no new
> unhandled `OperationalError` surfaces as a 500 or an unhandled bot exception. *Hard
> constraints:* change no code; Docker `test` service only. *Must return:* the bounded-wait
> test's red-before/green-after evidence, the state of all **eight** concurrency tests, and a
> per-call-site confirmation that each newly-possible error is handled or deliberately allowed
> to propagate with a stated reason.

**Implementor task.**

```yaml
id: task_03_b05_lock_timeout
title: Bound the row-lock wait and give both processes an OperationalError boundary
priority: high
depends_on: [task_03_b03_record_event_transaction]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 5 — Bound the lock wait and give both processes a retry boundary (DB-004, timeout half)"
extra_context: |
  Q1 AND Q2 ARE DECISION GATES, closed by Researcher + Planner inside this block. Record the
  chosen option in the commit message.
  BLOCK 3 MUST LAND FIRST (03-VAL-002): a statement_timeout produces exactly the class of
  server-side OperationalError that record_event swallows.
  ONLY THE TIMEOUT HALF IS IN SCOPE. The ENT-006 addendum was already shipped by phase 01
  (migrate_locked docstring + the "Requesting session advisory lock %s" line). Do not re-touch
  migrate_locked.py and add no timeout wording to advisory_lock.py's session branch.
  D-3: EIGHT row-lock concurrency tests across SIX files hold for ~1 s, not six tests.
  test_edit_views_locking.py::TestEditViewsRowLockConcurrency (3 tests) is in that set and was
  absent from the source plan. Exclude test_anon_lang_cache.py (cache TTL, not a row lock).
  D-10: a new env var must satisfy BOTH config/settings/tests/test_env_allowlist.py AND
  test_env_allowlist_reverse.py (the 511-line AST scanner). The plan's "one parity test" was wrong.
  D-12/D-13: base.py's DATABASE_URL branch REPLACES OPTIONS wholesale; add any OPTIONS key to
  BOTH branches. A new env var goes in the "Python-consumed" group of ALLOWED_ENV_VARS.
  NEVER raise the asgiref worker count. NEVER re-open CONN_MAX_AGE / connection lifecycle.
  libpq timeout units are MILLISECONDS.

description: >
  A single blocked row lock currently stalls every DB operation in the bot, because all bot DB
  work serialises on the one asgiref thread_sensitive worker holding one thread-local
  connection. Nothing bounds the wait. Land the Q1 timeout mechanism and the Q2 error boundary
  so a lock wait is bounded and observable in both processes, and so every newly-possible
  OperationalError is handled rather than surfacing as a 500 or an unhandled bot exception.

goals:
  - bound the row-lock wait and make the bound observable
  - give every newly-failing row-locking call site a retry-or-error decision
  - keep the six-for-eight shipped concurrency tests asserting what they mean
  - leave CONN_MAX_AGE, connection lifecycle, and the asgiref worker count untouched
  - correct the documentation sentence that claims no lock timeout is configured

files:
  - path: src/backend/config/settings/base.py
    targets: [{ type: module, name: base }]
    semantic_anchors:
      replace_in_body:
        old: 'DATABASES["default"]["OPTIONS"] = {"prepare_threshold": None}'
        new: 'DATABASES["default"]["OPTIONS"] = {"prepare_threshold": None, **LOCK_TIMEOUT_OPTIONS}'
      replace_in_body:
        old: '"OPTIONS": {"prepare_threshold": None},'
        new: '"OPTIONS": {"prepare_threshold": None, **LOCK_TIMEOUT_OPTIONS},'
  - path: src/backend/apps/core/utils/                       # Option A only (shared helper)
    targets: []
    semantic_anchors: {}
  - path: src/backend/apps/ads/services/submission.py        # submit_ad
    targets: [{ type: function, name: submit_ad }]
    semantic_anchors: {}
  - path: src/telegram_bot/handlers/login.py                 # handle_login_orm
    targets: [{ type: function, name: handle_login_orm }]
    semantic_anchors: {}
  - path: src/telegram_bot/handlers/alerts.py                # SavedSearch toggle
    targets: []
    semantic_anchors: {}
  - path: src/backend/apps/ads/views/edit.py                  # ad_edit / ad_archive / ad_reactivate
    targets: []
    semantic_anchors: {}
  - path: src/backend/apps/ads/views/delete.py                # ad_delete
    targets: [{ type: function, name: ad_delete }]
    semantic_anchors: {}
  - path: src/backend/apps/moderation/views/review.py        # approve / reject / ban
    targets: []
    semantic_anchors: {}
  - path: src/backend/apps/moderation/admin_actions.py
    targets: []
    semantic_anchors: {}
  - path: src/backend/apps/moderation/services/moderation_log.py
    targets: [{ type: function, name: set_published }, { type: function, name: set_moderation_failed }]
    semantic_anchors: {}
  - path: src/backend/apps/core/management/commands/archive_sweep.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors: {}
  - path: src/backend/apps/currencies/management/commands/recompute_normalized_prices.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors: {}
  - path: .env.example, .env.dev.example, .env.prod.example, .env.test.example   # Option A only
    targets: [{ type: module, name: env_template }]
    semantic_anchors: {}
  - path: docs/02-database/db-retention.md
    targets: [{ type: module, name: db_retention }]
    semantic_anchors:
      replace_in_body:
        old: "Acquires advisory lock 11; a contending run **blocks** until the lock is granted (no lock timeout is configured)."
        new: "Acquires advisory lock 11; a contending run **blocks** until the lock is granted or a lock timeout is reached."
  - path: src/telegram_bot/middlewares/connection.py        # ONLY if the Researcher justifies it
    targets: [{ type: class, name: ConnectionMiddleware }]
    semantic_anchors: {}

changes:
  - action: add_code
    description: >
      Apply the Q1 decision. Option A: a global lock_timeout (and optionally statement_timeout)
      in DATABASES["default"]["OPTIONS"] as a libpq connection parameter in MILLISECONDS, added
      to BOTH branches, with a named typed constant whose unit is documented; plus an
      ALLOWED_ENV_VARS entry in the "Python-consumed" group and updates to all four
      .env.*.example templates in the SAME commit. Option B: SET LOCAL scoped to each
      row-locking transaction.atomic().
  - action: add_code
    description: >
      Apply the Q2 decision: a shared bounded-retry OperationalError boundary that works in both
      the gunicorn sync web tier and the aiogram async bot tier, applied per the Auditor's
      retry-vs-error classification. Also cover the scheduler's CommandError path.
  - action: edit_doc
    description: >
      Correct the db-retention.md sentence that asserts "no lock timeout is configured" — it
      becomes false the moment a timeout lands.

acceptance_criteria:
  - a call holding a row lock for ~1 s fails fast with a BOUNDED, observable wait instead of
    hanging; the new bounded-wait test was demonstrated RED against the pre-fix code
  - all EIGHT shipped row-lock concurrency tests (six files, D-3) still assert what they mean;
    any that were changed had their intent preserved under a recorded change
  - a test proves the configured value is expressed in the documented unit (libpq = milliseconds)
  - every newly-possible OperationalError is handled or deliberately allowed to propagate with
    a stated reason — no unhandled 500 in a web view, no unhandled exception in a bot handler
  - CONN_MAX_AGE, connection lifecycle and the asgiref worker count are unchanged
  - base.py's ALLOWED_ENV_VARS grouping, the read_env() skip condition and the secret guards
    are untouched (phase 02 owns them)
  - any new env var satisfies BOTH test_env_allowlist.py and test_env_allowlist_reverse.py and
    appears in all four templates; .env.example has no UTF-8 BOM
  - test_sweep_lock_structure.py's `session is False` assertion is untouched
  - docs/02-database/db-retention.md no longer claims "no lock timeout is configured"
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - the Docker gate below is green
```

**Tests required.**

- *Must keep passing unchanged:* the **eight** `time.sleep(1.0)` row-lock concurrency tests
  across **six** files — `ads/tests/test_edit_views_locking.py::TestEditViewsRowLockConcurrency`
  (×3), `ads/tests/test_transition_concurrency.py`, `core/tests/test_sweep_archive.py::
  TestArchiveSweepRowLockConcurrency`, `currencies/tests/test_recompute_command.py::
  TestRecomputeRowLockConcurrency`, `moderation/tests/test_admin_actions.py`,
  `telegram_bot/tests/test_unsubscribe.py`; `test_sweep_lock_structure.py`;
  `test_sweep_archive.py::test_archive_sweep_handle_uses_select_for_update_and_atomic`;
  `test_admin_actions.py::test_bulk_ban_users_must_not_gain_select_for_update`;
  `config/settings/tests/` in full.
- *Must be added:* the **bounded-wait test** — **red against the pre-fix code** (which hangs);
  the unit-expression test; under Option A the env-var parity assertion.
- *Must be changed:* none expected.

**Exact gate command (Docker only).**

```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/config/settings/tests/ src/backend/apps/core/tests/ src/backend/apps/ads/tests/ src/backend/apps/moderation/tests/ src/backend/apps/currencies/tests/ src/telegram_bot/tests/" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk (highest):* a global timeout below ~1 s turns eight shipped concurrency tests red and
  the Implementor "fixes" the tests instead of the value. The value must let those tests keep
  asserting what they mean, **or** their intent must be preserved under a deliberate, recorded
  change.
- *Risk:* a new `OperationalError` path surfacing as an uncaught 500. Q2's inventory prevents it.
- *Risk:* clobbering phase 02's concurrent edits to `base.py` or a template — `base.py` is the
  second-most contended file after `conftest.py`. Re-read immediately before editing.
- *Risk:* a `SET LOCAL` in an `atomic()` nested inside a longer transaction — the `SET` reverts
  at the **enclosing** boundary. The Implementor must know which case each `atomic()` is.
- *Rollback:* the setting and the per-site edits are independently revertible, but the **error
  handling** must be reverted together with the setting or the code carries a handler for an
  error that can no longer occur. No schema change.

---

### BLOCK 6 — Idle-timeout semantics for drafts (`03-DB-003`)

| | |
|---|---|
| **Findings owned** | `03-DB-003` (absorbs phase 01's `ENT-009`) |
| **`depends_on`** | BLOCK 1 (soft: same file, `sweep_drafts.Command.handle`) |
| **Priority** | P1 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Roster decision — CONFIRMED unchanged; all five.** Re-verified at `ba23277`: the FSM
inventory is **≈15 mutating handlers across 6 modules**, not "~10" (§3.9 of the code context;
`R-7`). That materially strengthens the Auditor (a missed handler re-creates the exact defect)
and the Planner (mapping 15 touch points is design, not transcription). Q5 and Q6 remain
genuine. HIGH: a wrong choice either reaps live drafts (data loss) or keeps junk forever, and
neither failure is visible in the suite.

**Grouping decision (carried forward).** The three parts — heartbeat + predicate + migration,
the seller-facing message, and the `_STAGING_TTL_SECONDS` re-derivation — are **one end-to-end
contract** ("an idle draft is reaped, a live one is not"). Splitting them produces three states
in which the system is worse than before. The internal order below is cheaper than three
review passes over the same function.

**Decision gates — Q5 and Q6: CLOSED** by the Researcher (`{context_r}` §2.4, §4, §8) and
this Planner. The option tables in the source plan §3.6.1–§3.6.2 are **superseded**. Do not
re-open either gate, do not substitute an alternative, do not "improve" on them.

- **Q5 — Option A, *restructured*.** One `touch_draft(ad_id)` call at the **entry** of each
  of the **11** `@router.*(AdCreateForm.<state>)` handlers — **not** one call per `update_data`
  site — plus a **new AST coverage-guard test** (`test_ad_create_heartbeat_coverage.py`) that
  turns a missed handler into a **red test** instead of silent data loss. The six non-decorated
  helpers are each reachable only from one of the 11, so **11 entry calls cover 13 functions
  and all 16 mutation sites**. **Option B (a new aiogram middleware) is REJECTED** — unbounded
  write amplification on a multi-tap toggle (`process_features`), it cannot tell a dialog step
  from an update that changed nothing, and because phase 05's `AD-016` FSM-state decision is
  out of scope a reaped draft's FSM is never cleared, so a middleware would spin on **0-row**
  writes indefinitely. Full argument: `{context_r}` §2.4.
- **Q6 — `_STAGING_TTL_SECONDS` STAYS `2 * 60 * 60`.** The plan's dichotomy ("inactivity
  window" vs. "worst-case dialog duration") was a **false choice**; the number does not move.
  Instead add a **2-site filesystem touch** (`process_photos`, `process_preview`) so `staging/`
  file mtimes and the row's `updated_at` share one clock. The pre-existing justification
  ("2 hours — safely beyond the 30-minute DRAFT retention") is **false** after this change and
  is replaced by the invariant in `{context_r}` §4.4. **BLOCK 8 depends on the TTL being
  settled by this block** and must re-read the value, not assume it.

**Message detection — CLOSED.** `process_preview` probes row existence on the **failure path
only**, via the already-exported `ad_data._get_ad_status(data["ad_id"])`; `None` ⇒ the draft
is gone ⇒ answer a **new appended** msgid. One extra `SELECT … LIMIT 1`, **only when something
already failed**, so the happy path is untouched. String comparison against
`str(_("Ad not found"))` is **rejected** (locale-fragile; the bot would pattern-match a
service's msgid). A richer `submit_ad` return is **rejected** — phase 05's `AD-016` owns it.
The probe **must not** change `state.clear()`: **BLOCK 6 owns the message, phase 05 owns the
state**, and exactly **one** "your draft expired" string may exist.

**Migration verification — CLOSED, and it DROPS a gate.** `config/settings/test.py::
DisableMigrations` makes pytest-django build `test_mko_bazuna` by **model introspection**, so
`0008_*` is **never replayed by any gate**; `test-recreate` therefore buys nothing for an index
migration, and it omits `PYTEST_SKIP_MARKERS=seed` (≈35 min including `seed`). Replacement:
`makemigrations --check --dry-run`; a real `migrate` **forward and back on a scratch database**;
a `pg_indexes` assertion in a **non-transactional** `django_db` test. See C6-5.

**Corrections to this block's source plan — binding on the Implementor.**

| # | The source plan says | Anchor reality | Correction |
|---|---|---|---|
| **C6-1** | Two defective shipped tests; "leave `test_dry_run_does_not_delete` alone" | It back-dates only `created_at`, so after the flip its ad is **not even eligible** — the sweep deletes nothing with or without `--dry-run`. It becomes **vacuously green**. | **THREE** defective tests, not two. `test_dry_run_does_not_delete` must back-date `updated_at` **and** prove eligibility (assert the `DRY RUN: Would delete 1 …` count), or it proves nothing. |
| **C6-2** | `test_collects_thumbnail_keys_for_media_cleanup` needs a back-date | Red after the flip **and its docstring is already false**: it credits the sweep with passing `AdImage.storage_keys()` to `delete_photo`, which BLOCK 1 (`d913088`) deleted. The mechanism is now the `AdImage` `pre_delete` signal → `transaction.on_commit`. | Rewrite the docstring to state the truth; the sweep's only obligation is to make the row eligible. Keep the `monkeypatch` target `"apps.media.signals.delete_photo"` (it is correct). The commit message must say this is **BLOCK 1 debt fixed in passing**. |
| **C6-3** | DoD: a reaped draft renders the *generic* moderation text; check it is "not the generic text" | `bb034e9` made `process_preview` render `str(errors[0])` when `errors` is non-empty, and `submit_ad` always returns a non-empty list ⇒ the generic string is **unreachable**. | That half of the DoD is a **tautology that cannot fail**. Restated falsifiable DoD (`{context_r}` §6.2) is carried verbatim into the Implementor task's `acceptance_criteria`. |
| **C6-4** | BLOCK 6 owns the bot failure surface; the plan's test list does not mention the bot tests | **Two shipped tests already assert the reaped-draft message**: `test_lock_timeout_boundary.py::TestProcessPreviewLockTimeout::test_moderation_failure_is_rendered_in_russian` / `::…_in_bosnian` drive the **real** `submit_ad` with `ad_id = 999_999_999` (forcing `Ad.DoesNotExist`) through the **real** `process_preview` and assert `== "Объявление не найдено"` / `== "Oglas nije pronađen"`. Their docstrings claim `Ad failed moderation checks` while asserting "Ad not found". | They must be **updated**, not merely accompanied — they are the right home for the new assertions. Fix the docstrings. A **genuine** moderation-failure test (real ad that fails moderation) must still render `"Ad failed moderation checks"`. |
| **C6-5** | Gate: `.\Makefile.ps1 test-recreate` **first**, after the migration | `DisableMigrations` ⇒ migrations are never replayed in tests; `test-recreate` also omits `PYTEST_SKIP_MARKERS=seed`. | **`test-recreate` is dropped from the gate.** The removal **and its reason** must be stated in the commit message — an unexplained removal looks like a shortcut. |
| **C6-6** | "`create_test_ad`'s docstring instructs back-dating via `QuerySet.update()`" | **No such instruction exists** — the docstring mentions only the five status-coupled timestamps; `**kwargs` cannot back-date because `auto_now_add` overwrites it. | Conclusion unchanged, provenance wrong. Back-date **locally**: `Ad.objects.filter(pk=…).update(updated_at=…)` + `refresh_from_db()`. `conftest.py` stays untouched. |
| **C6-7** | Q5 Option A: "~10 touch points"; the ordering argument rests on `updated_at == created_at` for an untouched draft | **13 mutating functions / 16 `update_data` sites**, 3 of them in non-decorated helpers. Measured `updated_at − created_at` on an untouched draft is **+12…+26 µs, never negative**. | Coverage becomes 13/16 (covered by the 11 entry calls). The ordering argument **survives**; its wording does not — the flip alone is at worst **marginally more permissive**, never more aggressive. |
| **C6-8** | "`updated_at` on a DRAFT is written only by the bot" | `apps/ads/views/edit.py::ad_edit`'s direct-save branch also bumps a DRAFT's `updated_at`; ownership is its only gate. | It **refreshes** rather than starves, so the predicate stays safe — but the **documentation must name it** instead of assuming it away. |
| **C6-9** | `process_preview` is "terminal" and not a heartbeat target | It is the state a seller **deliberates in** — the single most likely place to idle past 30 minutes, i.e. the exact defect. It is harmless when the ad is gone (the `status=DRAFT` filter yields 0 rows — measured). | `process_preview` **is** one of the 11 heartbeat call sites, and one of the 2 filesystem-touch sites. |

**Named accepted risks (recorded, not re-litigated).** From `{context_r}` §7:

| Risk | Disposition |
|---|---|
| A heartbeat site missed today ⇒ a live draft is reaped (the original defect) | **Mitigated to zero at merge time** by entry placement + the two-way AST guard (handlers→states *and* states→handlers). **Residual accepted:** a handler on a **non-`AdCreateForm`** state is outside the guard's scope. |
| A future "helpful" full `save()` heartbeat clobbers a publish | **Mitigated** by the single-column form (measured: a stale `save()` wrote `status='draft'` + a stale title over a just-published ad, leaving `published_at` set — a row that is simultaneously DRAFT and already gone from the site). The helper's **docstring** must carry that argument, not just the shape. |
| An escaping lock-timeout `OperationalError` aborts the handler, stalling the single worker | **Mitigated** by fail-soft `is_lock_timeout`. **Residual accepted:** a lost heartbeat degrades that one dialog to the pre-fix 30-minute-creation-age behaviour — it must never cost the seller their step. |
| ~11 extra single-column UPDATEs per dialog on the single `thread_sensitive` worker | **Accepted.** Measured 1.1–1.7 ms each, ≤11 per dialog, ≈0.4–0.6 % of worker time at 100 concurrent dialogs. No mitigation. |
| `0008_*` is never executed by any gate | **Accepted with a manual gate** (`makemigrations --check`, scratch-DB `migrate` fwd/back). Not fixable without un-shipping `DisableMigrations`, which is out of scope. |
| Rolling back the predicate while keeping the heartbeat (or the reverse) | **Accepted.** Revert **both or neither**; land model + `0008_*` + predicate as **one** commit so `makemigrations --check` is never red in between. |
| `ads/0008_*` number collides with a concurrent phase | **Accepted.** Re-check `apps/ads/migrations/` **immediately before** generating (last is `0007_adimage_ix_adimages_image_and_more` as of `bb034e9`). Two migrations with one number is a hard failure. |
| `pytest-randomly` reordering + the pre-existing `django_db(transaction=True)` teardown flush | **Pre-existing, not BLOCK 6's.** The new `pg_indexes` guard test **must** be **non-transactional**. |

**Logged, NOT fixed here.** `apps/media/services/filesystem.py::move_staging_to_permanent`
guards its rename with `if os.path.exists(...)` and then **unconditionally** does
`setattr(photo, field, permanent_key)`. If a staging file has already been reclaimed, the key
is rewritten to a permanent path that does not exist and `AdImageService.create_or_skip` creates
the row — a live ad with a permanently broken image that the orphan sweep will never reclaim.
**Pre-existing defect in `apps/media`; new finding for phase 07 / BLOCK 8. Do not fix it in
this block.** It is the real severity of the staging-TTL question, and it is why the
filesystem touch ships.

**Binding constraints carried forward.**

1. **The spec is already on the implementation's side.** The spec and the seller stories both
   say *idle*; the code measures age since creation. The spec-conformant fix is the cheaper one.
   **Keep 30 minutes** — `db-retention.md` states retention values are hardcoded and read from
   source. **Do not** make the window environment-configurable.
2. **The index must change with the predicate** — `IX_ads_draft_sweep` from
   `["status","created_at"]` to `["status","updated_at"]`, via a new `ads/0008_*` migration
   doing `RemoveIndex` + `AddIndex`.
3. **THREE shipped green tests are defective, not two, and none may be left alone**
   (**C6-1**, **C6-2**): `test_dry_run_does_not_delete` (vacuously green unless it is made
   non-vacuous), `test_deletes_drafts_older_than_30_minutes`, and
   `test_collects_thumbnail_keys_for_media_cleanup` (docstring already false — BLOCK 1 debt).
   `test_does_not_touch_published_drafts` still meaningfully tests the **status** filter and is
   not required to change; `test_dedup_migration_collapses_duplicate_drafts` and
   `test_lock_id_is_sweep_drafts` are untouched.
4. **`src/backend/conftest.py` is untouchable** (`create_test_ad` never sets `created_at` or
   `updated_at`, both `auto_*`, and `**kwargs` cannot back-date either). Back-date locally
   with `Ad.objects.filter(pk=…).update(updated_at=…)` + `refresh_from_db()`. Note **C6-6**:
   the fixture's docstring carries **no** back-dating instruction — the plan's claim otherwise
   is wrong; only the conclusion stands.
5. **Mandatory internal order** is the six-commit sequence in the Implementor task below; the
   two load-bearing orderings are **(i)** helper + call sites + AST guard land **together**
   (an unprotected heartbeat is the Auditor's named risk) and **(ii)** model + `0008_*` +
   predicate flip land as **one** commit, so `makemigrations --check` is never red in between.
6. **The heartbeat write** must be a single-column `UPDATE`, not a full `save()`, and must not
   open a transaction of its own beyond the statement — it lands on the single shared asgiref
   worker thread.
7. **`uq_ads_single_draft_per_user` is a partial unique index**, so `SET CONSTRAINTS` cannot
   defer it. Recorded so no Implementor confuses it with BLOCK 3's reasoning.
8. **The `ad_data` service boundary is hard.** The helper lives in
   `telegram_bot/services/ad_data/orm.py` and is re-exported in `__init__.py`/`__all__`.
   **`apps.*` must never import `telegram_bot.*`.**
9. **Documentation surface is exactly two files** (**N-3**): `docs/02-database/db-retention.md`
   and `docs/02-database/db-indexes.md`. Do **not** touch
   `technical-specification.md`, `seller-stories.md` (both already say *idle* and become more
   correct), or `architecture.md` (no draft-retention section; **and it is currently dirty
   with another phase's uncommitted work — N-1**).

**Agent briefs (paste-ready).**

> **Auditor.** *Goal:* re-derive the FSM step inventory and confirm no other code path filters
> drafts by `created_at`. *Hard constraints:* change no code; never target a line number.
> *Files + symbols:* `src/telegram_bot/handlers/ad_create/` — `entry.py::cmd_post` (the only
> writer of the FSM key `ad_id`), `category.py` (`process_category`,
> `process_category_selected`, `process_purpose`, `process_condition`, `process_features`,
> `proceed_to_features_or_city`, `_show_features_or_city_step`), `city.py::process_city`,
> `text.py::process_title` / `::process_description`,
> `price.py::process_price_currency` / `::process_price`, `photos.py::process_photos`,
> `submit.py::process_preview`, `preview.py::show_preview` (non-router render helper).
> *Must return:* the complete list of handlers that mutate an ad input — **≈15 across 6
> modules**, explicitly listing `listing_purpose_id` and `condition_id` (both in
> `SubmitAdInput`, both easy to forget); and a statement of every place that filters `Ad` by
> `created_at`.

> **Researcher.** *Goal:* close **Q5** (explicit `touch_draft(ad_id)` call per handler vs. a new
> aiogram middleware keyed on the `AdCreateForm.*` states) and **Q6** (whether the staging TTL
> must be re-derived, whether staging files need touching, or whether a documented loss is the
> honest answer). *Hard constraints:* the package has **four** middlewares today
> (`connection`, `language`, `permissions`, `update_id_dedup`); the middleware already has a
> precedent to follow — `update_id_dedup` reads `state.get_data()["ad_id"]`-shaped context;
> a filesystem touch (`os.utime`) is a FS side effect and must respect TX-then-FS and must not
> run inside a transaction. *Files + symbols:*
> `telegram_bot/services/ad_data/orm.py`, `ad_data/__init__.py`,
> > `apps/media/management/commands/sweep_orphaned_media.py::_STAGING_TTL_SECONDS`
> (currently `2 * 60 * 60`), `_reclaim_stale_staging`. *Must return:* the chosen Q5 option with
> the per-dialog write count quantified (fire-and-forget `UPDATE` vs. piggybacking an existing
> write), and the Q6 decision with the orphan-photo-loss window quantified.

> **Planner.** *Goal:* design the whole block — the new bot↔DB write contract, the migration,
> the seller-facing error surface and the i18n set. *Hard constraints:* a **new user-visible
> string** must have a non-empty `msgstr` for **both** `ru` and `bs`; locale files are a
> **shared artefact** — **append, never regenerate wholesale** (a full `makemessages` would
> discard a concurrent phase-14 addition); the error surface is
> `submit_ad`'s `return False, ["Ad not found"]` branch and `submit.py::process_preview`'s
> currently generic `_("Ad failed moderation. Please check your content and try again.")`
> followed by `state.clear()` — the reaped draft loses all typed work with a misleading
> message. *Must return:* the ordered implementation sequence, the migration shape, the exact
> new msgids, and the FSM touch-point map.

> **Validator.** *Goal:* confirm retention semantics actually changed and that no live draft
> can be reaped. *Hard constraints:* change no code. *Must return:* evidence that a draft with an
> old `created_at` and a recent `updated_at` **survives**, that an old `updated_at` is
> **deleted**, that the two rewritten tests were red before the fix, and that the i18n gate
> passed.

**Implementor task.**

```yaml
id: task_03_b06_idle_timeout
title: Measure draft staleness by inactivity (updated_at) with a bot heartbeat, not by age since creation
priority: high
depends_on: [task_03_b01_remove_storage_keys_precollection]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 6 — Idle-timeout semantics for drafts (DB-003)"
extra_context: |
  Q5 AND Q6 ARE CLOSED — see "Decision gates" and "Corrections" above. Do not re-open them,
  do not substitute an alternative.
    Q5 = Option A, RESTRUCTURED: one `touch_draft(ad_id)` call at the ENTRY of each of the
      11 `@router.*(AdCreateForm.<state>)` handlers — NOT one call per `update_data` site — plus
      a NEW AST coverage-guard test. The 11 entry calls cover 13 functions and all 16 mutation
      sites. Middleware (Option B) is REJECTED.
    Q6 = `_STAGING_TTL_SECONDS` STAYS `2 * 60 * 60`; add a 2-site filesystem touch so
      `staging/` mtimes and the row's `updated_at` share one clock.
  MESSAGE DETECTION IS CLOSED: `process_preview` probes `ad_data._get_ad_status(data["ad_id"])`
  on the FAILURE PATH ONLY; `None` means the draft is gone. `state.clear()` is UNCHANGED —
  phase 05's `AD-016` owns it. Exactly ONE "your draft expired" string may exist.
  MIGRATION VERIFICATION IS CLOSED: `.\Makefile.ps1 test-recreate` is DROPPED from the gate
  (DisableMigrations means migrations are never replayed; it costs ~35 min and buys nothing).
  The removal and its reason MUST appear in the commit message.
  SIX-COMMIT SEQUENCE (see `implementation_sequence`): helper+exports -> call sites + AST guard
  -> the three defective tests (red) -> model + 0008_* + predicate (ONE commit) -> message ->
  docs. A wrong order reaps live drafts.
  KEEP THE 30-MINUTE WINDOW. Do not make retention environment-configurable; db-retention.md
  states retention values are hardcoded in the command sources — that sentence is a
  CONSTRAINT, not an edit target.
  src/backend/conftest.py MUST NOT BE EDITED, and its docstring carries NO back-dating
  instruction (C6-6). Back-date locally with
  `Ad.objects.filter(pk=...).update(updated_at=...)` + `refresh_from_db()`.
  DOC SURFACE IS EXACTLY TWO FILES (execution plan 13 §1.3 N-3):
  docs/02-database/db-retention.md and docs/02-database/db-indexes.md.
  Do NOT edit docs/01-spec/technical-specification.md or docs/04-user-stories/seller-stories.md
  (both already state "idle timeout" and become MORE correct after this change) and do NOT
  edit docs/99-agent/architecture.md (no draft-retention section; also currently dirty with
  another phase's uncommitted work).
  The heartbeat helper lives in telegram_bot/services/ad_data/ and MUST NOT be imported from apps.*
  The new user-visible string needs non-empty msgstr for ru AND bs; `en` stays empty.
  Locale files are SHARED — append, never run a wholesale makemessages.
  The heartbeat must be a single-column UPDATE, not a full save().
  LOGGED, NOT FIXED HERE: `move_staging_to_permanent`'s `os.path.exists` guard followed by an
  unconditional `setattr` creates a dangling `AdImage` reference (phase 07 / BLOCK 8).

description: >
  sweep_drafts measures staleness from Ad.created_at (stamped once at /post) with no heartbeat,
  so an in-progress ad dialog that takes longer than 30 minutes has its draft reaped and all
  the seller's typed work is lost behind a misleading generic moderation-failure message. The
  spec and the seller stories both already say "idle timeout". Add a bot heartbeat that writes
  Ad.updated_at on every step that changes an ad input, flip the predicate to updated_at, ship
  the index migration with it, and give the expired-draft failure a translated,
  seller-recoverable message.

goals:
  - a live dialog's draft is never reaped
  - an idle draft is still reaped after 30 minutes
  - the sweep query stays indexed on (status, updated_at)
  - an expired draft produces a translated, seller-recoverable message instead of the generic
    moderation-failure text plus a state clear
  - keep the retention window at 30 minutes and hardcoded

files:
  - path: src/telegram_bot/services/ad_data/orm.py                      # heartbeat helper (NEW)
    targets: [{ type: function, name: touch_draft }, { type: constant, name: __all__ }]
    semantic_anchors:
      add_to_list:
        target: __all__
        value: '"touch_draft"'          # 9 names -> 10
  - path: src/telegram_bot/services/ad_data/media.py                     # staging touch (NEW)
    targets: [{ type: function, name: touch_staging_photos }, { type: constant, name: __all__ }]
    semantic_anchors:
      add_to_list:
        target: __all__
        value: '"touch_staging_photos"' # 2 names -> 3
  - path: src/telegram_bot/services/ad_data/__init__.py                  # THREE export edits
    targets: [{ type: module, name: ad_data }]
    semantic_anchors:
      add_to_import_from:
        module: '.orm'
        names: ['touch_draft']
      add_to_import_from:
        module: '.media'
        names: ['touch_staging_photos']
      add_to_list:
        target: __all__
        value: ['"touch_draft"', '"touch_staging_photos"']   # 21 -> 23 names, hand-ordered
  # 11 DB-heartbeat entry call sites + 2 filesystem-touch call sites
  - path: src/telegram_bot/handlers/ad_create/category.py                # 4 handlers
    targets: [{ type: function, name: process_category }, { type: function, name: process_purpose },
              { type: function, name: process_condition }, { type: function, name: process_features }]
    semantic_anchors: {}
  - path: src/telegram_bot/handlers/ad_create/city.py
    targets: [{ type: function, name: process_city }]
    semantic_anchors: {}
  - path: src/telegram_bot/handlers/ad_create/text.py
    targets: [{ type: function, name: process_title }, { type: function, name: process_description }]
    semantic_anchors: {}
  - path: src/telegram_bot/handlers/ad_create/price.py
    targets: [{ type: function, name: process_price_currency }, { type: function, name: process_price }]
    semantic_anchors: {}
  - path: src/telegram_bot/handlers/ad_create/photos.py                  # DB + FS touch
    targets: [{ type: function, name: process_photos }]
    semantic_anchors: {}
  - path: src/telegram_bot/handlers/ad_create/submit.py                  # DB + FS touch + message
    targets: [{ type: function, name: process_preview }]
    semantic_anchors: {}
  # NOT targets: entry.py (cmd_post creates the row; cmd_cancel deletes it), preview.py
  #             (show_preview is a presenter, already covered transitively), and the six
  #             non-decorated helpers (reachable only from the 11).
  - path: src/backend/apps/core/management/commands/sweep_drafts.py
    targets: [{ type: function, name: Command.handle }, { type: attribute, name: Command.help },
              { type: module, name: sweep_drafts }]
    semantic_anchors:
      replace_in_body:
        target: Command.handle
        old: 'Ad.objects.filter(status=AdStatus.DRAFT, created_at__lt=cutoff_date)'
        new: 'Ad.objects.filter(status=AdStatus.DRAFT, updated_at__lt=cutoff_date)'
  - path: src/backend/apps/ads/models.py                                 # 12th and LAST index
    targets: [{ type: class, name: Ad }, { type: attribute, name: 'Ad.Meta.indexes' }]
    semantic_anchors:
      replace_in_body:
        target: Ad.Meta.indexes
        old: 'name="IX_ads_draft_sweep",\n                fields=["status", "created_at"],'
        new: 'name="IX_ads_draft_sweep",\n                fields=["status", "updated_at"],'
  - path: src/backend/apps/ads/migrations/0008_change_ix_ads_draft_sweep.py   # NEW
    targets: [{ type: module, name: migration }]
    semantic_anchors: {}
  - path: src/backend/apps/media/management/commands/sweep_orphaned_media.py  # COMMENT ONLY
    targets: [{ type: constant, name: _STAGING_TTL_SECONDS }, { type: function, name: _reclaim_stale_staging }]
    semantic_anchors: {}
  # Tests
  - path: src/backend/apps/core/tests/test_sweep_drafts.py               # THREE defective tests
    targets: [{ type: method, name: 'TestSweepDrafts.test_dry_run_does_not_delete' },
              { type: method, name: 'TestSweepDrafts.test_deletes_drafts_older_than_30_minutes' },
              { type: method, name: 'TestSweepDrafts.test_collects_thumbnail_keys_for_media_cleanup' }]
    semantic_anchors: {}
  - path: src/telegram_bot/tests/test_lock_timeout_boundary.py           # TWO shipped tests
    targets: [{ type: method, name: 'TestProcessPreviewLockTimeout.test_moderation_failure_is_rendered_in_russian' },
              { type: method, name: 'TestProcessPreviewLockTimeout.test_moderation_failure_is_rendered_in_bosnian' }]
    semantic_anchors: {}
  - path: src/telegram_bot/tests/test_ad_create_heartbeat_coverage.py    # NEW — AST guard
    targets: [{ type: module, name: test_ad_create_heartbeat_coverage }]
    semantic_anchors: {}
  # Docs + locale (append-only)
  - path: docs/02-database/db-retention.md                # 4 disjoint regions (N-3)
    targets: [{ type: module, name: db_retention }]
    semantic_anchors: {}
  - path: docs/02-database/db-indexes.md                  # IX_ads_draft_sweep fields + comment
    targets: [{ type: module, name: db_indexes }]
    semantic_anchors: {}
  - path: src/backend/locale/ru/LC_MESSAGES/django.po     # APPEND, never regenerate
    targets: [{ type: module, name: django_po }]
    semantic_anchors: {}
  - path: src/backend/locale/bs/LC_MESSAGES/django.po     # APPEND, never regenerate
    targets: [{ type: module, name: django_po }]
    semantic_anchors: {}
  - path: src/backend/locale/en/LC_MESSAGES/django.po     # APPEND, msgstr stays EMPTY
    targets: [{ type: module, name: django_po }]
    semantic_anchors: {}
  # NOT touched: src/backend/conftest.py;
  #             apps/ads/services/submission.py; apps/ads/views/edit.py;
  #             Ad.transition_to; telegram_bot/main.py; the middlewares/ package;
  #             handlers/ad_create/entry.py; handlers/ad_create/preview.py;
  #             db-retention.md's "All retention values are hardcoded ..." sentence;
  #             docs/01-spec/technical-specification.md; docs/04-user-stories/seller-stories.md;
  #             docs/99-agent/architecture.md.

architectural_constraints:
  - >-
    `apps.*` must NEVER import `telegram_bot.*`; the helper lives in
    `telegram_bot/services/ad_data/` and is re-exported through that package's `__init__.py`
    and `__all__` (three coordinated export edits per new helper). `sweep_drafts.py` must not
    call it.
  - >-
    The heartbeat is a SINGLE-COLUMN `QuerySet.update()` filtered on
    `status=AdStatus.DRAFT`, wrapped in an inner `@sync_to_async` closure (the module's stated
    contract). NEVER `save()`, and never `save(update_fields=[...])` without `"updated_at"`:
    `auto_now` is a `Model.save()` pre-save hook, `QuerySet.update()` never fires it, and a
    full save was MEASURED to clobber a concurrent `submit_ad`.
  - >-
    The heartbeat is FAIL-SOFT: catch `OperationalError`, distinguish SQLSTATE 55P03 with
    `apps.core.utils.db_lock_timeout.is_lock_timeout`, log and return; re-raise anything else.
    It must never open a transaction beyond the statement.
  - >-
    `sweep_drafts`' window stays 30 MINUTES and hardcoded; the `dry_run` -> `atomic()` ->
    `advisory_lock(4)` -> `cutoff_date` -> filter -> `count()` -> dry-run early return ->
    `queryset.delete()` ordering is preserved, and `test_sweep_lock_structure.py`'s
    `session is False` assertion is UNTOUCHED.
  - >-
    `src/backend/conftest.py` is NEVER edited. Back-date locally with
    `Ad.objects.filter(pk=...).update(updated_at=...)` + `refresh_from_db()`.
  - >-
    `db-retention.md`'s "All retention values are hardcoded ..." sentence is a CONSTRAINT, not
    an edit target — it stays true because the window does not move.
  - >-
    The new msgid is APPENDED to ru/bs/en; `ru`/`bs` `msgstr` NON-EMPTY, `en` `msgstr` EMPTY
    (the msgid is English). Locale files are a SHARED artefact — append, never regenerate.
  - >-
    Exactly ONE "your draft expired" string may exist. BLOCK 6 owns the MESSAGE, phase 05's
    `AD-016` owns the STATE: `state.clear()` is unchanged, `submit_ad` is unchanged, and the
    "Ad not found" msgid is unchanged and still rendered by `apps/ads/views/edit.py`.
  - >-
    `test_sweep_drafts.py`'s `monkeypatch` target stays
    "apps.media.signals.delete_photo". No new dependency. `logger`, never `print()`. English
    throughout.
  - >-
    No task target is a line number.
  - >-
    No test asserts on a source line, a log string, or a variable's absence — EXCEPT the AST
    coverage guard, whose entire job is a structural assertion. That is not trivia: the defect
    this block fixes is UNOBSERVABLE from behaviour (a missed heartbeat site is
    indistinguishable from a seller who simply walked away), so the invariant has to be
    asserted over the code's STRUCTURE. It is scoped deliberately — it asserts a POSITIVE
    (every guarded handler calls `touch_draft`) and a TWO-WAY invariant
    (`set(AdCreateForm states) == set(states seen on guarded handlers)`), so it can never pass
    merely because a symbol is missing.

implementation_sequence:                 # ordered so a failure is unambiguous at each step
  - step: 1
    commit: none — recon
    action: >
      Re-read `sweep_drafts.Command.handle` (BLOCK 1 removed `ad_ids` from it — do not assume
      either state). Re-list `apps/ads/migrations/` and confirm `0008_*` is still free
      (phase 05 contends for it). Re-read `git status --short` before every later commit.
    gate: none
  - step: 2
    commit: A — helper + exports (pure addition, zero behaviour change)
    action: >
      `touch_draft` in `ad_data/orm.py` + 3 export edits; `touch_staging_photos` in
      `ad_data/media.py` + 3 export edits. Docstrings carry the `save()`-clobber argument and
      the fail-soft rationale, not just the shape.
    gate: "ruff + basedpyright clean; `makemigrations --check --dry-run` still `No changes detected`"
  - step: 3
    commit: B — call sites + AST guard + focused heartbeat tests
    action: >
      Write `test_ad_create_heartbeat_coverage.py` FIRST and run it RED (it must name the
      unguarded handlers), then add the 11 entry `touch_draft` calls and the 2
      `touch_staging_photos` calls and run it GREEN. An unprotected heartbeat must never land.
    gate: "the guard was demonstrated RED before the call sites existed, then GREEN"
  - step: 4
    commit: C — the THREE defective tests, demonstrated RED
    action: >
      Rewrite `test_dry_run_does_not_delete`, `test_deletes_drafts_older_than_30_minutes` and
      `test_collects_thumbnail_keys_for_media_cleanup` to back-date `updated_at`. Add the
      survival test (old `created_at`, fresh `updated_at`) and the deletion test. Leave them
      RED — the predicate has not flipped yet. That redness is the proof they test the
      predicate and not the delete path.
    gate: "exactly these tests are red and nothing else is"
  - step: 5
    commit: D — model + `0008_*` + predicate, ONE commit
    action: >
      `Ad.Meta.indexes` `fields=["status","created_at"]` -> `["status","updated_at"]` (12th and
      LAST entry, so a clean single-token replacement); generate `0008_*` (`RemoveIndex` then
      `AddIndex`, `dependencies` on `0007_adimage_ix_adimages_image_and_more`); flip the
      `sweep_drafts` predicate and its four creation-age prose sites. Add the `pg_indexes`
      guard test (NON-transactional `django_db`).
    gate: >
      `makemigrations --check --dry-run` -> `No changes detected`; commit C's three tests are
      GREEN; the survival test is GREEN
  - step: 6
    commit: E — the reaped-draft message
    action: >
      `process_preview`: failure-path row-existence probe -> answer the NEW msgid; update the
      TWO shipped bot tests in `test_lock_timeout_boundary.py`; add the genuine
      moderation-failure test; append the msgid to ru/bs/en.
    gate: "the two shipped tests pass with the new msgstr; a real moderation failure still renders `Ad failed moderation checks`; the i18n gate is green"
  - step: 7
    commit: F — documentation
    action: >
      `db-retention.md`'s four regions + the new staging-coupling paragraph; `db-indexes.md`;
      the `_STAGING_TTL_SECONDS` comment and `_reclaim_stale_staging`'s docstring.
    gate: "no other document has a modified mtime in `git status --short -- docs`"
  - step: 8
    commit: none — gates
    action: "run the full gate list below"
    gate: "all green"

changes:
  - action: add_code
    description: >
      `touch_draft(ad_id)` in `ad_data/orm.py`: `async def` wrapping an inner `@sync_to_async`
      closure that issues ONE single-column
      `Ad.objects.filter(id=ad_id, status=AdStatus.DRAFT).update(updated_at=timezone.now())`,
      fail-soft on `is_lock_timeout`. Docstring must carry the measured clobber argument and
      the fail-soft rationale.
  - action: add_code
    description: >
      `touch_staging_photos(photos)` in `ad_data/media.py`: skip keys without `STAGING_PREFIX`,
      `os.utime` each under `settings.MEDIA_ROOT` via `asyncio.to_thread` (never on the event
      loop, never inside a transaction), `FileNotFoundError` -> skip, `OSError` -> log and
      continue.
  - action: edit_code
    description: >
      11 entry `touch_draft` calls, one per `@router.*(AdCreateForm.<state>)` handler, as the
      first statement after the existing guards and BEFORE any branch, guarded by
      `if data.get("ad_id") is not None:`. Add the `state.get_data()` call where absent; do not
      remove one where `data` is already bound. `process_preview` must hoist a single
      `data = await state.get_data()` to its top (its current one lives inside the `confirm`
      branch) so the heartbeat, the filesystem touch and the probe share one value.
  - action: add_code
    description: >
      2 filesystem-touch calls: `process_photos` and `process_preview`, alongside the DB
      heartbeat — the only two handlers that can ever see a non-empty `data["photos"]`.
  - action: add_test
    description: >
      NEW `src/telegram_bot/tests/test_ad_create_heartbeat_coverage.py` — pure `ast`, no DB, no
      Django import. Collect module-level functions in `handlers/ad_create/*.py` with a
      `router.*` decorator referencing `AdCreateForm.<x>`; assert each contains a call whose
      unparsed source contains `touch_draft`; assert
      `set(AdCreateForm states) == set(states seen on guarded handlers)` (the two-way
      invariant — without it a new state with no handler is invisible). The failure message
      must name the file, the symbol and the states.
  - action: edit_code
    description: >
      `sweep_drafts.Command.handle`: `created_at__lt` -> `updated_at__lt`, window unchanged;
      update the module docstring, `Command.help`, the `DRY RUN` log and the closing log from
      creation-age to inactivity prose.
  - action: edit_code
    description: >
      `Ad.Meta.indexes`: `IX_ads_draft_sweep` `fields=["status","created_at"]` ->
      `["status","updated_at"]`; `name` and `condition` unchanged.
  - action: add_migration
    description: >
      NEW `ads/0008_*`: `RemoveIndex(model_name="ad", name="IX_ads_draft_sweep")` then
      `AddIndex(...)` with the new `fields`, `dependencies` on
      `0007_adimage_ix_adimages_image_and_more`. Reversible by symmetry; no `RunPython`.
      RE-CHECK THE DIRECTORY IMMEDIATELY BEFORE GENERATING.
  - action: edit_code
    description: >
      `process_preview` failure branch: `if await _get_ad_status(data["ad_id"]) is None:` answer
      the NEW msgid, else keep `str(errors[0]) if errors else _("Ad failed moderation. ...")`.
      `state.clear()` UNCHANGED. `submit_ad` UNCHANGED. `\"Ad not found\"` UNCHANGED.
  - action: rewrite_test
    description: >
      THREE defective tests in `test_sweep_drafts.py`, not two. `test_dry_run_does_not_delete`:
      back-date `updated_at` AND prove eligibility (assert the `DRY RUN: Would delete 1 ...`
      count) or it proves nothing. `test_deletes_drafts_older_than_30_minutes`: back-date BOTH
      rows' `updated_at`, keep the two-sided assertion, add a docstring line saying the
      predicate measures inactivity. `test_collects_thumbnail_keys_for_media_cleanup`: back-date
      `updated_at` AND rewrite the FALSE docstring (the `pre_delete` signal collects the keys
      and unlinks on commit; the sweep's only obligation is eligibility). Keep the `monkeypatch`
      target `\"apps.media.signals.delete_photo\"`.
  - action: rewrite_test
    description: >
      `test_lock_timeout_boundary.py::TestProcessPreviewLockTimeout::
      test_moderation_failure_is_rendered_in_{russian,bosnian}`: these two SHIPPED tests already
      drive the reaped-draft path (`ad_id = 999_999_999`) and assert
      `== \"Объявление не найдено\"` / `== \"Oglas nije pronađen\"`. Update them to assert the new
      msgid's `ru`/`bs` `msgstr`, keep `assert rendered != \"Ad not found\"`, keep
      `state.clear.assert_awaited()` (phase 05 owns that assertion), and fix their docstrings —
      they claim `Ad failed moderation checks` while asserting \"Ad not found\".
  - action: add_test
    description: >
      One focused heartbeat test per mechanism, NOT per handler; a 0-row no-op test for a
      non-`DRAFT` row (it pins the `status=DRAFT` guard that makes a publish unclobberable);
      a fail-soft test (`OperationalError(55P03)` must not escape the handler); a
      filesystem-touch test (mtime refreshed, missing file tolerated); the survival test; the
      deletion test; a NON-transactional `pg_indexes` test; and a GENUINE moderation-failure
      test (real ad that fails moderation -> `\"Ad failed moderation checks\"`).
  - action: edit_doc
    description: >
      `db-retention.md`'s FOUR disjoint regions (retention table `DRAFT` row; `### Other sweeps`
      `sweep_drafts` row; the new inactivity paragraph + `## Configuration` sentence; the new
      staging-coupling paragraph) and `db-indexes.md`'s code block + trailing comment + one
      sentence. Touch no other document (N-3).
  - action: edit_code
    description: >
      COMMENT ONLY: replace the now-FALSE justification above `_STAGING_TTL_SECONDS` (the VALUE
      does not change) and `_reclaim_stale_staging`'s \"mirroring the safety margin of the
      30-minute DRAFT retention\" docstring line with the invariant from `{context_r}` §4.4.

commit_message_requirements:
  - >-
    State that Q5 landed as Option A restructured (11 entry call sites + an AST coverage guard)
    and Q6 landed as an UNCHANGED TTL plus a 2-site filesystem touch.
  - >-
    State that `.\Makefile.ps1 test-recreate` was DROPPED from the gate and why: DisableMigrations
    makes pytest-django build the schema by introspection, so `0008_*` is never replayed by any
    gate; the replacement is `makemigrations --check --dry-run` plus a real forward/backward
    `migrate` on a scratch database. An unexplained removal looks like a shortcut.
  - >-
    Record the two PRE-EXISTING debts fixed in passing: BLOCK 1's false
    `test_collects_thumbnail_keys_for_media_cleanup` docstring (the sweep never passed
    `storage_keys()` to `delete_photo`; the `pre_delete` signal does), and the vacuous
    `test_dry_run_does_not_delete`.
  - >-
    Record that `move_staging_to_permanent`'s silent dangling-`AdImage` reference is a NEW
    finding for phase 07 / BLOCK 8 and is deliberately NOT fixed here.
  - >-
    Record that the reaped-draft MESSAGE is BLOCK 6's and the FSM-state decision is phase 05's
    `AD-016`, so exactly one "your draft expired" string exists.
  - >-
    Record that migration verification was manual (a scratch database, named in the message)
    because no gate replays migrations.
  - >-
    Name the migration (`ads/0008_*`) and state that model + migration + predicate landed as
    ONE commit, so `makemigrations --check` was never red in between.

acceptance_criteria:
  # ── retention semantics ──────────────────────────────────────────────────────
  - >-
    A draft with an old `created_at` and a RECENT `updated_at` SURVIVES the sweep — the direct
    regression guard for 03-DB-003.
  - >-
    A draft with an old `updated_at` IS deleted, including when its `created_at` is older
    still: the predicate did not become "created OR updated", it is `updated_at` ONLY.
  - >-
    `sweep_drafts`' window is still 30 minutes and still hardcoded; its `dry_run` ->
    `atomic()` -> `advisory_lock` -> filter -> `count()` -> delete ordering and
    `test_sweep_lock_structure.py`'s `session is False` assertion are unchanged.
  # ── heartbeat ────────────────────────────────────────────────────────────────
  - >-
    Exactly 11 `touch_draft` call sites exist, one at the ENTRY of each
    `@router.*(AdCreateForm.<state>)` handler — `process_category`, `process_purpose`,
    `process_condition`, `process_features`, `process_city`, `process_photos`,
    `process_price_currency`, `process_price`, `process_title`, `process_description`,
    `process_preview` — and the AST guard test proves it, including the
    `listing_purpose_id` and `condition_id` steps that are written from non-decorated helpers.
  - >-
    The AST guard also asserts `set(AdCreateForm states) == set(states seen on guarded
    handlers)` (the two-way invariant), and it was demonstrated RED before the call sites
    existed.
  - >-
    `touch_draft` issues a single-column `UPDATE ... SET "updated_at" ... WHERE id = %s AND
    status = 'draft'` with no `RETURNING`, opens no transaction beyond the statement, and
    returns 0 rows for every non-`DRAFT` status.
  - >-
    A lock timeout (SQLSTATE 55P03) is swallowed and logged, any other `OperationalError`
    propagates, and neither costs the seller their step.
  - >-
    The helper's docstring carries the `save()`-clobbers-a-publish argument, not just the shape
    of the call.
  - >-
    `touch_staging_photos` is called from `process_photos` and `process_preview` only, runs via
    `asyncio.to_thread`, skips keys without the `staging/` prefix, and tolerates a missing file.
  # ── migration + index ────────────────────────────────────────────────────────
  - >-
    `IX_ads_draft_sweep` is on `(status, updated_at)`, `name` and `condition` are unchanged,
    and it is still the 12th and last entry of `Ad.Meta.indexes`.
  - "`makemigrations --check --dry-run` prints `No changes detected`."
  - >-
    A real `migrate` runs 0007 -> 0008 -> 0007 on a SCRATCH database with `showmigrations ads`
    reporting `[X]` on `0008` at both ends; the shared `test_mko_bazuna` and the named volume
    were never touched.
  - >-
    A NON-transactional `django_db` test asserts `pg_indexes.indexdef` for `IX_ads_draft_sweep`
    contains `updated_at`.
  - >-
    `.\Makefile.ps1 test-recreate` is NOT in the gate, and the commit message says why.
  # ── the message (falsifiable, restated DoD) ─────────────────────────────────
  - >-
    A reaped draft renders a DISTINCT, translated, seller-recoverable message — neither
    "Ad not found" nor the generic moderation-failure text (the latter is unreachable since
    `bb034e9`, so that half of the old DoD was a tautology).
  - >-
    The new msgid's `msgstr` is NON-EMPTY for BOTH `ru` and `bs`, `en` stays empty, and the
    catalogues were APPENDED to, never regenerated.
  - >-
    "Ad not found" is UNCHANGED in all three catalogues and is still rendered by
    `apps/ads/views/edit.py` at its two `errors[0]` sites.
  - >-
    A genuine moderation failure (a real ad that fails moderation) still renders
    "Ad failed moderation checks" and never the draft-expired text.
  - >-
    The two SHIPPED tests
    `TestProcessPreviewLockTimeout::test_moderation_failure_is_rendered_in_russian` and
    `::test_moderation_failure_is_rendered_in_bosnian` were UPDATED to the new msgstr and still
    assert `rendered != "Ad not found"` and `state.clear.assert_awaited()`.
  - >-
    Exactly ONE "your draft expired" string exists; `state.clear()` and `submit_ad` are
    UNMODIFIED.
  # ── tests ────────────────────────────────────────────────────────────────────
  - >-
    The THREE defective tests were demonstrated RED against the pre-flip predicate and are
    GREEN after; `test_dry_run_does_not_delete` is non-vacuous (it proves the row was eligible).
  - >-
    `test_collects_thumbnail_keys_for_media_cleanup`'s docstring no longer credits the sweep
    with passing `storage_keys()` to `delete_photo`; its `monkeypatch` target is unchanged.
  - "`src/backend/conftest.py` is UNMODIFIED."
  # ── docs ─────────────────────────────────────────────────────────────────────
  - >-
    `db-retention.md`'s four regions and `db-indexes.md` are updated; the "All retention values
    are hardcoded ..." sentence is UNCHANGED; the retention doc names
    `apps/ads/views/edit.py::ad_edit`'s direct-save branch as a second writer of a DRAFT's
    `updated_at`; and NO other document is touched (`technical-specification.md`,
    `seller-stories.md` and `architecture.md` are all unmodified).
  - >-
    The `_STAGING_TTL_SECONDS` comment no longer claims the 2 hours is "safely beyond the
    30-minute DRAFT retention"; the VALUE is still `2 * 60 * 60`.
  # ── static gates ─────────────────────────────────────────────────────────────
  - "`uv run ruff check src/` exits 0 and `uv run basedpyright src/` reports 0 errors."
  # ── exact gate commands (Docker only — `uv run pytest` locally fails, no DB on :5432) ──
  - |
    ```powershell
    $dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

    # 1. model <-> migration agreement  (falsifiable; must print "No changes detected")
    docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml `
      run --rm --no-deps --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test test `
      python src/backend/manage.py makemigrations --check --dry-run

    # 2. real migrate FORWARD and BACKWARD on a SCRATCH database — NEVER test_mko_bazuna,
    #    NEVER drop the named volume. Credentials come from .env.test.
    $dc exec -T db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS b6_scratch" -c "CREATE DATABASE b6_scratch"
    $scratch = 'postgres://postgres:postgres@db:5432/b6_scratch'
    $dc run --rm --no-deps --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test -e DATABASE_URL=$scratch test python src/backend/manage.py migrate --database=default
    $dc run --rm --no-deps --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test -e DATABASE_URL=$scratch test python src/backend/manage.py showmigrations ads   # 0008 [X]
    $dc run --rm --no-deps --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test -e DATABASE_URL=$scratch test python src/backend/manage.py migrate ads 0007 --database=default
    $dc run --rm --no-deps --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test -e DATABASE_URL=$scratch test python src/backend/manage.py showmigrations ads   # 0008 [ ]
    $dc exec -T db psql -U postgres -d postgres -c "DROP DATABASE b6_scratch"

    # 3. targeted suite  (PYTEST_OPTS is UNQUOTED in the entrypoint and word-splits on spaces;
    #    setting it REPLACES the defaults; never --override-ini=addopts=)
    $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_sweep_drafts.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_ad_constraints.py src/backend/apps/ads/tests/test_edit_views_locking.py src/backend/apps/ads/tests/test_i18n_completeness.py src/backend/apps/media/tests/test_sweep_orphaned_media.py src/telegram_bot/tests/test_lock_timeout_boundary.py src/telegram_bot/tests/test_ad_create_heartbeat_coverage.py src/telegram_bot/tests/test_ad_create.py" test

    # 4. full suite + static gates
    .\Makefile.ps1 test
    uv run ruff check src/
    uv run basedpyright src/
    ```
  - |
    Gate environment notes, all binding:
      - An infra hazard, NOT a test result: `docker compose run` recreates
        `mko-bazuna-test-db-1` and can abort with
        `dependency failed to start: ... is unhealthy` BEFORE pytest runs. Wait ~45 s, retry.
      - `PYTEST_OPTS` is unquoted in `docker/entrypoint-test.sh` and word-splits on spaces:
        bare file paths and single-token flags work; quoted multi-token values do NOT. Setting
        it also replaces the defaults, so targeted runs lose `--reuse-db` and xdist parallelism.
      - Known PRE-EXISTING flakiness, not to be fixed here: `django_db(transaction=True)`
        teardown is a full-table flush that destroys session-scoped reference data.
        Signatures: `ExchangeRateNotFoundError`, `test_bulk_delete_skips_hard_deleted_row`
        seeing leftover `Ad` rows, `test_mko_bazuna is being accessed by other users`.
        ANY new `pg_indexes` guard test MUST be non-transactional.
      - `head`/`tail` do not work in PowerShell; `rg` is unavailable — use the Grep tool or
        `Select-String`.
      - The tree is dirty BY DESIGN and other phases commit concurrently. Never `git reset`,
        `git checkout`, `git stash`, `git clean`, `git add -A`, `git add .`, `git commit -a`.
        Stage EXPLICIT paths. Never touch `.ai/audit/**`, `.ai/plans/**`,
        `src/backend/conftest.py`. Re-read `git status --short` immediately before every
        commit and verify each staged file's diff — another Implementor in this phase hit CRLF
        damage by using `Set-Content` on a `.env.*.example`; use byte-safe edits.
```

**Tests required.** Verification is **inline** — the Implementor runs the gate commands in
`acceptance_criteria` and checks every criterion before marking the task complete. There is
**no separate verification task** and **no `tests_to_run` block**.

- *Must be CHANGED (three, not two — C6-1, C6-2, C6-4):*
  `src/backend/apps/core/tests/test_sweep_drafts.py::TestSweepDrafts::test_dry_run_does_not_delete`
  (back-date `updated_at` **and** prove eligibility, or it is vacuous),
  `::test_deletes_drafts_older_than_30_minutes` (back-date **both** rows' `updated_at`, keep the
  two-sided assertion),
  `::test_collects_thumbnail_keys_for_media_cleanup` (back-date `updated_at` **and** rewrite the
  false docstring — the `pre_delete` signal collects the keys, the sweep only makes the row
  eligible; keep the `monkeypatch` target `"apps.media.signals.delete_photo"`);
  plus `src/telegram_bot/tests/test_lock_timeout_boundary.py::TestProcessPreviewLockTimeout::test_moderation_failure_is_rendered_in_russian`
  and `::test_moderation_failure_is_rendered_in_bosnian` (C6-4 — they already assert the
  reaped-draft message and are **not** in the source plan's list).
- *Must be ADDED:* the AST coverage guard (one test, two-way invariant);
  `test_ad_create_heartbeat_coverage.py` is new; one focused heartbeat test **per mechanism,
  not per handler**; a 0-row no-op test for a non-`DRAFT` row; a fail-soft test for SQLSTATE
  55P03; a filesystem-touch test (mtime refreshed, missing file tolerated); the survival test;
  the deletion test; a **non-transactional** `pg_indexes` test; and a **genuine**
  moderation-failure test asserting `"Ad failed moderation checks"`.
- *Must keep passing UNCHANGED:*
  `test_sweep_drafts.py::TestSweepDrafts::test_does_not_touch_published_drafts`,
  `::test_dedup_migration_collapses_duplicate_drafts`, `::test_lock_id_is_sweep_drafts`;
  all of `apps/core/tests/test_sweep_lock_structure.py` (**`session is False` untouched**);
  `src/backend/apps/ads/tests/test_submission.py`;
  `test_i18n_completeness.py` and `test_i18n_pipeline.py`;
  `apps/media/tests/test_sweep_orphaned_media.py::TestSweepOrphanedMedia::test_staging_file_survives_sweep`,
  `::test_stale_staging_file_reclaimed`, `::test_fresh_staging_file_preserved`,
  and `TestSweepLockScope::test_delete_photo_called_within_lock_scope` (**D-8** — the plan
  names only one class; there are two), plus `test_orphaned_file_is_deleted`,
  `::test_referenced_file_is_kept`, `::test_seed_subdir_excluded`, `::test_dry_run_is_nondestructive`,
  `::test_delete_photo_routing`;
  `src/telegram_bot/tests/test_main.py::test_configure_dispatcher_registers_five_middleware`
  and `::test_language_middleware_before_account_state` (no middleware is added or reordered);
  `test_bot_query_count.py` (the probe costs nothing on the happy path);
  `test_lock_timeout_boundary.py::TestProcessPreviewLockTimeout::test_lock_timeout_answers_busy_and_keeps_state`
  and `::test_non_lock_operational_error_is_reraised`.

**Exact gate command — Docker only.** `uv run pytest` fails locally (no DB on
`localhost:5432`). The full command list, in order, is inside `acceptance_criteria` above;
`.\Makefile.ps1 test-recreate` is **deliberately absent** (C6-5).

**Risk / rollback.**

- *Risk (migration):* a wrong `updated_at` choice either reaps live drafts or keeps junk
  forever. **This is data loss, and the suite cannot see it** — the AST guard is the only
  mechanical defence, which is why it lands with the call sites.
- *Risk:* the heartbeat adds up to 11 UPDATEs per dialog to the single shared asgiref worker
  thread — the same queue BLOCK 5 is about to bound. **Accepted** (measured 1.1–1.7 ms each).
- *Risk:* an escaping lock-timeout stalls the single worker for up to BLOCK 5's 10 s.
  **Mitigated** by fail-soft.
- *Risk:* the new user-visible string ships without complete `ru`/`bs` translations.
- *Risk:* BLOCK 8 also edits `sweep_orphaned_media.py`. Sequential Implementor handles it; BLOCK 8
  must **re-read** `_STAGING_TTL_SECONDS` rather than assume this block's value.
- *Rollback:* the migration is reversible (`RemoveIndex` + `AddIndex` back). The code halves are
  independently revertible, but **rolling back the predicate while keeping the heartbeat is
  harmless, and rolling back the heartbeat while keeping the predicate restores the original
  defect — revert both or neither.**

---

### BLOCK 7 — Per-batch commit with the advisory lock held once (`03-DB-008`)

| | |
|---|---|
| **Findings owned** | `03-DB-008` |
| **`depends_on`** | **BLOCK 5** (both rewrite `archive_sweep.Command.handle` and `recompute_normalized_prices.Command.handle`) |
| **Priority** | P2 |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Roster decision — CONFIRMED unchanged; all five.** Re-verified at `ba23277`: `D-15`
confirms the 13-command lock-structure test exactly as the source plan describes, so BLOCK 7's
amendment surface is precisely bounded. Q11 remains structurally unresolvable as written and
needs a real survey. Validator is mandatory because resolving Q11 wrongly loses mutual
exclusion **silently**.

**Decision gate — Q11 (must be closed before implementation).** The tension is exact:
`pg_advisory_xact_lock` releases with the **enclosing** transaction, so an outer `atomic()`
spanning the loop makes the per-batch commits not real commits, and a real per-batch commit
releases the lock. The option table (A session-scoped lock held once; B dedicated-connection
transaction-scoped lock; C keep one transaction and only add a timeout — **does not fix
DB-008**; D defer the block) is in the source plan §3.7.1. **This execution plan does not
choose.** The Researcher must resolve Q11 before any batching code is written.

**The two invariants that must survive any relaxation.**

1. The advisory lock is taken **once** and held across **every** batch. Moving the commit
   inside the loop while the lock is released per batch is **strictly worse** than today.
2. The queryset is **re-derived at the start of each batch**, not iterated from a single
   long-lived cursor, so batch *N+1* cannot act on rows batch *N* already changed.

**Agent briefs (paste-ready).**

> **Auditor.** *Goal:* map the three shipped tests that encode the current structure, and confirm
> the re-pointing surface if `select_for_update` moves out of `handle`. *Hard constraints:* change
> no code; never target a line number. *Files + symbols:*
> `apps/core/tests/test_sweep_archive.py::test_archive_sweep_handle_uses_select_for_update_and_atomic`
> (`inspect.getsource(Command.handle)`, asserts `"transaction.atomic"` **and**
> `"select_for_update"` inside `handle`);
> `apps/core/tests/test_sweep_lock_structure.py::TestSweepLockOrdering::test_all_sweep_commands_lock_inside_transaction`
> (13 commands, `len(lock_calls) == 13`, `in_atomic is True`, `session is False`);
> `apps/currencies/tests/test_recompute_command.py::test_process_batch_uses_select_for_update`
> (`inspect.getsource(Command._process_batch)`).
> *Must return:* which assertions break under each Q11 option and the exact re-pointing needed;
> the current `.order_by("pk")` / `.values_list("pk", flat=True).iterator(chunk_size=500)`
> batching shape of both commands; and confirmation that `AdvisoryLockId.ARCHIVE_SWEEP` (1) and
> `RECOMPUTE_NORMALIZED_PRICES` (12) are distinct, so the two commands cannot deadlock against
> each other on the advisory lock.

> **Researcher.** *Goal:* close **Q11** — how is "lock held once across per-batch commits"
> achieved, given `pg_advisory_xact_lock` releases with the enclosing transaction? *Hard
> constraints:* `advisory_lock(session=False)` **requires** an enclosing `atomic()` (it raises
> `RuntimeError` otherwise); `session=True` is documented in the project as the
> **pre-PgBouncer** shape and is **not** safe under PgBouncer transaction-mode pooling —
> state which pooling mode the deployment uses; Option C does **not** fix the finding.
> *Files + symbols:* `advisory_lock`; `archive_sweep.Command.handle`;
> `recompute_normalized_prices.Command.handle` / `._recompute` / `._process_batch` / `_BATCH_SIZE`;
> the `backfill_thumbnails` command (the in-repo model: short transaction + lock only for the
> count-to-mutate sequence). *Must return:* the chosen strategy with its PgBouncer caveat stated
> explicitly, and what the `test_sweep_lock_structure.py` amendment must say in its docstring.

> **Planner.** *Goal:* design the batching change preserving invariants 1 and 2 while relaxing
> all-or-nothing. *Hard constraints:* **lock ordering is a deadlock hazard, not a detail** —
> `archive_sweep` uses `.order_by("pk")` specifically to make lock order deterministic and any
> per-batch re-derivation must preserve it; `recompute_normalized_prices` batches by ascending
> `pk` but issues `select_for_update().filter(pk__in=batch_ids)` and PostgreSQL is **free to
> lock in any order**, so **an explicit ordering must be added**; `HOURLY_COMMANDS` /
> `DAILY_COMMANDS` in `apps/core/utils/scheduler.py` are **not modified** (they are pinned
> exactly by `test_scheduler.py`). *Must return:* the batch loop design, the explicit ordering
> for `recompute_normalized_prices`, the new test list, and the exact wording of what
> all-or-nothing relaxation loses (stated for the commit message).

> **Validator.** *Goal:* confirm mutual exclusion was not silently lost. *Hard constraints:* change
> no code. *Must return:* red-before/green-after evidence for the batch-failure test; the
> "acquired exactly once and held across all batches" evidence, independent of `session=True|False`;
> a two-invocation no-deadlock result under real concurrency
> (`django_db(transaction=True)`); and confirmation that the `session is False` amendment was
> constrained to the **two** named entries.

**Implementor task.**

```yaml
id: task_03_b07_per_batch_commit
title: Commit per batch in archive_sweep and recompute_normalized_prices while holding the advisory lock once
priority: medium
depends_on: [task_03_b05_lock_timeout]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 7 — Per-batch commit with the advisory lock held once (DB-008)"
extra_context: |
  Q11 IS A DECISION GATE, closed by Researcher + Planner inside this block. Record the chosen
  strategy in the commit message. Resolving Q11 wrongly ships a batching fix that SILENTLY loses
  mutual exclusion between two concurrent sweeps — that is the highest risk in this block.
  Option C (keep one transaction, add only a lock_timeout) does NOT fix DB-008; it addresses
  the waiter, not the hold.
  TWO INVARIANTS MUST SURVIVE ANY RELAXATION:
    1. The advisory lock is taken ONCE and held across every batch.
    2. The queryset is re-derived at the start of EACH batch.
  LOCK ORDERING IS A DEADLOCK HAZARD: archive_sweep's .order_by("pk") must be preserved through
  per-batch re-derivation, and recompute_normalized_prices MUST GAIN an explicit ordering
  (PostgreSQL is free to lock in any order).
  test_sweep_lock_structure.py asserts session is False for all 13 commands. If Q11 changes it,
  the amendment is constrained to archive_sweep and recompute_normalized_prices only — the other
  11 assertions stay byte-identical. Phase 03 allocates NO new AdvisoryLockId (D-1: id 13 is
  REPAIR_BOT_USERNAME; any new id starts at 14 and needs the three-artefact commit).
  HOURLY_COMMANDS / DAILY_COMMANDS in apps/core/utils/scheduler.py are NOT modified and are
  pinned exactly by test_scheduler.py.

description: >
  archive_sweep.Command.handle wraps the entire sweep in one transaction.atomic() around
  advisory_lock(ARCHIVE_SWEEP), iterating a single select_for_update().order_by("pk") queryset.
  recompute_normalized_prices is worse in shape: it walks the non-draft table in 500-row
  batches, taking select_for_update() per batch, ALL inside the one outer transaction, so locks
  accumulate for the whole sweep. Apply the Q11 decision so each batch is a real commit while
  the advisory lock is still taken once and held across the whole run.

goals:
  - release accumulated row locks per batch instead of at end of sweep
  - keep the advisory lock taken exactly once and held across every batch
  - re-derive the queryset per batch so batch N+1 cannot act on rows batch N already changed
  - preserve (and where missing, add) deterministic lock ordering by ascending pk
  - make re-running safe and state what all-or-nothing relaxation costs

files:
  - path: src/backend/apps/core/management/commands/archive_sweep.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors:
      replace_in_body:
        old: "with transaction.atomic():"   # the single outer atomic spanning the sweep
  - path: src/backend/apps/currencies/management/commands/recompute_normalized_prices.py
    targets:
      - { type: function, name: Command.handle }
      - { type: function, name: Command._recompute }
      - { type: function, name: Command._process_batch }
      - { type: constant, name: _BATCH_SIZE }
    semantic_anchors: {}
  - path: src/backend/apps/core/tests/test_sweep_lock_structure.py
    targets: [{ type: function, name: test_all_sweep_commands_lock_inside_transaction }]
    semantic_anchors: {}   # amend ONLY if Q11 changes session for these two commands
  - path: src/backend/apps/core/tests/test_sweep_archive.py
    targets: [{ type: function, name: test_archive_sweep_handle_uses_select_for_update_and_atomic }]
    semantic_anchors: {}   # RE-POINT at the helper if select_for_update leaves handle
  - path: src/backend/apps/currencies/tests/test_recompute_command.py
    targets: [{ type: function, name: test_process_batch_uses_select_for_update }]
    semantic_anchors: {}   # RE-POINT only if _process_batch moves
  # NOT touched: apps/core/utils/scheduler.py's command lists; Ad.transition_to;
  #             IX_ads_archive_sweep.

changes:
  - action: edit_code
    description: >
      Apply the Q11 decision. Give each batch its own transaction.atomic() so the commit is
      real, while the advisory lock is acquired exactly once and spans the whole run. Re-derive
      the queryset at the start of each batch. Preserve archive_sweep's .order_by("pk") and ADD
      an explicit ascending-pk ordering to recompute_normalized_prices' select_for_update().
  - action: rewrite_test
    description: >
      Re-point the two structural tests if select_for_update moves out of handle /
      _process_batch, IN THE SAME CHANGE. Amend test_sweep_lock_structure's `session is False`
      assertion ONLY for archive_sweep and recompute_normalized_prices, with the justification
      recorded in that test's docstring; the other 11 entries must remain unchanged.
  - action: add_test
    description: >
      Add: a failure-in-batch-N test asserting batches 1..N-1 ARE COMMITTED (the OPPOSITE of what
      the current code implies — demonstrate it RED against the pre-fix code); an
      "advisory lock acquired exactly once and held across all batches" test written to be
      independent of session=True|False; a per-batch queryset re-derivation test; and a
      real-concurrency (django_db(transaction=True)) test that two overlapping invocations over
      overlapping row sets do not deadlock.

acceptance_criteria:
  - a failure in batch N leaves batches 1..N-1 COMMITTED; the test was demonstrated RED
    against the pre-fix code
  - the advisory lock is acquired exactly once and held across all batches, proven independently
    of whether session=True or session=False
  - the queryset is re-derived per batch; a row that becomes ineligible between batches is not
    acted on by a later batch
  - archive_sweep's .order_by("pk") is preserved and recompute_normalized_prices GAINS an
    explicit ascending-pk ordering
  - test_sweep_lock_structure.py's `session is False` assertion is either unchanged or amended
    for EXACTLY the two named commands; the other 11 entries are byte-identical
  - HOURLY_COMMANDS and DAILY_COMMANDS are unmodified; test_scheduler.py passes unchanged
  - AdvisoryLockId gained no new member
  - the commit message states what all-or-nothing relaxation costs (a mid-sweep failure leaves
    earlier batches applied and the sweep re-runs on the next tick; re-running is safe because
    the predicates are time-based and re-derived, transition_to is idempotent per row, and
    unchanged normalised values are already skipped)
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - the Docker gate below is green
```

**Tests required.**

- *Must keep passing unchanged:* all of `test_sweep_archive.py` **except** the re-pointed
  structural case; all of `test_sweep_delete.py`; the 11 non-affected entries in
  `test_sweep_lock_structure.py`; `apps/core/tests/test_scheduler.py`.
- *Must be added:* the four tests named in `changes.add_test`, the first of which is **red
  against the pre-fix code**.
- *Must be changed:* the two structural tests **only if** Q11 forces a re-point.

**Exact gate command (Docker only).**

```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_sweep_archive.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/core/tests/test_sweep_delete.py src/backend/apps/currencies/tests/test_recompute_command.py" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk (highest):* resolving Q11 wrongly ships a batching fix that silently loses mutual
  exclusion between two concurrent sweeps. Invisible in every existing test; the
  "acquired exactly once" test is the control.
- *Risk:* losing `order_by("pk")` during re-derivation and introducing a deadlock against a
  concurrent `ad_edit`.
- *Risk:* weakening `session is False` for **all 13** commands instead of the two affected.
- *Risk:* writing the batch-failure test as "everything rolls back" — that passes against the
  **pre-fix** code and proves nothing.
- *Rollback:* two commands plus test amendments. No schema. Rolling back restores the current
  all-or-nothing behaviour — safe, just slow.

---

### BLOCK 8 — Media promotion must not become visible before its row commits (`03-DB-005`)

| | |
|---|---|
| **Findings owned** | `03-DB-005` (absorbs phase 01's `ENT-009`) |
| **`depends_on`** | **BLOCK 6** (both edit `sweep_orphaned_media.py`, including `_STAGING_TTL_SECONDS`) |
| **Priority** | P2 — the largest design in the phase; execute after BLOCK 6 has settled the TTL |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Roster decision — CONFIRMED unchanged; all five.** Re-verified at `ba23277`: `D-8` and `D-18`
both hold; `move_staging_to_permanent`'s docstring still **mandates** the defect in prose, and
`AdImage.save()` computes SHA-256 from `MEDIA_ROOT / self.image`, so a staging-keyed row hashes
differently pre- and post-move. Q7/Q8 remain the phase's largest design question. Validator is
mandatory: the failure mode of getting it wrong is **silent data loss for sellers**.

**Decision gates — Q7 and Q8 (must be closed before implementation).** Option table in the
source plan §3.8.1 (A: new sweep-excluded subdirectory promoted in `on_commit`; B: re-check
before unlink inside the lock — narrows but does not close the window; C: both, not
recommended). **This execution plan does not choose.** Phase 01 explicitly deferred this fork
to phase 03 and nothing in the tree pre-empts it.

**Agent briefs (paste-ready).**

> **Auditor.** *Goal:* map the entire media storage contract before the design is written.
> *Hard constraints:* change no code; never target a line number; do not read `ads/signals.py`
> — it does not exist. *Files + symbols:*
> `apps/media/services/filesystem.py` — `STAGING_SUBDIR`, `STAGING_PREFIX`, `KEY_FORMAT_REGEX`,
> `move_staging_to_permanent`, `delete_photo`, `upload_photo`, `download_telegram_file`,
> `DELETE_PHOTO_MAX_ATTEMPTS`, `DELETE_PHOTO_BASE_DELAY`;
> `apps/media/management/commands/sweep_orphaned_media.py` — `_SEED_SUBDIR`, `_STAGING_TTL_SECONDS`,
> `_collect_referenced_keys`, `_walk_media_files`, `_reclaim_stale_staging`, `Command.handle`;
> `apps/media/signals.py::delete_adimage_files_on_delete`;
> `apps/media/models.py::AdImage.save()`;
> `apps/ads/services/submission.py::submit_ad` (ordered outline, per **D-18**).
> *Must return:* the exact directory-exclusion mechanism `_walk_media_files` uses and how a new
> subdirectory would follow it; whether `AdImage.save()`'s SHA-256 changes across a promotion
> move; whether the sweep's snapshot→walk→unlink sequence has **any** re-check at delete time
> (it does not); and the ordered outline of `submit_ad` confirming step 2 (`move_staging_to_permanent`)
> precedes step 3 (`with transaction.atomic():`).

> **Researcher.** *Goal:* close **Q7** — where the final move happens relative to the transaction
> boundary — and **Q8** — whether the cheaper re-check-before-unlink variant is actually safe.
> *Hard constraints:* the exposure window spans the **entire** `os.walk` of `MEDIA_ROOT`, not a
> millisecond race; the command holds both the transaction and the sweep lock for the whole
> traversal; **locking the submit hot path is the strongest argument against the locking remedy**
> — it would serialise every seller submission against an `os.walk` and is a new availability
> incident. *Files + symbols:* the same set as the Auditor brief.
> *Must return:* the chosen option with its cost; the realistic orphan count (which drives Option
> B's transaction-per-file cost); and an explicit statement of whether Option B is an acceptable
> *complete* fix or only a stopgap.

> **Planner.** *Goal:* design the chosen option end to end — the new sweep-excluded subdirectory
> constant, the matching `_walk_media_files` exclusion, the **reclamation policy** for it, and
> the corrected docstrings. *Hard constraints:* the directory-exclusion precedent already exists
> (`_SEED_SUBDIR` and `STAGING_SUBDIR` are skipped by `_walk_media_files`), so no new pattern is
> needed; a migration is required **only if** the DB schema changes (then it is `media/0002_*` —
> check the directory immediately before generating); `AD-003` (phase 05) must **not** be merged
> in — no refcounting, no removal of `copy_ad`'s storage-key reuse, no change to
> `delete_adimage_files_on_delete`. *Must return:* the design, the reclamation rule, the
> docstring rewrites, and the test plan.

> **Validator.** *Goal:* confirm the finding is closed and that no storage is leaked. *Hard
> constraints:* change no code. *Must return:* red-before/green-after evidence for the concurrency
> regression test; the reclamation test result (Option A); the pre-/post-promotion hash equality
> result; and confirmation that the class docstring of `TestSubmitAdStagingMove` now states the
> corrected contract, not the defect.

**Implementor task.**

```yaml
id: task_03_b08_media_promotion_window
title: Close the window where a promoted file is visible to the orphan sweep before its AdImage row commits
priority: medium
depends_on: [task_03_b06_idle_timeout]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 8 — Media promotion must not become visible before its row commits (DB-005)"
extra_context: |
  Q7 AND Q8 ARE DECISION GATES, closed by Researcher + Planner inside this block. Record the
  chosen option in the commit message. Do not begin implementation before they are written down.
  D-8: test_sweep_orphaned_media.py has TWO classes —
  TestSweepOrphanedMedia::test_orphaned_file_is_deleted (NOT test_orphan_file_deleted),
  ::test_referenced_file_is_kept (NOT test_ad_referenced_file_survives),
  ::test_seed_subdir_excluded (NOT test_seed_dir_is_excluded) — and
  TestSweepLockScope::test_delete_photo_called_within_lock_scope, a class the source plan omits.
  D-18: the bot error surface is ad_create/submit.py::process_preview; preview.py::show_preview
  is a non-router render helper. submit_ad promotes at step 2, before step 3's atomic().
  move_staging_to_permanent's docstring MANDATES the defect in prose and is a deliverable.
  AdImage.save() computes SHA-256 from MEDIA_ROOT / self.image — a staging-keyed row hashes
  DIFFERENTLY pre- and post-promotion. Check this explicitly before writing Option A.
  Do NOT merge AD-003 (phase 05): no refcounting, no removal of copy_ad's storage-key reuse,
  no change to delete_adimage_files_on_delete.
  Do NOT lock the submit hot path — it would serialise every seller submission against an
  os.walk.
  A migration is required only if the DB schema changes; then it is media/0002_* — check the
  directory immediately before generating.

description: >
  submit_ad promotes staged files to permanent MEDIA_ROOT BEFORE opening its
  transaction.atomic(), then inserts AdImage rows inside that transaction, and never takes
  AdvisoryLockId.SWEEP_ORPHANED_MEDIA. A concurrent sweep_orphaned_media takes a point-in-time
  snapshot of referenced keys and unlinks on_disk-minus-referenced across the whole os.walk
  with no re-check, so a promoted file whose row is not yet committed is classified as an
  orphan and deleted. Apply the chosen design so no file is ever visible to the sweep before the
  row that owns it is committed.

goals:
  - eliminate the promote-before-row-commit window
  - do not introduce unbounded growth (files left behind must be reclaimed within a bounded time)
  - keep AdImage content dedup (SHA-256) stable across any promotion move
  - keep the TX-then-FS convention for every deletion
  - leave AD-003 (phase 05) untouched

files:
  - path: src/backend/apps/ads/services/submission.py
    targets: [{ type: function, name: submit_ad }]
    semantic_anchors:
      replace_in_body:
        old: "move_staging_to_permanent(input.photos)"   # step 2 — currently BEFORE the atomic
  - path: src/backend/apps/media/services/filesystem.py
    targets:
      - { type: function, name: move_staging_to_permanent }
      - { type: function, name: delete_photo }
      - { type: module,   name: filesystem }
    semantic_anchors: {}
  - path: src/backend/apps/media/management/commands/sweep_orphaned_media.py
    targets:
      - { type: function,  name: _walk_media_files }
      - { type: function,  name: _collect_referenced_keys }
      - { type: function,  name: _reclaim_stale_staging }
      - { type: function,  name: Command.handle }
      - { type: constant,  name: _SEED_SUBDIR }
      - { type: constant,  name: _STAGING_TTL_SECONDS }
    semantic_anchors: {}
  - path: src/backend/apps/media/models.py                   # AdImage.save() — REFERENCE ONLY
    targets: [{ type: class, name: AdImage }]
    semantic_anchors: {}
  - path: src/backend/apps/media/signals.py                 # REFERENCE ONLY unless design changes
    targets: [{ type: function, name: delete_adimage_files_on_delete }]
    semantic_anchors: {}
  - path: src/telegram_bot/tests/test_save_photo_integration.py
    targets: [{ type: class, name: TestSubmitAdStagingMove }]
    semantic_anchors: {}
  - path: src/backend/apps/media/tests/test_sweep_orphaned_media.py
    targets: [{ type: class, name: TestSweepOrphanedMedia }, { type: class, name: TestSweepLockScope }]
    semantic_anchors: {}
  # NOT touched: copy_service.py's storage-key reuse (AD-003, phase 05);
  #             delete_draft's storage_keys (that path genuinely uses them);
  #             sweep_drafts.py (BLOCK 1 and BLOCK 6 own it).

changes:
  - action: add_code
    description: >
      Apply the Q7 decision. Option A: a new sweep-excluded subdirectory constant in
      filesystem.py, promoted to permanent storage in a transaction.on_commit callback after the
      owning AdImage row commits, plus a matching exclusion in _walk_media_files and a
      reclamation rule (possibly reusing _reclaim_stale_staging). Option B: a re-check inside a
      short transaction immediately before each unlink, kept INSIDE the
      AdvisoryLockId.SWEEP_ORPHANED_MEDIA lock scope so test_delete_photo_called_within_lock_scope
      keeps holding.
  - action: rewrite_docstring
    description: >
      Correct move_staging_to_permanent's "the caller must run this before any
      transaction.atomic()" contract and TestSubmitAdStagingMove's class docstring. Both
      currently document the DEFECT as intended behaviour. Per project rule 2 the TESTS bend;
      the docstrings are corrected, not preserved.
  - action: rewrite_test
    description: >
      Rewrite BOTH cases of TestSubmitAdStagingMove to the chosen design: after a rolled-back
      submit no file exists in permanent storage; after a successful submit the file is permanent
      AND an AdImage row exists AND a concurrent sweep running between the row commit and the
      promotion move cannot unlink it.

acceptance_criteria:
  - a sweep overlapping a submit_ad never deletes a file whose AdImage row commits
  - files orphaned by a rolled-back submit are reclaimed within a bounded time
  - AdImage.save() produces the same content hash before and after any promotion move
  - the concurrency regression test is RED against the pre-fix code
  - every delete_photo call still happens inside the SWEEP_ORPHANED_MEDIA lock scope
  - test_sweep_orphaned_media.py's seed, staging, reclaim, dry-run and routing cases pass
    unchanged, using their ACTUAL names (D-8)
  - copy_service.py's storage-key reuse and delete_adimage_files_on_delete are unchanged (AD-003)
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - `.\Makefile.ps1 test-recreate` was run if a migration was generated, then the Docker gate is green
```

**Tests required.**

- *Must be changed (rewritten — this is the block's core obligation):*
  `src/telegram_bot/tests/test_save_photo_integration.py::TestSubmitAdStagingMove` —
  `test_submit_ad_rollback_leaves_permanent_orphans` currently asserts permanent files **exist**
  after a rollback, staging files do **not**, and `AdImage.objects.filter(ad=ad).count() == 0`,
  with the class docstring calling the ordering *intended*; its rewrite must state **why** the
  old expectation encoded the defect. `test_submit_ad_moves_staging_to_permanent` must be
  re-derived.
- *Must be added:* the **concurrency regression test** — force the interleaving with a
  hook/barrier, **never with sleeps**; **red against the pre-fix code**. Option A also requires
  the **reclamation test** (without it Option A trades data loss for unbounded growth) and the
  **dedup-key test**.
- *Must keep passing unchanged:*
  `TestSweepOrphanedMedia::test_seed_subdir_excluded`, `::test_referenced_file_is_kept`,
  `::test_orphaned_file_is_deleted`, `::test_staging_file_survives_sweep`,
  `::test_stale_staging_file_reclaimed`, `::test_fresh_staging_file_preserved`,
  `::test_dry_run_is_nondestructive`, `::test_delete_photo_routing`;
  `TestSavePhotoThumbnailsIntegration` (untouched by this finding);
  `src/backend/apps/ads/tests/test_ad_image_dedup.py`.

**Exact gate command (Docker only).**

```powershell
# run only if a migration was generated:
.\Makefile.ps1 test-recreate
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_save_photo_integration.py src/backend/apps/media/tests/ src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_ad_image_dedup.py" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk (highest):* rewriting `TestSubmitAdStagingMove` and **not** updating the class docstring,
  so the next reader inherits "promote before TX ⇒ orphans on rollback" as documented intent
  and reverts the fix. **The docstring is part of the deliverable.**
- *Risk (Option A):* the new sweep-excluded subdirectory becomes a **second** `staging/` and
  nothing reclaims it. The reclamation test is the control.
- *Risk (Option A):* `AdImage.save()`'s SHA-256 changes across the promotion move, silently
  breaking content dedup.
- *Risk:* taking `SWEEP_ORPHANED_MEDIA` on the submit hot path — a new availability incident.
- *Risk:* BLOCK 6 also edits `sweep_orphaned_media.py`. Re-read `_STAGING_TTL_SECONDS`.
- *Rollback:* code and test changes are reversible. **A deployed Option A leaves files in a
  subdirectory that a rolled-back code version would treat as orphans — the rollback plan must
  include a one-off reclamation of that directory.**

---

### BLOCK 9 — Serialise and de-duplicate immediate-alert delivery (`03-DB-007`)

| | |
|---|---|
| **Findings owned** | `03-DB-007` |
| **`depends_on`** | **BLOCK 5** (hard) and **BLOCK 7** (ordering) |
| **Priority** | P3 — **latent** |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Roster decision — CONFIRMED unchanged; all five.** Re-verified at `ba23277`: `D-5` confirms
the gate file, **N-2** strengthens the "latent" claim (all four templates set the flag `false`;
base default `False`), and `D-2` invalidates the hash the source plan's `extra_context` cites.
`delivered_by_immediate_alerts` does **not** exist anywhere in `src/`; `SavedSearchNotification`
carries only `uq_saved_search_ad`. Validator is mandatory: the block lands **behind a disabled
feature flag**, so nothing in production exercises it.

**Ordering decision (carried forward).** BLOCK 7 before BLOCK 9 — same shared advisory-lock and
lock-structure-test neighbourhood, and BLOCK 7 is the more structural of the two, which keeps
BLOCK 9's diff concentrated in `apps/search`.

**Decision gates — Q9 and Q10 (must be closed before implementation).** Q9 options in the source
plan §3.9.1 (A: shared advisory lock alone — **provably insufficient** for the stated defect;
B: service-level `delivered_by_immediate_alerts` on `SavedSearchNotification` with a
`NOT EXISTS` filter in `find_matching_saved_searches`; C: command-level "skip any existing
notification row", which misses the immediate path). Q10 specifies the column's contract.
**This execution plan does not choose.** The Researcher must answer explicitly: *does the shared
advisory lock close the reported double-send, and if not, what does?*

**The finding's framing correction, carried into every brief.** `deliver_immediate_alerts`
records the `SavedSearchNotification` rows **before** dispatch. If the send then fails, the row is
already committed, so the daily `send_alerts` run **skips** that (search, ad) pair — a
**silent alert loss**, which is the opposite of a duplicate and arguably worse. The source
report frames the finding only as a double-send. **A block that ships only Option A must record
in its commit message that the concurrency path is unproven and that B remains required.**

**Agent briefs (paste-ready).**

> **Auditor.** *Goal:* re-verify the activation precondition after BLOCK 5/6/7/8 have changed
> transaction boundaries in the same neighbourhood, and establish the rollout state. *Hard
> constraints:* change no code; never target a line number; **`src/backend/apps/ads/signals.py`
> does not exist.** *Files + symbols:*
> `src/backend/apps/moderation/signals.py::deliver_immediate_alerts_on_publish` (guarded by
> `getattr(settings, "IMMEDIATE_ALERTS_ENABLED", False)`);
> `config/settings/base.py::IMMEDIATE_ALERTS_ENABLED`;
> `src/backend/apps/search/services/immediate_alerts.py::deliver_immediate_alerts`, `_executor`,
> `_run_send`, `_SEND_CONCURRENCY`, `_BACKOFF_BASE`, `UNSUB_CALLBACK_PREFIX`;
> `src/backend/apps/search/services/alert_query.py::find_matching_saved_searches`,
> `::record_notifications`, `::find_matching_ads`;
> `src/backend/apps/search/models.py::SavedSearchNotification`;
> `src/backend/apps/search/management/commands/send_alerts.py::Command.handle`;
> `src/backend/apps/ads/services/submission.py::submit_ad` → `ad.transition_to`.
> *Must return:* (a) whether the "immediate path can double-send" precondition is **still** true
> after BLOCK 5/6/7/8; (b) confirmation that `IMMEDIATE_ALERTS_ENABLED` is `False` by default and
> `false` in **all four** `.env.*.example` templates (**N-2** — the source plan's "appears in no
> template" is wrong), and the real gate test is
> `moderation/tests/test_approve_ad_side_effects.py` via `override_settings`; (c) confirmation
> that `record_notifications` returns `len(ads)` ("not necessarily created") and that
> `find_matching_saved_searches` has **no** `NOT EXISTS` filter while `find_matching_ads` **does**;
> (d) the shape of `send_alerts.Command.handle`'s docstring, which already nominates *"a
> delivery-state column on `SavedSearchNotification` (phase 03 DB-007's schema)"*.

> **Researcher.** *Goal:* close **Q9**. *Hard constraints:* **adding the lock alone is
> provably insufficient** — it does not address the missing `NOT EXISTS` filter or the
> meaningless return value; the `on_commit` call site is unique, so the concurrency trigger the
> report describes is a **hypothesis, not a demonstrated fact**. *Files + symbols:* the same set
> as the Auditor brief. *Must return:* the chosen option with why; an explicit answer to *"does
> the shared advisory lock close the reported double-send, and if not, what does?"*; and whether
> Option C is viable as a complement.

> **Planner.** *Goal:* close **Q10** — the delivery-state column's contract — before coding.
> *Hard constraints:* a **fixed value** must be an enum member or named constant, never a bare
> boolean literal scattered across call sites (project rule 10); only
> `deliver_immediate_alerts` writes it, never `send_alerts`; it is written **inside the same
> transaction that creates the notification row and BEFORE dispatch** (writing it after the send
> leaves a crash window where the duplicate is already out and the flag is lost); backfill is
> **`NULL` with no backfill** — a `NOT NULL DEFAULT false` backfill would **re-notify every
> previously immediate-sent pair**, a mass duplicate send on first enable; the column must be
> **nullable**; `uq_saved_search_ad` is a true no-op backstop for concurrent creates of the same
> pair and does **nothing** for the "immediate sent ⇒ daily skips" filter, which needs its own
> column; the daily path's phase-01 idempotency is **untouched**. *Files + symbols:* `models.py::
> SavedSearchNotification`; a **new** `search/migrations/0003_*` (check the directory immediately
> before generating). *Must return:* the column name/type/nullability, the writer, the ordering
> relative to dispatch, the backfill rule, and the migration shape.

> **Validator.** *Goal:* confirm the delivery contract before the flag is ever enabled. *Hard
> constraints:* change no code; tests must exercise the code path **directly**, not by flipping
> `IMMEDIATE_ALERTS_ENABLED` globally. *Must return:* evidence that a failed `_run_send`
> followed by a `send_alerts` run **still delivers** (red before the fix); that an
> already-delivered pair is **not** delivered twice; that pre-existing rows are `NULL` and are
> not filtered; and that the feature still does nothing with the flag off. *Also:* confirm phase
> 01's `send_alerts` idempotency behaviour was **not** reverted (re-anchor by **symbol**:
> `apps.core.utils.scheduler.SchedulerDailyMarker`, `send_alerts._DIGEST_AD_LIMIT` — **not** by
> the hash `fbbb6cf`, which is the scheduler daily-marker commit and never touched
> `send_alerts.py`; see **D-2**).

**Implementor task.**

```yaml
id: task_03_b09_immediate_alert_serialisation
title: Serialise immediate-alert delivery and de-duplicate it against the daily digest
priority: medium
depends_on: [task_03_b05_lock_timeout, task_03_b07_per_batch_commit]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 9 — Serialise and de-duplicate immediate-alert delivery (DB-007)"
extra_context: |
  Q9 AND Q10 ARE DECISION GATES, closed by Researcher + Planner inside this block.
  D-5: src/backend/apps/ads/signals.py DOES NOT EXIST. The gate is
  src/backend/apps/moderation/signals.py::deliver_immediate_alerts_on_publish.
  N-2: IMMEDIATE_ALERTS_ENABLED IS present in all four .env.*.example templates (value false)
  and in ALLOWED_ENV_VARS. Do NOT add a template entry for it and do NOT claim it is
  undocumented. The "latent" conclusion still holds and is stronger.
  D-2: DO NOT cite the hash fbbb6cf — it is the scheduler daily-marker commit and never touched
  send_alerts.py. Re-anchor the "do not revert" artefacts by SYMBOL:
  apps.core.utils.scheduler.SchedulerDailyMarker, apps.core.services.scheduler_daily_state,
  send_alerts._DIGEST_AD_LIMIT, send_alerts.Command.handle's loss-window docstring.
  THE FINDING'S REAL HALF IS SILENT ALERT LOSS: deliver_immediate_alerts records the
  SavedSearchNotification rows BEFORE dispatch, so a failed send permanently suppresses that pair
  in the daily run. Adding the advisory lock alone is PROVABLY INSUFFICIENT — it addresses
  neither find_matching_saved_searches' missing NOT EXISTS filter nor record_notifications'
  meaningless return value.
  Shipping Option A alone is permitted ONLY if the commit message records that the concurrency
  path is unproven and that Option B remains required.
  Q10: the column must be NULLABLE with NO backfill. NOT NULL DEFAULT false would re-notify
  every previously immediate-sent pair on first enable — a mass duplicate send. The flag must be
  written inside the same transaction that creates the row and BEFORE _executor.submit.
  Tests must exercise the path directly, not by flipping IMMEDIATE_ALERTS_ENABLED globally.
  Phase 03 allocates NO new AdvisoryLockId (D-1: id 13 is REPAIR_BOT_USERNAME).

description: >
  deliver_immediate_alerts takes no advisory lock, opens no transaction, and calls
  record_notifications(saved_search, [ad]) BEFORE _executor.submit(_run_send, payloads). If the
  send fails, the SavedSearchNotification row is already committed, so the daily send_alerts run
  SKIPS that (search, ad) pair — a silent alert loss. Separately, a re-published ad re-runs the
  matcher with no exclusion filter, because find_matching_saved_searches has no NOT EXISTS
  clause. Apply the chosen option so a failed immediate send is retried by the daily path and
  an already-delivered pair is not delivered twice.

goals:
  - a failed immediate send must not permanently suppress the daily digest for that pair
  - an already-delivered pair must not be delivered twice
  - keep the daily path's phase-01 idempotency untouched (re-anchored by symbol)
  - keep the IMMEDIATE_ALERTS_ENABLED gate and the bounded executor unchanged
  - keep recipient-selection semantics unchanged (PII-104, phase 06)

files:
  - path: src/backend/apps/moderation/signals.py          # NOT apps/ads/signals.py (D-5)
    targets: [{ type: function, name: deliver_immediate_alerts_on_publish }]
    semantic_anchors: {}                                   # reference only
  - path: src/backend/apps/search/services/immediate_alerts.py
    targets:
      - { type: function, name: deliver_immediate_alerts }
      - { type: module,   name: immediate_alerts }
    semantic_anchors: {}
  - path: src/backend/apps/search/services/alert_query.py
    targets:
      - { type: function, name: find_matching_saved_searches }
      - { type: function, name: record_notifications }
    semantic_anchors: {}
  - path: src/backend/apps/search/models.py               # Option B only
    targets: [{ type: class, name: SavedSearchNotification }]
    semantic_anchors: {}
  - path: src/backend/apps/search/migrations/0003_alter_savedsearchnotification.py  # Option B only
    targets: [{ type: module, name: migration }]
    semantic_anchors: {}                                   # CHECK THE DIRECTORY FIRST
  - path: src/backend/apps/search/management/commands/send_alerts.py
    targets: [{ type: class, name: Command }]
    semantic_anchors: {}
  - path: src/backend/apps/search/tests/test_alert_query.py
    targets:
      - { type: class, name: TestRecordNotifications }
      - { type: class, name: TestDeliverImmediateAlerts }
      - { type: class, name: TestImmediateAlertsGate }
      - { type: class, name: TestFindMatchingSavedSearches }
      - { type: class, name: TestFindMatchingAds }
      - { type: class, name: TestSendAlertsCommand }
    semantic_anchors: {}
  # NOT touched: _build_payload, build_alert_message, the bot's unsubscribe handler, or the
  # daily run marker / idempotency work owned by an earlier cycle.

changes:
  - action: add_code
    description: >
      Apply the Q9 decision (advisory lock via AdvisoryLockId.ALERT_DELIVERY_TASK (9), a
      delivered-state column, a NOT EXISTS filter on find_matching_saved_searches, a
      command-level skip, or a combination).
  - action: add_migration
    description: >
      Option B only: add a NULLABLE delivery-state column with NO backfill, written inside the
      same transaction that creates the notification row and BEFORE _executor.submit. NEVER
      NOT NULL DEFAULT false — that re-notifies every previously immediate-sent pair. Any fixed
      value must be an enum member or named constant (project rule 10), not a bare boolean
      literal. CHECK THE search/migrations DIRECTORY IMMEDIATELY BEFORE GENERATING (0003_* is
      correct as of ba23277).
  - action: edit_docstring
    description: >
      Correct the immediate_alerts module docstring's claim that "ignore_conflicts" alone means
      the daily command never double-sends, and correct record_notifications' return of
      len(ads) if the chosen option changes its contract. Note explicitly that a failed send
      currently causes silent loss, not a duplicate.
  - action: rewrite_test
    description: >
      Rewrite TestDeliverImmediateAlerts::test_records_notification_idempotently ONLY if the
      chosen option inverts it, with a recorded rationale in its docstring. Note that it
      currently monkeypatches _run_send so the executor is bypassed and dispatch ordering is NOT
      actually tested.

acceptance_criteria:
  - a failed _run_send followed by a send_alerts run STILL delivers the pair; the test was
    demonstrated RED against the pre-fix code
  - a pair already delivered by the immediate path is not re-delivered by send_alerts
  - a pair delivered only by send_alerts is still excluded by the immediate matcher
  - pre-existing notification rows are NULL and are NOT filtered out (Option B backfill test)
  - the feature still does nothing when IMMEDIATE_ALERTS_ENABLED is False
  - test_alert_query.py::TestRecordNotifications::test_ignore_conflicts_skips_duplicates passes
    unchanged
  - recipient-selection logic is unchanged beyond the delivery-state filter (PII-104, phase 06)
  - _executor, the Bot lifecycle and asyncio.run-per-batch behaviour are UNCHANGED
  - AdvisoryLockId gained no new member
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - `.\Makefile.ps1 test-recreate` was run if search/0003_* was generated, then the Docker gate
    below is green
```

**Tests required.**

- *Must keep passing unchanged:*
  `test_alert_query.py::TestRecordNotifications::test_ignore_conflicts_skips_duplicates`;
  `::TestImmediateAlertsGate::test_gate_off_does_not_deliver_on_publish`; the phase-01
  `send_alerts` idempotency tests (re-anchored by symbol, **D-2**);
  `src/backend/apps/moderation/tests/test_approve_ad_side_effects.py`;
  `src/telegram_bot/tests/test_alerts*.py`.
- *Must be added:* the **lost-alert regression test** — **red against the pre-fix code**;
  the **duplicate-suppression test** and its converse; the **backfill test** (Option B); a test
  that the immediate path still behaves correctly with the flag off.
- *Must be changed:* `test_records_notification_idempotently` **only if** the chosen option
  inverts it, with a recorded rationale.

**Exact gate command (Docker only).**

```powershell
# run only if search/0003_* was generated:
.\Makefile.ps1 test-recreate
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/search/tests/ src/backend/apps/ads/tests/ src/backend/apps/moderation/tests/test_approve_ad_side_effects.py src/telegram_bot/tests/test_alerts.py" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk:* shipping Option A alone and recording the feature as fixed. The block summary must
  state that the concurrency path is unproven and that B remains required.
- *Risk (Option B):* writing the flag **after** the send — a crash then duplicates the message.
- *Risk (Option B):* a `NOT NULL DEFAULT false` backfill re-notifies every previously
  immediate-sent pair on first enable.
- *Risk:* reverting an earlier cycle's `send_alerts` idempotency work by an over-broad
  "simplification".
- *Rollback:* the column-removal migration is reversible. **Rolling back after the flag is
  enabled means every pair already marked `True` becomes eligible again — the rollback plan must
  disable `IMMEDIATE_ALERTS_ENABLED` first.**

---

### BLOCK 10 — One single-draft policy, applied in both creators (`03-DB-009`)

| | |
|---|---|
| **Findings owned** | `03-DB-009` |
| **`depends_on`** | **BLOCK 4** (both implement the same single-draft policy) |
| **Priority** | P3 |
| **Roster** | **Implementor, Auditor, Planner, Validator** — **no Researcher** |

**Roster decision — CONFIRMED unchanged: no Researcher, and that is the right call.**

- **Implementor — yes.** Always.
- **Auditor — yes.** The finding's central correction is that `copy_ad` has exactly **one**
  production site and there is **no** web route; the report's other source was a **test helper**.
  That must be re-verified at `ba23277`, together with the `Ad.status` default BLOCK 10 depends on.
- **Researcher — NO, and this is a deliberate correction of instinct, not an oversight.** Q12 is a
  **product** decision, not a technical survey; the tree points at an in-repo model
  (`create_draft_ad`'s delete-then-recreate); and project rule 5 says prefer the simple obvious
  solution over abstractions. Adding a Researcher here would be ceremony with no question to
  answer. **If the coordinator challenges this, the answer is that there is no external
  best-practice question — only a product preference with a fixed default.**
- **Planner — yes.** The product rule must be specified for **both** creators at once, the
  error-handling boundary defined, and the i18n string set designed.
- **Validator — yes.** Seller-visible behaviour changes and a new user-facing message ships; the
  "unified rule" is only credible if both call sites are shown to obey it.

**Decision gate — Q12.** Option table in the source plan §3.10.1. **The default is fixed:**

> **Default if unanswerable: Option A — "a new draft replaces the current one."** It matches
> the shipped `create_draft_ad` policy, needs **no** new i18n string, and requires no behaviour
> change on the busiest bot path. If the coordinator/product is not consulted, **default to A and
> record in the commit message that the choice was made by default, not by decision.**
> **Option C is FORBIDDEN.** It improves the message without addressing the missing policy, which
> is the finding's actual ask.

**Agent briefs (paste-ready).**

> **Auditor.** *Goal:* re-verify `copy_ad`'s call graph and the model default. *Hard constraints:*
> change no code; never target a line number. *Files + symbols:*
> `src/backend/apps/ads/services/copy_service.py::copy_ad` and its docstring's `Raises:` section;
> `src/telegram_bot/handlers/ad_copy.py::cmd_copy`; `src/backend/apps/ads/models.py::Ad.status`
> default and `uq_ads_single_draft_per_user`;
> `src/backend/apps/ads/tests/test_copy_ad.py` module docstring.
> *Must return:* confirmation that `cmd_copy` is the **only** production caller (the report's other
> source is `test_copy_ad.py::TestCopyAd`, a test helper) and that there is **no** web route;
> the exact current `cmd_copy` exception branch and its message; and the `test_copy_ad.py`
> `test_copy_ad_happy_path` assertion that must survive an explicit `status=AdStatus.DRAFT`.

> **Planner.** *Goal:* specify the single-draft policy for **both** creators, the
> error-handling boundary, and the i18n set. *Hard constraints:* whatever option is chosen,
> `cmd_copy`'s broad formatter must stop surfacing raw driver text (constraint name,
> `DETAIL Key (user_id, status)=…`, `CONTEXT INSERT INTO ads`); the user id comes from
> `tg_ctx.user.id`, not a stored profile; under Option A the delete and the create are **one
> transaction** and the file deletions are **after commit** (the `AdImage.pre_delete` signal
> already defers to `transaction.on_commit`); the **partial unique index remains the backstop**,
> and if it fires the retry path is BLOCK 4's savepoint shape, not a new mechanism; adding an
> explicit `status=AdStatus.DRAFT` is **cosmetic** and must not be bundled as if it were the fix.
> *Files + symbols:* `copy_service.py::copy_ad`; `ad_copy.py::cmd_copy`;
> `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` (Option B only — **append**, never
> regenerate; the locale files are a **shared artefact** with phase 14). *Must return:* the
> chosen option (or "defaulted to A"), the ordering rule, the error surface, the exact new msgid
> set, and the statement that `test_ad_copy.py`'s `"failed"` assertion survives.

**Implementor task.**

```yaml
id: task_03_b10_single_draft_policy
title: Apply one single-draft policy in both draft creators and stop leaking raw driver errors
priority: low
depends_on: [task_03_b04_create_draft_savepoint]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 10 — One single-draft policy, applied in both creators (DB-009)"
extra_context: |
  Q12 IS A PRODUCT DECISION GATE.
  DEFAULT IF UNANSWERABLE: Option A — "a new draft replaces the current one." It matches the
  shipped create_draft_ad policy and needs no new i18n. If defaulted, the commit message MUST
  record that the choice was made by default, not by decision.
  OPTION C IS FORBIDDEN — it improves the message without addressing the missing policy, which
  is the finding's actual ask.
  Whichever option is chosen, cmd_copy's broad `except Exception` formatter must stop
  interpolating raw psycopg IntegrityError text (constraint name, `DETAIL Key (...)`,
  `CONTEXT  INSERT INTO ads`) into a Telegram message.
  Adding an explicit `status=AdStatus.DRAFT` in copy_ad is COSMETIC — do not bundle it as if it
  were the fix.
  Locale files are a SHARED artefact with phase 14 — APPEND, never run a wholesale makemessages.
  Do NOT touch cmd_post's existing draft replacement (BLOCK 4) and do NOT touch copy_ad's
  storage-key reuse (AD-003, phase 05).

description: >
  copy_ad never sets status, never handles uq_ads_single_draft_per_user, and never touches an
  existing DRAFT. When a seller already has one, the partial unique index fires and cmd_copy's
  broad `except Exception` interpolates the raw psycopg IntegrityError text into a Telegram
  message. Apply the chosen single-draft policy in copy_ad, keep it identical to the one
  create_draft_ad already implements, and stop surfacing raw exception text.

goals:
  - apply ONE single-draft policy across create_draft_ad and copy_ad
  - stop interpolating raw database exception text into user-facing messages
  - keep filesystem deletions after commit, not inside the transaction
  - keep the partial unique index as the backstop, not as the primary mechanism

files:
  - path: src/backend/apps/ads/services/copy_service.py
    targets: [{ type: function, name: copy_ad }]
    semantic_anchors:
      insert_after:
        type: assignment
        value: "new_ad = Ad("
  - path: src/telegram_bot/handlers/ad_copy.py
    targets: [{ type: function, name: cmd_copy }]
    semantic_anchors:
      replace_in_body:
        old: '_("Failed to copy ad: {error}").format(error=e)'
        new: '_("Failed to copy ad.")'
  - path: src/backend/apps/ads/tests/test_copy_ad.py
    targets: [{ type: module, name: test_copy_ad }]
    semantic_anchors: {}
  - path: src/telegram_bot/tests/test_ad_copy.py
    targets: [{ type: function, name: test_copy_unexpected_error }]
    semantic_anchors: {}   # the `assert "failed" in called_text.lower()` must keep passing; do not edit
  - path: src/backend/locale/ru/LC_MESSAGES/django.po   # Option B only — APPEND
    targets: [{ type: module, name: django_po }]
    semantic_anchors: {}
  - path: src/backend/locale/bs/LC_MESSAGES/django.po   # Option B only — APPEND
    targets: [{ type: module, name: django_po }]
    semantic_anchors: {}

changes:
  - action: add_code
    description: >
      Option A: delete the seller's existing DRAFT before creating the copy, inside the same
      transaction, exactly mirroring create_draft_ad's documented delete+recreate pattern, with
      the AdImage file deletions deferred to transaction.on_commit().
      Option B: let the constraint fire and map IntegrityError to a new translated domain error
      with a seller-facing message.
  - action: edit_error_handler
    description: >
      Replace the raw-interpolating `except Exception` branch in cmd_copy with one that logs via
      logger.exception and answers a translated, non-interpolating message.
  - action: edit_docstring
    description: >
      Correct copy_ad's docstring (its Raises: section lists only Ad.DoesNotExist and
      PermissionError) and test_copy_ad.py's module docstring, which currently states the
      single-draft precondition as a fact the code does not enforce.

acceptance_criteria:
  - a seller with an existing DRAFT running /copy ends with exactly one DRAFT (Option A), or
    keeps the old one and receives the translated message (Option B)
  - the failure message contains NO raw driver text (no "Key (", no "DETAIL", no "CONTEXT",
    no "INSERT INTO")
  - a replaced draft's media files are removed after commit, not inside the transaction
  - test_ad_copy.py's `assert "failed" in called_text.lower()` passes unchanged
  - test_copy_ad.py::TestCopyAd::test_copy_ad_happy_path's DRAFT-status assertion passes unchanged
  - src/backend/apps/ads/tests/test_ad_constraints.py passes unchanged
  - copy_ad's storage-key reuse and cmd_post's draft replacement are unchanged
  - Option B only: non-empty msgstr for ru AND bs; locale files appended, never regenerated
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - the Docker gate below is green
```

**Tests required.**

- *Must keep passing unchanged:* all of `src/backend/apps/ads/tests/test_copy_ad.py`'s
  field-copying assertions (including `test_copy_ad_happy_path`);
  `src/telegram_bot/tests/test_ad_copy.py` including the `"failed"` assertion;
  `src/backend/apps/ads/tests/test_ad_constraints.py`.
- *Must be added:* the **unified-policy test** (assert the **chosen** option's outcome, in both
  `create_draft_ad` and `copy_ad`); the **no-raw-driver-text** test; and, under Option A, the
  **after-commit media deletion** test mirroring `TestCreateDraftAdCrashRecovery`.
- *Must be changed:* none.

**Exact gate command (Docker only).**

```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_copy_ad.py src/backend/apps/ads/tests/test_ad_constraints.py src/telegram_bot/tests/test_ad_copy.py src/telegram_bot/tests/test_create_draft_ad.py" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk:* Option A deleting the seller's in-progress draft **before** the copy commits, so a
  later failure loses both. Delete and create in one transaction; file deletions after commit.
- *Risk:* changing the error surface in a way that breaks `test_ad_copy.py`'s `"failed"` assertion.
- *Risk:* Option C shipped by default — explicitly forbidden above.
- *Rollback:* two small functions plus an i18n string. Fully reversible; no schema.

---

### BLOCK 11 — Finding-ID namespace disambiguation (`03-VAL-001`, source-comment half)

| | |
|---|---|
| **Findings owned** | `03-VAL-001` (the source-comment half) |
| **`depends_on`** | *(none)* — executes last; re-reads every file it touches |
| **Priority** | P2 — **gated on a coordinator decision** |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** → *all five* |

**Roster decision — CONFIRMED unchanged; all five.** Re-verified at `ba23277`: the inventory is
**68 citations across 27 files** (**D-7**), of which **8 are production** and 19 are tests.
`D-6` removes `ad_data/orm.py` from the production list entirely (it has zero citations) and
adds three test files. The Auditor's job (re-derive the set, establish each legacy ID's cycle
from the audit history) is real and is an **archival investigation, not a grep**. The
Researcher's conventions question and the Planner's cross-phase convention-setting are both
still justified. **Scope is what changed — see N-5, not the roster.**

**Scope shrink (N-5) — this is the correction to the source plan's scope.** BLOCK 11's
**default scope is the 8 production files**:

1. `src/backend/apps/core/utils/advisory_lock.py` (3 citations) — *two of the three this-cycle
   citations are handled inside BLOCK 2; the legacy `DB-001`/`DB-007` text is BLOCK 11's.*
2. `src/backend/apps/moderation/admin_actions.py` (4)
3. `src/backend/apps/moderation/services/moderation_log.py` (4)
4. `src/backend/apps/ads/services/submission.py` (1)
5. `src/backend/apps/ads/views/edit.py` (1)
6. `src/backend/apps/ads/models.py` (1)
7. `src/backend/apps/core/management/commands/archive_sweep.py` (1)
8. `src/backend/apps/search/management/commands/send_alerts.py` (1) — **the third this-cycle
   citation; non-negotiable under any option.**

The **19 test files are an explicitly optional second pass**, owned by phase 11 (test coverage).
**Reason:** the source plan's own §5.2 assigns test-file concerns to phase 11 and forbids phase 03
from expanding them; note 3 of the block already ranks production above test; and rewriting
comments in files that **twelve other phases are writing against in parallel** is the block's
largest process risk. If the coordinator wants the full sweep, the second pass runs as a
**separate commit** within the same block.

**Decision gate — Q14, second half (coordinator).** Option table in the source plan §3.11.1
(A prefix-only — rejected; B prefix sweep — risky where the audit history is missing; C
descriptive replacement — the plan's recommendation). **Default if unanswerable: the block is
DE-SCOPED and the de-scope is recorded** (§3.1). Under **any** option, the **three production
citations this cycle already polluted are non-negotiable** — `advisory_lock.py`'s `DB-004` and
`DB-010` (handled by BLOCK 2) and `send_alerts.py`'s `DB-007`. On a de-scope, `send_alerts.py`
is handed to the coordinator.

**Already decided and not up for renegotiation:** this plan and every phase from 04 onwards keys
its tracker on **`NN-<PREFIX>-00N`**; the precedent is shipped
(`src/telegram_bot/tests/test_unsubscribe.py` cites `03-DB-002`); every comment phase 03 adds in
BLOCK 1–10 uses `03-DB-00N`; BLOCK 11 does **not** touch a file it has no other business
touching.

**Agent briefs (paste-ready).**

> **Auditor.** *Goal:* re-derive the ambiguous-citation set at `ba23277` and establish which
> cycle each legacy ID belongs to. *Hard constraints:* change no code; **never infer a cycle
> number** — `git blame` / the audit history is the only evidence, and if it cannot be
> established the descriptive form is the correct fallback because it needs no attribution;
> `src/telegram_bot/services/ad_data/orm.py` has **zero** citations and is **not** a target
> (**D-6**). *Must return:* the exact inventory — 68 matches / **27** files, **8 production**
> / **19 test** (**D-7**) — plus, for each production file, the cycle attribution with its
> evidence, or an explicit "cannot be established".

> **Researcher.** *Goal:* answer Q14's conventions question — what is the maintainable way to
> cross-reference an ephemeral, per-cycle identifier in code comments so the reference is
> unambiguous, durable, and does not require archaeology to resolve. *Hard constraints:* a
> description cannot become ambiguous when a new cycle reuses an id; the repository already
> contains one shipped precedent (`03-DB-002` in `src/telegram_bot/tests/test_unsubscribe.py`).
> *Must return:* the recommended citation form, its durability argument, and how it interacts
> with the `NN-<PREFIX>-00N` convention phases 04–15 are adopting in parallel.

> **Planner.** *Goal:* specify the rewrite so it is safe against twelve phases writing in
> parallel. *Hard constraints:* **no test's name and no assertion may change**; production files
> before test files; files another phase is editing concurrently must be **re-read immediately
> before editing** and staged by explicit path; if the block is de-scoped, the three
> non-negotiable production citations are still handled. *Must return:* the ordered file list,
> the per-file rewrite plan, and the split between the mandatory production pass and the optional
> test pass.

> **Validator.** *Goal:* judge whether a future reader is misled — a judgement about reviewer
> experience that inspection cannot confirm. *Hard constraints:* change no code. *Must return:*
> the re-derivation sweep showing zero remaining in-scope ambiguous citations, confirmation that
> no assertion moved, and an explicit statement of what was left undone if de-scoped.

**Implementor task.**

```yaml
id: task_03_b11_finding_id_disambiguation
title: Disambiguate finding-id cross-references in production comments and docstrings
priority: medium
depends_on: []
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 11 — Finding-ID namespace disambiguation (VAL-001)"
extra_context: |
  THIS BLOCK IS GATED ON A COORDINATOR DECISION (Q14 second half). DEFAULT IF UNANSWERABLE:
  the block is DE-SCOPED and the de-scope is recorded. Under ANY option, the three production
  citations this cycle already polluted must be disambiguated:
  advisory_lock.py (DB-004 and DB-010 — two of these are handled inside BLOCK 2) and
  send_alerts.py (phase 03 DB-007 — handed to the coordinator if the block is de-scoped).
  ASSERTIONS ARE IMMUTABLE — comment and docstring text only, never a test name, never an
  assertion. Do not "helpfully" rename tests.
  NEVER INFER A CYCLE NUMBER. git blame / the audit history is the only evidence; where it
  cannot be established, use the descriptive form, which needs no attribution. A confident-but-
  wrong attribution is arguably worse than today's honest ambiguity.
  SCOPE (execution plan 13 §1.3 N-5): the DEFAULT scope is the 8 PRODUCTION files. The 19 test
  files are an OPTIONAL second pass, owned by phase 11, and run as a SEPARATE COMMIT if
  scheduled at all.
  CORRECTED INVENTORY (D-6, D-7): 68 citations across 27 files, NOT 26.
  src/telegram_bot/services/ad_data/orm.py has ZERO citations and is NOT a target.
  Files another phase is editing concurrently must be re-read immediately before editing and
  staged by explicit path — never `git add -A` (the tree carries 19 tracked .ai/audit/**
  deletions and 5 dirty docs, N-1).

description: >
  Bare DB-00N ids are used for previous cycles' defects across 27 shipped files, while this
  cycle's DB-004, DB-007 and DB-010 are cited naming-collision-identically. advisory_lock.py
  cites both a previous cycle's DB-010 and this cycle's DB-004 three lines apart, beside a
  previous cycle's DB-007. Apply the chosen disambiguation so a future reader is not misled,
  and so the NN-DB-00N convention is unambiguous going forward.

goals:
  - disambiguate every in-scope citation without asserting a cycle number that cannot be evidenced
  - reserve the NN-DB-00N form for the current remediation cycle
  - touch production files before test files
  - change no behaviour, no test name and no assertion

files:
  - path: src/backend/apps/core/utils/advisory_lock.py            # production, first
    targets: [{ type: function, name: advisory_lock }, { type: module, name: advisory_lock }]
    semantic_anchors: {}
  - path: src/backend/apps/moderation/admin_actions.py
    targets: [{ type: class, name: ModerationAdminActions }, { type: module, name: admin_actions }]
    semantic_anchors: {}
  - path: src/backend/apps/moderation/services/moderation_log.py
    targets: [{ type: module, name: moderation_log }]
    semantic_anchors: {}
  - path: src/backend/apps/ads/services/submission.py
    targets: [{ type: function, name: submit_ad }]
    semantic_anchors: {}
  - path: src/backend/apps/ads/views/edit.py
    targets: [{ type: function, name: ad_edit }]
    semantic_anchors: {}
  - path: src/backend/apps/ads/models.py
    targets: [{ type: class, name: Ad }]
    semantic_anchors: {}
  - path: src/backend/apps/core/management/commands/archive_sweep.py
    targets: [{ type: function, name: Command.handle }]
    semantic_anchors: {}
  - path: src/backend/apps/search/management/commands/send_alerts.py
    targets: [{ type: class, name: Command }]
    semantic_anchors: {}
  # OPTIONAL SECOND PASS, SEPARATE COMMIT, phase-11 territory: the 19 test files.
  # NOT a target: src/telegram_bot/services/ad_data/orm.py (zero citations, D-6).

changes:
  - action: edit_comment
    description: >
      Option C (recommended): replace opaque ids with a description of the defect, or name the
      symbol and the test that guard the fix. Option B: prefix with the cycle, ONLY where
      attribution is evidenced by the audit history — never inferred.
  - action: edit_docstring
    description: >
      Production-file docstrings first. Test-file docstrings may be rewritten in the optional
      second pass; TEST NAMES AND ASSERTIONS MAY NOT, ever. Files another phase is editing
      concurrently must be re-read immediately before editing and staged by explicit path.

acceptance_criteria:
  - zero remaining ambiguous citations among the production files this block was scoped to cover
  - the three this-cycle production citations are disambiguated under any option, or the
    de-scope explicitly hands send_alerts.py to the coordinator
  - no test name and no assertion was changed (the full suite proves it)
  - no behaviour changed: `.\Makefile.ps1 test` green, ruff and basedpyright green
  - no file was clobbered from a concurrent phase's uncommitted edit
  - no new AdvisoryLockId member and no change to advisory_lock's semantics — BLOCK 2 owns that
    file's logic and its allocation table
```

**Tests required.**

- *Must be added:* **none.** A comment-only block cannot have a behavioural test, and writing one
  would be testing trivia.
- *Must be changed:* **none.** No test name and no assertion may change.
- *Must keep passing unchanged:* the **entire** suite.

**Exact gate command (Docker only).**

```powershell
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.**

- *Risk:* rewriting a comment in a file **another phase is editing right now**, causing a
  conflict or a clobbered edit. Re-read each file immediately before editing; stage explicit paths.
- *Risk:* attributing the wrong cycle (Option B) — confidently-wrong is worse than ambiguous.
  Prefer the descriptive form wherever attribution is uncertain.
- *Risk:* an Implementor renames tests or touches assertions "while in there". **Explicitly
  forbidden.**
- *Risk:* the block is treated as cosmetic and de-scoped, leaving three production citations
  ambiguous. **Those three are non-negotiable.**
- *Rollback:* comment-only; fully reversible.

---

## 3. Gates and escalations

### 3.1 Decision gates — `Q1` … `Q14`

Every gate is **owned inside its block** unless marked *coordinator*. **No gate may be closed
silently by an Implementor**, and the chosen option must be recorded in the block's commit
message.

| # | Question | Gates | Owner | Default if unanswerable |
|---|---|---|---|---|
| **Q1** | Global `DATABASES["default"]["OPTIONS"]` libpq timeout vs. per-transaction `SET LOCAL` | BLOCK 5 | Researcher + Planner | **Must be closed inside BLOCK 5 before implementation.** No default is permitted — a wrong value turns **eight** row-lock concurrency tests red (`D-3`) or leaves the wait unbounded. |
| **Q2** | Where does the bounded-retry `OperationalError` boundary live, and who owns the seller-facing message? | BLOCK 5 | Researcher + Planner | **Must be closed inside BLOCK 5 before implementation.** The full `select_for_update` inventory (15 production expressions) must be enumerated and split retry-vs-error first. |
| **Q3** | `SET CONSTRAINTS ALL IMMEDIATE` vs. a named constraint | BLOCK 3 | Researcher + Implementor | **Must be closed inside BLOCK 3 before implementation.** Generated FK constraint names **must be read from the live Docker test schema**, never copied from the report. If `ALL IMMEDIATE` introduces a caller-visible behaviour change that matters, **escalate** rather than force a choice. |
| **Q4** | Savepoint + `SET CONSTRAINTS` vs. moving the write out of the caller's transaction | BLOCK 3 | Planner + Researcher | **Must be closed inside BLOCK 3 before implementation.** Both options' costs against the two shipped in-transaction tests must be stated. The **plain savepoint** variant is **rejected** — it does not fix the finding. |
| **Q5** | Heartbeat: explicit per-handler call vs. a new aiogram middleware | BLOCK 6 | Researcher + Planner | **Must be closed inside BLOCK 6 before implementation.** The inventory is **≈15 mutating handlers across 6 modules** (`R-7`); a missed one re-creates the exact defect. |
| **Q6** | Does staging need protecting, and must `_STAGING_TTL_SECONDS` be re-derived? | BLOCK 6 | Researcher | **Must be closed inside BLOCK 6 before implementation.** One of the three stated answers is legitimate — including "a seller who abandons a dialog for N hours loses their photo, and that is acceptable and must be documented". |
| **Q7** | **Where does the final media move happen relative to the transaction boundary?** | BLOCK 8 | Researcher + Planner | **Must be closed inside BLOCK 8 before implementation.** The single largest design question in the phase. Phase 01 explicitly deferred it; nothing in the tree pre-empts it. |
| **Q8** | Is the cheaper re-check-before-unlink variant actually safe? | BLOCK 8 | Researcher + Planner | **Bundled into BLOCK 8's gate.** It narrows but does not close the window, and costs a transaction per candidate orphan inside a lock already held for the whole `os.walk`. |
| **Q9** | Does the shared advisory lock close the double-send, or is `find_matching_saved_searches`' missing `NOT EXISTS` the real hole? | BLOCK 9 | Researcher + Planner | **Must be closed inside BLOCK 9 before implementation.** **Adding the lock alone is provably insufficient.** A block shipping only Option A must record in its commit message that the concurrency path is unproven and that B remains required. |
| **Q10** | The delivery-state column: which states, who writes them, when, and what is the backfill? | BLOCK 9 | Planner | **Must be closed inside BLOCK 9 before implementation** (only if Q9 chooses Option B). The **nullable column with `NULL` backfill** is already binding; `NOT NULL DEFAULT false` is forbidden. |
| **Q11** | How is "lock held once across per-batch commits" achieved, given `pg_advisory_xact_lock` releases with the enclosing transaction? | BLOCK 7 | Researcher + Planner | **Must be closed inside BLOCK 7 before implementation.** Structurally unresolvable as written. Option C (timeout only) **does not fix the finding** and is not a substitute. |
| **Q12** | Which product rule — "a new draft replaces the current one" or "a second draft is rejected"? | BLOCK 10 | **User / product, via coordinator** | **FIXED DEFAULT: Option A — "a new draft replaces the current one."** It matches shipped `create_draft_ad` behaviour and needs no new i18n. If defaulted, the commit message **must record that the choice was made by default, not by decision**. **Option C is FORBIDDEN.** |
| **Q13** | `03-VAL-003`: `AD-005` vs `03-DB-001` severity | BLOCK 4 (advisory) | **Coordinator** | **DECIDED.** One work item, one severity: **MEDIUM**, shipped in BLOCK 4. The phase-05 re-rating is escalated, not silently decided. **Advisory — must not block the phase** (§3.2). |
| **Q14** | Cross-cutting: how does this cycle key its IDs, and are the shipped comments disambiguated? | BLOCK 11 | **Coordinator** | **Tracker half DECIDED:** `NN-<PREFIX>-00N`, recorded for phases 04–15. **Source half: FIXED DEFAULT is a RECORDED DE-SCOPE.** BLOCK 11 does not run; the three production citations this cycle polluted remain non-negotiable — two are handled inside BLOCK 2, `send_alerts.py` is handed to the coordinator. |

**Options NOT decided here, by instruction:** Q1, Q3, Q5, Q6, Q7, Q9, Q10, Q11 (technical,
Researcher/Planner, inside their blocks), and Q2. Q12 and Q14 are surfaced with the source
plan's fixed defaults stated explicitly, as above.

### 3.2 Escalations routed **out** of phase 03 — both **advisory, must not block the phase**

| ID | Claim | Routing | Phase-03 obligation |
|---|---|---|---|
| **`03-VAL-003`** | `AD-005` (phase 05, **HIGH**) and `03-DB-001` (this cycle, **MEDIUM**) are **one defect filed twice** with disagreeing severities. If both are reported at their filed severities, the final report states a CRITICAL/HIGH pair for a defect that **destroys no data** — the rollback *preserves* the pre-existing DRAFT row and no `pre_delete`/`on_commit` deletion fires. `create_draft_ad` has one production invocation site inside a single bot process, where concurrent calls serialise on the single asgiref `thread_sensitive` worker; the trigger requires a second bot process. | **Coordinator**, for the `AD-005` re-rating in phase 05. **Phase 05 must not ship a second patch.** BLOCK 4 ships the **one** work item at MEDIUM. | BLOCK 4's gate is an **acknowledgement, not an investigation**, and **must not stall the phase if it never arrives**. The correct invariant to test is *"a draft is returned"*, **not** *"the seller's draft survived"* — a test written against the report's original framing would **fail against correct code**. |
| **`03-VAL-004`** | Two of the audit input's retained runtime reproductions do not survive contact with the production code path: `V-04` observed every `record_event` call wrapped in `transaction.atomic()` — true only because every call site was itself inside a transaction at measurement time; `V-02` observed the analytics INSERT succeeding *inside* `handle_login_orm`, but the INSERT is a statement Django issues **after** the savepoint block closes, so no savepoint covered it. The narrower real call graph makes DB-002's **reachability argument harder, not easier**. | **Coordinator**, for the final report's evidence-quality note. **No phase-03 block fixes an audit document.** `.ai/audit/**` is unmodifiable by mandate. | Record the full list of runtime claims that were **not** re-derived, so the report is corrected once centrally rather than eleven times. This is why BLOCK 3 carries a mandatory runtime probe and treats the ad-detail query budget as a first-class constraint. |

---

## 4. Cross-block rules — the non-negotiables

These bind **every** block. They are never re-derived per block.

1. **`src/backend/conftest.py` is untouched.** `create_test_ad` never sets `created_at` or
   `updated_at` (both `auto_*`), which is exactly why BLOCK 6's two tests back-date **locally**
   with `Ad.objects.filter(pk=…).update(updated_at=…)`. BLOCK 6 changes the two test files, not
   the helper.
2. **No new `AdvisoryLockId` member without the three-artefact commit.** `AdvisoryLockId` has
   **19** members; `REPAIR_BOT_USERNAME = 13` exists (`D-1`); ID 10 is reserved; any new id starts
   at **14**. If a design in BLOCK 7/8/9 concludes a new id is unavoidable, **`enums.py`** +
   **the lock-allocation table in `advisory_lock.py`'s module docstring** + **`test_advisory_lock_ids.py`**
   all change **in one commit**, and the coordinator is told **before**, not after.
3. **Never `git add -A`, `git add .`, `git commit -a`, `git reset`, `git checkout`, `git stash`
   or `git clean`.** The tree is dirty by design — **19** tracked `.ai/audit/**` deletions plus
   untracked plan/temp files — **and it moves under us**: another phase committed five dirty docs
   and moved HEAD while this document was being written (**N-1**). Stage explicit paths and
   re-read `git status --short` **immediately before every commit**; never trust a status list
   captured earlier in the block.
4. **Migration numbers are checked against their directories immediately before generation.**
   `ads` → `0008_*` (BLOCK 6); `search` → `0003_*` (BLOCK 9, Option B);
   `media` → `0002_*` (BLOCK 8, only if the schema changes); `core` → `0006_*` is claimed by
   phase 02 and **phase 03 needs no `core` migration** — do not create one to dodge the collision.
   The numbers above are correct **as of `ba23277`** and may not be by BLOCK 9.
5. **`apps.*` must never import `telegram_bot.*`.** BLOCK 6's heartbeat helper lives in
   `telegram_bot/services/ad_data/` and is re-exported through that package's `__init__.py` /
   `__all__` — never in `apps/`.
6. **Locale files are appended to, never regenerated.** `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`
   is a **shared artefact** with phase 14. Only BLOCK 6 and BLOCK 10 add user-visible strings;
   `msgstr` must be non-empty for **`ru` and `bs`** (`en` may be empty). A wholesale
   `makemessages` would discard a concurrent phase's additions.
7. **Filesystem side effects happen only after commit, via `transaction.on_commit()`.** Never
   unlink or move inside `transaction.atomic()`. The one deliberate exception direction is
   BLOCK 8's Option A, where an `on_commit` **promotion** is the fix — and it is still after
   commit.
8. **No new dependency.** Nothing in this plan needs one. Adding one would require `uv add`, a
   `uv.lock` update, and a CI `uv lock --check` pass.
9. **The three production citations that are non-negotiable in BLOCK 11** — `advisory_lock.py`
   (`DB-004`, `DB-010`) and `send_alerts.py` (`DB-007`) — must be disambiguated **under any
   option**, including on a de-scope. Two are handled inside **BLOCK 2**; `send_alerts.py` is
   BLOCK 11's or, on de-scope, the coordinator's. Leaving them ambiguous is the block's stated
   worst outcome.

**Standing implementation rules (from the source plan §1, carried forward unchanged).**

- **Tests run in Docker only.** `.\Makefile.ps1 test`, or `$dc run --rm --env PYTEST_SKIP_MARKERS=seed … test`.
  **Never** `uv run pytest` locally — no DB on `localhost:5432`. **Never**
  `--override-ini=addopts=` (it strips `--import-mode=importlib`). `PYTEST_OPTS` word-splits on
  spaces and **replaces** the defaults, so prefer `PYTEST_SKIP_MARKERS` for marker exclusion.
- **Static gates:** `uv run ruff check src/` and `uv run basedpyright src/` — both green at
  `ba23277`, both must stay green. Import sorting is `ruff check --fix src/`;
  **`ruff format` is not the project convention.**
- **No `print()`** — `logger = logging.getLogger(__name__)` with lazy `%s` formatting. All
  comments, docstrings, log messages, error messages and documentation in **English**.
- **Type safety:** every `with transaction.atomic():` carries the project's established
  `# pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed;
  Atomic.__enter__/__exit__ untyped` suppression (or an honest typed equivalent — never a bare
  suppression).
- **`StrEnum`/`IntEnum` for all fixed values** (project rule 10) — including the BLOCK 5 timeout
  constant and any BLOCK 9 delivery-state value. Never a bare literal or a dict-of-strings.
- **Pydantic v2 only at system boundaries**; the Django ORM remains the persistence layer for
  all CRUD in this plan. Business logic lives in `services/`, never in a view or a handler beyond
  a thin boundary change.
- **Bot async:** every bot DB call is `@sync_to_async` at the default `thread_sensitive=True`.
  **Do not "fix" DB-004 by raising the asgiref worker count.**
- **Production code is king:** where a shipped **green** test conflicts with the architecture or
  business logic, **fix the test** — and record the justification in the commit message. Blocks
  2, 3 (Option B), 6, 8, 9 and 10 each rewrite at least one green test; each names the test and
  the reason.
- **Task targets are never line numbers** — always `file` + semantic symbol.

---

## 5. Sequencing and status

### 5.1 Serial order and dependency edges

```
BLOCK 1  DB-011    Remove redundant AdImage key pre-collection (6 sweeps)   deps: —
      │     ──► soft edge to BLOCK 6 (same file: sweep_drafts.Command.handle)
BLOCK 2  DB-010    Advisory-lock release log + allocation-table correction  deps: —
      │     ──► soft edge to BLOCK 11 (advisory_lock.py)
BLOCK 3  DB-002    record_event must not abort the caller's transaction      deps: —
      │     ══► HARD edge (03-VAL-002): BLOCK 5
BLOCK 4  DB-001    Recoverable race backstop in create_draft_ad             deps: — [ADVISORY gate: 03-VAL-003]
      │     ══► HARD edge: BLOCK 10
BLOCK 5  DB-004    Bound the lock wait + retry boundary (timeout half)      deps: BLOCK 3
      │     ├──► HARD edge: BLOCK 7   (both rewrite archive_sweep / recompute handle)
      │     └──► HARD edge: BLOCK 9   (shared ALERT_DELIVERY_TASK lock surface)
BLOCK 6  DB-003    Idle-timeout semantics (heartbeat + migration)          deps: BLOCK 1 (soft)
      │     ══► HARD edge: BLOCK 8   (both edit sweep_orphaned_media.py + _STAGING_TTL_SECONDS)
BLOCK 7  DB-008    Per-batch commit, advisory lock held once                deps: BLOCK 5
BLOCK 8  DB-005    Media promotion must not precede its row commit          deps: BLOCK 6
BLOCK 9  DB-007    Serialise + de-duplicate immediate-alert delivery        deps: BLOCK 5, BLOCK 7 (order)
BLOCK 10 DB-009    One single-draft policy in both creators                 deps: BLOCK 4
BLOCK 11 VAL-001   Finding-ID namespace disambiguation (production files)   deps: — [GATED: Q14]
```

**Execution order: `1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11`.** Exactly one Implementor runs
at a time, so the order is always serial. The edges above record what must not be started early.

| Edge | Kind | Reason |
|---|---|---|
| **3 → 5** | **HARD — `03-VAL-002`** | A `statement_timeout` produces exactly the class of server-side `OperationalError` that `record_event`'s bare `except Exception` swallows and that aborts the caller's transaction. Shipping BLOCK 5 first turns DB-002 from *latent* into *live*. The single most important ordering constraint in the phase. |
| **5 → 7** | **HARD** | BLOCK 7 rewrites `archive_sweep.Command.handle` and `recompute_normalized_prices.Command.handle`, where BLOCK 5's timeout mechanism lands under either Q1 option. |
| **5 → 9** | **HARD** | `AdvisoryLockId.ALERT_DELIVERY_TASK` (9) is the surface BLOCK 9 operates on, and BLOCK 5 defines the bounded-wait behaviour lock acquisition inherits. |
| **6 → 8** | **HARD** | Both edit `sweep_orphaned_media.py` — `_STAGING_TTL_SECONDS` (BLOCK 6's Q6) and `_walk_media_files` / `_reclaim_stale_staging` / `_SEED_SUBDIR` (BLOCK 8's Q7). BLOCK 8's reclamation policy must be designed **against the TTL BLOCK 6 chose**. |
| **7 → 9** | **HARD (ordering only)** | No correctness dependency — different apps. The edge exists because BLOCK 7's `AdvisoryLockId` / `test_sweep_lock_structure.py` work is the more structural of the two; sequencing BLOCK 7 first keeps BLOCK 9's diff concentrated in `apps/search`. |
| **4 → 10** | **HARD** | Both implement **one** single-draft policy. BLOCK 4 establishes what it is for `create_draft_ad`; BLOCK 10 applies the *same* rule in `copy_ad`. |
| **1 → 6** | **SOFT** | BLOCK 1 removes the collection from `sweep_drafts.Command.handle`; BLOCK 6 changes the *predicate* in the same function. BLOCK 6 must re-read the file rather than assume BLOCK 1's state. |
| **2 → 11** | **SOFT** | BLOCK 2 already normalises this cycle's citations in `advisory_lock.py` **and** corrects its allocation table. BLOCK 11 runs last and re-reads the file. If BLOCK 11 is de-scoped, only `send_alerts.py` remains for the coordinator. |

**No edge exists, by design:** BLOCK 1 ↔ BLOCK 2 (different files, both low risk);
BLOCK 3 ↔ BLOCK 4 (independent chains — BLOCK 3 gates BLOCK 5, BLOCK 4 gates BLOCK 10);
BLOCK 6 ↔ BLOCK 5 (neither's correctness depends on the other — BLOCK 6's heartbeat is a
single-column `UPDATE` with no `select_for_update`); BLOCK 9 ↔ BLOCK 6/8 (different apps, no
shared file, lock id or test).

### 5.2 Status table — the coordinator's single surface

Update **this table** as blocks land. Do not edit the source plan's §8.6 checklist instead.

| # | Block | Findings | Roster | Gates closed | Depends on | Migration | Implementor | Validator | Committed |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `task_03_b01_remove_storage_keys_precollection` | `03-DB-011` | Impl, Validator | — | — | — | ☐ | ☐ | ☐ |
| 2 | `task_03_b02_advisory_lock_release_log` | `03-DB-010` + `D-1` table fix | Impl, Validator | — | — | — | ☐ | ☐ | ☐ |
| 3 | `task_03_b03_record_event_transaction` | `03-DB-002` | **All five** | **Q3, Q4** | — | — | ☐ | ☐ | ☐ |
| 4 | `task_03_b04_create_draft_savepoint` | `03-DB-001` | Impl, Auditor, Validator | `03-VAL-003` *(advisory)* | — | — | ☐ | ☐ | ☐ |
| 5 | `task_03_b05_lock_timeout` | `03-DB-004` (timeout half) | **All five** | **Q1, Q2** | BLOCK 3 | — | ☐ | ☐ | ☐ |
| 6 | `task_03_b06_idle_timeout` | `03-DB-003` | **All five** | **Q5, Q6** | BLOCK 1 (soft) | `ads/0008_*` | ☐ | ☐ | ☐ |
| 7 | `task_03_b07_per_batch_commit` | `03-DB-008` | **All five** | **Q11** | BLOCK 5 | — | ☐ | ☐ | ☐ |
| 8 | `task_03_b08_media_promotion_window` | `03-DB-005` | **All five** | **Q7, Q8** | BLOCK 6 | `media/0002_*` only if schema changes | ☐ | ☐ | ☐ |
| 9 | `task_03_b09_immediate_alert_serialisation` | `03-DB-007` | **All five** | **Q9, Q10** | BLOCK 5, BLOCK 7 | `search/0003_*` (Option B) | ☐ | ☐ | ☐ |
| 10 | `task_03_b10_single_draft_policy` | `03-DB-009` | Impl, Auditor, Planner, Validator | **Q12** (default **A**) | BLOCK 4 | — | ☐ | ☐ | ☐ |
| 11 | `task_03_b11_finding_id_disambiguation` | `03-VAL-001` | **All five** | **Q14** | — | — | ☐ | ☐ | ☐ |

### 5.3 Definition of done — phase 03

Distilled from the source plan §8 and **corrected where the tree at `ba23277` proves §8 stale**.

**Scope**
- [ ] All 11 `03-DB-*` findings have a recorded disposition: **10 implemented** (`001`, `002`,
      `003`, `004` *timeout half only*, `005`, `007`, `008`, `009`, `010`, `011`), **1 rejected**
      (`006`, residue shown covered by `011`).
- [ ] `03-DB-004`'s commit message states that the `ENT-006` addendum was already shipped by
      phase 01 and only the timeout half landed here — re-anchored **by symbol**
      (`test_migrate_locked.py::TestSessionLockAcquisitionLog::test_session_lock_logs_request_before_acquire`).
- [ ] All 4 `03-VAL-*` findings have a recorded disposition: `VAL-001` tracker half **decided**
      and source half **shipped or explicitly de-scoped**; `VAL-002` landed as the `3 → 5`
      ordering edge and was honoured; `VAL-003` escalated (§3.2); `VAL-004` routed to the
      final report (§3.2).
- [ ] **Every gated block (3, 5, 6, 7, 8, 9, 10) has a written decision** naming the option
      chosen and the consequences accepted. Silence is not an acceptable outcome. For Q12 the
      record states whether A was **decided or defaulted**.
- [ ] `03-DB-006`'s rejection is restated so it is not silently re-filed by a later phase.

**Gates — all green**
- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `.\Makefile.ps1 test` → full suite green (seed marker skipped).
- [ ] `.\Makefile.ps1 test-recreate` executed at least once after BLOCK 6's `ads/0008_*` and, if
      generated, after BLOCK 9's `search/0003_*` and BLOCK 8's `media/0002_*`.
- [ ] `git status --short .ai` shows **no new modifications** beyond the 19 pre-existing
      `.ai/audit/**` deletions.
- [ ] `git status --short docs` shows **no modifications beyond those an in-flight parallel phase
      had when this block started** — and no other phase's doc content was swept into a phase-03
      commit (**N-1**).
- [ ] Every block's **exact gate command** was run and green — not the full suite alone.
- [ ] ID-sweep: zero remaining ambiguous `DB-0\d\d` citations among the files BLOCK 11 was scoped
      to cover — **or** a recorded de-scope with the three non-negotiable production citations
      handled (two by BLOCK 2, `send_alerts.py` handed to the coordinator).
- [ ] BLOCK 3's runtime probe was executed against the Docker test database **before** the fix,
      its result recorded, and the probe deleted (not committed).
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git stash`, `git add -A` or `git commit -a` was run at any point.

**Per-finding behavioural confirmation**
- [ ] **`03-DB-001`** — with `uq_ads_single_draft_per_user` forced to fire, `create_draft_ad`
      **returns a draft** rather than propagating the driver error. `TestCreateDraftAdCrashRecovery`
      passes unchanged.
- [ ] **`03-DB-002`** — inside a caller-owned `atomic()`, a **real server-side** error in
      `record_event` leaves the caller's business write **committed**; the test was demonstrated
      **red**. `submit_ad`'s roll-back-on-moderation-failure case passes unchanged. The ad-detail
      budget was **measured**: either `_QUERY_BOUND` was raised with a derivation, or the commit
      message records why the count did not change.
- [ ] **`03-DB-003`** — a draft with an old `created_at` and a **recent** `updated_at`
      **survives**; an old `updated_at` **is deleted**; a heartbeat on a dialog step keeps the
      draft alive; `IX_ads_draft_sweep` is on `(status, updated_at)`; an expired draft produces
      the **translated**, seller-recoverable message, not the generic moderation text.
- [ ] **`03-DB-004`** — a call holding a row lock ~1 s is **not** blocked indefinitely. All
      **eight** shipped ~1 s concurrency tests across **six** files (`D-3`) still assert what they
      mean. `record_event` handles the resulting `OperationalError`. No worker-count change.
- [ ] **`03-DB-005`** — a sweep overlapping a `submit_ad` never deletes a file whose `AdImage`
      row commits, **and** files orphaned by a rolled-back submit are reclaimed within a bounded
      time. `AdImage.save()`'s content hash is identical before and after any promotion move.
- [ ] **`03-DB-007`** — a failed `_run_send` followed by a `send_alerts` run **still delivers**.
      An already-delivered pair is **not** delivered twice. A pair delivered only by the daily
      path is still excluded by the immediate matcher. Pre-existing rows are `NULL` and not
      filtered. The feature still does nothing with the flag `False`.
- [ ] **`03-DB-008`** — a failure in batch *N* leaves batches 1..*N*-1 **committed**. The lock is
      acquired **exactly once** and held across all batches. The queryset is re-derived per batch.
      `order_by("pk")` lock ordering is preserved, and **added** where missing, for
      `recompute_normalized_prices`. The test was demonstrated **red**.
- [ ] **`03-DB-009`** — a seller with an existing `DRAFT` running `/copy` ends with the chosen
      option's outcome, and the same policy is demonstrably in force in **both** `create_draft_ad`
      and `copy_ad`. The failure message contains **no** raw driver text. `test_ad_copy.py`'s
      `"failed"` assertion passes unchanged.
- [ ] **`03-DB-010`** — the release line is emitted on the **rollback** path as well as the normal
      path, the exception still propagates, `pg_advisory_xact_lock` is issued exactly once with no
      `pg_advisory_unlock` added to the transaction branch. Both rewritten tests were demonstrated
      **red**.
- [ ] **`03-DB-011`** — no `storage_keys` and no dead `ad_ids` remain in the six commands;
      `delete_photo` still runs **exactly once** per key; `consent_hard_delete` still logs its
      user count and keeps `user_ids`.
- [ ] **`03-VAL-001`** — `advisory_lock.py` no longer contains two different `DB-010` references
      three lines apart, this cycle's own citations are cycle-scoped, and the allocation table
      lists all **19** ids with the reserved range stated as **14–99** (`D-1`).

**Cross-phase integrity**
- [ ] `test_migrate_locked.py::TestSessionLockAcquisitionLog` passes **unchanged**.
- [ ] The earlier cycle's `send_alerts` idempotency behaviour is intact, verified **by symbol**
      (`SchedulerDailyMarker`, `_DIGEST_AD_LIMIT`) — **not** by the hash `fbbb6cf` (`D-2`).
- [ ] `ENT-009` is recorded as **absorbed** by `03-DB-003`, not re-shipped.
- [ ] `src/backend/conftest.py` is **unmodified**.
- [ ] `AdvisoryLockId` gained **no new member**, or the three artefacts (`enums.py`,
      `advisory_lock.py`'s table, `test_advisory_lock_ids.py`) changed in one commit and the
      coordinator was notified **before**.
- [ ] No `apps/*` module imports `telegram_bot/*`.
- [ ] `copy_ad`'s storage-key reuse and `delete_adimage_files_on_delete` are unchanged
      (`AD-003`, phase 05).
- [ ] Recipient-selection logic in `find_matching_saved_searches` is unchanged beyond the
      delivery-state filter (`PII-104`, phase 06).
- [ ] `CONN_MAX_AGE` / connection lifecycle is unchanged; the asgiref worker count is unchanged.
- [ ] Migration numbers were checked against their directories **immediately before** generation;
      `apps/core/migrations/` gained nothing in this phase.
- [ ] `docs/02-database/db-retention.md` no longer claims *"no lock timeout is configured"* and
      its `sweep_drafts` row states inactivity, not creation age; `db-indexes.md` matches
      `IX_ads_draft_sweep`. **No other document was edited** (`N-3`).
- [ ] Locale files were **appended** to, never regenerated wholesale; `ru` and `bs` `msgstr` are
      non-empty for every new string.
- [ ] No new dependency was added (`uv.lock` unchanged).

**Project conventions**
- [ ] Every new constant is a named module-level constant or a `StrEnum`/`IntEnum` member.
- [ ] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] All comments, docstrings, log messages and error messages are in **English**.
- [ ] Every `with transaction.atomic():` carries the project's established pyright suppression (or
      an honest typed equivalent).
- [ ] Business logic lives in `services/`; no new logic in a view or handler beyond the thin
      boundary change its block requires.
- [ ] Every non-trivial behaviour change has a test that verifies **logic and component
      interaction** — not a variable's absence, not a log string, not a line count. (This is why
      BLOCK 1 and BLOCK 11 add **no** tests.)
- [ ] Filesystem side effects happen only **after** commit, via `transaction.on_commit()`.
- [ ] No task target is a line number; every target is a file plus a semantic symbol.
- [ ] `uv run ruff check --fix src/` was run if imports were reordered.
- [ ] New test code is bandit-clean (list-form `subprocess.run([sys.executable, …])`, no literal
      `/tmp`).

**Deliverables**
- [ ] The `03-VAL-003` re-rating request for phase 05's `AD-005` is recorded and communicated to
      the coordinator — **not** silently decided.
- [ ] The `03-VAL-004` evidence-quality note is recorded for the final report, including every
      runtime claim that was **not** re-derived.
- [ ] The `03-VAL-001` convention (`NN-<PREFIX>-00N`) is recorded and handed to the phases
      04–15 coordinators, so twelve plans do not invent twelve conventions.
- [ ] The status table in §5.2 is complete.
- [ ] No commit was made without an explicit user request.
