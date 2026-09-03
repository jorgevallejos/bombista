"""The canonical SP JSON skeleton (round A, item 1).

Written for `bombista new`, which wrote the skeleton a song started from.
**`new` was deleted on 2026-09-03** — `serve`'s page 1 collects the
metadata the skeleton existed to supply, and align-then-`promote` refuses
a skeleton's single placeholder lyric line against a real recording's
lines. A song starts from its words now.

**These assertions outlive the command**, because what they pin is not a
command's behaviour but the format: the required field set, the key order
`validation` and `writers` both assume, and the two absences that are
load-bearing. `song_skeleton` is reached only from here now, which is
recorded rather than hidden.
"""
from __future__ import annotations

import pytest

from bombista.skeleton import song_skeleton, title_from_song_id
from bombista.validation import REQUIRED_SONG_FIELDS, errors, validate_song


def test_the_skeleton_passes_validate():
    """The one property that makes the shape worth stating: it is already
    a legal song file."""
    assert validate_song(song_skeleton("hasta-calmar-el-alma", lang="es")) == []


def test_the_skeleton_carries_every_required_field():
    skeleton = song_skeleton("libertad", lang="es")

    for field in REQUIRED_SONG_FIELDS:
        assert field in skeleton, f"the skeleton omits the required field {field}"


def test_tempo_is_absent_not_a_placeholder():
    """`songs@c5adf65`: a missing tempo is a real state and a fake one is a
    bug that reaches a stage. `null` is not neutral once a consumer reads
    it — Pregonero degrades safely on absence and NaNs on a partial block.
    """
    assert "tempo" not in song_skeleton("libertad", lang="es")


def test_the_timing_keys_are_absent_until_bombista_writes_them():
    skeleton = song_skeleton("libertad", lang="es")

    for key in ("timelineVersion", "leadIn", "timeline", "linesHash", "timelineSignedOff"):
        assert key not in skeleton


def test_lyrics_entries_are_objects_keyed_by_language_never_strings():
    """The shape that was got wrong once (§10.2): flattening a lyric entry
    to a string destroys every translation on the round trip. The skeleton
    is what an LLM copies, so it has to show the right shape."""
    skeleton = song_skeleton("libertad", lang="nl")

    assert skeleton["lyrics"] == [{"nl": ""}]


def test_the_chosen_language_keys_the_translated_blocks():
    skeleton = song_skeleton("libertad", lang="fr")

    assert set(skeleton["title_translations"]) == {"fr"}
    assert set(skeleton["intro"]) == {"fr"}


def test_the_title_is_seeded_from_the_song_id():
    skeleton = song_skeleton("hasta-calmar-el-alma", lang="es")

    assert skeleton["title"] == "Hasta calmar el alma"
    assert skeleton["title_translations"]["es"] == "Hasta calmar el alma"


def test_an_explicit_title_wins_over_the_seed():
    skeleton = song_skeleton("la-pajita", lang="es", title="La Pajita")

    assert skeleton["title"] == "La Pajita"
    assert skeleton["title_translations"]["es"] == "La Pajita"


def test_artist_and_notes_are_empty_because_bombista_does_not_know_them():
    """§10.2.1's from-scratch shape. Empty, not omitted: they are fields a
    human fills, and an absent key says nothing to whoever fills it."""
    skeleton = song_skeleton("libertad", lang="es")

    assert skeleton["artist"] == ""
    assert skeleton["notes"] == ""


def test_the_key_order_is_the_catalogue_order():
    """§10.2 fixes the real song-file key order against
    `songs/pimiento.json`. A skeleton in another order teaches the wrong
    one to every file made from it."""
    assert list(song_skeleton("libertad", lang="es")) == [
        "title",
        "artist",
        "notes",
        "title_translations",
        "intro",
        "lyrics",
    ]


@pytest.mark.parametrize(
    "song_id,expected",
    [
        ("libertad", "Libertad"),
        ("hasta-calmar-el-alma", "Hasta calmar el alma"),
        ("no_te_voy_a_odiar", "No te voy a odiar"),
        ("  duelo  ", "Duelo"),
    ],
)
def test_title_from_song_id_deslugifies(song_id, expected):
    assert title_from_song_id(song_id) == expected


@pytest.mark.parametrize("song_id", ["", "   ", "songs/libertad", "a\\b"])
def test_a_song_id_that_cannot_name_a_file_is_refused(song_id):
    with pytest.raises(ValueError):
        song_skeleton(song_id, lang="es")


def test_a_skeleton_with_no_timeline_is_named_manual_not_refused():
    """**Reversed 2026-09-02.** A song without a timeline is performed by
    advancing the lines by hand, which is a normal night — so the
    performance gate names the mode instead of turning the song away."""
    from bombista.validation import modes

    found = validate_song(song_skeleton("libertad", lang="es"), for_performance=True)

    assert errors(found) == []
    assert [f.where for f in modes(found)] == ["timeline"]
