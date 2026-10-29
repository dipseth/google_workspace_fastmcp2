# SegmentConfig

**Symbol:** `S_4`

## Description

Fields: vector_data (dict[str, VectorDataConfig]); sparse_vector_data (dict[str, SparseVectorDataConfig]); payload_storage_type (PayloadStorageTypeOneOf | PayloadStorageTypeOneOf1 | PayloadStorageTypeOneOf2 | PayloadStorageTypeOneOf3).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `vector_data` | dict[str, VectorDataConfig]? | No | `{}` |  |
| `sparse_vector_data` | dict[str, SparseVectorDataConfig]? | No | — |  |
| `payload_storage_type` | Union[PayloadStorageTypeOneOf, PayloadStorageTypeOneOf1, PayloadStorageTypeOneOf2, PayloadStorageTypeOneOf3] | Yes | — |  |
