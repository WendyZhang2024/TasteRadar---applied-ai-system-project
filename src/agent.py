"""
The recommendation agent: parse, retrieve, rank, check, then decide what to say.

The loop is small but it is a loop. It can revise its own plan exactly once --
dropping the softest constraint when the catalog proves that combination does
not exist -- and then it either answers, answers with a warning, asks a question
or refuses. Every step is recorded, so a verdict can be explained after the fact
instead of being taken on faith.

Why only the mood is ever relaxed: genre is the hardest boundary in this scoring
recipe (worth 2.0 on its own), so dropping it would not make the answer more
honest, it would just make it about something else.
"""

from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

from src import guardrails
from src.guardrails import Issue
from src.nlu import ParsedRequest, resolve_request
from src.recommender import ScoreBreakdown, Song, UserProfile, rank
from src.retrieval import Hit, Retriever

# An answer that had to drop a constraint is not worth full confidence.
RELAXATION_PENALTY = 0.85
# Every word we failed to understand is a piece of the request we ignored.
UNKNOWN_PENALTY = 0.05
MAX_UNKNOWN_PENALTY = 0.20


@dataclass(frozen=True)
class Step:
    name: str
    detail: str


@dataclass(frozen=True)
class AgentResult:
    request: str
    parsed: ParsedRequest
    decision: str  # "answer" | "caveat" | "refuse" | "clarify"
    confidence: float
    recommendations: Tuple[ScoreBreakdown, ...]
    issues: Tuple[Issue, ...]
    evidence: Tuple[Hit, ...]
    relaxation: Optional[str]
    trace: Tuple[Step, ...]


class RecommendationAgent:
    def __init__(self, songs: Sequence[Song], retriever: Retriever):
        self.songs = list(songs)
        self.retriever = retriever

    def recommend(self, text: str, k: int = 5) -> AgentResult:
        trace: List[Step] = []

        parsed = resolve_request(text, self.songs, self.retriever)
        trace.append(Step("parse", _describe(parsed)))

        hits = tuple(self.retriever.search(text, k=3))
        trace.append(
            Step(
                "retrieve",
                ", ".join(f"{hit.chunk.citation} {hit.score:.2f}" for hit in hits)
                or "no knowledge matches",
            )
        )

        if parsed.needs_clarification:
            trace.append(Step("stop", "no genre and no mood were recognised"))
            return AgentResult(
                request=text,
                parsed=parsed,
                decision="clarify",
                confidence=0.0,
                recommendations=(),
                issues=(),
                evidence=hits,
                relaxation=None,
                trace=tuple(trace),
            )

        issues = guardrails.catalog_gaps(parsed, self.songs)
        trace.append(Step("gaps", _gap_text(issues)))

        scoring = parsed
        relaxation: Optional[str] = None

        if _has_pair_gap(issues) and parsed.mood is not None:
            candidate = replace(parsed, mood=None)
            remaining = guardrails.catalog_gaps(candidate, self.songs)
            if not any(issue.is_gap for issue in remaining):
                scoring = candidate
                relaxation = "mood"
                issues = remaining
                trace.append(
                    Step("relax", "dropped the mood constraint after a catalog gap")
                )

        breakdowns = self._rank(scoring, k)
        trace.append(
            Step(
                "rank",
                f"top={breakdowns[0].song.title} {breakdowns[0].total:.2f}"
                if breakdowns
                else "no candidates",
            )
        )

        value = guardrails.confidence(scoring, breakdowns, hits)
        value = round(value * _penalty(scoring, relaxation), 2)

        issues = list(issues) + guardrails.soft_issues(scoring, breakdowns, hits)
        decision = _decide(issues, value, relaxation)
        trace.append(Step("decide", f"{decision} at confidence {value:.2f}"))

        return AgentResult(
            request=text,
            parsed=parsed,
            decision=decision,
            confidence=value,
            recommendations=tuple(breakdowns),
            issues=tuple(issues),
            evidence=hits,
            relaxation=relaxation,
            trace=tuple(trace),
        )

    def _rank(self, parsed: ParsedRequest, k: int) -> List[ScoreBreakdown]:
        """Score with whatever survived the relaxation step; (any) means unset."""
        profile = UserProfile(
            favorite_genre=str(parsed.genre.value) if parsed.genre else "",
            favorite_mood=str(parsed.mood.value) if parsed.mood else "",
            target_energy=float(parsed.energy.value) if parsed.energy else 0.5,
        )
        return rank(self.songs, profile, k=k)


def _penalty(parsed: ParsedRequest, relaxation: Optional[str]) -> float:
    """
    Confidence is trust, not fit.

    Two things shrink how much an answer is worth trusting: a constraint that had
    to be dropped, and words in the request that were never understood.
    """
    factor = RELAXATION_PENALTY if relaxation is not None else 1.0
    if parsed.unknown:
        factor *= 1.0 - min(MAX_UNKNOWN_PENALTY, UNKNOWN_PENALTY * len(parsed.unknown))
    return factor


def _decide(issues: Sequence[Issue], confidence: float, relaxation: Optional[str]) -> str:
    if any(issue.is_gap for issue in issues):
        return "refuse"
    if confidence < guardrails.REFUSE_BELOW:
        return "refuse"
    if relaxation is not None:
        return "caveat"
    if confidence < guardrails.CAVEAT_BELOW or issues:
        return "caveat"
    return "answer"


def _has_pair_gap(issues: Sequence[Issue]) -> bool:
    return any(issue.code == "pair_missing" for issue in issues)


def _describe(parsed: ParsedRequest) -> str:
    parts = []
    if parsed.genre:
        parts.append(f"genre={parsed.genre.value}")
    if parsed.mood:
        parts.append(f"mood={parsed.mood.value}")
    if parsed.context:
        parts.append(f"context={parsed.context.value}")
    if parsed.energy:
        parts.append(f"energy={float(parsed.energy.value):.2f} ({parsed.energy.source})")
    return ", ".join(parts) or "nothing recognised"


def _gap_text(issues: Sequence[Issue]) -> str:
    return ", ".join(f"{issue.code}: {issue.message}" for issue in issues) or "none"
