# HnswConfigDiff

**Symbol:** `η`

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
| `m` | int? | No | — | Number of edges per node in the index graph. Larger the value - more accurate the search, more space required. |
| `ef_construct` | int? | No | — | Number of neighbours to consider during the index building. Larger the value - more accurate the search, more time required to build the index. |
| `full_scan_threshold` | int? | No | — | Minimal size threshold (in KiloBytes) below which full-scan is preferred over HNSW search. This measures the total size of vectors being queried against. When the maximum estimated amount of points that a condition satisfies is smaller than `full_scan_threshold_kb`, the query planner will use full-scan search instead of HNSW index traversal for better performance. Note: 1Kb = 1 vector of size 256 |
| `max_indexing_threads` | int? | No | — | Number of parallel threads used for background index building. If 0 - automatically select from 8 to 16. Best to keep between 8 and 16 to prevent likelihood of building broken/inefficient HNSW graphs. On small CPUs, less threads are used. |
| `on_disk` | bool? | No | — | Store HNSW index on disk. If set to false, the index will be stored in RAM. Default: false |
| `payload_m` | int? | No | — | Custom M param for additional payload-aware HNSW links. If not set, default M will be used. |
| `inline_storage` | bool? | No | — | Store copies of original and quantized vectors within the HNSW index file. Default: false. Enabling this option will trade the search speed for disk usage by reducing amount of random seeks during the search. Requires quantized vectors to be enabled. Multi-vectors are not supported. |
