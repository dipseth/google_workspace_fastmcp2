# Qdrant Text Indexing Strategy for Card Building

## Overview

Our card building system stores component metadata in Qdrant. Beyond vector embeddings,
we can leverage Qdrant's full-text indexing features to enable:
- Faster keyword searches
- Fuzzy matching for user input variations
- Phrase matching for multi-word component names
- Language-aware stemming for documentation search

## Current Architecture

Our `mcp_gchat_cards` collection has these payload fields that could benefit:

| Field | Current Type | Content Example | Text Index Candidate? |
|-------|-------------|-----------------|----------------------|
| `name` | keyword | "DecoratedText" | Yes - for component lookup |
| `full_path` | keyword | "card_framework.v2.widgets.DecoratedText" | Yes - for path search |
| `docstring` | text | "A widget that displays..." | **High value** |
| `relationships.nl_descriptions` | text | "decorated text with icon, button..." | **High value** |
| `relationships.child_classes` | list | ["Icon", "Button", "OnClick"] | Array filter works |

## Feature Analysis

### 1. ASCII Folding (v1.16.0+)

**What it does**: Converts Unicode characters to ASCII equivalents (ã→a, é→e)

**Use case for us**:
- Users might search "cafe" when docs contain "café"
- Component descriptions might use special chars: "naïve implementation"

**Where to apply**:
```python
# On docstring and nl_descriptions fields
client.create_payload_index(
    collection_name="mcp_gchat_cards",
    field_name="docstring",
    field_schema=models.TextIndexParams(
        type=models.TextIndexType.TEXT,
        tokenizer=models.TokenizerType.WORD,
        ascii_folding=True,  # Enable
    ),
)
```

**Impact**: Low priority for our use case - component names are ASCII-only.

---

### 2. Stemming (Snowball)

**What it does**: Reduces words to root form (running/runs/runner → "run")

**Use case for us**:
- Search "buttons" matches "Button", "ButtonList"
- Search "selecting" matches "SelectionInput"
- Search "clickable" matches "OnClick"

**Where to apply**:
```python
# On docstring and nl_descriptions for natural language search
client.create_payload_index(
    collection_name="mcp_gchat_cards",
    field_name="relationships.nl_descriptions",
    field_schema=models.TextIndexParams(
        type=models.TextIndexType.TEXT,
        tokenizer=models.TokenizerType.WORD,
        stemmer=models.SnowballParams(
            type=models.Snowball.SNOWBALL,
            language=models.SnowballLanguage.ENGLISH
        )
    ),
)
```

**Impact**: **High value** - Helps match user queries like "add a clickable icon" to
components that have "click" in their relationships.

---

### 3. Stopwords

**What it does**: Filters common words (the, is, at, which, on)

**Use case for us**:
- Ignore "the", "a", "with" in searches
- Focus on meaningful terms: "button with icon" → search "button icon"

**Where to apply**:
```python
client.create_payload_index(
    collection_name="mcp_gchat_cards",
    field_name="docstring",
    field_schema=models.TextIndexParams(
        type=models.TextIndexType.TEXT,
        tokenizer=models.TokenizerType.WORD,
        stopwords=models.StopwordsSet(
            languages=[models.Language.ENGLISH],
            custom=[
                "widget",  # Too generic in our context
                "component",  # Too generic
                "gchat",  # Domain-specific noise
            ]
        ),
    ),
)
```

**Impact**: Medium - Helps with longer docstring searches, reduces noise.

---

### 4. Phrase Search

**What it does**: Matches exact word sequences ("machine learning" as a phrase)

**Use case for us**:
- Match "decorated text" exactly, not "text" AND "decorated" separately
- Match "button list" vs just "button" or "list"
- Match "overflow menu" as exact phrase

**Where to apply**:
```python
client.create_payload_index(
    collection_name="mcp_gchat_cards",
    field_name="name",  # Component names
    field_schema=models.TextIndexParams(
        type=models.TextIndexType.TEXT,
        tokenizer=models.TokenizerType.WORD,
        lowercase=True,
        phrase_matching=True,  # Enable
    ),
)

# Search with phrase:
client.scroll(
    collection_name="mcp_gchat_cards",
    scroll_filter=models.Filter(
        must=[
            models.FieldCondition(
                key="name",
                match=models.MatchText(text='"Decorated Text"')  # Quotes for phrase
            )
        ]
    )
)
```

**Impact**: **High value** - Critical for multi-word component names.

---

## Recommended Index Configuration

```python
from qdrant_client import models

def create_text_indices(client, collection_name: str):
    """Create optimized text indices for card component search."""

    # 1. Component name index - phrase matching for multi-word names
    client.create_payload_index(
        collection_name=collection_name,
        field_name="name",
        field_schema=models.TextIndexParams(
            type=models.TextIndexType.TEXT,
            tokenizer=models.TokenizerType.WORD,
            lowercase=True,
            phrase_matching=True,
        ),
    )

    # 2. Docstring index - stemming + stopwords for NL search
    client.create_payload_index(
        collection_name=collection_name,
        field_name="docstring",
        field_schema=models.TextIndexParams(
            type=models.TextIndexType.TEXT,
            tokenizer=models.TokenizerType.WORD,
            lowercase=True,
            stemmer=models.SnowballParams(
                type=models.Snowball.SNOWBALL,
                language=models.SnowballLanguage.ENGLISH
            ),
            stopwords=models.Language.ENGLISH,
            ascii_folding=True,
        ),
    )

    # 3. Relationship descriptions - stemming for NL matching
    client.create_payload_index(
        collection_name=collection_name,
        field_name="relationships.nl_descriptions",
        field_schema=models.TextIndexParams(
            type=models.TextIndexType.TEXT,
            tokenizer=models.TokenizerType.WORD,
            lowercase=True,
            stemmer=models.SnowballParams(
                type=models.Snowball.SNOWBALL,
                language=models.SnowballLanguage.ENGLISH
            ),
        ),
    )
```

---

## Multi-Module Considerations

For supporting multiple modules (Gmail, Sheets, etc.), we should:

1. **Add module prefix to component names** in payload:
   - `gchat:Button` vs `gmail:Button`
   - Already supported by SymbolGenerator's prefix system

2. **Create separate collections** per module:
   - `mcp_gchat_cards`
   - `mcp_gmail_messages`
   - Keeps indices focused and performant

3. **Or use filtered searches** with a `module` field:
   ```python
   client.scroll(
       scroll_filter=models.Filter(
           must=[
               models.FieldCondition(key="module", match=models.MatchValue(value="gchat")),
               models.FieldCondition(key="name", match=models.MatchText(text="Button")),
           ]
       )
   )
   ```

---

## Implementation Priority

| Feature | Priority | Effort | Benefit |
|---------|----------|--------|---------|
| Phrase matching on `name` | High | Low | Critical for multi-word components |
| Stemming on `nl_descriptions` | High | Low | Better NL query matching |
| Stopwords on `docstring` | Medium | Low | Cleaner searches |
| ASCII folding | Low | Low | Edge case handling |
| Multi-module support | High | Medium | Required for Gmail, Sheets, etc. |

---

## Next Steps

1. Add text index creation to `scripts/initialize_collection.py`
2. Test phrase search for component lookup
3. Benchmark stemmed vs non-stemmed NL queries
4. Plan multi-module collection strategy
