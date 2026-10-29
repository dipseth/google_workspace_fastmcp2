# DivParams

**Symbol:** `◦`

## Description

Fields: left (float | str | FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter | GeoDistance | DatetimeExpression | DatetimeKeyExpression | MultExpression | SumExpression | NegExpression | AbsExpression | DivExpression | SqrtExpression | PowExpression | ExpExpression | Log10Expression | LnExpression | LinDecayExpression | ExpDecayExpression | GaussDecayExpression); right (float | str | FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter | GeoDistance | DatetimeExpression | DatetimeKeyExpression | MultExpression | SumExpression | NegExpression | AbsExpression | DivExpression | SqrtExpression | PowExpression | ExpExpression | Log10Expression | LnExpression | LinDecayExpression | ExpDecayExpression | GaussDecayExpression); by_zero_default (float).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `left` | Union[float[float], str[str], FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter, GeoDistance, DatetimeExpression, DatetimeKeyExpression, MultExpression, SumExpression, NegExpression, AbsExpression, DivExpression, SqrtExpression, PowExpression, ExpExpression, Log10Expression, LnExpression, LinDecayExpression, ExpDecayExpression, GaussDecayExpression] | Yes | — |  |
| `right` | Union[float[float], str[str], FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter, GeoDistance, DatetimeExpression, DatetimeKeyExpression, MultExpression, SumExpression, NegExpression, AbsExpression, DivExpression, SqrtExpression, PowExpression, ExpExpression, Log10Expression, LnExpression, LinDecayExpression, ExpDecayExpression, GaussDecayExpression] | Yes | — |  |
| `by_zero_default` | float? | No | — |  |
