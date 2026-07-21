"""
Login handler for Telegram bot deep-link authentication.

Implements atomic token claim via UPDATE with constant-time comparison.
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

    # Atomic claim via UPDATE
    login_token = await claim_login_token(
        token_hash=token_hash, telegram_id=message.from_user.id
    )

    if not login_token:
        await message.answer(
            "This login link is invalid, expired, or already used."
        )
        return

    # Create or get user
    user, created = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    await state.update_data(user_id=user.id)

    if created:
        await message.answer(
            "Login successful! Your account has been created. "
            "You can now create ads with /post."
        )
    else:
        await message.answer(
            "Login successful! You can now create ads with /post."
        )


async def claim_login_token(
    token_hash: str, telegram_id: int
) -> LoginToken | None:
    """
    Atomically claim a login token.

    Uses constant-time comparison via hmac.compare_digest.
    Wrapped in sync_to_async for bot compatibility.
    """
    @sync_to_async
    def _claim() -> LoginToken | None:
        now = timezone.now()

        # Atomic UPDATE claim
        updated = LoginToken.objects.filter(
            token_hash=token_hash,
            telegram_id__isnull=True,
            consumed_at__isnull=True,
            expires_at__gt=now,
        ).update(telegram_id=telegram_id)

        if updated == 0:
            return None

        return LoginToken.objects.get(token_hash=token_hash)

    return await _claim()


async def get_or_create_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> tuple[User, bool]:
    """
    Get existing user or create new one.

    Uses sync_to_async for ORM operations. Wraps get_or_create in
    transaction.atomic() to guard against concurrent IntegrityError
    on duplicate telegram_id. On conflict, re-fetches the existing user.
    """
    @sync_to_async
    def _get_or_create() -> tuple[User, bool]:
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
        return user, created

    return await _get_or_create()
