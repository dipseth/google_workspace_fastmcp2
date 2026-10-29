# VectorParamsDiff

**Symbol:** `V_0`

## Description

Fields: hnsw_config (HnswConfigDiff): Update params for HNSW index. If empty object - it will be unset.; quantization_config (ScalarQuantization | ProductQuantization | BinaryQuantization | Disabled): Update params for quantization. If none - it is left unchanged.; on_disk (bool): If true, vectors are served from disk, improving RAM usage at the cost of latency.

## Valid Children

- `η` HnswConfigDiff

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `hnsw_config` | HnswConfigDiff? | No | — | Update params for HNSW index. If empty object - it will be unset. |
| `quantization_config` | Union[ScalarQuantization, ProductQuantization, BinaryQuantization, Disabled, NoneType] | No | — | Update params for quantization. If none - it is left unchanged. |
| `on_disk` | bool? | No | — | If true, vectors are served from disk, improving RAM usage at the cost of latency |
