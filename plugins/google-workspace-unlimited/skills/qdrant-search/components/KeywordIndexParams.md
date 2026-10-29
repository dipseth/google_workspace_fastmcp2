# KeywordIndexParams

**Symbol:** `κ`

## Description

Fields: type (KeywordIndexType); is_tenant (bool): If true - used for tenant optimization. Default: false.; on_disk (bool): If true, store the index on disk. Default: false.; enable_hnsw (bool): Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true..

## Valid Children

- `ĸ` KeywordIndexType

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | KeywordIndexType | Yes | — |  |
| `is_tenant` | bool? | No | — | If true - used for tenant optimization. Default: false. |
| `on_disk` | bool? | No | — | If true, store the index on disk. Default: false. |
| `enable_hnsw` | bool? | No | — | Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true. |
