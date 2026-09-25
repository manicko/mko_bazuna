"""
Support contact read service for Mko Bazuna.

Provides cached access to active ``SupportContact`` rows for the Telegram bot
(support delivery) and web. Fails open to ``[]`` when the DB or cache is
unavailable (R-SN-05).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from apps.core.enums import SupportChannelType

if TYPE_CHECKING:
    from apps.core.models import SupportContact

logger = logging.getLogger(__name__)


def get_support_contacts() -> list[SupportContact]:
    """Return active SupportContact rows (cached, 1h TTL).

    Falls open to ``[]`` if the DB or cache is unavailable (R-SN-05).
    """
    from apps.core.models import SupportContact
    from apps.core.utils.cache import (
        get_cached_support_contacts,
        set_cached_support_contacts,
    )

    cached = get_cached_support_contacts()
    if cached is not None:
        return list(cached)
    try:
        objs = list(
            SupportContact.objects.filter(is_active=True)
            .order_by("ordering", "id")
        )
        set_cached_support_contacts(objs)
        return objs
    except Exception:
        logger.warning("SupportContact unavailable; returning empty list")
        return []


async def get_support_contacts_async() -> list[SupportContact]:
    """Async wrapper for bot handlers — runs get_support_contacts in a thread."""
    return await sync_to_async(get_support_contacts)()


def get_email_contacts() -> list[SupportContact]:
    """Return active EMAIL-channel support contacts (cached, 1h TTL).

    Filters the cached active contacts to ``SupportChannelType.EMAIL`` so the
    email delivery service can iterate recipients without an extra DB hit.
    """
    return [
        c
        for c in get_support_contacts()
        if c.channel_type == SupportChannelType.EMAIL
    ]


async def get_email_contacts_async() -> list[SupportContact]:
    """Async wrapper for bot handlers — runs get_email_contacts in a thread."""
    return await sync_to_async(get_email_contacts)()
