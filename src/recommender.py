"""
Core logic for the Music Recommender Simulation (TasteRadar).

Scoring recipe (documented in README):
    +2.0  genre matches the user's favorite genre
    +1.0  mood matches the user's favorite mood
    +1.0 * (1 - |song energy - target energy|)   energy similarity
Maximum score is 4.0.

Design rule for this module: the recipe lives in exactly ONE place,
score_song(). Ranking, the explanation text and the Recommender facade are all
derived from the ScoreBreakdown it returns, so a change to a weight or to a
match rule can no longer drift between two parallel implementations.

This module does no file I/O. Loading and validating the catalog lives in
src/catalog.py, which keeps scoring a pure function of (song, profile, weights).
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """

    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float


@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """

    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool = False


@dataclass(frozen=True)
class Weights:
    """How many points each rule is worth. Change these, never the scoring code."""

    genre: float = 2.0
    mood: float = 1.0
    energy: float = 1.0

    @property
    def max_score(self) -> float:
        return self.genre + self.mood + self.energy


DEFAULT_WEIGHTS = Weights()
MAX_SCORE = DEFAULT_WEIGHTS.max_score


@dataclass(frozen=True)
class ScoreItem:
    """
    One line of the recipe: which rule fired, what it was worth, and the sentence
    a human reads. `matched` is None for graded rules such as energy, where
    "matched" is not a yes/no question.
    """

    rule: str
    points: float
    detail: str
    matched: Optional[bool] = None


@dataclass(frozen=True)
class ScoreBreakdown:
    """The full result of scoring one song. Everything else is derived from it."""

    song: Song
    items: List[ScoreItem]
    total: float
    energy_gap: float

    def text(self) -> str:
        """Render the explanation from the same data the ranking used."""
        return " | ".join(item.detail for item in self.items)


def score_song(
    song: Song, profile: UserProfile, weights: Weights = DEFAULT_WEIGHTS
) -> ScoreBreakdown:
    """Score one song against one profile. The single implementation of the recipe."""
    genre_hit = song.genre == profile.favorite_genre
    genre_points = weights.genre if genre_hit else 0.0
    if genre_hit:
        genre_detail = f"genre match: {song.genre} (+{genre_points})"
    else:
        genre_detail = (
            f"genre mismatch: {song.genre} vs {profile.favorite_genre} (+{genre_points})"
        )

    mood_hit = song.mood == profile.favorite_mood
    mood_points = weights.mood if mood_hit else 0.0
    if mood_hit:
        mood_detail = f"mood match: {song.mood} (+{mood_points})"
    else:
        mood_detail = (
            f"mood mismatch: {song.mood} vs {profile.favorite_mood} (+{mood_points})"
        )

    gap = abs(song.energy - profile.target_energy)
    energy_points = weights.energy * (1 - gap)
    energy_detail = (
        f"energy {song.energy:.2f} vs target {profile.target_energy:.2f} "
        f"(gap {gap:.2f}, +{energy_points:.2f})"
    )

    items = [
        ScoreItem(rule="genre", points=genre_points, detail=genre_detail, matched=genre_hit),
        ScoreItem(rule="mood", points=mood_points, detail=mood_detail, matched=mood_hit),
        ScoreItem(rule="energy", points=energy_points, detail=energy_detail, matched=None),
    ]
    total = round(genre_points + mood_points + energy_points, 2)
    return ScoreBreakdown(song=song, items=items, total=total, energy_gap=gap)


def rank(
    songs: List[Song],
    profile: UserProfile,
    k: int = 5,
    weights: Weights = DEFAULT_WEIGHTS,
) -> List[ScoreBreakdown]:
    """
    Score every song, then order them.

    Ties are broken by the closer energy match, then by the lower song id, so the
    output is deterministic and reproducible run after run.
    """
    scored = [score_song(song, profile, weights) for song in songs]
    scored.sort(
        key=lambda breakdown: (
            -breakdown.total,
            breakdown.energy_gap,
            breakdown.song.id,
        )
    )
    return scored[:k]


class Recommender:
    """
    OOP facade kept for the starter tests and for first-time readers of the
    project. It holds no rules of its own: every method delegates to
    score_song() / rank(), so there is still only one recipe in the codebase.
    """

    def __init__(self, songs: List[Song], weights: Weights = DEFAULT_WEIGHTS):
        self.songs = songs
        self.weights = weights

    def score(self, user: UserProfile, song: Song) -> ScoreBreakdown:
        return score_song(song, user, self.weights)

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        return [
            breakdown.song
            for breakdown in rank(self.songs, user, k=k, weights=self.weights)
        ]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        return self.score(user, song).text()
