---
id: ast-editor
domain: reference
tags:
  - tools
  - ast-editor
  - code-editing
related:
  - doc-maintenance-rules
  - morfx-tools
---

# ast-editor — Quick Reference

**Target format:** `ClassName.method` for methods, bare name for top-level functions. Case-sensitive.
**Always run first:** `list_symbols` to discover exact names.
**Always run after editing:** `uv run ruff check <file>` and `uv run basedpyright <file>`

---

## Critical Rules

### Do not manually adjust indentation levels for base or class level always

- Decorator lines starts at 0
- def` starts at  0 no leading spaces before `def`
- Body uses 4 spaces per indentation level

### Pre-edit checklist

Before editing any Python file:
1. Run `read_symbol` to discover exact target name and current indentation
2. For `replace_in_body`: copy EXACT whitespace from the file (including blank lines)
3. For `replace_function`: verify indentation level matches the target's actual level

### Post-edit checklist

After EVERY edit:
1. Run `uv run ruff check <file>` immediately
2. Run `uv run basedpyright <file>` to verify type hints
3. If ruff reports E111/E112/E113/E114/E117 (indentation errors): fix before proceeding
4. If tests fail due to your changes: fix before proceeding
