# LocalShardTelemetry

**Symbol:** `L_0`

## Description

Fields: variant_name (str); status (ShardStatus); total_optimized_points (int): Total number of optimized points since the last start.; vectors_size_bytes (int): An ESTIMATION of effective amount of bytes used for vectors Do NOT rely on this number unless you know what you are doing; payloads_size_bytes (int): An estimation of the effective amount of bytes used for payloads Do NOT rely on this number unless you know what you are doing; num_points (int): Sum of segment points This is an approximate number Do NOT rely on this number unless you know what you are doing; num_vectors (int): Sum of number of vectors in all segments This is an approximate number Do NOT rely on this number unless you know what you are doing; num_vectors_by_name (dict[str, int]): Sum of number of vectors across all segments, grouped by their name. This is an approximate number. Do NOT rely on this number unless you know what you are doing; segments (list[SegmentTelemetry]); optimizations (OptimizerTelemetry); async_scorer (bool); indexed_only_excluded_vectors (dict[str, int]).

## Valid Children

- `O_1` OptimizerTelemetry
- `S_6` SegmentTelemetry
- `□` ShardStatus
- `S_43` ShardUpdateQueueInfo

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `variant_name` | str? | No | — |  |
| `status` | ShardStatus? | No | — |  |
| `total_optimized_points` | int | Yes | — | Total number of optimized points since the last start. |
| `vectors_size_bytes` | int? | No | — | An ESTIMATION of effective amount of bytes used for vectors Do NOT rely on this number unless you know what you are doing |
| `payloads_size_bytes` | int? | No | — | An estimation of the effective amount of bytes used for payloads Do NOT rely on this number unless you know what you are doing |
| `num_points` | int? | No | — | Sum of segment points This is an approximate number Do NOT rely on this number unless you know what you are doing |
| `num_vectors` | int? | No | — | Sum of number of vectors in all segments This is an approximate number Do NOT rely on this number unless you know what you are doing |
| `num_vectors_by_name` | dict[str, int]? | No | — | Sum of number of vectors across all segments, grouped by their name. This is an approximate number. Do NOT rely on this number unless you know what you are doing |
| `segments` | list[SegmentTelemetry]? | No | — |  |
| `optimizations` | OptimizerTelemetry? | No | — |  |
| `async_scorer` | bool? | No | — |  |
| `indexed_only_excluded_vectors` | dict[str, int]? | No | — |  |
| `update_queue` | ShardUpdateQueueInfo? | No | — | Update queue status |
