# Bug Report 01 — `bulk_ban` filters `telegram_id__in` with user PK values

**Date:** 2026-07-20  
**Severity:** High (silent no-op / wrong-target ban)  
**Component:** `src/backend/apps/moderation/admin_actions.py`  
**Status:** Reported — NOT fixed (out of scope of task_003 research)

---

## Summary

`bulk_ban()` collects seller primary keys and then filters the `User` table on the
**`telegram_id`** column using those PK values. `telegram_id` (Telegram user id,
`BigIntegerField`, huge random-looking integers) and the `User.id` autoincrement
primary key are completely disjoint namespaces. The filter therefore matches
essentially no real users, so the bulk ban is a silent no-op.

## Evidence

```python
# moderation/admin_actions.py  (inside bulk_ban)
user_ids = set(queryset.values_list("user_id", flat=True))   # ← User.id PKs
...
User.objects.filter(telegram_id__in=user_ids).update(is_banned=True)  # ← WRONG column
```

- `user_ids` are `Ad.user_id` values (FK → `User.id`, small sequential ints).
- The queryset filters `User.telegram_id IN (<user pks>)` — a mismatch.

## Impact

- Moderators believe they banned a set of sellers; in reality no rows are updated
  (or, by astronomically unlikely coincidence, the wrong users whose
  `telegram_id` happens to equal a PK).
- Enforcement of bans via the bot middleware / publish gate is bypassed for the
  intended targets.

## Recommended Fix (for a separate task)

Filter on the primary key, not `telegram_id`:

```python
User.objects.filter(id__in=user_ids).update(is_banned=True)
```

The `user_ids` set is already built from `user_id` PKs, so `id__in` is correct.

## Why not fixed here

This report was found while researching PII-001 (task_003_research_pii_chat_id).
It is unrelated to the chat_id / bot-identity rewrite and must not be patched as
part of that work. Filed separately per project rules.
