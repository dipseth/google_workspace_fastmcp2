# InferenceObject

**Symbol:** `I_1`

## Description

WARN: Work-in-progress, unimplemented  Custom object for embedding. Requires inference infrastructure, unimplemented.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `object` | Any | Yes | — | Arbitrary data, used as input for the embedding model. Used if the model requires more than one input or a custom input. |
| `model` | str | Yes | — | Name of the model used to generate the vector. List of available models depends on a provider. |
| `options` | dict[str, Any]? | No | — | Parameters for the model Values of the parameters are model-specific |
