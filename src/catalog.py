"""
Loading and validation for the song catalog (data/songs.csv).

This module is the only place in the project that reads input from disk.
Everything downstream -- scoring, retrieval, the agent -- works on Song objects
that are already known to be well formed, so a malformed CSV fails exactly once,
loudly, with a message that names the file, the line and the column that need
fixing.

Design choice: a bad row is an error, not a warning. Skipping it would silently
shrink the catalog and change recommendations without anyone noticing.
"""

import csv
import math
from pathlib import Path
from typing import Dict, List, Optional

from src.recommender import Song

TEXT_FIELDS = ("title", "artist", "genre", "mood")
UNIT_FIELDS = ("energy", "valence", "danceability", "acousticness")
NUMERIC_FIELDS = UNIT_FIELDS + ("tempo_bpm",)
REQUIRED_COLUMNS = ("id",) + TEXT_FIELDS + NUMERIC_FIELDS

UNIT_MIN = 0.0
UNIT_MAX = 1.0
TEMPO_MIN = 0.0
TEMPO_MAX = 400.0


class CatalogError(ValueError):
    """
    Raised when the catalog file cannot be read as a valid catalog.

    The location of the problem is carried both in the message and in separate
    fields, so tests and tooling can react to `line` / `column` without parsing
    an English sentence.
    """

    def __init__(
        self,
        message: str,
        *,
        path: Optional[str] = None,
        line: Optional[int] = None,
        column: Optional[str] = None,
        value: object = None,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.line = line
        self.column = column
        self.value = value


def load_songs(csv_path) -> List[Song]:
    """
    Load and validate the catalog.

    Accepts a str or a Path. Raises CatalogError on the first problem found.
    """
    path = Path(csv_path)
    if not path.is_file():
        raise CatalogError(f"Catalog file not found: {path}", path=str(path))

    songs: List[Song] = []
    seen_ids: Dict[int, int] = {}  # song id -> line number where it first appeared

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _check_header(reader.fieldnames, path)
        for row in reader:
            song = _parse_row(row, reader.line_num, path)
            if song.id in seen_ids:
                raise CatalogError(
                    f"{path} line {reader.line_num} (id={song.id}): "
                    f"duplicate id {song.id}, already used on line {seen_ids[song.id]}",
                    path=str(path),
                    line=reader.line_num,
                    column="id",
                    value=song.id,
                )
            seen_ids[song.id] = reader.line_num
            songs.append(song)

    if not songs:
        raise CatalogError(f"Catalog is empty: {path}", path=str(path))
    return songs


def _check_header(fieldnames: Optional[List[str]], path: Path) -> None:
    found = fieldnames or []
    missing = [name for name in REQUIRED_COLUMNS if name not in found]
    if missing:
        raise CatalogError(
            f"{path} is missing required column(s): {', '.join(missing)}. "
            f"Columns found: {', '.join(found) if found else '(none)'}",
            path=str(path),
        )


def _parse_row(row: Dict[str, str], line: int, path: Path) -> Song:
    where = f"{path} line {line}"

    song_id = _parse_id(row.get("id"), where, path, line)
    # From here on every message can name the row by id as well as by line.
    where = f"{where} (id={song_id})"

    labels: Dict[str, str] = {}
    for column in TEXT_FIELDS:
        text = _text(row.get(column))
        if not text:
            raise CatalogError(
                f"{where}: column '{column}' is empty",
                path=str(path),
                line=line,
                column=column,
            )
        labels[column] = text

    numbers: Dict[str, float] = {}
    for column in NUMERIC_FIELDS:
        numbers[column] = _number(row.get(column), column, where, path, line)

    for column in UNIT_FIELDS:
        _check_range(numbers[column], column, UNIT_MIN, UNIT_MAX, where, path, line)
    _check_range(
        numbers["tempo_bpm"], "tempo_bpm", TEMPO_MIN, TEMPO_MAX, where, path, line
    )

    return Song(
        id=song_id,
        title=labels["title"],
        artist=labels["artist"],
        genre=labels["genre"],
        mood=labels["mood"],
        energy=numbers["energy"],
        tempo_bpm=numbers["tempo_bpm"],
        valence=numbers["valence"],
        danceability=numbers["danceability"],
        acousticness=numbers["acousticness"],
    )


def _parse_id(raw: Optional[str], where: str, path: Path, line: int) -> int:
    text = _text(raw)
    if not text:
        raise CatalogError(
            f"{where}: column 'id' is empty", path=str(path), line=line, column="id"
        )
    try:
        song_id = int(text)
    except ValueError:
        raise CatalogError(
            f"{where}: column 'id' must be a whole number: '{text}'",
            path=str(path),
            line=line,
            column="id",
            value=text,
        ) from None
    if song_id <= 0:
        raise CatalogError(
            f"{where}: column 'id' must be a positive whole number, got {song_id}",
            path=str(path),
            line=line,
            column="id",
            value=song_id,
        )
    return song_id


def _number(
    raw: Optional[str], column: str, where: str, path: Path, line: int
) -> float:
    text = _text(raw)
    if not text:
        raise CatalogError(
            f"{where}: column '{column}' is empty",
            path=str(path),
            line=line,
            column=column,
        )
    try:
        value = float(text)
    except ValueError:
        raise CatalogError(
            f"{where}: column '{column}' is not a number: '{text}'",
            path=str(path),
            line=line,
            column=column,
            value=text,
        ) from None
    # float("nan") and float("inf") parse happily but poison every later
    # comparison and the sort order, which is painful to debug. Reject them here.
    if not math.isfinite(value):
        raise CatalogError(
            f"{where}: column '{column}' is not a finite number: '{text}'",
            path=str(path),
            line=line,
            column=column,
            value=text,
        )
    return value


def _check_range(
    value: float,
    column: str,
    low: float,
    high: float,
    where: str,
    path: Path,
    line: int,
) -> None:
    if not low <= value <= high:
        raise CatalogError(
            f"{where}: column '{column}' must be between {low} and {high}, got {value}",
            path=str(path),
            line=line,
            column=column,
            value=value,
        )


def _text(raw: Optional[str]) -> str:
    return (raw or "").strip()
