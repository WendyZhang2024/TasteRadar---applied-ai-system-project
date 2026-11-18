"""
Frozen-behaviour test for TasteRadar 1.0.

This file was written BEFORE the scoring refactor and pins the exact
title/score sequence the command line prints for the five built-in profiles.
It runs the real CLI in a subprocess instead of importing Python objects, so it
keeps passing while the internals are restructured -- which is what makes it a
useful refactor safety net rather than a second description of the code.

If this test goes red, the refactor changed behaviour. Fix the code, not the
expectation.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# "1. Sunrise City - Neon Echo  (3.97/4.00)"
LINE = re.compile(
    r"^\d+\. (?P<title>.+?) - (?P<artist>.+?)\s+\((?P<score>\d+\.\d{2})/4\.00\)$"
)

EXPECTED = [
    # High-Energy Pop (pop / happy / 0.85)
    ("Sunrise City", "3.97"),
    ("Gym Hero", "2.92"),
    ("Rooftop Lights", "1.91"),
    ("火炎", "1.00"),
    ("Storm Runner", "0.94"),
    # Chill Lofi (lofi / chill / 0.30)
    ("Library Rain", "3.95"),
    ("Midnight Coding", "3.88"),
    ("Focus Flow", "2.90"),
    ("Spacewalk Thoughts", "1.98"),
    ("Cornfield Chase", "1.00"),
    # Intense Rock (rock / intense / 0.90)
    ("Storm Runner", "3.99"),
    ("Gym Hero", "1.97"),
    ("Piscina spedup", "0.95"),
    ("火炎", "0.95"),
    ("Sunrise City", "0.92"),
    # J-Pop, Calm (j-pop / calm / 0.40)
    ("晩餐歌", "2.78"),
    ("打上花火", "2.68"),
    ("Gymnopédie No.1", "1.72"),
    ("Focus Flow", "1.00"),
    ("Midnight Coding", "0.98"),
    # Impossible: Classical + Euphoric (classical / euphoric / 0.90)
    ("Gymnopédie No.1", "2.22"),
    ("Storm Runner", "0.99"),
    ("Gym Hero", "0.97"),
    ("Piscina spedup", "0.95"),
    ("火炎", "0.95"),
]


def run_cli() -> str:
    """Run the real CLI with UTF-8 forced, so Chinese/Japanese titles survive."""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "src.main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_cli_reproduces_the_documented_baseline():
    pairs = []
    for line in run_cli().splitlines():
        match = LINE.match(line)
        if match:
            pairs.append((match["title"], match["score"]))

    assert len(pairs) == 25  # 5 profiles x top 5
    assert pairs == EXPECTED
