# FeatureFlags

**Symbol:** `F_0`

## Description

Fields: all (bool): Magic feature flag that enables all features. Note that this will only be applied to all flags when passed into [`init_feature_flags`].; payload_index_skip_rocksdb (bool): Skip usage of RocksDB in new immutable payload indices. First implemented in Qdrant 1.13.5. Enabled by default in Qdrant 1.14.1.; payload_index_skip_mutable_rocksdb (bool): Skip usage of RocksDB in new mutable payload indices. First implemented in Qdrant 1.15.0. Enabled by default in Qdrant 1.16.0.; payload_storage_skip_rocksdb (bool): Skip usage of RocksDB in new payload storages. On-disk payload storages never use Gridstore. First implemented in Qdrant 1.15.0. Enabled by default in Qdrant 1.16.0.; incremental_hnsw_building (bool): Use incremental HNSW building. Enabled by default in Qdrant 1.14.1.; migrate_rocksdb_id_tracker (bool): Migrate RocksDB based ID trackers into file based ID tracker on start. Enabled by default in Qdrant 1.15.0.; migrate_rocksdb_vector_storage (bool): Migrate RocksDB based vector storages into new format on start. Enabled by default in Qdrant 1.16.1.; migrate_rocksdb_payload_storage (bool): Migrate RocksDB based payload storages into new format on start. Enabled by default in Qdrant 1.16.1.; migrate_rocksdb_payload_indices (bool): Migrate RocksDB based payload indices into new format on start. Rebuilds a new payload index from scratch. Enabled by default in Qdrant 1.16.1.; appendable_quantization (bool): Use appendable quantization in appendable plain segments. Enabled by default in Qdrant 1.16.0.; single_file_mmap_vector_storage (bool): Use single-file mmap in-ram vector storage (InRamMmap) Enabled by default in Qdrant 1.17.1+.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `all` | bool? | No | `False` | Magic feature flag that enables all features.  Note that this will only be applied to all flags when passed into [`init_feature_flags`]. |
| `payload_index_skip_rocksdb` | bool? | No | `True` | Skip usage of RocksDB in new immutable payload indices.  First implemented in Qdrant 1.13.5. Enabled by default in Qdrant 1.14.1. |
| `payload_index_skip_mutable_rocksdb` | bool? | No | `True` | Skip usage of RocksDB in new mutable payload indices.  First implemented in Qdrant 1.15.0. Enabled by default in Qdrant 1.16.0. |
| `payload_storage_skip_rocksdb` | bool? | No | `True` | Skip usage of RocksDB in new payload storages.  On-disk payload storages never use Gridstore.  First implemented in Qdrant 1.15.0. Enabled by default in Qdrant 1.16.0. |
| `incremental_hnsw_building` | bool? | No | `True` | Use incremental HNSW building.  Enabled by default in Qdrant 1.14.1. |
| `migrate_rocksdb_id_tracker` | bool? | No | `True` | Migrate RocksDB based ID trackers into file based ID tracker on start.  Enabled by default in Qdrant 1.15.0. |
| `migrate_rocksdb_vector_storage` | bool? | No | `True` | Migrate RocksDB based vector storages into new format on start.  Enabled by default in Qdrant 1.16.1. |
| `migrate_rocksdb_payload_storage` | bool? | No | `True` | Migrate RocksDB based payload storages into new format on start.  Enabled by default in Qdrant 1.16.1. |
| `migrate_rocksdb_payload_indices` | bool? | No | `True` | Migrate RocksDB based payload indices into new format on start.  Rebuilds a new payload index from scratch.  Enabled by default in Qdrant 1.16.1. |
| `appendable_quantization` | bool? | No | `True` | Use appendable quantization in appendable plain segments.  Enabled by default in Qdrant 1.16.0. |
| `single_file_mmap_vector_storage` | bool? | No | `False` | Use single-file mmap in-ram vector storage (InRamMmap)  Enabled by default in Qdrant 1.17.1+ |
