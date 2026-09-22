"""Shared test constants for settings tests."""

# 53-char key that passes prod.py strength checks (>= 50 chars, no <...>
# placeholder, no dev-only-dummy sentinel). Starts with the legacy
# "test-secret-key-for-testing-only" prefix so the existing gitleaks
# allowlist regex (".env.test.example" path allowlist + "test-secret-key-for-testing-only"
# regex allowlist in .gitleaks.toml) continues to suppress findings.
TEST_SECRET_KEY = "test-secret-key-for-testing-only-extra-entropy-9f2a7c"
TEST_BOT_TOKEN = "test-bot-token-for-testing-only"
TEST_TRANSLATE_KEY = "test-translate-key-for-testing-only"
