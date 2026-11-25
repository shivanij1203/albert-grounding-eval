"""Render docs/index.html from results/latest.json and report/story.html.

Every number on the page comes from the run files, and the build refuses to run
if a sentence on the page no longer matches the data.

    python -m harness.report
"""
from __future__ import annotations

import html
import re
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICE_ARTICLE = "help-21583583733271"
SYSTEMS = ("closed_book", "naive_rag", "grounded")


def _load() -> tuple[dict, dict, dict]:
    run = json.loads((ROOT / "results" / "latest.json").read_text())
    cases = {c["id"]: c for c in json.loads((ROOT / "evalset" / "cases.json").read_text())["cases"]}
    corpus = {s["id"]: s for s in json.loads((ROOT / "data" / "corpus.json").read_text())}
    return run, cases, corpus


def _answer(run: dict, system: str, case: str) -> str:
    return next(r["answer"] for r in run["results"] if r["system"] == system and r["case"] == case)


def _check_narrative(run: dict, corpus: dict) -> None:
    """The page makes specific claims about this run. Refuse to build it if a rerun
    or a corpus refresh has made any of them false."""
    passed = {(r["system"], r["case"]): r["grade"]["passed"] for r in run["results"]}
    claims = {
        "the AI alone capped advances at $250": "$250" in _answer(run, "closed_book", "adv-max"),
        "the AI alone said advances are due on payday": "payday" in _answer(run, "closed_book", "adv-due"),
        "page reading fails the Instant late-fee question": not passed[("naive_rag", "adv-late-fees")],
        "quoting passes the Instant late-fee question": passed[("grounded", "adv-late-fees")],
        "every version fails the cancel-without-zeroing question": not any(
            passed[(s, "cancel-zero-savings")] for s in SYSTEMS),
        "quoting and page reading differ by at most one question": abs(
            run["summary"]["grounded"]["passed"] - run["summary"]["naive_rag"]["passed"]) <= 1,
        "Albert's price article still says $39.99": "Genius costs $39.99 a month" in corpus[PRICE_ARTICLE]["text"],
        "the Terms still require $0 balances to cancel": "balance of $0 to cancel your Albert Subscription"
            in corpus["help-16768060313111"]["text"],
    }
    false = [name for name, ok in claims.items() if not ok]
    if false:
        raise ValueError(f"page no longer matches the data: {false}")


def _price_answers(run: dict) -> list[str]:
    """Every answer the model gave to the Genius price question: the scored run plus the
    resamples. The page says "$14.99 every time", so refuse to build if that's not true."""
    resamples = json.loads((ROOT / "results" / "closed_book_resamples.json").read_text())
    answers = [a for a in [_answer(run, "closed_book", "price-genius")] + resamples["answers"]["price-genius"]
               if a.strip()]
    if not answers or not all("14.99" in a for a in answers):
        raise ValueError("not every price answer says $14.99; the headline is false")
    return answers


def _highlight_price(answer: str) -> str:
    return html.escape(answer.replace("**", "").strip()).replace("$14.99", "<mark>$14.99</mark>")


def _sentence_with(text: str, phrase: str) -> str:
    """The sentence of `text` that contains `phrase`, exactly as the model wrote it."""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if phrase in sentence:
            return sentence.strip()
    raise ValueError(f"no sentence containing {phrase!r}")


def _phone_data(run: dict, cases: dict, corpus: dict) -> dict:
    """Everything the phone screen shows. AI messages are exact excerpts of saved
    answers, so the page can't put words in the model's mouth."""
    grounded_price = next(r for r in run["results"] if r["system"] == "grounded" and r["case"] == "price-genius")
    data = {
        "price_q": cases["price-genius"]["question"],
        "wrong": _sentence_with(_answer(run, "closed_book", "price-genius"), "$14.99").rstrip(",").split(", though")[0],
        "read": _sentence_with(_answer(run, "naive_rag", "price-genius"), "$39.99"),
        "quoted": _sentence_with(grounded_price["answer"], "$39.99"),
        "quote": next(c["quote"] for c in grounded_price["citations"] if "39.99" in c["quote"]),
        "source": corpus[PRICE_ARTICLE]["title"],
        "fees_q": cases["adv-late-fees"]["question"],
        "conflict": _sentence_with(_answer(run, "naive_rag", "adv-late-fees"), "conflicts with"),
        "conflict_mark": "conflicts with",
        "cancel_q": cases["cancel-zero-savings"]["question"],
        "cancel_wrong": _sentence_with(_answer(run, "closed_book", "cancel-zero-savings"), "shouldn't need").split(",")[0],
        "terms": "You must have an Albert Savings and/or Albert Investing balance of $0 to cancel your Albert Subscription.",
    }
    checks = {
        "wrong": _answer(run, "closed_book", "price-genius"),
        "cancel_wrong": _answer(run, "closed_book", "cancel-zero-savings"),
        "read": _answer(run, "naive_rag", "price-genius"),
        "quoted": grounded_price["answer"],
        "conflict": _answer(run, "naive_rag", "adv-late-fees"),
        "terms": corpus["help-16768060313111"]["text"],
    }
    for key, source in checks.items():
        if data[key].rstrip(".") not in source:
            raise ValueError(f"phone message {key!r} is not a verbatim excerpt")
    if data["quote"] not in corpus[PRICE_ARTICLE]["text"]:
        raise ValueError("phone quote is not on Albert's price page")
    if data["conflict_mark"] not in data["conflict"]:
        raise ValueError("phone highlight is not in the conflict sentence")
    return data


def build_story() -> str:
    run, cases, corpus = _load()
    _check_narrative(run, corpus)
    summary = run["summary"]
    price_answers = _price_answers(run)
    order = list(dict.fromkeys(r["case"] for r in run["results"]))
    passed = {(r["system"], r["case"]): r["grade"]["passed"] for r in run["results"]}
    story = {name: [passed[(name, c)] for c in order] for name in SYSTEMS}
    phone = _phone_data(run, cases, corpus)

    template = (ROOT / "report" / "story.html").read_text()
    if "{{STORY_DATA}}" not in template or "</html>" not in template:
        raise ValueError("story template is incomplete")
    fills = {
        "{{N}}": str(run["cases"]), "{{SOURCES}}": str(run["corpus_sources"]),
        "{{HELP}}": str(sum(s["kind"] == "help" for s in corpus.values())),
        "{{REFUSE}}": str(sum(c["expect"] == "refuse" for c in cases.values())),
        "{{CB}}": str(summary["closed_book"]["passed"]),
        "{{RAG}}": str(summary["naive_rag"]["passed"]), "{{GR}}": str(summary["grounded"]["passed"]),
        "{{MODEL}}": html.escape(run["model"]),
        "{{PRICE_URL}}": corpus[PRICE_ARTICLE]["url"],
        "{{PRICE_TOTAL}}": str(len(price_answers)),
        "{{PRICE_ANSWERS}}": "".join(f"<li>{_highlight_price(a)}</li>" for a in price_answers),
        "{{RUN_AT}}": datetime.strptime(run["run_at"][:8], "%Y%m%d").strftime("%b %-d, %Y"),
        "{{PRICE_Q}}": html.escape(phone["price_q"]), "{{WRONG}}": html.escape(phone["wrong"]),
    }
    for key, value in fills.items():
        template = template.replace(key, value)
    if "{{" in template.replace("{{STORY_DATA}}", "").replace("{{PHONE_DATA}}", ""):
        raise ValueError("unfilled placeholder in story template")
    return (template.replace("{{STORY_DATA}}", json.dumps(story))
            .replace("{{PHONE_DATA}}", json.dumps(phone).replace("</", "<\\/")))


def main() -> None:
    out = ROOT / "docs" / "index.html"
    out.write_text(build_story())
    print(f"wrote {out.relative_to(ROOT)}")
    script = ROOT / "docs" / "phone3d.js"
    script.write_text((ROOT / "report" / "phone3d.js").read_text())
    print(f"wrote {script.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
