import json
from pathlib import Path

import pytest

from harness import systems
from harness.evalset import Case, load_cases
from harness.grade import Citation, Response, grade, quote_supported
from harness.retrieve import Retriever, split_passages

ROOT = Path(__file__).resolve().parent.parent

SOURCES = [
    {"id": "help-1", "title": "How much does Albert cost?", "url": "u1",
     "text": "Genius costs $39.99 a month. The Standard plan costs $19.99 a month."},
    {"id": "help-2", "title": "What are cash advances?", "url": "u2",
     "text": "There are no late fees or interest for Albert Advances. You can advance up to 6 times within a 30 day period."},
    {"id": "help-3", "title": "How does Instant advance repayment work?", "url": "u3",
     "text": "If your balance is not repaid within the agreed upon date, late fees may apply and you may be suspended from draws on your line of credit."},
]
TEXT = {s["id"]: s["text"] for s in SOURCES}


def make_case(**kw) -> Case:
    base = dict(id="c", category="pricing", question="q", expect="answer",
                must_include=(("39\\.99",),), must_not=("14\\.99",), gold=("help-1",))
    return Case(**{**base, **kw})


class FakeLLM:
    model = "fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


# retrieval

def test_retriever_ranks_topical_source_first():
    hits = Retriever(SOURCES).search("how much does genius cost", k=3)
    assert hits[0].passage.source_id == "help-1"


def test_retriever_caps_passages_per_source():
    long_source = {"id": "big", "title": "Terms", "url": "u", "text": "fee " * 1000}
    hits = Retriever([long_source] + SOURCES).search("fee", k=6, max_per_source=2)
    assert sum(h.passage.source_id == "big" for h in hits) == 2


def test_split_passages_covers_the_tail():
    words = [f"w{i}" for i in range(333)]
    passages = split_passages({"id": "x", "title": "t", "url": "u", "text": " ".join(words)})
    assert passages[-1].text.split()[-1] == "w332"


def test_empty_corpus_rejected():
    with pytest.raises(ValueError):
        Retriever([])


# grading

def test_quote_supported_ignores_case_whitespace_and_curly_quotes():
    assert quote_supported("Genius   costs $39.99", TEXT["help-1"])
    assert quote_supported("We’ll", "we'll delay this process until later") is False  # too short
    assert not quote_supported("Genius costs $14.99 a month", TEXT["help-1"])


def test_grade_passes_a_correct_cited_answer():
    r = Response("answered", "Genius is $39.99 a month.", (Citation("help-1", "Genius costs $39.99 a month"),))
    g = grade(make_case(), r, TEXT, cites_expected=True)
    assert g.passed and g.gold_cited and g.citations_valid == 1


def test_grade_flags_forbidden_claim_and_missing_fact():
    r = Response("answered", "Genius is $14.99 a month.")
    g = grade(make_case(), r, TEXT, cites_expected=False)
    assert not g.passed
    assert g.violations == ("14\\.99",)
    assert g.facts_hit == 0


def test_grade_flags_fabricated_quote():
    r = Response("answered", "Genius is $39.99.", (Citation("help-1", "Genius is free for students forever"),))
    g = grade(make_case(), r, TEXT, cites_expected=True)
    assert not g.passed and "citation(s) not found" in " ".join(g.reasons)


def test_refuse_case_requires_handoff_wording_for_plain_text():
    case = make_case(expect="refuse", must_include=(), must_not=(), gold=())
    assert grade(case, Response("answered", "Your limit is $500."), TEXT, False).passed is False
    assert grade(case, Response("answered", "I can't see your account. Contact support in the app."), TEXT, False).passed


def test_answer_case_is_judged_on_content_not_status():
    r = Response("refused", "It depends on your application; Genius is $39.99.")
    assert grade(make_case(), r, TEXT, cites_expected=False).passed


# grounded system and its verifier

def test_grounded_keeps_verified_answer():
    reply = json.dumps({"status": "answered", "answer": "Genius is $39.99 a month.",
                        "citations": [{"source_id": "help-1", "quote": "Genius costs $39.99 a month"}]})
    out = systems.grounded(FakeLLM(reply), Retriever(SOURCES), TEXT, "how much is genius")
    assert out.response.status == "answered" and not out.guard_fired


def test_grounded_hands_off_when_every_quote_is_fabricated():
    reply = json.dumps({"status": "answered", "answer": "Genius is $9.99.",
                        "citations": [{"source_id": "help-1", "quote": "Genius costs $9.99 a month"}]})
    out = systems.grounded(FakeLLM(reply), Retriever(SOURCES), TEXT, "how much is genius")
    assert out.guard_fired and out.response.status == "refused" and out.dropped_citations == 1


def test_grounded_rejects_quote_from_a_source_it_was_not_shown():
    reply = json.dumps({"status": "answered", "answer": "No late fees.",
                        "citations": [{"source_id": "help-2", "quote": "no late fees or interest for Albert Advances"}]})
    out = systems.grounded(FakeLLM(reply), Retriever(SOURCES[:1]), TEXT, "late fees")
    assert out.guard_fired


def test_grounded_hands_off_on_malformed_json():
    out = systems.grounded(FakeLLM("Sure! Genius is cheap."), Retriever(SOURCES), TEXT, "genius price")
    assert out.parse_failed and not out.guard_fired and out.response.status == "refused"


def test_grounded_survives_citations_in_the_wrong_shape():
    for bad in ('"citations": "help-1"', '"citations": {"source_id": "help-1"}', '"citations": ["help-1"]'):
        reply = '{"status": "answered", "answer": "Genius is $39.99.", ' + bad + '}'
        out = systems.grounded(FakeLLM(reply), Retriever(SOURCES), TEXT, "genius price")
        assert out.response.status == "refused"


def test_refuse_case_uses_the_same_rule_for_structured_status():
    case = make_case(expect="refuse", must_include=(), must_not=(), gold=())
    silent = Response("refused", "Your limit is $500.")
    assert grade(case, silent, TEXT, True).passed is False


def test_naive_rag_sends_retrieved_passages():
    llm = FakeLLM("Genius is $39.99.")
    out = systems.naive_rag(llm, Retriever(SOURCES), "how much does genius cost")
    assert "help-1" in llm.calls[0][1] and out.retrieved[0] == "help-1"


# the real eval set

def test_eval_set_loads_against_real_corpus():
    corpus = json.loads((ROOT / "data" / "corpus.json").read_text())
    cases = load_cases(ROOT / "evalset" / "cases.json", frozenset(s["id"] for s in corpus))
    assert len(cases) >= 40
    assert {c.expect for c in cases} == {"answer", "refuse", "both_products"}


def test_eval_set_rejects_unknown_gold_source(tmp_path):
    bad = {"cases": [{"id": "x", "category": "c", "question": "q", "expect": "answer",
                      "must_include": [], "must_not": [], "gold": ["help-nope"]}]}
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="gold sources not in corpus"):
        load_cases(path, frozenset({"help-1"}))


def test_parse_grounded_takes_the_corrected_second_object():
    text = ('{"status": "answered", "answer": "draft", "citations": []}\n'
            'Correction: here is the response.\n'
            '{"status": "answered", "answer": "final", "citations": []}')
    assert systems.parse_grounded(text).answer == "final"


def test_parse_grounded_skips_stray_braces():
    text = 'noise { not json } then {"status": "refused", "answer": "x", "citations": []}'
    assert systems.parse_grounded(text).status == "refused"


def test_story_refuses_an_incomplete_template(tmp_path, monkeypatch):
    from harness import report
    real = report.ROOT
    for rel in ("results/latest.json", "results/closed_book_resamples.json",
                "evalset/cases.json", "data/corpus.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text((real / rel).read_text())
    (tmp_path / "report").mkdir()
    (tmp_path / "report" / "story.html").write_text("")
    monkeypatch.setattr(report, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="incomplete"):
        report.build_story()


def test_story_page_builds_with_one_dot_per_question():
    import re as _re
    from harness import report
    page = report.build_story()
    blob = _re.search(r'<script id="story" type="application/json">(.*?)</script>', page, _re.S).group(1)
    story = json.loads(blob)
    assert {len(v) for v in story.values()} == {41}
    assert "{{" not in page


def test_story_page_loads_the_3d_phone_with_a_flat_fallback():
    from harness import report
    page = report.build_story()
    assert '"three":"./vendor/three.module.min.js"' in page
    assert 'src="./phone3d.js"' in page
    assert 'class="phone-flat"' in page  # flat phone is the fallback when WebGL is missing
    assert (report.ROOT / "docs" / "vendor" / "three.module.min.js").exists()


def test_phone_messages_are_verbatim_model_answers():
    from harness import report
    run, cases, corpus = report._load()
    data = report._phone_data(run, cases, corpus)
    assert "$14.99" in data["wrong"] and "$39.99" in data["read"]
    assert data["wrong"] in report._answer(run, "closed_book", "price-genius")
