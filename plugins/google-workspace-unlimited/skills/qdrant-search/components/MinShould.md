# MinShould

**Symbol:** `◆`

## Description

Fields: conditions (list[FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter]); min_count (int).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `conditions` | list[Union[FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter]] | Yes | — |  |
| `min_count` | int | Yes | — |  |
