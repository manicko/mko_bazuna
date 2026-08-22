---
id: alert-delivery-research
domain: agent
tags:
  - research
  - alerts
  - signals
  - near-real-time
related:
  - architecture
---

# Research: Near-Real-Time Saved-Search Alert Delivery on Ad Publish

RESEARCH-ONLY report — no code changed. Consensus: deliver saved-search alerts
at the moment an ad transitions to `PUBLISHED` (Decision_017, Q5 = B), replacing
the daily-digest cadence as the primary path while retaining the daily command
as a catch-all/backfill.

## Implementation Status

**Outcome: Implemented (Approach 1).** Near-real-time publish-time alert delivery is
implemented:

- `apps/moderation/signals.py:55` `deliver_immediate_alerts_on_publish` — a
  `post_save` receiver on `Ad`, registered via `apps/moderation/apps.py` `ready()`.
- Fires when `instance.status == AdStatus.PUBLISHED`; defers delivery via
  `transaction.on_commit(...)` so `SavedSearchNotification` rows exist first.
- `apps/search/services/immediate_alerts.py:42` `deliver_immediate_alerts(ad_id)`:
  fetches the ad, runs `find_matching_saved_searches(ad)`
  (`alert_query.py:132`, ad-centric matcher), records notifications
  idempotently (`ignore_conflicts=True` under `uq_saved_search_ad`), then spawns a
  daemon `threading.Thread` running `asyncio.run(_send_payloads(...))`.
- Concurrency capped with `asyncio.Semaphore(_SEND_CONCURRENCY=10)`;
  `TelegramBadRequest`/`TelegramForbiddenError` caught per send.
- Gated by `settings.IMMEDIATE_ALERTS_ENABLED` (env-driven, default `false`)
  (`config/settings/base.py:227`). Daily `send_alerts` (`send_alerts.py`) retained
  as the catch-all/backfill (advisory lock ID 9; see `architecture-structure.md`).

> **Deviation:** the signal fires on *any* save where `status == PUBLISHED`
> (including a PUBLISHED->PUBLISHED re-save), not strictly a state transition.
> Double delivery is prevented by the `SavedSearchNotification` idempotency
> (`uq_saved_search_ad`). See
> `.ai/audit/problems/17_doc-update-discrepancies-plan14-16.md` #5.

## Verified Facts

1. **Single publish funnel.** All three publish paths (bot auto-publish via
   `auto_moderate` → `_pass_moderation` → `set_published`; web admin
   `approve_ad` → `set_published`; seller reactivation → `auto_moderate`) converge
   on `Ad.transition_to(AdStatus.PUBLISHED)` which ends with
   `self.status = target; self.save(update_fields=update_fields)`
   (`apps/ads/models.py:432-433`). `Ad` has no `save()` override.
2. **Signal precedent.** `apps/moderation/signals.py:32` already registers
   `@receiver(post_save, sender=Ad)` (`calculate_ad_priority`), wired in
   `apps/moderation/apps.py` `ready()`. The project's established idiom for
   model-change side-effects is `post_save` registered in `apps.<app>/apps.py`.
3. **No task broker**, no Redis pub/sub beyond cache, no Celery/RQ. Two processes
   (`web` gunicorn sync ×3 + `bot` aiogram polling) share one Postgres + Redis.
4. **Idempotent dedup.** `SavedSearchNotification` `UniqueConstraint(saved_search, ad)`
   + `record_notifications(..., ignore_conflicts=True)` (`alert_query.py:99`,
   `models.py:138-141`) means delivery (and re-delivery) is safe. `find_matching_ads`
   excludes already-notified ads via `NOT EXISTS` (`alert_query.py:90-94`).
5. **Daily command** `send_alerts` runs daily 08:00 UTC
   (`docker/entrypoint-scheduler.sh:40`) under advisory lock, persists
   notifications + analytics in a transaction, then sends Telegram outside it
   via `asyncio.run(Bot(token=settings.BOT_TOKEN))` (`send_alerts.py:57-58,140`).
6. **`transaction.on_commit` is unused today** (grep) — new but standard Django
   5.2 primitive.

## Recommended Approach (of 3 evaluated)

**Approach 1 — recommended:** add a `post_save` receiver on `Ad` (sibling to
`calculate_ad_priority`) that fires only when `instance.status == PUBLISHED`,
defers via `transaction.on_commit(...)` (so `SavedSearchNotification` rows exist
before any other process can observe the ad), then runs a new **ad-centric**
matcher ("which active saved searches match ad X?") in a background thread +
`asyncio.run(Bot.send_message(...))`.

- True near-real-time (fires at publish commit), no new container/event-loop/broker.
- Reuses existing `post_save` + `apps.py ready()` pattern and the `asyncio.run(Bot)`
  send primitive.
- `on_commit` correctness + `ignore_conflicts` idempotency = daily command can
  never double-send to already-delivered pairs, and a failed immediate send is
  picked up by the daily backfill (dedup gate ≠ empty).
- New ad-centric matcher required (inverse of `find_matching_ads`): iterate
  `SavedSearch.objects.filter(is_active=True)` with `select_related`, test each
  against the single ad (city equality, category subtree via
  `Category.get_descendants`, price range, per-language FTS via
  `LanguageLocale.fts_vector_field`). Feasibility HIGH.

**Approach 2 (sub-minute polling loop)** — rejected as primary: lag-bound, adds
continuous DB/Telegram load; acceptable only as fallback.

**Approach 3 (in-process asyncio task off the publish path)** — rejected: races
unless `on_commit` is used anyway; needs a cross-process coroutine runner.

## Risks & Mitigations

- **Blocking the request thread:** wrap the send in a daemon
  `threading.Thread(...).start()` around `asyncio.run(...)`.
- **Rate limits / fan-out:** cap concurrent sends (`asyncio.Semaphore(10)`),
  rely on existing 10-per-search cap; monitor via a new
  `SEARCH_ALERT_DELIVERED_IMMEDIATE` event.
- **Signal fires in both processes:** desirable (each publishes its own); dedup
  makes cross-process overlap safe.
- **Perf of ad-centric scan:** gate behind `settings.IMMEDIATE_ALERTS_ENABLED`;
  index `IX_saved_searches_user_active` already exists.

## Reconciliation with daily command

Keep `send_alerts` (daily) unchanged as the **catch-all/backfill**: already-notified
ads are skipped by its `NOT EXISTS`; failed immediate sends are picked up later.
On-publish = speed; daily = durability.
