# GeoIndexParams

**Symbol:** `G_4`

## Description

Fields: type (GeoIndexType); on_disk (bool): If true, store the index on disk. Default: false.; enable_hnsw (bool): Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true..

## Valid Children

- `G_0` GeoIndexType

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | GeoIndexType | Yes | — |  |
| `on_disk` | bool? | No | — | If true, store the index on disk. Default: false. |
| `enable_hnsw` | bool? | No | — | Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true. |
