# LocalShardTelemetry

**Symbol:** `L_0`

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

- `□` ShardStatus
- `S_6` SegmentTelemetry
- `O_1` OptimizerTelemetry
- `S_43` ShardUpdateQueueInfo
- `□` ShardStatus
- `S_6` SegmentTelemetry
- `O_1` OptimizerTelemetry
- `S_43` ShardUpdateQueueInfo
- `□` ShardStatus
- `S_6` SegmentTelemetry
- ... and 2 more

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `variant_name` | str? | No | — |  |
| `status` | ShardStatus? | No | — |  |
| `total_optimized_points` | int | Yes | — | Total number of optimized points since the last start. |
| `vectors_size_bytes` | int? | No | — | An ESTIMATION of effective amount of bytes used for vectors Do NOT rely on this number unless you know what you are doing |
| `payloads_size_bytes` | int? | No | — | An estimation of the effective amount of bytes used for payloads Do NOT rely on this number unless you know what you are doing |
| `num_points` | int? | No | — | Sum of segment points This is an approximate number Do NOT rely on this number unless you know what you are doing |
| `num_vectors` | int? | No | — | Sum of number of vectors in all segments This is an approximate number Do NOT rely on this number unless you know what you are doing |
| `num_vectors_by_name` | dict[str, int]? | No | — | Sum of number of vectors across all segments, grouped by their name. This is an approximate number. Do NOT rely on this number unless you know what you are doing |
| `segments` | list[SegmentTelemetry]? | No | — |  |
| `optimizations` | OptimizerTelemetry? | No | — |  |
| `async_scorer` | bool? | No | — |  |
| `indexed_only_excluded_vectors` | dict[str, int]? | No | — |  |
| `update_queue` | ShardUpdateQueueInfo? | No | — | Update queue status |
