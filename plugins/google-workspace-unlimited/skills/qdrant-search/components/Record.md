# Record

**Symbol:** `ρ`

## Description

Point data

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | Union[int[int], str[str], UUID] | Yes | — | Point data |
| `payload` | dict[str, Any]? | No | — | Payload - values assigned to the point |
| `vector` | Union[list[float[float]], list[list[float[float]]], dict[str[str], Union[list[float[float]], SparseVector, list[list[float[float]]]]], NoneType] | No | — | Vector of the point |
| `shard_key` | Union[int[int], str[str], NoneType] | No | — | Shard Key |
| `order_value` | Union[int[int], float[float], NoneType] | No | — | Point data |
