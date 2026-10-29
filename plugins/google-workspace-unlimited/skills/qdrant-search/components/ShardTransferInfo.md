# ShardTransferInfo

**Symbol:** `S_16`

## Description

Fields: shard_id (int); to_shard_id (int): Target shard ID if different than source shard ID Used exclusively with `ReshardingStreamRecords` transfer method.; from_ (int): Source peer id; to (int): Destination peer id; sync (bool): If `true` transfer is a synchronization of a replicas If `false` transfer is a moving of a shard from one peer to another; method (ShardTransferMethod); comment (str): A human-readable report of the transfer progress. Available only on the source peer..

## Valid Children

- `S_29` ShardTransferMethod

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_id` | int | Yes | — |  |
| `to_shard_id` | int? | No | — | Target shard ID if different than source shard ID  Used exclusively with `ReshardingStreamRecords` transfer method. |
| `from_` | int | Yes | — | Source peer id |
| `to` | int | Yes | — | Destination peer id |
| `sync` | bool | Yes | — | If `true` transfer is a synchronization of a replicas If `false` transfer is a moving of a shard from one peer to another |
| `method` | ShardTransferMethod? | No | — |  |
| `comment` | str? | No | — | A human-readable report of the transfer progress. Available only on the source peer. |
