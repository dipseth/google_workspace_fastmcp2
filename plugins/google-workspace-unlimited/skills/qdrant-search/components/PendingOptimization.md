# PendingOptimization

**Symbol:** `P_9`

## Description

Fields: optimizer (str): Name of the optimizer that scheduled this optimization.; segments (list[OptimizationSegmentInfo]): Segments that will be optimized..

## Valid Children

- `O_3` OptimizationSegmentInfo

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `optimizer` | str | Yes | — | Name of the optimizer that scheduled this optimization. |
| `segments` | list[OptimizationSegmentInfo] | Yes | — | Segments that will be optimized. |
