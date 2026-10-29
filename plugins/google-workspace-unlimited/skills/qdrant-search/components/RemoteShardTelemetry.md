# RemoteShardTelemetry

**Symbol:** `R_17`

## Description

Fields: shard_id (int); peer_id (int); searches (OperationDurationStatistics); updates (OperationDurationStatistics).

## Valid Children

- `O_5` OperationDurationStatistics

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_id` | int | Yes | — |  |
| `peer_id` | int | Yes | — |  |
| `searches` | OperationDurationStatistics? | No | — |  |
| `updates` | OperationDurationStatistics? | No | — |  |
