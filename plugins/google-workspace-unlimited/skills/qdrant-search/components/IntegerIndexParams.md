# IntegerIndexParams

**Symbol:** `I_15`

## Description

Fields: type (IntegerIndexType); lookup (bool): If true - support direct lookups. Default is true.; range (bool): If true - support ranges filters. Default is true.; is_principal (bool): If true - use this key to organize storage of the collection data. This option assumes that this key will be used in majority of filtered requests. Default is false.; on_disk (bool): If true, store the index on disk. Default: false. Default is false.; enable_hnsw (bool): Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true..

## Valid Children

- `I_4` IntegerIndexType

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | IntegerIndexType | Yes | — |  |
| `lookup` | bool? | No | — | If true - support direct lookups. Default is true. |
| `range` | bool? | No | — | If true - support ranges filters. Default is true. |
| `is_principal` | bool? | No | — | If true - use this key to organize storage of the collection data. This option assumes that this key will be used in majority of filtered requests. Default is false. |
| `on_disk` | bool? | No | — | If true, store the index on disk. Default: false. Default is false. |
| `enable_hnsw` | bool? | No | — | Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true. |
