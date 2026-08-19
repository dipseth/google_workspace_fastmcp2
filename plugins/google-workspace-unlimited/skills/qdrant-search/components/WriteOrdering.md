# WriteOrdering

**Symbol:** `ẁ`

## Description

Defines write ordering guarantees for collection operations  * `weak` - write operations may be reordered, works faster, default  * `medium` - write operations go through dynamically selected leader, may be inconsistent for a short period of time in case of leader change  * `strong` - Write operations go through the permanent leader, consistent, but may be unavailable if leader is down
