# DistributedCollectionTelemetry

**Symbol:** `D_13`

## Description

Fields: id (str): Collection name; shards (list[DistributedShardTelemetry]): Shards topology; reshardings (list[ReshardingInfo]): Ongoing resharding operations; shard_transfers (list[ShardTransferInfo]): Ongoing shard transfers.

## Valid Children

- `D_16` DistributedShardTelemetry
- `R_1` ReshardingInfo
- `S_16` ShardTransferInfo

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | str | Yes | — | Collection name |
| `shards` | list[DistributedShardTelemetry]? | No | — | Shards topology |
| `reshardings` | list[ReshardingInfo]? | No | — | Ongoing resharding operations |
| `shard_transfers` | list[ShardTransferInfo]? | No | — | Ongoing shard transfers |
