---
name: 04-auth-login
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 04 — Authentication & Login Token Security

**Instruction set for an LLM auditor.** Follow the steps below in order. Be laconic, structured, and evidence-driven. Report ONLY real deviations with runtime evidence (`problems-only: true` — see Output Mode).

## Purpose

Reusable handbook for auditing the authentication & login-token security of a **dual-process Django system** where sellers authenticate via a **QR deep-link login token**.

- A **32-char cryptographically-random token** is issued.
- The **RAW value is NEVER stored** — only a hash.
- The bot **claims** the token via a **two-phase atomic claim** using **constant-time comparison**, **expiry enforcement**, and **replay protection** (consumed-once).
- The bot FSM **binds the Telegram identity** to the site account.
- The web side **consumes** the token to establish the session.

This phase owns the **security correctness** of the login-token auth mechanism **end-to-end**.

## Scope Boundaries

- **OWNED here:** the security correctness of the login-token auth mechanism (token issuance → claim → consumption → session).
- **NOT owned here (do not duplicate):**
  - Phase 02 — secrets in config.
  - Phase 03 — concurrency atomicity *mechanisms* (but the *auth correctness* of the claim is owned here).
  - Phase 06 — PII / consent.

## Output Mode

`problems-only: true`. Rules:

- Emit ONLY real deviations, bugs, or missing required behavior.
- Provide **runtime evidence** (command output, grep result, assertion) for each finding.
- Omit passing rows entirely.
- If nothing is wrong: `"No problems found in this phase."`
- Each finding must state the **exact consequence** of the defect.

## Architectural Layers

| Layer | Zone of responsibility | Key risks |
|-------|------------------------|-----------|
| Token-issuance zone | Generate random token, compute hash, store entity, render QR/deep-link | Raw value leaked, weak entropy, rate-limit missing |
| Token-claim/consumption zone | Atomic two-phase claim: bot binds identity, web consumes | Race/double-claim, non-atomic, wrong identity |
| Token-hash storage zone | Persist only hash, indexed lookup | Raw token at rest, hash truncation |
| Constant-time comparison zone | Timing-attack-resistant validation | `==` on secrets, microsecond side-channel |
| Expiry/lifecycle zone | TTL enforcement, reject expired+consumed, cleanup sweep | Expired accepted, replay, orphaned tokens |
| Deep-link/QR generation zone | Unguessable URL, no PII leak in referrer/logs | Guessable token, leakage |
| Bot FSM auth-binding zone | Bind Telegram identity to claimed token | Identity spoofing, FSM state loss |
| Web session/cookie layer | Secure session after claim | Insecure cookie, session fixation |

## Discovery Stage

Identify the system roles (not concrete names) and map each to its zone.

1. **Token-issuance mapping** — trace the issuance flow; confirm the raw value is returned exactly once, the hash is stored, and the raw value is never logged.
2. **Token-claim mapping** — trace the bot claim (parse deep-link, hash value, atomic UPDATE binding identity) **AND** the web consumption (mark consumed). Confirm **both phases exist**.
3. **Constant-time comparison mapping** — locate where the token is compared/validated; confirm a **constant-time utility** is used, **not** `==`.
4. **Token-hash storage mapping** — confirm only the hash is persisted, indexed for lookup, and no raw column exists.
5. **Expiry/replay mapping** — confirm expiry + consumed-once are enforced **inside** the claim query; locate the cleanup sweep.
6. **Deep-link/QR + FSM + session mapping** — confirm unguessable URL, no token in logs/referrer, FSM binds the correct identity, and a secure cookie is set.

## Mandatory Runtime Verification

Run these BEFORE the checklist. Capture evidence for each.

- **R1 Token issuance secrecy** — issue a token; confirm the raw value is NEVER in the response / logs / storage (only the hash at rest).
- **R2 Invalid/expired/consumed rejection** — claim with wrong / expired / already-consumed token → verify rejection with a clear error.
- **R3 Concurrent double-claim race** — two identities claim the same token concurrently → exactly ONE succeeds.
- **R4 Insecure-comparison scan** — grep for `==` / non-constant-time comparison on token / secrets; confirm the constant-time utility is used where secrets are compared.
- **R5 Token-leak scan** — grep for logging of token values / token in URLs or error messages.
- **R6 Linter + type-check + auth/login test-suite run** — focused on the auth surface.

## Audit Dimensions

### (a) Token storage hash-only

| Check | Description |
|-------|-------------|
| Raw token never stored | Only the hash is persisted; no raw column exists at rest. |
| Raw token never logged | Issuance/claim/consumption do not emit the raw value. |
| Hash indexed | Stored hash supports indexed lookup. |

**Evidence required:** grep for raw-token columns/fields; R1 output; R5 output.

### (b) Constant-time comparison

| Check | Description |
|-------|-------------|
| Constant-time utility used | A constant-time utility (e.g. digest comparison) is used wherever the token is validated. |
| No `==` on secrets | No `==` / non-constant-time comparison on the token or derived secrets. |
| Hash pre-computed | Hash is computed before the lookup/comparison (no raw secret round-trip). |

**Evidence required:** R4 grep; code trace of the validation entrypoint.

### (c) Atomic/idempotent claim

| Check | Description |
|-------|-------------|
| Single-statement claim | One UPDATE / transaction with all conditions (hash-match, not-yet-claimed, not-consumed, not-expired). |
| Race-proof | Concurrent claims yield exactly one success. |
| Consumed exactly once | Double-claim is rejected. |
| Web consumption exists | The web-side consumption step exists and is atomic. |

**Evidence required:** R3 output; code trace of claim + web consumption; R2 consumed-rejection output.

### (d) Expiry & replay

| Check | Description |
|-------|-------------|
| Server-side expiry | Expiry enforced in the claim query (not client-side only). |
| Consumed rejected | Already-consumed tokens are rejected. |
| Cleanup sweep | A sweep removes expired / orphaned tokens. |

**Evidence required:** R2 expired/consumed output; location of cleanup sweep.

### (e) Token generation quality

| Check | Description |
|-------|-------------|
| Cryptographic randomness | Token from a CSPRNG, not sequential/time-based. |
| Sufficient entropy | Length/entropy >= ~256 bits. |
| URL-safe | Token is URL-safe; not guessable. |

**Evidence required:** code trace of the generator; entropy estimate.

### (f) Deep-link/QR + FSM + session safety

| Check | Description |
|-------|-------------|
| No token leakage | Token not in logs / referrer / URLs / error messages. |
| Unguessable URL | Deep-link URL is unguessable. |
| Correct FSM binding | FSM binds the *claiming* Telegram identity (no identity spoofing). |
| Secure cookie | Session cookie is Secure + HttpOnly + SameSite. |
| No session fixation | New session issued on claim; old identifier not reused. |

**Evidence required:** R5 output; FSM code trace; cookie attribute inspection.

## Cross-Cutting Concerns (this phase)

- **Token confidentiality across BOTH processes** (web issues, bot claims) — never in logs / tracebacks / URLs / referrers.
- **Cross-process atomicity of the claim** (web issues, bot claims) — auth correctness is owned here even though the concurrency mechanism is Phase 03.
- **FSM auth completeness** — authentication must complete (or safely abort) and **persist through bot restart** via the shared ORM.

## Severity Taxonomy

| Severity | Examples |
|----------|----------|
| CRITICAL | Raw token stored; timing-attack-vulnerable comparison; non-atomic claim allowing double-claim / account-takeover; expired/consumed token accepted; weak/predictable token; token leaked in logs/URL. |
| HIGH | Missing expiry enforcement; replay not blocked; claim for wrong identity; deep-link token guessable; web consumption step missing. |
| MEDIUM | Token in non-HttpOnly / insecure cookie; missing rate-limit on issuance; insufficient entropy margin. |
| LOW | Missing type hints; log verbosity around auth. |

## Edge-Case Checklist

- Issued token never scanned → expiry cleanup must remove it.
- Concurrent multi-device scan → exactly one claim wins.
- Token intercepted in transit → TLS dependency must hold.
- Bot restart mid-claim → FSM state restored via shared ORM; no half-claim.
- Clock skew vs expiry → tolerant boundary decision documented.
- Replay of old deep-link → consumed/expired rejection.
- Issuance flood → rate limiting present.

## Isolation / Test Note

- Auth tests must use **synthetic tokens** (never real ones).
- Simulate the **concurrent claim race**.
- Verify **consumed-token rejection**.
- Confirm the **constant-time utility** is present and invoked.

## Dead-Code Note

Claim / consumption / cleanup utilities that are defined but **never wired** into the flow are findings.

## Report Output

Write to `.ai/audit/04-auth-login/findings.md` using the template `.ai/audit/templates/audit-findings.md`.
Incremental append, ≤100 lines. Prefix findings with `AUT-`.

**Problems-only rules (restated):**
- Only findings; omit passing rows.
- If none → `"No problems found in this phase."`
- Each finding: runtime evidence + exact consequence.
