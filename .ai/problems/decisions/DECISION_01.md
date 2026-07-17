# DECISION_01 — Phase 1 Domain Decisions

Source: `CONTEXT_01.md` + `docs/wiki/01_technical_specification.md`.
Scope: non-technical, domain-level decisions only (no DB/modules/architecture).
These decisions are locked for downstream research and planning.

---

## 1. Login / One-Time-Code Flow (US-S1)

- **Entry point:** Site has a "Войти" button; clicking opens a dedicated login page where the bot-issued one-time code is pasted.
- **Code to account binding:** The code is generated server-side and bound to the `telegram_id` that requested it. Entering the code logs into that exact account (stateless code, no separate account selection).
- **Expired / wrong code:** Login page shows a clear message ("code expired / wrong — request a new one in the bot") with a retry path back to the bot. No silent failure.
- **Session lifetime:** Persistent web session (cookie) that survives browser restarts until explicit logout or a long idle timeout.
- **Account reuse:** Existing `telegram_id` is found and reused; no duplicate account created on repeat login.

---

## 2. Seller-Bot Conversation Flow (US-S2)

- **Dialogue style:** Strictly guided, one field at a time. Bot asks category, city, title, description, price (if applicable), photos, and confirms each.
- **Category selection:** Closed admin-defined tree (decision D). Bot proposes TOP-3-5 by keywords; seller must pick from the proposed list or browse the full tree. Custom/free-text categories are **rejected** — no free "other" label.
- **Photos:** 1 to 5 required, **compressed Telegram photos only**. A document/file upload is rejected with a clear message; publishing requires at least 1 valid photo.
- **Preview and correction:** Before final send the bot shows a preview and lets the seller fix inaccuracies (including city/category mapping).
- **Abandoned draft:** Partial drafts are auto-discarded after an idle timeout (e.g. 30 min). Nothing is published; no half-ad is saved.

---

## 3. Search and Filtering (US-B2 / US-B3 / US-B7)

- **Result ordering:** Buyer-selectable sort — by date or by price.
- **Result scope:** Only `published` ads; search covers title and description.
- **Language and search basis:** Ads are stored in **one base language — Russian**. UI language switch (Russian / Bosnian Latin) translates only the interface chrome; ad text is shown translated on display. Search is Russian-based for now.
- **City matching:** Exact match to the preset city list by default. Use a ready-made, free, well-established fuzzy-match library **only if** one is trivially available; otherwise keep exact match.
- **Zero results:** Friendly "no results" empty state with a suggestion to broaden filters.

### Deferred to research (search/lang)
- Cross-language / multilingual search approach used by large classifieds (e.g. AliExpress-style): how to index and query ads stored in a single base language while serving a second UI language. Research before planning multilingual search.
- Identify a concrete, free, mature fuzzy-match library for city names (if exact match is deemed insufficient later).

---

## 4. Ad Lifecycle and Re-Moderation (US-S5 / US-S7 / decision A)

- **Edits requiring re-moderation:** Text edits (title / description) send the ad back to `on_moderation`. Price and photo edits publish instantly.
- **Visibility during re-check:** An ad recalled for re-moderation is **immediately hidden** from the public site until it passes.
- **Archive/delete timers:** Run from the **original publication date**. Any edit (text or media) **resets** the timer to the edit time (archived at 2 months, hard-deleted at 4 months from the reset point).
- **Reactivation:** A seller can reactivate an `archived` ad from their cabinet; reactivation re-publishes it (text is re-checked).
- **Independent timers:** Auto-check-failed deletion (1 week, decision A) and consent-revoked hard-delete (30 days, decision F) are separate from the archive/delete timers above.

---

## 5. Consent and Privacy Banner (decision F)

- **Browse before consent:** Buyers may browse published ads freely before accepting the banner.
- **Decline effect:** "Decline" blocks seller login / account actions only. The external "Contact seller" `t.me/@username` button still works (it leaves the site).
- **Re-show policy:** Once accepted, the banner stays dismissed (persisted); it is not re-shown on return visits.
- **Bot coverage:** Website banner consent covers all personal-data processing, including the bot. The bot requires **no separate** acknowledgment (matches decision F).
- **Logged:** Consent acceptance timestamp is recorded; withdrawal/deletion follows decision F (soft delete immediately, hard delete of `telegram_id` within 30 days).

---

## Deferred Ideas (out of Phase 1 scope — captured, not acted on)

- **Multilingual search/indexing** of single-base-language ads (see section 3 deferred).
- **Fuzzy city matching** beyond exact match (gated on a trivially available free library).
- **Resumable drafts** in the bot (currently auto-discarded on idle).
- **Group/channel monitoring** (decision B) — separate future phase with its own API.
- **Multi-item ads** (several products in one post) — explicitly out of Phase 1.

---

## Open Questions for Research Phase

1. Which free, mature fuzzy-match library fits city-name matching (if adopted)?
2. How do large classifieds implement search when content is stored in one base language but served in a second UI language? (drives section 3 multilingual search design)
