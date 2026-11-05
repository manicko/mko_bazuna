---
id: architecture-correction-execution
domain: planning
tags: [architecture, execution, correction]
related: [architecture-correction-plan]
---

# Architecture correction — execution plan

Source plan: `.ai/plans/architecture-correction-plan.md` (packages P0–P8, gates G0–G8,
retirement manifest, coverage-transfer ledger). This file records execution decisions only.
The source plan remains authoritative for scope; nothing below widens it.

## Execution mode

Audit and planning phases were skipped per instruction (`skip general audit and plan phase`).
The source plan already contains package decomposition, dependencies, risks, retirement
manifest, coverage ledger, and verification gates.

## Block definitions

| Block | Source | Risk | Agents | Dependencies |
|---|---|---|---|---|
| B0 | P0 — Repair edit results | HIGH (product behavior regression) | Auditor → Researcher → Planner → Implementor → Validator | none |
| B1 | P1 — Restore lifecycle atomicity | HIGH (transactions, locks) | Auditor → Researcher → Planner → Implementor → Validator | none (ordered after B0) |
| B2 | P2 — Verify endpoint consumers | GATE (business/operational) | User decision required | none; blocks B3/B4 |
| B3 | P3 — Transfer business tests | MEDIUM (coverage loss risk) | Planner → Implementor | B0, B1 |
| B4 | P4 — Retire unused endpoints + parity machinery | MEDIUM/HIGH (deletion) | Auditor → Planner → Implementor → Validator | B2, B3 |
| B5 | P5 — Remove exclusive support | MEDIUM | Planner → Implementor | B4 |
| B6 | P6 — Simplify retained services | LOW/MEDIUM | Planner → Implementor | B0, B1, B4 |
| B7 | P7 — Docs/catalogs | LOW | Doc-specialist | B4, B5 |
| B8 | P8 — Verification and measurement | — | Validator | all |

## Decisions

- B0 order is deliberate: the P0 edit-result contract determines how the API edit adapter maps
  results, and P1 is "preferably after P0" per source plan.
- B2 is a hard gate. Repository silence does not prove no external consumer (plan §9). No
  endpoint retirement (P4/P5) executes until the Product Owner states whether deployed/external
  consumers exist.
- P6 signature simplification is deferred until after P4 so API callers do not need dual paths.

## Gate status

- G0 Consumer compatibility: **CLOSED** — Product Owner confirmed no external/deployed consumers
  of `/api/v1/` (2026-11-05); full retirement authorised.
- G1 Edit correctness: **PASS** — repaired in `bb434452`; `EditResult` carries
  `submission_outcome: SubmitAdOutcome | None` + `errors`; HTML redirects only on `PUBLISHED`;
  no production `unittest.mock` remains; six-outcome × two-branch service matrix, HTML
  refusal/no-redirect rows, and API mapping tests landed.
- G2 Lifecycle atomicity: **PASS** — `716fe3e1` restored one transaction/lock per request;
  `3f0a5fab` adopted the single locked-ad convention. `TestLifecycleActionAtomicContinuity`,
  `TestLifecycleActionLockContinuity` (55P03 probe), archive/reactivate 503 boundary tests green;
  moderation rollback pinned by `test_check_error_rolls_back_to_archived`.
- G3 Search/listing behaviour: **PASS** — `test_listings_query.py` ports the matrix with the D28
  fix (4 sort rows, no unused `page` parametrize); `-id` tiebreakers intact.
- G4 Existing product contracts: **PASS** — bulk-action canary, autocomplete, preferred-city,
  login token, consent/logout, health/metrics/admin/media/bot suites retained and green.
- G5 Removal consistency: **PASS** — zero executable references to the retired surface,
  helpers, budgets, or lifecycle precheck; only `/moderation/api/v1/` remains (expected).
- G6 Static/docs/i18n: **PASS** — ruff/basedpyright clean; catalogs pruned with the gate as
  authority (B4: 16, B5: 16); shared strings and the Bosnian repair preserved; docs describe the
  shipped surface.
- G7 No infrastructure/data rollback: **PASS** — no migration/settings/dependency/lockfile delta;
  `submission.py` and `media/schemas.py` byte-identical to `d2f6df33^`; `RateLimitBudget` back to
  five members.
- G8 Coverage and measured feedback: **PASS (tier-separated evidence)** — all 7 deletion blockers
  have named retained tests; the coverage ledger has no unexplained loss. Measured at HEAD
  `a0e09be1` (2026-11-05, warm Docker test DB, xdist 4-worker loadgroup unless noted):
  fast gate `.\Makefile.ps1 test` = **3778 passed, 3 warnings**; full non-seed tier on a fresh
  schema (`--create-db`, `PYTEST_SKIP_MARKERS=seed`) = **3804 passed, 3 warnings in 364.31 s**;
  seed tier (`-m seed`) = **37 passed, 43 warnings in 59.45 s**. The 26-test fast-gate gap is the
  `slow` + `real_images` deselection; it includes the `slow`-marked G2 lock-continuity proof,
  which ran green in the full tier. Local single-invocation `test-all` is **not** valid evidence
  in this environment: it mixes `transaction=True` and seed-marked tests on one shared
  `--reuse-db` database across xdist workers, producing fixture `UniqueViolation`s on seeded
  reference data (`categories_slug_key='transport'`, `lookup_groups_code_key='listing_feature'`,
  `cities_slug_key='podgorica'`) in suites untouched by this change; those suites pass in
  isolation and the tier-separated runs mirroring CI are green. Pre-existing test-infrastructure
  issue, out of scope (D29–D31 KEEP; "do not redesign CI in this correction").

## B0 audit findings

Read-only audit of block B0 (P0 — Repair edit results), 2026-11-04. Semantic anchors are
authoritative; line numbers (HEAD `22dd26be`+) are hints. Baseline = `57966ea0`
(`src/backend/apps/ads/views/edit.py` extracted to `.ai/tmp/baseline_edit.py`).

### Current implementation (per symbol)

- `apps/ads/services/edit_flow.py::EditOutcome` (StrEnum, L108–115): `REACTIVATED`,
  `RESUBMITTED`, `PRICE_UPDATED`, `DIRECT_SAVED`, `REFUSED` — branch labels only.
- `EditResult` (NamedTuple, L118–134): `outcome`, `moderation_failed: bool = False`,
  `errors: tuple[str, ...] = ()`. No submission-outcome field; only MODERATION_FAILED is
  distinguishable from success.
- `_submit_like` (L233–262): calls `submit_ad` with `photos=[]`. On
  `SubmitAdOutcome.PUBLISHED` → `EditResult(REACTIVATED)` (hardcoded label). Otherwise →
  `moderation_failed = (outcome is MODERATION_FAILED)`, `errors` forwarded. So
  `CONSENT_REQUIRED`, `DRAFT_GONE`, `PHOTO_UNAVAILABLE`, `INVALID_TRANSITION` arrive with
  `moderation_failed=False` but errors intact.
- `apply_edit_payload` (L265–346): the loss point is L300–307 — `if result.moderation_failed:
  return EditResult(outcome_prefix, moderation_failed=True, errors=…)`; else
  `return EditResult(outcome_prefix)` **discards `result.errors`** for the four non-moderation
  refusals and reports them as a successful submit-branch. `outcome_prefix` (kwarg, L270) is the
  caller-selected label the plan removes; success/failure is not represented at all.
- `can_edit_ad_by_service` (L163–175): composes `can_create_ad` + `can_edit_ad`. **No production
  caller** (repo-wide grep: only `test_edit_flow_service.py`). The HTML view keeps its own
  `_seller_may_create_ad`; the API gates on `can_create_ad` + `can_edit_ad`.
- `apps/ads/views/edit.py::ad_edit` POST (L198–288): redirect condition is
  `result.outcome in (REACTIVATED, RESUBMITTED) and not result.moderation_failed` (L228–237) →
  **redirects on the four discarded refusals**; only genuine MODERATION_FAILED re-renders
  `ads/edit.html` with `errors[0]`/fallback. `PRICE_UPDATED`/`DIRECT_SAVED` redirect (correct,
  preserve). `_apply_price_change` (L69–87) is a byte-identical duplicate of
  `edit_flow.apply_price_change`; **zero call sites in the view** — kept solely as the patch
  point for `test_edit.py::TestApplyPriceChangeDelegation`. `__all__` (L60–66) re-exports
  `EDITABLE_DIRECT_SAVE_STATUSES`/`EDIT_FORM_AVAILABLE_STATUSES` — used by
  `dashboard.py` (also imports `_consent_required_forbidden`, `_seller_may_create_ad`) and
  `test_edit.py`; must be preserved.
- `apps/ads/views/api/edit.py`: `SUBMIT_AD_PATH` (L148) targets the
  `edit_flow.submit_ad` global; `_apply` (L356–425) wraps the call in
  `with patch(SUBMIT_AD_PATH, _capturing(SUBMIT_AD_PATH, submitted))` (L376) — **production
  `unittest.mock.patch` on the global service symbol** — then recovers CONSENT_REQUIRED from
  the captured list (L396–402 → 403), maps service `REFUSED` → 409 `invalid_transition`
  (L404–410), and returns 200 for everything else, including the four dropped refusals
  (200 with `outcome: reactivated|resubmitted`, `moderation_failed: false`, `errors: []` —
  dishonest). `_capturing` (L428–445) uses `import_module` + `wraps`.
- `apps/ads/services/submission.py::SubmitAdOutcome` (L53–67): `PUBLISHED`, `MODERATION_FAILED`,
  `PHOTO_UNAVAILABLE`, `DRAFT_GONE`, `INVALID_TRANSITION`, `CONSENT_REQUIRED`.
  `SubmitAdResult` (L70–81): `outcome` + `errors: list[str]`; docstring pins "outcome in its own
  field, never in a truthiness position". `submit_ad` (L196–484) runs consent gate → staged-media
  plan → thumbnails → `transaction.atomic()` (locked re-fetch, save, images,
  `transition_to(ON_MODERATION)`, `auto_moderate`) → returns PUBLISHED or MODERATION_FAILED;
  lock timeout stays an exception.

### Baseline (57966ea0) semantics

No `edit_flow.py` existed; `ad_edit` (baseline L248–290 reactivation, L292–334 PUBLISHED text
branch) called `submit_ad` inline and branched on the typed outcome: **redirect only when
`result.outcome is SubmitAdOutcome.PUBLISHED`; every other outcome re-rendered
`ads/edit.html` with `result.errors[0] or _("Ad failed moderation checks")` (HTTP 200)**. That
covers CONSENT_REQUIRED/DRAFT_GONE/PHOTO_UNAVAILABLE/INVALID_TRANSITION+MODERATION_FAILED.
Price-only and direct-save branches were inline at the view and redirected on save (with the
explicit allow-list refusal rendering the "cannot be edited in its current status" message).
The current `TestApplyPriceChangeDelegation` patch target was then real production code
(view L344/L367 at baseline); after `c3c604b2` it is dead production logic kept for a test
import — exactly what P0 removes. Current files are **byte-identical to `c3c604b2`**; the API
adapter with the patch workaround arrived in `1f71bef4`.

### Exact callers/call sites

- `apply_edit_payload`: HTML `ad_edit` (twice, with `outcome_prefix=`), API `_apply` (once, with
  `outcome_prefix=`), tests (`test_edit_flow_service.py`, `test_edit_route_api.py`). No other
  production caller; no bot caller (`src/telegram_bot` has zero `edit_flow` references).
- `EditResult` consumers: only the two views above + tests.
- `can_edit_ad_by_service`: tests only (`test_edit_flow_service.py::TestCanEditAdByService`).
- `views.edit::_apply_price_change`: imported by `test_edit.py` (L36) and patched at
  `apps.ads.views.edit.normalize_price_to_eur` (L715); docstring references in
  `price_normalizer.py` (L135) and `test_recompute_command.py` (L371) only.
- Re-export consumers: `dashboard.py` (L16–20), `test_edit.py`, `test_dashboard`-family tests;
  `urls.py` (L7) routes `ad_edit` as `ads:edit`.

### Test inventory — wrong vs correct encodings

Encode the **wrong post-migration contract** (must change with P0):
- `test_edit_flow_service.py::TestCanEditAdByService` (L88–138) — pins the to-be-removed symbol.
- All `outcome_prefix=` call sites: `test_edit_flow_service.py` L247–248, L263–264, L278–279,
  L296–297; `test_edit_route_api.py` L412–416, L605–614 — pin the misleading-label parameter.
- `test_edit.py::TestApplyPriceChangeDelegation` (L694–723) — patches the duplicate production
  helper; rewrite against `edit_flow.apply_price_change` patching
  `apps.ads.services.edit_flow.normalize_price_to_eur` (the real dependency seam).
- Missing coverage (the actual regression is untested): no service, HTML, or API test drives
  `CONSENT_REQUIRED`/`DRAFT_GONE`/`PHOTO_UNAVAILABLE`/`INVALID_TRANSITION` through the edit
  seam. API: those currently yield a dishonest 200; HTML: dashboard redirect.

Encode **correct baseline-compatible behavior** (survive, some need call-site-only updates):
- HTML suites patching `apps.moderation.services.auto_moderation.auto_moderate` (PUBLISHED→302,
  MODERATION_FAILED→200+error): `test_edit.py` L92–209, L363–685 — the honest seam; unaffected.
- HTML refusal tests: `TestEditOtherStatusDirectSave` (L1043+), `TestEditStatusAllowListEnumeration`
  (L1176+), dashboard gate (L1273+) — unaffected.
- `test_edit_route_api.py::test_submit_ad_consent_required_race_maps_to_403` (L319–338) — its
  expectation (403) is the honest behavior; it monkeypatches `edit_flow.submit_ad` (correct test
  seam) and needs no change once the API reads the honest result instead of `_capturing`.
- `test_edit_route_api.py::test_reactivation_moderation_failure_is_200` (L533–556) — 200 on
  MODERATION_FAILED is the documented O-2a commit rule (matches submit row of api-surface.md);
  keep. Happy-path `TestEditOutcomeMatrix` (L427+) keeps 200s for genuinely successful branches.
- `test_edit_views_locking.py`, `test_db_lock_timeout_boundary.py` (patches
  `edit.Ad.objects.select_for_update`, not the edit result) — unaffected.

### Existing outcome patterns to follow (reuse, do not invent)

- `submission.py::SubmitAdResult` — StrEnum `outcome` carried in its own field + `errors`;
  this is the dominant in-project typed-outcome pattern and the exact type
  `_submit_like` already holds before losing it.
- `lifecycle.py` — `ArchiveResult`/`ReactivateResult`/`DeleteResult` NamedTuples with honest
  status fields (`ReactivateResult.passed: bool | None`), never re-labeled by callers.
- `apps/ads/views/api/submit.py::_refusal` (L515–548) — the **honest outcome→problem mapping
  precedent** for the temporarily-retained API: CONSENT_REQUIRED→403, INVALID_TRANSITION/
  DRAFT_GONE/PHOTO_UNAVAILABLE→409 with existing `type` tokens; MODERATION_FAILED→200 with
  parked state + errors. The fixed `api/edit.py` should mirror this table.
- Reachability note for G1 parametrized tests: through the edit seam, `photos=[]` makes
  PHOTO_UNAVAILABLE unreachable naturally; the outer row lock makes INVALID_TRANSITION
  (ARCHIVED/PUBLISHED→ON_MODERATION is legal) and DRAFT_GONE ~unreachable; CONSENT_REQUIRED is
  the real race. Service/HTML tests must inject the four refusals by monkeypatching
  `apps.ads.services.edit_flow.submit_ad` (the pattern
  `test_submit_ad_consent_required_race_maps_to_403` already uses), while PUBLISHED and
  MODERATION_FAILED run for real via `permissive_criteria`/`banning_criteria`.

### Risks and constraints

- Regression is user-visible in HTML only via the consent race / unnatural delete races
  (silently successful dashboard redirect for a refused edit); fixing it changes observable
  behavior back to baseline — by design, but wrong-fix risk is silently breaking
  redirect/render for the honest success paths. Pin PUBLISHED→302 and MODERATION_FAILED→200+form
  first, then add refusal tests.
- Signature churn: removing `outcome_prefix` and adding a submission-outcome field changes
  `apply_edit_payload`'s public surface; all four production call sites + both test files must
  change together. Keep `EditResult` a NamedTuple (positional construction used in tests).
- `test_import_rule.py` (R-F2) pair `("apps.ads.views.api.edit", "apps.ads.views.edit")`:
  after deleting `patch`/`import_module`/`SubmitAdOutcome`/`SubmitAdResult` imports from
  `api/edit.py`, its remaining imports must stay within the union of the HTML view's imports —
  update both modules coherently.
- API response-shape churn for the four refusals (200→403/409) is pre-B2-approval; no product
  consumer found in-repo, but the honest mapping must reuse the existing §2.5 problem tokens
  (as `submit.py` does) and `docs/01-spec/api-surface.md` row 6 (L73) + errors row (L129) +
  the `api/edit.py` docstring table must be updated in the same change.
- i18n: no new msgids needed — "Please accept the personal data storage consent first."
  (ru .po L282), "Ad not found" (L1550), "One of your photos is no longer available. Please
  upload it again." (L512), fallback "Ad failed moderation checks" (L499) all exist;
  INVALID_TRANSITION (empty errors) renders the existing baseline fallback message.
- Preserve: `EDITABLE_DIRECT_SAVE_STATUSES`/`EDIT_FORM_AVAILABLE_STATUSES` semantics and their
  re-exports (dashboard + tests); the single-save publish-clock reset in the price branch
  (duplicate-alert guard `test_edit_published_price_only_fires_single_post_save`);
  direct-save allow-list refusals; lock-timeout boundary behavior.
- Two doc references to the dying duplicate helper (`price_normalizer.py` L135,
  `test_recompute_command.py` L371 docstrings) need trivial comment updates.

### Files that must change for P0

1. `src/backend/apps/ads/services/edit_flow.py` — carry the real
   `SubmitAdOutcome | None` (+ errors) in `EditResult`; drop `outcome_prefix`; derive the
   branch internally (reactivation → `REACTIVATED`, PUBLISHED+text → `RESUBMITTED`); delete
   `can_edit_ad_by_service`.
2. `src/backend/apps/ads/views/edit.py` — redirect only on successful submission; render the
   existing error path for every refusal; delete `_apply_price_change`; keep re-exports/`__all__`.
3. `src/backend/apps/ads/views/api/edit.py` — consume the honest result directly (mirror
   `submit.py::_refusal`); delete `patch`, `SUBMIT_AD_PATH`, `_capturing`, `wraps`,
   `import_module`, and now-unused imports; update the docstring mapping table.
4. `src/backend/apps/ads/tests/test_edit.py` — rewrite the delegation test against
   `edit_flow.apply_price_change`; add HTML refusal tests (no redirect, error rendered).
5. `src/backend/apps/ads/tests/test_edit_flow_service.py` — remove `TestCanEditAdByService`;
   update call sites; add the G1 parametrized six-outcome service matrix.
6. `src/backend/apps/ads/tests/test_edit_route_api.py` — update call sites; add honest-mapping
   assertions for the four refusals; keep the consent-race and O-2a tests.
7. `docs/01-spec/api-surface.md` — row 6 and errors-row refusals.
8. Docstring touch-ups: `apps/currencies/services/price_normalizer.py`,
   `apps/currencies/tests/test_recompute_command.py` (references to `edit._apply_price_change`).

## B0 research decision

Read-only research for block B0 (P0 — Repair edit results), 2026-11-04. Inputs re-read from
`architecture-correction-plan.md` §4 D07, §5 R03, §7 P0 row, §8 G1, and the B0 audit above.
Evidence re-verified at HEAD: `edit_flow.py`, `views/edit.py`, `views/api/edit.py`,
`views/api/submit.py`, `services/submission.py`, `services/lifecycle.py`, `testing/moderation_fixtures.py`,
`tests/test_edit_flow_service.py`, `tests/test_edit.py`, `tests/test_edit_route_api.py`,
`apps/api/tests/test_import_rule.py`, `docs/01-spec/api-surface.md`.

### Alternatives compared

| # | Option | Verdict | Reason (evidence) |
|---|---|---|---|
| A | `EditResult(outcome, submission_outcome: SubmitAdOutcome | None = None, errors: tuple[str, ...] = ())`; drop `moderation_failed` and `outcome_prefix`; derive `outcome` internally | **SELECTED** | One field set, two orthogonal facts (which branch ran; what the submission said). Reuses `SubmitAdResult`'s exact vocabulary instead of inventing a parallel one; `moderation_failed` becomes the derived predicate `submission_outcome is SubmitAdOutcome.MODERATION_FAILED`, so no boolean can contradict the enum (the current root cause). No production import change for `views/api/edit.py` beyond what P4 deletes (`SubmitAdOutcome` is already imported there and in `views/edit.py`). |
| B | Carry `submit_result: SubmitAdResult | None` in `EditResult` | **REJECTED** | Couples the edit seam to the submission result **object** (its `errors: list[str]` is an un-str()-ified, mutable list of lazy strings — violating the `str()`-before-render contract `submit_ad` documents) and forces every future change of `SubmitAdResult` (P5/D23 will touch `submit_ad`) to ripple into the edit contract. Two nested NamedTuples also make the six-way matrix harder to read. Value-level copy (A) keeps the service result self-held. |
| C | Keep `moderation_failed` and add `refused: bool` | **REJECTED** | Three booleans over a six-member enum ⇒ 2³×5 combinations, most impossible, and the imprecision persists: `DRAFT_GONE`/`PHOTO_UNAVAILABLE`/`INVALID_TRANSITION`/`CONSENT_REQUIRED` all collapse into `refused` so the API cannot map them to distinct §2.5 problems without a second lookup. It also keeps the "success" label caller-selectable unless a fourth field is added. |
| D | Raise exceptions for refusals | **REJECTED** | Inverts the project's dominant typing convention (`SubmitAdResult`, `ArchiveResult`/`ReactivateResult`/`DeleteResult`, and `submit_ad`'s explicit "`INVALID_TRANSITION` is a business outcome, not an exception"). It would put consent/status refusals on the same channel as `OperationalError` and the ORM's `DatabaseError`/`Http404` handling in both views, forcing exception-shape changes to the HTML 403/404 branches, contradicting the plan §9 "do not broaden catches to convert DB errors/authorization into apparent success/success-shaped flows", and rewriting the existing API tests that monkeypatch `edit_flow.submit_ad` to return a result. |

### Selected contract

**1. `apps/ads/services/edit_flow.py`**

- `EditOutcome` is unchanged (5 members; DB/API-facing vocabulary stays stable).
- `EditResult` becomes:
  `class EditResult(NamedTuple): outcome: EditOutcome; submission_outcome: SubmitAdOutcome | None = None; errors: tuple[str, ...] = ()`.
  Positional order is **kept** (`outcome` first) so existing `EditResult(EditOutcome.X)` constructions stay valid;
  the optional second/third fields are keyword-only in **call sites** (write `EditResult(EditOutcome.REACTIVATED, submission_outcome=result.outcome, errors=errors)`), never positionally, so future field insertions cannot silently reorder. No `moderation_failed` field; where the current API still serializes `moderation_failed`, it is computed as `result.submission_outcome is SubmitAdOutcome.MODERATION_FAILED`.
- Docstrings: replace the `moderation_failed` paragraph with "`submission_outcome` is `None` for the two non-submission branches (`PRICE_UPDATED`, `DIRECT_SAVED`); it is always set for `REACTIVATED`/`RESUBMITTED` and for `REFUSED` after that branch's `submit_ad` refusal. `errors` always carries the submission's `str()`-ified errors — empty for `PUBLISHED`, `PRICE_UPDATED`, `DIRECT_SAVED` and the status-set `REFUSED`."

**2. Branch derivation (no caller labels)**

Replace the `is_reactivation` → `outcome_prefix` mapping with an internal branch choice:

```
is_reactivation = ad.status == AdStatus.ARCHIVED and reactivate
is_text_resubmit = ad.status == AdStatus.PUBLISHED and text_fields_changed(dto, ad)

if is_reactivation or is_text_resubmit:
    branch = EditOutcome.REACTIVATED if is_reactivation else EditOutcome.RESUBMITTED
    result = submit_ad(SubmitAdInput(...))            # unchanged input
    return EditResult(branch,
                      submission_outcome=result.outcome,
                      errors=tuple(str(e) for e in result.errors))
```

The `PUBLISHED` price-only, `EDITABLE_DIRECT_SAVE_STATUSES`, and final status-set branches are untouched and return `EditResult(EditOutcome.PRICE_UPDATED)` / `EditResult(EditOutcome.DIRECT_SAVED)` / `EditResult(EditOutcome.REFUSED)` — `submission_outcome is None`. `apply_edit_payload` drops the keyword-only `outcome_prefix` parameter; `is_reactivation` is recomputed internally from the same two inputs (it is already a pure function of `ad`/`reactivate`; no duplicate lock or query is added).

**3. `EditOutcome` → `SubmitAdOutcome` mapping**

| Branch | `submit_ad` called | `submission_outcome` | HTML status after | Redirect? |
|---|---|---|---|---|
| `REACTIVATED` | yes (ARCHIVED + `reactivate`) | `PUBLISHED` \| `MODERATION_FAILED` \| `CONSENT_REQUIRED` \| `INVALID_TRANSITION` \| `DRAFT_GONE` \| `PHOTO_UNAVAILABLE` | `PUBLISHED` set; `MODERATION_FAILED` parks; all four refusals leave status unchanged under the caller tx | **only** `PUBLISHED` |
| `RESUBMITTED` | yes (PUBLISHED + text change) | same six | same | **only** `PUBLISHED` |
| `PRICE_UPDATED` | no | `None` | stays `PUBLISHED`, clock reset, single save | yes (unchanged) |
| `DIRECT_SAVED` | no | `None` | unchanged (`DRAFT`/`ON_MODERATION`) | yes (unchanged) |
| `REFUSED` | no (status outside both sets) | `None` | unchanged | no — existing "cannot be edited" 200 render |

Note: on refusal `submit_ad` may still have committed nothing (each refusal is an early return before `save()`), so the outer `transaction.atomic()` leaves the row untouched — the same guarantee the HTML/API lock already relies on.

**4. HTML `apps/ads/views/edit.py::ad_edit`** — drop `outcome_prefix`; keep the two calls as one call `result = apply_edit_payload(ad, dto, bool(request.POST.get("reactivate")))` (the `is_reactivation` computation moves into the service). Replace the redirect/render block with:

```
if result.outcome in (EditOutcome.REACTIVATED, EditOutcome.RESUBMITTED):
    if result.submission_outcome is SubmitAdOutcome.PUBLISHED:
        # log line selection depends only on result.outcome (RESUBMITTED -> text)
        return redirect("ads:dashboard")
    re-fetch + render ads/edit.html with
        "error": result.errors[0] if result.errors else _("Ad failed moderation checks")
```

That is **exactly baseline `57966ea0`** for both submission branches (baseline: `if result.outcome is SubmitAdOutcome.PUBLISHED: redirect else render(result.errors[0] or fallback)`). `PRICE_UPDATED`/`DIRECT_SAVED`/`REFUSED` blocks are unchanged. Import `SubmitAdOutcome` (mirror import set gains it; `EditOutcome` import stays for `PRICE_UPDATED`/`DIRECT_SAVED`/`REFUSED` and the log branch). Delete `_apply_price_change` and its `CurrencyCode`/`normalize_price_to_eur` imports; keep `__all__` (`EDITABLE_DIRECT_SAVE_STATUSES`, `EDIT_FORM_AVAILABLE_STATUSES`, `ad_archive`, `ad_edit`, `ad_reactivate`) and `_seller_may_create_ad`/`_consent_required_forbidden` (dashboard + P6).

**5. API `apps/ads/views/api/edit.py::_apply`** — delete `SUBMIT_AD_PATH`, `_capturing`, `patch`, `functools.wraps`, `importlib.import_module`; keep `SubmitAdOutcome` import. Mapping, reusing `submit.py::_refusal` tokens and `submit.py` detail strings locally (the adapter must not import `apps.ads.views.api.submit` — that would add a new R-F2 import edge):

```
so = result.submission_outcome
if so is SubmitAdOutcome.CONSENT_REQUIRED            -> 403 consent_required
if so is SubmitAdOutcome.INVALID_TRANSITION          -> 409 invalid_transition   (TYPE_INVALID_TRANSITION, existing _DETAIL_INVALID_TRANSITION)
if so is SubmitAdOutcome.DRAFT_GONE                  -> 409 draft_gone           (_("The draft no longer exists. Please start a new ad."))
if so is SubmitAdOutcome.PHOTO_UNAVAILABLE           -> 409 photo_unavailable    (_("One of the photos is no longer available. Please upload it again."))
if result.outcome is EditOutcome.REFUSED             -> 409 invalid_transition   (status-set refusal; unchanged)
PUBLISHED / MODERATION_FAILED / PRICE_UPDATED / DIRECT_SAVED -> 200 JSON
```

Priority order: the `submission_outcome` checks come **before** the `REFUSED` check (mutually exclusive in practice; documented). MODERATION_FAILED stays 200 + parked state + `errors` (O-2a). `_serialize_edit_state` signature stays `(ad_id, outcome, moderation_failed: bool, errors)` and the caller passes `result.submission_outcome is SubmitAdOutcome.MODERATION_FAILED`. Response body keys do **not** change (no `submission_outcome` key is added to JSON — out of scope; the `outcome` value for REACTIVATED/RESUBMITTED already matches `SubmitAdOutcome.PUBLISHED|MODERATION_FAILED` spellings, and a refusal now never yields a 200 with an edit-branch label). Update the module docstring table (lines 38–58) to the honest table and note that refusals now carry `draft_gone`/`photo_unavailable`/`invalid_transition`, not only `invalid_transition`.

**6. Deletions** — `can_edit_ad_by_service` (zero production callers; the API composes `can_create_ad` + `can_edit_ad`, the HTML keeps `_seller_may_create_ad`) and `views/edit.py::_apply_price_change` (zero call sites; test-only patch point). `views/edit.py` keeps re-exports; `dashboard.py` untouched.

**7. Tests**

- `test_edit_flow_service.py`: delete `TestCanEditAdByService`; drop every `outcome_prefix=`; add a **six-outcome parametrized service matrix** (`SubmitAdOutcome` × branch):
  - `PUBLISHED`, `MODERATION_FAILED` × (`REACTIVATED`, `RESUBMITTED`) — run **for real** (`permissive_criteria` / `banning_criteria`; `banning_criteria` changes the title to contain "spam"; harmless: `submit_ad` overwrites it);
  - `CONSENT_REQUIRED`, `DRAFT_GONE`, `PHOTO_UNAVAILABLE`, `INVALID_TRANSITION` × (`REACTIVATED`, `RESUBMITTED`) — via `monkeypatch.setattr("apps.ads.services.edit_flow.submit_ad", lambda *a, **k: SubmitAdResult(outcome, ["reason"]))`. These are unreachable via the real call: `photos=[]` never produces `PHOTO_UNAVAILABLE`; the caller's lock + `submit_ad`'s locked re-fetch make `DRAFT_GONE` a race only; the caller's `is_reactivation` computation makes `INVALID_TRANSITION` a race only; `CONSENT_REQUIRED` requires a mid-request consent withdrawal, which is the **one** refusal also covered end-to-end through HTML/API.
  Each row asserts: `result.outcome` is the derived branch, `result.submission_outcome is <the injected outcome>`, `result.errors == ("reason",)`, and the DB row is unchanged **except** for `PUBLISHED` (status committed) and `MODERATION_FAILED` (parked).
- `test_edit.py`: rewrite `TestApplyPriceChangeDelegation` to call `edit_flow.apply_price_change` and patch `apps.ads.services.edit_flow.normalize_price_to_eur` (the real dependency call site). Add HTML tests: `CONSENT_REQUIRED` monkeypatched on `edit_flow.submit_ad` → 200 render + `(result.errors[0])`, no redirect; `DRAFT_GONE` (empty-errors outcome) → 200 with the fallback `"Ad failed moderation checks"`. Keep all `auto_moderate` patch tests unchanged (they assert 302/200 and pass through the new contract).
- `test_edit_route_api.py`: drop `outcome_prefix=` at L412–416 and L605–614; `TestEditOutcomeMatrix`'s REACTIVATED/PUBLISHED path still yields 200; add refusal-row parametrization (`CONSENT_REQUIRED` → 403, `DRAFT_GONE`/`PHOTO_UNAVAILABLE`/`INVALID_TRANSITION` → 409 with respective `type`). `test_submit_ad_consent_required_race_maps_to_403` keeps its monkeypatch (now exercising the honest path); `test_reactivation_moderation_failure_is_200` keeps.
- Verification commands: the §8 P0 docker block, then `uv run ruff check`/`basedpyright` on touched files, then `.\Makefile.ps1 test`.

**8. `docs/01-spec/api-surface.md`** — update **now**, in the same commit (the mapping becomes honest at P0, and the API adapter stays live until P4): row 6 (L73) gains the refusal family `409 draft_gone / photo_unavailable / invalid_transition` + `403 consent_required` (submit-time race); the errors row (L129) splits "edit refusal" into the status-set refusal (`not_editable`/`invalid_transition`) and the `submit_ad` refusal family; the S4.4 narrative (L821+) and the `api/edit.py` docstring table must agree. No new i18n msgids: the `draft_gone`/`photo_unavailable` detail msgids already exist in the catalog (shipped with the submit endpoint). `price_normalizer.py` L135 and `test_recompute_command.py` L371 docstrings mentioning `edit._apply_price_change` get a one-line comment update.

### Risks on the selected path

- **Silent behavior change for consent/submission refusal** (deliberate, baseline-restoring): HTML changes from "302 redirect with the edit silently not applied" to "200 + error". Mitigation: pin PUBLISHED→302 and MODERATION_FAILED→200 first, then add the refusal assertions; compare against `57966ea0`.
- **R-F2 import-rule breakage**: `api/edit.py` must not import anything its mirror (`views/edit.py`) does not (plus `ALLOWLIST`). After the fix it imports `SubmitAdOutcome` (also imported by the mirror after step 4), drops `unittest.mock`/`importlib`/`functools` (stdlib-whitelisted anyway), and declares its own `TYPE_DRAFT_GONE`/`TYPE_PHOTO_UNAVAILABLE`/detail strings instead of importing `views.api.submit`. `pydantic`/`apps.core.utils.problem`/`apps.core.schemas`/`apps.users.services.account_state`/`apps.core.enums.RateLimitBudget` remain allowlisted.
- **NamedTuple positional breakage**: avoided by keeping `outcome` first and leaving the new fields optional; test constructions `EditResult(EditOutcome.X)` continue to work (there are none in production; all production sites are internal to `edit_flow.py`). Making construction fully explicit (keyword) for the 3-field form is enforced by review, not by the type.
- **Doc/i18n impact**: no new msgids in code; doc updates mandatory (row 6, errors row, S4.4 narrative, docstrings) — otherwise G6 fails.

### Acceptance for B0 (maps to G1)

Every `SubmitAdOutcome` × both submission branches asserted at the service tier; HTML asserts no redirect on refusal and the error text; API asserts 403/409 for the refusal family without `unittest.mock.patch`; price-only single-save and direct-save invariants unchanged (`test_edit.py` L496 set); `can_edit_ad_by_service` and `_apply_price_change` gone with the test patch point retargeted at `edit_flow`.
## B0 task description

```yaml
id: b0_repair_edit_results

title: >
  P0 — Repair edit results: carry the honest SubmitAdOutcome in EditResult,
  redirect the HTML edit only on PUBLISHED, map the API edit without
  unittest.mock.patch, and delete the two test-only production symbols.

priority: high

type: implementation

depends_on: []

# ── Plan/Audit report source (REQUIRED — this task originates from the
#    architecture-correction plan and the B0 audit/research blocks) ──
source_reference: .ai/plans/architecture-correction-plan.md
source_section: §5 R03 — Is the edit extraction safe to keep? · §7 P0 — Repair edit results · §8 G1 — Edit correctness
source_file: .ai/plans/architecture-correction-execution.md
source_blocks:
  - "B0 audit findings"
  - "B0 research decision"    # selected contract = alternative A

extra_context: |
  Baseline semantic anchor: migration-commit 57966ea0's ad_edit branched on the typed
  submit_ad result — redirect ONLY when result.outcome is SubmitAdOutcome.PUBLISHED;
  every other outcome re-rendered ads/edit.html (HTTP 200) with
  "result.errors[0] or fallback 'Ad failed moderation checks'". The regression introduced
  by c3c604b2 (edit_flow extraction) is that apply_edit_payload discards four of
  SubmitAdOutcome's six members behind moderation_failed=False; ad_edit then redirects
  on them, and views/api/edit.py::_apply recovers the consent outcome only by globally
  patching apps.ads.services.edit_flow.submit_ad at request time with unittest.mock.patch.
  Current production files are byte-identical to c3c604b2 (verified in the B0 audit).

  Chosen contract (research decision A, do not re-litigate):
    EditResult(NamedTuple):
        outcome: EditOutcome
        submission_outcome: SubmitAdOutcome | None = None
        errors: tuple[str, ...] = ()
    moderation_failed is DERIVED where consumed
    (result.submission_outcome is SubmitAdOutcome.MODERATION_FAILED), never stored.
    outcome stays first: EditResult(EditOutcome.PRICE_UPDATED) and other 1-field
    positional constructions keep working; the new fields are supplied by KEYWORD
    at every construction site (review-enforced), never positionally.

description: >
  Replace the lossy edit result contract with the honest one. The service keeps the
  branch label (REACTIVATED / RESUBMITTED / PRICE_UPDATED / DIRECT_SAVED / REFUSED) and
  the submission outcome as two orthogonal typed facts, dropping moderation_failed and
  the caller-supplied outcome_prefix. The HTML view redirects only when the submission
  published, rendering the existing error form for every other submission outcome
  (restoring the 57966ea0 baseline). The API adapter consumes the typed result directly
  (no unittest.mock in production), mapping refusal outcomes to the existing §2.5
  problem tokens declared locally. Delete can_edit_ad_by_service and
  views/edit.py::_apply_price_change (both production-dead, kept only as test patch
  points) and retarget the delegation test at the real service seam. Update the mapping
  docs and the two docstrings that name the dying duplicate. No schema, settings,
  dependency, i18n-catalog, or lifecycle-atomicity change.

goals:
  - all six SubmitAdOutcome members survive apply_edit_payload in typed form with errors
  - success is a property of the submission outcome, never of a caller-provided label
  - HTML edit: redirect only on PUBLISHED; every other submission outcome re-renders
    ads/edit.html with result.errors[0] or the existing fallback string
  - API edit: honest per-outcome mapping without unittest.mock.patch/SUBMIT_AD_PATH/_capturing
  - PRICE_UPDATED / DIRECT_SAVED / status-set REFUSED behaviour byte-identical to today
  - test-only production patch points removed; tests patched at real dependency seams
  - docs describe the mapping that actually ships (row 6, errors row, S4.4 narrative)

# ─────────────────────────────────────────────────────────────────────────────
# Files and semantic targets (symbols only — never line numbers)
# ─────────────────────────────────────────────────────────────────────────────

files:

  # ── 1. Service contract ────────────────────────────────────────────────────
  - path: src/backend/apps/ads/services/edit_flow.py
    targets:
      - type: module_docstring
        name: edit_flow module docstring
        change: replace the closing paragraph that refers consumers to
          EditResult.moderation_failed ("A moderation failure on families 1/2 is
          reported through the same REFUSED-adjacent shape … see
          :class:`EditResult.moderation_failed` and `errors`") with the
          submission_outcome semantics.
      - type: class
        name: EditResult
        action: replace_body
      - type: function
        name: _submit_like
        action: replace_body
      - type: function
        name: apply_edit_payload
        action: replace_signature_and_body
      - type: function
        name: can_edit_ad_by_service
        action: delete_symbol            # zero production callers (repo-wide: tests only)
      - type: docstring
        name: can_edit_ad docstring
        change: its final paragraph references the deleted
          "see :func:`can_edit_ad_by_service`, which composes it" — rewrite to name the
          caller-side consent gates directly (can_create_ad / the HTML _seller_may_create_ad)
    semantic_anchors:
      keep_unchanged:
        - EditOutcome (all five members and values — vocabulary is frozen)
        - EDITABLE_DIRECT_SAVE_STATUSES / EDIT_FORM_AVAILABLE_STATUSES
        - can_edit_ad
        - text_fields_changed
        - apply_price_change (body byte-identical — it becomes the delegation target)
        - resolve_edit_currency
        - the submit_ad(SubmitAdInput(...)) construction inside _submit_like
          (field set incl. photos=[] — byte-identical)
        - apply_edit_payload's PRICE_UPDATED branch body (single shared save +
          reset_publish_clock — the duplicate-alert guard)
        - apply_edit_payload's DIRECT_SAVED branch body
        - apply_edit_payload's final status-set REFUSED return
        - OperationalError propagation (lock timeout stays an exception)
      derive_internally: >
        apply_edit_payload computes the branch label itself, from the same two inputs it
        already has: is_reactivation = ad.status is AdStatus.ARCHIVED and reactivate;
        is_text_resubmit = ad.status is AdStatus.PUBLISHED and text_fields_changed(dto, ad).
        No duplicate lock or query is introduced (pure function of ad/reactivate/dto).

  # ── 2. HTML view ──────────────────────────────────────────────────────────
  - path: src/backend/apps/ads/views/edit.py
    targets:
      - type: function
        name: _apply_price_change
        action: delete_symbol            # byte-identical duplicate of
                                          # edit_flow.apply_price_change; zero view call sites
      - type: import_block
        name: module imports
        change: >
          add SubmitAdOutcome to the existing `from apps.ads.services.submission import
          AdEditInput` statement; after deleting _apply_price_change and the
          is_reactivation local, remove the imports that become unused (CurrencyCode,
          normalize_price_to_eur, Decimal, AdStatus — verify each with ruff F401 before
          removal; keep anything still referenced).
      - type: function
        name: ad_edit
        action: replace_in_function      # POST block only
      - type: module_constant
        name: __all__
        action: keep_byte_identical      # EDITABLE_DIRECT_SAVE_STATUSES,
                                          # EDIT_FORM_AVAILABLE_STATUSES, ad_archive,
                                          # ad_edit, ad_reactivate
    semantic_anchors:
      insert_after: the AdEditInput.model_validate call inside ad_edit's atomic block
      delete_in_body: the `is_reactivation = ad.status == AdStatus.ARCHIVED and
        request.POST.get("reactivate")` local (its "Determine if this is a reactivation
        request" comment moves with it)
      keep_unchanged:
        - _seller_may_create_ad and _consent_required_forbidden
          (imported by apps/ads/views/dashboard.py)
        - _ownership_refused_forbidden
        - the GET branch, ownership/consent ordering, the transaction.atomic +
          select_for_update re-fetch, the OperationalError lock-timeout re-render
          (03-DB-004)
        - ad_archive and ad_reactivate entirely (B1 owns them)
        - PRICE_UPDATED / DIRECT_SAVED / status-set REFUSED response blocks

  # ── 3. API adapter ────────────────────────────────────────────────────────
  - path: src/backend/apps/ads/views/api/edit.py
    targets:
      - type: module_constant
        name: SUBMIT_AD_PATH
        action: delete_symbol
      - type: function
        name: _capturing
        action: delete_symbol
      - type: import_block
        name: module imports
        change: >
          delete `from functools import wraps`, `from importlib import import_module`,
          `from unittest.mock import patch`, and SubmitAdResult from the
          apps.ads.services.submission import; KEEP AdEditInput (used by
          AdEditBody.to_edit_input) and SubmitAdOutcome.
      - type: function
        name: _apply
        action: replace_body
      - type: module_docstring
        name: edit API module docstring
        change: update the "Result → HTTP mapping" table (the dishonest 200-on-refusal
          rows are replaced by the refusal family), pipeline step 8 (Transition) prose,
          and the "Consent ordering" paragraph (the patch/_capturing justification is
          gone; the endpoint reads the typed result).
      - type: module_constant
        name: TYPE_DRAFT_GONE            # new: Final[str] = "draft_gone"
      - type: module_constant
        name: TYPE_PHOTO_UNAVAILABLE     # new: Final[str] = "photo_unavailable"
      - type: module_constant
        name: _DETAIL_DRAFT_GONE         # new: existing msgid "The draft no longer
                                          # exists. Please start a new ad."
      - type: module_constant
        name: _DETAIL_PHOTO_UNAVAILABLE  # new: existing msgid "One of the photos is no
                                          # longer available. Please upload it again."
      - type: module_constant
        name: __all__
        change: add TYPE_DRAFT_GONE and TYPE_PHOTO_UNAVAILABLE to the existing
          entries (mirror submit.py's __all__ convention)
    semantic_anchors:
      keep_unchanged:
        - AdEditBody (all validators and to_edit_input)
        - edit_view pipeline (identity → method → rate limit → body → uniform 404 →
          consent → can_edit_ad / 409 not_editable)
        - _parse_body, _body_validation_problem, _retryable_response
        - _serialize_edit_state SIGNATURE (ad_id, outcome, moderation_failed: bool,
          errors) and the JSON body keys — the caller passes the derived bool
          `result.submission_outcome is SubmitAdOutcome.MODERATION_FAILED`;
          do NOT add a submission_outcome JSON key
        - the Ad.DoesNotExist and DatabaseError/is_lock_timeout handling (503 retryable)
    forbidden_imports:
      - apps.ads.views.api.submit    # tokens are spelled identically but DECLARED
        LOCALLY; importing the submit module would add a new R-F2 mirror edge

  # ── 4. Tests ──────────────────────────────────────────────────────────────
  - path: src/backend/apps/ads/tests/test_edit_flow_service.py
    targets:
      - type: import_block
        name: module imports
        change: remove can_edit_ad_by_service; add SubmitAdOutcome and SubmitAdResult
          to the apps.ads.services.submission import
      - type: class
        name: TestCanEditAdByService
        action: delete_symbol          # pins the removed symbol
      - type: test
        name: TestApplyEditPayloadDirectSave.test_direct_save_writes_fields_and_keeps_status
        change: replace `result.moderation_failed is False` with
          `result.submission_outcome is None` (keep the `result.errors == ()` assertion)
      - type: test
        name: TestApplyEditPayloadRefusal.test_refused_status_is_untouched
        change: same assertion swap as above
      - type: test
        name: TestApplyEditPayloadResubmit.test_text_change_reports_resubmitted
        change: drop outcome_prefix kwarg; assert
          result.submission_outcome is SubmitAdOutcome.PUBLISHED
      - type: test
        name: TestApplyEditPayloadResubmit.test_text_change_moderation_failure_is_flagged
        change: drop outcome_prefix kwarg; assert
          result.submission_outcome is SubmitAdOutcome.MODERATION_FAILED
      - type: test
        name: TestApplyEditPayloadResubmit.test_description_change_alone_counts_as_text_change
        change: drop outcome_prefix kwarg
      - type: test
        name: TestApplyEditPayloadReactivation.test_reactivation_reports_reactivated
        change: drop outcome_prefix kwarg; assert
          result.submission_outcome is SubmitAdOutcome.PUBLISHED
      - type: class
        name: TestApplyEditPayloadSubmitOutcomeMatrix   # NEW (name is a suggestion)
        action: add_code
      - type: module_docstring
        name: test_edit_flow_service module docstring
        change: stop naming can_edit_ad_by_service; name the new matrix
    keep_unchanged:
      - TestCanEditAd (whole class — can_edit_ad survives)
      - TestApplyEditPayloadPriceOnly (add submission_outcome-is-None assertions only
        if trivial; the PRICE_UPDATED row semantics)
      - TestApplyEditPayloadReactivation.test_archived_without_flag_is_refused
      - TestApplyEditPayloadRefusal.test_every_status_has_one_outcome

  - path: src/backend/apps/ads/tests/test_edit.py
    targets:
      - type: import_block
        name: module imports
        change: remove _apply_price_change from the apps.ads.views.edit import;
          add `from apps.ads.services.edit_flow import apply_price_change`
      - type: class
        name: TestApplyPriceChangeDelegation
        action: replace_symbol          # same DRY invariant, real seam
      - type: class
        name: TestEditSubmissionRefusalsRender   # NEW (name is a suggestion)
        action: add_code
      - type: leading_comment
        name: "Parity test" section banner
        change: the "Parity test: _apply_price_change delegates to the shared utility
          (10-QLT-001 …)" banner and the class docstring retarget their wording to
          edit_flow.apply_price_change
    keep_unchanged:
      - TestReactivationStatusTransition / TestReactivationAutoModerate /
        TestPublishedTextEdit (the auto_moderate-patch PUBLISHED→302 and
        MODERATION_FAILED→200+error tests — they pass through the new contract
        unchanged and pin the honest success/render sides FIRST)
      - test_edit_published_price_only_fires_single_post_save (single-save clock guard)
      - TestEditOtherStatusDirectSave, TestEditStatusAllowListEnumeration,
        TestDashboardEditLinkGate, TestSellerWebStorageConsentGate (status-set REFUSED,
        affordance sets, consent gate)

  - path: src/backend/apps/ads/tests/test_edit_route_api.py
    targets:
      - type: test
        name: TestInvalidTransition.test_archived_without_reactivate_matches_service_tier
        change: drop the outcome_prefix kwarg from its apply_edit_payload call
      - type: test
        name: TestEditOutcomeMatrix.test_endpoint_outcome_matches_service_tier
        change: drop the outcome_prefix kwarg from its apply_edit_payload call
      - type: class
        name: TestSubmitOutcomeRefusalMapping   # NEW (name is a suggestion)
        action: add_code
      - type: module_docstring
        name: test_edit_route_api module docstring
        change: add the refusal-family rows to the coverage bullet list
    keep_unchanged:
      - test_submit_ad_consent_required_race_maps_to_403 (monkeypatches
        apps.ads.services.edit_flow.submit_ad — the correct seam; its 403 expectation
        now exercises the honest path; body unchanged)
      - test_reactivation_moderation_failure_is_200 (O-2a: MODERATION_FAILED is 200
        + parked state + errors)
      - TestEditOutcomeMatrix happy paths (REACTIVATED / RESUBMITTED / PRICE_UPDATED /
        DIRECT_SAVED all stay 200 with unchanged JSON keys incl. "moderation_failed")
      - TestAuthMatrix / TestMethodGate / TestValidationMatrix / TestRateLimit /
        TestUniformNotFound / TestConsentGate / TestNotEditable / TestO27BodyContract
        and the route-registration smoke test

  # ── 5. Docs and docstring touch-ups ───────────────────────────────────────
  - path: docs/01-spec/api-surface.md
    targets:
      - type: table_row
        name: endpoint table row whose "Action" cell is "Edit" (row #6)
        change: its "Error notes" cell gains the submit-time refusal family
          (403 consent_required; 409 invalid_transition / draft_gone /
          photo_unavailable) alongside the existing status-set refusal mapping
      - type: table_row
        name: errors table row "Edit refusal (status outside editable/affordance sets)"
        change: split its one-shot wording — the pre-gate status refusal stays
          409 not_editable (with 409 invalid_transition when the branch table refuses
          an in-affordance status), and the edit's submit-branch refusals follow the
          SubmitAdOutcome family
      - type: section
        name: S4.4 narrative ("POST /api/v1/ads/{id}/edit/ shipped …")
        change: the "Result → HTTP mapping" table gains the refusal rows; the sentence
          claiming "the endpoint observes the shared orchestrator's result; edit_flow.py
          and submission.py are untouched" is replaced (the endpoint now reads
          EditResult.submission_outcome; edit_flow.py's contract changed in this task);
          the "Tests:" sentence adds the refusal mapping rows
      - type: section
        name: S4.2 narrative paragraph mentioning can_edit_ad_by_service and EditResult
        change: minimal factual correction of exactly those two present-tense claims
          (the composed-predicate symbol no longer exists; EditResult carries
          submission_outcome, not moderation_failed). No restructuring, no ledger
          compression — that is B7 (P7) work.
  - path: src/backend/apps/currencies/services/price_normalizer.py
    targets:
      - type: docstring
        name: normalize_price_to_eur docstring
        change: the line "Shared seam used by `edit._apply_price_change` and
          `submit_ad`" → reference edit_flow.apply_price_change (one line)
  - path: src/backend/apps/currencies/tests/test_recompute_command.py
    targets:
      - type: docstring
        name: concurrent_price_edit docstring
        change: "mirroring `edit._apply_price_change`" → mirror
          edit_flow.apply_price_change (one line)

# ─────────────────────────────────────────────────────────────────────────────
# Changes with code hints (contract shapes — implement against the live code)
# ─────────────────────────────────────────────────────────────────────────────

changes:

  - action: modify_code
    target: apps/ads/services/edit_flow.py::EditResult
    description: >
      Honest two-fact contract. Docstring states: submission_outcome is None for the
      two non-submission branches (PRICE_UPDATED, DIRECT_SAVED) and for the status-set
      REFUSED; it is always set for REACTIVATED / RESUBMITTED; errors always carries
      the submission's str()-ified errors — empty for PUBLISHED, PRICE_UPDATED,
      DIRECT_SAVED and the status-set REFUSED.
    code_hint: |
      class EditResult(NamedTuple):
          outcome: EditOutcome
          submission_outcome: SubmitAdOutcome | None = None
          errors: tuple[str, ...] = ()

  - action: modify_code
    target: apps/ads/services/edit_flow.py::apply_edit_payload (+ _submit_like)
    description: >
      Remove the keyword-only outcome_prefix parameter. Derive the branch internally
      from the same inputs; the submit-branch keeps its single return — no
      moderation_failed branching, no error discard. PRICE_UPDATED / DIRECT_SAVED /
      REFUSED returns are untouched (submission_outcome defaults to None).
    code_hint: |
      is_reactivation = ad.status == AdStatus.ARCHIVED and reactivate
      is_text_resubmit = ad.status == AdStatus.PUBLISHED and text_fields_changed(dto, ad)
      if is_reactivation or is_text_resubmit:
          branch = EditOutcome.REACTIVATED if is_reactivation else EditOutcome.RESUBMITTED
          price_currency = resolve_edit_currency(dto, ad)
          submit_result = submit_ad(SubmitAdInput(...))       # unchanged input, photos=[]
          return EditResult(
              branch,
              submission_outcome=submit_result.outcome,
              errors=tuple(str(error) for error in submit_result.errors),
          )
      # (fold _submit_like into this branch, or give it a `branch` parameter —
      #  the constraint is: no caller-provided label, one return, errors preserved)

  - action: modify_code
    target: apps/ads/views/edit.py::ad_edit (POST block)
    description: >
      One apply_edit_payload call passing the raw POST flag (the ARCHIVED conjunct now
      lives in the service — semantically identical, the service re-checks status).
      Redirect ONLY on PUBLISHED; every other submission outcome takes the existing
      re-fetch-and-render error path. This is exactly the 57966ea0 baseline for both
      submission branches.
    code_hint: |
      result = apply_edit_payload(ad, dto, bool(request.POST.get("reactivate")))

      if result.outcome in (EditOutcome.REACTIVATED, EditOutcome.RESUBMITTED):
          if result.submission_outcome is SubmitAdOutcome.PUBLISHED:
              if result.outcome is EditOutcome.RESUBMITTED:
                  logger.info("Ad %s text edited, moved to ON_MODERATION", ad_id)
              return redirect("ads:dashboard")
          ad = Ad.objects.prefetch_related("images").get(id=ad_id)
          return render(request, "ads/edit.html", {
              "ad": ad,
              "error": result.errors[0]
              if result.errors
              else _("Ad failed moderation checks"),
          })

  - action: modify_code
    target: apps/ads/views/api/edit.py::_apply
    description: >
      Consume the honest result directly: the submitted-sink and patch context are
      gone. Refusal mapping mirrors submit.py::_refusal tokens (declared locally);
      submission_outcome checks before the status-set REFUSED check; 200 for
      PUBLISHED / MODERATION_FAILED (O-2a, keep the info log) / PRICE_UPDATED /
      DIRECT_SAVED via the unchanged _serialize_edit_state call passing the derived
      moderation_failed bool. Keep the CONSENT_REQUIRED warning log line.
    code_hint: |
      # inside the unchanged atomic() + select_for_update() block:
      result = apply_edit_payload(locked, body.to_edit_input(), body.reactivate)

      # after the except blocks:
      so = result.submission_outcome
      if so is SubmitAdOutcome.CONSENT_REQUIRED:
          logger.warning("Ad %s edit refused: consent required at submit time", ad.id)
          return problem(HTTPStatus.FORBIDDEN, TYPE_CONSENT_REQUIRED, _DETAIL_CONSENT_REQUIRED)
      if so is SubmitAdOutcome.INVALID_TRANSITION:
          return problem(HTTPStatus.CONFLICT, TYPE_INVALID_TRANSITION, _DETAIL_INVALID_TRANSITION)
      if so is SubmitAdOutcome.DRAFT_GONE:
          return problem(HTTPStatus.CONFLICT, TYPE_DRAFT_GONE, _DETAIL_DRAFT_GONE)
      if so is SubmitAdOutcome.PHOTO_UNAVAILABLE:
          return problem(HTTPStatus.CONFLICT, TYPE_PHOTO_UNAVAILABLE, _DETAIL_PHOTO_UNAVAILABLE)
      if result.outcome is EditOutcome.REFUSED:
          logger.info("Ad %s edit refused by the service branch table", ad.id)
          return problem(HTTPStatus.CONFLICT, TYPE_INVALID_TRANSITION, _DETAIL_INVALID_TRANSITION)
      # ... existing MODERATION_FAILED info log, then:
      return JsonResponse(_serialize_edit_state(
          ad.id, result.outcome,
          result.submission_outcome is SubmitAdOutcome.MODERATION_FAILED,
          result.errors,
      ))

  - action: modify_tests
    target: the three test modules (files section above)
    description: >
      Service matrix; HTML refusal-render tests; API refusal-mapping rows; delegation
      test retarget; delete every pin of the removed symbols and parameters (details
      in required_tests).

# Implementation sequence (mandatory order — each step green before the next;
# steps 1–3 land in ONE commit, no deployable intermediate revision):
sequence:
  1: >
     Service contract: edit_flow.py (EditResult, _submit_like/apply_edit_payload,
     delete can_edit_ad_by_service, docstrings). After this step the HTML/API callers
     are broken by design — do NOT commit or run the focused gate alone.
  2: >
     HTML view: views/edit.py (ad_edit POST block, delete _apply_price_change,
     imports). Update test_edit.py's import block so collection is not import-broken
     (the delegation-class rewrite itself belongs to step 4). Run the HTML-leg tests
     touched by 1+2 to confirm PUBLISHED→302 before adding refusal assertions.
  3: >
     API adapter: views/api/edit.py (_apply, deletions, local tokens, docstring,
     __all__). Immediately run the import-rule harness
     (apps/api/tests/test_import_rule.py) to confirm the R-F2 mirror subset still
     holds for the pair ("apps.ads.views.api.edit", "apps.ads.views.edit").
  4: >
     Tests: test_edit_flow_service.py, test_edit.py, test_edit_route_api.py (delete
     wrong-contract pins, add the matrix and refusal rows per required_tests).
  5: >
     Docs/docstrings: docs/01-spec/api-surface.md (row 6, errors row, S4.4, the two
     stale S4.2 claims), price_normalizer.py and test_recompute_command.py one-liners.
     Then the full verification block, then commit.

architectural_constraints:
  - Reuse the SubmitAdResult convention — outcome carried in its own typed field,
    never in a truthiness or boolean slot; no parallel invented vocabulary.
  - EditResult stays a NamedTuple; outcome stays first; the new fields keep defaults
    so one-argument positional constructions keep working; every production
    construction of the 3-field form uses keywords (review-enforced).
  - No caller-provided outcome labels: apply_edit_payload has no outcome_prefix (or
    equivalent); the branch is derived from ad.status / reactivate /
    text_fields_changed(dto, ad) inside the service.
  - No unittest.mock (or any test machinery) in production code: SUBMIT_AD_PATH,
    _capturing, patch, import_module, wraps are all deleted from views/api/edit.py.
  - The reactivate argument passed by both callers is the raw request flag
    (bool(request.POST.get("reactivate")) / body.reactivate); the ARCHIVED conjunct
    moves into the service — semantically identical to today for every status.
  - Stay within the R-F2 allowed imports for the pair
    ("apps.ads.views.api.edit", "apps.ads.views.edit") until P4 retires the harness:
    do not import apps.ads.views.api.submit (or any new module) into the API adapter;
    declare TYPE_DRAFT_GONE / TYPE_PHOTO_UNAVAILABLE and the two detail strings
    locally with the exact existing spellings; views/edit.py gains the
    SubmitAdOutcome import so the mirror union covers the adapter.
  - Preserve the public re-exports and the private helpers dashboard.py imports:
    __all__ of views/edit.py byte-identical; _seller_may_create_ad,
    _consent_required_forbidden and _ownership_refused_forbidden stay.
  - Preserve behaviour of PRICE_UPDATED (single-save publish-clock reset — no second
    save()), DIRECT_SAVED, and the status-set REFUSED render in HTML / 409
    invalid_transition in the API.
  - Preserve the HTML lock-timeout boundary (OperationalError re-render) and the API
    503 retryable response; do not broaden any exception handling.
  - API JSON body keys do not change; in particular moderation_failed remains a
    response key, computed as submission_outcome is SubmitAdOutcome.MODERATION_FAILED;
    no submission_outcome key is added.
  - No new translatable msgids anywhere (all reused strings already exist in the
    ru/bs/en catalogs); i18n catalog files are not edited in this task.
  - English only for all comments/docstrings/messages; StrEnum vocabulary frozen;
    no logging changes beyond moving the two existing log lines with their blocks.

required_tests:
  service_matrix: >
    test_edit_flow_service.py — NEW parametrized class covering every
    SubmitAdOutcome member × both submit branches (REACTIVATED: ARCHIVED ad + True;
    RESUBMITTED: PUBLISHED ad with changed title): PUBLISHED and MODERATION_FAILED run
    for real (permissive_criteria / banning_criteria — the "spam" title harmlessness is
    expected: submit_ad overwrites it); CONSENT_REQUIRED, DRAFT_GONE,
    PHOTO_UNAVAILABLE, INVALID_TRANSITION are injected via
    monkeypatch.setattr("apps.ads.services.edit_flow.submit_ad", ...) returning
    SubmitAdResult(outcome, ["reason"]). Each row asserts: the derived branch label;
    result.submission_outcome is the row's outcome; result.errors == ("reason",)
    (injected rows); and the DB row unchanged EXCEPT PUBLISHED (committed status) and
    MODERATION_FAILED (parked). Document in the class docstring why four of the six
    are unreachable through the real seam (photos=[] / caller lock / rechecked status /
    consent race).
  html_refusal_render: >
    test_edit.py — NEW class: POST an edit whose submit branch returns CONSENT_REQUIRED
    (injected via monkeypatch on apps.ads.services.edit_flow.submit_ad) → asserts
    HTTP 200 (status_code != 302, no Location header), template ads/edit.html,
    response.context["error"] equals the injected error string, and the ad row
    unchanged; and a row with INVALID_TRANSITION and empty errors → HTTP 200 with
    response.context["error"] == "Ad failed moderation checks" (the existing fallback
    msgid). Cover at least one row per submit branch (archived+reactivate vs
    published+text-change). The existing auto_moderate-patch tests already pin
    PUBLISHED→302 and MODERATION_FAILED→200+error — they must remain in the file
    unchanged.
  api_honest_mapping: >
    test_edit_route_api.py — NEW parametrized refusal class over the four injected
    SubmitAdOutcome rows: CONSENT_REQUIRED → 403 with json type consent_required;
    INVALID_TRANSITION → 409 invalid_transition; DRAFT_GONE → 409 draft_gone;
    PHOTO_UNAVAILABLE → 409 photo_unavailable — each asserting
    Content-Type application/problem+json, the type token, and the ad row unchanged;
    all four via monkeypatch.setattr("apps.ads.services.edit_flow.submit_ad", ...).
    The existing tests keep pinning the 200 side: TestEditOutcomeMatrix happy paths,
    test_reactivation_moderation_failure_is_200 (O-2a), and
    test_submit_ad_consent_required_race_maps_to_403 (unchanged, now exercising the
    honest path).
  delegation_real_seam: >
    test_edit.py::TestApplyPriceChangeDelegation — rewritten to call
    edit_flow.apply_price_change under
    unittest.mock.patch("apps.ads.services.edit_flow.normalize_price_to_eur"),
    asserting the same two delegation shapes (currency-present and None paths).
  no_redirect: >
    HTML refusal tests must assert the absence of the redirect explicitly (status 200,
    no Location header, ads/edit.html rendered) — this is the regression surface G1 names.
  wrong_contract_pins: >
    Remove exactly: TestCanEditAdByService + its import; every outcome_prefix=
    occurrence (test_edit_flow_service.py and test_edit_route_api.py); every
    result.moderation_failed field assertion (replaced by submission_outcome checks);
    the _apply_price_change import and patch target in test_edit.py.

verification:
  focused_p0: >
    docker compose --project-name mko-bazuna-test --env-file .env.test -f
    docker-compose.yml -f docker-compose.test.yml run --rm -e
    "PYTEST_OPTS=src/backend/apps/ads/tests/test_edit.py src/backend/apps/ads/tests/test_edit_views_locking.py
    src/backend/apps/ads/tests/test_edit_flow_service.py src/backend/apps/ads/tests/test_ad_lifecycle.py
    src/backend/apps/ads/tests/test_lifecycle_service.py src/backend/apps/ads/tests/test_ad_consent_gate.py
    src/backend/apps/ads/tests/test_edit_route_api.py src/backend/apps/ads/tests/test_lifecycle_api.py"
    test
  import_rule_after_api_step: >
    docker compose --project-name mko-bazuna-test --env-file .env.test -f
    docker-compose.yml -f docker-compose.test.yml run --rm -e
    "PYTEST_OPTS=src/backend/apps/api/tests/test_import_rule.py" test
    (run immediately after sequence step 3 — the R-F2 pair is the one static risk the
    focused gate does not cover; it also runs in the fast gate)
  lint: uv run ruff check src/backend/apps/ads src/backend/apps/currencies
  typecheck: >
    uv run basedpyright src/backend/apps/ads/services/edit_flow.py
    src/backend/apps/ads/views/edit.py src/backend/apps/ads/views/api/edit.py
    src/backend/apps/ads/tests/test_edit.py src/backend/apps/ads/tests/test_edit_flow_service.py
    src/backend/apps/ads/tests/test_edit_route_api.py
    src/backend/apps/currencies/services/price_normalizer.py
    src/backend/apps/currencies/tests/test_recompute_command.py
  fast_gate: .\Makefile.ps1 test     # canonical PR gate; includes the import-rule
                                     # harness and the lock-timeout boundary suites
  notes: >
    Never run `uv run pytest` locally (no DB on localhost:5432); start the test DB with
    `.\Makefile.ps1 test-db` if `docker ps --filter "name=mko-bazuna-test-db-"` is
    empty. PYTEST_OPTS replaces the xdist/reuse-db defaults — the focused run is
    serial by design. No full `.\Makefile.ps1 test-all` run is required for B0 alone
    (no seed/slow/real_images surface is touched); the final fast gate must be green
    before commit. No migration delta is expected (no model changes) — `git status
    --short` must show only the files listed in this task.

acceptance_criteria:
  - >
    Service: apply_edit_payload returns EditResult with submission_outcome set for
    REACTIVATED/RESUBMITTED, None otherwise; no outcome_prefix parameter; errors
    preserves tuple(str(e)) for every submit_ad outcome; can_edit_ad_by_service is
    gone; edit_flow module + EditResult docstrings describe the honest contract.
  - >
    HTML: only submission_outcome is SubmitAdOutcome.PUBLISHED redirects; every other
    submission outcome renders ads/edit.html (200) with errors[0] or the existing
    fallback; PRICE_UPDATED/DIRECT_SAVED/REFUSED blocks and the 03-DB-004 boundary are
    behaviour-identical to pre-task; no redirect assertion fails.
  - >
    API: no production mock indirection remains (grep apps/ads/views/api/edit.py for
    "unittest.mock", "SUBMIT_AD_PATH", "_capturing", "from functools import wraps",
    "import_module" — all absent); REFUSED still maps 409 invalid_transition;
    CONSENT_REQUIRED→403, INVALID_TRANSITION/DRAFT_GONE/PHOTO_UNAVAILABLE→409 with
    existing tokens; PUBLISHED/MODERATION_FAILED/PRICE_UPDATED/DIRECT_SAVED return
    200 with unchanged JSON keys.
  - >
    Tests: six-outcome × two-branch matrix green at the service tier (real runs for
    PUBLISHED/MODERATION_FAILED); HTML refusal-render/no-redirect tests green;
    API refusal family green; delegation test patches
    apps.ads.services.edit_flow.normalize_price_to_eur; no file under src/ references
    outcome_prefix, result.moderation_failed, can_edit_ad_by_service, or
    apps.ads.views.edit._apply_price_change.
  - >
    Harness/statics: apps/api/tests/test_import_rule.py green (R-F2 pair unchanged);
    `uv run ruff check src/backend/apps/ads src/backend/apps/currencies` clean;
    basedpyright clean on all changed files; `.\Makefile.ps1 test` green.
  - >
    Docs: api-surface.md row 6, the errors row, the S4.4 narrative, and the two stale
    S4.2 claims now state the shipped mapping (no 200-on-refusal claims, no patch
    prose, no can_edit_ad_by_service / moderation_failed references);
    price_normalizer.py and test_recompute_command.py docstrings reference
    edit_flow.apply_price_change.
  - >
    i18n: no new msgids; no .po/.mo file changes (the i18n completeness test in the
    fast gate stays green). No schema/migration/settings/env/dependency/lockfile delta.

out_of_scope:
  - Lifecycle atomicity (B1): ad_archive/ad_reactivate transaction shape,
    assert_lifecycle_owner — do not touch, even though they live in views/edit.py.
  - API retirement (B4) and exclusive-support removal (B5): the /api/v1/ edit
    endpoint, submit endpoint, problem/api_auth helpers, budgets, and
    test_import_rule.py all remain; B0 only makes the live adapter honest.
  - i18n catalog edits and any scratch makemessages run.
  - Any schema/model/migration, settings/env, middleware, dependency, or lockfile
    change.
  - P6 simplifications beyond the two deletions named here (no
    resolve_edit_currency or lock-ownership reshaping, no public-helper renames).
  - Behaviour changes to submit_ad, the price-only single-save clock semantics, the
    status sets, dashboard, bot, or the legacy moderation/HTML surfaces.

risks:
  - >
    Silent behavior change for refusal outcomes (deliberate, baseline-restoring):
    HTML goes from 302-on-refusal (bug) to 200+form. Mitigation: land the PUBLISHED→302
    and MODERATION_FAILED→200 pins first (existing tests, step 2), then add refusal
    tests; compare against the 57966ea0 baseline semantics quoted in extra_context.
  - >
    Signature churn: removing outcome_prefix changes apply_edit_payload's public
    surface; ALL production call sites (the two calls in views/edit.py::ad_edit and the
    one in views/api/edit.py::_apply) and every test call site must change together —
    sequence steps 1–3 land in one commit.
  - >
    R-F2 drift: if the API adapter's imports ever exceed the mirror's union plus the
    allowlist, the import-rule harness fails; run it right after step 3.

commit:
  message: >
    fix(ads): repair edit results — carry SubmitAdOutcome in EditResult, redirect only
    on PUBLISHED, remove the API mock-patch workaround
  body: >
    Service: EditResult gains submission_outcome (SubmitAdOutcome | None) and keeps
    errors; drops moderation_failed and the caller-supplied outcome_prefix; branch
    labels derive inside apply_edit_payload; delete unused can_edit_ad_by_service.
    HTML ad_edit redirects only on PUBLISHED and renders the error form for every
    other submission outcome (restores the 57966ea0 baseline); delete the duplicate
    view _apply_price_change. API _apply consumes the typed result directly
    (CONSENT_REQUIRED→403, INVALID_TRANSITION/DRAFT_GONE/PHOTO_UNAVAILABLE→409 with
    existing tokens; delete patch/SUBMIT_AD_PATH/_capturing). Tests: six-outcome
    service matrix, HTML refusal/no-redirect rows, API refusal mapping, delegation
    test retargeted to edit_flow.apply_price_change. Docs: api-surface.md row 6 /
    errors row / S4.4 (+two stale S4.2 claims) and two docstring touch-ups.
  files_hint: single coherent commit covering all eight files; no deployable
    intermediate revision may exist with mismatched view/service call signatures.
```

## B1 audit findings

Read-only audit of block B1 (P1 — Restore lifecycle atomicity), 2026-11-04. Semantic anchors
are authoritative; line numbers (HEAD `bb434452`, i.e. B0 landed) are hints. State verified:
working tree clean for `views/edit.py` / `services/lifecycle.py`; `ad_archive`/`ad_reactivate`
byte-identical to extraction commit `5b894a44` (the plan's evidence state, unchanged by B0);
`services/lifecycle.py` and `views/delete.py` have exactly one commit — `5b894a44`. Baseline =
`57966ea0`. Scope guard re-verified: P1 closes the transaction gap and fixes lock-lifetime docs;
`assert_lifecycle_owner` elimination and signature simplification stay in P6/B6.

### Current implementation (per symbol)

- `apps/ads/views/edit.py::ad_archive` (L260–298): **two transactions**. tx1 =
  `with transaction.atomic():` containing ONLY `assert_lifecycle_owner(ad_id, request.user.id)`
  (wrapped in `try/except PermissionDenied → return _ownership_refused_forbidden(...)` at L283)
  and the consent gate `if not _seller_may_create_ad(...) → return _consent_required_forbidden(...)`
  at L290–291; the block exits, committing and releasing the row lock acquired inside
  `assert_lifecycle_owner`. tx2 = separate `try: archive_ad(ad_id, request.user.id)` at L293–294
  (`except Http404: raise`), then redirect. There is **no handler around the service call for
  `PermissionDenied` or `DatabaseError`**: a lock timeout stays an `OperationalError` that
  `DbLockTimeoutMiddleware` turns into 503 (`apps/core/middleware/db_lock_timeout.py`, which names
  this view), but a late `PermissionDenied` from the service is uncaught → Django's **default 403
  surface** (no project `403.html` exists), losing the specific
  "You do not have permission to archive this ad." message and the `_ownership_refused_forbidden`
  warning log.
- `ad_reactivate` (L301–381): same two-transaction shape inside one `try:`; the service call
  `passed = reactivate_ad(ad_id, request.user.id).passed` at L345 runs **after the atomic block
  exited**. `except (Http404, DatabaseError): raise` keeps the 404 and the lock-timeout→503
  middleware boundary; `except Exception:` (L352) converts any other failure into
  `logger.exception("Ad %s reactivation failed during auto-moderation")` + dashboard
  messages.error "Reactivating ad #%(id)s failed. The ad stays archived; please try again later."
  — a late `PermissionDenied` from the service lands **here** and is misreported as a
  moderation/system failure. Then `passed is False` → moderation warning; redirect.
- Helpers intact and B1-untouched: `_seller_may_create_ad` (thin `can_create_ad` seam, L65–76),
  `_consent_required_forbidden` (L79–96), `_ownership_refused_forbidden` (L99–111, called only by
  the two lifecycle views).
- `apps/ads/services/lifecycle.py::_fetch_owned_ad` (L95–120): `Ad.objects.select_for_update()
  .get(id=ad_id)` → `Http404` (`raise … from None` on `Ad.DoesNotExist`) / ownership mismatch →
  warn log + `PermissionDenied("You do not own this ad.")`. `assert_lifecycle_owner` (L123–139):
  `with transaction.atomic(): _fetch_owned_ad(...)` and **returns `None`** — its docstring claims
  "the row is locked for the duration of the **returned transaction**" and that the follow-up
  lifecycle call "sees a stable row": factually wrong today — no transaction is returned; the lock
  lives in the *caller's* still-open outer atomic and dies when the caller exits it, which is
  exactly what the views do before calling the service. `archive_ad` (L142–168) /
  `reactivate_ad` (L171–211) / `delete_ad` (L214–240): each opens its **own**
  `transaction.atomic()` and repeats `_fetch_owned_ad` (the duplicate lock + ownership re-check);
  `reactivate_ad` keeps `transition_to(ON_MODERATION)` + `auto_moderate` inside its atomic
  (raise → rollback → propagate; DB errors propagate untouched).
- `apps/ads/views/delete.py::ad_delete` (L29–50): one call `delete_ad(ad_id, request.user.id)`
  inside `except PermissionDenied → HttpResponseForbidden("You do not have permission to delete
  this ad.")`; consent-free (no gate anywhere); single transaction — **already
  baseline-shaped**, no code change required, only re-verification via existing tests.
- Net per archive/reactivate request: 2 transactions, 2 row-lock acquisitions, 2 commits
  (baseline: 1/1/1), with an interleaving window between the consent check and the action.

### Baseline (57966ea0) semantics

- `ad_archive`: **one** `with transaction.atomic():` containing
  `get_object_or_404(Ad.objects.select_for_update(), id=ad_id)`, the ownership check on the
  **locked** row (warn log + specific `HttpResponseForbidden` message), the consent check, and the
  `PUBLISHED → ARCHIVED` transition; non-PUBLISHED = silent no-op inside the same block; redirect
  after. Ownership refusal was a plain in-transaction `return` — no `PermissionDenied` exception,
  no race: check and write shared one locked transaction.
- `ad_reactivate`: `passed: bool | None = None`; try → **one** atomic: fetch-lock, ownership 403,
  consent 403, `if status == ARCHIVED: ad.transition_to(ON_MODERATION); passed =
  auto_moderate(ad)`; `except (Http404, DatabaseError): raise`; `except Exception:` → rollback +
  dashboard error (the same safe-state reporting born there); `passed is False` → moderation
  warning. The broad catch could only ever see failures of the single block — no path existed for
  an authorization refusal to masquerade as a moderation failure. Ordering: ownership → consent →
  action, on the locked instance, one commit.

### Exact difference and the real risk (matches plan R04; no more, no less)

1. The regression: checks commit in tx1; lock drops; the action re-fetches, re-locks, re-checks,
   and commits in tx2. Every lifecycle request performs an extra transaction/lock round-trip, and
   another request (moderation, delete, a second archive) can interleave in the gap.
2. No demonstrated authorization bypass (confirmed): the service re-checks ownership under its
   own lock, and status transitions are still validated on the locked row. A late
   `PermissionDenied` requires a mid-request ownership flip — `Ad.user` has no transfer flow in
   the codebase — so it is a pathological race, not a practical hole.
3. Changed error mapping (archive): in that race, the generic Django 403 replaces the
   owner-specific 403 message and log. Changed error mapping (reactivate): the same
   `PermissionDenied` is swallowed by the broad `except Exception` and reported as
   "reactivation failed during auto-moderation".
4. Consent races are NOT fixed by B1 and were not solved by the baseline either:
   `can_create_ad` reads flags off the request's `User` instance (no lock on user/consent rows).
   Per R04: retain the shared predicates, do not claim broader race prevention. One ad-row
   transaction only restores the baseline's check→action serialization for the ad row.
5. Lock-timeout surface is unchanged and must survive: the (today second) `select_for_update`
   acquisition can hit `lock_timeout` → `DbLockTimeoutMiddleware` 503 (03-DB-004). Post-B1 the
   second acquisition is a same-transaction self-reacquire that cannot block; contention moves to
   the single first acquisition — fewer spurious 503s, strictly reduced deadlock/timeout exposure
   (the ad row is the only lock; `can_create_ad` performs non-locking reads).

### Nested-atomic precedent (P1's move is the established in-repo shape)

- Django `atomic()` nests as a SAVEPOINT. Moving `archive_ad(...)`/`reactivate_ad(...)` inside the
  view's open atomic makes the service's `transaction.atomic()` a savepoint — exactly the shape
  the shipped `ad_edit` path already uses: view atomic → `edit_flow.apply_edit_payload` →
  `_submit_like` → `submission.submit_ad`, which opens its own `transaction.atomic()`
  (`submission.py` L350) and its own `Ad.objects.select_for_update()` re-fetch (L352) inside the
  view's outer block. Same-transaction row-lock self-reacquire is a no-op in PostgreSQL.
- `apps/core/services/analytics.py::record_event` explicitly detects caller-owned transactions
  (`in_atomic_block`) and owns a savepoint + `SET CONSTRAINTS … IMMEDIATE`; it is called by
  `auto_moderate` and behaves identically under either nesting depth.
- `on_commit` consumers (`search/signals.py` cache bump, `moderation/signals.py` immediate alerts)
  fire at the outermost commit: today that is the service tx2 commit; post-B1 the view's tx —
  strictly-after-commit guarantee is identical (baseline behavior restored).
- Raise-path: `reactivate_ad`'s non-DB error rolls back its savepoint, escapes the outer atomic,
  and is reported by the existing `except Exception` — ad stays ARCHIVED (verbatim behavior of
  `test_reactivate_moderation_error_keeps_ad_archived`).
- Post-B1 the second `_fetch_owned_ad` reads the same locked row inside the same transaction, so
  ownership/status verdicts are deterministic and the late-`PermissionDenied` paths become
  structurally unreachable; the precheck `except PermissionDenied` remains the single explicit
  ownership-response mapping point (plan §7 P1 "explicit PermissionDenied handling").

### Callers (complete inventory)

- `archive_ad` / `reactivate_ad`: HTML `views/edit.py::ad_archive` / `ad_reactivate`; API
  `views/api/lifecycle_actions.py::archive_view` / `reactivate_view` via `_run_transition`. **No
  bot caller** (repo-wide grep over `src/telegram_bot` = 0 references).
- `delete_ad`: HTML `views/delete.py::ad_delete`; API `lifecycle_actions.py::delete_view`.
- `assert_lifecycle_owner`: **only** the two HTML views (`views/edit.py` L281, L333). No API use,
  no test usage. (The API deliberately does its own non-locking uniform-404 ownership preflight,
  `_ownership_refusal`, and consults consent gate-free-delete semantics independently.)
- Plan-note: the API lifecycle file is named `lifecycle_actions.py`, not `lifecycle.py`; its three
  service calls, the `PermissionDenied → uniform 404` mapping and `_run_transition`'s broad
  `except Exception → 503 retryable` contract are untouched by B1.
- `dashboard.py` imports of `_seller_may_create_ad` / `_consent_required_forbidden` and the
  status-set re-exports re-verified as B1-untouched. `moderation/admin_actions.py::soft_delete_ad`
  is a different symbol — out of scope.

### Test inventory — wrong vs correct encodings

No test encodes the wrong two-transaction topology: the gap is invisible to the current suite at
HEAD. B1 therefore has **zero test deletions** and only additions; the correct-behavior suites
below must keep passing byte-identically.

- `test_edit.py` (correct observable behavior, must stay green): `TestAdArchive` (owner 302 +
  ARCHIVED; wrong-user 403 + unchanged — **status-code-only assert**, message bytes not pinned;
  REJECTED no-op 302), `TestAdArchiveGetRejected` (405), `TestAdReactivateDirect` (owner 302 →
  PUBLISHED; wrong-user 403; non-ARCHIVED no-op 302; GET 405; moderation failure → 200 +
  ON_MODERATION_FAILED + "did not pass moderation"; moderation error → 200, ad stays ARCHIVED,
  "stays archived" — patches `apps.moderation.services.auto_moderation.auto_moderate`, the seam
  `lifecycle.py` calls via module attribute, unaffected by the move),
  `TestBannedSellerRelistNowRefused`, and `TestSellerWebStorageConsentGate::
  test_archive_refused_for_owner_without_consent` / `test_reactivate_refused_for_owner_without_consent`
  — the ownership/ban/consent refusal-ordering pins for P1.
- `test_lifecycle_service.py` (service contract, signature-stable across B1): full no-op status
  matrix, `PermissionDenied`/`Http404` refusals, rollback via patching
  `apps.ads.services.lifecycle.auto_moderation.auto_moderate`, gate-free archive/delete consent
  tests. Keep verbatim.
- `test_db_lock_timeout_boundary.py`: `TestAdReactivateLockTimeout` patches
  `edit.Ad.objects.select_for_update` — the **shared manager instance** `lifecycle._fetch_owned_ad`
  also goes through — so the first locked fetch raises, `except (Http404, DatabaseError)` re-raises
  and the middleware 503s: asserts 503 + "busy". Boundary survives the move unchanged.
  **No archive-through-view lock-timeout test exists** — the only boundary gap (advisory addition).
- `test_edit_views_locking.py`: `TestEditViewsLocking` is callable-only sentinels (its own comments
  refer to a historical project "B1 #7" cleanup, unrelated to this block) — it cannot detect the
  gap. `TestEditViewsRowLockConcurrency` proves PostgreSQL `select_for_update` blocks a concurrent
  DELETE, but **drives no view at all** — it locks a row directly; it would stay green even if the
  views had no lock before the transition. G2's "regression test observes the actual HTML action
  within its original atomic block" is currently satisfied by nothing.
- `test_ad_lifecycle.py` is **not** about the HTML views: it pins `Ad.transition_to()` and the
  `ALLOWED_TRANSITIONS` matrix. Unaffected. `test_ad_consent_gate.py` is the 06-PII-109
  consent-withdrawal retention record, not the lifecycle consent gate (that pin lives in
  `test_edit.py::TestSellerWebStorageConsentGate`; delete's consent-free pins live in
  `test_lifecycle_service.py::TestDeleteAd::test_consent_gate_is_caller_side`,
  `test_lifecycle_api.py::TestConsentGate::test_delete_is_gate_free`, and delete's absence from
  `TestSellerWebStorageConsentGate`).
- `test_lifecycle_api.py`: API contract, incl. `TestConsentGate::test_consent_gate_matches_html_gate`
  which drives **both** surfaces and compares 403-vs-403 — stays green. Docstring alert
  (`lifecycle_actions.py` "Consent ordering" bullet says the HTML views assert consent "after the
  transition block was reached"): that claim flips with B1 — a one-line truthful docstring update
  rides along (no functional surface change).

### Proposed G2 regression tests (non-flaky techniques, repo-precedented)

1. **"HTML action inside the original atomic block" — deterministic, no threads/sleeps.**
   `@pytest.mark.django_db(transaction=True)`; monkeypatch `apps.ads.views.edit.archive_ad`
   (and `.reactivate_ad`) — the exact name the view calls — with a wrapper that records
   `transaction.get_connection().in_atomic_block` **at wrapper entry** and calls the original;
   drive `client.post(reverse("ads:archive", args=[ad.id]))` for real; assert the recorded flag
   is `True`. At HEAD the view's atomic has exited before the call ⇒ flag is `False` (test fails);
   post-B1 the only open block is the view's ⇒ `True`. The observation point sits *before* the
   service opens its own atomic, so the flag isolates the view's block. **Must** be
   `transaction=True` — under plain `django_db` the pytest wrapper itself keeps
   `in_atomic_block` True and the test proves nothing (the repo's own caveat,
   `test_ad_detail_queries.py` ~L45; `transaction=True` precedents: `test_search_cache.py`
   on_commit tests, `TestEditViewsRowLockConcurrency`, `test_analytics_service.py` asserting
   `not connection.in_atomic_block`; `transaction.get_connection` patching precedent in
   `test_advisory_lock_release_log.py`).
2. **"Row lock persists" — focused concurrency test, bounded waits, real view.** In the existing
   calibrated framework (`@pytest.mark.django_db(transaction=True) @slow @concurrent
   @xdist_group("concurrent") @flaky(reruns=1, reruns_delay=1)`): a background thread runs the real
   `client.post(...)`; a seam monkeypatch (`edit.archive_ad` wrapper; for reactivate also
   `lifecycle.auto_moderation.auto_moderate`) signals `started` and parks on a proceed-Event;
   the main thread (its own thread-local connection — the `TestEditViewsRowLockConcurrency`
   pattern) probes `Ad.objects.select_for_update().get(pk=ad.id)` under
   `SET LOCAL lock_timeout = '500ms'` (or `.select_for_update(nowait=True)`) and **expects**
   OperationalError/55P03: proof the row lock is held at the service-call instant. At HEAD the
   probe acquires the row through the gap and the assertion fails; post-B1 it times out. Then
   release, join, and assert the view committed (302 + status change). All waits are bounded
   (Event timeouts + lock_timeout) — no blind `time.sleep` coordination — so the test is
   non-flaky modulo scheduling noise, covered by the existing reruns marker.
   `transaction=True` is mandatory: a savepoint-only commit releases PostgreSQL row locks and
   would mask the gap.
3. **Why not `pg_locks` / `on_commit`** (questioned techniques): PostgreSQL keeps `FOR UPDATE`
   locks on the tuple; `pg_locks` shows waiters, not the non-waiting holder — the repo's related
   tests use *advisory* locks (`pg_try_advisory_lock` via raw cursor in
   `test_sweep_lock_structure.py`), a different mechanism; no `pg_locks` row-lock precedent
   exists. `transaction.on_commit` (widely used) and `TestCase.captureOnCommitCallbacks` (unused
   in this repo) do not discriminate: callbacks fire at the outermost commit under both
   topologies; the defect is a lock-holder gap between two commits, not a commit-timing artifact.
4. **403-mapping pin** (per §7 P1 "explicit PermissionDenied handling"): patch the view-module
   seam with `side_effect=PermissionDenied(...)` and assert archive answers the ownership 403
   (not Django's default 403 page) and reactivate answers 403 (not the "stays archived"
   moderation message/exception log). Relevant only if the belt below is adopted; through the
   real path the post-B1 race is structurally unreachable.
5. **Archive lock-timeout mirror** in `apps/core/tests/test_db_lock_timeout_boundary.py`: same
   `edit.Ad.objects.select_for_update` patch as the reactivate test, asserting 503 + "busy" —
   closes the only boundary-suite gap, cheap, and pins that the move did not swallow the timeout.

### Design choice flagged for Planner/Implementor

- Minimal one-line relocation (service call becomes the last statement of each existing
  `with transaction.atomic():`; reactivate keeps the `try`/handlers; archive's separate
  `try: … except Http404: raise` around the call becomes redundant but is behavior-identical
  either way) vs. **belt-and-braces**: additionally wrap the service call in
  `except PermissionDenied → _ownership_refused_forbidden(...)` so the broad reactivate handler
  structurally can never misreport an authorization refusal, at the cost of one branch per view.
  Recommendation: adopt the belt — it makes the §7 P1 "explicit PermissionDenied handling"
  literal at every layer and keeps the 403 bytes identical to the precheck's — but either choice
  passes G2. Never extend the broad catch to convert refusals into apparent success (plan §9).
- Docstring corrections (mandatory): `assert_lifecycle_owner` must stop claiming "duration of
  the returned transaction"; correct wording: the row lock persists until the caller's atomic
  block exits, so keep the follow-up lifecycle call inside that block. `_fetch_owned_ad`'s
  contract paragraph gains the savepoint-nesting rule (when the caller's block is open, the
  service's own `atomic()` is a savepoint inside it). No signature/symbol changes (B6).
- Preserve exactly: refusal ordering (ownership before consent before action), reactivate's
  `except (Http404, DatabaseError): raise` positioned before `except Exception:`, the
  message/log strings, the middleware 503 path, `ArchiveResult`/`ReactivateResult`/`DeleteResult`
  values, and delete's gate-free single-call shape.

### Templates / error surfaces (for the record)

- Ownership/consent 403s are plain-text `HttpResponseForbidden` (translated strings; no template):
  "You do not have permission to archive/reactivate/delete this ad." /
  "To manage ads, please accept the personal data storage consent first." Reactivate outcomes
  render through the `messages` framework into `templates/ads/dashboard.html` (~L28
  `{% for message in messages %}`). No project `403.html`/`404.html` exists — the late-
  PermissionDenied drift renders Django's default 403 surface (evidence, not a fix target; the
  fix eliminates the path). Lock timeout renders the middleware's plain 503. **No new msgids are
  needed** — all strings already exist and are unchanged.

### Files that must change for P1

1. `src/backend/apps/ads/views/edit.py` — `ad_archive`: move `archive_ad(...)` inside the
   existing atomic block (after the consent check); `ad_reactivate`: move
   `passed = reactivate_ad(...).passed` inside the same block; option: `except PermissionDenied`
   belt; local comment/docstring lines that describe the service boundary.
2. `src/backend/apps/ads/services/lifecycle.py` — `assert_lifecycle_owner` + `_fetch_owned_ad`
   docstrings only (lock-lifetime / savepoint-nesting contract).
3. `src/backend/apps/ads/tests/test_edit_views_locking.py` — new deterministic atomic-continuity
   tests + the parked-seam lock-probe concurrency tests (item 1 and 2 above).
4. `src/backend/apps/core/tests/test_db_lock_timeout_boundary.py` — archive lock-timeout mirror
   (item 5 above; `test_edit.py` optional host for the 403-mapping pin if the belt is adopted).
5. `src/backend/apps/ads/views/api/lifecycle_actions.py` — docstring-only "Consent ordering"
   bullet truthing (no code change; all 474 lines otherwise untouched).
6. No changes: models, migrations, submission/auto_moderation/analytics services, bot, URLs,
   templates, API logic, delete view. Gate bookkeeping (G2 status flip) happens after B1's
   Validator step, per source-plan process, not in the code commit.

## B1 research decision

Read-only research for block B1 (P1 — Restore lifecycle atomicity), 2026-11-04, HEAD `bb434452`
(B0 landed). Inputs re-read from `architecture-correction-plan.md` §5 R04, §7 P1 row, §8 G2, §9
risks; the B1 audit above; and re-verified source: `apps/ads/views/edit.py`,
`apps/ads/services/lifecycle.py`, `apps/ads/views/delete.py`,
`apps/ads/views/api/lifecycle_actions.py`, `apps/core/middleware/db_lock_timeout.py`,
`apps/core/utils/db_lock_timeout.py`, `config/settings/{base,test}.py`,
`apps/ads/tests/{test_edit,test_edit_views_locking,test_lifecycle_service,test_lifecycle_api}.py`,
`apps/core/tests/{test_db_lock_timeout,test_db_lock_timeout_boundary,test_sweep_lock_structure}.py`,
`apps/core/services/analytics.py`, `apps/ads/services/submission.py`, `pyproject.toml`,
`apps/api/tests/test_import_rule.py`. `git status`: tree clean except this plan file. Scope guard held:
`assert_lifecycle_owner` deletion, signature simplification and service-internal refetch removal stay
in P6; the API adapter's `_run_transition` is untouched.

### Alternatives compared

| # | Option | Verdict | Reason (evidence) |
|---|---|---|---|
| A | Move both service calls inside their existing `atomic()`; add an explicit `except PermissionDenied -> _ownership_refused_forbidden` belt around the archive service call and around reactivate's (ordered before `except Exception`) | **SELECTED** | Restores the baseline's one-transaction/one-lock topology (§5 R04; baseline `57966ea0`: fetch-lock → ownership 403 → consent 403 → transition/moderation, one commit). The belt makes §7 P1's "explicit PermissionDenied handling" literal at **both** layers: the precheck stays the normal 403 mapping point, and the service's own refusal can no longer fall to Django's default 403 (archive) or be misprinted as "reactivation failed during auto-moderation" (reactivate). Bytes identical to the precheck 403 (`_ownership_refused_forbidden` with the same translated message + warning log). Cost: one extra `except` clause per view; dead in the normal path, reachable only by a monkeypatched seam in tests. |
| B | Move calls inside the block, no belt | **REJECTED** | Passes G2's observable assertions, but leaves two wrong mappings in code: a service-raised `PermissionDenied` in `ad_archive` still surfaces as the generic Django 403 (losing the specific message/log), and in `ad_reactivate` it is caught by `except Exception` and reported as a moderation failure with `logger.exception`. The plan explicitly asks P1 to preserve "explicit PermissionDenied handling"; the belt is one clause and makes the invariant structural rather than incidental. Opens no new path. |
| C | Remove the pre-check (`assert_lifecycle_owner`) now and rely on the service call inside the atomic | **REJECTED (out of scope + behavior change)** | Two violations. (1) Scope: the plan defers precheck elimination to P6 ("Leave signature simplification to P6 while API callers still exist"; P6 "remove redundant precheck/refetch"). Doing it here widens B1. (2) Semantics: deleting the precheck moves ownership/consent ordering from `ownership -> consent -> action` to `consent -> ownership -> action` — a non-owner without consent would now learn nothing new but a **non-owner with consent** still gets 403, while a **non-owner without consent** flips from "You do not have permission to …" to the consent message. `test_edit.py::TestAdArchive::test_archive_wrong_user_returns_403` and `test_reactivate_wrong_user_returns_403` assert status only, so they would still pass, but the refusal text/order would silently change — exactly the "changing product semantics while fixing extraction" risk in plan §9. P6 can remove the precheck there with an explicit ordering decision. |
| D | Rewrite the service to accept an already-locked `Ad` (single locked-ad convention) | **REJECTED (P6)** | It is P6's target ("one clear convention … on that locked instance"), not P1's. It needs API/H T M L callers migrated together, changes public signatures while the API adapters still exist (P4 not done), and is strictly larger than the correctness repair. |

### Selected contract (exact implementation)

**1. `apps/ads/views/edit.py::ad_archive`** — the service call becomes the last statement inside the existing `transaction.atomic()` and gets the belt:

```python
with transaction.atomic():
    try:
        assert_lifecycle_owner(ad_id, request.user.id)
    except PermissionDenied:
        return _ownership_refused_forbidden(_("You do not have permission to archive this ad."), "archive", ad_id, request.user.id)

    if not _seller_may_create_ad(request.user):
        return _consent_required_forbidden(request.user, ad_id)

    try:
        archive_ad(ad_id, request.user.id)
    except Http404:
        raise
    except PermissionDenied:
        return _ownership_refused_forbidden(<same message/args>)

return redirect("ads:dashboard")
```

The separate top-level `try: archive_ad(...) except Http404: raise` after the block is removed by the move; `except Http404: raise` stays (documents that a missing ad keeps its 404 rather than being caught by the belt). Do not add `except DatabaseError` here: today archive has **no** envelope, so `OperationalError` already escapes to `DbLockTimeoutMiddleware`; adding a handler would be new code with no new behaviour. The public-keyword options after the re-read (`test_archive_*`) rely on the leading `get_object_or_404` and are unchanged.

**2. `apps/ads/views/edit.py::ad_reactivate`** — the service call moves inside the atomic and the belt is ordered before `except (Http404, DatabaseError)`:

```python
passed: bool | None = None
try:
    with transaction.atomic():
        try:
            assert_lifecycle_owner(ad_id, request.user.id)
        except PermissionDenied:
            return _ownership_refused_forbidden(_("You do not have permission to reactivate this ad."), "reactivate", ad_id, request.user.id)

        if not _seller_may_create_ad(request.user):
            return _consent_required_forbidden(request.user, ad_id)

        passed = reactivate_ad(ad_id, request.user.id).passed
except PermissionDenied:
    return _ownership_refused_forbidden(<same message/args>)
except (Http404, DatabaseError):
    raise
except Exception:
    logger.exception("Ad %s reactivation failed during auto-moderation", ad_id)
    messages.error(...)
    return redirect("ads:dashboard")
```

Handler order is load-bearing: `PermissionDenied` is not a `DatabaseError` (both descend from `Exception`, `PermissionDenied` from `django.core.exceptions.Exception`), so the belt could be placed first or immediately after `(Http404, DatabaseError)`; placed **first** to make the intent obvious and to shortcut any future base-class change. `PermissionDenied` maps to the precheck's 403 (not Django's default), and never to the moderation failure message. `(Http404, DatabaseError): raise` must stay **before** the broad `except Exception:` — otherwise a `DatabaseError` would be reported as a moderation failure with a dashboard redirect and `DbLockTimeoutMiddleware` would never see the 503.

**3. `apps/ads/services/lifecycle.py` — docstrings only, no code.**

- `_fetch_owned_ad` (current L98–100 wrongly says "every public function here opens its own `transaction.atomic()` before calling this, so the lock and the subsequent write share one unit of work"). Correct: *"The row lock must run inside *some* transaction. When a caller opens a lifecycle function, its own `atomic()` acquires the lock and holds it to its commit; when a boundary calls a lifecycle function **inside its own atomic block** (the HTML `ad_archive`/`ad_reactivate` and the edit view's nested `submit_ad` precedent), the service's `atomic()` is a PostgreSQL SAVEPOINT inside the caller's transaction, so the `select_for_update()` re-acquisition is a same-transaction self-reacquire (a no-op that cannot block) and the lock and the write share the caller's one unit of work and one commit."* Also state the consequence: `on_commit` callbacks fire at the **outermost** commit, and a savepoint rollback releases only the savepoint's work, **not** the row lock — one transaction, one commit, one lock lifetime.
- `assert_lifecycle_owner` (current L131–135: "The row is locked for the duration of the returned transaction … the follow-up lifecycle call … sees a stable row") — **factually wrong** (the function returns `None`). Correct: *"Returns `None`; it does **not** own a long-lived lock. The `select_for_update()` runs inside the caller's block; because this function opens only a nesting `atomic()`, the lock lives until the **caller's** transaction exits, not until this function returns. The caller must keep its own `atomic()` open across the follow-up `archive_ad`/`reactivate_ad` call — that is what makes the check and the action one unit of work and what keeps the refusals ordered ownership → consent → action. A caller that exits its block first releases the lock and reintroduces the gap."* Keep the `Raises:` block and the ownership-before-consent rationale. (P6 will delete both the function and this caveat.)

**4. `apps/ads/views/api/lifecycle_actions.py` — one-line docstring truthing, no code change.** The "Consent ordering" bullet (L64–67) says HTML asserts consent *"after the transition block was reached"* — that sentence is already odd today and becomes wrong after B1. Correct to: *"The HTML `ad_archive` / `ad_reactivate` views assert consent **inside** the transaction that performs the transition (ownership → consent → action, one commit); these endpoints assert it **before** any service call, so a consent-refused request provably changes nothing (§2.5 "consent BEFORE transition")."* Everything else in the file (incl. the lock-timeout bullet and all 474 lines of logic) stays.

**5. Untouched:** `ad_delete` (already one call, consent-free, `PermissionDenied -> 403`); the API `_run_transition` (uniform 404, 55P03 → 503 retryable, broad catch); `ArchiveResult`/`ReactivateResult`/`DeleteResult` and every service signature (P6); the services' `select_for_update` re-fetch (P6); imports (`PermissionDenied` is already imported in `edit.py`; no new symbol, no new msgid, so **no catalog change** and no i18n impact).

### Savepoint / lock / on_commit analysis (the questions asked)

- **Inner `atomic()` becomes a savepoint.** Django `atomic()` nests as a SAVEPOINT. The move therefore adds exactly `SAVEPOINT` + `RELEASE SAVEPOINT` per lifecycle action (no new round-trip that can fail under normal operation). This is the shipped `ad_edit -> submit_ad` shape (`submission.py` L350 also opens `atomic()` and `select_for_update()` inside the view's block) and the shape `analytics.record_event` documents (`if not connection.in_atomic_block` — L94 — because its caller may own the transaction; `auto_moderate` calls it, so on the old two-transaction path analytics took the autocommit branch and on the new path it takes the savepoint branch; the observed event **rows** are identical and the existing `_event_types` assertions exercise the savepoint branch through `submit_ad`'s reactivation today).
- **`select_for_update` re-acquisition is a self-reacquire.** PostgreSQL row locks are held by the transaction, so `SELECT ... FOR UPDATE` on a row already locked by the **same** transaction returns immediately (FOR UPDATE does not throw on self-lock, unlike some ORMs). The second `_fetch_owned_ad` therefore cannot block and cannot `lock_timeout`; lock contention now occurs only at the **first** acquisition (the view's precheck), exactly as at baseline. Deadlock exposure is unchanged-to-reduced (one transaction instead of two, the same single ad row, and `can_create_ad` performs non-locking `User` reads — no second lock to order). **No lock-ordering change is introduced by B1.**
- **Rollback semantics.** A raising `auto_moderate` rolls back **the service savepoint** (ARCHIVED -> ON_MODERATION undone), then propagates; the view's `atomic()` __exit__ rolls back the (already-savepoint-rolled-back) outer transaction, and the `except Exception` handler runs on the request's fresh autocommit connection. That is the same observable state as today (`test_reactivate_moderation_error_keeps_ad_archived`, `test_lifecycle_service.py::test_check_error_rolls_back_to_archived` — both pass unchanged). The `on_commit` callbacks (`search/signals.py`, `moderation/signals.py`) fire at the **outermost** commit; today that is the service's tx2 commit, after B1 the view's single commit — same strictly-after-commit guarantee, one commit instead of two.
- **Lock-timeout path.** Unchanged definition (`config/settings/base.py` `LOCK_TIMEOUT_SECONDS=10`, rendered `options=-c lock_timeout=10s` for the whole process; `test.py` reuses `_db_options()`), unchanged exception (`OperationalError` whose `__cause__` is `psycopg.errors.LockNotAvailable`, SQLSTATE 55P03), unchanged classifier (`db_lock_timeout.is_lock_timeout:59`), unchanged middleware (names `ad_archive`/`ad_reactivate`; `process_exception` catches it). In archive it escapes from inside the `with` (no `DatabaseError` clause exists today, none added). In reactivate `except (Http404, DatabaseError): raise` re-raises `OperationalError`; Python unwinds the `with` synchronously, aborting the transaction (savepoint already gone), then middleware 503s. `TestAdReactivateLockTimeout` patches the **shared** `edit.Ad.objects.select_for_update` that `lifecycle._fetch_owned_ad` also uses, so it hits the first (precheck) acquisition pre- and post-fix: still 503 + "busy".

### G2 test design (precise, non-flaky)

Marker check (verified): `pyproject.toml` registers `integration`, `concurrent` ("requires transaction=True"), `slow`, `xdist_group`, `flaky`, plus `addopts=["--import-mode=importlib","-ra","-q"]`, `pythonpath=["src","src/backend","src/backend/tests"]`, `testpaths=["src/backend","src/telegram_bot"]`. `xdist_group("concurrent")` is used at `apps/core/tests/test_db_lock_timeout.py:64`, `apps/ads/tests/test_edit_views_locking.py:153`, `apps/moderation/tests/test_auto_moderation.py:73,751`, `apps/core/tests/test_sweep_archive.py:202`, and others. The repo's calibrated concurrency decorator stack is `@pytest.mark.django_db(transaction=True) @pytest.mark.slow @pytest.mark.integration @pytest.mark.concurrent @pytest.mark.xdist_group("concurrent") @pytest.mark.flaky(reruns=1, reruns_delay=1)` — reuse it verbatim. `permissive_criteria` / `banning_criteria` are fixtures from the root-level plugin `src/backend/testing/moderation_fixtures.py` (auto-loaded; available in `apps/core/tests`). Both `Client()` and `reverse("ads:archive"|"ads:reactivate")` are available.

New tests live in `src/backend/apps/ads/tests/test_edit_views_locking.py` (a new module is not needed; the file already owns view-locking behavior). The 403-belt pin lives in `src/backend/apps/ads/tests/test_edit.py`. The archive lock-timeout mirror lives in `src/backend/apps/core/tests/test_db_lock_timeout_boundary.py`.

**Test 1 — atomic continuity (deterministic, no threads, no sleeps).** This is the direct G2 clause "regression test observes the actual HTML action within its original atomic block".

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("status", "target", "service_name"), [
    (AdStatus.PUBLISHED, "ads:archive", "archive_ad"),
    (AdStatus.ARCHIVED,  "ads:reactivate", "reactivate_ad"),
])
def test_html_action_runs_inside_the_view_transaction(monkeypatch, client-like, seller, category, city, status, target, service_name):
    ad = create_test_ad(...); if status == ARCHIVED: ad.transition_to(AdStatus.ARCHIVED); ad.refresh_from_db()
    observed: list[bool] = []
    original = getattr(edit, service_name)
    def recording(*a, **kw):
        observed.append(transaction.get_connection().in_atomic_block)
        return original(*a, **kw)
    monkeypatch.setattr(edit, service_name, recording)        # the exact view-module name the view calls
    response = Client().post(reverse(target, args=[ad.id]))
    assert observed == [True]          # HEAD: False (view's atomic exited before the call); post-fix: True
    assert response.status_code == 302
```

- **Seam reason:** `views/edit.py` does `from apps.ads.services.lifecycle import archive_ad, reactivate_ad`, so the view resolves the name from its **own module**. Patching `apps.ads.views.edit.<name>` (not `apps.ads.services.lifecycle.<name>`) is the seam the view actually calls; the wrapper delegates to the original, so behavior is unchanged.
- **Why it fails on HEAD:** at wrapper entry the view's `with` block has already exited (`in_atomic_block` is `False` in the view's autocommit — `transaction=True` means pytest does not wrap the test in an outer atomic, which is the repo's documented caveat at `test_ad_detail_queries.py:45` and `test_sweep_lock_structure.py:145-148`; with plain `django_db` every observation would be `True` and the test would prove nothing). The service then opens its **own** atomic, so an observation taken *inside* the service would also be `True` post-fix — hence the observation must be taken **before** delegating.
- **Why it passes post-fix:** the only open block at the wrapper entry is the view's own `atomic()`.
- `reactivate` case uses `permissive_criteria` so the wrapped call takes the full ARCHIVED -> ON_MODERATION -> published path (still inside the savepoint) and returns 302.
- Cost: ~0 extra DB round-trips; runs in the fast tier (no `slow`), so it is a cheap permanent guard.
- Contract assertion is `in_atomic_block is True`. Do **not** assert on `connection.savepoint_ids`: pytest-django's `transaction=True` fixture creates no savepoints of its own, and the savepoint count is an implementation detail, not the contract. Keep the test minimal.

**Test 2 — row-lock continuity across the action (the G2 "focused DB lock/concurrency test").** This is the companion: Test 1 proves the call site is inside a transaction; Test 2 proves the **lock acquired by the view's precheck is still held** when the service call runs (i.e. the gap that lets another connection mutate the row between check and action is closed). Without Test 2, a future refactor could keep `in_atomic_block` true while re-opening a **nested** block that released the lock (it cannot in Django, but the test is the behavioral proof, not the structural one).

```python
# module-level decorators (reuse the calibrated stack above)
def test_view_holds_the_row_lock_until_the_action_commits(...):
    ad = create_test_ad(seller, category, city, status=<PUBLISHED for archive / ARCHIVED for reactivate>)
    proceed = threading.Event(); entered = threading.Event(); t_error = []; response = []
    original = edit.archive_ad  # or reactivate_ad
    def parked(*a, **kw):
        entered.set()
        assert proceed.wait(timeout=10), "test never released the seam"
        return original(*a, **kw)
    monkeypatch.setattr(edit, "archive_ad", parked)
    def drive():
        try:
            response.append(Client().post(reverse("ads:archive", args=[ad.id])))
        except BaseException as e: t_error.append(e)
        finally: connection.close()
    t = threading.Thread(target=drive); t.start()
    assert entered.wait(timeout=10), "view never reached the service call"
    # main thread, own connection: probe the row under a bounded lock wait
    probe = {}
    try:
        with transaction.atomic():
            with connection.cursor() as c:
                c.execute("SET LOCAL lock_timeout = '500ms'")
            Ad.objects.select_for_update().get(pk=ad.id)      # expect OperationalError/55P03
    except OperationalError as exc:
        probe["exc"] = exc
    assert isinstance(probe.get("exc"), OperationalError), "row was NOT locked when the service call ran"
    assert probe["exc"].__cause__ is not None and getattr(probe["exc"].__cause__, "sqlstate", None) == "55P03"
    proceed.set(); t.join(timeout=15); assert not t.is_alive() and not t_error
    ad.refresh_from_db(); assert ad.status == AdStatus.ARCHIVED  # committed once
    assert response[0].status_code == 302
```python

- **Seam reason:** the main thread must observe the lock **at the instant the service is called**. Parking the view-module seam gives a deterministic rendezvous *without* `sleep`-based coordination: the background request is blocked inside its atomic, holding the precheck's lock, waiting on `proceed`. A plain `time.sleep` probe is racy; parking at the actual call site is not.
- **Probe under `SET LOCAL lock_timeout`.** `SET LOCAL` is transaction-scoped and auto-restored, so it cannot leak into the pooled test connection. `lock_timeout='500ms'` is safely above scheduling noise (~10-100 ms) and 20x below the suite's 10 s connection-level bound. The probe runs inside its own `atomic()` under `transaction=True`; a lock timeout aborts only the probe's transaction. Expect `OperationalError` with `__cause__.sqlstate == '55P03'` - the SQLSTATE assertion (not the message) matches `is_lock_timeout`'s own contract. Capture the probe outcome in a dict and assert outside the `except` block: `except OperationalError as exc: probe['exc'] = exc`, then `assert isinstance(probe.get('exc'), OperationalError)` and `assert getattr(probe['exc'].__cause__, 'sqlstate', None) == '55P03'`. Any other exception type is a loud failed assertion, never a silent pass. `select_for_update(nowait=True)` is an acceptable alternative that raises `LockNotAvailable` immediately, but does not exercise the configured bound the production code relies on.
- **Why it fails on HEAD:** HEAD commits the precheck in tx1 and then calls the service in autocommit. At the instant the parked seam runs, the precheck's lock has been released, so the probe **acquires** the row (no exception) and the `isinstance` assertion fails. Post-fix the probe times out with 55P03.
  Note: `proceed.wait` inside the **background** thread means the parked seam releases the row lock only after the main thread's probe has resolved; if the probe acquires the row (HEAD), `archive_ad` will then block until the probe's transaction ends (release by context-manager __exit__ at the `try/finally`). Make sure the probe's `atomic()` exits before `proceed.set()` — put `proceed.set()` **after** the `try/except` — so HEAD never deadlocks the run; the bounded `t.join(timeout=15)` then collects the request, and the assertion fails on `probe["exc"]`, not on a hang. This ordering is essential to the "fails in bounded time, never hangs" property.
- **Why it passes post-fix:** the view's single transaction holds the row from the precheck `select_for_update` through the service's same-transaction self-reacquire; the probe (a **different** connection) waits and times out at 55P03. After release the request commits the ARCHIVED transition once (assert the final status).
- Covers both views via `@pytest.mark.parametrize` (archive: PUBLISHED -> ARCHIVED; reactivate: ARCHIVED -> PUBLISHED with `permissive_criteria`; for reactivate, park on `edit.reactivate_ad`, which also sits inside the lock, before `auto_moderate`).
- The repo's existing `flaky(reruns=1, reruns_delay=1)`, `slow` and `xdist_group("concurrent")` markers make this test resilient to CI scheduling noise; all coordination is `Event`-bounded and every join has a deadline, so a failure is a fast failure, never a suite hang (same defensive shape as `test_db_lock_timeout.py::test_lock_wait_is_bounded` and `TestEditViewsRowLockConcurrency`).

**Test 3 — 403-belt pin (only meaningful with option A).** In `test_edit.py` (or `test_edit_views_locking.py`), drive the **real view** with the seam patched to raise:

```
def test_archive_late_permission_denied_keeps_the_ownership_403(monkeypatch, ...):
    monkeypatch.setattr("apps.ads.views.edit.archive_ad", lambda *a, **k: (_ for _ in ()).throw(PermissionDenied("You do not own this ad.")))
    response = Client().post(reverse("ads:archive", args=[ad.id]))
    assert response.status_code == 403
    assert response.content == b"You do not have permission to archive this ad."

def test_reactivate_late_permission_denied_is_not_a_moderation_failure(monkeypatch, caplog, ...):
    monkeypatch.setattr("apps.ads.views.edit.reactivate_ad", ... raise PermissionDenied ...)
    response = Client().post(reverse("ads:reactivate", args=[ad.id]))      # NOT follow=True
    assert response.status_code == 403
    assert "reactivation failed during auto-moderation" not in caplog.text
```python

`ad` must be PUBLISHED / ARCHIVED respectively so the flow reaches the belt, not the precheck. The wrapper delegation is stubbed because the point is the handler, not the service. On HEAD the archive case returns Django's default 403 page and the reactivate case redirects with the "stays archived" message — both assertions fail.

**Test 4 — archive lock-timeout mirror** (in `apps/core/tests/test_db_lock_timeout_boundary.py`, mirroring `TestAdReactivateLockTimeout` L117-143):

```
class TestAdArchiveLockTimeout:
    @pytest.mark.django_db
    def test_lock_timeout_still_returns_503(self, seller, category, city):
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        with patch.object(edit.Ad.objects, "select_for_update", side_effect=_lock_timeout_error()):
            response = Client().post(reverse("ads:archive", args=[ad.id]))
        assert response.status_code == 503
        assert "busy" in response.content.decode().lower()
```python

Why in scope: G2 says "timeout behavior passes" for both actions; only reactivate had a boundary test. The patch hits the **shared** manager instance so it intercepts the precheck's `select_for_update` in `lifecycle._fetch_owned_ad`; the assertion distinguishes "escaped as `OperationalError` → middleware 503" from "swallowed into a dashboard message", which is the exact hazard the move could introduce. It is nearly zero-cost (a single mock-raise path; no real lock). Strongly recommended.

**Why not `pg_locks` / `on_commit` / `TestCase.captureOnCommitCallbacks` (re-affirmed).** `pg_locks` reports waiters, not non-waiting holders of tuple locks; `on_commit` callbacks fire at the outermost commit under either topology, so they cannot see the *lock* gap (only a commit-count difference, which would be measuring an implementation choice, not the contract). `captureOnCommitCallbacks` is unused in the repo and is `TestCase`-only. The recommended Test 1 + Test 2 pair observes the contract directly (call site inside a block + lock held at the call instant) and is the smallest defensible pair.

### Risks on the selected path

- **Broadened catches (archive).** The belt adds `except PermissionDenied` — it does **not** catch `Http404`, `DatabaseError`, or `Exception`. A lock timeout in archive still escapes to the middleware; a missing ad still 404s (the explicit `except Http404: raise` documents it). **Do not** add `except DatabaseError` to archive (new semantics). In reactivate the belt is narrowed to `PermissionDenied` only and placed **first**; the existing `(Http404, DatabaseError): raise` → `except Exception:` ordering is preserved verbatim.
- **Changed error mapping.** The only intended change is better: a late `PermissionDenied` now yields the owner-specific 403 + warning log in both views (archive was Django's default 403; reactivate was mislabelled moderation failure). No success-shaped conversion is introduced (plan §9).
- **Savepoint on rollback.** A raising `auto_moderate` rollback targets the service savepoint only; the outer transaction is rolled back by `atomic().__exit__` as today. No partial-write exposure: the transition and the check live in the same savepoint. `analytics.record_event` takes its caller-owned-transaction branch (3 statements instead of 1) — same rows, still through `auto_moderate`, already exercised by `submit_ad`'s nested path; the `on_commit` cache bumps move to the single view commit.
- **Lock-timeout path.** One transaction, one lock acquisition (precheck), a self-reacquire inside it that cannot block. 55P03 surface, 10 s bound, middleware 503 and `Retry-After: 30` are unchanged; existing `TestAdReactivateLockTimeout` stays green; the new archive mirror pins it.
- **Deadlocks.** Unchanged lock set (the ad row; `can_create_ad` reads `User` without locks; `auto_moderate` writes its own rows, no competing orderings on the ad row). The one-transaction shape is strictly less exposed than two transactions.
- **API adapter.** Untouched — it never used `assert_lifecycle_owner` and its `_run_transition` still owns the JSON mapping. The docstring bullet is corrected so the file tells the truth.
- **P6 hand-off.** The belt and the precheck's dual ownership-check are deliberately temporary: P6 deletes `assert_lifecycle_owner`, moves to a single locked-ad convention, and removes the belt together with the precheck in one coherent change. The G2 tests (1, 2, 4 and the public tests) must remain meaningful after P6 — Test 1 still observes `in_atomic_block` at the service seam (which P6's refactor keeps), Test 2 still proves the lock, Test 3 is rewritten to assert the single 403 path in P6.

### Acceptance for B1 (maps to G2)

One transaction and one row-lock lifetime per HTML archive/reactivate, observed by Test 1 (`in_atomic_block` at the seam) and Test 2 (55P03 while the request is parked at the seam); late `PermissionDenied` maps to the owner 403 and never to the moderation-failure message (Test 3); lock timeout still yields the 503 + "busy" boundary for both views (existing reactivate test + Test 4); refusal ordering ownership → consent → action unchanged (`TestSellerWebStorageConsentGate`, `TestBannedSellerRelistNowRefused`, `test_consent_gate_matches_html_gate`); delete remains gate-free and single-call (`test_delete.py`, `test_lifecycle_service.py::TestDeleteAd`); moderation false commits hidden state and moderation exception leaves ARCHIVED (`TestAdReactivateDirect`, `test_lifecycle_service.py`). Existing suites must pass byte-identically: `test_edit.py::TestAdArchive/TestAdArchiveGetRejected/TestAdReactivateDirect/TestBannedSellerRelistNowRefused/TestSellerWebStorageConsentGate`, `test_lifecycle_service.py`, `test_delete.py`, `test_db_lock_timeout_boundary.py::TestAdReactivateLockTimeout`, `test_lifecycle_api.py` (incl. `test_consent_gate_matches_html_gate`). No new msgid, no migration, no settings change.

## B1 task description

```yaml
id: b1_restore_lifecycle_atomicity

title: >
  P1 — Restore lifecycle atomicity: run the archive/reactivate service calls
  inside the views' open transaction, add the explicit late-PermissionDenied 403
  belt to both views, and make the lock-lifetime documentation truthful.

priority: high

type: implementation

depends_on: []
  # The plan's "preferably after P0" ordering is already satisfied: B0 landed
  # (see "Gate status" and the B0 task description above). No B0 surface is
  # touched: ad_edit, edit_flow, services/submission, and the edit API adapter
  # stay exactly as B0 left them.

# ── Plan/Audit report source (REQUIRED — this task originates from the
#    architecture-correction plan and the B1 audit/research blocks) ──
source_reference: .ai/plans/architecture-correction-plan.md
source_section: §5 R04 — Is the lifecycle extraction safe to keep? · §7 P1 — Restore lifecycle atomicity · §8 G2 — Lifecycle atomicity
source_file: .ai/plans/architecture-correction-execution.md
source_blocks:
  - "B1 audit findings"
  - "B1 research decision"    # selected path = alternative A (move inside the block + PermissionDenied belt)

extra_context: |
  Baseline semantic anchor: migration-commit 57966ea0's ad_archive/ad_reactivate
  each used ONE atomic block per request — fetch under select_for_update,
  ownership refusal, consent refusal, then the transition (/auto_moderate),
  one commit. The extraction commit 5b894a44 split this into TWO transactions
  per request: tx1 wraps only assert_lifecycle_owner (ownership) and the
  consent gate, then EXITS — committing and releasing the row lock — and tx2 is
  the service's own transaction.atomic() inside archive_ad/reactivate_ad, which
  re-fetches, re-locks, and re-checks ownership. Net per request today:
  2 transactions, 2 row-lock acquisitions, 2 commits (baseline 1/1/1) with an
  interleaving window between the consent check and the action, plus two wrong
  error mappings for a pathologically late PermissionDenied (ad_archive →
  Django's default 403 surface, losing the owner message + warning log;
  ad_reactivate → swallowed by the broad except Exception and misreported as
  "reactivation failed during auto-moderation" with logger.exception).

  Chosen contract (research decision A — do not re-litigate):
  - Move both service calls inside the view's existing atomic() block, after the
    consent gate, as its last statements.
  - ad_archive: belt around the in-block service call —
    except Http404: raise, then except PermissionDenied →
    _ownership_refused_forbidden (SAME message/args as the precheck's 403).
  - ad_reactivate: belt as the FIRST except clause of the existing outer try,
    ordered BEFORE except (Http404, DatabaseError): raise and the broad
    except Exception.
  - Docstring-only corrections in services/lifecycle.py and ONE truthful
    docstring bullet in views/api/lifecycle_actions.py. No code change in the
    service, the API adapter, or the delete view.
  - The belt is deliberately temporary: P6/B6 deletes it together with the
    precheck (assert_lifecycle_owner) and the second locked fetch in one
    coherent change. B1 must not start that work.

  Why the move is safe (audit-verified — do not redo the analysis):
  - Django atomic() nests as a SAVEPOINT. The in-repo precedent is the shipped
    ad_edit path: view atomic → apply_edit_payload → _submit_like →
    submit_ad, where submission.py opens its own atomic() plus a
    select_for_update() re-fetch inside the view's outer block.
  - The second select_for_update is a same-transaction self-reacquire — a
    PostgreSQL no-op that cannot block and cannot lock_timeout. Contention
    moves to the single first acquisition, so 55P03 → OperationalError →
    DbLockTimeoutMiddleware 503 is unchanged and deadlock exposure strictly
    shrinks (the ad row is the only lock; can_create_ad reads User without locks).
  - on_commit consumers (search/signals.py cache bump, moderation/signals.py
    immediate alerts) fire at the outermost commit — today the service's tx2
    commit, post-B1 the view's single commit: same strictly-after-commit
    guarantee, one commit instead of two.
  - A raising auto_moderate rolls back the service savepoint, propagates
    through the view's atomic (outer rollback), and is reported by the existing
    broad handler exactly as today — the ad stays ARCHIVED
    (test_reactivate_moderation_error_keeps_ad_archived behavior preserved).
  - analytics.record_event detects caller-owned transactions via
    in_atomic_block and behaves identically under either nesting depth; the
    observed event rows are unchanged.

description: >
  Restore the single-transaction topology for the HTML archive/reactivate
  actions: the ownership precheck, the consent gate, and the lifecycle service
  call share ONE view-owned transaction and one row-lock lifetime, as at
  baseline. Add the explicit PermissionDenied belt so a late ownership refusal
  maps to the owner-specific 403 in both views (never to Django's default 403,
  never to the moderation-failure message). Correct the lock-lifetime and
  savepoint-nesting contract in the lifecycle service docstrings and the one
  stale "Consent ordering" claim in the API adapter's docstring. Prove the
  topology with four new tests: deterministic atomic-continuity flag
  observation, a bounded parked-seam row-lock probe expecting SQLSTATE 55P03,
  the 403-belt pin, and the archive lock-timeout mirror. Everything else is
  behavior-identical: no signature, symbol, msgid, schema, settings, middleware,
  or dependency change; no exception handler is broadened.

goals:
  - one transaction, one row-lock acquisition, one commit per HTML archive and
    reactivate request (the 57966ea0 topology, via the view's atomic block
    staying open across the service call)
  - refusal ordering ownership → consent → action holds on the locked row, in
    the view's block
  - a late PermissionDenied from the service maps to the owner-specific 403
    (_ownership_refused_forbidden with the pre check's exact message and
    warning log) in both views — never to Django's default 403, and in
    ad_reactivate never to the "reactivation failed during auto-moderation"
    panel/log
  - reactivate's handler order becomes PermissionDenied → (Http404,
    DatabaseError): raise → Exception, preserving the 404 boundary and the
    03-DB-004 lock-timeout → DbLockTimeoutMiddleware 503 boundary verbatim
  - lifecycle docstrings state the real lock lifetime (the caller's block) and
    the savepoint/self-reacquire rule; the API adapter's "Consent ordering"
    bullet tells the truth about the HTML consent position
  - delete stays gate-free and single-call; the API adapter stays
    logic-identical; no B0 (edit-result) surface changes
  - regression coverage (4 new tests) makes the two-transaction gap observable:
    the red-on-regression suite proves in-atomic-block entry AND live lock
    holding at the service-call instant

# ─────────────────────────────────────────────────────────────────────────────
# Files and semantic targets (symbols only — never line numbers)
# ─────────────────────────────────────────────────────────────────────────────

files:

  # ── 1. HTML views — the actual fix ─────────────────────────────────────────
  - path: src/backend/apps/ads/views/edit.py
    targets:
      - type: function
        name: ad_archive
        action: move_in_block_and_belt
        change: >
          archive_ad(ad_id, request.user.id) and its `except Http404: raise`
          relocate INTO the existing `with transaction.atomic():` block as the
          block's last statement (after the consent gate), wrapped by a belt;
          the now-redundant separate top-level `try: archive_ad(...)` that
          follows the block dissolves (final shape in changes[0]).
      - type: function
        name: ad_reactivate
        action: move_in_block_and_belt
        change: >
          `passed = reactivate_ad(ad_id, request.user.id).passed` relocates INTO
          the existing `with transaction.atomic():` block as the block's last
          statement, still inside the outer `try:`; add the belt clause as the
          FIRST handler of that outer try (final shape in changes[1]).
      - type: docstring
        name: ad_archive docstring
        change: the "Ownership, locking and the PUBLISHED -> ARCHIVED transition
          live in the shared lifecycle service (S4.1)" boundary sentence now
          states that the service call runs INSIDE this view's atomic block, so
          the check and the action share one unit of work and one lock (the
          service's atomic nests as a savepoint).
      - type: docstring
        name: ad_reactivate docstring
        change: same one-sentence boundary correction (check, gate, service call
          and auto_moderate decision in one transaction; the docstring's
          moderation-failure/DB-error paragraphs stay verbatim).
    semantic_anchors:
      keep_unchanged:
        - the decorators (@require_POST, @login_required) and function signatures
        - the precheck try/except around the assert_lifecycle_owner call with
          its PermissionDenied → _ownership_refused_forbidden 403 mapping (the
          normal ownership refusal; message, "archive"/"reactivate" action
          tokens, log line byte-identical)
        - the ownership-before-consent gate order (_seller_may_create_ad →
          _consent_required_forbidden in second position) and both translated
          messages' bytes
        - except (Http404, DatabaseError): raise with its comment block, the
          broad except Exception with its logger.exception + messages.error +
          dashboard redirect (byte-identical bodies, only prefixed by the new
          PermissionDenied clause)
        - the post-try outcome rendering: passed is False → logger.info +
          messages.warning; elif passed → logger.info; final
          redirect("ads:dashboard")
        - the imports (PermissionDenied and Http404 are already imported — no
          new import, no new symbol, no new msgid)
        - ad_edit entirely, _seller_may_create_ad, _consent_required_forbidden,
          _ownership_refused_forbidden, and the module __all__

  # ── 2. Service docstrings — contract truthing, code untouched ───────────────
  - path: src/backend/apps/ads/services/lifecycle.py
    targets:
      - type: docstring
        name: _fetch_owned_ad docstring
        change: >
          Replace "The row lock must run inside the caller's transaction —
          every public function here opens its own transaction.atomic() before
          calling this, so the lock and the subsequent write share one unit of
          work": extend it with the savepoint-nesting rule — when a boundary
          calls a lifecycle function inside its own open atomic block (the
          ad_edit → submit_ad precedent; the HTML views after B1), the
          service's own atomic() is a SAVEPOINT inside the caller's
          transaction, the select_for_update() re-acquisition is a
          same-transaction self-reacquire (a no-op that cannot block), and the
          lock and the write share the caller's ONE commit; on_commit callbacks
          fire at the outermost commit, and a savepoint rollback releases only
          the savepoint's work, not the row lock.
      - type: docstring
        name: assert_lifecycle_owner docstring
        change: >
          Rewrite "The row is locked for the duration of the returned
          transaction, so the follow-up lifecycle call … sees a stable row":
          assert_lifecycle_owner returns None and does NOT own a long-lived
          lock; its select_for_update runs inside the caller's still-open block
          and the lock lives until the CALLER's transaction exits; the caller
          must keep its own atomic block open across the follow-up
          archive_ad/reactivate_ad call — that is what makes check and action
          one unit of work and keeps refusals ordered ownership → consent →
          action; exiting the block first releases the lock and reintroduces
          the gap. Keep the Raises: block and the boundary-check rationale
          verbatim.
    semantic_anchors:
      keep_unchanged:
        - every code byte: _fetch_owned_ad, assert_lifecycle_owner, archive_ad,
          reactivate_ad, delete_ad bodies; ArchiveResult / ReactivateResult /
          DeleteResult; all Raises blocks and module docstring scope split
        - all signatures and symbols — the elimination of assert_lifecycle_owner
          and the locked second fetch is P6/B6, not B1

  # ── 3. API adapter — one docstring bullet, no code ──────────────────────────
  - path: src/backend/apps/ads/views/api/lifecycle_actions.py
    targets:
      - type: docstring
        name: '"Consent ordering" bullet of the module docstring'
        change: >
          The sentence "The HTML ad_archive / ad_reactivate views assert consent
          **after** the transition block was reached" flips to reflect the
          post-B1 truth: the HTML views assert consent **inside** the
          transaction that performs the transition (ownership → consent →
          action, one commit); the endpoints assert it **before** any service
          call, so a consent-refused request provably changes nothing (§2.5
          "consent BEFORE transition") — that endpoint half stays verbatim.
    semantic_anchors:
      keep_unchanged:
        - all logic in the module's 474 lines: archive_view / reactivate_view /
          delete_view, _run_transition, the uniform-404 ownership mapping, §2.5
          tokens, rate limiting, is_lock_timeout handling, the "Lock timeout"
          bullet

  # ── 4. New regression tests — the G2 evidence ─────────────────────────────
  - path: src/backend/apps/ads/tests/test_edit_views_locking.py
    targets:
      - type: class
        name: TestLifecycleActionAtomicContinuity      # NEW — G2 clause 1
        action: add_code
      - type: class
        name: TestLifecycleActionLockContinuity        # NEW — G2 clause 2
        action: add_code
      - type: module_docstring
        name: test_edit_views_locking module docstring
        change: one paragraph naming the two new classes and what they prove
          (atomic continuity + live lock holding at the service-call instant)
    semantic_anchors:
      keep_unchanged:
        - TestEditViewsLocking (the historical sentinels — including their
          "B1 #7" comments, which refer to an UNRELATED past project cleanup,
          not this correction block)
        - TestEditViewsRowLockConcurrency (verbatim — the generic
          select_for_update-vs-DELETE proof)

  - path: src/backend/apps/ads/tests/test_edit.py
    targets:
      - type: class
        name: TestLifecycleOwnershipRefusalBelt        # NEW — 403-belt pin
        action: add_code
    semantic_anchors:
      keep_unchanged:
        - every existing class in the file, byte-identical: TestAdArchive,
          TestAdArchiveGetRejected, TestAdReactivateDirect,
          TestBannedSellerRelistNowRefused, TestSellerWebStorageConsentGate,
          and all edit-flow/refusal-coverage classes from B0
        - the module pytestmark [django_db, integration] is inherited by the new
          class — no new module-level marks

  - path: src/backend/apps/core/tests/test_db_lock_timeout_boundary.py
    targets:
      - type: class
        name: TestAdArchiveLockTimeout                 # NEW — boundary mirror
        action: add_code
        change: >
          Mirrors TestAdReactivateLockTimeout exactly (same
          _lock_timeout_error() helper, same
          patch.object(edit.Ad.objects, "select_for_update", ...) shared-manager
          patch that lifecycle._fetch_owned_ad also goes through) but drives
          client.post(reverse("ads:archive", args=[ad.id])) on a PUBLISHED ad;
          asserts 503 + "busy" — pins that the move did not swallow the
          archive timeout surface.
    semantic_anchors:
      keep_unchanged:
        - TestMiddleware, TestAdEditLockTimeout, TestAdReactivateLockTimeout,
          TestBulkLockTimeout, TestMiddlewareWiring and both error factories

  # ── 5. Verified-only files — must stay green and untouched ─────────────────
  - path: src/backend/apps/ads/views/delete.py
    change: NO CHANGE (ad_delete is already single-call, gate-free, with its
      PermissionDenied → 403; re-verified by test_delete.py in the focused run)
  - path: src/backend/apps/ads/tests/test_delete.py
    change: NO CHANGE (must stay green)
  - path: src/backend/apps/ads/tests/test_lifecycle_service.py
    change: NO CHANGE (service contract is signature-stable; must stay green)
  - path: src/backend/apps/ads/tests/test_lifecycle_api.py
    change: NO CHANGE (API contract untouched; must stay green, incl.
      TestConsentGate::test_consent_gate_matches_html_gate)
  - path: src/backend/apps/ads/tests/{test_ad_lifecycle,test_ad_consent_gate}.py
    change: NO CHANGE (transition matrix + consent retention records; green)
  - path: src/backend/apps/core/middleware/db_lock_timeout.py
    change: NO CHANGE (the 03-DB-004 boundary is preserved, not altered)

# ─────────────────────────────────────────────────────────────────────────────
# Changes with code hints (contract shapes — implement against the live code)
# ─────────────────────────────────────────────────────────────────────────────

changes:

  - action: modify_code
    target: apps/ads/views/edit.py::ad_archive
    description: >
      Service call inside the block, belt around it, one transaction from
      precheck to commit. No except DatabaseError and no except Exception is
      added in this view — a lock timeout still escapes to
      DbLockTimeoutMiddleware.
    code_hint: |
      with transaction.atomic():
          try:
              assert_lifecycle_owner(ad_id, request.user.id)
          except PermissionDenied:
              return _ownership_refused_forbidden(
                  _("You do not have permission to archive this ad."),
                  "archive", ad_id, request.user.id,
              )

          if not _seller_may_create_ad(request.user):
              return _consent_required_forbidden(request.user, ad_id)

          try:
              archive_ad(ad_id, request.user.id)
          except Http404:
              raise
          except PermissionDenied:
              return _ownership_refused_forbidden(
                  _("You do not have permission to archive this ad."),
                  "archive", ad_id, request.user.id,
              )

      return redirect("ads:dashboard")

  - action: modify_code
    target: apps/ads/views/edit.py::ad_reactivate
    description: >
      Service call inside the block; belt as the FIRST handler of the outer
      try, before (Http404, DatabaseError) and Exception — dead in the normal
      path, it only handles a service-side refusal so it can never reach the
      moderation-failure handler. `except Http404: raise` on archive documents
      that the belt never converts a missing ad; reactivate keeps that meaning
      through the (Http404, DatabaseError) tuple.
    code_hint: |
      passed: bool | None = None
      try:
          with transaction.atomic():
              try:
                  assert_lifecycle_owner(ad_id, request.user.id)
              except PermissionDenied:
                  return _ownership_refused_forbidden(
                      _("You do not have permission to reactivate this ad."),
                      "reactivate", ad_id, request.user.id,
                  )

              if not _seller_may_create_ad(request.user):
                  return _consent_required_forbidden(request.user, ad_id)

              passed = reactivate_ad(ad_id, request.user.id).passed
      except PermissionDenied:
          return _ownership_refused_forbidden(
              _("You do not have permission to reactivate this ad."),
              "reactivate", ad_id, request.user.id,
          )
      except (Http404, DatabaseError):
          raise                      # unchanged block, unchanged comment
      except Exception:
          ...                        # unchanged moderation-failure block

  - action: modify_docstrings
    target: apps/ads/services/lifecycle.py::{_fetch_owned_ad, assert_lifecycle_owner}
    description: >
      Lock-lifetime and savepoint-nesting truthing per the B1 research decision
      (§3) — wording requirements in files[2]. Code, signatures, Raises blocks
      and result tuples byte-identical.

  - action: modify_docstring
    target: apps/ads/views/api/lifecycle_actions.py (module docstring, "Consent ordering" bullet)
    description: one-line truthing; everything else in the module untouched.

  - action: add_tests
    target: the three test modules (files[4..6])
    description: the four regression tests per required_tests.

# Implementation sequence (mandatory order — all four steps land in ONE commit:
# the new tests in steps 4 are red on the pre-move topology by design, so no
# intermediate revision may exist with either a gap or a failing suite):
sequence:
  1: >
     views/edit.py — move archive_ad/reactivate_ad inside their atomic blocks
     and add the two PermissionDenied belts (changes[0..1]) + the two boundary
     docstring sentences. Immediately re-run the FOCUSED command (verification
     block) — only the pre-existing tests exist at this point, and they must
     all be green BEFORE any new test is written: this proves the move is
     behavior-preserving (TestAdArchive, TestAdReactivateDirect,
     TestAdReactivateLockTimeout, TestConsentGate ... byte-identical).
  2: >
     services/lifecycle.py — the two docstring corrections (_fetch_owned_ad,
     assert_lifecycle_owner). Code untouched; no import or signature drift.
  3: >
     views/api/lifecycle_actions.py — the "Consent ordering" bullet. This is a
     pure docstring edit; the focused run is not needed again for it.
  4: >
     Tests — test_edit_views_locking.py (TestLifecycleActionAtomicContinuity +
     TestLifecycleActionLockContinuity), test_edit.py
     (TestLifecycleOwnershipRefusalBelt),
     test_db_lock_timeout_boundary.py (TestAdArchiveLockTimeout).
     All four new classes green (new tests red on pre-MOVE topology by
     design).
  5: >
     Full verification block (focused docker run, ruff, basedpyright,
     .\Makefile.ps1 test), git status review (only the six changed files),
     then the single coherent commit. Do NOT commit between steps 1 and 4.

architectural_constraints:
  - One transaction, one lock acquisition, one commit per HTML lifecycle
    request: the service call is the last statement INSIDE the view's open
    atomic; the service's own atomic nests as a savepoint (the shipped ad_edit →
    submit_ad shape). No new view-level locking helper, no extra query.
  - Refusal ordering is frozen: ownership (assert_lifecycle_owner) → consent
    (_seller_may_create_ad) → action (service call), all on the locked row,
    all inside the block. Belt clauses never reorder anything; they only map a
    PermissionDenied that the precheck path did not produce.
  - Do NOT broaden any catch: no except DatabaseError in ad_archive (a lock
    timeout must keep escaping to DbLockTimeoutMiddleware); do NOT touch
    except (Http404, DatabaseError): raise or the broad except Exception bodies;
    never convert an authorization refusal or a DB error into an apparent
    success (plan §9).
  - Reactivate handler order is load-bearing: PermissionDenied FIRST, then
    (Http404, DatabaseError): raise, then Exception — a reordering that puts
    Exception before the 404/DB clause would turn a timeout into a dashboard
    message and kill the 503 boundary.
  - Belt responses must be byte-identical to the precheck responses: the SAME
    _ownership_refused_forbidden call (same translated message string, same
    action token, same warning log) as the precheck's 403 uses.
  - No signature or symbol change anywhere: archive_ad, reactivate_ad,
    delete_ad, assert_lifecycle_owner, _fetch_owned_ad and all three result
    NamedTuple pairs keep their current names/shapes. `assert_lifecycle_owner`
    deletion, the single-locked-ad convention and the belt's removal are
    P6/B6 — B1 must not start them.
  - The API adapter is logic-frozen: only the one docstring bullet changes;
    its uniform-404 ownership mapping, §2.5 tokens, rate limits and
    _run_transition broad-catch → 503 retryable contract are untouched.
  - ad_delete and the delete flow are untouched (already the correct
    single-transaction, gate-free shape).
  - i18n: no new msgids, no .po/.mo edit, no scratch extraction — every string
    the belts render already exists in the catalogs and is reused verbatim.
  - No schema/model/migration, settings/env, middleware, dependency, lockfile,
    URL, or template change. `git status --short` must list only the six
    changed files listed in files (items 1–4: the three source files and the
    three test files).

required_tests:
  atomic_continuity_deterministic: >
    apps/ads/tests/test_edit_views_locking.py — NEW parametrized class
    `TestLifecycleActionAtomicContinuity` with ONE test method
    `test_html_action_runs_inside_the_view_transaction`, parametrized over
    ("status", "target", "service_name") rows (AdStatus.PUBLISHED, "ads:archive",
    "archive_ad") and (AdStatus.ARCHIVED, "ads:reactivate", "reactivate_ad").
    Marker stack: `@pytest.mark.django_db(transaction=True)` ONLY (plus the
    module's pytestmark integration) — deterministic, fast tier, no threads, no
    sleeps, NOT slow-marked. Nothing else may be added to the stack: under
    plain `django_db` the pytest wrapper keeps in_atomic_block True and the
    test proves nothing (repo caveat in test_ad_detail_queries.py /
    test_sweep_lock_structure.py). Technique: monkeypatch the exact
    view-module names (`apps.ads.views.edit.archive_ad` / `.reactivate_ad` —
    the name the view actually resolves) with a delegating wrapper that
    records `transaction.get_connection().in_atomic_block` at wrapper entry
    BEFORE delegating to the original; drive a real
    `Client().post(reverse(target, args=[ad.id]))` (seller logged in;
    reactivate row uses the permissive_criteria fixture so the real service
    completes ARCHIVED → ON_MODERATION → PUBLISHED); assert
    `observed == [True]` and `response.status_code == 302`. On the pre-move
    topology the flag is False (the view's block already exited); post-move
    it is True because the only open block at wrapper entry is the view's.
    DO NOT assert on savepoint_ids — implementation detail, not the contract.
  row_lock_continuity_concurrent: >
    apps/ads/tests/test_edit_views_locking.py — NEW parametrized class
    `TestLifecycleActionLockContinuity` with ONE test method
    `test_view_holds_the_row_lock_until_the_action_commits`, parametrized
    archive (PUBLISHED → ARCHIVED, parking `edit.archive_ad`) and reactivate
    (ARCHIVED → PUBLISHED via permissive_criteria, parking `edit.reactivate_ad`
    — which also parks inside the lock, before auto_moderate). Marker stack —
    the repo's calibrated concurrency stack, applied to the class, VERBATIM:
    @pytest.mark.django_db(transaction=True), @pytest.mark.slow,
    @pytest.mark.integration, @pytest.mark.concurrent,
    @pytest.mark.xdist_group("concurrent"),
    @pytest.mark.flaky(reruns=1, reruns_delay=1). All waits are bounded
    Events (entered/proceed, timeout=10) and joins (timeout=15) — no
    time.sleep coordination. Technique: background thread runs the real
    client.post(...) and parks at the view-module seam (entry sets `entered`,
    then waits on `proceed`, delegates, and closes its thread-local connection
    in a finally); the main thread — its OWN thread-local connection — waits
    for `entered`, then probes `Ad.objects.select_for_update().get(pk=ad.id)`
    inside its own transaction.atomic() with `SET LOCAL lock_timeout='500ms'`
    and EXPECTS OperationalError with `__cause__.sqlstate == "55P03"`
    (SQLSTATE, not message, matching is_lock_timeout's contract). Capture the
    probe exception in a dict and assert after the except block. ORDERING —
    load-bearing: the probe's atomic block must fully EXIT before
    `proceed.set()` so the pre-move topology fails on the probe assertion
    instead of deadlocking (the parked service would otherwise block on the
    probe's lock). After release: join with a deadline, assert the request
    completed without error, `response[0].status_code == 302`, and the ad's
    committed final status (ARCHIVED / PUBLISHED). `SET LOCAL` is
    transaction-scoped — it cannot leak into the pooled connection.
  ownership_refusal_belt_pins: >
    apps/ads/tests/test_edit.py — NEW class
    `TestLifecycleOwnershipRefusalBelt` with TWO test methods (module
    pytestmark [django_db, integration] inherited, no extra marks). Both drive
    the REAL views through `Client().post` with the view-module seam patched
    to raise PermissionDenied("You do not own this ad.") — the point is the
    handler, so the stub does not delegate:
    `test_archive_late_permission_denied_keeps_the_ownership_403` — a
    PUBLISHED ad (so the request reaches the belt past the precheck);
    asserts the ownership 403, NOT Django's default 403 surface —
    `response.content` contains the owner message "You do not have permission
    to archive this ad."; `test_reactivate_late_permission_denied_is_not_a_moderation_failure`
    — an ARCHIVED ad, response NOT followed with follow=True; asserts the
    ownership 403, `"reactivation failed during auto-moderation" not in
    caplog.text`, and the ad row still ARCHIVED (unchanged).
  archive_lock_timeout_mirror: >
    apps/core/tests/test_db_lock_timeout_boundary.py — NEW class
    `TestAdArchiveLockTimeout` with ONE test method
    `test_lock_timeout_still_returns_503` (@pytest.mark.django_db + module
    integration): the exact TestAdReactivateLockTimeout shape against
    reverse("ads:archive", ...) — patch.object(edit.Ad.objects,
    "select_for_update", side_effect=_lock_timeout_error()) (the patch hits
    the FIRST locked fetch inside the block, the one
    lifecycle._fetch_owned_ad also goes through), assert 503 + "busy"
    (case-insensitive) — pinning that the move does not swallow the archive
    timeout surface; no real lock needed, near-zero cost.
  existing_suites_must_stay_green: >
    Verified-only, byte-identical, no edits: test_edit.py (TestAdArchive,
    TestAdArchiveGetRejected, TestAdReactivateDirect incl.
    test_reactivate_moderation_failure_surfaces_message and
    test_reactivate_moderation_error_keeps_ad_archived which patches
    apps.moderation.services.auto_moderation.auto_moderate — unaffected by the
    move because it is the seam lifecycle.py itself calls,
    TestBannedSellerRelistNowRefused,
    TestSellerWebStorageConsentGate.test_archive_refused_for_owner_without_consent
    and test_reactivate_refused_for_owner_without_consent),
    test_lifecycle_service.py (whole file), test_delete.py,
    test_db_lock_timeout_boundary.py::TestAdReactivateLockTimeout,
    test_lifecycle_api.py (whole file, incl.
    TestConsentGate::test_consent_gate_matches_html_gate), test_ad_lifecycle.py,
    test_ad_consent_gate.py.
  rejected_techniques_do_not_use: >
    pg_locks (shows waiters, not the non-waiting tuple-lock holder — no repo
    precedent), transaction.on_commit / TestCase.captureOnCommitCallbacks
    (callbacks fire at the outermost commit under both topologies — they
    cannot discriminate a lock gap), source-string/inspect.getsource
    assertions (already removed once, see TestEditViewsLocking comments),
    and sleep-based rendezvous (racy — the parked-seam Event pattern is the
    deterministic alternative).

verification:
  test_db_note: >
    Never run `uv run pytest` locally (no DB on localhost:5432). Start the
    test DB with `.\Makefile.ps1 test-db` if
    `docker ps --filter "name=mko-bazuna-test-db-"` is empty.
  focused_b1: >
    docker compose --project-name mko-bazuna-test --env-file .env.test -f
    docker-compose.yml -f docker-compose.test.yml run --rm -e
    "PYTEST_OPTS=src/backend/apps/ads/tests/test_edit.py src/backend/apps/ads/tests/test_edit_views_locking.py
    src/backend/apps/ads/tests/test_edit_flow_service.py src/backend/apps/ads/tests/test_ad_lifecycle.py
    src/backend/apps/ads/tests/test_lifecycle_service.py src/backend/apps/ads/tests/test_ad_consent_gate.py
    src/backend/apps/ads/tests/test_edit_route_api.py src/backend/apps/ads/tests/test_lifecycle_api.py
    src/backend/apps/core/tests/test_db_lock_timeout_boundary.py src/backend/apps/ads/tests/test_delete.py"
    test
    (the plan §8 P0/P1 gate set — B0's edit suites re-run to prove B1 does not
    regress B0 — extended with the two B1-relevant boundary/delete suites).
    Run it twice: once right after sequence step 1 (only pre-existing tests —
    behavior preservation), and once after step 4 (the four new classes —
    regression evidence).
  focused_run_semantics: >
    PYTEST_OPTS is expanded BEFORE the fixed PYTEST_DEFAULTS
    (docker/entrypoint-test.sh) — it ADDS to, never replaces,
    --reuse-db/--tb=short/-n auto/--maxprocesses=4/--dist loadgroup, so the
    focused run is parallel and keeps xdist_group("concurrent") grouping.
    All PYTEST_OPTS tokens must be single-token file paths (the entrypoint
    expansion is unquoted; quoted multi-token values break).
  concurrent_coverage_note: >
    The focused run sets no PYTEST_SKIP_MARKERS, so the slow-marked
    TestLifecycleActionLockContinuity RUNS there; the fast gate
    (`.\Makefile.ps1 test`, PYTEST_SKIP_MARKERS="seed or slow or real_images")
    skips it by design. No `.\Makefile.ps1 test-all` run is required for B1
    (no seed/slow-marker/real_images surface beyond the one covered by the
    focused run; nightly re-covers it anyway).
  lint: uv run ruff check src/backend/apps/ads src/backend/apps/core
  typecheck: >
    uv run basedpyright src/backend/apps/ads/views/edit.py
    src/backend/apps/ads/services/lifecycle.py
    src/backend/apps/ads/views/api/lifecycle_actions.py
    src/backend/apps/ads/tests/test_edit.py
    src/backend/apps/ads/tests/test_edit_views_locking.py
    src/backend/apps/core/tests/test_db_lock_timeout_boundary.py
  fast_gate: .\Makefile.ps1 test     # canonical PR gate; the shipped marker
                                     # parity guard and the lock-boundary suites
                                     # run inside it
  git_hygiene: >
    `git status --short` must list exactly the six changed files (views/edit.py,
    services/lifecycle.py, views/api/lifecycle_actions.py,
    apps/ads/tests/test_edit.py, apps/ads/tests/test_edit_views_locking.py,
    apps/core/tests/test_db_lock_timeout_boundary.py); `git diff --check`
    clean; no migration delta is expected (no model changes).

acceptance_criteria:
  - >
    Topology: `Client()`-driven HTML archive/reactivate requests show
    transaction.get_connection().in_atomic_block True at the view-module
    service seam (TestLifecycleActionAtomicContinuity green), and a
    main-thread select_for_update probe under SET LOCAL lock_timeout='500ms'
    times out with SQLSTATE 55P03 while the request is parked at the seam,
    then the request commits the transition once and redirects
    (TestLifecycleActionLockContinuity green).
  - >
    Belt: a monkeypatched PermissionDenied at the archive seam yields the
    owner-specific translated 403 bytes; at the reactivate seam it yields the
    owner 403 with the ad still ARCHIVED and NO
    "reactivation failed during auto-moderation" log
    (TestLifecycleOwnershipRefusalBelt green).
  - >
    Boundary: a lock timeout still returns 503 + "busy" for BOTH views
    (TestAdArchiveLockTimeout + TestAdReactivateLockTimeout green).
  - >
    Order and messages: refusal ordering ownership → consent → action is
    unchanged; the precheck 403s, consent 403, moderation-failure message,
    redirect targets, log lines, and belt responses are byte-identical to the
    pre-task responses; reactivate's handler order is PermissionDenied →
    (Http404, DatabaseError): raise → Exception.
  - >
    Existing suites green byte-identically: the test_edit.py archive/reactivate
    and consent/ban classes, test_lifecycle_service.py, test_delete.py,
    test_lifecycle_api.py (incl. test_consent_gate_matches_html_gate),
    test_ad_lifecycle.py, test_ad_consent_gate.py — and B0's re-covered
    suites (test_edit_flow_service.py, test_edit_route_api.py stay untouched
    by B1 and stay green).
  - >
    Docs: services/lifecycle.py's _fetch_owned_ad and assert_lifecycle_owner
    docstrings and the api/lifecycle_actions.py "Consent ordering" bullet
    state the shipped lock/transaction contract truthfully; the two view
    docstrings describe the in-block service call.
  - >
    No functional surface beyond the six files: no msgid, catalog, schema,
    migration, settings, middleware, URL, template or dependency delta;
    `git status --short` lists only the six files; ruff and basedpyright clean
    on the changed files; `.\Makefile.ps1 test` green.

out_of_scope:
  - Removing `assert_lifecycle_owner`, the service's second locked fetch, or
    the new belt; any signature simplification or single-locked-ad
    convention — all P6/B6, after P4 retires the API callers. B1 must not
    start that work.
  - Any change to apps/ads/views/api/lifecycle_actions.py beyond the ONE
    docstring bullet (uniform-404 mapping, §2.5 tokens, _run_transition,
    rate limits all stay), and any logic change in services/lifecycle.py
    (docstrings only).
  - ad_delete / views/delete.py / the delete flow (already correct,
    consent-free single call — re-verified only).
  - B0 surfaces: ad_edit, edit_flow, views/api/edit.py, submission — untouched.
  - i18n catalog edits or any scratch makemessages run (no new msgids).
  - Any schema/model/migration, settings/env, middleware, URL, template,
    dependency or lockfile change; any exception-handler broadening (no
    except DatabaseError in archive; no new catches anywhere).
  - The G2 gate-status flip in this file (that happens after the Validator
    step, per the source-plan process).

risks:
  - >
    Handler-order regression (reactivate): if `except PermissionDenied` is not
    first — or worse, the (Http404, DatabaseError) clause moves below
    Exception — a lock timeout becomes a dashboard message and the 503
    boundary dies. Mitigation: exact order pinned in changes[1] +
    architectural_constraints, TestLifecycleActionLockContinuity +
    both lock-timeout boundary tests must stay green.
  - >
    Over-broadening (archive): the implementer might add except DatabaseError
    or except Exception around the moved call "for symmetry" — that is new
    semantics with no behavior gain; a lock timeout must reach
    DbLockTimeoutMiddleware. Mitigation: TestAdArchiveLockTimeout + review
    of the constraint block.
  - >
    Test 2 flakiness: thread-scheduling noise could break the bounded probe.
    Mitigation (all already in the design): Event-bounded coordination (no
    sleeps), 500 ms lock_timeout well above noise, SET LOCAL scoping,
    xdist_group("concurrent") keeping the class on one xdist worker, and
    flaky(reruns=1, reruns_delay=1). If it still flakes, the documented
    fallback is select_for_update(nowait=True) — raise the fallback in the
    task result; do not widen waits.
  - >
    Test-1 false pass: recording in_atomic_block AFTER delegating (inside the
    service) is always True post-move and proves nothing; under plain
    django_db the pytest wrapper also keeps it True. Mitigation: the spec
    mandates recording at wrapper entry BEFORE delegating, and
    transaction=True on both classes.
  - >
    Red-before-green suite state: the new tests fail on the pre-fix topology by
    design — if they are committed before the move lands, main is left with a
    broken suite. Mitigation: steps 1–4 land as ONE coherent commit; never
    commit a step in isolation.
  - >
    P6 hand-off drift: the belt and precheck are temporary; a later change
    that deletes one but not the other leaves misleading shape. Mitigation:
    this task records the pairing in extra_context (P6 deletes both together);
    the G2 tests are designed to survive P6 (tests 1, 2, 4 keep meaning; test
    3 is rewritten by P6 to the single-path assertion).
  - >
    Baseline drift: if `ad_archive`/`ad_reactivate`/`lifecycle.py` have moved
    since the B1 audit (they were byte-identical to 5b894a44 at audit time),
    stop and re-verify against the new state instead of applying stale
    assumptions (`git status` + re-read the two functions first).

commit:
  message: >
    fix(ads): restore lifecycle atomicity — run archive/reactivate inside the
    view transaction, add the ownership 403 belt
  body: >
    The HTML ad_archive/ad_reactivate checks (assert_lifecycle_owner,
    consent) now share one view-owned transaction with the
    archive_ad/reactivate_ad call, restoring the one-transaction/one-lock
    topology of 57966ea0 (was: precheck block exits and drops the row lock
    before the service re-fetches and re-locks; 2 tx/2 locks/2 commits per
    request). Both views map a late PermissionDenied to the owner-specific 403
    via _ownership_refused_forbidden (archive previously fell to Django's
    default 403; reactivate previously misreported it as an auto-moderation
    failure). lifecycle.py docstrings now state the real lock lifetime
    (caller's block) and savepoint/self-reacquire rule; the API lifecycle
    adapter's "Consent ordering" bullet is corrected. Tests: atomic
    continuity (in_atomic_block at the view-module seam), park-and-probe lock
    continuity (55P03 via SET LOCAL lock_timeout), the 403-belt pin, and the
    archive lock-timeout 503 mirror.
  files_hint: single coherent commit covering all six files; no deployable
    intermediate revision may exist (the new regression tests are red against
    the two-transaction topology).
```</think><tool_call>edit<arg_key>filePath</arg_key><arg_value>C:\py_dev\mko_bazuna\.ai\plans\architecture-correction-execution.md


---

## B3 audit findings

Audit block: B3 (P3 — Transfer business tests) · READ-ONLY · Date: 2026-11-05 · HEAD `716fe3e1` (B1 landed; working tree clean except this plan file). Scope: all 20 retiring test modules (301 collected `def test_` functions), plus mixed-file surgery on `test_copy_ad.py`. Every destination claim below was verified against the CURRENT tree (post-B0 honest-refusal work is present in `test_edit_flow_service.py::TestApplyEditPayloadSubmitOutcomeMatrix` and `test_edit.py::TestEditSubmissionRefusalsRender`; post-B1 work in `test_edit.py::TestLifecycleOwnershipRefusalBelt` and `test_edit_views_locking.py::TestLifecycleActionAtomicContinuity/LockContinuity`).

Legend — **COVERED**: invariant already asserted by a named retained test. **PORT**: currently asserted ONLY in a retiring module → must land in the named destination BEFORE deletion (deletion blocker). **TRANSPORT**: JSON envelope / status-code / problem-doc / route-reverse assertion bound to the dying endpoint, or an API↔HTML parity test whose service/HTML legs are independently covered. Parity tests die with the mirror; the retained leg keeps the invariant.

### 1. ads

#### `apps/ads/tests/test_ad_detail_api.py` (18 tests / 7 classes)

| Class | Invariant | Verdict |
|---|---|---|
| TestAudienceMatrix | Non-published states (draft, unpublished, declined, withdrawn, banned, deleted) → 404 on detail | declined COVERED `test_detail_context.py::TestAdDetailDeclinedUserVisibility`; banned COVERED `test_ban_visibility_gate.py` (detail 404); withdrawn (real path) COVERED `test_ad_consent_gate.py::test_deleted_ad_404s_from_detail`; **draft/non-published rows PORT → `test_detail_context.py`** (new `TestAdDetailAudienceStatuses`, parametrized over DRAFT/ON_MODERATION/REJECTED/DELETED/ON_MODERATION_FAILED; only media-gate drafts are covered today, `test_media_security.py::test_draft_ad_returns_forbidden`) |
| TestSideEffectParity | HTML detail GET records exactly one `AD_VIEWED` with seller attribution; missing-id GET records none | **PORT → `test_detail_context.py`** (new `TestAdDetailViewEvent`: one event, `user_id=seller`, `ad_id`; 404 leg records none). Repo-wide grep shows NO retained test asserts the HTML detail→AD_VIEWED wiring — this is the single most at-risk invariant in the whole scope |
| TestFavoritesState | `is_favorited` false anonymous / false authenticated-non-favorite / true authenticated-favorite | false rows COVERED `test_detail_context.py::test_detail_context_contains_is_favorited_for_authenticated`; **true row PORT** (extend that test: favorite the ad first, assert context True) |
| TestMediaUrlsOnly | media serialized as URL strings only | TRANSPORT (HTML gallery rendering covered by `test_gallery_markup.py`; media gating by `test_media_security.py`) |
| TestContactDeepLink | contact bot URL; withheld when seller has no `telegram_id` | deep-link href COVERED `test_detail_render.py::test_telegram_contact_deep_link_href`; the telegram_id-None withholding is an API-serialization branch with NO HTML counterpart (template renders the contact link unconditionally) — TRANSPORT with divergence note |
| TestRateLimitProblem | 429 problem envelope | TRANSPORT (endpoint dies) |
| TestReverseSmoke | route reverse | TRANSPORT (route dies) |

#### `apps/ads/tests/test_dashboard_api.py` (8 tests / 5 classes)

| Class | Invariant | Verdict |
|---|---|---|
| TestAuthMatrix | 401 anonymous / 200 consented | TRANSPORT |
| TestConsentGateRL1 | R-L1 consent gate before grouping (never-consented/withdrawn/banned → 403) | never-consented COVERED `test_edit.py::TestSellerWebStorageConsentGate::test_dashboard_refused_for_owner_without_consent` (403, HTML); banned COVERED `test_moderation_views.py::TestBanUserSessionKnownGap::test_banned_seller_is_now_refused_the_dashboard`; withdrawn row is structurally unreachable on HTML (withdrawal soft-deletes + nulls telegram_id + flushes session — `test_consent.py::test_withdraw_workflow_returns_anonymous`) — TRANSPORT |
| TestGateEquivalence | API gate == HTML gate | TRANSPORT (parity) |
| TestTimeRangeParity | time_range values / grouping | COVERED `test_dashboard_stats.py::TestDashboardTimeRange` (7/30/invalid→all_time) + `TestAdsByStatusService` (five-status grouping) + `TestViewConsumesServiceGrouping` |
| TestPayloadShape | groups/stats block parity | TRANSPORT; stats semantics COVERED `apps/analytics/tests/test_views.py` + `test_trust_analytics.py` + `test_seller_stats.py` |

#### `apps/ads/tests/test_edit_route_api.py` (28 tests / 11 classes + 1 module fn; file is post-B0)

| Class | Invariant | Verdict |
|---|---|---|
| TestAuthMatrix / TestMethodGate / TestRateLimit | 401 / 405 / 429 | TRANSPORT |
| TestValidationMatrix | 422 + nothing written | no-write COVERED `test_edit.py::TestSellerWebStorageConsentGate::test_edit_post_refused_and_writes_nothing`; DTO 422 mapping TRANSPORT; refusal rendering COVERED `TestEditSubmissionRefusalsRender` (B0) |
| TestUniformNotFound | missing vs non-owned indistinguishable | TRANSPORT (ownership refusal on HTML COVERED `TestEditAuthorization` + `TestLifecycleOwnershipRefusalBelt` (B1)) |
| TestConsentGate | consent before edit writes; consent race → 403 | COVERED `TestSellerWebStorageConsentGate::test_edit_get/post_refused_for_owner_without_consent`; B0 refusal set COVERED `test_edit_flow_service.py::TestApplyEditPayloadSubmitOutcomeMatrix` + `test_edit.py::TestEditSubmissionRefusalsRender`; the API-specific 403 mapping is TRANSPORT |
| TestNotEditable | 409 status refusals; affordance predicate enumeration | COVERED `test_edit.py::TestEditStatusAllowListEnumeration::test_every_status_has_a_defined_outcome` (all 7 statuses, 200+error+unchanged) and `test_edit_flow_service.py::TestCanEditAd::test_status_matrix` (`can_edit_ad(ad, seller.id) is (status in EDIT_FORM_AVAILABLE_STATUSES)` — the exact predicate equality the API test asserted) |
| TestInvalidTransition | archived-without-reactivate → 409 | COVERED `test_edit_flow_service.py::TestApplyEditPayloadReactivation::test_archived_without_flag_is_refused` |
| TestSubmitOutcomeRefusalMapping (B0) | honest refusal mapping on API tier | TRANSPORT (endpoint dies; service/HTML legs landed in B0) |
| TestEditOutcomeMatrix | happy-path parity vs service tier | COVERED: price-only clock reset `TestApplyPriceChangeDelegation` + `TestApplyEditPayloadPriceOnly`; published text edit `TestPublishedTextEdit`; reactivation events `test_lifecycle_service.py::TestReactivateAd` (AD_PUBLISHED + MODERATION_APPROVED); moderation-failure parking `TestReactivationAutoModerate` + `TestApplyEditPayloadSubmitOutcomeMatrix` |
| TestO27BodyContract | AdEditBody semantics (missing-field overwrite, partial key set) | TRANSPORT (DTO dies; surviving form behavior is the HTML edit form, covered by the edit suites) |
| `test_route_is_registered_under_the_plan_url` | URLconf registration | TRANSPORT |

#### `apps/ads/tests/test_favorites_toggle_api.py` (13 tests)

Toggle on/off/count COVERED `test_favorites.py::TestToggleFavoriteService::test_toggle_on_off_on_reports_active_and_count`; count scoping COVERED `::test_count_is_scoped_to_the_caller`; non-published 404 COVERED `test_favorites.py::TestFavoriteToggle::test_non_published_ad_is_404`. Remaining classes (auth/method/validation/uniform-404/rate) TRANSPORT. No ports. CSRF on the surviving HTML heart form is independently pinned by `test_favorites.py::test_heart_form_carries_csrf_header` (AUTZ-002) — not in retirement scope.

#### `apps/ads/tests/test_lifecycle_api.py` (22 tests)

Auth/method/rate/uniform/consent + 405/415/422-payload classes TRANSPORT; consent gate COVERED `TestSellerWebStorageConsentGate::test_archive/reactivate_refused_for_owner_without_consent`. Happy paths: archive/reactivate/delete end-state parity — service semantics COVERED `test_lifecycle_service.py::TestArchiveAd/TestReactivateAd/TestDeleteAd` (incl. unarchive rows purge), HTML views COVERED `test_edit.py::TestAdArchive/TestAdReactivateDirect`; archived-without-reactivate COVERED `TestApplyEditPayloadReactivation::test_archived_without_flag_is_refused`. No ports.

#### `apps/ads/tests/test_listings_api.py` (25 tests / 7 classes) — contains the D28 defect

| Class / dimension | Verdict |
|---|---|
| Matrix: category descendants (subtree incl. self) | **PORT** — no retained listings-surface test creates a child category and asserts the parent's listing page shows descendant ads (search surface only: `test_search_view.py::TestSearchViewDescendantCategories`). Destination: `apps/ads/tests/test_listings_query.py` (new) |
| Matrix: unknown category applies no filter | **PORT** (sub-assertion in the same new query test) |
| Matrix: city filter | COVERED `test_filter_url_reset.py::test_city_category_coexistence` (behavioral narrowing on results) |
| Matrix: min/max price bounds | **PORT** — `test_listings_context.py` maps context values only; `test_price_sort.py` covers ordering, not bounds. Destination: `test_listings_query.py` |
| Matrix: purpose | COVERED `test_listing_purpose_filter.py` |
| Matrix: condition | COVERED `test_listing_condition_filter.py` |
| Matrix: features AND | COVERED `test_features_filter.py` |
| Matrix: every sort accepted | COVERED `test_listings_sort.py` (date_new/date_old/default + `-id` tiebreakers) + `test_price_sort.py` (price_low/high + tiebreakers) |
| Matrix: unknown sort falls back to newest-first | COVERED `test_listings_sort.py::test_sort_uses_newest_first_when_sort_param_is_unknown` |
| Matrix: 3-page union / no duplicates across every sort | **PORT** (with the D28 fix — see §6 below) to `test_listings_query.py` |
| TestAudienceParity | banned COVERED `test_ban_visibility_gate.py`; declined COVERED `test_search_view.py::TestSearchViewDeclinedConsent` (covers listings too); withdrawal via real path COVERED `test_ad_consent_gate.py::test_deleted_ad_is_absent_from_listings_queryset`. **PORT** the synthetic audience rows (consent_revoked_at-only with ad still PUBLISHED; is_deleted-only) through `ListingsQuery.build_queryset` — predicate conjuncts are covered at `users/tests/test_account_state.py::TestPredicateConjunctIsLoadBearing`, but no retained test wires those two states into the listings queryset |
| TestValidationProblem | 422 over-cap features | TRANSPORT (shared-DTO rule pinned on the surviving search surface by `test_search_view.py::test_features_over_cap_rejected_at_dto` — same `ListingsQueryParams` constraint) |
| TestHtmlJsonParity | warm-cache HTML == JSON | TRANSPORT (parity; warm-cache discipline retained by `test_search_cache.py`) |
| TestPaginationEnvelope | per_page clamp / has_next keys | TRANSPORT (envelope keys); page-union behavior is subsumed by the cross-product port |
| TestRateLimitProblem / TestReverseSmoke | | TRANSPORT |

#### `apps/ads/tests/test_submit_route_api.py` (23 tests)

Auth/method/rate/uniform/consent classes TRANSPORT. Submit outcomes: DRAFT_GONE COVERED `test_submission.py::test_submit_ad_deleted_draft_returns_draft_gone`; PHOTO_UNAVAILABLE COVERED `test_submission.py::test_missing_staged_file_reports_a_recoverable_error`; INVALID_TRANSITION COVERED `::test_submit_ad_invalid_transition_returns_outcome_not_raises`; OperationalError COVERED `::test_submit_ad_operational_error_propagates_as_exception`; consent gate COVERED `TestSubmitAdStorageConsentGate`; staged-file lifecycle COVERED `::test_intra_submission_duplicate_reclaims_all_four_staged_files` + bot `test_save_photo_integration.py::test_submit_ad_moves_staging_to_permanent` / `::test_submit_ad_rollback_leaves_files_in_staging`. TestDryRunInventory (O-14 readiness/media-caps inventory) and TestNotReadySubmission: plan §6 explicitly rules these are not retained product requirements — TRANSPORT/delete (note `views/api/submit.py::media_caps()` reads the moderation tuple by index — D23/P5 dependency; P5 must keep that call-site fix coordinated). Happy-path parity dies; publishing invariant COVERED `test_submission.py::test_submit_ad_commit_when_auto_moderate_passes`. No ports.

### 2. cabinet

#### `apps/cabinet/tests/test_favorites_list_api.py` (5 tests)

Auth/method/rate TRANSPORT. Content parity COVERED `test_favorites.py::TestFavoritesList` (HTML list, media behind gate) + `TestFavoritesQuerysetService` (scoping, ordering `-favorites__created_at`, media-gate column). Pagination envelope TRANSPORT (ordering+scoping retained at service tier). No mandatory ports (optional advisory: one multi-page HTML favorites pagination test).

#### `apps/cabinet/tests/test_saved_search_write_api.py` (21 tests)

Happy paths (create/toggle/edit/delete end-state) COVERED `test_cabinet_sections.py::TestSavedSearchesManagement::test_create_disable_edit_delete_workflow` + `test_saved_search_create.py` + `test_saved_search_service.py`. Over-cap refusal + PII redaction COVERED `test_saved_search_create.py` (at-cap round-trip, over-cap refusal, redaction) + `TestCreate::test_create_returns_redacted_dto...` + `::test_over_cap_sixth_refuses`. Cross-owner refusal COVERED `test_saved_search_service.py::TestUpdate::test_update_foreign_row_raises_does_not_exist` + `test_cabinet_sections.py::test_guest_cannot_manage_other_users_search` (toggle/delete 404; service covers the edit leg). Token stability COVERED `TestTokenBehavior` (never regenerated on update/toggle; unique across rows). TestHtmlEndStateEquivalence TRANSPORT (parity). Auth/method/validation/uniform/rate TRANSPORT. No mandatory ports.

#### `apps/cabinet/tests/test_saved_searches_api.py` (14 tests)

A6 anonymous search-history is session-only COVERED `test_autocomplete.py::TestSearchViewRecording::test_search_anonymous_records_session_history` (+ service anonymous tests). Ownership scoping of the list read: management/write refusals covered (above); **advisory PORT (LOW)** — one `test_cabinet_sections.py` test asserting another user's saved search is not rendered in my cabinet list (read-leg scoping currently only implied by write refusals). Pagination envelopes TRANSPORT (history service limits COVERED `TestSearchHistoryService`; saved-search multi-page HTML advisory only). TestHtmlParity + TestUrlRestructureGuard (D9) + token non-leak TRANSPORT.

#### `apps/cabinet/tests/test_search_history_clear_api.py` (9 tests)

Clear semantics COVERED `test_cabinet_sections.py::TestSearchHistorySection::test_lists_and_clears_history` (DB rows cleared + empty-state render). **PORT (deletion blockers)**: (a) Q8 idempotency — re-POST clear on already-empty history succeeds and stays at 0; (b) scope — another user's `SearchHistory` rows are untouched by my clear. Both land in `test_cabinet_sections.py::TestSearchHistorySection` (extend to 2 asserts or one `test_clear_is_idempotent_and_scoped_to_the_owner`). Auth/method/rate TRANSPORT.

### 3. analytics

#### `apps/analytics/tests/test_analytics_api.py` (13 tests)

All payload-parity and 401/404-vs-403 conventions TRANSPORT. Data invariants COVERED: seller dashboard `test_views.py::TestSellerTrustDashboardView` (score/level bands incl. 60.0 VERIFIED, daily metrics, totals, other-seller exclusion, empty-zero, cache+compute `test_seller_stats.py::TestSellerStatsCache` incl. TTL 300 and days filtering); moderation dashboard `TestModerationAnalyticsView` (staff 404/200, stats incl. `approved == 1`, pending queue, moderator performance, rejection reasons) + `test_moderation_analytics.py` (days-parameter exclusions, ordering). No ports.

### 4. categories / locations

#### `apps/categories/tests/test_categories_api.py` (10 tests)

Active-only children, unknown-404, inactive-top-404, localized content, locale isolation COVERED `test_submenu.py::TestCategorySubmenu` (+ `test_submenu_swr.py` cache semantics incl. version-bump isolation). Name resolution fallback COVERED `test_categories.py::TestCategoryGetNameFallback`. JSON tree shape, nesting depth, leaf `children=[]`, orphan-under-inactive-parent, header-root parity, rate limit: TRANSPORT. **Advisory (LOW)**: the active-only + name-order of header `root_categories` was only asserted via the API parity test — optionally port one context-processor test (`apps/core` header test) asserting active-only, name-ordered roots.

#### `apps/locations/tests/test_cities_api.py` (6 tests)

City catalog integrity COVERED `test_load_cities.py` (all slugs, field deserialization, idempotency, catalog lock); suggestion/fuzzy tiers COVERED `test_city_suggestions.py`; slug resolution incl. stale-slug passthrough COVERED `test_city_resolution_middleware.py`. JSON envelope/ordering/localized names TRANSPORT. No ports.

### 5. moderation

#### `apps/moderation/tests/test_moderation_api_actions.py` (23 tests)

Approve outcomes COVERED `test_admin_actions.py::TestApproveAdOutcome` (out-of-pair `transition_refused`, on-moderation → PUBLISHED, failed no-transition/no-rows, criteria-failure `criteria_rejected`) + `test_moderation_views.py::TestApproveAdView`. Reject outcomes COVERED `TestRejectAdRouting/Outcome` (incl. already-rejected no-op) + `TestRejectAdView`. Ban privileged/self refusals COVERED `test_admin_ban_privilege_guard.py` (cannot ban superuser/staff row, self-ban refused, no audit row on refusal, idempotent bulk ban, two-sided tier wording); banned-session gap COVERED `TestBanUserSessionKnownGap`. **TestBulkUntouched — the `/moderation/api/v1/bulk-action/` legacy JSON contract (which SURVIVES, do not delete the endpoint)**: COVERED outside the retiring module — `test_priority_service.py` bulk block asserts the exact `{"completed": 1, "errors": []}` happy shape (L970-973), per-id error shape, mixed-batch partial-failure contract, over-cap dedupe, `/api/v2/` → 404; `test_moderation_views.py::TestBulkModerationApproveOutcome` asserts the per-id refusal string; `test_admin_actions.py::TestBulkOperations/TestBulkLockingStructure` cover semantics+locking; `test_db_lock_timeout.py::TestBulkLockTimeout` (B1) covers the lock-timeout tier. No port required — recommendation: keep the explicit two-key exact-equality assert in `test_priority_service.py` (already present). Auth/method/rate/uniform-404 TRANSPORT.

#### `apps/moderation/tests/test_moderation_api_reads.py` (19 tests)

Staff gates COVERED `test_moderation_views.py::TestModerationStaffAccess` + `test_decorators.py::TestStaffRequired`. Queue priority filters + counts COVERED `test_priority_service.py::TestModerationQueueView::test_queue_filters_by_priority/test_queue_priority_all_default/test_queue_shows_priority_counts` + service `get_queued_ads` filter tests. Review localized names COVERED `test_moderation_views.py::test_review_renders_localized_category_name`; out-of-pair review 404 COVERED `::test_review_returns_404_for_non_moderation_status`. **PORT (one assert)**: queue ordering by `base_score` DESC (API asserted ids == [high, low]) — no retained service or HTML test asserts queue order, only membership/filtering. Destination: `test_priority_service.py` (e.g. new `TestModerationQueueView::test_queue_orders_by_base_score_desc` or a `TestPriorityService` ordering test). Envelope/shape/reverse TRANSPORT.

### 6. search

#### `apps/search/tests/test_search_api.py` (21 tests)

Narrowing / `all_categories` opt-out (incl. preserved filters + pagination) COVERED `test_search_view.py::TestSearchViewCategoryNarrowingSignal` + `TestSearchViewDescendantCategories` + `TestSearchViewCitySuggestion` (valid city filters results; invalid slug suggests). Cap/truncation COVERED `test_search_view.py::TestSearchViewTotalCount` (at-cap truncated, capped display) + `test_fts_service.py::TestCacheHitPathAndCapSemantics` + bounded-producer truncation. Warm/cold/stale/fallback cache paths COVERED `test_search_cache.py` (cold/warm/stale-while-revalidate, Redis-outage fallback to SQL) + `test_search_rank_page.py` (cold/warm identical order per page) + `test_search_view.py::TestSearchViewHasResultsMatchesRenderedRows`. Locale vectors COVERED `test_fts_service.py::TestLocaleParameterRespected` + `TestServiceDelegationEquivalence`. Analytics/history recorded once for HTML requests COVERED `test_autocomplete.py::TestSearchViewRecording` (user history + analytics event + popular) + `test_first_party_consent_basis.py` (real search view writes SearchHistory + AnalyticsEvent). 429 on the surviving HTML search surface COVERED `test_search_view.py::test_search_returns_429_after_threshold`. Error problem docs / envelope keys / reverse TRANSPORT. No ports.

### 7. users

#### `apps/users/tests/test_consent_api.py` (18 tests)

Accept/decline COVERED `test_consent.py::TestConsentAccept` (cookies incl. secure flag, `consent_given_at`, anonymous null-user audit row, accept-after-decline restores) + `TestConsentDecline` (browse-only, reversible, cookie, deleted-user refusal); withdraw COVERED `::test_withdraw_triggers_user_soft_delete` (PII nulled — `telegram_id is None` asserted) + `::test_withdraw_soft_deletes_ads` + `::test_withdraw_flushes_session_and_redirects` + `::test_consent_withdraw_idempotent_on_deleted_user` + `test_deletion.py` (withdrawal record, PII). Logout COVERED `test_logout.py` (405 on GET, session flush, redirect, workflow). 204/status conventions TRANSPORT. No ports.

### 8. apps/api machinery

`apps/api/tests/test_urls.py` (R02 inversion guard) and `test_import_rule.py` (import-boundary guard): pure API-surface machinery, no business invariants — DELETE with P4/P5 per D24. Coordination note: `test_import_rule.py` is the R-F2 pairing table consumed by `verify_parity` (plan §5 layer 5) and `docs/01-spec/api-surface.md`; P4 must update `verify_parity` + the doc together with the deletion or the parity command will fail (G4/G5 interface).

### 9. Mixed-file surgery

- `apps/ads/tests/test_copy_ad.py` — KEEP the original `TestCopyAd` 6 service tests (draft replacement, happy path, ownership, missing ad, positions, M2M). REMOVE the API-era additions: `TestCopyEndpoint`, `TestCopyEndpointV1` (11 tests), `_COPY_URL_NAME`, `_copy_post`, `_clear_rate_limit_cache`, `client_` fixture, and the now-unused API imports (`Client`, `reverse`, `PROBLEM_CONTENT_TYPE`, `RETRY_AFTER_HEADER`, `RateLimitBudget`, `AdStatus` if unused). **PORT first** (deletion blocker): publication-history reset on copy — new `TestCopyAd::test_copy_resets_publication_history` parametrized over PUBLISHED/ARCHIVED sources asserting the new DRAFT has `published_at/archived_at/rejected_at/moderation_failed_at/deleted_at` all None and the source row is untouched. (Draft invisibility of the copy to other users is covered by the detail/listings audience predicate after the §1 ports; ownership of the source covered by `test_copy_ad_non_owner_raises_permission_error`.)
- `apps/ads/tests/test_favorites.py` — KEEP unchanged (service additions `TestFavoritesQuerysetService` / `TestToggleFavoriteService` + HTML heart-form tests are the retained destinations).
- `apps/ads/tests/test_dashboard_stats.py` — KEEP unchanged (`TestAdsByStatusService` + `TestDashboardTimeRange` + `TestViewConsumesServiceGrouping` are the retained destinations).

### 10. CSRF on surviving write paths (task 5)

Repo-wide `Client(enforce_csrf_checks=True)` inventory (backend + telegram_bot): exactly ONE test — `apps/users/tests/test_logout.py::test_post_logout_without_csrf_returns_403`, on the surviving HTML `POST /logout/` route. No retiring module contains CSRF-enforced tests (the `/api/v1/` writes are CSRF-exempt JSON problem endpoints by design; their pipelines are transport). Surviving-write CSRF posture is otherwise pinned by: `test_favorites.py::test_heart_form_carries_csrf_header` (X-CSRFToken header on the heart form), `test_consent.py` require_POST coverage, `test_autocomplete_template.py::test_header_search_form_has_no_csrf_token` (GET form must not carry a token). B3 action: none to port — just do not delete `test_logout.py` (it is outside the retirement scope) and keep the heart-form header test with the favorites suite.

### 11. D28 — duplicate `page` parametrization (task 6)

`apps/ads/tests/test_listings_api.py::TestExhaustiveFilterSortPageMatrix::test_filter_sort_page_cross_product`: outer `@pytest.mark.parametrize("page", [1, 2, 3])` whose `page` argument is never referenced in the body (the body loops `for p in (1, 2, 3)` itself), producing 12 collected tests that each re-run the full three-page loop — 3× redundant execution and misleading collection counts. Fix when porting to `test_listings_query.py`: drop the outer `page` parametrize entirely; keep one test per `sort` value (4 collected tests), each running the three-page union/no-duplicates loop exactly once. Also fold the per-sort page-union assertion into the same loop (ads in exactly one page, union over pages 1-3 equals the full filtered set, no duplicates).

### 12. Deletion blocker list — invariants LOST today if the modules are deleted without porting (task 7)

1. HTML `GET /ads/<id>/` records exactly one `AD_VIEWED` analytics event with seller attribution; a missing-id GET records none — only in `test_ad_detail_api.py::TestSideEffectParity`. PORT → `test_detail_context.py::TestAdDetailViewEvent` (2 tests).
2. DRAFT / non-published ad detail returns 404 on the HTML surface — only `TestAudienceMatrix::test_unpublished_statuses_return_404`. PORT → `test_detail_context.py::TestAdDetailAudienceStatuses` (parametrized, 5 statuses).
3. `is_favorited` is True on HTML detail for a viewer who favorited the ad — only `TestFavoritesState::test_html_reports_true_when_favorited`. PORT → extend `test_detail_context.py::test_detail_context_contains_is_favorited_for_authenticated`.
4. Listings-surface query matrix: category-descendants subtree filter, unknown-category-no-filter, min/max normalized-EUR price bounds, synthetic withdrawn/deleted-seller audience rows, 3-page union/no-duplicates per sort — only `test_listings_api.py`. PORT → new `apps/ads/tests/test_listings_query.py` (5 tests, one per dimension; cross-product test with the D28 fix).
5. Search-history clear idempotency (Q8) and per-user scope on the HTML cabinet route — only `test_search_history_clear_api.py::TestClear`. PORT → `test_cabinet_sections.py::TestSearchHistorySection::test_clear_is_idempotent_and_scoped_to_the_owner`.
6. Moderation queue ordering by `base_score` descending — only `test_moderation_api_reads.py::TestQueueEnvelope::test_queue_items_order`. PORT → `test_priority_service.py` (1 test).
7. Copy re-creates a DRAFT with a fully reset publication history (source untouched) — only `test_copy_ad.py::TestCopyEndpoint::test_copy_published_ad_creates_new_draft` / `::test_copy_archived_ad_creates_new_draft`. PORT → `test_copy_ad.py::TestCopyAd::test_copy_resets_publication_history` (parametrized), then remove the API-era classes.

Everything else in the 20 retiring modules is either COVERED by a named retained test (majority — see tables) or TRANSPORT (JSON envelope / status-code / problem-doc / route-reverse / API↔HTML parity, including the entire dashboard, submit-route, consent, analytics, cities, categories-shape, and apps/api machinery modules). G8 impact: 301 retiring test functions; 7 blocked invariants → 10-12 new/extended retained tests; expected retained-suite delta ≈ +10-12 tests against −301 deleted, with zero unexplained invariant loss provided the 7 blockers land first.

## B3 task description

```yaml
id: b3_transfer_business_tests

title: >
  P3 — Transfer business tests: port the seven deletion-blocker invariants from
  the retiring API test modules into retained service/HTML suites (purely
  additively), land the two cheap LOW advisories, apply the D28 fix while
  porting the listings matrix, and defer every removal — including the
  test_copy_ad.py API-era classes — to B4.

# MEDIUM coverage-loss risk per the block table, but a hard prerequisite
# for B4: P4 may not delete any retiring module until every blocker below
# has a named passing test in a retained module.
priority: medium

type: implementation

depends_on:
  - b0_repair_edit_results
  - b1_restore_lifecycle_atomicity
  # Both landed (B3 audit verified at HEAD 716fe3e1: the post-B0 classes
  # TestApplyEditPayloadSubmitOutcomeMatrix / TestEditSubmissionRefusalsRender
  # and the post-B1 classes TestLifecycleOwnershipRefusalBelt /
  # TestLifecycleActionAtomicContinuity / TestLifecycleActionLockContinuity
  # are present and green).
  # NOTE: B3 does NOT wait on B2 (G0 consumer decision). The port is additive
  # and valid under either G0 outcome: if a real consumer is found and an
  # endpoint subset is retained, its API tests keep running next to the new
  # retained-suite tests; if G0 clears, B4 deletes the API modules with every
  # invariant already re-pinned. Only B4 consumes the B2 gate.

# ── Plan/Audit report source (REQUIRED — this task originates from the
#    architecture-correction plan and the B3 audit block) ──
source_reference: .ai/plans/architecture-correction-plan.md
source_section: "§6 — Coverage transfer ledger required before deletion · §7 P3 — Transfer business tests · §8 G8 — Coverage and measured feedback · §4 D26 (KEEP/RELOCATE), D27 (REMOVE with endpoint), D28 (SIMPLIFY page parametrization)"
source_file: .ai/plans/architecture-correction-execution.md
source_blocks:
  - "B3 audit findings"    # per-module COVERED/PORT/TRANSPORT ledger; §11 D28; §12 deletion-blocker list; §9 mixed-file surgery

extra_context: |
  The B3 audit walked all 20 retiring test modules (301 collected `def test_`
  functions) and classified every class: COVERED (a named retained test
  asserts it), PORT (asserted ONLY in the retiring module -> must land in B3),
  or TRANSPORT (JSON envelope / status-code / problem-doc / route-reverse /
  API-HTML parity bound to the dying endpoint — dies with the mirror and is
  not a product requirement). Exactly seven invariants are PORT (deletion
  blockers); everything else is COVERED or TRANSPORT. This task ports the
  seven blockers plus the two cheap LOW advisories, and NOTHING else.

  Test-input sourcing rule (audit charter): copy the concrete data shapes
  from the retiring API test modules (fixtures, prices, slugs, telegram_ids,
  row counts — inventor shapes are forbidden), but assert on HTML render
  context / service return values / ORM rows instead of JSON envelopes.

  Deletion blockers (destination of record from the audit ledger §12):
  1. HTML detail GET records exactly ONE `AD_VIEWED` analytics event with
     SELLER attribution (`user_id == ad.user_id`, never the viewer); a
     missing-id GET records none. Only
     `test_ad_detail_api.py::TestSideEffectParity` asserts it today; no
     retained test pins the detail-view side effect at all (single most
     at-risk invariant of the whole scope).
       -> NEW `test_detail_context.py::TestAdDetailViewEvent` (2 tests).
  2. DRAFT / non-published ad detail returns 404 on the HTML surface.
       -> NEW `test_detail_context.py::TestAdDetailAudienceStatuses`,
          parametrized over DRAFT / ON_MODERATION / REJECTED / DELETED /
          ON_MODERATION_FAILED (the ledger's five rows) PLUS ARCHIVED — the
          sixth row is what the retiring
          `TestAudienceMatrix::test_unpublished_statuses_return_404` itself
          asserted and no retained test covers it; a strict superset of the
          ledger, zero risk.
  3. `is_favorited` is True on HTML detail for a viewer who favorited the ad.
       -> EXTEND `test_detail_context.py::TestAdDetailContext::
          test_detail_context_contains_is_favorited_for_authenticated`
          (keep its False leg, add the True leg with a favoriting viewer).
  4. Listings-surface query matrix: category-descendants subtree, unknown-
     category-no-filter, min/max normalized-EUR price bounds, synthetic
     withdrawn/deleted-seller audience rows, 3-page union with no duplicates
     per sort.
       -> NEW `apps/ads/tests/test_listings_query.py` driving
          `ListingsQuery.build_queryset` (the single pipeline the retained
          HTML `listings()` and `search()` views share — D02 KEEP). The
          cross-product port carries the D28 fix: the retiring
          `test_filter_sort_page_cross_product` parametrizes an unused `page`
          argument (12 collected tests each re-running the full three-page
          loop); the port keeps ONE test per sort (4 collected), each looping
          pages 1-3 exactly once: union == full 25-id set, no duplicates.
  5. Search-history clear idempotency (Q8) + per-owner scope: re-POSTing the
     clear on an already-empty history succeeds and stays at 0 rows for the
     caller; another user's `SearchHistory` rows are untouched.
       -> NEW `test_cabinet_sections.py::TestSearchHistorySection::
          test_clear_is_idempotent_and_scoped_to_the_owner`.
  6. Moderation queue ordering by `base_score` DESC (triage order).
       -> NEW `test_priority_service.py::TestPriorityService::
          test_get_queued_ads_orders_by_base_score_desc` (service tier:
          `PriorityService.get_queued_ads` is the one ordering seam shared by
          the HTML queue and the retiring API queue read).
  7. Copy re-creates a DRAFT with a fully reset publication history while
     the source row (status AND its status timestamp) is untouched.
       -> NEW `test_copy_ad.py::TestCopyAd::
          test_copy_resets_publication_history` (parametrized
          PUBLISHED / ARCHIVED source).

  Non-blocker advisories (LOW) — both INCLUDED (cheap + justified):
  A. Saved-search read-leg scoping: after P4 nothing would assert that the
     cabinet saved-searches LIST renders only the caller's rows (today only
     implied by the write-leg 404s). One test reusing existing fixtures.
       -> NEW `test_cabinet_sections.py::TestSavedSearchesManagement::
          test_saved_searches_list_is_scoped_to_the_owner`.
  B. Header `root_categories` active-only + name-order: only the retiring
     `test_categories_api.py::test_json_tree_matches_header_root_categories`
     pins it; a regression (dropping `.filter(is_active=True)` or
     `.order_by("name")` in `apps.core.context_processors.header_context`)
     would be invisible to the whole retained suite. One test.
       -> NEW class in `apps/core/tests/test_header_child_queries.py`
          (same real-header render theme; the unit-marked
          test_context_processors.py mocks Category, so it is not a
          destination).

  DECISION — mixed-file surgery on test_copy_ad.py DEFERRED TO B4 (final;
  do not re-litigate or execute class removal in B3). The audit and the
  source-plan §6 retirement manifest both permit the removal inside B3;
  this task deliberately does NOT do it, making B3 purely additive (the D28
  fix deletes nothing at HEAD — `test_listings_api.py` is untouched; the
  defective outer parametrize simply is not carried into the port).
  Justification:
  (a) G0 is still undecided (B2 gate pending). The copy-endpoint classes
      include live protection for a still-mounted write route: 401/405
      method gate, 422 validation, 429 rate budget, uniform-404 ownership
      equivalence. Source plan §6: if a real consumer is found, its subset's
      "helpers, budgets, contract/security tests" must be KEPT — deleting
      them now risks a retained endpoint whose protection tests are already
      gone, the exact "deployable intermediate revision with live routes but
      missing protection" state §6 forbids.
  (b) §6 coherence rule: code deletion commits together with its affected
      route/docs changes. The class removal is the P4 retirement manifest's
      "Mixed-test surgery" row; B4 executes that manifest together with
      deleting `apps/ads/views/api/copy.py` and its `ads_api:copy` route, so
      B4 is the coherent deletion point.
  (c) B3's own gate is coverage transfer, not deletion; a purely additive
      diff is trivially reviewable and revertible.
  Consequence recorded for the B4 planner: the audit's "TestCopyEndpoint /
  TestCopyEndpointV1" names are the TestCopyEndpoint* family whose LIVE
  names at HEAD are `TestCopyEndpointPipeline` and `TestCopyEndpointHappyPath`
  (6 + 5 = 11 test functions), plus the helpers `_COPY_URL_NAME`,
  `_copy_post`, the autouse `_clear_rate_limit_cache` fixture, the `client_`
  fixture, and the API-only imports (prune with ruff F401 at execution time;
  `AdStatus` and `timezone` stay — `TestCopyAd` uses them). Until B4, the
  ported service test deliberately duplicates the publication-history
  assertions of `test_copy_published_ad_creates_new_draft` / the API happy
  path — expected, transitional duplication, resolved by B4's removal.

  STOP RULE (task charter): NO production code changes in B3. Every ported
  invariant was verified present on the RETAINED surface:
  - `apps/ads/views/listings.py::ad_detail` records
    `record_event(AnalyticsEventType.AD_VIEWED, user_id=ad.user_id, ad_id=ad.id)`
    and 404s via one `.get(id=ad_id, status=AdStatus.PUBLISHED)` under
    `account_state_q("user__")`;
  - its context sets
    `is_favorited = ad.favorites.filter(user_id=request.user.id).exists()`
    for authenticated viewers;
  - `ListingsQuery.build_queryset` carries the subtree (get_descendants
    include_self, unknown-slug pass), price (`price_normalized_eur` gte/lte),
    audience (`account_state_q("user__")`), and sort (`-id` tiebreakers per
    D02) dimensions;
  - `apps.cabinet.views.search_history.search_history_clear` clears
    `filter(user=request.user)` and redirect-succeeds on empty history;
  - `PriorityService.get_queued_ads` ends
    `.order_by("-moderation_priority__base_score", "-created_at")`;
  - `copy_service._build_ad_copy` constructs a fresh `Ad(...)` with
    `status=AdStatus.DRAFT` and never sets any publication-history timestamp.
  If a ported test FAILS because the retained HTML/service surface lacks a
  behavior the API had, STOP and report — do not fix production code here.

  PYTEST_OPTS semantics (verified against docker/entrypoint-test.sh, whose
  final line expands `${PYTEST_OPTS:-}` BEFORE the always-appended
  PYTEST_DEFAULTS): focused PYTEST_OPTS runs KEEP `--reuse-db -n auto
  --maxprocesses=4 --dist loadgroup`; only single tokens / bare file paths
  are safe (the value is word-split unquoted). The `.kilo/rules/commands.md`
  claim that PYTEST_OPTS "replaces the defaults" is stale (source-plan R06
  already flags it); do not correct it in B3 — command-doc fixes are P7.

description: >
  Transfer the business invariants that will lose their only coverage when P4
  deletes the retiring API test modules, into the retained service/HTML test
  suites, before any deletion happens: seven deletion-blocker ports plus two
  cheap LOW advisory ports across six test files (one new file, five
  additions to existing files, one existing test extended). All ports copy
  the retiring modules' concrete data shapes but assert on HTML render
  context, service return values, and ORM rows instead of JSON. The only
  defect fixed is D28, applied by NOT carrying the unused outer `page`
  parametrize into the ported cross-product test. Removals (the retiring
  API modules, and test_copy_ad.py's TestCopyEndpoint* family with its
  helpers) are explicitly deferred to B4/P4. No production file changes;
  any HTML-surface gap discovered by a port is a STOP-and-report condition,
  not something to fix here.

goals:
  - >
    Every one of the seven deletion-blocker invariants has a named, passing
    test in a retained module before B4 deletes any retiring module.
  - >
    Every port asserts on HTML context / service return values / ORM rows —
    never on a JSON envelope, status-code family, or problem document.
  - >
    The D28 defect does not survive the port — exactly 4 collected union
    tests (one per sort), each looping pages 1-3 once.
  - >
    The two LOW advisories (saved-search read-leg scoping, header
    root_categories active-only + name-order) land as one cheap test each.
  - >
    B3 is purely additive at HEAD — no retiring module, API-era class, or
    helper is deleted or modified; the CSRF posture
    (test_logout.py::test_post_logout_without_csrf_returns_403 and
    test_favorites.py::test_heart_form_carries_csrf_header) is untouched.
  - >
    Retained-suite delta is measurable for G8 — 16 new/extended functions,
    +25 collected tests (parametrized expansion), 0 removed.

# ─────────────────────────────────────────────────────────────────────────────
# Deletion-blocker map (source -> destination -> invariant -> seam -> failure)
# ─────────────────────────────────────────────────────────────────────────────

deletion_blocker_map:
  - blocker: 1  # detail AD_VIEWED side effect
    source: test_ad_detail_api.py::TestSideEffectParity (test_api_get_records_ad_viewed_like_html, test_404_does_not_record_event)
    destination: apps/ads/tests/test_detail_context.py::TestAdDetailViewEvent (NEW class, 2 tests)
    invariant: one successful HTML detail GET of a PUBLISHED ad records exactly one AnalyticsEvent with event_type=AD_VIEWED and user_id == the SELLER's id (ad.user_id, never the viewer); a missing-id GET records none
    seam: "Client().get(reverse('ads:detail', args=[ad.id])) — the retained production view apps/ads/views/listings.py::ad_detail; asserted via AnalyticsEvent ORM rows"
    data_shape: "existing published_ad fixture; missing id 999999 (retiring shape)"
    fails_when: the AD_VIEWED recording is dropped from the view, fires twice (e.g. an added HTMX partial re-render path), or is mis-attributed to the viewer — the last would corrupt seller statistics (analytics/services/seller_stats.py aggregates AD_VIEWED through the seller's ads), so the user_id assertion nails the seller not the anonymous viewer
  - blocker: 2  # non-published detail 404
    source: test_ad_detail_api.py::TestAudienceMatrix::test_unpublished_statuses_return_404 (+ the draft row of test_all_404_causes_share_identical_shape)
    destination: apps/ads/tests/test_detail_context.py::TestAdDetailAudienceStatuses (NEW class, 1 parametrized test)
    invariant: every non-PUBLISHED status answers 404 on the direct HTML detail URL — DRAFT, ON_MODERATION, REJECTED, DELETED, ON_MODERATION_FAILED, ARCHIVED (no existence leak on the retained route)
    seam: "Client().get(reverse('ads:detail', args=[ad.id])) — the .get(id=..., status=AdStatus.PUBLISHED) + account_state_q('user__') gate in ad_detail"
    data_shape: "create_test_ad(seller, category, city, status=<row>) per row (conftest sets the check-constraint timestamps)"
    fails_when: the visibility gate broadens — a draft, queued, rejected, archived, or deleted ad leaking through the direct URL is a privacy/existence leak; today only media-gate drafts and the consent/decline/ban account states are retained-covered, so this class is the ONLY guard over the status dimension
  - blocker: 3  # is_favorited True
    source: test_ad_detail_api.py::TestFavoritesState::test_logged_in_with_favorite_reads_true
    destination: apps/ads/tests/test_detail_context.py::TestAdDetailContext::test_detail_context_contains_is_favorited_for_authenticated (EXTEND the existing method)
    invariant: response.context['is_favorited'] is True for an authenticated viewer who favorited the ad (and stays False for a non-favoriting authenticated viewer — the existing leg)
    seam: "AdFavorite.objects.create(ad=published_ad, user=user); Client().force_login(user); response.context['is_favorited'] (view reads ad.favorites.filter(user_id=request.user.id).exists())"
    data_shape: "user fixture (900000002) as the favoriting viewer, distinct from the seller; same AdFavorite row shape the retiring module used"
    fails_when: the favorite context is computed against the wrong user id, dropped for authenticated viewers, or the heart state stops matching the favorites table
  - blocker: 4  # listings matrix -> service tier, with the D28 fix
    source: "test_listings_api.py::TestExhaustiveFilterSortPageMatrix (subtree, unknown-category, min/max price, cross-product) + TestAudienceParity (withdrawn/deleted synthetic rows)"
    destination: NEW apps/ads/tests/test_listings_query.py (4 classes, 8 methods, 11 collected)
    invariant: |
      Through the shared service pipeline:
      - category filter resolves the SUBTREE (parent + child + grandchild ads
        all match; a sibling-root control ad does not);
      - an unknown category slug applies NO filter (all seeded rows return);
      - min/max price bound on EUR-normalized price, inclusive at the bound
        (min_price=150 includes the 150-eur ads; max_price=150 excludes the
        300-eur ad; combined (100,200) -> the 150-eur ads only);
      - a PUBLISHED ad whose seller has ONLY consent_revoked_at set (no ban,
        decline, or delete — synthetic state the real withdrawal flow never
        leaves behind) is excluded by the base queryset, as is a seller with
        ONLY is_deleted=True;
      - for every sort, the union of pages 1-3 at per_page=10 equals the full
        25-ad set exactly once (page lengths 10/10/5) — the D02 -id
        tiebreakers keep every page boundary deterministic.
    seam: "ListingsQuery.build_queryset(ListingsQueryParams(...)) + django.core.paginator.Paginator(qs, 10) + paginator.get_page(p) — exactly the retained view's construction (views/listings.py::listings)"
    data_shape: "copied from the retiring module: matrix prices cheap=50/mid=150/expensive=300 in city, elsewhere=150 in other_city (City slug 'drugigrad', ME/Central); unknown slug 'does-not-exist'; subtree via Category.objects.create(parent=...); audience flips via seller.save(update_fields=[...]); 25 ads via create_test_ads_bulk"
    fails_when: the subtree resolution stops including descendants (or starts filtering on unknown slugs), the price operators flip at the bound, the account_state_q conjunct is dropped from the base queryset (leaking a withdrawn/deleted seller's inventory), or the loss of the -id tiebreaker lets a page boundary duplicate/drop a row — the union catches all three
    d28_fix: drop the retiring test's unused outer @pytest.mark.parametrize("page", [1, 2, 3]) entirely; keep @pytest.mark.parametrize over the four AdSort values ONLY; each collected test loops pages (1, 2, 3) once. Expect exactly 4 union ids in collection and 11 collected tests in the new file.
  - blocker: 5  # clear idempotent + scoped
    source: "test_search_history_clear_api.py::TestClear::test_repost_on_empty_is_idempotent + TestScopeParity::test_other_users_history_untouched"
    destination: apps/cabinet/tests/test_cabinet_sections.py::TestSearchHistorySection::test_clear_is_idempotent_and_scoped_to_the_owner (NEW method)
    invariant: the HTML clear POST is idempotent (a second POST on an already-empty history still succeeds and the caller's row count stays 0) and scoped (another user's SearchHistory rows survive my clear untouched)
    seam: "POST /cabinet/search-history/clear/ (retained apps.cabinet.views.search_history.search_history_clear — @login_required, SearchHistory.objects.filter(user=request.user).delete()); asserted on SearchHistory ORM rows"
    data_shape: "SearchHistory.objects.create(user=..., query=..., query_normalized=...) rows for buyer + make_user(940000501) — the retiring module's shapes and telegram_id"
    fails_when: the delete queryset loses its user filter (clearing everyone's history) or the second POST errors instead of staying a no-op success (e.g. a 405/500 on empty)
  - blocker: 6  # queue ordering
    source: test_moderation_api_reads.py::TestQueueEnvelope::test_ordering_by_base_score_desc
    destination: apps/moderation/tests/test_priority_service.py::TestPriorityService::test_get_queued_ads_orders_by_base_score_desc (NEW method)
    invariant: the moderation queue lists the highest base_score first (triage order)
    seam: "PriorityService().get_queued_ads() directly — the single ordering seam (.order_by('-moderation_priority__base_score', '-created_at')) used by both the HTML queue and the dying API read"
    data_shape: "the retiring _queue_ad shape: two ON_MODERATION ads (low created first, high second so insertion order opposes expected order), AdModerationPriority.objects.update_or_create(ad=..., defaults={'base_score': 10, 'priority_level': AdPriorityLevel.LOW.value}) and (99, HIGH); exact-equality assert on values_list('id')"
    fails_when: the ordering is dropped or reversed — the moderation queue would surface low-priority content first with no test failing at HEAD
  - blocker: 7  # copy resets publication history
    source: "test_copy_ad.py::TestCopyEndpointHappyPath::test_copy_published_ad_creates_new_draft (+ ::test_copy_archived_ad_creates_new_draft) — publication-history half only"
    destination: apps/ads/tests/test_copy_ad.py::TestCopyAd::test_copy_resets_publication_history (NEW method, parametrized [AdStatus.PUBLISHED, AdStatus.ARCHIVED])
    invariant: copy_ad creates a NEW DRAFT whose five publication-history timestamps (published_at, archived_at, rejected_at, moderation_failed_at, deleted_at) are all None, while the source row keeps its status and its status-specific timestamp
    seam: "apps.ads.services.copy_service.copy_ad(source.id, seller.id) directly (the bot-served seam), asserted on refreshed ORM rows"
    data_shape: "create_test_ad(status=PUBLISHED | ARCHIVED); usage note: the JSON payload outcome/fields of the retiring tests are TRANSPORT and are not ported"
    fails_when: copy starts carrying over publication history (a stale published_at would make the copy publish-clock-visible) or the copy mutates the source row

advisory_map:
  - advisory: A  # saved-search read-leg scoping
    destination: apps/cabinet/tests/test_cabinet_sections.py::TestSavedSearchesManagement::test_saved_searches_list_is_scoped_to_the_owner (NEW method)
    why_cheap: one GET + two content assertions, reusing buyer_client / SavedSearch.objects.create / make_user already imported in the file
    fails_when: the list queryset loses filter(user=request.user) — another user's search terms (PII) would render in my cabinet list, and no retained test would catch it today
  - advisory: B  # header root_categories content
    destination: apps/core/tests/test_header_child_queries.py::TestHeaderRootCategoriesContent (NEW class at end of file) ::test_root_categories_active_only_and_name_ordered
    why_cheap: three Category rows + one listings GET; reads response.context['root_categories'] — same real-header render the file already drives; apps/core is the owning app of header_context (categories/tests/test_categories_api.py::test_json_tree_matches_header_root_categories is the retiring parity test being replaced)
    fails_when: header_context drops .filter(is_active=True) (an inactive root appears for every anonymous visitor on every page) or .order_by('name') (roots render in encoding-dependent order)

# ─────────────────────────────────────────────────────────────────────────────
# Files and semantic targets (symbols only — never line numbers)
# ─────────────────────────────────────────────────────────────────────────────

files:

  # ── 1. Detail context: blockers 1, 2, 3 ─────────────────────────────────────
  - path: src/backend/apps/ads/tests/test_detail_context.py
    targets:
      - type: import_block
        name: module imports
        change: add `from apps.ads.models import AdFavorite`; add
          `from apps.analytics.models import AnalyticsEvent`; extend the
          existing `from apps.core.enums import AdStatus` with
          `AnalyticsEventType`
      - type: module_docstring
        name: test_detail_context module docstring
        change: add three "Covers:" bullets — AD_VIEWED side effect (one
          event, seller attribution, none on 404), non-PUBLISHED statuses 404
          on the HTML detail route, is_favorited True/False per viewer state
      - type: class
        name: TestAdDetailViewEvent          # NEW (blocker 1)
        action: add_code
        insert_after: TestAdDetailDeclinedUserVisibility (end of the class
          section, before the "Template-source tests" banner)
      - type: class
        name: TestAdDetailAudienceStatuses   # NEW (blocker 2)
        action: add_code
        insert_after: TestAdDetailViewEvent
      - type: test
        name: TestAdDetailContext::test_detail_context_contains_is_favorited_for_authenticated
        action: replace_method_body           # blocker 3: keep False leg, add True leg
        change: signature gains the `user` fixture; body keeps the existing
          seller-login False leg, then creates
          `AdFavorite.objects.create(ad=published_ad, user=user)`, logs in
          `user`, and asserts `response.context["is_favorited"] is True`;
          docstring updated to cover both legs
    keep_unchanged:
      - TestAdDetailContext (all other methods — bot_username, ad,
        breadcrumb_category, trust-score prefetch, display_features)
      - TestAdDetailDeclinedUserVisibility (both methods)
      - published_ad fixture definition
      - the template-source / breadcrumb module functions at the bottom

  # ── 2. NEW listings query file: blocker 4 (+ D28 fix) ─────────────────────
  - path: src/backend/apps/ads/tests/test_listings_query.py
    action: create_file                      # NEW module
    structure:
      - >
        Module docstring naming its origin (ports the business matrix of
        the retiring test_listings_api.py to the retained service seam) and
        the D28 note — one union test per sort, pages looped once.
      - "pytestmark = [pytest.mark.django_db, pytest.mark.integration]"
      - >
        Imports — pytest; django.core.paginator Paginator; django.utils
        timezone; apps.ads.services.listings_query (ListingsQuery,
        ListingsQueryParams); apps.categories.models Category;
        apps.core.enums (AdSort, AdStatus); apps.locations.models City;
        conftest (create_test_ad, create_test_ads_bulk).
      - >
        class TestListingsQueryCategoryFilter —
        test_category_filter_includes_descendant_subtree;
        test_unknown_category_slug_applies_no_filter.
      - >
        class TestListingsQueryPriceBounds — function-scoped fixture
        `price_matrix` mirroring the retiring matrix_fixture shape
        (other_city "drugigrad", cheap=50, mid=150, expensive=300 in the
        fixture city, elsewhere=150 in other_city); test_min_price_bound;
        test_max_price_bound; test_min_price_and_max_price_bounds_combined.
      - >
        class TestListingsQuerySellerAudienceStates —
        test_withdrawn_consent_seller_ad_is_hidden;
        test_deleted_seller_ad_is_hidden.
      - >
        class TestListingsQueryPageUnion —
        test_three_page_union_no_duplicates_per_sort, parametrized over
        [AdSort.DATE_NEW, AdSort.DATE_OLD, AdSort.PRICE_LOW,
        AdSort.PRICE_HIGH] ONLY — the D28 fix; NO outer page parametrize.
    expected_collection: >
      11 tests — 2 category + 3 price + 2 audience + 4 sort rows.

  # ── 3. Cabinet sections: blocker 5 + advisory A ────────────────────────────
  - path: src/backend/apps/cabinet/tests/test_cabinet_sections.py
    targets:
      - type: module_docstring
        name: test_cabinet_sections module docstring
        change: extend the "Covers" bullets — clear idempotency + owner
          scoping on the HTML route; saved-searches list scoping
      - type: test
        name: TestSearchHistorySection::test_clear_is_idempotent_and_scoped_to_the_owner  # NEW (blocker 5)
        action: add_method
        insert_after: TestSearchHistorySection::test_lists_and_clears_history
      - type: test
        name: TestSavedSearchesManagement::test_saved_searches_list_is_scoped_to_the_owner  # NEW (advisory A)
        action: add_method
        insert_after: TestSavedSearchesManagement::test_guest_cannot_manage_other_users_search
    keep_unchanged:
      - TestSavedSearchesManagement::test_create_disable_edit_delete_workflow
      - TestSavedSearchesManagement::test_guest_cannot_manage_other_users_search
      - TestSearchHistorySection::test_lists_and_clears_history
      - TestCabinetHub and the anonymous POST gate parametrization

  # ── 4. Priority service: blocker 6 ───────────────────────────────────────
  - path: src/backend/apps/moderation/tests/test_priority_service.py
    targets:
      - type: test
        name: TestPriorityService::test_get_queued_ads_orders_by_base_score_desc  # NEW (blocker 6)
        action: add_method
        insert_after: TestPriorityService (end of class; thematically
          grouped with the get_queued_ads tests)
      - type: module_docstring
        name: test_priority_service module docstring
        change: extend the PriorityService bullet to name the base_score
          DESC ordering coverage
    keep_unchanged:
      - every other TestPriorityService method (filtering, counts,
        calculate_and_save)
      - TestModerationQueueView, all bulk-action classes, locking and
        transaction tests

  # ── 5. Copy service tests: blocker 7 (surgery DEFERRED to B4) ─────────────
  - path: src/backend/apps/ads/tests/test_copy_ad.py
    targets:
      - type: test
        name: TestCopyAd::test_copy_resets_publication_history  # NEW (blocker 7)
        action: add_method
        insert_after: TestCopyAd::test_copy_ad_features_m2m_copied (end of
          class)
      - type: module_docstring
        name: test_copy_ad module docstring
        change: add one contract bullet — a copy resets every
          publication-history timestamp to None and leaves the source
          untouched
    keep_unchanged:
      - the ORIGINAL TestCopyAd service tests (draft replacement, happy
        path, ownership PermissionError, missing-ad DoesNotExist,
        positions, M2M)
      # B3 deliberately ALSO keeps, byte-identical:
      - TestCopyEndpointPipeline and TestCopyEndpointHappyPath (the live
        audit names for the "TestCopyEndpoint*" family)
      - _COPY_URL_NAME, _copy_post, the autouse _clear_rate_limit_cache
        fixture, the client_ fixture, and every API import
      # Removal of the above is the P4 retirement-manifest "Mixed-test
      # surgery" row — it executes in B4 together with
      # apps/ads/views/api/copy.py and its route, NOT in B3 (see DECISION in
      # extra_context).

  # ── 6. Header child queries file: advisory B ───────────────────────────────
  - path: src/backend/apps/core/tests/test_header_child_queries.py
    targets:
      - type: class
        name: TestHeaderRootCategoriesContent   # NEW (advisory B)
        action: add_code
        placement: end of file
      - type: module_docstring
        name: test_header_child_queries module docstring
        change: append one sentence noting the file now also pins the
          root_categories CONTENT contract (active-only, name-ordered),
          ported from the retiring categories API parity test in block B3
    keep_unchanged:
      - TestHeaderChildExistenceQueryCount (both query-count tests and the
        _make_roots / _child_existence_queries helpers)

# ─────────────────────────────────────────────────────────────────────────────
# Changes with code hints (target-destination skeletons; implement against
# the live code and the retirement-source data shapes quoted above)
# ─────────────────────────────────────────────────────────────────────────────

changes:

  - action: add_test_class
    target: apps/ads/tests/test_detail_context.py::TestAdDetailViewEvent
    description: >
      The HTML detail-GET side effect, previously asserted only through the
      dying JSON mirror. Reuses the published_ad fixture.
    code_hint: |
      class TestAdDetailViewEvent:
          """A successful HTML detail GET records exactly one AD_VIEWED with
          seller attribution; a missing-id GET records none."""

          def test_detail_get_records_exactly_one_ad_viewed_with_seller_attribution(
              self, published_ad, seller
          ) -> None:
              response = Client().get(reverse("ads:detail", args=[published_ad.id]))
              assert response.status_code == 200

              events = AnalyticsEvent.objects.filter(
                  event_type=AnalyticsEventType.AD_VIEWED,
                  ad_id=published_ad.id,
              )
              assert events.count() == 1
              # Seller attribution — the view records ad.user_id, not the viewer.
              assert events.get().user_id == seller.id

          def test_missing_ad_detail_get_records_no_ad_viewed_event(self) -> None:
              before = AnalyticsEvent.objects.filter(
                  event_type=AnalyticsEventType.AD_VIEWED
              ).count()

              response = Client().get(reverse("ads:detail", args=[999999]))

              assert response.status_code == 404
              assert (
                  AnalyticsEvent.objects.filter(
                      event_type=AnalyticsEventType.AD_VIEWED
                  ).count()
                  == before
              )

  - action: add_test_class
    target: apps/ads/tests/test_detail_context.py::TestAdDetailAudienceStatuses
    description: >
      Non-PUBLISHED detail 404s on the retained HTML route. Six rows: the
      ledger's five plus ARCHIVED (which the retiring test itself asserted).
      conftest's create_test_ad supplies the check-constraint timestamps.
    code_hint: |
      class TestAdDetailAudienceStatuses:
          """Every non-PUBLISHED status answers 404 on the HTML detail route."""

          @pytest.mark.parametrize(
              "status",
              [
                  AdStatus.DRAFT,
                  AdStatus.ON_MODERATION,
                  AdStatus.REJECTED,
                  AdStatus.DELETED,
                  AdStatus.ON_MODERATION_FAILED,
                  AdStatus.ARCHIVED,
              ],
          )
          def test_non_published_status_returns_404_on_detail(
              self, seller, category, city, status
          ) -> None:
              ad = create_test_ad(seller, category, city, status=status)
              response = Client().get(reverse("ads:detail", args=[ad.id]))
              assert response.status_code == 404

  - action: modify_code
    target: apps/ads/tests/test_detail_context.py::TestAdDetailContext::test_detail_context_contains_is_favorited_for_authenticated
    description: >
      Keep the existing False leg byte-for-byte, then add the True leg with
      a favoriting viewer (a distinct user, not the owner). Update the
      docstring to describe both legs.
    code_hint: |
      def test_detail_context_contains_is_favorited_for_authenticated(
          self, published_ad, seller, user, category, city
      ) -> None:
          """is_favorited mirrors the viewer: False when the authenticated
          viewer has not favorited the ad, True when they have."""
          client = Client()
          client.force_login(seller)
          response = client.get(reverse("ads:detail", args=[published_ad.id]))
          assert response.status_code == 200
          assert response.context["is_favorited"] is False

          AdFavorite.objects.create(ad=published_ad, user=user)
          client = Client()
          client.force_login(user)
          response = client.get(reverse("ads:detail", args=[published_ad.id]))
          assert response.status_code == 200
          assert response.context["is_favorited"] is True

  - action: create_file
    target: apps/ads/tests/test_listings_query.py
    description: >
      Service-tier home for the retiring listings matrix. Every test drives
      ListingsQuery.build_queryset directly — the same pipeline the retained
      HTML listings()/search() views call — and asserts on queryset id sets,
      never on a JSON envelope. Data shapes copied from test_listings_api.py.
    code_hint: |
      class TestListingsQueryCategoryFilter:
          def test_category_filter_includes_descendant_subtree(
              self, seller, category, city
          ) -> None:
              child = Category.objects.create(
                  name="Child", slug="listings-child-leaf", parent=category
              )
              grandchild = Category.objects.create(
                  name="Grandchild", slug="listings-grandchild-leaf", parent=child
              )
              control_root = Category.objects.create(
                  name="Control Root", slug="listings-control-root"
              )
              mine = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
              in_child = create_test_ad(seller, child, city, status=AdStatus.PUBLISHED)
              in_grandchild = create_test_ad(
                  seller, grandchild, city, status=AdStatus.PUBLISHED
              )
              outside = create_test_ad(
                  seller, control_root, city, status=AdStatus.PUBLISHED
              )

              ads = ListingsQuery.build_queryset(
                  ListingsQueryParams(category_slug=category.slug)
              )

              assert set(ads.values_list("id", flat=True)) == {
                  mine.id, in_child.id, in_grandchild.id,
              }
              assert outside.id not in set(ads.values_list("id", flat=True))

          def test_unknown_category_slug_applies_no_filter(
              self, seller, category, city
          ) -> None:
              # The DoesNotExist branch applies no filter (retiring shape:
              # slug "does-not-exist", all seeded rows returned).
              seeded = {
                  create_test_ad(seller, category, city, status=AdStatus.PUBLISHED).id
                  for _ in range(2)
              }
              ads = ListingsQuery.build_queryset(
                  ListingsQueryParams(category_slug="does-not-exist")
              )
              assert seeded <= set(ads.values_list("id", flat=True))

      class TestListingsQueryPriceBounds:
          @pytest.fixture
          def price_matrix(self, seller, category, city):
              other_city = City.objects.create(
                  country_code="ME", name="Другиград",
                  region="Central", slug="drugigrad",
              )
              cheap = create_test_ad(seller, category, city, title="Cheap", price=50, status=AdStatus.PUBLISHED)
              mid = create_test_ad(seller, category, city, title="Mid", price=150, status=AdStatus.PUBLISHED)
              expensive = create_test_ad(seller, category, city, title="Expensive", price=300, status=AdStatus.PUBLISHED)
              elsewhere = create_test_ad(seller, category, other_city, title="Elsewhere", price=150, status=AdStatus.PUBLISHED)
              return {"cheap": cheap, "mid": mid, "expensive": expensive, "elsewhere": elsewhere}

          def _ids(self, **params) -> set[int]:
              qs = ListingsQuery.build_queryset(ListingsQueryParams(**params))
              return set(qs.values_list("id", flat=True))

          def test_min_price_bound(self, price_matrix) -> None:
              ids = self._ids(min_price=150)
              assert ids == {price_matrix[k].id for k in ("mid", "expensive", "elsewhere")}
              assert price_matrix["cheap"].id not in ids

          def test_max_price_bound(self, price_matrix) -> None:
              ids = self._ids(max_price=150)
              assert ids == {price_matrix[k].id for k in ("cheap", "mid", "elsewhere")}
              assert price_matrix["expensive"].id not in ids

          def test_min_price_and_max_price_bounds_combined(self, price_matrix) -> None:
              ids = self._ids(min_price=100, max_price=200)
              assert ids == {price_matrix[k].id for k in ("mid", "elsewhere")}

      class TestListingsQuerySellerAudienceStates:
          def _visible(self, ad) -> bool:
              return ListingsQuery.build_queryset(ListingsQueryParams()).filter(
                  pk=ad.pk
              ).exists()

          def test_withdrawn_consent_seller_ad_is_hidden(self, seller, category, city) -> None:
              ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
              assert self._visible(ad)  # sanity: visible before the flip
              # Synthetic audience state: ONLY consent_revoked_at is set; the
              # ad stays PUBLISHED and the seller is not banned/declined/deleted.
              seller.consent_revoked_at = timezone.now()
              seller.save(update_fields=["consent_revoked_at"])
              assert not self._visible(ad)
              seller.consent_revoked_at = None
              seller.save(update_fields=["consent_revoked_at"])
              assert self._visible(ad)  # isolated conjunct: restore

          def test_deleted_seller_ad_is_hidden(self, seller, category, city) -> None:
              ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
              assert self._visible(ad)
              # Synthetic state: ONLY is_deleted=True.
              seller.is_deleted = True
              seller.save(update_fields=["is_deleted"])
              assert not self._visible(ad)
              seller.is_deleted = False
              seller.save(update_fields=["is_deleted"])
              assert self._visible(ad)

      class TestListingsQueryPageUnion:
          @pytest.mark.parametrize(
              "sort",
              [AdSort.DATE_NEW, AdSort.DATE_OLD, AdSort.PRICE_LOW, AdSort.PRICE_HIGH],
          )
          # D28 fix: the retiring test ALSO had an unused outer
          # @pytest.mark.parametrize("page", [1, 2, 3]). It is NOT carried
          # over: one collected test per sort, each looping pages 1-3 once.
          def test_three_page_union_no_duplicates_per_sort(
              self, seller, category, city, sort
          ) -> None:
              ads = create_test_ads_bulk(seller, category, city, 25, status=AdStatus.PUBLISHED)
              all_ids = {a.id for a in ads}

              # Same pagination construction the retained view uses:
              # Paginator(ads, params.per_page) + get_page(page).
              qs = ListingsQuery.build_queryset(ListingsQueryParams(sort=sort))
              paginator = Paginator(qs, 10)
              assert paginator.count == 25

              seen: list[int] = []
              for p in (1, 2, 3):
                  page = paginator.get_page(p)
                  # 25 ads at 10/page -> pages hold 10, 10, 5.
                  assert len(page.object_list) == (5 if p == 3 else 10)
                  seen.extend(a.id for a in page.object_list)

              assert len(seen) == len(set(seen)) == 25
              assert set(seen) == all_ids

  - action: add_test_method
    target: apps/cabinet/tests/test_cabinet_sections.py::TestSearchHistorySection::test_clear_is_idempotent_and_scoped_to_the_owner
    description: >
      Idempotency + owner scope on the retained HTML clear route; assert on
      DB rows, not the dying JSON body ({"cleared": ..., "remaining": ...} is
      TRANSPORT).
    code_hint: |
      def test_clear_is_idempotent_and_scoped_to_the_owner(
          self, buyer_client: Client, buyer: User
      ) -> None:
          """Re-clearing an empty history succeeds; other users keep theirs."""
          other = make_user(940000501)
          SearchHistory.objects.create(
              user=buyer, query="мой", query_normalized="мой"
          )
          SearchHistory.objects.create(
              user=other, query="чужой", query_normalized="чужой"
          )

          first = buyer_client.post("/cabinet/search-history/clear/")
          assert first.status_code == 302
          assert SearchHistory.objects.filter(user=buyer).count() == 0

          # Q8 idempotency: a second POST on the already-empty history stays
          # a successful no-op, and the other user's rows are untouched.
          second = buyer_client.post("/cabinet/search-history/clear/")
          assert second.status_code == 302
          assert SearchHistory.objects.filter(user=buyer).count() == 0
          assert SearchHistory.objects.filter(user=other).count() == 1

  - action: add_test_method
    target: apps/cabinet/tests/test_cabinet_sections.py::TestSavedSearchesManagement::test_saved_searches_list_is_scoped_to_the_owner
    description: >
      Read-leg scoping of the retained list view (advisory A): another
      user's saved-search query must not render in my cabinet list. Reuses
      the write-leg test's SavedSearch/make_user shapes.
    code_hint: |
      def test_saved_searches_list_is_scoped_to_the_owner(
          self, buyer_client: Client, buyer: User
      ) -> None:
          other = make_user(940000502)
          SavedSearch.objects.create(user=buyer, query="велосипед")
          SavedSearch.objects.create(user=other, query="чужой")

          resp = buyer_client.get("/cabinet/saved-searches/")

          assert resp.status_code == 200
          assert "велосипед" in resp.content.decode()
          assert "чужой" not in resp.content.decode()
          assert SavedSearch.objects.filter(user=other).count() == 1

  - action: add_test_method
    target: apps/moderation/tests/test_priority_service.py::TestPriorityService::test_get_queued_ads_orders_by_base_score_desc
    description: >
      Triage ordering at the single shared seam. Exact-equality assert (ids
      == [high.id, low.id]) also pins membership and exclusion of non-queue
      ads within the test's transaction.
    code_hint: |
      def test_get_queued_ads_orders_by_base_score_desc(self, category, city) -> None:
          """get_queued_ads lists the highest base_score first (triage order)."""
          user = make_user(990030010)
          # Created low-first so insertion order opposes the expected output,
          # proving the ordering comes from base_score DESC.
          low = create_test_ad(user, category, city, title="Low", status=AdStatus.ON_MODERATION)
          high = create_test_ad(user, category, city, title="High", status=AdStatus.ON_MODERATION)
          AdModerationPriority.objects.update_or_create(
              ad=low,
              defaults={"base_score": 10, "priority_level": AdPriorityLevel.LOW.value},
          )
          AdModerationPriority.objects.update_or_create(
              ad=high,
              defaults={"base_score": 99, "priority_level": AdPriorityLevel.HIGH.value},
          )

          ids = list(
              PriorityService().get_queued_ads().values_list("id", flat=True)
          )

          assert ids == [high.id, low.id]

  - action: add_test_method
    target: apps/ads/tests/test_copy_ad.py::TestCopyAd::test_copy_resets_publication_history
    description: >
      Service-tier port of the publication-history half of the retiring
      copy-endpoint happy path. Parametrized over the two source statuses
      the endpoint tests asserted. The copy's five publication-history
      timestamps are all None; the source keeps status + its status
      timestamp. Everything else in the file stays untouched (B4 removes the
      endpoint classes).
    code_hint: |
      @pytest.mark.parametrize(
          "source_status", [AdStatus.PUBLISHED, AdStatus.ARCHIVED]
      )
      def test_copy_resets_publication_history(
          self, seller, category, city, source_status
      ) -> None:
          """The new DRAFT carries no publication history; source untouched."""
          source = create_test_ad(seller, category, city, status=source_status)

          new_ad = copy_ad(source.id, seller.id)
          new_ad.refresh_from_db()

          assert new_ad.pk != source.pk
          assert new_ad.status == AdStatus.DRAFT
          for field in (
              "published_at", "archived_at", "rejected_at",
              "moderation_failed_at", "deleted_at",
          ):
              assert getattr(new_ad, field) is None

          source.refresh_from_db()
          assert source.status == source_status
          status_timestamp = {
              AdStatus.PUBLISHED: "published_at",
              AdStatus.ARCHIVED: "archived_at",
          }[source_status]
          assert getattr(source, status_timestamp) is not None

  - action: add_test_class
    target: apps/core/tests/test_header_child_queries.py::TestHeaderRootCategoriesContent
    description: >
      Advisory B: the content contract of header_context's root_categories —
      active-only and name-ordered — previously pinned only by the retiring
      categories API parity test. Renders the real header like the sibling
      query-count tests.
    code_hint: |
      class TestHeaderRootCategoriesContent:
          """root_categories renders active roots only, in name order."""

          def test_root_categories_active_only_and_name_ordered(self) -> None:
              Category.objects.create(name="Beta Root", slug="hdr-beta-root")
              Category.objects.create(name="Alpha Root", slug="hdr-alpha-root")
              Category.objects.create(
                  name="Retired Root", slug="hdr-retired-root", is_active=False
              )

              response = Client().get(reverse("ads:listings"))

              assert response.status_code == 200
              roots = response.context["root_categories"]
              assert [c.slug for c in roots] == ["hdr-alpha-root", "hdr-beta-root"]

# ─────────────────────────────────────────────────────────────────────────────
# Implementation sequence (one direction of travel; steps 1-6 may run in any
# order, step 7+ verify the completed set)
# ─────────────────────────────────────────────────────────────────────────────

implementation_sequence:
  - step: 1
    action: >
      test_detail_context.py — extend the import block and module docstring;
      add TestAdDetailViewEvent after TestAdDetailDeclinedUserVisibility;
      add TestAdDetailAudienceStatuses after it; extend
      test_detail_context_contains_is_favorited_for_authenticated with the
      True leg (blockers 1-3).
  - step: 2
    action: >
      Create apps/ads/tests/test_listings_query.py with the four classes
      (blocker 4 + D28 fix). No outer page parametrize anywhere in the file.
  - step: 3
    action: >
      test_cabinet_sections.py — add
      TestSearchHistorySection::test_clear_is_idempotent_and_scoped_to_the_owner
      and TestSavedSearchesManagement::test_saved_searches_list_is_scoped_to_the_owner
      (blocker 5 + advisory A); extend the module docstring.
  - step: 4
    action: >
      test_priority_service.py — add
      TestPriorityService::test_get_queued_ads_orders_by_base_score_desc
      (blocker 6); extend the module docstring bullet.
  - step: 5
    action: >
      test_copy_ad.py — add
      TestCopyAd::test_copy_resets_publication_history (blocker 7); extend
      the module docstring bullet. TOUCH NOTHING ELSE in this file — the
      TestCopyEndpoint* family and its helpers remain byte-identical for
      B4 to remove with the endpoint.
  - step: 6
    action: >
      test_header_child_queries.py — append TestHeaderRootCategoriesContent
      and one docstring sentence (advisory B).
  - step: 7
    action: >
      Run the focused Docker suite (verification command V1). If any new
      test fails because the retained surface lacks the behavior it pins,
      STOP and report (STOP RULE) — do not modify production code, do not
      weaken an assertion to pass, and do not delete the failing test.
  - step: 8
    action: >
      ruff check (auto-fix only import sorting) and basedpyright on the six
      touched files; then the D28 collection check (V2); then the fast gate
      (V3); finally the git hygiene checks (V4).
  - step: 9
    action: >
      Record the G8 measurement note in the task completion report: files
      touched, +25 collected / 16 new-or-extended functions, focused-run and
      fast-gate elapsed times, and the one decision deviation from the audit
      (copy-endpoint class removal deferred to B4, plus the ARCHIVED sixth
      status row) so P8 can reconcile the ledger.

# ─────────────────────────────────────────────────────────────────────────────
# Verification (Docker test service — never local `uv run pytest`)
# ─────────────────────────────────────────────────────────────────────────────

verification:
  v0_setup: |
    # Inspect/start the test DB once per session (--env-file is required).
    docker ps --filter "name=mko-bazuna-test-db-"
    docker compose --project-name mko-bazuna-test --env-file .env.test `
      -f docker-compose.yml -f docker-compose.test.yml up -d db
  v1_focused: |
    # Focused run of the six touched suites. NB (verified in
    # docker/entrypoint-test.sh): PYTEST_OPTS is expanded BEFORE the fixed
    # PYTEST_DEFAULTS, so --reuse-db/-n auto/--dist loadgroup are RETAINED;
    # only single tokens / bare file paths are safe (unquoted word-split).
    docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm -e "PYTEST_OPTS=src/backend/apps/ads/tests/test_detail_context.py src/backend/apps/ads/tests/test_listings_query.py src/backend/apps/ads/tests/test_copy_ad.py src/backend/apps/cabinet/tests/test_cabinet_sections.py src/backend/apps/moderation/tests/test_priority_service.py src/backend/apps/core/tests/test_header_child_queries.py --tb=short" test
  v2_d28_collection: |
    # D28 proof: the new file must collect exactly 11 tests, and the union
    # test exactly one id per sort (4) — no outer page parametrize.
    docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm -e "PYTEST_OPTS=src/backend/apps/ads/tests/test_listings_query.py --collect-only -q" test
  v3_statics_and_gate: |
    # Statics on the touched files, then the canonical fast gate (PR tier).
    uv run ruff check src/backend/apps/ads/tests/test_detail_context.py src/backend/apps/ads/tests/test_listings_query.py src/backend/apps/ads/tests/test_copy_ad.py src/backend/apps/cabinet/tests/test_cabinet_sections.py src/backend/apps/moderation/tests/test_priority_service.py src/backend/apps/core/tests/test_header_child_queries.py
    uv run basedpyright src/backend/apps/ads/tests/test_detail_context.py src/backend/apps/ads/tests/test_listings_query.py src/backend/apps/ads/tests/test_copy_ad.py src/backend/apps/cabinet/tests/test_cabinet_sections.py src/backend/apps/moderation/tests/test_priority_service.py src/backend/apps/core/tests/test_header_child_queries.py
    .\Makefile.ps1 test
  v4_hygiene: |
    # Test-only change set: no schema delta is possible, so no
    # makemigrations --check is required. Confirm only the six files moved.
    git status --short
    git diff --check
    git diff --stat

# ─────────────────────────────────────────────────────────────────────────────
# Acceptance criteria (B3 is complete when ALL hold)
# ─────────────────────────────────────────────────────────────────────────────

acceptance_criteria:
  - >
    BLOCKER MAP COMPLETE: every blocker invariant has a named passing test in
    a retained module — (1) TestAdDetailViewEvent's two tests; (2)
    TestAdDetailAudienceStatuses::test_non_published_status_returns_404_on_detail;
    (3) the extended
    test_detail_context_contains_is_favorited_for_authenticated; (4)
    test_listings_query.py's TestListingsQueryCategoryFilter (2),
    TestListingsQueryPriceBounds (3), TestListingsQuerySellerAudienceStates
    (2), TestListingsQueryPageUnion (4 collected); (5)
    TestSearchHistorySection::test_clear_is_idempotent_and_scoped_to_the_owner;
    (6) TestPriorityService::test_get_queued_ads_orders_by_base_score_desc;
    (7) TestCopyAd::test_copy_resets_publication_history.
  - >
    All new/extended tests pass in V1 (focused run) and the fast gate (V3)
    is green; the two existing CSRF anchors still pass untouched
    (users/tests/test_logout.py::test_post_logout_without_csrf_returns_403,
    ads/tests/test_favorites.py::test_heart_form_carries_csrf_header).
  - >
    D28 not propagated: `--collect-only` on test_listings_query.py shows
    exactly 11 tests with exactly 4 union ids (one per AdSort,
    test_three_page_union_no_duplicates_per_sort); no test in the new file
    parametrizes an unused `page`.
  - >
    PURELY ADDITIVE at HEAD: `git status --short` lists exactly the six test
    files (one new); every retiring API test module is byte-identical; in
    test_copy_ad.py the TestCopyEndpoint* classes and every helper
    (_COPY_URL_NAME, _copy_post, _clear_rate_limit_cache, client_) are
    byte-identical; test_favorites.py and test_dashboard_stats.py untouched
    (audit §9 KEEP).
  - >
    No production file changed: no file under src/backend outside
    apps/*/tests/ is modified; no migration, settings, pyproject, or
    lockfile delta (V4 proves it).
  - >
    Assertions honor the sourcing rule: data shapes copied from the retiring
    modules (prices 50/150/300, "drugigrad", "does-not-exist", 25 ads at 10
    per page, telegram_id 940000501/990030010 patterns); all assertions
    target HTML context, service return values, or ORM rows — grep the six
    files for `response.json()`/`PROBLEM_CONTENT_TYPE`/`RETRY_AFTER_HEADER`
    finds nothing.
  - >
    G8 note recorded (step 9): +25 collected tests / 16 new-or-extended
    functions against 0 removed at HEAD, focused+gate timings, and the two
    ledger deltas (copy surgery deferred to B4; ARCHIVED sixth status row)
    handed to the B4/P8 planners.
  - >
    ruff and basedpyright clean on all six touched files (V3).

# ─────────────────────────────────────────────────────────────────────────────
# Out of scope
# ─────────────────────────────────────────────────────────────────────────────

out_of_scope:
  - >
    ANY deletion: the 20 retiring API test modules stay byte-identical
    (P4/B4); test_copy_ad.py's TestCopyEndpoint* family / helpers / API
    imports stay (P4 mixed-file surgery, executed in B4 with the copy
    endpoint's own deletion); apps/api machinery (test_urls.py,
    test_import_rule.py, verify_parity) untouched (P4/P5).
  - >
    Production code of any kind. If a ported test reveals that the HTML or
    service surface lacks a behavior the API had (i.e. the port cannot pass
    without a view/service change), STOP and report — changing production
    code is a new task, never a test-transfer side effect.
  - >
    TRANSPORT rows are intentionally NOT ported: JSON envelope keys, RFC 9457
    problem shapes, 401/405/429 matrixes, route-reverse smokes, and
    API-HTML parity classes of the retiring modules (audit verdict TRANSPORT
    for each). Coverage already-COVERED rows (city/purpose/condition/features
    filters, sorts, favorites counts, submission outcomes, consent gates,
    bulk-action JSON contract, etc.) are not re-ported either.
  - >
    Docs (P7/B7): no api-surface.md, README, commands.md, or 99-agent doc
    changes — including NOT "fixing" the stale PYTEST_OPTS claim in
    .kilo/rules/commands.md (flag it in the completion report instead).
  - >
    i18n catalogs: no .po/.mo changes (no new user-visible strings; test
    docstrings are English per rule 1; the fast gate's i18n completeness test
    must stay green).
  - >
    Any schema/model/migration, settings/env/middleware, dependency, or
    lockfile change; any marker/tier/entrypoint change; any bot test change.
  - >
    P6 service simplifications (lifecycle single-op convention, dashboard
    gates) and any rename of retained modules.

# ─────────────────────────────────────────────────────────────────────────────
# Risks
# ─────────────────────────────────────────────────────────────────────────────

risks:
  - risk: >
      Modification of an existing green test (blocker 3 extends
      test_detail_context_contains_is_favorited_for_authenticated). If the
      True leg fails, the AdFavorite relation or the context computation
      regressed — do not loosen the assertion; investigate; note that the
      view reads `ad.favorites.filter(user_id=request.user.id).exists()`
      and the retiring module created favorites with
      `AdFavorite.objects.create(ad=ad, user=user)`, so the port's shape is
      verified.
    mitigation: land blocker 3 in the same session as the new classes so the
      focused run (V1) isolates any failure to a single file; the False leg
      must keep passing unchanged.
  - risk: >
      The union test depends on the D02 `-id` tiebreakers for deterministic
      page boundaries. Bulk-created rows share (nearly) identical
      published_at values, so a lost tiebreaker WOULD produce duplicates or
      gaps across the 3 pages — that is precisely the regression this test
      exists to catch, not flakiness.
    mitigation: none needed — it is a deterministic single-threaded
      assertion over a fully ordered queryset; do not add tolerance for
      duplicate ids.
  - risk: >
      Duplicate coverage between the new copy service test and the still-
      live endpoint tests (both assert the publication-history reset) looks
      like redundancy to a reviewer and may tempt an in-scope removal.
    mitigation: this duplication is deliberate and transitional until B4;
      the task text and commit body say so explicitly; no B3 reviewer may
      delete the endpoint classes.
  - risk: >
      The audience-state ports use synthetic User flag combinations
      (consent_revoked_at-only; is_deleted-only) that the real withdrawal
      flow never leaves behind, so a future reader might call them artificial
      and delete them.
    mitigation: the audit already pins the justification — the
      `account_state_q` conjuncts are individually load-bearing
      (users/tests/test_account_state.py::TestPredicateConjunctIsLoadBearing)
      and no retained test wires these two states into the listings
      queryset; docstrings in the new tests restate it.
  - risk: >
      ON_MODERATION rows (blocker 6, plus one audience-status row in
      blocker 2) trigger the moderation post_save signal, creating
      AdModerationPriority rows.
    mitigation: harmless for both tests — blocker 2 asserts only the detail
      404; blocker 6's update_or_create upserts the signal-created row (the
      same pattern the retiring _queue_ad and the existing calculate_and_save
      tests use).
  - risk: >
      Collection-count drift (e.g. accidentally re-adding a page parametrize
      or splitting tests) would silently weaken the G8 delta measurement.
    mitigation: V2 pins the expected count (11) and the 4 union ids in CI
      verifiable form.

commit:
  message: >
    test(ads): transfer retirable API business invariants to retained suites
  scope_note: >
    Files span ads (3: test_detail_context.py, NEW test_listings_query.py,
    test_copy_ad.py), cabinet (1), moderation (1), core (1). Dominant scope
    is ads — 4 of the 7 deletion-blocker homes and the only new file — so a
    single `test(ads)` scope is used per the charter's dominant-scope rule;
    the cabinet/moderation/core additions are enumerated in the body.
  body: >
    Port the seven deletion-blocker invariants out of the retiring API test
    modules into retained service/HTML suites, before B4 retires the
    endpoints (B3 audit, plan §6 ledger / §7 P3): detail AD_VIEWED side
    effect with seller attribution + 404-no-event; non-PUBLISHED detail 404
    parametrized over six statuses; is_favorited True leg on HTML detail;
    new test_listings_query.py driving ListingsQuery.build_queryset
    (category subtree, unknown-slug no-filter, EUR price bounds, synthetic
    withdrawn/deleted-seller rows, 3-page union per sort — carrying the D28
    fix: no unused outer page parametrize, 4 collected, pages looped once);
    cabinet search-history clear idempotent + owner-scoped; moderation
    queue base_score DESC ordering at the PriorityService seam; copy resets
    publication history (parametrized PUBLISHED/ARCHIVED). Also two LOW
    advisories: saved-search read-leg scoping in cabinet;
    header root_categories active-only + name-order in core. Purely
    additive: no retiring module, endpoint class, or helper removed — the
    test_copy_ad.py mixed-file surgery (TestCopyEndpoint* family) moves to
    B4 with the endpoint per the §6 coherence rule and the pending G0
    consumer gate. No production code, schema, docs, or i18n changes.
  files_hint: >
    Single commit, six test files (one new). Atomic by design: no
    deployable revision exists between "invariants ported" and "tests
    green", because nothing else can reference the new tests. Do NOT stage
    anything outside the six files; verify with `git status --short`.
```

## B4 audit findings

Read-only audit of block B4 (P4 — Retire unused endpoints + parity machinery), 2026-11-05.
HEAD `0f5d2714` (B3 landed; working tree clean except this plan file and the
`.ai/tmp/b4_msgid_audit.py` scratch script this audit created for msgid extraction).
Gates: **G0 CLOSED** (Product Owner confirmed no external/deployed consumers — no
temporary consumer subset exists, so "keep all support used by any temporary consumer
subset" reduces to "keep the legacy interfaces"). G1/G2 pass (B0/B1). B3 ported the
seven deletion-blocker invariants and the two LOW advisories (`0f5d2714`,
purely additive — verified: `test_listings_query.py` imports nothing from the
retiring surface). Scope below is the §6 retirement manifest re-verified file by
file against the current tree; the B4/B5 split follows the §7 P4/P5 package rows.

### 1. Deletion list — existence verified at HEAD (all under `src/backend/`)

Every file listed below exists at HEAD; counts are `Get-ChildItem`/`git`-verified.
`git status` shows no other modifications. (A) = deleted in **B4**; (B) = deferred to
**B5** per the §7 split (§4 below).

**API adapters — 27 files, 4,857 lines (A).** Six `views/api/` directories, complete:

| Directory | Files |
|---|---|
| `apps/ads/views/api/` | `__init__.py`, `copy.py`, `dashboard.py`, `detail.py`, `edit.py` (post-B0 honest mapping — still retiring), `favorite.py`, `lifecycle_actions.py`, `listings.py`, `submit.py` (9) |
| `apps/analytics/views/api/` | `__init__.py`, `moderation.py`, `seller.py` (3) |
| `apps/cabinet/views/api/` | `__init__.py`, `favorites.py`, `saved_search_writes.py`, `saved_searches.py`, `search_history.py`, `search_history_clear.py` (6) |
| `apps/moderation/views/api/` | `__init__.py`, `actions.py`, `queue.py`, `review.py` (4) |
| `apps/search/views/api/` | `__init__.py`, `search.py` (2) |
| `apps/users/views/api/` | `__init__.py`, `consent.py`, `logout.py` (3) |

**One-module adapters (A):** `apps/categories/api_tree.py`; `apps/locations/api_cities.py`.

**Route modules — 9 files (A):** `apps/{ads,analytics,cabinet,categories,locations,moderation,search,users}/api_urls.py`
(8) + `apps/ads/api_dashboard_urls.py`. Root mount: `config/urls.py` line
`path("api/v1/", include("apps.api.urls"))` (A) — remove only this line; the
`path("moderation/", include("apps.moderation.urls"))` line above it is NOT part of the
new mount and stays.

**Aggregator/harness — 5 files (A):** `apps/api/__init__.py`, `apps/api/urls.py`,
`apps/api/tests/__init__.py`, `apps/api/tests/test_urls.py` (93 lines),
`apps/api/tests/test_import_rule.py` (373 lines, incl. B0's `apps.currencies.enums`
allowlist entry at its L247 — dies with the file).

**Metadata CLI (A):** `apps/core/management/commands/verify_parity.py` (846 lines);
`apps/core/tests/test_verify_parity.py` (409 lines, 27 tests — includes the
never-scheduled pin, which dies with the command; no scheduler entry exists to clean).

**Exclusive helpers (B — B5):** `apps/core/utils/api_auth.py` (181),
`apps/core/utils/problem.py` (188); `apps/core/tests/test_api_auth.py` (16 tests),
`apps/core/tests/test_problem_response.py` (18 tests). Rationale in §4.

**Per-app API test modules — 18 files (A):** ads 7
(`test_ad_detail_api` 18, `test_dashboard_api` 8, `test_edit_route_api` 28,
`test_favorites_toggle_api` 13, `test_lifecycle_api` 22, `test_listings_api` 25,
`test_submit_route_api` 23); cabinet 4 (`test_favorites_list_api` 5,
`test_saved_search_write_api` 21, `test_saved_searches_api` 14,
`test_search_history_clear_api` 9); analytics 1 (`test_analytics_api` 13);
categories 1 (`test_categories_api` 10); locations 1 (`test_cities_api` 6);
moderation 2 (`test_moderation_api_actions` 23, `test_moderation_api_reads` 19);
search 1 (`test_search_api` 21); users 1 (`test_consent_api` 18).
Together with `test_urls.py` (2) + `test_import_rule.py` (3) these are the "20 retiring
test modules, 301 `def test_` functions" of the B3 audit — recount at HEAD confirms 301.

**Mixed-test surgery — `apps/ads/tests/test_copy_ad.py` (A):** remove the entire
"S4.6" section: `_COPY_URL_NAME` (L267), `_copy_post` (L270–276), `_clear_rate_limit_cache`
(autouse fixture, L279–282), `client_` fixture (L285–290), `TestCopyEndpointPipeline`
(6 test fns), `TestCopyEndpointHappyPath` (5 test fns) — 11 of the file's 18 test
functions. Then prune imports that become unused: `Any`, `cache`, `Client`, `reverse`,
`timezone`, `RateLimitBudget`, `PROBLEM_CONTENT_TYPE`/`RETRY_AFTER_HEADER` (whole
`problem` import line), `make_user` (keep only `create_test_ad` from the conftest
import). KEEP: `TestCopyAd` (7 fns incl. B3's `test_copy_resets_publication_history`),
`purpose_item`/`feature_items` fixtures, `uuid`, `AdStatus`, `AdImage`, `copy_ad`,
`LookupGroup`/`LookupItem`, module docstring (already describes the retained contract).
`git status` check after surgery: file retains only the service-era content.

**B4 total: 63 files deleted + 1 surgery + 1 config edit + 1 new guard module (§5).**
**B5 remainder: 4 files + 3 shared-code surgeries (§4).** Baseline placeholder dirs
(`apps/api/serializers/`, `apps/api/views/` — deleted at S0) need no recreation.
Untracked `__pycache__` dirs inside the deleted trees are build artifacts; `git rm`
handles only tracked sources.

### 2. Inbound references — full sweep results ("references to fix" checklist)

Sweeps run over `src/` (incl. `src/telegram_bot`, `src/benchmark`), `scripts/`,
`.github/workflows/`, `docs/`, `.kilo/`, `Makefile`, `Makefile.ps1`, `conftest.py`,
`AGENTS.md`, `README.md`, `docker-compose*.yml`, `docker/*.sh`, root `entrypoint*.sh`,
`pyproject.toml`. Verified **negative** unless listed. `docker/.kilo/worktrees/carefree-beast/`
is a git-ignored stray worktree on disk (0 tracked files) — its `api/v1` copies are
NOT at HEAD and are out of commit scope (environment note for the implementor: do not
let a tool "clean" it into the diff).

| Deleted file / area | Inbound references that must be fixed in the SAME commit |
|---|---|
| 6× `views/api/` dirs, `api_tree.py`, `api_cities.py` | **None.** Only retiring `api_urls.py` modules, retiring tests, `test_import_rule.py`, and `verify_parity.py` reference them (one intra-set import: `cabinet/views/api/saved_search_writes.py` imports `saved_searches` — both deleted together). Zero retained importers. |
| 9 route modules | Referenced only by `apps/api/urls.py` `include(...)` lines (deleted together) + comments in retiring tests. No CI/Makefile/entrypoint path pins. |
| `apps/api/` package + `test_urls.py` + `test_import_rule.py` | Referenced by `config/urls.py` mount (fix) and `verify_parity.py` L76/L263 (deleted together). `INSTALLED_APPS` does NOT contain `apps.api` — no settings change. |
| `verify_parity.py` + `test_verify_parity.py` | No workflow, Makefile, entrypoint, or scheduler reference (verified: zero `verify_parity` hits outside the command, its test, `docs/01-spec/api-surface.md` L84/L204/L232/L1077, `.kilo/rules/commands.md` L47–57). Docs fixed per §6. |
| 18 per-app API test modules | **None.** Collected implicitly via `pyproject.toml` `testpaths=["src/backend"]`; no `--ignore`/path pin in `ci.yml`/`ci-nightly.yml`/`ci-seed.yml`/entrypoints mentions them (the `--ignore` lists there target unrelated modules). No retained test imports them. |
| `test_copy_ad.py` surgery | Self-contained; the two B3-transferred invariants live in retained classes (verified). |
| Reverse names (30 total: `ads_api:` ×8, `dashboard_api:dashboard`, `search_api:search`, `categories_api:tree`, `locations_api:cities`, `cabinet_api:` ×8, `users_api:` ×4, `moderation_api:` ×5, `analytics_api:` ×2) | Referenced ONLY inside retiring modules + `test_verify_parity.py` + `test_copy_ad.py` (`ads_api:copy`, removed by surgery). Zero retained references — namespaces `ads`, `search`, `moderation`, `cabinet`, `consent`, `analytics` (HTML) are untouched and keep their names. |
| `RateLimitBudget.API_PUBLIC_READ`/`API_WRITE` (B5) | Retiring adapters + retiring tests + `core/enums.py` L47–51/L61–62/L73–74/L86–87 + `test_rate_limit_budget.py` L85–95 (two dedicated tests — delete in B5; the file's other content is retained). **No non-retiring endpoint uses either member** — see §3. |
| `core/utils/problem.py`, `api_auth.py` (B5) | Importers are 100% retiring modules + retiring tests + each other (`api_auth` imports `problem`); after B4 both are importless — B5 deletes them with their 2 dedicated test files. |
| `submission.media_caps()` (B5) | Sole caller `apps/ads/views/api/submit.py::_media_caps` (L457–464). |
| `SubmittedPhoto.sha256` + digest-precedence (B5) | `apps/media/schemas.py` L48–54 (optional field) + `apps/ads/services/submission.py` L327–340 branch; only populator is `views/api/submit.py` L293. `AdImage.sha256` and `FileHashService` are pre-existing — PRESERVE. |

Docstring/comment mentions of "future `/api/v1/`" or "dying mirror" in RETAINED
modules (14 files: `ads/services/{dashboard_query,edit_flow,favorites,lifecycle,listings_query}.py`,
`ads/views/{delete,edit,favorite}.py`, `cabinet/views/{favorites,saved_searches}.py`,
`search/services/saved_searches.py`, `search/views/save_search.py`,
`search/tests/test_saved_search_service.py`, `ads/tests/test_listings_query.py`)
are non-executable historical commentary → P7/B7 ("Remove obsolete migration-stage
commentary"), NOT B4.

### 3. Preserve list — verified with retained coverage anchors

| Preserved interface | Route / symbol | Retained coverage (verified at HEAD) |
|---|---|---|
| `apps/moderation/views/api_bulk.py` | `/moderation/api/v1/bulk-action/` (`moderation:bulk_action`, `apps/moderation/urls.py` L19 — OUTSIDE the dying root mount) | `test_priority_service.py` L562–563 asserts `reverse("moderation:bulk_action") == "/moderation/api/v1/bulk-action/"` + the exact `{"completed": 1, "errors": []}` contract, per-id errors, partial failure, over-cap, `/api/v2/` 404; `test_moderation_views.py` L577 + `TestBulkModerationApproveOutcome`; `test_admin_actions.py` bulk blocks; `test_db_lock_timeout.py` lock-timeout tier |
| Autocomplete | `/api/search/autocomplete` (`search:autocomplete`) | `test_autocomplete.py` (8+ literal-path GETs incl. recording); `test_autocomplete_template.py`; `test_rate_limit_budget.py::test_rate_limit_check_defaults_to_autocomplete_budget` |
| Preferred-city | `/api/preferred-city/` (`search:preferred_city`) | `test_preferred_city.py` (6 literal POSTs); `test_preferred_city_readback.py` L242 |
| Login token protocol | `/login/issue/`, `/login/status/` (`consent:login_issue`, `consent:login_status`) | `test_login.py` (200/204/410 matrix); `test_consent.py` L561; `test_auth_nav.py` L112; `test_contact_rate_limit.py` L150 |
| HTML consent/logout | `consent:accept/decline/withdraw`, `consent:logout` | `test_consent.py`, `test_logout.py` (incl. the repo's only `enforce_csrf_checks=True` test) |
| Health/readiness | `core:health*` | `test_health_contract.py` reverses all four names |
| Metrics gate | `/metrics` loopback view | `test_observability.py` L61/L240/L459–466 |
| Admin, media delivery | `admin/`, `ads:media_gate` | `test_media_security.py`, admin suites |
| Bot dialogs/commands | `src/telegram_bot` (no HTTP routes; zero references to the API surface — verified) | bot suites |

Support used ONLY by preserved surfaces and NOT in scope: `apps/moderation/views/decorators.py`
(`staff_required_api` used by `api_bulk.py` L25), `apps/core/utils/sanitize.py`
(`pydantic_errors_json` — `api_bulk.py` 422 shape), `apps/core/utils/rate_limit_response.py`
(legacy 429 builder — autocomplete/login/HTML), budgets `SEARCH_PAGE`, `AUTOCOMPLETE`,
`DEEP_LINK_RENDER`, `LOGIN_ISSUE`, `MEDIA_GATE` (+ their `test_rate_limit_budget.py`
pins). The §6 "Preserve old moderation decorators and sanitizer" and P5 "legacy
auth/429 helpers stay unchanged" clauses are satisfied by construction: none of the
B4/B5 deletions touch them.

### 4. B4 vs B5 — exclusive-support decision (task 4)

Evidence-based answer to the deciding question:

- `bulk_moderation_action` imports `staff_required_api` (legacy decorator) +
  `pydantic_errors_json` (sanitize) + plain `JsonResponse` — it does NOT import
  `core.utils.api_auth`, `core.utils.problem`, `RateLimitBudget.API_PUBLIC_READ`, or
  `API_WRITE`. It is also POST-only with **no** rate limiter (`/api/preferred-city/`
  likewise has none; autocomplete uses `AUTOCOMPLETE`; login uses `LOGIN_ISSUE`).
- Therefore `problem.py`, `api_auth.py`, `API_PUBLIC_READ`, `API_WRITE`,
  `submission.media_caps()`, `SubmittedPhoto.sha256`, and the digest-precedence branch
  are **exclusive to the retiring API** — no preserved endpoint uses any of them.

**Recommended split (follows §7 P4/P5 rows, D21/D22/D23 "REMOVE after last caller"):**
B4 removes the endpoints, routes, harness, CLI, and API test modules; **B5** removes
`core/utils/{api_auth,problem}.py` + `test_api_auth.py` + `test_problem_response.py`
(the dedicated tests keep the helpers exercised through the B4 state, so no revision
ships dead code with orphan tests), the two `RateLimitBudget` members + their 4
property-table entries + docstring rationale + the two dedicated test cases in
`test_rate_limit_budget.py`, `submission.media_caps`, the optional `sha256` field, and
the digest-precedence branch (restoring staged-digest computation exactly per R05).
This matches "Remove unused problem/auth variants, API budgets and dedicated tests,
API-only submission/media additions" = P5 row and keeps B4's atomic footprint reviewable.
Trade-off recorded: the §6 "Exclusive helpers/CLI" manifest row lumps helpers with
`verify_parity`; merging the helper deletion into B4 is *possible* (importers are 100%
retiring) but contradicts the package-row assignment and forfeits P5's per-deletion
caller-reachability check. If the implementor prefers one commit, the invariant that
must hold is: helpers and their dedicated tests die together, never before their last
importer.

### 5. URL/reverse-name smoke replacement (task 5)

`apps/api/tests/test_urls.py` dies with the aggregator it guards. Required replacement
for G5 ("removed routes are absent, legacy routes still work"):

- **Legacy routes still work — already covered** by retained suites (§3 table);
  no new tests needed. The only reverse-smoke a preserved JSON route needs
  (`moderation:bulk_action`) already exists at `test_priority_service.py` L562–563.
- **Removed routes are absent — NOT covered anywhere after deletion.** Add ONE small
  guard module, suggested `src/backend/apps/core/tests/test_url_surface.py`
  (project-level URLconf concern, core app): `Client().get("/api/v1/")` → 404 and
  `Client().get("/api/v1/ads/")` → 404 (a re-added mount would resolve and fail the
  test); optionally pin `reverse("moderation:bulk_action")` once for the legacy JSON
  contract (2–3 tests, `@pytest.mark.django_db` for the Client legs). Effort: trivial.
  This is the direct functional inversion of `test_urls.py::test_mount_unknown_paths_return_404`.

### 6. Documentation updates — B4 (same commit) vs B7 (P7 polish) (task 6)

| Doc | B4 or B7 | Exact change |
|---|---|---|
| `config/urls.py` | **B4** | Delete mount line L61; replace the L15–23 comment block (its whole `/api/v1/` multi-consumer narrative incl. the `api-surface.md` "single source of truth" pointer) with the accurate short contract: legacy JSON surfaces (`/moderation/api/v1/bulk-action/`, `/api/search/autocomplete`, `/api/preferred-city/`, `/login/issue/`, `/login/status/`), health/metrics/admin/media |
| `.kilo/rules/commands.md` | **B4** | Delete the `## API parity audit (rule 18)` section (L45–57: heading, `verify_parity` paragraph, the 3-row command table). It documents a command that no longer exists; P4 requires command docs updated in the same revision. (No executable test parses this file — `test_docs_ci_parity.py` pins only CI/Makefile marker tokens.) The separate stale `PYTEST_OPTS` claim in that file is B7 per plan checklist. |
| `README.md` | **B4** | L99 table row: reword `api-surface.md` description to "Legacy JSON surfaces & operational contracts" (or the post-B7 title); L144–148 "JSON API" paragraph: replace the "ratified multi-consumer" `/api/v1/` claim with the retained-interface statement (bot-first posting; legacy JSON endpoints as listed; browserless verification = Django `Client()` + pytest). |
| `docs/01-spec/api-surface.md` | **B4 (destructive part) / B7 (polish)** | B4: strip the 23 mirror rows + `?lang`-on-`/api/v1/` row-25 clause from the inventory; delete the mount/import-rule bullets (L34–36), the `verify_parity` receipt claims (L84 row-17 cell, L204, L232, the L1077–1078 S5.1 paragraph), and rows for removed endpoints from all narrative sections; retain rows 4, 14, 17, 19, 21, 23, 24, 26, 27, 28 (the unique legacy-contract facts) + the auth/error/budget sections reduced to what remains. B7: final restructure/shortening, spec-index cross-check, agent-doc task→service map. (Alternative per plan: delete the file and repair incoming links — README L99/L148, spec-index L163/L169, architecture-structure L444/L465/L489; NOT recommended, the legacy rows carry unique facts.) |
| `docs/01-spec/spec-index.md` | B4 minimal / **B7 full** | B4: neutralize the two `/api/v1/` claims (L158–169: "`/api/v1/` is the ratified multi-consumer surface" and the L169 sentence); B7: rewrite §API surface to the retained inventory. |
| `docs/01-spec/architecture-structure.md` | B4 minimal / **B7 full** | B4: remove/repair the mount + import-rule + `problem.py` claims (L134–138 tree comment, L437–489 §"API surface contract") so no doc asserts a mount that is gone; B7: restructure the section. Frontmatter `related: api-surface` (L15) stays while the file exists. |
| `docs/99-agent/*` | **B7** | architecture.md/rules.md/references.md have ZERO references to `/api/v1/`, `verify_parity`, or api-surface.md (verified — the S5.3 seam section never landed). P7 adds the task→service→tests map; nothing to fix in B4. |
| Retained service/view docstrings ("future `/api/v1/`") | **B7** | 14 files listed in §2 — commentary only, non-executable, G5-clean without edits. |
| i18n catalogs | **B7** | Do NOT touch catalogs in B4 (see §9). |

### 7. Risk flags (task 7)

1. **Name-collision deletions (plan §9 "deleting old JSON by matching `api` broadly").**
   `apps/moderation/views/api/` (directory, retiring) sits NEXT TO
   `apps/moderation/views/api_bulk.py` (file, PRESERVED) — any `rm …/views/api*` glob
   kills the legacy bulk endpoint. Similarly `core/utils/problem.py` (retiring) vs
   `core/utils/rate_limit_response.py` (preserved) and `api_auth.py` vs
   `moderation/views/decorators.py::staff_required_api`. In `config/urls.py`, the only
   line to remove is the exact `path("api/v1/", include("apps.api.urls"))`; the legacy
   `/moderation/api/v1/bulk-action/` lives in `apps/moderation/urls.py` L19 under the
   `moderation/` include and must resolve identically after B4. Mitigation: use the
   explicit §1 file list, then run the §3 preserved-route assertions (bulk contract
   suite is the canary).
2. **Similar route names.** Retiring namespaces all end `_api` (`ads_api:edit` vs
   retained `ads:edit`, `moderation_api:approve` vs `moderation:approve`,
   `users_api:consent_accept` vs `consent:accept`, `analytics_api:seller` vs
   `analytics:seller_trust_dashboard`, `cabinet_api:favorites` vs `cabinet:favorites`).
   A find/replace on the bare name will corrupt retained tests; match the `_api`
   suffix and the module paths, never the action word alone.
3. **`apps/ads/api_dashboard_urls.py`** is easily mistaken for part of
   `apps/ads/urls.py`'s dashboard route: `ads:dashboard` (HTML, retained) is registered
   in `apps/ads/urls.py` and consumed by `test_edit.py`/dashboard suites — deleting the
   API route module must leave `apps/ads/urls.py` byte-identical (verified zero coupling).
4. **`.kilo/rules/commands.md` verify_parity section** is the only rule-file reference
   to the deleted command; removing the section without touching anything else in that
   file (the `PYTEST_OPTS` semantics paragraph is B7, and user edits in
   `.kilo/rules/project.md`/`.kilo/commands/debug/bugfix.md` must be preserved verbatim).
5. **`docs/99-agent/*`** needs no B4 edit (verified zero references) — do not "clean up"
   nonexistent references; the B7 doc pass owns the additions.
6. **i18n**: do not prune catalogs in B4 — unreferenced msgids do not break the
   completeness gate (it checks msgstr presence, not source references). Pruning is a
   whole-tree scratch-extraction procedure in B7/P7 (§9).
7. **Stray ignored worktree** `docker/.kilo/worktrees/carefree-beast/` contains stale
   `api/v1` copies; it is untracked and must not leak into the commit (environment
   hazard for agents running broad greps/`git clean`).
8. **test-count optics (G8)**: B4 removes 339 `def test_` functions (301 + 27 +
   11) plus parametrized collection inflation (e.g. the D28 matrix's ×3 page rows,
   wrong-method ×4, bad-body ×3). This is intended transport deletion; the ledger is
   the 7 B3 blockers (already landed) — record collected counts before/after instead
   of arguing from raw deltas.

### 8. Ordered deletion sequence (single atomic commit; intra-commit order is an
implementation safety net so a partial `git add` never stages broken imports)

1. Delete the 18 per-app API test modules (leaves of the import graph).
2. `test_copy_ad.py` mixed surgery (removes `ads_api:copy` + `problem` imports from a
   retained file).
3. Delete `apps/core/tests/test_verify_parity.py` + `verify_parity.py` (command before
   harness so the command's consumers disappear before its input registry).
4. Delete `apps/api/tests/{test_urls,test_import_rule,__init__}.py`, then `apps/api/urls.py`,
   `apps/api/__init__.py` (package gone).
5. Delete the 9 route modules (`api_urls.py` ×8 + `api_dashboard_urls.py`).
6. Delete the 27 adapter files / 6 `views/api/` dirs + `api_tree.py` + `api_cities.py`.
7. `config/urls.py`: remove the mount line; rewrite the comment block.
8. Add `apps/core/tests/test_url_surface.py` (§5 guard).
9. Docs (§6 B4 column): `.kilo/rules/commands.md` section removal; `README.md`;
   `docs/01-spec/api-surface.md` destructive strip; minimal `spec-index.md` +
   `architecture-structure.md` factual corrections.
10. Verify: `uv run ruff check src/` → `uv run basedpyright src/` → G5 grep sweep
    (`api/v1/`, `views.api`, `*_api:`, `API_PUBLIC_READ|API_WRITE`, `verify_parity`,
    `problem|api_auth` imports — expected residue ONLY: `/moderation/api/v1/` legacy
    path, B5-pending helpers/budgets, doc-commentary deferred to B7) →
    `.\Makefile.ps1 test` (fast gate) → focused retained suites for the §3 canaries
    (`test_priority_service.py` bulk block, `test_edit.py`, `test_consent.py`,
    `test_logout.py`, `test_health_contract.py`, `test_observability.py`,
    `test_moderation_views.py`). `makemigrations --check --dry-run` stays clean (no
    model/schema delta — B5's `SubmittedPhoto.sha256` is a Pydantic field, no
    migration, `AdImage.sha256` untouched).

### 9. i18n msgids that become unreferenced (P7/B7 list — do NOT edit catalogs in B4)

Extraction at HEAD via `.ai/tmp/b4_msgid_audit.py` (regex over
`_()/gettext()/gettext_lazy()` in retiring modules vs all retained `src/` Python,
retained-reference spot-check against `.html`/`.py` prose). 32 candidate msgids
become source-unreferenced after **B4+B5** (helpers included); 3 shared msgids MUST
STAY (also used by retained HTML sources):
`The server is busy processing another change. Please try again shortly.`,
`This ad cannot be edited in its current status.`,
`To manage ads, please accept the personal data storage consent first.`

Only-retiring candidates (P7 must re-verify each with the whole-tree scratch-extraction
recipe from `.kilo/rules/commands.md` before pruning; preserve `c2f130dd`'s Bosnian fix):

- From `core/utils/problem.py` (13): `Bad Request`, `Conflict`, `Error`, `Forbidden`,
  `Internal Server Error`, `Method Not Allowed`, `Not Found`,
  `Request body failed validation.`, `Service Unavailable`, `Too Many Requests`,
  `Too many requests; retry after the indicated delay.`, `Unauthorized`,
  `Unprocessable Entity`.
- From `core/utils/api_auth.py` (3): `Authentication required.`,
  `Method not allowed.`, `Staff access required.`
- From ads adapters (12): `Ad not found.`, `Method not allowed.`,
  `One of the photos is no longer available. Please upload it again.`,
  `The ad cannot take that edit in its current status.`,
  `The draft no longer exists. Please start a new ad.`,
  `Storage consent is required to view the seller dashboard.`,
  `This ad cannot be archived in its current status.`,
  `This ad cannot be reactivated in its current status.`,
  `This ad is already deleted.`,
  `This ad cannot be submitted in its current status.`,
  `This ad cannot be submitted: the field check reports missing or over-cap content.`
  (note: two candidates are shared across ads adapters; dedupe against the same list)
- From moderation adapter (2): `The ban was not applied to this ad's owner.`,
  `This ad cannot be published: its current status does not allow the transition to published.`
  (+ `Ad not found.`, `Method not allowed.` shared with ads).
- From cabinet adapters (2): `Saved search not found.`, `Search query is too long.`
  (+ `Method not allowed.` shared).
- From users adapters (2): `Consent cannot be changed for a withdrawn account.`,
  (+ `Method not allowed.` shared).

Caveats for B7: the two multi-line implicitly-concatenated submit/actions strings are
given here in full; verify `Ad not found.`/`Method not allowed.` against templates as
well (spot-check found only docstring prose, not `{% trans %}`); the catalogs also
carry retired-endpoint msgids introduced by i18n batches `babd3210`/`7b123781`/
`c2f130dd`/`82742908` — the scratch diff is authoritative, this list is the scoped
preview. The completeness gate remains green with unreferenced entries present.

### 10. B4 acceptance mapping

- "Removed paths are absent" → §1/§8 step 10 grep sweep + URLconf has no `/api/v1/` mount.
- "Retained product routes resolve with previous contracts" → §3 coverage table +
  focused suites in §8 step 10 (bulk-action canary first).
- "No executable import of deleted modules" → ruff/basedpyright clean; zero retained
  importers verified in §2.
- "Keep all support used by any temporary consumer subset" → no subset exists (G0);
  everything preserved is enumerated in §3.
- G5 sweep residue expectations documented in §8 step 10 (`/moderation/api/v1/`
  expected; B5 helpers pending; B7 doc-commentary listed).

## B4 task description

```yaml
id: b4_retire_api_surface

title: P4 — retire the unused /api/v1/ mirror surface and the API-parity machinery

priority: high

depends_on:
  - "G0 consumer-compatibility gate CLOSED (Product Owner confirmed: no external or deployed consumers exist)"
  - "b3_transfer_business_tests landed (HEAD 0f5d2714, purely additive — test_listings_query.py imports nothing from the retiring surface)"

source_reference: '.ai\plans\architecture-correction-plan.md'
source_section: '§4 D09–D25/D27, §6 retirement manifest, §7 P4, §8 G5'
source_file: '.ai\plans\architecture-correction-execution.md'
source_blocks:
  - '## B4 audit findings — §1 deletion list, §2 inbound references, §3 preserve list, §4 B4/B5 split, §5 guard spec, §6 docs split, §7 risk flags, §8 ordered sequence, §10 acceptance mapping'

description: >
  ONE atomic commit retiring the /api/v1/ JSON mirror surface and its parity
  tooling: 63 files deleted (27 API adapters, 2 one-module adapters, 9 route
  modules, the apps.api aggregator package with its 3 test files, the
  verify_parity CLI + its test, 18 per-app API test modules), the root mount
  removed from config/urls.py, apps/ads/tests/test_copy_ad.py surgically
  reduced to its service-era content, ONE new URL-surface guard module added,
  and the enumerated doc corrections. Zero behavior change to any retained
  module — no production code change beyond deletions and the URLconf mount.

goals:
  - Removed paths are absent (G5): no /api/v1/ mount in the root URLconf; none of the 30 retiring *_api: reverse names resolve
  - Preserved routes resolve with their previous contracts (§3 preserve canaries)
  - No executable import of any deleted module survives
  - Docs state the shipped surface (no stale mount / verify_parity claims)
  - B5 boundary exact: exclusive helpers, budgets, sha256, media_caps stay pending B5, untouched and still exercised

extra_context: |
  ENVIRONMENT HAZARD (audit §7.7): docker/.kilo/worktrees/carefree-beast/ is a
  git-ignored stray worktree on disk (0 tracked files) holding stale api/v1
  copies. It is NOT at HEAD and must not leak into the commit: stage via the
  explicit file lists below — never `git add -A`, never a broad `git clean`.
  Untracked __pycache__ dirs inside deleted trees are build artifacts; git rm
  handles only tracked sources.
  Test-count optics (audit §7.8): B4 removes 339 `def test_` functions
  (301 retiring modules + 27 verify_parity + 11 copy surgery) plus parametrized
  collection inflation. This is intended transport deletion — record collected
  counts before/after (`--collect-only`) instead of arguing from raw deltas;
  the coverage ledger is B3's 7 ported invariants (already landed).
  PYTEST_OPTS semantics (B3-verified in docker/entrypoint-test.sh): ADDITIVE —
  focused runs keep --reuse-db / xdist loadgroup; the commands.md "replaces
  the defaults" prose is stale (R06) and its fix is B7. Do not touch that
  paragraph in this task; run the commands as given.
  Zero-inbound-reference guarantee (audit §2): every deleted file is referenced
  only by files deleted in the same commit (the one intra-set import —
  cabinet/views/api/saved_search_writes.py imports saved_searches — dies with
  both members). INSTALLED_APPS has no apps.api entry; no settings change.

files:
  - path: src/backend/apps/ads/tests/test_copy_ad.py
    targets:
      - type: module
        name: test_copy_ad
        action: SURGERY-REDUCE (retained file — never delete); detail under "changes"
    semantic_anchors:
      keep_symbols:
        - module docstring (already describes the retained service contract)
        - pytestmark
        - 'fixtures: purpose_item, feature_items'
        - 'TestCopyAd (7 tests, incl. b3''s test_copy_resets_publication_history)'
        - 'imports kept: uuid, pytest, Ad/AdImage, copy_ad, AdStatus, LookupGroup/LookupItem, create_test_ad'
  - path: src/backend/config/urls.py
    targets:
      - type: urlpattern
        name: 'path("api/v1/", include("apps.api.urls"))'
        action: remove (ONLY this urlpatterns entry, identified by its first argument, the route string "api/v1/")
      - type: comment_block
        name: module-head URL-surface narrative (the /api/v1/ multi-consumer contract description referencing apps.api.urls, Pydantic DTOs, problem.py, api-surface.md as single source of truth)
        action: rewrite to the retained-surface contract
    semantic_anchors:
      keep_unchanged:
        - 'path("moderation/", include("apps.moderation.urls")) and every other include entry (byte-identical)'
        - _metrics_gate view
        - include import (still used by the remaining entries)
  - path: src/backend/apps/core/tests/test_url_surface.py
    targets:
      - type: module
        name: test_url_surface
        action: NEW (G5 inverse of the dying apps/api/tests/test_urls.py)
  - path: .kilo/rules/commands.md
    targets:
      - type: doc_section
        name: '## API parity audit (rule 18)'
        action: remove section only — heading, verify_parity paragraph, 3-row command table
  - path: README.md
    targets:
      - type: doc_paragraph/doc_table_row
        name: docs-table row describing api-surface.md; the JSON-API paragraph (ratified multi-consumer /api/v1/ claim)
        action: reword per "changes"
  - path: docs/01-spec/api-surface.md
    targets:
      - type: doc_sections
        name: endpoint inventory table; mount/import-rule bullets; verify_parity receipt claims; S5.1 narrative paragraph
        action: destructive strip per "changes" (no restructure — B7)
  - path: docs/01-spec/spec-index.md
    targets:
      - type: doc_claims
        name: the two /api/v1/ claims ("/api/v1/ is the ratified multi-consumer surface" sentence + its follow-on)
        action: neutralize (minimal factual correction only)
  - path: docs/01-spec/architecture-structure.md
    targets:
      - type: doc_claims
        name: URL-tree mount comment + API-surface-contract section claims (mount, import rule, problem.py)
        action: remove/repair so no doc asserts the retired mount (no restructure — B7)

# ─────────────────────────────────────────────────────────────────────────────
# Deletion list — exact, grouped in the audit's 10-step ordered sequence
# (§8; ONE atomic commit; intra-commit order is a staging-safety net so a
#  partial `git add` never stages broken imports)
# ─────────────────────────────────────────────────────────────────────────────

deletions:

  step_1_api_test_modules:   # 18 per-app API test modules — leaves of the import graph
    - src/backend/apps/ads/tests/test_ad_detail_api.py
    - src/backend/apps/ads/tests/test_dashboard_api.py
    - src/backend/apps/ads/tests/test_edit_route_api.py
    - src/backend/apps/ads/tests/test_favorites_toggle_api.py
    - src/backend/apps/ads/tests/test_lifecycle_api.py
    - src/backend/apps/ads/tests/test_listings_api.py
    - src/backend/apps/ads/tests/test_submit_route_api.py
    - src/backend/apps/cabinet/tests/test_favorites_list_api.py
    - src/backend/apps/cabinet/tests/test_saved_search_write_api.py
    - src/backend/apps/cabinet/tests/test_saved_searches_api.py
    - src/backend/apps/cabinet/tests/test_search_history_clear_api.py
    - src/backend/apps/analytics/tests/test_analytics_api.py
    - src/backend/apps/categories/tests/test_categories_api.py
    - src/backend/apps/locations/tests/test_cities_api.py
    - src/backend/apps/moderation/tests/test_moderation_api_actions.py
    - src/backend/apps/moderation/tests/test_moderation_api_reads.py
    - src/backend/apps/search/tests/test_search_api.py
    - src/backend/apps/users/tests/test_consent_api.py

  step_3_parity_cli:   # command before harness: the command's consumers disappear before its input registry
    - src/backend/apps/core/tests/test_verify_parity.py
    - src/backend/apps/core/management/commands/verify_parity.py

  step_4_api_package:   # ordered: tests first, then urls.py, then __init__.py — package fully gone
    - src/backend/apps/api/tests/test_urls.py
    - src/backend/apps/api/tests/test_import_rule.py   # R-F2 harness + B0's apps.currencies.enums allowlist entry die with the file
    - src/backend/apps/api/tests/__init__.py
    - src/backend/apps/api/urls.py
    - src/backend/apps/api/__init__.py

  step_5_route_modules:   # 9 files
    - src/backend/apps/ads/api_urls.py
    - src/backend/apps/analytics/api_urls.py
    - src/backend/apps/cabinet/api_urls.py
    - src/backend/apps/categories/api_urls.py
    - src/backend/apps/locations/api_urls.py
    - src/backend/apps/moderation/api_urls.py
    - src/backend/apps/search/api_urls.py
    - src/backend/apps/users/api_urls.py
    - src/backend/apps/ads/api_dashboard_urls.py

  step_6_adapters:   # 27 files across 6 views/api/ dirs + 2 one-module adapters
    - src/backend/apps/ads/views/api/                   # __init__.py, copy.py, dashboard.py, detail.py, edit.py, favorite.py, lifecycle_actions.py, listings.py, submit.py (9)
    - src/backend/apps/analytics/views/api/             # __init__.py, moderation.py, seller.py (3)
    - src/backend/apps/cabinet/views/api/               # __init__.py, favorites.py, saved_search_writes.py, saved_searches.py, search_history.py, search_history_clear.py (6)
    - src/backend/apps/moderation/views/api/            # __init__.py, actions.py, queue.py, review.py (4)
    - src/backend/apps/search/views/api/               # __init__.py, search.py (2)
    - src/backend/apps/users/views/api/                # __init__.py, consent.py, logout.py (3)
    - src/backend/apps/categories/api_tree.py
    - src/backend/apps/locations/api_cities.py

# ─────────────────────────────────────────────────────────────────────────────
# Changes with code hints (semantic targets — no line numbers)
# ─────────────────────────────────────────────────────────────────────────────

changes:

  - action: prune_symbols
    target: src/backend/apps/ads/tests/test_copy_ad.py   (sequence step 2)
    description: >
      Remove the entire API-endpoint section of the file: every reference to
      the ads_api:copy route and its problem/auth machinery, leaving the
      service-era content.
    contract:
      remove_symbols:
        - _COPY_URL_NAME          (module constant, value "ads_api:copy")
        - _copy_post              (module-level request helper)
        - _clear_rate_limit_cache (autouse fixture)
        - client_                 (fixture)
        - TestCopyEndpointPipeline  (class, 6 tests)
        - TestCopyEndpointHappyPath  (class, 5 tests)
      prune_now_unused_imports:
        - typing.Any
        - django.core.cache.cache
        - django.test.Client
        - django.urls.reverse
        - django.utils.timezone
        - apps.core.enums.RateLimitBudget   (keep AdStatus on the same import line — TestCopyAd still uses it)
        - the whole apps.core.utils.problem import line (PROBLEM_CONTENT_TYPE, RETRY_AFTER_HEADER)
        - make_user from the conftest import (keep create_test_ad)
      keep_verified:
        - 'TestCopyAd — 7 tests incl. test_copy_resets_publication_history (B3 transfer)'
        - 'purpose_item / feature_items fixtures; uuid; Ad, AdImage; copy_ad; AdStatus; LookupGroup, LookupItem; module docstring; pytestmark'

  - action: remove_urlpattern
    target: src/backend/config/urls.py   (sequence step 7)
    description: >
      Remove ONLY the urlpatterns entry path("api/v1/", include("apps.api.urls"))
      (identified by its first argument, the route string "api/v1/"). Everything
      else in the file stays byte-identical — in particular the adjacent
      path("moderation/", include("apps.moderation.urls")) line and the
      include import (still used by the remaining entries).
    code_hint: |
      urlpatterns = [
          path("metrics", _metrics_gate, name="prometheus-django-metrics"),
          path("", include("django_prometheus.urls")),
          path("admin/", admin.site.urls),
          # path("api/v1/", include("apps.api.urls"))  <- removed
          path("moderation/", include("apps.moderation.urls")),
          ...
      ]

  - action: rewrite_comment_block
    target: src/backend/config/urls.py module-head comment block
    description: >
      Replace the /api/v1/ multi-consumer narrative (it references apps.api.urls,
      Pydantic BaseInputModel DTOs, 422 problem responses, problem.py, and
      api-surface.md as single source of truth) with the accurate short
      contract: legacy JSON surfaces are /moderation/api/v1/bulk-action/
      (moderation bulk actions), /api/search/autocomplete, /api/preferred-city/,
      /login/issue/ + /login/status/ (login-token protocol), alongside the
      health/readiness, metrics, admin, media and HTML routes.
    code_hint: |
      # URL surface: the HTMX/MPA site (bot-first ad posting through the
      # Telegram bot) plus the retained legacy JSON routes —
      # /moderation/api/v1/bulk-action/ (moderation bulk actions),
      # /api/search/autocomplete, /api/preferred-city/, and the /login/
      # token protocol — and operational endpoints (health, metrics, admin,
      # media). See docs/01-spec/api-surface.md for the retained contracts.

  - action: add_module
    target: src/backend/apps/core/tests/test_url_surface.py   (sequence step 8 — NEW)
    description: >
      Project-level URLconf guard (core app). Direct functional inversion of the
      dying apps/api/tests/test_urls.py::test_mount_unknown_paths_return_404:
      removed routes must stay absent; the one retained legacy JSON route keeps
      its exact path and reverse name. Spec pinned under required_tests.
    code_hint: |
      """URL-surface guard for the retired /api/v1/ mount (plan §8 G5).

      Replaces apps.api.tests.test_urls (deleted with its aggregator): the
      removed root mount must stay absent while the retained legacy JSON
      route keeps its exact path and reverse name.
      """

      import pytest
      from django.test import Client
      from django.urls import reverse

      pytestmark = pytest.mark.django_db


      def test_api_v1_root_returns_404() -> None:
          # With the mount removed nothing resolves under /api/v1/.
          assert Client().get("/api/v1/").status_code == 404


      def test_api_v1_ads_prefix_returns_404() -> None:
          # A re-added per-app route module under the old mount would resolve here.
          assert Client().get("/api/v1/ads/").status_code == 404


      def test_moderation_bulk_action_legacy_route_pinned() -> None:
          # The retained legacy JSON surface lives OUTSIDE the retired mount.
          assert reverse("moderation:bulk_action") == "/moderation/api/v1/bulk-action/"

  - action: update_docs
    target: the five doc files in "files"   (sequence step 9)
    description: >
      Enumerated, bounded corrections only — full docs restructure is B7.
      1) .kilo/rules/commands.md: remove ONLY the "## API parity audit (rule
      18)" section (heading + verify_parity paragraph + the 3-row command
      table). Touch nothing else in the file — the stale PYTEST_OPTS
      "replaces the defaults" paragraph is B7, and user edits in project.md
      and .kilo/commands/debug/bugfix.md stay verbatim.
      (test_docs_ci_parity.py pins CI/Makefile marker tokens only — it cannot
      break from this edit.)
      2) README.md: docs-table row describing api-surface.md → "Legacy JSON
      surfaces & operational contracts" phrasing; the JSON-API paragraph →
      retained-interface statement (bot-first posting; legacy JSON endpoints
      as enumerated; browserless verification via Django Client() + pytest).
      3) docs/01-spec/api-surface.md (destructive part): strip the 23 mirror
      rows and the ?lang-on-/api/v1/ clause from the inventory; delete the
      mount/import-rule bullets; delete the verify_parity receipt claims
      (row-17 receipt cell, the receipts bullets, the S5.1 paragraph); remove
      rows of removed endpoints from all narrative sections; RETAIN the rows
      carrying unique legacy-contract facts (moderation bulk-action,
      autocomplete, preferred-city, login issue/status, health, metrics,
      media gate) and the auth/error/budget sections reduced to what remains.
      4) docs/01-spec/spec-index.md: neutralize the two /api/v1/ claims
      (the "ratified multi-consumer surface" sentence and its follow-on);
      the §API rewrite is B7.
      5) docs/01-spec/architecture-structure.md: remove/repair the mount
      claim (URL-tree comment), the import-rule claim, and the problem.py
      claim in the API-surface-contract section so no doc asserts the
      retired mount. Frontmatter "related: api-surface" stays while the
      file exists. No restructure.
      6) docs/99-agent/*: ZERO references verified — do NOT clean up
      nonexistent references there.

sequence:      # mandatory staging order inside the single commit
  1: Delete the 18 per-app API test modules (deletions.step_1).
  2: test_copy_ad.py mixed surgery (changes.prune_symbols) — removes ads_api:copy and problem imports from a retained file.
  3: Delete apps/core/tests/test_verify_parity.py then apps/core/management/commands/verify_parity.py (deletions.step_3).
  4: Delete apps/api/tests/{test_urls,test_import_rule,__init__}.py, then apps/api/urls.py, then apps/api/__init__.py (deletions.step_4).
  5: Delete the 9 route modules (deletions.step_5).
  6: Delete the 27 adapter files (6 whole views/api/ dirs incl. their __init__.py) + api_tree.py + api_cities.py (deletions.step_6). NEVER a glob: apps/moderation/views/api_bulk.py is PRESERVED.
  7: config/urls.py: remove the mount entry; rewrite the module-head comment block.
  8: Add apps/core/tests/test_url_surface.py.
  9: Docs — the five enumerated doc corrections (changes.update_docs).
  10: Full verification block (verification key) incl. the G5 grep sweep and the fast gate.

architectural_constraints:
  - Deletions by explicit path only (the lists above); never a glob or name-prefix match — `views/api*` would kill the PRESERVED apps/moderation/views/api_bulk.py, and problem.py/rate_limit_response.py + api_auth.py/staff_required_api are adjacent name pairs.
  - Zero behavior change to retained modules: no retained URLconf entry, view, service, template, middleware, setting, or runtime path may change; apps/ads/urls.py (retained ads:dashboard) stays byte-identical — api_dashboard_urls.py is a separate file with verified zero coupling.
  - No retained importer may remain: the only intra-retiring import (cabinet/views/api/saved_search_writes.py -> saved_searches) dies with both members; INSTALLED_APPS has no apps.api entry; no CI/Makefile/entrypoint path pins any deleted module.
  - Reverse namespaces are disjoint: retiring *_api: (ads_api, dashboard_api, search_api, categories_api, locations_api, cabinet_api, users_api, moderation_api, analytics_api) vs retained ads, search, moderation, cabinet, consent, analytics — never rewrite a bare action word.
  - config/urls.py: exactly one urlpatterns entry removed, identified by its first argument ("api/v1/"); the include import stays (remaining includes use it).
  - docs/99-agent/* stays untouched (verified zero references); i18n catalogs stay untouched (completeness gate checks msgstr presence, not source references); no .po/.mo edits.
  - B5-pending symbols stay intact and exercised through their dedicated tests: apps/core/utils/api_auth.py, apps/core/utils/problem.py, core/tests/test_api_auth.py, core/tests/test_problem_response.py, RateLimitBudget.API_PUBLIC_READ / API_WRITE (+ their pins in core/tests/test_rate_limit_budget.py), submission.media_caps(), SubmittedPhoto.sha256 + the digest-precedence branch in apps/ads/services/submission.py. AdImage.sha256 and FileHashService are pre-existing and preserved.
  - English only; no logging changes; no new msgids; no schema/model/migration delta (makemigrations --check stays clean).

required_tests:
  url_surface_guard: >
    NEW src/backend/apps/core/tests/test_url_surface.py — exactly three tests,
    pytest.mark.django_db on the module:
    1) test_api_v1_root_returns_404 — Client().get("/api/v1/").status_code == 404;
    2) test_api_v1_ads_prefix_returns_404 — Client().get("/api/v1/ads/").status_code
    == 404 (a re-added mount or per-app route module would resolve and fail);
    3) test_moderation_bulk_action_legacy_route_pinned —
    reverse("moderation:bulk_action") == "/moderation/api/v1/bulk-action/"
    (the retained legacy JSON contract pin; also asserted independently by the
    retained test_priority_service.py bulk block, which must keep passing
    byte-unchanged).
    No new tests for other preserved routes: the §3 preserve table documents
    the retained suites that already pin autocomplete, preferred-city, login
    issue/status, HTML consent/logout, health/readiness, metrics, admin,
    media — all of them must stay green UNCHANGED.

verification:
  lint: uv run ruff check src/
  typecheck: uv run basedpyright src/
  focused_canaries: >
    docker compose --project-name mko-bazuna-test --env-file .env.test -f
    docker-compose.yml -f docker-compose.test.yml run --rm -e
    "PYTEST_OPTS=src/backend/apps/moderation/tests/test_priority_service.py
    src/backend/apps/moderation/tests/test_moderation_views.py
    src/backend/apps/ads/tests/test_edit.py
    src/backend/apps/ads/tests/test_copy_ad.py
    src/backend/apps/users/tests/test_consent.py
    src/backend/apps/users/tests/test_logout.py
    src/backend/apps/core/tests/test_health_contract.py
    src/backend/apps/core/tests/test_observability.py
    src/backend/apps/core/tests/test_url_surface.py" test
    (bulk-action contract canary first in the list; includes the NEW guard
    module; start the DB first — .\Makefile.ps1 test-db — if
    docker ps --filter "name=mko-bazuna-test-db-" is empty; never
    `uv run pytest` locally)
  fast_gate: .\Makefile.ps1 test
  g5_sweep: >
    G5 grep sweep (ripgrep; scope OUTSIDE the stray worktree docker/.kilo/ —
    it is untracked and irrelevant; .ai/ planning records are process files,
    out of scope):
    1. rg -n "api/v1/" src/ .kilo/rules README.md docs/ Makefile Makefile.ps1 scripts/
    2. rg -n "views\.api" src/
    3. rg -n "_api:" src/
    4. rg -n "API_PUBLIC_READ|API_WRITE" src/
    5. rg -n "verify_parity" src/ scripts/ .github/ Makefile Makefile.ps1 .kilo/ README.md docs/
    6. rg -n "core\.utils\.problem|core\.utils\.api_auth" src/
    EXPECTED RESIDUE (and nothing else):
    (1) only the /moderation/api/v1/ legacy route family (path + reverse
    literals in apps/moderation, its tests, the new guard, config comments)
    and B7-deferred doc commentary in retained docs/docstrings;
    (2) zero; (3) zero; (4) only apps/core/enums.py members + docstring and
    their dedicated pins in core/tests/test_rate_limit_budget.py (B5-pending);
    (5) zero outside .ai/; (6) only the two B5-pending helper modules, their
    mutual import, and their two dedicated test files (B5-pending).
  schema_check: >
    No model/schema delta by design: uv run python -c equivalent of
    manage.py makemigrations --check --dry-run stays clean when run via the
    dev container; simpler: rely on the fast gate's test_docs_ci_parity +
    suite (no migration file may appear in git status).
  notes: >
    `git status --short` after the commit prep must show exactly the files in
    this task (63 deletions + test_copy_ad.py + config/urls.py + the new
    guard + the 5 doc files) and NOTHING from docker/.kilo/worktrees/.
    Record pytest --collect-only counts before/after (expected delta -339
    `def test_` base functions plus parametrized-collection inflation —
    e.g. run once with the changes staged and once on HEAD~).
    Verify the commands.md edit leaves the PYTEST_OPTS paragraph intact
    (diff the file against the section boundary only).

acceptance_criteria:
  - >
    Removed paths are absent (G5): config/urls.py contains no
    path("api/v1/", include("apps.api.urls")) entry; the guard module proves
    Client().get("/api/v1/") and Client().get("/api/v1/ads/") both return 404;
    none of the 30 retiring *_api: reverse names resolve anywhere in src/;
    the root URLconf resolves the remaining includes (admin, moderation,
    analytics, cabinet, users, ads, categories, locations, search, core,
    metrics, django_prometheus) exactly as before.
  - >
    Preserved routes resolve with their previous contracts: moderation
    bulk-action canary green (reverse name + path + JSON contract + per-id
    errors + partial failure + over-cap + /api/v2/ 404 — test_priority_service.py),
    autocomplete, preferred-city, login issue/status, HTML consent/logout,
    health/readiness, /metrics loopback, admin, media-gate, and the bot
    suites all green UNCHANGED (the §3 preserve table enumerates their
    retained tests; none of them is edited in this task).
  - >
    No executable import of deleted modules: ruff clean on src/; basedpyright
    clean on src/; no retained module references apps.api, apps.<app>.views.api,
    apps.<app>.api_urls, apps.categories.api_tree, apps.locations.api_cities, or
    verify_parity (G5 sweep greps 2/3/5 zero-hit); the six B5-pending symbols of
    architectural_constraints are still present, imported (by pending tests
    only), and covered by their green dedicated tests.
  - >
    test_copy_ad.py is reduced to its service-era content: 7 remaining tests
    (incl. test_copy_resets_publication_history), _COPY_URL_NAME, _copy_post,
    _clear_rate_limit_cache, client_, TestCopyEndpointPipeline,
    TestCopyEndpointHappyPath and the pruned imports gone; ruff reports no
    unused imports left in it.
  - >
    G5 sweep residue matches the documented expectations exactly (only
    /moderation/api/v1/ legacy route family, B5-pending helper/budget
    symbols, B7-deferred doc commentary); no other residue.
  - >
    Docs updated exactly per the enumeration: commands.md shows only the
    parity section removed (PYTEST_OPTS paragraph + every other line
    byte-identical); README JSON-API paragraph + docs-table row reworded;
    api-surface.md mirror rows / mount bullets / import-rule bullets /
    verify_parity receipt claims stripped with the unique legacy-contract
    facts retained; spec-index.md + architecture-structure.md claims
    neutralized; no doc restructure beyond the enumerated edits.
  - >
    Hygiene: single commit; git status shows exactly the intended files; the
    stray worktree docker/.kilo/worktrees/carefree-beast/ contributes nothing
    (no untracked file staged); no migration, settings, env, dependency,
    lockfile, or .po/.mo file changed; i18n completeness gate green in the
    fast gate.

out_of_scope:
  - B5-exclusive-symbol removals: delete of apps/core/utils/api_auth.py, apps/core/utils/problem.py, core/tests/test_api_auth.py, core/tests/test_problem_response.py, Removal of RateLimitBudget.API_PUBLIC_READ / API_WRITE (incl. property-table entries, docstring rationale, their dedicated pins in core/tests/test_rate_limit_budget.py) — all stay untouched and exercised in B4.
  - B5 submission/media removals: submission.media_caps(), the optional SubmittedPhoto.sha256 field, and the staged-digest-precedence branch in apps/ads/services/submission.py (AdImage.sha256 and FileHashService are pre-existing and preserved).
  - i18n catalog edits — the ~32 source-unreferenced msgid candidates (B4+B5) stay in the catalogs; pruning belongs to B7 via the whole-tree scratch-extraction recipe; the 3 shared msgids must never be pruned.
  - Docs restructure beyond the enumerated edits: api-surface.md final restructure/shortening, spec-index §API rewrite, architecture-structure section restructure, docs/99-agent/* additions, and the 14 retained files' "future /api/v1/" docstring/commentary touch-ups — all B7.
  - Any behavior change (or docstring edit) to retained modules — prefer zero in B4; the only retained-file edits are test_copy_ad.py surgery, config/urls.py mount+comment, and the new guard module.
  - Any schema/model/migration, settings/env, middleware, dependency, or lockfile change; any bot-workflow change; B6/P6 signature simplifications.

risks:
  - >
    Name-collision deletions (plan §9): apps/moderation/views/api/ (directory,
    retiring) sits NEXT TO apps/moderation/views/api_bulk.py (file, PRESERVED)
    — any `rm .../views/api*` glob kills the legacy bulk endpoint; same
    pattern for core/utils/problem.py (retiring B5) vs rate_limit_response.py
    (preserved) and api_auth.py vs staff_required_api. Mitigation: explicit
    file lists only; bulk contract canary run immediately after deletion.
  - >
    Similar route names: retiring *_api: namespaces vs retained ads:/moderation:/
    consent:/cabinet:/analytics: (ads_api:edit vs ads:edit, users_api:consent_accept
    vs consent:accept, analytics_api:seller vs analytics:seller_trust_dashboard);
    a find/replace on the bare action word corrupts retained tests — never
    rewrite bare action words, only exact *_api-qualified names in deleting files.
  - >
    api_dashboard_urls.py is easily mistaken for apps/ads/urls.py dashboard
    routing: retained ads:dashboard (HTML) is registered in apps/ads/urls.py,
    consumed by test_edit.py/dashboard suites; that file must stay
    byte-identical (verified zero coupling).
  - >
    config/urls.py: exactly one entry removed — the entry whose first argument
    is "api/v1/"; the adjacent path("moderation/", ...) line is NOT part of
    any change; include import must remain used (remaining includes use it).
  - >
    Stray ignored worktree docker/.kilo/worktrees/carefree-beast/ contains
    stale api/v1 copies — untracked and must not leak into the commit: no
    `git add -A`, no `git clean`; stage via explicit path lists; exclude the
    directory from G5 sweep interpretation.
  - >
    Test-count optics (G8): 339 test functions removed (plus parametrized
    collection inflation — D28 matrix x3 page rows, wrong-method x4, bad-body
    x3) may look like a coverage regression; the coverage ledger is B3's 7
    ported invariants (already landed at HEAD) — record collected counts
    before/after instead of arguing from raw deltas.
  - >
    i18n gate: unreferenced msgids do NOT fail the completeness gate (it
    checks msgstr presence, not source references) — do not "help" by
    pruning catalogs without the B7 scratch-extraction recipe; any .po edit
    in B4 violates the plan and risks losing c2f130dd's Bosnian fix to
    fuzzy merge artifacts.
  - >
    commands.md scoping: remove ONLY the "## API parity audit (rule 18)"
    section; the stale PYTEST_OPTS "replaces the defaults" paragraph and any
    user edits in that file belong to B7 / stay verbatim —
    test_docs_ci_parity.py cannot break (it pins CI/Makefile marker tokens
    only), so there is no test excuse for touching more.

commit:
  message: 'refactor(api): retire unused /api/v1/ mirror surface and parity tooling'
  body: >
    Delete the unused /api/v1/ JSON mirror surface: the full apps/api
    aggregator package, the 27 API adapters, categories/locations one-module
    adapters, all 9 route modules, the root URLconf mount, the verify_parity
    CLI and its test, and the 18 per-app API test modules. Reduce
    test_copy_ad.py to its service-era content. Add a URL-surface guard
    (test_url_surface.py) proving /api/v1/ stays 404 while the retained
    moderation bulk-action legacy route keeps its exact path/reverse pin.
    Drop the parity audit section from commands.md and correct README,
    api-surface.md, spec-index.md, architecture-structure.md to the shipped
    surface. Exclusive helpers/budgets/sha256/media_caps stay pending B5.
    No behavior change to retained modules.
  files_hint: single atomic commit — 63 deletions + test_copy_ad.py surgery + config/urls.py mount/comment edit + new test_url_surface.py + 5 doc files; no deployable intermediate revision may exist with a mounted route pointing at deleted modules.
```

## B5 audit findings

Read-only audit of block B5 (P5 — Remove exclusive support), 2026-11-05. HEAD `e968a1dd`
(B4 landed: the `/api/v1/` mirror, route modules, adapters, `apps/api/`, `verify_parity`,
18 API test modules, and 16 newly-stale msgids are gone). Working tree: only this plan file
and `.ai/tmp/` scratch (untracked). Scope re-verified against §4 D21/D22/D23, §5 R05, §7 P5,
§9 "Hash/staging loss" row; every candidate was re-grepped at HEAD across `src/` (incl.
`src/telegram_bot`, templates; `src/benchmark` does not exist in this tree), `scripts/`,
`.github/workflows/`, `pyproject.toml`, `conftest.py`, Makefiles, and entrypoints.

### 1. Caller reachability — post-B4 verification (task 1)

All greps run at HEAD `e968a1dd`. **Zero retained callers exist for every candidate.**

| Candidate | Remaining references at HEAD | Verdict |
|---|---|---|
| `apps/core/utils/problem.py` | `api_auth.py:34` (intra-set import, both dying) + `core/tests/test_problem_response.py:24` (dedicated test, dying). No other hit in `src/`, scripts, workflows, docs, `.kilo/`. | DELETE |
| `apps/core/utils/api_auth.py` | `core/tests/test_api_auth.py:28` (dedicated test, dying) only. | DELETE |
| `RateLimitBudget.API_PUBLIC_READ` / `API_WRITE` | `core/enums.py` (docstring L47–53, members L61–62, `requests` table L73–74, `period` table L86–87) + `core/tests/test_rate_limit_budget.py` L87/L93 (the two dedicated tests). The enum **values** (`"api_public_read"`, `"api_write"`) appear nowhere else (no cache-key literal, no settings). | DELETE members + entries + tests |
| `submission.media_caps()` | Definition only (`submission.py:180–193`). Sole historical caller was `views/api/submit.py::_media_caps` (L134/L418/L457–464), deleted in B4. **No test ever referenced the symbol directly** (the deleted `test_submit_route_api.py` drove it through the endpoint; B3 recorded `TestDryRunInventory` as TRANSPORT-delete). | DELETE |
| `SubmittedPhoto.sha256` | Field def `apps/media/schemas.py:48–54` + read in `submission.py::staged_digests` (L336–347, the precedence branch). Sole historical populator: deleted `views/api/submit.py:300` (`sha256=image.sha256 or _disk_digest(image.image)`). Every remaining `SubmittedPhoto(...)` construction in `src/` (`test_filesystem.py` ×7, bot photo dicts, `test_submission.py` dict-coercion tests) uses `storage_key`/`thumbnail_*` only — **zero sources pass `sha256`** (also true of dict-form inputs; no `"sha256"` key anywhere). | DELETE field + branch |

Environment hazards carried over from B4 still apply (stray worktree
`docker/.kilo/worktrees/carefree-beast/`, no `git add -A`); no new one found.

### 2. `core/enums.py` budget surgery — exact map (task 2)

Five edit locations, all inside `RateLimitBudget` (no `_BUDGET_PROPERTIES` table exists —
the property tables are the two `@property` dict literals):

1. **Docstring "Budgets:" list** — remove the two API paragraphs (L47–53): the whole
   `API_PUBLIC_READ: 60 requests / 60 s. …` entry (4 lines incl. the `api_listings`/
   `api_search`/`api_detail`/`api_categories`/`api_cities` namespace continuation) and the
   whole `API_WRITE: 30 requests / 60 s. …` entry (3 lines incl. the `api_write` namespace
   continuation).
2. **Members** — `API_PUBLIC_READ = "api_public_read"` (L61), `API_WRITE = "api_write"` (L62).
3. **`requests` property table** — `RateLimitBudget.API_PUBLIC_READ: 60,` (L73) and
   `RateLimitBudget.API_WRITE: 30,` (L74).
4. **`period` property table** — `RateLimitBudget.API_PUBLIC_READ: 60,` (L86) and
   `RateLimitBudget.API_WRITE: 60,` (L87).

**Stays byte-identical:** `SEARCH_PAGE`/`AUTOCOMPLETE`/`DEEP_LINK_RENDER`/`LOGIN_ISSUE`/
`MEDIA_GATE` members, docstring paragraphs, table entries, and all 6 retained
`TestRateLimitBudgetTable` tests (`test_rate_limit_check_defaults_to_autocomplete_budget`,
`test_autocomplete_budget_equals_search_budget`, `test_deep_link_limiter_matches_its_budget`,
`test_login_limiter_matches_its_budget`, `test_media_gate_limiter_matches_its_budget`,
`test_budgets_are_the_reviewed_values`), plus `TestOneResponseShape` ×7,
`TestNamespaceIsolation`, `TestForwardedForRegressionGuard` — none references the API
members; the module/class docstrings need no edit.

**Dedicated tests to delete (exactly two, in `core/tests/test_rate_limit_budget.py`):**

- `TestRateLimitBudgetTable::test_api_public_read_budget_is_the_reviewed_value` (L85–89)
- `TestRateLimitBudgetTable::test_api_write_budget_is_the_reviewed_value` (L91–95)

Atomicity constraint: members and property entries must be removed together — a stale
dict entry naming a deleted member is an import-time `NameError`; a retained member without
its entry is a runtime `KeyError` on `.requests`/`.period`.

### 3. Digest restoration — exact contract (task 3, most important)

**Provenance:** `git log d2f6df33..HEAD -- submission.py schemas.py` is EMPTY — both files
are byte-identical to the `d2f6df33` migration commit. The full
`git diff d2f6df33^ HEAD` for the two files is **exactly** three additions (verified hunk
by hunk): `media_caps()`, the digest-precedence branch (+comment), and the `sha256` field
(+comment). Therefore restoration = byte-exact reverse of those hunks, and the strongest
acceptance check is: after B5, `git diff d2f6df33^ HEAD -- src/backend/apps/ads/services/submission.py
src/backend/apps/media/schemas.py` **must be empty** (both files byte-identical to the
pre-migration blobs `d538a09c`/`f4b6fc19`).

**Current (API-era) digest path in `submit_ad` (L326–347):** 12-line comment (incl. the
"A caller that already knows the digest … re-submitted DRAFT keeps its image set"
rationale) + comprehension that prefers `photo.sha256` when not `None`, else hashes the
staged key, else `None`, iterating `zip(input.photos, staged_keys, strict=True)`.

**Baseline (pre-`d2f6df33`) digest path — the restoration target, verbatim:**

```python
    # Capture the staged originals for the SHA-256 passed to AdImageService: under
    # deferred promotion the bytes are still at staging/<key>, so the digest must
    # come from the staged key captured above (03-DB-005).  The list keeps each
    # digest aligned with ``input.photos`` by index.
    staged_digests: list[str | None] = [
        FileHashService.calculate_sha256(
            os.path.join(settings.MEDIA_ROOT, staged_key)
        )
        if staged_key is not None
        else None
        for staged_key in staged_keys
    ]
```

(The baseline iterates `for staged_key in staged_keys` — safe without `zip`: `staged_keys`
is built from `input.photos` immediately above, same length by construction.)

**The precise edit set (three code hunks, nothing else in these files):**

1. `submission.py` — delete `media_caps()` (L180–193, def + 13-line docstring + body +
   trailing blank separators; the `_get_cached_criteria` deferred import dies with it —
   after removal that private symbol is again referenced only inside `apps/moderation`
   plus `testing/moderation_fixtures.py` patches, exactly the R05 intent).
2. `submission.py` — replace the 12-line comment + precedence comprehension with the
   baseline 4-line comment + comprehension above. Everything around it is untouched:
   `staged_keys`/`read_paths` capture, `plan_staging_promotion`, the pre-tx thumbnail
   pipeline, `sha256=staged_digests[index]` at the `AdImageService.create_or_skip` call
   (L414), the `created.image != photo.storage_key` reclaim test (L424), the
   `transition_to` refusal early return, `auto_moderate` delegation, both
   `transaction.on_commit` callbacks (`reclaim_staged_keys` prune ordering L452–478) —
   the full on-commit lifecycle.
3. `schemas.py` — delete the field block (6-line comment + `sha256: str | None = None`,
   L48–54). `SubmittedPhoto` survives with `storage_keys()` and its module docstring
   intact; `filesystem.plan_staging_promotion`'s `list[SubmittedPhoto]` signature is
   unaffected.

**Preserved by construction (R05/§9 checklist, all pre-existing — `d2f6df33` touched none
of them):** `AdImage.sha256` (`apps/ads/models.py:648`), `AdImage.save()`'s
file-based fallback (models.py L711–740), `FileHashService.calculate_sha256`
(`apps/media/services/hash_service.py:12–25`), `AdImageService.create_or_skip` with its
`sha256: str | None = None` param, `_compute_sha256` ""-on-missing guard, per-ad
`.filter(ad=ad, sha256=digest).order_by("pk")` dedup and skip-log
(`apps/ads/services/images.py` — the whole file is byte-untouched by B5), staging prefix
re-queue `_permanent_thumbnail_key`, `reclaim_staged_keys`, `promote_media_files`, and
both commit callbacks.

**Behavior delta analysis:** for every live input, the precedence branch already reduces
to baseline (nothing supplies `photo.sha256`; Pydantic defaults it to `None`), so the
restore changes no observable behavior on any live bot/web path. The only post-B5 delta
is for a hypothetical caller passing `sha256=`: `BaseInputModel` sets
`model_config = ConfigDict(extra="forbid")`, so it now fails loudly at DTO construction
instead of being honored — the intended API-era removal, and the loud failure is itself
protection against silent digest divergence (a missed populator raises `ValidationError`,
it does not silently re-hash).

### 4. `media_caps()` removal (task 4)

- Current callers: **zero** (definition-only; verified by full-tree grep).
- Current tests referencing it: **zero**. The referencing tests were exactly the deleted
  API submit tests (B4's `test_submit_route_api.py` readiness/`TestDryRunInventory`
  classes, recorded as TRANSPORT-delete in B3 with "no ports"). Nothing remains to
  retarget or delete in test files for this symbol.
- Consequence worth noting: `_get_cached_criteria` and the moderation tuple's index
  layout (indices 5/6 = min/max images, documented in
  `testing/moderation_fixtures.py:25–32`) cease to have any consumer outside
  `apps/moderation` + the fixtures — the "private tuple index read" smell R05 flagged is
  gone with the function.

### 5. i18n — msgids becoming source-unreferenced (task 5)

`test_reverse_stale_entry_gate` (`apps/ads/tests/test_i18n_completeness.py:1785`) is
strict: it extracts msgids in-process (Python AST over `settings.BASE_DIR` + full-root
template scan, `_real_extraction_msgids`) and fails per catalog on any msgid absent from
that extraction, with **no exemptions**. Once B5 deletes `problem.py`/`api_auth.py`, their
16 msgids vanish from the extraction, so **B5 must prune them from ru/bs/en in the same
commit** — exactly the B4 procedure (its commit `e968a1dd` pruned 16 msgids / 64 lines
per catalog).

| # | msgid | Last source |
|---|---|---|
| 1 | `Bad Request` | problem.py L59 (`_STATUS_TITLES`) |
| 2 | `Unauthorized` | problem.py L60 |
| 3 | `Forbidden` | problem.py L61 |
| 4 | `Not Found` | problem.py L62 |
| 5 | `Method Not Allowed` | problem.py L63 |
| 6 | `Conflict` | problem.py L64 |
| 7 | `Unprocessable Entity` | problem.py L65 |
| 8 | `Too Many Requests` | problem.py L66 |
| 9 | `Service Unavailable` | problem.py L67 |
| 10 | `Internal Server Error` | problem.py L68 |
| 11 | `Error` | problem.py L85 (`_title_for` fallback) |
| 12 | `Request body failed validation.` | problem.py L146 |
| 13 | `Too many requests; retry after the indicated delay.` | problem.py L173 |
| 14 | `Authentication required.` | api_auth.py L73 + L150 |
| 15 | `Staff access required.` | api_auth.py L156 |
| 16 | `Method not allowed.` | api_auth.py L162 |

Catalog locations (verified reads of all three tails): the 16 entries form the **file
tail** in every catalog — ru L1752–1816, bs L1733–1796, en L1570–1633 — a clean 64-line
tail cut per catalog (15 entries at 4 lines + `Method not allowed.` at 5: it carries a
second, already-stale location comment for the B4-deleted
`analytics/views/api/seller.py`; the whole entry dies). en msgstrs are empty as expected;
ru/bs carry real translations, none of which is `c2f130dd`'s shared Bosnian fix (the
preserved shared strings from B4's §9 are untouched by this set).

Re-verification already done for **shared-string risk**: no retained `_()`/`gettext`/
`gettext_lazy` call and no `{% trans %}`/`{% blocktrans %}` in any template references
any of the 16. The near-collisions are distinct msgids: the legacy
`staff_required_api` decorator emits gettext-free literals `{"error": "Authentication
required"}` / `{"error": "Staff access required"}` (`moderation/views/decorators.py:55/57`,
**no trailing period**, not wrapped in `gettext`) — retained, unaffected, and NOT this
msgid; `test_download_seed_photos.py:220`'s `text="Unauthorized"` is a mock body, not an
extraction source. Forward direction stays green too: `test_extraction_completeness`
only requires present-in-catalog for msgids still in source, and these leave the source
in the same commit. Optional cross-check per `.kilo/rules/commands.md`: the whole-tree
scratch extraction; the hand-prune stays authoritative-enumerated (B4 precedent).

### 6. Docs/docstrings — B5 same-commit vs B7 (task 6)

| Reference | B5 or B7 | Exact change |
|---|---|---|
| `docs/01-spec/api-surface.md` L36–38 | **B5** | The "the RFC 9457 `problem.py` helper is used only by the moderation bulk endpoint's 422 shape" clause is already false post-B4 (bulk's 422 comes from `pydantic_errors_json` in `sanitize.py`, as its own L83 correctly states) and B5 deletes the module. Remove the clause from the "Errors" bullet; L83 (naming `sanitize.py`) stays as is. |
| `core/enums.py` budget docstring, `submission.py` digest comment, `schemas.py` field comment, `media_caps` docstring, the 2 budget tests' docstrings | **B5** (code-adjacent, die/get restored with their hunks) | No separate doc edits. |
| ru/bs/en catalogs | **B5** | The 16-entry tail prune (§5 above). |
| `.kilo/rules/project.md` L53 (rule 16 "RFC 9457 for API Errors") | **B7** | User-owned rule doc; plan P7 says scope error-format guidance to maintained APIs, not retrofit legacy shapes. B5 must not touch it (bulk-action JSON remains an RFC 9457-consumable surface; the rule as written is policy, not a claim about `problem.py`). |
| 14 retained files' "future `/api/v1/`" docstring commentary (B4 §2 list) | **B7** | Unchanged by B5; none references `media_caps`/`sha256` field/budgets (verified). |
| `docs/01-spec/i18n-spec.md` L414 + `docs/99-agent/rules.md` L258/L278 (`_EXTRACTION_GAP_MSGIDS` description vs the retired exemption) | **B7** | Pre-existing staleness, unrelated to B5 symbols — flag only. |
| `docs/99-agent/*` (architecture.md L353 lists `SubmittedPhoto` among `BaseInputModel` DTOs) | **no edit** | Still accurate — the DTO survives; only an optional field dies. |
| `docs/01-spec/technical-specification.md` L251/271, `db-indexes.md` L310 | **no edit** | Document `AdImageService.create_or_skip`/`AdImage.sha256` dedup — pre-existing behavior B5 preserves. |
| `.ai/` plan/audit records | never | Process/historical files, untouched. |

### 7. Risks, behavior-change analysis, and protected neighbors (task 7)

1. **Submission/media behavior risk — NONE for live paths, one loud-failure delta by
   design** (§3 above). The one real engineering risk is over-deletion (§9 "Hash/staging
   loss"): if the staged hashing went with the precedence branch,
   `create_or_skip(sha256=None)` → `_compute_sha256(permanent_key)` → `""` under deferred
   promotion → `if digest:` no-ops dedup for **every** staged submission. The tripwire is
   `test_dedup_survives_deferred_promotion` (asserts `first_image.sha256 == <digest of the
   staged bytes>` and that a second identical submission skips) — it fails loudly if the
   restoration is wrong in either direction.
2. **Retained imports of the helpers: zero.** The only import edge is
   `api_auth → problem` (both dying) plus each one's dedicated test (both dying).
   `moderation/views/decorators.py::staff_required_api` and
   `core/utils/rate_limit_response.py` are NOT importers (name-pair hazard noted in B4 §7.1
   — delete by explicit path, never a glob).
3. **`pydantic_errors_json` / `sanitize.py`: NOT affected.** Retained callers enumerated:
   `apps/core/views.py:17/213` (preferred-city 422) and `apps/moderation/views/api_bulk.py:20/78`
   (preserved bulk endpoint). `problem.py` was a third importer; its import dies with it.
4. **`rate_limit_response.py`: NOT affected.** It defines its OWN
   `RETRY_AFTER_HEADER` (L19) — no import from `problem.py`. Retained callers: consent.py,
   search.py, autocomplete.py, listings.py, core/views.py + the whole retained
   `TestOneResponseShape` suite. The only dying importer is
   `test_problem_response.py::test_legacy_renderer_untouched`'s comparison test (dies with
   its file; the legacy renderer's own proof lives in `test_rate_limit_budget.py`).
5. **Budget-edition atomicity:** §2 member/entry pairs must change together (import-time
   `NameError` / runtime `KeyError` otherwise). No retained test iterates the full enum
   (`for budget in RateLimitBudget:` exists only in the dying
   `test_problem_response.py`), so no iteration breaks mid-commit.
6. **i18n gate risk is inverted vs B4's note:** pruning is mandatory this time — the
   reverse gate makes unreferenced entries a hard failure in the fast gate. The prune risk
   is the shared-string/Bosnian class of mistake; §5 verified all 16 as exclusive (py +
   templates), and none of B4's 3 shared strings is in the set.
7. **Test-count optics:** B5 removes 36 `def test_` functions (16 + 18 + 2), zero of which
   encodes a retained invariant — they pin the dying helpers/members themselves. The
   retained staged-media/dedup/lifecycle matrix is enumerated in §8 and must be green
   byte-unchanged.
8. **No schema/settings/env/middleware/dependency/lockfile delta.** `SubmittedPhoto.sha256`
   is a Pydantic DTO field, not a model column; `AdImage.sha256` is untouched
   (`makemigrations --check` stays clean). No build/CI wiring references any deleted file
   (pyproject/conftest/Makefiles/entrypoints/workflows greps clean; B4's
   `test_url_surface.py` guard references nothing B5 touches).

### 8. Per-symbol removal list, test inventory, and verification

**Removal list (one atomic commit; intra-commit order = staging safety net):**

| Seq | File/symbol | Action |
|---|---|---|
| 1 | `src/backend/apps/core/tests/test_api_auth.py` (16 tests) | delete |
| 2 | `src/backend/apps/core/tests/test_problem_response.py` (18 tests) | delete |
| 3 | `src/backend/apps/core/utils/api_auth.py` (181 lines) | delete (importer first) |
| 4 | `src/backend/apps/core/utils/problem.py` (188 lines) | delete |
| 5 | `src/backend/apps/core/enums.py` | remove 2 members, 2 docstring blocks, 4 property-table lines (§2) |
| 6 | `src/backend/apps/core/tests/test_rate_limit_budget.py` | remove the 2 dedicated tests (§2) |
| 7 | `src/backend/apps/ads/services/submission.py` | delete `media_caps()` + restore baseline digest comprehension & comment (§3) |
| 8 | `src/backend/apps/media/schemas.py` | delete `sha256` field + comment (§3) |
| 9 | `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | prune the 16-entry tail (§5; 64 lines each) |
| 10 | `docs/01-spec/api-surface.md` | remove the L36–38 problem.py clause (§6) |

**Tests that must stay green byte-unchanged (the staged hashing/dedup/staging/promotion
matrix + gates):**

- `apps/ads/tests/test_submission.py` — reclaim/dedup suite:
  `test_intra_submission_duplicate_reclaims_all_four_staged_files`,
  `test_rollback_leaves_skipped_photo_staged_and_promotes_nothing`,
  `test_invalid_transition_does_not_reclaim_skipped_files` (pre-creates a matching-digest
  row → staged hashing drives the skip),
  `test_moderation_failure_still_reclaims_skipped_files`,
  `test_reclaim_failure_leaves_skipped_file_staged_not_promoted`; plus
  `test_missing_staged_file_reports_a_recoverable_error` and
  `TestSubmitAdStorageConsentGate` (refusal precedes the staged plan).
- `apps/ads/tests/test_ad_image_service.py::TestAdImageServiceCreateOrSkip` (5 tests —
  hash-on-create, same-user duplicate skip, different-user new row, missing-file empty
  hash, per-ad scoping).
- `apps/media/tests/test_adimage_sha256.py::TestAdImageSaveSha256` (5 tests, incl.
  `test_sha256_not_recomputed_on_insert_when_explicitly_passed` — the model-level
  explicit-digest path B5 preserves; and `test_sha256_matches_file_hash_service`).
- `apps/media/tests/test_filesystem.py` — `TestPlanStagingPromotion` ×5,
  `TestPromoteMediaFiles` ×4, `TestReclaimStagedKeys` ×3 (its `SubmittedPhoto(...)`
  constructions never pass `sha256`).
- `src/telegram_bot/tests/test_save_photo_integration.py` — `TestSubmitAdStagingMove`:
  `test_dedup_survives_deferred_promotion` (THE staged-digest tripwire),
  `test_files_are_not_promoted_before_the_row_commits`,
  `test_submit_ad_moves_staging_to_permanent`,
  `test_submit_ad_rollback_leaves_files_in_staging`;
  `TestSavePhotoThumbnailsIntegration` (permanent-key photos → `AdImage.save()` on-disk
  fallback digest and thumbnail null-on-failure).
- `apps/core/tests/test_rate_limit_budget.py` — retained 6 budget tests + shape suites.
- `apps/ads/tests/test_i18n_completeness.py` — `test_reverse_stale_entry_gate` and
  `test_extraction_completeness` (the prune's own green proof); forward direction unaffected.

**Verification commands (B5's focused tier before the fast gate):**
`test_submission.py`, `test_ad_image_service.py`, `test_adimage_sha256.py`,
`test_filesystem.py`, `test_rate_limit_budget.py`, `test_i18n_completeness.py`,
`test_save_photo_integration.py` (bot tier), then `uv run ruff check src/`,
`uv run basedpyright src/`, `.\Makefile.ps1 test`, and the dev-container
`makemigrations --check --dry-run` (no schema delta). Acceptance extra to B4's G5 sweep:
`API_PUBLIC_READ|API_WRITE`, `media_caps`, `core\.utils\.problem|core\.utils\.api_auth`,
and `photo\.sha256` greps must be zero over `src/`; expected residue is only
`AdImage`-level `sha256` references (models/service/tests/docstrings) and the
`/moderation/api/v1/` legacy path. Strongest single check: the post-edit diff against
`d2f6df33^` for the two restored files is empty.

## B5 task description

```yaml
id: b5_remove_exclusive_support

title: >
  P5 — Remove exclusive support: delete the API-only problem/auth helpers and
  their dedicated tests, retire the two API rate budgets, remove
  submission.media_caps and the API-supplied digest path (restoring the
  baseline staged-digest computation byte-exactly), prune the 16 newly-stale
  catalog msgids, and drop the now-false problem.py doc clause — one atomic
  commit.

priority: medium

type: implementation

depends_on:
  - "b4_retire_api_surface landed (HEAD e968a1dd): the /api/v1/ mirror, route modules, adapters, apps/api, verify_parity, and 18 API test modules are gone; post-B4 re-verification shows zero retained callers for every B5 candidate — re-grep each candidate immediately before its edit (plan P5 'Check caller reachability before each deletion')"

source_reference: .ai/plans/architecture-correction-plan.md
source_section: >
  §4 D21 (Problem renderer/auth variants) · §4 D22 (API rate budgets) ·
  §4 D23 (API-only shared submission additions) · §5 R05 (Are submission/media
  additions independent improvements?) · §7 P5 — Remove exclusive support ·
  §8 G5 (removal consistency) / G6 (static/docs/i18n) / G7 (no infrastructure
  rollback) · §9 risk row "Hash/staging loss"
source_file: .ai/plans/architecture-correction-execution.md
source_blocks:
  - "B5 audit findings"   # §1 caller reachability · §2 enums map · §3 digest
                         #   contract · §4 media_caps · §5 i18n · §6 docs split ·
                         #   §7 risks/neighbors · §8 removal list & verification

extra_context: |
  Provenance of the two restored files (audit §3, verified at e968a1dd):
  `git log d2f6df33..HEAD -- src/backend/apps/ads/services/submission.py
  src/backend/apps/media/schemas.py` is EMPTY — both files are byte-identical
  to the d2f6df33 migration commit, and the full `git diff d2f6df33^ HEAD` over
  them is EXACTLY three additions: `media_caps()`, the digest-precedence branch
  (with its rationale comment), and the `SubmittedPhoto.sha256` field (with its
  comment). Restoration is therefore the byte-exact reverse of those hunks.
  Take the restored bytes from `git show d2f6df33^:<path>` — never retype them;
  the pre-migration blobs are the byte authority.

  Behavior delta (audit §3/§7.1): for every live input the precedence branch
  already reduces to baseline — nothing supplies `photo.sha256` (every retained
  `SubmittedPhoto(...)` construction and every dict form uses only
  `storage_key`/`thumbnail_*`; zero `"sha256"` keys exist anywhere in src/), and
  Pydantic defaults it to None — so the restore changes NO observable bot/web
  behavior. The one post-B5 delta is by design: a hypothetical caller passing
  `sha256=` now fails LOUDLY at DTO construction (`BaseInputModel` sets
  `model_config = ConfigDict(extra="forbid")` → `ValidationError`) instead of
  being honored — a missed populator raises, it does not silently re-hash.

  i18n is MANDATORY in the same commit (audit §5): the reverse gate
  `apps/ads/tests/test_i18n_completeness.py::test_reverse_stale_entry_gate` is
  strict — it extracts msgids in-process (Python AST over settings.BASE_DIR +
  full-root template scan) and fails per catalog on any msgid absent from that
  extraction, with NO exemptions. Once problem.py/api_auth.py are deleted their
  16 msgids leave the extraction set; an unpruned catalog fails the fast gate.
  B4 set the precedent (commit e968a1dd pruned 16 msgids / 64 lines per catalog
  via surgical entry removal, no makemessages). The prune risk class is the
  shared-string/Bosnian mistake: all 16 were verified exclusive to the two
  dying modules (py + templates), and none of B4's preserved shared strings nor
  c2f130dd's Bosnian script repair is in the set.

  Environment hazards carried from B4 (audit §1): the stray ignored worktree
  docker/.kilo/worktrees/carefree-beast/ holds stale api/v1-era copies on disk
  — never `git add -A`, never a broad glob; stage via this task's explicit
  file list only.

description: >
  ONE atomic commit removing the API-exclusive support the retired /api/v1/
  surface left behind (plan D21/D22/D23, R05): the core/utils/problem.py and
  core/utils/api_auth.py helpers and their two dedicated test modules (36 test
  functions, every one pinning a dying symbol); the RateLimitBudget.API_PUBLIC_READ
  and API_WRITE members together with their docstring rationale lines, their
  entries in both property tables, and their two dedicated tests;
  submission.media_caps() (sole historical caller died in B4 — the private
  moderation tuple-index read R05 flagged goes with it); and the optional
  SubmittedPhoto.sha256 field with the digest-precedence branch, restoring the
  baseline staged-digest computation verbatim so submission.py and schemas.py
  come out byte-identical to the pre-migration blobs. Prune the 16 newly
  source-unreferenced msgids from ru/bs/en (each is the clean catalog tail) and
  remove the now-false problem.py clause from docs/01-spec/api-surface.md.
  Zero behavior change to any retained path: original staged hashing/dedup/
  staging/promotion and both on-commit callbacks; legacy auth/429 helpers and
  the moderation bulk surface; all five retained budgets; no schema, settings,
  dependency, or lockfile delta.

goals:
  - the two helper modules and their two test modules are gone, with zero
    surviving executable references anywhere in src/ (G5)
  - RateLimitBudget declares exactly its five original members with a
    consistent docstring and property tables, import-clean and lookup-clean;
    the retained budget/shape suites stay green byte-unchanged
  - submission.py and media/schemas.py are byte-identical to d2f6df33^
    (acceptance: empty `git diff d2f6df33^ HEAD --` over both files)
  - every retained staged-media/dedup/promotion/lifecycle invariant stays
    green byte-unchanged, first among them the staged-digest tripwire
    (bot test_dedup_survives_deferred_promotion)
  - each of ru/bs/en catalogs loses exactly its 16-entry API tail; both i18n
    gate directions (extraction completeness and reverse stale-entry) pass
  - no schema/migration/settings/env/middleware/dependency/lockfile delta
    (makemigrations --check stays clean) and no retained-module behavior
    change (G7)

# ─────────────────────────────────────────────────────────────────────────────
# Deletions — explicit paths only, never a glob or name-prefix match
# ─────────────────────────────────────────────────────────────────────────────

deletions:
  # sequence step 1 — leaves first: the dedicated tests, then api_auth.py
  # (the only importer of problem.py), then problem.py
  helper_tests:                       # pin the dying helpers; zero other refs
    - src/backend/apps/core/tests/test_api_auth.py          # 16 tests
    - src/backend/apps/core/tests/test_problem_response.py  # 18 tests (incl. the only full-enum iteration `for budget in RateLimitBudget:`)
  helper_modules:                     # intra-set edge: api_auth.py → problem.py
    - src/backend/apps/core/utils/api_auth.py                # 181 lines; delete BEFORE problem.py (importer first)
    - src/backend/apps/core/utils/problem.py                # 188 lines
  # Re-verify reachability immediately before each deletion (audit §1, B4-repeated):
  # repo-wide grep over src/ (incl. src/telegram_bot, templates), scripts/, .github/workflows/,
  # pyproject.toml, conftest.py, Makefiles, docker/ entrypoints for the import paths
  # "core.utils.problem" / "core.utils.api_auth" — expected hits BEFORE the deletions:
  # api_auth→problem (intra-set, both dying) + each module's own dying test file. NOTHING else.

# ─────────────────────────────────────────────────────────────────────────────
# Files and semantic targets (symbols only — line numbers are HEAD hints)
# ─────────────────────────────────────────────────────────────────────────────

files:

  # ── 1. Budget enum surgery ─────────────────────────────────────────────────
  - path: src/backend/apps/core/enums.py
    targets:
      - type: docstring
        name: RateLimitBudget "Budgets:" rationale list
        change: remove the two API paragraphs — the whole `API_PUBLIC_READ:
          60 requests / 60 s. …` entry (4 lines incl. the api_listings/
          api_search/api_detail/api_categories/api_cities key-namespace
          continuation) and the whole `API_WRITE: 30 requests / 60 s. …`
          entry (3 lines incl. the single api_write namespace continuation).
          The five retained paragraphs and every other docstring line stay
          byte-identical.
      - type: enum_member
        name: RateLimitBudget.API_PUBLIC_READ   # "api_public_read"
        action: delete
      - type: enum_member
        name: RateLimitBudget.API_WRITE        # "api_write"
        action: delete
      - type: dict_entry
        name: requests property table
        change: remove `RateLimitBudget.API_PUBLIC_READ: 60,` and
          `RateLimitBudget.API_WRITE: 30,` from the requests property's
          dict literal
      - type: dict_entry
        name: period property table
        change: remove `RateLimitBudget.API_PUBLIC_READ: 60,` and
          `RateLimitBudget.API_WRITE: 60,` from the period property's
          dict literal
    semantic_anchors:
      atomicity: >
        All targets above change in ONE atomic edit: a stale property-table
        entry naming a deleted member is an import-time NameError; a retained
        member without its entry is a runtime KeyError on .requests/.period.
        The enum VALUES ("api_public_read"/"api_write") appear nowhere else
        (no cache-key literal, no settings) — removing the members leaves no
        dangling string keys.
      keep_unchanged:
        - RateLimitBudget members SEARCH_PAGE / AUTOCOMPLETE / DEEP_LINK_RENDER
          / LOGIN_ISSUE / MEDIA_GATE with their docstring paragraphs and both
          property-table entries (byte-identical)
        - the requests/period property docstrings and dict ordering of the
          five retained rows
        - every other symbol in the module byte-identical (AdSort, AdvisoryLockId,
          AdStatus, SEEDABLE_AD_STATUSES, AdSource, AnalyticsEventType,
          BulkModeration*, the LanguageLocale FTS mappings, __all__, etc.)

  # ── 2. Budget dedicated tests ──────────────────────────────────────────────
  - path: src/backend/apps/core/tests/test_rate_limit_budget.py
    targets:
      - type: test
        name: TestRateLimitBudgetTable.test_api_public_read_budget_is_the_reviewed_value
        action: delete_symbol
      - type: test
        name: TestRateLimitBudgetTable.test_api_write_budget_is_the_reviewed_value
        action: delete_symbol
    semantic_anchors:
      keep_unchanged:      # none of these references the API members — audit §2
        - test_rate_limit_check_defaults_to_autocomplete_budget
        - test_autocomplete_budget_equals_search_budget
        - test_deep_link_limiter_matches_its_budget
        - test_login_limiter_matches_its_budget
        - test_media_gate_limiter_matches_its_budget
        - test_budgets_are_the_reviewed_values
        - TestOneResponseShape (all 7 tests) / TestNamespaceIsolation /
          TestForwardedForRegressionGuard (rate_limit_response.py's own proof
          lives here once its problem.py comparison twin dies with
          test_problem_response.py)
        - the module docstring and every fixture/import line still referenced

  # ── 3. Submission service — the RESTORATION contract (highest risk) ──────
  - path: src/backend/apps/ads/services/submission.py
    targets:
      - type: function
        name: media_caps
        action: delete_symbol            # def + 13-line docstring + body incl.
                                          # the deferred `from
                                          # apps.moderation.services.auto_moderation
                                          # import _get_cached_criteria`; remove the
                                          # function plus one surrounding blank-line
                                          # pair so PEP 8 two-blank separation between
                                          # _permanent_thumbnail_key and submit_ad
                                          # is preserved
      - type: code_block
        name: submit_ad staged-digest capture (the `staged_digests` comprehension
          and its 12-line comment: the API-era "A caller that already knows the
          digest … re-submitted DRAFT keeps its image set" precedence paragraph)
        action: replace_with_baseline
    semantic_anchors:
      baseline_byte_authority: >
        `git show d2f6df33^:src/backend/apps/ads/services/submission.py` — the
        pre-migration blob. The replaced block must be copied verbatim from it.
        The baseline iterates `for staged_key in staged_keys` (safe without zip:
        staged_keys is built from input.photos immediately above, same length
        by construction).
      keep_unchanged:
        - SubmitAdOutcome / SubmitAdResult / SubmitAdInput and their docstrings
        - _permanent_thumbnail_key (staging-prefix strip + permanent_keys re-queue)
        - the staged_keys/read_paths capture and the
          `zip(input.photos, staged_keys, strict=True)` read-path comprehension
        - the plan_staging_promotion call + FileNotFoundError →
          PHOTO_UNAVAILABLE early return (the ONE existence rule)
        - the pre-transaction thumbnail pipeline
        - the `sha256=staged_digests[index]` argument at the
          AdImageService.create_or_skip call site
        - the `created.image != photo.storage_key` reclaim test
        - the locked re-fetch, DRAFT_GONE, transition refusal early return,
          and auto_moderate delegation inside transaction.atomic()
        - both transaction.on_commit callbacks with their
          reclaim/prune ordering (reclaim_staged_keys / promote_media_files)

  # ── 4. Media DTO ──────────────────────────────────────────────────────────
  - path: src/backend/apps/media/schemas.py
    targets:
      - type: field
        name: SubmittedPhoto.sha256
        action: delete_symbol            # the 6-line "Pre-computed SHA-256 …"
                                          # comment AND the `sha256: str | None =
                                          # None` field line; after removal
                                          # `thumbnail_large` is again the last
                                          # field before storage_keys()
    semantic_anchors:
      keep_unchanged:
        - the module docstring (the leaf-module import contract)
        - SubmittedPhoto fields storage_key / telegram_file_id / position /
          thumbnail_small / thumbnail_medium / thumbnail_large
        - SubmittedPhoto.storage_keys() (byte-identical)
        - __all__ and both import lines
        - apps/media/services/filesystem.py::plan_staging_promotion's
          `list[SubmittedPhoto]` signature (unaffected: the field deletion
          does not touch that module)

  # ── 5. Catalog tails — the 16-entry i18n prune ────────────────────────────
  - path: src/backend/locale/ru/LC_MESSAGES/django.po
    targets:
      - type: catalog_block
        name: the contiguous 16-entry API tail (from the first entry whose
          `#:` location comment names src/backend/apps/core/utils/api_auth.py —
          "Authentication required." — through EOF; ~L1752–1815 at HEAD)
        action: remove_entries   # exactly the 16 msgids enumerated in
                                # changes.i18n_prune; nothing above the tail
                                # changes
  - path: src/backend/locale/bs/LC_MESSAGES/django.po
    targets:
      - type: catalog_block
        name: the same 16-entry tail (~L1733–1796 at HEAD)
        action: remove_entries
  - path: src/backend/locale/en/LC_MESSAGES/django.po
    targets:
      - type: catalog_block
        name: the same 16-entry tail (~L1570–1633 at HEAD; en msgstrs are
          empty as expected — en may carry empty msgstr)
        action: remove_entries

  # ── 6. Docs — the one same-commit clause ───────────────────────────────────
  - path: docs/01-spec/api-surface.md
    targets:
      - type: doc_clause
        name: the Errors bullet's problem.py claim ("the RFC 9457 `problem.py`
          helper is used only by the moderation bulk endpoint's 422 shape";
          the "Errors:" bullet in Main Concepts, ~L36–38 at HEAD)
        action: remove_clause    # already false post-B4 (bulk's 422 comes from
                                 # pydantic_errors_json in sanitize.py, as the
                                 # file's own later bulk row correctly states)
                                 # and B5 deletes the module. The rest of the
                                 # Errors bullet and the later sanitize.py
                                 # naming stay byte-identical. Everything else
                                 # in docs/ is B7.

  # ── 7. Explicit DO-NOT-TOCH neighbors (verified retention inventory) ──────
  - path: src/backend/apps/core/utils/rate_limit_response.py
    semantic_anchors:
      reason: >
        NOT an importer of problem.py — it defines its OWN RETRY_AFTER_HEADER.
        Retained callers: consent.py, search.py, autocomplete.py,
        listings.py, core/views.py + the retained TestOneResponseShape suite.
        Its proof twin in test_problem_response.py dies with that file; this
        module and its own code stay byte-untouched. The name-pair hazard with
        problem.py is why deletions use explicit paths only.
  - path: src/backend/apps/core/utils/sanitize.py
    semantic_anchors:
      reason: >
        pydantic_errors_json's retained callers: apps/core/views.py
        (preferred-city 422) and apps/moderation/views/api_bulk.py (the
        preserved bulk endpoint's 422). problem.py was a third importer; that
        import dies with problem.py. No edit to sanitize.py.
  - path: src/backend/apps/ads/services/images.py
    semantic_anchors:
      reason: >
        AdImageService.create_or_skip with its `sha256: str | None = None`
        parameter, the _compute_sha256 ""-on-missing guard, and the per-ad
        `.filter(ad=ad, sha256=digest).order_by("pk")` dedup + skip log. The
        whole file is byte-untouched by B5 (verified: d2f6df33 touched none of
        it, and the empty-diff acceptance covers the two files it did touch).
  - path: src/backend/apps/ads/models.py
    semantic_anchors:
      reason: >
        AdImage.sha256 field and AdImage.save()'s file-based fallback digest
        (the model-level explicit-digest path pinned by
        TestAdImageSaveSha256::test_sha256_not_recomputed_on_insert_when_explicitly_passed) —
        pre-existing behavior R05/§9 require preserved.
  - path: src/backend/apps/media/services/hash_service.py
    semantic_anchors:
      reason: FileHashService.calculate_sha256 — the digest producer the
        restored comprehension calls; byte-untouched.
  - path: src/backend/apps/media/services/filesystem.py
    semantic_anchors:
      reason: >
        plan_staging_promotion / reclaim_staged_keys / promote_media_files and
        the staging-existence rule; its `list[SubmittedPhoto]` signature is
        unaffected by the DTO field deletion. Byte-untouched.
  - path: src/backend/apps/moderation
    semantic_anchors:
      reason: >
        _get_cached_criteria returns to moderation-private use (its consumers
        are again only inside apps/moderation plus
        testing/moderation_fixtures.py patches, exactly R05's intent). Do not
        edit the tuple index layout, its fixtures documentation
        (indices 5/6 = min/max images), or
        apps/moderation/views/decorators.py::staff_required_api. NEVER delete
        apps/moderation/views/api_bulk.py — the legacy bulk endpoint.
  - path: src/backend/apps/moderation/views/decorators.py
    semantic_anchors:
      reason: >
        staff_required_api emits gettext-free literals `{"error": "Authentication
        required"}` / `{"error": "Staff access required"}` — NO trailing period,
        NOT wrapped in gettext, hence distinct msgids that are not in the prune
        set; retained, byte-untouched.
  - path: src/backend/testing/moderation_fixtures.py
    semantic_anchors:
      reason: taxonomy-period fixtures patching _get_cached_criteria;
        byte-untouched.
  - path: .ai/plans + .kilo/rules
    semantic_anchors:
      reason: >
        planning/process records stay untouched; in particular
        .kilo/rules/project.md's rule 16 (RFC 9457) is user-owned policy text
        and stays verbatim (bulk-action JSON remains an RFC 9457-consumable
        surface); commands.md edits are B7's.

# ─────────────────────────────────────────────────────────────────────────────
# Changes with code hints
# ─────────────────────────────────────────────────────────────────────────────

changes:

  - action: restore_baseline_block
    target: apps/ads/services/submission.py::staged_digests
    description: >
      Replace the 12-line API-era comment + the photo.sha256-precedence
      comprehension (which iterates `zip(input.photos, staged_keys,
      strict=True)`) with the baseline 4-line comment + comprehension below,
      copied byte-exactly from `git show d2f6df33^:<path>`. Everything around
      the block is untouched (semantic_anchors keep_unchanged list).
    code_hint: |
      # Capture the staged originals for the SHA-256 passed to AdImageService: under
      # deferred promotion the bytes are still at staging/<key>, so the digest must
      # come from the staged key captured above (03-DB-005).  The list keeps each
      # digest aligned with ``input.photos`` by index.
      staged_digests: list[str | None] = [
          FileHashService.calculate_sha256(
              os.path.join(settings.MEDIA_ROOT, staged_key)
          )
          if staged_key is not None
          else None
          for staged_key in staged_keys
      ]
    acceptance: >
      git diff d2f6df33^ HEAD -- src/backend/apps/ads/services/submission.py
      src/backend/apps/media/schemas.py is EMPTY after the edit (both files
      byte-identical to the pre-migration blobs; pre-check
      `git log d2f6df33..HEAD -- <the two files>` is empty before editing).

  - action: prune_enum_members
    target: apps/core/enums.py::RateLimitBudget
    description: >
      The four atomic edits under files[0] (docstring rationale paragraphs,
      two members, two property-table rows each) plus the two dedicated test
      deletions in test_rate_limit_budget.py — one coherent atomicity unit.
    code_hint: |
      # Budgets: list ends at MEDIA_GATE's paragraph in the docstring;
      # member list ends at MEDIA_GATE = "media_gate";
      # requests table ends at RateLimitBudget.MEDIA_GATE: 240,
      # period table ends at RateLimitBudget.MEDIA_GATE: 60,

  - action: i18n_prune
    target: src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po
    description: >
      Same commit, procedure identical to the B4 precedent (commit e968a1dd):
      the gate is the authority; per-msgid grep verification; surgical entry
      removal (plain text edits of the three tracked catalogs — NEVER
      makemessages/msgmerge against the tracked tree, NEVER a whole-catalog
      restore); parser validation; preserve shared strings and c2f130dd's
      Bosnian script repair. The 16 entries form the clean contiguous file
      tail in each catalog (~64 lines; 15 entries at 4 lines + `Method not
      allowed.` at 5 — its second `#:` location line, the stale
      analytics/views/api/seller.py reference for a B4-deleted module, dies
      with the whole entry).
    msgids:                           # EXACT set — nothing else may be pruned
      - "Bad Request"                                     # problem.py _STATUS_TITLES
      - "Unauthorized"                                   # problem.py _STATUS_TITLES
      - "Forbidden"                                      # problem.py _STATUS_TITLES
      - "Not Found"                                      # problem.py _STATUS_TITLES
      - "Method Not Allowed"                             # problem.py _STATUS_TITLES
      - "Conflict"                                       # problem.py _STATUS_TITLES
      - "Unprocessable Entity"                          # problem.py _STATUS_TITLES
      - "Too Many Requests"                              # problem.py _STATUS_TITLES
      - "Service Unavailable"                           # problem.py _STATUS_TITLES
      - "Internal Server Error"                         # problem.py _STATUS_TITLES
      - "Error"                                          # problem.py _title_for fallback
      - "Request body failed validation."                # problem.py validation_problem
      - "Too many requests; retry after the indicated delay."   # problem.py rate_limited_problem
      - "Authentication required."                       # api_auth.py (two call sites)
      - "Staff access required."                        # api_auth.py
      - "Method not allowed."                            # api_auth.py
    validation_steps:
      - per_msgid_grep: >
          after the source deletions and before pruning, grep retained src/
          (Python `_(` / gettext / gettext_lazy arguments AND all templates'
          {% trans %} / {% blocktrans %}) for each msgid — expected ZERO
          translation references. Known non-references that must not confuse:
          moderation/views/decorators.py's gettext-free "Authentication
          required" / "Staff access required" (no trailing period — distinct
          strings, retained), test_download_seed_photos.py's `text="Unauthorized"`
          (a mock body, not an extraction source).
      - surgical_removal: >
          remove each entry as a whole `#:` comment line(s) + msgid + msgstr +
          trailing blank from the tail of each catalog; no other entry, header,
          or line changes; ru/bs real translations in the tail die with their
          entries, en empty msgstrs likewise.
      - parser_validation: >
          `from testing.i18n_helpers import _parse_po_entries` over each edited
          catalog text — each file parses and its msgid set equals the pre-edit
          set minus exactly these 16; no fuzzy entries introduced.
      - gate_authority: >
          test_i18n_completeness.py both directions —
          test_extraction_completeness (forward: every extracted msgid present
          in catalog) and test_reverse_stale_entry_gate (reverse: no catalog
          entry absent from extraction) — green in the focused run AND the
          fast gate. The .mo files are compiled automatically by the image
          build/entrypoint/CI (gitignored); no manual compilemessages on the
          tracked tree.

# Implementation sequence (mandatory order — ONE atomic commit; the focused
# staged-media tier runs BETWEEN steps 3 and 4 so the tripwire guards the
# riskiest hunk before any catalog is touched):
sequence:
  1: >
     Helpers/tests deletion (deletions.helper_tests then deletions.helper_modules;
     leaves first, importer api_auth.py before problem.py). Re-grep import paths
     immediately before each file deletion.
  2: >
     Enums surgery: core/enums.py four atomic edits + the two dedicated test
     deletions in core/tests/test_rate_limit_budget.py, in one coherent edit
     (import-time NameError / runtime KeyError otherwise).
  3: >
     Submission/schemas restoration: copy the two baseline blocks byte-exactly
     from `git show d2f6df33^:<path>` (media_caps deletion + staged_digests
     replacement in submission.py; sha256 field+comment deletion in schemas.py).
     Immediately run verification.focused_tier's staged-media subset — the
     tripwire test_dedup_survives_deferred_promotion plus
     test_submission.py's reclaim/dedup suite — and the
     verification.baseline_empty_diff check. STOP on any failure (risks[0]).
  4: >
     i18n prune: the 16-entry tail from ru, then bs, then en, strictly per
     changes.i18n_prune (after the source deletions so the extraction set has
     actually shrunk); parser-validation after each file.
  5: >
     Docs: remove the single problem.py clause from docs/01-spec/api-surface.md.
     Everything else doc-shaped is B7.
  6: >
     Full verification block (below), then the single commit — no deployable
     intermediate revision may exist (enum member/table mismatch breaks
     imports mid-history; an unpruned catalog fails the reverse gate).

architectural_constraints:
  - Deletions and edits by explicit path/symbol only — never a glob or
    name-prefix match: problem.py sits beside the PRESERVED
    rate_limit_response.py, and api_auth.py's role is name-adjacent to
    moderation/views/decorators.py::staff_required_api; moderation/views/api_bulk.py
    is PRESERVED legacy surface.
  - Budget atomicity: the two members, both property-table row pairs, the two
    docstring paragraphs, and the two dedicated tests change together in one
    edit; no retained test iterates the full RateLimitBudget enum (the only
    `for budget in RateLimitBudget:` lived in the dying test_problem_response.py),
    so nothing breaks mid-commit.
  - No production-code invention: the restored submission/schemas bytes come
    from the d2f6df33^ blobs; only the three D23 hunks reverse. No new
    functions, no new comments beyond the baseline's, no signature changes.
  - Preserve R05/§9 checklist by construction: AdImage.sha256,
    AdImage.save()'s fallback digest, FileHashService, AdImageService.create_or_skip(sha256=…),
    _compute_sha256 ""-on-missing guard, per-ad dedup + skip log, staging
    prefix re-queue (_permanent_thumbnail_key), reclaim_staged_keys,
    promote_media_files, and both transaction.on_commit callbacks with their
    reclaim-prune ordering.
  - _get_cached_criteria returns to moderation-private use; no edit to
    apps/moderation or testing/moderation_fixtures.py — the private
    tuple-index read R05 flagged disappears because its only external consumer
    (media_caps) is gone, not by re-documenting the layout.
  - i18n: prune exactly the enumerated 16 msgids; B4's preserved shared strings
    and c2f130dd's Bosnian repair are all OUTSIDE the tail and stay
    byte-identical; no makemessages anywhere near the tracked tree; no .mo
    files are committed (gitignored, auto-compiled).
  - English only for all comments/docstrings/messages; no logging changes; no
    new msgids; no schema/model/migration delta (makemigrations --check stays
    clean — SubmittedPhoto.sha256 is a Pydantic DTO field, not a model column);
    no settings/env/middleware/dependency/lockfile change; no bot-workflow
    change; no B6/P6 signature simplification.

protected_suites:   # must stay GREEN byte-unchanged — the retained invariant set
  submission_reclaim_dedup: >
    apps/ads/tests/test_submission.py —
    test_intra_submission_duplicate_reclaims_all_four_staged_files,
    test_rollback_leaves_skipped_photo_staged_and_promotes_nothing,
    test_invalid_transition_does_not_reclaim_skipped_files (pre-creates a
    matching-digest row — staged hashing drives the skip),
    test_moderation_failure_still_reclaims_skipped_files,
    test_reclaim_failure_leaves_skipped_file_staged_not_promoted,
    test_missing_staged_file_reports_a_recoverable_error,
    TestSubmitAdStorageConsentGate (refusal precedes the staged plan).
  image_service: >
    apps/ads/tests/test_ad_image_service.py::TestAdImageServiceCreateOrSkip
    (hash-on-create, same-user duplicate skip, different-user new row,
    missing-file empty hash, per-ad scoping).
  model_digest: >
    apps/media/tests/test_adimage_sha256.py::TestAdImageSaveSha256,
    incl. test_sha256_not_recomputed_on_insert_when_explicitly_passed and
    test_sha256_matches_file_hash_service.
  filesystem_suites: >
    apps/media/tests/test_filesystem.py — TestPlanStagingPromotion (×5),
    TestPromoteMediaFiles (×4), TestReclaimStagedKeys (×3); its
    SubmittedPhoto(...) constructions never pass sha256.
  bot_staged_digest_tripwire: >
    src/telegram_bot/tests/test_save_photo_integration.py —
    TestSubmitAdStagingMove::test_dedup_survives_deferred_promotion (asserts
    first_image.sha256 == digest of the STAGED bytes and that a second
    identical submission skips — fails loudly if the restoration is wrong in
    EITHER direction), test_files_are_not_promoted_before_the_row_commits,
    test_submit_ad_moves_staging_to_permanent,
    test_submit_ad_rollback_leaves_files_in_staging, plus
    TestSavePhotoThumbnailsIntegration.
  budget_and_shape: >
    apps/core/tests/test_rate_limit_budget.py — the retained 6
    TestRateLimitBudgetTable tests, TestOneResponseShape ×7,
    TestNamespaceIsolation, TestForwardedForRegressionGuard.
  i18n_gate: >
    apps/ads/tests/test_i18n_completeness.py —
    test_reverse_stale_entry_gate AND test_extraction_completeness (the
    prune's own green proof; both directions).

verification:
  baseline_empty_diff: >       # the strongest single check for the restoration
    git diff d2f6df33^ HEAD -- src/backend/apps/ads/services/submission.py
    src/backend/apps/media/schemas.py   (MUST print nothing). Pre-check before
    editing: git log d2f6df33..HEAD -- <the two files> is empty (provenance).
  focused_tier: >
    docker compose --project-name mko-bazuna-test --env-file .env.test -f
    docker-compose.yml -f docker-compose.test.yml run --rm -e
    "PYTEST_OPTS=src/backend/apps/ads/tests/test_submission.py
    src/backend/apps/ads/tests/test_ad_image_service.py
    src/backend/apps/media/tests/test_adimage_sha256.py
    src/backend/apps/media/tests/test_filesystem.py
    src/backend/apps/core/tests/test_rate_limit_budget.py
    src/backend/apps/ads/tests/test_i18n_completeness.py
    src/telegram_bot/tests/test_save_photo_integration.py" test
    (start the DB first — .\Makefile.ps1 test-db — if
    docker ps --filter "name=mko-bazuna-test-db-" is empty; never
    `uv run pytest` locally; run the commands as given and do not touch the
    commands.md PYTEST_OPTS prose — its correction is B7's). Run the staged-media
    subset (submission/adimage/image_service/filesystem + bot tripwire) right
    after sequence step 3, and the full tier above (adding the i18n gate) at
    the end.
  lint: uv run ruff check src/
  typecheck: uv run basedpyright src/
  fast_gate: .\Makefile.ps1 test       # canonical PR gate; includes the i18n
                                       # completeness gate and
                                       # test_docs_ci_parity marker token pins
  schema_check: >
    dev-container makemigrations --check --dry-run (no schema delta by
    design): docker compose --project-name mko-bazuna-dev --env-file .env.dev
    -f docker-compose.yml -f docker-compose.dev.override.yml run --rm
    --no-deps --entrypoint "" web python src/backend/manage.py makemigrations
    --check --dry-run
  g5_sweep: >
    zero-reference greps over src/ (scope OUTSIDE the stray worktree
    docker/.kilo/; .ai/ planning records are process files, out of scope):
    1. API_PUBLIC_READ|API_WRITE        → zero
    2. media_caps                        → zero
    3. core\.utils\.problem|core\.utils\.api_auth → zero
    4. photo\.sha256                     → zero
    5. RETRY_AFTER_HEADER|PROBLEM_CONTENT_TYPE → hits allowed ONLY in
       core/utils/rate_limit_response.py (its OWN constant) and its retained
       callers/suites; zero imports from the deleted modules anywhere
    EXPECTED RESIDUE (and nothing else): AdImage-level sha256 references
    (apps/ads/models.py, apps/ads/services/images.py, their tests, docstrings)
    and the /moderation/api/v1/ legacy route family.
  hygiene: >
    git status --short must show exactly this task's paths — 4 deleted files,
    core/enums.py, core/tests/test_rate_limit_budget.py,
    ads/services/submission.py, media/schemas.py, 3 × django.po,
    docs/01-spec/api-surface.md — and NOTHING from
    docker/.kilo/worktrees/ (never git add -A; stage by explicit list).
    Record pytest --collect-only counts before/after: expected delta is
    −36 `def test_` functions (16 + 18 + 2), all of which pin dying symbols
    (dedicated helper tests, dedicated budget member tests); zero of them
    encodes a retained invariant (B3's ledger already recorded the
    API-era tests as TRANSPORT-deletes).

acceptance_criteria:
  - >
    G5 removal consistency: no executable reference survives to
    apps.core.utils.problem, apps.core.utils.api_auth, their modules' public
    symbols, RateLimitBudget.API_PUBLIC_READ/API_WRITE, submission.media_caps,
    or SubmittedPhoto.sha256/photo.sha256 anywhere in src/ (the g5_sweep
    expectations match exactly; legacy /moderation/api/v1/ and AdImage-level
    sha256 residue only). ruff and basedpyright pass on src/.
  - >
    RateLimitBudget shape: exactly the five original members; docstring lists
    five; both property tables have five consistent rows; no NameError at
    import and no KeyError on any member's .requests/.period;
    test_rate_limit_budget.py green with only the two dedicated tests removed.
  - >
    Byte-exact restoration: `git diff d2f6df33^ HEAD -- <submission.py>
    <schemas.py>` is EMPTY; every protected staged-media/dedup/promotion/on-commit
    suite listed in protected_suites is green byte-unchanged, first among them
    the bot tripwire test_dedup_survives_deferred_promotion and
    test_invalid_transition_does_not_reclaim_skipped_files.
  - >
    Catalogs: each of ru/bs/en lost exactly the enumerated 16-entry appendix
    tail (validated with testing.i18n_helpers._parse_po_entries — set equality
    pre minus 16) with every other entry byte-identical (shared strings and the
    Bosnian repair intact); test_reverse_stale_entry_gate AND
    test_extraction_completeness green in the focused tier and the fast gate.
  - >
    Docs: api-surface.md no longer claims any problem.py helper; the bulk 422's
    sanitize.py attribution remains untouched; no other doc/markdown file
    changed in this task.
  - >
    G7 hygiene: single atomic commit; makemigrations --check clean; no
    migration/settings/env/middleware/dependency/lockfile/bot-workflow/.mo
    delta; git status shows exactly the task's file list with no stray-worktree
    leakage.

out_of_scope:
  - B6/P6 signature simplifications: lifecycle single-locked-ad convention,
    assert_lifecycle_owner elimination, edit-flow refinements, any public
    re-export or signature reshaping.
  - B7 doc restructure: everything in docs/ beyond the single api-surface.md
    clause — the 14 retained files' "future /api/v1/" docstring commentary,
    spec-index/architecture-structure updates, i18n-spec.md / 99-agent rules.md
    stale `_EXTRACTION_GAP_MSGIDS` prose, commands.md PYTEST_OPTS paragraph,
    and .kilo/rules/project.md rule 16 (user-owned; the bulk endpoint keeps
    consuming RFC 9457-shaped documents).
  - Any schema/model/migration, settings/env, middleware, dependency, or
    lockfile change. SubmittedPhoto.sha256 is a Pydantic DTO field, not a
    model column; AdImage.sha256 is untouched.
  - Any behavior change to AdImage.sha256, FileHashService,
    AdImageService.create_or_skip, _compute_sha256, per-ad dedup, staging
    cleanup/reclaim, promotion, thumbnail pipeline, or both on_commit
    callbacks (apps/ads/services/images.py, apps/ads/models.py,
    apps/media/services/{hash_service,filesystem}.py are byte-untouched).
  - sanitize.py / rate_limit_response.py and their retained callers
    (core/views.py preferred-city 422, moderation api_bulk bulk 422,
    consent/search/autocomplete/listings 429s); the moderation tuple-index
    layout and testing/moderation_fixtures.py; staff_required_api and the
    /moderation/api/v1/bulk-action/ legacy surface; bot dialog/FSM and photo
    staging flows.
  - Re-adding reverse() URL pins for the deleted modules (B4's
    test_url_surface.py already guards the retired mount; nothing in B5 adds
    routes).

risks:
  - >
    Hash/staging loss is a STOP condition (plan §9): the one real engineering
    risk is over-deletion — if the staged hashing went with the precedence
    branch, create_or_skip(sha256=None) → _compute_sha256(permanent_key) → ""
    under deferred promotion → the `if digest:` guard no-ops dedup for EVERY
    staged submission. Tripwire: test_dedup_survives_deferred_promotion (and
    the whole protected_suites matrix) must be green immediately after the
    sequence-3 restoration, before any catalog is touched. On ANY
    image/storage regression: STOP, revert the two files from the d2f6df33^
    blobs, re-run the staged-media tier, and do not proceed to commit.
  - >
    Budget-edition atomicity: a stale property-table entry naming a deleted
    member is an import-time NameError; a retained member without its entry is
    a runtime KeyError on .requests/.period — the four enum edits and the two
    test deletions land as ONE atomicity unit inside the single commit.
  - >
    Translation collateral (plan §9): only the 16 enumerated, per-msgid
    grep-verified entries are pruned, surgically, per catalog; shared strings
    and the c2f130dd Bosnian repair must survive byte-identical (all are
    outside the tail); never makemessages against the tracked tree (it
    rewrites all three .po files and risks fuzzy-merge loss); never restore a
    whole catalog from baseline. The gate is the authority in both directions.
  - >
    Name-pair deletion hazard (carried from B4 §7): problem.py vs
    rate_limit_response.py, api_auth.py vs staff_required_api — any
    glob/name-prefix deletion kills preserved legacy code; explicit paths and
    symbols only, and the grep sweep documents the allowed RETRY_AFTER_HEADER
    residue in rate_limit_response.py.
  - >
    Stray ignored worktree docker/.kilo/worktrees/carefree-beast/ must not
    leak into the commit: no `git add -A`, stage by explicit file list, and
    check git status --short shows exactly the task's paths.
  - >
    Test-count optics (G8): 36 test functions removed, zero of which encode a
    retained invariant — they pin the dying helpers/members themselves, and
    B3's ledger already dispositioned the API-era transports. Record collected
    counts before/after (--collect-only) instead of arguing from raw deltas.

commit:
  message: refactor(core): remove API-only helpers, budgets, and media additions
  body: >
    Remove the /api/v1/-exclusive support left after the surface retirement
    (D21/D22/D23, R05): delete core/utils/problem.py, core/utils/api_auth.py
    and their dedicated test modules (36 tests); retire
    RateLimitBudget.API_PUBLIC_READ/API_WRITE with their docstring rationale,
    property-table entries, and the two dedicated tests (the five original
    budgets and their suites are untouched); delete submission.media_caps()
    (the private moderation tuple-index read goes with it) and the optional
    SubmittedPhoto.sha256 DTO field with the digest-precedence branch,
    restoring the baseline staged-digest computation byte-exactly —
    submission.py and schemas.py are identical to the pre-migration state
    (git diff d2f6df33^ HEAD over both is empty). Prune the 16 newly
    source-unreferenced msgids from ru/bs/en (the clean catalog tails) as
    required by the strict reverse i18n gate, preserving shared strings and
    the Bosnian repair. Remove the now-false problem.py clause from
    api-surface.md. No behavior change to any retained path: staged hashing,
    dedup, promotion, on-commit lifecycle, legacy auth/429 helpers, the
    moderation bulk surface, and all five retained budgets are untouched;
    no schema/settings/dependency delta.
  files_hint: >
    single atomic commit — 4 file deletions + core/enums.py +
    core/tests/test_rate_limit_budget.py + ads/services/submission.py +
    media/schemas.py + locale/{ru,bs,en}/LC_MESSAGES/django.po +
    docs/01-spec/api-surface.md; no deployable intermediate revision may
    exist (enum member/table mismatch breaks imports mid-history; an
    unpruned catalog fails the strict reverse gate).
```

## B6 audit findings

Read-only audit of block B6 (P6 — Simplify retained services: lifecycle convention), 2026-11-05,
HEAD `44620e97` (B5 landed; B4 `e968a1dd` retired the `/api/v1/` surface). Scope: the plan §4 D08
"SIMPLIFY" residual, §5 R04 second half, §7 P6 row, §8 G2 (must keep passing). Semantic anchors are
authoritative; line numbers are hints. All lifecycle callers re-verified at HEAD.

### Current implementation (per symbol, at HEAD `44620e97`)

- `apps/ads/services/lifecycle.py` (258 lines): `archive_ad(ad_id, user_id)`,
  `reactivate_ad(ad_id, user_id)`, `delete_ad(ad_id, user_id)` — id-based; each opens its own
  `transaction.atomic()` and calls `_fetch_owned_ad(ad_id, user_id)`, which locks
  (`Ad.objects.select_for_update().get`) and refuses missing (`Http404`) / non-owner
  (`PermissionDenied` + warn log). `assert_lifecycle_owner(ad_id, user_id)` exists solely to open
  the caller's transaction around `_fetch_owned_ad` for the HTML precheck; zero remaining callers
  besides `views/edit.py` L287/L356. Result NamedTuples: `ArchiveResult(archived)`,
  `ReactivateResult(attempted, passed: bool | None)`, `DeleteResult(deleted)` — used by the view
  only for `reactivate_ad(...).passed`; no other production consumer. `reactivate_ad` runs
  `transition_to(ON_MODERATION)` + `auto_moderation.auto_moderate(ad)` inside its block (rollback
  invariant). B1-corrected docstrings describe the savepoint/self-reacquire topology accurately.
  Module docstring claims "state mechanics only" yet the code also owns fetch+lock+ownership —
  the documented scope is the P6 target, not the current behavior.
- `apps/ads/views/edit.py` (415 lines): `ad_archive` / `ad_reactivate` run, inside one outer
  `transaction.atomic()`: `assert_lifecycle_owner(...)` precheck (→ `_ownership_refused_forbidden`
  ownership 403) → `_seller_may_create_ad` consent gate (→ `_consent_required_forbidden` 403) →
  the service call wrapped in the **B1 "belt"** (`except PermissionDenied` → same owner-403;
  reactivate orders the belt before `except (Http404, DatabaseError): raise` and
  `except Exception:` moderation-failure reporting). `ad_edit` POST already has the exact
  single-locked-ad shape P6 wants: `atomic()` → `get_object_or_404(Ad.objects.select_for_update(),
  id=ad_id)` → return-based ownership 403 → consent gate → service call (L173–191). Helpers
  `_seller_may_create_ad`, `_consent_required_forbidden`, `_ownership_refused_forbidden` are
  shared (dashboard.py imports the first two). `__all__`:
  `EDITABLE_DIRECT_SAVE_STATUSES`, `EDIT_FORM_AVAILABLE_STATUSES`, `ad_archive`, `ad_edit`,
  `ad_reactivate`. B0 already removed `_apply_price_change` and `can_edit_ad_by_service`
  (verified: absent).
- `apps/ads/views/delete.py` (50 lines): `ad_delete` = `try: delete_ad(ad_id, request.user.id)
  except PermissionDenied: return HttpResponseForbidden(_("You do not have permission to delete
  this ad."))` → redirect. Consent-free by design. Single fetch/ownership check (inside the
  service) — already "one implementation, one transaction owner"; no gap exists in delete today.
- `DbLockTimeoutMiddleware` + `is_lock_timeout` (03-DB-004 boundary): predicate-gated on
  SQLSTATE 55P03, **not view-name-gated**; its docstring already names all six lock-acquiring
  views incl. `ad_delete`.
- Callers (complete): production = the two HTML views above + `views/delete.py`. Tests =
  `test_lifecycle_service.py` (direct), `test_edit.py` (monkeypatches the **view-module seam**
  `apps.ads.views.edit.archive_ad` / `.reactivate_ad`, belt class), `test_edit_views_locking.py`
  (G2 tests resolve the same view-module seam via `getattr(edit, service_name)` with
  `service_name ∈ {"archive_ad", "reactivate_ad"}`). **Zero bot callers** (`src/telegram_bot`
  uses `Ad.transition_to` directly in test setup; `telegram_bot/lifecycle.py` is process
  lifecycle, unrelated). **Zero API callers** (B4 deleted `views/api/lifecycle_actions.py`).
  `assert_lifecycle_owner`: zero test and doc references.
- Test inventory (what pins what):
  - `test_lifecycle_service.py`: id-signature call sites throughout; per-op non-owner
    `PermissionDenied` (3) and missing-ad `Http404` (3) **service-tier** refusals; status no-op
    matrices; reactivate verdict/rollback (patches
    `apps.ads.services.lifecycle.auto_moderation.auto_moderate`); analytics-event assertions;
    archive/delete `test_consent_gate_is_caller_side` (service must stay gate-free).
  - `test_edit.py`: `TestAdArchive` (owner 302, wrong-user 403 status-only, REJECTED no-op),
    `TestAdArchiveGetRejected` (405), `TestAdReactivateDirect` (owner 302→PUBLISHED, wrong-user
    403, non-ARCHIVED no-op, GET 405, `banning_criteria` moderation-failure message, patched
    `auto_moderate` raise → "stays archived"), `TestBannedSellerRelistNowRefused`,
    `TestSellerWebStorageConsentGate` (owner-without-consent consent-403 ordering pins),
    `TestLifecycleOwnershipRefusalBelt` (B1 belt tests: patched seam raises `PermissionDenied` →
    owner-403 bytes, never the moderation-failure message).
  - `test_edit_views_locking.py`: `TestLifecycleActionAtomicContinuity` (records
    `in_atomic_block` at wrapper entry on the view-module seam; `transaction=True`),
    `TestLifecycleActionLockContinuity` (parked seam + 55P03 probe; class docstring says
    "lock taken by the precheck"), `TestEditViewsRowLockConcurrency` (no view involved),
    callable-only sentinels.
  - `apps/core/tests/test_db_lock_timeout_boundary.py`: `TestAdArchiveLockTimeout`,
    `TestAdReactivateLockTimeout` patch `edit.Ad.objects.select_for_update` — the **shared
    manager singleton** `lifecycle` also uses, so the intercept hits whichever fetch runs first.
  - `test_delete.py`: 4 view-driven tests (wrong-user 403, owner 302+DELETED, re-delete noop,
    GET 405) — no missing-ad test. `test_ad_lifecycle.py` (ads + bot): `Ad.transition_to`
  matrix only — orthogonal to P6, unchanged.

### Recommended design — single locked-ad lifecycle convention

The boundary owns fetch+lock+authorization+consent; the service owns state mechanics+moderation on
the row it is handed. This is exactly what `lifecycle.py`'s own scope-split docstring already
promises, what R04 prescribes, what B1's recorded hand-off (B1 research, "P6 hand-off") expects,
and what `ad_edit` POST already implements in the same file. `moderation/admin_actions::
soft_delete_ad(ad, moderator_id, reason)` is the in-repo precedent for instance-passing state ops.

**Service** (`archive_ad(ad: Ad) -> ArchiveResult`, same for the other two):

```python
def archive_ad(ad: Ad) -> ArchiveResult:
    """Apply PUBLISHED -> ARCHIVED to a row the caller fetched, locked, and authorized."""
    with transaction.atomic():   # savepoint inside the caller's block; whole tx standalone
        if ad.status == AdStatus.PUBLISHED:
            ad.transition_to(AdStatus.ARCHIVED)
            logger.info("Ad %s archived by user %s", ad.id, ad.user_id)
            return ArchiveResult(archived=True)
    return ArchiveResult(archived=False)
```

- Keep each function's own `with transaction.atomic()` — it is **not** redundant: it is what
  makes `reactivate_ad`'s moderation rollback invariant real (raising check → row stays ARCHIVED)
  both standalone and nested (savepoint). Dropping it would break
  `test_check_error_rolls_back_to_archived` and any future non-HTML caller.
- Keep names `archive_ad`/`reactivate_ad`/`delete_ad` (the B1 G2 tests resolve the view-module
  seam by these names) and the three result NamedTuples with unchanged fields ("keep useful
  outcome values"). Signature churn is minimal: `(ad_id, user_id)` → `(ad)`; nothing else.
- Docstring records the convention once: caller (HTML) fetches under `select_for_update` inside its
  open atomic block and has already verified ownership (and consent, non-delete) — this module
  never re-fetches, never re-checks ownership; consent stays caller-side and consent races are not
  solved by one ad-row transaction (R04 honesty clause).

**Views** — `ad_archive` / `ad_reactivate` become the `ad_edit` POST shape:

```python
with transaction.atomic():
    ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)   # Http404 if missing
    if ad.user_id != request.user.id:
        return _ownership_refused_forbidden(_("You do not have permission to archive this ad."),
                                            "archive", ad_id, request.user.id)
    if not _seller_may_create_ad(request.user):
        return _consent_required_forbidden(request.user, ad_id)
    archive_ad(ad)            # reactivate: passed = reactivate_ad(ad).passed
return redirect("ads:dashboard")
```

- `ad_reactivate` keeps the outer `try:` and the handler order **minus the belt**:
  `except (Http404, DatabaseError): raise` (still first-class; the fetch can now raise Http404
  inside the block) before `except Exception:` moderation-failure reporting. `passed is False`
  → warning message; `passed` → log — unchanged.
- The B1 belt (`except PermissionDenied` around the service call, in both views) is deleted
  together with the precheck, per the recorded B1 hand-off ("P6 ... removes the belt together
  with the precheck"). No second ownership check remains that could raise, so Test-3-style
  scenarios are structurally impossible; the belt becomes unreachable dead code.
- **`delete_ad` joins the same convention** (recommended): `ad_delete` gains
  atomic → locked fetch → ownership 403 (via `_ownership_refused_forbidden`, imported from
  `apps.ads.views.edit` — the established cross-view helpers pattern dashboard.py uses) →
  `delete_ad(ad)`. No consent line by design. The current inline `except PermissionDenied`
  try/except disappears; 403 body bytes stay identical ("You do not have permission to delete
  this ad."), and the refusal gains the ownership warning log. Alternative recorded (also
  G2-safe, lower churn): keep `delete_ad(ad_id, user_id)` id-based — but then `_fetch_owned_ad`,
  the `PermissionDenied`/`Http404` imports, and the user_id plumbing survive **solely** for
  delete, leaving two conventions in one module and failing D08's "one clear convention"; delete
  is the only remaining caller, so "callers have moved" is satisfied. Uniformity wins; the
  per-op behavior deltas are nil either way (delete's check+write were already single-transaction).
- What disappears: `assert_lifecycle_owner`, `_fetch_owned_ad`, `PermissionDenied` and `Http404`
  imports (lifecycle.py; `Ad` import stays for the annotation), the view-side belt try/excepts,
  the service-tier refusal docstring paragraphs, and the "Ad.DoesNotExist between fetch and
  transition" caveat. `transition_to`'s own `refresh_from_db()` on the locked row keeps the
  stale-instance hazard covered exactly as `ad_edit` covers it today.
- What stays: `_seller_may_create_ad`/`_consent_required_forbidden`/`_ownership_refused_forbidden`
  (dashboard.py imports; B6 uses them more), `edit.py::__all__`, `urls.py`/reverse names
  (`ads:archive|reactivate|delete`), messages/log strings, `DbLockTimeoutMiddleware` contract
  (predicate-gated; its "six lock-acquiring views" docstring becomes true at the view tier),
  `edit_flow.py`, models/migrations/settings/bot. FTS renaming etc. — out of scope, not needed
  for success (plan explicitly optional).

### Alternatives compared

| # | Option | Verdict | Reason (evidence) |
|---|---|---|---|
| A | Locked-instance service `(ad) -> Result`; all three ops; view owns fetch+ownership+consent; belt+precheck deleted; service keeps savepoint `atomic()` | **SELECTED** | R04's literal convention; matches `ad_edit` POST and `soft_delete_ad` precedent; B1 hand-off names exactly this ("deletes `assert_lifecycle_owner`, single locked-ad convention, removes the belt together with the precheck"); closes D08's duplicate precheck/refetch; one convention module-wide; minimal churn (names/results/URLs unchanged). |
| B | Instance for archive/reactivate; `delete_ad(ad_id, user_id)` stays id-based | REJECTED | Keeps `_fetch_owned_ad` + HTTP exception machinery alive for one caller; two conventions in one 3-function module; saves only ~6 test-method edits (worse uniformity per churn). |
| C | Keep `(ad_id, user_id)`; add `for_update=False` or caller-transaction flags | REJECTED | Signature churn **increases** (flag plumbing), duplicates the existing savepoint self-reacquire behavior with an explicit knob, and still leaves the second ownership check to remove. |
| D | Move ownership/consent into the service "so nothing depends on the caller" | REJECTED | Inverts R04 (gates are caller-side by design; delete gate-free); re-introduces the gate-in-service anti-pattern `can_edit_ad_by_service` embodied; consent must NOT be checked by the delete path. |

### Coverage-transfer ledger for B6 (plan §6 rule)

| Deleted / rewritten test | Retained destination |
|---|---|
| `test_lifecycle_service.py::TestArchiveAd::test_non_owner_is_refused_and_ad_unchanged` | `test_edit.py::TestAdArchive::test_archive_wrong_user_returns_403` (existing) + new message-bytes pin (below) |
| `TestArchiveAd::test_missing_ad_raises_http404` | NEW `test_edit.py::TestAdArchive::test_archive_missing_ad_returns_404` (HTML) |
| `TestReactivateAd::test_non_owner_is_refused_and_ad_unchanged` | `test_edit.py::TestAdReactivateDirect::test_reactivate_wrong_user_returns_403` (existing) + new bytes pin |
| `TestReactivateAd::test_missing_ad_raises_http404` | NEW HTML reactivate missing-ad 404 test |
| `TestDeleteAd::test_non_owner_is_refused_and_ad_unchanged` | `test_delete.py::TestAdDelete::test_delete_wrong_user_returns_403` (existing) |
| `TestDeleteAd::test_missing_ad_raises_http404` | NEW `test_delete.py::TestAdDelete::test_delete_missing_ad_returns_404` |
| `test_edit.py::TestLifecycleOwnershipRefusalBelt` (both tests) | Rewrite as `TestLifecycleOwnershipRefusal`: real-path wrong-owner POSTs → 403 + exact ownership message bytes + row unchanged; reactivate asserts the moderation-failure message/log does NOT appear. This is B1's recorded plan: "Test 3 is rewritten to assert the single 403 path in P6." |
| Service-tier matrices, verdicts, rollback, analytics, gate-free-ness, `TestAdArchive`/`TestAdReactivateDirect`/`TestBannedSellerRelistNowRefused`/`TestSellerWebStorageConsentGate`, `test_delete.py`, boundary suites | **Kept** (call-shape-only edits in `test_lifecycle_service.py`: `archive_ad(Ad.objects.get(pk=…))`; plain unlocked instance is fine — the service's own `atomic()` owns the standalone transaction) |

### G2 survival matrix (how the B1 G2 tests keep meaning)

- `TestLifecycleActionAtomicContinuity`: **code unchanged, meaning unchanged** — wrapper entry at
  the view-module seam still observes `in_atomic_block True` because the view calls
  `archive_ad(ad)`/`reactivate_ad(ad)` as its last statement inside its own open block; the
  service then opens a savepoint *after* observation.
- `TestLifecycleActionLockContinuity`: **code unchanged, meaning unchanged** — at the same parked
  seam instant, the row is locked (now by the view's own `select_for_update` fetch rather than the
  precheck's — same transaction, same lock, same instant); the 55P03 probe still proves it. One
  docstring word ("taken by the precheck") is truthed to the view's fetch.
- `TestAdArchiveLockTimeout`/`TestAdReactivateLockTimeout` (03-DB-004): **unchanged code, boundary
  preserved** — the patch hits the shared `Ad.objects` manager; the single first acquisition now
  happens at the view fetch; OperationalError still escapes (`ad_archive` has no catch at all;
  `ad_reactivate` re-raises via `except (Http404, DatabaseError)` before `except Exception`) to
  the predicate-gated middleware → 503 + busy.
- Ordering suites (`TestSellerWebStorageConsentGate`, `TestBannedSellerRelistNowRefused`,
  wrong-user 403s): unchanged — the convention makes the order literal source order
  (fetch → ownership → consent → action). Delete stays gate-free.
- `TestEditViewsRowLockConcurrency` + sentinels + `test_ad_lifecycle.py`: implementation- or
  model-level, unaffected.

### Proposal-era commentary — B6 vs B7 split

- **B6 (code-adjacent; B6's own hunks falsify them — rewrite in the same commit):**
  `lifecycle.py` module + per-function docstrings (the "request-free — an Ad (already fetched by
  the caller) plus the acting user_id" contract sentence, the `Http404`/`PermissionDenied`
  refusal paragraphs, the `Ad.DoesNotExist` caveat, `assert_lifecycle_owner`/`_fetch_owned_ad`
  contract text, the "future `/api/v1/...` endpoints share one transition stack" framing, the
  "HTML surfaces and the API views" gate audience); `views/delete.py` module docstring ("so the
  future `/api/v1/ads/{id}/delete/` endpoint runs the same state mechanics"); `ad_archive`/
  `ad_reactivate` docstrings (savepoint/self-reacquire topology prose → view-owned convention);
  `test_lifecycle_service.py` module docstring ("a future API caller inherits the same proofs" →
  current-truth wording + relocations); belt-class docstrings (replaced test names its own).
- **B7 (unchanged by B6's code, per B4 §2's recorded 14-file decision):** the "future `/api/v1/`"
  commentary in the ~11 retained files B6 does not touch (`dashboard_query.py`, `edit_flow.py`,
  `favorites.py`, `listings_query.py`, `favorite.py`, cabinet views, saved-search modules,
  `test_listings_query.py`). `views/edit.py` module docstring's edit-endpoint `/api/v1/` clause
  (L11–12) is B4-era staleness, not falsified by B6 — fix belongs to B7, though dropping it while
  B6 has the file open is a permitted trivial ride-along.
- Docs sweep found **zero** references to lifecycle symbols in `docs/` — no doc-file changes
  required for B6 (the 99-agent task→service map is B7 work).

### Risks

1. **Losing the 03-DB-004 boundary** — mitigated by keeping reactivate's `except (Http404,
   DatabaseError): raise` ordering and adding no new catches; the two boundary tests patch the
   shared manager and stay green unchanged.
2. **Losing ownership→consent ordering** — order becomes literal statement order; ordering
   suites stay byte-green. The single ownership 403 keeps exact message bytes via
   `_ownership_refused_forbidden`.
3. **Losing moderation rollback** — service's `atomic()` savepoint is **kept**; implementor must
   not "simplify" it away (it is the rollback mechanism, not redundant nesting).
4. **Breaking B1 G2 tests' meaning** — the view-module seam (`edit.archive_ad`/`edit.reactivate_ad`)
   and the observation points are preserved; per the G2 matrix above, tests 1/2/boundary pass
   unchanged. Only Test-3's premise (belt) is deleted — B1 itself scheduled its rewrite.
5. **Over-churning signatures** — only `(ad_id, user_id)`→`(ad)` on three functions; names,
   result types, view names, URLs, `__all__`, re-exports, messages, and logs unchanged; ruff/pyright
   over the three production files + three test files catches stragglers.
6. **Bot/web conflation** — zero bot callers (verified); the service is single-boundary now and
   the docstrings may say so honestly.
7. **Migration/schema risks** — none; no model/settings change.

### Files that must change for P6

1. `src/backend/apps/ads/services/lifecycle.py` — delete `assert_lifecycle_owner` and
   `_fetch_owned_ad`; switch all three signatures to `(ad: Ad)`; drop `PermissionDenied`/`Http404`
   imports; docstrings to the locked-instance contract (savepoint rule, caller-owned
   authorization/gates, R04 honesty clause).
2. `src/backend/apps/ads/views/edit.py` — `ad_archive`/`ad_reactivate`: locked fetch + return-based
   ownership + consent + `(ad)` service call inside the view block; delete the belt handlers;
   drop the `assert_lifecycle_owner` import (keep `archive_ad`/`reactivate_ad` imports — the G2
   seam) and unused-import cleanup; docstrings truthed (module-doc B4-era clause optional).
3. `src/backend/apps/ads/views/delete.py` — adopt the same convention (recommended), import
   `_ownership_refused_forbidden`; delete the `PermissionDenied` try/except; docstring truthed.
4. `src/backend/apps/ads/tests/test_lifecycle_service.py` — call-shape updates; relocate the six
   refusal tests per the ledger; docstring updated; matrices/verdict/rollback/analytics/gate-free
   kept.
5. `src/backend/apps/ads/tests/test_edit.py` — replace `TestLifecycleOwnershipRefusalBelt` with the
   message-pinning `TestLifecycleOwnershipRefusal`; add archive/reactivate missing-ad 404 tests;
   drop the `PermissionDenied` import.
6. `src/backend/apps/ads/tests/test_delete.py` — add the missing-ad 404 test.
7. `src/backend/apps/ads/tests/test_edit_views_locking.py` — docstring word truthing only
   ("precheck" → view's locked fetch); code unchanged.
8. No changes: `urls.py`, `dashboard.py`, `edit_flow.py`, models/migrations, middleware, settings,
   bot, templates, docs (B7 owns the commentary sweep), i18n catalogs (no string changes; all 403/
   503/message strings byte-identical).

### Acceptance for B6 (maps to plan §7 P6 + G2)

One operation implementation and one clear transaction owner per action (the HTML view owns the
transaction+lock+authorization; the service owns state mechanics+moderation on the locked row);
`assert_lifecycle_owner` and `_fetch_owned_ad` gone; no duplicated precheck/refetch/HTTP-exception
machinery left; G2 tests (atomic continuity, 55P03 lock continuity, both lock-timeout mirrors)
pass unchanged in code; ownership→consent→action ordering pinned by real-path message-byte tests;
delete consent-free single-call; moderation rollback and outcome values preserved verbatim
(`test_check_error_rolls_back_to_archived`, `ReactivateResult.passed` messages); no URL/schema/
settings/i18n delta; the ledger above has no unexplained coverage loss. Verification: the focused
docker run over `test_edit.py`, `test_edit_views_locking.py`, `test_edit_flow_service.py`,
`test_ad_lifecycle.py`, `test_lifecycle_service.py`, `test_delete.py`, `test_ad_consent_gate.py`,
`apps/core/tests/test_db_lock_timeout_boundary.py` (drop the deleted `test_edit_route_api.py` /
`test_lifecycle_api.py` from the plan's §8 vintage list), then `uv run ruff check src/`,
`uv run basedpyright src/`, `.\Makefile.ps1 test`, and one `-m slow`/`concurrent` targeted run for
the parked-seam tests before the full gate.

## B6 task description

```yaml
id: b6_simplify_lifecycle_service

title: >
  P6 — Simplify retained lifecycle services: adopt the single locked-ad
  convention (view owns transaction + lock + ownership + consent, service
  owns state mechanics + moderation on the locked row), delete the
  precheck/belt/second-fetch machinery, relocate the six service-tier
  refusal tests to the HTML tier, and keep the B1 G2 proofs meaningful.

priority: medium

type: implementation

depends_on: [b0_repair_edit_results, b1_restore_lifecycle_atomicity, b4_retire_api_surface]

# ── Plan/Audit report source (REQUIRED — this task originates from the
#    architecture-correction plan and the B6 audit block) ─────────────────
source_reference: .ai/plans/architecture-correction-plan.md
source_section: §4 D08 — Lifecycle extraction (SIMPLIFY/FIX) · §5 R04 — Is the
  lifecycle extraction safe to keep? · §7 P6 — Simplify retained services ·
  §8 G2 — Lifecycle atomicity
source_file: .ai/plans/architecture-correction-execution.md
source_blocks:
  - "B6 audit findings"    # selected design = alternative A (locked-instance service)

extra_context: |
  State at HEAD 44620e97 (B5 landed; B4 e968a1dd retired the /api/v1/ surface):
  the ONLY production lifecycle callers are the HTML views
  apps/ads/views/edit.py::ad_archive / ad_reactivate and
  apps/ads/views/delete.py::ad_delete, plus tests. Zero bot callers, zero API
  callers. assert_lifecycle_owner has zero references outside lifecycle.py and
  its two edit.py call sites; _fetch_owned_ad has zero references outside
  lifecycle.py. Signature simplification is therefore now unblocked (the
  "Decisions" deferral until after P4 is satisfied by history).

  Chosen design — B6 audit alternative A, do not re-litigate (B/C/D rejected;
  see the audit's alternatives table):
    archive_ad(ad: Ad) -> ArchiveResult
    reactivate_ad(ad: Ad) -> ReactivateResult
    delete_ad(ad: Ad) -> DeleteResult
  Names, result NamedTuples, field values, messages, log format strings, view
  names, URL names (ads:archive|reactivate|delete) and edit.py::__all__ are
  UNCHANGED. Only the parameter changes: (ad_id, user_id) -> (ad). No flags,
  no kwargs, no renames.

  The convention (R04, second half — this is what the service's own scope-split
  docstring already promised and what ad_edit POST already implements in the
  same file):
    VIEW  (boundary): opens transaction.atomic(); fetches with
                      get_object_or_404(Ad.objects.select_for_update(), ...)
                      (missing -> Http404; lock held for the whole block);
                      returns the ownership 403 via _ownership_refused_forbidden
                      (non-delete only); gates consent via _seller_may_create_ad
                      (non-delete only, AFTER ownership); calls service(ad) as
                      the last statement inside the open block.
    SERVICE          : operates on the row it is handed — transition +
                      auto_moderate (reactivate) inside its OWN
                      transaction.atomic(); never re-fetches, never re-checks
                      ownership, never reads consent.
  soft_delete_ad(ad, moderator_id, reason) in moderation/admin_actions is the
  in-repo instance-passing precedent.

  NON-NEGOTIABLE constraints recorded by the audit and the B1 hand-off:
    * Each service function KEEPS its own transaction.atomic(). It is the
      moderation-rollback mechanism (a SAVEPOINT inside the caller's block; a
      whole transaction standalone) — NOT redundant nesting. Dropping it
      breaks test_check_error_rolls_back_to_archived and any future non-HTML
      caller. The implementor must not "simplify" it away.
    * ad_reactivate keeps its outer try and the handler order MINUS the belt:
      except (Http404, DatabaseError): raise  stays BEFORE  except Exception:
      (moderation-failure reporting). The fetch can now raise Http404 inside
      the block — that is exactly what the first handler keeps re-raising.
      ad_archive ends with NO catch at all. A lock timeout (OperationalError /
      SQLSTATE 55P03) escapes both views untouched to the predicate-gated
      DbLockTimeoutMiddleware -> 503 (03-DB-004 boundary).
    * The B1 "belt" (except PermissionDenied around the service call, in both
      edit.py lifecycle views) and the precheck (assert_lifecycle_owner) are
      deleted TOGETHER — B1's recorded hand-off: "P6 deletes both together;
      tests 1, 2, 4 keep meaning; test 3 is rewritten by P6 to the
      single-path assertion."
    * delete_ad joins the convention so _fetch_owned_ad dies ENTIRELY: ad_delete
      gains atomic -> locked fetch -> ownership 403 (via
      _ownership_refused_forbidden imported from apps.ads.views.edit — the
      established cross-view helper pattern dashboard.py already uses) ->
      delete_ad(ad). No consent line, by design. The 403 body bytes stay
      identical ("You do not have permission to delete this ad."); the refusal
      gains the ownership warning log (the only sanctioned log delta: the wrong-
      owner delete warning switches from _fetch_owned_ad's "attempted a
      lifecycle action on ad %s owned by %s" wording to the ownership helper's
      "attempted to delete ad %s without owning it" wording).
    * G2 survival (B1 tests are written so B6 passes them CODE-UNCHANGED):
      TestLifecycleActionAtomicContinuity and TestLifecycleActionLockContinuity
      resolve the view-module seam via getattr(edit, "archive_ad"|"reactivate_ad")
      — the services must remain module-level names IMPORTED by views/edit.py,
      called as the view's last in-block statement; at the seam instant the row
      is locked (now by the view's own select_for_update fetch rather than the
      precheck's — same transaction, same lock, same instant) and
      in_atomic_block is True (the service's savepoint opens after the
      observation). TestAdArchiveLockTimeout / TestAdReactivateLockTimeout patch
      the shared Ad.objects manager — the single first acquisition moves to the
      view fetch and OperationalError still escapes. Only ONE docstring word in
      TestLifecycleActionLockContinuity ("taken by the precheck") needs
      truthing; those test bodies change ZERO bytes.
    * transition_to's own refresh_from_db() on the locked row keeps the
      stale-instance hazard covered exactly as ad_edit covers it today; a plain
      unlocked instance passed in service tests is fine (the service's own
      atomic owns the standalone transaction).
    * views/edit.py's module docstring edit-endpoint "/api/v1/" clause is
      B4-era staleness owned by B7 — dropping it while B6 has the file open is
      a permitted trivial ride-along, nothing more.

description: >
  Adopt one locked-ad lifecycle convention for all three seller state
  operations. The HTML views become the single transaction owner: each opens
  transaction.atomic(), locks the ad with get_object_or_404 +
  select_for_update, refuses a non-owner with the existing ownership 403
  helper (and consent with the existing consent 403 helper, except delete,
  which stays gate-free), and hands the locked instance to the service as the
  last statement inside the block. The three service functions keep their
  names and result NamedTuples but take the instance instead of
  (ad_id, user_id); each keeps its own transaction.atomic() as the
  moderation-rollback savepoint; values, messages and log format strings are
  unchanged. Delete everything the convention makes dead: the
  assert_lifecycle_owner precheck, _fetch_owned_ad, the PermissionDenied /
  Http404 imports in lifecycle.py, both view belts, delete.py's inline
  PermissionDenied handler, and the PermissionDenied import in test_edit.py.
  Relocate the six service-tier refusal tests to the HTML tier (three new
  missing-ad 404 tests; wrong-owner paths gain exact message-bytes pins),
  rewrite TestLifecycleOwnershipRefusalBelt into the real-path
  TestLifecycleOwnershipRefusal, and truth the one falsified word in the
  lock-continuity docstring. Truth the proposal-era commentary this task's own
  hunks falsify (lifecycle contract paragraphs, delete.py's "future /api/v1/"
  claim); other files' /api/v1/ commentary stays B7. Zero behavior, schema or
  i18n change.

goals:
  - one operation implementation and one transaction owner per action (view:
    transaction + lock + authorization; service: state mechanics + moderation)
  - ownership checked exactly once per request path (in the view); no
    redundant fetch / second locked read / duplicate precheck anywhere
  - the convention fully adopted: assert_lifecycle_owner, _fetch_owned_ad and
    both view belt handlers gone,
    with zero remaining references
  - delete consent-free single-call; ownership-before-consent-before-action
    becomes literal statement order and is pinned by real-path 403 byte tests
  - moderation rollback preserved verbatim (every service keeps its own
    atomic(); test_check_error_rolls_back_to_archived stays green)
  - all four B1 G2/03-DB-004 tests pass with zero code change and keep their
    meaning (same seam, same observation, same lock holder tier-move only)
  - zero behavior change: retained outcome values (incl.
    ReactivateResult.passed), all 403/404/consent/moderation message bytes,
    URLs / reverse names, __all__, the 503 middleware boundary
  - coverage-transfer ledger closed: every deleted service-tier refusal test
    has a named retained destination; no unexplained coverage loss

# ─────────────────────────────────────────────────────────────────────────────
# Files and semantic targets (symbols only — never line numbers)
# ─────────────────────────────────────────────────────────────────────────────

files:

  # ── 1. Service — locked-instance state mechanics ─────────────────────────
  - path: src/backend/apps/ads/services/lifecycle.py
    targets:
      - type: module_docstring
        name: lifecycle module docstring
        change: >
          rewrite to the shipped convention — state mechanics and (for
          reactivation) the auto_moderate decision ONLY, operating on a row
          the caller fetched, locked and authorized; this module never
          re-fetches, never re-checks ownership. Delete every sentence the
          new shape falsifies: the "request-free — an Ad (already fetched by
          the caller) plus the acting user_id" contract sentence (no more
          user_id), the "future /api/v1/ads/{id}/{archive,reactivate,delete}/
          endpoints share one transition stack" framing, the "HTML surfaces
          and the API views" gate audience (consent/audience gates stay
          CALLER-side, asserted by each boundary), the Http404 /
          PermissionDenied refusal paragraph, and the "Ad.DoesNotExist when
          the row disappears between fetch and transition" caveat (no fetch
          remains). Add the convention sentence once: the caller (the HTML
          view) fetches under select_for_update inside its own open atomic
          block and has already verified ownership (and consent, non-delete).
          Keep the R04 honesty clause: a single ad-row transaction does not
          by itself solve concurrent account-consent changes.
      - type: import_block
        name: module imports
        change: >
          remove `from django.core.exceptions import PermissionDenied` and
          `from django.http import Http404`; KEEP `Ad` (annotation-only), the
          __future__ annotations import, logging, NamedTuple, transaction,
          AdStatus, auto_moderation and the logger.
      - type: function
        name: _fetch_owned_ad
        action: delete_symbol    # zero remaining callers after the views move
      - type: function
        name: assert_lifecycle_owner
        action: delete_symbol    # HTML-only callers; service re-checks nothing
      - type: function
        name: archive_ad
        action: replace_signature_and_body    # (ad: Ad) -> ArchiveResult
      - type: function
        name: reactivate_ad
        action: replace_signature_and_body    # (ad: Ad) -> ReactivateResult
      - type: function
        name: delete_ad
        action: replace_signature_and_body    # (ad: Ad) -> DeleteResult
    semantic_anchors:
      keep_unchanged:
        - ArchiveResult / ReactivateResult / DeleteResult NamedTuples — names,
          field names, field order, defaults and docstring semantics
          (ReactivateResult.passed: True=PUBLISHED / False=committed
          ON_MODERATION_FAILED / None=not attempted) — value-frozen
        - each function's own `with transaction.atomic():` — the
          moderation-rollback SAVEPOINT; it is NOT redundant nesting
        - reactivate_ad's transition + auto_moderation.auto_moderate(ad) both
          inside that block, and the rollback comment; Database-error
          propagation paragraph (03-DB-004) in its docstring
        - status preconditions exactly as-is: archive acts only on PUBLISHED;
          reactivate no-ops on != ARCHIVED; delete no-ops on already-DELETED
        - the log format strings — "Ad %s archived by user %s" and
          "Ad %s deleted by user %s" (args become ad.id / ad.user_id:
          value-identical through the only remaining caller, which has already
          verified ownership)
        - reactivate's Raises: Exception (auto_moderate, after rollback) and
          archive's Raises: ValueError (transition_to matrix, unreachable for
          the PUBLISHED precondition)

  # ── 2. HTML views — the transaction owner ────────────────────────────────
  - path: src/backend/apps/ads/views/edit.py
    targets:
      - type: import_block
        name: lifecycle service import
        change: >
          drop assert_lifecycle_owner from `from apps.ads.services.lifecycle
          import (...)`; KEEP archive_ad and reactivate_ad module-level names —
          the B1 G2 tests and the belt replacement resolve the view-module
          seam apps.ads.views.edit.archive_ad / .reactivate_ad by name.
      - type: import_block
        name: django imports
        change: >
          remove `from django.core.exceptions import PermissionDenied` (its
          only uses were the precheck / belt handlers, all deleted); KEEP
          Http404 (ad_reactivate's ordered re-raise), DatabaseError,
          OperationalError, transaction, HttpResponseForbidden (ad_edit).
      - type: function
        name: ad_archive
        action: replace_function    # ad_edit POST shape, no catch at all
      - type: function
        name: ad_reactivate
        action: replace_function    # ad_edit POST shape + ordered handlers
      - type: docstring
        name: ad_archive docstring
        change: >
          the "service call runs inside this view's atomic() block … savepoint
          … same-transaction self-reacquire" topology prose becomes the
          view-owned convention: the view fetches and locks the row, refuses
          the non-owner, gates consent, and the service applies the
          transition to that locked instance (its atomic() nests as a
          savepoint under this block — keep that one clause).
      - type: docstring
        name: ad_reactivate docstring
        change: same rewrite; keep the moderation-outcome paragraphs
          (passed False message / non-database exception rollback) and the
          03-DB-004 paragraph byte-equivalent in meaning.
      - type: module_docstring
        name: edit module docstring optional ride-along
        change: >
          OPTIONAL (B7-owned; permitted trivial ride-along): drop the stale
          "the future /api/v1/ads/{id}/edit/ endpoint cannot drift" clause.
          Everything else in the module docstring stays.
    semantic_anchors:
      keep_unchanged:
        - _seller_may_create_ad and _consent_required_forbidden (imported by
          apps/ads/views/dashboard.py)
        - _ownership_refused_forbidden — byte-identical (message string, log
          line "User %s attempted to %s ad %s without owning it", 403 shape)
        - ad_edit entirely — GET and POST blocks, imports, the 03-DB-004
          OperationalError lock-timeout re-render
        - module __all__ byte-identical (EDITABLE_DIRECT_SAVE_STATUSES,
          EDIT_FORM_AVAILABLE_STATUSES, ad_archive, ad_edit, ad_reactivate)
        - messages: "You do not have permission to archive this ad." /
          "You do not have permission to reactivate this ad." / the consent
          message; messages.error "Reactivating ad #%(ad_id)s failed. The ad
          stays archived; please try again later."; messages.warning
          "Ad #%(ad_id)s did not pass moderation and is hidden pending
          review."; log lines "Ad %s reactivation failed during
          auto-moderation" / "Ad %s failed re-moderation on reactivation" /
          "Ad %s reactivated by user %s"; the passed-False / passed branches

  - path: src/backend/apps/ads/views/delete.py
    targets:
      - type: module_docstring
        name: delete module docstring
        change: >
          delete the "so the future /api/v1/ads/{id}/delete/ endpoint runs the
          same state mechanics" sentence; state the actual convention (this
          view owns the transaction + row lock + ownership; the service
          applies the transition to the locked row). Keep the gate-free
          sentence — it is the reason there is no consent line.
      - type: import_block
        name: module imports
        change: >
          add `from django.db import transaction`, extend the shortcuts
          import to `get_object_or_404, redirect`, add
          `from apps.ads.models import Ad`, add
          `from apps.ads.views.edit import _ownership_refused_forbidden`;
          remove `from django.core.exceptions import PermissionDenied` and
          `HttpResponseForbidden` from the django.http import (the 403 is
          built inside the helper; KEEP HttpRequest / HttpResponse).
      - type: function
        name: ad_delete
        action: replace_function    # same convention; no try/except remains
    semantic_anchors:
      keep_unchanged:
        - the 403 body bytes — "You do not have permission to delete this
          ad." (now produced via _ownership_refused_forbidden; identical bytes)
        - gate-free by design: NO consent check line anywhere in the delete
          flow; reactivating consent requirements stay archive/reactivate-only
        - @require_POST + @login_required decorators, URL name ads:delete,
          redirect("ads:dashboard") on success
        - re-delete already-DELETED rows is still a service-tier no-op (302,
          row untouched) — the view does not pre-read status

  # ── 3. Tests — call-shape-only edits, relocations, one rewrite ───────────
  - path: src/backend/apps/ads/tests/test_lifecycle_service.py
    targets:
      - type: module_docstring
        name: test_lifecycle_service module docstring
        change: >
          drop "so a future API caller inherits the same proofs"; state the
          B6 split: this module proves the service's state mechanics on a
          caller-fetched row (matrices, verdicts, rollback, analytics,
          gate-freeness); the HTML boundary suites in test_edit.py /
          test_delete.py own the fetch/refusal coverage (missing ad, wrong
          owner), relocated here from the service tier by this task.
      - type: import_block
        name: module imports
        change: >
          remove `from django.core.exceptions import PermissionDenied` and
          `from django.http import Http404` (no longer raised by the service);
          keep patch, Ad, the lifecycle imports, AnalyticsEvent, enums,
          conftest fixtures.
      - type: test
        name: TestArchiveAd::test_published_ad_is_archived_with_archived_at
        change: call-shape only — archive_ad(ad) (drop ad.id, seller.id)
      - type: test
        name: TestArchiveAd::test_archive_records_no_analytics_event
        change: call-shape only — archive_ad(ad)
      - type: test
        name: TestArchiveAd::test_non_published_ad_is_silent_noop
        change: call-shape only — archive_ad(ad)
      - type: test
        name: TestArchiveAd::test_consent_gate_is_caller_side
        change: >
          call-shape only — archive_ad(ad) with owner; reword the docstring's
          "API callers assert theirs at their own boundary" to the boundary
          being the HTML view (the gate stays caller-side; the service must
          not duplicate it).
      - type: test
        name: TestArchiveAd::test_non_owner_is_refused_and_ad_unchanged
        action: delete_symbol   # relocated: existing
                                   TestAdArchive::test_archive_wrong_user_returns_403
                                   + new bytes pin in test_edit.py
      - type: test
        name: TestArchiveAd::test_missing_ad_raises_http404
        action: delete_symbol   # relocated: NEW HTML
                                   TestAdArchive::test_archive_missing_ad_returns_404
      - type: test
        name: TestReactivateAd::test_passing_check_publishes_and_records_events
        change: call-shape only — reactivate_ad(archived_ad)
      - type: test
        name: TestReactivateAd::test_failing_check_commits_on_moderation_failed
        change: call-shape only — reactivate_ad(archived_ad)
      - type: test
        name: TestReactivateAd::test_check_error_rolls_back_to_archived
        change: >
          call-shape only — reactivate_ad(archived_ad); this test IS the
          savepoint guard and must stay green byte-unchanged apart from the
          call site (it patches
          apps.ads.services.lifecycle.auto_moderation.auto_moderate).
      - type: test
        name: TestReactivateAd::test_non_archived_ad_is_silent_noop
        change: call-shape only — reactivate_ad(ad)
      - type: test
        name: TestReactivateAd::test_non_owner_is_refused_and_ad_unchanged
        action: delete_symbol   # relocated: existing wrong-user 403 + new bytes
                                   pin in test_edit.py
      - type: test
        name: TestReactivateAd::test_missing_ad_raises_http404
        action: delete_symbol   # relocated: NEW HTML
                                   TestAdReactivateDirect::test_reactivate_missing_ad_returns_404
      - type: test
        name: TestDeleteAd::test_any_status_transitions_to_deleted
        change: call-shape only — delete_ad(ad)
      - type: test
        name: TestDeleteAd::test_already_deleted_is_noop
        change: call-shape only — delete_ad(ad)
      - type: test
        name: TestDeleteAd::test_consent_gate_is_caller_side
        change: call-shape only — delete_ad(ad) with a never-consented owner
      - type: test
        name: TestDeleteAd::test_non_owner_is_refused_and_ad_unchanged
        action: delete_symbol   # relocated: existing
                                   TestAdDelete::test_delete_wrong_user_returns_403
                                   (+ bytes pin added there)
      - type: test
        name: TestDeleteAd::test_missing_ad_raises_http404
        action: delete_symbol   # relocated: NEW HTML
                                   TestAdDelete::test_delete_missing_ad_returns_404
      - type: class
        name: TestArchiveAd / TestReactivateAd / TestDeleteAd class docstrings
        change: >
          trim the "+ ownership + lock" phrase from TestArchiveAd's docstring
          and the equivalent service-owns-authorization claims — the class
          docstrings must say state mechanics on a caller-fetched row.
    semantic_anchors:
      keep_unchanged:
        - every retained assertion body — result NamedTuple comparisons,
          refresh_from_db status/assert/timestamp assertions, analytics
          _event_types assertions, parametrize tables (no-op matrices
          unchanged)
        - the archived_ad fixture (its transition_to stays a direct model call
          in test setup — it is NOT a service consumer)
        - a plain unlocked instance is a valid service argument (the
          service's own atomic owns the standalone case) — do NOT wrap the
          relocations' fixtures in select_for_update

  - path: src/backend/apps/ads/tests/test_edit.py
    targets:
      - type: import_block
        name: module imports
        change: remove `from django.core.exceptions import PermissionDenied`
          (its only uses die with the belt class)
      - type: class
        name: TestLifecycleOwnershipRefusalBelt
        action: replace_symbol   # becomes TestLifecycleOwnershipRefusal
      - type: leading_comment
        name: belt section banner
        change: >
          "# Lifecycle ownership-refusal belt: a late PermissionDenied keeps
          the owner 403" banner → the single-path refusal banner the new
          class docstring names.
      - type: test
        name: TestAdArchive::test_archive_missing_ad_returns_404   # NEW
        action: add_code
      - type: test
        name: TestAdReactivateDirect::test_reactivate_missing_ad_returns_404   # NEW
        action: add_code
    semantic_anchors:
      keep_unchanged:
        - TestAdArchive (owner 302, wrong-user 403+row-unchanged, no-op),
          TestAdArchiveGetRejected, TestAdReactivateDirect (owner 302 +
          PUBLISHED, wrong-user 403, non-ARCHIVED no-op, GET 405,
          banning_criteria moderation-failure message, patched auto_moderate
          raise -> "stays archived"), TestBannedSellerRelistNowRefused,
          TestSellerWebStorageConsentGate (archive/reactivate consent-403
          ordering rows) — byte-green through the new shape; these are the
          pinned happy/refusal sides FIRST
        - every edit-flow suite in the file (reactivation/price/text classes,
          TestEditSubmissionRefusalsRender, TestApplyPriceChangeDelegation,
          TestEditAuthorization, TestEditGetPath,
          TestEditOtherStatusDirectSave, TestEditStatusAllowListEnumeration,
          TestDashboardEditLinkGate) — untouched by B6

  - path: src/backend/apps/ads/tests/test_delete.py
    targets:
      - type: test
        name: TestAdDelete::test_delete_missing_ad_returns_404   # NEW
        action: add_code
      - type: test
        name: TestAdDelete::test_delete_wrong_user_returns_403
        change: >
          add the 403 message-bytes pin (bytes check for "You do not have
          permission to delete this ad.") so the _ownership_refused_forbidden
          swap is proven byte-identical; keep the status + row-unchanged
          assertions.
      - type: module_docstring
        name: test_delete module docstring
        change: add the missing-ad 404 row to the Covers list
    semantic_anchors:
      keep_unchanged:
        - TestAdDelete owner-302 + DELETED + deleted_at, re-delete no-op,
          TestAdDeleteGetRejected 405 — byte-unchanged
        - no consent test ever appears in this file (delete is gate-free)

  - path: src/backend/apps/ads/tests/test_edit_views_locking.py
    targets:
      - type: module_docstring
        name: locking module docstring
        change: >
          docstring wording only — "the second proves the row lock taken by
          the ownership precheck is still held at the service-call instant"
          → "taken by the view's locked fetch". Zero code bytes change.
      - type: docstring
        name: TestLifecycleActionLockContinuity class docstring
        change: >
          "The row lock taken by the precheck is still held at the
          service-call instant." → "taken by the view's locked fetch". Same
          one-word-y family fix; the test method body, fixtures, parametrize
          tables and sentinels are byte-frozen.
    semantic_anchors:
      keep_unchanged:
        - every class and method in the file byte-identical (module code):
          TestEditViewsLocking sentinels, TestEditViewsRowLockConcurrency,
          TestLifecycleActionAtomicContinuity, TestLifecycleActionLockContinuity
          — they are the G2 seam and observation points B6 is required to
          pass code-unchanged

  # ── Explicitly NOT changing ───────────────────────────────────────────────
  - path: src/backend/apps/ads/urls.py
    action: keep_byte_identical   # routes for ad_archive/ad_reactivate/ad_delete
  - path: src/backend/apps/ads/views/dashboard.py
    action: keep_byte_identical   # imports _seller_may_create_ad +
                                  # _consent_required_forbidden from edit.py
  - path: src/backend/apps/ads/services/edit_flow.py
    action: keep_byte_identical
  - path: src/backend/apps/core/middleware/db_lock_timeout.py
    action: keep_byte_identical   # predicate-gated; its "six lock-acquiring
                                  # views" docstring becomes literally true at
                                  # the view tier (ad_delete now locks in-view)

# ─────────────────────────────────────────────────────────────────────────────
# Changes with code hints (contract shapes — implement against the live code)
# ─────────────────────────────────────────────────────────────────────────────

changes:

  - action: modify_code
    target: apps/ads/services/lifecycle.py::archive_ad
    description: >
      Locked-instance operation. The function's own atomic() nests as a
      savepoint inside the caller's block; standalone it is the whole
      transaction. Docstring records the convention once (see module docstring
      target); Raises keeps only ValueError (transition_to matrix).
    code_hint: |
      def archive_ad(ad: Ad) -> ArchiveResult:
          """Apply PUBLISHED -> ARCHIVED to a row the caller fetched, locked, and authorized."""
          with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # savepoint inside the caller's block
              if ad.status == AdStatus.PUBLISHED:
                  ad.transition_to(AdStatus.ARCHIVED)
                  logger.info("Ad %s archived by user %s", ad.id, ad.user_id)
                  return ArchiveResult(archived=True)
          return ArchiveResult(archived=False)

  - action: modify_code
    target: apps/ads/services/lifecycle.py::reactivate_ad
    description: >
      Same convention. The transition and the content check stay inside ONE
      atomic block — the rollback mechanism MANDATED by
      test_check_error_rolls_back_to_archived; keep the existing rollback
      comment and the database-error propagation paragraph.
    code_hint: |
      def reactivate_ad(ad: Ad) -> ReactivateResult:
          with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
              if ad.status != AdStatus.ARCHIVED:
                  return ReactivateResult(attempted=False, passed=None)
              ad.transition_to(AdStatus.ON_MODERATION)
              # a raising check rolls the transition back: the ad stays
              # ARCHIVED, the safe state (comment content unchanged)
              passed = auto_moderation.auto_moderate(ad)
          return ReactivateResult(attempted=True, passed=passed)

  - action: modify_code
    target: apps/ads/services/lifecycle.py::delete_ad
    description: >
      Same convention; gate-free by design (caller-side consent never applies
      to delete). No-op short-circuit and log stay as-is.
    code_hint: |
      def delete_ad(ad: Ad) -> DeleteResult:
          with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
              if ad.status == AdStatus.DELETED:
                  return DeleteResult(deleted=False)
              # transition_to sets deleted_at and refreshes updated_at.
              ad.transition_to(AdStatus.DELETED)
              logger.info("Ad %s deleted by user %s", ad.id, ad.user_id)
              return DeleteResult(deleted=True)

  - action: modify_code
    target: apps/ads/views/edit.py::ad_archive
    description: >
      The ad_edit POST shape, with no try/except at all: the locked fetch
      raises Http404 to Django's 404 handler, a wrong owner gets the ownership
      403 bytes, consent refusal stays second, and the service call is the
      last statement inside the open block. The precheck and BOTH belt
      handlers are gone with it.
    code_hint: |
      @require_POST
      @login_required
      def ad_archive(request: HttpRequest, ad_id: int) -> HttpResponse:
          with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
              ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)
              if ad.user_id != request.user.id:
                  return _ownership_refused_forbidden(
                      _("You do not have permission to archive this ad."),
                      "archive",
                      ad_id,
                      request.user.id,
                  )
              if not _seller_may_create_ad(request.user):
                  return _consent_required_forbidden(request.user, ad_id)
              archive_ad(ad)
          return redirect("ads:dashboard")

  - action: modify_code
    target: apps/ads/views/edit.py::ad_reactivate
    description: >
      Same shape, PLUS the preserved outer try with the B1 handler order
      minus the belt: `except (Http404, DatabaseError): raise` (the fetch can
      now raise Http404 inside the block; a lock timeout keeps escaping to
      DbLockTimeoutMiddleware) sits BEFORE `except Exception:` (unchanged
      moderation-failure reporting). No PermissionDenied handler remains
      anywhere. The passed False / passed dashboard branches after the try
      are byte-unchanged.
    code_hint: |
      passed: bool | None = None
      try:
          with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
              ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)
              if ad.user_id != request.user.id:
                  return _ownership_refused_forbidden(
                      _("You do not have permission to reactivate this ad."),
                      "reactivate",
                      ad_id,
                      request.user.id,
                  )
              if not _seller_may_create_ad(request.user):
                  return _consent_required_forbidden(request.user, ad_id)
              passed = reactivate_ad(ad).passed
      except (Http404, DatabaseError):
          raise
      except Exception:
          # unchanged: logger.exception("Ad %s reactivation failed during
          # auto-moderation", ad_id) + messages.error + redirect
          ...
      # unchanged: passed is False -> messages.warning; passed -> log; redirect

  - action: modify_code
    target: apps/ads/views/delete.py::ad_delete
    description: >
      Delete joins the convention (this is what makes _fetch_owned_ad fully
      dead). atomic -> locked fetch -> ownership 403 via the shared helper
      (identical 403 bytes, plus the ownership warning log) -> delete_ad(ad).
      No consent line by design. No catch remains — a lock timeout escapes to
      the predicate-gated middleware (503), exactly as before via a different
      tier. Http404 from the fetch goes to Django's 404 handler.
    code_hint: |
      @require_POST
      @login_required
      def ad_delete(request: HttpRequest, ad_id: int) -> HttpResponse:
          with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
              ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)
              if ad.user_id != request.user.id:
                  return _ownership_refused_forbidden(
                      _("You do not have permission to delete this ad."),
                      "delete",
                      ad_id,
                      request.user.id,
                  )
              delete_ad(ad)
          return redirect("ads:dashboard")

  - action: modify_tests
    target: the four test modules (files section above)
    description: >
      Call-shape-only edits in test_lifecycle_service.py (retained matrices,
      verdicts, rollback, analytics, gate-freeness); the six refusal relocations
      per the ledger; TestLifecycleOwnershipRefusalBelt rewritten into the
      real-path TestLifecycleOwnershipRefusal; three new missing-ad 404 tests;
      delete bytes pin; "precheck" docstring truthing. Details in required_tests.

  - action: delete_code
    target: the belt + precheck machinery (all deletions, verified zero refs)
    description: >
      lifecycle.py::_fetch_owned_ad, lifecycle.py::assert_lifecycle_owner,
      the PermissionDenied/Http404 imports in lifecycle.py, the try/except
      PermissionDenied precheck blocks in ad_archive/ad_reactivate, the
      except PermissionDenied belt handlers (edit.py outer + archive inner),
      delete.py's inline try/except PermissionDenied + its PermissionDenied and
      HttpResponseForbidden imports, test_edit.py's PermissionDenied import,
      and the six relocated service-tier refusal tests. After the change,
      grep src/ for assert_lifecycle_owner and _fetch_owned_ad returns
      NOTHING (production, tests, docs-comments alike).

# Implementation sequence (working order; ALL steps land in ONE coherent
# commit — no deployable intermediate revision may exist with the instance
# service signature but id-based callers, or the belt removed but the precheck
# kept; B1 recorded the belt+precheck pairing as misleading if split):
sequence:
  1: >
     Service: lifecycle.py — three replace_function bodies + docstrings,
     delete_symbol _fetch_owned_ad / assert_lifecycle_owner, import cleanup.
     Production callers are now intentionally broken by design — do NOT run
     the suite or commit yet.
  2: >
     Views: views/edit.py (ad_archive / ad_reactivate shapes, both belts and
     the precheck deleted, assert_lifecycle_owner + PermissionDenied imports
     dropped, docstrings truthed, module-doc /api/v1/ clause optional ride-along)
     and views/delete.py (convention adoption, imports, docstring). Production
     is self-consistent again.
  3: >
     Tests: test_lifecycle_service.py (module docstring, call-shape edits,
     six refusal relocations OUT), test_edit.py (belt rewrite into
     TestLifecycleOwnershipRefusal, two new missing-ad 404 tests,
     PermissionDenied import out, section banner), test_delete.py (new
     missing-ad 404 test, bytes pin on the wrong-owner test, docstring row),
     test_edit_views_locking.py ("precheck" -> view's locked fetch, both
     occurrences).
  4: >
     Verification: the focused docker run (below, includes the slow/concurrent
     parked-seam tests because it sets no PYTEST_SKIP_MARKERS), the stale-
     reference greps, ruff, basedpyright, then .\Makefile.ps1 test; only then
     the single commit (message below).

architectural_constraints:
  - One operation implementation and one transaction owner per action: the
    view owns transaction + row lock + authorization (+ consent for
    archive/reactivate); the service owns state mechanics + moderation on the
    locked row. Never move ownership or consent into the service (audit
    alternative D rejected; the delete path must NEVER consult consent).
  - Every service function KEEPS its own transaction.atomic(): it is the
    moderation-rollback SAVEPOINT (nested) / standalone transaction, the
    mechanism test_check_error_rolls_back_to_archived pins. Do not factor
    it out, flag it, or treat it as redundant nesting.
  - Signature churn is bounded to (ad_id, user_id) -> (ad) on exactly
    archive_ad / reactivate_ad / delete_ad. No flags, no optional kwargs, no
    renames of functions, result NamedTuples, views, URLs, __all__ entries,
    messages, or log format strings.
  - archive_ad and reactivate_ad stay module-level imports in
    views/edit.py: the B1 G2 tests monkeypatch the view-module seam
    (apps.ads.views.edit.archive_ad / .reactivate_ad) and the boundary tests
    patch the shared Ad.objects manager — both seams must survive.
  - Ownership-before-consent-before-action is literal statement order inside
    the view's atomic block; the 403s come from _ownership_refused_forbidden /
    _consent_required_forbidden with unchanged message bytes and log lines.
  - Exception surface may only SHRINK: no new catch clauses anywhere; no
    catch that could swallow OperationalError/DatabaseError; ad_reactivate
    keeps `except (Http404, DatabaseError): raise` ordered before
    `except Exception:` (a service-side non-database failure -> dashboard
    message + rollback stays); ad_archive and ad_delete end with no catch.
  - The 03-DB-004 lock-timeout boundary is untouched: OperationalError
    escapes both lifecycle views and delete to the predicate-gated
    DbLockTimeoutMiddleware (503 + Retry-After; SQLSTATE 55P03 only).
  - Cross-view private imports follow the dashboard.py precedent
    (_seller_may_create_ad / _consent_required_forbidden); do NOT move
    _ownership_refused_forbidden into a new module (no new surface, no new
    file — workspace cleanliness).
  - No new translatable msgids; every retained/relocated user-visible string
    already exists in the ru/bs/en catalogs; no .po/.mo edit; i18n catalog
    files are not touched by this task.
  - No schema/model/migration/settings/env/middleware/dependency/lockfile
    change; no bot-workflow change; no template change.
  - English only for all comments/docstrings/messages; keep the pyright
    ignore comments on every moved transaction.atomic() (django-stubs not
    installed).

required_tests:
  service_call_shape_only: >
    test_lifecycle_service.py — the retained surface changes ONLY its call
    sites from archive_ad(ad.id, seller.id) style to archive_ad(ad) etc.:
    archive (happy path + archived_at, no-analytics, 6-way no-op matrix,
    gate-free), reactivate (pass verdict + analytics pair, fail verdict +
    ON_MODERATION_FAILED, non-ARCHIVED 7-way no-op matrix), delete (5-way
    status matrix, already-DELETED no-op, gate-free). All NamedTuple
    comparisons, refresh_from_db assertions, analytics _event_types rows and
    the parametrize tables stay byte-identical. Docstrings truthed where the
    module hunks falsified them (module docstring future-API claim, the
    gate-free test's "API callers" sentence, class docstring "+ ownership +
    lock" claims).
  relocate_six_refusals: >
    Ledger (B6 audit; plan §6 rule): TestArchiveAd::test_non_owner_is_refused_
    and_ad_unchanged -> existing TestAdArchive::test_archive_wrong_user_
    returns_403 + new bytes pin; TestArchiveAd::test_missing_ad_raises_http404
    -> NEW TestAdArchive::test_archive_missing_ad_returns_404;
    TestReactivateAd::test_non_owner_is_refused_and_ad_unchanged -> existing
    TestAdReactivateDirect::test_reactivate_wrong_user_returns_403 + bytes
    pin; TestReactivateAd::test_missing_ad_raises_http404 -> NEW
    TestAdReactivateDirect::test_reactivate_missing_ad_returns_404;
    TestDeleteAd::test_non_owner_is_refused_and_ad_unchanged -> existing
    TestAdDelete::test_delete_wrong_user_returns_403 (+ bytes pin);
    TestDeleteAd::test_missing_ad_raises_http404 -> NEW
    TestAdDelete::test_delete_missing_ad_returns_404. The empty service-tier
    "ownership refusals" claim is replaced by the gate-free tests only —
    ownership is boundary-owned now; do not delete any retained row blindly.
  html_missing_ad_404: >
    Three NEW tests, one per action, all real-path: an authenticated owner
    POSTs reverse("ads:archive" | "ads:reactivate" | "ads:delete",
    args=[999_999_999]) -> assert response.status_code == 404. These prove
    get_object_or_404 inside the atomic block replaced the service's Http404
    one-for-one (the relocated service-tier 404 coverage).
  ownership_refusal_real_path: >
    test_edit.py — TestLifecycleOwnershipRefusalBelt (monkeypatched seam
    raising PermissionDenied) is REWRITTEN as TestLifecycleOwnershipRefusal:
    real-path wrong-owner POSTs (the `user` fixture attacking the `seller`'s
    ad) to archive (PUBLISHED ad) and reactivate (ARCHIVED ad). Each asserts
    403, the exact ownership message bytes (b"You do not have permission to
    archive this ad." / b"You do not have permission to reactivate this
    ad."), and the row unchanged; the reactivate test additionally asserts
    "reactivation failed during auto-moderation" not in caplog.text (the
    refusal can never masquerade as a moderation failure — the B1 belt-order
    property, now structural). Class docstring states the single 403 path and
    why no belt exists. No monkeypatch anywhere in the new class.
  delete_bytes_pin: >
    test_delete.py — the existing TestAdDelete::test_delete_wrong_user_
    returns_403 gains `assert b"You do not have permission to delete this
    ad." in response.content`, pinning that routing the 403 through
    _ownership_refused_forbidden kept the response byte-identical to the old
    inline HttpResponseForbidden, and that it fired the ownership warning log.
  g2_code_unchanged: >
    NO code change (this is the acceptance, not a to-do):
    TestLifecycleActionAtomicContinuity (in_atomic_block True observed at the
    view-module seam entry — the service call is the view's last in-block
    statement, the service savepoint opens after the observation);
    TestLifecycleActionLockContinuity (parked seam + 55P03 probe — at that
    instant the row is locked by the view's own select_for_update fetch,
    same transaction, same lock, same instant); TestAdArchiveLockTimeout and
    TestAdReactivateLockTimeout (test_db_lock_timeout_boundary.py patches the
    shared Ad.objects manager — the single first acquisition now happens at
    the view fetch; OperationalError still escapes: ad_archive has no catch,
    ad_reactivate re-raises it via the ordered handler). Both boundary tests
    stay green. The ONLY edit in the file is the docstring truthing
    ("precheck" -> view's locked fetch, two occurrences).
  gate_free_kept: >
    The two test_consent_gate_is_caller_side service tests and
    TestSellerWebStorageConsentGate (HTML) stay green: the service still
    never reads consent; delete still has no consent test (stays gate-free).

verification:
  focused_b6: >
    docker compose --project-name mko-bazuna-test --env-file .env.test -f
    docker-compose.yml -f docker-compose.test.yml run --rm -e
    "PYTEST_OPTS=src/backend/apps/ads/tests/test_edit.py src/backend/apps/ads/tests/test_edit_views_locking.py
    src/backend/apps/ads/tests/test_lifecycle_service.py src/backend/apps/ads/tests/test_delete.py
    src/backend/apps/ads/tests/test_ad_lifecycle.py src/backend/apps/ads/tests/test_ad_consent_gate.py
    src/backend/apps/ads/tests/test_edit_flow_service.py src/backend/apps/core/tests/test_db_lock_timeout_boundary.py"
    test
  focused_notes: >
    This invocation sets NO PYTEST_SKIP_MARKERS, so the slow/concurrent
    parked-seam tests (TestLifecycleActionLockContinuity,
    TestEditViewsRowLockConcurrency) run too — this IS the audit's one
    targeted -m slow/concurrent run for the parked seam, folded into the
    focused gate. PYTEST_OPTS is expanded before the fixed PYTEST_DEFAULTS
    (reuse-db + xdist loadgroup stay active); bare file paths are safe
    through the unquoted expansion; never pass shell-quoted multiword
    values. Start the DB if needed:
    docker compose --project-name mko-bazuna-test --env-file .env.test -f
    docker-compose.yml -f docker-compose.test.yml up -d db
  stale_reference_greps: >
    git grep -n "assert_lifecycle_owner" -- src/   (must be empty);
    git grep -n "_fetch_owned_ad" -- src/          (must be empty);
    git grep -n "TestLifecycleOwnershipRefusalBelt" -- src/ (must be empty);
    git grep -n "PermissionDenied" -- src/backend/apps/ads/services/lifecycle.py
    src/backend/apps/ads/views/edit.py src/backend/apps/ads/views/delete.py
    src/backend/apps/ads/tests/test_edit.py  (must be empty)
  lint: uv run ruff check src/backend/apps/ads src/backend/apps/core
  typecheck: >
    uv run basedpyright src/backend/apps/ads/services/lifecycle.py
    src/backend/apps/ads/views/edit.py src/backend/apps/ads/views/delete.py
    src/backend/apps/ads/tests/test_lifecycle_service.py
    src/backend/apps/ads/tests/test_edit.py
    src/backend/apps/ads/tests/test_delete.py
    src/backend/apps/ads/tests/test_edit_views_locking.py
  fast_gate: .\Makefile.ps1 test     # canonical PR gate (seed/slow/real_images
                                     # skipped; the parked-seam slow tests are
                                     # covered by focused_b6's no-skip run)
  notes: >
    Never run `uv run pytest` locally (no DB on localhost:5432). No full
    .\Makefile.ps1 test-all run is required for B6 (no seed/real_images
    surface is touched); B8 owns the final measurement tier. No migration
    delta is expected (no model change) — the dev-service makemigrations
    --check from plan §8 is optional reassurance only. git status --short
    must show EXACTLY the seven files: services/lifecycle.py, views/edit.py,
    views/delete.py, tests/test_lifecycle_service.py, tests/test_edit.py,
    tests/test_delete.py, tests/test_edit_views_locking.py.

acceptance_criteria:
  - >
    Convention: one operation implementation and one transaction owner per
    action. Each view opens atomic(), locks via get_object_or_404 +
    select_for_update, owns the ownership 403 (and consent 403 for
    archive/reactivate), and calls the service on the locked instance as its
    last in-block statement. Ownership is checked exactly once per request
    path; no redundant fetch, no second locked read, no precheck refetch.
  - >
    Deletions complete: assert_lifecycle_owner and _fetch_owned_ad are gone;
    both view belt handlers and delete.py's inline PermissionDenied handler
    are gone; the stale_reference_greps return empty. No production
    PermissionDenied/Http404 import remains in lifecycle.py; no belt-class
    name remains.
  - >
    Signatures churned exactly once, exactly three times:
    archive_ad(ad)/reactivate_ad(ad)/delete_ad(ad); names, result
    NamedTuples, outcome values (incl. ReactivateResult.passed), URL names
    (ads:archive|reactivate|edit|delete), views/edit.py __all__, and every
    retained user-visible message byte are unchanged.
  - >
    G2 still meaningful: TestLifecycleActionAtomicContinuity,
    TestLifecycleActionLockContinuity, TestAdArchiveLockTimeout and
    TestAdReactivateLockTimeout pass with ZERO code change (the file's only
    edit is the two "precheck"->"view's locked fetch" docstring fixes);
    focused_b6 runs them without marker exclusion and is green, including
    the parked-seam slow/concurrent tests.
  - >
    Rollback and boundaries preserved: test_check_error_rolls_back_to_archived
    green through the retained service atomic(); the 03-DB-004 lock timeout
    still escapes ad_archive/ad_reactivate/ad_delete to the predicate-gated
    middleware (503); ad_reactivate's except (Http404, DatabaseError): raise
    still precedes except Exception (unreachable-since-belt-removal
    PermissionDenied handling introduces no new catch).
  - >
    Ordering and gate-freeness pinned: ownership-before-consent-before-action
    proven by TestLifecycleOwnershipRefusal (real-path 403 message bytes +
    row unchanged + no moderation-failure log on the reactivate refusal),
    TestSellerWebStorageConsentGate and TestBannedSellerRelistNowRefused stay
    green; delete stays consent-free single-call (no consent test in
    test_delete.py; gate-free service tests retained).
  - >
    Coverage ledger closed: the six relocated service refusals all have named
    destinations — three new real-path missing-ad 404 tests (archive /
    reactivate / delete), existing wrong-owner tests retained, archive+
    reactivate+delete refusal bytes pinned; no other collected test was
    modified beyond the enumerated call-shape edits.
  - >
    Hygiene: ruff clean and basedpyright clean on the changed files;
    .\Makefile.ps1 test green; English-only comments; no new msgids; no
    schema/migration/settings/env/middleware/dependency/lockfile/i18n delta;
    git status --short lists exactly the seven task files.

out_of_scope:
  - FTS public helper renaming — plan P6 marks it optional coordinated
    cleanup; SKIP it here.
  - B7's commentary/doc/catalog sweep: the "future /api/v1/" docstring
    claims in the ~11 retained files B6 does not touch (dashboard_query.py,
    edit_flow.py, favorites.py, listings_query.py, favorite.py, cabinet
    views, saved-search modules, test_listings_query.py), spec-index /
    architecture-structure / 99-agent task->service map, and i18n catalog
    pruning. The views/edit.py module-docstring /api/v1/ edit-endpoint clause
    is B7-owned and only an optional ride-along.
  - Any behavior change to retained outcomes, messages, redirects, URLs,
    or the moderation pipeline; any schema/model/migration, settings/env,
    middleware, dependency, or lockfile change; any bot/template change.
  - Any signature change beyond (ad_id, user_id) -> (ad): no flags, optional
    kwargs, re-export reshaping, gate moves into the service, or renames of
    archive_ad/reactivate_ad/delete_ad, result types, view names, URL names.
  - Any new exception handling anywhere (audit alternatives B/C rejected —
    no for_update=False knobs, no id-based delete holdover).
  - Full test-all tier and any measurement/effort reporting (B8 owns it).

risks:
  - >
    Dropping the service savepoint: a "helpful" implementor sees the view's
    atomic() and deletes the service's own transaction.atomic() as redundant
    nesting — silently losing the moderation-rollback mechanism
    (test_check_error_rolls_back_to_archived pins it; a diff that removes any
    atomic() from lifecycle.py is wrong). Mitigation: the keep_unchanged
    anchor, the code hints, and the rollback test.
  - >
    Adding catches that swallow OperationalError: re-pointing the fetch into
    the view invites a new except around it. The 03-DB-004 boundary survives
    only if the exception surface shrinks. Mitigation: no new catch clauses;
    ordered handlers preserved verbatim; TestAdArchiveLockTimeout /
    TestAdReactivateLockTimeout / test_db_lock_timeout.py stay green.
  - >
    Breaking G2 meaning: renaming the services, inlining them, or moving the
    call out of the atomic block would void the view-module seam and the
    observation instants the B1 tests rely on. Mitigation: keep
    module-level archive_ad/reactivate_ad imports in views/edit.py, keep the
    service call as the last in-block statement, run focused_b6 without
    marker exclusion; only the belt-class premise is deleted (its rewrite is
    B1's own scheduled hand-off).
  - >
    Unnecessary signature churn: renaming results/views/URLs, moving helpers,
    or restructuring tests beyond the ledger. Mitigation: bounded (ad)-only
    signature delta; ruff/basedpyright over the seven files; grep for
    leftover id-style lifecycle calls.
  - >
    Splitting the belt from the precheck (or vice versa) into separate
    commits: B1 recorded that as a misleading intermediate shape. Mitigation:
    one coherent commit; sequence forbids intermediate commits.
  - >
    Delete refusal-log wording change could surprise log greppers: the wrong-
    owner delete warning switches to the ownership helper's wording —
    audit-sanctioned, log-only (no user-visible or HTTP change); the 403 body
    bytes are pinned by the new bytes assertion.

commit:
  message: >
    refactor(ads): adopt single locked-ad lifecycle convention
  body: >
    Service: archive_ad/reactivate_ad/delete_ad take the locked Ad instance
    instead of (ad_id, user_id); names, result NamedTuples, outcome values and
    log format strings unchanged; each keeps its own transaction.atomic()
    (moderation-rollback savepoint); delete assert_lifecycle_owner,
    _fetch_owned_ad and the Http404/PermissionDenied imports. HTML views own
    fetch + lock + authorization (+ consent, non-delete): ad_archive and
    ad_reactivate adopt the ad_edit POST shape (atomic, locked fetch,
    ownership 403 via _ownership_refused_forbidden, consent gate, instance
    service call), the B1 belt handlers are deleted together with the
    assert_lifecycle_owner precheck, and ad_reactivate keeps the ordered
    except (Http404, DatabaseError): raise before except Exception
    (03-DB-004 boundary untouched). ad_delete joins the convention (same 403
    bytes via the shared helper, ownership warn log added, gate-free, no
    catches left). Tests: six service-tier refusal tests relocated to the
    HTML tier (three new real-path missing-ad 404 tests, wrong-owner byte
    pins), TestLifecycleOwnershipRefusalBelt rewritten into the real-path
    TestLifecycleOwnershipRefusal, service suites changed call shape only;
    the B1 G2 tests pass code-unchanged (one docstring word truthed).
    Docstrings: lifecycle contract paragraphs and delete.py's "future
    /api/v1/" claim rewritten to the shipped convention. No behavior,
    schema, or i18n change.
  files_hint: >
    single coherent commit covering all seven files (services/lifecycle.py,
    views/edit.py, views/delete.py, tests/test_lifecycle_service.py,
    tests/test_edit.py, tests/test_delete.py, tests/test_edit_views_locking.py);
    no deployable intermediate revision may exist with mismatched service/view
    call signatures or the belt removed without the precheck.
```
