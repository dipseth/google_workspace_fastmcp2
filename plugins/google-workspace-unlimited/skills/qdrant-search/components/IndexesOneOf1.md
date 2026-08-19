# IndexesOneOf1

**Symbol:** `ı`

## Description

Use filterable HNSW index for approximate search. Is very fast even on a very huge collections, but require additional space to store index and additional time to build it.

## Valid Children

- `Ħ` HnswConfig

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | 'hnsw' | Yes | — | Use filterable HNSW index for approximate search. Is very fast even on a very huge collections, but require additional space to store index and additional time to build it. |
| `options` | HnswConfig | Yes | — | Use filterable HNSW index for approximate search. Is very fast even on a very huge collections, but require additional space to store index and additional time to build it. |
