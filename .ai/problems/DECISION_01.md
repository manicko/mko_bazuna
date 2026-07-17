# Phase 1 - Implementation Decisions

## 1. Seller Authentication Flow

**Trigger:** Bot has a "Give one-time password" button in menu.

**Code Delivery:** Password sent via private Telegram chat (personal chat).

**Post-Entry Flow:** Simple login - seller is authenticated immediately on website, no additional actions required.

**Concurrency:** Bot queries backend for codes - frontend/backend synchronization handled technically.

---

## 2. Multi-item Listings (BLOCKED for Phase 1)

**Decision:** Multi-item listings are blocked for Phase 1. If multiple items are detected in an ad, it will not be published.

**Implication:** Each ad represents a single item with one price, one description.

---

## 3. Contact Link Reliability (Research Required)

**Deferred to Research:** How to generate contact links for Telegram users without public usernames.

**Constraint:** Phone number cannot be used as fallback contact method.

**Requirement:** Sellers must have Telegram, but link generation mechanism needs investigation.

### Research Findings: Contact Links for Users Without Usernames

#### Available Mechanisms

1. **`tg://user?id=<user_id>` links (Inline mentions only)**
   - Syntax: `[text](tg://user?id=123456789)` (Markdown) or `<a href="tg://user?id=123456789">text</a>` (HTML)
   - Works within messages ONLY as inline links in text
   - **CRITICAL LIMITATION:** Does NOT work in inline keyboard buttons or as standalone clickable URLs
   - Only functions if user has contacted the bot before OR is a group member
   - Requires `parse_mode` to be set when sending

2. **Temporary Profile Links (`t.me/contact/<token>`)**
   - Generated via MTProto `contacts.exportContactToken` method
   - Format: `t.me/contact/<token>` or `tg://contact?token=<token>`
   - Expire after a set time (duration in `expires` field)
   - Can be generated for users WITHOUT usernames
   - **MAJOR LIMITATION:** Requires MTProto access (NOT available via Bot API HTTP endpoints)
   - Only works for the currently logged-in user's own profile, not for others

3. **Deep Links with Start Parameter**
   - Format: `https://t.me/<bot_username>?start=<parameter>`
   - Can include user ID in parameter: `?start=user_123456789`
   - The bot receives the parameter when user clicks the link
   - Requires user interaction to initiate contact

#### Pros/Cons Analysis

| Approach | Pros | Cons |
|----------|------|------|
| `tg://user?id=` inline links | Works in messages if user interacted before | Not clickable outside Telegram messages; Bot API cannot initiate conversation |
| Temporary profile links | Works for any user without username; creates t.me link | Requires MTProto (not Bot API); only generates for logged-in user; expires |
| Deep links | Works with Bot API; user can initiate contact | Requires user click to establish first contact |

#### Privacy Implications

- Telegram restricts bots from initiating unsolicited conversations (anti-spam measure)
- `tg://user?id=` links only work if user has previously interacted with the bot
- Users can block bots via privacy settings
- Phone number links (`t.me/+1234567890`) are NOT viable per project constraints

#### Recommendation

**For Phase 1: Inline Mention Links Only**

1. **Primary Approach:** Use `tg://user?id=<user_id>` inline links within message text
   - Format as: `[@<first_name>](tg://user?id=<user_id>)` in Markdown
   - Requires `parse_mode="Markdown"` or `"HTML"` in sendMessage calls
   - Only shows as clickable mention if user has messaged bot before

2. **Fallback for New Users:** 
   - If user hasn't messaged bot, display: "Contact: @{first_name}" (non-clickable)
   - Prompt user to message bot first (via `/start` or any message)
   - Once interaction exists, future links become clickable

3. **Alternative (Future):** Consider MTProto library (Telethon, MadelineProto) for temporary profile link generation if clickable links for all users become critical

---

## 4. City Normalization & Recognition

**City Database:** Predefined list of Bosnian/Herzegovinian cities (small set). No additional hierarchy.

**Unrecognized Cities:** Go to "общие / без города" (general/uncategorized) section on website.

**Seller Correction:** Seller can review and correct city recognition before final submission.

---

## 5. Category Keyword Matching (Research Required)

**Deferred to Research:** Implementation details for keyword matching rules, confidence thresholds, and suggestion algorithms.

**Business Rule:** Seller must select exactly ONE category from bot suggestions (or type their own). Bot presents multiple options, seller confirms.

### Research Findings: Category Keyword Matching Approaches

#### Approach Comparison

| Approach | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| Rule-based keyword lists | Simple, interpretable, no training data needed, fast execution | Manual curation required, may need constant updates, language-specific | ✅ **RECOMMENDED for ~20 categories** |
| TF-IDF + ML (sklearn) | Good baseline, handles unseen text, confidence scores | Requires training data, overkill for small category set | Considered but not primary |
| spaCy PhraseMatcher | Efficient multi-word matching, token normalization | Language model required, adds complexity | Optional enhancement |
| Transformers (BERT/RoBERTa) | State-of-the-art accuracy, handles nuance | Heavy model, slow, needs GPU for training, overkill | ❌ NOT RECOMMENDED |

#### Implementation Options

**Option A: Simple Rule-Based (Recommended for Phase 1)**
```python
# Structure using StrEnum per project standards
class Category(StrEnum):
    REAL_ESTATE = "real_estate"
    VEHICLES = "vehicles"
    # ... ~20 categories

KEYWORD_MAP: dict[Category, list[str]] = {
    Category.REAL_ESTATE: ["stan", "kuća", "apartman", "nekretnine", "продам квартиру", ...],
    Category.VEHICLES: ["automobil", "motor", "volkswagen", "toyota", "машина", ...],
}
```

**Option B: TF-IDF + Linear Classifier**
- Use `sklearn.feature_extraction.text.TfidfVectorizer`
- Train `LogisticRegression` or `LinearSVC` on labeled examples
- Provides confidence scores for threshold-based rejection
- Requires initial training data

**Option C: Hybrid (Future Enhancement)**
- Rule-based as primary filter
- ML fallback for unmatched/unconfident matches
- Reference: natasha-ex/razmetka pattern (Russian NLP library with rule + ML hybrid)

#### Language Support: Bosnian/Russian

**Challenges:**
- Both use Cyrillic script (Bosnian also uses Latin)
- Extensive inflection/declinations in both languages
- No dedicated Bosnian NLP libraries in Python ecosystem
- Russian has established libraries: pymorphy2 (lemmatization), razmetka (rule+ML)

**Recommended Approach:**
1. **Use Latin script primarily** (Bosnian users primarily use Latin script)
2. **Include Cyrillic variants** for Russian terms and Bosnian Cyrillic speakers
3. **Simple keyword matching** with stemming/lemmatization support:
   - Use `pymorphy2` for Russian text normalization
   - For Bosnian: dictionary-based stemming or simple lowercase matching
4. **Multi-script support** in keyword lists:
   ```python
   # Example: include both scripts
   "модем|modem", "продам|prodajem", "куца|kupa"
   ```

#### Confidence Thresholds

Given the business rule of "exactly ONE category" with bot presenting multiple options:

- **Match Score:** Count keyword matches per category
- **Ratio Threshold:** If top category has >2x matches vs second place, present it confidently
- **Low Confidence:** If no clear winner, present top 3-5 with "Other" option
- **Seller Confirmation:** Mandatory selection prevents misclassification errors

#### Recommendation

**Primary Implementation: Rule-Based Keyword Lists with Priority Scoring**

1. Create `StrEnum` for all categories (per project standards)
2. Define keyword lists per category with Bosnian/Russian variants
3. Match counting with weighted scoring (longer/more specific keywords score higher)
4. Present top 3-5 matches to seller for confirmation
5. Include "Other" option allowing custom category entry

---

## Next Steps

- [x] Research: Contact link generation for Telegram users without public usernames
- [x] Research: Category keyword matching implementation approaches
- Proceed to planning with decisions above locked