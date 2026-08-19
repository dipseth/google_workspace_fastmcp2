# Discriminator

## Description

!!! abstract "Usage Documentation"
    [Discriminated Unions with `Callable` `Discriminator`](../concepts/unions.md#discriminated-unions-with-callable-discriminator)

Provides a way to use a custom callable as the way to extract the value of a union discriminator.

This allows you to get validation behavior like you'd get from `Field(discriminator=<field_name>)`,
but without needing to have a single shared field across all the union choices. This also makes it
possible to handle unions of models and primitive types with discriminated-union-style validation errors.
Finally, this allows you to use a custom callable as the way to identify which member of a union a value
belongs to, while still seeing all the performance benefits of a discriminated union.

Consider this example, which is much more performant with the use of `Discriminator` and thus a `TaggedUnion`
than it would be as a normal `Union`.

```python
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Discriminator, Tag

class Pie(BaseModel):
    time_to_cook: int
    num_ingredients: int

class ApplePie(Pie):
    fruit: Literal['apple'] = 'apple'

class PumpkinPie(Pie):
    filling: Literal['pumpkin'] = 'pumpkin'

def get_discriminator_value(v: Any) -> str:
    if isinstance(v, dict):
        return v.get('fruit', v.get('filling'))
    return getattr(v, 'fruit', getattr(v, 'filling', None))

class ThanksgivingDinner(BaseModel):
    dessert: Annotated[
        Union[
            Annotated[ApplePie, Tag('apple')],
            Annotated[PumpkinPie, Tag('pumpkin')],
        ],
        Discriminator(get_discriminator_value),
    ]

apple_variation = ThanksgivingDinner.model_validate(
    {'dessert': {'fruit': 'apple', 'time_to_cook': 60, 'num_ingredients': 8}}
)
print(repr(apple_variation))
'''
ThanksgivingDinner(dessert=ApplePie(time_to_cook=60, num_ingredients=8, fruit='apple'))
'''

pumpkin_variation = ThanksgivingDinner.model_validate(
    {
        'dessert': {
            'filling': 'pumpkin',
            'time_to_cook': 40,
            'num_ingredients': 6,
        }
    }
)
print(repr(pumpkin_variation))
'''
ThanksgivingDinner(dessert=PumpkinPie(time_to_cook=40, num_ingredients=6, filling='pumpkin'))
'''
```

See the [Discriminated Unions] concepts docs for more details on how to use `Discriminator`s.

[Discriminated Unions]: ../concepts/unions.md#discriminated-unions
