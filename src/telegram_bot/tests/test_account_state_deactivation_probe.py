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
**the bot does not block a deactivated user.** ``AccountStateMiddleware``
delegates to ``get_account_state``, whose five fields are
``is_banned`` / ``is_deleted`` / ``is_declined`` / ``ads_auto_publish`` /
``consent_revoked`` — **none of them is ``is_active``**. A deactivated user
passes the gate and reaches every bot handler. The asserted residual below
carries the owner name.
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
    """KNOWN GAP (owner: ``15-AUTHZ-001``): the bot does NOT revoke ``is_active``.

    Drives a deactivated user through the real ``AccountStateMiddleware`` gate
    — the per-message bot handler gate — and records that it **passes**.

    This asserts the residual deliberately. Phase 15 ``15-AUTHZ-001`` owns the
    bot-tier account-state gate (deferred-work ``D-2``); when that lands, this
    test must be inverted to a positive assertion that a deactivated user is
    refused. Until then a green run here means "still unenforced", so the
    ``assert can_interact is True`` line is load-bearing evidence of the gap,
    not a desired behaviour.
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

    assert can_interact is True, (
        "is_active is not consulted by the bot gate; if this fails, the bot "
        "tier now blocks a deactivated user and 15-AUTHZ-001's residual is "
        "closed — invert this test and revise B-2's operator message."
    )
    assert message == ""
