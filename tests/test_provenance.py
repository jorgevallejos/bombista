"""
Tests for the provenance block builder — B1.

`build_provenance` is called once per `extract` run and records which
audio file a timeline was derived from (see docs/bombista-product-backlog.md
B1: a shipped timeline was ~17s wrong for weeks because nothing recorded
this). Fast: no whisper model. sha256/duration are exercised against small
real files (the committed 12s wav fixture, and tmp_path files), never
anything requiring the network or the ASR model.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bombista.aligner import DEVICE_STRING
from bombista.provenance import (
    build_provenance,
    compute_lines_hash,
    provenance_for_reused_words,
    words_meta,
)

FIXTURE_AUDIO = Path(__file__).parent / "fixtures" / "synthetic-es-12s.wav"


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

    assert result["toolVersion"] == f"bombista {version('bombista')}"


# ---------------------------------------------------------------------------
# compute_lines_hash — B4 (docs/bombista-product-backlog.md §1, §4)
# ---------------------------------------------------------------------------


def test_compute_lines_hash_returns_sha256_prefixed_string():
    result = compute_lines_hash(["uno", "dos", "tres"])

    assert result.startswith("sha256:")
    digest = result.split(":", 1)[1]
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_compute_lines_hash_matches_hashlib_over_newline_joined_utf8_bytes():
    lines = ["Fui brasa viva en la oscuridad,", "Chispa que quiso brotar."]

    result = compute_lines_hash(lines)

    expected = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    assert result == f"sha256:{expected}"


def test_compute_lines_hash_identical_for_identical_line_lists():
    lines = ["uno", "dos", "tres"]

    assert compute_lines_hash(lines) == compute_lines_hash(list(lines))


def test_compute_lines_hash_differs_when_a_line_is_edited():
    original = ["uno", "dos", "tres"]
    edited = ["uno", "dos editado", "tres"]

    assert compute_lines_hash(original) != compute_lines_hash(edited)


def test_compute_lines_hash_differs_when_a_line_is_inserted():
    original = ["uno", "dos", "tres"]
    with_insert = ["uno", "nueva linea", "dos", "tres"]

    assert compute_lines_hash(original) != compute_lines_hash(with_insert)


def test_compute_lines_hash_differs_from_a_reordering_of_the_same_lines():
    lines = ["uno", "dos", "tres"]
    reordered = ["tres", "dos", "uno"]

    assert compute_lines_hash(lines) != compute_lines_hash(reordered)


def test_compute_lines_hash_of_empty_list_is_stable():
    assert compute_lines_hash([]) == compute_lines_hash([])


# ---------------------------------------------------------------------------
# §11.10 — `extractedAt` is a claim about when the machine listened
# ---------------------------------------------------------------------------


def test_words_meta_carries_what_the_word_stream_cannot_say_about_itself(tmp_path):
    audio = tmp_path / "sub" / "a.wav"
    audio.parent.mkdir()
    audio.write_bytes(b"bytes")
    provenance = build_provenance(audio, model_size="medium", lang="es")

    meta = words_meta(provenance, audio)

    assert set(meta) == {"extractedAt", "model", "device", "lang", "sha256", "audio"}
    for key in ("extractedAt", "model", "device", "lang", "sha256"):
        assert meta[key] == provenance[key]


def test_words_meta_records_the_audio_as_an_absolute_path(tmp_path, monkeypatch):
    """§11.11: `align` stores the path *as it was given*, so a staging
    directory records `../../songs/audio/pimiento.m4a` — which resolves
    only from the directory that run happened in. Copy the directory and
    the player has nothing. The sibling records where the take actually
    is."""
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"bytes")
    monkeypatch.chdir(tmp_path)
    provenance = build_provenance(Path("a.wav"), model_size="medium", lang="es")

    meta = words_meta(provenance, Path("a.wav"))

    assert provenance["audio"] == "a.wav", "the run still records what it was given"
    assert Path(meta["audio"]).is_absolute()
    assert Path(meta["audio"]).resolve() == audio.resolve()


def test_reusing_words_carries_the_original_time_forward_rather_than_stamping(tmp_path):
    """The bug: on a `--words` run faster-whisper never runs, and the
    report claimed the machine listened at the moment the report was
    written. §9.4 makes reusing the word stream *the* correction loop, so
    that is most runs, not an edge case."""
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"bytes")
    fresh = build_provenance(audio, model_size="tiny", lang="nl")
    meta = {
        "extractedAt": "2026-08-14T20:55:00+02:00",
        "model": "faster-whisper:medium",
        "device": "cpu/int8",
        "lang": "es",
        "sha256": "ab" * 32,
        "audio": str(audio),
    }

    carried = provenance_for_reused_words(fresh, meta)

    assert carried["extractedAt"] == "2026-08-14T20:55:00+02:00"
    assert carried["model"] == "faster-whisper:medium"
    assert carried["device"] == "cpu/int8"
    assert carried["lang"] == "es"
    assert carried["wordsReused"] is True


def test_reusing_words_still_describes_the_audio_this_run_was_pointed_at(tmp_path):
    """The four fields carried forward are the four a `--words` run cannot
    establish. `sha256`, `durationSec` and `audio` it *can* — it hashed
    the file it was given — and they are one coherent description of one
    file, which is exactly what B1 exists to record. Splitting them across
    two runs would be the split brain this cleanup deletes elsewhere."""
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"bytes")
    fresh = build_provenance(audio, model_size="tiny", lang="nl")

    carried = provenance_for_reused_words(fresh, {"sha256": "cd" * 32, "audio": "/gone.wav"})

    assert carried["sha256"] == fresh["sha256"]
    assert carried["audio"] == fresh["audio"]
    assert carried["durationSec"] == fresh["durationSec"]


def test_reusing_words_with_no_sibling_omits_the_time_rather_than_inventing_one(tmp_path):
    """An older staging directory has no sibling. A wrong timestamp in an
    audit file is worse than an absent one, and absent is cheap — so the
    field goes, and `wordsReused` says why. Never an mtime: an mtime does
    not survive the directory being copied."""
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"bytes")
    fresh = build_provenance(audio, model_size="medium", lang="es")

    carried = provenance_for_reused_words(fresh, None)

    assert "extractedAt" not in carried
    assert carried["wordsReused"] is True
    assert carried["sha256"] == fresh["sha256"]
