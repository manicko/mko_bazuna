# 06 — PII Protection & Consent Compliance

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify that the system correctly separates **browse-only refusal (DECLINE)** from
**consent withdrawal (WITHDRAW)**, fully erases PII after the 30-day withdrawal
window, hides withdrawn/soft-deleted content from the public, and never leaks
identity data into analytics, logs, or the contact channel. Consent state must be
honored identically across the web process and the bot process.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Identity + PII** | The user/identity entity holds the only PII: external auth identifier, public handle, name components, consent timestamps, deletion/ban flags. |
| **Consent State** | Two distinct pathways: DECLINE (browse-only publishing restriction, no erasure) and WITHDRAW (revocation → soft-delete + scheduled hard-delete). |
| **Contact Gating** | The anonymous contact deep-link is rendered/delivered only when the ad is published, the seller identity is valid, not banned, not soft-deleted, and consent is not revoked. |
| **PII-Erasure Sweep** | A scheduled job hard-deletes identities 30 days after revocation, cascading to ads and media, and nulling identity references in analytics/audit rows. |
| **Analytics + Logs** | Event entity records activity with a nullable identity reference (SET NULL on erasure). Structured logs and tracebacks must contain no raw identity values. |
| **Cross-Process Consistency** | Both web and bot read the same identity state; the consent banner and bot middleware must reject identical states. |

## 3. Prerequisites

- Services runnable via the documented Docker commands (web + bot + DB).
- A throwaway database seeded with synthetic identities (NO real Telegram identifiers).
- Ability to advance the revocation timestamp past the 30-day window (seed/clock-mock).
- Linter, type-checker, and the consent/PII test suite available.

## 4. Runtime Verification (mandatory)

Execute, then capture evidence (DB state, logs, responses):

1. **DECLINE path** — decline consent. Assert: publishing flag set to browse-only; identity identifier/handle unchanged; revocation timestamp NOT set; existing ads remain public/searchable; contact deep-link still functions; own seller-login blocked.
2. **WITHDRAW path** — withdraw consent. Assert: revocation timestamp set; soft-delete flag + deletion timestamp set; PII fields (identifier, handle) nulled immediately; associated ads soft-deleted/hidden.
3. **Erasure sweep** — seed revocation timestamp >30d in the past; run the sweep. Assert: identity row removed; analytics/audit identity references NULLed (not cascaded away); no resurrection via rollback; re-run is idempotent (advisory lock).
4. **Contact gating** — for each condition in §5c, assert the deep-link is blocked: unpublished ad, null identifier, soft-deleted seller, banned seller, revoked consent.
5. **PII in telemetry** — grep the codebase and live logs for raw identifier/handle in analytics payloads, log messages, and exception tracebacks.
6. **Cross-process** — confirm an unrevoked-but-declined seller still appears in search and contact works (web and bot); confirm bot commands reject a revoked/soft-deleted identity.

## 5. Audit Dimensions (checks + evidence)

### (a) Consent semantics correctness — CRITICAL
DECLINE ≠ WITHDRAW. DECLINE blocks only own seller-login and keeps all data + contact; WITHDRAW triggers soft-delete + 30-day erasure.
- Evidence: DECLINE sets no revocation timestamp, no PII nulling, no ad deletion. WITHDRAW sets revocation timestamp, soft-deletes, nulls PII, schedules hard-delete.

### (b) PII erasure completeness (30-day window) — CRITICAL
After the window: identifier/handle nulled, associated data purged, no resurrection.
- Evidence: sweep queries the correct window; nulls references before deletion; identifier/handle NULL in DB; no path re-links erased identity.

### (c) Contact deep-link gating — CRITICAL
Rendered/delivered only when: ad PUBLISHED + seller identifier NOT null + NOT soft-deleted + NOT banned + consent NOT revoked. Identical on web and bot. Anonymous delivery exposes no identity to the recipient.
- Evidence: each of the 5 conditions blocks the link; bot and template enforce the same logic; message payload carries only the ad reference, not identity.

### (d) PII containment in analytics/logs — CRITICAL
No raw identifier/handle in events, logs, or tracebacks.
- Evidence: events store identity reference by ID only; logs avoid identity strings; display name uses name components, not the external identifier.

### (e) Soft-delete correctness — HIGH
Withdrawn/deleted content hidden from public listing and search immediately, restorable within the window.
- Evidence: public/search queries exclude soft-deleted status; direct-detail access returns not-found; owner view may still see within window.

### (f) Cross-process consent consistency — HIGH
Web banner and bot middleware honor identical consent state.
- Evidence: shared identity lookup; bot rejects restricted states; revocation reflects immediately on both sides.

## 6. Cross-Cutting (owned here, not duplicated)
- **Consent revocation → bot FSM cascade:** a seller who withdraws mid-ad-creation must have DRAFT rows and associated photos purged (the consent trigger is this phase; the row/file mechanics belong to phases 05/07).
- **PII erasure → media cascade:** the erasure trigger here must also clear referenced media files (file handling owned by phase 07).
- **Banner coverage:** the consent banner must cover BOTH web and bot entry points; no separate bot confirmation may bypass shared state.

## 7. Edge Cases
- Seller withdraws mid-FSM-dialog (DRAFT + photos) → DRAFT and photos purged, no residual PII.
- Buyer DECLINEs then later WITHDRAWs → second action follows WITHDRAW path.
- Revoked seller's old ads still in search index → sweep hard-delete cascades; index must not reference deleted rows.
- Sweep runs while seller re-publishes → advisory lock + transaction isolation prevent deleting new ads.
- Timezone skew on the 30-day window → verify UTC storage and boundary calculation.
- Contact deep-link opened for an ad that became archived/deleted → bot responds unavailable, no seller message sent.
- Analytics event references an erased identity → reference NULLed, aggregate preserved, not exposed to buyers.

## 8. Severity Taxonomy

- **CRITICAL**
  - DECLINE path triggers PII erasure (identifier/handle nulled).
  - WITHDRAW fails to erase after 30d (identifier/handle remain, ads persist).
  - Contact deep-link exposed for revoked/unpublished/invalid/banned ad.
  - PII leaked into analytics events or logs (raw identifier/handle).
  - Revoked/withdrawn seller ads still publicly visible/searchable.
- **HIGH**
  - Soft-delete fails to hide content from public/search.
  - Erasure sweep misses rows, double-runs, or corrupts state.
  - Consent banner not covering the bot.
  - DECLINE incorrectly blocks contact (identifier still present).
- **MEDIUM**
  - Erasure timing off by timezone.
  - Analytics/logs store raw identity in text.
  - Revocation not propagating to bot FSM state immediately.
  - Media cascade incomplete on erasure.
- **LOW**
  - Log verbosity includes identity.
  - Missing type hints on nullable returns.
  - Advisory lock not logged on entry/exit.

## 9. Recommended Sequence
1. Discovery — map identity entity, consent states, sweep, gating, analytics, soft-delete.
2. Runtime verification (§4).
3. Per-dimension checks (§5 a–f).
4. Cross-cutting (§6) and edge cases (§7).
5. Consolidate findings.

## 10. Finding Prefix
Use `PII-` for all findings in this phase.

## 11. Reporting
- `problems-only: true`.
- Each finding: severity, zone, evidence (path/line/query/response), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.
