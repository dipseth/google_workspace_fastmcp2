# TextIndexParams

**Symbol:** `ʈ`

## Description

Fields: type (TextIndexType); tokenizer (TokenizerType); min_token_len (int): Minimum characters to be tokenized.; max_token_len (int): Maximum characters to be tokenized.; lowercase (bool): If true, lowercase all tokens. Default: true.; ascii_folding (bool): If true, normalize tokens by folding accented characters to ASCII (e.g., 'ação' -&gt; 'acao'). Default: false.; phrase_matching (bool): If true, support phrase matching. Default: false.; stopwords (Language | StopwordsSet): Ignore this set of tokens. Can select from predefined languages and/or provide a custom set.; on_disk (bool): If true, store the index on disk. Default: false.; stemmer (SnowballParams): Algorithm for stemming. Default: disabled.; enable_hnsw (bool): Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true..

## Valid Children

- `S_3` SnowballParams
- `τ` TextIndexType
- `ƭ` TokenizerType

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | TextIndexType | Yes | — |  |
| `tokenizer` | TokenizerType? | No | — |  |
| `min_token_len` | int? | No | — | Minimum characters to be tokenized. |
| `max_token_len` | int? | No | — | Maximum characters to be tokenized. |
| `lowercase` | bool? | No | — | If true, lowercase all tokens. Default: true. |
| `ascii_folding` | bool? | No | — | If true, normalize tokens by folding accented characters to ASCII (e.g., 'ação' -&gt; 'acao'). Default: false. |
| `phrase_matching` | bool? | No | — | If true, support phrase matching. Default: false. |
| `stopwords` | Union[Language, StopwordsSet, NoneType] | No | — | Ignore this set of tokens. Can select from predefined languages and/or provide a custom set. |
| `on_disk` | bool? | No | — | If true, store the index on disk. Default: false. |
| `stemmer` | SnowballParams? | No | — | Algorithm for stemming. Default: disabled. |
| `enable_hnsw` | bool? | No | — | Enable HNSW graph building for this payload field. If true, builds additional HNSW links (Need payload_m &gt; 0). Default: true. |
