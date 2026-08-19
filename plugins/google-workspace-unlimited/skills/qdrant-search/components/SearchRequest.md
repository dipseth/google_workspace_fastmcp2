# SearchRequest

**Symbol:** `S_0`

## Description

Search request. Holds all conditions and parameters for the search of most similar points by vector similarity given the filtering restrictions.

## Valid Children

- `ƒ` Filter
- `♦` SearchParams

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
| `vector` | Union[list[float[float]], NamedVector, NamedSparseVector] | Yes | — | Search request. Holds all conditions and parameters for the search of most similar points by vector similarity given the filtering restrictions. |
| `filter` | Filter? | No | — | Look only for points which satisfies this conditions |
| `params` | SearchParams? | No | — | Additional search params |
| `limit` | int | Yes | — | Max number of result to return |
| `offset` | int? | No | — | Offset of the first result to return. May be used to paginate results. Note: large offset values may cause performance issues. |
| `with_payload` | Union[bool[bool], list[str[str]], PayloadSelectorInclude, PayloadSelectorExclude, NoneType] | No | — | Select which payload to return with the response. Default is false. |
| `with_vector` | Union[bool[bool], list[str[str]], NoneType] | No | — | Options for specifying which vectors to include into response. Default is false. |
| `score_threshold` | float? | No | — | Define a minimal score threshold for the result. If defined, less similar results will not be returned. Score of the returned result might be higher or smaller than the threshold depending on the Distance function used. E.g. for cosine similarity only higher scores will be returned. |
