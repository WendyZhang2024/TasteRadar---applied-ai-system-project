"""
Command line runner for the Music Recommender Simulation.

Run from the project root:
    python -m src.main                 # run every profile
    python -m src.main "Chill Lofi"    # run one profile by name
"""

import os
import sys
from typing import Dict, List

try:  # `python -m src.main`
    from src.recommender import MAX_SCORE, Song, UserProfile, load_songs, rank
except ModuleNotFoundError:  # `python src/main.py`
    from recommender import MAX_SCORE, Song, UserProfile, load_songs, rank

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "songs.csv")

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
    songs = load_songs(DATA_PATH)
    print(f"Loaded songs: {len(songs)}")
    print()

    requested = sys.argv[1] if len(sys.argv) > 1 else None
    for profile_name, profile in PROFILES.items():
        if requested and requested.lower() not in profile_name.lower():
            continue
        show_recommendations(profile_name, profile, songs)


if __name__ == "__main__":
    main()
