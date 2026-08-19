# CollectionParams

**Symbol:** `C_4`

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

## Valid Children

- `S_7` ShardingMethod

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `vectors` | Union[VectorParams, dict[str[str], VectorParams], NoneType] | No | — |  |
| `shard_number` | int? | No | `1` | Number of shards the collection has |
| `sharding_method` | ShardingMethod? | No | — | Sharding method Default is Auto - points are distributed across all available shards Custom - points are distributed across shards according to shard key |
| `replication_factor` | int? | No | `1` | Number of replicas for each shard |
| `write_consistency_factor` | int? | No | `1` | Defines how many replicas should apply the operation for us to consider it successful. Increasing this number will make the collection more resilient to inconsistencies, but will also make it fail if not enough replicas are available. Does not have any performance impact. |
| `read_fan_out_factor` | int? | No | — | Defines how many additional replicas should be processing read request at the same time. Default value is Auto, which means that fan-out will be determined automatically based on the busyness of the local replica. Having more than 0 might be useful to smooth latency spikes of individual nodes. |
| `read_fan_out_delay_ms` | int? | No | — | Define number of milliseconds to wait before attempting to read from another replica. This setting can help to reduce latency spikes in case of occasional slow replicas. Default is 0, which means delayed fan out request is disabled. |
| `on_disk_payload` | bool? | No | `True` | If true - point&#x27;s payload will not be stored in memory. It will be read from the disk every time it is requested. This setting saves RAM by (slightly) increasing the response time. Note: those payload values that are involved in filtering and are indexed - remain in RAM.  Default: true |
| `sparse_vectors` | dict[str, SparseVectorParams]? | No | — | Configuration of the sparse vector storage |
