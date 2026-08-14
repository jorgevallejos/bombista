"""
Timeline v2 contract tests (B12) — docs/timeline-v2-contract.md.

Verifies the real build_timeline -> normalize_to_lead_in -> serializer.to_dict
path reproduces the frozen golden fixture exactly (as parsed JSON values,
not file text), that normalisation is lossless within the contract's
documented rounding tolerance, that `leadIn.apply` defaults correctly from
`media.type`, and that the envelope carries exactly its three keys.
"""
import json
from pathlib import Path

import pytest

from timeline_extractor.anchoring import LineAnchor
from timeline_extractor.models import TimelineEntry, Word
from timeline_extractor.pipeline import build_timeline, normalize_to_lead_in
from timeline_extractor.serializer import to_dict

FIXTURES = Path(__file__).parent / "fixtures"

# The 21 raw (audio-clock) boundary values from the contract's worked
# example — 20 spans, i.e. 20 lyric lines.
RAW_BOUNDARIES = [
    7.26, 13.1, 16.9, 20.58, 24.26, 27.98, 31.92, 35.48, 40.14, 44.76,
    46.84, 51.26, 55.88, 59.52, 63.38, 67.08, 70.88, 74.52, 79.92, 83.9,
    106.1,
]

LAST_LINE_PAD = 1.0


def _raw_entries() -> list[TimelineEntry]:
    """Feed the contract's 21 boundaries through the real build_timeline
    path (synthetic anchors/words standing in for a real ASR run) and
    return the resulting raw, audio-clock entries."""
    starts = RAW_BOUNDARIES[:-1]  # 20 line onsets
    last_word_end = RAW_BOUNDARIES[-1] - LAST_LINE_PAD  # -> line 19's fallback end
    items = [{"es": f"line {i}"} for i in range(len(starts))]
    anchors = [
        LineAnchor(i, s, "HIGH", ("clean-anchor",), "", 0)
        for i, s in enumerate(starts)
    ]
    words = [Word("fin", max(last_word_end - 0.3, 0.0), last_word_end)]
    return build_timeline(anchors, words, items, lang="es")


def test_golden_fixture_reproduced_exactly_through_the_real_pipeline():
    """build_timeline -> normalize_to_lead_in -> to_dict on the contract's
    21 raw boundaries produces exactly the golden envelope — compared as
    parsed JSON values (0.00 parses to 0.0), not file text."""
    entries = _raw_entries()
    lead_in, normalized = normalize_to_lead_in(entries)
    song = {"media": {"type": "audio"}}  # -> leadIn.apply == false, per the fixture

    envelope = to_dict(lead_in, normalized, song)

    expected = json.loads(
        (FIXTURES / "libertad-timeline-v2.json").read_text(encoding="utf-8")
    )
    assert envelope == expected


def test_normalisation_is_lossless_within_rounding_tolerance():
    """Re-adding leadIn.durationSec to every normalised entry reproduces
    the raw measured values within the contract's documented tolerance —
    NOT exact equality, because e.g. 13.1 - 7.26 == 5.840000000000001 in
    IEEE floats."""
    entries = _raw_entries()
    lead_in, normalized = normalize_to_lead_in(entries)

    for raw, norm in zip(entries, normalized):
        assert abs((norm.start + lead_in) - raw.start) < 0.005
        assert abs((norm.end + lead_in) - raw.end) < 0.005


@pytest.mark.parametrize(
    "song, expected_apply",
    [
        ({"media": {"type": "video"}}, True),
        ({"media": {"type": "audio"}}, False),
        ({}, False),  # media absent entirely
    ],
)
def test_lead_in_apply_defaults_from_media_type(song, expected_apply):
    entries = [TimelineEntry(0.0, 5.0), TimelineEntry(5.0, 10.0)]

    envelope = to_dict(0.0, entries, song)

    assert envelope["leadIn"]["apply"] is expected_apply


def test_envelope_has_exactly_three_top_level_keys():
    entries = [TimelineEntry(0.0, 5.0)]

    envelope = to_dict(0.0, entries, {})

    assert set(envelope.keys()) == {"timelineVersion", "leadIn", "timeline"}
