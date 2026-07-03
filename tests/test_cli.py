"""
Tests for the extract/promote CLI (slice S3).

All fast: no whisper model, no audio decoding. `extract` is exercised via
`--words` (a pre-saved JSONL transcription), so transcription is skipped;
the audio argument is a placeholder file that is never read.
"""
import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from timeline_extractor.aligner import save_words
from timeline_extractor.cli import main
from timeline_extractor.models import Word


# ---------------------------------------------------------------------------
# Fixtures — a small song whose words anchor deterministically
# ---------------------------------------------------------------------------

SONG = {
    "title": "Canción de prueba",
    "lyrics": [
        {"type": "section", "label": "Verse 1"},
        {"es": "hola mundo bonito", "en": "hello beautiful world"},
        {"es": "vamos a bailar ahora"},
        "Chorus",
        {"es": "gracias por venir\ny quedarse"},
    ],
    "notes": "keep me intact",
}

WORDS = [
    Word("hola", 10.0, 10.3),
    Word("mundo", 10.3, 10.6),
    Word("bonito", 10.6, 10.9),
    Word("vamos", 20.0, 20.3),
    Word("a", 20.3, 20.4),
    Word("bailar", 20.4, 20.8),
    Word("ahora", 20.8, 21.2),
    Word("gracias", 30.0, 30.3),
    Word("por", 30.3, 30.5),
    Word("venir", 30.5, 30.8),
    Word("y", 31.0, 31.1),
    Word("quedarse", 31.2, 31.8),
]

EXPECTED_TIMELINE = [
    {"start": 0.0, "end": 0.0},      # section marker
    {"start": 10.0, "end": 20.0},
    {"start": 20.0, "end": 30.0},
    {"start": 0.0, "end": 0.0},      # bare-string marker
    {"start": 30.0, "end": 32.8},    # last word end 31.8 + 1.0 pad
]


@pytest.fixture
def workspace(tmp_path):
    audio = tmp_path / "cancion.wav"
    audio.write_bytes(b"")  # never read: --words skips transcription
    song = tmp_path / "cancion-de-prueba.json"
    song.write_text(
        json.dumps(SONG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    words = tmp_path / "words.jsonl"
    save_words(WORDS, words)
    staging = tmp_path / "staging"
    return {"audio": audio, "song": song, "words": words, "staging": staging}


def run_extract(ws, *extra):
    runner = CliRunner()
    return runner.invoke(
        main,
        [
            "extract",
            str(ws["audio"]),
            str(ws["song"]),
            "-o",
            str(ws["staging"]),
            "--words",
            str(ws["words"]),
            *extra,
        ],
    )


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


def test_extract_creates_staging_files_and_expected_timeline(workspace):
    result = run_extract(workspace)

    assert result.exit_code == 0, result.output
    staging = workspace["staging"]
    words_out = staging / "asr-words.jsonl"
    timeline_out = staging / "cancion-de-prueba-timeline.json"
    report_out = staging / "cancion-de-prueba-qa-report.md"

    assert words_out.exists()
    assert words_out.read_text(encoding="utf-8") == workspace["words"].read_text(
        encoding="utf-8"
    )
    assert json.loads(timeline_out.read_text(encoding="utf-8")) == {
        "timeline": EXPECTED_TIMELINE
    }
    assert report_out.exists()


def test_extract_echoes_band_counts_and_paths(workspace):
    result = run_extract(workspace)

    assert result.exit_code == 0, result.output
    assert "HIGH 3" in result.output
    assert "REVIEW 0" in result.output
    assert "FAIL 0" in result.output
    assert "cancion-de-prueba-timeline.json" in result.output
    assert "cancion-de-prueba-qa-report.md" in result.output


def test_extract_never_writes_the_song_json(workspace):
    before = workspace["song"].read_bytes()

    result = run_extract(workspace)

    assert result.exit_code == 0, result.output
    assert workspace["song"].read_bytes() == before


def test_extract_qa_report_contents(workspace):
    # make lyric line 2 unanchorable -> FAIL -> "needs attention" instruction
    song = json.loads(workspace["song"].read_text(encoding="utf-8"))
    song["lyrics"].insert(4, {"es": "palabras inexistentes rarezas"})
    workspace["song"].write_text(
        json.dumps(song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    result = run_extract(workspace)

    assert result.exit_code == 0, result.output
    report = (
        workspace["staging"] / "cancion-de-prueba-qa-report.md"
    ).read_text(encoding="utf-8")

    # header: band counts, model, audio-clock rule
    assert "HIGH 3" in report
    assert "FAIL 1" in report
    assert "medium" in report
    assert "master recording" in report

    # flagged line listed first with a hand-anchoring instruction
    assert "Needs attention" in report
    assert "--anchor 2=" in report
    assert "asr-words.jsonl" in report

    # per-line table carries canonical text and timings
    assert "hola mundo bonito" in report
    assert "palabras inexistentes rarezas" in report


def test_extract_anchor_override_flows_through(workspace):
    result = run_extract(workspace, "--anchor", "1=15.0")

    assert result.exit_code == 0, result.output
    timeline = json.loads(
        (workspace["staging"] / "cancion-de-prueba-timeline.json").read_text(
            encoding="utf-8"
        )
    )["timeline"]
    assert timeline[2]["start"] == 15.0   # lyric line 1 = item index 2
    assert timeline[1]["end"] == 15.0     # previous line's end follows


@pytest.mark.parametrize("bad", ["1", "abc=5.0", "1=abc", "1:5.0", "-1=5.0"])
def test_extract_rejects_malformed_anchor(workspace, bad):
    result = run_extract(workspace, "--anchor", bad)

    assert result.exit_code != 0
    assert "anchor" in result.output.lower()


def test_extract_rejects_out_of_range_anchor_line(workspace):
    result = run_extract(workspace, "--anchor", "99=5.0")

    assert result.exit_code != 0
    assert "99" in result.output


def test_extract_help_carries_the_audio_clock_rule():
    runner = CliRunner()
    result = runner.invoke(main, ["extract", "--help"])

    assert result.exit_code == 0
    assert "ffmpeg" in result.output
    assert "animation video" in result.output
    assert "master recording" in result.output


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

PROMOTE_SONG = {
    "title": "T",
    "lyrics": [{"es": "uno"}, {"es": "dos"}],
    "timeline": [
        {"start": 1.0, "end": 2.0},
        {"start": 2.0, "end": 3.0},
    ],
    "media": {"type": "audio", "src": "x.wav", "offset": 0.5},
}


@pytest.fixture
def promote_ws(tmp_path):
    song = tmp_path / "song.json"
    song.write_text(
        json.dumps(PROMOTE_SONG, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    timeline = tmp_path / "song-timeline.json"
    timeline.write_text(
        json.dumps(
            {
                "timeline": [
                    {"start": 1.0, "end": 2.0},
                    {"start": 2.5, "end": 3.5},
                ]
            }
        ),
        encoding="utf-8",
    )
    return {"song": song, "timeline": timeline, "dir": tmp_path}


def run_promote(ws):
    runner = CliRunner()
    return runner.invoke(main, ["promote", str(ws["timeline"]), str(ws["song"])])


def test_promote_replaces_only_timeline_preserving_key_order(promote_ws):
    result = run_promote(promote_ws)

    assert result.exit_code == 0, result.output
    updated = json.loads(promote_ws["song"].read_text(encoding="utf-8"))
    assert list(updated.keys()) == ["title", "lyrics", "timeline", "media"]
    assert updated["title"] == PROMOTE_SONG["title"]
    assert updated["lyrics"] == PROMOTE_SONG["lyrics"]
    assert updated["media"] == PROMOTE_SONG["media"]
    assert updated["timeline"] == [
        {"start": 1.0, "end": 2.0},
        {"start": 2.5, "end": 3.5},
    ]
    # file ends with a trailing newline
    assert promote_ws["song"].read_text(encoding="utf-8").endswith("\n")


def test_promote_backs_up_original_before_writing(promote_ws):
    original = promote_ws["song"].read_bytes()

    result = run_promote(promote_ws)

    assert result.exit_code == 0, result.output
    backups = list(promote_ws["dir"].glob("song.json.backup-*"))
    assert len(backups) == 1
    assert re.search(r"backup-\d{8}-\d{6}$", backups[0].name)
    assert backups[0].read_bytes() == original
    assert str(backups[0]) in result.output


def test_promote_diff_mentions_only_changed_lines(promote_ws):
    result = run_promote(promote_ws)

    assert result.exit_code == 0, result.output
    assert "line 1:" in result.output
    assert "line 0:" not in result.output


def test_promote_reports_timeline_added_when_none_existed(promote_ws):
    song = json.loads(promote_ws["song"].read_text(encoding="utf-8"))
    del song["timeline"]
    promote_ws["song"].write_text(
        json.dumps(song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    result = run_promote(promote_ws)

    assert result.exit_code == 0, result.output
    assert "timeline added" in result.output
    updated = json.loads(promote_ws["song"].read_text(encoding="utf-8"))
    assert updated["timeline"] == [
        {"start": 1.0, "end": 2.0},
        {"start": 2.5, "end": 3.5},
    ]


def test_promote_refuses_length_mismatch(promote_ws):
    promote_ws["timeline"].write_text(
        json.dumps({"timeline": [{"start": 1.0, "end": 2.0}]}), encoding="utf-8"
    )
    before = promote_ws["song"].read_bytes()

    result = run_promote(promote_ws)

    assert result.exit_code != 0
    assert "1" in result.output and "2" in result.output  # both lengths named
    assert promote_ws["song"].read_bytes() == before
    assert list(promote_ws["dir"].glob("song.json.backup-*")) == []


def test_promote_refuses_invalid_timeline(promote_ws):
    promote_ws["timeline"].write_text(
        json.dumps(
            {
                "timeline": [
                    {"start": 5.0, "end": 8.0},
                    {"start": 4.0, "end": 9.0},  # non-monotonic
                ]
            }
        ),
        encoding="utf-8",
    )
    before = promote_ws["song"].read_bytes()

    result = run_promote(promote_ws)

    assert result.exit_code != 0
    assert promote_ws["song"].read_bytes() == before


def test_promote_refuses_non_numeric_entries(promote_ws):
    promote_ws["timeline"].write_text(
        json.dumps(
            {
                "timeline": [
                    {"start": "1.0", "end": 2.0},
                    {"start": 2.5, "end": 3.5},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_promote(promote_ws)

    assert result.exit_code != 0
