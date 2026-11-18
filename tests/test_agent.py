"""
Tests for the agent and its guardrails.

The interesting cases are the ones where the system must *not* answer: a catalog
hole, a request that satisfies nothing, a sentence with no clue in it. Those are
the behaviour the module exists for, so they get the most coverage.
"""

from pathlib import Path

import pytest

from src import guardrails
from src.agent import RecommendationAgent
from src.catalog import load_songs
from src.nlu import parse_request
from src.retrieval import Retriever

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG = REPO_ROOT / "data" / "songs.csv"


@pytest.fixture(scope="module")
def songs():
    return load_songs(CATALOG)


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    return Retriever.from_directory()


@pytest.fixture(scope="module")
def agent(songs, retriever) -> RecommendationAgent:
    return RecommendationAgent(songs, retriever)


# --------------------------------------------------------------------------
# catalog gaps
# --------------------------------------------------------------------------


def test_a_missing_genre_mood_pair_is_a_gap(songs):
    issues = guardrails.catalog_gaps(parse_request("calm j-pop", songs), songs)

    assert [issue.code for issue in issues] == ["pair_missing"]
    assert issues[0].is_gap


def test_an_unreachable_energy_is_only_a_warning(songs):
    issues = guardrails.catalog_gaps(parse_request("classical energy 0.9", songs), songs)

    assert [issue.code for issue in issues] == ["energy_unreachable"]
    assert not issues[0].is_gap


def test_a_satisfiable_request_has_no_gaps(songs):
    assert guardrails.catalog_gaps(parse_request("chill lofi", songs), songs) == []


# --------------------------------------------------------------------------
# confidence
# --------------------------------------------------------------------------


def test_a_perfect_match_fits_completely(agent):
    result = agent.recommend("chill lofi for late night coding")

    assert guardrails.fit(result.parsed, result.recommendations[0]) == 1.0


def test_a_poor_match_scores_lower_than_a_good_one(agent):
    good = agent.recommend("chill lofi for late night coding")
    poor = agent.recommend("classical high energy")

    assert good.confidence > poor.confidence


# --------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------


def test_a_clear_request_is_answered(agent, songs):
    result = agent.recommend("chill lofi for late night coding")

    assert result.decision == "answer"
    assert len(result.recommendations) == 5
    assert result.confidence >= guardrails.CAVEAT_BELOW


def test_answered_songs_all_exist_in_the_catalog(agent, songs):
    result = agent.recommend("chill lofi for late night coding")
    catalog_ids = {song.id for song in songs}

    assert {entry.song.id for entry in result.recommendations} <= catalog_ids


def test_a_catalog_hole_relaxes_the_softest_constraint(agent):
    result = agent.recommend("calm j-pop")

    assert result.decision == "caveat"
    assert result.relaxation == "mood"
    assert result.recommendations[0].song.genre == "j-pop"


def test_an_unsatisfiable_request_is_refused(agent):
    result = agent.recommend("classical high energy")

    assert result.decision == "refuse"
    assert result.confidence < guardrails.REFUSE_BELOW


def test_a_refusal_still_reports_the_closest_candidate(agent):
    result = agent.recommend("classical high energy")

    assert result.recommendations
    assert result.recommendations[0].song.genre == "classical"


def test_a_request_with_no_clue_asks_a_question(agent):
    result = agent.recommend("深夜写代码")

    assert result.decision == "clarify"
    assert result.recommendations == ()
    assert result.confidence == 0.0


def test_unrecognised_words_are_reported_as_a_warning(agent):
    result = agent.recommend("chill lofi 别太吵")

    assert result.decision == "caveat"
    codes = {issue.code for issue in result.issues}
    assert "unknown_terms" in codes


# --------------------------------------------------------------------------
# evidence, trace, determinism
# --------------------------------------------------------------------------


def test_the_knowledge_base_hit_is_recorded_as_evidence(agent):
    result = agent.recommend("chill lofi for late night coding")

    citations = [hit.chunk.citation for hit in result.evidence]
    assert any("context_study" in citation for citation in citations)


def test_the_trace_records_every_step(agent):
    result = agent.recommend("calm j-pop")
    names = [step.name for step in result.trace]

    assert names[0] == "parse"
    assert "retrieve" in names
    assert "relax" in names
    assert names[-1] == "decide"


def test_the_same_request_gives_the_same_verdict(agent):
    first = agent.recommend("calm j-pop")
    second = agent.recommend("calm j-pop")

    assert first.decision == second.decision
    assert first.confidence == second.confidence
    assert [entry.song.id for entry in first.recommendations] == [
        entry.song.id for entry in second.recommendations
    ]
