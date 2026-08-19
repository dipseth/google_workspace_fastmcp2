# SparseVectorParams

**Symbol:** `S_20`

## Description

Params of single sparse vector data storage

## Valid Children

- `S_19` SparseIndexParams
- `ɯ` Modifier

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `index` | SparseIndexParams? | No | — | Custom params for index. If none - values from collection configuration are used. |
| `modifier` | Modifier? | No | — | Configures addition value modifications for sparse vectors. Default: none |
