# Research Report: Multilingual Search for Classifieds Board MVP

**Date:** 2026-07-17  
**Target:** Bosnia and Herzegovina classifieds (Avito-like)  
**Stack:** Python + Django  
**Languages:** Russian (base) / Bosnian Latin (UI)  
**Search Context:** Single-language storage + translation-on-display

---

## Executive Summary

Large classifieds and e-commerce platforms universally treat search as a **cross-lingual problem**. Storing content in a single base language is viable for MVP, but **search requires handling queries in the user's UI language**. The recommended approach: **translate Bosnian search queries to Russian at query time**, then search the Russian-indexed content.

---

## Findings

### 1. Real-World Architecture Patterns

#### eBay Classifieds Group
- Uses **single-language indexing per market** but implements **query translation** for cross-market search
- The eBay Translation API translates item titles/descriptions between markets [^1]
- Each regional site (DBA Denmark, KijijiAUTOS Canada) maintains localized content indexed for that locale
- For cross-lingual scenarios: queries are translated, not content re-indexed

#### OLX/OLX Group
- Operates as **localized marketplaces per country** with language-aware architecture
- Search is **language-sensitive** - users search in their native language within each market [^2]
- The platform supports 30+ countries with separate language implementations
- No evidence of cross-market translation-on-display; each market maintains local content

#### AliExpress
- Implements **cross-lingual semantic search** using multilingual embedding models (E5) [^3]
- Product titles remain in original language; search works across 100+ languages via vector embeddings
- Uses **translation-on-display** for product descriptions while enabling cross-language search

#### Walmart.com (Research Paper)
- Deployed **query translation** for Spanish-to-English search [^4]
- Results: +70% nDCG gain for Spanish queries, statistically significant lift in Spanish GMV
- Key insight: translating queries to match indexed content is more practical than indexing in multiple languages

### 2. Technical Approaches Comparison

| Approach | Description | Pros | Cons | Used By |
|----------|-------------|------|------|---------|
| **Query Translation** | Translate user query to base language, search Russian content | Simple, single index, proven ROI | Translation latency, quality varies | eBay, Walmart |
| **Multi-Field Indexing** | Index same field with multiple language analyzers (ES) | No query translation needed | Index bloat, complex maintenance | Some ES implementations |
| **Multilingual Embeddings** | Use models like E5/BGE-M3 for cross-lingual vector search | Language-agnostic search | Requires ML infrastructure, higher complexity | AliExpress (modern), Elasticsearch |
| **Native Content per Language** | Store separate content for each language | Best relevance, local SEO | Content duplication, sync overhead | Avito regional sites |

### 3. Language Similarity: Russian ↔ Bosnian

Both Russian and Bosnian are **Slavic languages**, but with important distinctions:

- **Russian** (East Slavic): Cyrillic script, ~258 million speakers
- **Bosnian** (South Slavic): Latin script (primary), ~2.2 million speakers

Lexical similarity between Slavic languages varies significantly:
- Russian shares moderate vocabulary with other Slavic languages (e.g., 0.24-0.60 similarity with listed languages) [^5]
- **Low mutual intelligibility**: Speakers of one cannot reliably understand the other
- **Shared grammatical structures**: Both use cases, gendered nouns, similar verb aspects

**Key insight for MVP**: Query translation is required; linguistic similarity alone won't bridge comprehension gap.

### 4. Cross-Lingual Search Implementation Patterns

#### Elasticsearch Multilingual Strategy [^6]
```
# Single index with language-aware fields
{
  "title_russian": { "type": "text", "analyzer": "russian" },
  "title_bosnian": { "type": "text", "analyzer": "bosnian_latin" },
  "content_russian": { "type": "text", "analyzer": "russian" }
}

# Or: Translate query at search time
# Bosnian query → Russian query → Search Russian-indexed content
```

#### Embedding-Based Cross-Lingual Search [^3]
Modern trend uses models like **multilingual-E5-base** or **BGE-M3** that map semantically equivalent phrases across languages into similar vector spaces. This enables:
- Query in Bosnian → Search Russian content without explicit translation
- Mixed-language queries handled gracefully
- Higher implementation complexity (requires vector DB, model inference)

---

## Recommendation for MVP

### Recommended Architecture: **Query Translation to Base Language**

**Rationale:**
1. **Simplicity**: Single index, no content duplication
2. **Proven**: Walmart's +70% nDCG improvement validates effectiveness
3. **Cost-effective**: No additional ML infrastructure for MVP
4. **Compatible**: Works with Django ORM + PostgreSQL full-text search

### Implementation Plan

#### Phase 1: Core Search (MVP)
```python
# Pseudocode for search flow
def search_ads(query: str, ui_language: str) -> QuerySet:
    if ui_language == "bosnian" and query_language(query) == "bs":
        query_russian = translate_to_russian(query)
    else:
        query_russian = query
    
    return Ad.objects.filter(
        Q(title__icontains=query_russian) |
        Q(description__icontains=query_russian)
    )
```

**Components:**
- Integrate **Google Cloud Translation API** or **DeepL API** for query translation
- Cache translations for frequently searched terms
- Use PostgreSQL full-text search with Russian `pg_trgm` extension for fuzzy matching
- Add translation indicator in UI: "Rezultati prevedeni iz ruskog (Results translated from Russian)"

#### Phase 2: Search Enhancement (Post-MVP)
Consider migration to:
- **Multilingual embeddings** (E5/BGE-M3 via sentence-transformers)
- **Elasticsearch** with cross-lingual capabilities
- **Hybrid search**: keyword + semantic similarity

#### Phase 3: Long-term Scaling
If market grows:
- Evaluate **native content per language** for SEO benefits
- Implement **hreflang tags** for search engine indexing
- Add **language-specific synonyms** and stop words

### Search Flow Diagram (MVP)

```
User (Bosnian UI) ──query──▶ Query Translator ──Russian query──▶ 
                                    │
                                    ▼
                        Search Russian-indexed Ads
                                    │
                                    ▼
                    Results shown with UI-translated chrome
```

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Translation quality variance | Cache common queries, use high-quality MT service |
| Translation latency | Async pre-translation for common terms, show loading state |
| User confusion (source language shown) | Clearly mark "Translated from Russian" in UI |

---

## References

[^1]: eBay Developers Program. "Translation API Overview." https://developer.ebay.com/api-docs/translation/overview.html  
[^2]: OLX Tech Blog. "Microservices Architecture." https://tech.olx.in/  
[^3]: Elasticsearch Labs. "Deploying multilingual embedding model in Elasticsearch." 2025-10-22. https://www.elastic.co/search-labs/blog/multilingual-model-deployment-elasticsearch  
[^4]: Perez-Martin et al. "Cross-lingual Search for e-Commerce based on Query Translatability." WWW 2023. Walmart.com deployment showed +70% nDCG gain.  
[^5]: Wikipedia. "Lexical similarity." Ethnologue data on Slavic language similarities.  
[^6]: OneUptime. "How to Use Elasticsearch for Multi-Language Search." 2026-01-21.  

---

## Appendix: Language Detection for Query Routing

For robust query handling, implement language detection to determine when translation is needed:

```python
# Detect if query is already Russian (no translation needed)
# If query contains Bosnian Latin characters or detected as Bosnian → translate
```

This prevents double-translation and reduces unnecessary API calls.