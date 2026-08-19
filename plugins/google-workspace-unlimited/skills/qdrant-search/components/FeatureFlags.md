# FeatureFlags

**Symbol:** `F_0`

## Description

!!! abstract "Usage Documentation"
    [Models](../concepts/models.md)

A base class for creating Pydantic models.

Attributes:
    __class_vars__: The names of the class variables defined on the model.
    __private_attributes__: Metadata about the private attributes of the model.
    __signature__: The synthesized `__init__` [`Signature`][inspect.Signature] of the model.

    __pydantic_complete__: Whether model building is completed, or if there are still undefined fields.
    __pydantic_core_schema__: The core schema of the model.
    __pydantic_custom_init__: Whether the model has a custom `__init__` function.
    __pydantic_decorators__: Metadata containing the decorators defined on the model.
        This replaces `Model.__validators__` and `Model.__root_validators__` from Pydantic V1.
    __pydantic_generic_metadata__: Metadata for generic models; contains data used for a similar purpose to
        __args__, __origin__, __parameters__ in typing-module generics. May eventually be replaced by these.
    __pydantic_parent_namespace__: Parent namespace of the model, used for automatic rebuilding of models.
    __pydantic_post_init__: The name of the post-init method for the model, if defined.
    __pydantic_root_model__: Whether the model is a [`RootModel`][pydantic.root_model.RootModel].
    __pydantic_serializer__: The `pydantic-core` `SchemaSerializer` used to dump instances of the model.
    __pydantic_validator__: The `pydantic-core` `SchemaValidator` used to validate instances of the model.

    __pydantic_fields__: A dictionary of field names and their corresponding [`FieldInfo`][pydantic.fields.FieldInfo] objects.
    __pydantic_computed_fields__: A dictionary of computed field names and their corresponding [`ComputedFieldInfo`][pydantic.fields.ComputedFieldInfo] objects.

    __pydantic_extra__: A dictionary containing extra values, if [`extra`][pydantic.config.ConfigDict.extra]
        is set to `'allow'`.
    __pydantic_fields_set__: The names of fields explicitly set during instantiation.
    __pydantic_private__: Values of private attributes set on the model instance.

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
