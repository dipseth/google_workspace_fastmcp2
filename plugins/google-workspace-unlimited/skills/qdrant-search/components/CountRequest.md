# CountRequest

**Symbol:** `ç`

## Description

Count Request Counts the number of points which satisfy the given filter. If filter is not provided, the count of all points in the collection will be returned.

## Valid Children

- `ƒ` Filter

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
| `filter` | Filter? | No | — | Look only for points which satisfies this conditions |
| `exact` | bool? | No | `True` | If true, count exact number of points. If false, count approximate number of points faster. Approximate count might be unreliable during the indexing process. Default: true |
