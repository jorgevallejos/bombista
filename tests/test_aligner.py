"""
Tests for the aligner — full-file ASR transcription with word timestamps.

Unit tests cover the JSONL save/load round-trip (no model, no audio).
The integration test runs the real faster-whisper `tiny` model against a
committed 12s audio fixture cut from the Tragedia master recording, to
prove the wiring against a real model without paying for `medium`'s
download/runtime cost in the default test run.
"""
import json
import re
import unicodedata
from pathlib import Path

import pytest

from timeline_extractor.aligner import load_words, save_words, transcribe_words
from timeline_extractor.models import Word


FIXTURE_AUDIO = Path(__file__).parent / "fixtures" / "tragedia-opening-12s.wav"

# First lines of the sung lyric, used only to check for *some* overlap with
# the tiny model's output — not an exact-transcription assertion.
EXPECTED_OPENING_WORDS = {
    "me", "acuestan", "en", "la", "cama", "de", "plata", "brillante",
    "me", "ungen", "con", "hierbas", "manteca", "ajo", "y", "sal",
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _normalize(word: str) -> str:
    word = _strip_accents(word.lower())
    return re.sub(r"[^a-z]", "", word)


def test_round_trip_preserves_words(tmp_path):
    words = [
        Word(text="me", start=0.0, end=0.2),
        Word(text="acuestan", start=0.2, end=0.8),
        Word(text="cama", start=1.0, end=1.4),
    ]
    out = tmp_path / "words.jsonl"

    save_words(words, out)
    loaded = load_words(out)

    assert loaded == words


def test_round_trip_preserves_unicode_accents(tmp_path):
    words = [
        Word(text="canción", start=0.0, end=0.5),
        Word(text="ungüento", start=0.5, end=1.0),
        Word(text="ajo", start=1.0, end=1.2),
    ]
    out = tmp_path / "words.jsonl"

    save_words(words, out)
    loaded = load_words(out)

    assert loaded == words
    assert loaded[0].text == "canción"
    assert loaded[1].text == "ungüento"


def test_round_trip_handles_empty_list(tmp_path):
    out = tmp_path / "empty.jsonl"

    save_words([], out)
    loaded = load_words(out)

    assert loaded == []


def test_save_words_writes_one_json_object_per_line(tmp_path):
    words = [
        Word(text="uno", start=0.0, end=0.1),
        Word(text="dos", start=0.1, end=0.2),
    ]
    out = tmp_path / "words.jsonl"

    save_words(words, out)

    lines = out.read_text(encoding="utf-8").strip("\n").split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first == {"text": "uno", "start": 0.0, "end": 0.1}


@pytest.mark.integration
def test_transcribe_words_on_fixture_with_tiny_model():
    assert FIXTURE_AUDIO.exists(), f"missing fixture: {FIXTURE_AUDIO}"

    words = transcribe_words(FIXTURE_AUDIO, model_size="tiny", language="es")

    assert len(words) > 0

    for w in words:
        assert w.start >= 0.0
        assert w.end >= 0.0
        assert w.start <= w.end
        assert w.end <= 13.0  # fixture is 12s; allow a little slack

    starts = [w.start for w in words]
    # allow tiny jitter in ordering but expect overall non-decreasing starts
    out_of_order = sum(1 for a, b in zip(starts, starts[1:]) if b < a - 0.05)
    assert out_of_order == 0

    normalized = {_normalize(w.text) for w in words}
    overlap = normalized & EXPECTED_OPENING_WORDS
    assert len(overlap) >= 3, (
        f"expected at least 3 recognized words to overlap with the opening "
        f"lyric, got {sorted(overlap)} from transcription {[w.text for w in words]}"
    )
