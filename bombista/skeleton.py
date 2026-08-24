"""`bombista new` — the canonical SP JSON skeleton, and nothing else.

**Why this exists.** A song's life is `bombista new` → an LLM session
writes the words into the skeleton → `bombista align` times it against the
audio → `bombista validate` gates the result. Bombista owns both ends of
the one un-tooled step. Until this module, the first step was folklore: a
file appeared, and that was the whole process — which is precisely why the
pipeline had silent failures at the far end.

**Two absences are load-bearing, and neither is an oversight:**

- **`tempo` is absent, not a placeholder.** A missing tempo is a real
  state and a fake one is a bug that reaches a stage (`songs@c5adf65`).
  `null` is not neutral once a consumer reads it: Pregonero on an absent
  block gives no pulse, no count-in and scale pinned to 1, while a partial
  one NaNs `getBeatsPerBar` — correct scaling, broken pulse, no error
  anywhere.
- **`timeline` and its keys are absent until Bombista writes them.** A
  human starting a song does not write timings; `align` and `promote` do.

Pure and stdlib-only. Nothing here reads audio, and nothing here invents a
value a human is the source of record for.
"""
from __future__ import annotations

import re

__all__ = ["song_skeleton", "title_from_song_id"]

_SEPARATORS = re.compile(r"[-_]+")
_ILLEGAL = ("/", "\\", "\0")


def title_from_song_id(song_id: str) -> str:
    """`hasta-calmar-el-alma` -> `Hasta calmar el alma`.

    A **seed**, not a claim: hyphens and underscores become spaces and the
    first letter is capitalised, which is the Chango Pepper catalogue's own
    convention (`Hasta calmar el alma`, `No te voy a odiar`) and wrong for
    the proper nouns in it (`Don Bonifacio`, `La Pajita`). It is the first
    thing the author edits, and unlike a tempo it is a value a reader can
    see is wrong.
    """
    words = _SEPARATORS.sub(" ", song_id.strip()).strip()
    if not words:
        return ""
    return words[0].upper() + words[1:]


def song_skeleton(song_id: str, *, lang: str = "es", title: str | None = None) -> dict:
    """The skeleton for *song_id*: a legal song file with nothing in it.

    Keys are in the catalogue's order (docs/bombista-serve-spec.md §10.2,
    fixed against `songs/pimiento.json`) — a skeleton in another order
    teaches the wrong one to every file made from it.

    `lyrics` carries one empty entry rather than none, because the entry
    **shape** is the thing the next step gets wrong: a lyric entry is an
    object keyed by language, and flattening it to a string destroys every
    translation on the round trip (§10.2). One empty object says that in
    the only place the author is looking.

    Raises ValueError if *song_id* could not name a file.
    """
    cleaned = song_id.strip()
    if not cleaned or any(bad in cleaned for bad in _ILLEGAL):
        raise ValueError(
            f"{song_id!r}: a song id is a slug that can name a file — "
            "e.g. `hasta-calmar-el-alma`"
        )

    resolved = title if title is not None else title_from_song_id(cleaned)
    return {
        "title": resolved,
        "artist": "",
        "notes": "",
        "title_translations": {lang: resolved},
        "intro": {lang: ""},
        "lyrics": [{lang: ""}],
    }
