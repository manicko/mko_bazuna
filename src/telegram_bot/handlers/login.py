"""
Login handler for Telegram bot deep-link authentication.

Implements atomic token claim via indexed SHA-256 hash lookup.
"""

import datetime
import hashlib
import logging
import re

from aiogram import Bot, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.users.models import User, LoginToken
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AnalyticsEventType
from apps.core.services.site_config import get_site_name_async
from django.db import IntegrityError, connection, transaction

logger = logging.getLogger(__name__)

# Deep-link pattern: login_<32-char-token>
LOGIN_PATTERN = re.compile(r"^login_([A-Za-z0-9_-]{32})$")

router = Router()


@router.message(Command("start"))
async def handle_login_deep_link(
    message: types.Message, bot: Bot, state: FSMContext
) -> None:
    """
    Handle /start with login deep-link.

    Pattern: /start login_<token>
    Token is SHA-256 hashed and claimed atomically via UPDATE.
    Delegates contact deep-links to contact module.
    """
    if not message.text or not message.from_user:
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            f"Welcome to {await get_site_name_async()}! To login, use a deep-link: /start login_<your_token>"
        )
        return

    deep_link = args[1]

    # Delegate contact deep-links to contact module
    from telegram_bot.handlers.contact import handle_contact_start

    if await handle_contact_start(message, bot, deep_link):
        return

    # Delegate saved-search unsubscribe deep-links to alerts module (AL-002)
    from telegram_bot.handlers.alerts import handle_unsubscribe_start

    if await handle_unsubscribe_start(message, bot, deep_link):
        return

    # Handle login pattern
    match = LOGIN_PATTERN.match(deep_link)
    if not match:
        await message.answer(
            "Invalid login link format. Expected: /start login_<token>"
        )
        return

    raw_token = match.group(1)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    # Combined ORM: claim token + get or create user
    login_token, user, created = await handle_login_orm(
        token_hash=token_hash,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    if not login_token:
        await message.answer("This login link is invalid, expired, or already used.")
        return

    # user is guaranteed non-None when login_token is claimed
    assert user is not None
    await state.update_data(user_id=user.id)

    if created:
        await message.answer(
            "Login successful! Your account has been created. "
            "You can now create ads with /post."
        )
    else:
        await message.answer("Login successful! You can now create ads with /post.")


def _claim_login_token(
    token_hash: str, telegram_id: int, now: datetime.datetime
) -> LoginToken | None:
    """Atomically claim a login token by setting its ``telegram_id``.

    Uses PostgreSQL ``UPDATE ... RETURNING`` for a single-statement,
    zero-TOCTOU claim. The ``WHERE`` clause guarantees only an unclaimed
    (``telegram_id IS NULL``), not-yet-consumed (``consumed_at IS NULL``),
    and unexpired (``expires_at > now``) token is touched. Postgres holds a
    row-level lock for the duration of the ``UPDATE``, so a concurrent claim
    from another bot worker matches zero rows and returns ``None``.

    Returns the claimed ``LoginToken`` instance (with ``telegram_id`` set and
    ``consumed_at`` still ``NULL``), or ``None`` when no token matched.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE login_tokens
               SET telegram_id = %s
             WHERE token_hash = %s
               AND telegram_id IS NULL
               AND consumed_at IS NULL
               AND expires_at > %s
            RETURNING id, token_hash, telegram_id, created_at, expires_at, consumed_at
            """,
            [telegram_id, token_hash, now],
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]

    return LoginToken(**dict(zip(columns, row, strict=True)))


async def handle_login_orm(
    token_hash: str,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> tuple[LoginToken | None, User | None, bool]:
    """
    Atomically claim a login token, then get or create the user.

    Combines the claim and user operations in a single sync_to_async call
    to reduce DB connection churn with CONN_MAX_AGE=0.
    The claim uses UPDATE ... RETURNING to avoid a TOCTOU race between
    the UPDATE and a subsequent SELECT.

    User lookup uses stable chat_id (never nullified) instead of telegram_id
    so that withdrawn/deleted users are still found by the middleware.
    """

    @sync_to_async
    def _handle() -> tuple[LoginToken | None, User | None, bool]:
        now = timezone.now()

        # Atomic UPDATE ... RETURNING claim — single query, zero TOCTOU.
        # token_hash is unique-indexed; the UPDATE row lock guarantees only
        # one concurrent claimer wins. See docs/02-database/db-schema.md:84-85.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            login_token = _claim_login_token(token_hash, telegram_id, now)

        if login_token is None:
            return None, None, False

        # Get or create user by stable chat_id (never nullified on withdraw)
        try:
            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
                user, created = User.objects.get_or_create(
                    chat_id=telegram_id,
                    defaults={
                        "telegram_id": telegram_id,
                        "chat_id": telegram_id,
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                    },
                )
        except IntegrityError:
            user = User.objects.get(chat_id=telegram_id)
            created = False
        else:
            if created:
                AnalyticsEvent.objects.create(
                    event_type=AnalyticsEventType.REGISTRATION_CREATED,
                    user_id=user.id,
                )
                logger.info(f"Registration event recorded for user {user.id}")
        return login_token, user, created

    return await _handle()
