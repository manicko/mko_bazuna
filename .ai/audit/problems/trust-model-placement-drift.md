---
id: trust-model-placement-drift
domain: audit
tags:
  - trust
  - users
  - schema
  - discrepancy
related:
  - db-schema
  - technical-specification
  - phase-02-detailed-plan-3
  - trust-signals-plan
---

# Discrepancy: telegram_premium placement + SellerTrustScore fields (plan vs. implementation)

## Summary

Two planning documents place `telegram_premium` on the `SellerVerification` model and claim it
is absent from `User`. The implemented schema and source code place `telegram_premium` directly
on the `users` table. `docs/02-database/db-schema.md` (line 62) and
`docs/01-spec/technical-specification.md` §M both agree with the code.

A related divergence: the planned `SellerTrustScore` field set (plan-3 §1.2.1; trust-signals-plan §T3)
includes `avg_ad_quality_score` and a `calculation_version`/`updated_at` timestamp that do not
match the implemented schema (`score`, `rejection_rate`, `last_calculated`).

## telegram_premium placement

### Planning docs that contradict the implementation

**A. phase-02-detailed-plan-3.md §1.3.1** — `SellerVerification` model table row:

```
| telegram_premium | BOOL | Telegram Premium flag (trust signal) |
```

Explicit Note (plan-3 §1.3.1):

> The `telegram_premium` field is defined in the `SellerVerification` model, NOT in the
> `User` model. The current `User` model does not contain a `telegram_premium` field.

**B. trust-signals-plan.md §T4** — `SellerVerification` model code block:

```python
class SellerVerification(models.Model):
    user = models.OneToOneField("users.User", on_delete=models.CASCADE, related_name="verification")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    telegram_premium = models.BooleanField(default=False)   # ← present in plan, absent in code
    verified_by_admin = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)
```

### Implemented (source of truth)

`docs/02-database/db-schema.md` L62 — the `users` table **does** carry the column:

```
telegram_premium (BOOL, default False)    # Telegram Premium subscription status
```

`docs/02-database/db-schema.md` L517–528 — the `seller_verifications` table (`SellerVerification`)
contains **only**: `id`, `user_id` (ONE_TO_ONE), `phone_number`, `verified_by_admin`, `verified_at`
— **no** `telegram_premium` column.

`technical-specification.md` §M:

> SellerVerification (...): two verification paths — admin verification (manual, US-A11) and
> Telegram Premium auto-verification (`telegram_premium` field on `User`).

Source code (verified against `apps/users/models.py` + `apps/trust/models.py`):

- `User` model carries `telegram_premium` among its account-state flags.
- `SellerVerification` does **not** define `telegram_premium`.

### Internal inconsistency within plan-3

plan-3 §1.3.1 claims `telegram_premium` is on `SellerVerification`. But `trust-signals-plan.md`
§T2 ("Add `telegram_premium` field to `apps/users/models.py`") and the trust-level badge logic
(§1.4, §2 Current State) are consistent with the field living on `User`. Only the §1.3.1
`SellerVerification` table row + Note and the §T4 code block are wrong.

## SellerTrustScore field divergence

### Planned (plan-3 §1.2.1 + trust-signals-plan §T3)

| Field | Source |
|---|---|
| user | both |
| trust_level | both |
| ad_count_lifetime | both |
| ad_count_active | both |
| contact_response_rate | both |
| avg_ad_quality_score | both |
| last_calculated_at / updated_at | both |
| calculation_version | plan-3 §1.2.1 (trust-signals-plan §T3 omits) |
| score | neither planned |
| rejection_rate | neither planned |
| last_calculated | neither planned |

### Implemented (db-schema.md L501–510 + code)

`SellerTrustScore` (`apps/trust/models.py`, db_table `seller_trust_scores`):

```
user_id (ONE_TO_ONE users) | trust_level (choices=TrustLevel) | score (POSITIVE SMALL INT, default 0)
ad_count_lifetime | ad_count_active | rejection_rate (DECIMAL 5,2) | contact_response_rate (DECIMAL 5,2)
last_calculated (auto_now)
```

The plan's `avg_ad_quality_score` maps loosely to the implemented aggregate `score`;
`calculation_version` and `updated_at` are not present in the code.

## Recommendation

1. Remove the `telegram_premium` row from plan-3 §1.3.1 `SellerVerification` table.
2. Correct plan-3 §1.3.1 Note: `telegram_premium` is on `User` (db-schema.md L62), consumed by
   the trust system as an auto-verification signal — not a `SellerVerification` column.
3. Update plan-3 §1.3.2 integration point ("Store telegram_premium flag in SellerVerification")
   to reflect recording on `User`.
4. Align trust-signals-plan §T3 `SellerTrustScore` code with db-schema.md (add `score` +
   `rejection_rate`, `last_calculated`; remove `avg_ad_quality_score`/`updated_at`/
   `calculation_version`).
5. Remove `telegram_premium` from trust-signals-plan §T4 `SellerVerification` code block
   (it is correctly on `User` per §T2).
6. `db-schema.md` remains the single source of truth.
