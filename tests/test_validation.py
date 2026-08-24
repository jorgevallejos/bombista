"""`bombista validate` — the gate, as a pure function (round A, item 2).

Two strictness levels. The default asks *is this file sane* and must
tolerate work in progress: a song fresh from `bombista new` has no
timeline yet and must still be savable. `--for-performance` asks *is this
song finished* and is what a song must pass before it can be put in a
setlist.

**Playability is checked here and not in Pregonero.** Every rule below
lives inside a single song file and needs no gig. Two implementations of
these rules would be two understandings of SP JSON, and the second would
go stale the moment the first changed.
"""
from __future__ import annotations

import json

import pytest

from bombista.validation import (
    Finding,
    errors,
    load_and_validate,
    validate_song,
    validate_tempo,
    warnings,
)

REAL_TEMPO = {"bpm": 66.67, "numerator": 6, "denominator": 8, "countInBars": 1}


def song(**overrides) -> dict:
    """A catalogue-shaped song: the keys every file in `songs/` carries."""
    base = {
        "title": "Libertad",
        "artist": "Chango Pepper",
        "notes": "Capo 3, Acordes de LA",
        "title_translations": {"es": "Libertad", "en": "Freedom"},
        "intro": {"es": "Una canción."},
        "lyrics": [{"es": "uno"}, {"es": "dos"}, {"es": "tres"}],
    }
    base.update(overrides)
    return base


def timed(**overrides) -> dict:
    """The same song, with a valid v2 timeline over its three lines."""
    timing = {
        "timelineVersion": 2,
        "leadIn": {
            "durationSec": 1.0,
            "source": "measured",
            "confidence": "low",
            "apply": False,
        },
        "timeline": [
            {"start": 0.0, "end": 2.0},
            {"start": 2.0, "end": 4.0},
            {"start": 4.0, "end": 6.0},
        ],
    }
    timing.update(overrides)
    return song(**timing)


def wheres(findings, severity=None):
    return [f.where for f in findings if severity is None or f.severity == severity]


def joined(findings) -> str:
    return "\n".join(f"{f.where}: {f.message}" for f in findings)


# ---------------------------------------------------------------------------
# the default level — is this file sane
# ---------------------------------------------------------------------------


def test_a_catalogue_shaped_song_passes():
    assert validate_song(song()) == []


def test_a_song_with_a_real_timeline_and_a_real_tempo_passes():
    assert validate_song(timed(tempo=REAL_TEMPO)) == []


def test_a_song_with_no_timeline_and_no_tempo_passes_the_default_level():
    """Work in progress is savable. Ten of thirteen songs looked like this
    the day this gate was written."""
    assert validate_song(song()) == []


def test_every_problem_is_reported_not_just_the_first():
    """A person fixing a file wants all of it at once."""
    broken = song(
        lyrics=[{"es": "uno"}, "dos", {"es": "[Estribillo]"}],
        tempo={"bpm": 0},
    )
    del broken["artist"]

    found = errors(validate_song(broken))

    assert len(found) >= 5, joined(found)
    assert "artist" in wheres(found)
    assert "lyrics[1]" in wheres(found)
    assert "lyrics[2]" in wheres(found)


# --- required fields, per the skeleton `new` writes ------------------------


@pytest.mark.parametrize("field", ["title", "artist", "notes", "title_translations", "lyrics"])
def test_a_missing_required_field_is_an_error_naming_it(field):
    incomplete = song()
    del incomplete[field]

    found = errors(validate_song(incomplete))

    assert wheres(found) == [field]


def test_intro_is_not_required():
    """`serve`'s from-scratch branch cannot supply one (§10.2.1), so a file
    without it is not malformed."""
    without = song()
    del without["intro"]

    assert validate_song(without) == []


def test_lyrics_must_be_a_list():
    found = errors(validate_song(song(lyrics={"es": "uno"})))

    assert wheres(found) == ["lyrics"]
    assert "list" in joined(found)


# --- lyric items and section markers --------------------------------------


def test_an_item_that_is_not_a_lyric_line_is_an_error_naming_its_index():
    found = errors(validate_song(song(lyrics=[{"es": "uno"}, 42, {"es": "tres"}])))

    assert wheres(found) == ["lyrics[1]"]


def test_an_item_missing_the_chosen_language_key_is_an_error():
    found = errors(validate_song(song(lyrics=[{"es": "uno"}, {"en": "two"}])))

    assert wheres(found) == ["lyrics[1]"]


def test_a_section_marker_in_the_lyrics_array_is_an_error_that_says_so():
    """Lyrics arrays carry sung lines only — the contract, both sides."""
    found = errors(validate_song(song(lyrics=[{"es": "[Estribillo]"}, {"es": "uno"}])))

    assert wheres(found) == ["lyrics[0]"]
    assert "section marker" in joined(found)


def test_a_lyric_line_that_merely_contains_a_bracket_is_not_a_marker():
    assert validate_song(song(lyrics=[{"es": "un [suspiro] largo"}])) == []


# --- tempo: whole, or not written at all (§11.5) ---------------------------


def test_a_whole_tempo_block_passes():
    assert validate_tempo(REAL_TEMPO) == []


def test_an_absent_tempo_is_not_an_error_at_the_default_level():
    assert validate_song(song()) == []


def test_a_bpm_only_tempo_block_is_refused_naming_every_missing_key():
    """§11.5, proved against Pregonero: `beatScheduler.ts` requires
    `numerator` and `denominator`, and `getBeatsPerBar` does `numerator %
    3`, so a bpm-only block gives NaN beats — correct scaling, broken
    pulse, no error anywhere. There is no valid partial tempo block."""
    found = errors(validate_song(song(tempo={"bpm": 128})))

    assert wheres(found) == ["tempo.numerator", "tempo.denominator", "tempo.countInBars"]


@pytest.mark.parametrize("key", ["bpm", "numerator", "denominator"])
@pytest.mark.parametrize("value", [0, -4, "four", None, True])
def test_a_tempo_value_that_is_not_positive_and_real_is_refused(key, value):
    block = dict(REAL_TEMPO)
    block[key] = value

    found = errors(validate_song(song(tempo=block)))

    assert wheres(found) == [f"tempo.{key}"]


def test_count_in_bars_may_be_zero():
    """Zero count-in bars is a real answer — the one tempo field that is
    legitimately not positive."""
    assert validate_tempo({**REAL_TEMPO, "countInBars": 0}) == []


@pytest.mark.parametrize("value", [-1, 1.5, "one", None])
def test_count_in_bars_must_be_a_whole_number_of_bars(value):
    found = errors(validate_tempo({**REAL_TEMPO, "countInBars": value}))

    assert wheres(found) == ["tempo.countInBars"]


def test_a_tempo_that_is_not_an_object_is_refused():
    found = errors(validate_song(song(tempo=128)))

    assert wheres(found) == ["tempo"]


def test_an_unknown_key_inside_tempo_is_refused():
    found = errors(validate_tempo({**REAL_TEMPO, "swing": 0.6}))

    assert wheres(found) == ["tempo.swing"]


# --- media ----------------------------------------------------------------


def test_declared_media_that_does_not_resolve_is_an_error(tmp_path):
    found = errors(
        validate_song(
            song(media={"type": "video", "src": "missing.mp4"}),
            song_path=tmp_path / "libertad.json",
        )
    )

    assert wheres(found) == ["media.src"]
    assert "missing.mp4" in joined(found)
    assert str(tmp_path) in joined(found), "the message must name where it looked"


def test_media_resolves_beside_the_song_file(tmp_path):
    (tmp_path / "cerdo.mp4").write_bytes(b"\x00")

    assert (
        validate_song(
            song(media={"type": "video", "src": "cerdo.mp4"}),
            song_path=tmp_path / "libertad.json",
        )
        == []
    )


def test_media_resolves_through_a_media_dir(tmp_path):
    """`media.src` is a logical filename — Pregonero keeps a per-machine
    map of where it actually lives — so the gate has to be told."""
    videos = tmp_path / "video"
    videos.mkdir()
    (videos / "cerdo.mp4").write_bytes(b"\x00")

    assert (
        validate_song(
            song(media={"type": "video", "src": "cerdo.mp4"}),
            song_path=tmp_path / "libertad.json",
            media_dirs=[videos],
        )
        == []
    )


def test_an_absolute_media_src_is_used_as_given(tmp_path):
    video = tmp_path / "cerdo.mp4"
    video.write_bytes(b"\x00")

    assert validate_song(song(media={"type": "video", "src": str(video)})) == []


def test_media_without_a_src_is_an_error():
    found = errors(validate_song(song(media={"type": "video"})))

    assert wheres(found) == ["media.src"]


def test_media_is_not_checked_when_absent():
    assert validate_song(song()) == []


# --- the timeline keys ----------------------------------------------------


def test_a_timeline_version_other_than_two_is_refused():
    found = errors(validate_song(timed(timelineVersion=1)))

    assert wheres(found) == ["timelineVersion"]
    assert "2" in joined(found)


def test_a_declared_v2_timeline_that_is_empty_is_refused():
    found = errors(validate_song(timed(timeline=[])))

    assert wheres(found) == ["timeline"]
    assert "no timeline" in joined(found)


def test_a_timeline_without_a_version_is_refused_as_a_v1_leftover():
    """The contract: `timelineVersion` absent → reject loudly, never
    coerce. This is the half-stamped file `migrate` refuses too."""
    half = timed()
    del half["timelineVersion"]

    found = errors(validate_song(half))

    assert "timelineVersion" in wheres(found)


def test_a_timeline_entry_count_that_disagrees_with_the_lyrics_is_refused():
    found = errors(validate_song(timed(timeline=[{"start": 0.0, "end": 2.0}])))

    assert wheres(found) == ["timeline"]
    assert "1" in joined(found) and "3" in joined(found)


def test_a_timeline_that_does_not_start_at_zero_is_refused():
    found = errors(
        validate_song(
            timed(
                timeline=[
                    {"start": 1.0, "end": 2.0},
                    {"start": 2.0, "end": 4.0},
                    {"start": 4.0, "end": 6.0},
                ]
            )
        )
    )

    assert wheres(found) == ["timeline"]


def test_a_song_with_neither_timeline_nor_version_is_a_normal_untimed_song():
    """The 11-song regression case, named in the contract."""
    assert validate_song(song()) == []


# ---------------------------------------------------------------------------
# --for-performance — is this song finished
# ---------------------------------------------------------------------------


def test_a_finished_song_passes_for_performance(tmp_path):
    video = tmp_path / "cerdo.mp4"
    video.write_bytes(b"\x00")
    finished = timed(tempo=REAL_TEMPO, media={"type": "video", "src": "cerdo.mp4"})

    found = validate_song(
        finished, song_path=tmp_path / "libertad.json", for_performance=True
    )

    assert found == []


def test_a_missing_timeline_is_a_hard_failure_for_performance():
    """Nothing can be displayed without one."""
    found = errors(validate_song(song(tempo=REAL_TEMPO), for_performance=True))

    assert wheres(found) == ["timeline"]


def test_a_song_fresh_from_new_passes_the_default_level_and_fails_for_performance():
    from bombista.skeleton import song_skeleton

    fresh = song_skeleton("hasta-calmar-el-alma", lang="es")

    assert validate_song(fresh) == []
    assert errors(validate_song(fresh, for_performance=True)) != []


def test_a_missing_tempo_is_a_warning_for_performance_not_a_failure():
    """Pedal-driven mode works without one. Only the beat indicator, the
    count-in and clock-driven mode need it."""
    found = validate_song(timed(), for_performance=True)

    assert errors(found) == []
    assert wheres(warnings(found)) == ["tempo"]


def test_a_partial_tempo_is_still_a_hard_failure_for_performance():
    """The warning is for an absent block. A present-but-broken one is the
    thing §11.5 exists to stop."""
    found = errors(validate_song(timed(tempo={"bpm": 128}), for_performance=True))

    assert found != []


def test_unresolvable_media_is_a_hard_failure_for_performance(tmp_path):
    found = errors(
        validate_song(
            timed(tempo=REAL_TEMPO, media={"type": "video", "src": "gone.mp4"}),
            song_path=tmp_path / "libertad.json",
            for_performance=True,
        )
    )

    assert wheres(found) == ["media.src"]


def test_a_lines_hash_that_no_longer_matches_the_lyrics_is_a_warning():
    """B4's guard, at the gate. `promote` warns rather than blocks and this
    keeps the same stance — the timeline may still be right, and only a
    human can say."""
    stale = timed(tempo=REAL_TEMPO, linesHash="sha256:" + "0" * 64)

    found = validate_song(stale, for_performance=True)

    assert errors(found) == []
    assert wheres(warnings(found)) == ["linesHash"]


def test_a_lines_hash_that_matches_is_silent():
    from bombista.provenance import compute_lines_hash

    matching = timed(tempo=REAL_TEMPO, linesHash=compute_lines_hash(["uno", "dos", "tres"]))

    assert validate_song(matching, for_performance=True) == []


# ---------------------------------------------------------------------------
# loading — malformed JSON is a finding, not a traceback
# ---------------------------------------------------------------------------


def test_malformed_json_is_one_finding(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")

    found = load_and_validate(path)

    assert [f.severity for f in found] == ["error"]
    assert "not valid JSON" in joined(found)


def test_a_json_file_that_is_not_an_object_is_one_finding(tmp_path):
    path = tmp_path / "array.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    found = load_and_validate(path)

    assert [f.severity for f in found] == ["error"]


def test_load_and_validate_finds_media_beside_the_file(tmp_path):
    (tmp_path / "cerdo.mp4").write_bytes(b"\x00")
    path = tmp_path / "libertad.json"
    path.write_text(
        json.dumps(song(media={"type": "video", "src": "cerdo.mp4"})), encoding="utf-8"
    )

    assert load_and_validate(path) == []


def test_findings_are_hashable_and_comparable():
    assert Finding("error", "tempo", "x") == Finding("error", "tempo", "x")
