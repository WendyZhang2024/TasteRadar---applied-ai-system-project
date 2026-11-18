# Evaluation report

11 labelled requests, run end to end through the agent with the catalog and the knowledge base as shipped.

Each case asserts a property of the verdict -- the decision, the top genre, whether the mood had to be relaxed -- not the wording of the output, so this table stays meaningful when the text changes.

| # | Request | Expected | Decision | Confidence | Top genre | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `chill lofi for late night coding` | answer / lofi | answer | 0.96 | lofi | PASS |
| 2 | `high energy pop for the gym` | answer / pop | answer | 0.93 | pop | PASS |
| 3 | `romantic r&b` | answer / r&b | answer | 0.90 | r&b | PASS |
| 4 | `sad mandopop` | answer / mandopop | answer | 0.90 | mandopop | PASS |
| 5 | `我想听日语歌` | answer / j-pop | answer | 0.94 | j-pop | PASS |
| 6 | `anything but rock, something chill` | answer | answer | 0.88 | lofi | PASS |
| 7 | `calm j-pop` | caveat / j-pop | caveat | 0.85 | j-pop | PASS |
| 8 | `classical high energy` | refuse | refuse | 0.52 | classical | PASS |
| 9 | `edm energy 0.1` | refuse | refuse | 0.51 | edm | PASS |
| 10 | `深夜写代码 别太吵` | clarify | clarify | 0.00 | - | PASS |
| 11 | `` | clarify | clarify | 0.00 | - | PASS |

## Summary

- 11 of 11 cases passed
- verdicts: 6 answer, 1 caveat, 2 clarify, 2 refuse
- answered cases: confidence 0.85 to 0.96
- refused cases: confidence 0.51 to 0.52

## Where the thresholds sit

The refusal boundary is a constant (`guardrails.REFUSE_BELOW`). This is the evidence that it is not doing heroics: the highest refused case and the lowest answered case are far apart, so the exact value could move without changing any verdict in this set.

| Confidence | Decision | Request |
| --- | --- | --- |
| 0.96 | answer | `chill lofi for late night coding` |
| 0.94 | answer | `我想听日语歌` |
| 0.93 | answer | `high energy pop for the gym` |
| 0.90 | answer | `romantic r&b` |
| 0.90 | answer | `sad mandopop` |
| 0.88 | answer | `anything but rock, something chill` |
| 0.85 | caveat | `calm j-pop` |
| 0.52 | refuse | `classical high energy` |
| 0.51 | refuse | `edm energy 0.1` |
| 0.00 | clarify | `深夜写代码 别太吵` |
| 0.00 | clarify | `` |

## What this does not cover

- Only 11 requests. It is a regression net, not a benchmark.
- Nothing here checks whether a *good* answer is also a *good song*, only that it satisfies the stated constraints.
- The catalog is fixed, so no case exercises a change in the data.
