# Specification: Apply Design System — Fix Stale Tailwind CSS Build

**File:** `07_design-system-css-pipeline_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-06
**Source Decision:** `.ai/problems/Decision_08.md`
**Research:** `ses_02c3297ceffe2T7IJG6z9JKs6t` (tailwind v3/v4 build pipeline, output.css class coverage, prose/plugin constraints)

---

## 1. Problem Statement

`Decision_08.md` reports the site has "no CSS styles at all" and asks to apply the design system for 2026. Investigation reframes the problem: the design-system docs (`docs/01-spec/design-system.md` + `docs/06-design-system/*`) and the templates are already aligned — the templates reference the design-system utility classes (e.g. `text-blue-600`, `rounded-lg`, `shadow-sm`, `bg-gray-50`, `object-cover`, `line-clamp-2`). The blocker is a stale compiled stylesheet:

- `src/theme/static/theme/css/output.css` (committed, 8,935 chars, 82 selectors) is missing ~209 utility classes the templates reference — e.g. `text-blue-600` (0), `bg-blue-600` (0), `rounded-lg` (0), `shadow-sm` (0), `bg-gray-50` (0), `bg-white` (0), `border-gray-300` (0).
- Root cause: `input.css` and `tailwind.config.js` use **Tailwind v3 syntax** (`@tailwind base/components/utilities` + a `content[]` key), but the project ships the **v4.3.3 standalone CLI** (`docker/Dockerfile` lines 42–44). In v4, `@tailwind` directives generate only a minimal fixed utility set and the `content` key in `tailwind.config.js` is **ignored** — content scanning requires v4-native `@source` at-rules in the CSS input.
- A v4-native build produces 291 selectors covering every template class (verified experimentally).

So the site is not unstyled because there is no framework — it ships Tailwind, but the build is misconfigured and the committed `output.css` was generated with v3 syntax under a v4 CLI.

## 2. Confirmed Requirements

- **R1** — `output.css` must contain every utility class referenced by the 16 templates (verified: a v4-native build yields 291 selectors with full coverage).
- **R2** — Must ship Tailwind v4-native build config (`@import "tailwindcss"` + `@source`), replacing the v3 directives.
- **R3** — Must NOT introduce Node.js / npm toolchain (`docs/03-packages/packages-list.md`: "NO Node.js"; standalone CLI only).
- **R4** — Must NOT add `@tailwindcss/typography` / plugins — the standalone CLI has no plugin support (`packages-list.md` line 87: "standalone has no plugin support"; daisyUI "EXCLUDED"). The `prose` class in `ads/detail.html` must be replaced with utility classes.
- **R5** — No template rewrites required for styling (templates already conform to `docs/01-spec/design-system.md`). Only the `prose` wrapper is removed (Task 4).
- **R6** — Build must work in both the Docker prod image build and the dev compose startup (the established regeneration mechanism).

## 3. Conceptual Development Tasks

### Task 1 — Migrate `input.css` to Tailwind v4-native syntax
**Purpose:** Enable content-based class extraction under the v4 standalone CLI.

- File: `src/theme/static/theme/css/input.css`
- Replace the v3 directives with v4-native syntax:
  ```css
  /* Tailwind input stylesheet */
  @source "src/backend/templates/**/*.html";
  @import "tailwindcss";
  ```

### Task 2 — Remove / neutralize v3-only `tailwind.config.js`
**Purpose:** v4 ignores `content`, `theme.extend`, and `plugins`; under the standalone CLI (invoked with no `--config`) the file is dead weight.

- File: `tailwind.config.js`
- Decision Q1 (PO) resolves: **delete** (recommended — no custom theme), or empty to `{}` with a comment.
- Note: `django-tailwind` template tags are NOT used anywhere (grep-verified; templates include CSS via `{% static 'theme/css/output.css' %}`), so the config is not read by Django at runtime.

### Task 3 — Regenerate `output.css`
**Purpose:** Produce a class-complete stylesheet.

- Production: the `Dockerfile` builder stage already runs `tailwindcss -i src/theme/static/theme/css/input.css -o src/theme/static/theme/css/output.css --minify` (line 66) before `collectstatic`. After Tasks 1–2, the rebuilt image produces the correct file.
- Development / manual: `docker compose exec web tailwindcss -i src/theme/static/theme/css/input.css -o src/theme/static/theme/css/output.css --minify` (also documented in `README.md` line 40).
- **Must run BEFORE any template edits and AGAIN after any class changes**, to guarantee coverage (see Risks).

### Task 4 — Replace the `prose` wrapper in `ads/detail.html`
**Purpose:** Remove the `@tailwindcss/typography`-only `prose` class (plugin unavailable under the no-Node / no-plugin constraint).

- File: `src/backend/templates/ads/detail.html` line 54
- Current:
  ```html
  <div class="prose max-w-none mb-6">
      <p class="text-gray-700 whitespace-pre-wrap">{{ ad|get_description:LANGUAGE_CODE }}</p>
  </div>
  ```
- Replace with a utility-only wrapper consistent with `docs/01-spec/design-system.md`:
  ```html
  <div class="mb-6">
      <p class="text-gray-700 whitespace-pre-wrap">{{ ad|get_description:LANGUAGE_CODE }}</p>
  </div>
  ```
- The description is plain text (XSS-safe autoescape, `whitespace-pre-wrap`) — no rich markup requires typography styling.

## 4. Product Owner Decisions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Handling of `tailwind.config.js` | **(A) Delete** — no custom theme; standalone CLI does not read it; django-tailwind tags unused. (Default recommendation.) |
| Q2 | Regenerate locally vs Docker-only | **(B) Docker-only** — the local `.venv/Scripts/tailwindcss.exe` is a non-functional stub and there is no Node toolchain. Use `docker compose exec web tailwindcss …`. (Default.) |
| Q3 | `prose` / rich-text description styling | **(A) Utility-only** — `@tailwindcss/typography` is unavailable (no plugin support). Replace the `prose` wrapper with a utility `<div>`. A hand-written `.prose` CSS file is an optional future enhancement only if rich-text ad descriptions are ever introduced. |

## 5. Research Summary

### Researcher session `ses_02c3297ceffe2T7IJG6z9JKs6t`

**Root-cause experiments (verified by actual builds):**
- v3 `input.css` (`@tailwind base/components/utilities`) + `tailwind.config.js` `content[]` + standalone CLI v4.3.3 → **8,935 chars / 82 selectors** — byte-identical to the committed `output.css`; `text-blue-600`, `bg-blue-600`, `rounded-lg`, `shadow-sm`, `bg-gray-50`, `border-gray-300`, `bg-white` all = **0** occurrences.
- v4-native `input.css` (`@import "tailwindcss"` + `@source "src/backend/templates/**/*.html"`) → **29,101 chars / 291 selectors**, with every template class present (`bg-blue-600` ✓, `text-blue-600` ✓, `rounded-lg` ✓, `shadow-sm` ✓, `bg-gray-50` ✓, `border-gray-300` ✓, `bg-white` ✓, `px-4` ✓, `py-4` ✓).
- In v4, `@tailwind` directives produce ONLY base utilities; the `content` key in `tailwind.config.js` is **ignored**. Only `@source` at-rules drive class extraction.

**Constraints (authoritative, from `docs/03-packages/packages-list.md`):**
- Line 46: `django-tailwind>=4.4.0` — "Tailwind standalone CLI (NO Node.js)."
- Line 87: "django-tailwind ≥4.4.0 — daisyUI excluded (standalone has no plugin support)."
- Line 98: "django-tailwind without daisyUI — MEDIUM — Plain Tailwind suffices for MVP."
- → `@tailwindcss/typography` is NOT an option; the `prose` class must be replaced by utilities.

**Build locations (authoritative):**
- `docker/Dockerfile` lines 42–44: downloads the standalone CLI (latest stable at build time).
- `docker/Dockerfile` line 66: `RUN tailwindcss -i src/theme/static/theme/css/input.css -o src/theme/static/theme/css/output.css --minify && uv run python src/backend/manage.py collectstatic --noinput` (prod image build).
- `docker-compose.dev.override.yml` lines 8–9: same command on dev container start.
- `README.md` lines 29–41: documents the manual rebuild command for template edits.
- `src/backend/config/settings/base.py` lines 174–176: `STATIC_ROOT = <root>/staticfiles`; `STATICFILES_DIRS` includes `src/theme/static` (where `output.css` is generated).

**Templates:** 8 full-page templates include `{% static 'theme/css/output.css' %}` (verified); 16 templates total under `src/backend/templates/`. The `prose` class appears only in `ads/detail.html:54`.

## 6. Assumptions

1. Templates already conform to `docs/01-spec/design-system.md` (verified via `ads/detail.html`).
2. The ad description is plain text, not rich HTML (`whitespace-pre-wrap` on a single `<p>`), so removing the `prose` wrapper is safe.
3. No custom theme tokens from `docs/06-design-system/tokens.md` are wired into the build (`tailwind.config.js` `theme.extend` is empty); the default Tailwind palette is the intended styling basis.
4. Local Windows dev has no functional Tailwind CLI; Docker is the canonical regeneration path.

## 7. Constraints

1. No Node.js / npm toolchain (`packages-list.md`).
2. Standalone CLI has no plugin support — `@tailwindcss/typography` and daisyUI are excluded.
3. Docker is the only working CSS regeneration path on the dev machine.
4. `input.css` and `output.css` live in `src/theme/static/theme/css/`.
5. `output.css` is a committed artifact (not gitignored).
6. Python 3.14 · Django 5.2 LTS · PostgreSQL 18.

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Editing template utility classes BEFORE regenerating `output.css` → classes referenced in templates but absent from the stylesheet → broken/strip rendering | High | High | SEQUENCE strictly: (1) migrate `input.css` → (2) regenerate `output.css` → (3) any template edits → (4) regenerate again. |
| v4-native `@source` glob misses a template path → a class used in an uncovered file is purged from `output.css` | Medium | Medium | Glob `src/backend/templates/**/*.html` covers all 16 templates. After regeneration, verify representative classes from each template appear in `output.css` (reuse the researcher's class-count checklist). |
| Deleting `tailwind.config.js` breaks the app at runtime | Low | Low | `django-tailwind` template tags are not used (grep-verified); templates load CSS via `{% static %}`. The config is not read at runtime. |
| Removing `prose` changes description rendering for buyers | Low | Low | The `<p class="text-gray-700 whitespace-pre-wrap">` is preserved; only the outer `prose max-w-none` wrapper changes to `mb-6` (same bottom margin as before). |
| Custom theme tokens (`docs/06-design-system/tokens.md`) diverge from the default palette in future | Medium | Future | Out of scope (Task 2 default = delete config). Track as a separate enhancement if a branded palette is ever required. |

## 9. Open Questions

None. The "no Node.js / no plugin support" constraint from `docs/03-packages/packages-list.md` resolves the `prose`/typography decision (Q3) without Product Owner input, and the build-pipeline fix is fully determined by the v3→v4 root cause.

## 10. Out of Scope

1. Custom theme / token theming from `docs/06-design-system/tokens.md` (CSS custom properties, non-default palette) — a separate enhancement; current templates use default Tailwind classes.
2. Template rewrites to match the design system — templates already conform (only the `prose` removal in Task 4).
3. Adding `@tailwindcss/typography` or any Node-based PostCSS pipeline (constraint).
4. Bootstrapping a local Windows Tailwind CLI from the `.venv/Scripts/tailwindcss.exe` stub — dev uses Docker.

## 11. Definition of Ready

This specification is ready for implementation planning when:

1. ✅ Root cause verified (v3 syntax under v4 CLI) via reproducible build experiments.
2. ✅ Constraints confirmed (no Node, no plugins) via `packages-list.md`.
3. ✅ Fix sequencing defined (migrate input.css → regenerate output.css → template edits → regenerate).
4. ✅ All PO decisions (Q1–Q3) captured with defaults.
5. ✅ Risks and mitigations documented.
6. ✅ Conceptual tasks are independent and acceptance-testable (class-coverage check on the regenerated `output.css`).

## Appendix — Acceptance: class-coverage check

After Task 3, regenerate `output.css` then confirm a non-zero count for each of these classes in `src/theme/static/theme/css/output.css` (representative of the design-system palette used across templates):

`bg-blue-600`, `text-blue-600`, `hover:bg-blue-700`, `rounded-lg`, `shadow-sm`, `shadow`, `bg-gray-50`, `bg-white`, `border-gray-300`, `text-gray-700`, `text-gray-600`, `text-gray-800`, `object-cover`, `line-clamp-2`, `line-clamp-3`, `container`, `min-h-screen`, `divide-y`. (Under the v4-native build all are present; under the stale v3 build most are 0.)
