"""Transformer inference cost model: arithmetic intensity, KV cache, latency, throughput.

Generation is memory bound, so per-step latency is approximated as the bytes that must
move from HBM (parameters + every sequence's KV cache) divided by memory bandwidth.
"""
import random
from dataclasses import dataclass, replace

BYTES_BF16 = 2


@dataclass(frozen=True)
class Hardware:
    name: str
    flops_per_s: float
    hbm_bytes_per_s: float
    hbm_bytes: float

    @property
    def intensity(self) -> float:
        """Accelerator arithmetic intensity (FLOPs per byte). Above it you are compute bound."""
        return self.flops_per_s / self.hbm_bytes_per_s


H100 = Hardware("H100 SXM", flops_per_s=989e12, hbm_bytes_per_s=3.35e12, hbm_bytes=80e9)


@dataclass(frozen=True)
class TransformerConfig:
    """S=context tokens, D=model dim, F=MLP dim, N=query heads, K=KV heads, H=head dim, L=layers, V=vocab."""

    S: int
    D: int
    F: int
    N: int
    K: int
    H: int
    L: int
    V: int

    def num_params(self) -> int:
        attention = self.D * self.N * self.H * 2 + self.D * self.K * self.H * 2  # Q, O + K, V
        mlp = 3 * self.D * self.F  # gate, up, down
        embeddings = 2 * self.V * self.D  # input embedding + LM head
        return self.L * (attention + mlp) + embeddings

    def kv_cache_bytes_per_sequence(self) -> int:
        return self.S * self.K * self.H * self.L * 2 * BYTES_BF16  # 2 = key and value

    def memory_bytes(self, batch: int) -> int:
        return batch * self.kv_cache_bytes_per_sequence() + self.num_params() * BYTES_BF16


LLAMA2_13B = TransformerConfig(S=1024, D=5120, F=13824, N=40, K=40, H=128, L=40, V=32000)


def with_gqa(config: TransformerConfig, kv_heads: int) -> TransformerConfig:
    if config.N % kv_heads:
        raise ValueError("query heads must divide evenly into KV groups")
    return replace(config, K=kv_heads)


@dataclass(frozen=True)
class InferenceStats:
    batch: int
    memory_bytes: int
    fits: bool
    latency_s: float  # seconds per generated token, per sequence
    throughput: float  # tokens per second across the batch


def inference_stats(config: TransformerConfig, hw: Hardware, batch: int) -> InferenceStats:
    memory = config.memory_bytes(batch)
    latency = memory / hw.hbm_bytes_per_s
    return InferenceStats(batch, memory, memory <= hw.hbm_bytes, latency, batch / latency)


def matmul_intensity(b: int, d: int, f: int) -> float:
    """Intensity of (B x D) @ (D x F) in bf16; tends to B when B << D, F."""
    flops = 2 * b * d * f
    bytes_moved = BYTES_BF16 * (b * d + d * f + b * f)
    return flops / bytes_moved


def mlp_intensity(b: int, t: int) -> float:
    """Leading-order MLP intensity: B*T (prefill: B*S, generation: B)."""
    return float(b * t)


def attention_intensity(s: int, t: int) -> float:
    """Leading-order attention intensity: S*T/(S+T). Independent of batch: each sequence has its own KV."""
    return s * t / (s + t)


def speculative_step(
    draft: dict, target: dict, rng: random.Random
) -> tuple:
    """One accept/reject step of speculative sampling for a single position.

    ``draft`` (p) and ``target`` (q) map token -> probability. Returns (token, accepted).
    The returned token is distributed exactly according to ``target``.
    """
    x = _sample(draft, rng)
    p, q = draft.get(x, 0.0), target.get(x, 0.0)
    if rng.random() < min(1.0, q / p):
        return x, True
    return _sample(residual_distribution(draft, target), rng), False


def residual_distribution(draft: dict, target: dict) -> dict:
    """Normalized max(q - p, 0): what to resample from after a rejection."""
    raw = {tok: max(target.get(tok, 0.0) - draft.get(tok, 0.0), 0.0) for tok in set(draft) | set(target)}
    total = sum(raw.values())
    if total == 0:
        return dict(target)
    return {tok: w / total for tok, w in raw.items() if w > 0}


def speculative_output_distribution(draft: dict, target: dict) -> dict:
    """Exact output distribution of ``speculative_step`` (equals ``target``; used to verify losslessness)."""
    residual = residual_distribution(draft, target)
    reject_mass = sum(p * (1 - min(1.0, target.get(t, 0.0) / p)) for t, p in draft.items() if p > 0)
    out = {}
    for tok in set(draft) | set(target):
        p = draft.get(tok, 0.0)
        accepted = p * min(1.0, target.get(tok, 0.0) / p) if p > 0 else 0.0
        out[tok] = accepted + reject_mass * residual.get(tok, 0.0)
    return out


def expected_tokens_per_target_pass(acceptance: float, draft_tokens: int) -> float:
    """Expected tokens emitted per target forward pass with i.i.d. acceptance rate (Leviathan et al.)."""
    if acceptance >= 1.0:
        return float(draft_tokens + 1)
    return (1 - acceptance ** (draft_tokens + 1)) / (1 - acceptance)


def _sample(dist: dict, rng: random.Random):
    r = rng.random() * sum(dist.values())
    acc = 0.0
    for tok, w in dist.items():
        acc += w
        if r < acc:
            return tok
    return next(reversed(dist))
