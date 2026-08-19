# SearchParams

**Symbol:** `♦`

## Description

Additional parameters of the search

## Valid Children

- `Å` AcornSearchParams
- `ʔ` QuantizationSearchParams

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `hnsw_ef` | int? | No | — | Params relevant to HNSW index Size of the beam in a beam-search. Larger the value - more accurate the result, more time required for search. |
| `exact` | bool? | No | `False` | Search without approximation. If set to true, search may run long but with exact results. |
| `quantization` | QuantizationSearchParams? | No | — | Quantization params |
| `indexed_only` | bool? | No | `False` | If enabled, the engine will only perform search among indexed or small segments. Using this option prevents slow searches in case of delayed index, but does not guarantee that all uploaded vectors will be included in search results |
| `acorn` | AcornSearchParams? | No | — | ACORN search params |
