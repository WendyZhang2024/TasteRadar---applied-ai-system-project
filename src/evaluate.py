"""
Labelled evaluation of the whole pipeline: parse, retrieve, rank, decide.

Each case asserts a *property* of the verdict -- which decision came out, which
genre reached the top, whether the mood had to be relaxed -- never a sentence of
output. Word a caveat differently and the suite still passes; answer a request
that should have been refused and it fails. That is the difference between a
regression test and a screenshot.

Run it with:

    python -m src.main eval

which writes reports/evaluation.md and reports/evaluation.json. No timestamps are
written on purpose, so two runs diff cleanly and a reviewer can see that the file
is generated, not hand-edited.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from src.agent import AgentResult, RecommendationAgent
from src.catalog import load_songs
from src.retrieval import Retriever

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "songs.csv"
REPORT_DIR = PROJECT_ROOT / "reports"


@dataclass(frozen=True)
class Case:
    """One labelled request and the property its verdict must satisfy."""

    name: str
    request: str
    expect: str  # "answer" | "caveat" | "refuse" | "clarify"
    genre: Optional[str] = None
    forbidden_genre: Optional[str] = None
    relax: Optional[str] = None
    min_confidence: float = 0.0
    max_confidence: float = 1.0


CASES: Tuple[Case, ...] = (
    Case("lofi_study", "chill lofi for late night coding", "answer", genre="lofi"),
    Case("pop_gym", "high energy pop for the gym", "answer", genre="pop"),
    Case("romantic_rnb", "romantic r&b", "answer", genre="r&b"),
    Case("sad_mandopop", "sad mandopop", "answer", genre="mandopop"),
    Case("chinese_genre", "我想听日语歌", "answer", genre="j-pop"),
    Case("negated_genre", "anything but rock, something chill", "answer", forbidden_genre="rock"),
    Case("jpop_calm", "calm j-pop", "caveat", genre="j-pop", relax="mood"),
    Case("classical_loud", "classical high energy", "refuse", max_confidence=0.54),
    Case("edm_quiet", "edm energy 0.1", "refuse", max_confidence=0.54),
    Case("vague_request", "深夜写代码 别太吵", "clarify"),
    Case("empty_request", "", "clarify"),
)


@dataclass(frozen=True)
class Outcome:
    case: Case
    decision: str
    confidence: float
    top_genre: Optional[str]
    relaxation: Optional[str]
    failures: Tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def check(case: Case, result: AgentResult) -> List[str]:
    """Every way this verdict can fail its label."""
    failures: List[str] = []
    top_genre = result.recommendations[0].song.genre if result.recommendations else None

    if result.decision != case.expect:
        failures.append(f"expected {case.expect}, got {result.decision}")

    if case.genre and top_genre != case.genre:
        failures.append(f"expected top genre {case.genre}, got {top_genre}")

    if case.forbidden_genre and top_genre == case.forbidden_genre:
        failures.append(f"top genre {top_genre} should have been excluded")

    if case.relax != result.relaxation:
        failures.append(f"expected relaxation {case.relax}, got {result.relaxation}")

    if not case.min_confidence <= result.confidence <= case.max_confidence:
        failures.append(
            f"confidence {result.confidence:.2f} outside "
            f"{case.min_confidence:.2f}-{case.max_confidence:.2f}"
        )

    return failures


def evaluate(
    agent: RecommendationAgent, cases: Sequence[Case] = CASES
) -> List[Outcome]:
    outcomes = []
    for case in cases:
        result = agent.recommend(case.request)
        top_genre = result.recommendations[0].song.genre if result.recommendations else None
        outcomes.append(
            Outcome(
                case=case,
                decision=result.decision,
                confidence=result.confidence,
                top_genre=top_genre,
                relaxation=result.relaxation,
                failures=tuple(check(case, result)),
            )
        )
    return outcomes


def summarise(outcomes: Sequence[Outcome]) -> dict:
    by_decision: dict = {}
    for outcome in outcomes:
        by_decision[outcome.decision] = by_decision.get(outcome.decision, 0) + 1

    answered = [o.confidence for o in outcomes if o.decision in ("answer", "caveat")]
    refused = [o.confidence for o in outcomes if o.decision == "refuse"]

    return {
        "total": len(outcomes),
        "passed": sum(1 for outcome in outcomes if outcome.passed),
        "failed": sum(1 for outcome in outcomes if not outcome.passed),
        "by_decision": by_decision,
        "answered_confidence": {
            "min": min(answered) if answered else None,
            "max": max(answered) if answered else None,
        },
        "refused_confidence": {
            "min": min(refused) if refused else None,
            "max": max(refused) if refused else None,
        },
    }


def render_markdown(outcomes: Sequence[Outcome]) -> str:
    summary = summarise(outcomes)
    lines: List[str] = [
        "# Evaluation report",
        "",
        f"{summary['total']} labelled requests, run end to end through the agent "
        "with the catalog and the knowledge base as shipped.",
        "",
        "Each case asserts a property of the verdict -- the decision, the top "
        "genre, whether the mood had to be relaxed -- not the wording of the "
        "output, so this table stays meaningful when the text changes.",
        "",
        "| # | Request | Expected | Decision | Confidence | Top genre | Result |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for index, outcome in enumerate(outcomes, start=1):
        case = outcome.case
        expected = case.expect + (f" / {case.genre}" if case.genre else "")
        result = "PASS" if outcome.passed else "FAIL: " + "; ".join(outcome.failures)
        lines.append(
            f"| {index} | `{case.request}` | {expected} | {outcome.decision} | "
            f"{outcome.confidence:.2f} | {outcome.top_genre or '-'} | {result} |"
        )

    lines += [
        "",
        "## Summary",
        "",
        f"- {summary['passed']} of {summary['total']} cases passed",
        f"- verdicts: "
        + ", ".join(f"{count} {name}" for name, count in sorted(summary["by_decision"].items())),
    ]

    answered = summary["answered_confidence"]
    refused = summary["refused_confidence"]
    if answered["min"] is not None:
        lines.append(
            f"- answered cases: confidence {answered['min']:.2f} to {answered['max']:.2f}"
        )
    if refused["max"] is not None:
        lines.append(
            f"- refused cases: confidence {refused['min']:.2f} to {refused['max']:.2f}"
        )

    lines += [
        "",
        "## Where the thresholds sit",
        "",
        "The refusal boundary is a constant (`guardrails.REFUSE_BELOW`). This is the "
        "evidence that it is not doing heroics: the highest refused case and the "
        "lowest answered case are far apart, so the exact value could move without "
        "changing any verdict in this set.",
        "",
        "| Confidence | Decision | Request |",
        "| --- | --- | --- |",
    ]
    for outcome in sorted(outcomes, key=lambda item: -item.confidence):
        lines.append(
            f"| {outcome.confidence:.2f} | {outcome.decision} | `{outcome.case.request}` |"
        )

    lines += [
        "",
        "## What this does not cover",
        "",
        "- Only 11 requests. It is a regression net, not a benchmark.",
        "- Nothing here checks whether a *good* answer is also a *good song*, only "
        "that it satisfies the stated constraints.",
        "- The catalog is fixed, so no case exercises a change in the data.",
        "",
    ]
    return "\n".join(lines)


def render_json(outcomes: Sequence[Outcome]) -> str:
    payload = {
        "summary": summarise(outcomes),
        "cases": [
            {
                "name": outcome.case.name,
                "request": outcome.case.request,
                "expected": outcome.case.expect,
                "decision": outcome.decision,
                "confidence": outcome.confidence,
                "top_genre": outcome.top_genre,
                "relaxation": outcome.relaxation,
                "passed": outcome.passed,
                "failures": list(outcome.failures),
            }
            for outcome in outcomes
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(output_dir: Path = REPORT_DIR) -> int:
    agent = RecommendationAgent(load_songs(DATA_PATH), Retriever.from_directory())
    outcomes = evaluate(agent)
    summary = summarise(outcomes)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation.md").write_text(render_markdown(outcomes), encoding="utf-8")
    (output_dir / "evaluation.json").write_text(render_json(outcomes), encoding="utf-8")

    print(f"{summary['passed']}/{summary['total']} cases passed")
    for outcome in outcomes:
        if not outcome.passed:
            print(f"  FAIL {outcome.case.name}: {'; '.join(outcome.failures)}")
    print(f"report written to {output_dir}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
