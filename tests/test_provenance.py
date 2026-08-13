"""
Tests for the provenance block builder — B1.

`build_provenance` is called once per `extract` run and records which
audio file a timeline was derived from (see docs/bombista-product-backlog.md
B1: the shipped Tragedia timeline was ~17s wrong for weeks because nothing
recorded this). Fast: no whisper model. sha256/duration are exercised
against small real files (the committed 12s wav fixture, and tmp_path
files), never anything requiring the network or the ASR model.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from timeline_extractor.aligner import DEVICE_STRING
from timeline_extractor.provenance import build_provenance

FIXTURE_AUDIO = Path(__file__).parent / "fixtures" / "tragedia-opening-12s.wav"


def test_build_provenance_returns_all_expected_keys(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"not real audio but has bytes")

    result = build_provenance(audio, model_size="medium", lang="es")

    assert set(result.keys()) == {
        "audio",
        "sha256",
        "durationSec",
        "model",
        "device",
        "lang",
        "extractedAt",
        "toolVersion",
    }


def test_build_provenance_sha256_matches_hashlib_over_full_bytes(tmp_path):
    audio = tmp_path / "a.wav"
    content = b"x" * (5 * 1024 * 1024 + 37)  # bigger than one chunk
    audio.write_bytes(content)

    result = build_provenance(audio, model_size="medium", lang="es")

    assert result["sha256"] == hashlib.sha256(content).hexdigest()


def test_build_provenance_sha256_differs_for_different_content(tmp_path):
    audio_a = tmp_path / "a.wav"
    audio_b = tmp_path / "b.wav"
    audio_a.write_bytes(b"content A")
    audio_b.write_bytes(b"content B")

    result_a = build_provenance(audio_a, model_size="medium", lang="es")
    result_b = build_provenance(audio_b, model_size="medium", lang="es")

    assert result_a["sha256"] != result_b["sha256"]


def test_build_provenance_audio_path_recorded_as_given(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"abc")

    result = build_provenance(audio, model_size="medium", lang="es")

    assert result["audio"] == str(audio)


def test_build_provenance_duration_from_real_audio_fixture():
    result = build_provenance(FIXTURE_AUDIO, model_size="tiny", lang="es")

    assert result["durationSec"] is not None
    assert result["durationSec"] == pytest.approx(12.0, abs=0.1)


def test_build_provenance_duration_is_null_but_present_for_unreadable_container(tmp_path):
    not_audio = tmp_path / "not-audio.wav"
    not_audio.write_bytes(b"this is not a media container at all, just text bytes")

    result = build_provenance(not_audio, model_size="medium", lang="es")

    assert "durationSec" in result
    assert result["durationSec"] is None
    # provenance never crashes an extract — sha256 etc. still computed
    assert result["sha256"] == hashlib.sha256(not_audio.read_bytes()).hexdigest()


def test_build_provenance_model_string(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"abc")

    result = build_provenance(audio, model_size="medium", lang="es")

    assert result["model"] == "faster-whisper:medium"


def test_build_provenance_model_string_reflects_model_size(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"abc")

    result = build_provenance(audio, model_size="tiny", lang="es")

    assert result["model"] == "faster-whisper:tiny"


def test_build_provenance_device_matches_aligner_constant(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"abc")

    result = build_provenance(audio, model_size="medium", lang="es")

    assert result["device"] == DEVICE_STRING
    assert result["device"] == "cpu/int8"


def test_build_provenance_lang_passthrough(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"abc")

    result = build_provenance(audio, model_size="medium", lang="nl")

    assert result["lang"] == "nl"


def test_build_provenance_extracted_at_uses_injected_now(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"abc")
    fixed_now = datetime(2026, 8, 11, 16, 45, 34, tzinfo=timezone(timedelta(hours=2)))

    result = build_provenance(audio, model_size="medium", lang="es", now=fixed_now)

    assert result["extractedAt"] == "2026-08-11T16:45:34+02:00"


def test_build_provenance_extracted_at_defaults_to_now_with_offset(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"abc")
    before = datetime.now().astimezone()

    result = build_provenance(audio, model_size="medium", lang="es")

    parsed = datetime.fromisoformat(result["extractedAt"])
    assert parsed.tzinfo is not None
    assert abs((parsed - before).total_seconds()) < 10


def test_build_provenance_tool_version_names_the_tool_and_its_version(tmp_path):
    from importlib.metadata import version

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"abc")

    result = build_provenance(audio, model_size="medium", lang="es")

    assert result["toolVersion"] == f"timeline-extractor {version('timeline-extractor')}"
