# FormulaQuery

**Symbol:** `F_2`

## Description

Fields: formula (float | str | FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter | GeoDistance | DatetimeExpression | DatetimeKeyExpression | MultExpression | SumExpression | NegExpression | AbsExpression | DivExpression | SqrtExpression | PowExpression | ExpExpression | Log10Expression | LnExpression | LinDecayExpression | ExpDecayExpression | GaussDecayExpression); defaults (dict[str, Any]).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `formula` | Union[float[float], str[str], FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter, GeoDistance, DatetimeExpression, DatetimeKeyExpression, MultExpression, SumExpression, NegExpression, AbsExpression, DivExpression, SqrtExpression, PowExpression, ExpExpression, Log10Expression, LnExpression, LinDecayExpression, ExpDecayExpression, GaussDecayExpression] | Yes | — |  |
| `defaults` | dict[str, Any]? | No | `{}` |  |
