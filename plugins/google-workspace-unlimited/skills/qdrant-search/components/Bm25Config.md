# Bm25Config

**Symbol:** `Ƀ`

## Description

Configuration of the local bm25 models.

## Valid Children

- `ƭ` TokenizerType
- `S_3` SnowballParams

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `k` | float? | No | `1.2` | Controls term frequency saturation. Higher values mean term frequency has more impact. Default is 1.2 |
| `b` | float? | No | `0.75` | Controls document length normalization. Ranges from 0 (no normalization) to 1 (full normalization). Higher values mean longer documents have less impact. Default is 0.75. |
| `avg_len` | float? | No | `256` | Expected average document length in the collection. Default is 256. |
| `tokenizer` | TokenizerType? | No | — | Configuration of the local bm25 models. |
| `language` | str? | No | — | Defines which language to use for text preprocessing. This parameter is used to construct default stopwords filter and stemmer. To disable language-specific processing, set this to `'language': 'none'`. If not specified, English is assumed. |
| `lowercase` | bool? | No | — | Lowercase the text before tokenization. Default is `true`. |
| `ascii_folding` | bool? | No | — | If true, normalize tokens by folding accented characters to ASCII (e.g., 'ação' -&gt; 'acao'). Default is `false`. |
| `stopwords` | Union[Language, StopwordsSet, NoneType] | No | — | Configuration of the stopwords filter. Supports list of pre-defined languages and custom stopwords. Default: initialized for specified `language` or English if not specified. |
| `stemmer` | SnowballParams? | No | — | Configuration of the stemmer. Processes tokens to their root form. Default: initialized Snowball stemmer for specified `language` or English if not specified. |
| `min_token_len` | int? | No | — | Minimum token length to keep. If token is shorter than this, it will be discarded. Default is `None`, which means no minimum length. |
| `max_token_len` | int? | No | — | Maximum token length to keep. If token is longer than this, it will be discarded. Default is `None`, which means no maximum length. |
