"""
Tests for the QA report header — B1's provenance wiring.

`render_qa_report` is the surface a human actually reads; the provenance
block (audio identity, sha256, duration, model, device, lang,
extractedAt, toolVersion) must show up in its header. Fast: no whisper
model, no audio decoding — a hand-built `provenance` dict stands in for
what `provenance.build_provenance` would produce.
"""
from __future__ import annotations

import shlex
from pathlib import Path

from bombista.anchoring import LineAnchor
from bombista.models import TimelineEntry
from bombista.report import render_qa_report

LINES = ["hola mundo", "vamos ya"]
ANCHORS = [
    LineAnchor(0, 10.0, "HIGH", ("clean-anchor",), "hola mundo", 0),
    LineAnchor(1, 20.0, "HIGH", ("clean-anchor",), "vamos ya", 0),
]
ENTRIES = [
    TimelineEntry(start=10.0, end=20.0),
    TimelineEntry(start=20.0, end=23.0),
]

PROVENANCE = {
    "audio": "songs/audio/libertad.m4a",
    "sha256": "4f2a9c" + "0" * 58,
    "durationSec": 172.4,
    "model": "faster-whisper:medium",
    "device": "cpu/int8",
    "lang": "es",
    "extractedAt": "2026-08-11T16:45:34+02:00",
    "toolVersion": "bombista 0.9.0",
}


def _render(**overrides):
    provenance = {**PROVENANCE, **overrides.pop("provenance_overrides", {})}
    kwargs = dict(
        anchors=ANCHORS,
        lines=LINES,
        line_entries=ENTRIES,
        lead_in=10.0,
        song_title="Libertad",
        song_path=Path("songs/libertad.json"),
        audio_path=Path(provenance["audio"]),
        model_size="medium",
        lang="es",
        staging_dir=Path("staging/libertad"),
        provenance=provenance,
    )
    kwargs.update(overrides)
    return render_qa_report(**kwargs)


def test_report_header_shows_audio_path():
    report = _render()
    assert "songs/audio/libertad.m4a" in report


def test_report_header_shows_full_sha256_somewhere():
    report = _render()
    assert PROVENANCE["sha256"] in report


def test_report_header_shows_duration():
    report = _render()
    assert "172.4" in report


def test_report_header_shows_model():
    report = _render()
    assert "faster-whisper:medium" in report


def test_report_header_shows_device():
    report = _render()
    assert "cpu/int8" in report


def test_report_header_shows_lang():
    report = _render()
    assert "es" in report


def test_report_header_shows_extracted_at():
    report = _render()
    assert "2026-08-11T16:45:34+02:00" in report


def test_report_header_shows_tool_version():
    report = _render()
    assert "bombista 0.9.0" in report


def test_report_header_shows_null_duration_gracefully():
    """durationSec: None (unreadable container) must not crash the report,
    and must not render a bare Python "None" that reads like a bug."""
    report = _render(provenance_overrides={"durationSec": None})
    header = report.split("## Needs attention")[0]
    assert "None" not in header


# ---------------------------------------------------------------------------
# Stripped lines (B5) — visible removal, not silent
# ---------------------------------------------------------------------------

STRIPPED_LINES = [
    {"line": 1, "text": "[Intro]", "reason": "bracketed"},
    {"line": 2, "text": "", "reason": "blank"},
]


def test_report_omits_stripped_lines_section_when_nothing_was_stripped():
    report = _render()
    assert "Stripped lines" not in report


def test_report_lists_stripped_lines_when_present():
    report = _render(stripped_lines=STRIPPED_LINES)

    assert "Stripped lines" in report
    assert "[Intro]" in report
    assert "bracketed" in report
    assert "blank" in report


def test_report_stripped_lines_shows_source_line_numbers():
    report = _render(stripped_lines=STRIPPED_LINES)
    section = report.split("## Stripped lines")[1]

    assert "| 1 " in section or "|1|" in section.replace(" ", "")
    assert "| 2 " in section or "|2|" in section.replace(" ", "")


# ---------------------------------------------------------------------------
# B17 — the printed commands must survive a paste
#
# Every path the report interpolates is attacker-free but space-full: the
# real invocation is `~/Chango Pepper/songs/audio/libertad.m4a`. The
# filename is space-free by the `songs/audio/<slug>.<ext>` convention, but
# the vault directory above it is not — one space is all it takes for an
# unquoted path to split into two argv entries and fail at the prompt. So
# the fixtures below keep their space in the DIRECTORY, which is where it
# actually lives. B16 fixed this in the HTML page; these tests hold the
# same line for the markdown report.
#
# The assertions round-trip through `shlex.split` rather than looking for
# quote characters, because what matters is the resulting argv, not which
# quoting style produced it.
# ---------------------------------------------------------------------------

SPACEY_AUDIO = Path("Chango Pepper/songs/audio/libertad.m4a")
SPACEY_SONG = Path("Chango Pepper/songs/libertad.json")
SPACEY_STAGING = Path("Chango Pepper/staging/libertad run")

REVIEW_ANCHORS = [
    LineAnchor(0, 10.0, "HIGH", ("clean-anchor",), "hola mundo", 0),
    LineAnchor(1, 20.0, "REVIEW", ("ambiguous",), "vamos ya", 0),
]


def _spacey_report(**overrides):
    return _render(
        audio_path=SPACEY_AUDIO,
        song_path=SPACEY_SONG,
        staging_dir=SPACEY_STAGING,
        **overrides,
    )


def _backticked(report: str, marker: str) -> str:
    """The one backticked span on the line introduced by `marker`."""
    line = next(ln for ln in report.splitlines() if marker in ln)
    return line.split("`")[1]


def test_rerun_command_survives_shlex_split():
    command = _backticked(_spacey_report(), "Re-run")
    argv = shlex.split(command)

    assert str(SPACEY_AUDIO) in argv
    assert str(SPACEY_SONG) in argv
    assert str(SPACEY_STAGING) in argv
    assert str(SPACEY_STAGING / "asr-words.jsonl") in argv


def test_rerun_command_keeps_its_argument_count():
    """A quoting failure shows up as extra argv entries, not as a crash —
    so pin the count rather than only checking the paths are findable."""
    command = _backticked(_spacey_report(), "Re-run")

    # bombista extract <audio> <song> -o <staging> --words <words> --lang es
    assert len(shlex.split(command)) == 10


def test_anchor_hint_paths_survive_shlex_split():
    report = _spacey_report(anchors=REVIEW_ANCHORS)
    # Not just any line mentioning `--anchor` — the audio-clock blockquote
    # names the flag too. The hints are the "- Line N:" bullets.
    hint = next(ln for ln in report.splitlines() if ln.startswith("- Line 1:"))

    # `--anchor 1=<seconds>` and `--words <path>` are separate backticked
    # spans; the words path is the one carrying the spaces.
    words = next(
        span for span in hint.split("`") if "asr-words.jsonl" in span
    )
    argv = shlex.split(words)

    assert argv == ["--words", str(SPACEY_STAGING / "asr-words.jsonl")]


def test_unspaced_paths_are_not_gratuitously_quoted():
    """`shlex.quote` leaves safe paths alone. Keeping that true means the
    common case reads exactly as it did before B17."""
    command = _backticked(_render(), "Re-run")

    assert "staging/libertad" in command
    assert "'staging/libertad'" not in command
