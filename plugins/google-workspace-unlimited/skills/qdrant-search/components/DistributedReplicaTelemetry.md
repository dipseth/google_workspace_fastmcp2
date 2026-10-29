# DistributedReplicaTelemetry

**Symbol:** `D_11`

## Description

Fields: peer_id (int): Peer ID hosting this replica; state (ReplicaState); status (ShardStatus): Shard status; total_optimized_points (int): Total optimized points; vectors_size_bytes (int): Estimated vectors size in bytes; payloads_size_bytes (int): Estimated payloads size in bytes; num_points (int): Approximate number of points; num_vectors (int): Approximate number of vectors; num_vectors_by_name (dict[str, int]): Approximate number of vectors by name; shard_cleaning_status (ShardCleanStatusTelemetryOneOf | ShardCleanStatusTelemetryOneOf1 | ShardCleanStatusTelemetryOneOf2): Shard cleaning task status. After a resharding, a cleanup task is performed to remove outdated points from this shard.; partial_snapshot (PartialSnapshotTelemetry): Partial snapshot telemetry.

## Valid Children

- `P_12` PartialSnapshotTelemetry
- `R_0` ReplicaState
- `□` ShardStatus

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `peer_id` | int | Yes | — | Peer ID hosting this replica |
| `state` | ReplicaState | Yes | — |  |
| `status` | ShardStatus? | No | — | Shard status |
| `total_optimized_points` | int? | No | — | Total optimized points |
| `vectors_size_bytes` | int? | No | — | Estimated vectors size in bytes |
| `payloads_size_bytes` | int? | No | — | Estimated payloads size in bytes |
| `num_points` | int? | No | — | Approximate number of points |
| `num_vectors` | int? | No | — | Approximate number of vectors |
| `num_vectors_by_name` | dict[str, int]? | No | — | Approximate number of vectors by name |
| `shard_cleaning_status` | Union[ShardCleanStatusTelemetryOneOf, ShardCleanStatusTelemetryOneOf1, ShardCleanStatusTelemetryOneOf2, NoneType] | No | — | Shard cleaning task status. After a resharding, a cleanup task is performed to remove outdated points from this shard. |
| `partial_snapshot` | PartialSnapshotTelemetry? | No | — | Partial snapshot telemetry |
