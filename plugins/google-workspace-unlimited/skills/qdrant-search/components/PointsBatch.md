# PointsBatch

**Symbol:** `★`

## Description

Fields: batch (Batch); shard_key (int | str | list[int | str] | ShardKeyWithFallback); update_filter (Filter): Filter to apply when updating existing points. Only points matching this filter will be updated. Points that don&#x27;t match will keep their current state. New points will be inserted regardless of the filter.; update_mode (UpdateMode): Mode of the upsert operation: insert_only, upsert (default), update_only.

## Valid Children

- `ᵬ` Batch
- `ƒ` Filter
- `υ` UpdateMode

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `batch` | Batch | Yes | — |  |
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — |  |
| `update_filter` | Filter? | No | — | Filter to apply when updating existing points. Only points matching this filter will be updated. Points that don&#x27;t match will keep their current state. New points will be inserted regardless of the filter. |
| `update_mode` | UpdateMode? | No | — | Mode of the upsert operation: insert_only, upsert (default), update_only |
