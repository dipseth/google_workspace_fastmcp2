# HnswConfig

**Symbol:** `Ħ`

## Description

Config of HNSW index

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `m` | int | Yes | — | Number of edges per node in the index graph. Larger the value - more accurate the search, more space required. |
| `ef_construct` | int | Yes | — | Number of neighbours to consider during the index building. Larger the value - more accurate the search, more time required to build index. |
| `full_scan_threshold` | int | Yes | — | Minimal size threshold (in KiloBytes) below which full-scan is preferred over HNSW search. This measures the total size of vectors being queried against. When the maximum estimated amount of points that a condition satisfies is smaller than `full_scan_threshold_kb`, the query planner will use full-scan search instead of HNSW index traversal for better performance. Note: 1Kb = 1 vector of size 256 |
| `max_indexing_threads` | int? | No | `0` | Number of parallel threads used for background index building. If 0 - automatically select from 8 to 16. Best to keep between 8 and 16 to prevent likelihood of slow building or broken/inefficient HNSW graphs. On small CPUs, less threads are used. |
| `on_disk` | bool? | No | — | Store HNSW index on disk. If set to false, index will be stored in RAM. Default: false |
| `payload_m` | int? | No | — | Custom M param for hnsw graph built for payload index. If not set, default M will be used. |
| `inline_storage` | bool? | No | — | Store copies of original and quantized vectors within the HNSW index file. Default: false. Enabling this option will trade the search speed for disk usage by reducing amount of random seeks during the search. Requires quantized vectors to be enabled. Multi-vectors are not supported. |
