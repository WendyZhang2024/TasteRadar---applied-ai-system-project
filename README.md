# 🎵 TasteRadar 2.0 — a recommender that knows when to stop

TasteRadar answers one sentence instead of three numbers, looks up what it does not
know in a small written knowledge base, and — the part the first version could not
do — refuses, or asks, when the catalog has nothing that fits.

---

## The base project

This is an extension of **TasteRadar 1.0**, my Modules 1–3 submission: a
content-based music recommender over a hand-built 20-song catalog. Given a taste
profile (favorite genre, favorite mood, target energy) it scored every song on
three rules, ranked them, and printed the top five with the points for each pick.

That behaviour is unchanged and still reproducible:

```bash
python -m src.main                 # the five original profiles, same numbers
git show v1.0-baseline:src/recommender.py   # the code as it was before 2.0
```

What 1.0 could not do, in its own words: *"The system has no way to return
nothing."* Ask it for euphoric 0.9-energy classical music and it returned
Gymnopédie No.1 — a calm piano piece at energy 0.12 — ranked first, looking exactly
like a normal answer.

---

## What 2.0 adds

| Capability | Where | What changed for the user |
| --- | --- | --- |
| **Free-text requests, English and Chinese** | `src/nlu.py` | "深夜写代码 别太吵" becomes genre/mood/energy, or a question |
| **A written knowledge base, searched** | `knowledge/`, `src/retrieval.py` | Missing details are filled from notes, and every fill is cited |
| **Retrieval-augmented explanations** | `src/agent.py` | Answers carry the exact section they relied on |
| **Four verdicts instead of one** | `src/guardrails.py` | answer / answer with warning / refuse / ask |
| **A labelled evaluation run** | `src/evaluate.py`, `reports/` | 11 requests checked on every change, with a written report |

The scoring recipe itself did not change: genre +2.0, mood +1.0, energy +1.0 ×
(1 − |gap|). That is deliberate. The extension is about *what the system does with
the score*, not about inventing a better score.

---

## Architecture

Source: [`diagrams/architecture.mmd`](diagrams/architecture.mmd) (Mermaid).

```mermaid
%% TasteRadar 2.0 -- how one sentence becomes an answer, a warning, a refusal
%% or a question. Node names mirror the modules in src/.
flowchart TD
    REQ["listener writes one sentence<br/>(English or Chinese)"] --> CLI["src/main.py<br/>ask()"]

    CSV[("data/songs.csv<br/>20 songs")] --> LOAD["src/catalog.py<br/>load_songs()<br/>validates every row"]
    LOAD -->|"CatalogError: file, line, column"| BAD["one-line diagnosis<br/>exit 2"]

    CLI --> PARSE["src/nlu.py<br/>parse_request()"]
    PARSE -->|"genre / mood / context / excluded / unknown"| RESOLVE["resolve_request()"]

    RESOLVE -->|"energy still empty?"| RET["src/retrieval.py<br/>Retriever.search()"]
    KB[("knowledge/*.md<br/>8 notes, 24 sections")] --> RET
    RET -->|"kb/context_study.md#Energy<br/>0.25-0.42"| RESOLVE

    RESOLVE --> GAPS{"src/guardrails.py<br/>catalog_gaps()"}
    GAPS -->|"no such genre/mood pair"| RELAX["drop the mood, retry once"]
    RELAX --> RANK
    GAPS -->|"no hole"| RANK["src/recommender.py<br/>rank() over score_song()"]
    LOAD --> RANK

    RANK --> CONF{"guardrails.confidence()<br/>fit x support"}
    RET --> CONF
    CONF --> DEC{"src/agent.py<br/>_decide()"}

    DEC -->|"fit high, nothing to report"| ANSWER["answer<br/>reasons + citations"]
    DEC -->|"a constraint was dropped"| CAVEAT["answer + warning<br/>says what it dropped"]
    DEC -->|"catalog hole or low fit"| REFUSE["refuse<br/>+ closest candidate"]
    DEC -->|"no genre and no mood"| ASK["clarify<br/>options read from the catalog"]

    ANSWER --> TRACE[("trace steps")]
    CAVEAT --> TRACE
    REFUSE --> TRACE
    ASK --> TRACE

    %% Humans: the listener is the final check on every verdict.
    ANSWER --> HUMAN["listener / reviewer<br/>reads reasons + citations,<br/>can disagree with a specific one"]
    CAVEAT --> HUMAN
    REFUSE -->|"closest candidate + real attributes"| HUMAN
    ASK -->|"one question"| HUMAN
    HUMAN -->|"adds a genre, mood or situation"| REQ

    %% Testing: regression run over labelled requests, plus unit tests.
    EVAL["src/evaluate.py<br/>11 labelled requests<br/>asserts verdict properties"] -->|"calls the same agent"| CLI
    EVAL --> REPORT[("reports/evaluation.md<br/>reports/evaluation.json")]
    REPORT -->|"developer reviews<br/>thresholds and failures"| DEV["developer<br/>(human review of tests)"]
    UNIT["tests/ (75 unit tests)<br/>incl. score-sum invariant"] -.->|"guards"| RANK
```

Data flow, in words:

1. **Input.** The sentence is parsed into slots. Only what is actually there gets
   filled; anything not understood is recorded, not ignored.
2. **Retrieval.** If the energy slot is empty and a situation was named, the
   knowledge base supplies a number — from the `Energy` section of that situation's
   note, with the citation kept.
3. **Processing.** The catalog is validated on load, scored by the single recipe,
   ranked with a deterministic tie-break. A catalog check may relax the mood
   constraint exactly once.
4. **Decision.** Confidence and issue list decide between answering, warning,
   refusing and asking.
5. **Human and test checkpoints.** Every verdict ends at the listener, who sees
   the reasons and citations and can dispute a specific one. A refusal shows the
   closest candidate with its real attributes, and a question hands control back
   to the listener. Separately, the evaluation run and the unit tests check the
   agent on every change, and a developer reviews the report and the thresholds.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # pytest only; everything else is the standard library
```

```bash
python -m src.main                            # the five original profiles
python -m src.main ask "chill lofi for late night coding"
python -m src.main ask "深夜写代码 别太吵" --trace
python -m src.main eval                       # writes reports/
python -m pytest -q                           # 75 tests
```

Exit codes from `ask`: `0` answered (with or without a warning), `1` needs more
information, `2` no confident match. A broken catalog also exits `2`, but before
any request is read.

---

## Sample interactions

Every block below is pasted verbatim from [`assets/sample_runs.txt`](assets/sample_runs.txt), generated by the commands shown. Nothing is trimmed.

### 1. A request the catalog can serve

answer, exit 0

```console
$ python -m src.main ask "chill lofi for late night coding"
Request   : chill lofi for late night coding
Genre     : lofi           <- text: "lofi"
Mood      : chill          <- text: "chill"
Context   : study          <- text: "late night"
Energy    : 0.35           <- text: "chill"
Excluded  : -
Unknown   : -
Evidence  : kb/context_study.md#What to avoid 0.28 | kb/context_study.md#Energy 0.21 | kb/context_study.md#Texture 0.18
Confidence: 0.96   [answer]

1. Library Rain - Paper Lanterns  (4.00/4.00)
   because: genre match: lofi (+2.0) | mood match: chill (+1.0) | energy 0.35 vs target 0.35 (gap 0.00, +1.00)
2. Midnight Coding - LoRoom  (3.93/4.00)
   because: genre match: lofi (+2.0) | mood match: chill (+1.0) | energy 0.42 vs target 0.35 (gap 0.07, +0.93)
3. Focus Flow - LoRoom  (2.95/4.00)
   because: genre match: lofi (+2.0) | mood mismatch: focused vs chill (+0.0) | energy 0.40 vs target 0.35 (gap 0.05, +0.95)
4. Spacewalk Thoughts - Orbit Bloom  (1.93/4.00)
   because: genre mismatch: ambient vs lofi (+0.0) | mood match: chill (+1.0) | energy 0.28 vs target 0.35 (gap 0.07, +0.93)
5. Apocalypse - Cigarettes After Sex  (1.00/4.00)
   because: genre mismatch: dream pop vs lofi (+0.0) | mood mismatch: melancholy vs chill (+0.0) | energy 0.35 vs target 0.35 (gap 0.00, +1.00)

[exit code: 0]
```

### 2. A request the catalog cannot serve, answered anyway, with a warning

caveat, exit 0. There is no calm j-pop track, so the agent drops the mood, re-ranks and says so.

```console
$ python -m src.main ask "calm j-pop"
Request   : calm j-pop
Genre     : j-pop          <- text: "j-pop"
Mood      : calm           <- text: "calm"
Context   : (not stated)
Energy    : 0.50           <- default (no context given)
Excluded  : -
Unknown   : -
Evidence  : kb/genre_jpop.md#The calm j-pop gap 0.61 | kb/genre_jpop.md#Energy 0.35 | kb/genre_jpop.md#When it fits 0.27
Confidence: 0.85   [caveat]
  relax : dropped the mood constraint, no track in the catalog matched it

1. 晩餐歌 - tuki.  (2.88/4.00)
   because: genre match: j-pop (+2.0) | no mood given (+0.0) | energy 0.62 vs target 0.50 (gap 0.12, +0.88)
2. 打上花火 - DAOKO, 米津玄師  (2.78/4.00)
   because: genre match: j-pop (+2.0) | no mood given (+0.0) | energy 0.72 vs target 0.50 (gap 0.22, +0.78)
3. Midnight Coding - LoRoom  (0.92/4.00)
   because: genre mismatch: lofi vs j-pop (+0.0) | no mood given (+0.0) | energy 0.42 vs target 0.50 (gap 0.08, +0.92)
4. Focus Flow - LoRoom  (0.90/4.00)
   because: genre mismatch: lofi vs j-pop (+0.0) | no mood given (+0.0) | energy 0.40 vs target 0.50 (gap 0.10, +0.90)
5. Coffee Shop Stories - Slow Stereo  (0.87/4.00)
   because: genre mismatch: jazz vs j-pop (+0.0) | no mood given (+0.0) | energy 0.37 vs target 0.50 (gap 0.13, +0.87)

[exit code: 0]
```

### 3. A request it refuses

refuse, exit 2. The closest candidate is shown with its real energy.

```console
$ python -m src.main ask "classical high energy"
Request   : classical high energy
Genre     : classical      <- text: "classical"
Mood      : (not stated)
Context   : (not stated)
Energy    : 0.90           <- text: "high energy"
Excluded  : -
Unknown   : -
Evidence  : kb/genre_classical.md#Why high-energy classical does not exist here 0.44 | kb/genre_classical.md#Energy 0.29 | kb/mood_intense.md#When it fits 0.15
Confidence: 0.52   [refuse]
  warn : no classical track is near 0.90 energy (closest is 0.12: Gymnopédie No.1)

No confident match.
  closest : Gymnopédie No.1 - Erik Satie (classical/calm, energy 0.12, 2.22/4.00)
[exit code: 2]
```

### 4. A request with no genre or mood in it

clarify, exit 1. The options in the question are read from the catalog at runtime.

```console
$ python -m src.main ask "深夜写代码 别太吵"
Request   : 深夜写代码 别太吵
Genre     : (not stated)
Mood      : (not stated)
Context   : study          <- text: "深夜"
Energy    : 0.33           <- kb/context_study.md#Energy (0.25-0.42)
Excluded  : -
Unknown   : 别太, 太吵
Evidence  : kb/context_study.md#Texture 0.22 | kb/context_study.md#What to avoid 0.21 | kb/context_study.md#Energy 0.19
Confidence: 0.00   [clarify]

Question  : I need one more clue. Name a genre (lofi, j-pop, pop, ambient, anime rock, cinematic ...) or a mood (chill, energetic, happy, intense, aggressive, calm ...), or a situation like studying or working out.
[exit code: 1]
```

---

## Execution evidence

Two of the files in [`assets/`](assets/) are generated and can be rebuilt in place:

```bash
python -m src.main eval > assets/eval_run.txt
python -m pytest -q > assets/pytest_run.txt
```

`assets/sample_runs.txt` is the four `ask` commands from above, run in order and
pasted with their exit codes.

Timings in the pytest output vary between machines. Everything else in these files
is byte-for-byte reproducible: the evaluation output and all four sample runs were
re-generated and compared as part of the review, not typed by hand.

**Evaluation run** ([`assets/eval_run.txt`](assets/eval_run.txt), full table in [`reports/evaluation.md`](reports/evaluation.md)):

```console
$ python -m src.main eval
11/11 cases passed
report written to reports/
```

| # | Request | Expected | Decision | Confidence | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | `chill lofi for late night coding` | answer / lofi | answer | 0.96 | PASS |
| 2 | `high energy pop for the gym` | answer / pop | answer | 0.93 | PASS |
| 3 | `romantic r&b` | answer / r&b | answer | 0.90 | PASS |
| 4 | `sad mandopop` | answer / mandopop | answer | 0.90 | PASS |
| 5 | `我想听日语歌` | answer / j-pop | answer | 0.94 | PASS |
| 6 | `anything but rock, something chill` | answer | answer | 0.88 | PASS |
| 7 | `calm j-pop` | caveat / j-pop | caveat | 0.85 | PASS |
| 8 | `classical high energy` | refuse | refuse | 0.52 | PASS |
| 9 | `edm energy 0.1` | refuse | refuse | 0.51 | PASS |
| 10 | `深夜写代码 别太吵` | clarify | clarify | 0.00 | PASS |
| 11 | `` | clarify | clarify | 0.00 | PASS |

**Unit tests** ([`assets/pytest_run.txt`](assets/pytest_run.txt)):

```console
$ python -m pytest -q
........................................................................ [ 96%]
...                                                                      [100%]
75 passed in 0.39s
```

**Guardrail behaviour in the runs above:** sample 2 shows the one allowed revision (mood dropped, named in the output), sample 3 shows a refusal with the closest real candidate, sample 4 shows a clarifying question instead of a guess.

---

## Design decisions

**One scoring implementation, derived output.** `score_song()` returns a
`ScoreBreakdown` of per-rule items; the ranking and the explanation text are both
rendered from that same object. An earlier version computed the explanation in a
second pass over a parallel code path, which meant a new rule had to be added
twice and the forgotten copy would drift silently.

**Retrieval fills holes, never overrides.** A knowledge-base number is only applied
to a slot the listener left empty, and the source is printed. Ask for energy 0.8 in
a study context and the note's 0.33 is ignored.

**Confidence is multiplicative, not additive.** `fit × (0.80 + 0.20 × support)`.
A result that misses an explicit constraint cannot be rescued by a big gap to the
runner-up or a strong citation — which is exactly what an additive score would
allow.

**Catalog holes are facts, not thresholds.** "No j-pop track is tagged calm" is
read off the data. Nothing is tuned to discover it, and the check cannot be
satisfied by a better score.

**Offline and deterministic.** No model, no API key, no network. The retrieval is
TF-IDF with CJK character bigrams, the parser is a word table. This costs semantic
matching (see Limitations) and buys reproducibility: anyone can clone, install
`pytest`, and get the same 11/11 evaluation.

**Only the mood is ever relaxed.** Genre is worth 2.0 on its own and is the hardest
boundary in the recipe; dropping it would not make the answer more honest, it would
answer a different question.

---

## Guardrails: input, behaviour, result

| Input | Behaviour | Result |
| --- | --- | --- |
| `""` | no clue at all | asks one question, exit 1 |
| `"chill lofi 别太吵"` | `别太` / `太吵` not understood | answers, warns, confidence ×0.90 |
| `"classical high energy"` | no classical track near 0.9 | refuses, names the closest track and its real energy |
| `"calm j-pop"` | pair exists nowhere in the catalog | drops mood, answers with a warning naming the drop |
| `data/songs.csv` with a blank `energy` | row-level validation on load | `line 7 (id=6): column 'energy' is empty`, exit 2 |
| `energy = nan` | non-finite rejection at load | refused before scoring, because NaN poisons every comparison |
| duplicate `id` | validation on load | `duplicate id 2, already used on line 3` |

---

## Evaluation

`python -m src.main eval` runs 11 labelled requests and writes
[`reports/evaluation.md`](reports/evaluation.md) and `.json`. Each case asserts a
*property* of the verdict — decision, top genre, whether mood was relaxed,
confidence bounds — never the wording, so the table survives copy changes.

Current result: **11/11**, with 6 answers, 1 caveat, 2 refusals, 2 questions.

The most useful line in the report is the threshold check: answered cases sit at
0.85–0.96, refused cases at 0.51–0.52. The `0.55` refusal boundary is not load
bearing for this set — it could move anywhere inside that gap without changing a
verdict. That is an honest statement about how thin the calibration evidence is.

The first run of this harness failed 5 of 11 cases and found a real parser bug:
filler words such as `我想` and `something` were counted as "not understood", which
downgraded correct answers to warnings. The parser's own unit tests had not caught
it, because none of them asked whether a *complete* sentence survived the round
trip.

---

## The recipe, in detail

| Rule | Points |
| --- | --- |
| Genre matches `favorite_genre` | +2.0 |
| Mood matches `favorite_mood` | +1.0 |
| Energy similarity | +1.0 × (1 − \|song.energy − target_energy\|) |

Genre carries the heaviest weight because it is the hardest boundary. Energy is
scored by distance rather than height: a 0.93 track scores badly for a target of
0.2. Maximum is 4.0.

Ranking sorts by score descending, then closer energy, then lower id, so the same
input always produces the same list.

Two weight experiments, re-run against the unified implementation:

```
baseline 2/1/1        : Sunrise City 3.97 | Gym Hero 2.92 | Rooftop Lights 1.91 | 火炎 1.00 | Storm Runner 0.94
genre 1.0, energy 2.0 : Sunrise City 3.94 | Gym Hero 2.84 | Rooftop Lights 2.82 | 火炎 2.00 | Storm Runner 1.88
mood removed          : Sunrise City 2.97 | Gym Hero 2.92 | 火炎 1.00 | Storm Runner 0.94 | Rooftop Lights 0.91
```

Halving genre barely reorders the list; it only squeezes the gaps. Removing mood
drops Rooftop Lights from third to fifth while Gym Hero does not move at all — the
mood term is doing real work only for songs whose genre is already wrong. Both are
a single `Weights(...)` argument, not a code change.

---

## Limitations

- **The catalog is 20 hand-tagged songs.** Thirteen of sixteen genres appear once.
  More than one refusal in the evaluation is a statement about the data, not the
  logic.
- **Retrieval is lexical.** `workout` and `training` are unrelated unless both are
  written in the note's tags. There is no stemming and no synonyms beyond the
  hand-written table.
- **The parser is a word table.** Anything outside it lands in `Unknown` and lowers
  confidence rather than being guessed at.
- **Negation is a 16-character lookback.** "这首歌不错" reads as a negation because
  of the `不`. Known, unfixed, and cheap to hit.
- **Refusal thresholds are provisional.** 0.55 and 0.70 were chosen before the
  evaluation set existed and are only as good as those 11 cases.
- **A genre match is still nearly veto-proof** inside the score itself, which is the
  old bias; the guardrails now name it, they do not remove it.

The reasoning, the collaboration notes and the ethics section live in the
[Model Card](model_card.md).

---

## Repository layout

```
data/songs.csv            the 20-song catalog, validated on load
knowledge/*.md            8 hand-written notes, the retrieval corpus
diagrams/architecture.mmd Mermaid source for the diagram above
src/catalog.py            loading + row-level validation
src/recommender.py        the single scoring recipe
src/retrieval.py          TF-IDF + CJK bigrams
src/nlu.py                text -> slots
src/guardrails.py         catalog gaps + confidence
src/agent.py              the loop, the four verdicts, the trace
src/evaluate.py           labelled evaluation + report
src/main.py               CLI: profiles, ask, eval
tests/                    75 tests
reports/                  generated evaluation output
assets/                   pasted execution evidence (eval, pytest, sample runs)
```
