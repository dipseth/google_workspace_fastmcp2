# PointRequest

**Symbol:** `P_3`

## Description

Fields: shard_key (int | str | list[int | str] | ShardKeyWithFallback): Specify in which shards to look for the points, if not specified - look in all shards; ids (list[int | str | UUID]): Look for points with ids; with_payload (bool | list[str] | PayloadSelectorInclude | PayloadSelectorExclude): Select which payload to return with the response. Default is true.; with_vector (bool | list[str]).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
| `ids` | list[Union[int[int], str[str], UUID]] | Yes | — | Look for points with ids |
| `with_payload` | Union[bool[bool], list[str[str]], PayloadSelectorInclude, PayloadSelectorExclude, NoneType] | No | — | Select which payload to return with the response. Default is true. |
| `with_vector` | Union[bool[bool], list[str[str]], NoneType] | No | — |  |
