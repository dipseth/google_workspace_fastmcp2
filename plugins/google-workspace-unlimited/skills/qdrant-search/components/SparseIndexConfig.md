# SparseIndexConfig

**Symbol:** `S_18`

## Description

Configuration for sparse inverted index.

## Valid Children

- `V_2` VectorStorageDatatype

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `full_scan_threshold` | int? | No | — | We prefer a full scan search upto (excluding) this number of vectors.  Note: this is number of vectors, not KiloBytes. |
| `index_type` | Union[SparseIndexTypeOneOf, SparseIndexTypeOneOf1, SparseIndexTypeOneOf2] | Yes | — | Configuration for sparse inverted index. |
| `datatype` | VectorStorageDatatype? | No | — | Datatype used to store weights in the index. |
