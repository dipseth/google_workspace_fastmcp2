# DatetimeIndexParams

**Symbol:** `D_12`

## Description

Fields: type (DatetimeIndexType); is_principal (bool): If true - use this key to organize storage of the collection data. This option assumes that this key will be used in majority of filtered requests.; on_disk (bool): If true, store the index on disk. Default: false.; enable_hnsw (bool): Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true..

## Valid Children

- `D_9` DatetimeIndexType

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | DatetimeIndexType | Yes | — |  |
| `is_principal` | bool? | No | — | If true - use this key to organize storage of the collection data. This option assumes that this key will be used in majority of filtered requests. |
| `on_disk` | bool? | No | — | If true, store the index on disk. Default: false. |
| `enable_hnsw` | bool? | No | — | Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true. |
