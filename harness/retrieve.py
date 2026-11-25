"""BM25 passage retrieval over the source corpus.

Sources are split into overlapping word windows so a 26,000-word Terms of Use
competes fairly with a 100-word help article. Each passage carries its source
title, which is also indexed, because titles are the strongest topical signal
in a help center.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

WINDOW_WORDS = 140
STRIDE_WORDS = 100
BM25_K1 = 1.5
BM25_B = 0.75

_TOKEN = re.compile(r"[a-z0-9$]+(?:[.,][0-9]+)*")
_STOP = frozenset(
    "a an and are as at be by can do does for from how i if in is it my of on or "
    "the to what when will with you your me we our this that there".split()
)


@dataclass(frozen=True)
class Passage:
    source_id: str
    title: str
    url: str
    text: str


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def split_passages(source: dict) -> list[Passage]:
    words = source["text"].split()
    starts = range(0, max(len(words) - WINDOW_WORDS, 0) + 1, STRIDE_WORDS)
    windows = [" ".join(words[s:s + WINDOW_WORDS]) for s in starts]
    # Keep the tail that a fixed stride can skip.
    tail_start = starts[-1] + WINDOW_WORDS
    if tail_start < len(words):
        windows.append(" ".join(words[tail_start - (WINDOW_WORDS - STRIDE_WORDS):]))
    return [Passage(source["id"], source["title"], source["url"], w) for w in windows]


class Retriever:
    def __init__(self, sources: list[dict]) -> None:
        if not sources:
            raise ValueError("cannot build a retriever over an empty corpus")
        self.passages = tuple(p for s in sources for p in split_passages(s))
        self._docs = tuple(
            Counter(tokenize(f"{p.title} {p.title} {p.text}")) for p in self.passages
        )
        self._lengths = tuple(sum(d.values()) for d in self._docs)
        self._avg_len = sum(self._lengths) / len(self._lengths)
        df = Counter(term for d in self._docs for term in d)
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def _score(self, terms: list[str], i: int) -> float:
        doc, length = self._docs[i], self._lengths[i]
        norm = BM25_K1 * (1 - BM25_B + BM25_B * length / self._avg_len)
        return sum(
            self._idf[t] * doc[t] * (BM25_K1 + 1) / (doc[t] + norm)
            for t in terms if t in doc
        )

    def search(self, query: str, k: int = 6, max_per_source: int = 2) -> list[Hit]:
        terms = tokenize(query)
        scored = sorted(
            ((self._score(terms, i), i) for i in range(len(self.passages))),
            reverse=True,
        )
        hits: list[Hit] = []
        per_source: Counter = Counter()
        for score, i in scored:
            if score <= 0 or len(hits) == k:
                break
            p = self.passages[i]
            if per_source[p.source_id] < max_per_source:
                hits.append(Hit(p, round(score, 3)))
                per_source[p.source_id] += 1
        return hits
