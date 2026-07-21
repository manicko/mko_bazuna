"""
Bot permission middleware for Mko Bazuna.

Checks account state flags (is_banned, is_deleted, ads_auto_publish) on every message.
Prevents banned/deleted users from any interaction and restricts publishing for
users with ads_auto_publish=False.
"""

import logging
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, Message
from asgiref.sync import sync_to_async

from apps.users.models import User

logger = logging.getLogger(__name__)


class AccountStateMiddleware(BaseMiddleware):
    """
    Middleware that checks account state on every Telegram message.

    Enforces three independent account flags:
    - is_banned: Admin action, blocks all bot interactions
    - is_deleted: GDPR withdrawal, blocks all bot interactions (telegram_id nulled)
    - is_declined: User declined consent, blocks all bot interactions (browse-only)
    - ads_auto_publish=False: Restricts /post command only
    - consent_revoked_at: Blocks all bot interactions for withdrawn users

    For banned/deleted/declined/withdrawn users: responds with rejection message and skips handler.
    For publish-restricted users: allows other commands but blocks /post.
    """
