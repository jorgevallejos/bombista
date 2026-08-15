"""
Human-QA report for an alignment run — the review surface between
`align` (staging) and `promote` (writes the song JSON).

One markdown file per run: band counts, the audio-clock rule, a
"Needs attention" table for REVIEW/FAIL lines with a one-line
hand-anchoring instruction each, then a table of every lyric line.
"""
from __future__ import annotations

import shlex
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .anchoring import SIGNAL_GLOSSES, LineAnchor
from .models import TimelineEntry

AUDIO_CLOCK_RULE = (
    "Timeline times are only meaningful relative to the audio you feed in. "
    "For Video-mode songs, extract the audio from the linked animation video "
    "(`ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav`); for Auto-mode "
    "songs, use the master recording."
)

MAX_TEXT_CHARS = 50
"""Canonical/ASR text is truncated to about this many characters per cell."""

BANDS = ("HIGH", "REVIEW", "FAIL")


def band_counts(anchors: Sequence[LineAnchor]) -> dict[str, int]:
    counts = {band: 0 for band in BANDS}
    for anchor in anchors:
        counts[anchor.band] = counts.get(anchor.band, 0) + 1
    return counts


def _cell(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Make text safe for a markdown table cell: escape pipes, replace
    newlines with a visible mark, truncate with an ellipsis."""
    flat = text.replace("|", "\\|").replace("\n", " ⏎ ")
    if len(flat) > limit:
        flat = flat[: limit - 1].rstrip() + "…"
    return flat


def _row(anchor: LineAnchor, line: str, entry: TimelineEntry) -> str:
    return (
        f"| {anchor.line_index} | {anchor.band} | {_cell(line)} "
        f"| {_cell(anchor.asr_context)} | {entry.start:.2f} | {entry.end:.2f} "
        f"| {entry.end - entry.start:.2f} | {', '.join(anchor.signals)} |"
    )


_TABLE_HEADER = (
    "| line | band | canonical text | ASR context | start | end | dur | signals |\n"
    "|------|------|----------------|-------------|-------|-----|-----|---------|"
)


def format_duration(duration_sec: float | None) -> str:
    """`durationSec` is null-but-present when the audio container couldn't
    be read (see provenance.py) — render that as an explicit "unknown",
    never a bare Python "None" that reads like a bug."""
    if duration_sec is None:
        return "unknown"
    return f"{duration_sec:.2f} s"


def render_qa_report(
    *,
    anchors: Sequence[LineAnchor],
    lines: Sequence[str],
    line_entries: Sequence[TimelineEntry],
    lead_in: float,
    song_title: str,
    song_path: Path,
    audio_path: Path,
    model_size: str,
    lang: str,
    staging_dir: Path,
    provenance: dict,
    generated_at: datetime | None = None,
    stripped_lines: Sequence[dict] | None = None,
) -> str:
    """Render the QA markdown. `anchors`, `lines` and `line_entries` are
    parallel, one per lyric line. `line_entries` and every time in this
    report are in **raw audio-clock seconds** — the same clock `--anchor
    LINE=SECONDS` overrides are given in — even though the emitted timeline
    (timeline v2) is normalised relative to `lead_in`. That divergence is
    intentional; see `lead_in`.

    `provenance` is the dict built by `provenance.build_provenance` for
    this run — this is the surface a human actually reads, so its audio
    identity (path + sha256), duration, model, device, lang, extractedAt
    and toolVersion are all shown in the header. It is never written into
    the native timeline v2 envelope (serializer.py).

    `stripped_lines` (B5) is the plain-text reader's `_bombista.
    strippedLines` — blank/`[Bracketed]` lines removed from a plain-text
    input before it became lyric lines. When present it's rendered as a
    short "Stripped lines" section so the removal is visible rather than
    silent; the section is omitted entirely when nothing was stripped
    (including the CP-JSON path, which never strips anything)."""
    generated_at = generated_at or datetime.now()
    counts = band_counts(anchors)
    words_path = staging_dir / "asr-words.jsonl"
    # Every path below is shell-quoted (B17). These commands exist to be
    # copied and pasted, and the real invocation lives under `Chango
    # Pepper/` — the audio filenames themselves are space-free by the
    # `songs/audio/<slug>.<ext>` convention, but the vault directory above
    # them is not, so an unquoted path still splits at the prompt. Same
    # defect B16 fixed in the HTML page; see writers.py::_anchor_command.
    quoted_words = shlex.quote(str(words_path))
    rerun = (
        f"bombista align {shlex.quote(str(audio_path))} "
        f"{shlex.quote(str(song_path))} -o {shlex.quote(str(staging_dir))} "
        f"--words {quoted_words} --lang {shlex.quote(lang)}"
    )

    parts = [
        f"# QA report — {song_title}",
        "",
        f"- Song file: `{song_path}`",
        f"- Audio file: `{audio_path}`",
        f"- Audio sha256: `{provenance['sha256']}`",
        f"- Audio duration: {format_duration(provenance['durationSec'])}",
        f"- Model: `{provenance['model']}` (lang `{provenance['lang']}`, "
        f"device `{provenance['device']}`)",
        f"- Extracted at: {provenance['extractedAt']}",
        f"- Tool version: {provenance['toolVersion']}",
        f"- Generated: {generated_at.isoformat(timespec='seconds')}",
        f"- Re-run (skips transcription): `{rerun}`",
        f"- Bands: HIGH {counts['HIGH']} / REVIEW {counts['REVIEW']} / FAIL {counts['FAIL']}",
        f"- Measured lead-in: {lead_in:.2f} s (subtracted from the emitted timeline)",
        "",
        f"> {AUDIO_CLOCK_RULE} All times in this report are raw audio-clock "
        f"seconds (before the {lead_in:.2f} s lead-in is subtracted) — "
        f"`--anchor` overrides are given in this same clock.",
        "",
    ]

    flagged = [a for a in anchors if a.band != "HIGH"]
    parts.append("## Needs attention")
    parts.append("")
    if flagged:
        parts.append(_TABLE_HEADER)
        for anchor in flagged:
            parts.append(_row(anchor, lines[anchor.line_index], line_entries[anchor.line_index]))
        parts.append("")
        for anchor in flagged:
            near = (
                f" (candidate start was {anchor.start:.2f} s)"
                if anchor.start is not None
                else " (no anchor found — listen for the line and time its onset)"
            )
            parts.append(
                f"- Line {anchor.line_index}: re-run `align` with "
                f"`--anchor {anchor.line_index}=<seconds>` and "
                f"`--words {quoted_words}` "
                f"to skip re-transcription{near}."
            )
            # The token above the table says which check fired; this says
            # what it means and where to listen (B20 §8.3). Signals with
            # nothing to say gloss to "" and print nothing — they never
            # reach this list anyway, since neither flags a line.
            for signal in anchor.signals:
                gloss = SIGNAL_GLOSSES.get(signal, "")
                if gloss:
                    parts.append(f"  - `{signal}` — {gloss}")
    else:
        parts.append("None — every line anchored HIGH.")
    parts.append("")

    parts.append("## All lines")
    parts.append("")
    parts.append(_TABLE_HEADER)
    for anchor in anchors:
        parts.append(_row(anchor, lines[anchor.line_index], line_entries[anchor.line_index]))
    parts.append("")

    if stripped_lines:
        parts.append("## Stripped lines")
        parts.append("")
        parts.append("| line | text | reason |")
        parts.append("|------|------|--------|")
        for item in stripped_lines:
            parts.append(
                f"| {item['line']} | {_cell(item['text'])} | {item['reason']} |"
            )
        parts.append("")

    return "\n".join(parts)
