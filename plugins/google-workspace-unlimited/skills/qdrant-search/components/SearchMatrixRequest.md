# SearchMatrixRequest

**Symbol:** `S_25`

## Description

Fields: shard_key (int | str | list[int | str] | ShardKeyWithFallback): Specify in which shards to look for the points, if not specified - look in all shards; filter (Filter): Look only for points which satisfies this conditions; sample (int): How many points to select and search within. Default is 10.; limit (int): How many neighbours per sample to find. Default is 3.; using (str): Define which vector name to use for querying. If missing, the default vector is used..

## Valid Children

- `ƒ` Filter

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
| `filter` | Filter? | No | — | Look only for points which satisfies this conditions |
| `sample` | int? | No | — | How many points to select and search within. Default is 10. |
| `limit` | int? | No | — | How many neighbours per sample to find. Default is 3. |
| `using` | str? | No | — | Define which vector name to use for querying. If missing, the default vector is used. |
