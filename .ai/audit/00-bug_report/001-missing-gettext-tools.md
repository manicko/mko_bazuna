---
id: 001
title: Translation compilation must be performed inside the Docker environment
date: 2026-07-27
author: automated
affected_task: TASK_009 — Create Locale Directory Structure
severity: medium
---

# Translation compilation should run inside Docker

## Description

The current workflow assumes `django-admin compilemessages` is executed directly on
the host machine (for example, via `uv run django-admin compilemessages`).

This is inconsistent with the project's Docker-first development model, where all
management commands are expected to run inside the application container.

Running `compilemessages` on the host introduces an unnecessary dependency on the
host operating system (GNU gettext / `msgfmt`) and makes the development workflow
platform-dependent.

## Impact

- Developers are instructed to install GNU gettext locally even though the project
  already provides a Dockerized development environment.
- Windows, macOS and Linux developers may require different installation steps.
- The development environment becomes less reproducible.
- The command may succeed in CI or Docker while failing on the host, or vice versa,
  leading to inconsistent behavior.

## Expected Behavior

Translation compilation should be executed inside the Docker container, using the
same environment as the application itself.

Example:

```bash
docker compose exec web uv run django-admin compilemessages
```

or

```bash
docker compose exec web python manage.py compilemessages
```

## Required Changes

1. Ensure the application image includes GNU gettext (`msgfmt`).
2. Execute `compilemessages` exclusively inside the `web` container.
3. Update project documentation to use the Docker command instead of invoking
   Django directly on the host.
4. Remove any requirement for developers to install GNU gettext on their local
   machines unless they intentionally run Django outside Docker.

## Benefits

- Single, reproducible development environment.
- No platform-specific setup instructions.
- Consistent behavior between development, CI and production.
- Reduced onboarding complexity for new developers.