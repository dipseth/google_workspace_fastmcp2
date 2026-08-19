# DeletePayload

**Symbol:** `D_0`

## Description

This data structure is used in API interface and applied across multiple shards

## Valid Children

- `ƒ` Filter

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `keys` | list[str] | Yes | — | List of payload keys to remove from payload |
| `points` | list[Union[int[int], str[str], UUID]]? | No | — | Deletes values from each point in this list |
| `filter` | Filter? | No | — | Deletes values from points that satisfy this filter condition |
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | This data structure is used in API interface and applied across multiple shards |
