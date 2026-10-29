# LocalShardInfo

**Symbol:** `λ`

## Description

Fields: shard_id (int): Local shard id; shard_key (int | str): User-defined sharding key; points_count (int): Number of points in the shard; state (ReplicaState).

## Valid Children

- `R_0` ReplicaState

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_id` | int | Yes | — | Local shard id |
| `shard_key` | Union[int[int], str[str], NoneType] | No | — | User-defined sharding key |
| `points_count` | int | Yes | — | Number of points in the shard |
| `state` | ReplicaState | Yes | — |  |
