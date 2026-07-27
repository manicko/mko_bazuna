---
id: 001
title: Missing GNU gettext tools (msgfmt) on Windows development environment
date: 2026-07-27
author: automated
affected_task: TASK_009 — Create Locale Directory Structure
---

# Missing GNU gettext tools (msgfmt) on Windows development environment

## Description

`django-admin compilemessages` requires `msgfmt` from GNU gettext tools (>=0.19).
The tool is not installed on the Windows development machine, preventing compilation
of `.po` files into `.mo` files.

## Impact

- `uv run django-admin compilemessages` fails with: `CommandError: Can't find msgfmt. Make sure you have GNU gettext tools 0.19 or newer installed.`
- `.mo` binary files cannot be generated from `.po` source files.
- Django i18n will not function at runtime without `.mo` files.

## Recommended Fix

Install GNU gettext tools on the development machine:

**Option 1 — Chocolatey:**
```
choco install gettext
```

**Option 2 — MSYS2:**
```
pacman -S mingw-w64-x86_64-gettext
```

**Option 3 — Manual:**
Download from https://mlocati.github.io/articles/gettext-iconv-windows.html and
add the `bin/` directory to `PATH`.

After installation, verify with:
```
msgfmt --version
```

Then re-run:
```
uv run django-admin compilemessages
```