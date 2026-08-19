# RecommendRequest

**Symbol:** `R_5`

## Description

Recommendation request. Provides positive and negative examples of the vectors, which can be ids of points that are already stored in the collection, raw vectors, or even ids and vectors combined.  Service should look for the points which are closer to positive examples and at the same time further to negative examples. The concrete way of how to compare negative and positive distances is up to the `strategy` chosen.

## Valid Children

- `R_10` RecommendStrategy
- `ƒ` Filter
- `♦` SearchParams
- `ɭ` LookupLocation
- `R_10` RecommendStrategy
- `ƒ` Filter
- `♦` SearchParams
- `ɭ` LookupLocation

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
| `positive` | list[Union[int[int], str[str], UUID, list[float[float]], SparseVector]]? | No | `[]` | Look for vectors closest to those |
| `negative` | list[Union[int[int], str[str], UUID, list[float[float]], SparseVector]]? | No | `[]` | Try to avoid vectors like this |
| `strategy` | RecommendStrategy? | No | — | How to use positive and negative examples to find the results |
| `filter` | Filter? | No | — | Look only for points which satisfies this conditions |
| `params` | SearchParams? | No | — | Additional search params |
| `limit` | int | Yes | — | Max number of result to return |
| `offset` | int? | No | — | Offset of the first result to return. May be used to paginate results. Note: large offset values may cause performance issues. |
| `with_payload` | Union[bool[bool], list[str[str]], PayloadSelectorInclude, PayloadSelectorExclude, NoneType] | No | — | Select which payload to return with the response. Default is false. |
| `with_vector` | Union[bool[bool], list[str[str]], NoneType] | No | — | Options for specifying which vectors to include into response. Default is false. |
| `score_threshold` | float? | No | — | Define a minimal score threshold for the result. If defined, less similar results will not be returned. Score of the returned result might be higher or smaller than the threshold depending on the Distance function used. E.g. for cosine similarity only higher scores will be returned. |
| `using` | str[str]? | No | — | Define which vector to use for recommendation, if not specified - try to use default vector |
| `lookup_from` | LookupLocation? | No | — | The location used to lookup vectors. If not specified - use current collection. Note: the other collection should have the same vector size as the current collection |
