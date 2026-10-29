# PointGroup

**Symbol:** `þ`

## Description

Fields: hits (list[ScoredPoint]): Scored points that have the same value of the group_by key; id (int | str); lookup (Record): Record that has been looked up using the group id.

## Valid Children

- `ρ` Record
- `○` ScoredPoint

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `hits` | list[ScoredPoint] | Yes | — | Scored points that have the same value of the group_by key |
| `id` | Union[int[int], str[str]] | Yes | — |  |
| `lookup` | Record? | No | — | Record that has been looked up using the group id |
