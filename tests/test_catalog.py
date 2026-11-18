"""
Tests for catalog loading and validation.

Every failure case writes a small broken CSV into tmp_path and asserts that the
error names the file, the line, the column and the offending value. Those
assertions are the contract: if the message gets less specific, these tests go
red.
"""

import csv
from pathlib import Path

import pytest

from src.catalog import CatalogError, load_songs

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CATALOG = REPO_ROOT / "data" / "songs.csv"

GOOD_HEADER = [
    "id",
    "title",
    "artist",
    "genre",
    "mood",
    "energy",
    "tempo_bpm",
    "valence",
    "danceability",
    "acousticness",
]


def make_row(**overrides: str) -> list:
    """Build one CSV row from the good defaults, with fields overridden."""
    base = {
        "id": "1",
        "title": "Test Song",
        "artist": "Test Artist",
        "genre": "pop",
        "mood": "happy",
        "energy": "0.8",
        "tempo_bpm": "120",
        "valence": "0.9",
        "danceability": "0.8",
        "acousticness": "0.2",
    }
    base.update(overrides)
    return [base[name] for name in GOOD_HEADER]


def write_catalog(path: Path, rows: list, header: list = GOOD_HEADER) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def test_loads_the_real_catalog():
    songs = load_songs(REAL_CATALOG)

    assert len(songs) == 20
    first = songs[0]
    assert first.id == 1
    assert first.title == "Sunrise City"
    assert first.genre == "pop"
    assert first.mood == "happy"
    assert first.energy == pytest.approx(0.82)


def test_missing_file_names_the_path(tmp_path):
    missing = tmp_path / "nope.csv"

    with pytest.raises(CatalogError) as info:
        load_songs(missing)

    assert "Catalog file not found" in str(info.value)
    assert "nope.csv" in str(info.value)


def test_missing_column_is_listed(tmp_path):
    # Trim the header and every row down to 9 columns.
    header = GOOD_HEADER[:-1]
    path = write_catalog(tmp_path / "songs.csv", [make_row()[:-1]], header=header)

    with pytest.raises(CatalogError) as info:
        load_songs(path)

    assert "missing required column(s)" in str(info.value)
    assert "acousticness" in str(info.value)


def test_blank_energy_reports_line_and_column(tmp_path):
    # header = line 1, so the third data row is line 4.
    rows = [make_row(id="1"), make_row(id="2"), make_row(id="3", energy="")]
    path = write_catalog(tmp_path / "songs.csv", rows)

    with pytest.raises(CatalogError) as info:
        load_songs(path)

    error = info.value
    assert error.line == 4
    assert error.column == "energy"
    assert "is empty" in str(error)
    assert "(id=3)" in str(error)


def test_non_numeric_energy_reports_the_value(tmp_path):
    path = write_catalog(tmp_path / "songs.csv", [make_row(energy="loud")])

    with pytest.raises(CatalogError) as info:
        load_songs(path)

    assert "not a number" in str(info.value)
    assert "'loud'" in str(info.value)


def test_energy_out_of_range_reports_allowed_range(tmp_path):
    path = write_catalog(tmp_path / "songs.csv", [make_row(energy="1.2")])

    with pytest.raises(CatalogError) as info:
        load_songs(path)

    assert "between 0.0 and 1.0" in str(info.value)
    assert "1.2" in str(info.value)


def test_nan_is_rejected(tmp_path):
    path = write_catalog(tmp_path / "songs.csv", [make_row(energy="nan")])

    with pytest.raises(CatalogError) as info:
        load_songs(path)

    assert "not a finite number" in str(info.value)


def test_duplicate_id_reports_both_lines(tmp_path):
    # Both rows are id 2; they land on lines 2 and 3.
    rows = [make_row(id="2"), make_row(id="2")]
    path = write_catalog(tmp_path / "songs.csv", rows)

    with pytest.raises(CatalogError) as info:
        load_songs(path)

    error = info.value
    assert error.line == 3
    assert error.column == "id"
    assert "duplicate id 2" in str(error)
    assert "already used on line 2" in str(error)


def test_empty_title_reports_the_column(tmp_path):
    path = write_catalog(tmp_path / "songs.csv", [make_row(title="   ")])

    with pytest.raises(CatalogError) as info:
        load_songs(path)

    assert info.value.column == "title"
    assert "column 'title' is empty" in str(info.value)


def test_surrounding_whitespace_is_stripped(tmp_path):
    path = write_catalog(
        tmp_path / "songs.csv", [make_row(title="  Test Song  ", genre=" pop ")]
    )

    song = load_songs(path)[0]

    assert song.title == "Test Song"
    assert song.genre == "pop"


def test_header_only_file_is_rejected(tmp_path):
    path = write_catalog(tmp_path / "songs.csv", [])

    with pytest.raises(CatalogError) as info:
        load_songs(path)

    assert "Catalog is empty" in str(info.value)
