# ReplicateShard

**Symbol:** `R_3`

## Description

Fields: shard_id (int); to_peer_id (int); from_peer_id (int); method (ShardTransferMethod): Method for transferring the shard from one node to another.

## Valid Children

- `S_29` ShardTransferMethod

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_id` | int | Yes | — |  |
| `to_peer_id` | int | Yes | — |  |
| `from_peer_id` | int | Yes | — |  |
| `method` | ShardTransferMethod? | No | — | Method for transferring the shard from one node to another |
