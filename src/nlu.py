"""
Turning one sentence of English or Chinese into the three values the scorer needs.

The vocabulary is hand-written on purpose. There is no model here: a short table
maps the words a listener actually types ("lo-fi", "低保真", "深夜写代码") onto the
labels the catalog uses ("lofi", "study"). Everything this module decides can be
read off the table, which is what makes it testable.

Three jobs, in order:

1. parse_request   -- text -> genre / mood / context / energy, plus what was
                      excluded ("anything but rock") and what was not understood
2. resolve_request -- fill a missing energy from the knowledge base, using the
                      context document ("study" says 0.25-0.42)
3. clarification   -- when neither a genre nor a mood was recognised, ask a
                      question built from the real catalog values instead of
                      guessing

Explicit user input always wins over knowledge-base defaults. The default is
only ever applied to a slot the listener left empty.
"""

import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

from src.recommender import Song
from src.retrieval import Retriever, content_terms

# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------

GENRE_ALIASES: Dict[str, str] = {
    "lo-fi": "lofi",
    "lofi": "lofi",
    "low fidelity": "lofi",
    "低保真": "lofi",
    "indie pop": "indie pop",
    "独立流行": "indie pop",
    "j-pop": "j-pop",
    "jpop": "j-pop",
    "j pop": "j-pop",
    "日语歌": "j-pop",
    "日系": "j-pop",
    "日本流行": "j-pop",
    "anime rock": "anime rock",
    "动漫摇滚": "anime rock",
    "pop": "pop",
    "流行": "pop",
    "流行歌": "pop",
    "rock": "rock",
    "摇滚": "rock",
    "edm": "edm",
    "电音": "edm",
    "电子": "edm",
    "classical": "classical",
    "古典": "classical",
    "钢琴曲": "classical",
    "piano": "classical",
    "ambient": "ambient",
    "氛围": "ambient",
    "jazz": "jazz",
    "爵士": "jazz",
    "synthwave": "synthwave",
    "合成器": "synthwave",
    "cinematic": "cinematic",
    "电影配乐": "cinematic",
    "dream pop": "dream pop",
    "梦幻流行": "dream pop",
    "r&b": "r&b",
    "rnb": "r&b",
    "mandopop": "mandopop",
    "华语": "mandopop",
    "国语歌": "mandopop",
    "game ost": "game ost",
    "游戏音乐": "game ost",
}

MOOD_ALIASES: Dict[str, str] = {
    "chill": "chill",
    "放松": "chill",
    "轻松": "chill",
    "悠闲": "chill",
    "relaxed": "relaxed",
    "舒缓": "relaxed",
    "focused": "focused",
    "专注": "focused",
    "集中": "focused",
    "intense": "intense",
    "激烈": "intense",
    "强烈": "intense",
    "energetic": "energetic",
    "有活力": "energetic",
    "元气": "energetic",
    "aggressive": "aggressive",
    "暴躁": "aggressive",
    "calm": "calm",
    "平静": "calm",
    "安静": "calm",
    "happy": "happy",
    "开心": "happy",
    "快乐": "happy",
    "dreamy": "dreamy",
    "梦幻": "dreamy",
    "melancholy": "melancholy",
    "忧郁": "melancholy",
    "nostalgic": "nostalgic",
    "怀旧": "nostalgic",
    "passionate": "passionate",
    "热血": "passionate",
    "燃": "passionate",
    "romantic": "romantic",
    "浪漫": "romantic",
    "sad": "sad",
    "伤感": "sad",
    "难过": "sad",
}

CONTEXT_ALIASES: Dict[str, str] = {
    "study": "study",
    "studying": "study",
    "coding": "study",
    "code": "study",
    "late night": "study",
    "reading": "study",
    "深夜": "study",
    "写代码": "study",
    "编程": "study",
    "学习": "study",
    "看书": "study",
    "赶作业": "study",
    "gym": "gym",
    "workout": "gym",
    "running": "gym",
    "training": "gym",
    "健身": "gym",
    "跑步": "gym",
    "运动": "gym",
    "锻炼": "gym",
    "撸铁": "gym",
}

ENERGY_WORDS: Dict[str, float] = {
    "very quiet": 0.15,
    "quiet": 0.25,
    "安静": 0.25,
    "轻声": 0.25,
    "mellow": 0.35,
    "chill": 0.35,
    "放松": 0.35,
    "轻松": 0.35,
    "moderate": 0.50,
    "upbeat": 0.70,
    "欢快": 0.70,
    "energetic": 0.75,
    "有活力": 0.75,
    "loud": 0.85,
    "吵": 0.85,
    "high energy": 0.90,
    "非常吵": 0.92,
    "intense": 0.90,
    "激烈": 0.90,
    "aggressive": 0.92,
    "暴躁": 0.92,
}

NEGATION_MARKERS = (
    "anything but ",
    "other than ",
    "without ",
    "not ",
    "no ",
    "别",
    "不要",
    "不想",
    "除了",
    "不",
)

NEGATION_WINDOW = 16

EXPLICIT_ENERGY = re.compile(
    r"(?:energy|能量)\s*(?:is|was|at|=|:|为)?\s*(0?\.\d+|1(?:\.0+)?|0)"
)
ENERGY_RANGE = re.compile(
    r"between\s+(0?\.\d+|1(?:\.0+)?)\s+and\s+(0?\.\d+|1(?:\.0+)?)", re.IGNORECASE
)
ENERGY_NUMBER = re.compile(r"(?<![\d.])(0?\.\d+|1\.0+)(?![\d.])")


# --------------------------------------------------------------------------
# result types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Slot:
    """One filled field, with a note about where the value came from."""

    value: object
    source: str


@dataclass(frozen=True)
class ParsedRequest:
    """What we understood, what we excluded, and what we did not understand."""

    text: str
    genre: Optional[Slot]
    mood: Optional[Slot]
    context: Optional[Slot]
    energy: Optional[Slot]
    excluded: Tuple[str, ...]
    unknown: Tuple[str, ...]

    @property
    def needs_clarification(self) -> bool:
        """True when there is not even one clue to score against."""
        return self.genre is None and self.mood is None


# --------------------------------------------------------------------------
# matching helpers
# --------------------------------------------------------------------------


def _occurrences(text: str, alias: str) -> List[int]:
    """Where an alias appears. ASCII aliases respect word boundaries."""
    if alias.isascii():
        pattern = re.compile(rf"(?<![a-z0-9-]){re.escape(alias)}(?![a-z0-9-])")
        return [match.start() for match in pattern.finditer(text)]

    positions: List[int] = []
    start = text.find(alias)
    while start != -1:
        positions.append(start)
        start = text.find(alias, start + 1)
    return positions


def _match(text: str, aliases: Dict[str, str]) -> List[Tuple[int, int, str, str]]:
    """
    All alias hits, longest alias first so that "indie pop" beats "pop".

    A span that another alias already claimed is skipped, which is what stops
    "pop" from matching inside "j-pop".
    """
    matches: List[Tuple[int, int, str, str]] = []
    claimed: List[Tuple[int, int]] = []

    for alias in sorted(aliases, key=len, reverse=True):
        for start in _occurrences(text, alias):
            end = start + len(alias)
            if any(start < claimed_end and end > claimed_start for claimed_start, claimed_end in claimed):
                continue
            claimed.append((start, end))
            matches.append((start, end, alias, aliases[alias]))

    matches.sort()
    return matches


def _is_negated(text: str, position: int) -> bool:
    window = text[max(0, position - NEGATION_WINDOW) : position]
    return any(marker in window for marker in NEGATION_MARKERS)


def _resolve_field(
    text: str, aliases: Dict[str, str]
) -> Tuple[Optional[Slot], List[str], List[Tuple[int, int]]]:
    """First non-negated hit wins; negated hits become exclusions."""
    chosen: Optional[Slot] = None
    excluded: List[str] = []
    spans: List[Tuple[int, int]] = []

    for start, end, alias, canonical in _match(text, aliases):
        spans.append((start, end))
        if _is_negated(text, start):
            excluded.append(canonical)
        elif chosen is None:
            chosen = Slot(value=canonical, source=f'text: "{alias}"')

    return chosen, excluded, spans


def _with_catalog_values(base: Dict[str, str], values) -> Dict[str, str]:
    """Catalog labels are searchable verbatim, so new rows need no new alias."""
    merged = dict(base)
    for value in values:
        merged.setdefault(value, value)
    return merged


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def parse_request(text: str, songs: Sequence[Song]) -> ParsedRequest:
    """Read one sentence. Never guesses a genre or mood it cannot see."""
    lowered = text.strip().lower()

    genre_aliases = _with_catalog_values(GENRE_ALIASES, (song.genre for song in songs))
    mood_aliases = _with_catalog_values(MOOD_ALIASES, (song.mood for song in songs))

    genre, excluded_genres, genre_spans = _resolve_field(lowered, genre_aliases)
    mood, excluded_moods, mood_spans = _resolve_field(lowered, mood_aliases)
    context, _, context_spans = _resolve_field(lowered, CONTEXT_ALIASES)

    energy, energy_spans = _read_energy(lowered)

    consumed = genre_spans + mood_spans + context_spans + energy_spans
    unknown = _unknown_terms(lowered, consumed)

    return ParsedRequest(
        text=text,
        genre=genre,
        mood=mood,
        context=context,
        energy=energy,
        excluded=tuple(sorted(set(excluded_genres + excluded_moods))),
        unknown=unknown,
    )


def _read_energy(lowered: str) -> Tuple[Optional[Slot], List[Tuple[int, int]]]:
    """An explicit number beats a word; a word beats a knowledge-base default."""
    explicit = EXPLICIT_ENERGY.search(lowered)
    if explicit:
        value = _clamp(float(explicit.group(1)))
        return Slot(value=value, source=f'text: "{explicit.group(0).strip()}"'), [
            explicit.span()
        ]

    for start, end, alias, canonical in _match(lowered, {k: k for k in ENERGY_WORDS}):
        if _is_negated(lowered, start):
            continue
        return Slot(value=ENERGY_WORDS[canonical], source=f'text: "{alias}"'), [(start, end)]

    return None, []


def _unknown_terms(text: str, consumed: List[Tuple[int, int]]) -> Tuple[str, ...]:
    """Content words that matched nothing: the honest measure of 'I did not get it'."""
    masked = list(text)
    for start, end in consumed:
        for index in range(max(0, start), min(len(masked), end)):
            masked[index] = " "
    leftover = "".join(masked)

    seen: List[str] = []
    for token in content_terms(leftover):
        if token.isdigit() or token in seen:
            continue
        seen.append(token)
    return tuple(seen[:5])


# --------------------------------------------------------------------------
# filling gaps from the knowledge base
# --------------------------------------------------------------------------


def extract_energy_hint(section: str) -> Optional[Tuple[float, str]]:
    """Pull an energy target out of a knowledge-base section."""
    if not section:
        return None

    found_range = ENERGY_RANGE.search(section)
    if found_range:
        low, high = float(found_range.group(1)), float(found_range.group(2))
        return _clamp((low + high) / 2), f"{low:.2f}-{high:.2f}"

    found_number = ENERGY_NUMBER.search(section)
    if found_number:
        return _clamp(float(found_number.group(1))), found_number.group(1)

    return None


def resolve_request(text: str, songs: Sequence[Song], retriever: Retriever) -> ParsedRequest:
    """
    Parse the sentence, then fill an empty energy slot from the knowledge base.

    The knowledge base never overrides something the listener said. It only
    fills a hole, and the source field records where the number came from.

    The number is read from the section named "Energy" of the context document
    the parser picked, not from whichever section happened to rank first: the
    best-matching section is usually about texture or things to avoid, and those
    paragraphs carry no numbers.
    """
    parsed = parse_request(text, songs)
    if parsed.energy is not None or parsed.context is None:
        return parsed

    doc_id = f"context_{parsed.context.value}"
    known = {chunk.doc_id for chunk in retriever.chunks}

    hits = retriever.search(parsed.text, k=3, kind="context")
    if doc_id not in known:
        if not hits:
            return parsed
        doc_id = hits[0].chunk.doc_id

    section = _energy_section(retriever, doc_id)
    if section is None:
        return parsed

    hint = extract_energy_hint(section.text)
    if hint is None:
        return parsed

    value, description = hint
    return replace(
        parsed,
        energy=Slot(value=value, source=f"{section.citation} ({description})"),
    )


def _energy_section(retriever: Retriever, doc_id: str):
    """The section that states the energy range for a context document."""
    for chunk in retriever.chunks:
        if chunk.doc_id == doc_id and chunk.section.strip().lower() == "energy":
            return chunk
    return None


def clarification(parsed: ParsedRequest, songs: Sequence[Song]) -> str:
    """
    Ask for one clue, using values that actually exist in the catalog.

    Ordered by how often each value appears, so the common answers come first:
    alphabetically, "ambient" would lead and "lofi" (the only genre with more
    than one track) would not be shown at all.
    """
    genres = _ranked_values([song.genre for song in songs])
    moods = _ranked_values([song.mood for song in songs])
    genre_list = ", ".join(genres[:6]) + (" ..." if len(genres) > 6 else "")
    mood_list = ", ".join(moods[:6]) + (" ..." if len(moods) > 6 else "")
    return (
        "I need one more clue. Name a genre "
        f"({genre_list}) or a mood ({mood_list}), or a situation like "
        "studying or working out."
    )


def _ranked_values(values: Sequence[str]) -> List[str]:
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)
