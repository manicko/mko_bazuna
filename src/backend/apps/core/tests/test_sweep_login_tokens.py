"""
Split from test_sweep_commands.py: Tests for the cleanup_login_tokens command.

Login token cleanup removes expired, consumed tokens older than 24 hours,
guarded by an advisory lock (lock id 5).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.core.enums import AdvisoryLockId
from apps.users.models import LoginToken

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


class TestCleanupLoginTokens:
    """Tests for cleanup_login_tokens command (advisory lock 5)."""

    def _make_token(self, **kwargs) -> LoginToken:
        defaults = {
            "token_hash": f"hash_{LoginToken.objects.count()}_{id(kwargs)}",
            "telegram_id": 900000002,
            "expires_at": timezone.now() - timezone.timedelta(hours=1),
        }
        defaults.update(kwargs)
        return LoginToken.objects.create(**defaults)

    def test_dry_run_does_not_delete(self):

        expired = self._make_token(expires_at=timezone.now() - timedelta(hours=1))
        call_command("cleanup_login_tokens", "--dry-run")
        assert LoginToken.objects.filter(pk=expired.pk).exists()

    def test_deletes_expired_tokens(self):

        # Expired token (expires_at in the past) is deleted.
        expired = self._make_token(expires_at=timezone.now() - timedelta(hours=1))
        # Valid (unexpired, unconsumed) token is preserved.
        valid = self._make_token(expires_at=timezone.now() + timedelta(hours=1))
        call_command("cleanup_login_tokens")
        assert not LoginToken.objects.filter(pk=expired.pk).exists()
        assert LoginToken.objects.filter(pk=valid.pk).exists()

    def test_preserves_recently_consumed_tokens(self):

        # consumed_at is set but created_at is recent (auto_now_add), so the
        # "consumed >24h ago" branch must NOT fire. With a future expiry the
        # expired branch also does not fire -> token is preserved.
        consumed_recent = self._make_token(
            expires_at=timezone.now() + timedelta(hours=1),
            consumed_at=timezone.now() - timedelta(hours=1),
        )
        call_command("cleanup_login_tokens")
        assert LoginToken.objects.filter(pk=consumed_recent.pk).exists()

    def test_preserves_fresh_unconsumed_tokens(self):

        token = self._make_token(
            expires_at=timezone.now() + timedelta(hours=1),
            consumed_at=None,
        )
        call_command("cleanup_login_tokens")
        assert LoginToken.objects.filter(pk=token.pk).exists()

    def test_lock_id_is_cleanup_login_tokens(self):
        assert AdvisoryLockId.CLEANUP_LOGIN_TOKENS == 5
