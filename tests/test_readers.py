"""
Tests for the input normaliser — B5 (docs/bombista-product-backlog.md §2,
§4). `read_lyrics_input` sits at the boundary: it detects whether the
second `extract` argument is a CP song JSON or a plain lyrics text file,
and converts either into a `NormalisedInput` (CP-shaped `song` dict +
`_bombista` metadata) *before* the existing pipeline runs. Structural
only — no network, no LLM; stdlib only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from timeline_extractor.readers import (
    MISSING_CP_FIELDS,
    NormalisedInput,
    read_lyrics_input,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIBERTAD_TXT = FIXTURES / "libertad-lines.txt"
LIBERTAD_ES_LINES = FIXTURES / "libertad-es-lines.json"


def _expected_es_lines() -> list[str]:
    return json.loads(LIBERTAD_ES_LINES.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Plain-text path
# ---------------------------------------------------------------------------


def test_plain_text_lines_match_committed_libertad_fixture_exactly_in_order():
    """Acceptance #1: the plain-text Libertad fixture (which also contains
    a blank line and a [Bracketed] line) must produce exactly the 20
    committed es lines, in order, after stripping."""
    result = read_lyrics_input(LIBERTAD_TXT, lang="es")

    assert isinstance(result, NormalisedInput)
    expected = _expected_es_lines()
    assert result.song["lyrics"] == [{"es": text} for text in expected]


def test_plain_text_title_comes_from_filename_stem_verbatim():
    result = read_lyrics_input(LIBERTAD_TXT, lang="es")

    assert result.song["title"] == "libertad-lines"


def test_plain_text_reports_partial_completeness_and_filled_lang():
    result = read_lyrics_input(LIBERTAD_TXT, lang="es")

    assert result.bombista["completeness"] == "partial"
    assert result.bombista["filledLang"] == "es"


def test_plain_text_missing_lists_the_known_cp_fields():
    result = read_lyrics_input(LIBERTAD_TXT, lang="es")

    assert result.bombista["missing"] == list(MISSING_CP_FIELDS)
    assert MISSING_CP_FIELDS == (
        "artist",
        "tempo",
        "media",
        "title_translations",
        "intro",
        "translations",
    )


def test_plain_text_stripped_lines_records_source_line_numbers_texts_reasons():
    """Acceptance #4: strippedLines must carry the original 1-based line
    number in the *source file*, not a post-stripping index."""
    result = read_lyrics_input(LIBERTAD_TXT, lang="es")

    assert result.bombista["strippedLines"] == [
        {"line": 1, "text": "[Intro]", "reason": "bracketed"},
        {"line": 2, "text": "", "reason": "blank"},
        {"line": 12, "text": "", "reason": "blank"},
        {"line": 13, "text": "[Chorus]", "reason": "bracketed"},
    ]


def test_plain_text_default_lang_is_es(tmp_path):
    path = tmp_path / "cancion.txt"
    path.write_text("una línea\notra línea\n", encoding="utf-8")

    result = read_lyrics_input(path)

    assert result.song["lyrics"] == [{"es": "una línea"}, {"es": "otra línea"}]
    assert result.bombista["filledLang"] == "es"


def test_plain_text_respects_custom_lang(tmp_path):
    path = tmp_path / "song.txt"
    path.write_text("hello there\n", encoding="utf-8")

    result = read_lyrics_input(path, lang="en")

    assert result.song["lyrics"] == [{"en": "hello there"}]
    assert result.bombista["filledLang"] == "en"


def test_plain_text_strips_trailing_whitespace_but_not_otherwise_alter_text(tmp_path):
    path = tmp_path / "song.txt"
    path.write_text("  leading kept, trailing gone   \n", encoding="utf-8")

    result = read_lyrics_input(path, lang="es")

    assert result.song["lyrics"] == [{"es": "  leading kept, trailing gone"}]


def test_plain_text_does_not_mutate_song_dict_with_bombista_block():
    """`song` and `bombista` stay separate objects — the CP dict is not
    stuffed with `_bombista` here (that's B2's job)."""
    result = read_lyrics_input(LIBERTAD_TXT, lang="es")

    assert "_bombista" not in result.song


# ---------------------------------------------------------------------------
# CP JSON path
# ---------------------------------------------------------------------------

CP_SONG = {
    "title": "Test Song",
    "artist": "Chango Pepper",
    "lyrics": [
        {"es": "primera línea", "en": "first line"},
        {"es": "segunda línea"},
    ],
    "timeline": [{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 2.0}],
}


def test_cp_song_json_passes_through_unchanged(tmp_path):
    """Acceptance #2: dict equality against the parsed input — byte-faithful
    pass-through."""
    path = tmp_path / "test-song.json"
    path.write_text(json.dumps(CP_SONG, ensure_ascii=False), encoding="utf-8")

    result = read_lyrics_input(path, lang="es")

    assert result.song == CP_SONG
    assert result.bombista["completeness"] == "complete"


def test_cp_song_json_is_the_same_object_shape_not_stuffed_with_bombista(tmp_path):
    path = tmp_path / "test-song.json"
    path.write_text(json.dumps(CP_SONG, ensure_ascii=False), encoding="utf-8")

    result = read_lyrics_input(path, lang="es")

    assert "_bombista" not in result.song


def test_cp_song_json_without_lyrics_list_fails_loudly(tmp_path):
    """Acceptance #3: a malformed song file, not a lyrics text file — must
    fail loudly, not be silently reinterpreted as plain text (which would
    turn `{` into a lyric line)."""
    path = tmp_path / "broken-song.json"
    path.write_text(json.dumps({"title": "No lyrics here"}), encoding="utf-8")

    with pytest.raises(ValueError, match="lyrics"):
        read_lyrics_input(path, lang="es")


def test_cp_song_json_with_non_list_lyrics_fails_loudly(tmp_path):
    path = tmp_path / "broken-song.json"
    path.write_text(json.dumps({"title": "x", "lyrics": "not a list"}), encoding="utf-8")

    with pytest.raises(ValueError, match="lyrics"):
        read_lyrics_input(path, lang="es")
