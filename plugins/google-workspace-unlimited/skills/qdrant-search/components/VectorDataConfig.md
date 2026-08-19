# VectorDataConfig

**Symbol:** `ỽ`

## Description

Config of single vector data storage

## Valid Children

- `δ` Distance
- `M_3` MultiVectorConfig
- `V_2` VectorStorageDatatype

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `size` | int | Yes | — | Size/dimensionality of the vectors used |
| `distance` | Distance | Yes | — | Config of single vector data storage |
| `storage_type` | Union[VectorStorageTypeOneOf, VectorStorageTypeOneOf1, VectorStorageTypeOneOf2, VectorStorageTypeOneOf3, VectorStorageTypeOneOf4] | Yes | — | Config of single vector data storage |
| `index` | Union[IndexesOneOf, IndexesOneOf1] | Yes | — | Config of single vector data storage |
| `quantization_config` | Union[ScalarQuantization, ProductQuantization, BinaryQuantization, NoneType] | No | — | Vector specific quantization config that overrides collection config |
| `multivector_config` | MultiVectorConfig? | No | — | Vector specific configuration to enable multiple vectors per point |
| `datatype` | VectorStorageDatatype? | No | — | Vector specific configuration to set specific storage element type |
