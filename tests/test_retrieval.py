"""
Tests for knowledge-base retrieval.

Two things are worth protecting here:

1. Chinese queries must work. The whole point of the bigram tokenizer is that
   "深夜写代码" finds a document that never contains that phrase, only the words
   separately.
2. Retrieval must be deterministic, because the evaluation harness in P6 and the
   citations in the recommendation output both assume the same query returns the
   same answer twice.
"""

import pytest

from src.retrieval import (
    Chunk,
    Hit,
    Retriever,
    content_terms,
    load_knowledge,
    tokenize,
)

EXPECTED_DOCS = {
    "context_gym",
    "context_study",
    "genre_classical",
    "genre_jpop",
    "genre_lofi",
    "genre_pop",
    "mood_chill",
    "mood_intense",
}


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    return Retriever.from_directory()


# --------------------------------------------------------------------------
# tokenizer
# --------------------------------------------------------------------------


def test_tokenize_splits_cjk_runs_into_bigrams():
    # "深夜写代码" -> 深夜 / 夜写 / 写代 / 代码: a sliding two-character window.
    assert tokenize("深夜写代码") == ["深夜", "夜写", "写代", "代码"]


def test_tokenize_keeps_latin_words_and_lowercases_them():
    assert tokenize("Lo-Fi Beats") == ["lo", "fi", "beats"]


def test_tokenize_handles_a_single_cjk_character():
    assert tokenize("吵") == ["吵"]


def test_content_terms_drops_noise_words():
    # "音乐" is sliced out; "放松" is what actually says something.
    assert content_terms("放松的音乐") == ["放松", "松的", "的音"]
    assert content_terms("music for study") == ["study"]


# --------------------------------------------------------------------------
# loading and chunking
# --------------------------------------------------------------------------


def test_loads_all_eight_documents(retriever):
    assert set(retriever.document_ids) == EXPECTED_DOCS
    # 8 documents x 3 real sections each; the single-'#' title is not a section.
    assert len(retriever.chunks) == 24


def test_front_matter_is_parsed():
    chunks = load_knowledge()

    study = [chunk for chunk in chunks if chunk.doc_id == "context_study"]
    assert study
    assert {chunk.kind for chunk in study} == {"context"}
    assert "写代码" in study[0].tags


def test_sections_are_split_on_second_level_headings(retriever):
    study = [c for c in retriever.chunks if c.doc_id == "context_study"]

    assert [chunk.section for chunk in study] == ["Energy", "Texture", "What to avoid"]
    assert all(chunk.text.strip() for chunk in study)


def test_citation_points_at_file_and_section(retriever):
    hit = retriever.search("gym workout", k=1)[0]

    assert hit.chunk.citation.startswith("kb/context_gym.md#")


# --------------------------------------------------------------------------
# search quality
# --------------------------------------------------------------------------


def test_english_query_finds_the_study_context(retriever):
    top = retriever.search("studying late at night", k=1)[0]

    assert top.chunk.doc_id == "context_study"


def test_chinese_query_finds_the_study_context(retriever):
    top = retriever.search("深夜写代码 别太吵", k=1)[0]

    assert top.chunk.doc_id == "context_study"


def test_genre_query_finds_the_lofi_document(retriever):
    top = retriever.search("lofi beats for background", k=1)[0]

    assert top.chunk.doc_id == "genre_lofi"


def test_gym_query_finds_the_gym_context(retriever):
    top = retriever.search("workout at the gym, high energy", k=1)[0]

    assert top.chunk.doc_id == "context_gym"


def test_relaxing_music_finds_the_chill_mood(retriever):
    # Regression: "音乐" used to pull this towards the lo-fi document because of
    # the "背景音乐" tag, even though the listener asked about a mood.
    top = retriever.search("放松的音乐", k=1)[0]

    assert top.chunk.doc_id == "mood_chill"


def test_noise_filter_keeps_background_music_searchable(retriever):
    # Dropping "音乐" must not make "背景音乐" unfindable.
    top = retriever.search("背景音乐", k=1)[0]

    assert top.chunk.doc_id == "genre_lofi"


def test_unknown_words_return_nothing(retriever):
    assert retriever.search("zzzz qqqq") == []


def test_empty_query_returns_nothing(retriever):
    assert retriever.search("") == []
    assert retriever.search("   ") == []


# --------------------------------------------------------------------------
# filtering, explain mode, determinism
# --------------------------------------------------------------------------


def test_kind_filter_returns_only_that_kind(retriever):
    hits = retriever.search("energy focus", k=10, kind="context")

    assert hits
    assert {hit.chunk.kind for hit in hits} == {"context"}


def test_explain_lists_the_terms_that_scored(retriever):
    hit = retriever.search("深夜写代码", k=1)[0]

    assert isinstance(hit, Hit)
    assert hit.matched
    assert hit.matched[0][0] in {"深夜", "夜写", "写作", "代码", "写代"}
    # The reported contributions are a decomposition of the score, not a guess.
    assert sum(value for _, value in hit.matched) <= hit.score + 1e-9


def test_same_query_returns_the_same_result_twice(retriever):
    first = retriever.search("calm piano for reading", k=5)
    second = retriever.search("calm piano for reading", k=5)

    def shape(hits):
        return [(hit.chunk.doc_id, hit.chunk.section, hit.score) for hit in hits]

    assert shape(first) == shape(second)
