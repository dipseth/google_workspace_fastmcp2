# CollectionTelemetry

**Symbol:** `C_10`

## Description

Fields: id (str); init_time_ms (int); config (CollectionConfigTelemetry); shards (list[ReplicaSetTelemetry]); transfers (list[ShardTransferInfo]); resharding (list[ReshardingInfo]); shard_clean_tasks (dict[str, ShardCleanStatusTelemetryOneOf | ShardCleanStatusTelemetryOneOf1 | ShardCleanStatusTelemetryOneOf2]).

## Valid Children

- `C_9` CollectionConfigTelemetry
- `R_11` ReplicaSetTelemetry
- `R_1` ReshardingInfo
- `S_16` ShardTransferInfo

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | str | Yes | — |  |
| `init_time_ms` | int? | No | — |  |
| `config` | CollectionConfigTelemetry? | No | — |  |
| `shards` | list[ReplicaSetTelemetry]? | No | — |  |
| `transfers` | list[ShardTransferInfo]? | No | — |  |
| `resharding` | list[ReshardingInfo]? | No | — |  |
| `shard_clean_tasks` | dict[str, Union[ShardCleanStatusTelemetryOneOf, ShardCleanStatusTelemetryOneOf1, ShardCleanStatusTelemetryOneOf2]]? | No | — |  |
