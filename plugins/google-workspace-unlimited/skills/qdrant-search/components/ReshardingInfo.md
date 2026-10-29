# ReshardingInfo

**Symbol:** `R_1`

## Description

Fields: direction (ReshardingDirection); shard_id (int); peer_id (int); shard_key (int | str).

## Valid Children

- `R_16` ReshardingDirection

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `direction` | ReshardingDirection | Yes | — |  |
| `shard_id` | int | Yes | — |  |
| `peer_id` | int | Yes | — |  |
| `shard_key` | Union[int[int], str[str], NoneType] | No | — |  |
