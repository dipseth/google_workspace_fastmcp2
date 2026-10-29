# WalConfigDiff

**Symbol:** `ẃ`

## Description

Fields: wal_capacity_mb (int): Size of a single WAL segment in MB; wal_segments_ahead (int): Number of WAL segments to create ahead of actually used ones; wal_retain_closed (int): Number of closed WAL segments to retain.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `wal_capacity_mb` | int? | No | — | Size of a single WAL segment in MB |
| `wal_segments_ahead` | int? | No | — | Number of WAL segments to create ahead of actually used ones |
| `wal_retain_closed` | int? | No | — | Number of closed WAL segments to retain |
