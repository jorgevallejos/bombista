"""Writing a song JSON back to disk, and describing what changed.

Both live here because both are shared by every command that writes a
song file — `promote` and `migrate` today, `serve`'s emit page (B20)
tomorrow. They were private helpers in `cli.py` until the B20 step-0
extraction; nothing about them was ever CLI-specific, and a second
implementation of either is the failure mode to avoid: a second backup
path could skip the backup, and a second diff could disagree with the
first about what a run did.

Pure and stdlib-only. Nothing here imports click or prints anything —
`timeline_diff` returns the lines it would print and the caller decides
where they go, which is what lets an HTTP handler reuse it.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

__all__ = ["back_up_and_replace", "timeline_diff"]


def back_up_and_replace(song_json: Path, song: dict) -> Path | None:
    """Copy *song_json* to a timestamped `.backup-<stamp>` sibling (never
    over an existing one — the stamp is the current second), then replace
    the original with *song*, atomically.

    THE one song-write path: `promote` and `migrate` both go through it.
    `timelineVersion`, `leadIn` and `timeline` are written as a unit, so
    an interrupted write must not be able to leave a half-stamped song on
    disk — hence the scratch file and `os.replace`, and the scratch file
    is removed if anything goes wrong. Returns the backup's path, or
    **None when *song_json* did not exist** and there was nothing to back
    up: creating is a real case now, and inventing a backup path for a
    file that never existed would be a lie in the caller's output.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # **Nothing to back up when the song is being created.** `promote` can now land a
    # `--emit songjson` candidate as a song that does not exist yet, which is the only way a
    # song made from a lyrics file and a recording ever reaches the catalogue. The atomic
    # write below is unchanged; only the copy is conditional, and the caller is told there is
    # no backup rather than handed a path that names nothing.
    backup = None
    if song_json.exists():
        backup = song_json.with_name(f"{song_json.name}.backup-{stamp}")
        shutil.copyfile(song_json, backup)
    else:
        song_json.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(song, indent=2, ensure_ascii=False) + "\n"
    temp = song_json.with_name(f"{song_json.name}.tmp-{stamp}")
    try:
        temp.write_text(payload, encoding="utf-8")
        os.replace(temp, song_json)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return backup


def timeline_diff(old: list | None, new: list[dict]) -> list[str]:
    """Human-readable per-line report of what *new* changes about *old*.

    Returns one string per changed line, or a single summary line when
    there is nothing per-line to say (no previous timeline at all, or an
    identical one). Never empty — "no changes" is itself a result worth
    printing, and an empty list would render as silence.
    """
    if not old:
        return [f"timeline added ({len(new)} entries)"]
    lines = []
    for i, entry in enumerate(new):
        previous = old[i] if i < len(old) else None
        if previous != entry:
            was = (
                f"{previous.get('start', '?')}–{previous.get('end', '?')}"
                if isinstance(previous, dict)
                else "(none)"
            )
            lines.append(f"line {i}: {was} -> {entry['start']}–{entry['end']}")
    return lines or ["no changes — new timeline is identical"]
