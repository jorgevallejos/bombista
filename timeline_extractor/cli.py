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
from .provenance import build_provenance
from .readers import read_lyrics_input
from .report import band_counts, render_qa_report
from .serializer import validate_v2_envelope, write_timeline

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
def extract(
    audio: Path,
    song_json: Path,
    staging_dir: Path,
    model_size: str,
    lang: str,
    anchor_opts: tuple[str, ...],
    words_path: Path | None,
) -> None:
    """Extract a candidate timeline from AUDIO for the song in
    SONG_JSON_OR_LYRICS_TXT.

    The lyrics input may be a CP song JSON (passed through unchanged) or
    a plain text file, one lyric line per line (blank lines and
    [Bracketed] lines are stripped and reported, never converted to
    markers) — either way it is normalised to a CP-shaped song dict
    before this pipeline runs (see readers.py).

    Writes asr-words.jsonl, <song>-timeline.json, and <song>-qa-report.md
    into the staging directory. Never writes to the song JSON — review the
    QA report, then apply with `timeline-extractor promote`.

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
    timeline_out = staging_dir / f"{stem}-timeline.json"
    report_out = staging_dir / f"{stem}-qa-report.md"
    write_timeline(lead_in, normalized_entries, song, timeline_out)

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

    counts = band_counts(anchors)
    click.echo(
        f"HIGH {counts['HIGH']} / REVIEW {counts['REVIEW']} / FAIL {counts['FAIL']} "
        f"— timeline: {timeline_out} — report: {report_out} — words: {words_out}"
    )


def _load_promotable_envelope(timeline_json: Path) -> dict:
    """Load and contract-validate a timeline v2 envelope file (see
    docs/timeline-v2-contract.md). Raises ClickException — naming the
    problem, never coercing — on any shape/type/version violation,
    including a v1 candidate (missing or non-2 `timelineVersion`)."""
    try:
        data = json.loads(timeline_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"{timeline_json}: not valid JSON ({exc})")
    try:
        validate_v2_envelope(data)
    except ValueError as exc:
        raise click.ClickException(f"{timeline_json}: {exc}")
    return data


def _apply_envelope(song: dict, envelope: dict) -> dict:
    """Return a copy of *song* with `timelineVersion`, `leadIn` and
    `timeline` set from *envelope*, in that order, replacing any existing
    occurrence of those keys in place (or appending them at the end if none
    existed) — every other key is preserved untouched and in order."""
    new_keys = ("timelineVersion", "leadIn", "timeline")
    new_song: dict = {}
    inserted = False
    for key, value in song.items():
        if key in new_keys:
            if not inserted:
                for k in new_keys:
                    new_song[k] = envelope[k]
                inserted = True
            continue
        new_song[key] = value
    if not inserted:
        for k in new_keys:
            new_song[k] = envelope[k]
    return new_song


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

    Validates the envelope against the timeline v2 contract (rejecting a
    v1 candidate loudly) and the song's item count, backs the song file up
    next to itself, and writes `timelineVersion`, `leadIn` and `timeline`
    — every other key is preserved untouched, in order.
    """
    envelope = _load_promotable_envelope(timeline_json)
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

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = song_json.with_name(f"{song_json.name}.backup-{stamp}")
    shutil.copyfile(song_json, backup)

    old_timeline = song.get("timeline")
    song = _apply_envelope(song, envelope)
    song_json.write_text(
        json.dumps(song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    click.echo(f"backup: {backup}")
    for line in _timeline_diff(old_timeline, new_timeline):
        click.echo(line)
