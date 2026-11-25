"""Render report/index.html from results/latest.json.

Every number on the page is computed here from the run file, so the page can't
drift from the data.

    python -m harness.report
"""
from __future__ import annotations

import html
from datetime import datetime
import json
from pathlib import Path

from harness.systems import RETRIEVAL_K

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/shivanij1203/albert-grounding-eval"
SYSTEM_LABELS = {"closed_book": "AI on its own", "naive_rag": "Reading help pages", "grounded": "Reading and quoting"}


def _load() -> tuple[dict, dict, dict, dict]:
    run = json.loads((ROOT / "results" / "latest.json").read_text())
    review = json.loads((ROOT / "evalset" / "closed_book_review.json").read_text())["labels"]
    cases = {c["id"]: c for c in json.loads((ROOT / "evalset" / "cases.json").read_text())["cases"]}
    corpus = {s["id"]: s for s in json.loads((ROOT / "data" / "corpus.json").read_text())}
    return run, review, cases, corpus


def _citation_stats(run: dict) -> dict:
    rows = [r for r in run["results"] if r["system"] == "grounded"]
    answered = [r for r in rows if r["status"] == "answered"]
    return {
        "answered": len(answered),
        "handoffs": len(rows) - len(answered),
        "quotes": sum(len(r["citations"]) for r in answered),
        "dropped": sum(r["dropped_citations"] for r in rows),
        "gold_cited": sum(r["grade"]["gold_cited"] for r in answered),
    }


_PLAIN_REASONS = {
    "missing fact": "left out a key fact",
    "forbidden claim": "said something known to be wrong",
    "should have handed off": "should have sent the customer to support",
}


def _plain_reason(reason: str) -> dict:
    """A reader-facing label, with the exact grader pattern kept for engineers."""
    kind = reason.partition(": ")[0]
    return {"text": _PLAIN_REASONS.get(kind, reason), "detail": reason}


def _case_rows(run: dict, cases: dict, corpus: dict) -> list[dict]:
    by_case: dict[str, dict] = {}
    for r in run["results"]:
        entry = by_case.setdefault(r["case"], {"id": r["case"], "category": r["category"],
                                               "question": r["question"], "why": cases[r["case"]].get("why", ""),
                                               "answers": {}})
        entry["answers"][r["system"]] = {
            "text": r["answer"], "passed": r["grade"]["passed"],
            "reasons": [_plain_reason(x) for x in r["grade"]["reasons"]],
            "citations": [{"title": corpus[c["source_id"]]["title"], "url": corpus[c["source_id"]]["url"],
                           "quote": c["quote"]} for c in r["citations"]],
        }
    return list(by_case.values())


def build() -> str:
    run, review, cases, corpus = _load()
    s = run["summary"]
    stats = _citation_stats(run)
    wrong = review["wrong"]
    closed = {r["case"]: r["answer"] for r in run["results"] if r["system"] == "closed_book"}
    data = {"cases": _case_rows(run, cases, corpus), "labels": SYSTEM_LABELS}
    template = (ROOT / "report" / "template.html").read_text()
    required = ("{{DATA}}", "{{WRONG_ROWS}}", "{{CB}}", "{{RAG}}", "{{GR}}", "</html>")
    missing = [r for r in required if r not in template]
    if missing:
        raise ValueError(f"report template is incomplete, missing {missing}")
    for cid, row in wrong.items():
        if row["said"] not in closed[cid].replace("**", ""):
            raise ValueError(f"review excerpt for {cid} is not in the model's answer")
    stable = {c: r for c, r in wrong.items() if r["stable"]}
    unstable = {c: r for c, r in wrong.items() if not r["stable"]}

    def row_html(cid: str, row: dict) -> str:
        hedge = " <span class='hedge'>hedged</span>" if row["hedged"] else ""
        return (f'<tr><td class="q">{html.escape(cases[cid]["question"])}</td>'
                f'<td>"{html.escape(row["said"])}"{hedge}</td>'
                f'<td>{html.escape(row["fact"])}</td>'
                f'<td class="rep">{row["resample_wrong"]} of {row["resample_valid"]}</td></tr>')

    wrong_rows = "".join(row_html(c, r) for c, r in stable.items())
    if unstable:
        wrong_rows += ('<tr class="divider"><td colspan="4">Wrong in the scored run, '
                       'but not in most resamples</td></tr>')
        wrong_rows += "".join(row_html(c, r) for c, r in unstable.items())
    bad_samples = sum(r["resample_valid"] < 5 and 5 - r["resample_valid"] or 0 for r in wrong.values())
    fills = {
        "{{N}}": str(run["cases"]), "{{SOURCES}}": str(run["corpus_sources"]),
        "{{CB}}": str(s["closed_book"]["passed"]), "{{RAG}}": str(s["naive_rag"]["passed"]),
        "{{GR}}": str(s["grounded"]["passed"]), "{{WRONG}}": str(len(wrong)), 
        "{{HEDGE}}": str(len(review["hedge"])), "{{INCOMPLETE}}": str(len(review["incomplete"])),
        "{{QUOTES}}": str(stats["quotes"]), "{{ANSWERED}}": str(stats["answered"]),
        "{{HANDOFFS}}": str(stats["handoffs"]), "{{GOLD_CITED}}": str(stats["gold_cited"]),
        "{{MODEL}}": html.escape(run["model"]), "{{RUN_AT}}": datetime.strptime(run["run_at"][:8], "%Y%m%d").strftime("%b %-d, %Y"),
        "{{RECALL}}": f'{round(run["retrieval"]["8"] * 100)}', "{{REPO}}": REPO_URL,
        "{{WRONG_ROWS}}": wrong_rows,
        "{{CB_PCT}}": _pct(s["closed_book"]["passed"], run["cases"]),
        "{{RAG_PCT}}": _pct(s["naive_rag"]["passed"], run["cases"]),
        "{{GR_PCT}}": _pct(s["grounded"]["passed"], run["cases"]),
        "{{PRICE_REPEAT}}": f'{wrong["price-genius"]["resample_wrong"]} of {wrong["price-genius"]["resample_valid"]}', "{{STABLE}}": str(len(stable)), "{{BAD_SAMPLES}}": str(bad_samples), "{{K}}": str(RETRIEVAL_K),
        "{{REFUSE}}": str(sum(c["expect"] == "refuse" for c in cases.values())),
        "{{DATA}}": json.dumps(data).replace("</", "<\\/"),
    }
    _check_narrative(run, cases)
    data_blob = fills.pop("{{DATA}}")
    for key, value in fills.items():
        template = template.replace(key, value)
    if "{{" in template.replace("{{DATA}}", ""):
        raise ValueError("unfilled placeholder in report template")
    return template.replace("{{DATA}}", data_blob)


def _pct(part: int, whole: int) -> str:
    return str(round(part / whole * 100, 1))


def _check_narrative(run: dict, cases: dict) -> None:
    """The template's prose makes specific claims about this run. Refuse to build
    the page if a rerun has made any of them false."""
    passed = {(r["system"], r["case"]): r["grade"]["passed"] for r in run["results"]}
    claims = {
        "closed book fails the Instant late-fee question": not passed[("closed_book", "adv-late-fees")],
        "naive RAG fails the Instant late-fee question": not passed[("naive_rag", "adv-late-fees")],
        "grounded passes the Instant late-fee question": passed[("grounded", "adv-late-fees")],
        "all three fail the cancel-without-zeroing question": not any(
            passed[(s, "cancel-zero-savings")] for s in ("closed_book", "naive_rag", "grounded")),
        "the AI alone said $14.99 for Genius": "14.99" in next(
            r["answer"] for r in run["results"] if r["system"] == "closed_book" and r["case"] == "price-genius"),
        "grounded and naive differ by at most one question": abs(
            run["summary"]["grounded"]["passed"] - run["summary"]["naive_rag"]["passed"]) <= 1,
    }
    false = [name for name, ok in claims.items() if not ok]
    if false:
        raise ValueError(f"report prose no longer matches the run: {false}")


def main() -> None:
    out = ROOT / "docs" / "index.html"
    out.write_text(build())
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
