# QueryResponse

**Symbol:** `Ǫ`

## Description

Fields: id (str | int); embedding (list[float]); sparse_embedding (SparseVector); metadata (dict[str, Any]); document (str); score (float).

## Valid Children

- `○` ScoredPoint

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | str | int | Yes | — |  |
| `embedding` | list[float] | None | Yes | — |  |
| `sparse_embedding` | qdrant_client.http.models.models.SparseVector | None | No | — |  |
| `metadata` | dict[str, Any] | Yes | — |  |
| `document` | str | Yes | — |  |
| `score` | float | Yes | — |  |
