# SegmentInfo

**Symbol:** `σ`

## Description

Aggregated information about segment

## Valid Children

- `■` SegmentType
- `ü` UUID

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `uuid` | UUID | Yes | — | Aggregated information about segment |
| `segment_type` | SegmentType | Yes | — | Aggregated information about segment |
| `num_vectors` | int | Yes | — | Aggregated information about segment |
| `num_points` | int | Yes | — | Aggregated information about segment |
| `num_indexed_vectors` | int | Yes | — | Aggregated information about segment |
| `num_deleted_vectors` | int | Yes | — | Aggregated information about segment |
| `vectors_size_bytes` | int | Yes | — | An ESTIMATION of effective amount of bytes used for vectors Do NOT rely on this number unless you know what you are doing |
| `payloads_size_bytes` | int | Yes | — | An estimation of the effective amount of bytes used for payloads |
| `ram_usage_bytes` | int | Yes | — | Aggregated information about segment |
| `disk_usage_bytes` | int | Yes | — | Aggregated information about segment |
| `is_appendable` | bool | Yes | — | Aggregated information about segment |
| `index_schema` | dict[str, PayloadIndexInfo] | Yes | — | Aggregated information about segment |
| `vector_data` | dict[str, VectorDataInfo] | Yes | — | Aggregated information about segment |
