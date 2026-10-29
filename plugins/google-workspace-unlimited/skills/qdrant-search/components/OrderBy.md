# OrderBy

**Symbol:** `ø`

## Description

Fields: key (str): Payload key to order by; direction (Direction): Direction of ordering: `asc` or `desc`. Default is ascending.; start_from (int | float | datetime | date): Which payload value to start scrolling from. Default is the lowest value for `asc` and the highest for `desc`.

## Valid Children

- `•` Direction

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `key` | str | Yes | — | Payload key to order by |
| `direction` | Direction? | No | — | Direction of ordering: `asc` or `desc`. Default is ascending. |
| `start_from` | Union[int[int], float[float], datetime, date, NoneType] | No | — | Which payload value to start scrolling from. Default is the lowest value for `asc` and the highest for `desc` |
