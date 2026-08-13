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
from .models import TimelineEntry
from .pipeline import build_timeline, lyric_lines
from .report import band_counts, render_qa_report
from .serializer import validate_timeline, write_timeline

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
@click.argument("song_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
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
    """Extract a candidate timeline from AUDIO for the song in SONG_JSON.

    Writes asr-words.jsonl, <song>-timeline.json, and <song>-qa-report.md
    into the staging directory. Never writes to the song JSON — review the
    QA report, then apply with `timeline-extractor promote`.

    Timeline times are only meaningful relative to the audio you feed in:
    for Video-mode songs extract the audio from the linked animation video
    (ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav); for Auto-mode
    songs use the master recording.
    """
    song = json.loads(song_json.read_text(encoding="utf-8"))
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

    stem = song_json.stem
    timeline_out = staging_dir / f"{stem}-timeline.json"
    report_out = staging_dir / f"{stem}-qa-report.md"
    write_timeline(entries, timeline_out)

    report = render_qa_report(
        anchors=anchors,
        lines=lines,
        line_entries=entries,
        song_title=song.get("title", stem),
        song_path=song_json,
        audio_path=audio,
        model_size=model_size,
        lang=lang,
        staging_dir=staging_dir,
    )
    report_out.write_text(report, encoding="utf-8")

    counts = band_counts(anchors)
    click.echo(
        f"HIGH {counts['HIGH']} / REVIEW {counts['REVIEW']} / FAIL {counts['FAIL']} "
        f"— timeline: {timeline_out} — report: {report_out} — words: {words_out}"
    )


def _load_promotable_timeline(timeline_json: Path) -> list[dict]:
    """Load and contract-validate a `{"timeline": [...]}` file. Returns the
    raw entry dicts; raises ClickException on any shape/type violation."""
    try:
        data = json.loads(timeline_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"{timeline_json}: not valid JSON ({exc})")
    if not isinstance(data, dict) or not isinstance(data.get("timeline"), list):
        raise click.ClickException(
            f'{timeline_json}: expected an object with a "timeline" array'
        )
    raw_entries = data["timeline"]
    entries: list[TimelineEntry] = []
    for i, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            raise click.ClickException(f"timeline[{i}]: must be an object")
        start, end = item.get("start"), item.get("end")
        for name, value in (("start", start), ("end", end)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise click.ClickException(
                    f"timeline[{i}]: {name} must be a number, got {value!r}"
                )
        try:
            entries.append(TimelineEntry(start=float(start), end=float(end)))
        except ValueError as exc:
            raise click.ClickException(f"timeline[{i}]: {exc}")
    try:
        validate_timeline(entries)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    return [{"start": e.start, "end": e.end} for e in entries]


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
    """Write the timeline from TIMELINE_JSON into SONG_JSON's `timeline` field.

    Validates the timeline against the output contract and the song's item
    count, backs the song file up next to itself, and replaces only the
    `timeline` key — every other key is preserved untouched, in order.
    """
    new_timeline = _load_promotable_timeline(timeline_json)

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
    song["timeline"] = new_timeline
    song_json.write_text(
        json.dumps(song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    click.echo(f"backup: {backup}")
    for line in _timeline_diff(old_timeline, new_timeline):
        click.echo(line)
