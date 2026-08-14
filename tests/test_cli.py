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
from timeline_extractor.provenance import compute_lines_hash


# ---------------------------------------------------------------------------
# Fixtures — a small song whose words anchor deterministically
# ---------------------------------------------------------------------------

SONG = {
    "title": "Canción de prueba",
    "lyrics": [
        {"es": "hola mundo bonito", "en": "hello beautiful world"},
        {"es": "vamos a bailar ahora"},
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
    {"start": 10.0, "end": 20.0},
    {"start": 20.0, "end": 30.0},
    {"start": 30.0, "end": 32.8},    # last word end 31.8 + 1.0 pad
]

# Timeline v2 envelope: normalised relative to lead_in = raw entry 0's
# start (10.0). media is absent from SONG -> leadIn.apply is false.
EXPECTED_ENVELOPE = {
    "timelineVersion": 2,
    "leadIn": {
        "durationSec": 10.0,
        "source": "measured",
        "confidence": "low",
        "apply": False,
    },
    "timeline": [
        {"start": 0.0, "end": 10.0},
        {"start": 10.0, "end": 20.0},
        {"start": 20.0, "end": 22.8},
    ],
}


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
    assert json.loads(timeline_out.read_text(encoding="utf-8")) == EXPECTED_ENVELOPE
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
    song["lyrics"].insert(2, {"es": "palabras inexistentes rarezas"})
    workspace["song"].write_text(
        json.dumps(song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    result = run_extract(workspace)

    assert result.exit_code == 0, result.output
    report = (
        workspace["staging"] / "cancion-de-prueba-qa-report.md"
    ).read_text(encoding="utf-8")

    # header: band counts, model, audio-clock rule, measured lead-in
    assert "HIGH 3" in report
    assert "FAIL 1" in report
    assert "medium" in report
    assert "master recording" in report
    assert "Measured lead-in" in report
    # the header times are raw audio-clock (10.00 s, first word's onset),
    # not normalised — normalising the report would break --anchor's
    # audio-clock hand-fix loop
    assert "10.00" in report

    # flagged line listed first with a hand-anchoring instruction
    assert "Needs attention" in report
    assert "--anchor 2=" in report
    assert "asr-words.jsonl" in report

    # per-line table carries canonical text and timings
    assert "hola mundo bonito" in report
    assert "palabras inexistentes rarezas" in report


def test_extract_anchor_override_flows_through(workspace):
    """--anchor is given in raw audio-clock seconds; the emitted timeline is
    normalised relative to lead_in (line 0's raw start, unaffected here)."""
    result = run_extract(workspace, "--anchor", "1=15.0")

    assert result.exit_code == 0, result.output
    envelope = json.loads(
        (workspace["staging"] / "cancion-de-prueba-timeline.json").read_text(
            encoding="utf-8"
        )
    )
    assert envelope["leadIn"]["durationSec"] == 10.0  # line 0 still raw 10.0
    timeline = envelope["timeline"]
    assert timeline[1]["start"] == 5.0    # raw 15.0 - lead_in 10.0
    assert timeline[0]["end"] == 5.0      # previous line's end follows


@pytest.mark.parametrize("bad", ["1", "abc=5.0", "1=abc", "1:5.0", "-1=5.0"])
def test_extract_rejects_malformed_anchor(workspace, bad):
    result = run_extract(workspace, "--anchor", bad)

    assert result.exit_code != 0
    assert "anchor" in result.output.lower()


def test_extract_rejects_out_of_range_anchor_line(workspace):
    result = run_extract(workspace, "--anchor", "99=5.0")

    assert result.exit_code != 0
    assert "99" in result.output


def test_extract_fails_loudly_on_section_marker_naming_its_index(workspace):
    """Section markers are no longer supported — a non-lyric entry in the
    song's `lyrics` array must fail loudly through the CLI, naming the
    offending index, rather than being silently skipped."""
    song = json.loads(workspace["song"].read_text(encoding="utf-8"))
    song["lyrics"].insert(1, {"type": "section", "label": "Bridge"})
    workspace["song"].write_text(
        json.dumps(song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    result = run_extract(workspace)

    assert result.exit_code != 0
    assert "lyrics[1]" in result.output
    assert "not a lyric line" in result.output


def test_extract_fails_loudly_on_bare_string_entry_naming_its_index(workspace):
    song = json.loads(workspace["song"].read_text(encoding="utf-8"))
    song["lyrics"].append("Outro")
    workspace["song"].write_text(
        json.dumps(song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    result = run_extract(workspace)

    assert result.exit_code != 0
    assert "lyrics[3]" in result.output
    assert "not a lyric line" in result.output


def test_extract_report_shows_which_audio_was_used_and_sha256_differs_by_audio(workspace):
    """B1 acceptance #1: two runs against different audio files for the
    same song produce different sha256 values, and the report header shows
    which audio was used. --words (the committed fixture words) means
    neither run actually transcribes — this is exactly the case where the
    sha256 has to earn its keep, since nothing else distinguishes the
    audio files from Bombista's point of view."""
    audio_a = workspace["audio"]
    audio_a.write_bytes(b"audio file A content")
    audio_b = workspace["staging"].parent / "other-audio.wav"
    audio_b.write_bytes(b"a completely different audio file B")

    result_a = run_extract(workspace)
    assert result_a.exit_code == 0, result_a.output
    report_a = (
        workspace["staging"] / "cancion-de-prueba-qa-report.md"
    ).read_text(encoding="utf-8")

    workspace["audio"] = audio_b
    workspace["staging"] = workspace["staging"].parent / "staging-b"
    result_b = run_extract(workspace)
    assert result_b.exit_code == 0, result_b.output
    report_b = (
        workspace["staging"] / "cancion-de-prueba-qa-report.md"
    ).read_text(encoding="utf-8")

    sha_line_a = next(line for line in report_a.splitlines() if "sha256" in line.lower())
    sha_line_b = next(line for line in report_b.splitlines() if "sha256" in line.lower())
    assert sha_line_a != sha_line_b

    assert str(audio_a) in report_a
    assert str(audio_b) in report_b


def test_extract_native_envelope_has_exactly_three_top_level_keys(workspace):
    """B1 must not leak provenance into the native timeline envelope — the
    translator parses it strictly (docs/timeline-v2-contract.md)."""
    result = run_extract(workspace)
    assert result.exit_code == 0, result.output

    envelope = json.loads(
        (workspace["staging"] / "cancion-de-prueba-timeline.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(envelope.keys()) == {"timelineVersion", "leadIn", "timeline"}


def test_extract_succeeds_with_null_duration_for_unreadable_audio_container(workspace):
    """B1 acceptance #3: durationSec must be null-but-present (never crash
    the run) when the "audio" file's container can't be read by PyAV —
    --words means transcription never touches it either, so this is purely
    exercising the provenance duration probe."""
    workspace["audio"].write_bytes(b"this is not a real media container")

    result = run_extract(workspace)

    assert result.exit_code == 0, result.output
    report = (
        workspace["staging"] / "cancion-de-prueba-qa-report.md"
    ).read_text(encoding="utf-8")
    assert "None" not in report.split("## Needs attention")[0]


def test_extract_help_carries_the_audio_clock_rule():
    runner = CliRunner()
    result = runner.invoke(main, ["extract", "--help"])

    assert result.exit_code == 0
    assert "ffmpeg" in result.output
    assert "animation video" in result.output
    assert "master recording" in result.output


# ---------------------------------------------------------------------------
# extract — plain-text lyrics input (B5)
# ---------------------------------------------------------------------------

PLAIN_TEXT_LYRICS = "[Intro]\n\nhola mundo bonito\n\nvamos a bailar ahora\n"

# Same WORDS fixture as the JSON-song tests above -> line 0 anchors at
# 10.0 (raw), line 1 at 20.0; last word ends 31.8 -> line 1's fallback end
# is 31.8 + 1.0 pad = 32.8 (raw). Normalised relative to lead_in = 10.0.
EXPECTED_PLAIN_TEXT_ENVELOPE = {
    "timelineVersion": 2,
    "leadIn": {
        "durationSec": 10.0,
        "source": "measured",
        "confidence": "low",
        "apply": False,
    },
    "timeline": [
        {"start": 0.0, "end": 10.0},
        {"start": 10.0, "end": 22.8},
    ],
}


def test_extract_accepts_plain_text_lyrics_input_and_produces_valid_v2_envelope(tmp_path):
    """Acceptance #5: extract driven through the CLI on a plain .txt lyrics
    file (not a CP song JSON) produces a valid, contract-passing v2
    envelope, and the QA report surfaces what the reader stripped."""
    from timeline_extractor.serializer import validate_v2_envelope

    audio = tmp_path / "cancion.wav"
    audio.write_bytes(b"")  # never read: --words skips transcription
    lyrics_txt = tmp_path / "cancion-de-prueba.txt"
    lyrics_txt.write_text(PLAIN_TEXT_LYRICS, encoding="utf-8")
    words = tmp_path / "words.jsonl"
    save_words(WORDS, words)
    staging = tmp_path / "staging"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "extract",
            str(audio),
            str(lyrics_txt),
            "-o",
            str(staging),
            "--words",
            str(words),
        ],
    )

    assert result.exit_code == 0, result.output
    envelope = json.loads(
        (staging / "cancion-de-prueba-timeline.json").read_text(encoding="utf-8")
    )
    validate_v2_envelope(envelope)  # raises on any contract violation
    assert envelope == EXPECTED_PLAIN_TEXT_ENVELOPE

    report = (staging / "cancion-de-prueba-qa-report.md").read_text(encoding="utf-8")
    assert "Stripped lines" in report
    assert "[Intro]" in report
    assert "bracketed" in report
    assert "blank" in report


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

LEAD_IN = {"durationSec": 1.0, "source": "measured", "confidence": "low", "apply": False}

# The song on disk is still v1-shaped pre-migration: a bare `timeline` list,
# no `timelineVersion`/`leadIn` keys (B13, the data migration, is gated).
PROMOTE_SONG = {
    "title": "T",
    "lyrics": [{"es": "uno"}, {"es": "dos"}],
    "timeline": [
        {"start": 0.0, "end": 1.0},
        {"start": 2.0, "end": 3.0},
    ],
    "media": {"type": "audio", "src": "x.wav", "offset": 0.5},
}

# The promote candidate is always a v2 envelope.
PROMOTE_ENVELOPE = {
    "timelineVersion": 2,
    "leadIn": LEAD_IN,
    "timeline": [
        {"start": 0.0, "end": 1.0},
        {"start": 1.5, "end": 2.5},
    ],
}


@pytest.fixture
def promote_ws(tmp_path):
    song = tmp_path / "song.json"
    song.write_text(
        json.dumps(PROMOTE_SONG, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    timeline = tmp_path / "song-timeline.json"
    timeline.write_text(json.dumps(PROMOTE_ENVELOPE), encoding="utf-8")
    return {"song": song, "timeline": timeline, "dir": tmp_path}


def run_promote(ws):
    runner = CliRunner()
    return runner.invoke(main, ["promote", str(ws["timeline"]), str(ws["song"])])


def test_promote_writes_envelope_preserving_other_key_order(promote_ws):
    result = run_promote(promote_ws)

    assert result.exit_code == 0, result.output
    updated = json.loads(promote_ws["song"].read_text(encoding="utf-8"))
    assert list(updated.keys()) == [
        "title",
        "lyrics",
        "timelineVersion",
        "leadIn",
        "timeline",
        "media",
    ]
    assert updated["title"] == PROMOTE_SONG["title"]
    assert updated["lyrics"] == PROMOTE_SONG["lyrics"]
    assert updated["media"] == PROMOTE_SONG["media"]
    assert updated["timelineVersion"] == 2
    assert updated["leadIn"] == LEAD_IN
    assert updated["timeline"] == PROMOTE_ENVELOPE["timeline"]
    # file ends with a trailing newline
    assert promote_ws["song"].read_text(encoding="utf-8").endswith("\n")


def test_promote_leaves_no_temp_file_behind(promote_ws):
    """The song file is replaced atomically so an interrupted write can't
    leave a half-stamped song on disk — and the scratch file it goes through
    must not survive the run."""
    result = run_promote(promote_ws)

    assert result.exit_code == 0, result.output
    leftovers = [p.name for p in promote_ws["song"].parent.glob("*.tmp-*")]
    assert leftovers == []


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
    assert updated["timeline"] == PROMOTE_ENVELOPE["timeline"]
    assert updated["timelineVersion"] == 2
    assert updated["leadIn"] == LEAD_IN


def test_promote_refuses_length_mismatch(promote_ws):
    promote_ws["timeline"].write_text(
        json.dumps(
            {
                "timelineVersion": 2,
                "leadIn": LEAD_IN,
                "timeline": [{"start": 0.0, "end": 2.0}],
            }
        ),
        encoding="utf-8",
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
                "timelineVersion": 2,
                "leadIn": LEAD_IN,
                "timeline": [
                    {"start": 0.0, "end": 8.0},
                    {"start": 4.0, "end": 9.0},  # non-monotonic
                ],
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
                "timelineVersion": 2,
                "leadIn": LEAD_IN,
                "timeline": [
                    {"start": "0.0", "end": 1.0},
                    {"start": 1.5, "end": 2.5},
                ],
            }
        ),
        encoding="utf-8",
    )
    before = promote_ws["song"].read_bytes()

    result = run_promote(promote_ws)

    assert result.exit_code != 0
    assert promote_ws["song"].read_bytes() == before


def test_promote_rejects_v1_candidate_missing_timeline_version(promote_ws):
    """A v1-shaped candidate (`{"timeline": [...]}`, no `timelineVersion`)
    must be rejected loudly — never coerced to v2 — leaving the song file
    untouched and no backup created."""
    promote_ws["timeline"].write_text(
        json.dumps(
            {
                "timeline": [
                    {"start": 0.0, "end": 1.0},
                    {"start": 1.5, "end": 2.5},
                ]
            }
        ),
        encoding="utf-8",
    )
    before = promote_ws["song"].read_bytes()

    result = run_promote(promote_ws)

    assert result.exit_code != 0
    assert "timelineVersion" in result.output
    assert promote_ws["song"].read_bytes() == before
    assert list(promote_ws["dir"].glob("song.json.backup-*")) == []


def test_promote_rejects_non_2_timeline_version(promote_ws):
    promote_ws["timeline"].write_text(
        json.dumps({**PROMOTE_ENVELOPE, "timelineVersion": 1}),
        encoding="utf-8",
    )
    before = promote_ws["song"].read_bytes()

    result = run_promote(promote_ws)

    assert result.exit_code != 0
    assert "timelineVersion" in result.output
    assert promote_ws["song"].read_bytes() == before
    assert list(promote_ws["dir"].glob("song.json.backup-*")) == []


# ---------------------------------------------------------------------------
# --emit (B2)
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"
LIBERTAD_SONG_FIXTURE = FIXTURES / "libertad-song.json"


def test_extract_default_emit_only_writes_timeline_not_other_outputs(workspace):
    """Default behaviour with no --emit must be exactly what happens
    today: only timeline.json (plus the always-on words/report)."""
    result = run_extract(workspace)

    assert result.exit_code == 0, result.output
    staging = workspace["staging"]
    assert (staging / "cancion-de-prueba-timeline.json").exists()
    assert not (staging / "cancion-de-prueba-song.json").exists()
    assert not (staging / "cancion-de-prueba-report.json").exists()
    assert not list(staging.glob("*.srt"))
    assert not list(staging.glob("*.lrc"))


def test_extract_emit_replaces_default_set_not_adds_to_it(workspace):
    """Passing --emit explicitly REPLACES the default set."""
    result = run_extract(workspace, "--emit", "songjson")

    assert result.exit_code == 0, result.output
    staging = workspace["staging"]
    assert (staging / "cancion-de-prueba-song.json").exists()
    assert not (staging / "cancion-de-prueba-timeline.json").exists()


def test_extract_emit_repeatable_writes_each_requested_target(workspace):
    result = run_extract(workspace, "--emit", "timeline", "--emit", "songjson")

    assert result.exit_code == 0, result.output
    staging = workspace["staging"]
    assert (staging / "cancion-de-prueba-timeline.json").exists()
    assert (staging / "cancion-de-prueba-song.json").exists()


def test_extract_words_and_report_always_written_regardless_of_emit(workspace):
    result = run_extract(workspace, "--emit", "songjson")

    assert result.exit_code == 0, result.output
    staging = workspace["staging"]
    assert (staging / "asr-words.jsonl").exists()
    assert (staging / "cancion-de-prueba-qa-report.md").exists()


def test_extract_help_documents_emit_replaces_default():
    runner = CliRunner()
    result = runner.invoke(main, ["extract", "--help"])

    assert result.exit_code == 0
    assert "--emit" in result.output
    assert "replaces" in result.output.lower()


def test_extract_emit_songjson_round_trips_libertad_fixture_non_timeline_fields(tmp_path):
    """Acceptance #1: --emit songjson on Libertad round-trips every
    non-timeline field byte-identically (values AND order)."""
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"")  # never read: --words skips transcription
    song_path = tmp_path / "libertad.json"
    song_path.write_text(LIBERTAD_SONG_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    words = tmp_path / "words.jsonl"
    words.write_text("", encoding="utf-8")  # no words needed: only non-timeline fields checked
    staging = tmp_path / "staging"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "extract",
            str(audio),
            str(song_path),
            "-o",
            str(staging),
            "--words",
            str(words),
            "--emit",
            "songjson",
        ],
    )
    assert result.exit_code == 0, result.output

    original = json.loads(LIBERTAD_SONG_FIXTURE.read_text(encoding="utf-8"))
    emitted = json.loads((staging / "libertad-song.json").read_text(encoding="utf-8"))

    reserved = {"timelineVersion", "leadIn", "timeline", "_bombista"}
    original_keys = [k for k in original if k not in reserved]
    emitted_keys = [k for k in emitted if k not in reserved]
    assert emitted_keys == original_keys
    for key in original_keys:
        assert emitted[key] == original[key]
        assert json.dumps(emitted[key], ensure_ascii=False) == json.dumps(
            original[key], ensure_ascii=False
        )

    assert emitted["_bombista"]["completeness"] == "complete"
    assert emitted["_bombista"]["source"]["audio"] == str(audio)


def test_extract_emit_srt_one_file_per_language_key(workspace):
    result = run_extract(workspace, "--emit", "srt")

    assert result.exit_code == 0, result.output
    staging = workspace["staging"]
    assert (staging / "cancion-de-prueba-es.srt").exists()
    assert (staging / "cancion-de-prueba-en.srt").exists()
    assert "hola mundo bonito" in (staging / "cancion-de-prueba-es.srt").read_text(encoding="utf-8")
    assert "hello beautiful world" in (staging / "cancion-de-prueba-en.srt").read_text(
        encoding="utf-8"
    )


def test_extract_emit_srt_excludes_lead_in_when_apply_false(workspace):
    """SONG has no `media` -> leadIn.apply defaults to False -> subtitle
    times are cue-relative, unshifted."""
    result = run_extract(workspace, "--emit", "srt")

    assert result.exit_code == 0, result.output
    content = (workspace["staging"] / "cancion-de-prueba-es.srt").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:10,000" in content


def test_extract_emit_srt_includes_lead_in_when_apply_true(workspace):
    """`media.type == "video"` -> leadIn.apply True -> the lead-in (10.0 s,
    line 0's raw onset) is added back into the subtitle times."""
    song = json.loads(workspace["song"].read_text(encoding="utf-8"))
    song["media"] = {"type": "video", "src": "x.mp4"}
    workspace["song"].write_text(
        json.dumps(song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    result = run_extract(workspace, "--emit", "srt")

    assert result.exit_code == 0, result.output
    content = (workspace["staging"] / "cancion-de-prueba-es.srt").read_text(encoding="utf-8")
    assert "00:00:10,000 --> 00:00:20,000" in content


def test_extract_emit_lrc_writes_files_with_tags(workspace):
    result = run_extract(workspace, "--emit", "lrc")

    assert result.exit_code == 0, result.output
    staging = workspace["staging"]
    assert (staging / "cancion-de-prueba-es.lrc").exists()
    assert (staging / "cancion-de-prueba-en.lrc").exists()
    content = (staging / "cancion-de-prueba-es.lrc").read_text(encoding="utf-8")
    assert "[ti:Canción de prueba]" in content


def test_extract_emit_report_json_produces_expected_shape(workspace):
    result = run_extract(workspace, "--emit", "report-json")

    assert result.exit_code == 0, result.output
    data = json.loads(
        (workspace["staging"] / "cancion-de-prueba-report.json").read_text(encoding="utf-8")
    )
    assert set(data.keys()) == {"source", "linesHash", "leadIn", "summary", "lines"}
    assert data["summary"] == {"high": 3, "review": 0, "fail": 0}
    assert len(data["lines"]) == 3
    assert data["linesHash"].startswith("sha256:")


# ---------------------------------------------------------------------------
# promote — refuses a partial candidate over a complete target (B2)
# ---------------------------------------------------------------------------

_REFUSAL_TARGET = {
    "title": "T",
    "lyrics": [{"es": "uno"}, {"es": "dos"}],
    "timeline": [{"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 3.0}],
    "media": {"type": "audio", "src": "x.wav"},  # a MISSING_CP_FIELDS field -> "complete"
}

_PARTIAL_CANDIDATE = {
    "title": "T",
    "lyrics": [{"es": "uno"}, {"es": "dos"}],
    "timelineVersion": 2,
    "leadIn": {"durationSec": 1.0, "source": "measured", "confidence": "low", "apply": False},
    "timeline": [{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 2.0}],
    "_bombista": {
        "completeness": "partial",
        "filledLang": "es",
        "missing": ["artist", "tempo", "media"],
        "strippedLines": [],
    },
}

_COMPLETE_CANDIDATE = {
    **{k: v for k, v in _PARTIAL_CANDIDATE.items() if k != "_bombista"},
    "_bombista": {"completeness": "complete"},
}


def test_promote_refuses_partial_candidate_over_complete_target(tmp_path):
    song_path = tmp_path / "song.json"
    song_path.write_text(
        json.dumps(_REFUSAL_TARGET, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(_PARTIAL_CANDIDATE, indent=2), encoding="utf-8")
    before = song_path.read_bytes()

    runner = CliRunner()
    result = runner.invoke(main, ["promote", str(candidate_path), str(song_path)])

    assert result.exit_code != 0
    assert "partial" in result.output.lower()
    assert "complete" in result.output.lower()
    assert song_path.read_bytes() == before
    assert list(tmp_path.glob("song.json.backup-*")) == []


def test_promote_succeeds_with_complete_candidate_over_complete_target(tmp_path):
    """Normal case: still succeeds when both sides are complete."""
    song_path = tmp_path / "song.json"
    song_path.write_text(
        json.dumps(_REFUSAL_TARGET, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(_COMPLETE_CANDIDATE, indent=2), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["promote", str(candidate_path), str(song_path)])

    assert result.exit_code == 0, result.output
    updated = json.loads(song_path.read_text(encoding="utf-8"))
    assert updated["timeline"] == _COMPLETE_CANDIDATE["timeline"]


def test_promote_never_refuses_a_bare_v2_envelope_candidate(promote_ws):
    """A bare envelope carries no completeness information, so no refusal
    is ever possible against it — regression against the existing
    promote_ws fixture, whose target song is "complete" (it has `media`)."""
    result = run_promote(promote_ws)
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# One merge path only (B2)
# ---------------------------------------------------------------------------


def test_exactly_one_merge_implementation_in_the_repo():
    import ast

    import timeline_extractor

    pkg_dir = Path(timeline_extractor.__file__).parent
    count = 0
    for py_file in pkg_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        count += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "merge_envelope"
        )
    assert count == 1
    assert "_apply_envelope" not in (pkg_dir / "cli.py").read_text(encoding="utf-8")


def test_promote_and_songjson_writer_produce_the_same_merged_result(promote_ws):
    """Acceptance #5: promote and the songjson writer produce the same
    merged result for the same inputs — because they call the same
    function."""
    from timeline_extractor.writers import merge_envelope

    result = run_promote(promote_ws)
    assert result.exit_code == 0, result.output
    via_promote = json.loads(promote_ws["song"].read_text(encoding="utf-8"))

    via_writer = merge_envelope(PROMOTE_SONG, PROMOTE_ENVELOPE)

    assert via_promote["timelineVersion"] == via_writer["timelineVersion"]
    assert via_promote["leadIn"] == via_writer["leadIn"]
    assert via_promote["timeline"] == via_writer["timeline"]
    assert list(via_promote.keys()) == list(via_writer.keys())


# ---------------------------------------------------------------------------
# promote — linesHash guard (B4)
# ---------------------------------------------------------------------------

HASH_SONG = {
    "title": "T",
    "lyrics": [{"es": "uno"}, {"es": "dos"}, {"es": "tres"}],
    "media": {"type": "audio", "src": "x.wav"},
}
HASH_SONG_LINES_HASH = compute_lines_hash(["uno", "dos", "tres"])

HASH_ENVELOPE = {
    "timelineVersion": 2,
    "leadIn": {"durationSec": 1.0, "source": "measured", "confidence": "low", "apply": False},
    "timeline": [
        {"start": 0.0, "end": 1.0},
        {"start": 1.0, "end": 2.0},
        {"start": 2.0, "end": 3.0},
    ],
}


def _songjson_candidate(lines_hash, lang="es"):
    return {
        **HASH_SONG,
        **HASH_ENVELOPE,
        "_bombista": {
            "completeness": "complete",
            "source": {"lang": lang, "audio": "x.wav"},
            "linesHash": lines_hash,
        },
    }


def test_promote_linesHash_guard_no_warning_when_target_lyrics_unchanged(tmp_path):
    """Acceptance #2: an unchanged target produces no warning."""
    song_path = tmp_path / "song.json"
    song_path.write_text(json.dumps(HASH_SONG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    candidate_path = tmp_path / "song-song.json"
    candidate_path.write_text(
        json.dumps(_songjson_candidate(HASH_SONG_LINES_HASH), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["promote", str(candidate_path), str(song_path)])

    assert result.exit_code == 0, result.output
    assert "WARNING" not in result.stderr
    assert "could not be checked" not in result.stderr
    updated = json.loads(song_path.read_text(encoding="utf-8"))
    assert updated["timeline"] == HASH_ENVELOPE["timeline"]


def test_promote_linesHash_guard_warns_loudly_on_mismatch_and_still_promotes(tmp_path):
    """Acceptance #1: editing one lyric line in the target song and then
    promoting an older timeline produces the warning, and the promotion
    still completes — assert both the stderr warning AND the song file
    actually being updated."""
    edited_song = json.loads(json.dumps(HASH_SONG))
    edited_song["lyrics"][1] = {"es": "dos-editado"}  # one line changed after extraction
    song_path = tmp_path / "song.json"
    song_path.write_text(json.dumps(edited_song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    candidate_path = tmp_path / "song-song.json"
    candidate_path.write_text(
        # candidate's linesHash was computed from the ORIGINAL lyrics
        json.dumps(_songjson_candidate(HASH_SONG_LINES_HASH), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["promote", str(candidate_path), str(song_path)])

    assert result.exit_code == 0, result.output  # a warning, NOT an error
    assert "WARNING" in result.stderr
    assert "lyrics changed" in result.stderr.lower() or "lyrics changed since" in result.stderr.lower()
    assert "position" in result.stderr.lower()
    assert "re-run" in result.stderr.lower() and "extract" in result.stderr.lower()

    # the promotion still completed
    updated = json.loads(song_path.read_text(encoding="utf-8"))
    assert updated["timeline"] == HASH_ENVELOPE["timeline"]
    assert updated["timelineVersion"] == 2


def test_promote_linesHash_guard_reads_hash_from_sibling_report_json(tmp_path):
    """Acceptance #4 (part 1): when the candidate is a bare v2 envelope (no
    _bombista), promote falls back to the sibling
    <stem>-timeline.json -> <stem>-report.json rich JSON for the hash."""
    edited_song = json.loads(json.dumps(HASH_SONG))
    edited_song["lyrics"][2] = {"es": "tres-editado"}
    song_path = tmp_path / "song.json"
    song_path.write_text(json.dumps(edited_song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    candidate_path = tmp_path / "cancion-timeline.json"
    candidate_path.write_text(json.dumps(HASH_ENVELOPE, indent=2), encoding="utf-8")
    sibling_report = tmp_path / "cancion-report.json"
    sibling_report.write_text(
        json.dumps({"source": {"lang": "es"}, "linesHash": HASH_SONG_LINES_HASH}, indent=2),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["promote", str(candidate_path), str(song_path)])

    assert result.exit_code == 0, result.output
    assert "WARNING" in result.stderr
    updated = json.loads(song_path.read_text(encoding="utf-8"))
    assert updated["timeline"] == HASH_ENVELOPE["timeline"]


def test_promote_linesHash_guard_prints_could_not_be_checked_when_no_hash_available(tmp_path):
    """Acceptance #4 (part 2): a bare envelope with no sibling rich JSON
    prints the "could not be checked" note rather than skipping quietly,
    and still promotes."""
    song_path = tmp_path / "song.json"
    song_path.write_text(json.dumps(HASH_SONG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    candidate_path = tmp_path / "cancion-timeline.json"
    candidate_path.write_text(json.dumps(HASH_ENVELOPE, indent=2), encoding="utf-8")
    # no cancion-report.json sibling written

    runner = CliRunner()
    result = runner.invoke(main, ["promote", str(candidate_path), str(song_path)])

    assert result.exit_code == 0, result.output
    assert "could not be checked" in result.stderr.lower()
    assert "--emit report-json" in result.stderr or "--emit songjson" in result.stderr
    assert "WARNING" not in result.stderr
    updated = json.loads(song_path.read_text(encoding="utf-8"))
    assert updated["timeline"] == HASH_ENVELOPE["timeline"]


def test_promote_linesHash_guard_says_so_when_the_target_lines_cannot_be_read(tmp_path):
    """The guard can't recompute a hash from a song whose lyrics aren't all
    lyric lines. It must say so — a skipped check must never look like a
    clean one."""
    broken_song = json.loads(json.dumps(HASH_SONG))
    broken_song["lyrics"][1] = {"type": "section", "label": "Bridge"}
    song_path = tmp_path / "song.json"
    song_path.write_text(json.dumps(broken_song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    candidate_path = tmp_path / "cancion-timeline.json"
    candidate_path.write_text(json.dumps(HASH_ENVELOPE, indent=2), encoding="utf-8")
    sibling = tmp_path / "cancion-report.json"
    sibling.write_text(
        json.dumps({"linesHash": "sha256:deadbeef", "source": {"lang": "es"}}),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["promote", str(candidate_path), str(song_path)])

    assert result.exit_code == 0, result.output
    assert "could not be checked" in result.stderr.lower()
    assert "lyrics[1]" in result.stderr
    assert "WARNING" not in result.stderr


def test_promote_linesHash_guard_falls_back_to_default_lang_when_source_lang_absent(tmp_path):
    """Documented fallback: when the sibling rich JSON carries no
    `source.lang`, promote still recomputes using the default (`es`,
    matching `extract --lang`'s own default) rather than skipping the
    guard."""
    edited_song = json.loads(json.dumps(HASH_SONG))
    edited_song["lyrics"][0] = {"es": "uno-editado"}
    song_path = tmp_path / "song.json"
    song_path.write_text(json.dumps(edited_song, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    candidate_path = tmp_path / "cancion-timeline.json"
    candidate_path.write_text(json.dumps(HASH_ENVELOPE, indent=2), encoding="utf-8")
    sibling_report = tmp_path / "cancion-report.json"
    # no "source" key at all -> lang must fall back
    sibling_report.write_text(json.dumps({"linesHash": HASH_SONG_LINES_HASH}), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["promote", str(candidate_path), str(song_path)])

    assert result.exit_code == 0, result.output
    assert "WARNING" in result.stderr


def test_promote_linesHash_never_leaks_into_the_song_top_level_keys(tmp_path):
    """Acceptance #5: promoting a songjson candidate (whose _bombista
    carries linesHash) must never leak `linesHash` into the target song's
    top-level keys — merge_envelope only ever touches the three envelope
    keys."""
    song_path = tmp_path / "song.json"
    song_path.write_text(json.dumps(HASH_SONG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    candidate_path = tmp_path / "song-song.json"
    candidate_path.write_text(
        json.dumps(_songjson_candidate(HASH_SONG_LINES_HASH), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["promote", str(candidate_path), str(song_path)])

    assert result.exit_code == 0, result.output
    updated = json.loads(song_path.read_text(encoding="utf-8"))
    assert "linesHash" not in updated
    assert "_bombista" not in updated


def test_extract_native_envelope_never_carries_linesHash(workspace):
    """Acceptance #5 (extract side): the native v2 envelope
    (`--emit timeline`, the default) still has exactly the three top-level
    keys — linesHash must not leak into it even though it's now computed
    every run."""
    result = run_extract(workspace)

    assert result.exit_code == 0, result.output
    envelope = json.loads(
        (workspace["staging"] / "cancion-de-prueba-timeline.json").read_text(encoding="utf-8")
    )
    assert set(envelope.keys()) == {"timelineVersion", "leadIn", "timeline"}
    assert "linesHash" not in envelope
