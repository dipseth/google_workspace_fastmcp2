# VectorIndexSearchesTelemetry

**Symbol:** `V_1`

## Description

Fields: index_name (str); unfiltered_plain (OperationDurationStatistics); unfiltered_hnsw (OperationDurationStatistics); unfiltered_sparse (OperationDurationStatistics); filtered_plain (OperationDurationStatistics); filtered_small_cardinality (OperationDurationStatistics); filtered_large_cardinality (OperationDurationStatistics); filtered_exact (OperationDurationStatistics); filtered_sparse (OperationDurationStatistics); unfiltered_exact (OperationDurationStatistics).

## Valid Children

- `O_5` OperationDurationStatistics

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `index_name` | str? | No | — |  |
| `unfiltered_plain` | OperationDurationStatistics | Yes | — |  |
| `unfiltered_hnsw` | OperationDurationStatistics | Yes | — |  |
| `unfiltered_sparse` | OperationDurationStatistics | Yes | — |  |
| `filtered_plain` | OperationDurationStatistics | Yes | — |  |
| `filtered_small_cardinality` | OperationDurationStatistics | Yes | — |  |
| `filtered_large_cardinality` | OperationDurationStatistics | Yes | — |  |
| `filtered_exact` | OperationDurationStatistics | Yes | — |  |
| `filtered_sparse` | OperationDurationStatistics | Yes | — |  |
| `unfiltered_exact` | OperationDurationStatistics | Yes | — |  |
