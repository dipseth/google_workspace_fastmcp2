# SnapshotPriority

**Symbol:** `S_12`

## Description

Defines source of truth for snapshot recovery:  `NoSync` means - restore snapshot without *any* additional synchronization. `Snapshot` means - prefer snapshot data over the current state. `Replica` means - prefer existing data over the snapshot.
