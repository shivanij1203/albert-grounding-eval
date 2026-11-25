"""The three assistants under test.

closed_book  the model alone, told it is Albert's support assistant
naive_rag    the usual first build: retrieve passages, ask the model to answer from them
grounded     retrieve, require a verbatim quote for every claim, separate same-named
             products, hand off when the sources don't cover it, then verify every
             quote in code and hand off if none survives
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace

from harness.grade import Citation, Response, looks_like_handoff, quote_supported
from harness.llm import LLM
from harness.retrieve import Hit, Retriever

RETRIEVAL_K = 8  # same context for both retrieval systems
NAIVE_K = RETRIEVAL_K
GROUNDED_K = RETRIEVAL_K
HANDOFF_MESSAGE = (
    "I couldn't confirm that from Albert's published help content, so I don't want to guess. "
    "A support agent can help: in the app, go to Profile, then Help."
)

CLOSED_BOOK_SYSTEM = (
    "You are the customer support assistant for Albert, the personal finance app. "
    "Answer the customer's question directly and concisely, in two to four sentences."
)

NAIVE_SYSTEM = (
    "You are the customer support assistant for Albert, the personal finance app. "
    "Answer the customer's question using the help center passages provided. "
    "Be direct and concise, in two to four sentences."
)

GROUNDED_SYSTEM = """You are the customer support assistant for Albert, the personal finance app.
You answer only from the source passages provided. Rules:
1. Every factual claim in your answer must be supported by a short quote copied exactly,
   word for word, from one passage. Cite it with that passage's source_id.
2. Albert has several products with similar names (for example the Instant Advance, the
   Instant line of credit, and Instant Loans). If the sources give different terms for
   products the customer's words could mean, say which terms apply to which product.
   Never merge their fees or limits.
3. If the passages do not answer the question, or the answer depends on the customer's own
   account (their limit, balance, rate, or eligibility), set status to "refused" and say
   briefly what you can't answer and that support can help in the app.
4. Do not give personalized financial or investment advice.
5. Two to four sentences. Plain language.

Respond with only a JSON object:
{"status": "answered" | "refused",
 "answer": "...",
 "citations": [{"source_id": "...", "quote": "..."}]}"""


@dataclass(frozen=True)
class Outcome:
    system: str
    response: Response
    raw_text: str
    retrieved: tuple[str, ...] = ()
    dropped_citations: int = 0
    guard_fired: bool = False
    parse_failed: bool = False


def _passages_block(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[source_id: {h.passage.source_id}] {h.passage.title}\n{h.passage.text}" for h in hits
    )


def _plain_response(text: str) -> Response:
    # Free-text systems have no explicit status. Grading treats them as answering,
    # and checks their wording for a handoff only on cases that require one, so a
    # correct answer that ends with "contact support" is not penalized.
    return Response(status="answered", answer=text.strip())


def _last_status_object(text: str) -> dict:
    """Models sometimes emit a draft and then a corrected object. Take the last
    well-formed JSON object that carries a status field."""
    decoder = json.JSONDecoder()
    found = None
    for start in (m.start() for m in re.finditer(r"\{", text)):
        try:
            obj, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "status" in obj:
            found = obj
    if found is None:
        raise ValueError("grounded response had no JSON object with a status")
    return found


def parse_grounded(text: str) -> Response:
    data = _last_status_object(text)
    status = data.get("status")
    if status not in ("answered", "refused"):
        raise ValueError(f"grounded response had invalid status {status!r}")
    raw_citations = data.get("citations") or []
    if not isinstance(raw_citations, list):
        raise ValueError("citations must be a list")
    citations = tuple(
        Citation(str(c.get("source_id", "")), str(c.get("quote", "")))
        for c in raw_citations if isinstance(c, dict)
    )
    return Response(status=status, answer=str(data.get("answer", "")).strip(), citations=citations)


def verify(response: Response, sources: dict[str, str], allowed: set[str]) -> tuple[Response, int, bool]:
    """Keep only citations whose quote is really in a retrieved source. If an answer
    keeps none, replace it with a handoff. Returns (response, dropped, guard_fired)."""
    kept = tuple(
        c for c in response.citations
        if c.source_id in allowed and quote_supported(c.quote, sources.get(c.source_id, ""))
    )
    dropped = len(response.citations) - len(kept)
    if response.status == "answered" and not kept:
        return Response("refused", HANDOFF_MESSAGE, ()), dropped, True
    return replace(response, citations=kept), dropped, False


def closed_book(llm: LLM, question: str) -> Outcome:
    text = llm.complete(CLOSED_BOOK_SYSTEM, question)
    return Outcome("closed_book", _plain_response(text), text)


def naive_rag(llm: LLM, retriever: Retriever, question: str) -> Outcome:
    hits = retriever.search(question, k=NAIVE_K)
    user = f"Help center passages:\n\n{_passages_block(hits)}\n\nCustomer question: {question}"
    text = llm.complete(NAIVE_SYSTEM, user)
    return Outcome("naive_rag", _plain_response(text), text,
                   tuple(h.passage.source_id for h in hits))


def grounded(llm: LLM, retriever: Retriever, sources: dict[str, str], question: str) -> Outcome:
    hits = retriever.search(question, k=GROUNDED_K)
    allowed = {h.passage.source_id for h in hits}
    user = f"Source passages:\n\n{_passages_block(hits)}\n\nCustomer question: {question}"
    text = llm.complete(GROUNDED_SYSTEM, user)
    try:
        parsed = parse_grounded(text)
    except (ValueError, TypeError, AttributeError):
        return Outcome("grounded", Response("refused", HANDOFF_MESSAGE, ()), text,
                       tuple(h.passage.source_id for h in hits), parse_failed=True)
    final, dropped, fired = verify(parsed, sources, allowed)
    return Outcome("grounded", final, text, tuple(h.passage.source_id for h in hits), dropped, fired)
