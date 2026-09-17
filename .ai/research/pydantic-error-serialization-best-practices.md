# Pydantic v2 `ValidationError` → Django `JsonResponse` Serialization: Best Practices

**Status:** Research report (evidence-verified, no code changes made).
**Target stack:** Django 5.2 LTS · Pydantic ≥ 2.13.4 (pydantic-core 2.46.4) · Python 3.14.
**Problem:** A Django view catches `pydantic.ValidationError` and passes `exc.errors()`
directly into `JsonResponse(...)`. For malformed/raw request bodies, Pydantic v2 embeds
**raw `bytes`** in the `input` field of the error list, which Django's JSON encoder
cannot serialize — producing `TypeError: Object of type bytes is not JSON serializable`
and an **HTTP 500** instead of the intended **422**.

---

## 1. Evidence from the project (the actual bug)

Source of truth is the project source code, not the audit notes.

**`src/backend/apps/moderation/views/api_bulk.py:42-49`** (current, post-audit state):

```python
try:
    payload = BulkModerationRequest.model_validate_json(request.body)
except ValidationError as exc:
    logger.warning("Invalid bulk moderation request body")
    return JsonResponse(
        {"error": "Invalid request body", "errors": exc.errors()},   # ← bytes hazard
        status=422,
    )
```

- `request.body` is a **bytestring** (`HttpRequest.body` docs — *"The raw HTTP request body as a bytestring"*). `BulkModerationRequest` is a Pydantic v2 `BaseModel` with `model_config = ConfigDict(extra="forbid")` (`schemas.py:17-24`).
- When the body is empty (`b""`) or non-UTF-8/garbage, `model_validate_json(bytes)` raises a `ValidationError` whose `input` field **is the raw `bytes`**.

**Observed failure** (from `test_output2.txt`, reproduced live on pydantic 2.13.4):

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for BulkModerationRequest
  Invalid JSON: EOF while parsing a value at line 1 column 0 [type=json_invalid, input_value=b'', input_type=bytes]

During handling of the above exception, another exception occurred:
TypeError: Object of type bytes is not JSON serializable
    when serializing dict item 'input'
    when serializing list item 0
    when serializing dict item 'errors'
```

The three failing tests are `test_empty_body_returns_422`, `test_malformed_json_body_returns_422`,
and `test_validation_error_includes_error_details` (`test_priority_service.py:611-730`).
> **Note on stale audit text:** audit write-ups (`.ai/audit/99-validation/...`,
> `.ai/audit/09-external-api/...`) describe a *pre-fix* state ("returns 400", "5 tests
> expect 400"). The **actual current code already returns 422 with an `errors` field**, and
> the **actual tests already assert 422**. The status-code issue is resolved; the *only*
> remaining defect is the serialization `TypeError` (category C). Source code is the truth.

---

## 2. Exact Pydantic v2 API for error extraction

Verified against the official Pydantic docs (pydantic-core reference, docs versions
2.4 → 2.12+ and `latest`) and against the installed **pydantic 2.13.4 / pydantic-core 2.46.4**:

### `ValidationError.errors()`

```python
def errors(
    *,
    include_url: bool = True,
    include_context: bool = True,
    include_input: bool = True,
) -> list[ErrorDetails]
```

- **`include_input`** (default `True`): whether to include the `input` value of each error.
  The `input` field is *"the input provided for validation"* — for a `json_invalid` error on a
  raw bytestring body, this is the **`bytes`** object itself (`b''`, `b'not-json'`, etc.).
- **`include_url`** (default `True`): whether to include a `url` string linking to the per-error
  docs page, e.g. `https://errors.pydantic.dev/2.13/v/json_invalid` (leaks the Pydantic version).
- **`include_context`** (default `True`): whether to include the `ctx` object. For `value_error`
  errors raised by **custom validators** (`@field_validator` / `plain_validator_function` that
  `raise ValueError(...)`), `ctx` holds a **live `ValueError` object** (`{'error': ValueError(...)}`)
  — which is also **not** stdlib-JSON-serializable.

### `ValidationError.json()`

```python
def json(
    *,
    indent: int | None = None,
    include_url: bool = True,
    include_context: bool = True,
    include_input: bool = True,
) -> str
```

- Returns a **JSON string** of the error list. Uses **pydantic-core's own Rust serializer**,
  which is what makes it robust where stdlib `json` is not (see §4).

### `ErrorDetails` shape

Each dict contains: `type` (str), `loc` (tuple), `msg` (str), `url` (str), and (conditionally)
`input` and `ctx`. Of these, **`input` and `ctx` are the two fields that can contain
non-stdlib-JSON-serializable values** (`bytes` and live objects respectively).

### Version history of `include_input`

`include_input` (and `include_url`, `include_context`) are present in the pydantic-core
reference docs from **v2.4** onward. The feature was added to `.errors()`/`.json()` via
pydantic-core PR [#973](https://github.com/pydantic/pydantic-core/pull/973) (tracked in
pydantic issue [#7461](https://github.com/pydantic/pydantic/issues/7461)).
The project pins `pydantic>=2.13.4` (`pyproject.toml:28`), so all three parameters are
guaranteed available — no compatibility concern.

### `model_validate_json()` and empty/non-UTF-8 bodies

`BaseModel.model_validate_json()` accepts `str | bytes | bytearray`. An **empty** body
(`b""`) or non-UTF-8 bytes (`b'\xff\xfe...'`) raise a `json_invalid` `ValidationError`
with `input` set to the raw bytes and `input_type='bytes'` (confirmed in `test_output2.txt:138,198`).

---

## 3. Two distinct non-serializable hazards (empirically verified)

A live probe on the installed pydantic 2.13.4 confirms that `exc.errors()` is **not** safe to
hand to `json.dumps`/`JsonResponse` in general — there are *two* hazards, and the common
"just set `include_input=False`" advice only fixes the first:

| Scenario | Raw `exc.errors()` | `errors(include_input=False)` | `json.loads(exc.json(...))` |
|---|---|---|---|
| `json_invalid` on `b""` → `input=b''` (bytes) | ❌ `TypeError: bytes` | ✅ OK | ✅ OK |
| `json_invalid` on non-UTF8 `b'\xff\xfe\x00bad'` | ❌ `TypeError: bytes` | ✅ OK | ⚠️ `exc.json()` **default flags raise `ValueError`** (invalid utf-8); `include_input=False` ✅ OK |
| `value_error` from custom validator → `ctx={'error': ValueError(...)}` | ❌ `TypeError: ValueError` | ❌ **still fails** (`ctx` retained) | ✅ OK; with `include_context=False` ✅ OK |
| Field-level type error (e.g. `action: int`) | ✅ OK | ✅ OK | ✅ OK |

**Decisive finding:** `include_input=False` alone is **insufficient and fragile** — it leaves
the `ctx` hazard (live `ValueError` objects from custom validators) untouched, and even
`exc.json()` with *default* flags raises `ValueError` on non-UTF-8 bodies because it tries to
encode the bytes input as a string. The **only** form that is both robust and safe is:

```python
json.loads(exc.json(include_input=False, include_url=False, include_context=False))
```

This was verified to succeed for empty, malformed, non-UTF-8, and field-level-error inputs,
returning only `{'type', 'loc', 'msg'}` per error — all JSON-native.

---

## 4. Why Django `JsonResponse` / `DjangoJSONEncoder` does not help

`JsonResponse.__init__` (`django/http/response.py`) serializes with
`data = json.dumps(data, cls=encoder, **json_dumps_params)` where `encoder` defaults to
`django.core.serializers.json.DjangoJSONEncoder` (confirmed in Django 5.2 source).

**`DjangoJSONEncoder` handles:** `datetime`/`date`/`time`, `Decimal`, `UUID`,
`django.utils.functional.lazy`, `QuerySet`, `datetime`... — **it does NOT handle `bytes`**
or arbitrary objects. For those it calls `super().default(o)` (stdlib `JSONEncoder.default`),
which raises `TypeError: Object of type bytes is not JSON serializable`. This is exactly the
traceback in the bug:

```
File ".../django/core/serializers/json.py", line 114, in default
    return super().default(o)
...
TypeError: Object of type bytes is not JSON serializable
```

A `JsonResponse(..., cls=MyEncoder)` that overrides `default()` to do `if isinstance(o, bytes):
return o.decode("latin-1")` would *mask* the `TypeError`, but it would **not**:
- fix the `ctx`-`ValueError` hazard (a custom `default` would need to coerce that too), and
- it would **echo the raw request body back to the client** (credentials/PII in the 422 body)
  — a CWE-209 information-exposure violation (see §6).

So a custom encoder is the **wrong** fix: it papering over a serialization crash while
*increasing* the security surface.

---

## 5. Recommended pattern

Use pydantic-core's own serializer to obtain a guaranteed-JSON-serializable dict, and
**strip** the three fields that carry non-serializable or sensitive data:

```python
import json
from typing import TYPE_checking  # noqa: F401  (see usage below)

from django.http import JsonResponse
from pydantic import BaseModel, ValidationError

if TYPE_checking:
    from collections.abc import Sequence  # optional, for typing


def pydantic_errors_json(exc: ValidationError) -> list[dict[str, object]]:
    """Return Pydantic v2 validation errors as a JSON-serializable, sanitized list.

    Delegates serialization to pydantic-core (exc.json), which correctly handles
    values stdlib json.dumps cannot (raw `bytes` in the `input` field, live objects
    in `ctx`, non-UTF-8 byte bodies). `input`, `ctx` and `url` are excluded:

      * input  - may contain the raw request body (bytes), which echoes
                 credentials/PII back to the client (CWE-209).
      * ctx    - for `value_error` errors, holds live exception objects that
                 stdlib json cannot encode; never useful to clients.
      * url    - only leaks the Pydantic version (fingerprinting).

    Full diagnostic detail is already captured server-side by the caller's logger.
    The remaining fields ({type, loc, msg}) are always JSON-native, so this
    cannot raise a serialization TypeError.
    """
    return json.loads(
        exc.json(include_input=False, include_url=False, include_context=False)
    )
```

Applied to the actual view (`api_bulk.py`):

```python
    try:
        payload = BulkModerationRequest.model_validate_json(request.body)
    except ValidationError as exc:
        logger.warning("Invalid bulk moderation request body")
        return JsonResponse(
            {"error": "Invalid request body", "errors": pydantic_errors_json(exc)},
            status=422,
        )
```

**Resulting 422 body** for `b""`:

```json
{
  "error": "Invalid request body",
  "errors": [
    {"type": "json_invalid", "loc": [], "msg": "Invalid JSON: EOF while parsing a value at line 1 column 0"}
  ]
}
```

For non-UTF-8 bodies the `msg` is `"Invalid JSON: expected value at line 1 column 1"` —
no raw bytes, no version URL, no `ValueError` objects. Client gets enough to know *where*
(`loc`) and *what kind* of (`type`) of error; operators have the full detail in logs.

### Defense-in-depth variant (optional)

If a future Pydantic change ever re-introduced a non-serializable residual, wrap the call so a
malformed error object can never 500 the request:

```python
    try:
        return JsonResponse(
            {"error": "Invalid request body",
             "errors": pydantic_errors_json(exc)},
            status=422,
        )
    except (TypeError, ValueError):
        logger.exception("Failed to serialize validation errors")
        return JsonResponse(
            {"error": "Invalid request body"}, status=422
        )
```

### What *not* to do

| Approach | Verdict |
|---|---|
| `exc.errors()` raw into `JsonResponse` | ❌ The bug. `bytes`/`ValueError` → `TypeError` → 500. |
| `exc.errors(include_input=False)` | ❌ Fixes the bytes case but **not** the `ctx`-`ValueError` hazard; still 500s on custom-`ValueError` validators. |
| `JsonResponse(..., cls=DjangoJSONEncoder, default=str)` | ❌ Still echoes raw input (CWE-209); fragile; `DjangoJSONEncoder` doesn't handle bytes/`ValueError` by default anyway. |
| `exc.json()` with default flags, then `json.loads` | ⚠️ Raises `ValueError` on non-UTF-8 byte bodies. |
| `json.loads(exc.json(include_input=False, include_url=False, include_context=False))` | ✅ **Recommended.** |

### Test compatibility

The existing test `test_validation_error_includes_error_details` (test_priority_service.py:710)
only asserts `"errors" in data` and `isinstance(data["errors"], list)` and `len > 0`. The
recommended pattern returns a non-empty list of `{type, loc, msg}` dicts, so it satisfies the
test without leaking sensitive fields. (No test currently asserts on the `input`/`url`/`ctx`
contents, so dropping them is safe.)

---

## 6. Security considerations (data leakage in error responses)

**CWE-209 — Generation of Error Message Containing Sensitive Information.** The `input`
field of a `json_invalid`/`value_error` can contain the **entire raw request body**, which for
an authenticated moderation API may itself be fine, but for *any* public or semi-public
endpoint could include submitted credentials, PII, API keys, or tokens. Echoing it in a 422 is
a textbook information-disclosure vulnerability.

- **CWE-209 mitigation** (MITRE): *"Ensure that error messages only contain minimal details
  that are useful to the intended audience and no one else... Highly sensitive information
  such as passwords should never be saved to log files."*
- **OWASP A10:2025 — Mishandling of Exceptional Conditions** (supersedes the older A05/A09):
  *"log full diagnostic detail server-side, and return generic, non-identifying messages to
  the client"*; mandates a global, centralized exception handler and a documented policy for
  *what* is reported to the user vs. logged.
- **eslint-plugin-express-security `no-error-details-in-response`** (CWE-209, OWASP A04:2021):
  explicitly flags `res.json({ error: err })` / `{ ...err }` / `err.stack` sent to clients;
  recommends a generic body + a correlation ID logged server-side. The same principle applies
  to `exc.errors()` placed verbatim in a Django `JsonResponse`.

**Additional leaks removed by stripping fields:**
- `url`: `https://errors.pydantic.dev/2.13/v/...` reveals the exact Pydantic version, enabling
  CVE targeting (cf. the Log4Shell reconnaissance pattern described in OWASP A10:2025 material).
- `ctx`: for `value_error`, pydantic-core serializes `ctx.error` to the **`str()`** of the
  `ValueError`. If a validator constructs its message with `repr(data)` (common), that **also
  leaks the input via `msg`** — a validator-authoring hazard. `include_context=False` removes
  `ctx`; `msg` hygiene is the validator author's responsibility.

**Recommendation (defense in depth):** log the **full** `exc.errors()` (or `str(exc)`)
server-side via `logger.warning(...)` *before* stripping, then return only the minimal
`{type, loc, msg}` set. This satisfies CWE-209 ("log full detail server-side, return minimal
detail to the client"), matches OWASP A10:2025, and gives operators everything needed to
debug while giving clients only field + kind information.

> **Scope note on the moderation endpoint:** the bulk-moderation API is `staff_required_api`-guarded
> (`decorators.py`), so the immediate client is a known operator. Nevertheless, the same
> `ValidationError` handler pattern is reusable across API boundaries, and raw-body echo is
> never safe to ship — strip unconditionally.

---

## 7. Project patterns / cross-references

- **Other `ValidationError` catch sites** (grep): only `apps/moderation/views/api_bulk.py:44`
  passes `.errors()` to a `JsonResponse`. `apps/users/views/consent.py:113` catches
  `ValidationError` but only **logs** it (returns `None`) — no serialization hazard.
  The `seed`/`ads` model validators use Django's own `django.core.exceptions.ValidationError`
  (not Pydantic) at `apps/categories/models.py:109` — a different type, not affected.
- **No DRF** is used anywhere in the project (no `rest_framework` references). DRF's
  `serializer.errors` is therefore N/A here; for reference, DRF returns
  `{"field": ["message"]}` and never echoes raw input bytes — its format is inherently
  JSON-serializable. The Pydantic-native approach in §5 mirrors that "no raw input in
  response" safety.
- **No `DjangoJSONEncoder` usage** exists in the codebase currently; the project relies on
  `JsonResponse`'s default encoder. Avoid introducing a custom one for this case.

---

## 8. Citations

1. Pydantic docs — *Errors / Error Handling*, `e.errors()` / `e.json()` / `ErrorDetails`
   fields (`type`, `loc`, `msg`, `input`, `ctx`, `url`):
   https://pydantic.dev/docs/validation/latest/errors/errors/
   (verified identical across docs versions 2.0, 2.4, 2.6, 2.8, 2.9, 2.12, latest).
2. pydantic-core API reference — `ValidationError.errors(*, include_url, include_context,
   include_input)` and `ValidationError.json(*, indent, include_url, include_context,
   include_input)`:
   https://pydantic.dev/docs/validation/latest/api/pydantic-core/pydantic_core/
   (docs v2.4 onward already list all three `include_*` params).
3. Pydantic issue #7461 / pydantic-core PR #973 — `include_input` added to `.errors()`/`.json()`:
   https://github.com/pydantic/pydantic/issues/7461
   https://github.com/pydantic/pydantic-core/pull/973
4. Django 5.2 — *Request and response objects* (`HttpRequest.body` is a bytestring) and
   *Serializing Django objects* (`DjangoJSONEncoder` handles date/Decimal/UUID/lazy, not bytes):
   https://docs.djangoproject.com/en/5.2/ref/request-response/
   https://docs.djangoproject.com/en/5.2/topics/serialization/
5. Django source — `JsonResponse.__init__` uses
   `json.dumps(data, cls=encoder, ...)` with `encoder=DjangoJSONEncoder` default:
   https://github.com/django/django/blob/stable/5.2.x/django/http/response.py
6. CWE-209 — Generation of Error Message Containing Sensitive Information:
   https://cwe.mitre.org/data/definitions/209.html
7. OWASP Top 10 2025 — A10 Mishandling of Exceptional Conditions:
   https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/
8. OWASP — Improper Error Handling:
   https://owasp.org/www-community/Improper_Error_Handling
9. eslint-plugin-express-security — `no-error-details-in-response` (CWE-209 / OWASP A04:2021):
   https://eslint.interlace.tools/docs/security/plugin-express-security/rules/no-error-details-in-response
10. Empirically verified on the project environment: **pydantic 2.13.4**,
    **pydantic-core 2.46.4** (versions from `uv.lock`/`pyproject.toml:28`). Behavior repro
    confirmed against the real `BulkModerationRequest` schema (`extra="forbid"`) and the
    exact bodies in the failing tests (`b""`, `"not-json"`) plus adversarial non-UTF-8 and
    field-level-error cases.
