# RemoteShardInfo

**Symbol:** `R_6`

## Description

Fields: shard_id (int): Remote shard id; shard_key (int | str): User-defined sharding key; peer_id (int): Remote peer id; state (ReplicaState).

## Valid Children

- `R_0` ReplicaState

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_id` | int | Yes | — | Remote shard id |
| `shard_key` | Union[int[int], str[str], NoneType] | No | — | User-defined sharding key |
| `peer_id` | int | Yes | — | Remote peer id |
| `state` | ReplicaState | Yes | — |  |
