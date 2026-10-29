# PointVectors

**Symbol:** `P_4`

## Description

Fields: id (int | str | UUID); vector (list[float] | list[list[float]] | dict[str, list[float] | SparseVector | list[list[float]] | Document | Image | InferenceObject] | Document | Image | InferenceObject).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | Union[int[int], str[str], UUID] | Yes | — |  |
| `vector` | Union[list[float[float]], list[list[float[float]]], dict[str[str], Union[list[float[float]], SparseVector, list[list[float[float]]], Document, Image, InferenceObject]], Document, Image, InferenceObject] | Yes | — |  |
