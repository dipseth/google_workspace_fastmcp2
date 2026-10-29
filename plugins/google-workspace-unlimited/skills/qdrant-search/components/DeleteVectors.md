# DeleteVectors

**Symbol:** `D_1`

## Description

Fields: points (list[int | str | UUID]): Deletes values from each point in this list; filter (Filter): Deletes values from points that satisfy this filter condition; vector (list[str]): Vector names; shard_key (int | str | list[int | str] | ShardKeyWithFallback).

## Valid Children

- `ƒ` Filter

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `points` | list[Union[int[int], str[str], UUID]]? | No | — | Deletes values from each point in this list |
| `filter` | Filter? | No | — | Deletes values from points that satisfy this filter condition |
| `vector` | list[str] | Yes | — | Vector names |
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — |  |
