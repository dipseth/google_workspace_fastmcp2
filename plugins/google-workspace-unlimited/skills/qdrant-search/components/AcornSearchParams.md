# AcornSearchParams

**Symbol:** `Å`

## Description

ACORN-related search parameters

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enable` | bool? | No | `False` | If true, then ACORN may be used for the HNSW search based on filters selectivity. Improves search recall for searches with multiple low-selectivity payload filters, at cost of performance. |
| `max_selectivity` | float? | No | — | Maximum selectivity of filters to enable ACORN.  If estimated filters selectivity is higher than this value, ACORN will not be used. Selectivity is estimated as: `estimated number of points satisfying the filters / total number of points`.  0.0 for never, 1.0 for always. Default is 0.4. |
