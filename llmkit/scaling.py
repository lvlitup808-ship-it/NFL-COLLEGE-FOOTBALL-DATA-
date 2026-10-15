"""Scaling-law helpers: WSD / cosine schedules, power-law fits, muP per-layer scaling."""
import math
from dataclasses import dataclass


def wsd_lr(
    step: int,
    peak_lr: float,
    warmup_steps: int,
    total_steps: int,
    decay_fraction: float = 0.1,
    final_ratio: float = 0.1,
) -> float:
    """Warmup-Stable-Decay. Warmup is a fixed step count; the last ``decay_fraction`` decays
    linearly to ``final_ratio * peak_lr``. Any stable-phase checkpoint can be resumed and
    re-decayed to a longer horizon, unlike cosine."""
    if step < warmup_steps:
        return peak_lr * (step + 1) / warmup_steps
    decay_start = int(total_steps * (1 - decay_fraction))
    if step < decay_start:
        return peak_lr
    progress = min(1.0, (step - decay_start) / max(1, total_steps - decay_start))
    return peak_lr * (1 - progress * (1 - final_ratio))


def cosine_lr(step: int, peak_lr: float, warmup_steps: int, total_steps: int, final_ratio: float = 0.1) -> float:
    if step < warmup_steps:
        return peak_lr * (step + 1) / warmup_steps
    progress = min(1.0, (step - warmup_steps) / max(1, total_steps - warmup_steps))
    floor = peak_lr * final_ratio
    return floor + (peak_lr - floor) * 0.5 * (1 + math.cos(math.pi * progress))


@dataclass(frozen=True)
class PowerLaw:
    """y = coefficient * x ** exponent, fit in log-log space."""

    coefficient: float
    exponent: float

    def __call__(self, x: float) -> float:
        return self.coefficient * x ** self.exponent


def fit_power_law(xs: list, ys: list) -> PowerLaw:
    """Least-squares line through (log x, log y), e.g. DeepSeek-style optimal LR/batch vs compute."""
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("need at least two paired points")
    lx = [math.log(x) for x in xs]
    ly = [math.log(y) for y in ys]
    mx, my = sum(lx) / len(lx), sum(ly) / len(ly)
    var = sum((a - mx) ** 2 for a in lx)
    if var == 0:
        raise ValueError("x values must not all be equal")
    slope = sum((a - mx) * (b - my) for a, b in zip(lx, ly)) / var
    return PowerLaw(math.exp(my - slope * mx), slope)


def mup_init_std(fan_in: int, fan_out: int) -> float:
    """sigma = 1/sqrt(fan_in) * min(1, sqrt(fan_out/fan_in)) keeps activations O(1) per unit."""
    return (1 / math.sqrt(fan_in)) * min(1.0, math.sqrt(fan_out / fan_in))


def mup_sgd_lr(base_lr: float, fan_in: int, fan_out: int) -> float:
    """SGD per-layer LR proportional to fan_out / fan_in."""
    return base_lr * fan_out / fan_in


def mup_adam_lr(base_lr: float, fan_in: int, base_fan_in: int) -> float:
    """Adam per-layer LR proportional to 1 / fan_in, anchored at the width the base LR was tuned on."""
    return base_lr * base_fan_in / fan_in


def newton_schulz_orthogonalize(matrix: list, steps: int = 5) -> list:
    """Approximate U V^T of ``matrix`` with matmuls only (the Muon update direction).

    Uses the quintic iteration X <- aX + (bA + cA^2)X with A = X X^T from Muon.
    """
    a, b, c = 3.4445, -4.7750, 2.0315
    transposed = len(matrix) > len(matrix[0])
    x = _t(matrix) if transposed else [row[:] for row in matrix]
    norm = math.sqrt(sum(v * v for row in x for v in row)) + 1e-7
    x = [[v / norm for v in row] for row in x]
    for _ in range(steps):
        gram = _mm(x, _t(x))
        poly = _add(_scale(gram, b), _scale(_mm(gram, gram), c))
        x = _add(_scale(x, a), _mm(poly, x))
    return _t(x) if transposed else x


def _t(m):
    return [list(col) for col in zip(*m)]


def _mm(a, b):
    bt = _t(b)
    return [[sum(x * y for x, y in zip(row, col)) for col in bt] for row in a]


def _add(a, b):
    return [[x + y for x, y in zip(ra, rb)] for ra, rb in zip(a, b)]


def _scale(a, s):
    return [[x * s for x in row] for row in a]
