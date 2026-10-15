"""Pretraining data pipeline primitives: source rights, rule filters, a fast quality
classifier, exact and MinHash-LSH near-duplicate removal, and epoch-aware mixing."""
import hashlib
import math
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from urllib import robotparser

# ---------------------------------------------------------------- source rights

PERMISSIVE_LICENSES = {"public-domain", "cc0", "cc-by", "cc-by-sa", "mit", "apache-2.0", "bsd"}


@dataclass(frozen=True)
class Source:
    name: str
    license: str
    license_is_per_item: bool  # a collection-level license does not cover the works inside it
    terms_allow_training: bool
    obtained_lawfully: bool  # e.g. not from a shadow library


def training_permission(source: Source) -> str:
    """'licensed', 'fair-use-risk' or 'excluded'. Training-as-fair-use is unsettled; unlawful acquisition is not."""
    if not source.obtained_lawfully or not source.terms_allow_training:
        return "excluded"
    if source.license.lower() in PERMISSIVE_LICENSES and source.license_is_per_item:
        return "licensed"
    return "fair-use-risk"


def robots_allows(robots_txt: str, user_agent: str, url: str) -> bool:
    parser = robotparser.RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(user_agent, url)


# ---------------------------------------------------------------- rule filters

_BAD_PHRASES = ("lorem ipsum", "terms of use", "cookie policy", "javascript must be enabled")


def c4_clean(document: str, bad_words: frozenset = frozenset()) -> str | None:
    """C4-style heuristics. Returns cleaned text, or None if the page is dropped."""
    lowered = document.lower()
    if "{" in document or any(w in lowered.split() for w in bad_words):
        return None
    kept = []
    for line in document.splitlines():
        line = line.strip()
        if len(line.split()) < 5 or not line.endswith((".", "!", "?", '"')):
            continue
        if any(p in line.lower() for p in _BAD_PHRASES):
            continue
        kept.append(line)
    text = "\n".join(kept)
    if len(re.findall(r"[.!?](\s|$)", text)) < 3:
        return None
    return text


# ---------------------------------------------------------------- quality classifier

_TOKEN = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> list:
    return _TOKEN.findall(text.lower())


class NaiveBayesQualityClassifier:
    """Bag-of-words target-vs-raw classifier (the fastText role in DCLM/GPT-3 filtering).

    Positives come from the target set (e.g. LLM-labelled 'educational' pages),
    negatives from a raw web sample. ``score`` returns P(target | text).
    """

    def __init__(self, alpha: float = 1.0):
        self.alpha = alpha
        self.counts = {True: Counter(), False: Counter()}
        self.docs = {True: 0, False: 0}

    def fit(self, positives: list, negatives: list) -> "NaiveBayesQualityClassifier":
        for label, docs in ((True, positives), (False, negatives)):
            for doc in docs:
                self.counts[label].update(_tokens(doc))
                self.docs[label] += 1
        return self

    def score(self, text: str) -> float:
        vocab = len(set(self.counts[True]) | set(self.counts[False])) or 1
        total_docs = self.docs[True] + self.docs[False]
        logp = {}
        for label in (True, False):
            denom = sum(self.counts[label].values()) + self.alpha * vocab
            logp[label] = math.log((self.docs[label] + 1) / (total_docs + 2)) + sum(
                math.log((self.counts[label][tok] + self.alpha) / denom) for tok in _tokens(text)
            )
        diff = max(-700.0, min(700.0, logp[False] - logp[True]))
        return 1 / (1 + math.exp(diff))


# ---------------------------------------------------------------- deduplication


def exact_dedup(items: list) -> list:
    """Keep the first occurrence of each exact item (whitespace-normalized)."""
    seen = set()
    out = []
    for item in items:
        digest = hashlib.sha256(" ".join(item.split()).encode()).digest()
        if digest not in seen:
            seen.add(digest)
            out.append(item)
    return out


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def shingles(text: str, n: int = 5) -> set:
    toks = _tokens(text)
    if len(toks) < n:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def _hash(seed: int, item: str) -> int:
    digest = hashlib.blake2b(item.encode(), digest_size=8, key=struct.pack("<Q", seed)).digest()
    return int.from_bytes(digest, "little")


def minhash_signature(items: set, num_hashes: int) -> tuple:
    """P(signature[i] equal for A and B) = Jaccard(A, B) for each independent seed i."""
    if not items:
        return tuple([0] * num_hashes)
    return tuple(min(_hash(seed, it) for it in items) for seed in range(num_hashes))


def lsh_collision_probability(similarity: float, bands: int, rows: int) -> float:
    """1 - (1 - s^r)^b: an S-curve that sharpens with r and shifts left with b."""
    return 1 - (1 - similarity ** rows) ** bands


def lsh_threshold(bands: int, rows: int) -> float:
    """Approximate phase-transition similarity (1/b)^(1/r)."""
    return (1 / bands) ** (1 / rows)


def near_duplicate_groups(
    docs: list, bands: int = 20, rows: int = 5, shingle_size: int = 5, verify_threshold: float | None = 0.8
) -> list:
    """MinHash-LSH candidate pairs, optionally verified by true Jaccard; returns index groups."""
    sets = [shingles(d, shingle_size) for d in docs]
    sigs = [minhash_signature(s, bands * rows) for s in sets]
    parent = list(range(len(docs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for band in range(bands):
        buckets = defaultdict(list)
        for idx, sig in enumerate(sigs):
            buckets[sig[band * rows:(band + 1) * rows]].append(idx)
        for members in buckets.values():
            for other in members[1:]:
                if verify_threshold is None or jaccard(sets[members[0]], sets[other]) >= verify_threshold:
                    parent[find(other)] = find(members[0])
    groups = defaultdict(list)
    for idx in range(len(docs)):
        groups[find(idx)].append(idx)
    return [g for g in groups.values() if len(g) > 1]


def near_dedup(docs: list, **kwargs) -> list:
    """Keep one document per near-duplicate group (the first)."""
    drop = {i for group in near_duplicate_groups(docs, **kwargs) for i in sorted(group)[1:]}
    return [d for i, d in enumerate(docs) if i not in drop]


# ---------------------------------------------------------------- mixing


def epochs_per_source(weights: dict, source_tokens: dict, train_tokens: float) -> dict:
    """How many times each source is repeated. Always check this before trusting a mixture."""
    return {name: weights[name] * train_tokens / source_tokens[name] for name in weights}


def unimax_weights(source_tokens: dict, train_tokens: float, max_epochs: float) -> dict:
    """UniMax: as uniform as possible, but no source exceeds ``max_epochs``.

    Smallest sources are capped first; their leftover budget is spread uniformly over the rest.
    """
    remaining_budget = float(train_tokens)
    remaining = sorted(source_tokens, key=source_tokens.get)
    alloc = {}
    while remaining:
        share = remaining_budget / len(remaining)
        name = remaining[0]
        cap = source_tokens[name] * max_epochs
        if cap < share:
            alloc[name] = cap
            remaining_budget -= cap
            remaining.pop(0)
        else:
            for n in remaining:
                alloc[n] = share
            break
    total = sum(alloc.values())
    if total < train_tokens * (1 - 1e-9):
        raise ValueError("not enough data to reach train_tokens under the epoch cap")
    return {n: a / total for n, a in alloc.items()}


def downsample_for_proxy(source_tokens: dict, proxy_tokens: float, target_tokens: float) -> dict:
    """Simulated epoching: shrink each source by proxy/target so small proxy runs feel the
    same data scarcity the large run will, and mixture search stops over-weighting tiny sources."""
    ratio = proxy_tokens / target_tokens
    return {name: tokens * ratio for name, tokens in source_tokens.items()}
