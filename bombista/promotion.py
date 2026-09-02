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
    "canonical_target_for",
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

    backup: Path | None
    """None when the song was created rather than replaced — there was
    nothing to back up, and naming a path for a file that never existed
    would be a lie in the caller's output."""

    diff: list[str]


CANDIDATE_SUFFIX = "-song.json"
"""What `align --emit songjson` names its output: `<stem>-song.json`."""


def canonical_target_for(timeline_json: Path) -> str | None:
    """The one filename a candidate may be **created** as.

    Two candidates are accepted, and both answer the same question:

    - `<stem>-song.json`, what `align --emit songjson` writes, may be
      created as `<stem>.json`.
    - `<stem>.json`, what `/api/emit` and page 3's `Save to the
      catalogue` write, may be created as `<stem>.json` — **its own
      name**, which is already the canonical one.

    None for anything else.

    **A song's id IS its filename**, in this catalogue and in Pregonero's
    library alike, so a free choice of target name when creating is a free
    choice of id — and that is a decision this suite removes rather than
    explains (`bombista`'s output always lands under the canonical name
    and the user never picks a path). The second case is not a loosening
    of that: `libertad.json` may still only ever become `libertad.json`,
    and the id still comes from the candidate rather than from whoever is
    calling. Replacing an existing song is unaffected: the name is already
    settled, and this never runs.

    **Why the second case exists** (2026-09-02, journey-setup step 6). The
    song flow ends at `Save to the catalogue`, which emits a NEW file
    beside `align`'s output — never over it, invariant 6 — and that file
    is what carries page 2's refinements. Promoting `align`'s
    `<stem>-song.json` instead would silently merge the unreviewed
    timeline, which is the failure this whole round removes. So the file
    the flow ends on has to be promotable, and until now it was refused
    for not being named like the file it deliberately is not.
    """
    name = timeline_json.name
    if name.endswith(CANDIDATE_SUFFIX):
        return name[: -len(CANDIDATE_SUFFIX)] + ".json"
    if name.endswith(".json"):
        return name
    return None


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

    creating = not song_json.exists()
    if creating:
        song = _song_to_create(timeline_json, song_json, data)
    else:
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
    #
    # **It cannot run when the song is being created, and saying nothing would be
    # worse than saying that.** The guard asks whether the TARGET's lyrics moved on
    # since extraction; a song that did not exist has no such history, and the
    # target's lyrics are the candidate's own by construction. Left in, it prints
    # "the lyrics changed since this timeline was extracted" about a song that has
    # never been edited — a sentence that is not true and that sends the reader to
    # re-run `align` for no reason.
    if creating:
        emit(
            "note: linesHash guard does not apply — this song is being created, so "
            "there are no earlier lyrics for its timeline to have drifted from."
        )
    else:
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
    # Nothing to be narrower than when the song is being created, so the
    # completeness refusal has no target to protect and does not run.
    if carries_more_than_envelope and not creating:
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

    # **A created song had no timeline, whatever the candidate carries.** `song` IS
    # the candidate on this path, so reading its `timeline` here would compare the
    # new timeline against itself and report "no changes" about a song that has just
    # been given one.
    old_timeline = None if creating else song.get("timeline")
    # Merge before touching the disk: an incomplete envelope must raise here,
    # with the song file still untouched, rather than after the backup. When
    # creating, the candidate already carries the envelope and merging it into
    # itself is the same operation — it is run either way so the contract check
    # inside it fires on both paths.
    try:
        song = merge_envelope(song, envelope)
    except ValueError as exc:
        raise ValueError(f"{timeline_json}: {exc}")

    backup = back_up_and_replace(song_json, song)

    return PromotionOutcome(backup=backup, diff=timeline_diff(old_timeline, new_timeline))


def _song_to_create(timeline_json: Path, song_json: Path, data: dict) -> dict:
    """The song to write when *song_json* does not exist yet.

    **Two refusals, and they are the whole of what makes creating safe.**

    - **The candidate must be a full `--emit songjson`.** A bare v2
      envelope is three keys; there is no song in it to create, and
      merging into a file that is not there is not a thing. This is the
      case the old `click.Path(exists=True)` was really protecting
      against, and it is protected properly now instead of by forbidding
      creation altogether.
    - **The target must be the canonical name for that candidate.** See
      `canonical_target_for`, which accepts `align`'s `<stem>-song.json`
      and the `<stem>.json` an emit wrote — the file the song flow ends
      on, and the only one carrying page 2's refinements.

    The `_bombista` block is dropped. It is provenance about a run, it
    belongs in the staging directory beside the report, and a catalogue
    where created songs carry a key hand-made ones do not is a catalogue
    with two kinds of song file in it.
    """
    if not set(data.keys()) - set(ENVELOPE_KEYS):
        raise ValueError(
            f"{song_json}: does not exist, and {timeline_json} is a bare "
            "timeline envelope — there is no song in it to create. Promote a "
            "full `--emit songjson` candidate to create a song, or point at an "
            "existing song to merge a timeline into."
        )

    canonical = canonical_target_for(timeline_json)
    if canonical is None:
        raise ValueError(
            f"{timeline_json}: to create a song, the candidate must be an "
            f"`--emit songjson` output named `<stem>{CANDIDATE_SUFFIX}`, or the "
            "`<stem>.json` an emit wrote."
        )
    if song_json.name != canonical:
        raise ValueError(
            f"{song_json}: refusing to create — a song's id is its filename, so "
            f"{timeline_json.name} may only be created as `{canonical}`. Rename "
            "the target, or promote into a song that already exists."
        )

    song = {k: v for k, v in data.items() if k != "_bombista"}
    return song
