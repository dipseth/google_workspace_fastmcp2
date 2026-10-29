# SearchGroupsRequest

**Symbol:** `S_24`

## Description

Fields: shard_key (int | str | list[int | str] | ShardKeyWithFallback): Specify in which shards to look for the points, if not specified - look in all shards; vector (list[float] | NamedVector | NamedSparseVector); filter (Filter): Look only for points which satisfies this conditions; params (SearchParams): Additional search params; with_payload (bool | list[str] | PayloadSelectorInclude | PayloadSelectorExclude): Select which payload to return with the response. Default is false.; with_vector (bool | list[str]): Options for specifying which vectors to include into response. Default is false.; score_threshold (float): Define a minimal score threshold for the result. If defined, less similar results will not be returned. Score of the returned result might be higher or smaller than the threshold depending on the Distance function used. E.g. for cosine similarity only higher scores will be returned.; group_by (str): Payload field to group by, must be a string or number field. If the field contains more than 1 value, all values will be used for grouping. One point can be in multiple groups.; group_size (int): Maximum amount of points to return per group; limit (int): Maximum amount of groups to return; with_lookup (str | WithLookup): Look for points in another collection using the group ids.

## Valid Children

- `ƒ` Filter
- `♦` SearchParams

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
| `vector` | Union[list[float[float]], NamedVector, NamedSparseVector] | Yes | — |  |
| `filter` | Filter? | No | — | Look only for points which satisfies this conditions |
| `params` | SearchParams? | No | — | Additional search params |
| `with_payload` | Union[bool[bool], list[str[str]], PayloadSelectorInclude, PayloadSelectorExclude, NoneType] | No | — | Select which payload to return with the response. Default is false. |
| `with_vector` | Union[bool[bool], list[str[str]], NoneType] | No | — | Options for specifying which vectors to include into response. Default is false. |
| `score_threshold` | float? | No | — | Define a minimal score threshold for the result. If defined, less similar results will not be returned. Score of the returned result might be higher or smaller than the threshold depending on the Distance function used. E.g. for cosine similarity only higher scores will be returned. |
| `group_by` | str | Yes | — | Payload field to group by, must be a string or number field. If the field contains more than 1 value, all values will be used for grouping. One point can be in multiple groups. |
| `group_size` | int | Yes | — | Maximum amount of points to return per group |
| `limit` | int | Yes | — | Maximum amount of groups to return |
| `with_lookup` | Union[str[str], WithLookup, NoneType] | No | — | Look for points in another collection using the group ids |
