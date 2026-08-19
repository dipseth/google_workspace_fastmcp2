# MessageSendErrors

**Symbol:** `M_4`

## Description

Message send failures for a particular peer

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `count` | int | Yes | — | Message send failures for a particular peer |
| `latest_error` | str? | No | — | Message send failures for a particular peer |
| `latest_error_timestamp` | Union[datetime, date, NoneType] | No | — | Timestamp of the latest error |
