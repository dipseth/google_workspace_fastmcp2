# WalConfig

**Symbol:** `ʍ`

## Description

Fields: wal_capacity_mb (int): Size of a single WAL segment in MB; wal_segments_ahead (int): Number of WAL segments to create ahead of actually used ones; wal_retain_closed (int): Number of closed WAL segments to keep.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `wal_capacity_mb` | int | Yes | — | Size of a single WAL segment in MB |
| `wal_segments_ahead` | int | Yes | — | Number of WAL segments to create ahead of actually used ones |
| `wal_retain_closed` | int? | No | `1` | Number of closed WAL segments to keep |
