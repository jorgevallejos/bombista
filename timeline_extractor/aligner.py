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
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Sequence

from .models import Word


def transcribe_words(
    audio_path: Path,
    *,
    model_size: str = "medium",
    language: str = "es",
) -> list[Word]:
    """Transcribe *audio_path* end-to-end and return recognized words with timestamps."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
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


def save_words(words: Sequence[Word], path: Path) -> None:
    """Write *words* to *path* as JSONL, one `{"text", "start", "end"}` object per line."""
    lines = (
        json.dumps({"text": w.text, "start": w.start, "end": w.end}, ensure_ascii=False)
        for w in words
    )
    Path(path).write_text("\n".join(lines) + ("\n" if words else ""), encoding="utf-8")


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
