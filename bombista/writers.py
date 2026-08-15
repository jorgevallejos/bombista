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
import os
import shlex
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from typing import Sequence
from urllib.parse import quote

from .anchoring import SIGNAL_GLOSSES, LineAnchor
from .models import TimelineEntry
from .report import AUDIO_CLOCK_RULE, band_counts, extracted_at, format_duration

__all__ = [
    "ENVELOPE_KEYS",
    "merge_envelope",
    "build_bombista_block",
    "write_songjson",
    "write_report_json",
    "write_srt",
    "write_lrc",
    "write_html_review",
]

ENVELOPE_KEYS = ("timelineVersion", "leadIn", "timeline")
"""The three envelope keys, in contract order. Public because `migrate.py`
needs the same ordered tuple to reason about "everything except the
envelope" — one definition, not a copy."""


def merge_envelope(song: dict, envelope: dict) -> dict:
    """Return a copy of *song* with `timelineVersion`, `leadIn` and
    `timeline` set from *envelope*, in that order, replacing any existing
    occurrence of those keys in place (or appending them at the end if none
    existed) — every other key is preserved untouched and in order.

    This is THE merge path (see module docstring) — do not reimplement it
    elsewhere.

    The three keys are written **as a unit, never partially**: a song
    carrying normalised timings without a `timelineVersion` stamp would be
    rejected by the translator, and one carrying a stamp without a `leadIn`
    would lose the offset needed to reconstruct the raw times. An envelope
    missing any of them raises ValueError *before* anything is written,
    rather than producing a half-stamped song.
    """
    absent = [k for k in ENVELOPE_KEYS if k not in envelope]
    if absent:
        raise ValueError(
            f"refusing to merge a partial envelope — missing {absent}. "
            f"{list(ENVELOPE_KEYS)} are written as a unit or not at all"
        )

    new_song: dict = {}
    inserted = False
    for key, value in song.items():
        if key in ENVELOPE_KEYS:
            if not inserted:
                for k in ENVELOPE_KEYS:
                    new_song[k] = envelope[k]
                inserted = True
            continue
        new_song[key] = value
    if not inserted:
        for k in ENVELOPE_KEYS:
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
    overrides and FAILs). `signalGlosses` maps each of the line's signals
    to `anchoring.SIGNAL_GLOSSES`'s plain sentence (B20 §8.3) and is
    omitted when none of them has one to give — `clean-anchor` and
    `override` say nothing, and a key full of empty strings on every clean
    line would be noise in an audit document. `previousSignals` is part of this shape per the
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
        glosses = {
            signal: SIGNAL_GLOSSES[signal]
            for signal in anchor.signals
            if SIGNAL_GLOSSES.get(signal)
        }
        if glosses:
            line["signalGlosses"] = glosses
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


# ---------------------------------------------------------------------------
# write_html_review — B16
# ---------------------------------------------------------------------------

_HTML_CSS = """\
:root {
  color-scheme: light dark;
  --bg: #fbfaf8; --fg: #1c1b19; --muted: #6b6862; --rule: #e2ded7;
  --card: #ffffff; --high: #2f7d4f; --review: #a86a00; --fail: #b3261e;
  --tint-review: #fdf4e3; --tint-fail: #fdeceb; --current: #fff6cc;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #17161a; --fg: #eceae6; --muted: #a09b93; --rule: #322f36;
    --card: #201e24; --high: #6cc08b; --review: #e0a437; --fail: #f2857c;
    --tint-review: #2c2418; --tint-fail: #2e1c1a; --current: #3a3320;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0 1.5rem 4rem;
  background: var(--bg); color: var(--fg);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { max-width: 62rem; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 1.75rem 0 .35rem; }
h2 { font-size: 1.1rem; margin: 2.25rem 0 .75rem; }
.meta { list-style: none; margin: .75rem 0; padding: 0; font-size: .82rem; color: var(--muted); }
.meta li { margin: .15rem 0; }
.meta b { color: var(--fg); font-weight: 600; }
code, .cmd { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .8rem; }
.note { font-size: .82rem; color: var(--muted); border-left: 3px solid var(--rule);
        padding: .4rem 0 .4rem .8rem; margin: 1rem 0; }
.player { position: sticky; top: 0; z-index: 5; background: var(--bg);
          padding: .75rem 0; border-bottom: 1px solid var(--rule); }
.player audio { width: 100%; }
.counts { display: flex; gap: .5rem; flex-wrap: wrap; margin: .5rem 0 0; }
.chip { font-size: .75rem; font-weight: 600; padding: .12rem .5rem; border-radius: 999px;
        border: 1px solid currentColor; }
.band-HIGH { color: var(--high); }
.band-REVIEW { color: var(--review); }
.band-FAIL { color: var(--fail); }
.flag { background: var(--card); border: 1px solid var(--rule); border-left: 5px solid currentColor;
        border-radius: 6px; padding: .8rem 1rem; margin: .7rem 0; }
.flag.band-REVIEW { background: var(--tint-review); }
.flag.band-FAIL { background: var(--tint-fail); }
.flag-head { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
.idx { font-size: .78rem; color: var(--muted); }
.signals { font-size: .78rem; color: var(--muted); }
.gloss { margin: .35rem 0 0; font-size: .85rem; color: var(--fg); }
.text { color: var(--fg); margin: .5rem 0 .3rem; white-space: pre-wrap; font-size: 1rem; }
.asr { margin: .1rem 0; font-size: .82rem; color: var(--muted); white-space: pre-wrap; }
.fix { display: flex; align-items: center; gap: .5rem; margin-top: .6rem; flex-wrap: wrap; }
.fix .cmd { background: var(--bg); border: 1px solid var(--rule); border-radius: 4px;
            padding: .35rem .5rem; overflow-x: auto; white-space: pre; flex: 1 1 20rem; }
button { font: inherit; cursor: pointer; border-radius: 5px; border: 1px solid var(--rule);
         background: var(--card); color: var(--fg); padding: .25rem .6rem; }
button:hover { border-color: var(--muted); }
.play { font-variant-numeric: tabular-nums; white-space: nowrap; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
th, td { text-align: left; padding: .4rem .5rem; border-bottom: 1px solid var(--rule);
         vertical-align: top; }
th { font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tr.band-REVIEW td { background: var(--tint-review); }
tr.band-FAIL td { background: var(--tint-fail); }
.current, tr.current td { background: var(--current) !important; }
"""

_HTML_JS = """\
(function () {
  var audio = document.getElementById("audio");
  var marks = Array.prototype.slice.call(document.querySelectorAll("[data-line]"));

  document.addEventListener("click", function (ev) {
    var el = ev.target;
    if (!el || !el.closest) { return; }
    var play = el.closest(".play");
    if (play) {
      var t = parseFloat(play.getAttribute("data-start"));
      if (!isNaN(t)) { audio.currentTime = t; audio.play(); }
      return;
    }
    var copy = el.closest(".copy");
    if (copy) {
      var cmd = copy.parentNode.querySelector(".cmd");
      if (cmd) { copyText(cmd.textContent, copy); }
    }
  });

  function flash(btn) {
    var was = btn.textContent;
    btn.textContent = "Copied";
    setTimeout(function () { btn.textContent = was; }, 1200);
  }

  function copyText(text, btn) {
    // navigator.clipboard is unavailable on file:// in some browsers
    // (not a secure context), so the selection fallback is not optional.
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () { flash(btn); },
        function () { legacyCopy(text, btn); }
      );
      return;
    }
    legacyCopy(text, btn);
  }

  function legacyCopy(text, btn) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); flash(btn); } catch (err) { /* nothing else to try */ }
    document.body.removeChild(ta);
  }

  audio.addEventListener("timeupdate", function () {
    var t = audio.currentTime;
    for (var i = 0; i < marks.length; i++) {
      var m = marks[i];
      var s = parseFloat(m.getAttribute("data-start"));
      var e = parseFloat(m.getAttribute("data-end"));
      if (t >= s && t < e) { m.classList.add("current"); }
      else { m.classList.remove("current"); }
    }
  });
})();
"""


def _audio_href(audio_path: Path, staging_dir: Path) -> str:
    """The page is written into the staging directory and the audio lives
    outside it, so the reference is relative — the whole staging dir stays
    portable (copy it elsewhere and the page still plays). Percent-encoded
    because real paths have spaces in them — audio filenames follow the
    `songs/audio/<slug>.<ext>` convention and are space-free, but they sit
    under `~/Chango Pepper/`, so the relative href still crosses a space.

    Falls back to the absolute path only when no relative route exists
    (different volume) — a page that plays beats a page that is portable.
    """
    try:
        rel = os.path.relpath(audio_path, staging_dir)
    except ValueError:
        rel = str(audio_path)
    return quote(Path(rel).as_posix())


def _anchor_command(
    line_index: int,
    *,
    audio_path: Path,
    song_path: Path,
    staging_dir: Path,
    words_path: Path,
    lang: str,
) -> str:
    """The re-run that hand-fixes one line, ready to paste. `<seconds>` is
    left as a placeholder — the number is what the human is here to
    decide. `--words` is what makes the correction loop instant.

    Paths are shell-quoted: this command exists to be copied and pasted,
    and real paths have spaces in them — the filenames themselves are
    space-free (`songs/audio/libertad.m4a`), but the vault directory above
    them is `Chango Pepper`, which would otherwise split into two
    arguments at the prompt.
    """
    quoted = " ".join(
        shlex.quote(str(p)) for p in (audio_path, song_path)
    )
    return (
        f"bombista align {quoted} -o {shlex.quote(str(staging_dir))} "
        f"--words {shlex.quote(str(words_path))} --lang {shlex.quote(lang)} "
        f"--anchor {line_index}=<seconds>"
    )


def _play_button(entry: TimelineEntry, label: str) -> str:
    return (
        f'<button type="button" class="play" data-start="{entry.start:.2f}" '
        f'data-end="{entry.end:.2f}">{label}</button>'
    )


def write_html_review(
    *,
    song_title: str,
    song_path: Path,
    audio_path: Path,
    staging_dir: Path,
    words_path: Path,
    lang: str,
    provenance: dict,
    lead_in: float,
    anchors: Sequence[LineAnchor],
    lines: Sequence[str],
    line_entries: Sequence[TimelineEntry],
    out_path: Path,
    generated_at: datetime | None = None,
) -> Path:
    """The B16 review page: one self-contained HTML file that lets a human
    *hear* the line they are judging instead of reading a timestamp and
    scrubbing an m4a in another app.

    **Fully offline, by construction.** CSS and JS are inlined and nothing
    is fetched from anywhere — Bombista running with no network is a stated
    product property (backlog §1), and an external stylesheet or CDN script
    would break it quietly, leaving a page that still renders. The audio is
    referenced by a relative path rather than base64-embedded: the file
    lives next to the audio, so embedding would bloat it for nothing.

    **Times here are raw audio-clock seconds**, like the markdown QA report
    and `--anchor LINE=SECONDS` — never the emitted timeline's cue-relative
    clock. The play buttons drive an `<audio>` element, whose clock *is*
    the audio file's; seeding them with normalised times would seek every
    line short by the lead-in. `anchors`, `lines` and `line_entries` are
    parallel, one per lyric line (same convention as
    `report.render_qa_report`).

    Returns the path written.
    """
    generated_at = generated_at or datetime.now()
    counts = band_counts(anchors)
    href = _audio_href(audio_path, staging_dir)
    esc = html_escape

    head = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>QA review — {esc(song_title)}</title>",
        f"<style>\n{_HTML_CSS}</style>",
        "</head>",
        "<body>",
        '<div class="wrap">',
        f"<h1>QA review — {esc(song_title)}</h1>",
        '<ul class="meta">',
        f"<li><b>Song file</b> <code>{esc(str(song_path))}</code></li>",
        f"<li><b>Audio file</b> <code>{esc(str(provenance['audio']))}</code></li>",
        f"<li><b>Audio sha256</b> <code>{esc(str(provenance['sha256']))}</code></li>",
        f"<li><b>Audio duration</b> {esc(format_duration(provenance['durationSec']))}</li>",
        f"<li><b>Model</b> <code>{esc(str(provenance['model']))}</code> "
        f"(lang <code>{esc(str(provenance['lang']))}</code>, "
        f"device <code>{esc(str(provenance['device']))}</code>)</li>",
        # `.get`, not `[…]`: a `--words` run against a staging directory
        # with no `asr-words.meta.json` omits the field rather than invent
        # a time (B20 §11.10), and this page is one of the two places that
        # has to render the absence.
        f"<li><b>Extracted at</b> {esc(extracted_at(provenance))}</li>",
        f"<li><b>Tool version</b> {esc(str(provenance['toolVersion']))}</li>",
        f"<li><b>Generated</b> {esc(generated_at.isoformat(timespec='seconds'))}</li>",
        f"<li><b>Measured lead-in</b> {lead_in:.2f} s "
        "(subtracted from the emitted timeline, not from the times below)</li>",
        "</ul>",
        '<div class="counts">',
        f'<span class="chip band-HIGH">HIGH {counts["HIGH"]}</span>',
        f'<span class="chip band-REVIEW">REVIEW {counts["REVIEW"]}</span>',
        f'<span class="chip band-FAIL">FAIL {counts["FAIL"]}</span>',
        "</div>",
        f'<p class="note">{esc(AUDIO_CLOCK_RULE)} All times on this page are raw '
        f"audio-clock seconds (before the {lead_in:.2f} s lead-in is subtracted) — "
        "the play buttons and <code>--anchor</code> use this same clock.</p>",
        '<div class="player">',
        f'<audio id="audio" controls preload="metadata" src="{href}"></audio>',
        "</div>",
    ]

    flagged = [a for a in anchors if a.band != "HIGH"]
    body = ['<section id="needs-attention">', "<h2>Needs attention</h2>"]
    if flagged:
        for anchor in flagged:
            i = anchor.line_index
            entry = line_entries[i]
            command = _anchor_command(
                i,
                audio_path=audio_path,
                song_path=song_path,
                staging_dir=staging_dir,
                words_path=words_path,
                lang=lang,
            )
            hint = (
                f"candidate start was {anchor.start:.2f} s"
                if anchor.start is not None
                else "no anchor found — listen for the line and time its onset"
            )
            body.extend(
                [
                    f'<article class="flag band-{anchor.band}" data-line="{i}" '
                    f'data-start="{entry.start:.2f}" data-end="{entry.end:.2f}">',
                    '<div class="flag-head">',
                    _play_button(entry, f"▶ {entry.start:.2f} s"),
                    f'<span class="idx">line {i}</span>',
                    f'<span class="chip band-{anchor.band}">{anchor.band}</span>',
                    f'<span class="signals">{esc(", ".join(anchor.signals))}</span>',
                    "</div>",
                ]
            )
            # The signal spelled out under its token (B20 §8.3) — the
            # tokens above mean nothing to a reader who has not opened
            # anchoring.py, and this page exists for exactly that reader.
            for signal in anchor.signals:
                gloss = SIGNAL_GLOSSES.get(signal, "")
                if gloss:
                    body.append(f'<p class="gloss">{esc(gloss)}</p>')
            body.append(f'<p class="text">{esc(lines[i])}</p>')
            if anchor.asr_context:
                body.append(f'<p class="asr">ASR heard: {esc(anchor.asr_context)}</p>')
            body.extend(
                [
                    f'<p class="asr">{esc(hint)}</p>',
                    '<div class="fix">',
                    f'<code class="cmd">{esc(command)}</code>',
                    '<button type="button" class="copy">Copy</button>',
                    "</div>",
                    "</article>",
                ]
            )
    else:
        body.append("<p>None — every line anchored HIGH.</p>")
    body.append("</section>")

    body.extend(
        [
            '<section id="all-lines">',
            "<h2>All lines</h2>",
            "<table>",
            "<thead><tr><th>line</th><th></th><th>canonical text</th><th>start</th>"
            "<th>end</th><th>dur</th><th>band</th><th>signals</th></tr></thead>",
            "<tbody>",
        ]
    )
    for anchor in anchors:
        i = anchor.line_index
        entry = line_entries[i]
        body.extend(
            [
                f'<tr class="band-{anchor.band}" data-line="{i}" '
                f'data-start="{entry.start:.2f}" data-end="{entry.end:.2f}">',
                f"<td>{i}</td>",
                f"<td>{_play_button(entry, '▶')}</td>",
                f'<td class="text">{esc(lines[i])}</td>',
                f'<td class="num">{entry.start:.2f}</td>',
                f'<td class="num">{entry.end:.2f}</td>',
                f'<td class="num">{entry.end - entry.start:.2f}</td>',
                f'<td><span class="band-{anchor.band}">{anchor.band}</span></td>',
                f'<td class="signals">{esc(", ".join(anchor.signals))}</td>',
                "</tr>",
            ]
        )
    body.extend(["</tbody>", "</table>", "</section>"])

    tail = ["</div>", f"<script>\n{_HTML_JS}</script>", "</body>", "</html>", ""]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(head + body + tail), encoding="utf-8")
    return out_path
