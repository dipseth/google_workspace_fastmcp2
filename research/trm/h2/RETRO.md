# H2 POC Retrospective — 2026-03-22

## What We Set Out to Do

Prove that a learned network can outperform hand-tuned heuristics for reranking
candidates retrieved from RIC embeddings in Qdrant, using Mancala as a test bed.

## What Worked

1. **SimilarityScorer V1** — A 4,865-param MLP on 9 cosine similarity features
   beat multiplicative fusion by +7.4% Top-1 (38.4% vs 31.0%). This proves a
   learned nonlinear combination of similarities outperforms hand-tuned multiplication.

2. **Listwise contrastive loss** — Softmax cross-entropy over K candidates per query.
   Binary BCE on individual pairs failed completely (predicted majority class).
   Listwise loss creates competition between candidates — the only loss that works
   for ranking.

3. **Visualization pipeline** — React UI showing board state, all 3 prediction methods
   side-by-side, candidate scoring table, and lookahead tree. Invaluable for debugging.

4. **Solver validation** — Caught that the depth-8 solver has ~26-45% label noise.
   Upgraded to depth-12 with transposition table + iterative deepening.

## What Failed

1. **TinyProjectionNetwork (529K params, full TRM recursion)** — Loss flatlined at
   the "predict majority class" value. Two root causes:
   - Random linear projections destroy MiniLM's learned embedding geometry
   - Binary CE on pairs cannot teach ranking (degenerate local minimum)

2. **Board features in V2** — Adding 21D numerical features (stone counts, captures,
   extra turns) didn't improve val accuracy (36.8% vs 39.3%). The board features
   capture positional info but the signal is diluted by the retrieval bottleneck.

3. **Lookahead search** — Conceptually sound (recursion in game-tree space) but the
   evaluation function is too coarse. All positions score 54.8 ± 0.1 because MiniLM
   embeds all Mancala states nearly identically (0.99+ cosine sim).

## Root Cause Analysis

The fundamental bottleneck is **retrieval coverage**, not scoring:

```
Query: "state where Pit 5 is optimal"
   ↓
Qdrant retrieves 57 candidates
   ↓
NONE of them have optimal_move=5  ← game over, no scorer can fix this
   ↓
All methods predict wrong
```

This happens because:
- 500 indexed states ÷ 6 possible moves = ~83 states per move on average
- Some moves are optimal in rare board configurations → sparse coverage
- MiniLM text embeddings produce 0.99+ cosine similarity across all Mancala states
  → retrieval returns "similar-looking" states, not "same-move" states

**The RIC embedding approach was designed for module wrapping (classes, functions, APIs)
where semantic text differences are large.** Mancala boards differ by stone counts,
not semantics — text embeddings are the wrong tool for this domain.

## Key Metrics

| What | Result |
|------|--------|
| V1 SimilarityScorer Top-1 | 38.4% (+21.4% vs RRF) |
| V2 SimilarityScorer Top-1 | 36.8% (depth-12 labels) |
| TinyProjectionNetwork | 0% (failed to learn) |
| Hand-tuned multi-dim | 31.0% |
| Single-pass RRF | 17.0% |
| Solver depth-8→12 label noise | ~26% |
| Solver depth-8→16 label noise | ~45% |

## What We Learned for the Module Wrapper

1. **Preserve embedding geometry.** Never project through random linear layers.
   Compute similarities in the original space, learn on top.

2. **Listwise loss is mandatory for ranking.** This applies directly to the MW's
   `search_hybrid_multidim()` — a learned scorer should use softmax CE over candidates.

3. **Retrieval coverage matters more than scoring.** If the correct component isn't
   in the candidate set, no scorer can find it. MW should ensure diverse retrieval
   (expand candidate pool, or use multiple retrieval strategies).

4. **Text embeddings work when text differences are meaningful.** MW components
   (DecoratedText vs ButtonList vs Section) have very different text descriptions.
   Mancala states ("pit 3 has 4 stones" vs "pit 3 has 5 stones") don't.

## What Happened Next (Same Session)

### Port to MW domain — DONE, 100% val accuracy
Extracted 500 points from `mcp_gchat_cards_v8` (cloud Qdrant). Trained
SimilarityScorerMW (1,409 params) with listwise contrastive loss. Hit 100%
validation accuracy on 15 held-out groups by epoch 18.

**Why it worked:** MW component similarity range is 0.35-0.99 (vs Mancala's
0.99+). Real semantic differences between Section, Button, DecoratedText, etc.

### Production integration — DONE
Added `search_hybrid_learned()` to `search_mixin.py`. Activated via
`SEARCH_MODE=learned`. Sent 15+ cards via `send_dynamic_card` — all validations
passed, correct components found every time. Graceful fallback to multidim if
torch missing.

### Card builder param issue identified
Scorer finds correct components but builder's `SmartCardBuilder` sometimes fails
to map `card_params` to widget properties (generic "Item 1", "Button 1"). This
is a pre-existing builder issue, not a scorer regression. Needs separate investigation.

## Remaining Next Steps

### 1. Direct position evaluation (HIGH impact, HIGH effort)
Instead of retrieval-based prediction ("find similar states"), train a model to
directly evaluate board positions ("is this a good position for current player?").
Use the game outcome as the label, not the optimal move.

**How:** Encode board as 14D vector + game features → MLP → win probability.
This bypasses retrieval entirely and tests whether a tiny network can learn
Mancala strategy. More relevant to TRM's vision (recursive reasoning about state).

### 3. Try a game where text embeddings discriminate (MEDIUM impact, LOW effort)
Tic-Tac-Toe has much more varied board descriptions ("X controls center" vs
"O has corner advantage"). The cosine similarities will spread wider, giving
the scorer more signal.

**How:** Re-run V1 on TicTacToe (the original H1 POC game). Compare learned
scorer vs multi-dim on a domain where embeddings actually differentiate.

### 4. Hybrid: board-vector retrieval (MEDIUM impact, MEDIUM effort)
Index Mancala states using the 14D board vector directly as a Qdrant vector
(not text embeddings). Retrieval becomes "find states with similar stone
distributions" — much more relevant than "find states with similar text."

**How:** Add a 4th named vector to Qdrant: `board_state` (14D, cosine distance).
Retrieve candidates using board similarity, score with learned MLP.

### 5. Increase training data + persistent Qdrant (LOW impact, LOW effort)
Index 5000+ states to cloud Qdrant for inspection. Better coverage reduces
the retrieval gap. Won't fix the fundamental embedding limitation but may
push accuracy up a few points.

## Files Created

```
research/trm/h2/
  model.py              — TinyProjectionNetwork (failed) + SimilarityScorer (works)
  data_pipeline.py      — Pair-centric + listwise data generation
  train.py              — V1 training (listwise contrastive loss)
  train_v2.py           — V2 training (+ board features + depth-12 solver)
  learned_search.py     — Inference-time search using trained model
  evaluate.py           — Comparison harness (RRF vs multi-dim vs learned)
  lookahead_search.py   — Game-tree lookahead using scorer as eval function
  validate_solver.py    — Mancala solver correctness validation
  HOW_IT_WORKS.md       — Visual guide (Mermaid diagrams)
  RETRO.md              — This file
  viz/
    inference_api.py    — HTTP API + React app server
    index.html          — React visualization UI
  tests/
    test_model.py       — 13 unit tests (all passing)
  mw_extract.py       — Qdrant data extraction for MW domain
  train_mw.py         — MW training (100% val acc)
  mw_groups.json      — 72 extracted query groups from mcp_gchat_cards_v8
  checkpoints/
    best_model.pt       — V1 Mancala checkpoint (4,865 params)
    best_model_v2.pt    — V2 Mancala checkpoint (11,713 params)
    best_model_mw.pt    — MW production checkpoint (1,409 params) ← LIVE

Production integration (outside h2/):
  adapters/module_wrapper/search_mixin.py  — search_hybrid_learned(), _load_learned_model()
  config/settings.py                       — search_mode field (SEARCH_MODE env var)
```
