# Grounding a money assistant in Albert's own content

An evaluation of 41 customer questions about Albert's plans, advances, fees, loans, and
cancellation. Each question is answered three ways by the same model, and every answer is
graded against what Albert publishes.

**Read the results:** https://shivanij1203.github.io/albert-grounding-eval/

| System | Passed |
|---|---|
| Model alone, told it is Albert's support assistant | 14 / 41 |
| Same model, answering from retrieved Albert passages | 39 / 41 |
| Retrieval, plus a word-for-word quote for every claim, checked in code | 40 / 41 |

## What it found

1. **"Instant" names three products with different fee terms.** The Terms of Use define the
   Instant Advance (no late fees or interest), the Instant line of credit (draw fee, and a late
   fee if applicable), and Instant Loans separately. The help articles don't say which product
   they cover. The one titled "How does Instant advance repayment work?" describes the line of
   credit's late fees. Given both pages, plain retrieval told the customer Albert's content
   "conflicts with the disclosures." An assistant with account context can likely pick the right
   product; logged-out help, search, and retrieval without a product filter cannot.
2. **Without retrieval, the model repeats wrong money facts.** 13 of 41 answers stated
   something false in the scored run. Asked 5 more times each, 10 came back wrong at least 4
   times in 5: Genius at $14.99 (published: $39.99), advances capped at $250 (published:
   $1,000), advances due on payday (published: 6 days), refunds "case by case" (published: no
   refunds), and more. This is a baseline for what the model assumes, not a test of Genius.
3. **A smaller note on "cancel" versus "deactivate."** Every system failed "Can I cancel
   Genius without emptying my savings first?" The answer is in the Terms and in an article
   titled "Deactivating or closing your Albert account." Partly a limit of the keyword
   retriever here; Albert's own search finds that article for "cancel subscription" but not
   for "cancel genius."
4. **Verified quotes scored 40 to 39, too close to call in one run.** What they add is an
   audit trail: every quote is confirmed to appear word for word in its source (which shows
   the quote is real, not that it supports the claim), and an answer with no verifiable
   quote becomes a handoff.

## How it works

- `corpus/build.py` pulls the 147 public help articles from the help center's public API
  and the 9 legal disclosures in the albert.com footer. Read-only, three requests.
- `evalset/cases.json` holds the questions. Each lists the facts a correct answer must
  contain, the claims that make it wrong, and the sources those come from.
- `harness/retrieve.py` is BM25 over overlapping passages. It was not tuned on these questions.
- `harness/systems.py` defines the three assistants. The grounded one must quote its sources;
  `verify()` drops any quote not found word for word in a passage it was shown, and hands
  off if nothing survives.
- `harness/grade.py` grades with fixed rules: required facts, forbidden claims, the right
  behavior (answer or hand off), and quote checks. No model grades another model.
- `evalset/CHANGELOG.md` lists every grader change made after seeing output.
  `evalset/closed_book_review.json` holds the hand review of the model-alone failures,
  including how often each wrong claim recurred across 5 resamples
  (`results/closed_book_resamples.json`).

## Run it

```
pip install -r requirements.txt
python -m pytest                         # unit tests, no API calls
python -m harness.run --retrieval-only   # retrieval recall, no API calls
echo "ANTHROPIC_API_KEY=..." > .env      # gitignored
python -m harness.run                    # all systems; responses cache to data/cache/
python -m harness.report                 # rebuild docs/index.html from results/latest.json
```

## Limits

One run of one model, on public content only. It says nothing about how Albert's own
assistant behaves, which needs account access. Pattern grading can miss a correct paraphrase;
every failure was read by hand, and the patterns were fixed where that happened.
