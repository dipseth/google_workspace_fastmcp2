# Tag

## Description

Provides a way to specify the expected tag to use for a case of a (callable) discriminated union.

Also provides a way to label a union case in error messages.

When using a callable `Discriminator`, attach a `Tag` to each case in the `Union` to specify the tag that
should be used to identify that case. For example, in the below example, the `Tag` is used to specify that
if `get_discriminator_value` returns `'apple'`, the input should be validated as an `ApplePie`, and if it
returns `'pumpkin'`, the input should be validated as a `PumpkinPie`.

The primary role of the `Tag` here is to map the return value from the callable `Discriminator` function to
the appropriate member of the `Union` in question.

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

!!! note
    You must specify a `Tag` for every case in a `Tag` that is associated with a
    callable `Discriminator`. Failing to do so will result in a `PydanticUserError` with code
    [`callable-discriminator-no-tag`](../errors/usage_errors.md#callable-discriminator-no-tag).

See the [Discriminated Unions] concepts docs for more details on how to use `Tag`s.

[Discriminated Unions]: ../concepts/unions.md#discriminated-unions
