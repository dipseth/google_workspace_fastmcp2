# RecommendInput

**Symbol:** `R_2`

## Description

Fields: positive (list[list[float] | SparseVector | list[list[float]] | int | str | UUID | Document | Image | InferenceObject]): Look for vectors closest to the vectors from these points; negative (list[list[float] | SparseVector | list[list[float]] | int | str | UUID | Document | Image | InferenceObject]): Try to avoid vectors like the vector from these points; strategy (RecommendStrategy): How to use the provided vectors to find the results.

## Valid Children

- `R_10` RecommendStrategy

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `positive` | list[Union[list[float[float]], SparseVector, list[list[float[float]]], int[int], str[str], UUID, Document, Image, InferenceObject]]? | No | — | Look for vectors closest to the vectors from these points |
| `negative` | list[Union[list[float[float]], SparseVector, list[list[float[float]]], int[int], str[str], UUID, Document, Image, InferenceObject]]? | No | — | Try to avoid vectors like the vector from these points |
| `strategy` | RecommendStrategy? | No | — | How to use the provided vectors to find the results |
