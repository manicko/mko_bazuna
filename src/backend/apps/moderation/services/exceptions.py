"""
Custom exceptions for moderation services.

Each exception has a single, well-defined trigger condition and a stable
``error_code`` attribute so callers can branch on it without relying on
string matching.
"""

__all__ = ["MaxAdsExceeded"]


class MaxAdsExceeded(Exception):
    """Raised when a user has reached their maximum active-ads limit.

    Triggered inside ``set_published()`` when the authoritative, locked
    re-count of PUBLISHED + ON_MODERATION ads reaches
    ``ModerationCriteria.max_ads_per_user``.  This is the race-safe guard:
    the early check in ``auto_moderate()`` / ``check()`` is advisory only;
    the authoritative check inside ``set_published()`` runs under
    ``select_for_update()`` with the user row locked.
    """

    error_code = "max_ads_exceeded"

    def __init__(self, user_id: int, limit: int, current_count: int) -> None:
        self.user_id = user_id
        self.limit = limit
        self.current_count = current_count
        super().__init__(
            f"User {user_id} has reached the maximum of {limit} active ads "
            f"(currently has {current_count})."
        )
