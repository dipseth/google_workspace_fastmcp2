# CollectionParams

**Symbol:** `C_4`

## Description

Fields: vectors (VectorParams | dict[str, VectorParams]); shard_number (int): Number of shards the collection has; sharding_method (ShardingMethod): Sharding method Default is Auto - points are distributed across all available shards Custom - points are distributed across shards according to shard key; replication_factor (int): Number of replicas for each shard; write_consistency_factor (int): Defines how many replicas should apply the operation for us to consider it successful. Increasing this number will make the collection more resilient to inconsistencies, but will also make it fail if not enough replicas are available. Does not have any performance impact.; read_fan_out_factor (int): Defines how many additional replicas should be processing read request at the same time. Default value is Auto, which means that fan-out will be determined automatically based on the busyness of the local replica. Having more than 0 might be useful to smooth latency spikes of individual nodes.; read_fan_out_delay_ms (int): Define number of milliseconds to wait before attempting to read from another replica. This setting can help to reduce latency spikes in case of occasional slow replicas. Default is 0, which means delayed fan out request is disabled.; on_disk_payload (bool): If true - point&#x27;s payload will not be stored in memory. It will be read from the disk every time it is requested. This setting saves RAM by (slightly) increasing the response time. Note: those payload values that are involved in filtering and are indexed - remain in RAM. Default: true; sparse_vectors (dict[str, SparseVectorParams]): Configuration of the sparse vector storage.

## Valid Children

- `S_7` ShardingMethod

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `vectors` | Union[VectorParams, dict[str[str], VectorParams], NoneType] | No | — |  |
| `shard_number` | int? | No | `1` | Number of shards the collection has |
| `sharding_method` | ShardingMethod? | No | — | Sharding method Default is Auto - points are distributed across all available shards Custom - points are distributed across shards according to shard key |
| `replication_factor` | int? | No | `1` | Number of replicas for each shard |
| `write_consistency_factor` | int? | No | `1` | Defines how many replicas should apply the operation for us to consider it successful. Increasing this number will make the collection more resilient to inconsistencies, but will also make it fail if not enough replicas are available. Does not have any performance impact. |
| `read_fan_out_factor` | int? | No | — | Defines how many additional replicas should be processing read request at the same time. Default value is Auto, which means that fan-out will be determined automatically based on the busyness of the local replica. Having more than 0 might be useful to smooth latency spikes of individual nodes. |
| `read_fan_out_delay_ms` | int? | No | — | Define number of milliseconds to wait before attempting to read from another replica. This setting can help to reduce latency spikes in case of occasional slow replicas. Default is 0, which means delayed fan out request is disabled. |
| `on_disk_payload` | bool? | No | `True` | If true - point&#x27;s payload will not be stored in memory. It will be read from the disk every time it is requested. This setting saves RAM by (slightly) increasing the response time. Note: those payload values that are involved in filtering and are indexed - remain in RAM.  Default: true |
| `sparse_vectors` | dict[str, SparseVectorParams]? | No | — | Configuration of the sparse vector storage |
