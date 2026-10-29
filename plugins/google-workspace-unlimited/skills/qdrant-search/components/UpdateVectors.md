# UpdateVectors

**Symbol:** `ʉ`

## Description

Fields: points (list[PointVectors]): Points with named vectors; shard_key (int | str | list[int | str] | ShardKeyWithFallback); update_filter (Filter).

## Valid Children

- `ƒ` Filter
- `P_4` PointVectors

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `points` | list[PointVectors] | Yes | — | Points with named vectors |
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — |  |
| `update_filter` | Filter? | No | — |  |
