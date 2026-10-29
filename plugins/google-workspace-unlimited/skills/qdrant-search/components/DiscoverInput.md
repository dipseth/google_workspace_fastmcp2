# DiscoverInput

**Symbol:** `D_6`

## Description

Fields: target (list[float] | SparseVector | list[list[float]] | int | str | UUID | Document | Image | InferenceObject); context (list[ContextPair] | ContextPair): Search space will be constrained by these pairs of vectors.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `target` | Union[list[float[float]], SparseVector, list[list[float[float]]], int[int], str[str], UUID, Document, Image, InferenceObject] | Yes | — |  |
| `context` | Union[list[ContextPair], ContextPair] | Yes | — | Search space will be constrained by these pairs of vectors |
