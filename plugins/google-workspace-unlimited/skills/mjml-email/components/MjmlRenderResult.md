# MjmlRenderResult

## Description

Result from rendering an EmailSpec to HTML.

## Valid Children

- MjmlDiagnostic

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `success` | bool | Yes | — |  |
| `html` | str? | No | — |  |
| `normalized_html` | str? | No | — |  |
| `mjml_source` | str? | No | — |  |
| `diagnostics` | list[MjmlDiagnostic] | No | — |  |
