"""
Round-trip test for the timeline serializer.
Status: RED — to_dict() raises NotImplementedError until implemented.
"""
import json
import pytest

from timeline_extractor.models import TimelineEntry
from timeline_extractor.serializer import to_dict, write_timeline


ENTRIES = [
    TimelineEntry(start=0.0, end=0.0),   # section-marker placeholder
    TimelineEntry(start=4.1, end=8.3),
    TimelineEntry(start=8.3, end=12.7),
]

EXPECTED_DICT = {
    "timeline": [
        {"start": 0.0, "end": 0.0},
        {"start": 4.1, "end": 8.3},
        {"start": 8.3, "end": 12.7},
    ]
}


def test_to_dict_round_trips_to_expected_shape():
    """Known entries produce the exact interchange dict the translator expects."""
    result = to_dict(ENTRIES)
    assert result == EXPECTED_DICT


def test_write_timeline_produces_valid_json(tmp_path):
    """write_timeline writes a parseable JSON file with the correct shape."""
    out = tmp_path / "tragedia.timeline.json"
    write_timeline(ENTRIES, out)
    parsed = json.loads(out.read_text())
    assert parsed == EXPECTED_DICT


def test_timeline_entry_rejects_negative_times():
    with pytest.raises(ValueError):
        TimelineEntry(start=-1.0, end=2.0)
