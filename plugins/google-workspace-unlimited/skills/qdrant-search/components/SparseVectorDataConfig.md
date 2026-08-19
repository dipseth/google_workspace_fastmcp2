# SparseVectorDataConfig

**Symbol:** `S_27`

## Description

Config of single sparse vector data storage

## Valid Children

- `S_18` SparseIndexConfig
- `ɯ` Modifier

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `index` | SparseIndexConfig | Yes | — | Config of single sparse vector data storage |
| `storage_type` | Union[SparseVectorStorageTypeOneOf, SparseVectorStorageTypeOneOf1, NoneType] | No | — | Config of single sparse vector data storage |
| `modifier` | Modifier? | No | — | Configures addition value modifications for sparse vectors. Default: none |
