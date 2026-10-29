# WithLookup

**Symbol:** `ω`

## Description

Fields: collection (str): Name of the collection to use for points lookup; with_payload (bool | list[str] | PayloadSelectorInclude | PayloadSelectorExclude): Options for specifying which payload to include (or not); with_vectors (bool | list[str]): Options for specifying which vectors to include (or not).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `collection` | str | Yes | — | Name of the collection to use for points lookup |
| `with_payload` | Union[bool[bool], list[str[str]], PayloadSelectorInclude, PayloadSelectorExclude, NoneType] | No | — | Options for specifying which payload to include (or not) |
| `with_vectors` | Union[bool[bool], list[str[str]], NoneType] | No | — | Options for specifying which vectors to include (or not) |
