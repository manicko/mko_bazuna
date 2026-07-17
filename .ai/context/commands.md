# Project Commands

## Environment

- **OS:** Windows
- **Package manager (Python):** uv
---

---

## Python (backend) — use `uv run` for all commands

| Task | Command |
|------|---------|
| Run tests | `uv run pytest <path>` |
| Lint (ruff check) | `uv run ruff check <path>` |
| Format (ruff format) | `uv run ruff format --check <path>` |
| Type check (mypy) | `uv run mypy <path>` |
| Type check (basedpyright) | `uv run basedpyright <path>` |
| Add dependency | `uv add <package>` |
| Add dev dependency | `uv add --dev <package>` |

---