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
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from asgiref.sync import sync_to_async
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.enums import AnalyticsEventType
from apps.core.services.analytics import record_event
from apps.core.services.site_config import get_site_name_async
from apps.users.models import LoginToken, User
from telegram_bot.handlers.contact import CONTACT_US_CALLBACK
from telegram_bot.services.rate_limit import check_login_rate_limit

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
        site_name = await get_site_name_async()
        await message.answer(
            _(
                "Welcome to %(site)s! To login, use a deep-link: "
                "/start login_<your_token>"
            )
            % {"site": site_name},
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                InlineKeyboardButton(
                    text=_("Contact us"), callback_data=CONTACT_US_CALLBACK
                ),
                    ],
                ],
            ),
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
            _("Invalid login link format. Expected: /start login_<token>")
        )
        return

    # Rate-limit login deep-link claims to prevent DB UPDATE flooding (EXT-007).
    if not await check_login_rate_limit(message.from_user.id):
        logger.warning(
            "Login rate limit exceeded for telegram_id=%s",
            message.from_user.id,
        )
        await message.answer(
            _("Too many login attempts. Please wait a minute and try again.")
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
        await message.answer(_("This login link is invalid, expired, or already used."))
        return

    # user is guaranteed non-None when login_token is claimed
    assert user is not None
    await state.update_data(user_id=user.id)

    if created:
        await message.answer(
            _(
                "Login successful! Your account has been created. "
                "You can now create ads with /post."
            )
        )
    else:
        await message.answer(_("Login successful! You can now create ads with /post."))


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

        # Single transaction: claim token + create/retrieve user.
        # If get_or_create raises a non-IntegrityError, the entire block
        # rolls back, returning the token to an unclaimed state.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            login_token = _claim_login_token(token_hash, telegram_id, now)

            if login_token is None:
                return None, None, False

            # Get or create user by stable chat_id (never nullified on withdraw).
            # The inner atomic() is a SAVEPOINT: it lets us catch IntegrityError
            # (concurrent INSERT race on chat_id) and fall back to a plain get(),
            # while keeping the token claim + user creation in the outer transaction.
            try:
                with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
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
                    record_event(
                        AnalyticsEventType.REGISTRATION_CREATED,
                        user_id=user.id,
                    )
                    logger.info("Registration event recorded for user %s", user.id)
            return login_token, user, created

    return await _handle()

