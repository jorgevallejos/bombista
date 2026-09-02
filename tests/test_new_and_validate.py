"""`bombista new` and `bombista validate` at the terminal (round A).

The three jobs that had no home before this round: supplying a tempo,
checking a song file is well-formed, and creating one. All three belong in
Bombista, because it is already the only thing that writes SP JSON.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from bombista.cli import main

REAL_TEMPO = {"bpm": 66.67, "numerator": 6, "denominator": 8, "countInBars": 1}


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def song(**overrides) -> dict:
    base = {
        "title": "Libertad",
        "artist": "Chango Pepper",
        "notes": "",
        "title_translations": {"es": "Libertad"},
        "lyrics": [{"es": "uno"}, {"es": "dos"}],
    }
    base.update(overrides)
    return base


def write(tmp_path, data, name="libertad.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


def test_new_writes_a_skeleton_to_stdout(runner):
    result = runner.invoke(main, ["new", "hasta-calmar-el-alma"])

    assert result.exit_code == 0
    skeleton = json.loads(result.output)
    assert skeleton["title"] == "Hasta calmar el alma"
    assert skeleton["lyrics"] == [{"es": ""}]


def test_new_writes_to_a_named_path(runner, tmp_path):
    out = tmp_path / "libertad.json"

    result = runner.invoke(main, ["new", "libertad", "-o", str(out)])

    assert result.exit_code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["title"] == "Libertad"
    assert str(out) in result.output


def test_new_refuses_to_overwrite_an_existing_file(runner, tmp_path):
    out = write(tmp_path, song())

    result = runner.invoke(main, ["new", "libertad", "-o", str(out)])

    assert result.exit_code != 0
    assert json.loads(out.read_text(encoding="utf-8"))["artist"] == "Chango Pepper"


def test_what_new_writes_passes_validate(runner, tmp_path):
    out = tmp_path / "libertad.json"
    runner.invoke(main, ["new", "libertad", "-o", str(out)])

    result = runner.invoke(main, ["validate", str(out)])

    assert result.exit_code == 0, result.output


def test_new_honours_the_language(runner):
    result = runner.invoke(main, ["new", "libertad", "--lang", "nl"])

    assert json.loads(result.output)["lyrics"] == [{"nl": ""}]


def test_new_takes_an_explicit_title(runner):
    result = runner.invoke(main, ["new", "la-pajita", "--title", "La Pajita"])

    assert json.loads(result.output)["title"] == "La Pajita"


def test_new_refuses_a_song_id_that_cannot_name_a_file(runner):
    result = runner.invoke(main, ["new", "songs/libertad"])

    assert result.exit_code != 0


def test_new_help_states_the_whole_flow(runner):
    """The reason the pipeline has silent failures today is that the first
    step is folklore. `--help` is where that stops being true."""
    result = runner.invoke(main, ["new", "--help"])

    for step in ("bombista new", "align", "validate"):
        assert step in result.output


# ---------------------------------------------------------------------------
# validate — the default level
# ---------------------------------------------------------------------------


def test_a_sane_song_passes_quietly(runner, tmp_path):
    result = runner.invoke(main, ["validate", str(write(tmp_path, song()))])

    assert result.exit_code == 0
    assert "ok" in result.output


def test_a_broken_song_exits_non_zero(runner, tmp_path):
    broken = song(lyrics=[{"es": "uno"}, {"en": "two"}])

    result = runner.invoke(main, ["validate", str(write(tmp_path, broken))])

    assert result.exit_code == 1
    assert "lyrics[1]" in result.output


def test_every_problem_is_listed_not_just_the_first(runner, tmp_path):
    broken = song(lyrics=[{"es": "[Coro]"}, 7], tempo={"bpm": 100})

    result = runner.invoke(main, ["validate", str(write(tmp_path, broken))])

    assert result.exit_code == 1
    for where in ("lyrics[0]", "lyrics[1]", "tempo.numerator", "tempo.denominator"):
        assert where in result.output


def test_malformed_json_is_a_message_not_a_traceback(runner, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ nope", encoding="utf-8")

    result = runner.invoke(main, ["validate", str(path)])

    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "not valid JSON" in result.output


def test_validate_honours_the_language(runner, tmp_path):
    dutch = song(lyrics=[{"nl": "een"}, {"nl": "twee"}])

    assert runner.invoke(main, ["validate", str(write(tmp_path, dutch))]).exit_code == 1
    assert (
        runner.invoke(
            main, ["validate", str(write(tmp_path, dutch)), "--lang", "nl"]
        ).exit_code
        == 0
    )


# ---------------------------------------------------------------------------
# validate --for-performance
# ---------------------------------------------------------------------------


def timed(**overrides) -> dict:
    timing = {
        "timelineVersion": 2,
        "leadIn": {
            "durationSec": 0.0,
            "source": "measured",
            "confidence": "low",
            "apply": False,
        },
        "timeline": [{"start": 0.0, "end": 2.0}, {"start": 2.0, "end": 4.0}],
    }
    timing.update(overrides)
    return song(**timing)


def test_for_performance_names_the_mode_of_a_song_with_no_timeline(runner, tmp_path):
    """**Reversed 2026-09-02**, and the exit code is the point: a manual
    song is performable, so the gate must not fail. What it prints becomes
    a claim about WHICH performance."""
    result = runner.invoke(
        main, ["validate", str(write(tmp_path, song(tempo=REAL_TEMPO))), "--for-performance"]
    )

    assert result.exit_code == 0
    assert "manual only: no timeline" in result.output


def test_for_performance_passes_a_finished_song(runner, tmp_path):
    result = runner.invoke(
        main, ["validate", str(write(tmp_path, timed(tempo=REAL_TEMPO))), "--for-performance"]
    )

    assert result.exit_code == 0, result.output


def test_a_missing_tempo_warns_and_still_passes(runner, tmp_path):
    result = runner.invoke(
        main, ["validate", str(write(tmp_path, timed())), "--for-performance"]
    )

    assert result.exit_code == 0, result.output
    assert "warning" in result.output.lower()
    assert "tempo" in result.output


def test_unresolvable_media_fails_and_names_where_it_looked(runner, tmp_path):
    with_media = timed(tempo=REAL_TEMPO, media={"type": "video", "src": "gone.mp4"})

    result = runner.invoke(
        main, ["validate", str(write(tmp_path, with_media)), "--for-performance"]
    )

    assert result.exit_code == 1
    assert "gone.mp4" in result.output
    assert str(tmp_path) in result.output


def test_media_dir_is_where_the_gate_is_told_to_look(runner, tmp_path):
    videos = tmp_path / "video"
    videos.mkdir()
    (videos / "cerdo.mp4").write_bytes(b"\x00")
    with_media = timed(tempo=REAL_TEMPO, media={"type": "video", "src": "cerdo.mp4"})

    result = runner.invoke(
        main,
        [
            "validate",
            str(write(tmp_path, with_media)),
            "--for-performance",
            "--media-dir",
            str(videos),
        ],
    )

    assert result.exit_code == 0, result.output


def test_validate_help_says_what_the_two_levels_ask(runner):
    result = runner.invoke(main, ["validate", "--help"])

    assert "--for-performance" in result.output
    assert "setlist" in result.output
