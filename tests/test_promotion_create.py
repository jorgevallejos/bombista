"""**`promote` landing a song that does not exist yet.**

Until this, a song made from a lyrics `.txt` and a recording could not be
finished at all. `align --emit songjson` writes a complete song file, but
into the *staging* directory; `promote` declared its target
`click.Path(exists=True)` and merged only the envelope keys, so it could
neither create `songs/<id>.json` nor carry the words into a `bombista new`
skeleton; and `back_up_and_replace` copied the original before replacing
it, so it threw on a target that was not there. Pregonero must not close
the gap itself — it never writes a song file.

**Creating is the narrow case, and the guards are the point.** Two
conditions, both refusals rather than judgement calls: the candidate must
be a full `--emit songjson`, and the target must be the canonical name for
that candidate. Promotion stays the one write path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bombista.promotion import promote_candidate


def envelope() -> dict:
    return {
        "timelineVersion": 2,
        "leadIn": {"durationSec": 1.0, "source": "measured", "confidence": "low", "apply": False},
        "timeline": [{"start": 0.0, "end": 2.0}],
    }


def full_candidate(**over) -> dict:
    """What `align --emit songjson` writes: a whole song plus `_bombista`."""
    data = {
        "title": "Libertad",
        "artist": "Chango Pepper",
        "lyrics": [{"es": "una línea"}],
        **envelope(),
        "_bombista": {
            "linesHash": "abc",
            "completeness": "partial",
            "source": {"lang": "es"},
        },
    }
    data.update(over)
    return data


def write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_creates_the_song_when_the_target_does_not_exist(tmp_path: Path):
    candidate = write(tmp_path / "libertad-song.json", full_candidate())
    target = tmp_path / "songs" / "libertad.json"

    outcome = promote_candidate(candidate, target)

    assert target.exists()
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["title"] == "Libertad"
    assert written["lyrics"] == [{"es": "una línea"}]
    assert written["timeline"] == [{"start": 0.0, "end": 2.0}]
    # Nothing to back up, so nothing was backed up — and that is said rather
    # than a path invented for it.
    assert outcome.backup is None


def test_the_created_song_is_an_ordinary_song_file(tmp_path: Path):
    """No `_bombista` block. Provenance belongs in staging, not in the
    catalogue: a created song has to be shaped like every hand-made one, or
    the catalogue has two kinds of song file in it."""
    candidate = write(tmp_path / "libertad-song.json", full_candidate())
    target = tmp_path / "libertad.json"

    promote_candidate(candidate, target)

    assert "_bombista" not in json.loads(target.read_text(encoding="utf-8"))


def test_refuses_to_create_from_a_bare_timeline_envelope(tmp_path: Path):
    """A bare envelope is three keys. There is nothing to create a song out
    of, and merging into a file that is not there is not a thing."""
    candidate = write(tmp_path / "libertad-timeline.json", envelope())
    target = tmp_path / "libertad.json"

    with pytest.raises(ValueError) as exc:
        promote_candidate(candidate, target)

    assert "does not exist" in str(exc.value)
    assert not target.exists()


def test_refuses_to_create_under_a_name_that_is_not_the_canonical_one(tmp_path: Path):
    """The target is `<stem>.json` for a candidate `<stem>-song.json`, and
    nothing else. The id of a song IS its filename, so a free choice of
    target name is a free choice of id — which is exactly the decision this
    suite removes rather than explains."""
    candidate = write(tmp_path / "libertad-song.json", full_candidate())
    target = tmp_path / "something-else.json"

    with pytest.raises(ValueError) as exc:
        promote_candidate(candidate, target)

    assert "libertad.json" in str(exc.value)
    assert not target.exists()


def test_creates_the_parent_folder_when_it_is_missing(tmp_path: Path):
    candidate = write(tmp_path / "duelo-song.json", full_candidate())
    target = tmp_path / "a" / "b" / "duelo.json"

    promote_candidate(candidate, target)

    assert target.exists()


def test_an_existing_target_still_takes_the_old_path(tmp_path: Path):
    """Creating is a branch, not a replacement. An existing song is still
    backed up and still has only its envelope keys merged."""
    candidate = write(tmp_path / "duelo-song.json", full_candidate(title="Not this"))
    target = write(
        tmp_path / "duelo.json",
        {"title": "Duelo", "artist": "Chango Pepper", "lyrics": [{"es": "otra"}]},
    )

    outcome = promote_candidate(candidate, target)

    written = json.loads(target.read_text(encoding="utf-8"))
    assert outcome.backup is not None and outcome.backup.exists()
    # The title and the words are the target's, untouched: promote merges the
    # envelope and nothing else onto a song that already exists.
    assert written["title"] == "Duelo"
    assert written["lyrics"] == [{"es": "otra"}]
    assert written["timeline"] == [{"start": 0.0, "end": 2.0}]


def test_the_lyrics_count_guard_still_applies_when_creating(tmp_path: Path):
    """The candidate's own timeline must match its own lyrics. A song
    created with a timeline that does not describe its words is exactly the
    failure `libertad` is the standing example of."""
    candidate = write(
        tmp_path / "libertad-song.json",
        full_candidate(lyrics=[{"es": "una"}, {"es": "dos"}]),
    )
    target = tmp_path / "libertad.json"

    with pytest.raises(ValueError) as exc:
        promote_candidate(candidate, target)

    assert "lyrics item count" in str(exc.value)
    assert not target.exists()


def test_a_v1_candidate_is_refused_before_anything_is_written(tmp_path: Path):
    candidate = write(
        tmp_path / "libertad-song.json",
        full_candidate(timelineVersion=1),
    )
    target = tmp_path / "libertad.json"

    with pytest.raises(ValueError):
        promote_candidate(candidate, target)

    assert not target.exists()


def test_the_lines_hash_guard_does_not_fire_when_creating(tmp_path: Path, capsys):
    """The guard asks whether the TARGET's lyrics moved on since extraction.
    A song that did not exist has no such history, and its lyrics are the
    candidate's own by construction — so the guard's message ("the lyrics
    changed since this timeline was extracted") would be untrue, and would
    send the reader to re-run `align` for no reason."""
    notes: list[str] = []
    candidate = write(tmp_path / "libertad-song.json", full_candidate())
    promote_candidate(candidate, tmp_path / "libertad.json", note=notes.append)

    joined = " ".join(notes)
    assert "does not apply" in joined
    assert "lyrics changed" not in joined


def test_a_created_song_reports_its_timeline_as_added(tmp_path: Path):
    """`song` IS the candidate on the create path, so reading its timeline
    as the "old" one compares it against itself and reports no changes —
    about a song that has just been given a timeline."""
    candidate = write(tmp_path / "libertad-song.json", full_candidate())
    outcome = promote_candidate(candidate, tmp_path / "libertad.json")
    assert outcome.diff == ["timeline added (1 entries)"]
