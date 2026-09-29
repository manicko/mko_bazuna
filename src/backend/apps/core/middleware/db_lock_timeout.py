"""Predicate-gated middleware turning a lock timeout into a 503 (03-DB-004).

Six web views acquire a row lock and, on failure, redirect: ``ad_archive`` and
``ad_reactivate`` (``ads/views/edit.py``), ``ad_delete``
(``ads/views/delete.py``), and ``approve_ad`` / ``reject_ad`` / ``ban_user``
(``moderation/views/review.py``). None of them has an error surface to render
into, so a lock timeout would otherwise surface as a bare 500.

This middleware gives those six one uniform boundary. It is **predicate-gated**:
anything that is not a PostgreSQL lock timeout (SQLSTATE 55P03) is re-raised
untouched, so a connection refusal, a disk-full or a genuine bug keeps its
existing behaviour and cannot be masked. Views that DO have an error surface
(``ad_edit`` returns ``ads/edit.html``) handle the timeout in-view instead, so
the seller's typed form is preserved rather than replaced by a 503.
"""

import logging

from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext_lazy as _

from apps.core.utils.db_lock_timeout import is_lock_timeout

logger = logging.getLogger(__name__)

# Body for the lock-timeout 503. Deliberately distinct from the bot/seller
# "system is busy" string so the two are not conflated in the message catalog:
# this is the operational, retry-oriented surface for a transient contention.
_LOCK_TIMEOUT_MESSAGE = _(
    "The server is busy processing another change. Please try again shortly."
)

# Advise the client to retry after the contention window. 30 s comfortably
# exceeds the 10 s connection-level lock_timeout, so a retry cannot land inside
# the same contention.
_RETRY_AFTER_SECONDS = 30


class DbLockTimeoutMiddleware:
    """Convert a lock-timeout ``OperationalError`` into a 503 response.

    ``process_exception`` is only called for an exception raised out of the
    view (or a later middleware). When the exception is anything other than a
    lock timeout the predicate returns False and this method returns None,
    letting Django's normal exception handling continue.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(  # pyright: ignore[reportUnusedParameter] - protocol signature
        self, request: HttpRequest, exception: BaseException
    ) -> HttpResponse | None:
        if not is_lock_timeout(exception):
            return None

        logger.warning(
            "Lock timeout while handling %s %s (SQLSTATE 55P03); returning 503",
            request.method,
            request.path,
        )
        return HttpResponse(
            str(_LOCK_TIMEOUT_MESSAGE),
            status=503,
            headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
        )
