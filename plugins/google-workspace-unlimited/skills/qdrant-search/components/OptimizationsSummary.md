# OptimizationsSummary

**Symbol:** `O_6`

## Description

Fields: queued_optimizations (int): Number of pending optimizations in the queue. Each optimization will take one or more unoptimized segments and produce one optimized segment.; queued_segments (int): Number of unoptimized segments in the queue.; queued_points (int): Number of points in unoptimized segments in the queue.; idle_segments (int): Number of segments that don&#x27;t require optimization..

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `queued_optimizations` | int | Yes | — | Number of pending optimizations in the queue. Each optimization will take one or more unoptimized segments and produce one optimized segment. |
| `queued_segments` | int | Yes | — | Number of unoptimized segments in the queue. |
| `queued_points` | int | Yes | — | Number of points in unoptimized segments in the queue. |
| `idle_segments` | int | Yes | — | Number of segments that don&#x27;t require optimization. |
