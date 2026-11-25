"""Run the eval.

    python -m harness.run --retrieval-only        # no model calls: gold-source recall
    python -m harness.run                          # all three systems, every case
    python -m harness.run --systems grounded --cases adv-late-fees,price-genius
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from harness import systems
from harness.evalset import Case, load_cases
from harness.grade import grade
from harness.llm import DEFAULT_MODEL, CachedAnthropic, load_api_key
from harness.retrieve import Retriever

ROOT = Path(__file__).resolve().parent.parent
SYSTEMS = ("closed_book", "naive_rag", "grounded")
WORKERS = 4
log = logging.getLogger("eval")


def load_corpus() -> list[dict]:
    return json.loads((ROOT / "data" / "corpus.json").read_text())


def retrieval_report(retriever: Retriever, cases: tuple[Case, ...]) -> dict:
    rows = []
    for case in (c for c in cases if c.gold):
        for k in sorted({6, systems.RETRIEVAL_K}):
            got = [h.passage.source_id for h in retriever.search(case.question, k=k)]
            rows.append({"case": case.id, "k": k, "hit": any(g in got for g in case.gold), "top": got[:3]})
    summary = {
        k: sum(r["hit"] for r in rows if r["k"] == k) / sum(1 for r in rows if r["k"] == k)
        for k in sorted({6, systems.RETRIEVAL_K})
    }
    return {"recall_at_k": summary, "rows": rows}


def run_case(name: str, case: Case, llm, retriever: Retriever, sources: dict[str, str]) -> dict:
    if name == "closed_book":
        outcome = systems.closed_book(llm, case.question)
    elif name == "naive_rag":
        outcome = systems.naive_rag(llm, retriever, case.question)
    else:
        outcome = systems.grounded(llm, retriever, sources, case.question)
    g = grade(case, outcome.response, sources, cites_expected=(name == "grounded"))
    return {
        "system": name, "case": case.id, "category": case.category, "expect": case.expect,
        "question": case.question, "answer": outcome.response.answer,
        "status": outcome.response.status,
        "citations": [asdict(c) for c in outcome.response.citations],
        "retrieved": list(outcome.retrieved), "dropped_citations": outcome.dropped_citations,
        "guard_fired": outcome.guard_fired, "parse_failed": outcome.parse_failed, "raw": outcome.raw_text, "grade": asdict(g),
    }


def summarize(results: list[dict]) -> dict:
    out = {}
    for name in sorted({r["system"] for r in results}):
        rows = [r for r in results if r["system"] == name]
        by_cat = {}
        for cat in sorted({r["category"] for r in rows}):
            cat_rows = [r for r in rows if r["category"] == cat]
            by_cat[cat] = f"{sum(r['grade']['passed'] for r in cat_rows)}/{len(cat_rows)}"
        out[name] = {
            "passed": sum(r["grade"]["passed"] for r in rows), "total": len(rows),
            "with_forbidden_claim": sum(bool(r["grade"]["violations"]) for r in rows),
            "guard_fired": sum(r["guard_fired"] for r in rows),
            "parse_failed": sum(r["parse_failed"] for r in rows),
            "by_category": by_cat,
        }
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", default=",".join(SYSTEMS))
    ap.add_argument("--cases", default="")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--retrieval-only", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    corpus = load_corpus()
    sources = {s["id"]: s["text"] for s in corpus}
    cases = load_cases(ROOT / "evalset" / "cases.json", frozenset(sources))
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = tuple(c for c in cases if c.id in wanted)
    retriever = Retriever(corpus)

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    retrieval = retrieval_report(retriever, cases)
    log.info("gold-source recall: %s", retrieval["recall_at_k"])
    if args.retrieval_only:
        (out_dir / "retrieval.json").write_text(json.dumps(retrieval, indent=2))
        return 0

    names = [n for n in args.systems.split(",") if n]
    unknown = set(names) - set(SYSTEMS)
    if unknown:
        ap.error(f"unknown systems: {sorted(unknown)}")
    llm = CachedAnthropic(load_api_key(ROOT / ".env"), ROOT / "data" / "cache", args.model)

    jobs = [(n, c) for n in names for c in cases]
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(lambda j: run_case(j[0], j[1], llm, retriever, sources), jobs))

    summary = summarize(results)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"run_at": stamp, "model": args.model, "corpus_sources": len(corpus),
               "cases": len(cases), "summary": summary, "retrieval": retrieval["recall_at_k"],
               "results": results}
    (out_dir / f"run-{stamp}.json").write_text(json.dumps(payload, indent=2))
    (out_dir / "latest.json").write_text(json.dumps(payload, indent=2))
    log.info(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
