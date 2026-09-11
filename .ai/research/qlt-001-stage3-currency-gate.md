---
id: qlt-001-stage3-currency-gate
domain: research
phase: code-quality
tags: [qlt-001, decision-gate, currency-coercion, submission-orchestrator]
related:
  - .ai/plans/24-code-quality-fixes-execution.md
  - .ai/audit/99-validation/10-code-quality-source-reaudit.md
  - .ai/research/qlt-001-stage1-decision.md
  - src/backend/apps/ads/services/submission.py
  - src/backend/apps/ads/views/edit.py
  - src/telegram_bot/handlers/ad_create.py
  - src/backend/apps/currencies/enums.py
---

# QLT-001 Stage 3 — Block 12 (A4) Currency Coercion Decision Gate

**Gate:** Reconcile the bot's "invalid currency → None" coercion in `submit_ad` with the web edit
path's "keep current currency on invalid" behavior, when routing the `ad_edit` reactivation branch
through `submit_ad`.

**Status:** RESOLVED — Path 2 (document as intentional divergence) selected.

**Researcher confidence:** HIGH (all claims verified against current source at HEAD `9bc5c4c`,
2026-09-11).

---

## 0. Current state of the QLT-001 rollout

Git log confirms the staged rollout is partially complete:

| Block | Commit | Status |
|-------|--------|--------|
| A1 (inert `submission.py`) | `bb2cccb` | **DONE** |
| A2 (bot rewire to `submit_ad`) | `9bc5c4c` | **DONE** |
| A3 (`test_edit.py`) | — | **NOT DONE** (file does not exist) |
| A4 (edit reactivation → `submit_ad`) | — | **PENDING** (currency gate) |

`ad_create.py` (line 25) imports `SubmitAdInput, submit_ad` and calls
`await sync_to_async(submit_ad)(SubmitAdInput(...))` at line 813. The old
`update_ad_and_moderate` function has been **deleted** — confirmed: zero grep hits for
`def update_ad_and_moderate` in `ad_create.py`.

The reactivation branch in `edit.py` is **still inline** (lines 163–194) — not yet migrated.
`test_edit.py` does **not** exist (Block 11/A3 is a blocking precondition that has not shipped).

---

## 1. How does `_apply_price_change` work? (Question 1)

**Finding:** `_apply_price_change` does **NOT** perform currency coercion. The coercion
(including the "keep current on invalid" fallback) lives in `ad_edit` itself, not in
`_apply_price_change`.

### Actual `_apply_price_change` (edit.py:29–62)

```python
def _apply_price_change(
    ad: Ad,
    price_amount: Decimal,
    price_currency: CurrencyCode | None,
) -> Ad:
    ad.price_amount = price_amount
    if price_currency is not None:
        ad.price_currency = price_currency.value
    if price_currency is not None:
        try:
            ad.price_normalized_eur = PriceNormalizer().normalize_to_eur(
                price_amount, price_currency
            )
        except Exception:
            logger.exception("Failed to normalize price for ad %s", ad.pk)
            ad.price_normalized_eur = None
    else:
        ad.price_normalized_eur = None
    return ad
```

The function receives an **already-coerced** `price_currency: CurrencyCode | None` and:
- Sets `ad.price_currency = price_currency.value` when not None (line 51).
- Computes `price_normalized_eur` via `PriceNormalizer` (lines 53–58).
- Does NOT call `CurrencyCode(str(...))` — no `ValueError` recovery here.

### Where the "keep current" logic actually lives (edit.py:148–158)

```python
# Parse the currency; fall back to the ad's current currency when
# unset/invalid. Do not coerce to None — a price (incl. Free=0) keeps
# a valid currency for normalized_eur computation.
price_currency_value: CurrencyCode | None = (
    CurrencyCode(ad.price_currency) if ad.price_currency else None
)
if new_price_currency:
    try:
        price_currency_value = CurrencyCode(new_price_currency)
    except ValueError:
        pass  # Keep the ad's current currency (already set above)
```

This produces `price_currency_value` as either:
- A valid `CurrencyCode` (the new valid currency, or the current currency if new is invalid), or
- `None` (only if `ad.price_currency` is falsy AND no new currency was submitted).

**The re-audit (line 77) and plan (Block 12, line 966) both attribute the coercion to
`_apply_price_change`, but the actual code places it in `ad_edit`'s request body (lines 148–158).**
The substantive finding (keep-current-on-invalid) is confirmed, but the attribution is slightly
off. This matters for the decision: the coercion is **shared** across all four branches of
`ad_edit` (reactivation at line 167, text-edit at line 204, price-only at line 221, other-statuses
at line 238).

### Key consequence

Because the currency parsing is computed **once** (lines 148–158) and shared by all branches,
it **cannot be removed** for just the reactivation branch when migrating to `submit_ad`. The
other three branches still need it for their `_apply_price_change` calls. The reactivation
branch will therefore have `price_currency_value` (a valid `CurrencyCode | None`) available
in scope when it calls `submit_ad`.

### Confidence: HIGH

Verified by direct reading of `edit.py:29–62` and `edit.py:148–158`. The `_apply_price_change`
signature takes `CurrencyCode | None` (not `str`), confirming it does not re-parse raw input.

---

## 2. How is the reactivation path structured? (Question 2)

### Structure of `ad_edit` POST handling (edit.py:119–251)

```
POST →
  line 124: with transaction.atomic():           # DB-003 row lock
  line 125:     ad = Ad.objects.select_for_update().get(id=ad_id)   # locked fetch
  lines 128-130: is_reactivation = ad.status == ARCHIVED and POST.get("reactivate")
  lines 133-136: new_title, new_description, new_price_amount, new_price_currency
  lines 141-146: price_amount_value = Decimal(...) or Decimal("0")
  lines 148-158: price_currency_value = pre-coerced CurrencyCode | None   # SHARED
  line 161:     has_text_change = _text_fields_changed(request, ad)

  line 163:     if is_reactivation:              # ← ONLY THIS BRANCH migrates to submit_ad
      line 165:     ad.title = new_title
      line 166:     ad.description = new_description
      line 167:     ad = _apply_price_change(ad, price_amount_value, price_currency_value)
      line 168:     ad.save(update_fields=[...])     # partial save
      line 179:     ad.transition_to(AdStatus.ON_MODERATION)
      line 182:     passed = auto_moderate(ad)        # INSIDE the atomic
      line 184:     if passed: return redirect(dashboard)
      line 189:     else: re-render edit.html with error

  line 196:     elif ad.status == PUBLISHED:       # text-edit / price-only (NOT migrated)
  ...
  line 234:     else:                               # other statuses (NOT migrated)
```

### Key structural facts

1. **No Django Form.** The reactivation branch reads POST data directly via
   `request.POST.get(...)` (lines 133–136). There is no `forms.Form` or `forms.ModelForm`.
2. **`_apply_price_change` is called BEFORE `auto_moderate`** (line 167 → line 182). The
   currency coercion (lines 148–158) happens even earlier, before the `if is_reactivation`
   branch.
3. **`auto_moderate` is called INSIDE `transaction.atomic()`** (line 182, within the `with`
   block at line 124). This is a **pre-existing difference** from the bot path: in `submit_ad`
   (submission.py:141–162), `auto_moderate` is called at line 169 **outside** `submit_ad`'s own
   `transaction.atomic()`. When the edit path calls `submit_ad`, `auto_moderate` will still be
   inside `edit.py`'s outer atomic (just outside `submit_ad`'s nested savepoint). This is a
   transaction-scope concern for the migration but **not** a currency-gate concern.
4. **The entire `if/elif/else` chain (163–251) is inside** the `with transaction.atomic()`
   at line 124 — confirmed by AST analysis (see `qlt-001-stage1-decision.md` notes, edit.py:124
   body ends at line 251).
5. **The reactivation branch re-renders** `ads/edit.html` with an error on moderation failure
   (lines 189–194), whereas the bot path always redirects with a message.

### Confidence: HIGH

Verified by direct reading of `edit.py:119–251`.

---

## 3. Does `submit_ad`'s coercion handle `CurrencyCode | str`? Is `ad.price_currency` available? (Question 3)

### `submit_ad` coercion logic (submission.py:75–88)

```python
# Currency coercion
currency: CurrencyCode | None = None
if input.price_currency is not None:
    try:
        currency = (
            input.price_currency
            if isinstance(input.price_currency, CurrencyCode)
            else CurrencyCode(str(input.price_currency))
        )
    except ValueError:
        logger.warning(
            "Invalid price_currency %r for ad %s", input.price_currency, input.ad_id
        )
ad.price_currency = currency.value if currency else None
```

**Handles `CurrencyCode | str`**: Yes. The `isinstance(input.price_currency, CurrencyCode)`
check at line 81 short-circuits when the input is already a `CurrencyCode` (the normal case from
both the bot handler and the edit path). The `else` branch attempts `CurrencyCode(str(...))`
coercion for raw strings, catching `ValueError`.

**`ad` is fetched at line 64**: Yes — `ad = Ad.objects.get(id=input.ad_id)`. So `ad.price_currency`
(the current DB value, a 3-char string like `"EUR"`) is loaded and available at the time the
coercion runs (line 88). This means `ad.price_currency` **could** serve as the "keep current"
fallback if a `keep` policy were implemented inside `submit_ad`.

### BUT — the Pydantic DTO changes everything

`SubmitAdInput.price_currency` is typed as `CurrencyCode | None` (submission.py:40) — **strict**,
not `str | CurrencyCode | None`. `SubmitAdInput` has **no `model_config`** (no
`arbitrary_types_allowed`, no validators). With Pydantic v2 (≥2.13.4, pyproject.toml:28):

| Input to `SubmitAdInput(price_currency=...)` | Pydantic v2 behavior |
|---|---|
| `CurrencyCode.EUR` | ✅ Accepted (enum instance) |
| `"EUR"` (valid str) | ✅ Coerced to `CurrencyCode.EUR` (str → StrEnum value lookup) |
| `"XYZ"` (invalid str) | ❌ `ValidationError` — **rejected before `submit_ad` runs** |
| `None` | ✅ Accepted (None allowed) |

**This means `submit_ad`'s `ValueError` recovery (invalid → `None`) is unreachable through the
DTO in both flows.** The bot handler always passes a valid `CurrencyCode` (from `PricePayload`
at message_payloads.py:50, set via `CurrencyCode(currency_value)` at ad_create.py:552). The edit
path, if it passes the pre-coerced `price_currency_value`, also passes a valid `CurrencyCode`.

The only way the `ValueError` branch could fire is if a caller bypasses Pydantic validation
(e.g., constructs a `SubmitAdInput` and mutates `input.price_currency` post-construction, or
calls `submit_ad` with an already-parsed string). In normal usage through the DTO, it is
defensive dead code — a harmless leftover from the original `update_ad_and_moderate` which
accepted bare parameters.

### Why this matters for the decision gate

For **Path 1 to work as the plan envisions** (pass raw invalid string to `submit_ad` with
`on_invalid="keep"`), the edit path would have to:
1. Pass `new_price_currency` (raw, possibly-invalid string) to `SubmitAdInput(price_currency=...)`.
2. Have `SubmitAdInput.price_currency` accept raw strings (type `str | CurrencyCode | None`).

But `price_currency` is typed `CurrencyCode | None`. Step 1 would cause Pydantic to **reject**
invalid strings with `ValidationError` before `submit_ad` ever runs. So Path 1's `on_invalid`
parameter **would never be reached** if the DTO type stays `CurrencyCode | None`.

To make Path 1 functional, the DTO type would need to be loosened to `str | CurrencyCode | None`,
which:
- Reduces type safety at the boundary (defeats part of rule #11).
- Requires `submit_ad`'s coercion to handle the `str` case (which it already does via the
  `else` branch).
- Still requires the edit path to **bypass** its own pre-coercion (lines 148–158) for the
  reactivation branch — which is impossible because that pre-coercion is shared and computed
  before the `if is_reactivation` branch.

### Confidence: HIGH

Verified by reading `submission.py:31–50` (DTO fields, no `model_config`), `submission.py:75–88`
(coercion), `ad_create.py:25, 813, 829` (bot passes `CurrencyCode`), `message_payloads.py:50`
(`PricePayload.price_currency: CurrencyCode`). Pydantic v2 enum coercion behavior is verified
against public documentation (Context7 / Pydantic docs).

---

## 4. Which path is cleaner and lower-risk? (Question 4)

### Path 1: Parameterize the coercer (`on_invalid="none" | "keep"`)

**What it requires:**
- Add `on_invalid_currency: Literal["none", "keep"] = "none"` to `SubmitAdInput`.
- Modify `submit_ad`'s coercion: when `ValueError` and `on_invalid=="keep"`, fall back to
  `CurrencyCode(ad.price_currency)`.
- The edit reactivation branch passes `on_invalid_currency="keep"`.

**Why it does NOT deliver value in the actual code:**

1. **The pre-coercion is shared (lines 148–158) and cannot be removed for just the
   reactivation branch.** It's computed before the `if is_reactivation:` branch and used by
   three other branches (text-edit, price-only, other-statuses) that are NOT being migrated.
   So `price_currency_value` is always a valid `CurrencyCode | None` by the time the
   reactivation branch runs.

2. **If the edit path passes the pre-coerced `price_currency_value` to `SubmitAdInput`**, then
   `submit_ad`'s `isinstance` check at line 81 returns True, `currency = input.price_currency`,
   and the `on_invalid` parameter is **dead code** — the `ValueError` branch never fires.

3. **If the edit path passes the raw `new_price_currency` string** (to make `on_invalid`
   meaningful), Pydantic rejects invalid strings at the DTO boundary (`ValidationError`) before
   `submit_ad`'s coercion runs. To circumvent this, the DTO type must be loosened to
   `str | CurrencyCode | None`, sacrificing type safety.

4. **The `on_invalid` parameter adds cognitive load** — future developers must reason about why
   it exists, what it does, and when it's used. Given finding #1 (it's dead code when the edit
   path pre-coerces), this is a net negative.

### Path 2: Document as intentional divergence

**What it requires:**
- The edit reactivation branch passes the pre-coerced `price_currency_value` (valid
  `CurrencyCode | None`) to `SubmitAdInput(price_currency=price_currency_value, ...)`.
- `submit_ad`'s coercion is a no-op (input is already a `CurrencyCode`).
- The "keep current on invalid" behavior is preserved by the pre-coercion in `ad_edit`
  (lines 148–158), which stays in `ad_edit` because it's shared with the non-migrated branches.
- Document the divergence in `submit_ad`'s docstring.

**Why it is cleaner and lower-risk:**

1. **Zero change to `SubmitAdInput` or `submit_ad`** — no new parameter, no new code path, no
   type-safety regression. The bot path (the active seller flow via FSM) is untouched.
2. **The pre-coercion naturally produces a valid `CurrencyCode | None`** — `submit_ad` accepts it
   via the `isinstance` check. No behavioral change.
3. **The `test_edit_reactivation_currency_keep_current` test** (Block 11/A3) still passes:
   the edit path's pre-coercion keeps the current currency, and `submit_ad` receives a valid
   `CurrencyCode` — no coercion to `None`.
4. **The divergence is genuinely intentional and architecturally justified**: `submit_ad`'s
   coercion is a defensive boundary check for raw-string inputs (inherited from
   `update_ad_and_moderate`); the edit path pre-coerces at the view layer because it must
   preserve the user's current currency when the form submits an invalid value — a web-specific
   UX decision that has no equivalent in the bot's button-based flow (which only offers valid
   `CurrencyCode` options via `process_price_currency`).

### Risk assessment

| Aspect | Path 1 | Path 2 |
|--------|--------|--------|
| Lines of code changed | ~4 (DTO field + coercion conditional) | 0 |
| Risk to bot flow (active) | Low (parameter has default) | **Zero** (no change) |
| Risk to edit flow (active) | Medium (DTO type change if raw string used) | **Zero** (pre-coercion unchanged) |
| Dead code introduced | `on_invalid` dead if pre-coerced input passed | None |
| Type safety impact | Reduces if DTO loosened to `str \| ...` | None |
| Test impact | `test_edit_reactivation_currency_keep_current` still passes | Same test passes |
| Cognitive load | New parameter, new branch in coercion | Documented in docstring |

### Confidence: HIGH

The structural analysis (shared pre-coercion, Pydantic DTO validation, bot always passes valid
`CurrencyCode`) is verified against `edit.py`, `submission.py`, `ad_create.py`, and
`message_payloads.py`.

---

## 5. StrEnum edge cases (Question 5)

`CurrencyCode` is a `StrEnum` (currencies/enums.py:11–25):

```python
class CurrencyCode(StrEnum):
    EUR = "EUR"
    RSD = "RSD"
    BAM = "BAM"

    @property
    def label(self) -> str:
        return self.value
```

### Relevant `StrEnum` behaviors

| Operation | Result | Impact on coercion |
|---|---|---|
| `str(CurrencyCode.EUR)` | `"EUR"` | The `else` branch `CurrencyCode(str(input.price_currency))` works even for enum inputs (round-trips back to the same enum). The `isinstance` check makes this a no-op optimization. |
| `CurrencyCode("EUR")` | `CurrencyCode.EUR` | The `ValueError`-catching path: invalid values raise `ValueError`, caught. |
| `CurrencyCode("XYZ")` | `ValueError` | `submit_ad`'s `except ValueError` catches this → coercion to `None`. |
| `CurrencyCode.EUR.value` | `"EUR"` | `submit_ad` stores `ad.price_currency = currency.value` (line 88) — correct for the `CharField(max_length=3)`. |
| `ad.price_currency` (DB value) | `"EUR"` (string) | For a hypothetical Path 1 "keep" fallback: `CurrencyCode(ad.price_currency)` would reconstruct the enum. The model's `choices` constraint (models.py:97) guarantees the DB value is always a valid code, so this never raises. |

### StrEnum does NOT affect the decision

Since `CurrencyCode` is a `str` subclass, `isinstance(input.price_currency, CurrencyCode)` (line 81)
correctly distinguishes enum instances from raw strings. The `str()` wrapper in the `else` branch
is harmless for both strings and StrEnum instances (since `str(StrEnum) == StrEnum.value ==`
the underlying string).

For Path 2, `ad.price_currency` (the model's CharField) is always a valid 3-char code due to the
model's `choices` constraint — `CurrencyCode(ad.price_currency)` always succeeds. There are **no
edge cases** with StrEnum that affect the recommendation.

### Confidence: HIGH

Verified by reading `currencies/enums.py:11–25` and `ads/models.py:95–101` (the `price_currency`
CharField with `choices` constraint). Pydantic v2 StrEnum coercion behavior verified against
Pydantic documentation.

---

## Recommendation

**Select Path 2: Document as intentional divergence.**

### Rationale (in priority order)

1. **The pre-coercion is shared and immutable for the reactivation branch.** Lines 148–158 of
   `ad_edit` compute `price_currency_value` (a valid `CurrencyCode | None`) once, and this value
   is used by all four branches. Only the reactivation branch migrates to `submit_ad` (per Block 12
   scope: "Leave the text-edit-hide branch and price-only-edit branch as-is"). The pre-coercion
   cannot be removed for just the reactivation branch. Therefore, `submit_ad` will always receive
   a valid `CurrencyCode | None` — making the "keep current on invalid" behavior already resolved
   by the pre-coercion, before `submit_ad` is even called.

2. **Path 1's `on_invalid` parameter would be dead code.** With the pre-coerced value passed to
   `SubmitAdInput`, `submit_ad`'s `isinstance(input.price_currency, CurrencyCode)` check (line 81)
   succeeds, and the `ValueError` branch never fires. Adding the parameter introduces code that
   cannot be exercised through the normal call path — a maintenance liability.

3. **Path 1 with raw-string input is blocked by the Pydantic DTO.** `SubmitAdInput.price_currency`
   is typed `CurrencyCode | None` (strict). Pydantic v2 rejects invalid strings (e.g., `"XYZ"`)
   with `ValidationError` at construction time — before `submit_ad`'s coercion logic runs. To make
   Path 1 functional, the DTO type would have to be loosened to `str | CurrencyCode | None`,
   sacrificing type safety (project rule #11 mandates Pydantic validation at boundaries). This
   trade-off is not justified.

4. **Path 2 introduces zero risk to the active bot flow.** The bot flow (ARCHIVED-ad-free, FSM →
   `submit_ad`) is the path with `on_invalid="none"` (invalid → None). Path 2 does not touch
   `submit_ad` or `SubmitAdInput` at all — the bot flow is completely unaffected. Path 1, by
   adding a parameter with a default, has low but non-zero risk (the coercion logic is modified).

5. **The divergence is genuinely intentional**, not accidental. The edit path's "keep current
   currency on invalid form input" is a deliberate web UX decision (a seller editing a price
   should not lose their currency selection if they submit a malformed value). The bot path only
   offers valid `CurrencyCode` options via inline keyboard buttons (`process_price_currency`,
   ad_create.py:528–566) — invalid currencies cannot occur in the bot flow. The "invalid → None"
   coercion in `submit_ad` is a defensive boundary check inherited from `update_ad_and_moderate`,
   now partially redundant due to the Pydantic DTO's own validation.

### Implementation for Block 12/A4 (Path 2)

1. **In `edit.py`'s reactivation branch:** Replace the inline `_apply_price_change` + `ad.save()`
   + `transition_to(ON_MODERATION)` + `auto_moderate(ad)` sequence with a call to
   `submit_ad(SubmitAdInput(...))`, passing:
   - `price_currency=price_currency_value` — the pre-coerced valid `CurrencyCode | None`
     (lines 148–158). This makes `submit_ad`'s coercion a no-op. "Keep current" is already
     resolved.
   - `photos=[]` — NOT `None`. `SubmitAdInput.photos` is typed `list[dict[str, Any]]`
     (required, non-optional). Passing `None` would raise `ValidationError`. Pass `[]` (empty
     list) — the thumbnail loop (submission.py:120) iterates `for photo in input.photos:` with
     zero iterations. *(This is a correction to the plan's Block 12 acceptance criteria which
     says "Pass `photos=None`" — that would fail Pydantic validation.)*
   - `original_language=None` — optional field, defaults to None. Correct for the edit context.
   - Other fields from the existing ad/POST data as appropriate.

2. **In `submit_ad`'s docstring:** Add a note documenting the intentional divergence:
   > "Currency coercion: this function defensively coerces `CurrencyCode | str` inputs,
   > falling back to None on ValueError (inherited from the bot handler's original
   > `update_ad_and_moderate`). The web edit view pre-validates currency at the view layer
   > (preserving the user's current currency on invalid form input) and passes a valid
   > `CurrencyCode | None` via `SubmitAdInput`, so the coercion is a no-op for the edit path.
   > Do not remove this defensive check without verifying the bot flow still guards against
   > raw-string currencies."

3. **No change to `SubmitAdInput` or `submit_ad`'s coercion logic.**

### Confidence in recommendation: HIGH

Based on:
- Direct reading of `edit.py:29–62` (`_apply_price_change` — no coercion), `edit.py:148–158`
  (pre-coercion, shared), `edit.py:163–194` (reactivation branch).
- Direct reading of `submission.py:31–50` (DTO fields, strict `CurrencyCode | None`),
  `submission.py:75–88` (coercion logic), `submission.py:141–169` (transaction + auto_moderate scope).
- Direct reading of `ad_create.py:25, 813, 829, 552, 539` (bot passes valid `CurrencyCode`).
- Pydantic v2 StrEnum validation behavior confirmed against Pydantic documentation.

---

## Appendix: Cross-referenced evidence table

| Claim | Source | Verified? |
|-------|--------|-----------|
| `submit_ad`'s coercion: invalid → `None` | `submission.py:76–88` | ✅ |
| `submit_ad` fetches `ad` at line 64 (so `ad.price_currency` available) | `submission.py:64` | ✅ |
| Edit path "keep current on invalid" logic | `edit.py:148–158` (NOT `_apply_price_change`) | ✅ |
| `_apply_price_change` does NOT coerce (receives pre-coerced `CurrencyCode \| None`) | `edit.py:29–62` | ✅ |
| Reactivation branch: `_apply_price_change` → save → transition → `auto_moderate` | `edit.py:163–194` | ✅ |
| `_apply_price_change` called BEFORE `auto_moderate` in reactivation | `edit.py:167` then `182` | ✅ |
| Reactivation branch inside `transaction.atomic()` | `edit.py:124` (with block), `163` (if branch) | ✅ |
| Currency pre-coercion shared by all 4 branches | `edit.py:148–158` → used at 167, 204, 221, 238 | ✅ |
| Bot always passes valid `CurrencyCode` (button-based FSM) | `ad_create.py:559, 539`; `message_payloads.py:50` | ✅ |
| `SubmitAdInput.price_currency` is `CurrencyCode \| None` (strict, no model_config) | `submission.py:40` | ✅ |
| Pydantic v2 rejects invalid enum strings before `submit_ad` runs | Pydantic v2 docs (Context7) | ✅ |
| A1 done, A2 done, A3 not done, A4 pending | `git log --oneline` + `glob test_edit.py` | ✅ |
| `update_ad_and_moderate` deleted | grep zero hits in `ad_create.py` | ✅ |
| `auto_moderate` does NOT modify price/currency fields | `auto_moderation.py:94–170` (validates only) | ✅ |
| Model's `price_currency` CharField has `choices` constraint | `ads/models.py:95–101` | ✅ |
| `ad_edit` reactivation branch does NOT use a Django Form | `edit.py:133–136` (direct `request.POST.get`) | ✅ |

---

## Open items for Block 12/A4 implementation

1. **A3 (`test_edit.py`) must exist before A4.** The `test_edit_reactivation_currency_keep_current`
   test pins the "keep current" behavior. It does not exist yet — must be created first.
2. **`photos` field:** Pass `[]`, not `None` (submit_ad.py:41, `list[dict[str, Any]]`).
3. **Transaction nesting:** `submit_ad`'s `transaction.atomic()` (submission.py:141) will nest
   inside `edit.py`'s atomic (edit.py:124) as a savepoint. The `select_for_update` lock (edit.py:125)
   is on the DB row, so `submit_ad`'s `Ad.objects.get(id=...)` (submission.py:64) reads the same
   locked row. Verify no deadlock.
4. **`ad.save()` vs `update_fields`:** `submit_ad` does a full `ad.save()` (submission.py:143);
   the current reactivation path uses `update_fields=[...]` (edit.py:168). The full save updates
   all fields — verify `updated_at` and other fields don't cause unintended side effects.
5. **Non-migrated branches:** The text-edit, price-only-edit, and other-statuses branches keep
   using `_apply_price_change` with the shared pre-coercion. They are NOT migrated (per scope).
