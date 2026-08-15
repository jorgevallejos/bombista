"""
Tests for the aligner — full-file ASR transcription with word timestamps.

Unit tests cover the JSONL save/load round-trip (no model, no audio).
The integration test runs the real faster-whisper `tiny` model against a
committed 12s audio fixture, to prove the wiring against a real model
without paying for `medium`'s download/runtime cost in the default test
run.

The fixture is **synthesised speech** (macOS `say`, es_ES, reading the
invented lines in FIXTURE_TEXT below), not a real recording — the repo is
public and carries no master audio. Worth knowing what that costs: clean
TTS is easier for Whisper than sung audio over a band, so this test is a
weaker proxy for the real domain than an excerpt of a real song would be.
It is still a *wiring* test — real model, real decode, real word
timestamps — and the recognition assertion below keeps its original
shape: at least 3 transcribed words must match the known text. `tiny`
still mishears several words here, which is what keeps that assertion
from being trivially true.
"""
import json
import re
import shutil
import unicodedata
from pathlib import Path

import pytest

from bombista.aligner import (
    COMPUTE_TYPE,
    DEVICE,
    DEVICE_STRING,
    WORDS_META_FILENAME,
    load_words,
    load_words_meta,
    save_words,
    transcribe_words,
)
from bombista.models import Word


FIXTURE_AUDIO = Path(__file__).parent / "fixtures" / "synthetic-es-12s.wav"

# The invented text the fixture was synthesised from. Regenerate the fixture
# with:
#
#   say -v "Mónica" -r 155 -o tts.aiff "<FIXTURE_TEXT>"
#   ffmpeg -i tts.aiff -af apad -t 12 -ar 16000 -ac 1 -c:a pcm_s16le \
#       tests/fixtures/synthetic-es-12s.wav
#
# `apad -t 12` pins the duration to exactly 12.000 s, which is what
# test_provenance.py's duration assertion reads.
FIXTURE_TEXT = (
    "Camino por la orilla del río dormido. "
    "La luna se derrama sobre el muelle vacío. "
    "El viento me devuelve tu nombre perdido, "
    "mientras cuento las piedras del sendero. "
    "Una lámpara sigue encendida en la ventana del puerto viejo."
)

# Used only to check for *some* overlap with the tiny model's output — not an
# exact-transcription assertion. `tiny` reliably mangles a few of these
# ("muelhe", "cendero", "derra más"), so the overlap floor is a real bar.
EXPECTED_FIXTURE_WORDS = {
    "camino", "por", "la", "orilla", "del", "rio", "dormido",
    "luna", "se", "derrama", "sobre", "el", "muelle", "vacio",
    "viento", "me", "devuelve", "tu", "nombre", "perdido",
    "mientras", "cuento", "las", "piedras", "sendero",
    "una", "lampara", "sigue", "encendida", "en", "ventana",
    "puerto", "viejo",
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _normalize(word: str) -> str:
    word = _strip_accents(word.lower())
    return re.sub(r"[^a-z]", "", word)


def test_device_string_is_built_from_the_module_constants():
    """DEVICE/COMPUTE_TYPE are the single source of truth for the device
    faster-whisper runs on (transcribe_words) — DEVICE_STRING (consumed by
    provenance.py) must never be able to drift from what transcribe_words
    actually passes to WhisperModel."""
    assert DEVICE == "cpu"
    assert COMPUTE_TYPE == "int8"
    assert DEVICE_STRING == f"{DEVICE}/{COMPUTE_TYPE}"
    assert DEVICE_STRING == "cpu/int8"


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


# ---------------------------------------------------------------------------
# the sibling — §11.10, §11.11: what the word stream cannot say about itself
# ---------------------------------------------------------------------------


def test_save_words_writes_no_sibling_when_it_is_given_no_meta(tmp_path):
    """`asr-words.jsonl` is bare word records with no header, and adding
    one would break every reader — so the facts about the run go beside it
    rather than in it. Only when there are facts to file."""
    out = tmp_path / "words.jsonl"

    save_words([Word("uno", 0.0, 0.1)], out)

    assert not (tmp_path / WORDS_META_FILENAME).exists()
    assert load_words_meta(out) is None


def test_save_words_files_the_meta_beside_the_stream_and_reads_it_back(tmp_path):
    out = tmp_path / "words.jsonl"
    meta = {
        "extractedAt": "2026-08-14T20:55:00+02:00",
        "model": "faster-whisper:medium",
        "device": "cpu/int8",
        "lang": "es",
        "sha256": "ab" * 32,
        "audio": "/somewhere/pimiento.m4a",
    }

    save_words([Word("uno", 0.0, 0.1)], out, meta=meta)

    sibling = tmp_path / WORDS_META_FILENAME
    assert sibling.exists()
    assert json.loads(sibling.read_text(encoding="utf-8")) == meta
    assert load_words_meta(out) == meta


def test_the_sibling_survives_the_staging_directory_being_copied(tmp_path):
    """The whole reason it is a file rather than an mtime: an mtime does
    not survive a copy, and a staging directory that is moved must still
    be able to say when the machine listened."""
    first = tmp_path / "one"
    first.mkdir()
    save_words([Word("uno", 0.0, 0.1)], first / "words.jsonl", meta={"lang": "es"})

    second = tmp_path / "two"
    shutil.copytree(first, second)

    assert load_words_meta(second / "words.jsonl") == {"lang": "es"}


def test_load_words_meta_returns_none_for_an_unreadable_sibling(tmp_path):
    """An older staging directory can hold anything. A half-written or
    hand-edited sibling is answered the same way a missing one is — the
    caller omits the field rather than inventing a value from rubble."""
    out = tmp_path / "words.jsonl"
    save_words([Word("uno", 0.0, 0.1)], out)
    (tmp_path / WORDS_META_FILENAME).write_text("{not json", encoding="utf-8")

    assert load_words_meta(out) is None


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
    overlap = normalized & EXPECTED_FIXTURE_WORDS
    assert len(overlap) >= 3, (
        f"expected at least 3 recognized words to overlap with the fixture "
        f"text, got {sorted(overlap)} from transcription {[w.text for w in words]}"
    )
