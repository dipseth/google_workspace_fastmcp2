# SetPayload

**Symbol:** `ș`

## Description

This data structure is used in API interface and applied across multiple shards

## Valid Children

- `ƒ` Filter
- `ƒ` Filter
- `ƒ` Filter

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `payload` | dict[str, Any] | Yes | — | This data structure is used in API interface and applied across multiple shards |
| `points` | list[Union[int[int], str[str], UUID]]? | No | — | Assigns payload to each point in this list |
| `filter` | Filter? | No | — | Assigns payload to each point that satisfy this filter condition |
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | This data structure is used in API interface and applied across multiple shards |
| `key` | str? | No | — | Assigns payload to each point that satisfy this path of property |
