# 🎧 Model Card: TasteRadar 2.0

## 1. Model name

TasteRadar 2.0

TasteRadar 1.0 scored a 20-song catalog against three numbers and reported the closest matches. Version 2.0 keeps that scoring and adds what a real assistant needs around it. It reads a sentence, looks things up in a written knowledge base, and decides whether the answer it can produce is worth giving at all.

## 2. What this is built on

This model card covers the extension of TasteRadar 1.0, my Modules 1–3 content-based recommender. The scoring recipe is unchanged: genre +2.0, mood +1.0, energy +1.0 × (1 − |gap|), for a maximum of 4.0. I left the arithmetic alone because the real failure was never in the numbers. The system simply had no way to say "I don't have that" or "I didn't understand you."

Everything around the score changed. Input is now a sentence instead of a hand-written dictionary. Missing details are filled in from a knowledge base. A verdict layer sits between the ranking and the user.

## 3. Intended use

**For:** demonstrating what a recommender looks like once it is allowed to be uncertain. It shows how a ranking turns into a decision, and where that decision goes wrong when the catalog is thin.

**Not for:** real listeners, production traffic, or any claim about musical taste. It returns 5 of 20 songs, a quarter of the catalog, and I tagged all 20 myself.

It also assumes the listener can say something: a genre, a mood, or a situation. A request with none of these gets a question instead of an answer. That is correct, but slower than people expect from a search box.

## 4. How it works

Five steps, each in its own module so each can be tested alone.

1. **Parse** (`src/nlu.py`). A hand-written table maps what people type onto the catalog's labels, in English and Chinese. The longest alias wins, so "indie pop" beats "pop" and "j-pop" does not trigger "pop". Negations ("anything but rock") become exclusions. Words that match nothing are recorded, not dropped.
2. **Retrieve** (`src/retrieval.py`). TF-IDF over 8 markdown notes split into 24 sections. Chinese is matched through character bigrams, which is how "深夜写代码" ("late-night coding") finds a note that contains those words only separately.
3. **Score** (`src/recommender.py`). A single implementation of the recipe that returns a per-rule breakdown. Both the ranking and the explanation read from it.
4. **Check** (`src/guardrails.py`). This step looks for two kinds of problem. *Catalog holes* are facts read directly off the data: a genre that does not exist, a mood that does not exist, a genre/mood pair with no track, or an energy level no track in that genre comes near. *Confidence* is computed as fit × (0.80 + 0.20 × support), where fit is how much of the stated request the best candidate satisfies.
5. **Decide** (`src/agent.py`). Four possible outcomes: answer, answer with a warning, refuse, or ask. One revision is allowed. If the requested genre/mood pair does not exist, the mood constraint is dropped once, and the output says so.

## 5. Data

Two datasets, both small and both mine.

**The catalog:** 20 songs, 16 genres, 15 moods. Ten rows came from the course starter file. I added ten from my own playlist (j-pop, piano, soundtracks), so the catalog leans toward my taste before anything is scored. Energy, valence, danceability and acousticness are hand-assigned estimates of how a track feels, not measurements.

**The knowledge base:** 8 notes (four genres, two moods, two situations), written by hand and derived from the catalog rather than from Wikipedia. For example, the study note gives an energy range of 0.25–0.42 because the three lo-fi tracks sit at 0.35, 0.40 and 0.42. If the notes and the data disagreed, the system would cite a rule the catalog does not follow.

**What is missing:** lyrics, era, popularity, skip behavior, and any signal from actual listening. Nothing here describes a real user.

## 6. Strengths

- **It can decline.** This is the clearest improvement over 1.0. "Classical high energy" now returns a refusal, the closest candidate, and that candidate's real energy, instead of a calm piano piece ranked first.
- **Every number has a source.** Output such as `Energy: 0.33 <- kb/context_study.md#Energy (0.25-0.42)` is printed, not implied, so a listener can dispute a specific citation.
- **It says what it dropped.** When the mood constraint is relaxed, the caveat names it. The failure I most wanted to avoid was quietly answering a different question.
- **It is deterministic and offline.** There is no model, no key and no network. Two runs produce byte-identical reports, which is what makes the evaluation meaningful.

## 7. Limitations and biases

- **The catalog is the real limit.** 13 of 16 genres appear exactly once. Two of the eleven evaluation cases end in refusal, and both reflect gaps in the data, not flaws in the logic.
- **A genre match nearly vetoes everything else.** At 2.0 points on its own, it outweighs a wrong mood and a wrong energy combined. The guardrails now name this bias but do not remove it.
- **Retrieval is lexical.** "Workout" and "training" are unrelated unless both appear in a note's tags. There is no stemming and no synonym table beyond what I wrote.
- **The parser is a word table.** Anything outside it is reported as unknown and lowers confidence. That is honest but brittle: a listener who says "something for the rain" gets a question.
- **Negation detection is crude.** It is a 16-character lookback, so "这首歌不错" ("this song isn't bad") reads as a negation because of the "不". This is a known, unfixed bug, and it is easy to hit in ordinary Chinese.
- **The refusal thresholds (0.55 / 0.70) were set before the evaluation set existed.** In the current 11 cases, answered requests score 0.85–0.96 and refused ones 0.51–0.52. The exact boundary therefore carries no weight, which is another way of saying the calibration evidence is thin.

## 8. Could this be misused, and how is that prevented?

The likely misuse is treating a ranked list as a recommendation. A 20-song catalog will always produce five results, and someone could read "it gave me five songs" as "it found five good songs."

Three things push against that:

- The verdict is printed with every result, not just logged: `[answer]`, `[caveat]` or `[refuse]`.
- A caveat must name the constraint it dropped.
- A refusal always shows the closest candidate with its real attributes, so a wrong answer is visibly wrong.

The opposite misuse deserves a mention too: a refusal can hide how small the catalog is. "No confident match" and "I don't know" are different statements, and the report keeps them apart by listing which catalog hole caused which refusal.

There is no personal data here, so the usual privacy risks do not apply. The bias risk does. The catalog encodes my taste, and a system that only recommends what already resembles the target can never introduce anyone to something new.

## 9. Evaluation

`python -m src.main eval` runs 11 labelled requests end to end and writes `reports/evaluation.md` and `.json`. Each case asserts a property of the verdict (decision, top genre, whether the mood was relaxed, confidence bounds) and never the wording, so the table survives copy changes.

**Current result:** 11/11, made up of 6 answers, 1 caveat, 2 refusals and 2 questions. The full unit suite has 75 tests.

**What the evaluation deliberately does not check:** whether a good answer is also a good song. It checks that the stated constraints are met and that the verdict matches the label. "Is this a nice track?" cannot be measured on 20 rows, and I won't pretend otherwise.

## 10. What surprised me while testing reliability

On its first run, the evaluation failed 5 of 11 cases, and none of the failures were crashes.

"我想听日语歌" ("I want to hear some Japanese songs") came back with a warning instead of an answer. The cause: 我想 ("I want") and 想听 ("to hear") were being counted as words the system did not understand. That lowered confidence and turned a correct answer into a caveat. The same thing happened to "something" and "but" in English.

What surprised me is that the parser's own unit tests were all green. They checked what the parser produced (genre, mood, energy), and every value was right. None of them asked whether a complete, ordinary sentence could pass through without being marked as partly incomprehensible. Twenty passing tests, and the behavior was wrong for the most natural way of asking.

Two things came out of this: a filler-word list, and a much lower opinion of "the tests pass" as evidence.

The second surprise was how much of the reliability work was about wording instead of numbers. I added a `relax:` line, and I changed `mood mismatch: energetic vs (+0.0)` to `no mood given (+0.0)`. Neither change affected the ranking, but both completely changed whether a reader could trust the output.

## 11. How I worked with AI

**A suggestion I accepted.** The instructor's feedback on my Module 1–3 submission pointed out that the scoring recipe existed twice: once in `Recommender._score` / `explain_recommendation` on dataclass objects, and once in `score_song` / `recommend_songs` on dictionaries. The weights were shared, but the tie-breaking, the match checks and the explanation strings were duplicated line for line.

I accepted the point and went further than deleting one copy. Scoring now returns a `ScoreBreakdown` of per-rule items, and the explanation text is rendered from those items instead of being recomputed. Ranking and explanation cannot disagree because they read the same object. I also added an invariant test that sums the per-rule points across the whole catalog and compares them to the total, so the duplication cannot creep back unnoticed.

**A suggestion I rejected.** The obvious way to make this a "real" RAG system is to call a language model: embed the knowledge base, embed the query, generate the explanation. I rejected that for two reasons. First, the graded artifact has to run for anyone who clones the repository, with no API key, no network and no model download. An evaluation that only works on my machine is not an evaluation. Second, at 8 notes and 24 sections, TF-IDF already retrieves the right section for all eleven cases. A model would have added a dependency and an uncontrollable source of variation without moving a single number.

I made the same call on a smaller problem. "放松的音乐" ("relaxing music") matched the lo-fi note instead of the chill-mood note because of "音乐" ("music"). I fixed it with a five-word noise list instead of a better model. The corpus is too small for statistics to solve this, and a hand-written list is something I can read and correct.

## 12. Future work

- **Let the system return nothing at all.** It can refuse now, but it still always shows a closest candidate. Sometimes the honest answer is "there is nothing here."
- **Grow the catalog before growing the model.** Two of the eleven cases fail for lack of data. More rows would improve this system more than any change to the scoring.
- **Add a diversity penalty.** Quiet requests still return the same three lo-fi tracks.
- **Use what is already loaded.** Valence, tempo, danceability and acousticness are read but never scored.
- **Replace the hand-tagged estimates with measured audio features,** so the scores rest on data instead of my judgment.
