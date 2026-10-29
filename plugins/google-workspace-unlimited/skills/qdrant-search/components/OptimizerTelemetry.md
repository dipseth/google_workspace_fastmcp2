# OptimizerTelemetry

**Symbol:** `O_1`

## Description

Fields: status (OptimizersStatusOneOf | OptimizersStatusOneOf1); optimizations (OperationDurationStatistics); log (list[TrackerTelemetry]).

## Valid Children

- `O_5` OperationDurationStatistics
- `T_0` TrackerTelemetry

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `status` | Union[OptimizersStatusOneOf, OptimizersStatusOneOf1] | Yes | — |  |
| `optimizations` | OperationDurationStatistics | Yes | — |  |
| `log` | list[TrackerTelemetry]? | No | — |  |
