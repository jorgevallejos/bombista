"""
Human-QA report for an extract run — the review surface between
`extract` (staging) and `promote` (writes the song JSON).

One markdown file per run: band counts, the audio-clock rule, a
"Needs attention" table for REVIEW/FAIL lines with a one-line
hand-anchoring instruction each, then a table of every lyric line.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

from .anchoring import LineAnchor
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


def render_qa_report(
    *,
    anchors: Sequence[LineAnchor],
    lines: Sequence[str],
    line_entries: Sequence[TimelineEntry],
    song_title: str,
    song_path: Path,
    audio_path: Path,
    model_size: str,
    lang: str,
    staging_dir: Path,
    generated_at: datetime | None = None,
) -> str:
    """Render the QA markdown. `anchors`, `lines` and `line_entries` are
    parallel, lyric lines only (markers carry no QA content)."""
    generated_at = generated_at or datetime.now()
    counts = band_counts(anchors)
    words_path = staging_dir / "asr-words.jsonl"
    rerun = (
        f"timeline-extractor extract {audio_path} {song_path} -o {staging_dir} "
        f"--words {words_path} --lang {lang}"
    )

    parts = [
        f"# QA report — {song_title}",
        "",
        f"- Song file: `{song_path}`",
        f"- Audio file: `{audio_path}`",
        f"- Model: faster-whisper `{model_size}` (lang `{lang}`)",
        f"- Generated: {generated_at.isoformat(timespec='seconds')}",
        f"- Re-run (skips transcription): `{rerun}`",
        f"- Bands: HIGH {counts['HIGH']} / REVIEW {counts['REVIEW']} / FAIL {counts['FAIL']}",
        "",
        f"> {AUDIO_CLOCK_RULE}",
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
                f"- Line {anchor.line_index}: re-run `extract` with "
                f"`--anchor {anchor.line_index}=<seconds>` and `--words {words_path}` "
                f"to skip re-transcription{near}."
            )
    else:
        parts.append("None — every line anchored HIGH.")
    parts.append("")

    parts.append("## All lines")
    parts.append("")
    parts.append(_TABLE_HEADER)
    for anchor in anchors:
        parts.append(_row(anchor, lines[anchor.line_index], line_entries[anchor.line_index]))
    parts.append("")

    return "\n".join(parts)
