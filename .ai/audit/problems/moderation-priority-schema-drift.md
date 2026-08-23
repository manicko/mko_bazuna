---
id: moderation-priority-schema-drift
domain: audit
tags:
  - moderation
  - schema
  - discrepancy
related:
  - db-schema
  - technical-specification
  - phase-02-detailed-plan-3
---

# Discrepancy: AdModerationPriority field set (plan vs. implementation)

## Summary

`docs/97-plans/phase-02-detailed-plan-3.md` §2.2.1 describes an `AdModerationPriority` model
with a field set that **does not match** the implemented schema. The authoritative schema is
`docs/02-database/db-schema.md` (lines 532–546) and the service-level description is
`docs/01-spec/technical-specification.md` §Q — both agree with each other and with the source
code (`apps/moderation/models`, `apps/moderation/services/priority_calculator.py`).

## Planned (plan-3 §2.2.1)

| Field | Type |
|---|---|
| ad | FK(ads.Ad) UNIQUE |
| priority_score | INT |
| priority_reason | TEXT |
| flagged_by_system | BOOL |
| flagged_at | TIMESTAMP |
| reviewed_at | TIMESTAMP |

## Implemented (db-schema.md L532–546 + code)

| Field | Type |
|---|---|
| ad | ONE_TO_ONE(ads.Ad), `related_name="moderation_priority"` |
| base_score | POSITIVE SMALL INT (default 0) |
| priority_level | VARCHAR(10) choices=`AdPriorityLevel` (HIGH/MEDIUM/LOW) |
| flags | JSONB (default []) |
| confidence_score | FLOAT (default 0.0) |
| escalation_required | BOOL (default False) |

Implemented detail (source: `apps/moderation/services/priority_calculator.py` +
`priority.py`; tech-specification.md §Q):

- `PriorityCalculator.calculate_priority(ad)` computes `base_score` from **content risk**
  (banned words, +20 capped at 100) and **user history** (`>50` lifetime ads +15,
  `>3` recent rejections in 7d +25 `repeat_offender`). `total = max(content, user)`.
- Score→level: ≥80 HIGH, ≥50 MEDIUM, else LOW.
  `escalation_required = score>=80 or len(flags)>=3`.
- `PriorityService.calculate_and_save(ad)` persists the row; `get_queued_ads()`
  orders `ON_MODERATION`/`ON_MODERATION_FAILED` ads by `-base_score, -created_at`
  with `select_related` + prefetch.

## Field mapping / drift

| Planned field | Implemented equivalent | Notes |
|---|---|---|
| priority_score | base_score | consolidated |
| priority_reason | (folded into `flags`) | dropped as a column |
| flagged_by_system | `flags` (JSONB) | reason codes stored in flags |
| flagged_at | (not modeled) | dropped |
| reviewed_at | (not modeled) | dropped |
| priority_level | priority_level | present in impl, omitted from plan table |
| confidence_score | confidence_score | present in impl, omitted from plan |
| escalation_required | escalation_required | present in impl, omitted from plan |

## Related divergence: §2.2.2 priority factors vs. §2.4 pipeline

plan-3 §2.2.2 lists per-factor point awards (new seller +20, banned words +40, duplicate
title +15, image quality +10, trust-level −10..+10, category risk +5..+30). The implemented
`PriorityCalculator` uses a **simplified** two-component model (content risk + user history)
that does not include image-quality or category-risk factors as separate point sources.

plan-3 §2.4.2 further describes an **elaborate two-stage pipeline** — three trigger objects
(`SuspiciousKeywordTrigger`, `DuplicateDetectionTrigger`, `AnomalyDetectionTrigger`) feeding a
flow that routes **high-priority** ads to the moderation queue and **low-priority** ads to
**auto-publish**. The implemented moderation is a **single synchronous auto-moderation gate**
(`apps.moderation.services.auto_moderation.auto_moderate`/`check`): on submit it evaluates the
`ModerationCriteria` singleton (title/description length, price-required, image count, banned
words, `max_ads_per_user`, duplicate-title via `difflib`); fail → `ON_MODERATION_FAILED` +
`MODERATION_REJECTED` event; pass → `PUBLISHED` directly. `PriorityCalculator` runs in a
`post_save` signal for `status==ON_MODERATION` purely for **queue triage ordering** — it is
not a publish gate. The separate trigger objects and the auto-publish-by-priority branch are
not present in the code.

## Recommendation

1. Update plan-3 §2.2.1 field table to match `db-schema.md` (the single source of truth).
2. Note that the §2.2.2 factor list is a superset of the implemented two-component model.
3. Clarify §2.4.2: the auto-flagging/auto-publish pipeline described is not the implemented
   flow; the implemented auto-moderation gate is documented in `db-schema.md`
   (`moderation_criteria`) and `technical-specification.md` §A.
4. `db-schema.md` remains the single source of truth for the model.
