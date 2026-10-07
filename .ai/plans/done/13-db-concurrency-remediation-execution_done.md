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
status: "complete"
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
    $dc run --rm --no-deps --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test -e DATABASE_URL=$scratch test python src/backend/manage.py showmigrations ads   # 0008 [x]
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
amendment surface is precisely bounded. Q11 is now **CLOSED** (see *Decisions* below) — the
Researcher resolved it and the Planner folded in the refutation, the two plan corrections, the
guard-test replacement and the two open items. Validator remains mandatory because resolving Q11
wrongly loses mutual exclusion **silently**.

**Decisions — CLOSED by Researcher + Planner. Do not re-open; do not substitute an alternative.**

The tension is exact: `pg_advisory_xact_lock` releases with the **enclosing** transaction, so an
outer `atomic()` spanning the loop makes the per-batch commits not real commits, and a real
per-batch commit releases the lock. Option table in source plan §3.7.1. All gates closed:

| Gate | CLOSED decision |
|---|---|
| **Q11** — lock held once across per-batch commits | **Option A — `advisory_lock(id, session=True)` → `pg_advisory_lock`**, with the existing `finally: pg_advisory_unlock` releasing it. **No enclosing `transaction.atomic()` in `handle`** — one would turn each per-batch `atomic()` into a savepoint and silently restore DB-008. **Zero change to `advisory_lock.py`**: the session branch already exists. Rejected: B (dedicated pinned connection — more machinery, same exclusion), per-batch re-acquisition (changes what the lock *means* — one batch, not one sweep), C (does not fix the finding), D. |
| **Q7** — `archive_sweep` batch key | **keyset on `(published_at, pk)`** — **no migration** (existing `IX_ads_archive_sweep`). |
| **Q7** — `recompute_normalized_prices` batch key | **keyset on `pk`** — **no migration** (existing `ads_pkey`). One statement per batch; the `values_list("pk").iterator()` enumeration **and** the second `filter(pk__in=batch_ids)` re-read both disappear. |
| **Q7** — re-derivation | **Forced, not preferred.** `.iterator()` uses `chunked_cursor()` (no `DISABLE_SERVER_SIDE_CURSORS` in `config/settings/**`), i.e. a server-side cursor PostgreSQL closes at `COMMIT`. A per-batch-commit design physically cannot keep today's one-pass cursor open. |
| **Q7** — batch size | **hardcoded module constant `_BATCH_SIZE = 500`.** No CLI argument, no env var. |
| **Q8** — `archive_sweep` observability | per-batch **INFO** with batch index + cursor + `hold_ms`; on failure `logger.exception` + **re-raise**; closing INFO moved **after** the lock; **no `skipped` counter** (`selected - archived` is structurally always `0` — the `ValueError` branch is unreachable while we hold `FOR UPDATE`). |
| **Q8** — `recompute_normalized_prices` | **fail-the-command** (BLOCK 5's `apps/moderation/management/commands/admin_actions.py` precedent). No marker, no per-batch isolation. The command is operator-triggered only (in neither `HOURLY_COMMANDS` nor `DAILY_COMMANDS`), so a zero exit on partial work would be the worst outcome. The two existing per-row handlers (`ValueError`, `ExchangeRateNotFoundError`) stay exactly as they are. |
| **Q7** — dead work | move `queryset.count()` **inside `if dry_run:`**, on a queryset **without** `select_for_update()` so a dry run provably takes no row locks. |

**The two invariants survive unchanged — both are still binding.**

1. The advisory lock is taken **once** and held across **every** batch. Moving the commit
   inside the loop while the lock is released per batch is **strictly worse** than today.
2. The queryset is **re-derived at the start of each batch**, not iterated from a single
   long-lived cursor, so batch *N+1* cannot act on rows batch *N* already changed.

**The plan's `order_by("pk")` invariant is superseded, not violated.** It is *preserved and
supplemented* for `recompute_normalized_prices` (whose `.order_by("pk")` did not exist — `Ad.Meta`
declares no `ordering`, and `_recompute` applied none, so the guarantee the invariant was
protecting was never there), and `archive_sweep` moves to ascending `(published_at, pk)` because
that is the only order PostgreSQL can serve as an `Index Cond`. Both commands gain an explicit
ordering where none was guaranteed, which is the intent of the invariant.

**Cost is measured and is NOT a regression.** `archive_sweep` **+2.4 %** (17.12 s → 17.53 s at
31 500 stale rows); the cost is dominated by 31 500 single-row `UPDATE`s at 542 µs, not by the
read loop (read+lock: 36 ms one-pass → 442 ms keyset). `recompute_normalized_prices` is **−68 %**
(3.1× faster: 118 batches, 307 ms → 99 ms). Worst measured per-batch transaction hold: **445 ms**
against BLOCK 5's 10 000 ms `lock_timeout` — a **22× margin** (~11× after the per-row Redis
`INCR` `post_save` performs).

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
    targets: [{ type: function, name: test_archive_sweep_handle_uses_select_for_update_and_atomic }]  # DELETE (token test) -> runtime spy
    semantic_anchors: {}   # replaced by a QuerySet.select_for_update runtime spy (see addendum 4)
  - path: src/backend/apps/currencies/tests/test_recompute_command.py
    targets:
      - { type: function, name: test_process_batch_uses_select_for_update }  # DELETE (token test) -> runtime spy
      - { type: class, name: TestRecomputeNormalizedPrices }
      - { type: class, name: TestRecomputeRowLockConcurrency }               # byte-identical, do NOT touch
  - path: docs/02-database/db-retention.md
    targets: [{ type: section, name: Configuration }]
    semantic_anchors:
      insert_after:
        type: paragraph
        value: "LOCK_TIMEOUT_SECONDS` (default 10) bounds every lock wait"
  - path: docs/ops/docker-deployment.md
    targets: [{ type: section, name: lock timeout runbook }]
    semantic_anchors:
      replace_in_body:
        old: "holds its `select_for_update()` for the whole sweep until per-batch commit lands"
  # NOT touched: apps/core/utils/scheduler.py's command lists; AdvisoryLockId;
  #             Ad.transition_to; Ad.Meta.indexes; apps/core/utils/advisory_lock.py;
  #             apps/media/management/commands/sweep_orphaned_media.py (BLOCK 6/8);
  #             src/backend/conftest.py. DO NOT add repair_bot_username to
  #             SWEEP_COMMANDS/_LOCK_TARGET_MODULES — it would change the
  #             count-coupled assertion in BLOCK 7's own backstop.

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
  - the cutoff is FROZEN once before the loop; the archive_sweep cursor is the TUPLE
    (published_at, pk) with ORDER BY published_at ASC, pk ASC
  - the LIMIT lives on the SAME queryset that is select_for_update()'d, and that queryset is
    evaluated inside the per-batch atomic(); no queryset is locked unbounded
  - NO enclosing transaction.atomic() remains in archive_sweep.Command.handle or
    recompute_normalized_prices.Command.handle / ._recompute
  - test_sweep_lock_structure.py's BOTH assertions (session is False AND in_atomic is True) are
    amended for EXACTLY the two named commands; the other 12 entries are byte-identical
  - HOURLY_COMMANDS and DAILY_COMMANDS are unmodified; test_scheduler.py passes unchanged
  - AdvisoryLockId gained no new member; no migration was created (apps/0009_* stays free)
  - the two docs/ files carry the batching + PgBouncer-prerequisite + partial-success text,
    including the removal of BLOCK 5's now-false "until per-batch commit lands" forward reference
  - the commit message states what all-or-nothing relaxation costs (a mid-sweep failure leaves
    earlier batches applied and the sweep re-runs on the next tick; re-running is safe because
    the predicates are time-based and re-derived, transition_to is idempotent per row, and
    unchanged normalised values are already skipped)
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - the Docker gate below is green
```

**Planner addendum (post-Researcher). Corrections and resolutions that supersede the task body
above.**

**1. The Researcher's refutation of the Auditor's "pk keyset is quadratic" claim. The Researcher
is right; the plan's `order_by("pk")` recommendation is withdrawn for `archive_sweep`.** The
claim did **not** reproduce as a stable property: the `pk` keyset produced **three different
plans across runs** for the same query shape (correlated `Index Cond: (id > 0)`; interleaved
`Index Cond: (id > 32000)`; and an emptied-tail `Index Scan using ads_pkey` with `Rows Removed
by Filter: 65000` at 28 ms / 63 798 buffers for a query returning **zero** rows) plus the
Auditor's `Bitmap Heap Scan + Sort (Sort Key: id)` with the `pk` window as a **post-scan Filter**.
That `Sort`/`Bitmap` shape *is* real — in it every batch re-reads and re-sorts the whole stale
set (63 × 31 500 ≈ 2 M visits) — it is simply not the plan PostgreSQL 18 picks on every
distribution. **The disqualifier is that the per-batch plan is pinned by nothing.** `published_at`
*is* pinned, because only `IX_ads_archive_sweep` can serve `ORDER BY published_at, pk` on that
predicate; the `Incremental Sort` it causes is a tiebreaker sort on `, pk` alone (one tiny group,
`Index Searches: 1`), and its tail query is **8× cheaper** (7.9 ms / 31 482 buffers vs 28 ms /
63 798). **That plan stability — not the read-loop constant — is why `published_at` wins.**
OFFSET/LIMIT is also rejected: every committed batch removes rows, so later offsets skip live
rows — strictly worse under exactly the concurrency the fix targets. A new index is rejected: the
only useful one is a partial index whose predicate contains the moving cutoff, and phase 05
contends for `ads/` (the `0008_*` collision with BLOCK 6 already happened). **BLOCK 7 ships no
migration; `ads/0009_*` stays free.**

**2. Plan correction — `test_sweep_lock_structure.py` needs `in_atomic is True` exempted too.**
With `session=True` and **no** enclosing `atomic()`, the spy's
`transaction.get_connection().in_atomic_block` records `False` for those two entries. Amending
only `session` leaves the test red. The amendment is a **per-command exemption keyed to the two
named entries** (`archive_sweep`, index 0 of `SWEEP_COMMANDS`; `recompute_normalized_prices`, index
12), asserted positively for them (`session is True`, `in_atomic is False`) and unchanged for the
other **12 of 14** transaction-scoped lock-takers, which stay byte-identical. The module docstring's
blanket "every command acquires `pg_advisory_xact_lock` inside `transaction.atomic()`" claim and
the `SWEEP_COMMANDS` comment must be corrected to say so explicitly.

**3. Plan correction — `docs/ops/docker-deployment.md` is in the file surface and must be
REWRITTEN, not amended.** BLOCK 5 left a forward-reference — *"holds its `select_for_update()` for
the whole sweep **until per-batch commit lands**"* — that becomes **false on landing**. It is
replaced by the runbook text in the task's documentation deliverable, which also carries the new
partial-success semantics and the PgBouncer prerequisite.

**4. Guard tests: the `inspect.getsource` token approach is DELETED and replaced.** Both token
tests asserted **two** tokens, so a **vestigial** `with transaction.atomic():` left in `handle`
(now only a savepoint) would keep them **green** while silently defeating the entire fix — token
presence is the wrong oracle. `test_archive_sweep_handle_uses_select_for_update_and_atomic` and
`test_recompute_command.py::test_process_batch_uses_select_for_update` are replaced by a
**`QuerySet.select_for_update` runtime spy** (`patch.object(QuerySet, "select_for_update", …)`,
the pattern already in `apps/core/tests/test_db_lock_timeout_boundary.py::TestBulkLockTimeout`),
which asserts a real call rather than a substring. The second token test must be **deleted, not
re-pointed** — it resolves `Command._process_batch` by attribute, and that symbol is renamed. One
new **behavioural** test is the regression control: `django_db(transaction=True)`, monkeypatched
small `_BATCH_SIZE`, `Ad.transition_to` raising in batch 2, asserting batch 1's rows are
**`ARCHIVED`** and the exception **propagates**. It is **RED pre-fix**, which is what makes it a
control. `TestArchiveSweepRowLockConcurrency` and `TestRecomputeRowLockConcurrency` stay
**byte-identical** — neither invokes either command, so they cannot detect this block in either
direction; they remain the DB-010/DB-001 property guards and must not be credited as controls.

**5. Two items the plan left open — RESOLVED by Planner (see the Implementor task for the full
reasoning).** (a) **`cutoff` is frozen ONCE, before the loop and before `advisory_lock` is
entered.** A per-batch cutoff lets a row cross *into* the eligible set behind the cursor, where
the keyset never revisits it — a silent skip for the whole run. The monotonic-shrinkage proof only
holds under a frozen cutoff, and the dry-run `count()` must describe the same population the real
sweep would archive. (b) **The `archive_sweep` cursor is the TUPLE `(published_at, pk)`, not
`published_at` alone.** `published_at` is not unique, so a single-column `published_at__gt` window
skips every remaining tie at a batch boundary — silent, unbounded staleness. `ORDER BY
published_at ASC, pk ASC` is additionally required for `LIMIT` determinism among ties.

**6. Accepted risks — recorded, NOT engineered away.** `session=True` is **not PgBouncer
transaction-mode safe** (hard prerequisite, with a future trigger). Lock ordering is advisory
discipline, not a guarantee — PostgreSQL does not promise acquisition order for `LIMIT … FOR
UPDATE`. A cross-command cycle between lock 1 and lock 12 in two key orders is possible: blast
radius **one batch**, `40P01` at `deadlock_timeout` (1 s) beats the 10 s bound, and it is
**strictly better than today** (which would roll back the whole sweep). A row entering eligibility
behind the cursor is **deferred one cycle** (measured). Uncaught `bulk_update` and every
non-expected exception **lose one batch, loudly**. **Per-row Redis `INCR` inside the row-locking
transaction** (`post_save` → `bump_search_version`, ~0.2–1 ms/row on top of 445 ms) is
**forbidden to fix** here — `Ad.transition_to` and `post_save` are out of scope. **Partial-success
semantic change:** a non-zero `archive_sweep` exit now means **batches 1..N-1 committed**; the
runbook text is in the task's documentation deliverable.

**7. Confirmed out of scope — state explicitly, do not "helpfully" fix.** `repair_bot_username`
(the 14th transaction-scoped lock-taker, `AdvisoryLockId.REPAIR_BOT_USERNAME == 13`, missing from
`SWEEP_COMMANDS` and `_LOCK_TARGET_MODULES`): **do not add it** — it would change the
count-coupled assertion in the very test BLOCK 7 relies on as its backstop. `filesystem.py::
move_staging_to_permanent`'s dangling-`AdImage` defect is BLOCK 8 / phase 07's and a shipped
green test currently **asserts** it (`test_filesystem.py::TestMoveStagingToPermanent::
test_updates_key_even_if_file_missing`) — reported, not fixed. `sweep_orphaned_media.py` —
BLOCK 6 left `_STAGING_TTL_SECONDS = 2*60*60` unchanged; **BLOCK 7 may not touch that file at
all.** `scheduler.py`'s command lists, `AdvisoryLockId`, `Ad.transition_to`, `Ad.Meta.indexes`,
`advisory_lock.py`, `src/backend/conftest.py`, `.ai/audit/**`, `.ai/plans/**` — untouched.
Pre-existing, record do not fix: `recompute_normalized_prices` never bumps the search content
version (`bulk_update` fires no `post_save`, so `price_normalized_eur ∈ _SEARCH_RELEVANT_FIELDS`
is not reindexed), and `PriceNormalizer._rate_cache` is process-local and does not memoise misses.

**Tests required.**

- *Must keep passing unchanged:* all of `test_sweep_archive.py` **except** the two replaced
  structural cases; all of `test_sweep_delete.py`; the **12** unaffected entries in
  `test_sweep_lock_structure.py`; `TestArchiveSweepRowLockConcurrency`;
  `TestRecomputeRowLockConcurrency`; `TestArchiveSweepPositivePath`; `apps/core/tests/test_scheduler.py`.
- *Must be added:* the behavioural `test_batches_commit_independently` (**red pre-fix**), its
  `recompute` mirror, and the two `QuerySet.select_for_update` runtime-spy replacements.
- *Must be changed:* `test_sweep_lock_structure.py::TestSweepLockOrdering` (two-entry exemption
  + docstrings) **only**.

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

**Implementor task.** *(rewritten by the Planner after Q7/Q8 were closed — this supersedes the
draft task body in the source plan; see the Planner addendum below for the four staleness
corrections it carries.)*

```yaml
id: task_03_b08_media_promotion_window
title: "Promote staged media in transaction.on_commit so no file is visible to the orphan sweep before its AdImage row commits"
priority: medium
depends_on: [task_03_b06_idle_timeout]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 8 — Media promotion must not become visible before its AdImage row commits (03-DB-005)"
source_blocks:
  - "BLOCK 8 — Media promotion must not become visible before its AdImage row commits (`03-DB-005`)"
extra_context: |
  Q7 AND Q8 ARE CLOSED. They are NOT open questions, MUST NOT be re-litigated, and no
  alternative may be substituted for either.

  Q7 = OPTION A-PRIME (a variant the source plan does not list): reuse `staging/` ITSELF as the
  sweep-excluded holding area and promote in `transaction.on_commit`. NO NEW DIRECTORY.
    - Files stay in `MEDIA_ROOT/staging/` for their whole uncommitted life.
    - The `AdImage` row is written with the PERMANENT key (prefix already stripped).
    - The `os.replace` runs from an `on_commit` callback registered INSIDE the atomic block.
    - The plan's Option A prices itself at four costs that are ALREADY PAID:
      `STAGING_SUBDIR`/`STAGING_PREFIX` exist, `_walk_media_files` already skips `staging/`,
      and `_reclaim_stale_staging` already reclaims it on BLOCK 6's mtime heartbeat. The
      `6 -> 8` hard edge is satisfied LITERALLY — BLOCK 8 inherits BLOCK 6's predicate,
      constant and heartbeat instead of re-deriving a policy against them.
    - On rollback the file stays in `staging/` and dies to the existing TTL — the same fate
      as an abandoned upload, already modelled and tested.
    - It closes interleaving A BY CONSTRUCTION: the file is never where `_walk_media_files`
      looks until its row commits. No lock, no re-check, no timing assumption. It is the only
      candidate that removes the premise of the race rather than bounding it.
    - It mirrors the shipped convention: the `AdImage pre_delete` signal ALREADY defers FS
      deletion via `transaction.on_commit`, so this adds no new machinery.
  CONSEQUENCES OF A-PRIME THAT SUPERSEDE THE SOURCE PLAN:
    - NO new subdirectory constant, NO new `_walk_media_files` exclusion, NO new reclamation
      policy. The plan's option-A risk row ("a sweep-excluded subdirectory that nothing
      reclaims") CANNOT FIRE, and its "mandatory reclamation test" resolves to the EXISTING
      `TestSweepOrphanedMedia::test_stale_staging_file_reclaimed`.
    - `STAGING_SUBDIR`, `STAGING_PREFIX` and `KEY_FORMAT_REGEX` are UNCHANGED. The row stores
      a permanent key, which already matches `KEY_FORMAT_REGEX`. Change none of them.
    - `docs/ops/docker-deployment.md` is UNCHANGED and the "these two commands" session-lock
      wording in `docs/02-database/db-retention.md` STAYS AS-IS.

  INTERLEAVING B IS FIXED INDEPENDENTLY OF Q7, BY THE `setattr` PLACEMENT — never by inheriting
  a fix from BLOCK 6. B is still reachable after BLOCK 6: only
  `telegram_bot/handlers/ad_create/photos.py::process_photos` and
  `telegram_bot/handlers/ad_create/submit.py::process_preview` call `touch_staging_photos`;
  `category.py`, `city.py`, `price.py` and `text.py` touch only the row. A dialog spending more
  than 2 h across those steps still loses its files. The contract:
      REWRITE A KEY IFF THE FILE WAS ACTUALLY MOVED.
      A MISSING STAGING FILE RAISES FileNotFoundError NAMING THE KEY. NO KEY IS REWRITTEN.
  RAISE, not skip. `delete_photo` already classifies `FileNotFoundError` as terminal ("the
  file is already gone and retrying would not help"), and raising is the only option that
  preserves the information needed for a RECOVERABLE seller message. Skip-silently IS the
  defect. `submit_ad` catches it BEFORE opening the transaction and returns
  `(False, [_("One of your photos is no longer available. Please upload it again.")])` —
  strictly better than today's `(True, [])`, which publishes an ad with a broken image.

  Q8 = NEITHER batching NOR session=True. `sweep_orphaned_media` keeps ONE read-only snapshot,
  ONE delete loop, ONE `transaction.atomic()` with `session=False`. The premise that forced
  `session=True` was Option B's per-candidate commit releasing the lock early; under A-prime
  there are no per-candidate transactions, so the premise is GONE. Therefore
  `sweep_orphaned_media` is NOT added to `_SESSION_SCOPED_BATCHERS`,
  `test_sweep_lock_structure.py` is UNTOUCHED, and the "these two commands" wording in
  `docs/02-database/db-retention.md` and `docs/ops/docker-deployment.md` STAYS AS-IS and
  remains accurate. ONE discipline, not blended.

  DEAD CODE: delete the unreachable `if not dry_run:` guard in
  `sweep_orphaned_media.Command.handle` (the `dry_run` branch has already returned). KEEP the
  early return — dropping it would make `--dry-run` reclaim staging files and break
  `test_dry_run_is_nondestructive`.

  D-8: `test_sweep_orphaned_media.py` has TWO classes —
  `TestSweepOrphanedMedia::test_orphaned_file_is_deleted` (NOT test_orphan_file_deleted),
  `::test_referenced_file_is_kept` (NOT test_ad_referenced_file_survives),
  `::test_seed_subdir_excluded` (NOT test_seed_dir_is_excluded) — and
  `TestSweepLockScope::test_delete_photo_called_within_lock_scope`, a class the source plan omits.
  D-18: the bot error surface is `handlers/ad_create/submit.py::process_preview`;
  `preview.py::show_preview` is a non-router render helper.
  Do NOT merge AD-003 (phase 05): no refcounting, no removal of `copy_ad`'s storage-key reuse,
  no change to `delete_adimage_files_on_delete`, and no special-casing of the dedup-hit file
  that stays in `staging/` for the TTL to reclaim.
  NO MIGRATION. `media/0001_initial.py` is the only migration in that directory and nothing
  schema-level changes.

description: >
  submit_ad promotes staged files to permanent MEDIA_ROOT BEFORE opening its
  transaction.atomic(), then inserts AdImage rows inside that transaction, and never takes
  AdvisoryLockId.SWEEP_ORPHANED_MEDIA. A concurrent sweep_orphaned_media takes a point-in-time
  snapshot of referenced keys and unlinks on_disk-minus-referenced across the whole os.walk
  with no re-check, so a promoted file whose row is not yet committed is classified as an
  orphan and deleted. Apply Option A-prime so the file is invisible to _walk_media_files until
  its row commits, and fix the unconditional key rewrite that lets a reaped staged file be
  published as a dangling AdImage reference.

goals:
  - eliminate the promote-before-row-commit window by construction, not by narrowing it
  - close interleaving B: no AdImage row may ever reference a file that is not on disk
  - convert a photo-less publication into a RECOVERABLE seller message
  - keep AdImage content dedup (SHA-256) working under deferred promotion
  - do not introduce unbounded growth: files left behind stay in staging/ and die to the TTL
  - keep the TX-then-FS convention for every deletion, including the new promotion move
  - leave AD-003 (phase 05) untouched and add no migration

files:
  - path: src/backend/apps/media/services/filesystem.py
    scope: |
      DELETE `move_staging_to_permanent` and REPLACE it with two single-responsibility
      functions (rule 4):
        * `plan_staging_promotion(photos) -> list[str]` — PURE. For every key field
          (`storage_key`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`) that carries
          `STAGING_PREFIX`: existence-check the file under `MEDIA_ROOT`; RAISE
          `FileNotFoundError` NAMING THE KEY if absent; otherwise rewrite the field to its
          permanent form (prefix stripped) in place. Returns the deduplicated list of
          permanent keys to move. Fields without the staging prefix are untouched (seed data,
          web-edit fixtures). It performs NO filesystem mutation — no move, no write, no mkdir.
        * `promote_media_files(keys) -> None` — the filesystem move: `os.replace` from
          `MEDIA_ROOT/staging/<key>` to `MEDIA_ROOT/<key>`, with the existing EXDEV ->
          `shutil.move` fallback and a non-EXDEV re-raise. It carries a PER-KEY
          `try`/`except` that LOGS AND CONTINUES: it runs post-commit, so one failure must not
          abort the rest and must never propagate into the caller (mirror the shipped
          convention in `apps/media/signals.py`). A post-commit raise would be a lie — the row
          is already committed. It needs NO containment assertion (unlike `delete_photo`,
          which takes operator-supplied keys): its keys are generated internally and were just
          prefix-stripped.
    targets:
      - { type: function, name: move_staging_to_permanent }   # DELETE
      - { type: function, name: plan_staging_promotion }       # ADD
      - { type: function, name: promote_media_files }          # ADD
      - { type: function, name: delete_photo }                 # REFERENCE ONLY
      - { type: module,   name: filesystem }                   # module docstring
      - { type: constant, name: STAGING_SUBDIR }               # UNCHANGED
      - { type: constant, name: STAGING_PREFIX }               # UNCHANGED
      - { type: constant, name: KEY_FORMAT_REGEX }             # UNCHANGED
    semantic_anchors: {}
  - path: src/backend/apps/media/services/__init__.py
    scope: |
      Remove the `move_staging_to_permanent` entry from the import list and from `__all__`;
      add `plan_staging_promotion` and `promote_media_files` to both, keeping the existing
      alphabetical order of `__all__`.
    targets:
      - { type: constant, name: __all__ }
    semantic_anchors: {}
  - path: src/backend/apps/ads/services/images.py
    scope: |
      `AdImageService.create_or_skip` gains ONE optional keyword `sha256: str | None = None`,
      and the body becomes:
          digest = sha256 if sha256 is not None else cls._compute_sha256(image)
      with `AdImage.objects.create(..., sha256=digest, ...)` otherwise unchanged. Document the
      parameter in the docstring, including WHY it exists (under deferred promotion the bytes
      are not at the row's key).
    targets:
      - { type: method, name: AdImageService.create_or_skip }
      - { type: method, name: AdImageService._compute_sha256 }   # REFERENCE ONLY
    semantic_anchors: {}
  - path: src/backend/apps/ads/services/submission.py
    scope: |
      `submit_ad`, in this order:
        1. PRE-FLIGHT — for each photo whose `storage_key` carries `STAGING_PREFIX`, assert the
           file resolves under `MEDIA_ROOT`. Missing -> return
           `(False, [_("One of your photos is no longer available. Please upload it again.")])`
           BEFORE any I/O and before the transaction. This is what makes the thumbnail loop's
           bare `except Exception` structural: by construction "file missing" can no longer be
           what that broad catch swallows, so it covers GENERATION failures only and
           `test_thumbnails_null_on_generation_failure` stays green unchanged. ~4 lines.
        2. THUMBNAIL LOOP — unchanged position (still before the transaction). Leave the broad
           `except` clause alone; do NOT narrow it (that is a separate, unrequested change).
        3. CAPTURE the staging storage keys into a local list (needed in step 6 for hashing).
        4. `plan_staging_promotion(input.photos)` — still OUTSIDE the atomic block, which is
           now correct for a DIFFERENT reason: it is pure key rewriting plus validation, with
           no filesystem mutation. The existing comment that says the promotion must happen
           BEFORE the transaction is FALSE under A-prime and must be corrected (see the
           documentation deliverable).
        5. `with transaction.atomic():` — otherwise UNCHANGED, including the
           `Ad.DoesNotExist` early return, the `create_or_skip` loop and the `auto_moderate`
           delegation. ONE placement constraint: register `transaction.on_commit` INSIDE the
           atomic, AFTER the `create_or_skip` loop and AFTER the `Ad.DoesNotExist` return, so a
           missing ad schedules no promotion. Its position relative to the `auto_moderate`
           delegation is free.
        6. Hash the CAPTURED STAGING keys with
           `FileHashService.calculate_sha256(<staging path>)` and pass the digest to
           `create_or_skip(..., sha256=...)`. Under deferred promotion
           `_compute_sha256(permanent_key)` finds nothing, returns `""`, and the existing
           `if digest:` guard SILENTLY DISABLES content dedup for every submission. This
           override is MANDATORY, not optional.
        7. `transaction.on_commit(<callable that calls promote_media_files(permanent_keys)>)`.
           Bind the key list into the callback's closure explicitly (default argument or
           `functools.partial`) so no late-binding trap is possible.
      NO advisory lock is added to `submit_ad`; `AdvisoryLockId` is untouched.
      `auto_moderate` is imported FUNCTION-LOCALLY in this module, so the only valid patch
      target for any test that hooks it is `apps.moderation.services.auto_moderation.auto_moderate`
      (patching `submission.auto_moderate` will not intercept it).
    targets:
      - { type: function, name: submit_ad }
    semantic_anchors:
      replace_in_body:
        old: 'move_staging_to_permanent(input.photos)'
        new: 'plan_staging_promotion(input.photos)'
      insert_after:
        type: comment
        value: "Promote staging files to permanent storage BEFORE the transaction"   # the comment that must be corrected, not kept
  - path: src/backend/apps/media/management/commands/sweep_orphaned_media.py
    scope: |
      TWO changes only, both non-functional:
        * DELETE the unreachable `if not dry_run:` guard around the `_reclaim_stale_staging`
          call in `Command.handle`. KEEP the call and KEEP the early `return` in the `dry_run`
          branch — that return is load-bearing (`test_dry_run_is_nondestructive`).
        * Docstring updates ONLY: the module docstring, the `_walk_media_files` docstring and
          the `_reclaim_stale_staging` docstring must record the EXTENDED meaning of
          `staging/` — it now holds in-flight uploads AND files awaiting post-commit promotion,
          and a file may briefly belong to a committed `AdImage` row, which the 2 h mtime TTL
          is what bounds. This is the "directory contract" phases 07/13 extend: a
          DOCUMENTATION change, not a structural one.
      NO new exclusion in `_walk_media_files` (`staging/` is already skipped) and NO new
      reclamation policy in `_reclaim_stale_staging`.
    targets:
      - { type: function,  name: _walk_media_files }
      - { type: function,  name: _collect_referenced_keys }   # REFERENCE ONLY
      - { type: function,  name: _reclaim_stale_staging }
      - { type: method,    name: Command.handle }
      - { type: constant,  name: _STAGING_TTL_SECONDS }       # UNCHANGED (BLOCK 6 owns it)
      - { type: constant,  name: _SEED_SUBDIR }               # UNCHANGED
    semantic_anchors: {}
  - path: src/backend/apps/media/tests/test_filesystem.py
    scope: |
      Split `TestMoveStagingToPermanent` into `TestPlanStagingPromotion` and
      `TestPromoteMediaFiles` and carry the existing cases across:
        * -> `TestPlanStagingPromotion`: `test_strips_staging_prefix_from_all_fields`,
          `test_leaves_non_staging_keys_untouched`, `test_multiple_photos_processed`, and the
          INVERTED missing-file case.
        * -> `TestPromoteMediaFiles` VERBATIM: `test_exdev_falls_back_to_shutil_move` and
          `test_non_exdev_oserror_reraises` (the latter already asserts the OPPOSITE contract
          and is the reason the missing-file case is the lone violation, not the rule).
      Add a case for `promote_media_files`' per-key log-and-continue: one key whose `os.replace`
      raises non-EXDEV must not abort the remaining keys and must not propagate.
    targets:
      - { type: class, name: TestMoveStagingToPermanent }        # SPLIT
      - { type: class, name: TestPlanStagingPromotion }          # ADD
      - { type: class, name: TestPromoteMediaFiles }             # ADD
    semantic_anchors: {}
  - path: src/telegram_bot/tests/test_save_photo_integration.py
    scope: >
      The concurrency regression test and the interleaving-B end-to-end test live here, next
      to the class they extend. The class is `pytestmark = [django_db(transaction=True),
      integration, concurrent]`, so `transaction.on_commit` DOES fire inside `submit_ad`.
    targets:
      - { type: class, name: TestSubmitAdStagingMove }
    semantic_anchors: {}
  - path: src/backend/apps/ads/tests/test_submission.py
    scope: >
      Home of the interleaving-B end-to-end test if it is written against `submit_ad` outside
      the `transaction=True` bot class. Locate the existing `submit_ad` cases by symbol; if
      the class's `django_db` mode prevents observing the pre-flight return, give the new test
      its own `transaction=True` class rather than converting an existing one.
    targets: []
    semantic_anchors: {}
  - path: src/backend/apps/ads/tests/test_ad_image_service.py
    scope: >
      The unit home for the `sha256=` override. NOTE: the source plan names
      `test_ad_image_dedup.py` — THAT FILE DOES NOT EXIST. The real class is
      `TestAdImageServiceCreateOrSkip`. The END-TO-END dedup control belongs in the bot test
      module instead (it must exercise `submit_ad`, not `create_or_skip` in isolation).
    targets:
      - { type: class, name: TestAdImageServiceCreateOrSkip }
    semantic_anchors: {}
  - path: src/backend/apps/media/tests/test_sweep_orphaned_media.py
    scope: |
      UNCHANGED. `test_stale_staging_file_reclaimed` IS the reclamation control under A-prime:
      a `staging/` file inside the TTL survives the sweep, which is exactly the property the
      post-commit gap relies on. Do not add a second reclamation test and do not edit any
      existing case.
    targets:
      - { type: class, name: TestSweepOrphanedMedia }
      - { type: class, name: TestSweepLockScope }
    semantic_anchors: {}
  - path: src/backend/apps/core/tests/test_sweep_lock_structure.py
    scope: |
      UNTOUCHED. Q8 decided neither batching nor `session=True`, so the `session is False`
      entry for `sweep_orphaned_media` remains correct and this file gains no amendment.
    targets: []
    semantic_anchors: {}
  - path: src/telegram_bot/services/ad_data/media.py
    scope: |
      CORRECT A MIS-ATTRIBUTION IN THE `touch_staging_photos` DOCSTRING. It states that the
      `move_staging_to_permanent` silent-skip defect "is phase 07's". That becomes wrong the
      moment this block lands and re-derives the wrong owner for a future reader. Correct it
      in THIS commit. Docstring only — no behavioural change to `touch_staging_photos`, whose
      fail-soft `FileNotFoundError -> continue` is correct for its own purpose (there is
      nothing left to protect).
    targets:
      - { type: function, name: touch_staging_photos }
    semantic_anchors: {}
  - path: docs/02-database/db-retention.md
    scope: |
      EXTEND the existing `staging/` paragraph (the one that names
      `sweep_orphaned_media._STAGING_TTL_SECONDS`, mtime, and `touch_staging_photos`) to record
      that `staging/` also holds files awaiting post-commit promotion and that the TTL is what
      bounds the gap between a committed `AdImage` row and its promoted file. DO NOT touch the
      "these two commands" session-lock wording in this file.
    targets: []
    semantic_anchors: {}
  # NOT touched: src/backend/apps/core/tests/test_sweep_lock_structure.py;
  #             src/backend/apps/core/enums.py (AdvisoryLockId);
  #             src/backend/apps/core/utils/advisory_lock.py;
  #             src/backend/apps/media/models.py (AdImage) and apps/media/signals.py
  #             (delete_adimage_files_on_delete) — REFERENCE ONLY;
  #             apps/ads/services/copy_service.py storage-key reuse (AD-003, phase 05);
  #             delete_draft's storage_keys; sweep_drafts.py (BLOCK 1 and BLOCK 6 own it);
  #             src/backend/apps/core/utils/scheduler.py;
  #             src/backend/apps/media/migrations/** (no migration);
  #             docs/ops/docker-deployment.md (Q8 leaves its wording accurate);
  #             src/backend/conftest.py; .ai/audit/**; .ai/plans/**.

changes:
  - action: add_code
    description: >
      Apply Q7 = Option A-prime. Replace `move_staging_to_permanent` with the pure
      `plan_staging_promotion` and the post-commit `promote_media_files`; give
      `create_or_skip` the `sha256` override; restructure `submit_ad` into pre-flight ->
      thumbnail loop -> capture staging keys -> pure key rewrite -> unchanged atomic block ->
      `on_commit` promotion. NO new directory, NO new sweep exclusion, NO new reclamation
      policy, NO advisory lock on the submit path.
  - action: edit_code
    description: >
      Delete the unreachable `if not dry_run:` guard in `Command.handle` and keep the early
      return. Remove the `move_staging_to_permanent` re-export from
      `apps/media/services/__init__.py` (import list and `__all__`) and export the two
      replacements in its place.
  - action: rewrite_docstring
    description: >
      Four shipped claims become FALSE with this change and are corrected IN THE SAME COMMIT —
      see the `documentation_deliverable` block below. Per project rule 2 the TESTS bend; the
      docstrings are corrected, not preserved. The docstring is part of the deliverable: a
      reader who inherits "promote before TX => orphans on rollback" as documented intent
      reverts the fix.
  - action: rewrite_test
    description: >
      INVERT, do not delete, the two tests that assert the defect:
      `TestSubmitAdStagingMove::test_submit_ad_rollback_leaves_permanent_orphans` (renamed to
      `test_submit_ad_rollback_leaves_files_in_staging`) and
      `TestMoveStagingToPermanent::test_updates_key_even_if_file_missing` (renamed to match its
      new meaning). `TestSubmitAdStagingMove::test_submit_ad_moves_staging_to_permanent` needs
      its DOCSTRING corrected and NO assertion rewrite.
  - action: add_test
    description: >
      Four new tests, specified in full in `tests_to_add` below: the concurrency regression
      test (RED pre-fix), the interleaving-B end-to-end test, the SHA-256 dedup control, and
      the per-key log-and-continue case for `promote_media_files`.

implementation_sequence:
  - step: 1
    name: Write the four tests FIRST, and prove two of them RED against the untouched tree
    detail: >
      Do this BEFORE any production edit. Four tests:
      (a) `test_files_are_not_promoted_before_the_row_commits` in `TestSubmitAdStagingMove` —
          patch `apps.moderation.services.auto_moderation.auto_moderate` (the symbol is
          imported FUNCTION-LOCALLY inside `submit_ad`, so patching `submission.auto_moderate`
          will not intercept it) with a side effect that inspects the filesystem FROM INSIDE
          the transaction. At that instant the staging original MUST still exist and the
          permanent `photo.jpg` MUST NOT. It must be RED pre-fix: today the promotion happens
          before the atomic block, so `photo.jpg` already exists and the assertion fails.
          This is the direct guard for 03-DB-005 and the block's one mandatory control.
      (b) `test_missing_staged_file_reports_a_recoverable_error` — drive interleaving B end to
          end: stage a photo, delete the staged file, call `submit_ad`, assert it returns
          `(False, [...])` carrying the new recoverable message, that NO `AdImage` row was
          created, and that no key was rewritten.
      (c) INVERT `TestMoveStagingToPermanent::test_updates_key_even_if_file_missing` (renamed)
          to assert that `FileNotFoundError` is raised AND that the storage key is STILL
          `"staging/missing.jpg"`. It must be RED pre-fix, because today no exception is
          raised and the key is rewritten to `"missing.jpg"`. Do NOT delete it.
      (d) SHA-256 dedup survives deferred promotion — assert that after a `submit_ad` the
          stored `AdImage.sha256` equals the digest of the STAGED bytes and is non-empty, and
          that a second submission of identical bytes still resolves to the SAME row. This is
          the control for accepted risk 2: it must FAIL if the `sha256=` override is removed
          from the `submit_ad` call site. Demonstrate that by temporarily deleting the
          override, showing RED, and restoring it.
      Then RUN the suite and RECORD, in the commit message, that (a) and (c) are RED against
      the pre-fix code and that (b) and (d) fail for their own (pre-fix) reasons. A control
      that is never seen red proves nothing.
  - step: 2
    name: Rewrite apps/media/services/filesystem.py and its re-export
    detail: >
      Delete `move_staging_to_permanent`; add `plan_staging_promotion` (pure) and
      `promote_media_files` (log-and-continue per key). Update the module docstring. Leave
      `STAGING_SUBDIR`, `STAGING_PREFIX`, `KEY_FORMAT_REGEX` and `delete_photo` alone. Update
      `apps/media/services/__init__.py` (import list and `__all__`).
  - step: 3
    name: Give AdImageService.create_or_skip the sha256 override
    detail: >
      One optional keyword `sha256: str | None = None`; body becomes
      `digest = sha256 if sha256 is not None else cls._compute_sha256(image)`. Document why it
      exists. No other signature, query or return-path change.
  - step: 4
    name: Restructure submit_ad
    detail: >
      In order: pre-flight existence check, thumbnail loop (unchanged), capture staging keys,
      `plan_staging_promotion` (still outside the atomic, now because it is PURE), the
      unchanged atomic block with the `on_commit` registration placed after the
      `create_or_skip` loop and after the `Ad.DoesNotExist` return, and the digest passed as
      `create_or_skip(..., sha256=...)`. Add the `FileNotFoundError` catch that returns the
      recoverable message BEFORE the transaction is opened. No advisory lock.
  - step: 5
    name: Apply the four documentation corrections with the code
    detail: >
      The corrected `submit_ad` comment, the `filesystem.py` module docstring (which inherits
      the "the caller must run this before any transaction.atomic()" claim that is now false),
      the `sweep_orphaned_media` docstrings, the `touch_staging_photos` mis-attribution, and
      the `TestSubmitAdStagingMove` class docstring. See `documentation_deliverable`.
  - step: 6
    name: "sweep_orphaned_media — delete the dead guard, docstrings only otherwise"
    detail: >
      Remove the unreachable `if not dry_run:` guard; keep the early return; update the module,
      `_walk_media_files` and `_reclaim_stale_staging` docstrings for the extended `staging/`
      meaning. `_STAGING_TTL_SECONDS` is BLOCK 6's and stays as it is.
  - step: 7
    name: i18n — append the new msgid
    detail: >
      One new user-visible string, `"One of your photos is no longer available. Please upload
      it again."` Add it to the `ru` and `bs` catalogs with NON-EMPTY `msgstr`; `en` MAY stay
      empty (the msgid is English). APPEND ONLY — these files are shared with phase 14 and
      another phase may be editing them. `test_i18n_completeness.py` gates this; the catalogs
      are recompiled automatically at container start, so no manual `compilemessages`.
  - step: 8
    name: Update db-retention.md, then run the gates
    detail: >
      Extend the `staging/` paragraph only. Then run lint, typecheck and the exact Docker gate
      commands in `acceptance_criteria` below. Do NOT run `test-recreate` — no migration was
      generated.
  - step: 9
    name: Commit with explicit staging
    detail: >
      Stage the EXPLICIT paths listed above. Never `git add -A`, `git add .`, or `git commit -a`
      — the tree is dirty by design and other phases commit concurrently. Watch for CRLF
      damage: this phase already had an Implementor corrupt a file with `Set-Content`. Do not
      run `git reset`, `checkout`, `stash`, or `clean`.

architectural_constraints:
  - "`apps.*` code must NEVER import `telegram_bot.*`. The dependency runs one way only."
  - >
    The `transaction.on_commit` callback is registered INSIDE the `with transaction.atomic():`
    block and AFTER both the `create_or_skip` loop AND the `Ad.DoesNotExist` early return, so a
    missing ad schedules no promotion. Its position relative to the `auto_moderate` delegation
    is free.
  - >
    `promote_media_files` runs POST-COMMIT and therefore MUST log and continue rather than
    raise: a per-key `try`/`except` around the move, never a bare propagate. The row is already
    committed, so an exception crossing back into the caller would be a lie.
  - "`plan_staging_promotion` is PURE and must perform NO filesystem mutation — no move, no write, no mkdir."
  - >
    `plan_staging_promotion` RAISES `FileNotFoundError` naming the key when a staged file is
    absent, and rewrites NO key in that case. `submit_ad` is the single place that converts that
    into a recoverable seller message.
  - "NO advisory lock is added to `submit_ad`. `AdvisoryLockId` is untouched — phase 03 allocates no new member."
  - "`test_sweep_lock_structure.py` is UNTOUCHED; `sweep_orphaned_media` is NOT added to `_SESSION_SCOPED_BATCHERS`."
  - >
    NO migration. `apps/media/migrations/` keeps only `0001_initial.py`. Nothing schema-level
    changes; the row already stores a permanent key.
  - >
    Locale files are APPENDED only, never re-sorted or rewritten wholesale (they are shared
    with phase 14). `ru` and `bs` `msgstr` MUST be non-empty; `en` MAY be empty.
  - "`logger` is never `print()` (rule 12). All code, comments, docstrings, log messages and docs are in clear English (rule 1)."
  - >
    Every `with transaction.atomic():` this block touches KEEPS the project's established
    pyright suppression comment on that line. Do not drop it, and do not add a second one.
  - "No new dependency. No refcounting and no `AD-003` content — `copy_service.py`'s storage-key reuse and `delete_adimage_files_on_delete` are unchanged."
  - >
    No test may assert on a source line, on a log string's exact wording, or on a variable's
    absence. Behavioural and runtime-spy oracles only. (The one logging test permitted asserts
    that an ERROR/WARNING record EXISTS and that a later key still moved — not the message.)
  - "Constants stay `StrEnum`/module constants. No plain-string or dict constant tables (rule 10)."

must_keep_passing_unchanged:
  - "`src/backend/apps/core/tests/test_sweep_lock_structure.py` — the WHOLE FILE, byte-identical."
  - "`src/backend/apps/media/tests/test_sweep_orphaned_media.py` — the WHOLE FILE, including `TestSweepOrphanedMedia::test_orphaned_file_is_deleted`, `::test_referenced_file_is_kept`, `::test_seed_subdir_excluded`, `::test_staging_file_survives_sweep`, `::test_stale_staging_file_reclaimed`, `::test_fresh_staging_file_preserved`, `::test_dry_run_is_nondestructive`, `::test_delete_photo_routing`, and `TestSweepLockScope::test_delete_photo_called_within_lock_scope` (D-8 names)."
  - "`src/backend/apps/ads/tests/test_ad_image_service.py::TestAdImageServiceCreateOrSkip` — all four existing cases."
  - "`src/telegram_bot/tests/test_save_photo_integration.py::TestSubmitAdStagingMove::test_submit_ad_moves_staging_to_permanent` — every assertion, unchanged; docstring only."
  - "`src/backend/apps/ads/tests/test_submission.py::…::test_thumbnails_null_on_generation_failure` — the pre-flight check is what keeps it green; do not narrow the thumbnail loop's `except`."
  - "`TestSavePhotoThumbnailsIntegration` and `src/backend/apps/media/tests/test_thumbnail_integration.py` — its `create_or_skip` call site writes the bytes AT the row key, so it needs no `sha256=` override and must be unchanged."
  - "`src/backend/apps/media/tests/test_filesystem.py::TestMoveStagingToPermanent::test_non_exdev_oserror_reraises` — carried into `TestPromoteMediaFiles` VERBATIM, assertions included."
  - "`src/backend/apps/media/tests/test_filesystem.py::TestDeletePhoto` and every other `filesystem.py` case."
  - "`docs/ops/docker-deployment.md` — unchanged; its \"these two commands\" wording stays accurate under Q8."

tests_to_add:
  - name: test_files_are_not_promoted_before_the_row_commits
    file: src/telegram_bot/tests/test_save_photo_integration.py
    target_class: TestSubmitAdStagingMove
    purpose: "Direct guard for 03-DB-005. RED pre-fix."
    must_be_red_before_any_production_edit: true
    notes: >
      Patch `apps.moderation.services.auto_moderation.auto_moderate` with a side effect that
      asserts, from inside the still-open transaction, that the staging original still exists
      and that the permanent `photo.jpg` does not. Force the interleaving with this hook — never
      with sleeps.
  - name: test_missing_staged_file_reports_a_recoverable_error
    file: src/backend/apps/ads/tests/test_submission.py
    purpose: >
      Interleaving B end to end through `submit_ad`. Assert `(False, [...])` carrying the new
      recoverable message, NO `AdImage` row, and no rewritten key.
  - name: "test_raises_and_leaves_key_untouched_when_file_missing (INVERTED from test_updates_key_even_if_file_missing)"
    file: src/backend/apps/media/tests/test_filesystem.py
    target_class: TestPlanStagingPromotion
    purpose: "Assert `FileNotFoundError` is raised AND the key is still `\"staging/missing.jpg\"`. RED pre-fix."
    must_be_red_before_any_production_edit: true
  - name: test_dedup_survives_deferred_promotion
    file: src/telegram_bot/tests/test_save_photo_integration.py
    purpose: >
      The control for accepted risk 2. The stored `AdImage.sha256` equals the digest of the
      STAGED bytes and is non-empty, and a second submission of identical bytes resolves to the
      SAME row. Must FAIL if the `sha256=` override is removed from the `submit_ad` call site —
      demonstrate that by temporarily deleting the override, showing RED, and restoring it.
  - name: test_one_failed_key_does_not_abort_the_remaining_promotions
    file: src/backend/apps/media/tests/test_filesystem.py
    target_class: TestPromoteMediaFiles
    purpose: >
      One key whose `os.replace` raises a non-EXDEV `OSError` is logged and skipped; the
      remaining keys still move; nothing propagates to the caller.

documentation_deliverable:
  - >
    `submit_ad`'s comment that reads "Promote staging files to permanent storage BEFORE the
    transaction" is FALSE under A-prime and must be replaced. It must now say that key
    rewriting happens before the transaction because `plan_staging_promotion` is pure, and
    that the file move happens AFTER the row commits.
  - >
    `filesystem.py`'s module docstring, which currently carries `move_staging_to_permanent`'s
    claim that "the caller is responsible for running this before any `transaction.atomic()`
    block so that a DB rollback leaves the permanent files as unreferenced orphans". The
    function is deleted; the new module docstring must state the A-prime contract: promotion
    happens AFTER the owning row commits via `transaction.on_commit`; a missing staged file is
    an ERROR, not a skip; a rollback leaves the file in `staging/` for TTL reclamation.
  - >
    `sweep_orphaned_media.py`: the module docstring, the `_walk_media_files` docstring and the
    `_reclaim_stale_staging` docstring must record the EXTENDED `staging/` lifecycle — in-flight
    uploads AND files awaiting post-commit promotion — and note that a file may briefly belong
    to a committed `AdImage` row, which the 2 h mtime TTL bounds.
  - >
    `telegram_bot/services/ad_data/media.py::touch_staging_photos`: its docstring mis-attributes
    the silent-skip defect to "phase 07". That becomes wrong the moment this block lands.
    Correct the attribution in THIS commit.
  - "`TestSubmitAdStagingMove`'s class docstring must state the corrected contract, not the defect."
  - "`docs/02-database/db-retention.md`: extend the `staging/` paragraph for the post-commit promotion gap. Do NOT touch the \"these two commands\" session-lock wording."
  - "i18n: the new msgid, appended to `ru` and `bs` (non-empty) and `en` (may stay empty)."

commit_message:
  - "Conventional Commit, scope `media`, referencing the finding — e.g. `fix(media): promote staged uploads in on_commit (03-DB-005)`. Match the style of the surrounding commits."
  - "State the two closed decisions: Q7 = Option A-prime (reuse `staging/` as the sweep-excluded holding area, promote in `transaction.on_commit`, NO new directory, NO new sweep exclusion, NO new reclamation policy) and Q8 = neither batching nor `session=True` (the sweep keeps one transaction-scoped lock across the whole walk; `test_sweep_lock_structure.py` untouched)."
  - "State the key-rewrite contract change: a key is rewritten IFF the file was actually moved; a missing staged file RAISES and `submit_ad` returns a recoverable seller message instead of publishing a photo-less ad."
  - "State the dedup obligation: `create_or_skip` gained an explicit `sha256=` and every call site whose bytes are not at the row key must pass it, or content dedup silently no-ops."
  - "Record that the two defect-asserting tests were INVERTED (not deleted) and that the concurrency regression test was demonstrated RED against the pre-fix code."
  - "Name the accepted risks carried forward (see `accepted_risks`), especially the crash-between-COMMIT-and-move window and the dependency on `sha256=` at every call site."

accepted_risks:
  - >
    (1) CRASH BETWEEN COMMIT AND THE `on_commit` MOVE leaves a committed row whose file is still
    in `staging/`; the TTL reclaims it, making the row permanently dangling. It requires a
    process kill in a sub-millisecond window — strictly narrower than today's guarantee, which
    is every submission for the length of a multi-minute walk. NO mitigation is proposed;
    deleting the row post-commit would be worse. Record it; do not engineer around it.
  - >
    (2) DEDUP NOW DEPENDS ON EVERY CALL SITE PASSING `sha256=` when the bytes are not at the row
    key. Miss one and it silently no-ops (`""` -> the existing `if digest:` guard). Owner: the
    mandatory `test_dedup_survives_deferred_promotion` control.
  - >
    (3) THE SWEEP KEEPS ONE TRANSACTION AND ONE LOCK ACROSS THE WHOLE WALK. Unchanged from
    today and DELIBERATELY unchanged; mixing lock disciplines is rejected under Q8. Record it.
  - >
    (4) PROMOTED FILES INHERIT THE STAGING MTIME (`os.replace` preserves it). Harmless today; a
    trap for any future mtime-keyed retention policy. Record it in the code where a reader would
    look.
  - >
    (5) INTERLEAVING B's TRIGGER IS NARROWED, NOT ELIMINATED, BY BLOCK 6. Only `photos.py` and
    `submit.py` call `touch_staging_photos`; `category.py`, `city.py`, `price.py` and `text.py`
    touch only the row, so a seller who uploads and then spends more than 2 h across those
    steps still has files reaped. Owner: BLOCK 6's Q5 coverage gap, or phase 07. BLOCK 8 owns
    only the consequence it fixes: the outcome is now a recoverable message instead of a
    silent photo-less publication. Do NOT widen `touch_staging_photos`'s call sites here.
  - "(6) The `media.py` mis-attribution comment is corrected here, in this commit."
  - >
    (7) `_SESSION_SCOPED_BATCHERS` STAYS AN EXCEPTION LIST. Replacing it with a positive
    per-entry `(session, in_atomic)` table is a NAMED FOLLOW-UP FOR THE COORDINATOR and is
    explicitly NOT BLOCK 8 WORK: BLOCK 7 authored that set at this HEAD, and editing it would
    collide on a shared artefact for zero correctness gain. Record it in the commit message;
    do not open the file.

acceptance_criteria:
  - "`test_files_are_not_promoted_before_the_row_commits` was demonstrated RED against the pre-fix code and is GREEN after, and the RED evidence is recorded in the commit message."
  - "The inverted missing-file test was demonstrated RED before the production edit and is GREEN after; it asserts BOTH that `FileNotFoundError` is raised and that the key is still `\"staging/missing.jpg\"`."
  - "No `AdImage` row can ever be committed for a file that is not on disk: `submit_ad` returns `(False, [<new recoverable message>])` before opening the transaction, creating no row and rewriting no key."
  - "`plan_staging_promotion` is pure — it rewrites key fields in place and performs no filesystem mutation; `promote_media_files` performs every move."
  - "`promote_media_files` never propagates: one failing key is logged and skipped, the rest still move (covered by `test_one_failed_key_does_not_abort_the_remaining_promotions`)."
  - "The `on_commit` callback is registered inside the atomic block and after both the `create_or_skip` loop and the `Ad.DoesNotExist` return."
  - "The `AdImage` row is written with the PERMANENT key, and content dedup still works: `test_dedup_survives_deferred_promotion` is GREEN, and is RED if the `sha256=` override is removed from the `submit_ad` call site."
  - "A rolled-back `submit_ad` leaves NO file in permanent storage: permanent `photo.jpg` does not exist, the staging original and its thumbnails still exist, `AdImage` count is 0, and the ad stays DRAFT."
  - "A committed `submit_ad` leaves the file permanent and every thumbnail key permanent — `test_submit_ad_moves_staging_to_permanent` needed no assertion rewrite and still passes."
  - "`test_dry_run_is_nondestructive` is GREEN (the early `return` was kept) and the unreachable `if not dry_run:` guard is gone from `Command.handle`."
  - "A file left in `staging/` by a rollback is reclaimed by the existing TTL — `TestSweepOrphanedMedia::test_stale_staging_file_reclaimed` is GREEN and unmodified. No new reclamation policy was written."
  - "`test_sweep_lock_structure.py` is byte-identical; `sweep_orphaned_media` was NOT added to `_SESSION_SCOPED_BATCHERS`; `docs/ops/docker-deployment.md` and the \"these two commands\" wording in `docs/02-database/db-retention.md` are unchanged."
  - "Every `delete_photo` call still happens inside the `SWEEP_ORPHANED_MEDIA` lock scope — `TestSweepLockScope::test_delete_photo_called_within_lock_scope` is GREEN."
  - "No migration was created; `apps/media/migrations/` still contains only `0001_initial.py`."
  - "All six documentation corrections above are present in the SAME commit as the code that falsified them."
  - "The new msgid is present in the `ru` and `bs` catalogs with non-empty `msgstr` (appended only, not re-sorted) and `test_i18n_completeness.py` is GREEN."
  - "`AdvisoryLockId` gained no new member; no `apps.*` module imports `telegram_bot.*`; `copy_service.py`'s storage-key reuse and `delete_adimage_files_on_delete` are unchanged (AD-003 untouched)."
  - "`uv run ruff check src/` exits 0 and `uv run basedpyright src/` reports 0 errors."
  - >
    THE DOCKER GATE (tests run ONLY through Docker — local `uv run pytest` fails, there is no DB
    on `localhost:5432`):

        $dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
        docker ps --filter "name=mko-bazuna-test-db-"
        # if the DB container is absent:
        $dc up -d db

        # RED/GREEN step 1 evidence (pre-fix) and the post-fix gate:
        $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests/test_filesystem.py src/backend/apps/media/tests/test_sweep_orphaned_media.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/telegram_bot/tests/test_save_photo_integration.py src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_ad_image_service.py" test

        .\Makefile.ps1 test

    Do NOT run `.\Makefile.ps1 test-recreate` — no migration was generated. The full suite
    expects EXACTLY ONE failure, the known pre-existing
    `test_search_slo.py::…::test_search_at_seed_volume_meets_slo`, which also fails on the
    anchor commit. Any other failure is BLOCK 8's.
  - >
    ENVIRONMENT NOTES the Implementor must honour: `PYTEST_OPTS` is UNQUOTED in
    `docker/entrypoint-test.sh`, so each token word-splits on spaces — bare file paths and
    single-token flags work, quoted multi-token values do NOT; setting `PYTEST_OPTS` also
    REPLACES the defaults, so the targeted run loses `--reuse-db` and xdist parallelism. NEVER
    use `--override-ini=addopts=` — it strips `--import-mode=importlib`. `docker compose run` can
    abort with `dependency failed to start: … is unhealthy` BEFORE pytest runs: wait ~45 s and
    retry. Known pre-existing teardown-flush flakiness: `ExchangeRateNotFoundError`,
    `test_bulk_delete_skips_hard_deleted_row` seeing leftover `Ad` rows, and
    `test_mko_bazuna is being accessed by other users`. `head` and `tail` do not work in
    PowerShell and `rg` is unavailable. The tree is dirty BY DESIGN and other phases commit
    concurrently: never `git reset`, `git checkout`, `git stash`, `git clean`, `git add -A`,
    `git add .` or `git commit -a`; stage EXPLICIT paths and watch for CRLF damage.
```

**Planner addendum (post-Researcher). Resolutions that supersede the source plan's BLOCK 8
body. The Implementor task above is the authoritative specification.**

**1. Q7 = Option A′, and it is not the plan's Option A.** The Researcher closed Q7 for a variant
the plan does not list: **reuse `staging/` itself** as the sweep-excluded holding area and
promote in `transaction.on_commit`. **No new directory.** The plan's Option A prices itself at
four costs that are **already paid**: `STAGING_SUBDIR`/`STAGING_PREFIX` exist, `_walk_media_files`
already skips `staging/`, and `_reclaim_stale_staging` already reclaims it on BLOCK 6's mtime
heartbeat. The `6 → 8` hard edge is therefore satisfied **literally** — BLOCK 8 inherits BLOCK 6's
predicate, constant and heartbeat rather than re-deriving a policy against them. The plan's
option-A risk row ("a sweep-excluded subdirectory that nothing reclaims") **cannot fire**, and its
"mandatory reclamation test" resolves to the **existing** `test_stale_staging_file_reclaimed`.
The rollback story also inverts cleanly: a rolled-back submit leaves the file **in `staging/`**
where the existing TTL reclaims it — the same fate as an abandoned upload, already modelled and
tested. **Option C** (locking the submit path on `SWEEP_ORPHANED_MEDIA`) was confronted head-on
and **rejected**: `lock_timeout` is 10 s and the sweep's hold is unbounded and volume-dependent;
the web `ad_edit` caller has no `OperationalError` boundary and would return a raw 500. It trades
guaranteed silent photo-loss for an availability incident on the hottest write path, and it does
not fix B anyway.

**2. The plan's "reclamation test", "dedup-key test" and "no new subdirectory constant" tasks are
CANCELLED**, per §1. `test_stale_staging_file_reclaimed` is the reclamation control. The
**dedup-key test survives and is mandatory** — see §3.

**3. Interleaving B is fixed independently of Q7, by the `setattr` placement, and must NOT be
inherited from BLOCK 6.** B is still reachable after BLOCK 6 (HIGH confidence): only
`handlers/ad_create/photos.py` and `.../submit.py` call `touch_staging_photos`;
`category.py`, `city.py`, `price.py` and `text.py` touch only the row, so a dialog spending more
than 2 h across those steps still loses its files. The contract: **rewrite a key iff the file was
actually moved; a missing staging file raises `FileNotFoundError` naming the key; no key is
rewritten.** **Raise, not skip** — `delete_photo` already classifies `FileNotFoundError` as
terminal, and raising is the only option that preserves the information needed for a
*recoverable* seller message. Skip-silently **is** the defect. `submit_ad` catches it before
opening the transaction and returns a recoverable message — strictly better than today's
`(True, [])`, which publishes an ad with a broken image. The Researcher's §2.3 also makes the
thumbnail loop's bare `except Exception` **structural** rather than narrower: the pre-flight
existence check runs **before** the loop, so "file missing" cannot be what that broad catch
swallows and `test_thumbnails_null_on_generation_failure` stays green unchanged.

**4. Q8 = neither batching nor `session=True`.** The premise that forced `session=True` was
Option B's per-candidate commit releasing the lock early; **under A′ there are no per-candidate
transactions, so the premise is gone.** `sweep_orphaned_media` keeps one read-only snapshot, one
delete loop, one `transaction.atomic()` with `session=False`. It is **not** added to
`_SESSION_SCOPED_BATCHERS`, `test_sweep_lock_structure.py` is **untouched**, and the "these two
commands" wording in `docs/02-database/db-retention.md` and `docs/ops/docker-deployment.md`
**stays as-is**. One discipline, not blended.

**5. The plan is partly stale — four corrections, carried into the task above.**
(a) `test_submit_ad_moves_staging_to_permanent` needs **no assertion rewrite**; the class is
`pytestmark = [django_db(transaction=True), …]`, so `on_commit` **fires** before `submit_ad`
returns and every file-side assertion stays true. Docstring only. (b)
`test_submit_ad_rollback_leaves_permanent_orphans` **asserts the defect** — **invert, do not
delete**. (c) `test_updates_key_even_if_file_missing` **also asserts the defect** — invert, do not
delete; deleting it leaves the unconditional `setattr` completely unguarded, and its sibling
`test_non_exdev_oserror_reraises` already asserts the *opposite* contract, so it is the lone
violation of "rewrite the key iff the file was actually moved". (d) The plan names
`src/backend/apps/ads/tests/test_ad_image_dedup.py` — **that file does not exist**; the real
home is `apps/ads/tests/test_ad_image_service.py::TestAdImageServiceCreateOrSkip`. Locate by
symbol.

**6. The `sha256=` override is MANDATORY, not a nice-to-have.** Under deferred promotion
`AdImageService._compute_sha256(permanent_key)` finds nothing and returns `""`, and the existing
`if digest:` guard then **silently disables content dedup for every submission**. This is the
concrete form the plan's `AdImage.save()` SHA-256 risk row takes, and
`test_dedup_survives_deferred_promotion` is its control. **No refcounting, no `AD-003`.** On a
dedup **hit** the staged file stays in `staging/` and the TTL reclaims it — correct, and no worse
than today, where the promoted file becomes a permanent orphan. Do not special-case it.

**7. Dead code: delete the unreachable `if not dry_run:` guard; KEEP the early return.** Dropping
the return would make `--dry-run` reclaim staging files and break `test_dry_run_is_nondestructive`.

**8. Accepted risks — recorded, NOT engineered away.** (1) A crash between COMMIT and the
`on_commit` move leaves a committed row whose file is still in `staging/`; the TTL reclaims it and
the dangling row becomes permanent. It needs a process kill in a sub-millisecond window —
**strictly narrower than today's guarantee**, which is every submission for the length of a
multi-minute walk. No mitigation; deleting the row post-commit would be worse. (2) Dedup now
depends on every call site passing `sha256=` when the bytes are not at the row key — miss one and
it silently no-ops. Owner: the mandatory dedup control. (3) The sweep keeps one transaction and
one lock across the whole walk — unchanged and **deliberately** so. (4) Promoted files inherit the
staging mtime (`os.replace` preserves it) — harmless today, a trap for any future mtime-keyed
retention policy; record it where a reader would look. (5) B's **trigger** is narrowed, not
eliminated, by BLOCK 6 — owner is BLOCK 6's Q5 coverage gap or phase 07; BLOCK 8 owns only the
consequence it fixes (recoverable message instead of silent photo-less publication). (6) The
`media.py` mis-attribution is corrected **in this commit**. (7) `_SESSION_SCOPED_BATCHERS` stays
an exception list — replacing it with a positive per-entry `(session, in_atomic)` table is a
**named follow-up for the coordinator, explicitly not BLOCK 8 work** (BLOCK 7 authored that set
at this HEAD; editing it collides on a shared artefact for zero correctness gain).

**9. One thing left deliberately undecided by the Planner: where the interleaving-B end-to-end
test lives** — `apps/ads/tests/test_submission.py` versus a new class in the bot's
`transaction=True` module. It is behaviourally identical either way, and both files are already
in the file surface and in the gate. The Implementor picks the one whose existing
`django_db` mode lets it observe the pre-flight return without converting an unrelated class, and
records the choice in the commit message.

**Tests required (corrected).**

- *Must be added (all four are specified in full in the task's `tests_to_add`):* the concurrency
  regression test `test_files_are_not_promoted_before_the_row_commits` — force the interleaving
  with a hook, **never with sleeps**, and it must be **RED against the pre-fix code**;
  `test_missing_staged_file_reports_a_recoverable_error`; the dedup control
  `test_dedup_survives_deferred_promotion`; and
  `test_one_failed_key_does_not_abort_the_remaining_promotions`. The plan's separate
  **reclamation test is cancelled** (§1, §2).
- *Must be changed — INVERTED, not deleted:* `TestSubmitAdStagingMove::
  test_submit_ad_rollback_leaves_permanent_orphans` (renamed to
  `test_submit_ad_rollback_leaves_files_in_staging`) and `TestMoveStagingToPermanent::
  test_updates_key_even_if_file_missing`. Both rewrites must state **why the old expectation
  encoded the defect**. The plan's instruction to "rewrite BOTH cases of
  `TestSubmitAdStagingMove`" is **over-stated** — see §5(a).
- *Must keep passing unchanged (exact list in the task's `must_keep_passing_unchanged`):*
  `TestSweepOrphanedMedia::test_seed_subdir_excluded`, `::test_referenced_file_is_kept`,
  `::test_orphaned_file_is_deleted`, `::test_staging_file_survives_sweep`,
  `::test_stale_staging_file_reclaimed`, `::test_fresh_staging_file_preserved`,
  `::test_dry_run_is_nondestructive`, `::test_delete_photo_routing` (actual names, D-8);
  `TestSweepLockScope::test_delete_photo_called_within_lock_scope`; the whole of
  `test_sweep_lock_structure.py`; `TestAdImageServiceCreateOrSkip`; `TestSubmitAdStagingMove::
  test_submit_ad_moves_staging_to_permanent`; `TestSavePhotoThumbnailsIntegration`;
  `test_thumbnail_integration.py`; and `…::test_thumbnails_null_on_generation_failure`.

**Exact gate command (Docker only).** No migration is generated, so `test-recreate` is
**deliberately absent**; the authoritative command list is inside `acceptance_criteria` above.

```powershell
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests/test_filesystem.py src/backend/apps/media/tests/test_sweep_orphaned_media.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/telegram_bot/tests/test_save_photo_integration.py src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_ad_image_service.py" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk (highest):* inverting the two defect-asserting tests but **not** updating the
  `TestSubmitAdStagingMove` class docstring and the `filesystem.py` module docstring, so the next
  reader inherits "promote before TX ⇒ orphans on rollback" as documented intent and reverts the
  fix. **All six documentation corrections are part of the deliverable.**
- *Risk:* shipping the `sha256=` override on `create_or_skip` but **not** passing it from the
  `submit_ad` call site — dedup then silently no-ops for every submission, and no existing test
  sees it. The dedup control is the only guard.
- *Risk:* a crash between COMMIT and the `on_commit` move (§8.1). Accepted; do not engineer.
- *Risk:* `promote_media_files` raising out of its `on_commit` callback, which would surface a
  post-commit failure to the caller as though it were pre-commit. It must log and continue.
- *Risk:* BLOCK 6 also edits `sweep_orphaned_media.py`. Re-read `_STAGING_TTL_SECONDS` and
  `_reclaim_stale_staging` immediately before editing; BLOCK 8 changes **no** constant there.
- *Risk:* dropping the `dry_run` early return along with the dead guard, which breaks
  `test_dry_run_is_nondestructive` and silently makes `--dry-run` destructive.
- *Risk (lower than under the plan's Option A):* the plan's "a deployed Option A leaves files in
  a subdirectory that a rolled-back code version would treat as orphans" rollback hazard **does
  not apply** — A′ introduces no new directory, so a rolled-back code version finds only
  `staging/` files, which it already TTL-reclaims.
- *Rollback:* code and test changes are reversible with no schema change and no data migration.
  A rolled-back tree resumes today's promote-before-`atomic()` behaviour — safe, with the
  original defect, and with any committed-but-unpromoted file reclaimed from `staging/` by the
  existing TTL.

---

### BLOCK 9 — Saved-search alert **delivery-state contract** (`03-DB-007`)

| | |
|---|---|
| **Findings owned** | `03-DB-007` |
| **`depends_on`** | **BLOCK 6**, **BLOCK 8** |
| **Priority** | P3 — latent behind `IMMEDIATE_ALERTS_ENABLED` (default `False`) |
| **`Q9` / `Q10`** | **CLOSED** — decision record `.ai/tmp/block9-context-r.md`; the re-publish call is coordinator-approved |
| **Roster** | **Implementor, Auditor, Researcher, Planner, Validator** |

**The stale draft in this section is WITHDRAWN.** Two of its instructions were unsafe and are
replaced here: the shared **advisory lock** (rejected outright, not merely "insufficient") and
**"nullable with NO backfill"** (that rule ships a mass re-notification on the live, ungated
08:00 UTC digest one day after deploy — see **F-1** below). The Researcher's decision record
`.ai/tmp/block9-context-r.md` is the source of truth for this block; the earlier paste-ready
agent briefs are superseded by it and are deliberately not restated. `delivered_by_immediate_alerts`
never existed in `src/`. Validator stays mandatory: the block lands behind a disabled flag, and
`moderation/tests/test_approve_ad_side_effects.py` is the real gate pin.

**Implementor task.**

```yaml
id: task_03_b09_alert_delivery_state_contract
title: Saved-search alert delivery-state contract (delivered_at marker written by both paths)
priority: medium
depends_on: [BLOCK 6, BLOCK 8]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 9 — Serialise and de-duplicate immediate-alert delivery (03-DB-007); Q9/Q10 as closed in .ai/tmp/block9-context-r.md (§2–§9, implementation shape §6)"

extra_context: |
  Q9 AND Q10 ARE CLOSED. Do not re-open, do not re-derive. Source of record:
  .ai/tmp/block9-context-r.md (Researcher, read-only, HEAD 35441e0). The previous draft's
  advisory-lock option and its "nullable with NO backfill" rule are BOTH WITHDRAWN — see F-1/F-2.

  ANCHOR CORRECTIONS CARRIED FORWARD
  D-5: src/backend/apps/ads/signals.py DOES NOT EXIST. The gate is
  src/backend/apps/moderation/signals.py::deliver_immediate_alerts_on_publish.
  N-2: IMMEDIATE_ALERTS_ENABLED is present in all four .env.*.example templates (false) and in
  ALLOWED_ENV_VARS. Do NOT add a template entry and do NOT claim it is undocumented.
  D-2: DO NOT cite the hash fbbb6cf — it is the scheduler daily-marker commit and never touched
  send_alerts.py. Re-anchor the "do not revert" artefacts by SYMBOL:
  apps.core.utils.scheduler.SchedulerDailyMarker, apps.core.services.scheduler_daily_state,
  send_alerts._DIGEST_AD_LIMIT, send_alerts.Command.handle's loss-window docstring.
  The flag gate: base setting IMMEDIATE_ALERTS_ENABLED (default False), never enable it in this
  block and never change a .env template. Phase 03 allocates NO new AdvisoryLockId.

  THE CLOSED DECISIONS
  1. KEY = (saved_search_id, ad_id) — UNCHANGED, still materialised as uq_saved_search_ad — PLUS a
     new NULLABLE delivered_at. Both FKs are immutable and written once, so the pair is stable
     across edit/archive/re-publish. The row becomes a RECORD of an alert attempt; delivered_at is
     the RECEIPT. The bare key's real question — "was this pair DELIVERED?" — is what is answered.
     uq_saved_search_ad stays a row-level backstop; it arbitrates rows, never messages.
  2. BOTH matchers exclude on delivered_at__isnull=False. find_matching_ads adds it to the
     existing ~Exists subquery; find_matching_saved_searches gains a correlated ~Exists on the
     candidate queryset (explicit ~Exists/OuterRef, never exclude() — multi-valued-relation trap).
     A row with delivered_at IS NULL, or no row at all, stays ELIGIBLE on both paths: that is the
     self-healing retry that replaces today's terminal loss.
  3. RE-PUBLISH IS NOT A NEW ALERT (coordinator-approved). One alert per (saved_search_id, ad_id)
     for the life of the listing, including across re-publish. ad_reactivate is a content-neutral
     status flip (verified in source), so a second alert is a duplicate message about an
     identical listing. original_published_at is NOT used in the key. This is also what US-B11
     already promises. The counter-case — a seller EDITS a live ad, it is re-moderated and
re-published — is DEFERRED to a named follow-up; if wanted, the epoch is a content-revision
      column, NOT Ad.published_at (published_at is reset by ad_reactivate too, so it would
      re-alert the content-neutral case). **The follow-up's named owner is the coordinator /
      Product Owner, recorded as follow-up item (a) in BLOCK 9's acceptance criteria. It was NOT
      reached by the 2026-10-03 Product Owner decision round and remains deferred.**
  4. The marker is written AFTER a successful send. Asymmetry that decides it: loss ≫ duplicate.
     Kill between send_message returning 200 and the UPDATE committing ⇒ ONE bounded,
     self-healing duplicate, visible as a 0-row UPDATE. Writing BEFORE dispatch ⇒ TERMINAL LOSS
     (any dead-letter, exhausted retry, exception or kill marks the pair delivered forever) and it
     has no un-claim hook, because _send_payloads returns None and swallows per-payload outcomes —
     which is phase 09 API-013's surface, not this block's.
  5. NO atomic(), NO advisory_lock in mark_delivered. One conditional statement in autocommit is
     already atomic, and send_message is not transactional, so a transaction would only wrap a
     network call. This also eliminates BLOCK 5's lock_timeout/55P03 exposure inside on_commit.
  6. The mark is ONE conditional statement, no bulk_update, no loop, no queryset abstraction:
       UPDATE saved_search_notifications SET delivered_at = %(sent_at)s
        WHERE saved_search_id = %(ss)s AND ad_id = %(ad)s AND delivered_at IS NULL
       RETURNING id
     True ⇒ this call recorded the delivery. False ⇒ a concurrent call already marked it: log at
     WARNING with the (saved_search_id, ad_id) pair. Idempotent — a second call is a no-op.

  F-1 — THE MIGRATION BACKFILLS delivered_at = sent_at, AND IT MUST.
  The withdrawn draft said "nullable, NO backfill", justified by "NOT NULL DEFAULT false would
  re-notify everyone on first enable". The conclusion was right, the RULE was wrong. With a
  no-backfill column every pre-existing row has delivered_at = NULL; the moment the filter change
  lands, find_matching_ads stops excluding those rows; send_alerts is in DAILY_COMMANDS and fires
  08:00 UTC UNGATED (apps.core.utils.scheduler), so the next run re-notifies EVERY previously
  notified (search, ad) pair to EVERY subscribed buyer — a mass duplicate send one day after
  deploy, with no flag to turn it off. The correct rule is "the backfill must be
  BEHAVIOUR-PRESERVING", not "no backfill". Therefore:
    SavedSearchNotification.objects.filter(delivered_at__isnull=True)
        .update(delivered_at=F("sent_at"))
  sent_at is auto_now_add, so F("sent_at") is a set-based UPDATE — no row loop, safe at any table
  size. Pre-existing D-1/D-2 rows therefore stay suppressed, exactly as today; repairing them is
  an ops decision OUTSIDE this block. The migration's REVERSE IS A NO-OP with a comment: a
  reverse that NULLs the column would re-arm the mass re-notification, so it must not.

  F-2 — TWO shipped tests encode the defect, not one.
  (1) test_records_notification_idempotently monkeypatches _run_send with a no-op and asserts only
  row count == 1. It asserts ROW-level idempotency under a name that claims MESSAGE-level
  idempotency: the second call still SUBMITS the payload, because its own comment ("re-running
  must not double-send") asserts a property the code does not have. Invert it (recorder +
  assert ONE submission), KEEP the row-count assertion, record the rationale in its docstring.
  (2) TestFindMatchingAds::test_excludes_already_notified_ads creates a BARE row (no delivered_at)
  and asserts it is EXCLUDED. Under the correct contract a bare row means "recorded, NOT
  delivered" and must stay collectable. It encodes the defect and must be rewritten: set
  delivered_at, rename to test_excludes_delivered_ads, and add the
  test_includes_recorded_but_undelivered_ads sibling. Per project rule 2 the TEST changes, not
  production code. The audit's list names only (1).
  ALSO: TestImmediateAlertsGate::test_gate_off_does_not_deliver_on_publish is a NO-OP — it never
  calls deliver_immediate_alerts, never uses override_settings, and asserts only a count == 0.
  Leave it byte-identical, do not count it as gate coverage, ADD a real override_settings-based
  gate test beside it, and report E2c as still open with the real pin named.

description: >
  Today a SavedSearchNotification row IS the delivery receipt, so deliver_immediate_alerts
  records before dispatch (a user with no chat_id gets a row and no message, forever), a failed
  send is permanently suppressed by the daily digest, and a re-publish re-alerts because
  find_matching_saved_searches has no exclusion at all. Add a nullable delivered_at receipt to
  the existing (saved_search_id, ad_id) key, make BOTH matchers filter on delivered state, and
  have BOTH paths write the receipt after a successful send — the two halves in one atomic
  change.

goals:
  - a recorded-but-undelivered pair is retried by the next run of the other path (self-healing)
  - a delivered pair is never delivered again, by either path, including across a re-publish
  - a user with no chat_id is never recorded, so the pair stays collectable
  - behaviour-preserving on deploy: pre-existing rows remain suppressed
  - the IMMEDIATE_ALERTS_ENABLED gate, the bounded executor and phase-01 daily idempotency are
    untouched (re-anchored by symbol)

files:
  - path: src/backend/apps/search/services/notification_delivery.py      # NEW MODULE
    targets:
      - { type: class,    name: DeliveryOutcome }   # StrEnum: DELIVERED / SKIPPED_ALREADY_DELIVERED
      - { type: function, name: mark_delivered }
    semantic_anchors: {}
  - path: src/backend/apps/search/models.py
    targets: [{ type: class, name: SavedSearchNotification }]
    semantic_anchors: {}                                # Meta (uq_saved_search_ad,
                                                       # idx_saved_search_notif_sid) UNCHANGED
  - path: src/backend/apps/search/services/alert_query.py
    targets:
      - { type: function, name: find_matching_ads }
      - { type: function, name: find_matching_saved_searches }
      - { type: function, name: record_notifications }
      - { type: module,   name: alert_query }
    semantic_anchors: {}
  - path: src/backend/apps/search/services/immediate_alerts.py
    targets:
      - { type: function, name: deliver_immediate_alerts }
      - { type: method,   name: _send_payloads }        # nested _send
      - { type: module,   name: immediate_alerts }
    semantic_anchors: {}                                # _run_send / _send_payloads FROZEN
  - path: src/backend/apps/search/management/commands/send_alerts.py
    targets:
      - { type: function, name: _collect_alerts }
      - { type: function, name: _send_user_digests }
      - { type: class,    name: Command }               # handle(): lock/transaction shape UNCHANGED
    semantic_anchors: {}
  - path: src/backend/apps/search/migrations/0003_*.py   # AddField delivered_at, null/blank, no default
    targets: [{ type: module, name: migration }]
    semantic_anchors: {}                                # RE-LIST THE DIRECTORY BEFORE GENERATING;
                                                       # take the generated slug, never guess
  - path: src/backend/apps/search/migrations/0004_*.py   # RunPython backfill delivered_at = sent_at
    targets: [{ type: module, name: migration }]        # reverse = NO-OP + comment
    semantic_anchors: {}
  - path: src/backend/apps/search/tests/test_alert_query.py
    targets:
      - { type: class, name: TestRecordNotifications }
      - { type: class, name: TestDeliverImmediateAlerts }
      - { type: class, name: TestFindMatchingSavedSearches }
      - { type: class, name: TestFindMatchingAds }
      - { type: class, name: TestSendAlertsCommand }
      - { type: class, name: TestImmediateAlertsGate }   # byte-identical; a real gate test is ADDED
    semantic_anchors: {}
  - path: src/backend/apps/search/tests/test_send_alerts_daily.py
    targets: [{ type: class, name: TestPerUserDigestCap }]   # the structure reference for D-1/D-2
    semantic_anchors: {}
  - path: src/backend/apps/search/tests/test_alert_delivery.py   # NEW — confirm the name against
    targets: []                                            # the tests directory before creating
    semantic_anchors: {}                                   # (backfill + mark_delivered unit tests)
  # NOT touched: moderation/signals.py (gate only — reference), ads/services/submission.py,
  # _build_payload's contract, build_alert_message(_keyboard), the bot's unsubscribe handler,
  # core/utils/advisory_lock.py, core/enums.py, config/settings/base.py, and the phase-01 daily
  # marker / idempotency work.
  # DOCS OWNED (4): docs/02-database/db-schema.md, docs/02-database/db-indexes.md,
  #   docs/04-user-stories/buyer-stories.md (US-B11), docs/01-spec/architecture-structure.md.
  # docs/01-spec/technical-specification.md — decision O gets NO EDIT (recorded, unchanged: it
  #   stays true, and PII-113 / phase 15 both file against that file).
  # docs/02-database/db-retention.md — OUT OF SCOPE: it has no alert-delivery region and is
  #   already three-way edited by BLOCKs 6/7/8.

changes:
  - action: add_code
    target: src/backend/apps/search/services/notification_delivery.py
    description: >
      New single-responsibility module holding the delivery contract; imports neither
      immediate_alerts nor send_alerts (no cycle). Define DeliveryOutcome(StrEnum) with
      DELIVERED / SKIPPED_ALREADY_DELIVERED — log-record vocabulary ONLY, not a DB column (the
      state is binary-by-nullness; rule 10 is satisfied by the one named function, not by a
      constant nothing branches on). Define
      mark_delivered(saved_search_id: int, ad_id: int, *, sent_at: datetime) -> bool issuing the
      single conditional UPDATE … WHERE saved_search_id AND ad_id AND delivered_at IS NULL
      RETURNING id, in autocommit, with NO transaction.atomic() and NO advisory_lock. True ⇒ this
      call recorded the delivery; False ⇒ log at WARNING with the (saved_search_id, ad_id) pair
      (the duplicate DETECTOR, see accepted_risks). Idempotent. No bulk_update, no loop.
  - action: edit_code
    target: src/backend/apps/search/models.py — SavedSearchNotification
    description: >
      Add delivered_at = DateTimeField(null=True, blank=True, help_text=…). The help_text is
      load-bearing documentation, not a comment: it must state that the value is written AFTER a
      successful send, that NULL means "recorded but not delivered" and therefore stays eligible
      for both paths, and that one alert per (saved_search_id, ad_id) for the life of the listing
      — including across a re-publish — is a recorded product decision. Rewrite the model
      docstring: "Tracks sent notifications to prevent duplicate alerts" is false; the row is an
      attempt record and delivered_at is the receipt. Correct sent_at's help_text to "when the
      notification record was created" (help_text is not in the DB, so no migration). Meta is
      untouched.
  - action: add_migration
    target: src/backend/apps/search/migrations/0003_* (AddField)
    description: >
      Run makemigrations and take the generated slug and number; RE-LIST the migrations directory
      immediately before generating (0003/0004 are a prediction, not a promise). AddField only:
      delivered_at, null=True, blank=True, no default.
  - action: add_migration
    target: src/backend/apps/search/migrations/0004_* (RunPython backfill)
    description: >
      RunPython(forward, migrations.RunPython.noop) with
      SavedSearchNotification.objects.filter(delivered_at__isnull=True).update(delivered_at=F("sent_at"))
      — set-based, no row loop. The REVERSE IS A NO-OP carrying an explicit comment that a
      reverse which NULLs delivered_at would re-arm the mass re-notification. Two migrations, not
      one, mirroring the existing data-migration precedent in search/0002_*.
  - action: edit_code
    target: src/backend/apps/search/services/alert_query.py
    description: >
      find_matching_ads: add delivered_at__isnull=False to the EXISTING ~Exists subquery and
      nothing else — which ads match a search is untouched. find_matching_saved_searches: add a
      correlated ~Exists(SavedSearchNotification.objects.filter(saved_search_id=OuterRef("pk"),
      ad_id=ad.pk, delivered_at__isnull=False)) to the CANDIDATE QUERYSET — not a per-candidate
      Exists (it would multiply the existing N+1) and not exclude() (join-multiplication trap).
      The is_active / city / price / category / FTS recipient predicate is NOT touched, and the
      chat_id check stays a DELIVERY PRECONDITION, not an audience filter (PII-104, phase 06) —
      say so in the docstrings so phase 06 cannot misread it. record_notifications: CONTRACT
      UNCHANGED — same bulk_create(ignore_conflicts=True), same count = len(ads); only the
      docstring is corrected to say the count is not a delivery signal and that the dedup decision
      lives in the matchers' delivered_at predicate plus notification_delivery.mark_delivered.
      Correct the module docstring's "record notifications to prevent duplicate alerts".
  - action: edit_code
    target: src/backend/apps/search/services/immediate_alerts.py
    description: >
      deliver_immediate_alerts, NEW ORDER: filter and build payloads FIRST, drop the Nones, then
      record only for the (saved_search, ad) pairs that actually produced a payload, then
      _executor.submit. (Today the record loop runs before _build_payload, so a user with no
      chat_id is recorded and then skipped — D-1.) Each payload dict gains a NON-SERIALISED
      side-channel tuple (saved_search_id, ad_id) used only for the post-send mark. In
      _send_payloads._send add exactly ONE call to mark_delivered after the successful
      await bot.send_message(...), INSIDE the try and before the except clauses. No signature
      change, no return-value change, no except change. Rewrite the module docstring: "Delivery is
      idempotent via uq_saved_search_ad + ignore_conflicts, so the daily send_alerts command never
      double-sends" is false.
  - action: edit_code
    target: src/backend/apps/search/management/commands/send_alerts.py
    description: >
      _collect_alerts additionally returns, per user, the SavedSearchNotification rows it already
      built, grouped by user_id. _send_user_digests marks each of that user's rows delivered
      INLINE, immediately after bot.send_message returns without raising; a user with no chat_id
      is skipped BEFORE the send, so its rows are correctly left unmarked (the daily path's own
      D-1 is fixed for free). Command.handle's LOCK/TRANSACTION SHAPE IS UNCHANGED — the mark
      happens after both scopes have closed, exactly where the send already is, which is what
      keeps test_sweep_lock_structure.py byte-identical. REPLACE the docstring sentence that
      nominates "a delivery-state column on SavedSearchNotification (phase 03 DB-007's schema)" as
      the future fix: after this block the column exists, and a shipped TODO is a lie in
      production code. Not touched: DAILY_COMMANDS membership, the run-level daily marker,
      _DIGEST_AD_LIMIT, _BACKOFF_BASE, _format_digest, the CommandError exit-code policy, the
      dry-run branch.
  - action: rewrite_test
    description: >
      F-2(1): invert test_records_notification_idempotently (recorder for _run_send, assert ONE
      submission, KEEP count() == 1, record the rationale). F-2(2): invert
      test_excludes_already_notified_ads → test_excludes_delivered_ads and add
      test_includes_recorded_but_undelivered_ads. Never delete these tests; invert and keep the
      still-valid assertions.
  - action: add_test
    description: >
      The supplementary suite below, plus one genuine override_settings(IMMEDIATE_ALERTS_ENABLED)
      gate test in test_alert_query.py (True ⇒ _run_send is reached; False ⇒ it is not) — an
      ADDITION beside the no-op gate test, not a strengthening of it.
  - action: edit_docs
    description: >
      The four owned docs. technical-specification.md decision O gets NO EDIT. db-retention.md is
      out of scope.

implementation_sequence:
  - step: 1
    action: >
      WRITE THE RED TESTS FIRST, and run them; capture the failing output. No production code
      before this: the inverted test_records_notification_idempotently, the inverted
      test_excludes_delivered_ads + its new collectable sibling, then
      test_no_chat_id_records_nothing_and_stays_collectable, test_failed_send_leaves_pair_undelivered_and_collectable,
      test_republish_submits_nothing_on_second_call, test_cross_path_dedup. Show them RED in the
      task report. Red is the whole point — today the suite cannot see the defect.
  - step: 2
    action: >
      Re-derive anchors by SYMBOL, not by line: re-list search/migrations/ immediately before
      generating; re-read immediate_alerts.py immediately before editing it, in case phase 09
      API-013 has landed in the interim.
  - step: 3
    action: >
      models.py field + help_text, then generate 0003_* (AddField) and 0004_* (backfill) with
      makemigrations/takemigrations, taking the generated slugs. Pin the behaviour-preservation
      with test_backfill_marks_preexisting_rows_delivered before touching the matchers.
  - step: 4
    action: >
      notification_delivery.py, then BOTH matchers, then BOTH writers (immediate_alerts.py and
      send_alerts.py). The filter change and the daily write change LAND IN ONE COMMIT — see
      architectural_constraints.
  - step: 5
    action: >
      Green the reds; add test_daily_digest_marks_delivered_after_send (the infinite-loop guard),
      the mark_delivered unit tests and the real gate test. Then ruff + basedpyright.
  - step: 6
    action: >
      The four docs, then the Docker gate in acceptance_criteria (sequential, foreground).

architectural_constraints:
  - >
    THE FILTER CHANGE AND THE DAILY WRITE CHANGE ARE ONE ATOMIC CHANGE. Changing only the filter
    produces an INFINITE daily re-notification loop: the daily path collects a pair whose row
    has delivered_at IS NULL, bulk_create(ignore_conflicts=True) silently no-ops the insert, the
    digest renders, and the next day collects it again — forever, to the same user. This is the
    single largest implementation hazard in the block. One commit, one rollback unit.
  - >
    mark_delivered contains NO transaction.atomic() and NO advisory_lock. A single conditional
    statement in autocommit is already atomic; send_message is not transactional. No new
    AdvisoryLockId is allocated, and no lock is taken on either path.
  - >
    TWO migrations, not one; the second one's REVERSE IS A NO-OP and must stay one.
  - >
    record_notifications' CONTRACT is unchanged (bulk_create(ignore_conflicts=True), returns
    len(ads)) — only its docstring changes. record_notifications still WRITES rows; it does not
    mark them delivered.
  - >
    Command.handle's lock/transaction shape is UNCHANGED. The daily mark happens after both
    scopes close. Do NOT move the send inside the transaction, split the collect/persist
    transaction, add a session lock, add a 14th sweep entry, or reorder _LOCK_TARGET_MODULES.
  - >
    core/tests/test_sweep_lock_structure.py stays BYTE-IDENTICAL. send_alerts remains SWEEP
    entry 12 of 13, still in_atomic is True / session is False, and still absent from
    _SESSION_SCOPED_BATCHERS.
  - >
    TestImmediateAlertsGate::test_gate_off_does_not_deliver_on_publish stays BYTE-IDENTICAL, is
    NOT counted as gate coverage, and is NOT strengthened. The real gate pin is
    moderation/tests/test_approve_ad_side_effects.py and it must stay green.
  - >
    _run_send / _send_payloads signatures, the AiogramError-only narrowing, the
    future/callback surface, _MAX_DELIVERY_THREADS, _SEND_CONCURRENCY, _BACKOFF_BASE,
    UNSUB_CALLBACK_PREFIX, build_alert_message and build_alert_message_keyboard are FROZEN.
    TestRunSendExceptionNarrowing::test_non_aiogram_error_propagates is a phase 09 API-013 pin.
    BLOCK 9's contract lives in the NEW module; immediate_alerts.py receives a one-line insertion
    only. No backpressure, no shutdown hook, no new pool.
  - >
    NO new index — and the decision is recorded, because an undocumented no-change is an
    omission. For find_matching_ads the unique index (saved_search_id, ad_id) is an EXACT PREFIX
    match for the two indexed columns and delivered_at is a cheap heap-level residual. For
    find_matching_saved_searches the correlated Exists drives off saved_searches.id and probes
    the same index prefix, leaving the outer query's cost unchanged. Meta is untouched.
  - >
    NO new user-visible strings: no gettext, no template, no translatable message. The field's
    help_text and the docstrings are not user-facing.
  - >
    logger = logging.getLogger(__name__), NEVER print(). Comments, docstrings, log records and
    migration comments in English. Any existing basedpyright suppression stays in place — do not
    delete suppressions to make the typechecker happy and do not add blanket ignores.
  - >
    No new dependency, no new feature flag, no change to IMMEDIATE_ALERTS_ENABLED's default or
    to any .env.*.example template.
  - >
    No test may assert on a source line number, on an exact log string, or on the ABSENCE of a
    name (e.g. "assert 'atomic' not in source"). Assert observable behaviour: rows, timestamps,
    submitted payloads, digests, return values.
  - >
    Scope fences: SavedSearch.last_notified_at's false help_text is recorded drift, not fixed here.
    The 'edited live ad should re-alert' product question is a named follow-up. send_alerts'
    pre-existing pre-send-record crash window is fixed as a SIDE EFFECT of the daily mark, not as
    a separate change. moderation/signals.py is a reference, not an edit.

tests_to_add:
  - { name: test_no_chat_id_records_nothing_and_stays_collectable,
      class: TestDeliverImmediateAlerts, file: test_alert_query.py,
      pins: "D-1. No SavedSearchNotification row for a user with no chat_id, and find_matching_ads still returns the ad.",
      red_today: true }
  - { name: test_failed_send_leaves_pair_undelivered_and_collectable,
      class: TestDeliverImmediateAlerts, file: test_alert_query.py,
      pins: "D-2. _run_send raises ⇒ a row exists, delivered_at IS NULL, find_matching_ads still returns the ad.",
      red_today: true }
  - { name: test_republish_submits_nothing_on_second_call,
      class: TestDeliverImmediateAlerts, file: test_alert_query.py,
      pins: "D-3. A second deliver_immediate_alerts on the same ad.id submits no payload.",
      red_today: true }
  - { name: test_cross_path_dedup,
      class: TestSendAlertsCommand, file: test_alert_query.py,
      pins: >
        Replaces the source plan's acceptance criterion the audit proved FALSE. A pair delivered by
        the immediate path is not re-delivered by send_alerts; a pair delivered only by send_alerts
        is still excluded by the immediate matcher. Assert on delivery, not on the return value.
      red_today: true }
  - { name: test_includes_recorded_but_undelivered_ads,
      class: TestFindMatchingAds, file: test_alert_query.py,
      pins: "The twin of the inverted test: a row with delivered_at = NULL is COLLECTABLE.",
      red_today: true }
  - { name: test_excludes_delivered_ads,
      class: TestFindMatchingAds, file: test_alert_query.py,
      pins: "The INVERSION of test_excludes_already_notified_ads — set delivered_at on the fixture row.",
      red_today: true }
  - { name: test_backfill_marks_preexisting_rows_delivered,
      class: new, file: test_alert_delivery.py,
      pins: >
        F-1 behaviour-preservation. A row created before the backfill migration has
        delivered_at == sent_at and REMAINS EXCLUDED by find_matching_ads. This is the test that
        stops a mass re-notification from reaching production.
      red_today: n/a }
  - { name: test_daily_digest_marks_delivered_after_send,
      class: TestPerUserDigestCap (or a sibling), file: test_send_alerts_daily.py,
      pins: >
        THE INFINITE-LOOP GUARD for the one-atomic-change rule. After a successful digest send that
        user's rows have delivered_at IS NOT NULL; after a FAILED send they do not.
      red_today: n/a }
  - { name: test_mark_delivered_is_idempotent_and_conditional,
      class: new, file: test_alert_delivery.py,
      pins: >
        A second call for the same pair is a no-op returning False; a WARNING log record names the
        (saved_search_id, ad_id) pair. Assert the returned bool and the row's timestamps — not the
        log text.
      red_today: n/a }
  - { name: test_immediate_alerts_flag_gate_reaches_sender_only_when_enabled,
      class: new (beside TestImmediateAlertsGate), file: test_alert_query.py,
      pins: >
        The real gate coverage the no-op test cannot give. With override_settings
        (IMMEDIATE_ALERTS_ENABLED=True) _run_send is reached; with False it is not.
      red_today: n/a }
  - note: >
      Shape reference for the D-1/D-2 regressions:
      test_send_alerts_daily.py::TestPerUserDigestCap::test_per_user_cap_is_applied_at_collection_time
      — the existing strongest pin of the "record ⊆ deliver" invariant. Copy its structure.
      Exercise the code path directly; do not flip IMMEDIATE_ALERTS_ENABLED globally.

must_keep_passing_unchanged:
  - test_alert_query.py::TestRecordNotifications::test_ignore_conflicts_skips_duplicates
  - test_alert_query.py::TestImmediateAlertsGate::test_gate_off_does_not_deliver_on_publish  # byte-identical
  - src/backend/apps/core/tests/test_sweep_lock_structure.py                                  # byte-identical
  - src/backend/apps/moderation/tests/test_approve_ad_side_effects.py
  - src/backend/apps/search/tests/test_send_alerts.py::TestHandleSafety::test_handle_swallows_aiogram_error
  - test_alert_query.py::TestRunSendExceptionNarrowing::test_non_aiogram_error_propagates
  - src/telegram_bot/tests/test_alerts*.py
  - >
      The phase-01 send_alerts idempotency tests, re-anchored by SYMBOL (D-2), not by a commit
      hash: apps.core.utils.scheduler.SchedulerDailyMarker, apps.core.services.scheduler_daily_state,
      send_alerts._DIGEST_AD_LIMIT, send_alerts.Command.handle's loss-window docstring.
  - src/backend/apps/ads/tests/ (unaffected neighbours, run for regression)

documentation_deliverable:
  - path: docs/02-database/db-schema.md
    region: "### SavedSearchNotification"
    owed: >
      Add delivered_at (TIMESTAMP, NULL, no default). Replace the header sentence "Tracks
      notification delivery…" with the real contract: the row is an ATTEMPT RECORD, delivered_at
      is the RECEIPT, NULL stays eligible. State that it is written AFTER a successful send, that
      it is backfilled from sent_at, and that one alert per (saved_search_id, ad_id) for the life
      of the listing — including across a re-publish — is a product decision, made visible.
  - path: docs/02-database/db-indexes.md
    region: "## Indexes — saved_search_notifications"
    owed: >
      Keep uq_saved_search_ad as-is and RECORD the "no new index" decision with its reason for
      BOTH predicates (exact prefix match + cheap heap residual; correlated Exists drives off
      saved_searches.id). A documented no-change is a decision; an undocumented one is an omission.
  - path: docs/04-user-stories/buyer-stories.md
    region: "### US-B11"
    owed: >
      Careful, minimal touch. The mechanism sentence cites uq_saved_search_ad as THE dedup
      mechanism — wrong today and wrong after the fix (it is the row-level backstop). Cite the
      delivery-state contract instead of the constraint name. The DEDUP PROMISE ITSELF DOES NOT
      CHANGE and must not be reworded. Do not touch the story, the unsubscribe surface or the
      flag sentence.
  - path: docs/01-spec/architecture-structure.md
    region: "the cron note"
    owed: >
      The only place in the docs that states the dedup invariant, and it states it for the DAILY
      path only. Extend it: the daily NOT EXISTS now filters on DELIVERED state (so a failed
      digest is retried on the next run rather than suppressed), and the immediate path is
      separately gated by IMMEDIATE_ALERTS_ENABLED and deduped by the same contract. COORDINATE
      WITH BLOCK 11 — both file against this file; BLOCK 9's claim is the cron note only.
  - path: docs/01-spec/technical-specification.md
    region: "decision O"
    owed: "NO EDIT. 'Deduplicated per search-ad pair' is MORE true after the fix, not less. Record the decision; change nothing (PII-113 and phase 15 both file against this file)."
  - path: docs/02-database/db-retention.md
    region: "—"
    owed: "OUT OF SCOPE. No alert-delivery region exists in it and it is already three-way edited by BLOCKs 6/7/8."
  - not_touched: >
      docs/99-agent/architecture.md, spec-index.md, search-patterns.md, docker-deployment.md
      (IMMEDIATE_ALERTS_ENABLED row), config/settings/base.py, apps/core/enums.py,
      core/utils/advisory_lock.py.

accepted_risks:
  - >
      1. The CONCURRENT duplicate is DETECTED, not PREVENTED. Two concurrent ticks both send; the
      loser's UPDATE … WHERE delivered_at IS NULL returns 0 rows and mark_delivered logs a WARNING
      with the (saved_search_id, ad_id) pair. This is the honest limit of any database-only answer
      without a Telegram-side idempotency key. Accepted because the concurrent trigger is
      UNDEMONSTRATED, the on_commit call site is unique per publish, and the feature is behind an
      OFF flag. ESCALATION TRIGGER: if mark_delivered ever returns False in production logs, that
      is evidence the concurrent case is real, and the fix is the claimed_at/lease shape — a
      separate block with search/0005_*.
  - >
      2. Crash-window duplicate between send_message returning 200 and the UPDATE committing — one
      extra message per affected pair, self-correcting, visible as a 0-row UPDATE. Accepted: the
      alternative's failure mode is a permanent loss.
  - >
      3. Pre-existing D-1/D-2 rows stay suppressed. The backfill preserves today's behaviour
      exactly, which is the point — but already-lost alerts are not recovered. OPS FOLLOW-UP, not
      this block: a pre-existing row whose user had no chat_id at record time is unrecoverable
      from the database.
  - >
      4. The re-publish product decision (§2.3) is encoded WITHOUT a filed finding. Accepted only
      because the coordinator approved it, and made visible in the field help_text, the model
      docstring and db-schema.md so it reads as a decision, not an accident.
  - >
      5. A seller who EDITS a live ad and is re-moderated back to PUBLISHED does not re-alert —
      a real, unquantified product loss. Deferred to a named follow-up whose recommended epoch is
      a content-revision column, NOT Ad.published_at. NAMED OWNER: the coordinator / Product Owner.
      The 2026-10-03 decision round did not reach this question and it is still deferred.
  - >
      6. lock_timeout/PgBouncer exposure (BLOCK 5's) is MOOT — no lock is taken, so no 55P03 can
      be raised inside an on_commit callback. ELIMINATED by the design, not accepted.
  - >
      7. Process attribution of deliver_immediate_alerts remains unverified (reachable from the
      bot's submit/auto-moderate and the web's approve/reactivate). IMMATERIAL to this design,
      which holds in any process because the state is in the database.
  - >
      8. The sent_at semantics lie is corrected in help_text and docstrings only, not in the
      column's value — existing rows' sent_at still means "recorded". A full semantic correction
      would need the backfill plus a column rename and is not warranted.
  - >
      9. UNVERIFIED BY EXECUTION on the anchor: the decision record used zero Docker invocations
      and zero test runs, so every claim in it is a SOURCE-READING claim at HEAD 35441e0, not a
      demonstrated behaviour. The red tests in implementation_sequence step 1 are what convert
      them into evidence.

commit_message_requirements:
  - >
      Name the finding: "03-DB-007 saved-search alert delivery-state contract" and state in the
      body that the row is an attempt record and delivered_at is the receipt.
  - >
      Record the BACKFILL explicitly — "backfill delivered_at = sent_at (behaviour-preserving);
      reverse is a no-op" — so a future reader does not "clean it up" into a NULLing reverse and
      re-arm a mass re-notification.
  - >
      Record the PRODUCT DECISION: one alert per (saved_search_id, ad_id) for the life of the
      listing, including across a re-publish; the edited-ad re-alert is a deferred follow-up.
  - >
      Record the LIMITS: the concurrent duplicate is DETECTED, not prevented; the escalation
      signal is mark_delivered returning False in production logs; a kill in the crash window
      yields one bounded duplicate.
  - >
      Record the ONE-ATOMIC-CHANGE constraint: the filter change and the daily write change are a
      single unit; reverting half of it creates an infinite daily re-notification loop.
  - >
      Record that IMMEDIATE_ALERTS_ENABLED remains OFF and unset in every template, and that
      the two shipped tests were INVERTED, not deleted, with the defect each one encoded.
  - >
      List the two migrations by their GENERATED names; English only; no print(), no secrets.

acceptance_criteria:
  - >
      RED-FIRST EVIDENCE: implementation_sequence step 1's failures were captured and shown before
      any production code changed.
  - >
      `uv run ruff check src/` exits 0 and `uv run basedpyright src/` reports 0 errors; no
      suppression deleted, no blanket ignore added.
  - >
      MIGRATION HYGIENE: `makemigrations --check --dry-run` reports no pending changes, AND a
      real forward AND backward `migrate` is exercised on a NAMED SCRATCH DATABASE
      (e.g. mko_bazuna_block9_migration_check): forward to 0004 with a pre-existing row, then
      reverse 0004 and observe that delivered_at is UNCHANGED (the no-op reverse, proved), then
      forward again, then back to 0002. NEVER run migrate against test_mko_bazuna and NEVER drop
      or recreate the named Docker volume: pytest's DisableMigrations means no test gate replays
      the migrations, so a hand-run migrate there is neither verified nor reversible and would
      corrupt the shared volume for the rest of the phase.
  - >
      SEARCH GATE (Docker only, run SEQUENTIALLY and in the FOREGROUND — never in the background,
      never two suites at once):
      $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=src/backend/apps/search/tests/ test
  - >
      ADJACENT GATES, each as its own sequential run:
      $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=src/backend/apps/moderation/tests/test_approve_ad_side_effects.py test
      $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=src/telegram_bot/tests/test_alerts.py test
  - >
      Fresh schema first, because two migrations were added:
      .\Makefile.ps1 test-recreate
  - >
      Then the full gate: .\Makefile.ps1 test
      $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/search/tests/ src/backend/apps/ads/tests/ src/backend/apps/moderation/tests/test_approve_ad_side_effects.py src/telegram_bot/tests/test_alerts.py" test
  - >
      NOTE on the Docker harness: PYTEST_OPTS is UNQUOTED in docker/entrypoint-test.sh and
      word-splits on spaces — quoted multi-token values do not work, and setting PYTEST_OPTS
      REPLACES the default --reuse-db --tb=short --durations=10 -n auto --maxprocesses=4
      --dist loadgroup. Never use --override-ini=addopts= (it strips
      --import-mode=importlib). Do not delete or recreate the test DB volume.
  - >
      THE FULL SUITE IS EXPECTED TO SHOW EXACTLY ONE FAILURE — the pre-existing
      search/tests/test_search_slo.py::…::test_search_at_seed_volume_meets_slo, which fails on the
      anchor. Any other failure, or a count other than one, is BLOCK 9's and must be fixed or
      explained. Do not attribute the SLO failure to this block, and do not "fix" it.
  - >
      Behavioural: a failed send is retried by the other path; a delivered pair is never delivered
      again by either path, including across a re-publish; a user with no chat_id is never
      recorded; pre-existing rows stay excluded (behaviour-preserving deploy).
  - >
      Structural: core/tests/test_sweep_lock_structure.py and
      TestImmediateAlertsGate::test_gate_off_does_not_deliver_on_publish are BYTE-IDENTICAL (prove
      it with a diff), no new AdvisoryLockId, Meta unchanged, no new index, no new user-visible
      string, technical-specification.md decision O and db-retention.md untouched.
  - >
      Follow-up findings filed, not fixed: (a) "an edited live ad should re-alert" product
      question, with the content-revision-column epoch recommendation — OWNER: coordinator /
      Product Owner, still deferred after the 2026-10-03 decision round; (b)
      SavedSearch.last_notified_at's false help_text drift; (c) audit E2c — the no-op gate test —
      named with its real replacement.
```

**Replace the stale draft above.** The advisory lock and the "no backfill" rule are gone; the
`delivered_at` delivery-state contract and the behaviour-preserving `delivered_at = sent_at`
backfill are in their place. **F-1 is the headline hazard in this block:** shipping the filter
change without that backfill mass re-notifies every previously notified pair to every subscribed
buyer on the next live 08:00 UTC `DAILY_COMMANDS` run, one day after deploy, with no flag to turn
it off.

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
- **Researcher — NO, and this is a deliberate correction of instinct, not an oversight.** Q12 was a
  **product** decision, not a technical survey; the tree points at an in-repo model
  (`create_draft_ad`'s delete-then-recreate); and project rule 5 says prefer the simple obvious
  solution over abstractions. Adding a Researcher here would be ceremony with no question to
  answer. **If the coordinator challenges this, the answer is that there was never an external
  best-practice question — only a product preference.** *(Settled twice over: the coordinator first
  closed Q12 as **Option A applied as a default**, and the **Product Owner then ruled Option A as a
  decision on 2026-10-03** — see the decision gate. Either way there was never an external question
  to survey, so the "no Researcher" rationale above is unchanged.)*
- **Planner — yes.** The product rule must be specified for **both** creators at once, the
  error-handling boundary defined, and the i18n string set designed.
- **Validator — yes.** Seller-visible behaviour changes and a new user-facing message ships; the
  "unified rule" is only credible if both call sites are shown to obey it.

**Decision gate — Q12 — ✅ RESOLVED 2026-10-03 by the Product Owner: Option A, taken as a
DECISION.**

> **The 2026-10-03 ruling supersedes this block's earlier "applied as a DEFAULT, not as a product
> decision" framing. The option is unchanged; the *character* of the answer is not.** A commit
> implementing it **must now record that the rule was chosen by the Product Owner on 2026-10-03** —
> the previous instruction ("must record that the choice was made by default, not by decision") is
> **withdrawn**, because it is no longer true. Recorded so no implementor satisfies the letter of
> the old rule and contradicts the new one.
>
> Option table in the source plan §3.10.1. **`copy_ad` deletes the seller's existing `DRAFT`
> inside its already-open `transaction.atomic()` before creating the copy** — exactly the shape
> BLOCK 4 shipped for `create_draft_ad` (`ad_data/orm.py::create_draft_ad`). The partial unique
> index `uq_ads_single_draft_per_user` stays as the **backstop**; a concurrent race is absorbed by
> the same savepoint-and-retry, never by a new mechanism.
> **Option B (catch `IntegrityError`, new translated string) is REJECTED** — it diverges from the
> already-shipped `/post` behaviour, so the two creators would disagree, and it puts a behaviour
> change on the hottest bot path. **Option C remains FORBIDDEN.**
>
> Independently of the option, `cmd_copy`'s `_("Failed to copy ad: {error}").format(error=e)`
> goes away: raw psycopg text (constraint name, `DETAIL Key (...)`, `CONTEXT INSERT INTO ads`)
> must never reach a seller's chat. That change needs **one** new msgid appended to **all three**
> `.po` files (`ru`/`bs` non-empty, `en` may be empty) —
> `test_extraction_completeness` fails if a msgid is missing from any locale.

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
title: Mirror BLOCK 4's single-draft savepoint in copy_ad and stop leaking raw driver errors
priority: low
depends_on: [task_03_b04_create_draft_savepoint]
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 10 — One single-draft policy, applied in both creators (DB-009)"
extra_context: |
  Q12 IS RESOLVED — 2026-10-03, Product Owner. Option A, TAKEN AS A DECISION (not as a default).
  A commit implementing it MUST record that the single-draft rule was ruled by the Product Owner on
  2026-10-03. The older "this was a default, not a decision" wording is WITHDRAWN.
  `copy_ad` deletes the seller's existing DRAFT inside its already-open `transaction.atomic()`
  before creating the copy, mirroring BLOCK 4's `create_draft_ad` EXACTLY: the create is wrapped
  in a NESTED `transaction.atomic()` savepoint with the `try` OUTSIDE it, and an
  `except IntegrityError:` branch cleans up and retries once.
  OPTION B IS REJECTED (diverges from the shipped `/post` behaviour); OPTION C IS FORBIDDEN.
  INDEPENDENT OF THE OPTION: `cmd_copy`'s broad `except Exception` must stop interpolating raw
  psycopg text (constraint name, `DETAIL Key (...)`, `CONTEXT  INSERT INTO ads`) into Telegram.
  Locale files are a SHARED artefact with phase 14 — APPEND the one new msgid to ru, bs AND en
  (test_extraction_completeness requires all three; ru/bs msgstr non-empty), never regenerate.
  Do NOT touch `create_draft_ad`/`ad_data/orm.py` (BLOCK 4, already shipped), the `Ad` model, the
  partial index, `AdvisoryLockId`/`advisory_lock.py`, or copy_ad's storage-key reuse
  (AD-003, phase 05). No new dependency, no migration, no new deployment surface.

description: >
  copy_ad never sets status, never handles uq_ads_single_draft_per_user, and never touches an
  existing DRAFT, so a seller who already has one trips the partial unique index; the raw psycopg
  text then propagates out of cmd_copy into a Telegram message. Apply BLOCK 4's shipped
  delete-then-recreate policy inside copy_ad's existing transaction, keep filesystem deletions
  after commit via the AdImage pre_delete signal, and stop surfacing raw exception text.

goals:
  - apply ONE single-draft policy across create_draft_ad and copy_ad (BLOCK 4's exact shape)
  - keep the partial unique index as the backstop, not the primary mechanism
  - stop interpolating raw database exception text into user-facing messages
  - make the rationale survive review, so nobody "simplifies" the savepoint away

files:
  - path: src/backend/apps/ads/services/copy_service.py
    targets: [{ type: function, name: copy_ad }]
    semantic_anchors:
      insert_after:
        type: raise_statement
        value: 'raise PermissionError("Cannot copy another user\'s ad")'
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
    targets: [{ type: module, name: test_ad_copy }]
    semantic_anchors: {}   # the `assert "failed" in called_text.lower()` must keep passing unchanged
  - path: src/backend/locale/ru/LC_MESSAGES/django.po   # APPEND the one new msgid
    targets: [{ type: module, name: django_po }]
    semantic_anchors: {}
  - path: src/backend/locale/bs/LC_MESSAGES/django.po
    targets: [{ type: module, name: django_po }]
    semantic_anchors: {}
  - path: src/backend/locale/en/LC_MESSAGES/django.po
    targets: [{ type: module, name: django_po }]
    semantic_anchors: {}   # en msgstr may stay empty

changes:
  - action: add_code
    description: >
      In copy_ad, after the ownership check and before constructing the copy, delete the seller's
      existing DRAFT inside the EXISTING atomic() — mirroring create_draft_ad's delete + recreate.
      Wrap the Ad construction/save in a NESTED transaction.atomic() savepoint with the `try`
      OUTSIDE it, and on IntegrityError delete the seller's DRAFT and retry once. The delete and
      the create must live in the SAME transaction so a failed create leaves the seller as they
      were. Do not hand-roll a manual storage-key sweep — the AdImage pre_delete signal
      (apps.media.signals::delete_adimage_files_on_delete) already defers file deletion to
      transaction.on_commit(), which is why copy_ad's own atomic() must remain the outermost one.
  - action: edit_error_handler
    description: >
      Replace the raw-interpolating `except Exception` branch in cmd_copy with one that logs via
      the existing logger.exception and answers a translated, non-interpolating message.
  - action: add_locale_entry
    description: >
      Append msgid "Failed to copy ad." to ru, bs and en django.po with non-empty ru/bs msgstr.
      Append only; never run makemessages/regenerate, and never delete the now-obsolete
      "Failed to copy ad: {error}" entry (it is a shared artefact with phase 14).
  - action: edit_docstring
    description: >
      copy_ad's docstring must document the delete-then-recreate policy AND the savepoint
      rationale, the way create_draft_ad's does — a reviewer finding that rationale absent treats
      it as a defect. test_copy_ad.py's module docstring currently asserts the unenforced
      precondition "the seller cannot have an existing DRAFT when copy_ad runs"; correct it.

acceptance_criteria:
  - a seller with an existing DRAFT running /copy ends with EXACTLY ONE DRAFT, and it is the copy
  - a seller with no existing DRAFT is unaffected (no regression)
  - the copy is DRAFT and its fields match the source
  - the failure message contains NO raw driver text (no constraint name, no "Key (", no "DETAIL",
    no "CONTEXT", no "INSERT INTO") and still contains the word "failed"
  - a replaced draft's media files are removed after commit, not inside the transaction
  - a failed create leaves the seller's original DRAFT intact (same transaction)
  - the 5 existing test_copy_ad.py tests and the 6 existing test_ad_copy.py tests pass unchanged
  - BLOCK 4's test_create_draft_ad.py (incl. TestCreateDraftAdCrashRecovery), BLOCK 6's
    test_ad_create_heartbeat_coverage.py + test_ad_create_heartbeat.py, test_sweep_lock_structure.py,
    test_ad_constraints.py and test_i18n_completeness.py pass unchanged
  - copy_ad's storage-key reuse and create_draft_ad's shipped shape are unchanged
  - no migration, no new dependency, no `apps.*` -> `telegram_bot.*` import
  - the commit body records the single-draft rule as a Product Owner DECISION dated 2026-10-03, and
    does not describe it as a default
  - uv run ruff check src/ exits 0 and uv run basedpyright src/ reports 0 errors
  - the Docker gate below is green
```

**Tests required.**

- *Must keep passing unchanged:* all 5 of `src/backend/apps/ads/tests/test_copy_ad.py`; all 6 of
  `src/telegram_bot/tests/test_ad_copy.py` (including the `"failed"` assertion); BLOCK 4's
  `src/telegram_bot/tests/test_create_draft_ad.py`; BLOCK 6's
  `src/telegram_bot/tests/test_ad_create_heartbeat_coverage.py` + `test_ad_create_heartbeat.py`;
  `src/backend/apps/core/tests/test_sweep_lock_structure.py`; `test_ad_constraints.py`;
  `test_i18n_completeness.py`.
- *Must be added:* the **pre-existing-DRAFT copy test**, written FIRST and shown RED against the
  unfixed tree (today it raises `IntegrityError`), asserting the invariant **"a draft is
  returned"** plus exactly one DRAFT for that seller — **never** "the seller's draft survived"
  (false) and **never** a specific exception class; the **no-pre-existing-draft** copy test; and
  the **raw-driver-text-never-reaches-Telegram** test.
- *Must be changed:* none of the existing tests. Only the two module/function docstrings.

**Exact gate command (Docker only — run SEQUENTIALLY, never two suites at once).**

```powershell
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_copy_ad.py src/telegram_bot/tests/test_ad_copy.py src/telegram_bot/tests/test_create_draft_ad.py" test
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_ad_create_heartbeat_coverage.py src/telegram_bot/tests/test_ad_create_heartbeat.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/ads/tests/test_i18n_completeness.py" test
.\Makefile.ps1 test
```

**Risk / rollback.**

- *Risk:* deleting the seller's in-progress draft before the copy commits loses both on a later
  failure. **Mitigated by construction:** one transaction, so a failed create rolls the delete
  back and the seller is exactly as they were.
- *Risk (accepted, not a defect):* `/copy` mid-dialog deletes the draft the FSM still points at,
  so the next step hits `process_preview`'s existing, already-translated "Your draft expired and
  was deleted. Please start again with /post." Confirm that string exists and is reachable, and
  record the consequence — do **not** "fix" it here.
- *Risk:* the savepoint being "simplified" away by a later reader. Countered by the docstring.
- *Risk:* changing the error surface breaking the `"failed"` assertion. Countered by a required
  test.
- *Rollback:* two functions, two docstrings and one msgid. Fully reversible; no schema.

---

### BLOCK 11 — Finding-ID namespace disambiguation (`03-VAL-001`, source-comment half)

| | |
|---|---|
| **Findings owned** | `03-VAL-001` (the source-comment half) |
| **`depends_on`** | *(none)* — executes last; re-reads every file it touches |
| **Priority** | P2 — **gate CLOSED**, executes unconditionally |
| **Roster** | **Auditor, Planner, Implementor, Validator** → *four* (Researcher dropped) |
| **Gate** | **CLOSED** — Option C chosen by the coordinator; no open gate remains |

**Roster decision — REDUCED to four; the Researcher is dropped.** The Researcher's role was
**archaeological ambiguity resolution** ("establish which cycle each legacy ID belongs to").
Option C **descriptive replacement never asks for that attribution** — a description needs no
cycle number — so the entire premise of the role is dead. Keeping it would mean paying for work
whose output is deliberately discarded. The other four roles all survive intact: the Auditor
still re-derives the inventory (and did, decisively), the Planner still sets the cross-phase
convention, Implementor and Validator unchanged.

**Decision gate Q14 (second half) — CLOSED: Option C, descriptive replacement.** Coordinator
ruling, recorded here so no later reader treats it as open:

1. Every unresolvable bare citation becomes a **short, self-contained description of the
   invariant the comment defends**, so the comment is useful **without** an id lookup.
2. Where the citation is unambiguously a finding **this cycle** fixed, use the phase-scoped
   **`03-DB-00N`** form instead.
3. **Test files are out of scope** — phase 11 territory (unchanged from §5.2).

**Corrected corpus — 6 production files / 18 citations, not 8 / 68.** Re-derived by the Auditor
at `64a9de6` with the mechanical gate `(?<!03-)\bDB-[0-9]{3}\b` over `src/**` excluding `tests/`
and `migrations/`:

| # | Production file | Bare `DB-0\d\d` | In this cycle's commit series? |
|---|---|---|---|
| 1 | `src/backend/apps/ads/services/submission.py` | 1 | yes (`35441e0`, `ead3bc9`, `ba1b059`, `64a9de6`) |
| 2 | `src/backend/apps/ads/views/edit.py` | 2 | yes (`42d0edd`, `bb034e9`) |
| 3 | `src/backend/apps/ads/models.py` | 1 | yes (`2697796`) |
| 4 | `src/backend/apps/core/utils/advisory_lock.py` | 3 | yes (`7c7a27e`, BLOCK 2) |
| 5 | `src/backend/apps/moderation/admin_actions.py` | 7 | yes (`42d0edd`) |
| 6 | `src/backend/apps/moderation/services/moderation_log.py` | 4 | **NO — untouched legacy**, last touched `83c7f70` (phase 05) |
| | **Total** | **18** | 5 of 6 in-series |

**Why the source plan's corpus was wrong in both directions.** The plan's "8 production files"
included `archive_sweep.py`, `send_alerts.py` and `ad_data/orm.py` — all three are **already
clean** at HEAD (every `DB-*` citation there is `03-DB-00N`-scoped: BLOCK 2 normalised
`advisory_lock.py`'s `DB-010`, BLOCK 9 `7245f48` normalised all three `send_alerts.py`
citations to `03-DB-007`, and `orm.py` never had a citation, per `D-6`). Conversely the plan's
"68 citations across 26 files" is **not reproducible at HEAD**: repo-wide the same gate returns
**68 matches across 25 files**, of which **18 are production** and **50 are test files**. The
`26`-file figure is not re-derivable and is treated as **superseded, not corrected**.

**Classification (Auditor-verified; all 18 comments are FACTUALLY CORRECT today).**

| Class | Count | Disposition |
|---|---|---|
| **(a)** this cycle's own `DB-004`, written bare by `42d0edd` (plus `advisory_lock.py`'s already words-qualified `phase 03 DB-004`, which needs only the hyphen) | **5** | → **`03-DB-004`** |
| **(b)** pre-phase-03 origins (`214a988`, `1d7aa1c`, `324d50b`, `ef319ad`, `AUT-003..010`) | **13** | → **descriptive text** |
| **(c)** already unambiguous | **0** | — |

**Class (b) cycle numbers are NOT inferred.** `.ai/audit/**` records are deleted from the working
tree (19 tracked deletions), and the pre-`03-DB-*` origin commits carry **bare `DB-00N` in their
own subjects** — so `git blame` yields the commit but not the cycle. A confident-but-wrong
attribution is worse than today's honest ambiguity, so the descriptions stand alone instead.

**Class-(c) premise DISPROVED — no finding id in this repo carries a phase prefix.** The brief's
hypothesis that `PII-002`, `CF-003`, `ENT-006` were already phase-qualified is **false**. A
census of every non-`DB-` finding-id citation in production source found **no** bare `PII-`,
`CF-`/`CFG-`, `ENT-`, `AUT-`, `ME-`/`MED-`, `SRH-`, `CAB-`, `FT-`, `AL-`, `EXT-`, `FQ-`, `AD-`,
`VAL-`, `OPS-`, `I18N-`, `PERF-`, `AUTHZ-`, `QLT-`-cited id that is phase-prefixed. Two
words-qualified exceptions exist, neither in that list: `alert_query.py`'s `(PII-104, phase 06)`
and `login_token.py`'s `` ``AUT-007`` (phase 04, VAL-002) ``.

**Scope ruling — the gate STAYS at `DB-0\d\d`, production files only.** The wider
unqualified-citation census is **~110 citations across ~61 production files**, because the
class-(c) disproof above generalises: *every* legacy finding id in this repo is bare.
Sweeping ~61 files would be **scope creep across other phases' active work** with real drift
risk — it collides head-on with phase 07 BLOCK 8 (`ME-003`) and phase 06, both already scoped.
**The gate is not widened.** The remaining **~92** non-`DB-0\d\d` unqualified citations are
**routed out to the final report**; the test-file `DB-0\d\d` citations (**50**, out of scope
under §5.2) are routed to **phase 11**. This routing is recorded **in the commit message** as
well as here, so the next reader cannot assume the sweep was complete.

**Convention documentation — three plans, one convention, no source of truth (now closed).**
The `NN-<PREFIX>-00N` rule lived **only** in phase 03's plan: not in `AGENTS.md`, not in
`.kilo/rules/project.md` or `commands.md`, not in any `docs/99-agent/` file — while phase 06
(`06-PII-1xx`) and phase 07 (`07-MEDIA-0NN`) each restated it locally. BLOCK 11 therefore ships
**one** documentation addition: a short *"Finding-id citations"* subsection in
`docs/99-agent/rules.md`, a **living** convention doc (`id: rules`). The four dated artefacts in
`docs/99-agent/` (`test-audit-*.md`, no frontmatter) hold historical citations, are point-in-time
reports of a finished audit, and are **out of scope and must not be edited**; the four living
docs carry no finding-id citation, so nothing stale needs reconciling there.

**Not established, deliberately:** the origin of the plan's `26`-file figure; the cycle number
for any class-(b) citation. Neither is needed under Option C.

**Already decided and not up for renegotiation:** this plan and every phase from 04 onwards keys
its tracker on **`NN-<PREFIX>-00N`**; the precedent is shipped
(`src/telegram_bot/tests/test_unsubscribe.py` cites `03-DB-002`); every comment phase 03 adds in
BLOCK 1–10 uses `03-DB-00N`; BLOCK 11 does **not** touch a file it has no other business
touching.

**Agent briefs (paste-ready).** All four remaining roles; **no Researcher** — its premise died
with Option C.

> **Auditor.** *Goal:* re-derive the ambiguous-citation set at `64a9de6` with the mechanical gate
> `(?<!03-)\bDB-[0-9]{3}\b`, and separate what is *resolvable* from what is not.
> *Hard constraints:* change no code; **never infer a cycle number** — the audit records are
> deleted and the pre-`03-DB-*` commits carry bare ids in their own subjects, so attribution is
> unresolvable by construction. *Must return:* the exact inventory (6 production files / 18
> citations), the class-(a)/(b) split with origin commits as evidence, an explicit
> "cannot be established" for every class-(b) id, and a factual-correctness check of all 18
> comments against current code. **Returned:** `.ai/tmp/block11-context-a.md` — 6/18 confirmed,
> 5/13/0 split, all 18 factually correct, plus the class-(c) disproof and the wider census.

> **Planner.** *Goal:* specify the rewrite so it is safe against twelve phases writing in
> parallel, and so the citation convention acquires the single source of truth it lacks.
> *Hard constraints:* comments and docs in **English**; **no executable code change at all**;
> **no test file touched**; no dated artefact under `docs/99-agent/` touched;
> `src/backend/conftest.py` untouched; **no task target may be a line number**; no new dependency;
> the commit touches only the 6 production files plus `docs/99-agent/rules.md`. *Must return:*
> the ordered file sequence, the per-site rewrite plan, the documentation addition, the
> mechanical acceptance gate, and the commit-message requirements recording the out-of-scope
> routing.

> **Validator.** *Goal:* judge whether a future reader is misled — a judgement about reviewer
> experience that inspection cannot confirm. *Hard constraints:* change no code.
> *Must return:* the mechanical sweep proving zero bare `DB-0\d\d` in production `src/`, the
> `03-DB-004` presence check at its 5 anchors, confirmation that no executable line moved, and an
> explicit statement of what was left undone and why (the ~92 routed-out citations, the 50
> test-file citations).

> **Implementor.** *Goal:* rewrite 18 citations across 6 files, plus one documentation subsection.
> *Hard constraints:* each comment's **technical claim is preserved verbatim** — only the citation
> is touched; comments must remain useful **without** any id lookup; no test name and no assertion
> may change; no line number may be used as a target — locate every site by symbol
> (`submit_ad`, `ad_edit`, `Ad.transition_to`, `advisory_lock`, `bulk_approve`, `bulk_reject`,
> `bulk_delete`, `set_moderation_failed`, `set_rejected`, `set_published`); re-read each file
> immediately before editing; stage explicit paths.

**Implementor task.**

```yaml
id: task_03_b11_finding_id_disambiguation
title: Replace ambiguous DB-00N comment citations (Option C) and document the citation convention
priority: medium
depends_on: []
source_reference: .ai/plans/03-db-concurrency-remediation.md
source_section: "BLOCK 11 — Finding-ID namespace disambiguation (VAL-001)"
extra_context: |
  OPTION C IS DECIDED (Q14 second half, CLOSED). No gate remains open.
  Pure traceability change: ALL 18 comments are factually correct at HEAD 64a9de6 (Auditor
  verified each against current code). DO NOT rewrite any technical claim — only the citation.
  SCOPE IS THE GATE `(?<!03-)\bDB-[0-9]{3}\b` OVER PRODUCTION src/ ONLY. 6 files / 18 citations.
  Test files are OUT OF SCOPE (phase 11). Never infer a cycle number for the 13 class-(b)
  citations: the audit records are deleted and the origin commits carry bare ids in their own
  subjects, so the cycle is unresolvable BY CONSTRUCTION. Describe the invariant instead.
  The 6 files/18 citations supersede the source plan's "8 files / 68 citations across 26
  files", which is unreproducible at HEAD (actual: 68 matches across 25 files, 18 production).
  Do not widen the gate to the ~92 non-DB unqualified citations: routed out to the final report.
  Re-read each file immediately before editing (5 of 6 are in this cycle's commit series) and
  stage EXPLICIT paths — never `git add .`, never `git add -A`.

description: >
  Bare DB-00N ids from previous cycles are shipped in 6 production files, and this cycle's own
  DB-004 was written bare in 3 of them — so advisory_lock.py and admin_actions.py cite a
  previous cycle's id and this cycle's id naming-collision-identically, three lines apart.
  Replace each unresolvable bare citation with a short self-contained description of the
  invariant the comment defends, and phase-scope the five that are this cycle's own. Ship the
  citation convention once, in docs/99-agent/rules.md, where no reader will miss it.

goals:
  - make every in-scope comment useful WITHOUT an id lookup
  - phase-scope the 5 citations that are this cycle's own DB-004 → 03-DB-004
  - add exactly one documentation subsection establishing NN-<PREFIX>-00N as the citation form
  - change no executable line, no test file, no test name, no assertion

files:
  - path: src/backend/apps/core/utils/advisory_lock.py
    targets:
      - { type: module, name: advisory_lock }
      - { type: function, name: advisory_lock }
    semantic_anchors:
      autocommit_assert_comment: "to prevent the autocommit-release bug (DB-001)"
      reserved_id_comment: "was removed in DB-007. IDs 14-99 are reserved"
      timeout_ownership_comment: "phase 03 DB-004 owns any timeout wording"
  - path: src/backend/apps/moderation/admin_actions.py
    targets:
      - { type: function, name: bulk_approve }
      - { type: function, name: bulk_reject }
      - { type: function, name: bulk_delete }
    semantic_anchors:
      lock_row_comments: "# DB-003: lock Ad rows through every transition"
      max_ads_comment: "MaxAdsExceeded (DB-002)"
      bulk_approve_timeout_comment: "# DB-004: the locking SELECT ... FOR UPDATE precedes"
      bulk_reject_timeout_comment: "# DB-004: fail the bulk with nothing committed rather than hanging."
      bulk_delete_timeout_comment: "# DB-004: fail the bulk with nothing committed rather than hanging."
  - path: src/backend/apps/ads/views/edit.py
    targets: [{ type: function, name: ad_edit }]
    semantic_anchors:
      row_lock_comment: "# DB-003: re-fetch the Ad under a row lock"
      timeout_boundary_comment: "# DB-004: a lock timeout aborts the transaction"
  - path: src/backend/apps/ads/services/submission.py
    targets: [{ type: function, name: submit_ad }]
    semantic_anchors:
      auto_moderate_scope_comment: "# DB-001: auto_moderate is inside the outer atomic()"
  - path: src/backend/apps/ads/models.py
    targets: [{ type: class, name: Ad }]
    semantic_anchors:
      transition_to_refresh_comment: "# DB-003: re-read from DB to defeat stale-state races"
  - path: src/backend/apps/moderation/services/moderation_log.py
    targets:
      - { type: function, name: set_moderation_failed }
      - { type: function, name: set_rejected }
      - { type: function, name: set_published }
    semantic_anchors:
      atomic_docstrings: "... are committed or rolled back together (DB-002)."
      toctou_comment: "closing the TOCTOU race on max_ads_per_user (DB-002)."
  - path: docs/99-agent/rules.md
    targets: [{ type: module, name: rules }]
    semantic_anchors:
      new_subsection: "### Finding-id citations — added under the existing `## Rules` heading, next to `### Coding Standards`"

implementation_sequence:
  - step: 1
    action: >
      Re-derive the corpus mechanically and record the numbers in the task report:
      PowerShell `Get-ChildItem src -Recurse -Include *.py | Select-String -Pattern '(?<!03-)\bDB-[0-9]{3}\b'`
      → expect 68 matches / 25 files, of which 18 in the 6 production files
      (submission 1, edit 2, models 1, advisory_lock 3, admin_actions 7, moderation_log 4).
      If the production count is not 18, STOP and report — the tree moved under another phase.
  - step: 2
    action: >
      src/backend/apps/core/utils/advisory_lock.py. Module docstring ×2 + `advisory_lock()` body.
      `(DB-001)` → drop the id, keep the sentence's invariant. `removed in DB-007` → state that
      the member was deleted. `phase 03 DB-004` → `03-DB-004`. Do NOT touch the `Atomic.__enter__`
      or `enums.py`. Do NOT add a `AdvisoryLockId` member — BLOCK 2 owns that file's logic.
  - step: 3
    action: >
      src/backend/apps/moderation/admin_actions.py — the densest file (7 sites).
      The three `with transaction.atomic():` lines carry a `# pyright: ignore[...]` comment that
      MUST be preserved byte-for-byte including its reason text; only the appended `DB-003: lock Ad
      rows through every transition` fragment is touched, and it stays an inline comment.
      `MaxAdsExceeded (DB-002)` → drop the parenthetical. The three `DB-004` sites become `03-DB-004`.
  - step: 4
    action: >
      src/backend/apps/ads/views/edit.py — `ad_edit`, the two adjacent comments. `DB-003` → drop
      the id; `DB-004` → `03-DB-004`. The `try:` that opens the timeout boundary must keep its
      exact position relative to the comments.
  - step: 5
    action: >
      src/backend/apps/ads/services/submission.py — `submit_ad`, the `# DB-001:` prefix drops.
      The comment's five-line technical claim (outer atomic → savepoints → full rollback → ad stays
      DRAFT) is preserved word for word.
  - step: 6
    action: >
      src/backend/apps/ads/models.py — `Ad.transition_to`, the `# DB-003:` prefix drops.
      Do NOT touch the two bare `AD-001` citations in the same file — phase 05, out of scope.
  - step: 7
    action: >
      src/backend/apps/moderation/services/moderation_log.py — the only untouched-legacy file
      (last modified by phase 05's 83c7f70), so it carries the highest drift risk: re-read it
      completely before editing. Three identical docstring sentences drop `(DB-002)`; the
      `set_published` inline comment drops it too. Do NOT touch the two bare `AD-002` citations.
  - step: 8
    action: >
      docs/99-agent/rules.md — add the "Finding-id citations" subsection (see
      documentation_deliverable). One addition under `## Rules`; nothing else in the file changes.
  - step: 9
    action: >
      Run the gates in gate_commands SEQUENTIALLY and in the FOREGROUND. Then re-run the step-1
      census and confirm 0 production matches, 50 test-file matches unchanged, and `03-DB-004`
      present at all 5 class-(a) anchors.

changes:
  - action: edit_comment
    detail: >
      13 class-(b) sites: DELETE the ephemeral id, keep the sentence so it still explains the
      invariant on its own. Deleting only the id token is correct — do not paraphrase the claim.
  - action: edit_comment
    detail: >
      5 class-(a) sites: `DB-004` → `03-DB-004`. In advisory_lock.py the text is already
      words-qualified (`phase 03 DB-004`) — normalise it to the hyphenated form only.
  - action: edit_docstring
    detail: >
      advisory_lock.py's module docstring ×2 and moderation_log.py's three docstrings. Docstring
      prose is preserved; only the citation token is removed or phase-scoped.
  - action: add_documentation
    detail: >
      One "Finding-id citations" subsection in docs/99-agent/rules.md. This is the ONLY
      documentation change in the block.

documentation_deliverable:
  file: docs/99-agent/rules.md
  where: >
    A `### Finding-id citations` subsection inside the existing `## Rules` section, immediately
    after `### Coding Standards`. It is a living convention doc (frontmatter `id: rules`), the
    only correct home for a convention.
  must_state:
    - >
      The citation format is `NN-<PREFIX>-00N` — a two-digit phase, a hyphen, the finding
      prefix, a hyphen, the finding number. Example: `03-DB-004`.
    - >
      A citation MUST carry its phase prefix. A bare `DB-004` / `PII-001` / `AD-002` is
      ambiguous because ids are reissued every cycle and the audit records that resolved the old
      ones are deleted.
    - >
      A comment that defends a past fix should be SELF-CONTAINED: describe the invariant, or name
      the guarding symbol or test, so it is useful without an id lookup.
    - >
      Where a cross-phase reference is genuinely needed, name the phase in words
      ("the phase-06 `PII-104` predicate").
    - >
      English only.
  must_not:
    - >
      Do NOT edit the dated artefacts in docs/99-agent/ (`test-audit-master-report.md`,
      `test-audit-block-f-findings.md`, `test-audit-implementation-plan.md`,
      `llm-tasks/seed-content-generation.md`). They are point-in-time reports of a finished
      audit and are allowed to name symbols that have since moved. Rewriting history in a dated
      report is wrong.
    - >
      Do NOT add finding-id citations of your own to the new subsection — it states the rule, it
      does not become a citation site.
    - >
      Do NOT edit AGENTS.md, .kilo/rules/project.md or .kilo/rules/commands.md. rules.md is the
      single source of truth; restating it elsewhere recreates the three-plans-one-convention
      failure this block closes.

commit_message_requirements:
  - >
    State that this is **Option C (descriptive replacement)** under the coordinator's scope
    ruling, so the choice is discoverable from history.
  - >
    State that the **5 `DB-004` citations became phase-scoped (`03-DB-004`) because they are
    this cycle's own finding**, written bare by 42d0edd.
  - >
    State that the **13 pre-phase-03 citations were DESCRIBED, not re-numbered, because the
    audit records are deleted and inferring a cycle would fabricate provenance.**
  - >
    Record the OUT-OF-SCOPE ROUTING explicitly: the ~92 non-`DB-0\d\d` unqualified finding-id
    citations elsewhere in the repo were deliberately NOT swept (sweeping ~61 files would be
    scope creep across other phases' active work, colliding with phase 06 and phase 07 BLOCK 8)
    and are routed to the final report; the 50 test-file `DB-0\d\d` citations are routed to
    phase 11. Without this sentence the next reader assumes the sweep was complete.
  - >
    Record that the 6 production files + docs/99-agent/rules.md are the entire commit surface,
    and that no executable line changed.
  - >
    No secrets, no `print()`, English only.

gate_commands:
  census_before: |
    PowerShell (rg is unavailable; head/tail do not work):
      Get-ChildItem -Path src -Recurse -Include *.py |
        Select-String -Pattern '(?<!03-)\bDB-[0-9]{3}\b' |
        Group-Object Path | ForEach-Object { "$($_.Count)  $($_.Name)" }
  lint_and_types:
    - uv run ruff check src/
    - uv run basedpyright src/
  tests: |
    .\.Makefile.ps1 test
  docker_only_note: |
    `uv run pytest` locally ALWAYS FAILS — there is no DB on localhost:5432. Tests run through
    the test service of the mko-bazuna-test Compose project:
      $dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
      $dc run --rm --env PYTEST_SKIP_MARKERS=seed test
    Run suites SEQUENTIALLY and in the FOREGROUND — never two at once.

test_environment: |
  Windows 11 · PowerShell · `uv` · PostgreSQL 18 in Docker (mko-bazuna-test, host port 5433).
  DOCKER ONLY for tests; never `uv run pytest` locally.
  - `PYTEST_OPTS` is UNQUOTED in docker/entrypoint-test.sh and word-splits on spaces; setting it
    REPLACES the defaults (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist
    loadgroup`); bare file paths and `-k name` work, quoted multi-token values do not.
  - NEVER `--override-ini=addopts=` — it strips `--import-mode=importlib`.
  - `docker compose run` can abort with `dependency failed to start: ... is unhealthy` BEFORE
    pytest runs; wait ~45 s and retry. A concurrent `--create-db` recreates the shared DB
    mid-flight and produces spurious failures — never run one in parallel.
  - Known pre-existing flakiness, NOT to be fixed: `django_db(transaction=True)` teardown is a
    full-table flush — `ExchangeRateNotFoundError`, `test_bulk_delete_skips_hard_deleted_row`
    seeing leftover `Ad` rows, `test_mko_bazuna is being accessed by other users`.
  - The full suite is expected to show EXACTLY ONE failure:
    `test_search_slo.py::...::test_search_at_seed_volume_meets_slo`. Any other failure is a
    regression introduced here.
  - `head`/`tail` do not work in PowerShell; `rg` is unavailable — use Select-String.
  - The tree is dirty by design and other phases commit concurrently: never `git reset`,
    `git checkout`, `git stash`, `git clean`, `git add -A`, `git add .`, or `git commit -a`.
    Stage EXPLICIT paths. Watch for CRLF damage in the diff.

verification:
  - step: "Mechanical sweep (the gate that matters)"
    command: |
      Get-ChildItem -Path src -Recurse -Include *.py |
        Where-Object { $_.FullName -notmatch '\\tests\\' } |
        Select-String -Pattern '(?<!03-)\bDB-[0-9]{3}\b'
    expect: "ZERO matches"
  - step: "Class-(a) presence"
    command: |
      Select-String -Path src/backend/apps/core/utils/advisory_lock.py,
                         src/backend/apps/ads/views/edit.py,
                         src/backend/apps/moderation/admin_actions.py `
                   -Pattern '03-DB-004'
    expect: "5 comment sites: advisory_lock (1), edit (1), admin_actions (3)"
  - step: "No executable line moved"
    command: git diff --stat <base> -- src/backend/apps
    expect: >
      Only comment/docstring lines changed. Prove it by inspecting the diff: every changed line
      must begin with `#`, be inside a docstring, or be an inline-comment fragment. A changed
      statement line is a defect, not a style question.
  - step: "Commit surface"
    command: git show --stat HEAD
    expect: "Exactly 7 paths: the 6 production files + docs/99-agent/rules.md. Nothing else."
  - step: "Lint and types"
    command: "uv run ruff check src/ ; uv run basedpyright src/"
    expect: "ruff: All checks passed. basedpyright: 0 errors, 0 warnings, 0 notes."
  - step: "Suite (Docker, sequential, foreground)"
    command: .\.Makefile.ps1 test
    expect: >
      No new failure. The fast gate skips the `seed` suite; if the `test_search_slo.py` SLO
      failure appears in the fast gate it is the known one and is acceptable.

acceptance_criteria:
  - >
    MECHANICAL GATE: `(?<!03-)\bDB-[0-9]{3}\b` returns ZERO matches across PRODUCTION `src/`
    (all `*.py` excluding any path containing `tests\`, and excluding `migrations\`).
    Rationale for the scoping: 50 bare `DB-0\d\d` citations live in test files, which this block
    must not touch, so a literal repo-wide zero would be unsatisfiable without violating scope.
    Those 50 are routed to phase 11 and the Implementor must report the post-change test-file
    count as UNCHANGED at 50.
  - >
    `03-DB-004` is present at all 5 class-(a) sites: `advisory_lock.advisory_lock`, `ad_edit`,
    `bulk_approve`, `bulk_reject`, `bulk_delete`.
  - >
    Every rewritten comment remains self-contained — a reader who has never seen the id can
    still understand why the line exists, and no comment now dangles on a reference that no
    longer resolves.
  - >
    Each comment's TECHNICAL CLAIM is preserved verbatim; only the citation token was removed
    or phase-scoped. The Auditor re-verified all 18 claims at HEAD — do not "improve" them.
  - >
    NO EXECUTABLE CODE CHANGED: `git diff --stat` shows no changed line outside a comment or
    docstring. This is the block's defining constraint.
  - >
    No test file edited. No test name and no assertion changed. No `AdvisoryLockId` member added
    (BLOCK 2 owns advisory_lock's logic and its allocation table). No `src/backend/conftest.py`
    edit. No dated artefact under `docs/99-agent/` edited.
  - >
    `docs/99-agent/rules.md` gained exactly one `### Finding-id citations` subsection; the rest
    of that file is untouched.
  - >
    `uv run ruff check src/` and `uv run basedpyright src/` stay green. A comment change cannot
    break them — the proof is required, not assumed.
  - >
    The Docker suite shows no new failure (the known `test_search_slo.py` SLO test is the only
    tolerated one).
  - >
    The commit message records all four facts in `commit_message_requirements`, including the
    out-of-scope routing of the ~92 non-`DB` citations.
  - >
    Exactly one commit for the block, touching no more than the 6 production files plus
    `docs/99-agent/rules.md`.
```

**Tests required.**

- *Must be added:* **none.** A comment-only block cannot have a behavioural test, and writing one
  would be testing trivia. The mechanical census in `verification` is the substitute, and it is
  strictly stronger than a test.
- *Must be changed:* **none.** No test name and no assertion may change.
- *Must keep passing unchanged:* the **entire** suite.

**Exact gate commands (Docker only).**

```powershell
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk / rollback.**

- *Risk:* rewriting a comment in a file **another phase is editing right now**, causing a
  conflict or a clobbered edit. Re-read each file immediately before editing; stage explicit paths.
- *Risk:* **fabricating a cycle number** for one of the 13 class-(b) citations. Confidently-wrong
  is worse than ambiguous — the audit records are deleted and inference would invent provenance.
  Description is the required form.
- *Risk:* **widening the gate** to the ~92 non-`DB` citations across ~61 files. That is scope
  creep across other phases' active work (phase 06, phase 07 BLOCK 8) with real drift risk.
- *Risk:* an Implementor "helpfully" touches the nearby bare `AD-001` / `AD-002` / `ME-003`
  citations, or renames a test, or edits a dated audit artefact "while in there".
  **Explicitly forbidden.**
- *Risk:* a mechanical sweep reads as complete when it is partial. The commit-message routing
  sentence is the mitigation and is mandatory.
- *Risk:* the stale `advisory_lock.py` reserved-id sentence (`IDs 14-99`) — BLOCK 2 already
  updated it and it is consistent with `enums.py` (`REPAIR_BOT_USERNAME = 13`). **No action.**
- *Rollback:* comment- and doc-only; fully reversible with a single `git revert`.

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
| **Q9** | Does the shared advisory lock close the double-send, or is `find_matching_saved_searches`' missing `NOT EXISTS` the real hole? | BLOCK 9 | Researcher + Planner | **Must be closed inside BLOCK 9 before implementation.** **Adding the lock alone is provably insufficient.** A block shipping only Option A must record in its commit message that the concurrency path is unproven and that B remains required. **✔ CLOSED and unchanged by the 2026-10-03 decision round** — the re-publish decision is recorded as **coordinator-approved**, not a Product Owner ruling, and is left exactly as written |
| **Q10** | The delivery-state column: which states, who writes them, when, and what is the backfill? | BLOCK 9 | Planner | **Must be closed inside BLOCK 9 before implementation** (only if Q9 chooses Option B). The **nullable column with `NULL` backfill** is already binding; `NOT NULL DEFAULT false` is forbidden. **✔ CLOSED and unchanged by the 2026-10-03 decision round** |
| **Q11** | How is "lock held once across per-batch commits" achieved, given `pg_advisory_xact_lock` releases with the enclosing transaction? | BLOCK 7 | Researcher + Planner | **Must be closed inside BLOCK 7 before implementation.** Structurally unresolvable as written. Option C (timeout only) **does not fix the finding** and is not a substitute. |
| **Q12** | Which product rule — "a new draft replaces the current one" or "a second draft is rejected"? | BLOCK 10 | **Product Owner** | **✅ RESOLVED 2026-10-03 — Option A, "a new draft replaces the current one", ruled by the Product Owner as a DECISION.** **The earlier FIXED DEFAULT is superseded: the same option is now a recorded product decision, and the commit message must state that it was taken *by decision*, not by default.** It still matches shipped `create_draft_ad` behaviour and needs no new i18n. **Option C remains FORBIDDEN.** BLOCK 10's gate is closed and the block no longer carries a decision to make |
| **Q13** | `03-VAL-003`: `AD-005` vs `03-DB-001` severity | BLOCK 4 (advisory) | **Coordinator** | **DECIDED.** One work item, one severity: **MEDIUM**, shipped in BLOCK 4. The phase-05 re-rating is escalated, not silently decided. **Advisory — must not block the phase** (§3.2). |
| **Q14** | Cross-cutting: how does this cycle key its IDs, and are the shipped comments disambiguated? | BLOCK 11 | **Coordinator** | **Tracker half DECIDED:** `NN-<PREFIX>-00N`, recorded for phases 04–15. **Source half: FIXED DEFAULT is a RECORDED DE-SCOPE.** BLOCK 11 does not run; the three production citations this cycle polluted remain non-negotiable — two are handled inside BLOCK 2, `send_alerts.py` is handed to the coordinator. |

**Options NOT decided here, by instruction:** Q1, Q3, Q5, Q6, Q7, Q9, Q10, Q11 (technical,
Researcher/Planner, inside their blocks), and Q2.

**Answered by the Product Owner on 2026-10-03:** `Q12` only. Its disposition column now reads
`RESOLVED`, the option is unchanged (**A**), and the *character* of the answer changed — it is a
**recorded product decision**, not a plan-stated default. No other question in this table changed,
and none of Q1–Q11 or Q13–Q14 may be re-litigated.

**One follow-up remains deferred, with a named owner:** the "an edited live ad should re-alert"
product question and its **content-revision-epoch** recommendation (§2.9, BLOCK 9 notes 3 and 5).
It is **still deferred** — the 2026-10-03 round did not reach it. **Owner: the coordinator /
Product Owner**, carried as follow-up item (a) in BLOCK 9's acceptance criteria. The epoch remains
a **content-revision column, never `Ad.published_at`** (`published_at` is reset by
`ad_reactivate` too, so it would re-alert the content-neutral case).

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
| 1 | `task_03_b01_remove_storage_keys_precollection` | `03-DB-011` | Impl, Validator | — | — | — | ☑ | ☑ | `d9130883` |
| 2 | `task_03_b02_advisory_lock_release_log` | `03-DB-010` + `D-1` table fix | Impl, Validator | — | — | — | ☑ | ☑ | `7c7a27ec` |
| 3 | `task_03_b03_record_event_transaction` | `03-DB-002` | **All five** | **Q3, Q4** | — | — | ☑ | ☑ | `549c58e8` |
| 4 | `task_03_b04_create_draft_savepoint` | `03-DB-001` | Impl, Auditor, Validator | `03-VAL-003` *(advisory)* | — | — | ☑ | ☑ | `664b572e` |
| 5 | `task_03_b05_lock_timeout` | `03-DB-004` (timeout half) | **All five** | **Q1, Q2** | BLOCK 3 | — | ☑ | ☑ | `4db77ed`, `42d0edd`, `bb034e9`, `00ecc96b` |
| 6 | `task_03_b06_idle_timeout` | `03-DB-003` | **All five** | **Q5, Q6** | BLOCK 1 (soft) | `ads/0008_*` | ☑ | ☑ | `8ddfebc1`–`f45a7558` (8 commits) |
| 7 | `task_03_b07_per_batch_commit` | `03-DB-008` | **All five** | **Q11** | BLOCK 5 | — | ☑ | ☑ | `e61555f1` |
| 8 | `task_03_b08_media_promotion_window` | `03-DB-005` | **All five** | **Q7, Q8** | BLOCK 6 | None (A-prime: reuses `staging/`, no schema change) | ☑ | ☑ | `35441e0c` |
| 9 | `task_03_b09_immediate_alert_serialisation` | `03-DB-007` | **All five** | **Q9, Q10** | BLOCK 5, BLOCK 7 (order) | `search/0003_*` + `search/0004_*` | ☑ | ☑ | `7245f489` |
| 10 | `task_03_b10_single_draft_policy` | `03-DB-009` | Impl, Auditor, Planner, Validator | **`Q12` — RESOLVED 2026-10-03, Product Owner, Option A as a DECISION** (gate closed) | BLOCK 4 | — | ☑ | ☑ | `ba1b059a` |
| 11 | `task_03_b11_finding_id_disambiguation` | `03-VAL-001` | **All five** | **Q14** | — | — | ☑ | ☑ | `fd8c4235` |

### 5.3 Definition of done — phase 03

Distilled from the source plan §8 and **corrected where the tree at `ba23277` proves §8 stale**.

**Scope**
- [x] All 11 `03-DB-*` findings have a recorded disposition: **10 implemented** (`001`, `002`,
      `003`, `004` *timeout half only*, `005`, `007`, `008`, `009`, `010`, `011`), **1 rejected**
      (`006`, residue shown covered by `011`).
- [x] `03-DB-004`'s commit message states that the `ENT-006` addendum was already shipped by
      phase 01 and only the timeout half landed here — re-anchored **by symbol**
      (`test_migrate_locked.py::TestSessionLockAcquisitionLog::test_session_lock_logs_request_before_acquire`).
- [x] All 4 `03-VAL-*` findings have a recorded disposition: `VAL-001` tracker half **decided**
      and source half **shipped or explicitly de-scoped**; `VAL-002` landed as the `3 → 5`
      ordering edge and was honoured; `VAL-003` escalated (§3.2); `VAL-004` routed to the
      final report (§3.2).
- [x] **Every gated block (3, 5, 6, 7, 8, 9) has a written decision** naming the option
      chosen and the consequences accepted. Silence is not an acceptable outcome. BLOCK 10 is
      listed in that sweep for history only: its gate `Q12` is **RESOLVED — 2026-10-03,
      Product Owner, Option A taken as a DECISION**, and the commit body records that date and
      that it was a decision, not a default.
- [x] `03-DB-006`'s rejection is restated so it is not silently re-filed by a later phase.

**Gates — all green**
- [x] `uv run ruff check src/` → exit 0.
- [x] `uv run basedpyright src/` → **0 errors**.
- [x] `.\Makefile.ps1 test` → full suite green (seed marker skipped).
- [x] `.\Makefile.ps1 test-recreate` executed at least once after BLOCK 6's `ads/0008_*` and, if
      generated, after BLOCK 9's `search/0003_*` and BLOCK 8's `media/0002_*`.
- [x] `git status --short .ai` shows **no new modifications** beyond the 19 pre-existing
      `.ai/audit/**` deletions.
- [x] `git status --short docs` shows **no modifications beyond those an in-flight parallel phase
      had when this block started** — and no other phase's doc content was swept into a phase-03
      commit (**N-1**).
- [x] Every block's **exact gate command** was run and green — not the full suite alone.
- [x] ID-sweep: zero remaining ambiguous `DB-0\d\d` citations among the files BLOCK 11 was scoped
      to cover — **or** a recorded de-scope with the three non-negotiable production citations
      handled (two by BLOCK 2, `send_alerts.py` handed to the coordinator).
- [x] BLOCK 3's runtime probe was executed against the Docker test database **before** the fix,
      its result recorded, and the probe deleted (not committed).
- [x] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git stash`, `git add -A` or `git commit -a` was run at any point.

**Per-finding behavioural confirmation**
- [x] **`03-DB-001`** — with `uq_ads_single_draft_per_user` forced to fire, `create_draft_ad`
      **returns a draft** rather than propagating the driver error. `TestCreateDraftAdCrashRecovery`
      passes unchanged.
- [x] **`03-DB-002`** — inside a caller-owned `atomic()`, a **real server-side** error in
      `record_event` leaves the caller's business write **committed**; the test was demonstrated
      **red**. `submit_ad`'s roll-back-on-moderation-failure case passes unchanged. The ad-detail
      budget was **measured**: either `_QUERY_BOUND` was raised with a derivation, or the commit
      message records why the count did not change.
- [x] **`03-DB-003`** — a draft with an old `created_at` and a **recent** `updated_at`
      **survives**; an old `updated_at` **is deleted**; a heartbeat on a dialog step keeps the
      draft alive; `IX_ads_draft_sweep` is on `(status, updated_at)`; an expired draft produces
      the **translated**, seller-recoverable message, not the generic moderation text.
- [x] **`03-DB-004`** — a call holding a row lock ~1 s is **not** blocked indefinitely. All
      **eight** shipped ~1 s concurrency tests across **six** files (`D-3`) still assert what they
      mean. `record_event` handles the resulting `OperationalError`. No worker-count change.
- [x] **`03-DB-005`** — a sweep overlapping a `submit_ad` never deletes a file whose `AdImage`
      row commits, **and** files orphaned by a rolled-back submit are reclaimed within a bounded
      time. `AdImage.save()`'s content hash is identical before and after any promotion move.
- [x] **`03-DB-007`** — a failed `_run_send` followed by a `send_alerts` run **still delivers**.
      An already-delivered pair is **not** delivered twice. A pair delivered only by the daily
      path is still excluded by the immediate matcher. Pre-existing rows are `NULL` and not
      filtered. The feature still does nothing with the flag `False`.
- [x] **`03-DB-008`** — a failure in batch *N* leaves batches 1..*N*-1 **committed**. The lock is
      acquired **exactly once** and held across all batches. The queryset is re-derived per batch.
      `order_by("pk")` lock ordering is preserved, and **added** where missing, for
      `recompute_normalized_prices`. The test was demonstrated **red**.
- [x] **`03-DB-009`** — a seller with an existing `DRAFT` running `/copy` ends with the chosen
      option's outcome, and the same policy is demonstrably in force in **both** `create_draft_ad`
      and `copy_ad`. The failure message contains **no** raw driver text. `test_ad_copy.py`'s
      `"failed"` assertion passes unchanged.
- [x] **`03-DB-010`** — the release line is emitted on the **rollback** path as well as the normal
      path, the exception still propagates, `pg_advisory_xact_lock` is issued exactly once with no
      `pg_advisory_unlock` added to the transaction branch. Both rewritten tests were demonstrated
      **red**.
- [x] **`03-DB-011`** — no `storage_keys` and no dead `ad_ids` remain in the six commands;
      `delete_photo` still runs **exactly once** per key; `consent_hard_delete` still logs its
      user count and keeps `user_ids`.
- [x] **`03-VAL-001`** — `advisory_lock.py` no longer contains two different `DB-010` references
      three lines apart, this cycle's own citations are cycle-scoped, and the allocation table
      lists all **19** ids with the reserved range stated as **14–99** (`D-1`).

**Cross-phase integrity**
- [x] `test_migrate_locked.py::TestSessionLockAcquisitionLog` passes **unchanged**.
- [x] The earlier cycle's `send_alerts` idempotency behaviour is intact, verified **by symbol**
      (`SchedulerDailyMarker`, `_DIGEST_AD_LIMIT`) — **not** by the hash `fbbb6cf` (`D-2`).
- [x] `ENT-009` is recorded as **absorbed** by `03-DB-003`, not re-shipped.
- [x] `src/backend/conftest.py` is **unmodified**.
- [x] `AdvisoryLockId` gained **no new member**, or the three artefacts (`enums.py`,
      `advisory_lock.py`'s table, `test_advisory_lock_ids.py`) changed in one commit and the
      coordinator was notified **before**.
- [x] No `apps/*` module imports `telegram_bot/*`.
- [x] `copy_ad`'s storage-key reuse and `delete_adimage_files_on_delete` are unchanged
      (`AD-003`, phase 05).
- [x] Recipient-selection logic in `find_matching_saved_searches` is unchanged beyond the
      delivery-state filter (`PII-104`, phase 06).
- [x] `CONN_MAX_AGE` / connection lifecycle is unchanged; the asgiref worker count is unchanged.
- [x] Migration numbers were checked against their directories **immediately before** generation;
      `apps/core/migrations/` gained nothing in this phase.
- [x] `docs/02-database/db-retention.md` no longer claims *"no lock timeout is configured"* and
      its `sweep_drafts` row states inactivity, not creation age; `db-indexes.md` matches
      `IX_ads_draft_sweep`. **No other document was edited** (`N-3`).
- [x] Locale files were **appended** to, never regenerated wholesale; `ru` and `bs` `msgstr` are
      non-empty for every new string.
- [x] No new dependency was added (`uv.lock` unchanged).

**Project conventions**
- [x] Every new constant is a named module-level constant or a `StrEnum`/`IntEnum` member.
- [x] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [x] All comments, docstrings, log messages and error messages are in **English**.
- [x] Every `with transaction.atomic():` carries the project's established pyright suppression (or
      an honest typed equivalent).
- [x] Business logic lives in `services/`; no new logic in a view or handler beyond the thin
      boundary change its block requires.
- [x] Every non-trivial behaviour change has a test that verifies **logic and component
      interaction** — not a variable's absence, not a log string, not a line count. (This is why
      BLOCK 1 and BLOCK 11 add **no** tests.)
- [x] Filesystem side effects happen only **after** commit, via `transaction.on_commit()`.
- [x] No task target is a line number; every target is a file plus a semantic symbol.
- [x] `uv run ruff check --fix src/` was run if imports were reordered.
- [x] New test code is bandit-clean (list-form `subprocess.run([sys.executable, …])`, no literal
      `/tmp`).

**Deliverables**
- [x] The `03-VAL-003` re-rating request for phase 05's `AD-005` is recorded and communicated to
      the coordinator — **not** silently decided.
- [x] The `03-VAL-004` evidence-quality note is recorded for the final report, including every
      runtime claim that was **not** re-derived.
- [x] The `03-VAL-001` convention (`NN-<PREFIX>-00N`) is recorded and handed to the phases
      04–15 coordinators, so twelve plans do not invent twelve conventions.
- [x] The status table in §5.2 is complete.
- [x] No commit was made without an explicit user request.
