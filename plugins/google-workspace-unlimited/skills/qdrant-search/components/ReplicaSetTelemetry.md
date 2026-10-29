# ReplicaSetTelemetry

**Symbol:** `R_11`

## Description

Fields: id (int); key (int | str); local (LocalShardTelemetry); remote (list[RemoteShardTelemetry]); replicate_states (dict[str, ReplicaState]); partial_snapshot (PartialSnapshotTelemetry).

## Valid Children

- `L_0` LocalShardTelemetry
- `P_12` PartialSnapshotTelemetry
- `R_17` RemoteShardTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | int | Yes | — |  |
| `key` | Union[int[int], str[str], NoneType] | No | — |  |
| `local` | LocalShardTelemetry? | No | — |  |
| `remote` | list[RemoteShardTelemetry] | Yes | — |  |
| `replicate_states` | dict[str, ReplicaState] | Yes | — |  |
| `partial_snapshot` | PartialSnapshotTelemetry? | No | — |  |
