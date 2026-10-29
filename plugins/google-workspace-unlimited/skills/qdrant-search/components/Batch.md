# Batch

**Symbol:** `ᵬ`

## Description

Fields: ids (list[int | str | UUID]); vectors (list[list[float]] | list[list[list[float]]] | dict[str, list[list[float] | SparseVector | list[list[float]] | Document | Image | InferenceObject]] | list[Document] | list[Image] | list[InferenceObject]); payloads (list[dict[str, Any]]).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `ids` | list[Union[int[int], str[str], UUID]] | Yes | — |  |
| `vectors` | Union[list[list[float[float]]], list[list[list[float[float]]]], dict[str[str], list[Union[list[float[float]], SparseVector, list[list[float[float]]], Document, Image, InferenceObject]]], list[Document], list[Image], list[InferenceObject]] | Yes | — |  |
| `payloads` | list[dict[str, Any]]? | No | — |  |
