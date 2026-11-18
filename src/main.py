"""
Command line runner for the Music Recommender Simulation.

Run from the project root:
    python -m src.main                      # run every built-in profile
    python -m src.main "Chill Lofi"         # run one profile by name
    python -m src.main ask "深夜写代码 别太吵"  # ask in plain language
    python -m src.main ask "chill lofi" --trace

Only `python -m src.main` is supported. Running the file directly would need a
dual-import fallback in every module of the project, which is a trap rather
than a feature.
"""

import sys
from pathlib import Path
from typing import Dict, List, Sequence

from src.agent import AgentResult, RecommendationAgent
from src.catalog import CatalogError, load_songs
from src.evaluate import main as run_evaluation
from src.nlu import ParsedRequest, Slot, clarification
from src.recommender import MAX_SCORE, ScoreBreakdown, Song, UserProfile, rank
from src.retrieval import Hit, Retriever

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "songs.csv"

# Four everyday taste profiles plus one that the catalog cannot satisfy, used to
# see where the scoring breaks down.
PROFILES: Dict[str, UserProfile] = {
    "High-Energy Pop": UserProfile(
        favorite_genre="pop", favorite_mood="happy", target_energy=0.85
    ),
    "Chill Lofi": UserProfile(
        favorite_genre="lofi", favorite_mood="chill", target_energy=0.30
    ),
    "Intense Rock": UserProfile(
        favorite_genre="rock", favorite_mood="intense", target_energy=0.90
    ),
    "J-Pop, Calm": UserProfile(
        favorite_genre="j-pop", favorite_mood="calm", target_energy=0.40
    ),
    "Impossible: Classical + Euphoric": UserProfile(
        favorite_genre="classical", favorite_mood="euphoric", target_energy=0.90
    ),
}


def load_catalog() -> List[Song]:
    """Load the catalog, or explain in one line why it could not be loaded."""
    try:
        return load_songs(DATA_PATH)
    except CatalogError as exc:
        print(f"Could not load the catalog.\n{exc}", file=sys.stderr)
        raise SystemExit(2)


def print_breakdowns(breakdowns: Sequence[ScoreBreakdown]) -> None:
    for position, breakdown in enumerate(breakdowns, start=1):
        song = breakdown.song
        print(
            f"{position}. {song.title} - {song.artist}  "
            f"({breakdown.total:.2f}/{MAX_SCORE:.2f})"
        )
        print(f"   because: {breakdown.text()}")
    print()


def show_recommendations(
    profile_name: str, profile: UserProfile, songs: List[Song], k: int = 5
) -> None:
    """Print the top k songs for one user profile."""
    print("=" * 72)
    print(
        f"{profile_name}: genre={profile.favorite_genre or '(any)'}, "
        f"mood={profile.favorite_mood or '(any)'}, energy={profile.target_energy}"
    )
    print("=" * 72)
    print_breakdowns(rank(songs, profile, k=k))


def _value_text(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _slot_line(label: str, slot: Slot) -> str:
    return f"{label:<10}: {_value_text(slot.value):<14} <- {slot.source}"


def print_parse(parsed: ParsedRequest, energy: Slot) -> None:
    """Show exactly what the sentence was understood to mean."""
    print(f"Request   : {parsed.text.strip() or '(empty)'}")
    for label, slot in (
        ("Genre", parsed.genre),
        ("Mood", parsed.mood),
        ("Context", parsed.context),
    ):
        print(_slot_line(label, slot) if slot else f"{label:<10}: (not stated)")
    print(_slot_line("Energy", energy))
    print(f"Excluded  : {', '.join(parsed.excluded) or '-'}")
    print(f"Unknown   : {', '.join(parsed.unknown) or '-'}")


def _evidence_text(hits: Sequence[Hit]) -> str:
    if not hits:
        return "(none)"
    return " | ".join(f"{hit.chunk.citation} {hit.score:.2f}" for hit in hits)


def print_result(result: AgentResult, trace: bool = False, songs: Sequence[Song] = ()) -> None:
    """The whole verdict: what was understood, why, and what came of it."""
    energy = result.parsed.energy or Slot(
        value=0.5, source="default (no context given)"
    )
    print_parse(result.parsed, energy)
    print(f"Evidence  : {_evidence_text(result.evidence)}")
    print(f"Confidence: {result.confidence:.2f}   [{result.decision}]")

    if result.relaxation:
        print(
            f"  relax : dropped the {result.relaxation} constraint, "
            "no track in the catalog matched it"
        )
    for issue in result.issues:
        print(f"  {issue.severity:<5}: {issue.message}")

    if trace:
        print("  trace :")
        for step in result.trace:
            print(f"    {step.name:<9} {step.detail}")

    if result.decision == "clarify":
        print()
        print(f"Question  : {clarification(result.parsed, songs)}")
        return

    if result.decision == "refuse":
        print()
        print("No confident match.")
        if result.recommendations:
            closest = result.recommendations[0]
            song = closest.song
            print(
                f"  closest : {song.title} - {song.artist} "
                f"({song.genre}/{song.mood}, energy {song.energy:.2f}, "
                f"{closest.total:.2f}/{MAX_SCORE:.2f})"
            )
        return

    print()
    print_breakdowns(result.recommendations)


def ask(text: str, trace: bool = False) -> int:
    """
    Answer one free-text request.

    Exit codes: 0 answered (with or without a warning), 1 needs more
    information, 2 no confident match.
    """
    agent = RecommendationAgent(load_catalog(), Retriever.from_directory())
    result = agent.recommend(text)
    print_result(result, trace=trace, songs=agent.songs)
    return {"answer": 0, "caveat": 0, "clarify": 1, "refuse": 2}[result.decision]


def _use_utf8_output() -> None:
    # Catalog titles and requests contain Chinese and Japanese. A Windows console
    # defaults to a legacy code page and would print them as mojibake.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def main() -> None:
    _use_utf8_output()
    args = sys.argv[1:]

    if args and args[0] == "eval":
        raise SystemExit(run_evaluation())

    if args and args[0] == "ask":
        rest = [arg for arg in args[1:] if arg != "--trace"]
        trace = "--trace" in args[1:]
        query = " ".join(rest).strip()
        if not query:
            print(
                'Usage: python -m src.main ask "<what you want to listen to>"',
                file=sys.stderr,
            )
            raise SystemExit(2)
        raise SystemExit(ask(query, trace=trace))

    songs = load_catalog()
    print(f"Loaded songs: {len(songs)}")
    print()

    requested = args[0] if args else None
    for profile_name, profile in PROFILES.items():
        if requested and requested.lower() not in profile_name.lower():
            continue
        show_recommendations(profile_name, profile, songs)


if __name__ == "__main__":
    main()
