# DecayParamsExpression

**Symbol:** `D_25`

## Description

Fields: x (float | str | FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter | GeoDistance | DatetimeExpression | DatetimeKeyExpression | MultExpression | SumExpression | NegExpression | AbsExpression | DivExpression | SqrtExpression | PowExpression | ExpExpression | Log10Expression | LnExpression | LinDecayExpression | ExpDecayExpression | GaussDecayExpression); target (float | str | FieldCondition | IsEmptyCondition | IsNullCondition | HasIdCondition | HasVectorCondition | NestedCondition | Filter | GeoDistance | DatetimeExpression | DatetimeKeyExpression | MultExpression | SumExpression | NegExpression | AbsExpression | DivExpression | SqrtExpression | PowExpression | ExpExpression | Log10Expression | LnExpression | LinDecayExpression | ExpDecayExpression | GaussDecayExpression): The target value to start decaying from. Defaults to 0.; scale (float): The scale factor of the decay, in terms of `x`. Defaults to 1.0. Must be a non-zero positive number.; midpoint (float): The midpoint of the decay. Should be between 0 and 1.Defaults to 0.5. Output will be this value when `|x - target| == scale`..

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `x` | Union[float[float], str[str], FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter, GeoDistance, DatetimeExpression, DatetimeKeyExpression, MultExpression, SumExpression, NegExpression, AbsExpression, DivExpression, SqrtExpression, PowExpression, ExpExpression, Log10Expression, LnExpression, LinDecayExpression, ExpDecayExpression, GaussDecayExpression] | Yes | — |  |
| `target` | Union[float[float], str[str], FieldCondition, IsEmptyCondition, IsNullCondition, HasIdCondition, HasVectorCondition, NestedCondition, Filter, GeoDistance, DatetimeExpression, DatetimeKeyExpression, MultExpression, SumExpression, NegExpression, AbsExpression, DivExpression, SqrtExpression, PowExpression, ExpExpression, Log10Expression, LnExpression, LinDecayExpression, ExpDecayExpression, GaussDecayExpression, NoneType] | No | — | The target value to start decaying from. Defaults to 0. |
| `scale` | float? | No | — | The scale factor of the decay, in terms of `x`. Defaults to 1.0. Must be a non-zero positive number. |
| `midpoint` | float? | No | — | The midpoint of the decay. Should be between 0 and 1.Defaults to 0.5. Output will be this value when `|x - target| == scale`. |
