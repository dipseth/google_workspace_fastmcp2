# FilterSelector

**Symbol:** `F_6`

## Description

Fields: filter (Filter); shard_key (int | str | list[int | str] | ShardKeyWithFallback).

## Valid Children

- `ƒ` Filter

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `filter` | Filter | Yes | — |  |
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — |  |
