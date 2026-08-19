# DatetimeRange

**Symbol:** `D_5`

## Description

Range filter request

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `lt` | Union[datetime, date, NoneType] | No | — | point.key &lt; range.lt |
| `gt` | Union[datetime, date, NoneType] | No | — | point.key &gt; range.gt |
| `gte` | Union[datetime, date, NoneType] | No | — | point.key &gt;= range.gte |
| `lte` | Union[datetime, date, NoneType] | No | — | point.key &lt;= range.lte |
