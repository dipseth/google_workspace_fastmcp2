# SnapshotRecover

**Symbol:** `S_10`

## Description

Fields: location (str): Examples: - URL `http://localhost:8080/collections/my_collection/snapshots/my_snapshot` - Local path `file:///qdrant/snapshots/test_collection-2022-08-04-10-49-10.snapshot`; priority (SnapshotPriority): Defines which data should be used as a source of truth if there are other replicas in the cluster. If set to `Snapshot`, the snapshot will be used as a source of truth, and the current state will be overwritten. If set to `Replica`, the current state will be used as a source of truth, and after recovery if will be synchronized with the snapshot.; checksum (str): Optional SHA256 checksum to verify snapshot integrity before recovery.; api_key (str): Optional API key used when fetching the snapshot from a remote URL..

## Valid Children

- `S_12` SnapshotPriority

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `location` | str | Yes | — | Examples: - URL `http://localhost:8080/collections/my_collection/snapshots/my_snapshot` - Local path `file:///qdrant/snapshots/test_collection-2022-08-04-10-49-10.snapshot` |
| `priority` | SnapshotPriority? | No | — | Defines which data should be used as a source of truth if there are other replicas in the cluster. If set to `Snapshot`, the snapshot will be used as a source of truth, and the current state will be overwritten. If set to `Replica`, the current state will be used as a source of truth, and after recovery if will be synchronized with the snapshot. |
| `checksum` | str? | No | — | Optional SHA256 checksum to verify snapshot integrity before recovery. |
| `api_key` | str? | No | — | Optional API key used when fetching the snapshot from a remote URL. |
