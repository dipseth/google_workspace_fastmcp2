# Image

**Symbol:** `ɨ`

## Description

WARN: Work-in-progress, unimplemented  Image object for embedding. Requires inference infrastructure, unimplemented.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `image` | Any | Yes | — | Image data: base64 encoded image or an URL |
| `model` | str | Yes | — | Name of the model used to generate the vector. List of available models depends on a provider. |
| `options` | dict[str, Any]? | No | — | Parameters for the model Values of the parameters are model-specific |
