"""
Bot-tier account-state probe after operator deactivation (plan 18, ``B-3``).

The web tier's revocation is proven by plan 18 §1: ``is_active = False`` kills
an already-issued web session on the next request (``ModelBackend`` ->
``user_can_authenticate``), and refuses a fresh issuance (``B-05``). The **bot**
tier is not proven by that probe, because the bot holds no web session and
resolves identity per message.

This module is a **permanent probe, not a revocation implementation** — it
records what the bot actually does today. Enforcement of account state in the
bot for anything beyond the flags its middleware already reads is owned by
phase 15 ``15-AUTHZ-001``; do **not** add bot-revocation code here.

Lives under ``src/telegram_bot/tests/`` rather than the ``users`` test module
because the bot suite runs under ``pytest_asyncio`` (``asyncio_mode = "strict"``)
and its ``conftest.py`` redefines the DB fixtures; backend conftest fixtures
are not importable from this tree (see ``src/telegram_bot/tests/conftest.py``).

Outcome (recorded at implementation time, plan 18 ``B-3`` gate ``18-G3``):
**the bot did not block a deactivated user.** ``AccountStateMiddleware``
delegated to ``get_account_state``, whose five fields were
``is_banned`` / ``is_deleted`` / ``is_declined`` / ``ads_auto_publish`` /
``consent_revoked`` — **none of them is ``is_active``**. A deactivated user
passed the gate and reached every bot handler.

**Updated by plan 19 (2026-10-03).** Plan 19 ``B-1``/``B-2`` added
``is_active`` to the shared predicate and an ``is_active`` branch (with a
support carve-out) to the middleware, closing plan 18's deferred work ``D-2``.
The assertion below is therefore **inverted**: a deactivated user is now
refused by the default gate (``deactivation_carve_out`` defaults to False).
See ``test_bot_deactivation_matrix.py`` for the carve-out paths that remain
reachable.
"""

import pytest
from asgiref.sync import sync_to_async

from apps.users.models import User
from telegram_bot.middlewares import AccountStateMiddleware

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.integration,
    pytest.mark.concurrent,
]
pytestmark.append(pytest.mark.xdist_group("bot_concurrent"))

_CHAT_ID = 900000301


@pytest.mark.asyncio
async def test_bot_tier_account_state_after_deactivation() -> None:
    """Plan 18 ``D-2`` is closed: the bot NOW refuses a deactivated user.

    Drives a deactivated user through the real ``AccountStateMiddleware`` gate
    — the per-message bot handler gate — and records that it is **refused**
    outside the plan 19 support carve-out.

    Inverted by plan 19 (``B-1``/``B-2``) from plan 18 ``B-3``'s residual
    assertion. Plan 18 ``B-3`` created this test as permanent evidence of the
    gap (``assert can_interact is True``); plan 19 closes ``D-2``, so the
    assertion is inverted rather than deleted, preserving the audit trail
    (``R-4``). The default ``_check_user_state(chat_id)`` carries no
    ``deactivation_carve_out``, so this is the plain hard-block path; the
    support carve-out is covered by ``test_bot_deactivation_matrix.py``.
    """
    user, _ = await sync_to_async(User.objects.get_or_create)(
        chat_id=_CHAT_ID,
        defaults={
            "telegram_id": _CHAT_ID,
            "password": "x",
            "is_active": False,
        },
    )
    # Guarantee the row is genuinely deactivated without a second fixture.
    if user.is_active:
        await sync_to_async(User.objects.filter(pk=user.pk).update)(is_active=False)

    middleware = AccountStateMiddleware()
    can_interact, message = await middleware._check_user_state(_CHAT_ID)

    assert can_interact is False, (
        "the bot tier now consults is_active (plan 19 B-1/B-2) and refuses a "
        "deactivated user by default; if this fails, the is_active branch or "
        "the shared predicate regressed and plan 18's D-2 re-opened."
    )
    assert message != ""
