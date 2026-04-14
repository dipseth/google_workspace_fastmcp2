# RIC-TRM POC: Recursive Vector Arithmetic on Solved Games

Standalone proof-of-concept exploring whether **recursive refinement of RIC (Relationships-Inputs-Components) embeddings** improves search accuracy compared to single-pass retrieval.

Based on the insight that TRM's (Tiny Recursive Models) dual-state recursive loop maps directly onto the module wrapper's 3-vector embedding schema.

## Key Findings

### Multi-Dimensional Scoring: +9.5% Top-1 Accuracy

The most significant result: **cross-dimensional consistency scoring** (scoring candidates across ALL 3 RIC vectors simultaneously) substantially outperforms both RRF fusion and recursive vector arithmetic.

| Method | Top-1 Accuracy | Top-3 Accuracy | Delta |
|--------|---------------|---------------|-------|
| Single-pass (RRF) | 46.5% | 78.0% | baseline |
| **Multi-dimensional (multiply)** | **56.0%** | **78.0%** | **+9.5%** |
| **Multi-dimensional (harmonic)** | **56.0%** | **78.0%** | **+9.5%** |
| Recursive (centroid) | 24.5% | 68.5% | -22.0% |
| Recursive (best_match) | 19.0% | 61.0% | -27.5% |
| Recursive (score_weighted) | 19.5% | 65.5% | -27.0% |
| Recursive (consistency) | 22.0% | 64.5% | -24.5% |

*Tic-Tac-Toe, 2000 train / 200 test states*

### Why Vector Arithmetic Recursion Fails

Recursive vector modification consistently **degrades** search quality (-15% to -28%). The reason:

1. **Regression to the mean**: Centroid cross-pollination averages retrieved vectors, losing the specificity of the original query
2. **Semantic destruction**: Adding/blending embedding vectors doesn't preserve semantic meaning — embeddings encode meaning geometrically, and arithmetic operations destroy that geometry
3. **TRM's network is learned**: TRM's recursion works because the 2-layer network LEARNS meaningful transformations. Pure vector arithmetic is not a substitute.

### Why Multi-Dimensional Scoring Works

The winning approach doesn't modify vectors at all. Instead it:

1. **Expands the candidate pool** (top-20 per vector vs top-5)
2. **Scores each candidate on ALL 3 dimensions** simultaneously (cosine similarity × 3)
3. **Multiplicative combination** rewards candidates that are good across all dimensions, penalizing one-dimensional matches

This is essentially **late fusion with geometric scoring** — it respects the embedding geometry while leveraging all 3 RIC dimensions.

### Implications for the Module Wrapper

1. The RIC 3-vector schema is validated — cross-dimensional consistency is a strong signal
2. **Multi-dimensional scoring should replace or supplement RRF fusion** in the module wrapper's `search_hybrid()` method
3. Recursive vector arithmetic is NOT the path to TRM-style reasoning — a **learned projection network** (Horizon 2) is needed for that
4. The "Horizon 1" approach from the design doc needs revision: pure vector arithmetic doesn't help, but multi-dimensional scoring (a non-recursive improvement) provides immediate value

## Quick Start

```bash
cd research/trm/poc
uv sync

# Run tests (31 tests)
uv run pytest tests/ -v

# Run accuracy comparison (tic-tac-toe, fast)
uv run python evaluation/accuracy.py --game tictactoe --train-size 500 --test-size 100

# Run with larger dataset (clearer signal)
uv run python evaluation/accuracy.py --game tictactoe --train-size 2000 --test-size 200

# Run convergence analysis
uv run python evaluation/convergence.py --game tictactoe --num-queries 50

# Run parameter sweep
uv run python evaluation/convergence.py --game tictactoe --sweep
```

## Architecture

### The Multi-Dimensional Scoring Algorithm (Winner)

```
1. Search each RIC vector independently with expanded pool (top-20)
2. Collect all unique candidates with their stored vectors
3. For each candidate:
   sim_c = cosine(query_components, candidate_components)
   sim_r = cosine(query_relationships, candidate_relationships)
   sim_i = cosine(query_inputs, candidate_inputs)
   score = sim_c × sim_r × sim_i   (multiplicative)
4. Rank by score, return top-K
```

### The Recursive Algorithm (Unsuccessful)

```
For each refinement cycle:
  1. z_H' = normalize(z_H + α·x)              # inject input context
  2. Search Qdrant with z_H' and z_L
  3. Cross-pollinate (4 strategy variants):
     - centroid: average retrieved vectors
     - best_match: move toward top-1 match
     - score_weighted: weighted average
     - consistency: overlap-based reranking
  4. EMA smooth: z_H = 0.9·z_H_new + 0.1·z_H_original
  5. Halt if top-K ranking stabilized
```

### RIC → TRM Mapping

| TRM Concept | RIC Vector | Role |
|-------------|-----------|------|
| z_H (answer state) | Components (384D) | "What IS the answer" |
| z_L (reasoning state) | Relationships (384D) | "How things connect" |
| x (input injection) | Inputs (384D) | "What's available" (constant) |
| Halting (q_head) | Ranking stability | "Is this good enough?" |
| EMA smoothing | 0.9/0.1 blend | Prevents drift |

### Search Strategies Tested

| Strategy | Approach | Result |
|----------|----------|--------|
| **multi_multiply** | Cross-dim cosine × cosine × cosine | **+9.5%** |
| **multi_harmonic** | Harmonic mean of cross-dim cosine | **+9.5%** |
| single_pass | RRF rank fusion | Baseline |
| rec_centroid | Centroid cross-pollination | -22% |
| rec_best_match | Move toward top-1 cross-dim match | -27.5% |
| rec_score_weighted | Score-weighted centroid | -27% |
| rec_consistency | Overlap-based reranking | -24.5% |

### Games as Test Beds

| Game | State Space | Solver | Purpose |
|------|------------|--------|---------|
| Tic-Tac-Toe | ~5K states | Exact (minimax) | Primary test, fast iteration |
| Connect 4 | ~10K sampled | Depth-limited α-β | Larger state space validation |
| Mancala | ~5K sampled | Depth-limited negamax | Variable structure, captures |

## Project Structure

```
research/trm/poc/
├── pyproject.toml              # Dependencies: numpy, qdrant-client, fastembed
├── ric_vectors.py              # RIC embedding generation + Qdrant indexing
├── recursive_search.py         # Recursive engine + multi-dimensional scoring
├── games/
│   ├── base.py                 # Abstract Game interface with RIC text methods
│   ├── tictactoe.py            # Exact solver, full state enumeration
│   ├── connect4.py             # Alpha-beta solver, random sampling
│   └── mancala.py              # Negamax solver, random sampling
├── evaluation/
│   ├── accuracy.py             # Multi-method accuracy comparison
│   └── convergence.py          # Cycle analysis + parameter sweep
└── tests/
    └── test_recursive.py       # 31 tests covering solvers, embeddings, search
```

## Next Steps

1. **Port multi-dimensional scoring to module wrapper** — Add as option in `search_mixin.py`'s `search_hybrid()` alongside RRF
2. **Test on Connect 4 / Mancala** — Validate with larger state spaces
3. **Horizon 2: Learned projection network** — The path to true TRM-style recursion requires a trained network, not vector arithmetic
4. **Training data pipeline** — Use Qdrant tool invocation history as training signal for the projection network

## References

- TRM Paper: "Less is More: Recursive Reasoning with Tiny Networks" (arXiv:2510.04871)
- TRM Analysis: `research/trm/TRM_ANALYSIS.md`
- Full Design Doc: `research/trm/TRM_MW_ANALYSIS.md`
- Module Wrapper RIC: `adapters/module_wrapper/search_mixin.py`
