# Embeddings

> **Status:** Coming soon

This document will cover multi-vector embedding strategies used in ModuleWrapper.

## Planned Topics

### Embedding Models

- **MiniLM (384D)** - Single-vector semantic embeddings
  - Model: `sentence-transformers/all-MiniLM-L6-v2`
  - Use case: Relationship and structural pattern matching
  - Initialization and caching

- **ColBERT (128D)** - Multi-vector late interaction
  - Model: `colbert-ir/colbertv2.0`
  - Use case: Component identity and parameter matching
  - Token-level MaxSim scoring

### V7 Named Vectors

- `components` vector - Component class identity
- `inputs` vector - Parameter value matching
- `relationships` vector - Structural patterns

### Embedding Generation

- Symbol wrapping for deterministic embeddings
- Token ratio truncation for performance
- Batch embedding strategies

### Search Strategies

- Single-vector search (MiniLM)
- Multi-vector search (ColBERT MaxSim)
- Hybrid search with RRF fusion

## Related Files

- `embedding_mixin.py` - EmbeddingMixin implementation
- `search_mixin.py` - Search methods using embeddings
- `pipeline_mixin.py` - V7 ingestion pipeline
