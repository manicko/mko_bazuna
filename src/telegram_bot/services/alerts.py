"""
Saved-search alert data access for the Telegram bot (10-CQ-002).

Hosts the saved-search reads/mutations that previously lived in
``telegram_bot.handlers.alerts``: listing a user's saved searches and the
token-owned enable/disable toggles used by the inline callbacks and the
``/start unsub_<token>`` deep link. The query and locking shape is
byte-preserved from the handler relocation. The bot-side lock-timeout policy
is explicitly out of scope for this relocation; it is routed to phase 03's
``SET LOCAL lock_timeout`` work.
"""

import logging

from asgiref.sync import sync_to_async
from django.db import OperationalError, transaction

from apps.core.utils.db_lock_timeout import is_lock_timeout
from apps.search.models import SavedSearch

logger = logging.getLogger(__name__)


@sync_to_async
def get_user_saved_searches(user_id: int) -> list[SavedSearch]:
    """Get all saved searches for a user, ordered by creation date."""
    return list(
        SavedSearch.objects.filter(user_id=user_id)
        .select_related("city", "category")
        .order_by("-created_at")
    )


@sync_to_async
def resolve_unsubscribe(token: str, chat_id: int | None) -> SavedSearch | None:
    """Disable the search owned by ``chat_id`` for ``token``.

    Returns the (now-inactive) SavedSearch when the caller owns it, else None
    (unknown token or not the owner — no state is leaked).
    """
    return _resolve_owned(token, chat_id, active=False)


@sync_to_async
def resolve_reenable(token: str, chat_id: int | None) -> SavedSearch | None:
    """Re-enable the search owned by ``chat_id`` for ``token``."""
    return _resolve_owned(token, chat_id, active=True)


def _resolve_owned(token: str, chat_id: int | None, active: bool) -> SavedSearch | None:
    if not chat_id:
        return None
    try:
        # The ownership check and save() must live inside the same atomic block
        # as the locked read so the row lock is held until the write commits,
        # preventing a concurrent toggle from interleaving.
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
            saved_search = (
                SavedSearch.objects.select_for_update()
                .select_related("user")
                .get(unsubscribe_token=token)
            )

            # Ownership via the stable, never-nullified chat_id (R5/F4/A4).
            if saved_search.user.chat_id != chat_id:
                return None

            saved_search.is_active = active
            saved_search.save(update_fields=["is_active", "updated_at"])
            logger.info(
                "Saved search %s for user %s set active=%s via Telegram",
                saved_search.pk,
                saved_search.user_id,
                active,
            )
            return saved_search
    except SavedSearch.DoesNotExist:
        return None
    except OperationalError as exc:
        # A lock timeout is a transient contention failure. None is already the
        # failure signal and both callers answer "Failed to disable/enable
        # notifications", so this is an honest degradation with no new string.
        # Re-raise anything that is not a lock timeout unchanged.
        if not is_lock_timeout(exc):
            raise
        logger.warning(
            "Lock timeout toggling saved search %s (SQLSTATE 55P03)",
            token,
        )
        return None
