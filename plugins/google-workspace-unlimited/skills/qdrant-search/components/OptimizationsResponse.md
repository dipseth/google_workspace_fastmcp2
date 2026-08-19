# OptimizationsResponse

**Symbol:** `O_2`

## Description

Optimizations progress for the collection

## Valid Children

- `Ω` Optimization
- `O_3` OptimizationSegmentInfo
- `O_6` OptimizationsSummary
- `P_9` PendingOptimization

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `summary` | OptimizationsSummary | Yes | — | Optimizations progress for the collection |
| `running` | list[Optimization] | Yes | — | Currently running optimizations. |
| `queued` | list[PendingOptimization]? | No | — | An estimated queue of pending optimizations. Requires `?with=queued`. |
| `completed` | list[Optimization]? | No | — | Completed optimizations. Requires `?with=completed`. Limited by `?completed_limit=N`. |
| `idle_segments` | list[OptimizationSegmentInfo]? | No | — | Segments that don&#x27;t require optimization. Requires `?with=idle_segments`. |
