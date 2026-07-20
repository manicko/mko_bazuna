# 10 — Code Quality

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify the codebase follows the project's engineering rules: strict type safety,
`StrEnum` for all fixed values, logging instead of `print()`, clean separation of
concerns, small single-responsibility modules, Pydantic at boundaries, English
only, migration discipline, and a single shared business-logic layer for both
processes.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Typing / Type Safety** | Strict hints everywhere; `Any` only where a framework signature forces it; Pydantic v2 DTOs at system boundaries; shared types where processes meet. |
| **Constants / StrEnum** | All fixed values (statuses, sorts, flags, lock IDs, event types) live in `StrEnum` — never raw strings, dicts, or lists. |
| **Logging** | Proper `logging.getLogger(__name__)`; NO `print()` in production code (including entry points). |
| **Separation of Concerns** | Bot handlers and web views are thin adapters that delegate to a shared service/business-logic layer; no ORM/validation/formatting mixed in presentation. |
| **Module Size / SRP** | Small modules and functions; one responsibility per unit; no giant handlers/services mixing ORM + validation + formatting. |
| **Schema / Validation Boundary** | Pydantic v2 validates input at every boundary (bot messages AND web form POST) before any ORM write. |
| **Naming / Conventions / English** | Meaningful consistent names; English-only comments, logs, docstrings, error messages (user-facing localized strings excepted). |
| **Migration Discipline** | Every schema change is versioned via migration; no direct DB mutation in code. |
| **DRY Across Processes** | The two processes (web + bot) share ONE business-logic/service layer; rules are not copy-pasted into handlers. |

## 3. Prerequisites

- Linter and type-checker configured per the project (run across the whole repo).
- Ability to grep the codebase (no `print(`, raw constant literals, `.pyc`/`__pycache__` excluded).
- Test suite runnable to confirm it passes (prod-code-king: a failing test that forces prod distortion is a phase-11 issue; note only if it would distort prod).
- No code modification — audit only.

## 4. Runtime / Static Verification (mandatory)

Execute, then capture evidence (tool output, grep hits, line counts):

1. **Static tools** — run linter + type-checker (strict) across the repo → capture all violations.
2. **No print()** — grep production code for `print(` → assert none (entry points included).
3. **StrEnum audit** — grep for raw string/dict/list literals used as fixed values (statuses, sorts, flags) → assert they are `StrEnum`; flag any place using a raw string where an enum exists.
4. **Logging** — confirm every module uses the logger, not `print`.
5. **SoC review** — inspect web views + bot handlers → assert no business logic / ORM / validation embedded; logic delegated to the shared service layer.
6. **Module/function size** — measure sizes → flag oversized modules/functions mixing concerns.
7. **Pydantic at boundaries** — assert bot input AND web POST validated via Pydantic before ORM writes; shared types where applicable.
8. **English-only** — scan comments/logs/errors for non-English in non-user-facing strings.
9. **Migration discipline** — confirm every schema change has a migration; no code-path DB mutation.
10. **DRY across processes** — confirm shared rules (e.g. contact-gating conditions, analytics recording) live in ONE place, not duplicated in both handlers.

## 5. Audit Dimensions (checks + evidence)

### (a) Type safety — HIGH
No `Any` masking real issues; strict hints; Pydantic at boundaries; shared types.
- Evidence: type-checker clean except framework-forced `Any` (documented); Pydantic DTOs present at all boundaries.

### (b) StrEnum for all constants — HIGH
Fixed values are `StrEnum`, never raw strings/dicts/lists; no drift (raw string where enum exists).
- Evidence: grep shows no raw constant literals in constant-like contexts; single source per fixed value.

### (c) Logging not print — HIGH
No `print()` anywhere in production code.
- Evidence: grep clean; logger used uniformly.

### (d) Separation of concerns — HIGH
Logic out of views/handlers/templates; shared service layer is the single source.
- Evidence: review shows delegation; no ORM/validation/formatting in presentation layer.

### (e) Module/function size + SRP — MEDIUM
Small, focused units; no giant modules mixing responsibilities.
- Evidence: measured sizes within target; single responsibility per module/function.

### (f) Schema/validation at boundaries — MEDIUM
Pydantic v2 at bot + web boundaries; invalid data rejected before ORM.
- Evidence: DTOs present; web POST validated (not parsed raw then written).

### (g) Naming + conventions + English-only — MEDIUM
Consistent meaningful naming; English in code/comments/logs/errors.
- Evidence: scan shows English-only non-user-facing strings; consistent naming.

### (h) Migration discipline — HIGH
Schema changes via migrations; no code-path DB mutation.
- Evidence: every model change has a migration; CI would catch drift.

### (i) No duplicated logic across processes — MEDIUM
Shared rules in one service layer; not copy-pasted into bot + web handlers.
- Evidence: same rule implemented once; handlers delegate.

## 6. Cross-Cutting (owned here, not duplicated)
- **Shared business-logic layer** is the seam between the two processes — duplication here is the core code-quality risk.
- **Settings/configuration module** must use `StrEnum` + Pydantic, never raw strings.
- **Type safety at the async/sync boundary** (phase 09) is partly a typing concern owned here.

## 7. Edge Cases
- A fixed value added as raw string in one place but `StrEnum` elsewhere → drift risk.
- A new schema field without a migration → caught by CI? verify.
- Business logic copy-pasted into a bot handler "for convenience".
- A large function mixing ORM + validation + formatting.
- `print()` hidden behind a debug flag in prod.
- `Any` used to "make the type-checker pass", masking real issues.
- English comment but non-English log/error message.
- Test-only code that distorts production patterns.

## 8. Severity Taxonomy

- **HIGH**
  - `print()` in production code path.
  - Pervasive `Any` losing type safety.
  - Business logic entangled in views/handlers (untestable).
  - Fixed values as raw strings/dicts instead of `StrEnum` (real bug/drift risk).
  - Missing migration for a schema change.
- **MEDIUM**
  - Oversized modules/functions hurting maintainability.
  - Duplicated service logic across the two processes.
  - Pydantic not used at a boundary (invalid data reaches ORM).
  - Inconsistent naming/conventions.
  - English-only violated in user-facing/error strings.
- **LOW**
  - Missing type hints on internal helpers.
  - Logging verbosity.
  - Minor convention drift.
  - No shared type definitions yet (future improvement).

## 9. Recommended Sequence
1. Static checks first: lint, type-check, `print()` grep, `StrEnum` grep.
2. Structural review of layering (handlers/views delegate; logic in service layer).
3. Module/function size + SRP.
4. Conventions, English-only, migrations, DRY.

## 10. Finding Prefix
Use `QLT-` for all findings in this phase.

## 11. Reporting
- `problems-only: true`.
- Each finding: severity, zone, evidence (path/line/tool output/grep hit), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.
