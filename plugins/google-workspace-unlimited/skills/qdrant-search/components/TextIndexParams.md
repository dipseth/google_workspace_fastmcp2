# TextIndexParams

**Symbol:** `ʈ`

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

- `τ` TextIndexType
- `ƭ` TokenizerType
- `S_3` SnowballParams

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | TextIndexType | Yes | — |  |
| `tokenizer` | TokenizerType? | No | — |  |
| `min_token_len` | int? | No | — | Minimum characters to be tokenized. |
| `max_token_len` | int? | No | — | Maximum characters to be tokenized. |
| `lowercase` | bool? | No | — | If true, lowercase all tokens. Default: true. |
| `ascii_folding` | bool? | No | — | If true, normalize tokens by folding accented characters to ASCII (e.g., 'ação' -&gt; 'acao'). Default: false. |
| `phrase_matching` | bool? | No | — | If true, support phrase matching. Default: false. |
| `stopwords` | Union[Language, StopwordsSet, NoneType] | No | — | Ignore this set of tokens. Can select from predefined languages and/or provide a custom set. |
| `on_disk` | bool? | No | — | If true, store the index on disk. Default: false. |
| `stemmer` | SnowballParams? | No | — | Algorithm for stemming. Default: disabled. |
| `enable_hnsw` | bool? | No | — | Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true. |
