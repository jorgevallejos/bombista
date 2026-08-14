"""
Tests for the timeline v2 serializer (envelope construction + validation).

`to_dict`/`write_timeline` take an already-normalised timeline (lead-in +
entries, as produced by `pipeline.normalize_to_lead_in`) plus the song dict,
and build/validate the three-key envelope from docs/timeline-v2-contract.md.
"""
import json

import pytest

from bombista.models import TimelineEntry
from bombista.serializer import (
    to_dict,
    validate_timeline,
    validate_v2_envelope,
    write_timeline,
)

ENTRIES = [
    TimelineEntry(start=0.0, end=4.2),
    TimelineEntry(start=4.2, end=8.6),
    TimelineEntry(start=8.6, end=13.0),
]

SONG_VIDEO = {"media": {"type": "video"}}
SONG_AUDIO = {"media": {"type": "audio"}}

EXPECTED_DICT = {
    "timelineVersion": 2,
    "leadIn": {
        "durationSec": 4.1,
        "source": "measured",
        "confidence": "low",
        "apply": False,
    },
    "timeline": [
        {"start": 0.0, "end": 4.2},
        {"start": 4.2, "end": 8.6},
        {"start": 8.6, "end": 13.0},
    ],
}


# ---------------------------------------------------------------------------
# to_dict / write_timeline
# ---------------------------------------------------------------------------


def test_to_dict_builds_the_v2_envelope():
    result = to_dict(4.1, ENTRIES, SONG_AUDIO)
    assert result == EXPECTED_DICT


def test_to_dict_apply_true_for_video_media_type():
    result = to_dict(4.1, ENTRIES, SONG_VIDEO)
    assert result["leadIn"]["apply"] is True


def test_to_dict_apply_false_when_media_absent():
    result = to_dict(4.1, ENTRIES, {})
    assert result["leadIn"]["apply"] is False


def test_to_dict_rounds_lead_in_to_two_decimals():
    result = to_dict(4.123456, ENTRIES, SONG_AUDIO)
    assert result["leadIn"]["durationSec"] == 4.12


def test_write_timeline_produces_valid_json(tmp_path):
    out = tmp_path / "song-timeline.json"
    write_timeline(4.1, ENTRIES, SONG_AUDIO, out)
    parsed = json.loads(out.read_text())
    assert parsed == EXPECTED_DICT


def test_to_dict_rejects_entry_zero_not_starting_at_zero():
    bad_entries = [TimelineEntry(1.0, 4.2), TimelineEntry(4.2, 8.6)]
    with pytest.raises(ValueError):
        to_dict(1.0, bad_entries, SONG_AUDIO)


# ---------------------------------------------------------------------------
# validate_timeline — the entry-list monotonic check
# ---------------------------------------------------------------------------


def test_timeline_entry_rejects_negative_times():
    with pytest.raises(ValueError):
        TimelineEntry(start=-1.0, end=2.0)


def test_validate_rejects_zero_length_entry_out_of_order():
    """Zero-length entries are not exempt from the monotonic chain —
    section-marker support has been removed, so every entry (including a
    {0,0}-shaped one) must respect the previous entry's end."""
    entries = [
        TimelineEntry(start=4.1, end=8.3),
        TimelineEntry(start=0.0, end=0.0),  # out of order, no longer exempt
        TimelineEntry(start=8.3, end=12.7),
    ]
    with pytest.raises(ValueError):
        validate_timeline(entries)


def test_validate_still_rejects_overlapping_real_entries():
    entries = [
        TimelineEntry(start=4.1, end=8.3),
        TimelineEntry(start=7.0, end=12.7),  # overlaps the previous window
    ]
    with pytest.raises(ValueError):
        validate_timeline(entries)


# ---------------------------------------------------------------------------
# validate_v2_envelope
# ---------------------------------------------------------------------------


def _envelope(**overrides):
    base = {
        "timelineVersion": 2,
        "leadIn": {
            "durationSec": 7.26,
            "source": "measured",
            "confidence": "low",
            "apply": False,
        },
        "timeline": [{"start": 0.0, "end": 5.84}, {"start": 5.84, "end": 9.64}],
    }
    base.update(overrides)
    return base


def test_validate_v2_envelope_accepts_a_well_formed_envelope():
    validate_v2_envelope(_envelope())  # does not raise


@pytest.mark.parametrize("bad_version", [None, 1, "2", 2.0, True])
def test_validate_v2_envelope_rejects_missing_or_wrong_version(bad_version):
    envelope = _envelope()
    if bad_version is None:
        del envelope["timelineVersion"]
    else:
        envelope["timelineVersion"] = bad_version
    with pytest.raises(ValueError, match="timelineVersion"):
        validate_v2_envelope(envelope)


def test_validate_v2_envelope_rejects_extra_top_level_key():
    envelope = _envelope()
    envelope["_bombista"] = {"completeness": "partial"}
    with pytest.raises(ValueError):
        validate_v2_envelope(envelope)


@pytest.mark.parametrize(
    "field, value",
    [
        ("durationSec", -1.0),
        ("durationSec", "7.26"),
        ("source", "guessed"),
        ("confidence", "medium"),
        ("apply", "true"),
    ],
)
def test_validate_v2_envelope_rejects_bad_lead_in_field(field, value):
    envelope = _envelope()
    envelope["leadIn"] = {**envelope["leadIn"], field: value}
    with pytest.raises(ValueError):
        validate_v2_envelope(envelope)


def test_validate_v2_envelope_rejects_entry_zero_not_starting_at_zero():
    envelope = _envelope()
    envelope["timeline"] = [{"start": 0.5, "end": 5.0}]
    with pytest.raises(ValueError, match="timeline\\[0\\]"):
        validate_v2_envelope(envelope)


def test_validate_v2_envelope_rejects_a_version_2_file_with_no_timeline():
    """Contract amendment 2026-08-13: a file that declares version 2 and
    carries no timeline is malformed — truncated or half-written — not an
    untimed song. Accepting it would make the song look silently untimed."""
    envelope = _envelope()
    envelope["timeline"] = []
    with pytest.raises(ValueError, match="incomplete"):
        validate_v2_envelope(envelope)


def test_validate_v2_envelope_rejects_non_monotonic_timeline():
    envelope = _envelope()
    envelope["timeline"] = [{"start": 0.0, "end": 8.0}, {"start": 4.0, "end": 9.0}]
    with pytest.raises(ValueError):
        validate_v2_envelope(envelope)
