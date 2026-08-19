# SearchGroupsRequest

**Symbol:** `S_24`

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

- `ƒ` Filter
- `♦` SearchParams

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
| `vector` | Union[list[float[float]], NamedVector, NamedSparseVector] | Yes | — |  |
| `filter` | Filter? | No | — | Look only for points which satisfies this conditions |
| `params` | SearchParams? | No | — | Additional search params |
| `with_payload` | Union[bool[bool], list[str[str]], PayloadSelectorInclude, PayloadSelectorExclude, NoneType] | No | — | Select which payload to return with the response. Default is false. |
| `with_vector` | Union[bool[bool], list[str[str]], NoneType] | No | — | Options for specifying which vectors to include into response. Default is false. |
| `score_threshold` | float? | No | — | Define a minimal score threshold for the result. If defined, less similar results will not be returned. Score of the returned result might be higher or smaller than the threshold depending on the Distance function used. E.g. for cosine similarity only higher scores will be returned. |
| `group_by` | str | Yes | — | Payload field to group by, must be a string or number field. If the field contains more than 1 value, all values will be used for grouping. One point can be in multiple groups. |
| `group_size` | int | Yes | — | Maximum amount of points to return per group |
| `limit` | int | Yes | — | Maximum amount of groups to return |
| `with_lookup` | Union[str[str], WithLookup, NoneType] | No | — | Look for points in another collection using the group ids |
