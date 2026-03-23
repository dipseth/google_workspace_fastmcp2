# How the TRPN POC Works — Visual Guide

## 1. What Is a Mancala "State"?

A game state is a snapshot of the board + whose turn it is. The solver computes the **optimal move** for each state.

```
  Player 2: [4] [4] [4] [4] [4] [4]
  Store P2 [0]                     [0] Store P1
  Player 1: [4] [4] [4] [4] [4] [4]

  Current Player: 1
  Legal Moves: [0, 1, 2, 3, 4, 5]  (pit indices with stones)
  Optimal Move: 2                    (computed by negamax solver)
```

---

## 2. How a State Becomes 3 RIC Vectors

Each state is described with 3 natural-language texts, then each text is embedded into a 384-dimensional vector using MiniLM:

```mermaid
graph TD
    STATE["Mancala Board State"] --> CT["Component Text<br/><i>'What IS this state?'</i>"]
    STATE --> IT["Inputs Text<br/><i>'What moves are available?'</i>"]
    STATE --> RT["Relationships Text<br/><i>'How do pieces connect?'</i>"]

    CT --> |"MiniLM embed"| CV["Components Vector<br/>384 dimensions"]
    IT --> |"MiniLM embed"| IV["Inputs Vector<br/>384 dimensions"]
    RT --> |"MiniLM embed"| RV["Relationships Vector<br/>384 dimensions"]

    style CT fill:#ff6b6b,color:#fff
    style IT fill:#4a9eff,color:#fff
    style RT fill:#ffd93d,color:#000
    style CV fill:#ff6b6b,color:#fff
    style IV fill:#4a9eff,color:#fff
    style RV fill:#ffd93d,color:#000
```

### Example Texts for One State

**Component Text** (identity — what IS this?):
```
Mancala Board State
Current Player: 1
Stones: P1=24 P2=24 (stores: 0/0)
Turn: early game (move 0)
Board: [4,4,4,4,4,4] [0] [4,4,4,4,4,4] [0]
```

**Inputs Text** (actions — what can you DO?):
```
Legal moves for Player 1: [0, 1, 2, 3, 4, 5]
  Move 0 (pit 0, 4 stones): sow to pits 1-4
  Move 2 (pit 2, 4 stones): lands in store → EXTRA TURN
  Move 5 (pit 5, 4 stones): sow into opponent side
```

**Relationships Text** (structure — how do pieces CONNECT?):
```
P1 pits: [4,4,4,4,4,4] sum=24  P1 store: 0
P2 pits: [4,4,4,4,4,4] sum=24  P2 store: 0
Extra turn opportunities: pit 2 (lands in store)
Capture threats: none (all pits have stones)
Store advantage: tied (0 vs 0)
```

---

## 3. Training Data: From States to (Query, Candidates) Groups

```mermaid
graph TD
    subgraph IndexPhase["Phase 1: Index 2000 states in Qdrant"]
        S1["State 1<br/>optimal=2"] --> E1["3 vectors"] --> Q["Qdrant<br/>(in-memory)"]
        S2["State 2<br/>optimal=0"] --> E2["3 vectors"] --> Q
        SN["State N<br/>optimal=4"] --> EN["3 vectors"] --> Q
    end

    subgraph QueryPhase["Phase 2: For each state, retrieve candidates"]
        QS["Query State<br/>optimal_move = 2"] --> EMBED["Embed → 3 vectors"]
        EMBED --> SEARCH["Search Qdrant<br/>(20 per vector × 3 = up to 60 candidates)"]
        SEARCH --> DEDUP["Deduplicate → ~25 unique candidates"]
    end

    subgraph LabelPhase["Phase 3: Label candidates"]
        DEDUP --> C1["Candidate A<br/>optimal_move=2<br/>✅ label=1.0"]
        DEDUP --> C2["Candidate B<br/>optimal_move=0<br/>❌ label=0.0"]
        DEDUP --> C3["Candidate C<br/>optimal_move=2<br/>✅ label=1.0"]
        DEDUP --> C4["Candidate D<br/>optimal_move=5<br/>❌ label=0.0"]
        DEDUP --> CN["...~25 candidates"]
    end

    style C1 fill:#00b894,color:#fff
    style C3 fill:#00b894,color:#fff
    style C2 fill:#e17055,color:#fff
    style C4 fill:#e17055,color:#fff
```

**Key insight:** A candidate is "correct" if its **optimal_move matches the query's optimal_move**. The model doesn't need to know the board — it just needs to learn which retrieved state has the same best move.

---

## 4. What the Model Sees (Input Features)

### SimilarityScorer (current working model)

For each (query, candidate) pair, compute 9 features:

```mermaid
graph LR
    subgraph Query["Query State Vectors"]
        QC["q_comp<br/>384D"]
        QI["q_inp<br/>384D"]
        QR["q_rel<br/>384D"]
    end

    subgraph Candidate["Candidate State Vectors"]
        CC["c_comp<br/>384D"]
        CI["c_inp<br/>384D"]
        CR["c_rel<br/>384D"]
    end

    QC --> |cosine sim| SC["sim_c = 0.83"]
    CC --> |cosine sim| SC
    QI --> |cosine sim| SI["sim_i = 0.71"]
    CI --> |cosine sim| SI
    QR --> |cosine sim| SR["sim_r = 0.65"]
    CR --> |cosine sim| SR

    QC --> |L2 norm| NQ1["‖q_comp‖"]
    QI --> |L2 norm| NQ2["‖q_inp‖"]
    QR --> |L2 norm| NQ3["‖q_rel‖"]
    CC --> |L2 norm| NC1["‖c_comp‖"]
    CI --> |L2 norm| NC2["‖c_inp‖"]
    CR --> |L2 norm| NC3["‖c_rel‖"]

    SC --> FEATURES["9 features:<br/>[sim_c, sim_i, sim_r,<br/> ‖q_c‖, ‖q_i‖, ‖q_r‖,<br/> ‖c_c‖, ‖c_i‖, ‖c_r‖]"]
    SI --> FEATURES
    SR --> FEATURES
    NQ1 --> FEATURES
    NQ2 --> FEATURES
    NQ3 --> FEATURES
    NC1 --> FEATURES
    NC2 --> FEATURES
    NC3 --> FEATURES

    FEATURES --> MLP["MLP<br/>9 → 64 → 64 → 1"]
    MLP --> SCORE["Score: 2.31"]

    style SC fill:#6c5ce7,color:#fff
    style SI fill:#6c5ce7,color:#fff
    style SR fill:#6c5ce7,color:#fff
    style SCORE fill:#00b894,color:#fff
```

**vs. multi_dimensional_search (hand-tuned):**
```
Hand-tuned:   score = sim_c × sim_r × sim_i
Learned MLP:  score = MLP([sim_c, sim_i, sim_r, norms...])
```

The MLP can learn non-linear relationships that multiplication cannot express.

---

## 5. How Training Works (Listwise Contrastive Loss)

```mermaid
graph TD
    subgraph OneTrainingStep["One Training Step"]
        QUERY["Query: 'state with optimal_move=2'"]

        QUERY --> SCORE_A["Score candidate A: 2.31 ✅ (move=2)"]
        QUERY --> SCORE_B["Score candidate B: 1.05 ❌ (move=0)"]
        QUERY --> SCORE_C["Score candidate C: 1.87 ✅ (move=2)"]
        QUERY --> SCORE_D["Score candidate D: 0.42 ❌ (move=5)"]

        SCORE_A --> SOFTMAX["Softmax over all K candidates"]
        SCORE_B --> SOFTMAX
        SCORE_C --> SOFTMAX
        SCORE_D --> SOFTMAX

        SOFTMAX --> PRED["Predicted: [0.52, 0.15, 0.33, 0.08]"]

        TARGET["Target:  [0.50, 0.00, 0.50, 0.00]<br/>(equal weight on correct candidates)"]

        PRED --> LOSS["Cross-Entropy Loss"]
        TARGET --> LOSS

        LOSS --> BACKPROP["Backprop → update MLP weights<br/>to push correct candidates' scores UP<br/>and incorrect candidates' scores DOWN"]
    end

    style SCORE_A fill:#00b894,color:#fff
    style SCORE_C fill:#00b894,color:#fff
    style SCORE_B fill:#e17055,color:#fff
    style SCORE_D fill:#e17055,color:#fff
```

**Why this works (vs. binary BCE which failed):**
- BCE sees each candidate independently → can minimize loss by predicting "all negative"
- Listwise sees all K candidates together → MUST rank correct ones higher to reduce loss
- The softmax creates competition between candidates — there's no degenerate solution

---

## 6. At Evaluation Time: What Gets Predicted

```mermaid
sequenceDiagram
    participant T as Test State<br/>(true move = 3)
    participant E as Embedder
    participant Q as Qdrant
    participant M as Model
    participant R as Result

    T->>E: Embed state → 3 vectors
    E->>Q: Search components (top 20)
    E->>Q: Search inputs (top 20)
    E->>Q: Search relationships (top 20)
    Q->>M: ~25 unique candidates<br/>(each with 3 stored vectors)

    Note over M: Score each candidate:<br/>features = cosine_sims + norms<br/>score = MLP(features)

    M->>R: Ranked candidates by score

    Note over R: Top-1: candidate with move=3? → ✅<br/>Top-3: move=3 in top 3? → ✅
```

**The final output is a ranked list of candidates.** "Accuracy" means: does the highest-scoring candidate have the same optimal move as the test state?

---

## 7. How It Compares to Existing Methods

```mermaid
graph TD
    subgraph Methods["All Methods — Same Candidates, Different Scoring"]
        CANDS["~25 candidates<br/>from Qdrant"]

        CANDS --> RRF["Single Pass (RRF)<br/>score = Σ 1/(k+rank)<br/>across 3 vectors"]
        CANDS --> MULTI["Multi-Dimensional<br/>score = sim_c × sim_r × sim_i<br/>(hand-tuned multiplication)"]
        CANDS --> LEARNED["SimilarityScorer<br/>score = MLP(sims, norms)<br/>(learned combination)"]

        RRF --> R1["Top-1 accuracy: ~37%"]
        MULTI --> R2["Top-1 accuracy: ~50%"]
        LEARNED --> R3["Top-1 accuracy: ???%"]
    end

    style RRF fill:#e17055,color:#fff
    style MULTI fill:#ffd93d,color:#000
    style LEARNED fill:#00b894,color:#fff
```

All three methods retrieve the SAME candidates from Qdrant. The only difference is how they **score and rank** those candidates. The question is whether a learned scoring function can beat the hand-tuned one.

---

## 8. Connection to TRM and the Module Wrapper

| POC (Games) | Module Wrapper (Production) |
|---|---|
| Mancala board state | Python module component (class/function) |
| Component text = board snapshot | Component text = class name + type + path |
| Inputs text = legal moves | Inputs text = parameters + description |
| Relationships text = piece connections | Relationships text = DAG parent/child links |
| Optimal move prediction | Correct component selection for DSL |
| MiniLM 384D × 3 | ColBERT 128D × 2 + MiniLM 384D × 1 |

The 3-vector RIC schema is the same. If a learned scorer beats hand-tuned multiplication on games, the same approach should improve component selection in the module wrapper.
