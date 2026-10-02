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
``RETURNING_COLUMNS`` is ``LoginToken``'s **complete** field set and the
``claim_token`` SQL's ``RETURNING`` clause is **built from it** (``", ".join``),
so a model column and the SQL can never drift apart.

The risk is **silent**, not loud, and the plan's earlier "raises ``TypeError``"
claim was inverted. ``django/db/models/base.py::Model.__init__`` iterates the
**model's** fields and pops each attname inside a ``try``, falling back to
``field.get_default()`` on ``KeyError``. A model field **missing** from the
``RETURNING`` list is therefore silently left at its default (``None``) — no
exception, a fully green suite, and the binding dropped on every bot claim.
``TypeError`` fires only in the **opposite** direction (a ``RETURNING`` name the
model lacks). ``strict=True`` in the ``zip`` below is vacuous because both
sequences come from the same ``cursor.execute``, and order divergence is not a
runtime concern (``dict(zip(...))`` discards order and ``LoginToken(**d)`` is
keyword-only) — matching order is a **consistency** obligation, tested as such.

The ``04-AUT-007`` boundary
---------------------------
``issue_token`` supersedes a browser's earlier **live, unclaimed** token at
issue time, so one browser profile holds at most **one live unclaimed token**.
The supersession predicate has exactly four conjuncts and all four are
load-bearing:

- ``browser_binding = <digest of the resolved browser id>`` — scoped to this
  browser only. There is deliberately **no** ``OR browser_binding IS NULL``
  disjunct: a ``NULL`` row is already never redeemable (``G-1a`` → ``UNBOUND``
  in ``consume_token``), so excluding it loses no control, and the disjunct
  would let one browser's issue reach across bindings.
- ``telegram_id IS NULL`` — **required**. At issue time no identity exists, so
  this excludes every token the bot has **already claimed**. A claimed row is
  mid-handshake; burning it would let a same-site prefetch of ``/login/issue/``
  kill a login whose user already tapped the Telegram button — strictly worse
  than ``04-AUT-007``. This applies ``B-03``'s ``UNBOUND`` non-burning rule to
  supersession.
- ``consumed_at IS NULL AND expires_at > now`` — only a currently live token is
  superseded; an already-consumed or expired row is left untouched.

The verb is ``UPDATE ... SET consumed_at``, **never** ``DELETE``: it reuses an
existing column (**no migration**), and ``claim_token``'s ``WHERE`` plus
``consume_token``'s read guard already refuse a burned row as ``GONE``. This
module therefore remains a **burn, not a third deleter** —
``users/services/deletion.py``'s ``withdraw_consent`` and
``core/management/commands/cleanup_login_tokens.py`` stay the **only two**
deleters.

The predicate is bounded by ``TOKEN_TTL_SECONDS`` (≤300 s): at most one
unclaimed row per browser can be live at a time, and any row the supersession
misses expires within the window. The framing is **one live unclaimed token per
browser profile**, not "one live token per user": ``telegram_id`` is ``NULL``
at issue time, so a per-user invariant is not expressible here. The likeliest
real-world trigger is a **second tab of the same profile**: opening
``/login/issue/`` there silently supersedes the first tab's still-live
unclaimed token, so only the second tab's deep-link stays redeemable.

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
import re
import secrets
from enum import StrEnum
from typing import Final, NamedTuple

from django.conf import settings
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

# Entropy of the browser id in bytes: secrets.token_urlsafe(16) yields a
# 22-char URL-safe value (128 bits). The binding is a **correlator**, not an
# authenticator — the 192-bit raw token remains the only authenticator — so
# 128 bits of unkeyed entropy is proportionate, and the stored value is a
# SHA-256 digest of it (the raw id is never stored).
BROWSER_ID_ENTROPY_BYTES: Final[int] = 16

# First-party essential cookie carrying the raw browser id across the two-phase
# handshake. The name and its ``Secure`` flag are **derived from one setting**
# (``LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX``) and therefore cannot disagree; the
# service owns the pair and the view imports both, mirroring
# PREFERRED_CITY_COOKIE_NAME's ownership pattern.
#
# The ``__Host-`` prefix is load-bearing, not cosmetic: without it the binding is
# client-chosen. RFC 6265 §5.3 lets *any* sibling subdomain set a domain cookie
# (``Set-Cookie: login_browser_id=<attacker value>; Domain=.example.com; Path=/``)
# and nothing forbids the name, so a subdomain with XSS or a dangling-CNAME
# takeover can supply the value on a victim's first login — the exact moment the
# control matters — and then redeem the token. ``__Host-`` restricts the cookie to
# a host-only, ``Secure``, ``Path=/`` origin, which converts "the client chose a
# value" into "only this exact origin can set a value". The ``__Host-`` contract
# requires all three attributes; the view's ``set_cookie`` call supplies them and
# the invariant is pinned by the cookie-contract test.
#
# Why name and flag are one resolved pair
# ---------------------------------------
# A ``__Host-``-prefixed cookie **without** ``Secure`` is rejected by every
# conformant user agent (Chromium 154, Firefox, Safari), so the cookie is
# discarded, ``login_status`` reads ``browser_id=None``, the binding gate returns
# ``UNBOUND``, and every dev login is a ``410``. The prefix and its mandatory
# ``Secure`` flag are therefore a single invariant: emitting one without the
# other is not a cosmetic mismatch but a broken login. Deriving both from
# ``LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX`` makes that state unrepresentable —
# there is no code path on which the emitted name can carry the prefix while the
# emitted flag is ``False``.
#
# The HTTP-only-origin trade-off (deliberate, not an oversight)
# -------------------------------------------------------------
# ``dev.py`` and ``test.py`` serve plain HTTP (Django is published directly on
# :8000; nginx is behind a profile). ``__Host-`` cannot be satisfied over plain
# HTTP, so those modules set the prefix off and emit the unprefixed name with no
# ``Secure`` flag. On an HTTP-only origin there is **no transport security
# anyway**, and the sibling-subdomain injection the prefix closes was never
# defeatable there in a way the prefix could help with, so the control is absent
# by design. ``base.py`` (production, behind TLS) keeps it on. Because the pair
# is resolved per settings module and cookies never cross origins, a client only
# ever sees the name belonging to its own origin — there is no cross-environment
# conflict. Do **not** "simplify" this into a single hardcoded name.
LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX: Final[bool] = bool(
    settings.LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX
)
LOGIN_BROWSER_ID_COOKIE: Final[str] = (
    "__Host-login_browser_id"
    if LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX
    else "login_browser_id"
)
LOGIN_BROWSER_ID_COOKIE_SECURE: Final[bool] = LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX

# A well-formed browser id is exactly the URL-safe shape secrets.token_urlsafe
# produces. A presented cookie value that does not match is treated as absent
# and re-minted, never persisted unvalidated.
_BROWSER_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{22}$")

# The complete ``LoginToken`` field set, in declaration order. The claim SQL's
# ``RETURNING`` clause is built from this tuple, so a new model column cannot
# go missing from the SQL. See the module docstring for why a stale
# ``RETURNING`` fails silently rather than raising.
RETURNING_COLUMNS: Final[tuple[str, ...]] = (
    "id",
    "token_hash",
    "telegram_id",
    "created_at",
    "expires_at",
    "consumed_at",
    "browser_binding",
)


class ConsumeOutcome(StrEnum):
    """Outcome of a web-side token consume, used to map to an HTTP status."""

    NOT_FOUND = "not_found"
    GONE = "gone"
    PENDING = "pending"
    UNBOUND = "unbound"
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
    """Typed result of ``issue_token`` — the raw token, its hash, and the raw
    browser id that the view must set as a cookie."""

    raw_token: str
    token_hash: str
    browser_id: str


def _hash_raw_token(raw_token: str) -> str:
    """Return the plain (unkeyed) SHA-256 hex digest of ``raw_token``."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _hash_browser_id(browser_id: str) -> str:
    """Return the plain (unkeyed) SHA-256 hex digest of ``browser_id``.

    Mirrors ``_hash_raw_token``: only the digest is ever persisted. The binding
    is a correlator, so an unkeyed digest is proportionate.
    """
    return hashlib.sha256(browser_id.encode()).hexdigest()


def _resolve_browser_id(presented: str | None) -> str:
    """Reuse a well-formed presented browser id, else mint a fresh one.

    Reuse (not re-mint) is what makes a repeat issue safe: ``login_issue``
    issues a fresh token per page view and several clients prefetch, so
    minting on every issue would leave token #1 bound to the old id while the
    cookie now holds a new one. An absent or malformed value is re-minted —
    an attacker-supplied cookie value must never reach the database.
    """
    if presented is not None and _BROWSER_ID_PATTERN.fullmatch(presented):
        return presented
    return secrets.token_urlsafe(BROWSER_ID_ENTROPY_BYTES)


def issue_token(browser_id: str | None = None) -> IssuedToken:
    """Mint a fresh login token and persist only its SHA-256 hash.

    Returns the ``(raw_token, token_hash, browser_id)`` triple. The raw token
    is never stored — the only two ways to obtain it are this return value and
    the POST body. ``telegram_id`` and ``consumed_at`` are left at their
    ``NULL`` defaults.

    The browser binding is the SHA-256 digest of the resolved browser id; only
    the digest is stored (``browser_binding``), never the raw id. A well-formed
    presented ``browser_id`` is reused; an absent or malformed one is minted.

    Before creating the new row, this browser's earlier live, **unclaimed**
    token is superseded with an ``UPDATE ... SET consumed_at`` — never a
    ``DELETE``, and never an ``atomic()`` of its own (the caller owns the
    transaction). The result is **one live unclaimed token per browser
    profile**; the framing is not "per user" because ``telegram_id`` is
    ``NULL`` at issue time. A token the bot has already claimed
    (``telegram_id IS NOT NULL``) is mid-handshake and is **not** touched, and
    a ``NULL``-binding row is excluded. See the module docstring's
    ``The 04-AUT-007 boundary`` section for the full predicate rationale.

    Args:
        browser_id: The raw browser id from the incoming login-binding cookie
            (``__Host-login_browser_id`` on a transport-secure origin,
            ``login_browser_id`` otherwise), or ``None`` when the cookie is
            absent.
    """
    raw_token = secrets.token_urlsafe(RAW_TOKEN_ENTROPY_BYTES)
    token_hash = _hash_raw_token(raw_token)
    resolved_browser_id = _resolve_browser_id(browser_id)
    browser_binding = _hash_browser_id(resolved_browser_id)

    # 04-AUT-007 supersession. UPDATE-before-CREATE, so a second issue supersedes
    # the first *instead of* leaving both live. Unclaimed tokens only
    # (``telegram_id IS NULL``): a claimed token is mid-handshake and burning
    # it would be worse than the defect. No ``OR browser_binding IS NULL``
    # disjunct — a NULL row is already unredeemable (UNBOUND) and the disjunct
    # would cross bindings.
    superseded = LoginToken.objects.filter(
        browser_binding=browser_binding,
        telegram_id__isnull=True,
        consumed_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).update(consumed_at=timezone.now())

    logger.info(
        "Issued login token hash=%s... superseded %d prior unclaimed token(s) "
        "for binding %s...",
        token_hash[:8],
        superseded,
        browser_binding[:8],
    )

    LoginToken.objects.create(
        token_hash=token_hash,
        expires_at=timezone.now() + datetime.timedelta(seconds=TOKEN_TTL_SECONDS),
        browser_binding=browser_binding,
    )
    return IssuedToken(
        raw_token=raw_token,
        token_hash=token_hash,
        browser_id=resolved_browser_id,
    )


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
            RETURNING """
            + ", ".join(RETURNING_COLUMNS),
            [telegram_id, token_hash, now],
        )
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]

    return LoginToken(**dict(zip(columns, row, strict=True)))


def consume_token(raw_token: str, *, browser_id: str | None) -> ConsumeResult:
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

    The browser binding is checked **after** ``PENDING`` and **before** the
    ``UPDATE``, and re-asserted inside the ``UPDATE``'s filter so it cannot be
    lost to a stale read. A row whose ``browser_binding`` is ``NULL``, or whose
    presented browser id is absent, malformed, or digests to a different value,
    returns ``UNBOUND`` and is **never burned** — an attacker who fails the
    binding check must not be able to destroy a legitimate user's in-flight
    login. Because this gate precedes the ``UPDATE``, it is the *only*
    non-``CONSUMED`` path that does not burn the token.

    ``browser_id`` is **required and keyword-only**. The reason is
    diagnosability, not fail-closedness: a default of ``None`` fails *closed*
    (the client presents nothing, a fresh id mismatches, and the outcome is
    ``UNBOUND``), but ``UNBOUND`` is deliberately indistinguishable from expiry
    at the HTTP layer, so a forgotten argument would surface as a nearly
    undiagnosable ``410``. A required keyword-only parameter turns that into a
    ``TypeError`` caught at review time.

    Args:
        raw_token: The raw token from ``request.POST["token"]``.
        browser_id: The raw browser id from the login-binding cookie
            (``__Host-login_browser_id`` on a transport-secure origin,
            ``login_browser_id`` otherwise), or ``None`` when the cookie is
            absent.

    Returns:
        A ``ConsumeResult`` whose ``outcome`` discriminates the six cases.
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

    # Binding gate — fail closed, and deliberately NO burn. A NULL stored
    # binding, an absent/malformed presented id, or a digest mismatch all
    # refuse the token without consuming it (unlike every other 410 path).
    if (
        token.browser_binding is None
        or browser_id is None
        or not _BROWSER_ID_PATTERN.fullmatch(browser_id)
    ):
        return ConsumeResult(ConsumeOutcome.UNBOUND, token_hash, token.telegram_id)
    if _hash_browser_id(browser_id) != token.browser_binding:
        return ConsumeResult(ConsumeOutcome.UNBOUND, token_hash, token.telegram_id)

    # Bot has claimed the token — atomically mark consumed (single UPDATE).
    # Optimistic concurrency: filter conditions ensure only an unclaimed,
    # unexpired token with a matching telegram_id AND a matching browser
    # binding is touched — the binding is re-asserted here, not trusted from
    # the read above.
    updated = LoginToken.objects.filter(
        token_hash=token_hash,
        telegram_id=token.telegram_id,
        consumed_at__isnull=True,
        expires_at__gt=timezone.now(),
        browser_binding=_hash_browser_id(browser_id),
    ).update(consumed_at=timezone.now())

    if updated == 0:
        # Race condition — another request already consumed it.
        return ConsumeResult(ConsumeOutcome.LOST_RACE, token_hash, token.telegram_id)

    return ConsumeResult(ConsumeOutcome.CONSUMED, token_hash, token.telegram_id)
