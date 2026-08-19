# UpdateCollection

**Symbol:** `U_2`

## Description

Operation for updating parameters of the existing collection

## Valid Children

- `O_7` OptimizersConfigDiff
- `C_28` CollectionParamsDiff
- `η` HnswConfigDiff
- `S_14` StrictModeConfig

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `vectors` | dict[str, VectorParamsDiff]? | No | — | Map of vector data parameters to update for each named vector. To update parameters in a collection having a single unnamed vector, use an empty string as name. |
| `optimizers_config` | OptimizersConfigDiff? | No | — | Custom params for Optimizers.  If none - it is left unchanged. This operation is blocking, it will only proceed once all current optimizations are complete |
| `params` | CollectionParamsDiff? | No | — | Collection base params. If none - it is left unchanged. |
| `hnsw_config` | HnswConfigDiff? | No | — | HNSW parameters to update for the collection index. If none - it is left unchanged. |
| `quantization_config` | Union[ScalarQuantization, ProductQuantization, BinaryQuantization, Disabled, NoneType] | No | — | Quantization parameters to update. If none - it is left unchanged. |
| `sparse_vectors` | dict[str, SparseVectorParams]? | No | — | Map of sparse vector data parameters to update for each sparse vector. |
| `strict_mode_config` | StrictModeConfig? | No | — | Operation for updating parameters of the existing collection |
| `metadata` | dict[str, Any]? | No | — | Metadata to update for the collection. If provided, this will merge with existing metadata. To remove metadata, set it to an empty object. |
