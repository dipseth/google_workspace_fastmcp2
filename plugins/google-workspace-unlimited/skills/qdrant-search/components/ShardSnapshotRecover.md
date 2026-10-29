# ShardSnapshotRecover

**Symbol:** `S_36`

## Description

Fields: location (str); priority (SnapshotPriority); checksum (str): Optional SHA256 checksum to verify snapshot integrity before recovery.; api_key (str): Optional API key used when fetching the snapshot from a remote URL..

## Valid Children

- `S_12` SnapshotPriority

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `location` | str | Yes | — |  |
| `priority` | SnapshotPriority? | No | — |  |
| `checksum` | str? | No | — | Optional SHA256 checksum to verify snapshot integrity before recovery. |
| `api_key` | str? | No | — | Optional API key used when fetching the snapshot from a remote URL. |
