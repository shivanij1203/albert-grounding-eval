"""Load and validate the eval cases."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

EXPECTATIONS = frozenset({"answer", "refuse", "both_products"})


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    question: str
    expect: str
    must_include: tuple[tuple[str, ...], ...]
    must_not: tuple[str, ...]
    gold: tuple[str, ...]
    why: str = ""


def _parse(raw: dict, source_ids: frozenset[str]) -> Case:
    case = Case(
        id=raw["id"], category=raw["category"], question=raw["question"],
        expect=raw["expect"],
        must_include=tuple(tuple(group) for group in raw["must_include"]),
        must_not=tuple(raw["must_not"]), gold=tuple(raw["gold"]), why=raw.get("why", ""),
    )
    if case.expect not in EXPECTATIONS:
        raise ValueError(f"{case.id}: unknown expect {case.expect!r}")
    if case.expect != "refuse" and not case.gold:
        raise ValueError(f"{case.id}: an answerable case needs at least one gold source")
    missing = [g for g in case.gold if g not in source_ids]
    if missing:
        raise ValueError(f"{case.id}: gold sources not in corpus: {missing}")
    for pattern in [p for group in case.must_include for p in group] + list(case.must_not):
        re.compile(pattern)  # fail at load time, not mid-run
    return case


def load_cases(path: Path, source_ids: frozenset[str]) -> tuple[Case, ...]:
    raw = json.loads(path.read_text())
    cases = tuple(_parse(c, source_ids) for c in raw["cases"])
    ids = [c.id for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate case ids: {sorted(dupes)}")
    return cases
