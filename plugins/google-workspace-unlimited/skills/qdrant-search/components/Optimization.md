# Optimization

**Symbol:** `Ω`

## Description

Fields: uuid (UUID): Unique identifier of the optimization process. After the optimization is complete, a new segment will be created with this UUID.; optimizer (str): Name of the optimizer that performed this optimization.; status (TrackerStatusOneOf | TrackerStatusOneOf1 | TrackerStatusOneOf2); segments (list[OptimizationSegmentInfo]): Segments being optimized. After the optimization is complete, these segments will be replaced by the new optimized segment.; progress (ProgressTree).

## Valid Children

- `O_3` OptimizationSegmentInfo
- `▪` ProgressTree
- `ü` UUID

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `uuid` | UUID | Yes | — | Unique identifier of the optimization process.  After the optimization is complete, a new segment will be created with this UUID. |
| `optimizer` | str | Yes | — | Name of the optimizer that performed this optimization. |
| `status` | Union[TrackerStatusOneOf, TrackerStatusOneOf1, TrackerStatusOneOf2] | Yes | — |  |
| `segments` | list[OptimizationSegmentInfo] | Yes | — | Segments being optimized.  After the optimization is complete, these segments will be replaced by the new optimized segment. |
| `progress` | ProgressTree | Yes | — |  |
