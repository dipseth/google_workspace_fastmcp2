# Mmr

**Symbol:** `μ`

## Description

Maximal Marginal Relevance (MMR) algorithm for re-ranking the points.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `diversity` | float? | No | — | Tunable parameter for the MMR algorithm. Determines the balance between diversity and relevance.  A higher value favors diversity (dissimilarity to selected results), while a lower value favors relevance (similarity to the query vector).  Must be in the range [0, 1]. Default value is 0.5. |
| `candidates_limit` | int? | No | — | The maximum number of candidates to consider for re-ranking.  If not specified, the `limit` value is used. |
