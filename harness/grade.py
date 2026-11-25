"""Deterministic grading. No model grades another model here.

An answer passes only if all of these hold:
  * behavior: it answers when the sources cover the question and hands off when
    they don't (both_products cases must answer and separate the products)
  * facts: every required fact group appears
  * no forbidden claim appears
  * for systems that cite: at least one citation, and every quoted span appears
    verbatim in the source it names
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from harness.evalset import Case

_HANDOFF = re.compile(
    r"(don't|do not|can't|cannot|can not|unable to|not able to) "
    r"(have|see|access|find|answer|provide|give|tell|confirm|recommend|help with)"
    r"|(don't|do not) know|can't say|cannot say|unable to view|reach out to"
    r"|not covered|isn't covered|outside (of )?what|contact (albert )?(support|customer)"
    r"|check (the|your) (albert )?app|live (support )?agent|financial (advisor|professional)",
    re.I,
)
_QUOTE_NORMALIZE = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


@dataclass(frozen=True)
class Citation:
    source_id: str
    quote: str


@dataclass(frozen=True)
class Response:
    status: str  # "answered" | "refused"
    answer: str
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True)
class Grade:
    passed: bool
    behavior_ok: bool
    facts_hit: int
    facts_total: int
    violations: tuple[str, ...]
    citations_valid: int
    citations_total: int
    gold_cited: bool
    reasons: tuple[str, ...]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTE_NORMALIZE)).strip().lower()


def quote_supported(quote: str, source_text: str) -> bool:
    q = normalize(quote).strip(" .\"'")
    return len(q) >= 12 and q in normalize(source_text)


def looks_like_handoff(response: Response) -> bool:
    return response.status == "refused" or bool(_HANDOFF.search(response.answer))


def _behavior_ok(case: Case, response: Response) -> bool:
    # One rule for every system: on a must-refuse case, the answer has to read as a
    # handoff, whether or not it came with a structured status.
    # On answerable cases the content decides, for every system: the required facts and
    # forbidden claims below. A structured "refused" that still states the right facts is
    # not penalized, the same as a free-text answer that ends with "contact support".
    if case.expect == "refuse":
        return bool(_HANDOFF.search(response.answer))
    return True


def grade(case: Case, response: Response, sources: dict[str, str], cites_expected: bool) -> Grade:
    text = response.answer
    reasons: list[str] = []

    behavior_ok = _behavior_ok(case, response)
    if not behavior_ok:
        reasons.append("should have handed off")

    hits = [any(re.search(p, text, re.I | re.M) for p in group) for group in case.must_include]
    reasons.extend(f"missing fact: {case.must_include[i][0]}" for i, ok in enumerate(hits) if not ok)

    violations = tuple(p for p in case.must_not if re.search(p, text, re.I | re.M))
    reasons.extend(f"forbidden claim: {p}" for p in violations)

    valid = [c for c in response.citations if quote_supported(c.quote, sources.get(c.source_id, ""))]
    gold_cited = any(c.source_id in case.gold for c in valid)
    if cites_expected and response.status == "answered":
        if not response.citations:
            reasons.append("answered without a citation")
        elif len(valid) < len(response.citations):
            reasons.append(f"{len(response.citations) - len(valid)} citation(s) not found in source")

    return Grade(
        passed=not reasons, behavior_ok=behavior_ok,
        facts_hit=sum(hits), facts_total=len(hits), violations=violations,
        citations_valid=len(valid), citations_total=len(response.citations),
        gold_cited=gold_cited, reasons=tuple(reasons),
    )
