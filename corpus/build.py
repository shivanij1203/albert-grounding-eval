"""Build data/corpus.json from Albert's public sources (read-only).

Two kinds of source:
  * help articles: help.albert.com's public Zendesk API (147 articles)
  * disclosures: the legal disclosure paragraphs in albert.com's site footer,
    which state current plan prices, advance limits, and fee terms

Fetching is polite: two API pages and one homepage request, with a pause
between them. Use --offline to rebuild from the raw files already in data/.

    python -m corpus.build            # fetch, then build
    python -m corpus.build --offline  # rebuild from data/raw_articles.json + data/home.html
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from corpus._pagetext import page_text

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = "https://help.albert.com/api/v2/help_center/en-us/articles.json?per_page=100&page={}"
HOME = "https://albert.com/"
UA = {"User-Agent": "Mozilla/5.0 (read-only research)"}
PAUSE_SECONDS = 1.5

# Footer paragraphs worth indexing, keyed by a stable id and matched by their opening words.
DISCLOSURES = {
    "disc-plans": "Albert subscription plans range",
    "disc-genius": "Albert Genius is an AI-powered financial assistant",
    "disc-instant-advance": "The Instant Advance is available",
    "disc-line-of-credit": "The Albert Instant Line of Credit",
    "disc-loans": "Loans may be issued by FinWise",
    "disc-early-deposit": "Early access to direct deposit",
    "disc-savings": "For High Yield Savings accounts",
    "disc-investing": "Investment advisory services are provided",
    "disc-banking": "Albert is not a bank. Banking services provided by Stride",
}

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_DUP = re.compile(r"\b(\w+)(\s+\1\b)+", re.I)


def strip_html(body: str | None) -> str:
    s = (body or "")
    for closer in ("</p>", "<br>", "<br/>", "</li>", "</h2>", "</h3>"):
        s = s.replace(closer, " ")
    s = html.unescape(_TAG.sub(" ", s))
    s = _WS.sub(" ", s).strip()
    # Zendesk headings sit right before the body, so stripping can repeat a word.
    return _DUP.sub(r"\1", s)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def fetch_raw() -> None:
    articles, page = [], 1
    while True:
        data = json.loads(_get(API.format(page)))
        articles.extend(data.get("articles", []))
        if not data.get("next_page"):
            break
        page += 1
        time.sleep(PAUSE_SECONDS)
    time.sleep(PAUSE_SECONDS)
    (DATA / "raw_articles.json").write_text(json.dumps(articles))
    (DATA / "home.html").write_bytes(_get(HOME))


def help_sources(raw_articles: list[dict]) -> list[dict]:
    out, seen = [], set()
    for a in raw_articles:
        text = strip_html(a.get("body"))
        if a["id"] in seen or not text:
            continue
        seen.add(a["id"])
        out.append({
            "id": f"help-{a['id']}", "kind": "help", "title": a["title"],
            "url": a["html_url"], "updated_at": a.get("updated_at"), "text": text,
        })
    return sorted(out, key=lambda s: s["id"])


def disclosure_sources(home_html: str) -> list[dict]:
    paragraphs = [line for line in page_text(home_html).split("\n") if len(line) > 60]
    out = []
    for sid, opening in DISCLOSURES.items():
        match = next((p for p in paragraphs if p.startswith(opening)), None)
        if match is None:
            raise ValueError(f"disclosure {sid!r} not found on homepage; the footer changed")
        out.append({
            "id": sid, "kind": "disclosure", "title": f"Albert disclosure: {sid[5:].replace('-', ' ')}",
            "url": HOME, "updated_at": None, "text": match,
        })
    return out


def build() -> list[dict]:
    raw = json.loads((DATA / "raw_articles.json").read_text())
    home = (DATA / "home.html").read_text(errors="ignore")
    return help_sources(raw) + disclosure_sources(home)


def main(argv: list[str]) -> None:
    DATA.mkdir(exist_ok=True)
    if "--offline" not in argv:
        fetch_raw()
    corpus = build()
    (DATA / "corpus.json").write_text(json.dumps(corpus, indent=2))
    kinds = {k: sum(1 for s in corpus if s["kind"] == k) for k in ("help", "disclosure")}
    print(f"sources: {len(corpus)} {kinds}")


if __name__ == "__main__":
    main(sys.argv[1:])
