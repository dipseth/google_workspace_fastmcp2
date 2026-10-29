# SearchMatrixOffsetsResponse

**Symbol:** `S_38`

## Description

Fields: offsets_row (list[int]): Row indices of the matrix; offsets_col (list[int]): Column indices of the matrix; scores (list[float]): Scores associated with matrix coordinates; ids (list[int | str | UUID]): Ids of the points in order.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `offsets_row` | list[int] | Yes | — | Row indices of the matrix |
| `offsets_col` | list[int] | Yes | — | Column indices of the matrix |
| `scores` | list[float] | Yes | — | Scores associated with matrix coordinates |
| `ids` | list[Union[int[int], str[str], UUID]] | Yes | — | Ids of the points in order |
