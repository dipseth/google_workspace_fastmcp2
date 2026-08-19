# Rrf

**Symbol:** `ɽ`

## Description

Parameters for Reciprocal Rank Fusion

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `k` | int? | No | — | K parameter for reciprocal rank fusion |
| `weights` | list[float]? | No | — | Weights for each prefetch source. Higher weight gives more influence on the final ranking. If not specified, all prefetches are weighted equally. The number of weights should match the number of prefetches. |
