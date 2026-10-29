# NearestQuery

**Symbol:** `ɲ`

## Description

Fields: nearest (list[float] | SparseVector | list[list[float]] | int | str | UUID | Document | Image | InferenceObject); mmr (Mmr): Perform MMR (Maximal Marginal Relevance) reranking after search, using the same vector in this query to calculate relevance..

## Valid Children

- `μ` Mmr

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `nearest` | Union[list[float[float]], SparseVector, list[list[float[float]]], int[int], str[str], UUID, Document, Image, InferenceObject] | Yes | — |  |
| `mmr` | Mmr? | No | — | Perform MMR (Maximal Marginal Relevance) reranking after search, using the same vector in this query to calculate relevance. |
