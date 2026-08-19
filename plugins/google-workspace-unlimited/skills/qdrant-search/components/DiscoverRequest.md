# DiscoverRequest

**Symbol:** `D_4`

## Description

Use context and a target to find the most similar points, constrained by the context.

## Valid Children

- `C_14` ContextExamplePair
- `ƒ` Filter
- `ɭ` LookupLocation
- `♦` SearchParams

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
| `target` | Union[int[int], str[str], UUID, list[float[float]], SparseVector, NoneType] | No | — | Look for vectors closest to this.  When using the target (with or without context), the integer part of the score represents the rank with respect to the context, while the decimal part of the score relates to the distance to the target. |
| `context` | list[ContextExamplePair]? | No | — | Pairs of { positive, negative } examples to constrain the search.  When using only the context (without a target), a special search - called context search - is performed where pairs of points are used to generate a loss that guides the search towards the zone where most positive examples overlap. This means that the score minimizes the scenario of finding a point closer to a negative than to a positive part of a pair.  Since the score of a context relates to loss, the maximum score a point can get is 0.0, and it becomes normal that many points can have a score of 0.0.  For discovery search (when including a target), the context part of the score for each pair is calculated +1 if the point is closer to a positive than to a negative part of a pair, and -1 otherwise. |
| `filter` | Filter? | No | — | Look only for points which satisfies this conditions |
| `params` | SearchParams? | No | — | Additional search params |
| `limit` | int | Yes | — | Max number of result to return |
| `offset` | int? | No | — | Offset of the first result to return. May be used to paginate results. Note: large offset values may cause performance issues. |
| `with_payload` | Union[bool[bool], list[str[str]], PayloadSelectorInclude, PayloadSelectorExclude, NoneType] | No | — | Select which payload to return with the response. Default is false. |
| `with_vector` | Union[bool[bool], list[str[str]], NoneType] | No | — | Options for specifying which vectors to include into response. Default is false. |
| `using` | str[str]? | No | — | Define which vector to use for recommendation, if not specified - try to use default vector |
| `lookup_from` | LookupLocation? | No | — | The location used to lookup vectors. If not specified - use current collection. Note: the other collection should have the same vector size as the current collection |
