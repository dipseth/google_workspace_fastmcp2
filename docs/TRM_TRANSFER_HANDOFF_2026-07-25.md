# TRM Cross-Module Transfer — Handoff

**Date:** 2026-07-25 (root cause revised 2026-07-25, later session)
**Branch:** `chore/bump-fastmcp-3.4.4`
**Status:** generator bug found and fixed; regenerated + retrained. In-domain and feature-space
both improved substantially, but **cross-module transfer still fails** for a second, distinct
reason — see [1b](#1b-why-transfer-still-fails--different-cause-further-down)
**Predecessor:** [NEXT_STEPS_2026-04-05.md](NEXT_STEPS_2026-04-05.md)

---

## TL;DR

Zero-shot transfer of the gchat-trained `UnifiedTRN` to a second wrapped module
(`qdrant_client.models`) **fails catastrophically** — it is worse than no model at all.
**9 of 17 input features are out of distribution**, and all 9 are the ColBERT-derived ones.

> **Correction (superseding the original diagnosis below).** The cause is *not* unrealistic
> training queries. It is a **shape bug in the training-data generator**: query ColBERT
> embeddings were kept as a 3-D `[1, tokens, dim]` batch and never unwrapped, so
> `maxsim_decomposed` normalized and reduced along the token axis instead of the embedding
> axis. Every ColBERT feature was inflated by ~`sqrt(dim/tokens)` and the max was taken over
> *document* tokens rather than *query* tokens. Training and inference were computing
> different statistics. See [The real root cause](#the-real-root-cause).

That has been fixed, regenerated and retrained. It closed most of the feature gap (OOD 9/17 →
4/17, worst z −12.5 → −3.4) and lifted in-domain `val_form_top1` to 100%, but **transfer is
still 0.0% Top-1** — because the model keys on *absolute* feature magnitudes whose training
spread is tiny (sd 0.05–0.13), so a −3σ shift saturates every logit and the reranking becomes
noise. Next lever is **per-query feature normalization**, not global standardization.

---

## Where things stand (context for a fresh session)

Work completed this session, all verified, **nothing committed**:

| area | state |
|---|---|
| `research/` restore | 60 `.py` files + 7 checkpoints recovered from `59207e9^`; `research/` now fully gitignored |
| Model vendoring | `unified_trn.py`, `slot_assigner.py`, `eval_metrics.py` moved to `adapters/`; `research/` copies are re-export shims |
| Production imports | zero `research.*` imports in shipped code; guarded by `tests/module/test_no_research_imports.py` (AST scan) |
| Deleted tests | 1,959 lines restored across 5 files, imports rewired |
| Slot pin policy | `SLOT_PIN_MODE` added (`always` default / `confidence`), wired into `config/settings.py` |
| Test suite | 502 passed, 32 skipped; `ruff check` + `ruff format --check` both clean |

Two prior findings that matter here:

- **`pool_head` is uncalibrated.** `label_smoothing=0.1` over 5 pools caps max-prob near
  0.92; observed range 0.896–0.959. `SLOT_REROUTE_CONFIDENCE` is an on/off switch, not a dial.
- **Checkpoints have no `data_version`.** The train/val split can't be reproduced, so no
  existing metric is trustworthy as held-out. This is still NEXT_STEPS #1 and #2.

---

## The finding

### Benchmark

```bash
python -m research.trm.h2.transfer_eval          # 45 queries, ~1 min
python -m research.trm.h2.transfer_eval --features-only
```

Self-labelling: query = each class's docstring with the class name scrubbed out, ground
truth = that class. `rrf` and `multidim` run identical queries through identical
retrieval, so any delta is purely the learned model's contribution.

**Result (45 queries, `best_model_unified.pt`, domain=gchat, 28,776 params):**

| mode | Top-1 | MRR | recall@10 |
|---|---|---|---|
| rrf | 26.7% | 0.276 | 33.3% |
| multidim | 20.0% | 0.247 | 33.3% |
| **learned** | **0.0%** | **0.002** | **2.2%** |

recall@10 collapsing from 33.3% → 2.2% means the model actively pushes correct answers
*out* of the top 10. Verified not to be an error path: the model loads, the DAG builds
(298 nodes, max_depth=5), 20 candidates are scored, no exception. Scores cluster in a
narrow −13 to −14 band — the signature of out-of-distribution input.

### The real root cause

The stored training features are not cosine similarities at all. Over
`mw_synthetic_groups_v5_hard2.json` (17,825 candidates):

| feature | min | mean | max |
|---|---|---|---|
| `sim_c_mean` | 0.436 | 0.951 | 1.708 |
| `sim_c_max` | 0.662 | 1.858 | **3.103** |
| `sim_i_max` | 0.164 | 2.188 | **4.372** |
| `sim_relationships` | −0.136 | 0.238 | 0.815 |
| `sim_content` | −0.124 | 0.123 | 1.000 |

A MaxSim over unit-norm ColBERT vectors is bounded by 1.0. The dense features
(`sim_relationships`, `sim_content`) respect that bound; every ColBERT feature does not.
The stored vectors in Qdrant *are* unit-norm, so the bound cannot be broken by the data.

The mechanism, in `generate_training_data.py`:

```python
comp_vecs = service.embed_multivector_sync([embed_text])  # -> [1, tokens, dim]
comp_np   = np.array(comp_vecs, dtype=np.float32)         # 3-D, never unwrapped
if comp_np.ndim == 1:                                     # only guards the 1-D case
    comp_np = comp_np.reshape(1, -1)
```

`embed_multivector_sync` takes a *list* of texts and returns one token matrix per text, so a
single string yields `[1, tokens, dim]`. Inside `maxsim_decomposed`, `axis=1` is then the
**token** axis rather than the embedding axis:

- `q_norm` normalizes across tokens per dimension, so rows have norm ≈ `sqrt(dim/tokens)`
  instead of 1 — with `dim=128`, `tokens=33` that is **1.97×**, and for the shorter DSL
  `inputs` text (`tokens≈8`) it approaches **4×**. That is exactly the observed ceiling of
  3.10 for `sim_c_max` and 4.37 for `sim_i_max`.
- `per_token_max = sim_matrix.max(axis=1)` reduces over *query* tokens, yielding one value
  per *document* token — a different statistic from the one inference computes.
- `sim_c_coverage` then counts inflated values against a fixed `0.4` threshold, which is why
  it saturates at 0.97.

**Verification.** Running the *exact* gchat training query text through the production
inference path gives `sim_c_coverage = 0.116`, not the 0.967 stored in the training data.
Query phrasing barely moves the feature at all:

| query | `sim_c_coverage` (inference path) |
|---|---|
| eval docstring | 0.213 |
| training-style component list | 0.230 |
| **gchat training query, verbatim** | **0.116** |
| short natural language | 0.341 |

Reproducing the 3-D path against the same corpus lifts coverage from 0.118 → 0.765 and
`sim_c_max` by 1.93× — matching the predicted `sqrt(128/33) = 1.97`. The gap is the bug,
not the queries.

### Original (superseded) hypothesis

```
feature              train mean     sd     live      z
sim_c_coverage           0.972   0.056    0.213   -13.5   <== OOD
sim_i_coverage           0.863   0.118    0.116    -6.3   <== OOD
sim_c_max                1.941   0.310    0.600    -4.3   <== OOD
sim_c_mean               0.974   0.181    0.282    -3.8   <== OOD
...                                                        9/17 OOD
is_parent                0.507   0.500    0.000    -1.0        ok
is_child                 0.672   0.469    0.000    -1.4        ok
n_shared_ancestors       0.486   0.268    0.000    -1.8        ok
```

The **retrieval** features are wrecked; the **DAG** features are fine. That inverts the
obvious hypothesis (that structural context differs between modules) and points squarely
at the training-data generator.

The original reading was that `sim_c_coverage ≈ 0.97` meant query tokens were almost fully
covered because queries were built from the components themselves. **That was wrong** — the
queries are natural-language descriptions, and running them through the inference path gives
coverage ≈ 0.12. The saturation came from the axis bug above, not from query construction.

The guess that `sim_c_max` was "a raw MaxSim *sum* that scales with query token count" was
directionally right about scale but wrong about mechanism: it is a mis-normalized dot
product, inflated by `sqrt(dim/tokens)`. Note the ColBERT embedder pads to a fixed token
count for short inputs, so query *length* is not itself the driver.

### Implication beyond transfer

The gchat model is probably weaker on *real* queries than its numbers suggest.
`val_pool_acc = 94.5%` came from the same synthetic generator, so it inherits the same
unrealistic regime. Consistent with the historical DualHead result (3.1% when evaluated
on a difficulty it wasn't trained for).

**The module-wrapper thesis is not refuted — it has never actually been tested**, because
the training distribution could not reach the test distribution.

---

## Work to do

### 0. Generator shape fix — **DONE**

`research/trm/h2/generate_training_data.py` now has `as_token_matrix()`, which unwraps the
`[1, tokens, dim]` batch dimension and rejects anything that is not a 2-D token matrix. It is
applied at all four query-embedding sites and defensively at the top of `maxsim_score` and
`maxsim_decomposed`, so no call site can reintroduce the axis bug.

Verified: with the fix, the generator and the production inference path
(`adapters/module_wrapper/search_mixin/_scoring.py::_maxsim_decomposed`) agree on all four
statistics to float32 precision (max abs diff ≈ 2e-7), and every feature is cosine-bounded.

`research/` is gitignored, so this change is not committed — it lives only in the working tree.

### 1. Regenerate and retrain — **DONE, and transfer still fails**

Ran the full pipeline on the corrected generator:

```bash
PYTHONPATH=.:research/trm .venv/bin/python -m h2.generate_training_data \
    --count 500 --variations 3 --seed 42 --domain gchat --feature-version 5 \
    --output research/trm/h2/mw_synthetic_groups_v5_fixed.json      # 642 groups, 16,050 cands
PYTHONPATH=.:research/trm .venv/bin/python -m h2.generate_unified_training_data \
    --search-data research/trm/h2/mw_synthetic_groups_v5_fixed.json \
    --build-data research/trm/h2/mw_slot_training_data.json \
    --output research/trm/h2/mw_unified_training_data_fixed.json
PYTHONPATH=.:research/trm .venv/bin/python -m h2.train_unified \
    --search-data research/trm/h2/mw_unified_training_data_fixed.json \
    --domain gchat --checkpoint-dir research/trm/h2/checkpoints_fixed
LEARNED_SCORER_CHECKPOINT=research/trm/h2/checkpoints_fixed/best_model_unified.pt \
    PYTHONPATH=. .venv/bin/python -m research.trm.h2.transfer_eval
```

**In-domain got much better. Transfer did not move.**

| | before fix | after fix |
|---|---|---|
| val_form_top1 | 66.1% | **100.0%** |
| val_pool_acc | 94.5% | 97.3% |
| features OOD (\|z\|>2) | 9/17 | **4/17** |
| worst z (`sim_c_coverage`) | −12.5 | **−3.4** |
| transfer Top-1 | 0.0% | 0.0% |
| transfer recall@10 | 2.2% | 6.7% |

Two caveats on the in-domain numbers. `val_form_top1 = 100%` is almost certainly optimistic —
the split is random over groups and only 340 of 642 groups have a unique DSL pattern, so
near-duplicates straddle it (this is still NEXT_STEPS #1/#2). And the new data has a **12.0%
form-positive rate vs 60.0% in `v5_hard2`**, because `--max-positives` defaults to 3 and the
original flags were never recorded — so 100% and 66.1% are not directly comparable.

The feature-space fix is real and large, but it was not sufficient.

### 1b. Why transfer still fails — different cause, further down

Scoring 30 candidates per query on `qdrant_client.models` with the retrained model:

- `form_score` spans **−17.3 to −15.8**, within-query std **0.40**. Every candidate is deep in
  the negative saturation region — the model calls the entire candidate set a negative.
- Mean rank of ground truth: **rrf 13.5 vs learned 13.2** (of 30). The learned reranking is not
  anti-correlated — it is **uninformative**. It replaces rrf's ordering with noise, which is why
  Top-1 goes to 0: rrf puts ground truth at rank 1 in 3 of 6 resolvable queries
  (`[1, 28, 23, 1, 1, 27]`), and learned scatters it (`[10, 5, 21, 14, 28, 1]`).
- Retrieval itself is a ceiling: ground truth appears in the candidate set in only **6 of 12**
  queries at limit=30, which bounds every mode including the baselines.

The remaining 4 OOD features are `sim_c_mean` (−3.2), `sim_c_max` (−3.7), `sim_c_coverage`
(−3.4), `sim_i_mean` (−2.1). Note their training **standard deviations are tiny** — 0.059,
0.051, 0.135, 0.119. The synthetic generator produces a very homogeneous corpus, so a modest
absolute shift is still several sigma, and the model keys on **absolute feature magnitudes**
that do not survive a change of module.

**Recommended next step: per-query feature normalization.** Z-score each of the 17 features
*within a candidate group* (the ~20–30 candidates for one query), in both the generator and
`_compute_learned_features`. The model then sees "this candidate's coverage is high *relative to
its competitors*", which is scale-free and domain-independent — exactly what the module-wrapper
thesis requires. This subsumes the checkpoint-stat standardization in step 2, which only
rescales globally and would not have prevented the saturation seen here.

### 1c. Original plan (superseded by 1 and 1b)

Every existing `mw_synthetic_groups_v5*.json` and `mw_unified_training_data.json` carries the
corrupted features, so **all of them must be regenerated** — and every metric derived from
them (including `val_form_top1 = 66.1%` and `val_pool_acc = 94.5%`) is measured in the wrong
feature space and is not comparable to post-fix numbers.

1. `generate_training_data.py --domain gchat --feature-version 5` against `mcp_gchat_cards_v8`
2. `generate_unified_training_data.py` to rebuild `mw_unified_training_data.json`
3. `train_unified.py`
4. `python -m research.trm.h2.transfer_eval`

The exact flags that produced `mw_synthetic_groups_v5_hard2.json` (713 groups) were never
recorded; defaults are `--count 500 --variations 3 --seed 42` with hard negatives on.

### 2. Feature standardization (robustness, not the fix)

The model feeds raw features straight into `Linear(17, 32)` with no normalization.

- **Compute** per-feature mean/std over the training set in
  `research/trm/h2/train_unified.py`, and **save them into the checkpoint** alongside
  `structural_dim` / `content_dim`.
- **Apply** at inference in `adapters/unified_trn.py` — either a non-trainable
  `nn.BatchNorm1d`-style buffer or an explicit `(x - mean) / std` in `forward()`.
  Buffers are preferable: they serialize with `state_dict` and can't drift out of sync.
- **Backward compatibility matters.** Existing checkpoints have no stats. Fall back to
  identity normalization when absent, so `best_model_unified.pt` keeps loading —
  `tests/module/test_no_research_imports.py` asserts it does.
- Consider normalizing `sim_c_max` / `sim_i_max` by query token count at the point of
  computation (`_compute_learned_features`) so the feature is scale-free by construction.
  If you change that function, the fix must land in **both** the training generator and
  the inference path or features silently diverge.

### 3. Realistic query generation (still worth doing, but demoted)

This was the headline fix in the original diagnosis and is no longer believed to be the
cause of the transfer failure — the synthetic queries are already natural language and land
in the same coverage regime as real ones. It remains a reasonable diversity improvement once
the regenerated baseline is in hand, but **do not do it before step 1**, or the two changes
will be confounded. Options:

- Paraphrase / underspecify ("something to show a couple of actions" → ButtonList)
- Use real logged queries — `mcp_tool_responses` has genuine `send_dynamic_card` and
  `qdrant_search` calls
- Deliberately drop query terms to force lower coverage

Validate by re-running `--features-only` against the *new* training data: the `z` column
should collapse toward 0. That is the acceptance criterion for step 1 as well.

### 4. Re-run and compare

`python -m research.trm.h2.transfer_eval`. Success = `learned` beats `rrf` (26.7% Top-1)
on a module it was never trained on. Partial success = `learned` ≥ `rrf`, which would
still prove the features carry across modules.

### 5. Only then — the round-trip test

Once transfer is non-catastrophic, `qdrant_client.models` supports a far stronger
evaluation than cards can:

```
real DSL query → parse_and_build() → Filter object        [ground truth]
                                          ↓ decompose
                    (structure DSL, flat bag of keys/values)
                                          ↓ model reassigns content→slots
                                     rebuilt Filter
                                          ↓ execute both against a collection
                        compare returned point IDs → semantic equivalence
```

Qdrant filters are **executable**, so correctness is verifiable rather than structural.
Infrastructure already exists: `middleware/qdrant_core/dsl_query_builder.py`
(`parse_and_build`), the wrapper (10,019 points in `mcp_qdrant_client_models`), and the
DSL parser. Only object→(structure, content) decomposition needs writing.

This also yields the **frozen eval set** from NEXT_STEPS #2 for free, since cases are
generated from real objects rather than sampled from the synthetic pool.

---

## Why `qdrant_client.models` is the right second domain

Measured, not assumed:

| | card_framework.v2 | qdrant_client.models |
|---|---|---|
| classes | 113 | 392 |
| median pairwise similarity | 0.183 | 0.156 |
| pairs > 0.95 | 0.0% | 0.0% |
| classes that are containers | 66% | **100%** |
| mean children per container | 8.7 | **24.4** (max 32) |
| self-recursive types | — | **26**, incl. `Filter.should` → Filter |

Pre-flight passes: the similarity spread matches the known-learnable gchat baseline, so
this is *not* the Mancala failure mode (`RETRO.md`: embeddings at 0.99+ are unlearnable).
An early hypothesis that `Match*`/`Condition` classes would be semantically confusable
was **wrong** — the `relationships` vector encodes field structure, not just prose, so
they separate cleanly.

The real difficulty is **compositional**: ~3× branching factor and genuine self-recursion.
Cards are shallow (`Section → widgets → leaf`); filters are recursive trees. Since the
recursion in `search_hybrid_recursive` refines the *candidate set* rather than a latent,
this is the first domain where the target structure is itself recursive — which makes
accuracy-vs-tree-depth a measurable curve rather than a single number.

---

## Gotchas that cost time this session

- **`embed_multivector_sync` is batch-shaped.** It takes a list of texts and returns a list
  of token matrices, so embedding one string gives `[1, tokens, dim]`. A `ndim == 1` guard
  does not catch it, and NumPy will happily broadcast the 3-D array through a matmul and
  produce plausible-looking numbers. Sanity-check that ColBERT features stay within `[-1, 1]`
  — that single check would have caught this immediately.
- **Two implementations of the same feature will drift.** `maxsim_decomposed` (training) and
  `_maxsim_decomposed` (inference) were textually near-identical and still disagreed, because
  the bug was in the *caller's* array shape. Compare the two numerically on shared inputs, not
  by reading them side by side.
- **HTTP 200 is not verification.** Google Chat accepts and stores a card, returns 200,
  then the client silently declines to render it. Read the echoed response body.
- **A button without `onClick` kills the entire card** client-side. `validate_structure`
  catches this (message: *"card will be silently dropped"*) and `fix_structure` repairs it,
  but only via `validate_and_repair_card`, which is called from `gchat/card_tools.py`.
  **Calling `build_from_params` directly bypasses the repair layer** — that is a test
  harness bug, not a builder bug.
- **`.env` does not reach `os.environ`.** pydantic-settings populates `Settings` only.
  Read config through `config.settings`, not `os.environ`, or `.env` is silently ignored.
- **`SEARCH_MODE=recursive` is set in `.env`** — the learned path is live in this
  configuration, so scorer regressions affect real behaviour.
- The pin-policy `except Exception` in `_should_release` and the loader `except ImportError`
  paths are deliberate: they fail toward safe behaviour, but they will hide real errors.
  Check logs at ERROR level before assuming a path is healthy.

---

## Key files

| purpose | path |
|---|---|
| Transfer benchmark | `research/trm/h2/transfer_eval.py` |
| Model definition (inference) | `adapters/unified_trn.py` |
| Feature computation | `adapters/module_wrapper/search_mixin/_learned_model.py` |
| Recursive search loop | `adapters/module_wrapper/search_mixin/_hybrid_recursive.py` |
| Training (unified) | `research/trm/h2/train_unified.py` |
| Training data generator | `research/trm/h2/generate_unified_training_data.py` |
| Qdrant wrapper | `middleware/qdrant_core/qdrant_models_wrapper.py` |
| DSL → object builder | `middleware/qdrant_core/dsl_query_builder.py` |
| Slot assignment + pin policy | `gchat/card_builder/slot_assignment.py` |
| Import guard test | `tests/module/test_no_research_imports.py` |

**Reminder:** `research/` is gitignored and excluded from the published repo. Production
must never import from it — the guard test fails the build if it does.
