---
id: doc-maintenance-rules
domain: overview
tags:
  - documentation
  - governance
  - rules
related:
  - technical-specification
---

## Purpose

Mandatory reference for agents and guidance for humans when creating, updating, or splitting documentation. Read this before any task that modifies files under `docs/`.

## Main Concepts

- **Single source of truth:** Each fact lives in exactly one file.
- **Translate on touch:** All docs are English-only.
- **No silent dropping:** Unclear content goes to `docs/.tmp/`.
- **Frontmatter is contract:** Every domain doc starts with YAML frontmatter.

## Update Triggers

Update docs for:
- New features (new endpoints, components, modules)
- API changes (request/response format, status codes)
- Schema changes (new tables, columns, enums)
- Security changes (auth flow, access control, rate limits)

Do NOT update for:
- Minor refactoring
- Bug fixes
- Cosmetic changes
- Code comments

## File Placement Rules

- Numbered prefixes: `00-overview/`, `01-auth/`, `02-dashboards/`, etc.
- Flat structure preferred; max depth 2 levels.
- Group related docs by number prefix and domain folder.
- Use `98-reference/` for guides and external docs.

## Naming Conventions

- Use `kebab-case` for all filenames.
- Lowercase only; numbers for ordering.
- Specific names at deeper levels (e.g., `schema-core.md`).
- Avoid generic names like `misc.md` or `notes.md`.

## Frontmatter Requirements

Every domain doc starts with YAML frontmatter:

```yaml
---
id: unique-identifier
domain: folder-name
tags:
  - relevant-tag-1
  - relevant-tag-2
related:
  - related-doc-id
---
```

Required fields: `id`, `domain`, `tags`, `related`.

## Content Quality Rules

- Every doc must have `## Purpose` section.
- Include `## Main Concepts` when applicable.
- Omit empty sections; mark TODOs in `docs/.tmp/`.
- Use tables for structured data.
- Link to relevant files using relative paths.

## Cross-Linking Strategy

- Reference SSOT (single source of truth) documents.
- Use relative paths: `[Text](../01-auth/auth-api.md)`.
- Include summary + cross-link rather than full copy.
- Verify all links are valid before commit.

## Doc Splitting Threshold

- **Soft threshold:** 800 lines — consider splitting.
- **Hard threshold:** 1000 lines — must split.
- Split at `##` boundaries into logical sections.
- Create new file in same domain folder.
- Update cross-links and related references.

## Translation Rules

- All documentation must be in English.
- No separate translation pass; translate during edits.
- Do not commit non-English content.
- Temporary uncertain content goes to `docs/.tmp/`.

## Output Guidelines

- Use `logger = logging.getLogger(__name__)` for all service layer output in `core/`
- Use `console.print()` (Rich) for CLI user-facing output in `app.py`
- Use `rich.progress.track()` for terminal progress bars — never use `print()` with `\r` manipulation
- Progress bars and user interaction belong to the CLI layer, not business logic

## Agent Enforcement

Agents must:
- Read this file before modifying any `docs/` content.
- Verify frontmatter on all new/modified docs.
- Check for English-only text.
- Ensure cross-links use relative paths.
- Validate line count against splitting threshold.

## Checklist Templates

### New Feature

- [ ] Created new doc with frontmatter
- [ ] Added to `## Related Docs` in parent docs
- [ ] Linked from relevant existing docs
- [ ] Purpose and Main Concepts sections included
- [ ] Cross-links use relative paths

### API Change

- [ ] Updated endpoint documentation
- [ ] Updated request/response examples
- [ ] Updated status codes if changed
- [ ] Updated cross-linked docs
- [ ] Verified all examples compile/run

### Schema Change

- [ ] Updated table/column definitions
- [ ] Updated enum values
- [ ] Updated relationships and constraints
- [ ] Updated `schema-core.md` if core change
- [ ] Added migration notes if required

### Doc Splitting

- [ ] Identified natural break at `##` boundary
- [ ] Created new file with proper frontmatter
- [ ] Moved content preserving structure
- [ ] Updated cross-links in both files
- [ ] Updated `related` arrays in frontmatter