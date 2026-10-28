# TRM cross-module transfer — per-query z-scoring session (2026-10-27)

Continues `docs/TRM_TRANSFER_HANDOFF_2026-07-25.md`, which ended with "next lever:
per-query feature normalization". This session built it, measured it, and found the
*actual* remaining causes of the transfer failure.

## TL;DR

| learned checkpoint | transfer Top-1 | MRR | recall@10 | within-pool Top-1 (n=13) | in-domain val_pool |
|---|---|---|---|---|---|
| raw features (`checkpoints_fixed`, Jul 25) | 0.0% | 0.012 | 6.7% | 7.7% | 97.3% |
| + group z-score (`checkpoints_zscore`) | 0.0% | 0.065 | 22.2% | 7.7% | 68.3% |
| + z-score + DAG/content mask 0.3 (`checkpoints_zscore_mask`) | 11.1%* / **20.0%** | 0.230 | 26.7% | **69.2%** | 68.3% |
| + mask 0.6 (`checkpoints_zscore_mask06`) | 6.7% | 0.156 | 26.7% | 23.1% | 65.9% |
| + mode flag, 150 epochs, seeds 42 / 7 / 123 (`checkpoints_zscore_full_s*`) | 8.9% / 20.0% / 6.7% | 0.153 / 0.233 / 0.147 | 26.7% | 30.8% / 69.2% / 23.1% | 68.3% / 66.0% / 81.4% |
| rrf baseline (model-free) | 26.7% | 0.276 | 33.3% | — | — |

\* 11.1% was measured before the alpha-blend bug fix below; 20.0% after.

**Transfer went from uninformative noise to a real reranker** (within-pool Top-1 7.7% → 69.2%
on the best seed) but still trails rrf end-to-end, for two reasons that are now measured
rather than guessed:

1. **Retrieval ceiling of the learned path.** `_query_grouped_candidates` with
   `candidate_pool_size=20` contains the ground truth in only **13/45** queries (28.9%), so
   the learned path's best possible Top-1 is 28.9% — barely above rrf's 26.7%. Pool 40 →
   22/45, pool 80 → 25/45, but within-pool accuracy falls as the pool grows (69% → 45% →
   36%) because training groups are always K=25 and z-scoring is group-size dependent.
   Two-stage (pool 80, rerank top 25) gives 18/45 in pool × 50% = 20% — no better.
2. **The model does not trust `sim_c_max`.** On `qdrant_client.models`, raw `sim_c_max`
   alone ranks the ground truth first **84.6%** of the time within the pool. In the gchat
   training data `sim_c_max` alone is only **38.8%** (cmean 72.3%), because synthetic hard
   negatives are near-identical siblings that only the DAG features separate. So the model
   learned to lean on `is_parent/is_child/is_sibling` (train-positive z ≈ +1.1 … +1.7) and
   `sim_content` (z +1.6) — and **all of those are identically zero on the transfer
   domain** (see below). Masking those features 30% of the time during training is what
   made the model usable; 60% over-corrects.

## Findings

### DAG features are structurally zero on any module without instance patterns

`_infer_component_paths` only reads `parent_paths` from `instance_pattern` points. The
`mcp_qdrant_client_models` collection has **0** instance patterns (392 class, 2,306
function, 5,283 method points), so `query_components` is empty and
`is_parent/is_child/is_sibling/n_shared_ancestors` are 0 for every candidate. The DAG itself
loads fine (298 nodes). This is a genuine domain gap, not a bug — but it means the
"universal module wrapper" features need an anchor set that does not come from card
history (e.g. self-anchoring on the top-k ColBERT candidates). Not attempted.

### Group z-scoring costs ~30 pts of pool accuracy, and it is NOT what I first thought

Every z-scored run has `val_pool_acc` 66–81% vs 97.3% raw. Ruled out this session:

- **Mode collision** (build-mode zero vector now sits inside the search distribution):
  added an explicit build/search bit (`mode_flag`) — no change (65.9%).
- **Early stopping with cosine LR still high**: `--patience 1000` (full 150 epochs) — no
  change (68.3% / 66.0% / 81.4% across seeds).

Remaining hypothesis: unit-variance structural inputs (|z| up to ~3 vs raw 0–1) let the
structural pathway dominate the shared backbone's gradients, starving the content pathway
the pool head depends on. Untested levers: scale z by ~0.3, LayerNorm after each encoder,
or raise `--w-pool`. **Do not ship a z-scored checkpoint until pool accuracy is back at
~97%** — `SLOT_PIN_MODE=confidence` consults this head.

### Seed variance dwarfs most deltas

With n=13 in-pool queries, seeds 42 vs 7 of the identical config give within-pool Top-1
30.8% vs 69.2% (five queries). Any future claim needs ≥3 seeds and a bigger eval set
(`--n 150` is available; the ceiling is retrieval, so also raise the pool).

### Production bug fixed: content head was blended in with no content text

`search_hybrid_learned` set `alpha = 1.0 if not content_text else 0.6` and then
unconditionally overwrote it with `Settings().dual_head_form_weight` (0.6). With no
content text the content head scores the query against *itself* — noise — and got 40% of
the final score. `search_hybrid_recursive` (production, `SEARCH_MODE=recursive`) did the
same via `recursive_alpha_init` (30–50% noise). Both now blend form-only when
`content_text` is absent. On the transfer set this alone moved learned Top-1 11.1% → 20.0%.
In-domain effect on gchat not measured.

## Code changes (all backward compatible; legacy checkpoints load unchanged)

| file | change |
|---|---|
| `adapters/unified_trn.py` | `normalize_feature_group(features, norm, mask)` + `FEATURE_NORM_*` constants; `UnifiedTRN(mode_flag=)` appends a build/search bit (ckpt key `mode_flag`, absent = False) |
| `adapters/module_wrapper/search_mixin/_learned_model.py` | reads ckpt `feature_norm` → `cls._learned_feature_norm`; passes `mode_flag` |
| `.../_hybrid_learned.py`, `.../_hybrid_recursive.py` | apply `normalize_feature_group` to each candidate group before the model; form-only blend without content text |
| `gchat/card_builder/slot_assignment.py` | constructor passes `mode_flag` (2 sites) |
| `tools/diagnostic-ui/backend/routes/ml_eval.py` | replaced a drifted hand-copied `_UnifiedTRN` (wrong halt_head LayerNorm placement — could not load current checkpoints) with the `adapters` import; passes `mode_flag` |
| `research/trm/h2/train_unified.py` | `--feature-norm {none,group_zscore}`, `--structural-mask-prob`, `--mask-content`, `--mode-flag`; checkpoint now carries `feature_norm`, `mode_flag`, `data_version`, `git_commit`, `timestamp`, `train_args` (NEXT_STEPS #1 done) |
| `research/trm/h2/transfer_diag.py` | new: per-query GT rank under pool order / learned / raw cmax, GT z-profile vs training positives, `--pool`, `--rerank-top`, `--prefilter` |
| `tests/module/test_unified_trn.py` | 7 tests for the normalizer and the mode flag |

Note: structure-aware slot assignment (`slot_assignment.py` ~L540) feeds **raw**
`_compute_learned_features` output to build mode. With a z-scored checkpoint that would be
a train/inference mismatch (training build pairs use zero structural). Left untouched
because no z-scored checkpoint is deployable yet.

## Repro

```bash
# train (best config this session)
PYTHONPATH=.:research/trm .venv/bin/python -m h2.train_unified \
  --search-data research/trm/h2/mw_unified_training_data_fixed.json --domain gchat \
  --feature-norm group_zscore --structural-mask-prob 0.3 --mask-content --mode-flag \
  --patience 1000 --seed 7 --checkpoint-dir research/trm/h2/checkpoints_zscore_full_s7
# end-to-end benchmark (rrf / multidim / learned)
LEARNED_SCORER_CHECKPOINT=research/trm/h2/checkpoints_zscore_full_s7/best_model_unified.pt \
  PYTHONPATH=. .venv/bin/python -m research.trm.h2.transfer_eval
# retrieval ceiling vs reranking, GT z-profile
LEARNED_SCORER_CHECKPOINT=... PYTHONPATH=. .venv/bin/python -m research.trm.h2.transfer_diag --pool 20
```

## Next (ranked)

1. **Fix the pool-accuracy regression** before anything ships: try z-scale 0.3 / encoder
   LayerNorm / `--w-pool 0.5`; acceptance = `val_pool_acc ≥ 0.95` with z-scoring on.
2. **Raise the learned path's retrieval ceiling** — it, not the scorer, now caps transfer.
   Options: larger grouped pool with top-25 rerank (needs the model to be trained on mixed
   K, or z-score over the top-25 only), or use `search_hybrid`'s prefetch (33.3% recall@10
   vs 28.9%).
3. **Self-anchored DAG features** so modules without instance patterns get non-zero
   structural signal; or train on a second domain (`qdrant_client.models` has an
   executable round-trip eval — 2026-07-25 handoff §5).
4. Measure the alpha-blend fix in-domain on gchat (it is live under `SEARCH_MODE=recursive`).

---

## Part 2 — second training module (same day, later)

The real fix was training-data diversity, not feature scale. Added `decision_pipeline`
(github.com/dipseth/decision-pipeline-python; 645 classes, pydantic-only, **no instance
patterns**, so DAG features are zero exactly as on the transfer domain) as a second training
module and trained on gchat + decision_pipeline. `qdrant_client.models` stays held out.

| training data | features | transfer Top-1 | MRR | in-pool Top-1 (n=13) | gchat val_pool |
|---|---|---|---|---|---|
| gchat only | raw | 0.0% | 0.012 | 7.7% | 97.3% |
| gchat only, best z-score+mask seed | z-score | 20.0% | 0.233 | 69.2% | 66.0% |
| **gchat + dp** (`checkpoints_md_raw_s7`) | **raw** | **26.7%** | **0.274** | **92.3%** | 70.5% |
| gchat + dp, z-score no mask, seeds 7/42 | z-score | 22.2% / 24.4% | 0.244 / 0.257 | 76.9% / 84.6% | 79.5% / 65.9% |
| gchat + dp, z-score + mask 0.3, seeds 7/42 | z-score | 20.0% / 24.4% | 0.231 / 0.256 | 69.2% / 84.6% | 75.0% / 59.1% |
| rrf (model-free) | — | 26.7% | 0.276 | — | — |

- Raw multi-domain matches rrf end-to-end and gets 12/13 in-pool queries right. The
  reranker is effectively solved; **the 13/45 retrieval ceiling is the whole gap now.**
- Z-scoring/masking are no longer needed and slightly hurt once the data is diverse.
- **Pool accuracy drops in every multi-domain run, raw included** (97% → 59–80%), so the
  morning's "z-scoring breaks the pool head" diagnosis was wrong: it is the 3× larger
  search set outweighing the unchanged 1,536 build pairs. Fix to try: `--w-pool` up / more
  build batches per epoch. Still blocks deployment (`SLOT_PIN_MODE=confidence`).
- Langfuse (`RECIPES_LANGFUSE_*`, 15,890 weReci traces): the `pipeline:conceits` /
  `pipeline:cuisine` traces are decision-pipeline *run records* (parameters in, record out),
  not NL queries with a class as the answer — not usable as labels for this task.

**New infrastructure**

| file | purpose |
|---|---|
| `research/trm/h2/dp_wrapper.py` | ModuleWrapper for `decision_pipeline` → collection `mcp_decision_pipeline` (6,448 pts). Needs the repo checkout on `PYTHONPATH`; `__main__` blocks on the daemon indexing thread (otherwise the process exits before the collection exists). |
| `research/trm/h2/generate_module_groups.py` | Self-labelled groups for any wrapped module: scrubbed docstring → production learned-search path → `_compute_learned_features`. K=25, GT injected when not retrieved (303/1197). ~45 min for 589 classes. Single-feature top-1 on dp: cmean 68%, cmax 49%. |
| `train_unified.py --extra-search-data` | merges extra domains; recorded in checkpoint `extra_search_data`. |

```bash
PYTHONPATH=.:/path/to/decision-pipeline-python .venv/bin/python -m research.trm.h2.dp_wrapper
PYTHONPATH=.:/path/to/decision-pipeline-python .venv/bin/python -m research.trm.h2.generate_module_groups \
  --wrapper decision_pipeline --output research/trm/h2/dp_search_groups.json
PYTHONPATH=.:research/trm .venv/bin/python -m h2.train_unified \
  --search-data research/trm/h2/mw_unified_training_data_fixed.json \
  --extra-search-data research/trm/h2/dp_search_groups.json --domain gchat --patience 1000 --seed 7 \
  --checkpoint-dir research/trm/h2/checkpoints_md_raw_s7
```

**Next (revised):** 1) restore pool acc under multi-domain training (loss weighting) →
raw multi-domain checkpoint becomes deployable; 2) raise the learned path's retrieval
ceiling; 3) a third module to confirm the trend.

---

## Part 3 — the three "next" items, measured (same day, afternoon)

### 1. Pool accuracy never dropped — the 97.3% baseline was leaky

`checkpoints_fixed` (Jul 25) predates the grouped build split (no `val_build_keys` in the
checkpoint), so its val set shared texts with training. Fresh **gchat-only** controls with
current code: val_pool **66.0% / 68.3%** (seeds 7 / 42). Multi-domain runs are in the same
band or higher, so there is nothing to restore. Old numbers are not targets; re-measure.
The val build set is only ~45 unique texts (~2 pts per item).

In-domain gchat search on gchat val groups held out by both runs: control 35/36 vs
md_raw_s7 33/36; on a second shared set (15 groups) both 100%.

### 2. Retrieval ceiling: production bug in `_query_grouped_candidates` (fixed)

`query_points_groups(group_by="type", prefetch=…, query=FusionQuery(RRF))` drops and
reorders hits (qdrant server 1.19.1 / client 1.17). The identical prefetch through
`query_points` keeps everything:

| retrieval (qdrant_client.models, n=45, pool 20) | Top-1 | R@20 |
|---|---|---|
| old grouped RRF call | 1–5 (nondeterministic) | 13 |
| `query_points` + same prefetch + RRF | 12 | 17 |
| components ColBERT alone | 12 | 17 |

Fix (`adapters/module_wrapper/search_mixin/_hybrid_helpers.py`): one fused `query_points`
(limit = pool × n_prefetch), then per-type caps client-side (≤5 types, `group_size` each,
fused order). Test: `tests/module/test_grouped_candidates.py`. **Affects gchat production
learned search too — in-domain effect not yet measured.**

Remaining ceiling is ColBERT recall itself: R@20 17/45, R@80 25/45. On class points
`inputs`/`relationships` embed only the symbol name (`"η HnswConfigDiff"`) and `content` is
empty (`has_content_vector: False`); adding them to the fusion *lowers* recall. Raising the
ceiling means indexing docstring text into a dense class vector (wrapper indexing change).

### 3. Third module (`mcp.types`) — plateau

`mcp.types`: 164 classes, collection `mcp_mcp_types` (4,887 pts), 317 groups (GT in pool
99.4% with the fixed retrieval). Transfer on qdrant_client.models, **n=150**, 3 seeds:

| training | learned Top-1 (s7/42/123) | in-pool Top-1 (n=51) | val_pool |
|---|---|---|---|
| gchat only (`gchat_ctrl_s7`) | 12.0% | 35.3% | 66.0% |
| gchat + dp (`md_raw_s*`) | **22.7 / 22.7 / 22.7%** | **66.7%** ×3 | 70.5 / 63.6 / 69.8% |
| gchat + dp + mcp (`3d_raw_s*`) | 20.0 / 22.0 / 21.3% | 58.8 / 64.7 / 62.7% | 75.0 / 74.4 / 66.7% |
| rrf (model-free) | 23.3% | — | — |
| ColBERT pool order (no rerank) | — | 68.6% | — |

- The 1→2 module jump is real (12% → 22.7%) and seed variance is gone.
- 2→3 is flat-to-slightly-worse (2–3 queries). The reranker now sits at ColBERT's own
  order; the 17 features don't carry more than ColBERT already does on this domain.
- Caveat: dp groups were generated with the old (buggy) retrieval (303/1197 GT injected);
  mcp groups with the fixed one. Regenerating dp (~45 min) would make them consistent.

**Deployable candidate:** `checkpoints_md_raw_s7` (pool head ≈ gchat-only, gchat search
33/36 vs 35/36, transfer ≈ rrf). Before swapping: measure gchat in-domain end-to-end with
the retrieval fix.

**Next:** 1) in-domain gchat eval with the retrieval fix + md_raw_s7; 2) dense docstring
vector for class points to lift ColBERT-only recall; 3) regenerate dp groups with fixed
retrieval, retrain 2- and 3-module.

```bash
PYTHONPATH=. .venv/bin/python -m research.trm.h2.dp_wrapper mcp_types   # index any MODULES entry
PYTHONPATH=. .venv/bin/python -m research.trm.h2.generate_module_groups --wrapper mcp_types \
  --output research/trm/h2/mcp_types_search_groups.json
# --extra-search-data is repeated per file (not nargs)
```

---

## Part 4 — gchat in-domain end-to-end (2026-10-28)

New: `research/trm/h2/gchat_e2e_eval.py` — replays the 36 gchat val groups held out by both
`md_raw_s7` and `gchat_ctrl_s7` through the production wrapper (3 positives per query;
hit@1 / R@3 / R@10). `--retrieval old` swaps in the pre-fix grouped call.

### Production bug: `search_hybrid_learned` never runs a model on gchat or email

The domain guard compares `domain_config.domain_label` (`"Google Chat Cards"`,
`"Email Blocks (MJML)"`) to the checkpoint's `domain_id` (`"gchat"`, `"email"`). They never
match, so `SEARCH_MODE=learned` silently falls back to `multidim` (since v2.0.0). The same
label is passed to `_resolve_checkpoint_path(domain=…)`, so registry/artifact lookups by
domain miss too. `search_hybrid_recursive` has no guard and loads without a domain, so
`recursive` mode does use the model. Not fixed yet (the wrapper DomainConfig has no
`domain_id` field; needs one, set in `gchat/wrapper_setup.py` and
`gmail/email_wrapper_setup.py`).

### Results (guard bypassed in the eval)

| mode / checkpoint | retrieval | hit@1 | R@3 | R@10 |
|---|---|---|---|---|
| **rrf** (production default) | — | **69.4%** | **80.6%** | **88.9%** |
| multidim (what `learned` silently runs today) | — | 5.6% | 15.3% | 55.6% |
| learned, `checkpoints/` (default) | old | 50.0% | 65.3% | 80.1% |
| learned, `checkpoints/` (default) | new | 36.1% | 27.3% | 84.3% |
| learned, `gchat_ctrl_s7` | old / new | 41.7 / 47.2% | 61.1 / 31.9% | 75.5 / 44.0% |
| learned, `md_raw_s7` | old / new | 38.9 / 44.4% | 60.6 / 27.8% | 79.6 / 51.9% |

(`--content` doesn't help: −14 to +6 pts hit@1.)

- **No learned config beats rrf on gchat.** Don't deploy `md_raw_s7` (or any current
  checkpoint) as a gchat search replacement.
- **The new retrieval has better recall but current models rank worse with it.** On gchat, positive recall in
  the pool rises 0.86 → 0.96, but the new pool has more same-name nested classes (9.8
  unique names of 20 vs 14.1, e.g. six `DividerStyle`s) and the models — trained on
  old-style pools — rank those duplicates high, so R@3 falls. The old grouped pool looks
  near-random (`SlashCommandMetadataType`, `AutoNumber` for an image/divider query), and
  the July training candidates have that same character.
- **gchat training features are stale.** For the same query and candidate, live features
  differ from the stored ones: mean |Δ| sim_i_coverage 0.37, sim_c_coverage 0.17, DAG
  0.24–0.32. In July positives separated on sim_i (coverage 0.60 vs 0.33); live they don't
  (0.13 vs 0.15) — class `inputs` vectors now embed only the symbol name.

**Next:** regenerate gchat search groups through the live feature path + fixed retrieval
(as dp/mcp were), retrain, re-run this eval against rrf; add `domain_id` to the wrapper
DomainConfig and fix the guard; consider deduping same-name results.

---

## Part 5 — fixes + live gchat retrain (2026-10-28)

### Code changes (production paths)

| change | file |
|---|---|
| `DomainConfig.domain_id` ("gchat" / "email"); learned guard + recursive checkpoint lookup key on it, not `domain_label` | `adapters/module_wrapper/domain_mixin.py`, `gchat/wrapper_setup.py`, `gmail/email_wrapper_setup.py`, `_hybrid_learned.py`, `_hybrid_recursive.py` |
| `_query_grouped_candidates`: fused `query_points` without vectors → per-type caps → `retrieve` vectors for kept ids only (the one-call version moved 60 ColBERT multivector sets and hit gRPC deadlines on cloud Qdrant) | `_hybrid_helpers.py` |
| `_categorize_scored_results` dedupes same-name classes (best score kept, others in `alt_full_paths`) — learned/multidim/recursive only; rrf unchanged | `_hybrid_helpers.py` |
| tests | `tests/module/test_grouped_candidates.py`, `tests/module/test_learned_domain_guard.py` (module suite 530 passed) |

**Behavior change:** with the guard fixed, `SEARCH_MODE=learned` now actually runs the
checkpoint on gchat/email instead of multidim. Note `_learned_model` is cached per class,
so the gchat and email wrappers (same class) share whichever checkpoint loads first; the
guard then sends the other domain to multidim (pre-existing).

### Live gchat groups

`research/trm/h2/regen_gchat_groups.py` → `gchat_live_groups.json`: same 642 labelled
queries, content and build pairs; candidates/features recomputed through the live path
(fixed retrieval, features over classes + instance patterns, class rows kept). Positives
retrieved 1066/1172 (91%), 106 injected.

### gchat end-to-end (each checkpoint's own val groups, names deduped for every mode)

| checkpoint | groups | rrf hit@1 | learned hit@1 | rrf R@10 | learned R@10 |
|---|---|---|---|---|---|
| `live_s7` / `s42` / `s123` (gchat live) | 132 / 129 / 131 | 73.5 / 63.6 / 66.4% | 64.4 / **80.6** / **74.0%** | 90.0 / 81.7 / 83.0% | 94.1 / 91.0 / 91.6% |
| `live_md_s7` / `s42` / `s123` (gchat live + dp) | 135 / 133 / 107 | 65.2 / 57.1 / 57.0% | **73.3 / 75.9 / 83.2%** | 86.5 / 81.6 / 79.8% | 93.6 / 90.2 / 88.9% |
| `md_raw_s7` (July gchat + dp) | 135 | 65.2% | 65.2% | 86.5% | 91.5% |

### Transfer (qdrant_client.models, n=150; rrf 23.3%)

`live_md_s7 / s42 / s123`: 23.3 / 22.0 / 20.7% (MRR 0.253 / 0.238 / 0.235 vs rrf 0.243).
`live_s42` (gchat only): 8.0%.

**Result:** gchat + dp trained on live features beats rrf on gchat on every seed
(+8 to +26 pts hit@1, +7 to +9 pts R@10) and matches rrf on the unseen module. The second
module is still required for transfer. **Best candidate: `checkpoints_live_md_s7`**
(val_pool 65.9%, same band as every current-code run). Not deployed: production default
is `SEARCH_MODE=rrf`; switching gchat to learned is a separate decision.

**Next:** decide on deploying `live_md_s7` for gchat (upload to the model artifact bucket
under the gchat key, `SEARCH_MODE=learned`); regenerate dp groups with the fixed retrieval
for consistency; class `inputs` vectors still embed only the symbol name (recall ceiling).
