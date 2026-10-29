# UuidIndexParams

**Symbol:** `U_3`

## Description

Fields: type (UuidIndexType); is_tenant (bool): If true - used for tenant optimization.; on_disk (bool): If true, store the index on disk. Default: false.; enable_hnsw (bool): Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true..

## Valid Children

- `U_1` UuidIndexType

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | UuidIndexType | Yes | — |  |
| `is_tenant` | bool? | No | — | If true - used for tenant optimization. |
| `on_disk` | bool? | No | — | If true, store the index on disk. Default: false. |
| `enable_hnsw` | bool? | No | — | Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true. |
