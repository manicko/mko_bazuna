"""
Tests for the ``apps.users.services.login_token`` service module (ENT-005).

This is the deliverable of the ENT-005 extraction: the ``LoginToken``
lifecycle (issue / claim / consume) is owned by a services module and is
testable synchronously — without HTTP and without Telegram. The module's
contract is written here rather than into ``test_login.py`` so that the
eleven must-survive suites keep passing byte-identical and the refactor stays
auditable.

Honest limits (stated, not skipped):
- Every behavioural case below is green *before* the extraction when expressed
  against the pre-refactor code paths — that is the point of a refactor.
- No behavioural test can discriminate ``telegram_id=<observed>`` from
  ``telegram_id IS NOT NULL`` in the consume predicate: given the preceding
  read has already excluded the ``NULL`` case the two spellings are
  semantically equivalent by construction, and no production caller can supply
  a foreign id. ``TestClaimConsumeAgreement::test_d_never_claimed_is_pending``
  is the closest proxy (it fails if the *read* guard disappears). The identity
  binding's remaining protection is structural and documentary — see
  ``TestLoginHandshakeOwnership``.
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.users.models import LoginToken, User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# A 32-char URL-safe token matching the bot's deep-link pattern.
_LOGIN_PATTERN = re.compile(r"^login_([A-Za-z0-9_-]{32})$")
_URLSAFE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)


def _make_token(
    raw_token: str,
    *,
    telegram_id: int | None = None,
    consumed_at=None,
    expires_at=None,
) -> LoginToken:
    """Create a ``LoginToken`` row for a known raw token."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    if expires_at is None:
        expires_at = timezone.now() + timedelta(hours=1)
    return LoginToken.objects.create(
        token_hash=token_hash,
        telegram_id=telegram_id,
        consumed_at=consumed_at,
        expires_at=expires_at,
    )


def _claim(token_hash: str, telegram_id: int, now=None) -> LoginToken | None:
    """Synchronous wrapper over the service claim for readable tests."""
    from apps.users.services.login_token import claim_token

    if now is None:
        now = timezone.now()
    return claim_token(token_hash, telegram_id, now)


# ---------------------------------------------------------------------------
# TestIssueToken
# ---------------------------------------------------------------------------


class TestIssueToken:
    """``issue_token`` mints a fresh token, persisting only the SHA-256 hash."""

    def test_stores_sha256_of_raw(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        stored = LoginToken.objects.get(token_hash=issued.token_hash)
        expected = hashlib.sha256(issued.raw_token.encode()).hexdigest()
        assert stored.token_hash == expected

    def test_leaves_telegram_id_and_consumed_at_null(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        stored = LoginToken.objects.get(token_hash=issued.token_hash)
        assert stored.telegram_id is None
        assert stored.consumed_at is None

    def test_expires_in_5_minutes(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        stored = LoginToken.objects.get(token_hash=issued.token_hash)
        remaining = stored.expires_at - timezone.now()
        assert 240 <= remaining.total_seconds() <= 300

    def test_raw_never_persisted(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        assert len(issued.raw_token) == 32
        assert len(issued.token_hash) == 64
        # The stored value is the hash, never the raw token.
        stored = LoginToken.objects.get(token_hash=issued.token_hash)
        assert stored.token_hash != issued.raw_token

    def test_raw_token_is_urlsafe_and_matches_pattern(self) -> None:
        from apps.users.services.login_token import issue_token

        issued = issue_token()
        assert all(c in _URLSAFE_CHARS for c in issued.raw_token)
        # The raw token is exactly the `{32}` captured group of the bot's
        # deep-link pattern: /start login_<32-char-token>.
        assert re.fullmatch(r"[A-Za-z0-9_-]{32}", issued.raw_token) is not None
        assert _LOGIN_PATTERN.match(f"login_{issued.raw_token}") is not None

    def test_two_issues_differ(self) -> None:
        from apps.users.services.login_token import issue_token

        first = issue_token()
        second = issue_token()
        assert first.raw_token != second.raw_token
        assert first.token_hash != second.token_hash


# ---------------------------------------------------------------------------
# TestClaimToken
# ---------------------------------------------------------------------------


class TestClaimToken:
    """``claim_token`` sets ``telegram_id`` on a live, unclaimed token."""

    def test_fresh_live_token_claimed_consumed_at_still_none(self) -> None:
        raw = "a" * 32
        token = _make_token(raw)
        claimed = _claim(token.token_hash, 700000001)
        assert claimed is not None
        assert claimed.telegram_id == 700000001
        # The web phase consumes it later — the claim must not set consumed_at.
        assert claimed.consumed_at is None

    def test_expired_token_not_claimable(self) -> None:
        raw = "b" * 32
        token = _make_token(raw, expires_at=timezone.now() - timedelta(hours=1))
        assert _claim(token.token_hash, 700000002) is None

    def test_already_consumed_token_not_claimable(self) -> None:
        raw = "c" * 32
        token = _make_token(
            raw, telegram_id=700000003, consumed_at=timezone.now()
        )
        assert _claim(token.token_hash, 700000004) is None

    def test_unknown_hash_not_claimable(self) -> None:
        assert _claim("f" * 64, 700000005) is None

    def test_second_claim_returns_none(self) -> None:
        raw = "d" * 32
        token = _make_token(raw)
        assert _claim(token.token_hash, 700000006) is not None
        # A different user cannot re-claim an already-claimed token.
        assert _claim(token.token_hash, 700000007) is None


# ---------------------------------------------------------------------------
# TestConsumeToken
# ---------------------------------------------------------------------------


class TestConsumeToken:
    """``consume_token`` returns a typed ``ConsumeResult`` for every case."""

    def test_unknown_token_not_found(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        result = consume_token("z" * 32)
        assert result.outcome is ConsumeOutcome.NOT_FOUND
        assert result.telegram_id is None

    def test_expired_token_gone(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "e" * 32
        _make_token(raw, expires_at=timezone.now() - timedelta(hours=1))
        result = consume_token(raw)
        assert result.outcome is ConsumeOutcome.GONE

    def test_consumed_token_gone(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "g" * 32
        _make_token(raw, telegram_id=700000010, consumed_at=timezone.now())
        result = consume_token(raw)
        assert result.outcome is ConsumeOutcome.GONE

    def test_unclaimed_live_token_pending(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "h" * 32
        token = _make_token(raw)
        result = consume_token(raw)
        assert result.outcome is ConsumeOutcome.PENDING
        assert result.telegram_id is None
        # The read must not mutate the row — consumed_at stays NULL.
        token.refresh_from_db()
        assert token.consumed_at is None

    def test_claimed_token_consumed(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "i" * 32
        _make_token(raw, telegram_id=700000011)
        result = consume_token(raw)
        assert result.outcome is ConsumeOutcome.CONSUMED
        assert result.telegram_id == 700000011
        # The UPDATE actually stamped consumed_at.
        token = LoginToken.objects.get(token_hash=hashlib.sha256(raw.encode()).hexdigest())
        assert token.consumed_at is not None

    def test_row_deleted_before_consume_not_found(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "j" * 32
        token = _make_token(raw)
        token.delete()
        result = consume_token(raw)
        assert result.outcome is ConsumeOutcome.NOT_FOUND


# ---------------------------------------------------------------------------
# TestClaimConsumeAgreement
# ---------------------------------------------------------------------------


class TestClaimConsumeAgreement:
    """The claim and consume predicates agree on the (deliberately different)
    phase boundaries — the cross-predicate guard the report asks for."""

    def test_a_second_claim_does_not_rewrite_telegram_id(self) -> None:
        raw = "k" * 32
        token = _make_token(raw)
        assert _claim(token.token_hash, 700000020) is not None
        # Second claim by a different user is rejected ...
        assert _claim(token.token_hash, 700000021) is None
        # ... and the row's telegram_id is still the first claimer's.
        token.refresh_from_db()
        assert token.telegram_id == 700000020

    def test_b_consumed_token_not_claimable_by_anyone(self) -> None:
        from apps.users.services.login_token import consume_token

        raw = "l" * 32
        token = _make_token(raw, telegram_id=700000022)
        assert consume_token(raw).outcome.value == "consumed"
        # Other direction of phase separation: after CONSUMED, no X can claim.
        for x in (700000023, 700000024):
            assert _claim(token.token_hash, x) is None

    def test_c_consumed_binds_to_the_claiming_user(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        # Users for BOTH the claiming and the non-claiming telegram_id exist.
        User.objects.create(
            telegram_id=700000030, chat_id=700000030, username="claimer"
        )
        User.objects.create(
            telegram_id=700000031, chat_id=700000031, username="other"
        )
        raw = "m" * 32
        token = _make_token(raw)
        assert _claim(token.token_hash, 700000030) is not None
        result = consume_token(raw)
        assert result.outcome is ConsumeOutcome.CONSUMED
        assert result.telegram_id == 700000030
        token.refresh_from_db()
        assert token.consumed_at is not None

    def test_d_never_claimed_is_pending(self) -> None:
        from apps.users.services.login_token import ConsumeOutcome, consume_token

        raw = "n" * 32
        token = _make_token(raw)
        result = consume_token(raw)
        # The case with real discriminating power: if the read's
        # ``telegram_id is None`` guard were deleted, the same input falls
        # through to the UPDATE, matches zero rows, and returns LOST_RACE
        # (410) instead of PENDING (204) — a silent failure of the two-phase
        # handshake.
        assert result.outcome is ConsumeOutcome.PENDING
        assert result.telegram_id is None
        token.refresh_from_db()
        assert token.consumed_at is None


# ---------------------------------------------------------------------------
# TestLoginHandshakeOwnership
# ---------------------------------------------------------------------------


class TestLoginHandshakeOwnership:
    """Structural assertions that the lifecycle is owned by one service module.

    This is the one genuinely red→green class: all three assertions are false
    before the extraction and true after. A green ownership test is not
    evidence of correctness — it is a structural tripwire so a future
    implementor knows where to move SQL rather than that the test is obsolete.
    """

    _OWNER = "apps.users.services.login_token"

    def test_three_operations_importable_from_one_module(self) -> None:
        # Must resolve from a single module by full path.
        from apps.users.services.login_token import (
            claim_token,
            consume_token,
            issue_token,
        )

        assert callable(issue_token)
        assert callable(claim_token)
        assert callable(consume_token)

    def test_consent_view_has_no_token_logic(self) -> None:
        source = Path(__file__).parents[1].joinpath("views", "consent.py").read_text()
        for forbidden in (
            "hashlib",
            "secrets",
            "LoginToken",
            "UPDATE login_tokens",
            ".update(consumed_at=",
        ):
            assert forbidden not in source, (
                f"consent.py must not contain {forbidden!r}; the consume/issue "
                f"predicates belong in {self._OWNER}"
            )

    def test_bot_handler_has_no_raw_sql(self) -> None:
        source = (
            Path(__file__).parents[4].joinpath("telegram_bot", "handlers", "login.py")
        ).read_text()
        # ``cursor.execute`` + ``UPDATE login_tokens`` together uniquely identify
        # raw SQL in the handler; ``RETURNING`` is deliberately not asserted
        # because the mandated thin-wrapper docstring mentions it in prose.
        for forbidden in (
            "UPDATE login_tokens",
            "cursor.execute",
        ):
            assert forbidden not in source, (
                f"handlers/login.py must not contain {forbidden!r}; the claim SQL "
                f"belongs in {self._OWNER}.claim_token"
            )
