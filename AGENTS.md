---
name: Agent Guidelines
description: Mandatory rules and context for the project
alwaysApply: true
---

# Agent Guidelines

CLI tool **Telegram classified monitor** designed to track messages with customizable **keyword filters**, automatically **forward** relevant posts, and include **source links** and **sender usernames** when availabl

## Commands

| Task | Command |
|------|---------|
| Test | `uv run pytest <path>` |
| Lint | `uv run ruff check <path>` |
| Type check (mypy) | `uv run mypy <path>` |
| Type check (basedpyright) | `uv run basedpyright <path>` |
| Add dependency | `uv add <package>` |

## Architecture

- **Fixed values**: `StrEnum` only — never plain strings, dicts, or lists for constants.
- **Small modules and functions** — short, focused files and functions give higher ROI in maintenance; easier to edit, review, and less prone to corruption.

## Rules

- Type hints on all public functions. `logger = logging.getLogger(__name__)` — never `print()`.
- `console.print()` (Rich) for CLI output in `cli.py` only.
- Use custom exceptions from `core/errors.py`. Never silently swallow errors.
- Clean up temp files with `try/finally` — never leave orphaned cache files.
- English only in code, comments, logs.
- **Production code is king** — if tests conflict with architecture or business logic, fix or remove the tests. Never distort production code for tests. Only fix the code when tests reveal an actual bug in the logic.
- **Write audit reports incrementally** — append blocks of ≤100 lines per tool call. Never buffer the entire report and write it in one shot; this causes an upstream idle timeout.
- Before editing documents read `\docs\99-reference\ast-editor.md`  to use appropriate tool

## Indentation

This project uses **4 spaces** — never tabs. When editing, read the full function/class and rewrite it entirely — never patch nested blocks in place. Never reindent surrounding code. After every edit, run `uv run ruff check <path>` and `uv run basedpyright <path>` and fix any reported issues immediately — do not assume the model got it right.

## References

- [Project structure](.ai/structure/map.md)
- [Full structure + dependencies](.ai/structure/**)
- [Specification](docs/SPEC.md)
- [Readme](README.md)
- [Commands](.ai/context/commands.md)
- [Python code standards](.ai/context/python-code-standards.md)
