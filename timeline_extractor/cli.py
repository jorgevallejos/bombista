"""
timeline-extractor CLI entrypoint — forced-alignment pipeline.

    timeline-extractor extract <audio> <song-json> -o <staging-dir>
    timeline-extractor promote <timeline-json> <song-json>

`extract` transcribes the audio (faster-whisper word timestamps), anchors
each lyric line, and writes a candidate timeline + QA report to a staging
directory. It never writes to the song JSON. `promote` copies an approved
timeline into the song JSON (backup + diff), touching nothing else.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import click

from .aligner import load_words, save_words, transcribe_words
from .anchoring import anchor_lines
from .pipeline import build_timeline, lyric_lines, normalize_to_lead_in
from .provenance import build_provenance, compute_lines_hash
from .readers import read_lyrics_input, song_completeness
from .report import band_counts, render_qa_report
from .serializer import to_dict, validate_v2_envelope, write_timeline
from .writers import (
    build_bombista_block,
    merge_envelope,
    write_lrc,
    write_report_json,
    write_songjson,
    write_srt,
)

_EMIT_CHOICES = ("timeline", "songjson", "report-json", "srt", "lrc")
_ENVELOPE_KEYS = ("timelineVersion", "leadIn", "timeline")

_FALLBACK_LANG = "es"
"""B4's linesHash guard needs the `lang` a candidate was extracted with to
recompute the target song's hash the same way. Both carriers record it
(`_bombista.source.lang` on a songjson, `source.lang` on a sibling rich
JSON) — this is only the documented fallback for when that's absent,
matching `extract --lang`'s own default."""

_EXTRACT_EPILOG = """\
\b
IMPORTANT — pick the right audio:
Timeline times are only meaningful relative to the audio you feed in.
- Video-mode songs: extract the audio from the linked animation video:
    ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav
- Auto-mode songs (no video): use the master recording.
"""


@click.group()
def main() -> None:
    """Derive a lyric timeline from audio via forced alignment."""


def _parse_anchor_overrides(values: tuple[str, ...], line_count: int) -> dict[int, float]:
    overrides: dict[int, float] = {}
    for raw in values:
        line_part, sep, seconds_part = raw.partition("=")
        try:
            if not sep:
                raise ValueError
            line = int(line_part)
            seconds = float(seconds_part)
            if line < 0 or seconds < 0:
                raise ValueError
        except ValueError:
            raise click.BadParameter(
                f"--anchor must be LINE=SECONDS (non-negative), got {raw!r}",
                param_hint="--anchor",
            )
        if line >= line_count:
            raise click.BadParameter(
                f"--anchor line {line} out of range: song has {line_count} "
                f"lyric lines (0..{line_count - 1})",
                param_hint="--anchor",
            )
        overrides[line] = seconds
    return overrides


@main.command(epilog=_EXTRACT_EPILOG)
@click.argument("audio", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument(
    "song_json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    metavar="SONG_JSON_OR_LYRICS_TXT",
)
@click.option(
    "-o",
    "--output",
    "staging_dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Staging directory for the candidate timeline, QA report, and ASR words.",
)
@click.option("--model-size", default="medium", show_default=True, help="faster-whisper model size.")
@click.option("--lang", default="es", show_default=True, help="Language: song-JSON lyric key and ASR language.")
@click.option(
    "--anchor",
    "anchor_opts",
    multiple=True,
    metavar="LINE=SECONDS",
    help="Hand-set a lyric line's onset (repeatable), e.g. --anchor 7=93.4.",
)
@click.option(
    "--words",
    "words_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Reuse a saved asr-words.jsonl and skip transcription (fast re-runs).",
)
@click.option(
    "--emit",
    "emit_targets",
    type=click.Choice(_EMIT_CHOICES),
    multiple=True,
    default=("timeline",),
    show_default=True,
    help=(
        "Output(s) to write into the staging directory (repeatable). "
        "Passing --emit at all REPLACES the default set — it does not add "
        "to it, so `--emit songjson` alone writes only the song JSON, not "
        "timeline.json too. asr-words.jsonl and the QA report are always "
        "written regardless of --emit."
    ),
)
def extract(
    audio: Path,
    song_json: Path,
    staging_dir: Path,
    model_size: str,
    lang: str,
    anchor_opts: tuple[str, ...],
    words_path: Path | None,
    emit_targets: tuple[str, ...],
) -> None:
    """Extract a candidate timeline from AUDIO for the song in
    SONG_JSON_OR_LYRICS_TXT.

    The lyrics input may be a CP song JSON (passed through unchanged) or
    a plain text file, one lyric line per line (blank lines and
    [Bracketed] lines are stripped and reported, never converted to
    markers) — either way it is normalised to a CP-shaped song dict
    before this pipeline runs (see readers.py).

    Writes asr-words.jsonl and <song>-qa-report.md into the staging
    directory unconditionally — those are part of the workflow, not an
    --emit output. --emit (repeatable) picks which of timeline / songjson
    / report-json / srt / lrc also get written there; default is
    `timeline` alone, matching today's behaviour. Never writes to the song
    JSON — review the QA report, then apply with `timeline-extractor
    promote` (accepts either a bare timeline or an emitted songjson).

    Timeline times are only meaningful relative to the audio you feed in:
    for Video-mode songs extract the audio from the linked animation video
    (ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav); for Auto-mode
    songs use the master recording.
    """
    try:
        normalised = read_lyrics_input(song_json, lang=lang)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    song = normalised.song
    stripped_lines = normalised.bombista.get("strippedLines")
    items = song.get("lyrics")
    if not isinstance(items, list):
        raise click.ClickException(f'{song_json}: song JSON has no "lyrics" list')
    try:
        lines = lyric_lines(items, lang)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    if not lines:
        raise click.ClickException(
            f"{song_json}: no lyric lines carry the {lang!r} language key"
        )
    lines_hash = compute_lines_hash(lines)  # B4 — positional-fragility guard
    overrides = _parse_anchor_overrides(anchor_opts, len(lines))

    staging_dir.mkdir(parents=True, exist_ok=True)
    words_out = staging_dir / "asr-words.jsonl"
    if words_path is not None:
        words = load_words(words_path)
        if words_path.resolve() != words_out.resolve():
            shutil.copyfile(words_path, words_out)
    else:
        words = transcribe_words(audio, model_size=model_size, language=lang)
        save_words(words, words_out)

    anchors = anchor_lines(words, lines, overrides=overrides or None)
    try:
        entries = build_timeline(anchors, words, items, lang=lang)
    except ValueError as exc:
        raise click.ClickException(str(exc))

    lead_in, normalized_entries = normalize_to_lead_in(entries)

    # Built once per run, even when --words skips transcription — that's
    # exactly when the audio's sha256 earns its keep (B1).
    provenance = build_provenance(audio, model_size=model_size, lang=lang)

    stem = song_json.stem
    emit_set = set(emit_targets)
    # Built once regardless of which --emit targets are requested: songjson,
    # srt, and lrc all need it, and it's cheap/pure.
    envelope = to_dict(lead_in, normalized_entries, song)

    produced: list[str] = []

    if "timeline" in emit_set:
        timeline_out = staging_dir / f"{stem}-timeline.json"
        write_timeline(lead_in, normalized_entries, song, timeline_out)
        produced.append(f"timeline: {timeline_out}")

    if "songjson" in emit_set:
        bombista = build_bombista_block(normalised.bombista, provenance, lines_hash)
        songjson_out = staging_dir / f"{stem}-song.json"
        write_songjson(song, envelope, bombista, songjson_out)
        produced.append(f"songjson: {songjson_out}")

    if "report-json" in emit_set:
        report_json_out = staging_dir / f"{stem}-report.json"
        write_report_json(
            provenance=provenance,
            lines_hash=lines_hash,
            lead_in_block=envelope["leadIn"],
            anchors=anchors,
            lines=lines,
            line_entries=entries,  # raw audio-clock — see writers.py docstring
            out_path=report_json_out,
        )
        produced.append(f"report-json: {report_json_out}")

    if "srt" in emit_set:
        srt_paths = write_srt(song, envelope, stem, staging_dir)
        produced.append("srt: " + ", ".join(str(p) for p in srt_paths))

    if "lrc" in emit_set:
        lrc_paths = write_lrc(song, envelope, stem, staging_dir)
        produced.append("lrc: " + ", ".join(str(p) for p in lrc_paths))

    report_out = staging_dir / f"{stem}-qa-report.md"
    report = render_qa_report(
        anchors=anchors,
        lines=lines,
        line_entries=entries,  # raw audio-clock times — see report.py docstring
        lead_in=lead_in,
        song_title=song.get("title", stem),
        song_path=song_json,
        audio_path=audio,
        model_size=model_size,
        lang=lang,
        staging_dir=staging_dir,
        provenance=provenance,
        stripped_lines=stripped_lines,
    )
    report_out.write_text(report, encoding="utf-8")
    produced.append(f"report: {report_out}")
    produced.append(f"words: {words_out}")

    counts = band_counts(anchors)
    click.echo(
        f"HIGH {counts['HIGH']} / REVIEW {counts['REVIEW']} / FAIL {counts['FAIL']} "
        "— " + " — ".join(produced)
    )


def _load_promotable_candidate(timeline_json: Path) -> dict:
    """Load *timeline_json* as JSON, no shape assumptions yet — the caller
    (`promote`) picks the envelope keys back out with `_extract_envelope`,
    which works identically whether this file is a bare v2 envelope or a
    full `--emit songjson` output (envelope keys plus everything else)."""
    try:
        data = json.loads(timeline_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"{timeline_json}: not valid JSON ({exc})")
    if not isinstance(data, dict):
        raise click.ClickException(f"{timeline_json}: candidate must be a JSON object")
    return data


def _extract_envelope(timeline_json: Path, data: dict) -> dict:
    """Pull `{timelineVersion, leadIn, timeline}` out of *data* and
    contract-validate the result (docs/timeline-v2-contract.md). Works
    whether *data* IS a bare v2 envelope already, or a full song JSON (an
    `--emit songjson` output) that carries those three keys plus everything
    else — extra keys on *data* are simply not part of the extracted
    envelope, so both shapes validate identically. Raises ClickException —
    naming the problem, never coercing — on any shape/type/version
    violation, including a v1 candidate (missing or non-2
    `timelineVersion`)."""
    envelope = {k: data.get(k) for k in _ENVELOPE_KEYS}
    try:
        validate_v2_envelope(envelope)
    except ValueError as exc:
        raise click.ClickException(f"{timeline_json}: {exc}")
    return envelope


def _find_candidate_lines_hash(timeline_json: Path, data: dict) -> tuple[str | None, str | None]:
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


def _lines_hash_mismatch_warning(candidate_hash: str, target_hash: str) -> str:
    return (
        "WARNING: this timeline's linesHash does not match the target "
        "song's current lyrics.\n"
        f"    recorded (at extraction time): {candidate_hash}\n"
        f"    song's lyrics right now:        {target_hash}\n"
        "The lyrics changed since this timeline was extracted — a line was "
        "likely inserted, deleted, or reordered. Because the timeline is "
        "matched to lyrics BY POSITION, every entry from the changed line "
        "onward may now be pointing at the wrong lyric line.\n"
        "Promoting anyway. To fix it: re-run `timeline-extractor extract` "
        "against the current lyrics and promote the new candidate instead."
    )


def _lines_hash_unavailable_note(timeline_json: Path) -> str:
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


def _timeline_diff(old: list | None, new: list[dict]) -> list[str]:
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


@main.command()
@click.argument("timeline_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("song_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def promote(timeline_json: Path, song_json: Path) -> None:
    """Write the timeline v2 envelope from TIMELINE_JSON into SONG_JSON.

    TIMELINE_JSON may be either a bare timeline v2 envelope (`extract`'s
    default `--emit timeline` output) or a full `--emit songjson` output
    (the envelope plus every other song field and a `_bombista` block) —
    only the envelope keys are read out of it either way. A bare envelope
    carries no completeness information, so no refusal (below) is ever
    possible against one.

    Validates the envelope against the timeline v2 contract (rejecting a
    v1 candidate loudly) and the song's item count, backs the song file up
    next to itself, and writes `timelineVersion`, `leadIn` and `timeline`
    (via `writers.merge_envelope` — the one merge path shared with
    `--emit songjson`) — every other key is preserved untouched, in order.

    Refuses to overwrite a target song whose `readers.song_completeness`
    is `"complete"` with a candidate (only possible when TIMELINE_JSON is
    an emitted songjson) whose own completeness is `"partial"` — promoting
    a thin, plain-text-derived candidate over a song that already has full
    CP data is very likely a mistake, not an upgrade.
    """
    data = _load_promotable_candidate(timeline_json)
    envelope = _extract_envelope(timeline_json, data)
    new_timeline = envelope["timeline"]

    song = json.loads(song_json.read_text(encoding="utf-8"))
    items = song.get("lyrics")
    if not isinstance(items, list):
        raise click.ClickException(f'{song_json}: song JSON has no "lyrics" list')
    if len(new_timeline) != len(items):
        raise click.ClickException(
            f"timeline length ({len(new_timeline)}) must match the song's "
            f"lyrics item count ({len(items)}) — refusing to promote"
        )

    # B4 — positional-fragility guard: warn (never block) if the target
    # song's lyrics changed since this candidate was extracted.
    candidate_lines_hash, candidate_lang = _find_candidate_lines_hash(timeline_json, data)
    if candidate_lines_hash is None:
        click.echo(_lines_hash_unavailable_note(timeline_json), err=True)
    else:
        try:
            target_lines = lyric_lines(items, candidate_lang or _FALLBACK_LANG)
        except ValueError as exc:
            # Can't recompute the hash, so the guard can't run — say so
            # rather than let it look like a clean check.
            target_lines = None
            click.echo(
                f"note: linesHash guard could not be checked — {exc}", err=True
            )
        if target_lines is not None:
            target_lines_hash = compute_lines_hash(target_lines)
            if target_lines_hash != candidate_lines_hash:
                click.echo(
                    _lines_hash_mismatch_warning(candidate_lines_hash, target_lines_hash),
                    err=True,
                )

    carries_more_than_envelope = set(data.keys()) - set(_ENVELOPE_KEYS)
    if carries_more_than_envelope:
        candidate_completeness = song_completeness(data)
        target_completeness = song_completeness(song)
        if target_completeness == "complete" and candidate_completeness == "partial":
            raise click.ClickException(
                f"{song_json}: refusing to promote — the target song is "
                "complete (it already carries CP fields a plain-text "
                f"extraction can't infer), but the candidate ({timeline_json}) "
                "is partial (no _bombista.completeness \"complete\", and none "
                "of those fields either). Promoting it would risk silently "
                "narrowing a complete song's timeline to a thinner source. "
                "Re-run extract against the complete song JSON, or promote a "
                "bare timeline envelope instead."
            )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = song_json.with_name(f"{song_json.name}.backup-{stamp}")
    shutil.copyfile(song_json, backup)

    old_timeline = song.get("timeline")
    song = merge_envelope(song, envelope)
    song_json.write_text(
        json.dumps(song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    click.echo(f"backup: {backup}")
    for line in _timeline_diff(old_timeline, new_timeline):
        click.echo(line)
