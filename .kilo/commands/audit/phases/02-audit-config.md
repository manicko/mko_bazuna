---
name: 02-config
status: complete
validated: no
executor: auditor
problems-only: true
---

# Phase 02 Audit — Configuration & Settings Models

## Purpose

This is a **reusable, system-agnostic handbook** for auditing how an application
defines, loads, validates, and consumes its configuration and settings models. It
is not tied to a specific schema library, file format, or framework. Apply the
discovery steps and audit dimensions to whatever configuration mechanism the
system actually uses (typed settings models, env files, structured config files,
etc.), adapting concrete names to the implementation at hand.

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- **Do NOT** write sections that say "X is correct" or "no issues found in Y".
- **Do NOT** include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: it describes a real problem, its evidence (code/logs/output), and its impact.

---

## Discovery Stage

Before performing audit checks, discover the configuration architecture:

1. **Config Model Discovery** — Locate all settings/model classes (typed config models). Map the model hierarchy (root model → sub-models). Identify all fields, their types, defaults, and validators.
2. **Config Loading Discovery** — Find where config is read from its source (file, env, remote), where validation happens, and where the loaded config lives (package templates vs user/runtime directory).
3. **Path Resolution Discovery** — Map how the system resolves paths (application base paths, user data directory, platform-specific directories). Identify where user config lives vs package templates.
4. **Config Flow Discovery** — Trace how a config value travels from source → model → consumer function. Identify every consumer of config values.

---

## Mandatory Runtime Verification

**Before evaluating any checklist item, you MUST complete these steps. Use the commands provided in the project's commands file. Skip only if a step is impossible — document why.**

### Step R1 — Import and Instantiate Models

Attempt to import all config models. Instantiate the root model with valid and invalid data.

- Verify validators fire correctly on invalid data.
- Verify defaults are applied correctly.
- Capture any validation errors — they are evidence.

### Step R2 — Config Loading Verification

If a sample/test config file exists, attempt to load it through the config reader.

- Verify the loaded model matches the file contents.
- Verify relative paths are resolved correctly.
- Test with missing/invalid config — verify clear error messages.

### Step R3 — Linter and Type Checker

Run the project's configured linter and type checker commands.

- Record exit codes and output.

### Step R4 — Run Test Suite

Run the project's test suite, focusing on config-related tests.

- Record pass/fail counts and failure output.

---

## Audit Scope

Settings models, config file loading, path resolution, config validation, init/scaffold service (template copying), config file templates.

---

## Audit Dimensions

### 1. Config Model Correctness

| Check | Description |
|-------|-------------|
| Every config section modeled | Each logical configuration section has a corresponding typed model. |
| No raw dicts in business logic | Services receive typed models, not raw parsed structures (e.g., raw dict from a YAML/JSON load). |
| Field validation | Required fields have no defaults; optional fields have sensible defaults. Constraints are appropriate. |
| Custom validators | Domain-specific validation (e.g., identifier formats) uses the model's validator mechanism. |
| Enum for fixed values | Fixed-value fields (statuses, types, modes) use enums, not plain strings or magic constants. |
| Unknown-key rejection on root model | The root settings model rejects unknown keys to catch typos in config. |

**Evidence required:** Read each model class. Verify field types and validators. Search for raw parsed-structure usage in service code.

### 2. Config Loading & Path Resolution

| Check | Description |
|-------|-------------|
| User config separated from package templates | Config is read from the user/runtime data directory, never from the package's own template directory. |
| Path resolution is consistent | All relative paths in config resolve against the user/runtime directory using the project's path utilities. |
| Missing config produces clear error | When the config file is missing, the error message tells the user how to create it. |
| Config reader validates on load | The loader validates through the typed model, not just parsing the source format. |

**Evidence required:** Read the config reader and path utilities. Trace the full path from source file to typed model in a service.

### 3. Init / Scaffold Service Correctness

| Check | Description |
|-------|-------------|
| Templates copied correctly | The init/scaffold function copies from package templates to the user/runtime config directory. |
| Overwrite flag works | With the force/overwrite flag, existing files are replaced. Without it, existing files are preserved. |
| No cross-package imports | The init service does not import from unrelated packages. |
| Return value is useful | The function returns the path to the created config directory or equivalent. |

**Evidence required:** Read the init service. Verify the source and destination paths. Check for any hardcoded paths.

### 4. Config Template Quality

| Check | Description |
|-------|-------------|
| Example config matches model | The config template matches the typed model structure exactly. |
| All fields documented | Every field in the example config has a comment explaining its purpose. |
| No real credentials in templates | Template files contain only placeholder values, no real API keys or tokens. |

**Evidence required:** Compare the template against the typed models. Check for mismatched field names or missing sections.

### 5. Config-to-Service Flow

| Check | Description |
|-------|-------------|
| Config reaches every consumer | Trace each config section from source → model → consumer function. Every section is consumed somewhere. |
| No unused config fields | Every field in the model is actually used by some service. |
| No missing config fields | Every parameter that should come from config does come from config (not hardcoded). |

**Evidence required:** For each model field, find at least one usage in service code. For each service parameter, verify it comes from config.

---

## Report Output

Write findings to: `.ai/audit/02-config/findings.md` using template `.ai/audit/templates/audit-findings.md`.

**Write the file incrementally — append blocks of ≤100 lines each. Never write the entire report in a single call.**

Use prefix `CFG-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is correct.
- If after completing all Runtime Verification steps and all Audit Dimensions, no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — model instantiation errors, config loading failures, path resolution bugs, test failures.
  2. **Not just:** "violates invariant X" — show the exact model/field/code that violates it and the exact consequence.
