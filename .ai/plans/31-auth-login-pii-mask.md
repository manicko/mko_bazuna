---
# Plan metadata
id: 31
name: auth-login-pii-mask
source: .ai/audit/99-validation/04-auth-login-validated-findings.md
finding: AUT-001
effort: S
priority: P2
severity: LOW
status: done
---

# Execution Plan — AUT-001: Bot login rate-limit warning logs raw Telegram ID

## Code Context (inspection result)

Validation report `.ai\audit\99-validation\04-auth-login-validated-findings.md`
was inspected. The live source matches the report verbatim:

- `src/telegram_bot/handlers/login.py:94-98` — the rate-limit-exceeded branch
  calls `logger.warning("Login rate limit exceeded for telegram_id=%s",
  message.from_user.id)` with the **raw** Telegram ID; the handler never
  imports or calls `mask_telegram_id`.
- `src/backend/apps/core/utils/sanitize.py:51` — `mask_telegram_id` exists,
  returns `tg_<sha256[:8]>` (non-reversible, stable). Already imported & used
  by 10 web-side call sites; the bot process (`django.setup()` + shared ORM)
  already imports sibling `apps.core.*` modules, so the import path is valid.
- Production routing: both `web` and `bot` use `config.settings.prod`
  (`docker-compose.yml`), so both emit via `RedactingJsonFormatter`;
  `re.findall` against the real message returns `[]` — no redaction applies
  to an interpolated `%s` integer.
- `src/telegram_bot/tests/test_login.py:468-501` —
  `test_login_rate_limit_blocks_after_threshold` asserts the cooldown text
  but never inspects `caplog` (test gap).
- `src/backend/apps/users/tests/test_consent.py:291-320` — web-side
  `TestLoginStatusNoPii` provides the reference assertion pattern:
  `str(telegram_id) not in caplog.text` + `"tg_" in caplog.text`.
- No technical uncertainty, no multiple viable approaches: the report
  prescribes the exact fix (mirror the existing web-side control).

## Risk Assessment

- **Architectural:** None. Logging-only change; no auth/DB/behavior change.
- **Rollback:** Trivial — revert the commit; no schema migration.
- **Log correlators:** The masked form is stable (same input → same
  `tg_<8-hex>`), so correlation keyed on the masked token is preserved.
  Documented as a known consideration in the report (ADR-03).

## Execution Blocks

### Block 1 — Apply `mask_telegram_id` wrap + caplog regression test (single atomic commit)

Required agents: **Implementor** (single, sequential). No Auditor /
Researcher / Planner required — the task is unambiguous and matches an
existing project convention.

#### task_description

```yaml
id: AUT-001-mask-bot-login-rate-limit
title: Mask Telegram ID in bot login rate-limit warning + add caplog regression
priority: P2
source_reference: .ai/plans/31-auth-login-pii-mask.md
source_section: Block 1

description: >
  The bot login rate-limit-exceeded warning logs the raw Telegram user ID,
  violating the project PII-002 logging control (already mandated by
  docs/01-spec/technical-specification.md:90) and diverging from 10 web-side
  call sites. Apply the existing mask_telegram_id() control and add a
  regression test mirroring the web-side TestLoginStatusNoPii pattern.

goals:
  - No raw Telegram ID in bot login rate-limit warning logs
  - Regression test blocks raw-ID log emission
  - Follow existing web-side mask_telegram_id convention
  - No auth/DB/behavior change

files:
  - path: src/telegram_bot/handlers/login.py
    targets:
      - type: import
        # add after line 23 (apps.core.services.site_config import), before
        # apps.users.models import, per ruff/isort ordering
        statement: from apps.core.utils.sanitize import mask_telegram_id
      - type: function
        name: handle_login_deep_link
    changes:
      - action: replace_in_body
        description: Wrap the rate-limit warning's telegram_id arg with mask_telegram_id
        old:
          |-
          logger.warning(
              "Login rate limit exceeded for telegram_id=%s",
              message.from_user.id,
          )
        new:
          |-
          logger.warning(
              "Login rate limit exceeded for telegram_id=%s",
              mask_telegram_id(message.from_user.id),
          )

  - path: src/telegram_bot/tests/test_login.py
    targets:
      - type: method
        name: test_login_rate_limit_blocks_after_threshold
        class: TestLoginRateLimit
    changes:
      - action: add_caplog_assertion
        description: >
          Add the caplog fixture and assert the raw user id is absent and the
          masked "tg_" token is present — mirroring the web-side
          TestLoginStatusNoPii.test_login_consume_no_raw_telegram_id pattern.
        imports_required:
          - import logging  # for caplog.set_level(logging.WARNING)
        assertion_block:
          |-
            caplog.set_level(logging.WARNING)
            ...
            assert str(blocked_msg.from_user.id) not in caplog.text
            assert "tg_" in caplog.text

acceptance_criteria:
  - login.py imports mask_telegram_id from apps.core.utils.sanitize
  - login.py rate-limit warning passes mask_telegram_id(message.from_user.id)
  - rate-limit test asserts raw id NOT in caplog.text
  - rate-limit test asserts "tg_" present in caplog.text
  - `uv run ruff check src/telegram_bot/handlers/login.py src/telegram_bot/tests/test_login.py` passes
  - `uv run basedpyright src/telegram_bot/handlers/login.py` passes
  - tests pass:
    - `pytest src/telegram_bot/tests/test_login.py::TestLoginRateLimit -x`
      (test DB required — run via docker compose test service)
```

## Verification

- Lint: `uv run ruff check --fix src/telegram_bot/handlers/login.py src/telegram_bot/tests/test_login.py`
- Typecheck: `uv run basedpyright src/telegram_bot/handlers/test_login.py` (login.py has pyright pragma issues pre-existing — do not introduce new ones)
- Test: rate-limit test class via docker compose test service (test DB).
- Commit: `git commit -m "fix(bot): mask telegram_id in login rate-limit warning (AUT-001)"`
