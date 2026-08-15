"""
Full-file ASR transcription with word timestamps — the aligner stage.

Ports the proven machinery from the translator's ASR spike
(`spike/asr_bench/scripts/run_forced_align_reference.py` on branch
`spike/asr-following`): faster-whisper batch-transcribes the whole audio
file with `word_timestamps=True`, producing a `Word` per recognized token
in the audio's own clock. This is the "reference" full-file pass (not a
streaming/real-time candidate).

`save_words` / `load_words` round-trip a `list[Word]` to JSONL so the CLI
can cache a transcription run (a `medium`-model pass over a full song is
tens of seconds) instead of re-running the model on every invocation.

`save_words` also files a sibling `asr-words.meta.json` — the facts the
word stream cannot state about itself (B20 §11.10, §11.11). The JSONL is
bare `{"text","start","end"}` records with no header, and adding one
would break every reader, so *when* the machine listened, *which* model
heard it and *where* the take actually is go in a file beside it. A file
rather than an mtime, because an mtime does not survive the staging
directory being copied. This module builds neither dict: it writes what
it is handed and reads it back, so `provenance.py` stays the one place
that decides what a run recorded.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Sequence

from .models import Word

DEVICE = "cpu"
COMPUTE_TYPE = "int8"
DEVICE_STRING = f"{DEVICE}/{COMPUTE_TYPE}"
"""Single source of truth for the device faster-whisper runs on. Also
imported by provenance.py so the recorded provenance can never drift from
what transcribe_words actually passes to WhisperModel."""


def transcribe_words(
    audio_path: Path,
    *,
    model_size: str = "medium",
    language: str = "es",
) -> list[Word]:
    """Transcribe *audio_path* end-to-end and return recognized words with timestamps."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=DEVICE, compute_type=COMPUTE_TYPE)
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        condition_on_previous_text=True,
    )
    raw_words = itertools.chain.from_iterable(segment.words for segment in segments)
    return [
        Word(text=w.word.strip(), start=round(w.start, 3), end=round(w.end, 3))
        for w in raw_words
    ]


WORDS_META_FILENAME = "asr-words.meta.json"
"""The sibling `save_words` files beside the stream. Named for the stream
rather than for the song, because it describes the transcription and
travels with it — copy the one and the other comes along."""


def words_meta_path(words_path: Path) -> Path:
    """The sibling that belongs to *words_path*."""
    return Path(words_path).with_name(WORDS_META_FILENAME)


def save_words(words: Sequence[Word], path: Path, *, meta: dict | None = None) -> None:
    """Write *words* to *path* as JSONL, one `{"text", "start", "end"}` object per line.

    *meta*, when given, is written verbatim to the sibling
    `asr-words.meta.json` — `provenance.words_meta` builds it. Omitted, no
    sibling is written: a stream saved with nothing to say about itself
    should not leave a file claiming otherwise.
    """
    lines = (
        json.dumps({"text": w.text, "start": w.start, "end": w.end}, ensure_ascii=False)
        for w in words
    )
    Path(path).write_text("\n".join(lines) + ("\n" if words else ""), encoding="utf-8")
    if meta is not None:
        save_words_meta(meta, path)


def save_words_meta(meta: dict, words_path: Path) -> None:
    """Write *meta* to the sibling beside *words_path*.

    Separate from `save_words` because `align --words` copies a stream it
    did not transcribe: the words are copied, and the facts about them
    have to travel with the copy or the new staging directory is the
    older-staging-directory case one run later.
    """
    words_meta_path(words_path).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_words_meta(words_path: Path) -> dict | None:
    """The sibling beside *words_path*, or None when there is none to read.

    None covers every way this can fail — no sibling (a staging directory
    written before they existed), unreadable, or not an object — because
    the caller does the same thing in all of them: omit the field rather
    than invent a value. A half-written sibling is not better evidence
    than no sibling.
    """
    path = words_meta_path(words_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_words(path: Path) -> list[Word]:
    """Read a JSONL file written by `save_words` back into a list of `Word`."""
    text = Path(path).read_text(encoding="utf-8")
    words = []
    for line in text.splitlines():
        if not line:
            continue
        data = json.loads(line)
        words.append(Word(text=data["text"], start=data["start"], end=data["end"]))
    return words
