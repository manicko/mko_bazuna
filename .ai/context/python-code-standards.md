---
name: python-code-standards
globs: "**/*.{py}"
alwaysApply: true
description: Standards for writing clean, maintainable Python code following Clean Architecture and strong modularity
---

- Follow **Clean Architecture** with clear separation between domain, application, and infrastructure layers
- Enforce **strict separation of concerns** and strong modularity (feature/domain-based structure preferred)
- Use **static typing** — type hints required everywhere
- Prefer **explicitness** over cleverness
- Use **Pydantic** for all data models and validation
- Prefer `Enum` / `StrEnum` over raw strings, dicts, or lists for fixed value sets
- Keep modules small and focused on a single responsibility
- Prefer composition over inheritance
- Avoid overengineering
- All comments and log messages must be in **English**
- Write logs with meaningful context (no generic messages)
- Comment only non-trivial logic; avoid obvious or redundant comments
