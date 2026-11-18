"""
Tests for request parsing.

The parser is a table plus some substring matching, so the tests are mostly
about the table's edge cases: which alias wins when two overlap, when a negation
flips an exclusion, and when the knowledge base is allowed to fill a gap (only
into an empty slot, never over something the listener said).
"""

from pathlib import Path

import pytest

from src.catalog import load_songs
from src.nlu import (
    ParsedRequest,
    clarification,
    extract_energy_hint,
    parse_request,
    resolve_request,
)
from src.retrieval import Retriever

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG = REPO_ROOT / "data" / "songs.csv"


@pytest.fixture(scope="module")
def songs():
    return load_songs(CATALOG)


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    return Retriever.from_directory()


def genre_of(parsed: ParsedRequest):
    return parsed.genre.value if parsed.genre else None


def mood_of(parsed: ParsedRequest):
    return parsed.mood.value if parsed.mood else None


# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------


def test_reads_an_english_genre_and_mood(songs):
    parsed = parse_request("happy pop for the weekend", songs)

    assert genre_of(parsed) == "pop"
    assert mood_of(parsed) == "happy"


def test_reads_a_chinese_genre_alias(songs):
    parsed = parse_request("我想听日语歌", songs)

    assert genre_of(parsed) == "j-pop"


def test_the_longer_alias_wins(songs):
    # "indie pop" contains "pop"; the longer alias must claim the span first.
    assert genre_of(parse_request("some indie pop please", songs)) == "indie pop"
    assert genre_of(parse_request("j-pop", songs)) == "j-pop"


def test_a_catalog_value_is_understood_verbatim(songs):
    # No alias needed: anything the catalog uses is searchable as-is.
    assert genre_of(parse_request("synthwave", songs)) == "synthwave"


def test_an_unrelated_word_produces_no_genre(songs):
    parsed = parse_request("zzzz qqqq", songs)

    assert genre_of(parsed) is None
    assert mood_of(parsed) is None


# --------------------------------------------------------------------------
# context and energy
# --------------------------------------------------------------------------


def test_context_is_recognised(songs):
    parsed = parse_request("深夜写代码", songs)

    assert parsed.context.value == "study"


def test_knowledge_base_fills_a_missing_energy(songs, retriever):
    parsed = resolve_request("深夜写代码", songs, retriever)

    assert parsed.energy is not None
    assert 0.25 <= parsed.energy.value <= 0.42
    assert "context_study" in parsed.energy.source


def test_explicit_energy_beats_the_knowledge_base(songs, retriever):
    parsed = resolve_request("深夜写代码 energy 0.8", songs, retriever)

    assert parsed.energy.value == 0.8
    assert parsed.energy.source.startswith("text:")


def test_a_loudness_word_sets_energy(songs):
    parsed = parse_request("high energy workout", songs)

    assert parsed.energy.value == 0.90
    assert parsed.context.value == "gym"


def test_no_context_means_no_energy_guess(songs):
    parsed = parse_request("classical", songs)

    assert parsed.energy is None


# --------------------------------------------------------------------------
# negation
# --------------------------------------------------------------------------


def test_english_negation_becomes_an_exclusion(songs):
    parsed = parse_request("anything but rock", songs)

    assert genre_of(parsed) is None
    assert "rock" in parsed.excluded


def test_chinese_negation_becomes_an_exclusion(songs):
    parsed = parse_request("不要摇滚", songs)

    assert "rock" in parsed.excluded
    assert genre_of(parsed) is None


def test_a_negated_loudness_word_is_ignored(songs):
    # "别太吵" must not be read as "energy 0.85".
    parsed = parse_request("别太吵", songs)

    assert parsed.energy is None


# --------------------------------------------------------------------------
# what was not understood / clarification
# --------------------------------------------------------------------------


def test_unknown_words_are_reported(songs):
    parsed = parse_request("深夜写代码 别太吵", songs)

    assert "太吵" in parsed.unknown


def test_empty_text_needs_clarification(songs):
    parsed = parse_request("", songs)

    assert parsed.needs_clarification


def test_clarification_uses_real_catalog_values(songs):
    question = clarification(parse_request("", songs), songs)

    assert "lofi" in question
    assert "chill" in question
    assert "studying" in question


# --------------------------------------------------------------------------
# energy extraction from knowledge-base prose
# --------------------------------------------------------------------------


def test_energy_range_is_read_as_a_midpoint():
    value, description = extract_energy_hint(
        "Background music sits between 0.25 and 0.42 energy."
    )

    assert value == pytest.approx(0.335, abs=0.01)
    assert description == "0.25-0.42"


def test_a_single_number_is_used_directly():
    value, description = extract_energy_hint("Sits at 0.12 energy and 70 bpm.")

    assert value == pytest.approx(0.12)
    assert description == "0.12"


def test_no_numbers_means_no_hint():
    assert extract_energy_hint("Keep it quiet and repetitive.") is None
