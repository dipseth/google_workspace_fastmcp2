# CollectionsAggregatedTelemetry

**Symbol:** `C_22`

## Description

Fields: vectors (int); optimizers_status (OptimizersStatusOneOf | OptimizersStatusOneOf1); params (CollectionParams).

## Valid Children

- `C_4` CollectionParams

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `vectors` | int | Yes | — |  |
| `optimizers_status` | Union[OptimizersStatusOneOf, OptimizersStatusOneOf1] | Yes | — |  |
| `params` | CollectionParams | Yes | — |  |
