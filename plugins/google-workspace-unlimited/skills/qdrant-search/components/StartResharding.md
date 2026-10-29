# StartResharding

**Symbol:** `S_9`

## Description

Fields: direction (ReshardingDirection); peer_id (int); shard_key (int | str).

## Valid Children

- `R_16` ReshardingDirection

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `direction` | ReshardingDirection | Yes | — |  |
| `peer_id` | int? | No | — |  |
| `shard_key` | Union[int[int], str[str], NoneType] | No | — |  |
