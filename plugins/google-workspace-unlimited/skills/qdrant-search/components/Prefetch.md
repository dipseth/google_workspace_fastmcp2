# Prefetch

**Symbol:** `¶`

## Description

Fields: prefetch (list[Prefetch] | Prefetch): Sub-requests to perform first. If present, the query will be performed on the results of the prefetches.; query (list[float] | SparseVector | list[list[float]] | int | str | UUID | Document | Image | InferenceObject | NearestQuery | RecommendQuery | DiscoverQuery | ContextQuery | OrderByQuery | FusionQuery | RrfQuery | FormulaQuery | SampleQuery | RelevanceFeedbackQuery): Query to perform. If missing without prefetches, returns points ordered by their IDs.; using (str): Define which vector name to use for querying. If missing, the default vector is used.; filter (Filter): Filter conditions - return only those points that satisfy the specified conditions.; params (SearchParams): Search params for when there is no prefetch; score_threshold (float): Return points with scores better than this threshold.; limit (int): Max number of points to return. Default is 10.; lookup_from (LookupLocation): The location to use for IDs lookup, if not specified - use the current collection and the &#x27;using&#x27; vector Note: the other collection vectors should have the same vector size as the &#x27;using&#x27; vector in the current collection.

## Valid Children

- `ƒ` Filter
- `ɭ` LookupLocation
- `♦` SearchParams

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prefetch` | Union[list[Prefetch], Prefetch, NoneType] | No | — | Sub-requests to perform first. If present, the query will be performed on the results of the prefetches. |
| `query` | Union[list[float[float]], SparseVector, list[list[float[float]]], int[int], str[str], UUID, Document, Image, InferenceObject, NearestQuery, RecommendQuery, DiscoverQuery, ContextQuery, OrderByQuery, FusionQuery, RrfQuery, FormulaQuery, SampleQuery, RelevanceFeedbackQuery, NoneType] | No | — | Query to perform. If missing without prefetches, returns points ordered by their IDs. |
| `using` | str? | No | — | Define which vector name to use for querying. If missing, the default vector is used. |
| `filter` | Filter? | No | — | Filter conditions - return only those points that satisfy the specified conditions. |
| `params` | SearchParams? | No | — | Search params for when there is no prefetch |
| `score_threshold` | float? | No | — | Return points with scores better than this threshold. |
| `limit` | int? | No | — | Max number of points to return. Default is 10. |
| `lookup_from` | LookupLocation? | No | — | The location to use for IDs lookup, if not specified - use the current collection and the &#x27;using&#x27; vector Note: the other collection vectors should have the same vector size as the &#x27;using&#x27; vector in the current collection |
