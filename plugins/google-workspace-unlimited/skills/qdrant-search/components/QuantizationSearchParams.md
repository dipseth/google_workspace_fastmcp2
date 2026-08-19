# QuantizationSearchParams

**Symbol:** `ʔ`

## Description

Additional parameters of the search

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `ignore` | bool? | No | `False` | If true, quantized vectors are ignored. Default is false. |
| `rescore` | bool? | No | — | If true, use original vectors to re-score top-k results. Might require more time in case if original vectors are stored on disk. If not set, qdrant decides automatically apply rescoring or not. |
| `oversampling` | float? | No | — | Oversampling factor for quantization. Default is 1.0.  Defines how many extra vectors should be pre-selected using quantized index, and then re-scored using original vectors.  For example, if `oversampling` is 2.4 and `limit` is 100, then 240 vectors will be pre-selected using quantized index, and then top-100 will be returned after re-scoring. |
