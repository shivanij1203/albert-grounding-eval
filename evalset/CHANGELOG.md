# Grader and eval-set changes

Every change made after seeing model output is listed here, with the reason.
None of them changed which facts count as correct.

2026-11-25, after the first full run:

- `adv-extension`: the fact pattern missed the Terms of Use's own wording,
  "seven ( 7 ) day extension". Both RAG systems had answered correctly. Added that form.
- `adv-late-fees`: "line of credit" missed the hyphenated "line-of-credit". Pattern now
  accepts either.
- `oos-my-apr` became `loan-my-apr`: it was marked must-refuse, but the Terms of Use do
  state a public APR ceiling, so "it depends on your application, up to 36%" is a correct,
  grounded answer. Now graded as an answer that must say the rate depends and must not
  state a personal rate.
- `acct-bank` removed from scoring: the footer disclosure names Stride Bank only, while
  the Terms of Use (updated 2026-11-02) and seven help articles say "Sutton Bank or Stride
  Bank". The sources disagree, so there is no single correct answer to grade. Reported as a
  content note instead.
- Harness, not grader: the grounded parser failed when the model emitted a draft JSON
  object followed by a corrected one, which made the guard hand off a correct answer
  (`adv-frequency`). The parser now takes the last valid object with a status.
- `adv-credit-check`, `cancel-pause-smart`: hand review of the closed-book run found two
  correct answers the patterns missed ("doesn't run a credit check", "doesn't cancel or
  pause"). Added those forms. This raised the closed-book score, which is the baseline the
  RAG systems are compared against.

After an independent code review:

- Both retrieval systems now get the same 8 passages. The first runs gave naive RAG 6 and
  grounded 8, which made any comparison between them unfair to naive RAG.
- Must-refuse cases now use one rule for all three systems: the answer text must read as a
  handoff. Before, the grounded system passed on its structured status alone. The handoff
  wording also accepts "I don't know", "can't say", "unable to view", and "reach out to".
- The must-refuse cases now carry forbidden claims (stating a personal limit, telling the
  customer to buy, describing a competitor's product), so a wrong answer that ends with
  "contact support" can't pass.
- Tightened `fee-fast-transfer` (a bare "25" matched "$250") and `acct-age` (word boundary).
- Answerable cases are now judged on content for every system. Before, the grounded
  system failed `loan-my-apr` for marking itself "refused" while stating the right answer
  ("it depends on your creditworthiness... up to 36%"); free-text systems were never
  judged on status. Facts and forbidden claims now decide for all three.
