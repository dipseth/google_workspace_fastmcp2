# CreateCollection

**Symbol:** `C_2`

## Description

Operation for creating new collection and (optionally) specify index params

## Valid Children

- `η` HnswConfigDiff
- `O_7` OptimizersConfigDiff
- `S_7` ShardingMethod
- `S_14` StrictModeConfig
- `ẃ` WalConfigDiff

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `vectors` | Union[VectorParams, dict[str[str], VectorParams], NoneType] | No | — | Operation for creating new collection and (optionally) specify index params |
| `shard_number` | int? | No | — | For auto sharding: Number of shards in collection. - Default is 1 for standalone, otherwise equal to the number of nodes - Minimum is 1  For custom sharding: Number of shards in collection per shard group. - Default is 1, meaning that each shard key will be mapped to a single shard - Minimum is 1 |
| `sharding_method` | ShardingMethod? | No | — | Sharding method Default is Auto - points are distributed across all available shards Custom - points are distributed across shards according to shard key |
| `replication_factor` | int? | No | — | Number of shards replicas. Default is 1 Minimum is 1 |
| `write_consistency_factor` | int? | No | — | Defines how many replicas should apply the operation for us to consider it successful. Increasing this number will make the collection more resilient to inconsistencies, but will also make it fail if not enough replicas are available. Does not have any performance impact. |
| `on_disk_payload` | bool? | No | — | If true - point&#x27;s payload will not be stored in memory. It will be read from the disk every time it is requested. This setting saves RAM by (slightly) increasing the response time. Note: those payload values that are involved in filtering and are indexed - remain in RAM.  Default: true |
| `hnsw_config` | HnswConfigDiff? | No | — | Custom params for HNSW index. If none - values from service configuration file are used. |
| `wal_config` | WalConfigDiff? | No | — | Custom params for WAL. If none - values from service configuration file are used. |
| `optimizers_config` | OptimizersConfigDiff? | No | — | Custom params for Optimizers.  If none - values from service configuration file are used. |
| `quantization_config` | Union[ScalarQuantization, ProductQuantization, BinaryQuantization, NoneType] | No | — | Quantization parameters. If none - quantization is disabled. |
| `sparse_vectors` | dict[str, SparseVectorParams]? | No | — | Sparse vector data config. |
| `strict_mode_config` | StrictModeConfig? | No | — | Strict-mode config. |
| `metadata` | dict[str, Any]? | No | — | Arbitrary JSON metadata for the collection This can be used to store application-specific information such as creation time, migration data, inference model info, etc. |
