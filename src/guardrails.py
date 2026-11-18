"""
Checks that run after a ranking exists, and the number that decides whether to
show it.

Two different questions are answered here, and keeping them apart is the point:

* Is there a hole in the catalog?  "No j-pop track is tagged calm" is a fact
  about the data, not a matter of degree. It is detected by looking at the songs,
  not by scoring, and it cannot be fixed by tuning a threshold.
* How much of the request does the best answer actually satisfy?  That is a
  fraction, and it is what the confidence number reports.

Confidence is `fit * support`, never a sum: a result that misses what the
listener explicitly asked for cannot be rescued by a big gap to the runner-up or
by a strong knowledge-base hit. Margin and evidence only nudge it.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence

from src.nlu import ParsedRequest
from src.recommender import ScoreBreakdown, Song
from src.retrieval import Hit

# A verdict boundary, not a law of nature. P6 tunes these against labelled cases.
REFUSE_BELOW = 0.55
CAVEAT_BELOW = 0.70

ENERGY_TOLERANCE = 0.15
ENERGY_FALLOFF = 0.50
EVIDENCE_REFERENCE = 0.45
SEPARATION_REFERENCE = 1.5

GENRE_WEIGHT = 0.40
MOOD_WEIGHT = 0.25
ENERGY_WEIGHT = 0.35

SATURATION_LIMIT = 3


@dataclass(frozen=True)
class Issue:
    """Something the answer should admit to."""

    code: str
    severity: str  # "gap" blocks an answer, "warn" only marks it down
    message: str

    @property
    def is_gap(self) -> bool:
        return self.severity == "gap"


def catalog_gaps(
    parsed: ParsedRequest, songs: Sequence[Song], tolerance: float = ENERGY_TOLERANCE
) -> List[Issue]:
    """Facts about the catalog that no amount of scoring can fix."""
    genres = {song.genre for song in songs}
    moods = {song.mood for song in songs}
    genre = parsed.genre.value if parsed.genre else None
    mood = parsed.mood.value if parsed.mood else None
    issues: List[Issue] = []

    if genre and genre not in genres:
        issues.append(Issue("genre_missing", "gap", f"the catalog has no {genre} track"))

    if mood and mood not in moods:
        issues.append(Issue("mood_missing", "gap", f"no track is tagged {mood}"))

    if genre and mood and genre in genres and mood in moods:
        if not any(song.genre == genre and song.mood == mood for song in songs):
            issues.append(
                Issue("pair_missing", "gap", f"no {mood} {genre} track exists")
            )

    if genre and parsed.energy is not None and genre in genres:
        value = float(parsed.energy.value)
        in_genre = [song for song in songs if song.genre == genre]
        if in_genre and all(abs(song.energy - value) > tolerance for song in in_genre):
            closest = min(in_genre, key=lambda song: abs(song.energy - value))
            issues.append(
                Issue(
                    "energy_unreachable",
                    "warn",
                    f"no {genre} track is near {value:.2f} energy "
                    f"(closest is {closest.energy:.2f}: {closest.title})",
                )
            )

    return issues


def fit(parsed: ParsedRequest, top: ScoreBreakdown) -> float:
    """
    How much of the request the best candidate actually satisfies, 0 to 1.

    Only constraints the listener stated count. A defaulted energy or an absent
    mood is neutral, not satisfied: counting it would inflate every answer.
    """
    parts = []
    if parsed.genre:
        parts.append((GENRE_WEIGHT, 1.0 if top.song.genre == parsed.genre.value else 0.0))
    if parsed.mood:
        parts.append((MOOD_WEIGHT, 1.0 if top.song.mood == parsed.mood.value else 0.0))
    if parsed.energy:
        gap = abs(top.song.energy - float(parsed.energy.value))
        parts.append((ENERGY_WEIGHT, max(0.0, 1.0 - gap / ENERGY_FALLOFF)))

    total_weight = sum(weight for weight, _ in parts)
    if total_weight == 0:
        return 0.0
    return sum(weight * value for weight, value in parts) / total_weight


def separation(breakdowns: Sequence[ScoreBreakdown]) -> float:
    """How far ahead the leader is. A tie for first is not a confident answer."""
    if len(breakdowns) < 2:
        return 1.0
    top = breakdowns[0].total
    rest = sum(entry.total for entry in breakdowns[1:]) / (len(breakdowns) - 1)
    return _clamp((top - rest) / SEPARATION_REFERENCE)


def evidence_strength(hits: Sequence[Hit]) -> float:
    """How well the knowledge base backed this request up."""
    best = max((hit.score for hit in hits), default=0.0)
    return _clamp(best / EVIDENCE_REFERENCE)


def confidence(
    parsed: ParsedRequest, breakdowns: Sequence[ScoreBreakdown], hits: Sequence[Hit]
) -> float:
    if not breakdowns:
        return 0.0
    support = 0.5 * separation(breakdowns) + 0.5 * evidence_strength(hits)
    return round(_clamp(fit(parsed, breakdowns[0]) * (0.80 + 0.20 * support)), 2)


def soft_issues(
    parsed: ParsedRequest,
    breakdowns: Sequence[ScoreBreakdown],
    hits: Sequence[Hit],
    limit: int = SATURATION_LIMIT,
) -> List[Issue]:
    """Problems that make an answer worth a warning, not a refusal."""
    issues: List[Issue] = []

    if parsed.unknown:
        issues.append(
            Issue(
                "unknown_terms",
                "warn",
                f"did not understand: {', '.join(parsed.unknown)}",
            )
        )

    # Missing knowledge-base support is deliberately NOT an issue. It already
    # lowers the confidence through the evidence term, and a request the parser
    # understood completely does not need a note about the knowledge base: that
    # would turn a correct answer into a warning for reasons the listener cannot
    # act on.

    if breakdowns:
        counts = {}
        for entry in breakdowns:
            counts[entry.song.genre] = counts.get(entry.song.genre, 0) + 1
        genre, count = max(counts.items(), key=lambda item: (item[1], item[0]))
        if count > limit:
            issues.append(
                Issue(
                    "saturated",
                    "warn",
                    f"{count} of the {len(breakdowns)} picks are {genre}",
                )
            )

    return issues


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
