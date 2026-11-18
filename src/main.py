"""
Command line runner for the Music Recommender Simulation.

Run from the project root:
    python -m src.main                      # run every built-in profile
    python -m src.main "Chill Lofi"         # run one profile by name
    python -m src.main ask "深夜写代码 别太吵"  # ask in plain language

Only `python -m src.main` is supported. Running the file directly would need a
dual-import fallback in every module of the project, which is a trap rather
than a feature.
"""

import sys
from pathlib import Path
from typing import Dict, List

from src.catalog import CatalogError, load_songs
from src.nlu import ParsedRequest, Slot, clarification, resolve_request
from src.recommender import MAX_SCORE, Song, UserProfile, rank
from src.retrieval import Retriever

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
    for position, breakdown in enumerate(rank(songs, profile, k=k), start=1):
        song = breakdown.song
        print(
            f"{position}. {song.title} - {song.artist}  "
            f"({breakdown.total:.2f}/{MAX_SCORE:.2f})"
        )
        print(f"   because: {breakdown.text()}")
    print()


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


def ask(text: str) -> int:
    """
    Answer one free-text request.

    Returns 0 when a ranking was produced and 1 when the request was too vague
    to score, in which case the listener is asked one clarifying question
    instead of being handed a list built on guesses.
    """
    songs = load_catalog()
    retriever = Retriever.from_directory()
    parsed = resolve_request(text, songs, retriever)
    energy = parsed.energy or Slot(value=0.5, source="default (no context given)")

    print_parse(parsed, energy)

    if parsed.needs_clarification:
        print()
        print(f"Question  : {clarification(parsed, songs)}")
        return 1

    profile = UserProfile(
        favorite_genre=str(parsed.genre.value) if parsed.genre else "",
        favorite_mood=str(parsed.mood.value) if parsed.mood else "",
        target_energy=float(energy.value),
    )
    print()
    show_recommendations("ask", profile, songs)
    return 0


def main() -> None:
    args = sys.argv[1:]

    if args and args[0] == "ask":
        query = " ".join(args[1:]).strip()
        if not query:
            print(
                'Usage: python -m src.main ask "<what you want to listen to>"',
                file=sys.stderr,
            )
            raise SystemExit(2)
        raise SystemExit(ask(query))

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
