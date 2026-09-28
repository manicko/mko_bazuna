"""
Owns the ``LoginToken`` lifecycle end to end: issuance (web), claim (bot,
phase 1), consume (web, phase 2). This is the single place the token protocol
is expressed. Web-side hashing lives here and nowhere else.

The two-phase protocol and the deliberate asymmetry
----------------------------------------------------
The login handshake is two operations with two *different* predicates. They
are written out in full in each function below — they are **not** the same
predicate and must **never** be unified into a shared helper:

- Claim (bot, phase 1) — ``claim_token`` sets ``telegram_id``:
  ``telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now``.
  The claim is a single statement with **no prior read**: there is no
  read-then-write window. Postgres re-evaluates the ``WHERE`` under READ
  COMMITTED after acquiring the row lock, so a concurrent claim matches
  zero rows (zero-TOCTOU).
- Consume (web, phase 2) — ``consume_token`` sets ``consumed_at``:
  ``telegram_id = <observed> AND consumed_at IS NULL AND expires_at > now``.
  The consume **must** read first (it needs ``token.telegram_id`` to pick the
  user), and its read may be stale, but every guard is re-asserted inside the
  ``UPDATE`` and the affected-row count is the arbiter (zero-TOCTOU).

The shared conjuncts (``consumed_at IS NULL AND expires_at > now``) are
written out and commented in **both** functions, deliberately not factored
out: a ``Q(consumed_at__isnull=True, expires_at__gt=now)`` helper cannot be
used by the raw-SQL claim without re-spelling it as SQL text, and using it
only in ``consume_token`` would invert the asymmetry. Phase 04 rated this
sound — there is no defect here.

The ``RETURNING`` / model-shape coupling
----------------------------------------
The ``RETURNING`` list in ``claim_token`` is ``LoginToken``'s **complete**
field set (``id, token_hash, telegram_id, created_at, expires_at,
consumed_at``), so ``zip(..., strict=True)`` + ``LoginToken(**…)`` raise
``TypeError`` if ``login_tokens`` ever gains a column without the list being
updated. It is a schema contract, not a convenience.

The ``AUT-007`` boundary
------------------------
No invalidation of prior outstanding tokens is implemented here —
``issue_token`` issues a fresh token per page view, so a browser can hold
several live tokens. That is ``AUT-007`` (phase 04, VAL-002), filed separately
and retained-not-merged with ``ENT-005``. When it lands it lands **inside
``issue_token`` in this module**, not as an ad-hoc patch in a view. Likewise,
this module **does not delete** tokens — ``users/services/deletion.py``'s
``withdraw_consent`` and ``core/management/commands/cleanup_login_tokens.py``
remain the **only two** deleters, and this module must not create a third.

Parameter asymmetry (forced by the two call sites): ``claim_token`` accepts a
``token_hash`` because the bot hashes before the handler boundary and
``handle_login_orm``'s ``token_hash=`` parameter is pinned by 12 bot test call
sites; ``consume_token`` accepts the ``raw_token`` because the web phase
receives only ``request.POST["token"]``. Do not "fix" this.

Clock rule: every expiry comparison and every stamp is a separate
``timezone.now()`` from the Python application clock; SQL ``NOW()`` is never
used and the call sites are deliberately **not** consolidated.
"""

import datetime
import hashlib
import logging
import secrets
from enum import StrEnum
from typing import Final, NamedTuple

from django.db import connection
from django.utils import timezone

from apps.users.models import LoginToken

# module-level logger is convention-driven (matches the services layer).
logger = logging.getLogger(__name__)

# Token lifetime in seconds (5 minutes). Unit is in the name; no second
# constant is derived from this one — timedelta(seconds=...) is computed at the
# use site.
TOKEN_TTL_SECONDS: Final[int] = 300

# Entropy of the raw token in bytes: secrets.token_urlsafe(24) yields 32
# URL-safe chars (~192-bit CSPRNG), matching the bot regex `{32}`.
RAW_TOKEN_ENTROPY_BYTES: Final[int] = 24


class ConsumeOutcome(StrEnum):
    """Outcome of a web-side token consume, used to map to an HTTP status."""

    NOT_FOUND = "not_found"
    GONE = "gone"
    PENDING = "pending"
    LOST_RACE = "lost_race"
    CONSUMED = "consumed"


class ConsumeResult(NamedTuple):
    """Typed result of ``consume_token``.

    ``token_hash`` is returned so the caller can log an 8-char correlation
    prefix without re-hashing a raw token it no longer holds.
    """

    outcome: ConsumeOutcome
    token_hash: str
    telegram_id: int | None


class IssuedToken(NamedTuple):
    """Typed result of ``issue_token`` — the raw token and its hash pair."""

    raw_token: str
    token_hash: str


def _hash_raw_token(raw_token: str) -> str:
    """Return the plain (unkeyed) SHA-256 hex digest of ``raw_token``."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def issue_token() -> IssuedToken:
    """Mint a fresh login token and persist only its SHA-256 hash.

    Returns the ``(raw_token, token_hash)`` pair. The raw token is never
    stored — the only two ways to obtain it are this return value and the
    POST body. ``telegram_id`` and ``consumed_at`` are left at their ``NULL``
    defaults.
    """
    raw_token = secrets.token_urlsafe(RAW_TOKEN_ENTROPY_BYTES)
    token_hash = _hash_raw_token(raw_token)
    LoginToken.objects.create(
        token_hash=token_hash,
        expires_at=timezone.now() + datetime.timedelta(seconds=TOKEN_TTL_SECONDS),
    )
    return IssuedToken(raw_token=raw_token, token_hash=token_hash)


def claim_token(
    token_hash: str, telegram_id: int, now: datetime.datetime
) -> LoginToken | None:
    """Atomically claim a login token by setting its ``telegram_id``.

    Uses PostgreSQL ``UPDATE ... RETURNING`` for a single-statement,
    zero-TOCTOU claim. The ``WHERE`` clause guarantees only an unclaimed
    (``telegram_id IS NULL``), not-yet-consumed (``consumed_at IS NULL``),
    and unexpired (``expires_at > now``) token is touched. Postgres holds a
    row-level lock for the duration of the ``UPDATE``, so a concurrent claim
    from another bot worker matches zero rows and returns ``None``.

    The claim is a single statement with no prior read — there is no
    read-then-write window. Postgres re-evaluates the ``WHERE`` under READ
    COMMITTED after acquiring the row lock, so a concurrent claim matches
    zero rows.

    The caller owns the transaction; the service owns the predicate. This
    function opens no ``atomic()`` of its own — the caller
    (``handle_login_orm``) keeps the claim inside its single outer
    ``transaction.atomic()``.

    ``now`` stays a required parameter: the caller (``handle_login_orm``)
    computes it once *before* opening its ``atomic()`` and passes it in;
    reading the clock here would move it *inside* the transaction and change
    the timestamp relative to transaction start.

    Returns the claimed ``LoginToken`` instance (with ``telegram_id`` set and
    ``consumed_at`` still ``NULL``), or ``None`` when no token matched.

    Args:
        token_hash: SHA-256 hex digest of the raw token.
        telegram_id: Telegram user id to bind to the token.
        now: The Python application clock used for the ``expires_at > now``
            comparison.

    Returns:
        The claimed ``LoginToken``, or ``None`` when no live unclaimed token
        matched.
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


def consume_token(raw_token: str) -> ConsumeResult:
    """Consume a login token on the web side, atomically marking it used.

    The consume **must** read first (it needs ``token.telegram_id`` to pick
    the user), and its read may be stale, but every guard is re-asserted
    inside the ``UPDATE`` and the affected-row count is the arbiter. The
    shared live-ness conjuncts (``consumed_at IS NULL AND expires_at > now``)
    are deliberately re-spelled here, not factored out — see the module
    docstring.

    Three separate ``timezone.now()`` calls, never one variable: they are
    strictly increasing today and the stamp lands *later* than the timestamp
    that validated expiry. Consolidating changes which instant lands in
    ``consumed_at`` at the 5-minute boundary.

    The caller owns the transaction; the service owns the predicate. This
    function opens no ``atomic()`` of its own — the caller (``login_status``)
    keeps the consume inside its outer ``transaction.atomic()``, and this
    function returns the already-held instance without re-querying after the
    ``UPDATE``, so a concurrent row deletion (``withdraw_consent`` /
    ``cleanup_login_tokens``) cannot open a second window.

    Args:
        raw_token: The raw token from ``request.POST["token"]``.

    Returns:
        A ``ConsumeResult`` whose ``outcome`` discriminates the five cases.
    """
    token_hash = _hash_raw_token(raw_token)

    try:
        token = LoginToken.objects.get(token_hash=token_hash)
    except LoginToken.DoesNotExist:
        return ConsumeResult(ConsumeOutcome.NOT_FOUND, token_hash, None)

    # Expired or already consumed — gone. Single `or` (mirrors the view's
    # original single `or`; do not split it).
    if token.expires_at <= timezone.now() or token.consumed_at is not None:
        return ConsumeResult(ConsumeOutcome.GONE, token_hash, token.telegram_id)

    # Bot has not claimed the token yet — keep polling.
    if token.telegram_id is None:
        return ConsumeResult(ConsumeOutcome.PENDING, token_hash, None)

    # Bot has claimed the token — atomically mark consumed (single UPDATE).
    # Optimistic concurrency: filter conditions ensure only an unclaimed,
    # unexpired token with matching telegram_id is touched.
    updated = LoginToken.objects.filter(
        token_hash=token_hash,
        telegram_id=token.telegram_id,
        consumed_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).update(consumed_at=timezone.now())

    if updated == 0:
        # Race condition — another request already consumed it.
        return ConsumeResult(ConsumeOutcome.LOST_RACE, token_hash, token.telegram_id)

    return ConsumeResult(ConsumeOutcome.CONSUMED, token_hash, token.telegram_id)
