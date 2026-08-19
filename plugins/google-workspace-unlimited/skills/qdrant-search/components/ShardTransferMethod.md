# ShardTransferMethod

**Symbol:** `S_29`

## Description

Methods for transferring a shard from one node to another.  - `stream_records` - Stream all shard records in batches until the whole shard is transferred.  - `snapshot` - Snapshot the shard, transfer and restore it on the receiver.  - `wal_delta` - Attempt to transfer shard difference by WAL delta.  - `resharding_stream_records` - Shard transfer for resharding: stream all records in batches until all points are transferred.
