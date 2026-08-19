# VectorStorageTypeOneOf3

**Symbol:** `V_6`

## Description

Same as `ChunkedMmap`, but vectors are forced to be locked in RAM In this way we avoid cold requests to disk, but risk to run out of memory  Designed as a replacement for `Memory`, which doesn&#x27;t depend on RocksDB
