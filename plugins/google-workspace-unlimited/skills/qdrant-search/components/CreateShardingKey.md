# CreateShardingKey

**Symbol:** `C_8`

## Description

Fields: shard_key (int | str); shards_number (int): How many shards to create for this key If not specified, will use the default value from config; replication_factor (int): How many replicas to create for each shard If not specified, will use the default value from config; placement (list[int]): Placement of shards for this key List of peer ids, that can be used to place shards for this key If not specified, will be randomly placed among all peers; initial_state (ReplicaState): Initial state of the shards for this key If not specified, will be `Initializing` first and then `Active` Warning: do not change this unless you know what you are doing.

## Valid Children

- `R_0` ReplicaState

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str]] | Yes | — |  |
| `shards_number` | int? | No | — | How many shards to create for this key If not specified, will use the default value from config |
| `replication_factor` | int? | No | — | How many replicas to create for each shard If not specified, will use the default value from config |
| `placement` | list[int]? | No | — | Placement of shards for this key List of peer ids, that can be used to place shards for this key If not specified, will be randomly placed among all peers |
| `initial_state` | ReplicaState? | No | — | Initial state of the shards for this key If not specified, will be `Initializing` first and then `Active` Warning: do not change this unless you know what you are doing |
