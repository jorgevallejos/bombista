"""
`--emit` writers — B2 (docs/bombista-product-backlog.md §4, §3.5-§3.7).

Every writer here reads the **canonical CP form** produced by `readers.py`
(a CP-shaped song dict, whatever the original input was) plus the timeline
v2 envelope already built by `serializer.to_dict` — none of them touch the
alignment/anchoring machinery.

**Deviation from the backlog note in §4/§6:** the backlog text says
"writers in serializer.py". They live here instead. `serializer.py` owns
the frozen timeline v2 contract envelope (docs/timeline-v2-contract.md)
and nothing else — folding the CP-song/rich-JSON/subtitle writers into it
would blur that boundary for no benefit. `write_timeline` (the envelope
writer) stays in `serializer.py`; everything downstream of the canonical
CP form lives here.

**One merge path only:** `merge_envelope` is the single place that merges
a v2 envelope's `timelineVersion`/`leadIn`/`timeline` into a song dict,
preserving every other key untouched and in order. Both `cli.py::promote`
and `write_songjson` call this same function — there is exactly one merge
implementation in the repo.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from .anchoring import LineAnchor
from .models import TimelineEntry
from .report import band_counts

__all__ = [
    "merge_envelope",
    "build_bombista_block",
    "write_songjson",
    "write_report_json",
    "write_srt",
    "write_lrc",
]

_ENVELOPE_KEYS = ("timelineVersion", "leadIn", "timeline")


def merge_envelope(song: dict, envelope: dict) -> dict:
    """Return a copy of *song* with `timelineVersion`, `leadIn` and
    `timeline` set from *envelope*, in that order, replacing any existing
    occurrence of those keys in place (or appending them at the end if none
    existed) — every other key is preserved untouched and in order.

    This is THE merge path (see module docstring) — do not reimplement it
    elsewhere.
    """
    new_song: dict = {}
    inserted = False
    for key, value in song.items():
        if key in _ENVELOPE_KEYS:
            if not inserted:
                for k in _ENVELOPE_KEYS:
                    new_song[k] = envelope[k]
                inserted = True
            continue
        new_song[key] = value
    if not inserted:
        for k in _ENVELOPE_KEYS:
            new_song[k] = envelope[k]
    return new_song


def build_bombista_block(reader_bombista: dict, provenance: dict, lines_hash: str) -> dict:
    """Combine `readers.py`'s `_bombista` block (`completeness`, and for a
    plain-text input `filledLang`/`missing`/`strippedLines`) with B1's
    provenance dict under a `source` key, plus B4's `linesHash` — the shape
    written into a `songjson` output's `_bombista` block.

    `lines_hash` is `provenance.compute_lines_hash`'s output over the exact
    ordered lyric texts this run aligned against (docs/bombista-product-
    backlog.md B4) — `promote` reads it back out of `_bombista.linesHash`
    to detect lyrics that changed since extraction.
    """
    return {**reader_bombista, "source": provenance, "linesHash": lines_hash}


def write_songjson(song: dict, envelope: dict, bombista: dict, out_path: Path) -> dict:
    """The canonical CP song dict with the v2 envelope merged in (via
    `merge_envelope` — the single merge path also used by `promote`), plus
    a `_bombista` block appended as the final key.

    Writes the result to *out_path* as indent=2 JSON (trailing newline,
    `ensure_ascii=False` — matching `promote`'s on-disk format) and also
    returns it.
    """
    merged = merge_envelope(song, envelope)
    merged["_bombista"] = bombista
    out_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return merged


def write_report_json(
    *,
    provenance: dict,
    lines_hash: str,
    lead_in_block: dict,
    anchors: Sequence[LineAnchor],
    lines: Sequence[str],
    line_entries: Sequence[TimelineEntry],
    out_path: Path,
) -> dict:
    """The rich JSON — confidence bands + signals per line, discarded today
    at serialisation into the plain timeline (backlog §3.6).

    `provenance` is embedded verbatim under `source` (same dict as B1's
    QA-report header and `songjson`'s `_bombista.source`). `lines_hash` is
    `provenance.compute_lines_hash`'s output over `lines` (B4) — a top-level
    `linesHash`, which `promote` reads back out of a candidate's sibling
    `<stem>-report.json` when the candidate itself is a bare v2 envelope.
    `lead_in_block` is the *whole* `leadIn` object from the v2 envelope (not
    just the raw float) so the relationship between these raw times and the
    emitted, normalised timeline is explicit here rather than implied.

    **Times in `lines[].start`/`.end` are raw audio-clock seconds** — the
    same clock as the markdown QA report and `--anchor LINE=SECONDS`
    overrides — NOT the lead-in-normalised clock of the emitted timeline.
    Subtract `lead_in_block['durationSec']` to get the normalised value.

    `anchors`, `lines` and `line_entries` are parallel, one per lyric line
    (same convention as `report.render_qa_report`). `asrContext` is
    included per line only when the anchor carries one (empty for
    overrides and FAILs). `previousSignals` is part of this shape per the
    backlog (recording a line's prior confidence signals across an
    `--anchor` correction) but nothing in `anchoring.py` populates it yet
    — it is never emitted here, by construction, until that tracking
    exists.
    """
    counts = band_counts(anchors)
    lines_out = []
    for anchor in anchors:
        entry = line_entries[anchor.line_index]
        line = {
            "i": anchor.line_index,
            "text": lines[anchor.line_index],
            "start": entry.start,
            "end": entry.end,
            "band": anchor.band,
            "signals": list(anchor.signals),
        }
        if anchor.asr_context:
            line["asrContext"] = anchor.asr_context
        lines_out.append(line)

    result = {
        "source": provenance,
        "linesHash": lines_hash,
        "leadIn": lead_in_block,
        "summary": {
            "high": counts.get("HIGH", 0),
            "review": counts.get("REVIEW", 0),
            "fail": counts.get("FAIL", 0),
        },
        "lines": lines_out,
    }
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _language_keys(items: Sequence[dict]) -> list[str]:
    """Every key present on any lyric item whose value is a string, in
    order of first appearance — i.e. every language key present in the
    input, CP song JSON's only per-item keys are language codes."""
    seen: dict[str, None] = {}
    for item in items:
        for key, value in item.items():
            if isinstance(value, str):
                seen.setdefault(key, None)
    return list(seen.keys())


def _absolute_entries(envelope: dict) -> list[TimelineEntry]:
    """Subtitle files are absolute by nature — an SRT/LRC cue's
    `00:00:07` means "seven seconds into this specific media file", full
    stop, with no live start cue to resolve against at playback. The
    native timeline (`timeline.json`) stays cue-relative on purpose, so a
    player can wait for whichever cue fires (pedal press or video start);
    a subtitle file has no such cue to wait for, so its only correct time
    base is the media's own clock. That is why the lead-in is added back
    here whenever `leadIn.apply` is true, and never subtracted again —
    this is a deliberate divergence from the native timeline, not a bug;
    do not "fix" it to match `timeline.json`'s cue-relative clock.
    """
    lead_in = envelope["leadIn"]["durationSec"] if envelope["leadIn"]["apply"] else 0.0
    return [
        TimelineEntry(round(e["start"] + lead_in, 2), round(e["end"] + lead_in, 2))
        for e in envelope["timeline"]
    ]


def _srt_timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(song: dict, envelope: dict, stem: str, out_dir: Path) -> list[Path]:
    """Write one `<stem>-<lang>.srt` file per language key present in
    `song['lyrics']`. Lyric text may contain embedded newlines — SRT
    allows multi-line cues, so they are kept as-is."""
    entries = _absolute_entries(envelope)
    items = song.get("lyrics", [])
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for lang in _language_keys(items):
        cue_lines: list[str] = []
        n = 0
        for item, entry in zip(items, entries):
            text = item.get(lang)
            if not isinstance(text, str):
                continue
            n += 1
            cue_lines.append(str(n))
            cue_lines.append(
                f"{_srt_timestamp(entry.start)} --> {_srt_timestamp(entry.end)}"
            )
            cue_lines.append(text)
            cue_lines.append("")
        path = out_dir / f"{stem}-{lang}.srt"
        path.write_text("\n".join(cue_lines) + ("\n" if cue_lines else ""), encoding="utf-8")
        paths.append(path)
    return paths


def _lrc_timestamp(seconds: float) -> str:
    total_cs = round(seconds * 100)
    minutes, rem = divmod(total_cs, 6000)
    secs, cs = divmod(rem, 100)
    return f"[{minutes:02d}:{secs:02d}.{cs:02d}]"


def write_lrc(song: dict, envelope: dict, stem: str, out_dir: Path) -> list[Path]:
    """Write one `<stem>-<lang>.lrc` file per language key present in
    `song['lyrics']`, with `[ti:]`/`[ar:]` tags when the song has a
    title/artist. LRC is strictly one line per timestamp — embedded
    newlines in the lyric text are flattened to a space (unlike SRT)."""
    entries = _absolute_entries(envelope)
    items = song.get("lyrics", [])
    out_dir.mkdir(parents=True, exist_ok=True)

    title = song.get("title")
    artist = song.get("artist")

    paths: list[Path] = []
    for lang in _language_keys(items):
        out_lines: list[str] = []
        if isinstance(title, str) and title:
            out_lines.append(f"[ti:{title}]")
        if isinstance(artist, str) and artist:
            out_lines.append(f"[ar:{artist}]")
        for item, entry in zip(items, entries):
            text = item.get(lang)
            if not isinstance(text, str):
                continue
            flat = " ".join(text.splitlines())
            out_lines.append(f"{_lrc_timestamp(entry.start)}{flat}")
        path = out_dir / f"{stem}-{lang}.lrc"
        path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        paths.append(path)
    return paths
