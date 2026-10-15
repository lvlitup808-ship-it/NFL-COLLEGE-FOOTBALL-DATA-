# llmkit — LLM inference, scaling and data reference code

`llmkit/` is a stdlib-only, tested implementation of the techniques from four lectures (inference, scaling laws II, data sources, data pipeline). It is **not part of the FIELDMIND pilot**: nothing in `app/` imports it, it is excluded from the Docker image, and it does not change the locked pilot scope in `docs/WEEKLY_WEDGE_EXECUTION.md`.

Run its tests: `python -m pytest -q tests/test_llmkit.py`

## `llmkit/inference.py`

| Function | Lecture idea |
|---|---|
| `matmul_intensity`, `mlp_intensity`, `attention_intensity`, `Hardware.intensity` | Prefill is compute bound; generation is memory bound. MLP intensity ≈ B·T, attention ≈ S·T/(S+T) — independent of batch because every sequence has its own KV cache. H100 ≈ 295 FLOPs/byte. |
| `TransformerConfig`, `LLAMA2_13B`, `inference_stats` | Params, KV cache (S·K·H·L·2·2 bytes), memory, latency = bytes / HBM bandwidth, throughput = B / latency. Reproduces ~124 tok/s at B=1 on H100 and out-of-memory at B=256. |
| `with_gqa` | Grouped-query attention shrinks the KV cache by N/K, improving latency *and* throughput and allowing larger batches. |
| `speculative_step`, `speculative_output_distribution`, `expected_tokens_per_target_pass` | Speculative sampling: accept with min(1, q/p), else resample from norm(max(q−p, 0)). Output is exactly the target distribution (tested analytically and by sampling). |

## `llmkit/scaling.py`

| Function | Lecture idea |
|---|---|
| `wsd_lr`, `cosine_lr` | Warmup-Stable-Decay (MiniCPM): stable-phase checkpoints are horizon-independent, so one long run + cheap re-decays gives Chinchilla data sweeps. Cosine is not. |
| `fit_power_law` | DeepSeek-style: grid-search optimal LR / batch at small compute, fit log-log line, extrapolate. |
| `mup_init_std`, `mup_sgd_lr`, `mup_adam_lr` | μP: init σ = 1/√fan_in · min(1, √(fan_out/fan_in)); SGD LR ∝ fan_out/fan_in; Adam LR ∝ 1/fan_in so the optimal LR transfers across width. |
| `newton_schulz_orthogonalize` | Muon's matmul-only approximation of U·Vᵀ for matrix-shaped updates. |

## `llmkit/data.py`

| Function | Lecture idea |
|---|---|
| `Source`, `training_permission` | Licensed vs. fair-use risk vs. excluded. Collection licenses don't cover individual works; unlawful acquisition (shadow libraries) is excluded regardless of fair use. |
| `robots_allows` | robots.txt check before crawling (stdlib `urllib.robotparser`). |
| `c4_clean` | C4 rules: lines end in punctuation, ≥5 words, ≥3 sentences, drop `{`, bad words, boilerplate. |
| `NaiveBayesQualityClassifier` | Target-vs-raw bag-of-words classifier (the fastText role in GPT-3/DCLM/phi-1 filtering). The keep threshold depends on token budget: longer runs tolerate lower quality. |
| `exact_dedup`, `jaccard`, `shingles`, `minhash_signature` | P(MinHash collision) = Jaccard. |
| `lsh_collision_probability`, `lsh_threshold`, `near_duplicate_groups`, `near_dedup` | LSH banding: 1 − (1 − s^r)^b; threshold ≈ (1/b)^(1/r). More rows sharpen/shift right, more bands shift left. Candidates are verified with true Jaccard. |
| `epochs_per_source`, `unimax_weights`, `downsample_for_proxy` | The 50-epoch trap of naive mixtures; UniMax uniform mixing with an epoch cap; simulated epoching so small proxy runs see large-run data scarcity. |

## Not implemented

Training-scale items with nothing meaningful to compute without a model or GPU: MLA, sliding-window/linear attention, quantization (GPTQ/AWQ), pruning + distillation, continuous batching, PagedAttention, regression-based mixture search (needs proxy training runs), HTML/PDF extraction, and synthetic post-training data generation.
