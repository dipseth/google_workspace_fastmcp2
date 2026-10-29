# PointIdsList

**Symbol:** `P_2`

## Description

Fields: points (list[int | str | UUID]); shard_key (int | str | list[int | str] | ShardKeyWithFallback).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `points` | list[Union[int[int], str[str], UUID]] | Yes | — |  |
| `shard_key` | Union[int[int], str[str], list[Union[int[int], str[str]]], ShardKeyWithFallback, NoneType] | No | — |  |
