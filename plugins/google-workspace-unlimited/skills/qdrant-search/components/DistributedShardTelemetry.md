# DistributedShardTelemetry

**Symbol:** `D_16`

## Description

Fields: id (int): Shard ID; key (int | str): Optional shard key; replicas (list[DistributedReplicaTelemetry]): Replica information.

## Valid Children

- `D_11` DistributedReplicaTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | int | Yes | — | Shard ID |
| `key` | Union[int[int], str[str], NoneType] | No | — | Optional shard key |
| `replicas` | list[DistributedReplicaTelemetry] | Yes | — | Replica information |
