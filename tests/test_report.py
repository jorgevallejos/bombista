"""
Tests for the QA report header — B1's provenance wiring.

`render_qa_report` is the surface a human actually reads; the provenance
block (audio identity, sha256, duration, model, device, lang,
extractedAt, toolVersion) must show up in its header. Fast: no whisper
model, no audio decoding — a hand-built `provenance` dict stands in for
what `provenance.build_provenance` would produce.
"""
from __future__ import annotations

from pathlib import Path

from timeline_extractor.anchoring import LineAnchor
from timeline_extractor.models import TimelineEntry
from timeline_extractor.report import render_qa_report

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
    "audio": "songs/audio/Song Libertad.m4a",
    "sha256": "4f2a9c" + "0" * 58,
    "durationSec": 172.4,
    "model": "faster-whisper:medium",
    "device": "cpu/int8",
    "lang": "es",
    "extractedAt": "2026-08-11T16:45:34+02:00",
    "toolVersion": "timeline-extractor 0.1.0",
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
    assert "songs/audio/Song Libertad.m4a" in report


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
    assert "timeline-extractor 0.1.0" in report


def test_report_header_shows_null_duration_gracefully():
    """durationSec: None (unreadable container) must not crash the report,
    and must not render a bare Python "None" that reads like a bug."""
    report = _render(provenance_overrides={"durationSec": None})
    header = report.split("## Needs attention")[0]
    assert "None" not in header
