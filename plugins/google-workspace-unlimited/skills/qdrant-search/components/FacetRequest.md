# FacetRequest

**Symbol:** `ɟ`

## Description

Fields: shard_key (int | str | list[int | str] | ShardKeyWithFallback); key (str): Payload key to use for faceting.; limit (int): Max number of hits to return. Default is 10.; filter (Filter): Filter conditions - only consider points that satisfy these conditions.; exact (bool): Whether to do a more expensive exact count for each of the values in the facet. Default is false..

## Valid Children

- `ƒ` Filter

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — |  |
| `key` | str | Yes | — | Payload key to use for faceting. |
| `limit` | int? | No | — | Max number of hits to return. Default is 10. |
| `filter` | Filter? | No | — | Filter conditions - only consider points that satisfy these conditions. |
| `exact` | bool? | No | — | Whether to do a more expensive exact count for each of the values in the facet. Default is false. |
