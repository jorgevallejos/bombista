"""Promoting a candidate timeline into a song JSON.

The whole of `promote`'s behaviour, minus the Click decorators: load the
candidate, pull the v2 envelope out of it, run B4's lines-hash guard,
refuse a partial candidate over a complete target, merge via
`writers.merge_envelope` (THE one merge path), back the song up and
replace it.

**Why this is a module and not a CLI command body** (B20 §2): `serve`'s
emit page must promote exactly what `promote` promotes. Two
implementations of this flow would drift, and the guard that stopped
firing would not announce itself — B4 exists because silent positional
misalignment is the failure class this tool is built against. So there
is one flow, and both front ends call it.

Nothing here imports click, prints, or reads `sys.argv`. Refusals raise
`ValueError` carrying the message verbatim — including the file path it
is about, because only the caller's error rendering differs between a
terminal and an HTTP response, never the reason.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .pipeline import lyric_lines
from .provenance import compute_lines_hash
from .readers import song_completeness
from .serializer import validate_v2_envelope
from .songfile import back_up_and_replace, timeline_diff
from .writers import ENVELOPE_KEYS, merge_envelope

__all__ = [
    "PromotionOutcome",
    "promote_candidate",
    "load_candidate",
    "extract_envelope",
    "find_candidate_lines_hash",
    "lines_hash_mismatch_warning",
    "lines_hash_unavailable_note",
    "FALLBACK_LANG",
]

FALLBACK_LANG = "es"
"""B4's linesHash guard needs the `lang` a candidate was extracted with to
recompute the target song's hash the same way. Both carriers record it
(`_bombista.source.lang` on a songjson, `source.lang` on a sibling rich
JSON) — this is only the documented fallback for when that's absent,
matching `align --lang`'s own default."""


@dataclass(frozen=True)
class PromotionOutcome:
    """What a successful promotion did: where the old song was saved, and
    the per-line description of what changed. Both are for the caller to
    render — `promote` echoes them to stdout, an HTTP handler would put
    them in a response body."""

    backup: Path
    diff: list[str]


def load_candidate(timeline_json: Path) -> dict:
    """Load *timeline_json* as JSON, no shape assumptions yet — the caller
    picks the envelope keys back out with `extract_envelope`, which works
    identically whether this file is a bare v2 envelope or a full
    `--emit songjson` output (envelope keys plus everything else)."""
    try:
        data = json.loads(timeline_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{timeline_json}: not valid JSON ({exc})")
    if not isinstance(data, dict):
        raise ValueError(f"{timeline_json}: candidate must be a JSON object")
    return data


def extract_envelope(timeline_json: Path, data: dict) -> dict:
    """Pull `{timelineVersion, leadIn, timeline}` out of *data* and
    contract-validate the result (docs/timeline-v2-contract.md). Works
    whether *data* IS a bare v2 envelope already, or a full song JSON (an
    `--emit songjson` output) that carries those three keys plus everything
    else — extra keys on *data* are simply not part of the extracted
    envelope, so both shapes validate identically. Raises ValueError —
    naming the problem, never coercing — on any shape/type/version
    violation, including a v1 candidate (missing or non-2
    `timelineVersion`)."""
    envelope = {k: data.get(k) for k in ENVELOPE_KEYS}
    try:
        validate_v2_envelope(envelope)
    except ValueError as exc:
        raise ValueError(f"{timeline_json}: {exc}")
    return envelope


def find_candidate_lines_hash(timeline_json: Path, data: dict) -> tuple[str | None, str | None]:
    """Locate a `linesHash` to check the promotion candidate against (B4),
    and the `lang` it was computed with, by naming convention:

    1. If *data* is an emitted `--emit songjson` (carries `_bombista`),
       read `_bombista.linesHash` and `_bombista.source.lang`.
    2. Otherwise *data* is a bare v2 envelope, which cannot carry a hash
       (the contract freezes it at three keys) — look for the sibling rich
       JSON `--emit report-json` would have written next to it:
       `<stem>-timeline.json` -> `<stem>-report.json` in the same
       directory. Read its `linesHash` / `source.lang` if it exists.

    Returns `(None, None)` if neither carrier is found or usable — the
    caller prints a "could not be checked" note rather than skipping
    quietly (this tool's whole philosophy, see module docstrings)."""
    bombista = data.get("_bombista")
    if isinstance(bombista, dict):
        lines_hash = bombista.get("linesHash")
        if isinstance(lines_hash, str):
            source = bombista.get("source")
            lang = source.get("lang") if isinstance(source, dict) else None
            return lines_hash, lang

    suffix = "-timeline.json"
    if timeline_json.name.endswith(suffix):
        sibling = timeline_json.with_name(timeline_json.name[: -len(suffix)] + "-report.json")
        if sibling.exists():
            try:
                report_data = json.loads(sibling.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None, None
            if isinstance(report_data, dict):
                lines_hash = report_data.get("linesHash")
                if isinstance(lines_hash, str):
                    source = report_data.get("source")
                    lang = source.get("lang") if isinstance(source, dict) else None
                    return lines_hash, lang

    return None, None


def lines_hash_mismatch_warning(candidate_hash: str, target_hash: str) -> str:
    return (
        "WARNING: this timeline's linesHash does not match the target "
        "song's current lyrics.\n"
        f"    recorded (at extraction time): {candidate_hash}\n"
        f"    song's lyrics right now:        {target_hash}\n"
        "The lyrics changed since this timeline was extracted — a line was "
        "likely inserted, deleted, or reordered. Because the timeline is "
        "matched to lyrics BY POSITION, every entry from the changed line "
        "onward may now be pointing at the wrong lyric line.\n"
        "Promoting anyway. To fix it: re-run `bombista align` "
        "against the current lyrics and promote the new candidate instead."
    )


def lines_hash_unavailable_note(timeline_json: Path) -> str:
    suffix = "-timeline.json"
    if timeline_json.name.endswith(suffix):
        sibling_name = timeline_json.name[: -len(suffix)] + "-report.json"
        hint = f"no sibling {sibling_name} was found next to it"
    else:
        hint = f"{timeline_json.name} doesn't follow the <stem>-timeline.json naming convention"
    return (
        "note: linesHash guard could not be checked — the candidate carries "
        f"no linesHash and {hint}. Re-run extract with --emit report-json "
        "or --emit songjson to enable this guard next time."
    )


def promote_candidate(
    timeline_json: Path,
    song_json: Path,
    *,
    note: Callable[[str], None] | None = None,
) -> PromotionOutcome:
    """Write the timeline v2 envelope from *timeline_json* into *song_json*.

    Raises ValueError, without touching the song file, on every refusal:
    an unreadable or misshapen candidate, a v1 candidate, a lyrics count
    that does not match, a partial candidate over a complete target, or a
    partial envelope. Returns the backup path and the per-line diff on
    success.

    *note* receives B4's non-fatal remarks — the guard's mismatch warning
    and its two "could not be checked" notes. It is a callback rather than
    a returned list on purpose: a refusal can follow a note, and the note
    has to have been delivered by the time the exception is raised.
    Warnings that only arrive when nothing goes wrong are not warnings.
    """
    emit = note if note is not None else lambda _message: None

    data = load_candidate(timeline_json)
    envelope = extract_envelope(timeline_json, data)
    new_timeline = envelope["timeline"]

    song = json.loads(song_json.read_text(encoding="utf-8"))
    items = song.get("lyrics")
    if not isinstance(items, list):
        raise ValueError(f'{song_json}: song JSON has no "lyrics" list')
    if len(new_timeline) != len(items):
        raise ValueError(
            f"timeline length ({len(new_timeline)}) must match the song's "
            f"lyrics item count ({len(items)}) — refusing to promote"
        )

    # B4 — positional-fragility guard: warn (never block) if the target
    # song's lyrics changed since this candidate was extracted.
    candidate_lines_hash, candidate_lang = find_candidate_lines_hash(timeline_json, data)
    if candidate_lines_hash is None:
        emit(lines_hash_unavailable_note(timeline_json))
    else:
        try:
            target_lines = lyric_lines(items, candidate_lang or FALLBACK_LANG)
        except ValueError as exc:
            # Can't recompute the hash, so the guard can't run — say so
            # rather than let it look like a clean check.
            target_lines = None
            emit(f"note: linesHash guard could not be checked — {exc}")
        if target_lines is not None:
            target_lines_hash = compute_lines_hash(target_lines)
            if target_lines_hash != candidate_lines_hash:
                emit(lines_hash_mismatch_warning(candidate_lines_hash, target_lines_hash))

    carries_more_than_envelope = set(data.keys()) - set(ENVELOPE_KEYS)
    if carries_more_than_envelope:
        candidate_completeness = song_completeness(data)
        target_completeness = song_completeness(song)
        if target_completeness == "complete" and candidate_completeness == "partial":
            raise ValueError(
                f"{song_json}: refusing to promote — the target song is "
                "complete (it already carries CP fields a plain-text "
                f"extraction can't infer), but the candidate ({timeline_json}) "
                "is partial (no _bombista.completeness \"complete\", and none "
                "of those fields either). Promoting it would risk silently "
                "narrowing a complete song's timeline to a thinner source. "
                "Re-run extract against the complete song JSON, or promote a "
                "bare timeline envelope instead."
            )

    old_timeline = song.get("timeline")
    # Merge before touching the disk: an incomplete envelope must raise here,
    # with the song file still untouched, rather than after the backup.
    try:
        song = merge_envelope(song, envelope)
    except ValueError as exc:
        raise ValueError(f"{timeline_json}: {exc}")

    backup = back_up_and_replace(song_json, song)

    return PromotionOutcome(backup=backup, diff=timeline_diff(old_timeline, new_timeline))
