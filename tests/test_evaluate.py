"""
Tests for the evaluation harness itself.

A report you cannot trust is worse than no report, so the harness gets its own
tests: the labelled set must actually pass, a wrong label must be reported
rather than swallowed, and the two output formats must agree.
"""

import json
from pathlib import Path

import pytest

from src.agent import RecommendationAgent
from src.catalog import load_songs
from src.evaluate import CASES, Outcome, Case, evaluate, render_json, render_markdown, summarise
from src.retrieval import Retriever

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG = REPO_ROOT / "data" / "songs.csv"


@pytest.fixture(scope="module")
def agent() -> RecommendationAgent:
    return RecommendationAgent(load_songs(CATALOG), Retriever.from_directory())


@pytest.fixture(scope="module")
def outcomes(agent):
    return evaluate(agent)


def test_every_labelled_case_passes(outcomes):
    failures = [
        f"{outcome.case.name}: {'; '.join(outcome.failures)}"
        for outcome in outcomes
        if not outcome.passed
    ]

    assert failures == []


def test_a_wrong_label_is_reported(agent):
    wrong = Case("deliberately_wrong", "chill lofi for late night coding", "refuse")

    outcome = evaluate(agent, [wrong])[0]

    assert not outcome.passed
    assert any("expected refuse" in failure for failure in outcome.failures)


def test_a_forbidden_genre_is_reported(agent):
    wrong = Case(
        "wrong_genre",
        "chill lofi for late night coding",
        "answer",
        forbidden_genre="lofi",
    )

    outcome = evaluate(agent, [wrong])[0]

    assert not outcome.passed
    assert any("should have been excluded" in failure for failure in outcome.failures)


def test_summary_counts_match_the_cases(outcomes):
    summary = summarise(outcomes)

    assert summary["total"] == len(CASES)
    assert summary["passed"] + summary["failed"] == summary["total"]
    assert sum(summary["by_decision"].values()) == summary["total"]


def test_markdown_has_a_row_per_case(outcomes):
    report = render_markdown(outcomes)
    rows = [line for line in report.splitlines() if line.startswith("| ") and "`" in line]

    assert len(rows) >= len(outcomes)
    assert "Evaluation report" in report


def test_json_round_trips_and_agrees_with_the_outcomes(outcomes):
    payload = json.loads(render_json(outcomes))

    assert len(payload["cases"]) == len(outcomes)
    assert payload["summary"]["total"] == len(outcomes)
    assert all(entry["passed"] for entry in payload["cases"])


def test_an_outcome_with_no_failures_passes():
    outcome = Outcome(
        case=CASES[0],
        decision="answer",
        confidence=0.9,
        top_genre="lofi",
        relaxation=None,
        failures=(),
    )

    assert outcome.passed
