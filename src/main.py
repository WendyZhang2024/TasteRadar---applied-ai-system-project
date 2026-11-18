"""
Command line runner for the Music Recommender Simulation.

Run from the project root:
    python -m src.main                 # run every profile
    python -m src.main "Chill Lofi"    # run one profile by name

Only `python -m src.main` is supported. Running the file directly would need a
dual-import fallback in every module of the project, which is a trap rather
than a feature.
"""

import sys
from pathlib import Path
from typing import Dict, List

from src.catalog import CatalogError, load_songs
from src.recommender import MAX_SCORE, Song, UserProfile, rank

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


def show_recommendations(
    profile_name: str, profile: UserProfile, songs: List[Song], k: int = 5
) -> None:
    """Print the top k songs for one user profile."""
    print("=" * 72)
    print(
        f"{profile_name}: genre={profile.favorite_genre}, "
        f"mood={profile.favorite_mood}, energy={profile.target_energy}"
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


def main() -> None:
    try:
        songs = load_songs(DATA_PATH)
    except CatalogError as exc:
        # A broken catalog is a one-line diagnosis, not a traceback.
        print(f"Could not load the catalog.\n{exc}", file=sys.stderr)
        raise SystemExit(2)

    print(f"Loaded songs: {len(songs)}")
    print()

    requested = sys.argv[1] if len(sys.argv) > 1 else None
    for profile_name, profile in PROFILES.items():
        if requested and requested.lower() not in profile_name.lower():
            continue
        show_recommendations(profile_name, profile, songs)


if __name__ == "__main__":
    main()
