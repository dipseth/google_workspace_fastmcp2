# StrictModeConfigOutput

**Symbol:** `S_49`

## Description

Fields: enabled (bool): Whether strict mode is enabled for a collection or not.; max_query_limit (int): Max allowed `limit` parameter for all APIs that don&#x27;t have their own max limit.; max_timeout (int): Max allowed `timeout` parameter.; unindexed_filtering_retrieve (bool): Allow usage of unindexed fields in retrieval based (e.g. search) filters.; unindexed_filtering_update (bool): Allow usage of unindexed fields in filtered updates (e.g. delete by payload).; search_max_hnsw_ef (int): Max HNSW value allowed in search parameters.; search_allow_exact (bool): Whether exact search is allowed or not.; search_max_oversampling (float): Max oversampling value allowed in search.; upsert_max_batchsize (int): Max batchsize when upserting; max_collection_vector_size_bytes (int): Max size of a collections vector storage in bytes, ignoring replicas.; read_rate_limit (int): Max number of read operations per minute per replica; write_rate_limit (int): Max number of write operations per minute per replica.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | bool? | No | — | Whether strict mode is enabled for a collection or not. |
| `max_query_limit` | int? | No | — | Max allowed `limit` parameter for all APIs that don&#x27;t have their own max limit. |
| `max_timeout` | int? | No | — | Max allowed `timeout` parameter. |
| `unindexed_filtering_retrieve` | bool? | No | — | Allow usage of unindexed fields in retrieval based (e.g. search) filters. |
| `unindexed_filtering_update` | bool? | No | — | Allow usage of unindexed fields in filtered updates (e.g. delete by payload). |
| `search_max_hnsw_ef` | int? | No | — | Max HNSW value allowed in search parameters. |
| `search_allow_exact` | bool? | No | — | Whether exact search is allowed or not. |
| `search_max_oversampling` | float? | No | — | Max oversampling value allowed in search. |
| `upsert_max_batchsize` | int? | No | — | Max batchsize when upserting |
| `max_collection_vector_size_bytes` | int? | No | — | Max size of a collections vector storage in bytes, ignoring replicas. |
| `read_rate_limit` | int? | No | — | Max number of read operations per minute per replica |
| `write_rate_limit` | int? | No | — | Max number of write operations per minute per replica |
| `max_collection_payload_size_bytes` | int? | No | — | Max size of a collections payload storage in bytes |
| `max_points_count` | int? | No | — | Max number of points estimated in a collection |
| `filter_max_conditions` | int? | No | — | Max conditions a filter can have. |
| `condition_max_size` | int? | No | — | Max size of a condition, eg. items in `MatchAny`. |
| `multivector_config` | dict[str, StrictModeMultivectorOutput]? | No | — | Multivector configuration |
| `sparse_config` | dict[str, StrictModeSparseOutput]? | No | — | Sparse vector configuration |
| `max_payload_index_count` | int? | No | — | Max number of payload indexes in a collection |
