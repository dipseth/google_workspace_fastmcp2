# BoolIndexParams

**Symbol:** `ɓ`

## Description

Fields: type (BoolIndexType); on_disk (bool): If true, store the index on disk. Default: false.; enable_hnsw (bool): Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true..

## Valid Children

- `ℬ` BoolIndexType

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | BoolIndexType | Yes | — |  |
| `on_disk` | bool? | No | — | If true, store the index on disk. Default: false. |
| `enable_hnsw` | bool? | No | — | Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true. |
