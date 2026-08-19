# Renderable

**Symbol:** `ɽ`

## Description

Renderable adds a 'render' method to subclasses objects.

Subclasses can also define the following special values, which can be set
at runtime by the user as well if need be (although I can't think why):
__SUPPRESS_TAG__ (bool)
  This causes the render method to behave like `to_dict`.

__TAG_OVERRIDE__ (str)
  Renames the root tag from the camelCase class name to the specified string.

Thus, given a fragment like this:
```
class SampleWidget(Renderable):
  sample_tag: str = standard_field()

s = Sample(sample_tag='Hello, my name is Inigo Montoya.')
s.render()
```
you would get
`{'sampleWidget': {'sampleTag': 'Hello, my name is Inigo Montoya.'}}`

However if `SampleWidget` were defined as:
```
class SampleWidget(Renderable):
  __SUPPRESS_TAG__ = True
  sample_tag: str = standard_field()
```
you'd get
`{'sampleTag': 'Hello, my name is Inigo Montoya.'}`

If it had the override set, thus:
```
class SampleWidget(Renderable):
  __TAG_OVERRIDE__ = 'aSampleWidgetClass'
  sample_tag: str = standard_field()
```
the `render` command would produce
`{'aSampleWidgetClass': {'sampleTag': 'Hello, my name is Inigo Montoya.'}}`

NOTE: the `__TAG_OVERRIDE__` is *NOT* camel-cased. What you enter is what you
get.

A subclass can implement their own `render` method, but it must return the
valid Chat API JSON. An examnple of this is the `Card` class which has to add
the `cardId` tag level with the `card` itself at the JSON top level.
