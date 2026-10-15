import math
import random

import pytest

from llmkit import data, inference, scaling


# ---------------------------------------------------------------- inference


def test_llama2_13b_matches_lecture_numbers():
    cfg = inference.LLAMA2_13B
    assert 12.9e9 < cfg.num_params() < 13.1e9
    assert cfg.kv_cache_bytes_per_sequence() == 838_860_800
    one = inference.inference_stats(cfg, inference.H100, batch=1)
    assert one.throughput == pytest.approx(124, abs=1)
    assert one.latency_s == pytest.approx(0.008, abs=0.0005)


def test_batch_trades_latency_for_throughput_until_memory_runs_out():
    cfg, hw = inference.LLAMA2_13B, inference.H100
    small, large = inference.inference_stats(cfg, hw, 1), inference.inference_stats(cfg, hw, 64)
    assert large.latency_s > small.latency_s
    assert large.throughput > small.throughput
    assert large.fits
    assert not inference.inference_stats(cfg, hw, 256).fits


def test_gqa_shrinks_kv_cache_and_improves_both_metrics():
    cfg, hw = inference.LLAMA2_13B, inference.H100
    gqa = inference.with_gqa(cfg, kv_heads=8)
    assert gqa.kv_cache_bytes_per_sequence() * 5 == cfg.kv_cache_bytes_per_sequence()
    base, fast = inference.inference_stats(cfg, hw, 64), inference.inference_stats(gqa, hw, 64)
    assert fast.latency_s < base.latency_s and fast.throughput > base.throughput
    assert inference.inference_stats(gqa, hw, 256).fits
    with pytest.raises(ValueError):
        inference.with_gqa(cfg, kv_heads=7)


def test_arithmetic_intensity():
    assert inference.H100.intensity == pytest.approx(295, abs=1)
    assert inference.matmul_intensity(1, 8192, 32768) == pytest.approx(1, abs=0.01)
    assert inference.matmul_intensity(64, 10**7, 10**7) == pytest.approx(64, rel=0.01)
    assert inference.attention_intensity(4096, 4096) == 2048  # prefill: S/2
    assert inference.attention_intensity(4096, 1) < 1  # generation: memory bound
    assert inference.mlp_intensity(128, 1) == 128


def test_speculative_sampling_is_lossless():
    draft = {"a": 0.6, "b": 0.3, "c": 0.1}
    target = {"a": 0.2, "b": 0.5, "c": 0.25, "d": 0.05}
    exact = inference.speculative_output_distribution(draft, target)
    for tok, q in target.items():
        assert exact[tok] == pytest.approx(q)
    rng = random.Random(0)
    n = 40_000
    counts = {}
    for _ in range(n):
        tok, _ = inference.speculative_step(draft, target, rng)
        counts[tok] = counts.get(tok, 0) + 1
    for tok, q in target.items():
        assert counts.get(tok, 0) / n == pytest.approx(q, abs=0.01)


def test_expected_tokens_per_target_pass():
    assert inference.expected_tokens_per_target_pass(0.0, 4) == 1
    assert inference.expected_tokens_per_target_pass(1.0, 4) == 5
    assert inference.expected_tokens_per_target_pass(0.8, 4) == pytest.approx(3.3616)


# ---------------------------------------------------------------- scaling


def test_wsd_schedule_shape():
    lr = lambda s: scaling.wsd_lr(s, 1e-3, warmup_steps=100, total_steps=1000)
    assert lr(0) == pytest.approx(1e-5)
    assert lr(99) == pytest.approx(1e-3)
    assert lr(500) == lr(899) == 1e-3
    assert lr(1000) == pytest.approx(1e-4)
    assert lr(950) < lr(900)


def test_wsd_stable_checkpoint_is_shared_across_horizons():
    short = [scaling.wsd_lr(s, 1e-3, 100, 1000) for s in range(900)]
    long = [scaling.wsd_lr(s, 1e-3, 100, 4000) for s in range(900)]
    assert short == long  # rewind to step 899 and re-decay for the longer run
    cos_short = [scaling.cosine_lr(s, 1e-3, 100, 1000) for s in range(900)]
    cos_long = [scaling.cosine_lr(s, 1e-3, 100, 4000) for s in range(900)]
    assert cos_short != cos_long


def test_fit_power_law_recovers_exponent():
    xs = [1e17, 1e18, 1e19, 1e20]
    law = scaling.fit_power_law(xs, [0.3 * x ** -0.125 for x in xs])
    assert law.exponent == pytest.approx(-0.125)
    assert law(1e21) == pytest.approx(0.3 * 1e21 ** -0.125)
    with pytest.raises(ValueError):
        scaling.fit_power_law([1.0], [1.0])


def test_mup_scaling_rules():
    assert scaling.mup_init_std(1024, 4096) == pytest.approx(1 / 32)
    assert scaling.mup_init_std(4096, 1024) == pytest.approx(1 / 64 * 0.5)
    assert scaling.mup_adam_lr(1e-2, fan_in=2048, base_fan_in=256) == pytest.approx(1.25e-3)
    assert scaling.mup_sgd_lr(0.1, fan_in=512, fan_out=2048) == pytest.approx(0.4)


def test_newton_schulz_flattens_singular_values():
    rng = random.Random(1)
    m = [[rng.gauss(0, 1) for _ in range(6)] for _ in range(4)]
    def spread(x):
        # k * sum(lambda^2) / (sum lambda)^2 over eigenvalues of X X^T; equals 1 when all singular values match
        gram = [[sum(a * b for a, b in zip(r1, r2)) for r2 in x] for r1 in x]
        trace = sum(gram[i][i] for i in range(len(gram)))
        trace_sq = sum(gram[i][j] * gram[j][i] for i in range(len(gram)) for j in range(len(gram)))
        return len(gram) * trace_sq / trace**2, trace / len(gram)

    o = scaling.newton_schulz_orthogonalize(m, steps=8)
    before, _ = spread(m)
    after, mean_sq_singular = spread(o)
    assert after < before and after < 1.1
    assert 0.45 < mean_sq_singular < 1.3  # Muon's quintic targets roughly-unit, not exact, singular values
    tall = scaling.newton_schulz_orthogonalize([list(r) for r in zip(*m)], steps=8)
    assert len(tall) == 6 and len(tall[0]) == 4


# ---------------------------------------------------------------- data


def test_training_permission():
    ok = data.Source("wiki", "cc-by-sa", True, True, True)
    collection = data.Source("hf-mix", "apache-2.0", False, True, True)
    pirated = data.Source("books3", "unknown", False, True, False)
    assert data.training_permission(ok) == "licensed"
    assert data.training_permission(collection) == "fair-use-risk"
    assert data.training_permission(pirated) == "excluded"


def test_robots_allows():
    robots = "User-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nDisallow: /private/\n"
    assert not data.robots_allows(robots, "ClaudeBot", "https://x.com/a")
    assert data.robots_allows(robots, "OtherBot", "https://x.com/a")
    assert not data.robots_allows(robots, "OtherBot", "https://x.com/private/a")


def test_c4_clean():
    page = (
        "Home | About\n"
        "The committee met on Tuesday to review the plan.\n"
        "Members agreed that the budget needed more detail.\n"
        "A final vote is scheduled for next month at noon.\n"
        "Please read our terms of use before continuing here.\n"
    )
    cleaned = data.c4_clean(page)
    assert cleaned is not None and "Home" not in cleaned and "terms of use" not in cleaned
    assert data.c4_clean("function f() { return 1; }") is None
    assert data.c4_clean("Too short. Only two sentences here today.") is None


def test_quality_classifier_separates_target_from_raw():
    good = ["the theorem proof uses induction on the integer n", "we derive the equation and prove the lemma"]
    bad = ["buy cheap pills now click here free", "hot deals click now limited offer free shipping"]
    clf = data.NaiveBayesQualityClassifier().fit(good, bad)
    assert clf.score("a short proof of the lemma by induction") > 0.9
    assert clf.score("click here for free deals") < 0.1


def test_exact_dedup():
    assert data.exact_dedup(["a  b", "a b", "c"]) == ["a  b", "c"]


def test_minhash_estimates_jaccard():
    a, b = {"1", "2", "3", "4"}, {"1", "2", "3", "5"}
    assert data.jaccard(a, b) == 0.6
    sa, sb = data.minhash_signature(a, 2000), data.minhash_signature(b, 2000)
    assert sum(x == y for x, y in zip(sa, sb)) / 2000 == pytest.approx(0.6, abs=0.04)


def test_lsh_curve():
    assert data.lsh_collision_probability(0.8, bands=5, rows=10) == pytest.approx(1 - (1 - 0.8 ** 10) ** 5)
    t = data.lsh_threshold(20, 450)
    assert data.lsh_collision_probability(t, 20, 450) == pytest.approx(1 - 1 / math.e, abs=0.01)
    # more rows sharpens and shifts right; more bands shifts left
    assert data.lsh_collision_probability(0.9, 10, 20) < data.lsh_collision_probability(0.9, 10, 10)
    assert data.lsh_collision_probability(0.9, 20, 10) > data.lsh_collision_probability(0.9, 10, 10)


def test_near_dedup_removes_templated_copies():
    base = "This product description is for a full face gas mask with dual filters and adjustable straps for adults"
    docs = [
        base,
        base + " in Canada",
        base.replace("adults", "grownups"),
        "An unrelated article about the history of the printing press in Europe during the fifteenth century",
    ]
    groups = data.near_duplicate_groups(docs, bands=20, rows=5, shingle_size=3, verify_threshold=0.7)
    assert groups == [[0, 1, 2]]
    assert data.near_dedup(docs, bands=20, rows=5, shingle_size=3, verify_threshold=0.7) == [docs[0], docs[3]]


def test_naive_mixture_epoch_trap_and_unimax():
    sources = {"low": 10e12, "high": 10e9}
    epochs = data.epochs_per_source({"low": 0.5, "high": 0.5}, sources, 1e12)
    assert epochs["high"] == pytest.approx(50)
    assert epochs["low"] == pytest.approx(0.05)
    weights = data.unimax_weights(sources, 1e12, max_epochs=4)
    assert sum(weights.values()) == pytest.approx(1)
    capped = data.epochs_per_source(weights, sources, 1e12)
    assert capped["high"] == pytest.approx(4)
    with pytest.raises(ValueError):
        data.unimax_weights({"tiny": 1e6}, 1e12, max_epochs=4)


def test_downsample_for_proxy():
    assert data.downsample_for_proxy({"wiki": 1e10}, proxy_tokens=1e10, target_tokens=1e12) == {"wiki": 1e8}
