# LookupLocation

**Symbol:** `ɭ`

## Description

Defines a location to use for looking up the vector. Specifies collection and vector field name.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `collection` | str | Yes | — | Name of the collection used for lookup |
| `vector` | str? | No | — | Optional name of the vector field within the collection. If not provided, the default vector field will be used. |
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — | Specify in which shards to look for the points, if not specified - look in all shards |
