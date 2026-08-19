# Document

**Symbol:** `ɖ`

## Description

WARN: Work-in-progress, unimplemented  Text document for embedding. Requires inference infrastructure, unimplemented.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `text` | str | Yes | — | Text of the document. This field will be used as input for the embedding model. |
| `model` | str | Yes | — | Name of the model used to generate the vector. List of available models depends on a provider. |
| `options` | Union[dict[str[str], Any], Bm25Config, NoneType] | No | — | Additional options for the model, will be passed to the inference service as-is. See model cards for available options. |
