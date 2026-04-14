# Tiny Recursive Model (TRM) — Technical Analysis

**Paper:** "Less is More: Recursive Reasoning with Tiny Networks"
**Author:** Alexia Jolicoeur-Martineau (Samsung SAIL Montreal)
**arXiv:** 2510.04871 (October 2025)
**Repo:** `research/trm/official-repo/` (cloned from SamsungSAILMontreal/TinyRecursiveModels)

---

## 1. WHAT IS TRM?

TRM is a **tiny neural network (7M params, 2 layers)** that solves hard reasoning tasks by **recursively refining its answer** through repeated forward passes. Instead of using a massive model with billions of parameters, TRM uses a single small network that loops over its own output — each pass improving the latent reasoning state and the predicted answer.

**Key claim:** 7M-parameter TRM achieves 45% on ARC-AGI-1 (vs. 37% Gemini 2.5 Pro, 34.5% o3-mini-high) and 87.4% on Sudoku-Extreme (vs. 55% for the predecessor HRM with 27M params).

---

## 2. ARCHITECTURE — THE NETWORK

### 2.1 Components

TRM has exactly **5 learnable components**:

| Component | Role | Shape |
|-----------|------|-------|
| `embed_tokens` | Maps input tokens → embeddings | `[vocab_size, hidden_size]` |
| `puzzle_emb` | Per-puzzle learned embedding (task identity) | `[num_puzzles, emb_dim]` |
| `L_level` | The single recursive network (2 transformer/MLP blocks) | ~5M params |
| `lm_head` | Maps embeddings → output logits | `[hidden_size, vocab_size]` |
| `q_head` | Halting decision head (binary: stop or continue?) | `[hidden_size, 2]` |

Plus two **learned initial states** (buffers, not trained via backprop in the usual sense):
- `H_init` — initial "answer" latent state (z_H)
- `L_init` — initial "reasoning" latent state (z_L)

### 2.2 The Single Block (`TinyRecursiveReasoningModel_ACTV1Block`)

Each block has **two sub-layers** with **post-norm RMS normalization**:

```
Input
  │
  ├──→ [Attention OR MLP-T] ──→ + ──→ RMS Norm ──→
  │         (sequence mixing)    ↑
  │──────────────────────────────┘ (residual)
  │
  ├──→ [SwiGLU MLP] ──→ + ──→ RMS Norm ──→ Output
  │    (channel mixing)  ↑
  │──────────────────────┘ (residual)
```

**Two modes:**
- **Attention mode** (`mlp_t=False`): Standard multi-head self-attention (non-causal) + SwiGLU MLP. Used for variable-length tasks like ARC-AGI.
- **MLP-Mixer mode** (`mlp_t=True`): SwiGLU on the **transposed** sequence dimension (mixes across positions instead of channels) + SwiGLU on channels. Used for fixed-size tasks like Sudoku (where sequence length is constant). **This is the default and best-performing mode.**

### 2.3 Default Configuration

```yaml
H_cycles: 3      # "supervision steps" (outer loop with gradient on last)
L_cycles: 6      # inner recursion depth per supervision step
L_layers: 2      # number of blocks in the single network
hidden_size: 512
num_heads: 8
expansion: 4      # SwiGLU expansion factor
halt_max_steps: 16  # max ACT supervision steps
```

**Effective depth per supervision step:** `L_cycles × L_layers = 6 × 2 = 12 layers`
**Effective total depth:** `H_cycles × (L_cycles + 1) × L_layers = 3 × 7 × 2 = 42 equivalent layers`

---

## 3. THE RECURSIVE PROCESS — How It Actually Works

This is the core innovation. The network maintains **two latent states**:

- **z_H** ("answer embedding") — decodable via `lm_head` into a prediction at any time
- **z_L** ("reasoning state") — pure latent computation, not directly interpretable

### 3.1 Single Forward Pass (Inner Recursion)

```python
# Given: x = input embeddings, z_H = answer state, z_L = reasoning state

# Step 1: Update reasoning state (L_cycles times)
for _ in range(L_cycles):           # 6 times by default
    z_L = network(z_L, z_H + x)    # reasoning sees: current answer + input

# Step 2: Update answer state (once)
z_H = network(z_H, z_L)            # answer absorbs reasoning results

# Step 3: Decode answer
output = lm_head(z_H)              # current prediction
q = q_head(z_H)                    # should we stop?
```

**The key insight:** The SAME network (`L_level`) is used for both z_L updates and the z_H update. It's called via `input_injection` — the second argument is added to the hidden state before processing:

```python
# From ReasoningModule.forward():
hidden_states = hidden_states + input_injection  # inject context
for layer in self.layers:
    hidden_states = layer(hidden_states=hidden_states)
return hidden_states
```

### 3.2 Deep Supervision (Outer Loop)

The training loop calls the inner forward pass **H_cycles times** (default 3), but only computes gradients on the **last iteration**:

```python
# From TinyRecursiveReasoningModel_ACTV1_Inner.forward():

# H_cycles - 1 iterations WITHOUT gradient
with torch.no_grad():
    for _ in range(H_cycles - 1):       # 2 times
        for _ in range(L_cycles):        # 6 inner steps each
            z_L = network(z_L, z_H + x)
        z_H = network(z_H, z_L)

# 1 final iteration WITH gradient
for _ in range(L_cycles):               # 6 inner steps
    z_L = network(z_L, z_H + x)
z_H = network(z_H, z_L)

# Detach for next supervision step
new_carry = InnerCarry(z_H=z_H.detach(), z_L=z_L.detach())
```

**This is repeated up to `halt_max_steps` (16) times** via the ACT wrapper, giving a maximum effective depth of:
`16 × 3 × (6+1) × 2 = 672 equivalent layers` — from a 2-layer network!

### 3.3 The Full Pipeline

```
┌─────────────────────────────────────────────────────────┐
│ ACT (Adaptive Computation Time) Wrapper                 │
│                                                         │
│  For each supervision step (up to 16):                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Inner Forward Pass                                │  │
│  │                                                   │  │
│  │  ┌─── H_cycles (3) ───────────────────────────┐  │  │
│  │  │                                             │  │  │
│  │  │  [no_grad × 2]  then  [with_grad × 1]      │  │  │
│  │  │                                             │  │  │
│  │  │  For each H_cycle:                          │  │  │
│  │  │  ┌─── L_cycles (6) ──────────────────────┐ │  │  │
│  │  │  │ z_L = net(z_L, z_H + input_emb)       │ │  │  │
│  │  │  │ z_L = net(z_L, z_H + input_emb)       │ │  │  │
│  │  │  │ z_L = net(z_L, z_H + input_emb)       │ │  │  │
│  │  │  │ z_L = net(z_L, z_H + input_emb)       │ │  │  │
│  │  │  │ z_L = net(z_L, z_H + input_emb)       │ │  │  │
│  │  │  │ z_L = net(z_L, z_H + input_emb)       │ │  │  │
│  │  │  └───────────────────────────────────────┘ │  │  │
│  │  │  z_H = net(z_H, z_L)  ← answer update     │  │  │
│  │  │                                             │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │                                                   │  │
│  │  output = lm_head(z_H)     ← decode prediction   │  │
│  │  q = q_head(z_H)           ← halt decision       │  │
│  │  loss += cross_entropy(output, labels)            │  │
│  │  loss += BCE(q, is_correct)                       │  │
│  │                                                   │  │
│  │  detach(z_H, z_L)  ← cut gradient for next step  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  if q says "halt" or max_steps reached → stop           │
│  else → continue with refined (z_H, z_L)               │
└─────────────────────────────────────────────────────────┘
```

---

## 4. THE LOSS FUNCTION

Two losses combined:

### 4.1 Prediction Loss (LM Loss)
```python
lm_loss = stablemax_cross_entropy(logits, labels)
```
- Uses **StableMax** instead of softmax — a numerically stable alternative where `s(x) = 1/(1-x)` for x<0, `x+1` for x>=0
- Computed at **every supervision step** (deep supervision signal)
- Masked: only cells that need prediction contribute

### 4.2 Halting Loss (Q Loss)
```python
q_halt_loss = BCE(q_halt_logits, is_correct)
```
- Binary cross-entropy: "is the current answer fully correct?"
- Target: 1 if all predicted tokens match labels, 0 otherwise
- **The network learns when its answer is good enough to stop**

### 4.3 Total Loss
```python
total_loss = lm_loss + 0.5 * q_halt_loss
```

---

## 5. KEY DESIGN DECISIONS — WHY IT WORKS

### 5.1 "Less is More" — Depth vs. Width Tradeoff

| Config | Layers | Recursion | Params | Sudoku Accuracy |
|--------|--------|-----------|--------|-----------------|
| HRM | 4 + 4 | n=2 | 27M | 55.0% |
| TRM (4-layer) | 4 | n=3 | 10M | 79.5% |
| **TRM (2-layer)** | **2** | **n=6** | **5M** | **87.4%** |

Fewer layers + more recursion = better generalization. The paper hypothesizes this is because:
- Deeper networks overfit faster on small datasets
- Recursion shares weights across "effective layers," acting as implicit regularization
- Each recursion step gets the same high-quality gradient signal (via deep supervision)

### 5.2 Single Network (Weight Sharing)

HRM used two separate networks (f_H for "high-frequency" and f_L for "low-frequency"). TRM uses **one network for everything**:
- z_L updates: `net(z_L, z_H + input)` — reasoning sees answer + question
- z_H updates: `net(z_H, z_L)` — answer absorbs reasoning

The network learns to behave differently based on **what's injected** (input_injection argument), not on having different weights.

### 5.3 Full Backpropagation (Not Fixed-Point)

HRM assumed latent states converge to fixed points and used 1-step gradient approximation (Implicit Function Theorem). TRM abandons this entirely:
- Gradients flow through the full final recursion cycle
- States are detached between supervision steps (truncated BPTT)
- No convergence assumption needed

### 5.4 MLP-Mixer Instead of Attention

For fixed-size inputs (Sudoku 9×9 = 81 tokens), self-attention is unnecessary overhead. The MLP-Mixer approach:
- Transposes `[B, L, D] → [B, D, L]`
- Applies SwiGLU across the **sequence dimension** (mixing token positions)
- Transposes back
- Then applies SwiGLU across the **channel dimension**

This is equivalent to attention with a fixed, learned mixing pattern — much cheaper and sufficient when input size is constant.

### 5.5 EMA (Exponential Moving Average)

- Maintains a shadow copy of all weights, averaged with decay 0.999
- Used at evaluation time instead of the raw trained weights
- Prevents instability from recursive weight sharing amplifying noise
- **Ablation shows removing EMA drops accuracy from 87.4% → 79.9%**

### 5.6 Adaptive Computation Time (ACT)

The halting mechanism:
- Q-head outputs `q_halt_logits` — sigmoid > 0 means "stop"
- During training: exploration probability (10%) forces random minimum steps
- During evaluation: always uses max steps (for batching consistency)
- Loss target: `is_correct` — the network learns that "correct = stop"

---

## 6. DATA AUGMENTATION — Critical to Small-Data Success

| Task | Training Examples | Augmentations | Effective Dataset |
|------|-------------------|---------------|-------------------|
| Sudoku-Extreme | 1,000 | 1,000 shuffles | 1,000,000 |
| Maze-Hard | varies | 8 (dihedral) | 8× |
| ARC-AGI | 800 tasks | 1,000 (color perms + geometric) | 800,000 |

At test time for ARC-AGI: **majority vote across 1,000 augmented versions** of each test input.

---

## 7. COMPARISON WITH HRM (PREDECESSOR)

| Aspect | HRM | TRM |
|--------|-----|-----|
| Networks | 2 (f_H + f_L) | 1 (shared) |
| Layers per network | 4 | 2 |
| Parameters | 27M | 5-7M |
| Gradient method | 1-step IFT approximation | Full backprop through recursion |
| Convergence assumption | Fixed-point (Banach) | None |
| Theoretical basis | Cortical hierarchy (biology) | "Less is more" (empirical) |
| Inner recursion (n) | 2 | 6 |
| Sudoku-Extreme | 55.0% | 87.4% |
| ARC-AGI-1 | 40.3% | 44.6% |

---

## 8. WHAT DIDN'T WORK (Failed Ablations)

The paper is unusually transparent about failed ideas:

1. **Mixture of Experts** — decreased generalization (more params = more overfitting)
2. **Fixed-point iteration** (TorchDEQ) — slower training, no improvement
3. **Partial gradient backprop** — no benefit over full or 1-step
4. **Weight tying** (embed_tokens ↔ lm_head) — too constraining
5. **Self-attention on fixed-size tasks** — worse than MLP-Mixer (74.7% vs 87.4%)
6. **More layers** — 4-layer with n=3 (79.5%) < 2-layer with n=6 (87.4%)

---

## 9. CODE STRUCTURE (Official Repo)

```
models/
  recursive_reasoning/
    trm.py              ← Main TRM implementation (298 lines)
    hrm.py              ← HRM baseline for comparison
    trm_hier6.py        ← Variant with 6-level hierarchy
    trm_singlez.py      ← Variant with single z (no z_H/z_L split)
  layers.py             ← Attention, SwiGLU, RoPE, RMS norm, CastedLinear
  losses.py             ← ACTLossHead, StableMax, loss computation
  common.py             ← Truncated normal initialization
  ema.py                ← Exponential Moving Average helper
  sparse_embedding.py   ← Puzzle-specific sparse embeddings

pretrain.py             ← Training loop (deep supervision, carry state)
puzzle_dataset.py       ← Data loading and augmentation
config/arch/trm.yaml    ← Default hyperparameters
```

---

## 10. KEY TAKEAWAYS FOR MODULE WRAPPER APPLICATION

### What maps to our architecture:

| TRM Concept | Module Wrapper Analog |
|-------------|----------------------|
| z_H (answer state) | Current DSL composition / component selection |
| z_L (reasoning state) | Latent search/reasoning embeddings |
| Input injection (x) | Query embedding + context |
| L_cycles (inner recursion) | Multi-vector search passes (components → inputs → relationships) |
| H_cycles (supervision steps) | Instance pattern refinement cycles |
| Halting decision | Confidence threshold for "good enough" match |
| Single shared network | Shared embedding space across all 3 vector types |
| Deep supervision | Feedback from successful executions at every step |

### The vision:
A TRM-like architecture where the module wrapper's 3-vector embeddings serve as the latent state, recursive passes refine component selection and DSL composition, and successful executions provide the deep supervision signal — all with a tiny network that gets better with each use.

---

## Sources

- [Paper (arXiv HTML)](https://arxiv.org/html/2510.04871v1)
- [Paper (PDF)](https://arxiv.org/pdf/2510.04871)
- [Official GitHub Repo](https://github.com/SamsungSAILMontreal/TinyRecursiveModels)
- [HuggingFace Paper Page](https://huggingface.co/papers/2510.04871)
- [AI Papers Academy Explainer](https://aipapersacademy.com/tiny-recursive-model/)
- [Medium Explainer](https://medium.com/data-science-in-your-pocket/less-is-more-recursive-reasoning-with-tiny-networks-paper-explained-a4573708376d)
