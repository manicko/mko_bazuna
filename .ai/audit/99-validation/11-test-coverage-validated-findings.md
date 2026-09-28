# Phase 11 — Test Coverage & Test Suite Quality — Validated Findings

> **Scope of this document.** Self-contained validation of
> `.ai/audit/11-test-coverage/findings.md` (13 findings, `TEST-001`…`TEST-013`) against
> the working tree at **`9e96b84`**. Finding IDs are preserved verbatim; none were
> renumbered. One finding was added (`TEST-014`) and two validation-level findings
> (`VAL-001`, `VAL-002`) were raised. Every verdict below was reached by reading the
> shipped source, by AST/static analysis performed in this validation, and by
> re-executing the local static-analysis toolchain. The test suite was **not**
> re-run (see §Evidence Not Reproduced).
>
> **Mode:** `problems_only = TRUE`. Passes are recorded in §Advisory, not as findings.
>
> **Prefix note (carried forward).** `TEST-` is used because `TST-001`…`TST-005`
> exist as in-source provenance markers. Key the remediation tracker on
> **`11-TEST-0NN`**, not on `TEST-0NN`.

---

## 1. Verdict Table

| ID | Verdict | Severity (was → is) | One-line justification |
|----|---------|---------------------|------------------------|
| **TEST-001** | **ADJUSTED** | CRITICAL → **HIGH** | The fixture default and the 111 count are both exactly right (independently re-derived), but CRITICAL is unsupported — the consequence is a test-fidelity defect that *gates* AD-008, not a demonstrable severe consequence; and the "must all land in one commit" constraint is refuted. |
| **TEST-002** | **ADJUSTED** | HIGH (held) | Mechanism confirmed byte-for-byte; consequence #2 ("`src/telegram_bot` is absent from the report") is **refuted** — the bot *is* measured, just without branch coverage and with `omit` ignored. |
| **TEST-003** | **ADJUSTED** | HIGH (held) | The coverage gap and the missing per-test bound are both confirmed; the `EXPLAIN`-only kill table is unverified and self-inconsistent, the quoted code is not the shipped code, and the recommended `SET LOCAL` is a no-op for `transaction=True` tests. |
| **TEST-004** | **CONFIRMED** (evidence corrected) | HIGH (held) | All four production `on_commit` sites verified at the exact cited lines and both mock-out sites verified; one supporting evidence cell is false, which *strengthens* the finding. |
| **TEST-005** | **ADJUSTED** | HIGH → **MEDIUM** | "Zero tests cross the web/bot boundary in either direction" is **refuted** — at least five static cross-tree tests exist and the report's own Appendix B credits one; the concurrency claim is largely already covered. |
| **TEST-006** | **ADJUSTED** | MEDIUM (held) | The gap survives but is narrower than stated: U+200B (a format-class invisible character) *is* tested; C0/NUL is not. The "zero NUL test hits" evidence is false. |
| **TEST-007** | **CONFIRMED** (evidence corrected) | MEDIUM (held) | Model and service claims exactly right (`no unique`, `no Meta.constraints`, `get_or_create` dedup); the quoted docstring does not exist. |
| **TEST-008** | **ADJUSTED** | MEDIUM (held) | Core claim right, but the seed is persisted in `.pytest_cache/v/cache/randomly_seed` and reused on re-runs, so local reproduction is already possible; only the CI-log gap is real. |
| **TEST-009** | **CONFIRMED** (evidence corrected) | MEDIUM (held) | No `timeout` key, no `--timeout`, no `--reruns` — confirmed. The cited `timeout-minutes: 30` **does not exist anywhere in the workflow** (0 hits), which makes the gap worse than reported. |
| **TEST-010** | **CONFIRMED** | MEDIUM (held) | Exact: 27 `inspect.getsource` sites, per-file distribution 7/5/4/4/3/2/1/1 reproduced precisely. |
| **TEST-011** | **ADJUSTED** | MEDIUM (held) | The `DisableMigrations` mechanism is right, but the named target migrations **do not exist** (no squash migration, no search-vector backfill migration); replaced with the four real data migrations. |
| **TEST-012** | **ADJUSTED** | MEDIUM (held) | The premise is **refuted** — `apps/core/tests/test_support_admin.py` already contains 12 registered-`ModelAdmin` introspection tests; the operative gap (`get_form` / `get_actions` / page render) survives and the remedy is an extension, not a new module. |
| **TEST-013** | **ADJUSTED** | LOW (held) | Error counts confirmed exactly (12 in the CI scope, 2 in the bot tree, both exit 1) but the per-file distribution is wrong — all 12 are in **two** files from **one** root cause, not six files from four. |
| **TEST-014** *(new)* | **CONFIRMED** | **MEDIUM** | `transaction.on_commit` is structurally unreachable in 2 of 4 production call sites, and MEDIA-001's remediation would be verified by exactly 3 tests in 1 file. |
| **VAL-001** *(new)* | **CONFIRMED** | MEDIUM | The report's anchor commit `0c91666` does not exist in the repository; at least nine code citations are stale. |
| **VAL-002** *(new)* | **CONFIRMED** | MEDIUM | The "bare `TestCase`" exposure framing used to scope this phase is inapplicable — **zero** `TestCase` subclasses exist. The real exposure is via `pytest.mark.django_db`. |

**Totals:** 13 auditor findings → 2 CONFIRMED unchanged (`TEST-010`, and `TEST-004`/
`TEST-007`/`TEST-009` confirmed-with-corrections), 9 ADJUSTED, 0 REJECTED, 0 MERGED
into another phase's finding. 1 new finding (`TEST-014`), 2 new `VAL-` items.

**No finding was rejected outright.** Every `TEST-` finding names a real, still-present
gap. The failures in this report are of *precision*, not of *substance* — which is
itself a finding about the phase's method (§VAL-001).

---

## 2. Cross-Phase Reconciliation

### 2.1 The 111-vs-34 discrepancy — **RESOLVED. TEST-001's 111 is correct; phase 05's VAL-002 is an undercount.**

Both numbers were reproduced from the same tree, and the difference is entirely
explained by counting method.

| | Counting method | Result |
|---|---|---|
| **Phase 05 VAL-002** | `grep -rn "status=AdStatus\.ON_MODERATION\)"` over `src/` | **34** matches in **10** files |
| **Phase 11 TEST-001** | AST scan of every `create_test_ad` / `create_test_ads_bulk` call, resolving the factory default | **111** in **19** files |
| **This validation** | Independent AST scan, same method as TEST-001 | **111** in **19** files — **exact match** |

**Why the grep undercounts, decomposed:**

1. **Two of the 34 grep hits are production code, not tests.**
   `apps/analytics/services/moderation_analytics.py:108` and
   `apps/moderation/admin_actions.py:162`. That is where phase 05's "10 files" comes
   from: 8 test files + 2 source files.
2. **One of the remaining 32 is not a construction site** —
   `apps/analytics/tests/test_moderation_analytics.py:379` is
   `Ad.objects.filter(status=AdStatus.ON_MODERATION).delete()` (a cleanup), leaving
   **31 explicit single-line construction sites**.
3. **18 explicit sites are invisible to the grep** because the call is multi-line and
   the `)` is not adjacent to `status=` (e.g.
   `apps/moderation/tests/test_moderation_views.py:266`).
4. **62 sites are invisible to any grep of `status=`** because they omit the argument
   entirely and inherit `create_test_ad`'s default — which *is* `ON_MODERATION`.
   Concentrated in `apps/moderation/tests/test_priority.py` (24),
   `test_priority_service.py` (27), `test_auto_moderation.py` (6),
   `test_price_normalizer.py` (3), `test_moderation_views.py` (1),
   `src/telegram_bot/tests/test_ad_lifecycle.py` (1).

`31 + 18 = 49` explicit, `+ 62` defaulted = **111**. The arithmetic closes exactly.

**Consequence for budgeting AD-008 (§Cross-Phase Impact):** phase 05's remediation
table and this report's remediation table must both be corrected to **111 sites in 18
test files** (plus `src/backend/conftest.py` itself as the 19th file, since the factory
definition is what must change). Use the TEST-001 figure. Do not use 34.

**Additional sites the AST scan surfaced that neither report counted:** 11
`transition_to(AdStatus.ON_MODERATION)` call sites, of which 2 are production
(`apps/ads/services/submission.py:230`, `apps/ads/views/edit.py:338`) and 9 are tests
(`test_ad_constraints.py:194`, `test_ad_lifecycle.py:50/124/144/152/173`,
`test_sweep_archive.py:191`, `src/telegram_bot/tests/test_ad_lifecycle.py:44/215`).
These assert the transition *rule*, not a fabricated durable row, and need no change —
but the total "rows a test asserts in `ON_MODERATION`" is **119**, not 111. Separately
confirmed: **zero** raw `Ad.objects.create(status=ON_MODERATION)` sites and **zero**
`.update(status=ON_MODERATION)` sites exist, so the factory is the only fabrication path.

### 2.2 TEST-003 ↔ SRCH-001 (Phase 08, CRITICAL) ↔ DB-004 (Phase 03, HIGH) — **complementary, not duplicative. Do not ship three fixes.**

```
                     ┌─────────────────────────────────────────────┐
   ATTACKER INPUT    │ SRCH-001 (Phase 08, CRITICAL)               │
   (N × ?features=)  │ "the join loop is unbounded — cap the input" │
                     └───────────────┬─────────────────────────────┘
                                     │  a cap is necessary but NOT sufficient
                     ┌───────────────▼─────────────────────────────┐
   RESOURCE BOUND    │ DB-004 (Phase 03, HIGH)                     │
   (any long stmt)   │ "no lock_timeout / statement_timeout exists" │
                     └───────────────┬─────────────────────────────┘
                                     │  without it, a *legitimate* large
                     │  filter set is still unbounded
                     ┌───────────────▼─────────────────────────────┐
   TEST HOSTABILITY  │ TEST-003 (this phase, HIGH)                 │
   (the suite)       │ "no per-test bound — the regression test    │
                     │  cannot be written without taking the DB    │
                     │  offline"                                   │
                     └─────────────────────────────────────────────┘
```

- **SRCH-001 owns the defect.** Phase 08's validator reproduced it end-to-end on an
  isolated PG 18: 20 slugs → 1.31 s, 40 → 7.88 s, 60 → 19.90 s, then
  `signal 9: Killed` → `all server processes terminated; reinitializing`. Already
  validated CRITICAL. **Not re-filed here.**
- **DB-004 owns the production-side bound.** Independently reconfirmed in this
  validation: a search for `statement_timeout|lock_timeout|idle_in_transaction_session_timeout`
  across every `.py/.sh/.yml/.yaml/.toml/.conf/.ps1` file under `src/` and `docker/`
  returns **0 matches**, and `config/settings/test.py` has no `OPTIONS` block on
  `DATABASES["default"]`. Already validated HIGH. **Not re-filed here.**
- **TEST-003 owns only the test-hosting half**, and that half is real: see §3.3.

**Do not double-count.** A single change — a `statement_timeout` — is what makes both
the production bound (DB-004) and the test-hosting bound (TEST-003) possible. They are
one remediation with two callers, and the *test-side* one is strictly a subset.

**Evidence correction on TEST-003's crash table (do not carry it forward).** The
report's `EXPLAIN`-only measurements (10 → 0.99 s, 50 → 44.30 s, 100 → backend
terminated) are internally inconsistent with SRCH-001's `ANALYZE` measurements
(60 → 19.90 s): a 50-slug *plan-only* query cannot cost more than a 60-slug
*execute* query by that margin. Only the qualitative claim — that the planner cost is
superlinear in the number of slugs — is safe to carry. **This validation did not
reproduce the crash**, deliberately: the shared test instance was in use by other
phases, and phase 08's own probe already terminated the cluster twice (its VAL-004).
Phase 08's independently-validated `ANALYZE` numbers are the authoritative measurement.

### 2.3 TEST-014 ↔ MEDIA-001 / Phase 07 VAL-003 — **the missing half of a rollback-safety record.**

Phase 07 VAL-003 already recorded that "a reference check in `pre_delete` invalidates
three tests that assert the current unconditional behaviour —
`apps/core/tests/test_ad_image_delete_signal.py:38`, `:74`, `:117`". This validation
independently arrived at **the same three tests** and adds the reason, which phase 07
did not state: they are the **only** tests in the entire media surface that run under
`django_db(transaction=True)`, and therefore the only three in which the `on_commit`
callback that MEDIA-001's fix modifies actually fires. See §3.15 for the full
quantification. Phase 07 owns the MEDIA-001 fix; **TEST-014 owns the fact that the fix
would be almost unverified.** They must be read together, and TEST-014's
`transaction=True`-scaffold requirement must be satisfied *before* MEDIA-001 lands.

### 2.4 Findings deliberately **not** re-filed

| Other phase's ID | Relationship to this report | Decision |
|---|---|---|
| `AD-008` / `VAL-002` / `VAL-003` (Phase 05) | TEST-001 measures the *test-side cost* of AD-008 | TEST-001 retained as a coverage finding; AD-008/VAL-003 remain the production record. **Both `34` figures in Phase 05 must be corrected to `111`.** |
| `SRCH-001` (Phase 08) | Same defect, test-coverage view | Cross-reference only. |
| `DB-004` (Phase 03) | Same missing bound, production view | Cross-reference only. |
| `PopularSearch` missing `UNIQUE` (Phase 08) | The constraint; TEST-007 is its coverage gap | Cross-reference only. |
| `NUL → 500` (Phase 08) | The defect; TEST-006 is its coverage gap | Cross-reference only. |
| `AUT-005` / `PII-103` / `PII-107` (Phases 04/06), `AD-001` (Phase 05) | Admin-surface defects no test can see; TEST-010/TEST-012 are the coverage gap | Cross-reference only. |
| `ENT-004` (Phase 01) | Root cause of TEST-013 | **Explicitly owned by ENT-004.** TEST-013 is recorded as the test-gate view only, and must not be actioned twice. |
| `DB-001` (Phase 03), `AUT-002` (Phase 04), `PII-104` (Phase 06) | Cross-process risk examples cited by TEST-005 | Cited as risk, not re-filed. |
| `MEDIA-001` / `MEDIA-002` (Phase 07) | Phase 07 owns the fixes; TEST-014 measures their verifiability | Cross-reference only — see §2.3. |

### 2.5 Internal contradictions inside the phase-11 report (evidence quality)

These are recorded because they affect how much weight the report's negative claims
can carry. All are corrected in §3.

| # | Contradiction | Resolution |
|---|---|---|
| 1 | §2 TEST-005: "zero tests cross the web/bot boundary in either direction" vs Appendix B item 4: "`test_contact_gate.py` in the bot tree proves **both processes** delegate to the same `_check_seller_contactable` helper" | Appendix B is right. The headline claim is narrowed in §3.5. |
| 2 | §2 TEST-003 quotes a `features_qs`/`OuterRef` subquery block at `listings_query.py:181-186`; the shipped code at `:183-186` is a plain `ads.filter(features__slug=slug)` loop | Quoted code struck; the structural claim (one JOIN per slug, unbounded) stands. |
| 3 | §2 TEST-001 cites `ad_reactivate` as `submission.py:161-199`; `submission.py` has no such function — it is the view at `apps/ads/views/edit.py:307-347` | Conclusion unchanged (`auto_moderate` runs in the same `atomic()` block); citation corrected. |
| 4 | §2 TEST-001's per-file table (`test_moderation_views.py` 58, `test_priority_service.py` 14, `test_edit.py` 13) does not match any counting method; measured values are 14, 27, 1 | Per-file table withdrawn; the 111 total is retained (§2.1). |
| 5 | §2 TEST-004's inventory says `test_ad_image_delete_signal.py` asserts files are "still present on rollback"; that file has no rollback test | Cell removed — which makes the finding *stronger*, not weaker (§3.4). |
| 6 | §2 TEST-006 says a grep for NUL returns "zero test hits"; two exist (`test_media_security.py:517`, `test_filesystem.py:437`) | Claim narrowed to the `?q=` path (§3.6). |
| 7 | §2 TEST-012 says "not one test" introspects a registered `ModelAdmin`; `test_support_admin.py` has 12 such tests | Premise corrected; the operative gap survives (§3.12). |

---

## 3. Per-Finding Validation

### 3.1 TEST-001 — `create_test_ad` defaults to an uncommittable ad state — **ADJUSTED, CRITICAL → HIGH**

**What is confirmed, exactly.**

- `src/backend/conftest.py:290` — `status: AdStatus = AdStatus.ON_MODERATION` in
  `create_test_ad`. **Verified.**
- `src/backend/conftest.py:333` — the same default in `create_test_ads_bulk`. **Verified.**
- `ON_MODERATION` is never committed by any production writer. **Verified, both writers:**
  - `apps/ads/services/submission.py:230` calls `ad.transition_to(AdStatus.ON_MODERATION)`
    inside the `transaction.atomic()` opened at `:169`, then calls `auto_moderate(ad)` at
    `:241` **inside the same block**.
  - `apps/ads/views/edit.py:338` (`ad_reactivate`) does the same inside the
    `transaction.atomic()` opened at `:321`, calling `auto_moderate(ad)` at `:343`.
  - `auto_moderate()` has no third exit: every path returns via `_pass_moderation`
    (`ON_MODERATION_FAILED` → `PUBLISHED`) or `_fail_moderation`
    (`ON_MODERATION_FAILED`). There is no `return` that leaves the ad in
    `ON_MODERATION`. **Verified** by reading all 9 validation branches.
- **The count: 111, in 19 files. Independently reproduced.** See §2.1 for the
  decomposition. This is the single most important number in the report and it is correct.

**Why CRITICAL is not supported — the severity decision, stated explicitly.**

CRITICAL in this rubric is reserved for a *demonstrable severe consequence*: data loss,
an outage, an authorisation bypass, or a test that actively **pressures production code
to be distorted**. TEST-001 has none of those.

- The fixture lies. That is real. Its consequence is **green tests over an unreachable
  state** — a *fidelity* defect.
- No user-visible, availability, security or data-integrity consequence attaches to the
  fixture itself. The severe consequence attaches to **AD-008** (a dead human-approval
  path, phase 05 VAL-003), which is a *different* finding in a *different* phase, already
  validated, and already carrying its own severity.
- Counting the *same* defect twice — once as the production defect (AD-008) and once as
  the test defect (TEST-001) — and rating the test-side copy CRITICAL inflates the
  roll-up. The production side is the one with the consequence.
- TEST-001's own framing concedes the limit: "the fixture lies, so 111 tests assert a
  state that cannot exist." That is a test-contract defect.

**Verdict: HIGH.** It stays HIGH rather than MEDIUM because it has three concrete,
non-hypothetical costs: (a) it is the documented reason all 32 of phase 05's moderation
checks passed against broken behaviour; (b) it is a live `[DOC-UPDATE]` defect — the
project's own agent rules misdescribe the default (below); (c) it materially changes how
much work an AD-008 remediation carries, so it must not be discovered late.

**Additional confirmed defect found by this validation — the project rules are wrong.**

`.kilo/rules/commands.md:70` instructs: *"Use `create_test_ad(user, category, city, *,
status=AdStatus.PUBLISHED, **kwargs)`"* — i.e. it documents the default as `PUBLISHED`.
The code says `ON_MODERATION`. Every agent and developer following the rules will
mis-predict what a bare `create_test_ad(...)` produces. (`docs/99-agent/rules.md:53`
gives different, *also* misleading advice — *"Add `status=AdStatus.PUBLISHED` explicitly
if the test requires it"* — which implies the default is not published. Both files need
correcting; the finding named only the second as wrong.)

**The "one commit" claim is REFUTED — the rollout hazard is real but smaller.**

The report asserts: *"fixing AD-008 requires rewriting the fixture contract AND migrating
all 111 sites in ONE commit"* and *"a half-migrated fixture is worse than either end
state."* Both are wrong, and the difference is worth real effort.

- **Whether the 111 sites need migrating at all depends on a product decision this phase
  did not consider.** Phase 05's validator was explicit: *"Do not action the auditor's
  'drop `ON_MODERATION` from the durable set' branch before VAL-003 is resolved — that
  branch deletes the queue the business asked for in US-A12."* If AD-008 is fixed by
  **making `ON_MODERATION` durable** (auto-moderation that defers to a human, so the
  ad really does sit in `ON_MODERATION` waiting for `approve_ad`), then **all 111 sites
  become correct and need no change.** The whole migration evaporates.
- The fixture fix is itself a **two-commit, each-green** sequence, not one:
  1. add an explicit `status=` to the 62 defaulted sites → **green** (behaviour identical,
     the default is still `ON_MODERATION`).
  2. flip both defaults to `PUBLISHED` → **green** (the 62 now pass their explicit value;
     the 49 explicit sites are unaffected).
  Nothing goes red at any point. The report's "must not be split" is over-constrained.
- The **genuine** must-land-together constraint is the one phase 07 already stated: a
  *test-EXPECTATION* change must land in the same commit as the production change it
  follows from. That applies to any `ON_MODERATION → ON_MODERATION_FAILED/PUBLISHED`
  expectation flip — which only becomes necessary under the "remove the durable state"
  branch, and that branch should not be taken.

**Corrected recommendation (production code untouched; the fixture is test code):**

1. **Decide AD-008's resolution direction first** (product decision, phase 05's owner).
   This determines whether the 111-site migration happens at all. Do not migrate first.
2. Add explicit `status=` at the 62 defaulted sites (mechanical, behaviour-preserving).
3. Flip both factory defaults to `AdStatus.PUBLISHED`; consider making `status`
   **required** in `create_test_ad` as well, so the "interesting variable" is always
   explicit. This is the change that actually prevents recurrence.
4. Correct `.kilo/rules/commands.md:70` and `docs/99-agent/rules.md:53` in the same
   commit as step 3.
5. Re-measure. My corrected per-file distribution is in §3.1a; use it, not the report's.

**Effort:** **S** for steps 2–4 (not M). Step 1 is a product decision, not work.

#### 3.1a Corrected per-file distribution (replaces the report's table)

`explicit` = `status=AdStatus.ON_MODERATION` passed; `defaulted` = `status` omitted,
inheriting `ON_MODERATION`.

| File | explicit | defaulted | total |
|---|---|---|---|
| `apps/moderation/tests/test_priority_service.py` | 0 | 27 | 27 |
| `apps/moderation/tests/test_priority.py` | 0 | 24 | 24 |
| `apps/moderation/tests/test_moderation_views.py` | 13 | 1 | 14 |
| `apps/moderation/tests/test_admin_actions.py` | 12 | 0 | 12 |
| `apps/moderation/tests/test_moderation_side_effects.py` | 5 | 0 | 5 |
| `apps/moderation/tests/test_approve_ad_side_effects.py` | 4 | 0 | 4 |
| `apps/moderation/tests/test_moderation_log.py` | 3 | 0 | 3 |
| `apps/analytics/tests/test_moderation_analytics.py` | 3 | 0 | 3 |
| `apps/moderation/tests/test_auto_moderation.py` | 1 | 6 | 7 |
| `apps/search/tests/test_search_view.py` | 2 | 0 | 2 |
| `apps/search/tests/test_search_cache.py` | 1 | 0 | 1 |
| `apps/users/tests/test_consent.py` | 1 | 0 | 1 |
| `apps/users/tests/test_deletion.py` | 1 | 0 | 1 |
| `apps/ads/tests/test_edit.py` | 1 | 0 | 1 |
| `apps/ads/tests/test_transition_concurrency.py` | 1 | 0 | 1 |
| `apps/core/tests/test_contact.py` | 1 | 0 | 1 |
| `apps/currencies/tests/test_price_normalizer.py` | 0 | 3 | 3 |
| `src/telegram_bot/tests/test_ad_lifecycle.py` | 0 | 1 | 1 |
| **Total** | **49** | **62** | **111** |

Plus `src/backend/conftest.py` itself (the two defaults) — the 19th file.

---

### 3.2 TEST-002 — CI never loads `[tool.coverage.*]` — **ADJUSTED, HIGH held**

**Mechanism: confirmed byte-for-byte, twice, by two independent methods.**

1. **Source reading.** `.github/workflows/ci.yml:133-139` runs pytest with
   `working-directory: src/backend` and a bare `--cov` (no value). There is exactly
   **one** `pyproject.toml` in the repository (repo root); `src/backend/pyproject.toml`
   does not exist. The CI job's "Install dependencies" step runs from `src/backend`
   purely via `uv`'s upward project discovery.
2. **Measurement.** Constructing a bare `coverage.Coverage()` from each working
   directory:

   ```
   CWD = src/backend  ->  config_file=None   branch=False source=None           fail_under=0.0  omit=0
   CWD = repo root    ->  config_file=<root pyproject.toml>  branch=True
                          source=['src/backend','src/telegram_bot']  fail_under=80.0  omit=7
   ```

   `coverage.py` resolves its configuration from the **current working directory only**;
   it does not walk upward. Confirmed by measurement, not by documentation reading.
3. **The plugin path.** `pytest_cov/plugin.py:184` — bare `--cov` normalises to
   `cov_source = None`; `pytest_cov/engine.py:237-241` then constructs
   `coverage.Coverage(source=None, branch=None, config_file=self.cov_config)`. So the
   entire result depends on the CWD-only config search.

**Consequences — three confirmed, one refuted.**

| # | Claimed consequence | Verdict |
|---|---|---|
| 1 | `fail_under = 80` is not enforced in CI; `coverage.xml` is uploaded as an artifact and nothing can fail on it | **CONFIRMED.** `ci.yml:153-158` is the only consumer of `coverage.xml` (`upload-artifact`, `retention-days: 30`). There is no codecov/quay/coveralls integration, no threshold step, and no `pytest-cov` exit-code path that could trip (`--cov-fail-under` is absent). Coverage could fall to 30% and CI stays green. |
| 2 | `src/telegram_bot` is absent from the CI coverage report | **REFUTED — see below.** |
| 3 | `omit` is ignored, so `conftest.py` / `testing/*.py` are measured as production code | **CONFIRMED.** `omit` lives in the same `[tool.coverage.run]` table that was not loaded, so all 7 patterns are void. |
| 4 | Local and CI numbers are not comparable | **CONFIRMED, and worse than reported.** |

**Why consequence #2 is refuted.** The report's premise is that the bot tests are not
part of the CI run. They are. Measured:

```
determine_setup(args=['<repo>/src/backend'])
  -> rootdir = <repo root>
  -> inipath = <repo root>/pyproject.toml
  -> testpaths = ['src/backend', 'src/telegram_bot']
```

pytest's `rootdir` discovery **does** walk upward and finds the root
`[tool.pytest.ini_options]`; only coverage.py's config search does not. So the CI run
resolves `testpaths` from the repo root, collects **both** trees, and executes all
2 394 tests including the 190 bot tests. With `source=None`, coverage.py's
`InOrOut.should_trace` traces everything except the stdlib and site-packages
(`inorout.py:455-458`), so `src/telegram_bot/**` modules that execute **are** measured
and **do** appear in the report.

**The accurate statement of consequence #2** — and it is still a genuine problem:

> The bot process *is* measured in CI, but with `branch=False` and with `omit` ignored.
> Its ~190 test files, both `conftest.py` files, all `tests/` packages and the
> `testing/` helpers are counted in the denominator, and branch coverage is not measured
> at all. **The bot's number is not comparable to any human-read number, and no
> threshold is applied to it.** The team's belief that CI measures the bot tree with
> branch coverage at an 80 % floor is false; CI measures it with no branch coverage, no
> exclusions, and no gate.

This is *still* HIGH: the belief gap is real, the phase handbook itself asserts
"80 % branch coverage gate" (`.kilo/commands/audit/phases/11-audit-test-coverage.md:291`),
and the blind spot is the half of the system other phases found thinnest coverage for.

**The remedy in the report is correct and still valid.** `working-directory: .` on the
pytest step (line 133) makes CWD the repo root, which is simultaneously the pytest
rootdir and the coverage config root; `testpaths` and `pythonpath` are already
rootdir-relative, so nothing else changes. Verify by asserting the log contains
`Required test coverage of 80.0% reached` and that the term report shows `Branch` /
`BrPart` columns.

**Effort:** S. **Unchanged.**

---

### 3.3 TEST-003 — No `?features=` bound test; the suite cannot host one — **ADJUSTED, HIGH held**

**Confirmed.**

- The join loop is unbounded. `apps/ads/services/listings_query.py:183-186`:
  ```python
  if params.feature_slugs:
      for slug in params.feature_slugs:
          ads = ads.filter(features__slug=slug)
      ads = ads.distinct()
  ```
  One JOIN per slug, no cap.
- The DTO has no bound. `listings_query.py:57`:
  `feature_slugs: list[str] = Field(default_factory=list)` — no `max_length`, no
  validator.
- Both entry points pass the raw repeated parameter through unfiltered:
  `apps/ads/views/listings.py:250` and `apps/search/views/search.py:101` —
  `request.GET.getlist("features")`.
- The coverage gap is real and slightly *worse* than stated. Across the whole test tree
  only 5 files ever send a `?features=` parameter, and the three requests in
  `apps/ads/tests/test_features_filter.py` (`:52`, `:71`, `:86`) use **two** slugs
  maximum. **The largest `?features=` list anywhere in the suite is 2.** The report
  cited 7 request sites; there are 3, all in one file, plus 1 in
  `test_filter_search_combine.py` and 1 in `test_seed.py`.
- Nothing bounds a runaway query in the test environment. `config/settings/test.py` has
  no `OPTIONS` on `DATABASES["default"]` (it sets only `NAME` at line 28), and the
  repo-wide search for `statement_timeout|lock_timeout|idle_in_transaction_session_timeout`
  returns **0 matches** across `src/` and `docker/`. **Independently reconfirmed here.**

**So the dependency claim is correct: the missing per-test bound is a genuine
prerequisite, not a stylistic preference.** A hostile-`?features=` test written today
would OOM the shared PostgreSQL instance, taking all 22 databases (including 17 xdist
worker databases) offline and failing the whole run plus any concurrent run. That is
exactly what happened to phase 08's probe. It is highly plausible this is *why* the test
was never written, and that is a real cost of the current state.

**Three corrections.**

1. **The quoted code does not exist.** The report's evidence block shows an
   `AdFeature.objects.filter(ad_id=OuterRef("pk"), …)` / `if features_qs.exists()`
   subquery-join construction. That is not the shipped implementation. Strike the block;
   the shipped loop above is cited instead. Same defect, different code, and an
   implementer following the report would be looking for the wrong thing.
2. **The `EXPLAIN`-only crash table is not carried forward** — see §2.2. It is
   internally inconsistent with SRCH-001's validated numbers and was not reproduced
   here, deliberately, to avoid another shared-instance outage. The **qualitative**
   claim (superlinear planner cost) is retained; the numbers are not.
3. **The recommended fix is subtly wrong for half the suite.** The report says
   "`SET LOCAL statement_timeout` in an autouse fixture". In PostgreSQL, `SET LOCAL`
   outside a transaction block is a **no-op**. The 46 `transaction=True`-marked scopes
   (including the whole bot tree) run with no wrapping transaction, so a `SET LOCAL`
   there sets nothing and the runaway query is unbounded precisely where the concurrency
   tests live.

**Corrected recommendation.**

1. Set the bound in `config/settings/test.py` as a connection option —
   `DATABASES["default"]["OPTIONS"] = {"options": "-c statement_timeout=10000"}` (or
   equivalently `SET statement_timeout` in a session-scoped fixture, with a `RESET` in
   teardown). This covers *every* test, transactional or not, and it is test
   configuration, not production code. Coordinate the value with **DB-004** so the
   test and production bounds do not drift.
2. Only then add the hostile-`?features=` test, landing it with SRCH-001's production
   cap in one commit.
3. Item 3 of the report (a `max_length` on `feature_slugs`) is **phase 08's**, correctly
   excluded. Confirm: not re-filed here.

**Effort:** S for item 1, S for item 2. **Lower than the report's "M".**

---

### 3.4 TEST-004 — Alert `on_commit` ordering mocked away, no rollback-negative test — **CONFIRMED, HIGH held**

**Confirmed, with the inventory verified line by line.** All four production
`transaction.on_commit` call sites exist at exactly the cited locations:

| Production site | Line | Deferred action | Real coverage? |
|---|---|---|---|
| `apps/users/services/deletion.py` | 63 | search cache-version bump | **Yes** — `test_deletion.py:143` is `@pytest.mark.django_db(transaction=True)`, so the callback fires on commit |
| `apps/media/signals.py` | 40 | physical file deletion | **Yes (commit only)** — `test_ad_image_delete_signal.py:25` is class-level `transaction=True` |
| `apps/core/utils/advisory_lock.py` | 84 | release log line | **No** — `test_advisory_lock_release_log.py:34,:61` patch `on_commit` |
| `apps/moderation/signals.py` | 77 | **Telegram alert delivery** | **No** — `test_approve_ad_side_effects.py:63,:82` patch `on_commit` |

**The mock-out is exactly as described.**
`test_approve_ad_side_effects.py:63` and `:82` both carry
`patch.object(transaction, "on_commit", side_effect=lambda fn: fn())`, inside a module
whose `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` (line 29) — i.e. a
**transactional** test, in which `on_commit` would otherwise never fire. The two tests
prove the flag gate, not the deferral.

**No rollback-negative test exists anywhere in `src/`** for the alert path. Confirmed by
full-tree search: `on_commit` appears in only 2 test files for patch-out purposes, and
neither constructs a rollback.

**Evidence correction — and it strengthens the finding.** The report's inventory says
`test_ad_image_delete_signal.py` "asserts the file is gone after commit **and still
present on rollback**". Read in full (146 lines, 3 tests: `:38` cascade delete, `:74`
delete-failure-does-not-roll-back-cascade, `:117` bulk delete), **there is no rollback
test in that file.** So the suite's *only* real `on_commit` coverage — for both the
media and the cache-version sites — is commit-only. The blind spot is wider than the
report claims, which strengthens rather than weakens TEST-004.

**Additional confirmation.** `apps/search/tests/test_immediate_alerts.py` is
`pytest.mark.unit` (line 23), 10 tests, all against `MagicMock`/`AsyncMock` collaborators
(`_send_payloads`, `_run_send`, `build_alert_message`). The DB-facing entry point
`deliver_immediate_alerts` is never exercised against a real database, so its
`AlertDelivery` write and `delivered_at` stamp are unasserted. Confirmed.

**Verdict: CONFIRMED, HIGH held.** The residual is narrow, real, cheap to close, and the
failure it would miss is user-visible and irreversible.

**Cross-reference:** the alert path is also the subject of phase 08's finding that the
alert FTS path uses a weaker visibility predicate than the web path, and phase 06's
PII-104. Those are *defects*; TEST-004 is the *coverage gap* that let them ship.

---

### 3.5 TEST-005 — Two-process consistency untested — **ADJUSTED, HIGH → MEDIUM**

**Two of the three headline claims are refuted.**

**(a) "Zero tests cross the web/bot boundary in either direction" — FALSE.**

- Bot side: 8 `django.test` imports, **all** `override_settings`
  (`test_ad_create.py` ×6, `test_save_photo_integration.py`, `test_support_delivery_email.py`);
  **zero** `Client(`, `RequestFactory` or `ASGIRequest`. So the narrow claim *"no bot
  test issues a web request"* is correct.
- Backend side: the report's "2 hits, both comments" is wrong. There are **21** hits, and
  **at least five are real cross-tree tests**, not comments:

  | Test | What it actually does |
  |---|---|
  | `apps/core/tests/test_advisory_lock_ids.py:83` `test_all_references_are_valid_members` | AST-walks **and** regex-greps every `.py` in **both** `src/backend/` and `src/telegram_bot/` and asserts every `AdvisoryLockId.*` reference resolves to a real enum member. A genuine cross-process contract test. |
  | `apps/ads/tests/test_i18n_completeness.py:1070` `test_bot_no_raw_model_field_access` | AST-scans every `.py` under `src/telegram_bot/handlers/` and `services/` for hardcoded-locale bypasses and raw model-field access. |
  | `apps/media/tests/test_thumbnail_integration.py:9,:17` | Documented cross-process parity against the bot's photo pipeline. |
  | `tests/test_docs_ci_parity.py:157` | Asserts `testpaths` includes `src/telegram_bot`. |
  | `apps/core/tests/test_ci_security.py:151` | Asserts the CI security job scans `src/telegram_bot`. |

  A sixth is noted by the report's own Appendix B: `src/telegram_bot/tests/test_contact_gate.py`
  proves both processes delegate to `_check_seller_contactable`. The report therefore
  **contradicts itself** — §2 says zero, Appendix B says otherwise.

**(b) "The concurrency tests use threads inside one process, so none exercises a second
connection taking its own snapshot" — LARGELY REFUTED.**

`apps/ads/tests/test_edit_views_locking.py:191,:251,:304` and the sweep/bulk-action
concurrency tests use `threading.Thread` under `django_db(transaction=True)`. Django
gives **each thread its own connection and its own transaction**, so the DB-level
interleaving the report says is untested — two independent transactions, two snapshots,
a real `select_for_update` wait — **is** what those tests exercise. What a thread cannot
model is process-level separation: separate Redis namespaces, separate connection pools,
crash/restart semantics, and the fact that the bot's ORM calls are funnelled through one
asgiref `thread_sensitive` worker. That last one **is** covered, by
`apps/core/tests/test_db_connection_middleware.py` (phase 03's DB-001). So the report
both overstates the gap and misses that the specific mechanism it worries about is tested.

**(c) What actually survives.**

The real, narrow, untested gap: **no test asserts that a state written by one process is
observed by the other at the behavioural level.** Concretely — after the bot's
`submit_ad` publishes an ad, nothing asserts `/search/` or `/ads/<id>/` returns it with
the right city, price and denormalised `category_name`; and after a web-side
`ad_edit`, nothing asserts the bot's "my ads" listing or `AccountStateMiddleware` view
reflects it. That is a genuine blind spot, and it is the class in which phase 04's AUT-002
(session/account-state divergence) and phase 06's PII-104 (alert audience predicate) live.

**Why MEDIUM, not HIGH.** The rubric band for this checklist item is HIGH, but the
validation standard is whether the finding as written is true. With (a) and (b) removed,
the residual is a bounded, additive set of ~6 tests against an existing shared-helper
pattern. The architectural risk (three processes, one database, divergent predicates) is
real; the *evidence* that it is untested is much weaker than claimed, and a good part of
it is already tested at the level the architecture actually depends on (shared helper
delegation, ORM identity, CI/testpaths parity).

**Verdict: ADJUSTED, HIGH → MEDIUM.**

**Corrected recommendation.**

1. Add the behavioural cross-process assertions for the 2–3 highest-value rows. Reuse
   the existing shape: bot side = `sync_to_async(ORM)` assertion; web side = a
   `Client` request. The web-side assertion is new; the bot-side one already exists
   everywhere. ~6 tests.
2. For concurrency, the report's own proposal 2 (a second Django connection committing
   mid-transaction) is **already the shape of the existing tests** — threads under
   `transaction=True` do exactly that. Replace this item with what is genuinely absent:
   a test that asserts a predicate evaluated in the bot process and the same predicate
   evaluated in the web process return the same set for the same row (the AUT-002 /
   PII-104 shape). That is a shared-predicate test, not a concurrency test.
3. Keep the report's proposal 3 — do not run the real bot process inside pytest. Agreed
   and endorsed; that would be the overengineering the project rules warn against.

**Effort:** S for the corrected scope. **Not architectural** — additive to an existing
pattern, not a new harness.

---

### 3.6 TEST-006 — No control-character case in `?q=` — **ADJUSTED, MEDIUM held**

**Confirmed, but the gap is narrower than stated — and the report's own evidence
undercuts its headline.**

- `apps/search/tests/test_search_view.py:642` `TestSearchViewInputRobustness` exists
  with exactly 3 tests: `:649` (oversized), `:669` (SQL injection), `:691`. Line
  citations in the report are accurate.
- **The third test's name is `test_homoglyph_and_control_chars_query_returns_200`** and
  its payload is `Транспорт` + **U+200B ZERO WIDTH SPACE** + `<script>`. U+200B is a
  format-class invisible character. So "there is no case for control characters" is
  **too strong**: a class of invisible characters is tested. The report's own quoted
  description of the case ("Cyrillic + zero-width + HTML-like payload") contradicts
  its conclusion.
- **The real gap is C0/C1 control characters, and above all NUL (`\x00`)** — which is
  exactly the input PostgreSQL rejects with `DataError: invalid byte sequence for
  encoding "UTF8": 0x00`. That is the untested class, and the 500 it produces is the
  defect phase 08 already validated.
- **The report's grep evidence is false**: it states a search for
  `x00|\u0000|NUL|null byte` across `src/backend/**/*.py` returns "zero test hits".
  Two real NUL tests exist: `apps/ads/tests/test_media_security.py:517`
  (`test_path_traversal_with_null_byte`, `/media/../../etc/passwd%00.jpg`) and
  `apps/media/tests/test_filesystem.py:437` (`test_rejects_nul_byte`). Both are on the
  **media** path, not the `?q=` path. This **strengthens** the finding: the project
  demonstrably knows about NUL-byte hostility in one subsystem and has not carried that
  discipline into search.

**Verdict: ADJUSTED, MEDIUM held.** The defect is real and the coverage gap is real; only
the boundary of the gap and one evidence line are wrong.

**Corrected recommendation.** Extend `TestSearchViewInputRobustness` with a
`pytest.mark.parametrize` case over C0 control characters — `%00`, `%01`, `%0a`, `%1b` —
asserting HTTP 200 and zero results, landing with phase 08's production fix in one
commit. Then generalise the class to a small hostile-input corpus, as the report
proposes.

---

### 3.7 TEST-007 — `PopularSearch` / `SearchHistory` dedup key untested under two writers — **CONFIRMED, MEDIUM held**

**Confirmed exactly.**

- `apps/search/models.py:18` — `query_normalized = models.CharField(max_length=200,
  db_index=True)`. **No `unique=True`.** `Meta` (`:33-34`) contains **only**
  `db_table = "popular_searches"` — **no `constraints`**. Verified.
- `apps/search/services/popular_search.py:44-47` — the dedup is a plain
  `PopularSearch.objects.get_or_create(query_normalized=normalized, defaults=…)`,
  followed by an `F()`-expression increment at `:49-52`. Under `READ COMMITTED` (the
  level phase 03 confirmed is in use) two concurrent `get_or_create` calls on a
  non-unique column can both miss and both insert.
- `apps/search/services/search_history.py:76,:79` — the same shape (`… .delete()` then
  `SearchHistory.objects.create(…)`), with the same window. Verified.
- Coverage measured: `apps/search/tests/test_autocomplete.py:281,:288,:296` are three
  sequential, single-threaded tests inside one transaction. They prove the counter
  increments; they cannot interleave. No `Meta.constraints` introspection test exists
  for `PopularSearch` (the `test_ad_constraints.py` pattern is not applied to it).

**Evidence correction.** The report says the class docstring "even states the invariant
it does not enforce: *'one row per normalized query'*". That sentence **does not exist**.
The actual docstring is *"Stores popular search queries for autocomplete suggestions."*
The invariant is stated only in the service docstring (`popular_search.py:26-27`:
*"Atomically increment the hit count for a normalized search query"*). The claim's
substance is unaffected; the quote is withdrawn.

**Verdict: CONFIRMED, MEDIUM held.** Correctly scoped as a *coverage* finding; phase 08
owns the missing `UNIQUE` constraint and the `MultipleObjectsReturned` 500 it produces.

**Recommendation (unchanged, confirmed):** items 2 and 3 (constraint-introspection test,
`transaction=True` two-thread dedup test) are S effort and phase 11's. Item 1
(the `UniqueConstraint` + migration) is **phase 08's** — confirm it is not actioned
twice.

---

### 3.8 TEST-008 — `pytest-randomly` seed unpinned and unrecorded — **ADJUSTED, MEDIUM held**

**Confirmed:** `pytest-randomly 5.0.0` is installed and auto-enabled (no
`-p no:randomly` anywhere). `[tool.pytest.ini_options].addopts` is
`["--import-mode=importlib", "-ra", "-q"]` (line 167) — no `--randomly-seed`, no
disable. `ci.yml`, `docker/entrypoint-test.sh` and `Makefile.ps1` never pass a seed.
Shuffling is real.

**Correction — the seed is already persisted, and locally reproducible.**
`pytest_randomly/__init__.py`:

- `:140` — `config.cache.set("randomly_seed", seed)`
- `:129` — `seed = config.cache.get("randomly_seed", make_seed())` when the option is
  unset

So the seed is written to and **read back from** pytest's cache directory
(`.pytest_cache/v/cache/randomly_seed`). A local re-run with the cache present replays
the *same* order. The report's claim that "attempting to reproduce locally will produce
a different order" is **wrong** unless the cache is cleared.

`:187-190` — the seed is reported only through `pytest_report_header`
(`f"Using --randomly-seed={seed}"`), which `-q` (verbosity −1) suppresses. That part of
the report is right.

**So the precise finding is narrower and still real:** the seed is not in the **CI log**
(CI archives only `coverage.xml`, not `.pytest_cache`), and there is no `timeout`/CI
backstop that would surface it. Local reproducibility already works; CI-to-local
reproduction does not.

**Verdict: ADJUSTED, MEDIUM held.**

**Recommendation (unchanged, plus one addition):** pin `--randomly-seed` in `addopts`
(item 1 — accepted; note that pinning makes the cache lookup moot and is strictly
better). For item 2, the cheapest correct fix is to **upload `.pytest_cache` as a CI
artifact** next to `coverage.xml` (one line) rather than to change verbosity — it keeps
`-q` and records the seed deterministically.

---

### 3.9 TEST-009 — `pytest-timeout` / `pytest-rerunfailures` installed but never configured — **CONFIRMED, MEDIUM held**

**Confirmed.** Installed: `pytest-timeout 2.4.0`, `pytest-rerunfailures 16.6.1`.
Configured: **nothing.**

- `[tool.pytest.ini_options]` (`pyproject.toml:160-169`) has **no `timeout` key** and no
  `timeout_method`.
- `--timeout` appears in **zero** of `ci.yml`, `docker/entrypoint-test.sh`,
  `Makefile.ps1`.
- `--reruns` appears in **zero** of the same files.
- The only `timeout` strings in `ci.yml` are `--health-timeout 5s` (three service
  health-check options) and gunicorn `--timeout 30`.

**Evidence correction — and the gap is larger than reported.** The report states
*"the 2-hour `timeout-minutes: 30` on the whole job (`.github/workflows/ci.yml:96`) is
the only backstop"*. A search for `timeout-minutes` in `ci.yml` returns **0 matches** —
the parameter is not set on any job, and there is no `timeout-minutes` in the workflow at
all. (The "2-hour" figure is also internally inconsistent with the value it quotes.)
So the situation is **worse** than the report states: a hung test in CI is bounded by
nothing but GitHub's default 6-hour job limit, and the job is cancelled with no
diagnostic. The report's conclusion survives; its supporting evidence must be replaced
with "no `timeout-minutes` is configured on any job."

**Verdict: CONFIRMED, MEDIUM held.** Note also that the report attributes installed
versions (`>=2.4.0`, `>=16.6.1`) to `pyproject.toml` lines that actually declare
`>=2.3.0` (line 221) and `>=15.0.0` (line 220). Immaterial — the lockfile pins the
stricter values.

**Recommendation (accepted, with one addition):** items 1 and 2 as written. Add item 4:
**set `timeout-minutes` on the `test` job** (the job currently has no bound at all, and
the `seed`-excluded fast gate completes in ~226 s locally, so a 20–30 minute ceiling is
generous and would turn a hang into a diagnosable failure).

---

### 3.10 TEST-010 — 27 `inspect.getsource()` substring assertions — **CONFIRMED, MEDIUM held**

**Confirmed exactly, including the per-file distribution.** An independent scan of every
`test_*.py` under `src/` for `inspect.getsource` returns **27** occurrences across
exactly **8** files, with counts:

```
7  apps/ads/tests/test_edit_views_locking.py
5  apps/moderation/tests/test_admin_actions.py
4  apps/users/tests/test_admin_pii_containment.py
4  apps/core/tests/test_migrate_locked.py
3  apps/moderation/tests/test_moderation_views.py
2  apps/users/tests/test_unsubscribe.py
1  apps/ads/tests/test_recompute_command.py
1  apps/core/tests/test_sweep_archive.py
```

Identical to the report. The representative example at
`test_admin_actions.py:218-226` is present in substance and the critique is correct: the
assertions check that three substrings occur somewhere in a module's text, so they pass
whether `bulk_approve` works or is entirely broken, and fail on an equivalent refactor.

**The "instructive case" is also confirmed, and it is the strongest part of the
finding.** `apps/users/tests/test_admin_pii_containment.py` is the only test file that
specifically audits the admin surface, and it is built entirely from `getsource` checks
on `list_display` helpers. AUT-005 / PII-103 (`UserAdmin` auto-building a `ModelForm`
with `password` as a plain-text `CharField`) lives in the **absence** of
`fields`/`fieldsets`/`exclude` — there is no source text to grep. Phase 04's validator
and phase 06's auditor both had to reach for registered-`ModelAdmin` form introspection
to find it. The same is true of AD-001 (`status` missing from `readonly_fields`).

**Verdict: CONFIRMED, MEDIUM held.** Effort S, dominated by item 3.

**Cross-reference to phase 06's VAL-007** (scope the introspection test to an explicit
data-subject column set, or it false-positives on `SupportContactAdmin.telegram_id`):
accepted, and now **more important than the report realises** — see §3.12, where an
existing test already asserts on `SupportContactAdmin` attributes.

---

### 3.11 TEST-011 — `syncdb` schema means no test exercises a data migration's effect — **ADJUSTED, MEDIUM held**

**Mechanism confirmed; the named targets do not exist.**

- `config/settings/test.py:89-97` defines `DisableMigrations` and assigns
  `MIGRATION_MODULES = DisableMigrations()` (line 97), so pytest-django builds the test
  schema by model introspection (`syncdb`). Confirmed.
- The conftest compensation at `src/backend/conftest.py:111-165`
  (`_restore_test_schema_post_db_setup`) re-applies the DDL and seed data that
  `syncdb` cannot create. Confirmed, and correctly reasoned in the report.
- `apps/core/tests/test_migrations.py` asserts migration **applicability** and
  **idempotency**, not **effect**. Confirmed.

**Correction 1 — the class is not a `dict` subclass.** The report quotes
`class DisableMigrations(dict):`. The shipped code is `class DisableMigrations:`. Trivial
but it signals the evidence was reconstructed rather than copied.

**Correction 2 — both named target migrations are absent.** The report names "the
search-vector backfills and the `squash_rehydrate_runsql` step". The full migration
inventory is 27 files; there is **no squash migration** and **no search-vector
backfill migration** anywhere. The search-vector is maintained entirely by a PostgreSQL
trigger, never by a `RunPython` backfill.

**Correction 3 — the real, named targets.** Every `RunPython`/`RunSQL` in the tree,
from a full scan of the 27 migration files:

| Migration | Ops | Why an effect-test matters |
|---|---|---|
| `apps/ads/migrations/0003_dedup_per_user_drafts.py` | 2 | **Destructive** — deletes duplicate per-user DRAFTs. A no-op here silently keeps duplicates forever and the `0004` UNIQUE constraint then fails to apply. The highest-value target in the set. |
| `apps/search/migrations/0002_redact_search_queries.py` | 2 | Rewrites production rows (PII redaction). A silent no-op leaves unredacted phone numbers/e-mails in the table. |
| `apps/core/migrations/0003_add_bot_username.py` | 2 | Backfills a user column. |
| `apps/core/migrations/0002_seed_default.py` | 1 | Seeds a reference row. |
| `apps/ads/migrations/0001_initial.py` (+ 7 other `0001_initial.py`) | 8 total | Index/constraint DDL. |

The gap is real and these four are strictly better targets than the ones named.

**Verdict: ADJUSTED, MEDIUM held.**

**Recommendation:** as written in item 1, but assert against the four real targets —
specifically, that after a forward migrate `0003_dedup_per_user_drafts` has left exactly
one DRAFT per user, and that `0002_redact_search_queries` has rewritten
`PopularSearch.query`. Note `apps/ads/migrations/0004_ad_uq_ads_single_draft_per_user.py`
adds the UNIQUE constraint whose precondition is exactly what `0003` guarantees — the two
together are the argument for testing the effect.

---

### 3.12 TEST-012 — No admin page is ever rendered or introspected — **ADJUSTED, MEDIUM held**

**The premise is refuted.** `src/backend/apps/core/tests/test_support_admin.py`
(146 lines, `pytest.mark.unit`) is exactly "a test module that introspects registered
`ModelAdmin`":

- `admin.site.is_registered(SupportContact)` / `(SupportTicket)` — lines 31, 36
- `SupportContactAdmin(SupportContact, admin.site)` and
  `SupportTicketAdmin(SupportTicket, admin.site)` **instantiated** and queried —
  lines 72, 82, 135, 144 (`has_add_permission` / `has_delete_permission`)
- `list_display`, `list_editable`, `list_filter`, `search_fields`, `readonly_fields`
  asserted as class attributes — lines 44, 51, 59, 65, 92, 100, 110, 128

That is **12 tests**. The report's grep pattern
(`get_form\(|get_actions\(|admin.site._registry|UserAdmin|AdAdmin`) does not match
`admin.site.is_registered` or `SupportContactAdmin`, so this is a **false negative from
a too-narrow search**, and the report's "the only hits are the `getsource` checks" is
wrong.

**What survives — and it is the operative gap.** A search across the whole test tree for
`get_form(` and `get_actions(` returns **zero** hits, and no test issues a
`Client().get("/admin/...")`. So:

| Surface | Tested? |
|---|---|
| `ModelAdmin` class attributes (`list_display`, `readonly_fields`, …) | Yes, for 2 of ~12 admins |
| Registered-`ModelAdmin` **generated form** (`get_form(request)` → field names, widget classes) | **No admin at all** |
| Registered-`ModelAdmin` **wired actions** (`get_actions(request)`) | **No admin at all** |
| Any rendered admin page | **No** |

That is exactly the blind spot in which AUT-005 / PII-103, AD-001 and PII-107 live, and
the report's diagnosis of *why* is right: the class-attribute style of
`test_support_admin.py` — like the `getsource` style of
`test_admin_pii_containment.py` — cannot see a defect expressed in an **absence**
(no `fields`/`fieldsets`/`exclude` ⇒ auto-built form; `status` missing from
`readonly_fields`; `withdraw_consent_action` declared but not added to `actions`).

**Verdict: ADJUSTED, MEDIUM held.** The defect class is real; the inventory of what
already exists was wrong, which **reduces the cost** and changes the remedy from "add a
new module" to "generalise the existing pattern".

**Corrected recommendation.**

1. **Extend the existing `test_support_admin.py` pattern to every registered
   `ModelAdmin`**, and change the assertion from class attributes to the generated form:
   `admin.site._registry[Model].get_form(request)` → assert the field-name set and the
   widget class per field. A `password` rendered as `AdminTextInputWidget`, or a raw
   identity column, fails. This single test would have caught **AUT-005 / PII-103** and
   **AD-001**.
2. Add `get_actions(request)` assertions for every admin declaring `actions`, so an
   action is either wired or removed (**PII-107**).
3. Scope rule 1 to an explicit declared set of data-subject columns — phase 06's
   **VAL-007** is now mandatory, not optional, because `test_support_admin.py:44,65`
   already asserts on `SupportContactAdmin.telegram_id`, and a blanket rule would
   false-positive on a support *channel* ID.
4. One rendered-page smoke test (`Client().get("/admin/<app>/<model>/")` with a staff
   user) is worth adding, but is the lowest-value item of the four.

**Effort:** S. **Lower than the report's M**, and no new file is required.

---

### 3.13 TEST-013 — The `basedpyright` gate is red; the bot tree is outside lint + typecheck — **ADJUSTED, LOW held**

**Counts confirmed exactly, by re-running the toolchain locally.**

```
basedpyright .   from src/backend        ->  12 errors, 0 warnings, 0 notes   (exit 1)
basedpyright .   from src/telegram_bot   ->   2 errors, 0 warnings, 0 notes   (exit 1)
```

All 12 backend-scope errors and both bot-scope errors are in **test** files. No
production file is implicated. This corroborates ENT-004 (Phase 01) and the
already-validated base fact that the gate is red today.

**Correction — the per-file distribution in the report is wrong.** The report attributes
the 12 errors to "4 in `test_admin_actions.py`, 3 each in `test_search_view.py` /
`test_deletion.py` / `test_incomplete_feature*`, 2 in `test_payment_forms.py`, 1 in
`test_moderation_side_effects.py`". Measured reality:

| File | Errors | Rule | Root cause |
|---|---|---|---|
| `apps/ads/tests/test_edit_views_locking.py` | **8** (`:239` ×2, `:247` ×2, `:292` ×2, `:300` ×2) | `reportGeneralTypeIssues` | untyped `advisory_lock` context manager |
| `apps/moderation/tests/test_admin_actions.py` | **4** (`:529` ×2, `:538` ×2) | `reportGeneralTypeIssues` | untyped `advisory_lock` context manager |
| **Total** | **12** | | **one root cause** |

The "incomplete `IncompleteFeature` stub" and the "`# type: ignore` in
`test_payment_forms.py`" cited by the report **do not exist**. Bot scope: 2 errors, both
`reportOptionalMemberAccess` at `src/telegram_bot/tests/test_ad_create.py:358,373`.

**This is good news for the remedy, and it is why TEST-013 is correctly LOW.** The
remediation is 12 mechanical errors in 2 files from a single cause (Django's untyped
`transaction.atomic()`-like CM returning `(...) -> object`), not six files and four
causes. It is a small hygiene commit.

**Verdict: ADJUSTED, LOW held.** Root cause remains **ENT-004's to own** — do not ship
the CI-scope widening twice. TEST-013 records only the test-gate view.

**Recommendation (accepted):** item 1 as written, now known to be a 12-error / 2-file /
1-cause fix. Item 2 (add a `basedpyright .` step for `src/telegram_bot`, move `ruff` to
the repo root) is correct and cheap — the bot tree measures only 2 errors, both in
tests, so widening the scope today is near-zero cost. Scope both to ENT-004's commit.

---

### 3.14 TEST-014 *(new)* — `transaction.on_commit` is structurally unreachable in half the production call sites, and MEDIA-001's fix would be verified by three tests — **CONFIRMED, MEDIUM**

This finding was **not in the auditor's report**. It is the quantified answer to the
question of how much of the suite can observe a real `on_commit` callback, and it is
raised here because two independent inputs converged on it: TEST-004's inventory, and
phase 07 VAL-003's statement that MEDIA-001's fix breaks exactly three tests.

**The mechanism, stated precisely.** The suite is entirely pytest-style:

| Item | Measured |
|---|---|
| Classes subclassing `django.test.TestCase` | **0** |
| Classes subclassing `TransactionTestCase` | **0** |
| Uses of `captureOnCommitCallbacks` / `getOnCommitCallbacks` | **0** |
| Scopes marked `pytest.mark.django_db(transaction=True)` | **46** across 37 files |
| Everything else marked `pytest.mark.django_db` (transactional) | the rest of ~2 394 |

**Correction to the framing used to scope this phase (VAL-002):** the audit input
assumed that "tests using bare `TestCase` are structurally blind to `on_commit`". That
premise is **factually inapplicable to this repository — there are no `TestCase`
subclasses at all.** The *underlying* blindness is real and **larger** than that framing
implies, but it arrives by a different route: `pytest.mark.django_db` (transactional,
the default for roughly 2 350 tests) wraps each test in an `atomic()` block, so
`on_commit` callbacks are **never** fired in those tests. The suite already knows this —
it is precisely why `test_approve_ad_side_effects.py` and
`test_advisory_lock_release_log.py` must patch `on_commit` to run at all.

**The quantified exposure:**

| Production `on_commit` site | Observable only under `transaction=True`? | Real coverage |
|---|---|---|
| `apps/users/services/deletion.py:63` | Yes | **Real** (`test_deletion.py:143`) |
| `apps/media/signals.py:40` | Yes | **Real, commit-only** (`test_ad_image_delete_signal.py`, 3 tests) |
| `apps/core/utils/advisory_lock.py:84` | Yes | **None** — `on_commit` is patched out in both tests |
| `apps/moderation/signals.py:77` | Yes | **None** — `on_commit` is patched out in both tests |

**2 of 4 production call sites — including the one that sends a real Telegram message —
are structurally unobservable by any test in the repository.** Not under-covered:
*unobservable*.

**The MEDIA-001 consequence, which is the reason this is MEDIUM and not LOW.**
Phase 07 validated MEDIA-001 (HIGH) with the remedy "a reference check inside the
existing `on_commit` callback, no schema change". That check would live in
`media/signals.py:40` — the callback that fires only under `transaction=True`. The
media test surface splits:

- `transaction=True` (callback fires): `test_ad_image_delete_signal.py`,
  `test_delete_photo_single_call.py`, and the seven `test_sweep_*.py` files.
- transactional `django_db` (callback never fires): `test_delete.py`,
  `test_media_security.py`, `test_ad_image_service.py`, `test_backfill_thumbnails.py`,
  `test_filesystem.py`, `test_save_photo_exif.py`,
  `test_sweep_orphaned_media.py`, `test_thumbnail_integration.py`.

A reference-counting check placed in the `on_commit` callback is therefore verified by
the **`test_sweep_*` subset plus `test_ad_image_delete_signal.py`** and by nothing else
in the media surface. Phase 07 VAL-003 independently identified
`test_ad_image_delete_signal.py:38/:74/:117` as the three tests that will break — this
validation arrived at the same three, and supplies the reason phase 07 could not state
from inside its own layer: **they are the only three tests in the file that run under
`transaction=True`.**

A refcount bug in an `on_commit` callback is the *worst* place to have one. Its failure
mode is asymmetric and irreversible: a false "this is the last reference" deletes live
bytes belonging to another ad (MEDIA-001's own data-loss), and a false "references
remain" leaks files silently. Both are invisible to the eight transactional media test
files that make up the bulk of the surface.

**Recommendation (required before MEDIA-001 lands):**

1. Add a `transaction=True` scaffold for the media surface: at minimum, a test that
   creates two `AdImage` rows in **different** ads sharing one key, deletes one ad
   under `transaction=True`, and asserts **the shared file still exists**; and its
   negative — the last reference *is* freed. Two tests.
2. Add the missing rollback-negative test for the existing `on_commit` sites while the
   scaffold exists (this is also TEST-004's item 1; the two findings share one test
   file, so land them together).
3. Coordinate ordering with phase 07: **TEST-014's scaffold must land before or with
   MEDIA-001**, not after. Phase 07's own VAL-004 flags the parallel "half-fix"
   hazard; this is the same hazard from the test side.

**Effort:** S. **Not architectural** — two or three tests. It is a *sequencing*
requirement, not a design change.

---

### 3.15 VAL-001 *(new)* — The report's anchor commit does not exist, and at least nine code citations are stale — **CONFIRMED, MEDIUM**

`.ai/audit/11-test-coverage/findings.md:6` declares
`Anchor commit: 0c91666 (docs: pre-audit report of bot middleware suite (36k lines / 190 tests))`.
`git cat-file -t 0c91666` returns **`fatal: Not a valid object name`**. `HEAD` is
**`9e96b84`** (`chore(agents) allow docker remove commands`). The nearest matching commit
in the log is `700d99d fix(test): make fixtures idempotent for --reuse-db`, which the
report itself cites in Appendix B item 7.

**Consequence — the report's line-level evidence cannot all be trusted.** The validator
confirmed 9 of the report's citations as stale, and 4 of its quoted code blocks as
not-the-shipped-code. This is a cross-phase evidence-provenance problem: the same report
also *corrects* phase 05's VAL-002 count, and a correction issued from an unresolvable
anchor cannot be checked the way the reader will assume it can.

**The corrections themselves are not in doubt** — this validation re-derived every one of
them from `9e96b84`:

| Report citation | Actual at `9e96b84` |
|---|---|
| `conftest.py:288-332` factory | `:283-322`; default at `:290` ✔ |
| `conftest.py:333-340` bulk factory | `:325-365`; default at `:333` ✔ |
| `submission.py:130-136`, `:148`, `:119` | `submit_ad` is `:122-245`; transition `:230`; `auto_moderate` `:241`; `atomic()` `:169` |
| `ad_reactivate` at `submission.py:161-199` | **Not in this file.** The view is `apps/ads/views/edit.py:307-347`; transition `:338`, `auto_moderate` `:343` |
| `auto_moderation.py:50-124` | `auto_moderate` is `:94-173`; `_fail_moderation` `:241`, `_pass_moderation` `:258` |
| `listings_query.py:181-186` (quoted `OuterRef` block) | `:183-186`, a plain `filter(features__slug=slug)` loop; **quoted code absent** |
| `ListingsQueryParams.feature_slugs` at `:44` | `:57` |
| `search.py:127` `params.getlist("features")` | `apps/search/views/search.py:101` (and `apps/ads/views/listings.py:250`) |
| `config/settings/test.py:89-97`, `class DisableMigrations(dict)` | `:89-97` ✔, but the class does **not** inherit `dict` |
| `pyproject.toml:230` `pytest-randomly>=3.16.0` | `:219` |
| `pyproject.toml:220` `pytest-rerunfailures>=16.6.1` | `:220` declares `>=15.0.0`; `16.6.1` is the *installed* version |
| `pyproject.toml:222` `pytest-timeout>=2.4.0` | `:221` declares `>=2.3.0`; `2.4.0` is the *installed* version |
| `ci.yml:133-138` | `:133-139` |
| `test_features_filter.py` — 7 request sites at `:46,:99,:140,:155,:179,:198,:226` | 3 requests, at `:52`, `:71`, `:86` |

**Required:** correct the anchor to `9e96b84` in the phase report, and treat the
findings' *narrative* as reliable and their *line citations* as indicative unless
re-derived. Every count in this report that carries remediation weight (111 sites,
27 `getsource`, 12 + 2 type errors, 4 `on_commit` sites, 0 `TestCase` classes) was
re-derived independently and is stated here as a self-contained anchor.

**Also recorded — handbook drift.** `.kilo/commands/audit/phases/11-audit-test-coverage.md:291`
asserts the suite has an *"80 % branch coverage gate"*, and `:253` says bot tests use
`transaction=True` in *"9 files"*. Both are false on the same evidence as TEST-002
(§3.2) and §3.14 (46 scopes / 37 files). The handbook's coverage assertion is the
clearest single statement of the belief gap TEST-002 identifies.

---

### 3.16 VAL-002 *(new)* — The "bare `TestCase`" exposure framing is inapplicable to this repository — **CONFIRMED, MEDIUM**

Recorded separately from TEST-014 because it concerns the **audit input**, not the
source code. The scoping premise supplied to this validation — *"tests using bare
`TestCase` are structurally blind to `on_commit`; quantify the exposure"* — does not
apply:

- **0** classes subclass `django.test.TestCase`.
- **0** classes subclass `TransactionTestCase`.
- **0** uses of `captureOnCommitCallbacks` / `getOnCommitCallbacks`.
- 46 `transaction=True`-marked scopes across 37 files; the remainder of the suite uses
  transactional `pytest.mark.django_db`.

The exposure is real but is delivered by `pytest.mark.django_db`, not by `TestCase`, and
its size (2 of 4 production `on_commit` sites unobservable) is quantified in TEST-014.
**No source change follows from this item**; it exists so that no downstream
remediation is scoped against the wrong mechanism, and so that the count is not
double-counted between TEST-004 and TEST-014.

---

## 4. Rollout Analysis

### 4.1 Dependency chains (ordered, not by severity)

```
1. TEST-013 (12 type errors, 1 cause, 2 files)      ── independent; unblocks CI signal
2. TEST-002 (coverage step working-directory)       ── independent; 1 CI line
3. TEST-003 step 1 (test statement_timeout)         ── must be sized WITH DB-004 (Ph.03)
                                                        and must NOT precede DB-002
4. TEST-014 scaffold (media transaction=True tests) ── MUST land with or before MEDIA-001 (Ph.07)
5. TEST-001 step 1 (product decision on AD-008)     ── decides whether 111 sites move at all
6. TEST-001 steps 2-4 (fixture default + docs)      ── 2 green commits, independent of 5's outcome
7. TEST-003 step 2 (hostile ?features= test)        ── needs 3, and lands with SRCH-001 (Ph.08)
8. TEST-004 + TEST-014 rollback-negative tests      ── share one file; land together
9. TEST-012 (admin form/action contract)            ── independent; closes AUT-005/AD-001/PII-107
10. TEST-006 / TEST-007 items 2-3 / TEST-011        ── each lands with its phase-08/07 production change
11. TEST-005 (corrected scope), TEST-010            ── independent
12. TEST-008 / TEST-009                             ── independent; do these early, they pay for everything above
```

### 4.2 Hard ordering constraints

1. **TEST-003's test-side `statement_timeout` must be sized together with DB-004, and
   must not land before DB-002 (Phase 03).** Phase 03's validator recorded that
   `statement_timeout` produces an `OperationalError` on exactly the kind of INSERT
   `record_event` issues, and `record_event` currently swallows it. Landing a
   statement-level bound first would convert a swallowed error into a new failure mode
   in the analytics path. **This is a live hazard, not a theoretical one.**
2. **TEST-014's scaffold must land with or before MEDIA-001 (Phase 07).** A refcount
   check inside `on_commit` with only 3 verifying tests is the half-fix hazard phase 07
   VAL-004 warns about, approached from the other side.
3. **TEST-001's fixture work must NOT be sequenced ahead of the AD-008 product
   decision.** Migrating 111 sites before knowing whether `ON_MODERATION` becomes
   durable risks doing ~111 sites of work that a product decision then invalidates.
4. **The test-expectation changes (TEST-003 step 2, TEST-006, TEST-007 item 1, TEST-011)
   must land in the same commit as their production change** — phase 07 VAL-003's rule,
   restated here because four of this phase's findings depend on it.

### 4.3 No circular dependencies

No dependency cycle exists among the 13 findings plus `TEST-014`. The only near-cycle —
TEST-003 (bound) → SRCH-001 (cap) → DB-004 (bound) — resolves because DB-004 satisfies
both TEST-003 and SRCH-001 in one change, with DB-002 as its own prerequisite.

### 4.4 Findings that genuinely require an architectural or structural change

| Finding | Structural? | What changes |
|---|---|---|
| **TEST-001** | **Yes — but smaller than reported** | A test-fixture *contract* change (2 green commits, S). The 111-site migration is contingent on a product decision, not required. |
| **TEST-002** | **No** | One CI line (`working-directory: .`). "CI restructure" is overstated; the blast radius is a single step. |
| **TEST-003** | **No (test infra)** | One connection option in `config/settings/test.py` + one test. Structural only in that the bound must be co-designed with DB-004. |
| **TEST-004** | **No** | 1–2 tests. |
| **TEST-005** | **No** (corrected) | ~6 additive tests following an existing pattern. Not a new harness. |
| **TEST-006 … TEST-013** | **No** | Individual tests / CI lines / doc corrections. |
| **TEST-014** *(new)* | **No** | 2–3 tests. A sequencing requirement against MEDIA-001, not a design change. |

**Net effect on the report's headline:** the report names 4 findings as requiring
architectural or significant change. On validation, **one** (TEST-001) genuinely does,
and its scope is a fixture contract plus a product decision — not "rewrite 111 sites in
one commit". The other three are a CI working directory, a test setting, and an
additive test layer. **Total corrected effort for the whole phase: S per item, M in
aggregate, dominated by TEST-001's conditional 111-site migration.**

---

## 5. Advisory Recommendations

Not required, and each is cheap:

1. **Add a `--cov-config` smoke assertion to CI** (or the explicit
   `--cov=src/backend --cov=src/telegram_bot --cov-branch --cov-fail-under=80
   --cov-config=pyproject.toml` form the report offers). Either makes the gate
   self-documenting and immune to the next `working-directory` change. The report's
   alternative is better than its primary recommendation, because it is explicit rather
   than positional.
2. **Correct the phase handbook** (`.kilo/commands/audit/phases/11-audit-test-coverage.md:291`
   "80 % branch coverage gate", `:253` "9 files") and the two rule files
   (`.kilo/rules/commands.md:70`, `docs/99-agent/rules.md:53`). The handbook is an
   audit input, not a finding — but a future run will read it and inherit the false
   premise.
3. **Adopt one assertion over repeated doc fixes** for the fixture default, in the
   spirit of phase 01 VAL-003 and phase 07's nginx note: a single test asserting
   `create_test_ad`'s default is `AdStatus.PUBLISHED` makes the documentation
   self-verifying and prevents a third drift.
4. **Promote the AST-scan pattern already in the suite** (`test_advisory_lock_ids.py`,
   `test_i18n_completeness.py`) as the house style for cross-tree invariants. It is
   cheap, it is already trusted here, and it is the right shape for the corrected
   TEST-005 items 2 and for the `AdStatus` allow-list checks `test_ad_constraints.py`
   already does.
5. **Record the seed in the CI artifact set** alongside `coverage.xml` (see §3.8) rather
   than changing verbosity.

---

## 6. Evidence Not Reproduced (and why)

| Claim | Status | Reason |
|---|---|---|
| `2394 passed in 226 s` baseline | **Accepted as given** (it is stated base context) | Re-running the suite risks the concurrent-container hazard that produced VAL-010 in phase 06 and this phase's own contaminated run. Read-only verification did not require it. |
| `EXPLAIN`-only kill of the PG backend at 50–100 slugs | **NOT reproduced — not carried forward** | Would repeat phase 08's VAL-004 (two cluster terminations, ~30 s outage for 22 databases) while other phases were using the shared instance. Phase 08's independently-validated `ANALYZE` numbers are authoritative. See §2.2. |
| `PROBE NUL-in-q -> 500` | **NOT reproduced** | Requires the DB. The defect is **already validated by Phase 08**; this phase files only the coverage gap, and the gap was verified by static analysis (§3.6). |
| Admin coverage percentages (`ads/admin.py` 57 %, etc.) | **NOT reproduced** | Requires a full coverage run. The finding's operative claim (no `get_form`/`get_actions`/page render anywhere) was verified by exhaustive grep, which is the stronger form of the claim. |
| Total suite passes 0 failed | **Not re-run** | See row 1. |

**Tools actually executed in this validation (all read-only):**

- `git log` / `git status` / `git cat-file` (anchor + tree state)
- `coverage.Coverage()` config resolution from both working directories
- `_pytest.config.determine_setup` for rootdir/inifile resolution from `src/backend`
- `ast`-based scans: factory call sites, `AdStatus.ON_MODERATION` production paths,
  `TestCase`/`TransactionTestCase`/`captureOnCommitCallbacks` inventory,
  `transaction=True` scope inventory
- `basedpyright .` from `src/backend` and from `src/telegram_bot`
- `importlib.metadata.version` for the six relevant pytest plugins
- static greps for `on_commit`, `statement_timeout`, `getsource`, `get_form`,
  `get_actions`, `RunPython`/`RunSQL`, `timeout-minutes`, `features=`, NUL patterns

**Cleanup performed.** Four probe scripts created by this validation under `.ai/tmp/`
were deleted. `git status --porcelain` reports **no modified tracked file** anywhere in
`src/`, `docker/`, `.github/` or `pyproject.toml`. No scratch database was created and
no container was started, so the shared test instance and the phantom `mko_bazuna`
database were not touched at all.

---

## 7. Rejected Findings

| ID | Title | Reason |
|---|---|---|
| *(none)* | — | No finding was rejected outright. Three headline claims inside findings were **rejected** (TEST-002's "bot absent from the report"; TEST-005's "zero tests cross the boundary"; TEST-012's "not one test introspects a registered `ModelAdmin`"), plus TEST-001's "must land in one commit" and the `EXPLAIN`-only crash table. Each rejection is stated in the corresponding §3 entry with the corrected statement. |

---

## 8. Merged Findings

| Original ID | Merged Into | Rationale |
|---|---|---|
| *(none)* | — | No finding in this phase is a duplicate of another phase's finding. Every one either measures the *test coverage* of a defect another phase owns (§2.4) or is a genuinely test-suite-scoped defect. The one candidate — TEST-013's root cause — is **explicitly left with ENT-004** rather than merged, per the report's own ownership note. |

---

## 9. Reclassified Findings

| ID | Original Type | New Type | Rationale |
|---|---|---|---|
| TEST-001 | `[SPEC-DEVIATION]` + structural | **`[TEST-CONTRACT]` / BEST-PRACTICE (test-fidelity)** | The fixture is test code, not a specification. The *specification* deviation is AD-008's (Phase 05), which is where the four documents promising a durable `ON_MODERATION` belong. Filing it again here as a spec deviation duplicates AD-008. |
| TEST-002 | `[SPEC-DEVIATION]` + CI config | `[BEST-PRACTICE]` (CI hygiene) with a belief-gap note | No requirement is violated; a configured control is inert. The "the team believes it measures X and it measures Y" framing is preserved as the justification for the severity, not as a spec deviation. |
| TEST-003 | `[BEST-PRACTICE]` + `[SPEC-DEVIATION]` | **`[SPEC-DEVIATION]` (test-isolation)** | The unbounded input is SRCH-001's; the test-side half is that the *test environment* has no resource bound, which is a deviation from the isolation the suite claims. |
| TEST-005 | `[BEST-PRACTICE]` | **`[BEST-PRACTICE]`, severity downgraded** | Type unchanged; the adjustment is scope + severity, not classification. |
| TEST-011 | `[SPEC-DEVIATION]` | `[BEST-PRACTICE]` | The suite's schema-restoration compensation is a deliberate, documented trade-off with a correctness argument. The unexercised *data-migration effect* is a test gap. |
| TEST-013 | `[SPEC-DEVIATION]` | `[SPEC-DEVIATION]` (unchanged) | Held. Root cause is ENT-004's; recorded here as the test-gate view only. |

---

## 10. Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 1 | `TEST-010` |
| Validated with evidence corrections | 3 | `TEST-004`, `TEST-007`, `TEST-009` |
| ADJUSTED (content and/or severity) | 9 | `TEST-001` (CRITICAL→HIGH), `TEST-002`, `TEST-003`, `TEST-005` (HIGH→MEDIUM), `TEST-006`, `TEST-008`, `TEST-011`, `TEST-012`, `TEST-013` |
| Reclassified (type only) | 6 | see §9 |
| MERGED into another phase | 0 | — |
| Rejected outright | 0 | — |
| **New findings raised** | 1 | `TEST-014` (MEDIUM) |
| **New VAL- items** | 2 | `VAL-001` (anchor commit unresolvable / 9 stale citations), `VAL-002` (`TestCase` framing inapplicable) |

**Severity roll-up after validation:** CRITICAL **0** · HIGH **3** (`TEST-002`,
`TEST-003`, `TEST-004`) · MEDIUM **9** (`TEST-001`, `TEST-005`, `TEST-006`,
`TEST-007`, `TEST-008`, `TEST-009`, `TEST-011`, `TEST-012`, `TEST-014`) · LOW **1**
(`TEST-013`).
Auditor's roll-up was CRITICAL 1 · HIGH 4 · MEDIUM 7 · LOW 1.

**Every count in this report was re-derived independently and is stated with its
anchor (`9e96b84`)** so that no reader needs the original findings file or any source
file to act on it.
