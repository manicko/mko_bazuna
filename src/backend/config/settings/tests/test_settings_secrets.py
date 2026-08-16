"""
Tests for Django settings import-time secret validation.

Asserts that:
- Absent DJANGO_SECRET_KEY raises ImproperlyConfigured at settings import time.
- BOT_TOKEN empty with DEBUG=False (production) raises ImproperlyConfigured.
- BOT_TOKEN empty with DEBUG=True (development) is permitted.

Settings are evaluated at import time and Django caches them on first access,
so override_settings/monkeypatch cannot test import-time failure. These tests
use subprocess isolation with controlled os.environ to verify the guards fire
at module import.
"""

import os
import subprocess
import sys

from django.test import SimpleTestCase


class SettingsSecretsTests(SimpleTestCase):
    """Tests for secret validation at settings import time."""

    def _run_in_subprocess(self, env: dict[str, str], import_code: str) -> str:
        """Run Python code in a subprocess with the given environment."""
        env_with_path = {
            **env,
            "PYTHONPATH": os.pathsep.join(sys.path),
        }
        result = subprocess.run(
            [sys.executable, "-c", import_code],
            env=env_with_path,
            capture_output=True,
            text=True,
        )
        return result.stderr

    def test_django_secret_key_required(self) -> None:
        """Importing settings without DJANGO_SECRET_KEY raises ImproperlyConfigured."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k != "DJANGO_SECRET_KEY" and k != "BOT_TOKEN"
        }
        env["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
        stderr = self._run_in_subprocess(
            env,
            "import django; django.setup()",
        )
        self.assertIn("ImproperlyConfigured", stderr)

    def test_bot_token_allowed_empty_in_debug(self) -> None:
        """BOT_TOKEN may be empty when DEBUG=True (development mode)."""
        env = dict(os.environ)
        env["BOT_TOKEN"] = ""
        env["DJANGO_SETTINGS_MODULE"] = "config.settings.dev"
        env["PYTHONPATH"] = os.pathsep.join(sys.path)
        result = subprocess.run(
            [sys.executable, "-c", "from django.conf import settings; print(settings.BOT_TOKEN)"],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_bot_token_required_in_production(self) -> None:
        """BOT_TOKEN empty with DEBUG=False (production) raises ImproperlyConfigured."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k != "BOT_TOKEN"
        }
        env["DJANGO_SECRET_KEY"] = "test-secret-key-for-testing-only"
        env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
        env["PYTHONPATH"] = os.pathsep.join(sys.path)
        result = subprocess.run(
            [sys.executable, "-c", "import django; django.setup()"],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("ImproperlyConfigured", result.stderr)
