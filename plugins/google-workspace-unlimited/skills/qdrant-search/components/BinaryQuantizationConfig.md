# BinaryQuantizationConfig

**Symbol:** `B_1`

## Description

Fields: always_ram (bool); encoding (BinaryQuantizationEncoding); query_encoding (BinaryQuantizationQueryEncoding): Asymmetric quantization configuration allows a query to have different quantization than stored vectors. It can increase the accuracy of search at the cost of performance..

## Valid Children

- `B_2` BinaryQuantizationEncoding
- `B_3` BinaryQuantizationQueryEncoding

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `always_ram` | bool? | No | — |  |
| `encoding` | BinaryQuantizationEncoding? | No | — |  |
| `query_encoding` | BinaryQuantizationQueryEncoding? | No | — | Asymmetric quantization configuration allows a query to have different quantization than stored vectors. It can increase the accuracy of search at the cost of performance. |
