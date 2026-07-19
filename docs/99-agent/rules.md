---
id: rules
domain: agent
tags:
  - rules
related:
  - architecture
  - references
---

## Purpose

This file contains coding standards and rules for the Mko Bazuna project.

## Rules

### Quality & Maintenance

- **Type safety:** Type hints on all public functions. Use strict typing throughout.
- **Logging:** `logger = logging.getLogger(__name__)` — never `print()`.
- **Error handling:** Custom exceptions from `core/errors.py`. Never silently swallow errors.
- **Cleanup:** Clean up temp files with `try/finally` — never leave orphaned cache files.
- **English only:** English only in code, comments, logs.
- **Production code is king:** If tests conflict with architecture/business logic, fix or remove tests; never distort production code for tests.
- **Audit reports:** Write audit reports incrementally — append blocks of ≤100 lines per tool call.

### Coding Standards

- **Indentation:** 4-space indentation, never tabs.
- **Code review:** Read full function/class before rewriting.
- **Linting:** After edits run `uv run ruff check <path>` and `uv run basedpyright <path>`.