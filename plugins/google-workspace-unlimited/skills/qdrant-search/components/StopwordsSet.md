# StopwordsSet

**Symbol:** `◙`

## Description

Fields: languages (list[Language]): Set of languages to use for stopwords. Multiple pre-defined lists of stopwords can be combined.; custom (list[str]): Custom stopwords set. Will be merged with the languages set..

## Valid Children

- `ŀ` Language

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `languages` | list[Language]? | No | — | Set of languages to use for stopwords. Multiple pre-defined lists of stopwords can be combined. |
| `custom` | list[str]? | No | — | Custom stopwords set. Will be merged with the languages set. |
