# Filter

**Symbol:** `ƒ`

## Description

Fields: should (list[FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter] | FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter): At least one of those conditions should match; min_should (MinShould): At least minimum amount of given conditions should match; must (list[FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter] | FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter): All conditions must match; must_not (list[FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter] | FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter): All conditions must NOT match.

## Valid Children

- `◆` MinShould

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `should` | Union[list[Union[FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter]], FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter, NoneType] | No | — | At least one of those conditions should match |
| `min_should` | MinShould? | No | — | At least minimum amount of given conditions should match |
| `must` | Union[list[Union[FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter]], FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter, NoneType] | No | — | All conditions must match |
| `must_not` | Union[list[Union[FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter]], FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter, NoneType] | No | — | All conditions must NOT match |
