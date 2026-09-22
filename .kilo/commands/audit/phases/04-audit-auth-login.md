---
name: 04-auth-login
status: draft
validated: yes
executor: auditor
problems-only: true
---

# Phase 04 — Authentication & Login Token Security

**Instruction set for an LLM auditor.** Follow the steps below in order. Be laconic, structured, and evidence-driven. Report ONLY real deviations with runtime evidence (`problems-only: true` — see Output Mode).

## Purpose

Reusable handbook for auditing the authentication & login-token security of a **dual-process Django system** where sellers authenticate via a **Telegram deep-link login token**.

- A 32-char cryptographically-random token is issued.
- The **RAW value is NEVER stored** — only a hash.
- The bot **claims** the token via atomic `UPDATE … RETURNING`, binding its Telegram identity; the **web side consumes** it. No raw-token `==`/`compare_digest` comparison exists — the raw token is SHA-256 hashed and looked up by its indexed unique `token_hash` column before the atomic claim.
- Expiry and consumed-once (replay) guards are enforced inside the claim/consumption query.

This phase owns the **security correctness** of the login-token auth mechanism **end-to-end**.

## Scope Boundaries

- **OWNED here:** the security correctness of the login-token auth mechanism (token issuance → claim → consumption → session).
- **NOT owned here (do not duplicate):**
  - Phase 02 — secrets in config.
  - Phase 03 — row-level-lock / `UPDATE … RETURNING` *mechanism* for contested rows (Phase 04 owns the *auth correctness* of single-consumption: the `consumed_at IS NULL` replay-protection guard is owned here; Phase 04 also owns consumed-once enforcement at the web consumption step).
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
| Token-issuance zone | Generate random token, compute hash, store entity, render deep-link button | Raw value leaked, weak entropy, rate-limit missing |
| Token-claim/consumption zone | Atomic two-phase claim: bot binds identity, web consumes | Race/double-claim, non-atomic, wrong identity |
| Token-hash storage zone | Persist only hash, indexed lookup | Raw token at rest, hash truncation |
| Hash-indexed lookup zone | Raw token hashed before storage; indexed unique-column lookup; no raw-token comparison | Raw token compared via `==` / `compare_digest` gate assumed, hash round-tripped |
| Expiry/lifecycle zone | TTL enforcement, reject expired+consumed, cleanup sweep | Expired accepted, replay, orphaned tokens |
| Deep-link generation zone | Unguessable `t.me/<bot>?start=login_<token>` URL assembled at click time | Guessable token, leakage |
| Bot FSM auth-binding zone | Bind Telegram identity to claimed token | Identity spoofing, FSM state loss |
| Web session/cookie layer | Secure session after claim | Insecure cookie, session fixation |

## Discovery Stage

Identify the system roles (not concrete names) and map each to its zone.

1. **Token-issuance mapping** — trace the issuance flow; confirm the raw value is returned exactly once, the hash is stored, and the raw value is never logged.
2. **Token-claim mapping** — trace the bot claim (parse deep-link, hash value, atomic UPDATE binding identity) **AND** the web consumption (mark consumed). Confirm **both phases exist**.
3. **Hash-indexed lookup mapping** — confirm the raw token is SHA-256 hashed *before* any storage or lookup; confirm no `==`/`compare_digest` on the raw token; confirm lookup is by indexed `token_hash` unique column.
4. **Token-hash storage mapping** — confirm only the hash is persisted, indexed for lookup, and no raw column exists.
5. **Expiry/replay mapping** — confirm expiry + consumed-once are enforced **inside** the claim query; locate the cleanup sweep.
6. **Deep-link/QR + FSM + session mapping** — confirm unguessable URL, no token in logs/referrer, FSM binds the correct identity, and a secure cookie is set.

## Mandatory Runtime Verification

Run these BEFORE the checklist. Capture evidence for each.

- **R1 Token issuance secrecy** — issue a token; confirm the raw value is NEVER in the response / logs / storage (only the hash at rest).
- **R2 Invalid/expired/consumed rejection** — claim with wrong / expired / already-consumed token → verify rejection with a clear error.
- **R3 Concurrent double-claim race** — two identities claim the same token concurrently → exactly ONE succeeds.
- **R4 No-raw-token-comparison scan** — grep for `==` / `compare_digest` on token / hash / secrets; confirm the hash is computed before the indexed DB lookup; confirm no `compare_digest` is *assumed* (the mechanism is hash-then-index, which eliminates the comparison entirely).
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

### (b) Hash-indexed lookup (no raw-token comparison)

| Check | Description |
|-------|-------------|
| Hash pre-computed | SHA-256 hash is computed from the raw token before any storage or lookup. |
| No raw-token comparison | No `==` or `compare_digest` on the raw token or its hash; lookup is by the indexed unique `token_hash` column. |
| Indexed unique lookup | Stored `token_hash` is `unique=True, db_index=True`, supporting O(log n) indexed lookup with no linear scan. |

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

### (f) Deep-link + FSM + session safety

| Check | Description |
|-------|-------------|
| No token leakage | Token not in logs / referrer / URLs / error messages. |
| Unguessable URL | Deep-link URL is unguessable. |
| Correct FSM binding | FSM binds the *claiming* Telegram identity (no identity spoofing). |
| Secure cookie | Session cookie is Secure + HttpOnly + SameSite. |
| No session fixation | New session issued on claim; old identifier not reused. |
| Session lifetime | Idle/absolute timeout configured; session invalidated on logout and on consent withdrawal/deletion. |
| Logout revocation | Logout invalidates the server-side session; session key cannot be replayed post-logout. |

**Evidence required:** R5 output; FSM code trace; cookie attribute inspection.

## Cross-Cutting Concerns (this phase)

- **Token confidentiality across BOTH processes** (web issues, bot claims) — never in logs / tracebacks / URLs / referrers.
- **Cross-process atomicity of the claim** (web issues, bot claims) — auth correctness is owned here even though the concurrency mechanism is Phase 03.
- **FSM auth completeness** — authentication must complete (or safely abort) and **persist through bot restart** via the shared ORM.

## Severity Taxonomy

| Severity | Examples |
|----------|----------|
| CRITICAL | Raw token stored; raw-token `==`/non-indexed comparison (timing-attack-vulnerable); non-atomic claim allowing double-claim / account-takeover; expired/consumed token accepted; weak/predictable token; token leaked in logs/URL. |
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
