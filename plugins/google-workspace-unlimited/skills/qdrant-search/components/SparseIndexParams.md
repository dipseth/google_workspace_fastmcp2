# SparseIndexParams

**Symbol:** `S_19`

## Description

Configuration for sparse inverted index.

## Valid Children

- `Đ` Datatype

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `full_scan_threshold` | int? | No | — | We prefer a full scan search upto (excluding) this number of vectors.  Note: this is number of vectors, not KiloBytes. |
| `on_disk` | bool? | No | — | Store index on disk. If set to false, the index will be stored in RAM. Default: false |
| `datatype` | Datatype? | No | — | Defines which datatype should be used for the index. Choosing different datatypes allows to optimize memory usage and performance vs accuracy.  - For `float32` datatype - vectors are stored as single-precision floating point numbers, 4 bytes. - For `float16` datatype - vectors are stored as half-precision floating point numbers, 2 bytes. - For `uint8` datatype - vectors are quantized to unsigned 8-bit integers, 1 byte. Quantization to fit byte range `[0, 255]` happens during indexing automatically, so the actual vector data does not need to conform to this range. |
