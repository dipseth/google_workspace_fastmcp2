# Annotated

## Description

Add context-specific metadata to a type.

Example: Annotated[int, runtime_check.Unsigned] indicates to the
hypothetical runtime_check module that this type is an unsigned int.
Every other consumer of this type can ignore this metadata and treat
this type as int.

The first argument to Annotated must be a valid type.

Details:

- It's an error to call `Annotated` with less than two arguments.
- Access the metadata via the ``__metadata__`` attribute::

    assert Annotated[int, '$'].__metadata__ == ('$',)

- Nested Annotated types are flattened::

    assert Annotated[Annotated[T, Ann1, Ann2], Ann3] == Annotated[T, Ann1, Ann2, Ann3]

- Instantiating an annotated type is equivalent to instantiating the
underlying type::

    assert Annotated[C, Ann1](5) == C(5)

- Annotated can be used as a generic type alias::

    type Optimized[T] = Annotated[T, runtime.Optimize()]
    # type checker will treat Optimized[int]
    # as equivalent to Annotated[int, runtime.Optimize()]

    type OptimizedList[T] = Annotated[list[T], runtime.Optimize()]
    # type checker will treat OptimizedList[int]
    # as equivalent to Annotated[list[int], runtime.Optimize()]

- Annotated cannot be used with an unpacked TypeVarTuple::

    type Variadic[*Ts] = Annotated[*Ts, Ann1]  # NOT valid

  This would be equivalent to::

    Annotated[T1, T2, T3, ..., Ann1]

  where T1, T2 etc. are TypeVars, which would be invalid, because
  only one type should be passed to Annotated.
