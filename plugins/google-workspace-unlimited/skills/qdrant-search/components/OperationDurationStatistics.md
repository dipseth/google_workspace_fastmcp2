# OperationDurationStatistics

**Symbol:** `O_5`

## Description

Fields: count (int); fail_count (int); avg_duration_micros (float): The average time taken by 128 latest operations, calculated as a weighted mean.; min_duration_micros (float): The minimum duration of the operations across all the measurements.; max_duration_micros (float): The maximum duration of the operations across all the measurements.; total_duration_micros (int): The total duration of all operations in microseconds.; last_responded (datetime | date).

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `count` | int | Yes | — |  |
| `fail_count` | int? | No | — |  |
| `avg_duration_micros` | float? | No | — | The average time taken by 128 latest operations, calculated as a weighted mean. |
| `min_duration_micros` | float? | No | — | The minimum duration of the operations across all the measurements. |
| `max_duration_micros` | float? | No | — | The maximum duration of the operations across all the measurements. |
| `total_duration_micros` | int? | No | — | The total duration of all operations in microseconds. |
| `last_responded` | Union[datetime, date, NoneType] | No | — |  |
