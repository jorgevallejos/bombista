"""
B13 — migrating the two shipped v1 timelines to timeline v2.

A v1 song carries raw audio-clock times in `timeline` and no version
stamp. Migration rebases them onto the start cue: subtract `raw[0].start`
from every entry, bank it in `leadIn`, stamp `timelineVersion: 2` — the
same transformation `extract` applies to a fresh run (B12), reached
through the same functions, so there is one implementation of the rule.

Fixtures are the real shipped data:
  - `libertad-song.json`   — the v1 Auto-mode song (20 lines, no media)
  - `tragedia-v1-song.json` — the v1 Video-mode timings (29 entries,
    `media.type == "video"`; lyric texts are placeholders, see the file)
so the golden fixture in docs/timeline-v2-contract.md is asserted entry
for entry against real numbers, not synthetic ones.
"""
import json
from pathlib import Path

import pytest

from timeline_extractor.migrate import ENVELOPE_KEYS, migrate_song_to_v2

FIXTURES = Path(__file__).parent / "fixtures"


def _song(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _golden() -> dict:
    return json.loads((FIXTURES / "libertad-timeline-v2.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The two real songs
# ---------------------------------------------------------------------------


def test_libertad_migrates_to_the_golden_envelope_entry_for_entry():
    """The whole point of B13: migrating the shipped v1 Libertad reproduces
    the contract's golden fixture exactly — all 20 entries and the leadIn,
    not just line 0."""
    migrated = migrate_song_to_v2(_song("libertad-song.json"))

    golden = _golden()
    assert migrated["timelineVersion"] == golden["timelineVersion"]
    assert migrated["leadIn"] == golden["leadIn"]
    assert migrated["timeline"] == golden["timeline"]
    assert len(migrated["timeline"]) == 20


def test_libertad_leads_in_at_7_26_and_starts_at_zero():
    migrated = migrate_song_to_v2(_song("libertad-song.json"))

    assert migrated["leadIn"] == {
        "durationSec": 7.26,
        "source": "measured",
        "confidence": "low",
        "apply": False,  # Auto mode: no media block
    }
    assert migrated["timeline"][0] == {"start": 0.00, "end": 5.84}


def test_tragedia_is_video_mode_so_the_lead_in_applies():
    """`leadIn.apply` follows `media.type == "video"` — the B12 rule,
    reused rather than reimplemented."""
    migrated = migrate_song_to_v2(_song("tragedia-v1-song.json"))

    assert migrated["leadIn"] == {
        "durationSec": 0.96,
        "source": "measured",
        "confidence": "low",
        "apply": True,
    }
    assert migrated["timeline"][0] == {"start": 0.00, "end": 2.80}
    assert len(migrated["timeline"]) == 29


@pytest.mark.parametrize("name", ["libertad-song.json", "tragedia-v1-song.json"])
def test_migration_is_lossless_within_the_contract_tolerance(name):
    """Re-adding `leadIn.durationSec` reproduces every raw value within
    0.005 — tolerance, not equality: `13.1 - 7.26 == 5.840000000000001`."""
    song = _song(name)
    raw = song["timeline"]

    migrated = migrate_song_to_v2(song)

    lead_in = migrated["leadIn"]["durationSec"]
    assert len(migrated["timeline"]) == len(raw)
    for i, (before, after) in enumerate(zip(raw, migrated["timeline"])):
        assert abs((after["start"] + lead_in) - before["start"]) < 0.005, f"entry {i} start"
        assert abs((after["end"] + lead_in) - before["end"]) < 0.005, f"entry {i} end"


@pytest.mark.parametrize("name", ["libertad-song.json", "tragedia-v1-song.json"])
def test_migrated_timeline_starts_at_zero_and_is_monotonic(name):
    migrated = migrate_song_to_v2(_song(name))

    timeline = migrated["timeline"]
    assert timeline[0]["start"] == 0.00
    previous_end = 0.0
    for i, entry in enumerate(timeline):
        assert entry["start"] >= previous_end, f"entry {i} goes backwards"
        assert entry["end"] >= entry["start"], f"entry {i} ends before it starts"
        previous_end = entry["end"]


@pytest.mark.parametrize("name", ["libertad-song.json", "tragedia-v1-song.json"])
def test_every_value_is_rounded_to_two_decimals(name):
    migrated = migrate_song_to_v2(_song(name))

    for entry in migrated["timeline"]:
        for value in (entry["start"], entry["end"]):
            assert round(value, 2) == value
    assert round(migrated["leadIn"]["durationSec"], 2) == migrated["leadIn"]["durationSec"]


# ---------------------------------------------------------------------------
# Everything else survives untouched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["libertad-song.json", "tragedia-v1-song.json"])
def test_every_other_key_is_preserved_byte_for_byte_and_in_order(name):
    """A migrated song must differ from the original in the timeline and
    the two added keys — and in nothing else, down to the serialized bytes
    of every remaining value and the order they appear in."""
    song = _song(name)

    migrated = migrate_song_to_v2(song)

    def rest(d: dict) -> str:
        return json.dumps(
            {k: v for k, v in d.items() if k not in ENVELOPE_KEYS},
            indent=2,
            ensure_ascii=False,
        )

    assert rest(migrated) == rest(song)
    assert [k for k in migrated if k not in ENVELOPE_KEYS] == [
        k for k in song if k not in ENVELOPE_KEYS
    ]


def test_the_three_envelope_keys_land_where_the_v1_timeline_was():
    """`timeline` is the last key in both shipped songs, so the stamp,
    the leadIn and the timeline go at the end, in contract order."""
    migrated = migrate_song_to_v2(_song("libertad-song.json"))

    assert list(migrated)[-3:] == ["timelineVersion", "leadIn", "timeline"]


# ---------------------------------------------------------------------------
# Refusals — a wrong migration must be loud, never silent
# ---------------------------------------------------------------------------


def test_refuses_a_song_that_is_already_v2():
    """Idempotence by refusal: running it twice must not subtract the
    lead-in a second time and shift the whole song earlier."""
    once = migrate_song_to_v2(_song("libertad-song.json"))

    with pytest.raises(ValueError, match="already timeline v2"):
        migrate_song_to_v2(once)


def test_refuses_a_song_carrying_a_lead_in_without_a_version_stamp():
    """A half-stamped song is a corrupt song, not a v1 one — subtracting
    again would be silently wrong."""
    song = _song("libertad-song.json")
    song["leadIn"] = {
        "durationSec": 7.26,
        "source": "measured",
        "confidence": "low",
        "apply": False,
    }

    with pytest.raises(ValueError, match="leadIn"):
        migrate_song_to_v2(song)


@pytest.mark.parametrize("delta", [1, -1])
def test_refuses_when_the_entry_count_does_not_match_the_lyric_count(delta):
    song = _song("libertad-song.json")
    if delta > 0:
        song["timeline"] = song["timeline"] + [{"start": 200.0, "end": 201.0}]
    else:
        song["timeline"] = song["timeline"][:-1]

    with pytest.raises(ValueError, match="lyric"):
        migrate_song_to_v2(song)


@pytest.mark.parametrize("timeline", [None, []], ids=["absent", "empty"])
def test_refuses_a_song_with_no_timeline_to_migrate(timeline):
    song = _song("libertad-song.json")
    if timeline is None:
        del song["timeline"]
    else:
        song["timeline"] = timeline

    with pytest.raises(ValueError, match="timeline"):
        migrate_song_to_v2(song)


def test_refuses_a_song_with_no_lyrics_list():
    song = _song("libertad-song.json")
    del song["lyrics"]

    with pytest.raises(ValueError, match="lyrics"):
        migrate_song_to_v2(song)


def test_refuses_a_non_monotonic_v1_timeline():
    """Garbage in must not become a stamped, v2-looking song."""
    song = _song("libertad-song.json")
    song["timeline"][5], song["timeline"][6] = song["timeline"][6], song["timeline"][5]

    with pytest.raises(ValueError, match="monotonic"):
        migrate_song_to_v2(song)


def test_refuses_a_timeline_whose_entries_are_not_numbers():
    song = _song("libertad-song.json")
    song["timeline"][3] = {"start": "13.32", "end": 17.0}

    with pytest.raises(ValueError):
        migrate_song_to_v2(song)


def test_does_not_mutate_the_song_it_was_given():
    song = _song("libertad-song.json")
    before = json.dumps(song, ensure_ascii=False)

    migrate_song_to_v2(song)

    assert json.dumps(song, ensure_ascii=False) == before
