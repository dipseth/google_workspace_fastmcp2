# VectorParams

**Symbol:** `ʋ`

## Description

Params of single vector data storage

## Valid Children

- `Đ` Datatype
- `δ` Distance
- `η` HnswConfigDiff
- `M_3` MultiVectorConfig

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `size` | int | Yes | — | Size of a vectors used |
| `distance` | Distance | Yes | — | Params of single vector data storage |
| `hnsw_config` | HnswConfigDiff? | No | — | Custom params for HNSW index. If none - values from collection configuration are used. |
| `quantization_config` | Union[ScalarQuantization, ProductQuantization, BinaryQuantization, NoneType] | No | — | Custom params for quantization. If none - values from collection configuration are used. |
| `on_disk` | bool? | No | — | If true, vectors are served from disk, improving RAM usage at the cost of latency Default: false |
| `datatype` | Datatype? | No | — | Defines which datatype should be used to represent vectors in the storage. Choosing different datatypes allows to optimize memory usage and performance vs accuracy.  - For `float32` datatype - vectors are stored as single-precision floating point numbers, 4 bytes. - For `float16` datatype - vectors are stored as half-precision floating point numbers, 2 bytes. - For `uint8` datatype - vectors are stored as unsigned 8-bit integers, 1 byte. It expects vector elements to be in range `[0, 255]`. |
| `multivector_config` | MultiVectorConfig? | No | — | Params of single vector data storage |
