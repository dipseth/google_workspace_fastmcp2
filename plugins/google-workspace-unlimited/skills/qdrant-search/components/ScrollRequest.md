# ScrollRequest

**Symbol:** `S_2`

## Description

Scroll request - paginate over all points which matches given condition

## Valid Children

- `ƒ` Filter

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
| `offset` | Union[int[int], str[str], UUID, NoneType] | No | — | Start ID to read points from. |
| `limit` | int? | No | — | Page size. Default: 10 |
| `filter` | Filter? | No | — | Look only for points which satisfies this conditions. If not provided - all points. |
| `with_payload` | Union[bool[bool], list[str[str]], PayloadSelectorInclude, PayloadSelectorExclude, NoneType] | No | — | Select which payload to return with the response. Default is true. |
| `with_vector` | Union[bool[bool], list[str[str]], NoneType] | No | — | Scroll request - paginate over all points which matches given condition |
| `order_by` | Union[str[str], OrderBy, NoneType] | No | — | Order the records by a payload field. |
