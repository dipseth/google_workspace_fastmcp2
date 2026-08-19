# StrictModeConfig

**Symbol:** `S_14`

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
| `enabled` | bool? | No | — | Whether strict mode is enabled for a collection or not. |
| `max_query_limit` | int? | No | — | Max allowed `limit` parameter for all APIs that don&#x27;t have their own max limit. |
| `max_timeout` | int? | No | — | Max allowed `timeout` parameter. |
| `unindexed_filtering_retrieve` | bool? | No | — | Allow usage of unindexed fields in retrieval based (e.g. search) filters. |
| `unindexed_filtering_update` | bool? | No | — | Allow usage of unindexed fields in filtered updates (e.g. delete by payload). |
| `search_max_hnsw_ef` | int? | No | — | Max HNSW ef value allowed in search parameters. |
| `search_allow_exact` | bool? | No | — | Whether exact search is allowed. |
| `search_max_oversampling` | float? | No | — | Max oversampling value allowed in search. |
| `upsert_max_batchsize` | int? | No | — | Max batchsize when upserting |
| `max_collection_vector_size_bytes` | int? | No | — | Max size of a collections vector storage in bytes, ignoring replicas. |
| `read_rate_limit` | int? | No | — | Max number of read operations per minute per replica |
| `write_rate_limit` | int? | No | — | Max number of write operations per minute per replica |
| `max_collection_payload_size_bytes` | int? | No | — | Max size of a collections payload storage in bytes |
| `max_points_count` | int? | No | — | Max number of points estimated in a collection |
| `filter_max_conditions` | int? | No | — | Max conditions a filter can have. |
| `condition_max_size` | int? | No | — | Max size of a condition, eg. items in `MatchAny`. |
| `multivector_config` | dict[str, StrictModeMultivector]? | No | — | Multivector strict mode configuration |
| `sparse_config` | dict[str, StrictModeSparse]? | No | — | Sparse vector strict mode configuration |
| `max_payload_index_count` | int? | No | — | Max number of payload indexes in a collection |
