"""
Login handler for Telegram bot deep-link authentication.

Implements atomic token claim via indexed SHA-256 hash lookup.
"""

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
from django.db import IntegrityError, transaction

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
            "Welcome! To login, use a deep-link: /start login_<your_token>"
        )
        return

    deep_link = args[1]

    # Delegate contact deep-links to contact module
    from telegram_bot.handlers.contact import handle_contact_start

    if await handle_contact_start(message, bot, deep_link):
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
    """

    @sync_to_async
    def _handle() -> tuple[LoginToken | None, User | None, bool]:
        now = timezone.now()

        # Atomic UPDATE claim with RETURNING — single query, no TOCTOU
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            login_token = (
                LoginToken.objects.filter(
                    token_hash=token_hash,
                    telegram_id__isnull=True,
                    consumed_at__isnull=True,
                    expires_at__gt=now,
                )
                .update(telegram_id=telegram_id, returning=True)
                .first()
            )

        if login_token is None:
            return None, None, False

        # Get or create user
        try:
            with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
                user, created = User.objects.get_or_create(
                    telegram_id=telegram_id,
                    defaults={
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                    },
                )
        except IntegrityError:
            user = User.objects.get(telegram_id=telegram_id)
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
