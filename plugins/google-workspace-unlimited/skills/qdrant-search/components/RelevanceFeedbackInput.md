# RelevanceFeedbackInput

**Symbol:** `R_14`

## Description

Fields: target (list[float] | SparseVector | list[list[float]] | int | str | UUID | Document | Image | InferenceObject); feedback (list[FeedbackItem]); strategy (NaiveFeedbackStrategy).

## Valid Children

- `F_1` FeedbackItem
- `N_2` NaiveFeedbackStrategy

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `target` | Union[list[float[float]], SparseVector, list[list[float[float]]], int[int], str[str], UUID, Document, Image, InferenceObject] | Yes | — |  |
| `feedback` | list[FeedbackItem] | Yes | — |  |
| `strategy` | NaiveFeedbackStrategy | Yes | — |  |
