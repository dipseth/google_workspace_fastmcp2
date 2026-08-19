# CollectionClusterInfo

**Symbol:** `C_12`

## Description

Current clustering distribution for the collection

## Valid Children

- `λ` LocalShardInfo
- `R_6` RemoteShardInfo
- `S_16` ShardTransferInfo
- `R_1` ReshardingInfo
- `λ` LocalShardInfo
- `R_6` RemoteShardInfo
- `S_16` ShardTransferInfo
- `R_1` ReshardingInfo

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `peer_id` | int | Yes | — | ID of this peer |
| `shard_count` | int | Yes | — | Total number of shards |
| `local_shards` | list[LocalShardInfo] | Yes | — | Local shards |
| `remote_shards` | list[RemoteShardInfo] | Yes | — | Remote shards |
| `shard_transfers` | list[ShardTransferInfo] | Yes | — | Shard transfers |
| `resharding_operations` | list[ReshardingInfo]? | No | — | Resharding operations |
