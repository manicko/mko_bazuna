---
name: 04-security
status: complete
validated: no
executor: auditor
problems-only: true
---

# Phase 04 Audit — Security & Secret Management

## Purpose

This is a **reusable, system-agnostic handbook** for auditing the security surface
of ANY application: secret management, credential file handling, logging hygiene,
config security, and input validation. It is not tied to a specific external
service, auth scheme, or credential format. Apply the discovery steps and audit
dimensions to whatever secretes and sensitive inputs the system actually has,
adapting concrete names to the implementation at hand.

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- **Do NOT** write sections that say "X is correct" or "no issues found in Y".
- **Do NOT** include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: it describes a real problem, its evidence (code/logs/output), and its impact.

---

## Discovery Stage

Before performing audit checks, discover the security surface:

1. **Secret Discovery** — Identify all secrets and sensitive values: API keys, tokens, passwords, private keys, session/identity names. Map where each is stored and how it flows through the code.
2. **Credential File Discovery** — Locate any credential/session/identity files. Check where they are stored, how they are created, who has access.
3. **Logging Discovery** — Search all logging calls. Identify any that might log sensitive data (tokens, keys, credentials, paths to secrets).
4. **Config Security Discovery** — Check how secrets are loaded: from config files, environment variables, or hardcoded. Verify config file permissions and ignore-file coverage.
5. **Input Validation Discovery** — Identify all external inputs: config values, names/identifiers, file paths. Check for path traversal or other input attacks.

---

## Mandatory Runtime Verification

**Before evaluating any checklist item, you MUST complete these steps. Use the commands provided in the project's commands file. Skip only if a step is impossible — document why.**

### Step R1 — Credential Leak Search

Search the entire codebase for hardcoded secrets: API keys, tokens, passwords, private keys.

- For each match, determine if it is: a hardcoded value (CRITICAL), an environment-variable reference (OK), a placeholder/default (OK if clearly marked), or a test fixture (verify it's not a real value).
- Check ignore-protected env/secret files: if committed with real values, that is CRITICAL.
- Check config templates for real credentials.

### Step R2 — Logger Audit

Search all logging calls for potential secret leakage:

- Any logger call that includes a variable containing a secret, token, key, or credential path is CRITICAL.
- Any logger call that dumps an entire config model (which may contain secrets) is a finding.

### Step R3 — File Permission Check

Check the permissions and ignore-file status of sensitive files:

- Credential/session/identity files — are they in the ignore file?
- Config directory — does it have appropriate permissions (owner-readable only)?

### Step R4 — Import Verification

Import all modules that handle secrets. Verify no import-time side effects leak credentials.

### Step R5 — Linter and Type Checker

Run the project's configured linter and type checker commands.

- Record exit codes and output.

### Step R6 — Run Test Suite

Run the project's test suite.

- Record pass/fail counts and failure output.

---

## Audit Scope

Secret management, credential/session file handling, logging security, config security, input validation, path traversal prevention.

---

## Audit Dimensions

### 1. Hardcoded Secrets

| Check | Description |
|-------|-------------|
| No hardcoded API keys | Credentials come from config, never from source code. |
| No hardcoded session/identity names | Session/identity file name comes from config, not hardcoded values. |
| Test fixtures use fake values | Test mocks use obviously fake values, not real credentials. |

**Evidence required:** Grep results for hardcoded values. Read config loading code. Read test fixtures.

### 2. Credential / Session File Security

| Check | Description |
|-------|-------------|
| Files in user directory | Credential/session/identity files are stored in the user/runtime data directory, not in the package directory. |
| Files in ignore file | Credential/session/identity files are covered by the ignore file. |
| No secrets in config templates | Config templates contain only placeholder values. |
| File contents never logged | The path to a credential file may be logged, but its contents are never logged. |

**Evidence required:** Read the ignore file. Read config templates. Check file paths in code.

### 3. Logging Security

| Check | Description |
|-------|-------------|
| Secrets never logged | Keys, tokens, passwords, session content are never passed to any logger call. |
| Config models not dumped | Entire typed config models are not logged (they may contain secrets). |
| Error messages don't leak secrets | Exception messages and error responses don't include credential values. |
| File paths to secrets are OK | Logging the *path* to a credentials file is acceptable; logging the *contents* is not. |

**Evidence required:** Read all logger calls. Search for any logger call near credential-handling code.

### 4. Config Security

| Check | Description |
|-------|-------------|
| Secrets loaded from a protected location | Credentials are loaded from the user's private config directory / a secret store, not from broadly-exposed environment variables where avoidable. |
| Config validation rejects empty secrets | Validators reject empty or obviously invalid credential values. |
| Production config is separate | User config is separate from package templates. |

**Evidence required:** Read config models and validators. Verify empty/invalid values are rejected.

### 5. Input Validation & Path Security

| Check | Description |
|-------|-------------|
| Path traversal prevention | User-supplied names/identifiers are validated before use. No user-supplied path can escape the intended directory. |
| Session/identity name validation | Names are validated for placeholder/illegal values. |
| Config value validation | All config values are validated by the typed model before use (no raw strings passed to file operations). |

**Evidence required:** Read path-handling code. Read config validators. Check for path operations on user-supplied inputs.

### 6. Session / Identity Security

| Check | Description |
|-------|-------------|
| Session file in user directory | The session/identity file is stored in the user/runtime directory, not in the package directory or a global temp directory. |
| Session file in ignore file | Session/identity files are covered by the ignore file. |
| Session not shared | The session/identity file is per-user, not shared between different users or environments. |

**Evidence required:** Read the client-creation code. Check the session/identity file path. Read the ignore file.

---

## Report Output

Write findings to: `.ai/audit/04-security/findings.md` using template `.ai/audit/templates/audit-findings.md`.

**Write the file incrementally — append blocks of ≤100 lines each. Never write the entire report in a single call.**

Use prefix `SEC-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is correct.
- If after completing all Runtime Verification steps and all Audit Dimensions, no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — grep results, file:line of problematic code, logger calls that leak secrets, missing ignore-file entries.
  2. **Not just:** "violates invariant X" — show the exact code, the exact secret at risk, and the exact exposure vector.
